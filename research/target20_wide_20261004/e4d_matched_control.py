# -*- coding: utf-8 -*-
"""E4d — 실적 놀람 효과를 '같은 시장·같은 시총 구간' 대조로 다시 잰다(Codex 조건 탐색의 시장 분리 지적 반영, 2026-10-04).
E4c 의 사건(처음 알려진 날 기준)을 그대로 쓰고 대조만 바꾼다: 같은 날, 같은 시장(KOSPI/KOSDAQ), 같은 시총 구간(상위 20% / 50~80% / 하위 50%)의 가드 통과 종목 평균.
python e4d_matched_control.py"""
import numpy as np, pandas as pd
from w20lib import *

s = study(choose=False); T, N = s.T, s.N; c, o, ok, ff = s.c, s.o, s.ok, s.ff; dates = s.d
shares = s.z["shares"].astype(float); mcp = rank(np.log(c * shares), ok)
E = pd.read_parquet(HERE / "events_first_disclosure.parquet"); E["mk"] = s.mi[E.k.values]
bucket = lambda p: np.where(p >= .8, 2, np.where(p >= .5, 1, 0)); E["b"] = bucket(E.mcap_pct.values)
B = bucket(np.nan_to_num(mcp, nan=-1)); cache = {}
for h in (20, 60):
    out = []
    for t, m, b in zip(E.d0.values, E.mk.values, E.b.values):
        key = (t, m, b, h)
        if key not in cache:
            f = entry_ok(s, t) & ok[t] & (s.mi == m) & (B[t] == b) & np.isfinite(mcp[t])
            cache[key] = np.mean(ff[t + h, f] / o[t + 1, f] - 1 - COST) * 100 if f.sum() >= 5 else np.nan
        out.append(cache[key])
    E[f"m{h}"] = E[f"r{h}"] - np.array(out)


def cci(g, col, k=2000):
    g = g.dropna(subset=[col]); a = g.groupby("d0")[col].agg(["sum", "count"]); n = len(a)
    if n < 5: return (np.nan, np.nan)
    idx = np.random.default_rng(7).integers(0, n, (k, n)); return tuple(np.quantile(a["sum"].values[idx].sum(1) / a["count"].values[idx].sum(1), [.025, .975]))


MK = {0: "KOSPI", 1: "KOSDAQ"}; BK = {2: "시총 상위20%", 1: "50~80%", 0: "하위50%"}
print("[실적 놀람 — 대조를 '같은 날·같은 시장·같은 시총 구간'으로] 초과 %p (괄호 = 종전 '전 종목' 대조)")
rows = []
for nm, cond in (("놀람≥+1%", E.sue >= .01), ("놀람≤−1%", E.sue <= -.01), ("전체(놀람 무관)", E.sue > -9)):
    for lab, m in [("두 시장 합", E.mk >= 0), ("KOSPI", E.mk == 0), ("KOSDAQ", E.mk == 1)] + [(f"{MK[a]} {BK[b]}", (E.mk == a) & (E.b == b)) for a in (0, 1) for b in (2, 1, 0)]:
        g = E[cond & m]
        if len(g) < 30: continue
        lo, hi = cci(g, "m20"); l6, h6 = cci(g, "m60"); ss = g.groupby("season").m20.mean(); yy = g.assign(y=[dates[i][:4] for i in g.d0]).groupby("y").m20.mean().round(2).to_dict()
        print(f"  {nm:<12} {lab:<16} n {len(g):>5} · 20봉 {g.m20.mean():+.2f} [{lo:+.2f},{hi:+.2f}] ({g.x20.mean():+.2f}) · 60봉 {g.m60.mean():+.2f} [{l6:+.2f},{h6:+.2f}] ({g.x60.mean():+.2f}) · 묶음 양(+) {int((ss > 0).sum())}/{len(ss)} · 연도 {yy}")
        rows.append(dict(signal=nm, group=lab, n=len(g), m20=g.m20.mean(), m20_lo=lo, m20_hi=hi, x20=g.x20.mean(), m60=g.m60.mean(), m60_lo=l6, m60_hi=h6, x60=g.x60.mean(), seasons_pos=int((ss > 0).sum()), seasons=len(ss)))
pd.DataFrame(rows).to_csv(HERE / "events_matched_control.csv", index=False, encoding="utf-8-sig")
