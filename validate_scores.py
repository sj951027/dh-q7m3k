#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_scores.py  —  스크리너 점수의 "예측력" 검증 도구
=============================================================
이 스크립트가 하는 일 (쉬운 설명):
  스크리너는 매일 종목마다 점수(final_score)를 매깁니다.
  이 도구는 history.db에 쌓인 과거 추천을 꺼내서,
  "그때 점수가 높았던 종목이 정말로 이후에 더 올랐는지"를 숫자로 확인합니다.

  핵심 결과 3가지:
    1) IC (정보계수)  : 점수와 '이후 수익률'의 순위 상관.
                        +0.05 이상이면 약하게나마 예측력 있음, 0 근처면 점수가 무의미,
                        음수면 점수가 거꾸로 작동(높은 점수가 오히려 더 나쁨).
    2) 구간 분석      : 점수 상위/중위/하위 그룹의 평균 수익률 비교.
                        상위 그룹이 하위보다 잘 갔으면 점수가 일하는 것.
    3) 시장초과 수익  : 그냥 "시장이 올라서"가 아니라, 코스피/코스닥 지수보다
                        더 갔는지(실력)를 따로 봅니다.

  + 보너스: final_score를 이루는 각 요소(과매도/매집/추세/수급/펀더멘털/OCF/레짐)별로
    따로 IC를 내서, '어떤 요소가 진짜 신호이고 어떤 게 노이즈인지' 알려줍니다.

사용법 (잘 몰라도 그냥 이대로):
    python validate_scores.py

옵션 (필요할 때만):
    python validate_scores.py --db history.db --horizons 5,20,60 --top 30
    python validate_scores.py --market kospi        # 한 시장만
    python validate_scores.py --self-test           # 인터넷 없이 계산 로직만 점검

결과물:
    - 화면에 사람이 읽는 리포트
    - validation_picks.csv     (추천 종목별 이후 수익률 상세)
    - validation_summary.csv   (요소별 IC 요약)

주의:
    - 데이터가 하루치뿐이면 결과는 '참고용'입니다. 표본이 작아 운의 영향이 큽니다.
      매일 스크리너가 돌면서 history.db에 쌓일수록 이 검증의 신뢰도가 올라갑니다.
    - 매수 시점은 '추천 다음 거래일 종가'로 가정합니다(추천 당일 종가엔 못 사니까).
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────
# 설정 기본값
# ─────────────────────────────────────────────────────────────
DEFAULT_DB = "history.db"
DEFAULT_HORIZONS = [5, 20, 60]          # 며칠 후 수익률을 볼지 (거래일 기준)
DEFAULT_TOP = None                       # None이면 전체 추천 사용, 숫자면 점수 상위 N개만
CACHE_DIR = "price_cache"                # 받아온 시세를 저장 (재실행 빠르게)
ENTRY_LAG = 1                            # 추천일 +N거래일 종가에 매수했다고 가정

MARKET_INDEX = {"kospi": "KS11", "kosdaq": "KQ11"}

# final_score를 이루는 요소들 (DB 컬럼명) — 각각 따로 IC를 낸다
FACTOR_COLUMNS = [
    "final_score",        # 최종 점수 (가장 중요)
    "stock_score",        # 레짐 제외한 종목 자체 점수
    "oversold_score",     # 과매도
    "acc_score",          # 매집
    "trend_score",        # 추세 전환
    "supply_score",       # 외인/기관 수급
    "fundamental_score",  # 펀더멘털(영업이익 YoY 패턴)
    "ocf_score",          # 영업현금흐름 질
    "momentum_score",     # 단기 모멘텀
    "regime_score",       # 시장 레짐(종목 무관, 참고용)
    # ── 관측 전용 후보 팩터 (catalyst_observe.py 가 stage3_final 에 채움) ──
    # 점수식(final_score)에는 안 들어감. 여기 등록은 'IC만 측정'하기 위함.
    "smartmoney_score",   # 과매도+거래대금폭발+양봉+수급 (가산 트리거)
    "roe_value",          # EPS/BPS — 품질(밸류업) 게이트 후보
    "insider_score",      # 내부자 매집(프록시) — catalyst csv 있을 때만
    "buyback_cancel_flag",  # 자사주 소각 — catalyst csv 있을 때만
    # ── 관측 후보 추가(2026-06-20): 둘 다 점수식 미사용, IC만 측정 ──
    "vol_1w_vs_1m_ratio", # 거래량 팽창(5일/21일 평균거래량). 가설: 팽창=거래량동반 반등(+IC). stage3 기존 컬럼.
    "realized_vol",       # trailing 실현변동성(observe_vol.py 가 채움). low-vol 가설 검정용(부호는 데이터에 맡김).
    # ── 관측 후보 추가(과매도 재출현/신선도, observe_recurrence.py 가 채움) ──
    # 가설: 만성 반복=밸류트랩(IC 음), 신규 진입=신선한 이탈(IC 양). 부호는 데이터에 맡김.
    # post-hoc(사용자 아이디어) → §11 forward-only(등록 이후 OOS만) 로 판정.
    "os_count_20d",       # 직전 20활성런 중 stage3 재등장 수(만성도). 점수식 미사용.
    "os_streak",          # R 직전부터 연속 등장 활성런 수(연속 갈림). 점수식 미사용.
    "os_is_new20",        # 최근 20활성런간 첫 등장=1(신규 진입자). 점수식 미사용.
    # ── 관측 후보 추가(목표축 대표 컬럼 — 기존 stage3 컬럼, 계산/점수 불변, IC만 측정) ──
    # "신선한 이탈 vs 만성 갈림" 축별 1개씩. 측정 ≠ 승격; 좋아도 forward 확인 후에만 챌린저.
    "return_1w_%",          # 급락 형태: 최근 1주 수익률(샤프 최근 낙폭). 점수식 미사용.
    "drop_acuteness",       # 급성도: 월 낙폭 중 최근 1주 비율(observe_acuteness.py). 점수식 미사용.
    "BB_pct",               # 스트레치: 볼린저밴드 위치(단기 과매도 신전도). 점수식 미사용.
    "vs_SMA50_%",           # 추세 위치: 50일선 이격(중기). 점수식 미사용.
    "reversal_rebound_3pct",# 반전 확인: 3% 반등 플래그(v31a 게이트 재료의 단독 IC). 점수식 미사용.
    "foreign_20d_억",       # 장기 수급: 외인 20일 순매수(억). 점수식 미사용.
    # ── 관측 후보 추가(2026-06-24): 워치리스트(같은날 IC)에서 '점수식 비중복+방향 일관'만 선별 ──
    # 모두 stage3 기존 컬럼(커버리지 100%) → 등록만으로 IC 자동 측정. post-hoc → forward-only(§11-A).
    # foreign_20d_억 은 위에 이미 등록됨(중복 제외). foreign_5d/inst_5d 는 supply_score 입력이라 점수식 중복으로 제외.
    "inst_20d_억",          # 장기 수급: 기관 20일 순매수(억). supply_score 는 5d만 쓰므로 20d 는 비중복. 같은날 IC 음(-)=기관 분산일수록 ↑(외인-기관 다이버전스 가설). 점수식 미사용.
    "distance_to_52w_low_%",# 스트레치: 52주 저점까지 거리. 워치리스트 최강 단일(|IC|~0.13). 저점 근처일수록 ↑. (drawdown_52w 는 oversold_score 입력이라 제외, distance 는 비입력.) 점수식 미사용.
    "amt_avg_1w_억",        # 유동성: 주간 평균거래대금. 같은날 IC 음(-) → '유동성 우위=착시'를 forward 로 판정. 점수식 미사용.
]


# ─────────────────────────────────────────────────────────────
# 시세 공급자 (실제로는 FinanceDataReader, 자가점검 때는 가짜)
# ─────────────────────────────────────────────────────────────
class PriceProvider:
    """ticker/지수의 일별 종가 시리즈를 돌려준다. 캐시 사용."""

    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._fdr = None
        self._mem = {}  # 메모리 캐시

    def _import_fdr(self):
        if self._fdr is None:
            import FinanceDataReader as fdr
            self._fdr = fdr
        return self._fdr

    def get_close(self, code, start, end):
        """code(종목 또는 지수)의 [start, end] 종가 시리즈. 실패 시 None."""
        key = f"{code}_{start}_{end}"
        if key in self._mem:
            return self._mem[key]

        cache_path = os.path.join(self.cache_dir, f"{code}.parquet")
        df = None
        # 1) 디스크 캐시
        if os.path.exists(cache_path):
            try:
                df = pd.read_parquet(cache_path)
            except Exception:
                df = None
        # 2) 캐시가 범위를 못 덮으면 새로 받아옴
        need_fetch = (
            df is None
            or df.index.min() > pd.Timestamp(start)
            or df.index.max() < pd.Timestamp(end)
        )
        if need_fetch:
            try:
                fdr = self._import_fdr()
                fetched = fdr.DataReader(code, start, end)
                if fetched is not None and not fetched.empty:
                    fetched = fetched[["Close"]].copy()
                    if df is not None:
                        df = pd.concat([df, fetched])
                        df = df[~df.index.duplicated(keep="last")].sort_index()
                    else:
                        df = fetched
                    try:
                        df.to_parquet(cache_path)
                    except Exception:
                        pass
            except Exception as e:
                print(f"      ⚠️  {code} 시세 조회 실패: {type(e).__name__}")
                if df is None:
                    self._mem[key] = None
                    return None

        if df is None or df.empty:
            self._mem[key] = None
            return None
        s = df["Close"].astype(float).sort_index()
        self._mem[key] = s
        return s


# ─────────────────────────────────────────────────────────────
# DB에서 추천 종목 읽기
# ─────────────────────────────────────────────────────────────
def load_picks(db_path, market=None, run_id=None, top=None):
    if not os.path.exists(db_path):
        print(f"❌ DB 파일이 없습니다: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    # stage3_final 에 '실제로 있는' 팩터 컬럼만 SELECT.
    # (catalyst_observe.py 미실행 DB에서도 안 깨지게 — 없는 팩터는 아래서 NaN 채움)
    have = {r[1] for r in conn.execute('PRAGMA table_info("stage3_final")')}
    sel_factors = [c for c in FACTOR_COLUMNS if c in have]
    cols = ", ".join(
        ['"run_id"', '"market"', '"ticker"', '"name"', '"sector"', '"price"']
        + [f'"{c}"' for c in sel_factors]
    )
    q = f'SELECT {cols} FROM stage3_final WHERE 1=1'
    params = []
    if market:
        q += " AND market = ?"
        params.append(market)
    if run_id:
        q += " AND run_id = ?"
        params.append(run_id)
    df = pd.read_sql(q, conn, params=params)
    conn.close()

    if df.empty:
        print("❌ 조건에 맞는 추천 기록이 없습니다.")
        sys.exit(1)

    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    for c in FACTOR_COLUMNS:
        if c not in df.columns:      # 아직 배선 안 된 팩터 → NaN (IC 단계서 'pending')
            df[c] = pd.NA
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # top N: run_id×market별로 final_score 상위만
    if top:
        df = (
            df.sort_values("final_score", ascending=False)
            .groupby(["run_id", "market"], group_keys=False)
            .head(top)
            .reset_index(drop=True)
        )
    return df


# ─────────────────────────────────────────────────────────────
# 이후 수익률 계산
# ─────────────────────────────────────────────────────────────
def run_id_to_date(run_id):
    return datetime.strptime(str(run_id), "%Y%m%d")


def forward_return_from_series(close, entry_date, horizon, entry_lag=ENTRY_LAG):
    """entry_date(추천일) 이후 entry_lag번째 거래일 종가에 사서,
    그로부터 horizon 거래일 뒤 종가까지의 수익률(%)을 반환.
    데이터가 모자라면 (None, None, None)."""
    after = close[close.index > pd.Timestamp(entry_date)]
    if len(after) < entry_lag + 1:
        return None, None, None
    entry_px = float(after.iloc[entry_lag - 1])  # +entry_lag번째 거래일 종가
    fwd = after.iloc[entry_lag - 1:]
    if len(fwd) < horizon + 1:
        return entry_px, None, None
    exit_px = float(fwd.iloc[horizon])
    if entry_px <= 0:
        return entry_px, None, None
    ret = (exit_px / entry_px - 1) * 100
    entry_dt = fwd.index[0]
    return entry_px, ret, entry_dt


def compute_forward_returns(picks, horizons, provider, entry_lag=ENTRY_LAG):
    """추천 종목별 + 시장 지수 대비 초과 수익률을 horizon별로 계산."""
    today = datetime.now()
    rows = []
    # 지수 시세는 시장별로 한 번만
    index_cache = {}

    n = len(picks)
    for i, (_, row) in enumerate(picks.iterrows(), 1):
        if i % 25 == 0 or i == n:
            print(f"   [{i}/{n}] 시세 조회 중...")
        code = row["ticker"]
        market = row["market"]
        rid = row["run_id"]
        entry_date = run_id_to_date(rid)
        start = (entry_date - timedelta(days=10)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        close = provider.get_close(code, start, end)
        rec = {
            "run_id": rid, "market": market, "ticker": code,
            "name": row["name"], "sector": row.get("sector"),
        }
        for c in FACTOR_COLUMNS:
            rec[c] = row[c]

        if close is None or close.empty:
            rec["entry_px"] = None
            for h in horizons:
                rec[f"ret_{h}d"] = None
                rec[f"exret_{h}d"] = None
            rows.append(rec)
            continue

        # 지수
        idx_code = MARKET_INDEX.get(market, "KS11")
        if (idx_code, rid) not in index_cache:
            index_cache[(idx_code, rid)] = provider.get_close(idx_code, start, end)
        idx_close = index_cache[(idx_code, rid)]

        entry_px = None
        for h in horizons:
            epx, ret, entry_dt = forward_return_from_series(close, entry_date, h, entry_lag)
            entry_px = epx if epx is not None else entry_px
            rec[f"ret_{h}d"] = round(ret, 2) if ret is not None else None
            # 시장 대비 초과
            exret = None
            if ret is not None and idx_close is not None and not idx_close.empty:
                _, iret, _ = forward_return_from_series(idx_close, entry_date, h, entry_lag)
                if iret is not None:
                    exret = round(ret - iret, 2)
            rec[f"exret_{h}d"] = exret
        rec["entry_px"] = round(entry_px, 1) if entry_px else None
        rows.append(rec)

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# 분석: IC / 구간 / 적중률
# ─────────────────────────────────────────────────────────────
def spearman_ic(df, score_col, ret_col):
    """점수와 수익률의 순위상관(스피어만). 표본 <5면 None."""
    sub = df[[score_col, ret_col]].dropna()
    if len(sub) < 5 or sub[score_col].nunique() < 2 or sub[ret_col].nunique() < 2:
        return None, len(sub)
    ic = sub[[score_col, ret_col]].corr(method="spearman").iloc[0, 1]
    return (round(float(ic), 3) if pd.notna(ic) else None), len(sub)


def grouped_spearman_ic(df, score_col, ret_col, by=("run_id", "market"), min_n=8):
    """(날짜, 시장)별로 각각 cross-sectional Spearman IC를 구해 평균낸다.

    pooled(전부 한 통에 섞기) 방식은 시점·시장 차이가 IC를 부풀린다.
    같은 날·같은 시장 안에서 '점수 높은 종목이 더 갔나'만 보도록 그룹별로
    상관을 구한 뒤 평균하는 게 올바른 IC다 (v3_backtest 와 동일한 방식).

    반환: (mean_ic, n_groups, total_n)
      - mean_ic : 그룹별 IC들의 평균 (유효 그룹 없으면 None)
      - n_groups: IC를 구한 (날짜,시장) 그룹 수
      - total_n : 그 그룹들에 들어간 종목 쌍 총합
    """
    by = list(by)
    sub = df[by + [score_col, ret_col]].dropna()
    ics, total = [], 0
    for _, g in sub.groupby(by):
        if (len(g) < min_n or g[score_col].nunique() < 3
                or g[ret_col].nunique() < 3):
            continue
        ic = g[[score_col, ret_col]].corr(method="spearman").iloc[0, 1]
        if pd.notna(ic):
            ics.append(float(ic))
            total += len(g)
    if not ics:
        return None, 0, 0
    return round(float(np.mean(ics)), 3), len(ics), total


def grouped_spread(df, score_col, ret_col, by=("run_id", "market"), q=3, min_n=9):
    """(날짜, 시장)별로 '상위 1/q 평균 − 하위 1/q 평균' 초과수익 격차를 구해 평균.

    pooled quantile(전부 한 통)은 시점·시장 차이로 격차가 부풀려진다.
    그룹별로 상·하위 격차를 구한 뒤 평균해야 IC와 같은 기준이 된다.

    반환: (mean_spread, n_groups) — 유효 그룹 없으면 (None, 0)
    """
    by = list(by)
    sub = df[by + [score_col, ret_col]].dropna()
    spreads = []
    for _, g in sub.groupby(by):
        if len(g) < max(min_n, q * 3) or g[score_col].nunique() < q:
            continue
        try:
            bucket = pd.qcut(g[score_col].rank(method="first"), q,
                             labels=[f"Q{i+1}" for i in range(q)])
        except Exception:
            continue
        m = g.groupby(bucket, observed=True)[ret_col].mean()
        hi, lo = f"Q{q}", "Q1"
        if hi in m.index and lo in m.index:
            spreads.append(float(m[hi] - m[lo]))
    if not spreads:
        return None, 0
    return round(float(np.mean(spreads)), 2), len(spreads)


def factor_ic_table(rets, horizons, ret_prefix="exret"):
    """요소별 × horizon별 IC 표."""
    out = []
    for fac in FACTOR_COLUMNS:
        rec = {"factor": fac}
        for h in horizons:
            ic, n = spearman_ic(rets, fac, f"{ret_prefix}_{h}d")
            rec[f"IC_{h}d"] = ic
            rec[f"N_{h}d"] = n
        out.append(rec)
    return pd.DataFrame(out)


def quantile_table(rets, score_col, ret_col, q=3):
    """점수를 q개 구간으로 나눠 평균 수익률. (하위/중위/상위)"""
    sub = rets[[score_col, ret_col]].dropna()
    if len(sub) < q * 3:
        return None
    try:
        sub = sub.copy()
        sub["bucket"] = pd.qcut(sub[score_col].rank(method="first"), q,
                                labels=[f"Q{i+1}" for i in range(q)])
    except Exception:
        return None
    g = sub.groupby("bucket", observed=True)[ret_col].agg(["mean", "count"])
    g["mean"] = g["mean"].round(2)
    return g


def hit_rate(rets, ret_col):
    sub = rets[ret_col].dropna()
    if len(sub) == 0:
        return None, 0
    return round((sub > 0).mean() * 100, 1), len(sub)


# ─────────────────────────────────────────────────────────────
# 리포트 출력
# ─────────────────────────────────────────────────────────────
def interpret_ic(ic):
    if ic is None:
        return "표본 부족"
    a = abs(ic)
    if ic < -0.03:
        return "⛔ 역방향 (점수가 거꾸로 작동)"
    if a < 0.03:
        return "⚪ 사실상 무의미"
    if a < 0.05:
        return "🟡 매우 약함"
    if a < 0.1:
        return "🟢 약하지만 유효 (퀀트 기준 쓸만)"
    return "💚 뚜렷함 (이례적으로 강함 — 표본/룩어헤드 재확인)"


def print_report(rets, horizons, n_runs, top, ret_prefix="exret"):
    label = "시장초과" if ret_prefix == "exret" else "단순"
    bar = "=" * 72
    print(f"\n{bar}")
    print("📊  스크리너 점수 예측력 검증 리포트")
    print(bar)
    n_dates = rets["run_id"].nunique()
    n_picks = len(rets)
    n_valid = rets[f"{ret_prefix}_{horizons[0]}d"].notna().sum()
    print(f"  분석 추천 수: {n_picks}개  |  추천일(run) 수: {n_dates}일  |  유효 시세: {n_valid}개")
    print(f"  수익률 기준: {label}수익률 (시장초과 = 종목 − 지수)")
    if n_dates <= 2:
        print("  ⚠️  추천일이 적어 통계적 신뢰도가 낮습니다 — '방향 참고용'으로만 보세요.")
        print("      매일 스크리너가 돌며 history.db에 쌓일수록 이 숫자가 믿을 만해집니다.")

    # 1) 최종 점수 IC
    print(f"\n{'─'*72}\n① final_score 예측력 (IC = 점수와 이후 {label}수익률의 순위상관)\n{'─'*72}")
    for h in horizons:
        ic, n = spearman_ic(rets, "final_score", f"{ret_prefix}_{h}d")
        ic_str = f"{ic:+.3f}" if ic is not None else "  N/A"
        print(f"   +{h:>2}거래일 후:  IC {ic_str}  (N={n})   {interpret_ic(ic)}")

    # 2) 구간 분석 (대표 horizon = 가운데)
    h_mid = horizons[len(horizons) // 2]
    print(f"\n{'─'*72}\n② 점수 구간별 평균 {label}수익률  (+{h_mid}거래일 기준)\n{'─'*72}")
    qt = quantile_table(rets, "final_score", f"{ret_prefix}_{h_mid}d", q=3)
    if qt is None:
        print("   (표본 부족 — 구간 분석 생략)")
    else:
        names = {"Q1": "하위 1/3", "Q2": "중위 1/3", "Q3": "상위 1/3"}
        for b in ["Q1", "Q2", "Q3"]:
            if b in qt.index:
                m = qt.loc[b, "mean"]; c = int(qt.loc[b, "count"])
                bar_n = int(max(0, min(20, abs(m))))
                vis = ("+" if m >= 0 else "-") * bar_n
                print(f"   {names[b]:<8} 평균 {m:+6.2f}%  (N={c:>3})  {vis}")
        if "Q3" in qt.index and "Q1" in qt.index:
            spread = qt.loc["Q3", "mean"] - qt.loc["Q1", "mean"]
            verdict = "✅ 상위가 더 좋음(점수 작동)" if spread > 0 else "⛔ 상위가 더 나쁨(점수 역작동)"
            print(f"   → 상위−하위 격차: {spread:+.2f}%p   {verdict}")

    # 3) 적중률
    print(f"\n{'─'*72}\n③ 적중률 (이후 {label}수익률 > 0 인 비율)\n{'─'*72}")
    for h in horizons:
        hr, n = hit_rate(rets, f"{ret_prefix}_{h}d")
        hr_str = f"{hr:.1f}%" if hr is not None else "N/A"
        print(f"   +{h:>2}거래일 후:  {hr_str}  (N={n})")

    # 4) 요소별 IC
    print(f"\n{'─'*72}\n④ 요소별 예측력 — 어떤 점수 항목이 진짜 신호인가\n{'─'*72}")
    ftab = factor_ic_table(rets, horizons, ret_prefix)
    header = "   요소".ljust(22) + "".join([f"+{h}d".rjust(9) for h in horizons])
    print(header)
    print("   " + "-" * (len(header) - 3))
    for _, r in ftab.iterrows():
        line = "   " + str(r["factor"]).ljust(19)
        for h in horizons:
            ic = r[f"IC_{h}d"]
            line += (f"{ic:+.3f}".rjust(9) if ic is not None else "N/A".rjust(9))
        print(line)
    print("\n   해석: 절대값이 클수록 그 요소가 수익률을 잘 설명. 음수면 거꾸로 작동.")
    print("         0 근처 요소는 점수 합산에서 빼거나 가중치를 낮추는 걸 검토.")

    print(f"\n{bar}\n")
    return ftab


# ─────────────────────────────────────────────────────────────
# 자가 점검 (인터넷 없이 계산 로직 검증)
# ─────────────────────────────────────────────────────────────
class _FakeProvider(PriceProvider):
    """점수가 높을수록 미래 수익률이 높아지도록 가짜 시세 생성.
    → IC가 '양수'로 나와야 계산 파이프라인이 올바른 것."""
    def __init__(self, picks):
        self._score = dict(zip(picks["ticker"], picks["final_score"]))
        smin, smax = picks["final_score"].min(), picks["final_score"].max()
        self._lo, self._span = smin, max(1e-9, smax - smin)
        self._rng = np.random.default_rng(7)

    def get_close(self, code, start, end):
        dates = pd.bdate_range(start=start, end=end)
        if len(dates) < 70:
            dates = pd.bdate_range(start=start, periods=120)
        if code in ("KS11", "KQ11"):              # 지수: 완만한 우상향
            drift = 0.0002
            noise = self._rng.normal(0, 0.004, len(dates))
        else:
            s = self._score.get(code, self._lo)
            strength = (s - self._lo) / self._span     # 0~1
            drift = (strength - 0.5) * 0.004           # 점수 높을수록 더 오름
            noise = self._rng.normal(0, 0.02, len(dates))
        rets = drift + noise
        px = 10000 * np.exp(np.cumsum(rets))
        return pd.Series(px, index=dates)


def self_test():
    print("🧪 자가 점검 모드 — 가짜 시세로 계산 로직을 검증합니다.")
    print("   (점수↑ → 수익률↑ 로 설계했으므로 IC가 '양수'로 나와야 정상)\n")
    if not os.path.exists(DEFAULT_DB):
        print("❌ history.db가 없어 자가점검도 불가합니다.")
        return
    picks = load_picks(DEFAULT_DB, top=50)
    provider = _FakeProvider(picks)
    rets = compute_forward_returns(picks, [5, 20, 60], provider)
    ftab = print_report(rets, [5, 20, 60], picks["run_id"].nunique(), 50, ret_prefix="ret")
    ic20, _ = spearman_ic(rets, "final_score", "ret_20d")
    print("🧪 점검 결과:", "✅ 통과 (IC 양수, 계산 정상)" if (ic20 and ic20 > 0.1)
          else "⚠️ 예상과 다름 — 코드 점검 필요")


# ─────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="스크리너 점수 예측력 검증")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--market", default=None, choices=["kospi", "kosdaq"])
    ap.add_argument("--run-id", default=None, help="특정 날짜만 (YYYYMMDD)")
    ap.add_argument("--horizons", default=",".join(map(str, DEFAULT_HORIZONS)),
                    help="쉼표구분 거래일, 예: 5,20,60")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP,
                    help="추천일별 점수 상위 N개만 (기본: 전체)")
    ap.add_argument("--simple", action="store_true",
                    help="시장초과 대신 단순 수익률로 분석")
    ap.add_argument("--self-test", action="store_true",
                    help="인터넷 없이 계산 로직만 점검")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    horizons = [int(x) for x in args.horizons.split(",") if x.strip()]
    ret_prefix = "ret" if args.simple else "exret"

    print("📥 추천 기록 로드 중...")
    picks = load_picks(args.db, market=args.market, run_id=args.run_id, top=args.top)
    print(f"   ✓ {len(picks)}개 추천 ({picks['run_id'].nunique()}일, "
          f"{', '.join(sorted(picks['market'].unique()))})")

    print("🌐 이후 시세 조회 + 수익률 계산 (FinanceDataReader)...")
    provider = PriceProvider()
    rets = compute_forward_returns(picks, horizons, provider)

    ftab = print_report(rets, horizons, picks["run_id"].nunique(), args.top, ret_prefix)

    # 저장
    rets.to_csv("validation_picks.csv", index=False, encoding="utf-8-sig")
    ftab.to_csv("validation_summary.csv", index=False, encoding="utf-8-sig")
    print("💾 저장: validation_picks.csv (종목별 상세), validation_summary.csv (요소별 IC)")


if __name__ == "__main__":
    main()
