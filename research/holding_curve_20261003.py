# -*- coding: utf-8 -*-
"""holding_curve_20261003.py — "한 번 사서 k일 들고 있으면 누적이 어떻게 되나" (2026-10-03, 관측·읽기 전용)
등록 후 목록 기준일마다 시장별 상위10을 다음 거래일 종가에 같은 금액씩 사서 k=1..60거래일째 누적수익을 재고,
목록 기준일들에 대해 평균. 시장 = 같은 시장 전종목 동일가중 같은 방식. build_scoreboard 규약(상위10·MIN_BASKET·등록일·게이트) 그대로.
출력: research/holding_curve_20261003.png · research/holding_curve_20261003.csv
"""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; REPO = HERE.parent; sys.path.insert(0, str(REPO))
import leaderboard as lb, build_scoreboard as bs

K = 60; MODELS = ["v30", "le_a", "lv_b", "sv_a", "lv_a", "mom_a", "sm_a", "qs_a"]


def main():
    close, mktmap = lb.load_ohlcv(); dates = list(close.index); N = len(dates)
    mk = pd.Series(mktmap).str.lower(); uni = {m: close.columns.intersection(mk.index[mk == m]) for m in ("kospi", "kosdaq")}
    con = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    lbj = json.loads((REPO / "docs/leaderboard.json").read_text(encoding="utf-8"))
    out = {}
    for m in lbj["models"]:
        if m["model"] not in MODELS: continue
        S = bs.load_scores(con, m); keep = lb.dedupe_by_anchor(S, didx, excl, reg=m["reg_date"])
        rows = []   # (k, model_ret, market_ret)
        for rid in sorted(keep):
            t = lb.anchor(rid, didx)
            if t is None or t + 1 >= N: continue
            g = S[S.run_id == rid].dropna(subset=["score"]); e = close.iloc[t + 1]
            tops = {mkt: gm.nlargest(bs.TOP, "score").ticker for mkt, gm in g.groupby("market")}
            for k in range(1, K + 1):
                if t + 1 + k >= N: break
                r = close.iloc[t + 1 + k] / e - 1; a = []; b = []
                for mkt, tk in tops.items():
                    x = r.reindex(tk).dropna(); y = r.reindex(uni[mkt]).dropna()
                    if len(x) >= bs.MIN_BASKET and len(y): a.append(x.mean() * 100); b.append(y.mean() * 100)
                if a: rows.append((k, np.mean(a), np.mean(b)))
        df = pd.DataFrame(rows, columns=["k", "model", "market"])
        g = df.groupby("k").agg(n=("model", "size"), model=("model", "mean"), market=("market", "mean"))
        g["excess"] = g.model - g.market; out[m["model"]] = g
        print(f"{m['model']:6s} k1 {g.excess.get(1, np.nan):+.2f} k5 {g.excess.get(5, np.nan):+.2f} k10 {g.excess.get(10, np.nan):+.2f} k20 {g.excess.get(20, np.nan):+.2f} k40 {g.excess.get(40, np.nan):+.2f} k60 {g.excess.get(60, np.nan):+.2f} (n60={int(g.n.get(60, 0))}, n20={int(g.n.get(20, 0))})")
    con.close()
    allc = pd.concat({k: v for k, v in out.items()}, names=["model_id"]).reset_index()
    allc.to_csv(HERE / "holding_curve_20261003.csv", index=False, encoding="utf-8-sig")
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        from matplotlib import font_manager
        for f in ("Malgun Gothic", "NanumGothic", "AppleGothic"):
            if any(f == x.name for x in font_manager.fontManager.ttflist): plt.rcParams["font.family"] = f; break
        plt.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
        for mid, g in out.items():
            gg = g[g.n >= 8]
            ax[0].plot(gg.index, gg.excess, label=f"{mid} (n{int(g.n.get(40, 0))}@40일)", lw=2 if mid in ("v30", "le_a", "lv_b") else 1.2, alpha=1 if mid in ("v30", "le_a", "lv_b") else 0.7)
        ax[0].axhline(0, color="#999", lw=.8); ax[0].set_title("한 번 사서 k일 보유 — 시장 대비 누적 초과(%p), 목록 기준일 평균"); ax[0].set_xlabel("보유 거래일 k"); ax[0].legend(fontsize=8)
        for mid, c in (("v30", "#2f5fd8"), ("le_a", "#1a8f5a"), ("lv_b", "#c9403a")):
            g = out[mid][out[mid].n >= 8]
            ax[1].plot(g.index, g.model, color=c, lw=2, label=f"{mid} 바스켓"); ax[1].plot(g.index, g.market, color=c, lw=1, ls="--", label=f"{mid} 때 시장")
        ax[1].axhline(0, color="#999", lw=.8); ax[1].set_title("절대 누적수익(%) — 바스켓(실선) vs 같은 날 산 시장 평균(점선)"); ax[1].set_xlabel("보유 거래일 k"); ax[1].legend(fontsize=8)
        for a in ax: a.grid(alpha=.3)
        fig.suptitle("10/2 자료 · 등록 후 목록 · 시장별 상위10 · 다음날 종가 매수 · 비용 0 · 날짜 수가 8 미만인 k는 생략", fontsize=10)
        fig.tight_layout(); fig.savefig(HERE / "holding_curve_20261003.png", dpi=130); print("png ok")
    except Exception as e:
        print("plot skip", e)


if __name__ == "__main__":
    main()
