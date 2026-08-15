# -*- coding: utf-8 -*-
"""
event_value_probe_20260815.py — 어닝 이벤트(PEAD)·컨센서스 괴리·밸류 첫 프로브 (§14 탐색)
==========================================================================================
새 광맥 후보 3종 — 전부 이미 적재 중인 직교 데이터, 최초 스캔:
  A) EPS 점프 이벤트: valuation_daily(7/06~)의 trailing EPS 가 바뀐 날 = 실적 반영일.
     2분기 실적시즌(7~8월)이 창에 통째로 포함. 개선/악화 방향별 forward 수익(PEAD 가설).
  B) 목표가 괴리율: consensus_daily(주간 3스냅) target_price/close − 1 의 forward IC.
  C) 밸류: PBR 역수 forward IC (주간 앵커 — 창 6주, 참고 수준).
정직성: 창이 짧고(6주·반등 국면) 전부 in-sample. '기움' 이상 결론 금지. 승격은 PREREGISTER 만.
실행: python research/event_value_probe_20260815.py
"""
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
oc = sqlite3.connect(f"file:{HERE.parent/'dh-q7m3k-data'/'ohlcv.db'}?mode=ro", uri=True)
RNG = np.random.default_rng(20260815)

px = pd.read_sql("SELECT ticker,date,close,volume,change_pct FROM daily_ohlcv WHERE date>='20260601'", oc)
dts = sorted(px.date.unique())
C = px.pivot_table(index='date', columns='ticker', values='close', aggfunc='last').reindex(dts)
V = px.pivot_table(index='date', columns='ticker', values='volume', aggfunc='last').reindex(dts)
R = px.pivot_table(index='date', columns='ticker', values='change_pct', aggfunc='last').reindex(dts)
amt20 = (C * V).rolling(20, min_periods=10).mean() / 1e8

val = pd.read_sql("SELECT ticker,date,eps,pbr,per FROM valuation_daily", oc)
E = val.pivot_table(index='date', columns='ticker', values='eps', aggfunc='last')
PB = val.pivot_table(index='date', columns='ticker', values='pbr', aggfunc='last')
print(f"valuation_daily: {E.shape[0]}일 × {E.shape[1]}종목 ({E.index.min()}~{E.index.max()})")

# ---------- A) EPS 점프 이벤트 (PEAD) ----------
print("\n===== A) EPS 점프 이벤트 → forward 수익 (PEAD 가설) =====")
ev = []
edts = sorted(E.index)
for i in range(1, len(edts)):
    d0, d1 = edts[i-1], edts[i]
    prev, cur = E.loc[d0], E.loc[d1]
    m = prev.notna() & cur.notna() & (prev != 0)
    chg = (cur[m] - prev[m]) / prev[m].abs()
    jump = chg[chg.abs() >= 0.02]          # trailing EPS 2% 이상 변화 = 분기 실적 반영
    for tkr, c in jump.items():
        if d1 in R.index and tkr in R.columns and (amt20.loc[d1].get(tkr, 0) >= 5):
            ev.append((d1, tkr, c))
ev = pd.DataFrame(ev, columns=['date', 'ticker', 'chg'])
print(f"이벤트 수: {len(ev)} (개선 {(ev.chg>0).sum()} · 악화 {(ev.chg<0).sum()})")

def fwd(d, tkr, h):
    if d not in R.index:
        return np.nan
    t = R.index.get_loc(d)
    if t + 1 + h > len(R):
        return np.nan
    return float((1 + R[tkr].iloc[t+1:t+1+h]).prod() - 1) * 100

for h in (5, 10, 20):
    ev[f'f{h}'] = [fwd(d, tk, h) for d, tk in zip(ev.date, ev.ticker)]
for lbl, g in (("EPS 개선(>+2%)", ev[ev.chg > 0]), ("EPS 악화(<−2%)", ev[ev.chg < 0])):
    line = f"  {lbl:14s} n={len(g):4d}"
    for h in (5, 10, 20):
        v = g[f'f{h}'].dropna()
        if len(v) < 10:
            line += f" · f{h} 표본부족"
            continue
        i = RNG.integers(0, len(v), (3000, len(v)))
        lo, hi = np.quantile(v.values[i].mean(axis=1), [.025, .975])
        line += f" · f{h} {v.mean():+.2f}% [{lo:+.2f},{hi:+.2f}]"
    print(line)
print("  (해석: 개선−악화 격차가 벌어져 있고 CI가 분리되면 PEAD 기움. 시장수익 미차감 원값 주의)")
# 개선−악화 스프레드 (같은 날 짝 아님 — 참고)
for h in (5, 10, 20):
    a = ev[ev.chg > 0][f'f{h}'].dropna(); b = ev[ev.chg < 0][f'f{h}'].dropna()
    if len(a) > 10 and len(b) > 10:
        print(f"  개선−악화 스프레드 f{h}: {a.mean()-b.mean():+.2f}%p")

# ---------- B) 목표가 괴리율 ----------
print("\n===== B) 컨센서스 목표가 괴리율 (target/close − 1) forward IC =====")
cons = pd.read_sql("SELECT date, ticker, target_price FROM consensus_daily WHERE target_price IS NOT NULL", oc)
for snap in sorted(cons.date.unique()):
    s = cons[cons.date == snap].set_index('ticker').target_price
    if snap not in C.index:
        continue
    c0 = C.loc[snap]
    ups = (s / c0.reindex(s.index) - 1).dropna()
    g = amt20.loc[snap].reindex(ups.index) >= 5
    ups = ups[g]
    line = f"  {snap} (n={len(ups)})"
    for h in (5, 20):
        t = C.index.get_loc(snap)
        if t + 1 + h > len(R):
            line += f" · h{h} 미도래"
            continue
        y = ((1 + R[ups.index].iloc[t+1:t+1+h]).prod() - 1)
        m = ups.notna() & y.notna()
        line += f" · h{h} IC {ups[m].rank().corr(y[m].rank()):+.3f}"
    print(line)

# ---------- C) 밸류 (1/PBR) ----------
print("\n===== C) 밸류(1/PBR) forward IC — 주간 앵커 (참고: 창 6주) =====")
wk, ics = set(), {5: [], 20: []}
for d in sorted(PB.index):
    w = pd.Timestamp(d).isocalendar()[:2]
    if w in wk or d not in C.index:
        continue
    wk.add(w)
    t = C.index.get_loc(d)
    pb = PB.loc[d]
    m = pb.notna() & (pb > 0) & (amt20.loc[d] >= 5)
    s = (1 / pb[m])
    for h in (5, 20):
        if t + 1 + h > len(R):
            continue
        y = ((1 + R[s.index].iloc[t+1:t+1+h]).prod() - 1)
        mm = s.notna() & y.notna()
        if mm.sum() < 100:
            continue
        ics[h].append((d, s[mm].rank().corr(y[mm].rank())))
for h in (5, 20):
    if ics[h]:
        v = [x for _, x in ics[h]]
        print(f"  h{h}: 평균 IC {np.mean(v):+.3f} (앵커 {len(v)}개: " +
              " ".join(f"{d[-4:]}:{x:+.2f}" for d, x in ics[h]) + ")")
print("\n⚠ 전부 6주 창·반등 국면 in-sample — '기움' 이상 금지. 다음 단계는 데이터 축적 후 재스캔.")
