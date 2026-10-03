# -*- coding: utf-8 -*-
"""v30_accumulate_3yr.py — 재계산 v30(수급 0·DIV 0·PBR/PER 근사·위험 부분) 상위10 을 3년 동안 "매일 사서 계속 보유"/"40일 보유" (2026-10-03, 관측)
입력: v30_hist_scores.parquet(v30_history.py) · 가격 패널. 규약: 성적표와 같음(시장별 상위10 · 다음날 종가 · 비용 0 · 시장 = 전종목 동일가중).
출력: research/accumulate_v30_3yr_20261003.png · research/dart_history/v30_accumulate_3yr.csv
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "research" / "fullscan_20260903"))
from fslib import Panel

H = 40; TOP = 10


def main():
    P = Panel(); dates = list(P.dates); di = {d: i for i, d in enumerate(dates)}; T, N = P.T, P.N
    c = P.close.astype(np.float64); mk = pd.Series(P.mk).str.lower().values; ti = {t: i for i, t in enumerate(P.tick)}
    sc = pd.read_parquet(HERE / "v30_hist_scores.parquet")
    sc = sc[sc.final_score_v3 > -900]
    picks = {}   # t -> {market: [col idx]}
    for (d, mkt), g in sc.groupby(["run_id", "market"]):
        if d not in di: continue
        top = [ti[x] for x in g.nlargest(TOP, "final_score_v3").ticker if x in ti]
        if len(top) >= 5: picks.setdefault(di[d], {})[mkt] = top
    uni = {m: np.where(mk == m)[0] for m in ("kospi", "kosdaq")}
    ok = np.isfinite(c)
    # ① 계속 보유
    rows = []; ent = sorted(picks)
    for d in range(min(ent) + 1, T):
        pa, pb = [], []
        for t in ent:
            e = t + 1
            if e > d: break
            a, b = [], []
            for mkt, cols in picks[t].items():
                x = c[d, cols] / c[e, cols] - 1; x = x[np.isfinite(x)]
                u = uni[mkt]; y = c[d, u] / c[e, u] - 1; y = y[np.isfinite(y)]
                if len(x) >= 5 and len(y): a.append(x.mean() * 100); b.append(y.mean() * 100)
            if a: pa.append(np.mean(a)); pb.append(np.mean(b))
        if pa: rows.append((dates[d], len(pa), np.mean(pa), np.mean(pb)))
    cur = pd.DataFrame(rows, columns=["date", "n", "basket", "market"]); cur["excess"] = cur.basket - cur.market
    # ② 40일 보유 막대
    br = []
    for t in ent:
        e = t + 1
        if e + H >= T: continue
        a, b = [], []
        for mkt, cols in picks[t].items():
            x = c[e + H, cols] / c[e, cols] - 1; x = x[np.isfinite(x)]; u = uni[mkt]; y = c[e + H, u] / c[e, u] - 1; y = y[np.isfinite(y)]
            if len(x) >= 5 and len(y): a.append(x.mean() * 100); b.append(y.mean() * 100)
        if a: br.append((dates[t], np.mean(a), np.mean(b)))
    bars = pd.DataFrame(br, columns=["list_date", "basket", "market"]); bars["excess"] = bars.basket - bars.market; bars["year"] = bars.list_date.str[:4]
    cur.to_csv(HERE / "v30_accumulate_3yr.csv", index=False, encoding="utf-8-sig"); bars.to_csv(HERE / "v30_bars_3yr.csv", index=False, encoding="utf-8-sig")
    print(f"계속보유 끝값: 계좌 {cur.basket.iloc[-1]:+.1f}% 시장 {cur.market.iloc[-1]:+.1f}% 차이 {cur.excess.iloc[-1]:+.1f}%p · 차이>0 날 {(cur.excess>0).mean():.0%} · 최저 {cur.excess.min():+.1f}%p · 날짜 {len(cur)}")
    for y, g in bars.groupby("year"): print(f"  {y}: 40일 초과 평균 {g.excess.mean():+.2f}%p · 양수 {(g.excess>0).mean():.0%} · 매수일 {len(g)} · 바스켓 {g.basket.mean():+.1f}% / 시장 {g.market.mean():+.1f}%")
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt; from matplotlib import font_manager
    for f in ("Malgun Gothic", "NanumGothic"):
        if any(f == x.name for x in font_manager.fontManager.ttflist): plt.rcParams["font.family"] = f; break
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(2, 1, figsize=(13, 8), height_ratios=[1.3, 1])
    x = pd.to_datetime(cur.date); ax[0].plot(x, cur.excess, color="#2f5fd8", lw=1.8, label=f"재계산 v30 상위10 — 끝값 {cur.excess.iloc[-1]:+.1f}%p · 0위 {(cur.excess>0).mean():.0%}")
    ax[0].axhline(0, color="#999", lw=.8); ax[0].grid(alpha=.3); ax[0].legend(fontsize=9)
    ax[0].set_title("① 3년 — 재계산 v30(수급 0·배당 0·PBR/PER 근사·위험등급 부분) 시장별 상위10 을 매일 같은 금액으로 사서 계속 보유: 시장과의 차이 %p")
    xb = pd.to_datetime(bars.list_date); ax[1].bar(xb, bars.excess, color=["#2f5fd8" if v > 0 else "#ccc" for v in bars.excess], width=1.0, alpha=.7)
    ax[1].plot(xb, bars.excess.rolling(20).mean(), color="#222", lw=1.1, label="20일 이동평균"); ax[1].axhline(0, color="#999", lw=.8); ax[1].grid(alpha=.3); ax[1].legend(fontsize=8)
    ys = " · ".join(f"{y} {g.excess.mean():+.1f}" for y, g in bars.groupby("year"))
    ax[1].set_title(f"② 매수일별 40일 초과(%p) · 연도별 평균 {ys}", fontsize=10)
    fig.suptitle("3년 패널 2024-01~2026-10 · 재무 = DART 보고서를 날짜별로 PIT 재구성(2,140종목분, 나머지는 재무 없음) · 비용 0", fontsize=10)
    fig.tight_layout(); fig.savefig(REPO / "research" / "accumulate_v30_3yr_20261003.png", dpi=120); print("png ok")


if __name__ == "__main__":
    main()
