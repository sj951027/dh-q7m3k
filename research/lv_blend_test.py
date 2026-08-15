# -*- coding: utf-8 -*-
"""
lv_blend_test.py — "lv_a(수익)와 lv_b(선구안)를 섞으면?" 실측 (§14 탐색 전용, 2026-08-15)
==========================================================================================
혼합 = lv_a·lv_b 점수의 1:1 순위 평균 = lv_b + 반전 0.5 가중과 동치.
평가 두 축: ① 일별 IC(h5/h10/h20, lv_b 짝비교) ② 상위20 모의계좌(수익·변동성·MDD, ENTRY_LAG=1).
정직성: in-sample(6/25~8/13, 폭락+반등 국면), 승격은 새 model id + PREREGISTER 만.
"""
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
RNG = np.random.default_rng(20260815)
hc = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
oc = sqlite3.connect(f"file:{HERE.parent/'dh-q7m3k-data'/'ohlcv.db'}?mode=ro", uri=True)

la = pd.read_sql("SELECT run_id, ticker, lowvol_score s FROM lowvol_scores WHERE model_id='lv_a' AND run_id>='20260625'", hc)
lb = pd.read_sql("SELECT run_id, ticker, lowvol_score s FROM lowvol_scores WHERE model_id='lv_b' AND run_id>='20260625'", hc)
tk = sorted(set(la.ticker) | set(lb.ticker)); ph = ",".join("?"*len(tk))
px = pd.read_sql(f"SELECT ticker,date,change_pct FROM daily_ohlcv WHERE ticker IN ({ph}) AND date>='20260601'", oc, params=tk)
dts = sorted(px.date.unique())
R = px.pivot_table(index="date", columns="ticker", values="change_pct", aggfunc="last").reindex(dts)
runs = sorted(set(la.run_id) & set(lb.run_id))
print(f"공통 run {len(runs)}개 ({runs[0]}~{runs[-1]})")

def scores_at(rid):
    a = la[la.run_id == rid].set_index("ticker").s
    b = lb[lb.run_id == rid].set_index("ticker").s
    idx = a.index.intersection(b.index).intersection(R.columns)
    a, b = a[idx], b[idx]
    ens = a.rank(pct=True) + b.rank(pct=True)   # 1:1 순위 평균(동치: lv_b + 반전 0.5)
    return {"lv_a": a, "lv_b": b, "혼합(1:1)": ens}

# ① 일별 IC (h5/h10/h20) — lv_b 짝비교
ics = {h: {m: {} for m in ("lv_a","lv_b","혼합(1:1)")} for h in (5,10,20)}
for rid in runs:
    if rid not in R.index: continue
    t = R.index.get_loc(rid)
    sc = scores_at(rid)
    for h in (5,10,20):
        if t+h >= len(R): continue
        idx = sc["lv_b"].index
        y = ((1+R[idx].iloc[t+1:t+1+h]).prod()-1)
        for m, s in sc.items():
            mm = s.notna() & y.notna()
            if mm.sum() < 8: continue
            ics[h][m][rid] = s[mm].rank().corr(y[mm].rank())

def wboot(diffs, nb=3000):
    wk = {}
    for rid, d in diffs.items():
        wk.setdefault(pd.Timestamp(rid).isocalendar()[:2], []).append(d)
    b = np.array([np.mean(v) for v in wk.values()])
    if len(b) < 3: return (np.nan, np.nan)
    i = RNG.integers(0, len(b), (nb, len(b)))
    return tuple(np.quantile(b[i].mean(axis=1), [.025,.975]))

print("\n① 순위 실력(IC) — lv_b 대비 짝비교")
for h in (5,10,20):
    base = ics[h]["lv_b"]
    for m in ("lv_a","혼합(1:1)","lv_b"):
        d = ics[h][m]; com = sorted(set(d) & set(base))
        if not com: continue
        ic = np.mean([d[r] for r in com])
        if m == "lv_b":
            print(f"  h{h} {m:8s} IC {ic:+.3f} (기준, n_run {len(com)})"); continue
        diffs = {r: d[r]-base[r] for r in com}
        lo, hi = wboot(diffs)
        print(f"  h{h} {m:8s} IC {ic:+.3f} · diff {np.mean(list(diffs.values())):+.4f} CI[{lo:+.3f},{hi:+.3f}]")

# ② 상위20 모의계좌 (ENTRY_LAG=1)
print("\n② 실전 모의계좌 (상위20, 수수료 0)")
for m in ("lv_a","lv_b","혼합(1:1)"):
    rets = []
    for rid in runs:
        if rid not in R.index: continue
        t = R.index.get_loc(rid)
        if t+1 >= len(R): continue
        s = scores_at(rid)[m]
        top = s.nlargest(20).index
        rets.append((dts[t+1], float(R.iloc[t+1][top].astype(float).mean(skipna=True))))
    sr = pd.Series(dict(rets)).sort_index().ffill(limit=2).fillna(0)
    nav = (1+sr).cumprod()
    mdd = float((nav/nav.cummax()-1).min())*100
    print(f"  {m:8s} 누적 {float(nav.iloc[-1]-1)*100:+.1f}% · 일변동성 {sr.std()*100:.2f}% · MDD {mdd:+.1f}% · n {len(sr)}일")
print("\n⚠ in-sample 단일 국면(폭락+반등) — 채택 판단 금지. 등록은 새 model id + PREREGISTER 만.")
