# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행. 읽기 전용(history.db·ohlcv.db mode=ro), seed 고정.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent

"""model_switching_test.py — "요즘 잘 나가는 모델로 갈아타면 이득인가?" 실측 (관측 전용·판정 아님)

묻는 것 두 가지:
  ① **갈아타기**: 최근 성적 1위 모델을 다음 구간에 쓰면, lv_b 를 그냥 계속 쓰는 것보다 나은가?
  ② **장세별**: 진입 시점의 시장 레짐(강세/반등/약세)에 따라 더 나은 모델이 갈리는가?

방법(그림자 포트와 같은 잣대 — shadow_ops_portfolio.py 규약 그대로):
  시장별 상위 10 동일가중 · 희석 배지 제외 · 진입 t+1 종가 · 보유 K거래일(기본 20)
  · 초과 = 종목수익 − 같은 시장 전종목 중앙값 · 부분/이중 실행 run 제외
  각 앵커 t 에서 '직전 LOOKBACK 앵커의 실현 초과 평균'으로 모델을 고르고(=그 시점에 알 수 있는 정보만),
  고른 모델의 앞으로의 초과수익을 기록한다. 미래 정보를 쓰지 않는다.

주의(결과 해석):
  - 표본이 작다. 앵커 수십 개·한 국면(2026 여름)뿐이다. '차이 없음'이 결론일 수 있고 그래도 정상이다.
  - 여기서 나온 수치로 운용 모델을 바꾸지 않는다. 바꾸려면 PREREGISTER_ops_adoption.md 절차를 탄다.

실행:  python research/model_switching_test.py [--hold 20] [--lookback 5]
"""
import argparse
import sqlite3
import sys

import numpy as np
import pandas as pd

REPO = _P(str(_REPO))
sys.path.insert(0, str(REPO))
import leaderboard as lb          # noqa: E402
import dilution_flag as dil       # noqa: E402

TOP_N = 10
BOOT = 4000
RNG = np.random.default_rng(20260912)

SRC = {   # 모델 → (점수 쿼리, 등록일)  — 등록 전 행은 post-hoc 이라 제외
    "lv_b":  ("SELECT run_id, market, ticker, lowvol_score AS score FROM lowvol_scores WHERE model_id='lv_b'", "20260625"),
    "lv_a":  ("SELECT run_id, market, ticker, lowvol_score AS score FROM lowvol_scores WHERE model_id='lv_a'", "20260625"),
    "mom_a": ("SELECT run_id, market, ticker, lowvol_score AS score FROM lowvol_scores WHERE model_id='mom_a'", "20260627"),
    "v30":   ("SELECT run_id, market, ticker, final_score_v3 AS score FROM v3_scores WHERE model_id='v30'", "20260606"),
    "sv_a":  ("SELECT run_id, market, ticker, wu_score AS score FROM wu_scores WHERE model_id='sv_a'", "20260715"),
    "qs_a":  ("SELECT run_id, market, ticker, wu_score AS score FROM wu_scores WHERE model_id='qs_a'", "20260723"),
}


def boot_ci(a):
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    if len(a) < 4:
        return (np.nan, np.nan)
    b = [RNG.choice(a, len(a)).mean() for _ in range(BOOT)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", type=int, default=20, help="보유 거래일(기본 20 — 앵커를 많이 쓰려고)")
    ap.add_argument("--lookback", type=int, default=5, help="'요즘 성적'을 볼 직전 앵커 수")
    args = ap.parse_args()

    close, mktmap = lb.load_ohlcv()
    dates = list(close.index); N = len(dates)
    con = sqlite3.connect(f'file:{REPO / "history.db"}?mode=ro', uri=True)
    partial, dbl, didx = lb.build_gates(con, dates)
    excl = partial | dbl

    # 레짐(진입 시점 시장 상태) — stage1_oversold 에 run/market 단위로 기록돼 있다
    reg = pd.read_sql("SELECT run_id, market, market_regime FROM stage1_oversold "
                      "GROUP BY run_id, market, market_regime", con)
    regime = {(r.run_id, r.market): r.market_regime for r in reg.itertuples()}

    _uni = {}

    def uni_median(mk, t0, t1):
        key = (mk, t0, t1)
        if key not in _uni:
            cols = [c for c in close.columns if str(mktmap.get(c, "")).lower() == mk]
            r = close.iloc[t1][cols] / close.iloc[t0][cols] - 1
            _uni[key] = float(np.nanmedian(r.values)) if len(cols) else 0.0
        return _uni[key]

    def basket_excess(bk, t, K):
        t0 = t + lb.ENTRY_LAG; t1 = t0 + K
        if t1 >= N:
            return np.nan
        ex = []
        for tic, mk in bk:
            if tic not in close.columns:
                continue
            p0 = close.iloc[t0].get(tic, np.nan); p1 = close.iloc[t1].get(tic, np.nan)
            if not (np.isfinite(p0) and np.isfinite(p1)) or p0 <= 0:
                continue
            jump = close[tic].pct_change(fill_method=None).abs().iloc[t0 + 1:t1 + 1].max()
            if jump > lb.JUMP_CAP:
                continue
            ex.append((p1 / p0 - 1 - uni_median(mk, t0, t1)) * 100)
        return float(np.mean(ex)) if ex else np.nan

    # ── 모델별 앵커 초과수익 ────────────────────────────────────────────
    series = {}
    for mid, (sql, regdate) in SRC.items():
        S = pd.read_sql(sql, con)
        S["ticker"] = S.ticker.astype(str).str.zfill(6)
        S["run_id"] = S.run_id.astype(str)
        if "market" not in S.columns:                      # wu 는 시장 구분이 없다 → ohlcv 로 붙인다
            S["market"] = [str(mktmap.get(t, "")).lower() for t in S.ticker]
            S = S[S.market.isin(["kospi", "kosdaq"])]
        keep = lb.dedupe_by_anchor(S, didx, excl, reg=regdate)
        out = {}
        for rid in keep:
            t = lb.anchor(rid, didx)
            if t is None:
                continue
            g = S[S.run_id == rid]
            flags = dil.load(asof=g.run_id.iloc[0])
            bk = []
            for mk, gm in g.groupby("market"):
                gm = gm[~gm.ticker.isin(flags)].sort_values("score", ascending=False)
                bk += [(x, mk) for x in gm.ticker.head(TOP_N)]
            v = basket_excess(bk, t, args.hold)
            if np.isfinite(v):
                out[g.run_id.iloc[0]] = v
        series[mid] = pd.Series(out).sort_index()
        print(f"   {mid:5s} 앵커 {len(series[mid]):3d}개 · 평균 {series[mid].mean():+.2f}%p")

    df = pd.DataFrame(series).sort_index()
    print("\n" + "=" * 72)
    print(f"① 갈아타기 검증 — 보유 {args.hold}거래일 · '요즘'은 직전 {args.lookback}앵커")
    print("=" * 72)
    rows = []
    for i, rid in enumerate(df.index):
        past = df.iloc[max(0, i - args.lookback):i]
        if len(past) < args.lookback:
            continue
        avail = past.dropna(axis=1, how="any")
        if avail.shape[1] < 2 or not np.isfinite(df.loc[rid]).any():
            continue
        pick = avail.mean().idxmax()                 # 그 시점까지의 정보만으로 1위 선택
        if not np.isfinite(df.loc[rid, pick]):
            continue
        rows.append({
            "run_id": rid, "pick": pick,
            "갈아타기": df.loc[rid, pick],
            "lv_b고정": df.loc[rid, "lv_b"],
            "전모델평균": float(np.nanmean(df.loc[rid].values)),
        })
    R = pd.DataFrame(rows)
    if R.empty:
        print("   표본 부족 — 비교 불가"); con.close(); return 0
    for c in ("갈아타기", "lv_b고정", "전모델평균"):
        x = R[c].dropna().values
        lo, hi = boot_ci(x)
        print(f"   {c:8s} n={len(x):3d} 평균 {np.nanmean(x):+6.2f}%p · CI [{lo:+.2f},{hi:+.2f}]")
    d = (R["갈아타기"] - R["lv_b고정"]).dropna().values
    lo, hi = boot_ci(d)
    print(f"\n   차이(갈아타기 − lv_b고정) n={len(d)} 평균 {d.mean():+.2f}%p · CI [{lo:+.2f},{hi:+.2f}]"
          f" · 갈아타기가 나은 비율 {100 * (d > 0).mean():.0f}%")
    print(f"   1위로 뽑힌 모델 분포: {R['pick'].value_counts().to_dict()}")

    print("\n" + "=" * 72)
    print("② 장세별 — 진입 시점 레짐(코스피 기준)에 따라 더 나은 모델이 갈리나")
    print("=" * 72)
    lab = {rid: regime.get((rid, "kospi")) for rid in df.index}
    df2 = df.copy(); df2["레짐"] = [lab.get(r) for r in df2.index]
    g = df2.dropna(subset=["레짐"]).groupby("레짐")
    tab = g.agg(["mean", "count"])
    for mid in SRC:
        if mid in df.columns:
            sub = df2.dropna(subset=["레짐"]).groupby("레짐")[mid].agg(["mean", "count"]).round(2)
            print(f"\n   [{mid}]")
            print("   " + sub.to_string().replace("\n", "\n   "))
    print("\n※ 레짐별 앵커가 한 자릿수면 평균은 우연이다. 숫자보다 '표본이 없다'는 사실을 먼저 본다.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
