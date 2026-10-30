# -*- coding: utf-8 -*-
"""나 갈래 ① 후속 — 실제 v30 상위 10 목록(2026-06~)에서 '직전 20거래일 안 실적 발표' 종목 vs 아닌 종목의 40일 수익 (2026-10-31, 사후 관측)

대리 바구니(earnings_oversold_3y)에서 발표−없음 −2.9%p 였다. 같은 정의를 **실제 목록**(paper_account.v30_picks: 시장별 상위 10, 희석·게이트 제외 동일)에 대고 본다.
수익 = 앵커 다음날 종가 → 40거래일 뒤 종가(비용 없음) · 40일이 끝난 앵커만 · 앵커 단위 동일가중 · 월 블록 2,000(seed 7).
재현: python research/earnings_v30_list_check_20261031.py → research/out_earnings_oversold/v30_list.txt"""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent; sys.path.insert(0, str(REPO))
import leaderboard as lb, paper_account as pa
EDB = REPO / ".." / "dh-q7m3k-data" / "earnings.db"; OUT = HERE / "out_earnings_oversold"; OUT.mkdir(exist_ok=True)
H = 40; rng = np.random.default_rng(7); LOG = []


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    if len(um) < 2: return (np.nan, np.nan)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


t0 = time.time()
close, tradable, shares, mkt = pa.load_prices(); dates = list(close.index); didx = {d: i for i, d in enumerate(dates)}; N = len(dates)
excl = pa.load_gates(dates); picks = pa.v30_picks(dates, didx, excl)
ec = sqlite3.connect(f"file:{EDB}?mode=ro", uri=True); E = pd.read_sql("SELECT ticker, rcept_dt, sue FROM earnings_q", ec); ec.close()
E["ticker"] = E.ticker.astype(str).str.zfill(6); E["rcept_dt"] = E.rcept_dt.astype(str).str.replace("-", "").str[:8]
dser = pd.Series(range(N), index=pd.to_datetime(dates))
E["i"] = [int(dser.iloc[p]) if (p := dser.index.searchsorted(pd.Timestamp(d))) < N else -1 for d in E.rcept_dt]
by_t = {t: g.sort_values("i") for t, g in E[E.i >= 0].groupby("ticker")}
arr = close.to_numpy(float); col = {t: k for k, t in enumerate(close.columns)}
rows = []
for rid, lst in sorted(picks.items()):
    t = didx.get(rid)
    if t is None or t + 1 + H >= N: continue
    for tk in lst:
        c = col.get(tk)
        if c is None: continue
        p0, p1 = arr[t + 1, c], arr[t + 1 + H, c]
        if not (p0 > 0 and p1 > 0): continue
        g = by_t.get(tk); recent = g[(g.i <= t) & (g.i > t - 20)] if g is not None else None
        has = bool(recent is not None and len(recent)); sue = float(recent.sue.iloc[-1]) if has and recent.sue.notna().iloc[-1] else np.nan
        rows.append(dict(run=rid, month=rid[:6], ticker=tk, has=has, sue=sue, ret=(p1 / p0 - 1) * 100))
L = pd.DataFrame(rows)
say(f"v30 실제 목록 슬롯 {len(L)} · 앵커 {L.run.nunique()} ({L.run.min()}~{L.run.max()}) · 발표 20일 안 비율 {L.has.mean():.1%} · {time.time()-t0:.0f}s")
say(f"슬롯 단위: 발표 {L[L.has].ret.mean():+.2f}% (n {L.has.sum()}) · 없음 {L[~L.has].ret.mean():+.2f}% (n {(~L.has).sum()}) · 악화(sue<0) {L[L.has & (L.sue<0)].ret.mean():+.2f} (n {(L.has & (L.sue<0)).sum()}) · 개선 {L[L.has & (L.sue>=0)].ret.mean():+.2f} (n {(L.has & (L.sue>=0)).sum()})")
D = L.groupby("run").apply(lambda g: pd.Series(dict(month=g.month.iloc[0], e=g[g.has].ret.mean() if g.has.any() else np.nan, n_=g[~g.has].ret.mean() if (~g.has).any() else np.nan,
                                                     share=g.has.mean(), tail_e=(g[g.has].ret <= -20).mean() if g.has.any() else np.nan, tail_n=(g[~g.has].ret <= -20).mean() if (~g.has).any() else np.nan))).reset_index()
D["d"] = D.e - D.n_; D["d_tail"] = D.tail_e - D.tail_n; dd = D.dropna(subset=["d"])
lo, hi = block_ci(dd.d, dd.month); lo2, hi2 = block_ci(dd.d_tail, dd.month)
say(f"앵커 단위(둘 다 있는 앵커 {len(dd)}): 발표 {dd.e.mean():+.2f} · 없음 {dd.n_.mean():+.2f} · 차 {dd.d.mean():+.2f} [{lo:+.2f}, {hi:+.2f}] · −20% 비율 차 {dd.d_tail.mean():+.3f} [{lo2:+.3f}, {hi2:+.3f}] · 앵커별 발표 비중 평균 {D.share.mean():.1%}")
say(f"앵커에서 발표 쪽이 나쁜 비율 {(dd.d<0).mean():.0%}")
say("월별(앵커 평균): " + " · ".join(f"{m} {g.d.mean():+.1f}(n{len(g)})" for m, g in dd.groupby('month')))
(OUT / "v30_list.txt").write_text("\n".join(LOG), encoding="utf-8"); L.to_csv(OUT / "v30_list_slots.csv", index=False, encoding="utf-8-sig")
