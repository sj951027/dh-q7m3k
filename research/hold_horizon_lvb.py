# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행. 읽기 전용(history.db·ohlcv.db mode=ro), seed 고정.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent

"""hold_horizon_lvb.py — "보유 40거래일이 여전히 맞나" 보유기간 격자 실측 (관측 전용·판정 아님)

배경: 40거래일은 3년 오프라인 격자(research/fullscan_20260903/out/hold_k_cost.csv)에서 나왔다.
      거기 핵심은 **비용 때문**이다 — 비용 전 20일당 수익은 k 와 거의 무관(0.63~0.80%)한데,
      왕복 비용을 넣으면 짧게 자주 굴릴수록 깎여서 k=40~60 이 남는다.
이 스크립트는 같은 질문을 **lv_b 의 실제 forward 앵커**(등록 20260625 이후)로 다시 잰다.

잣대(그림자 포트와 동일): 시장별 상위 10 동일가중 · 희석 배지 제외 · 진입 t+1 종가
                        · 초과 = 종목수익 − 같은 시장 전종목 중앙값
표시:
  - 앵커당 초과(%p)와, 굴림 속도를 맞추기 위한 **20거래일 환산**(초과 × 20/K)
  - 왕복 비용 차감본(기본 0.35%p/회전 — 매도세 0.18% + 수수료·슬리피지 가정)
  - K=40 과의 **짝비교**(같은 앵커만) — 표본이 다르면 평균 비교는 의미가 약해서
주의: forward 표본은 한 국면(2026 여름)이고 K 가 커질수록 창이 닫힌 앵커가 줄어든다.
      3년 격자와 방향이 같으면 '재확인', 다르면 '표본 부족'으로 읽는다. 규약 변경은 이 문서로 하지 않는다.

실행:  python research/hold_horizon_lvb.py [--model lv_b] [--cost 0.35]
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
KS = [5, 10, 15, 20, 30, 40, 50, 60]
RNG = np.random.default_rng(20260912)

SRC = {
    "lv_b": ("SELECT run_id, market, ticker, lowvol_score AS score FROM lowvol_scores WHERE model_id='lv_b'", "20260625"),
    "v30":  ("SELECT run_id, market, ticker, final_score_v3 AS score FROM v3_scores WHERE model_id='v30'", "20260606"),
}


def boot_ci(a):
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    if len(a) < 4:
        return (np.nan, np.nan)
    b = [RNG.choice(a, len(a)).mean() for _ in range(BOOT)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="lv_b", choices=list(SRC))
    ap.add_argument("--cost", type=float, default=0.35, help="왕복 비용 %p (기본 0.35)")
    args = ap.parse_args()

    close, mktmap = lb.load_ohlcv()
    dates = list(close.index); N = len(dates)
    con = sqlite3.connect(f'file:{REPO / "history.db"}?mode=ro', uri=True)
    partial, dbl, didx = lb.build_gates(con, dates)
    excl = partial | dbl

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

    sql, regdate = SRC[args.model]
    S = pd.read_sql(sql, con)
    S["ticker"] = S.ticker.astype(str).str.zfill(6)
    S["run_id"] = S.run_id.astype(str)
    keep = lb.dedupe_by_anchor(S, didx, excl, reg=regdate)

    recs = {}
    for rid in keep:
        t = lb.anchor(rid, didx)
        if t is None:
            continue
        g = S[S.run_id == rid]
        flags = dil.load(asof=rid)
        bk = []
        for mk, gm in g.groupby("market"):
            gm = gm[~gm.ticker.isin(flags)].sort_values("score", ascending=False)
            bk += [(x, mk) for x in gm.ticker.head(TOP_N)]
        recs[rid] = {K: basket_excess(bk, t, K) for K in KS}
    df = pd.DataFrame(recs).T.sort_index()
    con.close()

    print("=" * 78)
    print(f"📐 보유기간 격자 — {args.model} · 앵커 {len(df)}개 · 잣대 같은 시장 전종목 중앙값")
    print(f"   왕복 비용 {args.cost}%p 가정 · 20거래일 환산 = 초과 × 20/K − 비용 × 20/K")
    print("=" * 78)
    rows = []
    for K in KS:
        x = df[K].dropna().values
        if len(x) < 4:
            rows.append((K, len(x), np.nan, np.nan, np.nan, np.nan, np.nan, np.nan)); continue
        lo, hi = boot_ci(x)
        per20 = x * (20.0 / K)
        per20_cost = per20 - args.cost * (20.0 / K)
        lo2, hi2 = boot_ci(per20_cost)
        rows.append((K, len(x), x.mean(), lo, hi, 100 * (x > 0).mean(),
                     per20_cost.mean(), f"[{lo2:+.2f},{hi2:+.2f}]"))
    T = pd.DataFrame(rows, columns=["K", "n", "초과평균", "CI저", "CI고", "양(+)%",
                                    "20일환산(비용후)", "환산CI"])
    print(T.round(2).to_string(index=False))

    print(f"\n== K=40 과 짝비교(같은 앵커만) — 표본이 달라 생기는 착시 제거")
    base = df[40]
    for K in KS:
        if K == 40:
            continue
        both = df[[K, 40]].dropna()
        if len(both) < 4:
            print(f"   K={K:2d} vs 40: 공통 앵커 {len(both)}개 — 비교 불가"); continue
        d20 = both[K].values * (20.0 / K) - both[40].values * (20.0 / 40)          # 비용 전
        dc = d20 - args.cost * (20.0 / K - 20.0 / 40)                              # 비용 후
        lo, hi = boot_ci(dc)
        verdict = "차이 없음" if (lo < 0 < hi) else ("K 우위" if lo > 0 else "40 우위")
        print(f"   K={K:2d} vs 40: 공통 {len(both):2d}개 · 20일환산 차이(비용후) {dc.mean():+5.2f}%p "
              f"CI [{lo:+.2f},{hi:+.2f}] → {verdict}")

    print("\n※ 한 국면(2026 여름) 표본이다. 3년 오프라인 격자(hold_k_cost.csv)와 방향이 같은지만 본다.")
    print("   규약(40거래일) 변경은 이 출력으로 하지 않는다 — OPS_GUIDE 는 권고, 변경은 사전등록 절차.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
