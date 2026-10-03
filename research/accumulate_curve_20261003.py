# -*- coding: utf-8 -*-
"""accumulate_curve_20261003.py — "매일 같은 금액씩 그날 목록을 사서 계속 들고 가면" 날짜별 누적 (2026-10-03, 관측·읽기 전용)
① 계속 보유 계좌: 날짜 d 까지 들어온 매수분(목록 기준일 ≤ d−1, 다음날 종가 매수) 각각의 d 시점 수익을 같은 금액 기준으로 평균 = 계좌 수익(%).
   시장도 같은 날 같은 금액으로 전종목 동일가중 매수 → 차이(%p). 꾸준히 벌면 차이가 우상향.
② 매수일별 40일 결과 막대: 각 목록 기준일의 40일 초과(%p)를 시간순으로 + 누적 평균선. 한 시기 덕인지 고르게인지.
규약: build_scoreboard(시장별 상위10·MIN_BASKET·등록일·게이트). 비용 0. 출력: research/accumulate_curve_20261003.png · .csv
"""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; REPO = HERE.parent; sys.path.insert(0, str(REPO))
import leaderboard as lb, build_scoreboard as bs

MODELS = ["v30", "le_a", "lv_b", "sv_a"]; H = 40


def main():
    close, mktmap = lb.load_ohlcv(); dates = list(close.index); N = len(dates)
    mk = pd.Series(mktmap).str.lower(); uni = {m: close.columns.intersection(mk.index[mk == m]) for m in ("kospi", "kosdaq")}
    con = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    lbj = json.loads((REPO / "docs/leaderboard.json").read_text(encoding="utf-8"))
    curves, bars = {}, {}
    for m in lbj["models"]:
        if m["model"] not in MODELS: continue
        S = bs.load_scores(con, m); keep = lb.dedupe_by_anchor(S, didx, excl, reg=m["reg_date"])
        tr = []   # (entry_idx, {mkt: tickers})
        for rid in sorted(keep):
            t = lb.anchor(rid, didx)
            if t is None or t + 1 >= N: continue
            g = S[S.run_id == rid].dropna(subset=["score"])
            tr.append((t + 1, {mkt: list(gm.nlargest(bs.TOP, "score").ticker) for mkt, gm in g.groupby("market")}, dates[t]))
        # ① 계속 보유 계좌
        first = min(e for e, _, _ in tr); rows = []
        for d in range(first, N):
            pa, pb = [], []
            for e, tops, _ in tr:
                if e > d: continue
                r = close.iloc[d] / close.iloc[e] - 1; a = []; b = []
                for mkt, tk in tops.items():
                    x = r.reindex(tk).dropna(); y = r.reindex(uni[mkt]).dropna()
                    if len(x) >= bs.MIN_BASKET and len(y): a.append(x.mean() * 100); b.append(y.mean() * 100)
                if a: pa.append(np.mean(a)); pb.append(np.mean(b))
            if pa: rows.append((dates[d], len(pa), np.mean(pa), np.mean(pb)))
        c = pd.DataFrame(rows, columns=["date", "n_tranche", "model", "market"]); c["excess"] = c.model - c.market
        curves[m["model"]] = c
        # ② 매수일별 40일 결과
        br = []
        for e, tops, ld in tr:
            if e + H >= N: continue
            r = close.iloc[e + H] / close.iloc[e] - 1; a = []; b = []
            for mkt, tk in tops.items():
                x = r.reindex(tk).dropna(); y = r.reindex(uni[mkt]).dropna()
                if len(x) >= bs.MIN_BASKET and len(y): a.append(x.mean() * 100); b.append(y.mean() * 100)
            if a: br.append((ld, np.mean(a) - np.mean(b)))
        b = pd.DataFrame(br, columns=["list_date", "exc40"]); b["running_mean"] = b.exc40.expanding().mean(); bars[m["model"]] = b
        print(f"{m['model']:5s} 계속보유: 마지막 {c.date.iloc[-1]} 매수분 {int(c.n_tranche.iloc[-1])}개 계좌 {c.model.iloc[-1]:+.1f}% 시장 {c.market.iloc[-1]:+.1f}% 차이 {c.excess.iloc[-1]:+.1f}%p · 날짜 중 차이>0 비율 {(c.excess>0).mean():.0%} · 40일 막대 양수 {(b.exc40>0).mean():.0%} ({len(b)}개)")
    con.close()
    pd.concat({k: v for k, v in curves.items()}, names=["model_id"]).reset_index().to_csv(HERE / "accumulate_curve_20261003.csv", index=False, encoding="utf-8-sig")
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt; from matplotlib import font_manager
    for f in ("Malgun Gothic", "NanumGothic"):
        if any(f == x.name for x in font_manager.fontManager.ttflist): plt.rcParams["font.family"] = f; break
    plt.rcParams["axes.unicode_minus"] = False
    col = {"v30": "#2f5fd8", "le_a": "#1a8f5a", "lv_b": "#c9403a", "sv_a": "#e08a00"}
    fig = plt.figure(figsize=(14, 9)); gs = fig.add_gridspec(3, 2, height_ratios=[1.4, 1, 1])
    ax = fig.add_subplot(gs[0, :])
    for mid, c in curves.items():
        x = pd.to_datetime(c.date); ax.plot(x, c.excess, color=col[mid], lw=2, label=f"{mid}  (차이 끝값 {c.excess.iloc[-1]:+.1f}%p)")
    ax.axhline(0, color="#999", lw=.8); ax.set_title("① 매일 같은 금액으로 그날 목록을 사서 계속 들고 가는 계좌 — 시장(같은 방식)과의 차이 %p, 날짜별"); ax.legend(fontsize=9); ax.grid(alpha=.3)
    for i, mid in enumerate(MODELS):
        a = fig.add_subplot(gs[1 + i // 2, i % 2]); b = bars[mid]; x = pd.to_datetime(b.list_date)
        a.bar(x, b.exc40, color=[col[mid] if v > 0 else "#bbb" for v in b.exc40], width=1.0)
        a.plot(x, b.running_mean, color="#222", lw=1.2, label="누적 평균")
        a.axhline(0, color="#999", lw=.8); a.set_title(f"② {mid} — 매수일별 40일 초과(%p) · 양수 {(b.exc40>0).mean():.0%} · {len(b)}개", fontsize=10); a.grid(alpha=.3); a.legend(fontsize=8)
    fig.suptitle("10/2 자료 · 등록 후 목록 · 시장별 상위10 · 다음날 종가 매수 · 비용 0 · ①은 아직 안 판 것도 오늘 가격으로 포함", fontsize=10)
    fig.tight_layout(); fig.savefig(HERE / "accumulate_curve_20261003.png", dpi=120); print("png ok")


if __name__ == "__main__":
    main()
