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
            'realized_vol','roe_value','"drawdown_52w_high_%"','"return_1w_%"']
    q = f"SELECT {','.join(cols)} FROM stage3_final"
    df = pd.read_sql(q, con)
    df.columns = [c.replace('%','pct_').replace('억','uk') for c in df.columns]
    # 컬럼 별칭 정리
    ren = {'"drawdown_52w_high_pct_"':'drawdown_52w_high_%', '"return_1w_pct_"':'return_1w_%',
           '"amt_avg_1m_uk"':'amt_avg_1m_억'}
    # 위 replace로 따옴표가 남을 수 있어 직접 매핑
    df = df.rename(columns={c: c.strip('"').replace('pct_','%').replace('_uk','_억') for c in df.columns})

    # 부분적재일 제외(완전성)
    rc = df.groupby('run_id').size()
    med = rc.median()
    bad = set(rc[rc < med*0.5].index)
    if bad:
        print(f"[완전성] 부분적재 의심 run 제외: {sorted(bad)}")
    df = df[~df.run_id.isin(bad)].copy()

    if only_run:
        df = df[df.run_id == only_run].copy()

    # 이미 적재된 (run,model) 스킵 (증분), --full이면 전체
    if not mode_full:
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
                os_lo, os_hi, liq = mdef["uni"]
                # 모델별 유니버스: 과매도 구간 + 유동성 하한
                uni = sub[(sub[universe_col]>=os_lo)&(sub[universe_col]<os_hi)
                          &(sub[liq_col]>=liq)].copy()
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
