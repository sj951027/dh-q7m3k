#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lowvol_score.py — 저변동·우량·반전 트랙 점수 관측 적재 (LOWVOL_TRACK 1단계)

설계: LOWVOL_TRACK_DESIGN.md
- 유니버스: 중간 과매도(30≤oversold_score<70) + 유동성 하한(amt_avg_1m_억≥5)
- 점수: 4개 model_id (2×2 대조), run 내 cross-sectional 백분위 순위합
    lv_a = 저변동 + ROE + 반전     (저변동, 반전 포함)
    lv_b = 저변동 + ROE            (저변동, 반전 제외)
    lv_c = 낙폭   + ROE + 반전     (낙폭,   반전 포함)
    lv_d = 낙폭   + ROE            (낙폭,   반전 제외)
- 가중치 0 관측: 점수는 계산·저장만. 추천/표시엔 사용 안 함(검증 전).
- PIT 안전: 순위는 (run_id, market) 그룹 내에서만 매김. 미래 정보 미사용.
- 적재: 테이블 lowvol_scores (append-only, spec_hash). v3_scores 패턴 준용.

불변규칙(설계 §5): v3/large 테이블 미수정. 매직넘버 금지(유동성 하한은 분포 근거).
post-hoc(설계 §5-6): 이 신호는 사후발견 → forward-only. in-sample 수치는 가설.

Claude는 네트워크 없음. 이 스크립트는 stage3_final만 읽으므로 신규 API 호출 0.
사용자가 실행 후 로그+zip 제공 → Claude 오프라인 검증.
"""
import sqlite3, argparse, hashlib, json, sys
from datetime import datetime, timezone, timedelta

DB = "history.db"
# 수급·공매도는 ohlcv.db(전체 종목 raw)로 이전(§21-8 Phase1). short_flows 를 거기서 읽음.
# 없으면(구 환경) history.db 의 short_flows 로 폴백 — 0-diff 보장.
OHLCV_DB = "../dh-q7m3k-data/ohlcv.db"
KST = timezone(timedelta(hours=9))

# ---- 유니버스 파라미터 (전부 데이터 근거, 매직넘버 아님) ----
OVERSOLD_LO = 30.0   # 중간 과매도 하한 (극단 미만 = 반전 살아있는 구간)
OVERSOLD_HI = 70.0   # 중간 과매도 상한 (70+ = 반전 IC 반토막, 칼날)
LIQ_FLOOR   = 5.0    # 유동성 하한(억). 중간대 중앙값 10.4억의 절반, 하위25%(2.8억) 위.

# ---- 모델 spec: (사용 팩터, ascending) ----
# ascending 의미: True=큰값에 높은 백분위. "큰값=좋음"이면 True, "작은값=좋음"이면 False.
#   realized_vol: 작은값(저변동)=좋음 → False
#   drawdown_52w_high_%: 부호 확인됨 큰낙폭=높은초과수익 → 원시IC +0.129 → 큰값=좋음 → True
#   roe_value: 큰값=좋음 → True
#   return_1w_%(반전): 작은값(지난주 패자)=좋음 → False
FACTORS = {
    "realized_vol":         ("realized_vol",        False),
    "roe":                  ("roe_value",           True),
    "drawdown":             ('"drawdown_52w_high_%"', True),
    "reversal":             ('"return_1w_%"',       False),
    # ---- 고변동(highvol) 관측 팩터 (2026-06-27 추가) ----
    # realized_vol 과 '같은 컬럼·반대 방향'(ascending=True = 변동성 클수록 좋음).
    #   hv_a(고변동 대박 챌린저)용. lv_a 의 저변동을 정확히 뒤집은 대척점.
    #   가설: 상승장에선 고변동이 크게 튐(상승 run 4개서 >+5% 비율 40% vs 저변동 24%).
    #   단 하락장 손실 더 큼(-12.66% vs -8.23%), 예측 1.8배 어려움 → forward 검증 필수.
    "highvol":              ("realized_vol",        True),
    # ---- 상승포착(momentum) 대조 관측용 팩터 (2026-06-27 추가) ----
    # lowvol과 '정반대 방향' 신호. 오프라인 분석에서 forward 5d 시장초과 IC 양수 확인:
    #   vs_SMA20_%(+0.141)·return_1m_%(+0.125)·vol_1w_vs_1m_ratio(+0.089).
    # 전부 '큰값=좋음'(20일선 위·1개월 모멘텀↑·거래량 팽창↑) → ascending=True.
    # 커버리지 100%(과매도30~70 유니버스 내) → 핵심팩터 NaN 문제 없음.
    "sma20":                ('"vs_SMA20_%"',        True),
    "mom_1m":               ('"return_1m_%"',       True),
    "vol_exp":              ("vol_1w_vs_1m_ratio",  True),
    # ---- 공매도 관측 팩터 (2026-06-27 추가) ----
    # short_flows 테이블에서 LEFT JOIN으로 가져옴(stage3엔 없음). 공매도 비중 낮을수록 좋음.
    #   오프라인 페어비교: lv_a에 더하면 ΔIC +0.034(CI 0밖, 주로 코스닥). 단 run 10개 가설.
    #   '공매도 적은 저변동 우량주'가 '공매도 많은' 것보다 나음(공매도×고변동 -1.08% 최악).
    #   ⚠️ 보조 팩터로만 사용(핵심 불가) — short_flows 커버리지가 lv 종목의 일부라
    #      핵심으로 쓰면 공매도 없는 종목이 전부 제외돼 유니버스가 깨짐.
    "short":                ("short_vol_ratio",     False),
    # ---- 저회전율(turnover) 관측 팩터 (2026-08-29 추가, lv_e 용) ----
    # to20 = 최근 20거래일 평균 (거래량 / 상장주식수). 낮을수록(=조용할수록) 선호 → False.
    #   출처: ohlcv.db daily_ohlcv(volume, shares) — stage3_final 에 없어 LEFT JOIN(short 와 동일 패턴).
    #   근거: research/RESEARCH_lv_ablation_20260812.md V6 — lv_b 짝비교 diff h5/h10/h20 모두 CI>0.
    #   ⚠️ 보조 팩터 전용(핵심 불가): 커버리지 결손 시 NaN=0.5 중립으로 유니버스 보존.
    "to20":                 ("to20",                False),
}

# 모델 = {팩터리스트, 유니버스(os_lo, os_hi, liq)}.
# 원본 lv_a~d: 공통 유니버스(OVERSOLD_LO/HI/LIQ_FLOOR). 변형은 유니버스만 다름.
# 변형 추가가 원본 spec_hash를 안 바꾸도록 spec_hash는 모델별로 계산(아래).
DEFAULT_UNI = (OVERSOLD_LO, OVERSOLD_HI, LIQ_FLOOR)   # (30, 70, 5)
MODELS = {
    "lv_a":  {"factors": ["realized_vol", "roe", "reversal"], "uni": DEFAULT_UNI},
    "lv_b":  {"factors": ["realized_vol", "roe"],             "uni": DEFAULT_UNI},
    "lv_c":  {"factors": ["drawdown", "roe", "reversal"],     "uni": DEFAULT_UNI},
    "lv_d":  {"factors": ["drawdown", "roe"],                 "uni": DEFAULT_UNI},
    # ---- 미세조정 변형 (관찰용, 원본 불변) ----
    # lv_a3: lv_a와 점수식 동일, 유니버스만 과매도 상한 60으로 좁힘(30~60).
    #   근거: 민감도 분석서 상한 좁힐수록 IC↑(70→0.226, 60→0.236, 50→0.246), n 트레이드오프.
    #   원본 lv_a와 forward 비교해 좁힌 게 OOS서도 나은지 관찰. (lv_a2=하한제거는 원본과
    #   0-diff라 무의미해 제외 — 유동성 5억이 이미 저과매도 종목 걸러냄을 검증.)
    "lv_a3": {"factors": ["realized_vol", "roe", "reversal"], "uni": (OVERSOLD_LO, 60.0, LIQ_FLOOR)},
    # ---- 상승포착(momentum) 대조 관측 모델 (2026-06-27 추가, 가중치 0) ----
    # 목적: lowvol은 '저변동·반전'을 보는데, 상승장 주도주(거래량 터지며 20일선 회복하는
    #   종목)는 그 정반대 축이다. lowvol과 '같은 유니버스·같은 인프라'에서 대조 관측해,
    #   상승장이 충분히 낀 뒤 forward로 진짜 상승을 잡는지 판정하려는 준비용 모델.
    # ⚠️ 정체성은 lowvol과 반대 — model_id 접두사 'mom_'으로 구분(테이블만 공유).
    # ⚠️ post-hoc·하락장 in-sample 발견 → forward-only. 발견기간(≤20260627) 수치는 가설.
    #   판정은 등록일(20260627) 이후 OOS 40거래일 + 상승장 표본 충분 시. 그 전 노이즈.
    # 핵심팩터=sma20(20일선 위치, 커버리지 100%). 보조=1개월 모멘텀·거래량 팽창.
    "mom_a": {"factors": ["sma20", "mom_1m", "vol_exp"], "uni": DEFAULT_UNI},
    # ---- 모멘텀+눌림목 챌린저 (2026-07-17 추가, 가중치 0 관측) ----
    # mom_b = mom_a + 되돌림(reversal) 보조 1개 추가 — "추세는 있는데 지난주 급하게 눌린 종목".
    #   발견(post-hoc, outputs research_overlay 2026-07-17): stage3 41 run(5/23~7/16) in-sample,
    #   mom_a 상위10 풀 내 return_1w_% day-IC −0.269 CI[−0.356,−0.178](n=28일),
    #   top10→눌림5 교체 시뮬 Δ+2.29%p/5d CI[+0.49,+5.06] — 후보 22개 중 최강(다중검정 생존급).
    # ⚠️ 급락→반등 단일 레짐 발견 → forward-only. 등록 20260717(REG_DATE 원장·PREREGISTER_mom_b.md).
    #   lowvol 트랙 관례상 백필 행(<20260717)이 생기지만 판정에선 REG_DATE 게이트로 자동 제외.
    # 핵심팩터=sma20(mom_a와 동일, 실측필수). 보조=mom_1m·vol_exp·reversal(NaN=0.5).
    "mom_b": {"factors": ["sma20", "mom_1m", "vol_exp", "reversal"], "uni": DEFAULT_UNI},
    # ---- 공매도 챌린저 (2026-06-27 추가, 가중치 0 관측) ----
    # lv_a + 공매도비중(낮을수록 좋음). lv_a와 점수식 동일 + 공매도 1팩터 추가.
    #   목적: 오프라인서 ΔIC +0.034(유의, 코스닥 위주)로 나온 공매도 효과가 forward(OOS)서도
    #   유지되는지 lv_a와 나란히 관찰. 유지되면 lv_a 후보로 승격 판단.
    # 핵심팩터=realized_vol(lv_a와 동일, 실측필수). 보조=roe·reversal·short(NaN은 0.5 중립).
    #   → 공매도 없는 종목도 lv_a처럼 점수 나옴(공매도만 0.5 중립), 유니버스 동일 유지.
    # ⚠️ post-hoc·하락장 in-sample·run 10개 발견 → forward-only. 등록일 20260627 이후 OOS 40거래일 판정.
    "lv_short": {"factors": ["realized_vol", "roe", "reversal", "short"], "uni": DEFAULT_UNI},
    # ---- 고변동 대박 챌린저 (2026-06-27 추가, 가중치 0 관측) ----
    # hv_a = lv_a 의 저변동을 고변동으로 뒤집은 것. 핵심팩터만 highvol 로 교체, 나머지 동일.
    #   lv_a(저변동+ROE+반전) ↔ hv_a(고변동+ROE+반전) = 정확한 대척점 대조 실험.
    # 목적: "큰 수익을 노리면(고변동) 반등장에서 어떻게 되나"를 forward 로 관찰.
    #   오프라인(하락 편중 구간): 고변동은 평균 절대수익 더 나쁨(하락장 손실 큼), 단 상승 run(4개)
    #   에선 >+5% 비율 40%로 대박 잦음. 상승장 우위는 run 4개 가설 → 상승장 충분히 쌓여야 판정.
    # ⚠️ 핵심팩터=highvol(realized_vol 실측 필수, lv_a 와 동일 커버리지 43%). 유니버스도 lv_a 동일.
    # ⚠️ post-hoc·하락장 in-sample 발견 → forward-only. 등록일 20260627, OOS 40거래일 + 상승장 표본.
    "hv_a": {"factors": ["highvol", "roe", "reversal"], "uni": DEFAULT_UNI},
    # ---- 초소형(small) 트랙 (2026-06-27 추가, 가중치 0 관측) ----
    # sm_a = lv_a 와 점수식 동일(저변동+ROE+반전), 유니버스만 '거래대금 1~5억 초소형'.
    #   lv_a 가 유동성 하한(5억)으로 *버리는* 영역. 유동성 프리미엄 가설:
    #   오프라인서 거래대금 작을수록 단조롭게 시장초과↑ (h20: 초소형 +6.41% vs 대형 -6.10%).
    #   초소형+저변동 결합이 변동성·꼬리위험 줄임(변동성 9.8→8.6%). 핵심팩터=realized_vol(실측).
    # uni 4번째 원소 = 유동성 상한(5억). 하한 1억(<1억은 거래 거의 불가라 제외).
    # ⚠️ 실거래 제약: 중앙값 거래대금 2억 → 소액만 가능(슬리피지·거래불가 위험 = 프리미엄의 정체).
    #   관찰·소액 전용. post-hoc·하락장 in-sample → forward-only. 등록 20260627, OOS 40거래일(h20 위주).
    "sm_a": {"factors": ["realized_vol", "roe", "reversal"], "uni": (OVERSOLD_LO, OVERSOLD_HI, 1.0, 5.0)},
    # ---- 저회전 챌린저 lv_e (등록일=첫 적재일·REG_DATE 원장 정본, 가중치 0 관측) — PREREGISTER_lv_e.md ----
    # lv_e = lv_b(저변동+ROE) + to20(저회전) 1개만 추가. 변수 1개 원칙 준수.
    #   근거: RESEARCH_lv_ablation_20260812 V6 — 3지평(h5/h10/h20) 모두 짝비교 CI>0, 주별일관 6/7.
    #   ⚠️ post-hoc·in-sample(6/05~8/11 폭락+반등 단일 국면, 30검정) 발견 → forward-only.
    #      등록일(20260901, 첫 적재일) 이전 백필 행은 판정에서 REG_DATE 게이트로 자동 제외.
    # 핵심팩터=realized_vol(lv_b 와 동일, 실측필수). 보조=roe·to20(NaN=0.5).
    "lv_e": {"factors": ["realized_vol", "roe", "to20"], "uni": DEFAULT_UNI},
}

def spec_hash(model_id):
    """모델별 spec_hash. 원본 모델은 변형 추가와 무관하게 항상 동일 해시.
    payload에 그 모델의 팩터·유니버스·방식만 포함(전역 MODELS 미포함)."""
    m = MODELS[model_id]
    payload = json.dumps({
        "factors": [(f, FACTORS[f]) for f in m["factors"]],
        "universe": list(m["uni"]),
        "method": "cross_sectional_pct_rank_sum_v1",
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]

def ensure_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS lowvol_scores (
            run_id TEXT, market TEXT, ticker TEXT, model_id TEXT,
            spec_hash TEXT, lowvol_score REAL,
            n_universe INTEGER, frozen_at TEXT,
            PRIMARY KEY (run_id, market, ticker, model_id)
        )
    """)
    con.commit()

def pct_rank(series, ascending):
    # run 내 백분위. NaN은 NaN 유지(순위합에서 제외 처리).
    return series.rank(pct=True, ascending=ascending)

def score_run(df_run, model_factors):
    """df_run = 한 (run,market)의 유니버스 종목. 순위합 점수 반환.

    설계 결정(검증으로 확정): 모델의 '핵심 팩터'(= model_factors[0], 그 트랙의 정체성)는
    반드시 실측이어야 점수 유효. NaN을 0.5로 채워 넣으면 신호가 희석돼 IC가 망가짐
    (lv_a 0.199→0.119 확인). 따라서 핵심 팩터 NaN인 종목은 점수 NaN(=제외).
    보조 팩터(2번째 이후)의 NaN만 0.5 중립 채움(다른 팩터로 보완).
    """
    import pandas as pd
    total = None
    core_mask = None
    for i, fname in enumerate(model_factors):
        col_expr, asc = FACTORS[fname]
        col = col_expr.strip('"')
        r = pct_rank(df_run[col], asc)
        if i == 0:
            # 핵심 팩터: 실측 필수. 순위 그대로(NaN 유지).
            core_mask = r.notna()
            filled = r
        else:
            # 보조 팩터: NaN은 중립(0.5)로 채움.
            filled = r.fillna(0.5)
        total = filled if total is None else total + filled
    # 핵심 팩터 실측 종목만 유효 점수
    total = total.where(core_mask)
    return total

def run(mode_full=False, only_run=None):
    import pandas as pd
    con = sqlite3.connect(DB)
    ensure_table(con)
    now = datetime.now(KST).isoformat()

    cols = ['market','run_id','ticker','oversold_score','"amt_avg_1m_억"',
            'realized_vol','roe_value','"drawdown_52w_high_%"','"return_1w_%"',
            '"vs_SMA20_%"','"return_1m_%"','vol_1w_vs_1m_ratio']
    q = f"SELECT {','.join(cols)} FROM stage3_final"
    df = pd.read_sql(q, con)
    df.columns = [c.replace('%','pct_').replace('억','uk') for c in df.columns]
    # 컬럼 별칭 정리
    ren = {'"drawdown_52w_high_pct_"':'drawdown_52w_high_%', '"return_1w_pct_"':'return_1w_%',
           '"amt_avg_1m_uk"':'amt_avg_1m_억'}
    # 위 replace로 따옴표가 남을 수 있어 직접 매핑
    df = df.rename(columns={c: c.strip('"').replace('pct_','%').replace('_uk','_억') for c in df.columns})

    # 공매도 비중을 short_flows 에서 LEFT JOIN (lv_short 챌린저용 관측 팩터).
    #   short_flows.date == stage3.run_id (둘 다 YYYYMMDD). 없는 종목/날짜는 NaN(보조라 0.5 중립).
    #   Phase1: ohlcv.db(전체 raw)에서 우선 읽고, 없으면 history.db 폴백 → 0-diff 보장.
    sfdf = None
    import os
    if os.path.exists(OHLCV_DB):
        try:
            ocon = sqlite3.connect(OHLCV_DB)
            sfdf = pd.read_sql(
                "SELECT ticker, date AS run_id, short_vol_ratio FROM short_flows", ocon)
            ocon.close()
        except Exception:
            sfdf = None
    if sfdf is None:   # 폴백: history.db 의 short_flows (구 환경/이전 전)
        try:
            sfdf = pd.read_sql(
                "SELECT ticker, date AS run_id, short_vol_ratio FROM short_flows", con)
        except Exception:
            sfdf = None
    if sfdf is not None:
        sfdf['run_id'] = sfdf['run_id'].astype(str)
        df['run_id'] = df['run_id'].astype(str)
        df = df.merge(sfdf, on=['ticker', 'run_id'], how='left')
    else:
        df['short_vol_ratio'] = float('nan')   # short_flows 부재 시에도 동작

    # 20일 평균 회전율(to20)을 ohlcv.db daily_ohlcv 에서 LEFT JOIN (lv_e 챌린저용 관측 팩터).
    #   to20 = rolling20 mean(volume / shares), 기준일 포함 직전 20거래일(PIT — 미래 미사용).
    #   research/lv_ablation_scan.py 의 V6 정의와 동일 규약(전체 날짜 격자 위 최근 20행 평균).
    #   ohlcv.db 부재 시 NaN → 보조 팩터라 0.5 중립(유니버스·다른 모델 무영향).
    df['to20'] = float('nan')
    if os.path.exists(OHLCV_DB):
        try:
            ocon = sqlite3.connect(OHLCV_DB)
            ov = pd.read_sql("SELECT ticker, date, volume, shares FROM daily_ohlcv", ocon)
            ocon.close()
            ov['date'] = ov['date'].astype(str)
            ov['ticker'] = ov['ticker'].astype(str)
            ov['ratio'] = ov['volume'] / ov['shares'].replace(0, float('nan'))
            grid = ov.pivot_table(index='date', columns='ticker', values='ratio',
                                  aggfunc='last').sort_index()
            to20 = grid.rolling(20, min_periods=1).mean()
            t20 = to20.stack(future_stack=True).rename('to20_new').reset_index()
            t20.columns = ['run_id', 'ticker', 'to20_new']
            t20['run_id'] = t20['run_id'].astype(str)
            t20['ticker'] = t20['ticker'].astype(str)
            df['run_id'] = df['run_id'].astype(str)
            df['ticker'] = df['ticker'].astype(str)
            df = df.merge(t20, on=['ticker', 'run_id'], how='left')
            df['to20'] = df.pop('to20_new')
        except Exception as e:
            print(f"[to20] 적재 실패(무시, NaN 유지): {e}")

    # 부분적재일 제외(완전성) — [2026-08-11 교정] stage3 행수 기준 → stage1 행수 기준.
    #   근거: 약세장에서 stage3(추천)가 실제로 축소되면 정상 run 이 부분실행으로 오탐됨
    #   (실측: 20260723·20260804~0810 6개 run 오탐 제외, stage1 은 2,270~2,300행 정상 —
    #    리더보드 §28-2 게이트 교정과 동일 원리). 파이프라인 완주 여부는 stage1 이 판정.
    try:
        s1 = pd.read_sql("SELECT run_id, COUNT(*) n FROM stage1_oversold GROUP BY run_id",
                         con).set_index('run_id')['n']
        s1.index = s1.index.astype(str)
        med1 = s1.median()
        bad = set(s1[s1 < med1 * 0.5].index) | (set(df.run_id.unique()) - set(s1.index))
        bad &= set(df.run_id.unique())
    except Exception:   # stage1 부재(구 환경) 폴백: 종전 stage3 기준
        rc = df.groupby('run_id').size()
        bad = set(rc[rc < rc.median() * 0.5].index)
    if bad:
        print(f"[완전성] 부분실행 의심 run 제외(stage1 기준): {sorted(bad)}")
    df = df[~df.run_id.isin(bad)].copy()

    if only_run:
        df = df[df.run_id == only_run].copy()

    # 이미 적재된 (run,model) 스킵 (증분), --full이면 전체
    if not mode_full:
        # [idempotent 재적재] --run 으로 특정일을 지정하면, 그날 기존 행을 먼저 지우고 다시 쓴다.
        #   근거: 같은 날 배치가 두 번 돌면 stage3_final 은 덮어써지는데(최신), lowvol_scores 는
        #   append-only 라 새벽분이 스킵되어 유니버스가 어긋난다(2026-07-03 사건). --run 재적재는
        #   "지금 stage3 기준으로 이 날을 다시 만든다"는 의도이므로, 그날을 지우고 재계산해야 정합.
        #   (전체 증분 실행에는 영향 없음 — only_run 이 있을 때만.)
        if only_run:
            deleted = con.execute(
                "DELETE FROM lowvol_scores WHERE run_id=?", (only_run,)).rowcount
            con.commit()
            if deleted:
                print(f"[idempotent] --run {only_run}: 기존 {deleted}행 삭제 후 재적재")
        done = pd.read_sql("SELECT DISTINCT run_id, model_id FROM lowvol_scores", con)
        done_set = set(zip(done.run_id, done.model_id))
    else:
        done_set = set()
        if only_run is None:
            con.execute("DELETE FROM lowvol_scores")
            con.commit()
            print("[--full] lowvol_scores 전체 재적재")

    universe_col = 'oversold_score'
    liq_col = 'amt_avg_1m_억'
    rows_written = 0
    runs = sorted(df.run_id.unique())
    for rid in runs:
        for mkt in ['kospi','kosdaq']:
            sub = df[(df.run_id==rid)&(df.market==mkt)].copy()
            if len(sub)==0: continue
            for mid, mdef in MODELS.items():
                if (rid, mid) in done_set: continue
                u = mdef["uni"]
                os_lo, os_hi, liq = u[0], u[1], u[2]
                liq_hi = u[3] if len(u) > 3 else float("inf")  # 유동성 상한(optional)
                # 모델별 유니버스: 과매도 구간 + 유동성 하한(+선택적 상한)
                uni = sub[(sub[universe_col]>=os_lo)&(sub[universe_col]<os_hi)
                          &(sub[liq_col]>=liq)&(sub[liq_col]<liq_hi)].copy()
                if len(uni)<10:  # 너무 작으면 순위 무의미
                    continue
                n_uni = len(uni)
                sh = spec_hash(mid)
                sc = score_run(uni, mdef["factors"])
                out = uni[['ticker']].copy()
                out['lowvol_score'] = sc.values
                out = out.dropna(subset=['lowvol_score'])
                recs = [(rid, mkt, t, mid, sh, float(s), n_uni, now)
                        for t,s in zip(out.ticker, out.lowvol_score)]
                con.executemany(
                    "INSERT OR IGNORE INTO lowvol_scores VALUES (?,?,?,?,?,?,?,?)", recs)
                rows_written += len(recs)
        con.commit()
    print(f"[적재 완료] 신규 {rows_written}행")
    # 요약
    summ = pd.read_sql(
        "SELECT model_id, COUNT(*) n, COUNT(DISTINCT run_id) runs FROM lowvol_scores GROUP BY model_id", con)
    print(summ.to_string(index=False))
    con.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="전체 재적재(기본은 증분)")
    ap.add_argument("--run", type=str, default=None, help="특정 run_id만")
    a = ap.parse_args()
    run(mode_full=a.full, only_run=a.run)
