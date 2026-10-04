# -*- coding: utf-8 -*-
"""E4b·E5b — 결과를 본 뒤의 추가 탐색(사후): ① 실적 놀람 크기별·보유기간별(5~60봉)·시총별 ② 120일선 규칙의 전환 횟수·길이 민감도. python e4b_e5b_followup.py"""
import numpy as np, pandas as pd
from w20lib import *

s = study(choose=False); T, N = s.T, s.N; c, o, ok, ff = s.c, s.o, s.ok, s.ff; dates = s.d
shares = s.z["shares"].astype(float)
E = pd.read_parquet(HERE / "events_trades.parquet"); tix = {t: i for i, t in enumerate(s.tick)}
# ① 실적: e4 의 사건을 다시 만들지 않고 '실적:전체 · d0+1 시가' 거래에 놀람 크기를 붙이기 위해 e4 의 EV 를 재계산
import importlib, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    e4 = importlib.import_module("e4_events")
EV = e4.EV.copy(); EV = EV[(EV.d0 >= s.t0) & (EV.d0 < T - 62) & ok[EV.d0.values, EV.k.values]]
f = np.array([entry_ok(s, t)[k] for t, k in zip(EV.d0, EV.k)]); EV = EV[f]
base = o[EV.d0.values + 1, EV.k.values]
um = {}   # 같은 날 전 종목 평균(시가 진입, h봉)
for h in (5, 10, 20, 40, 60):
    EV[f"r{h}"] = (ff[EV.d0.values + h, EV.k.values] / base - 1 - COST) * 100
    for t in EV.d0.unique():
        fo = entry_ok(s, t) & ok[t]; um[(t, h)] = np.mean(ff[t + h, fo] / o[t + 1, fo] - 1 - COST) * 100
    EV[f"x{h}"] = EV[f"r{h}"] - [um[(t, h)] for t in EV.d0]
EV["mcap_pct"] = rank(np.log(c * shares), ok)[EV.d0.values, EV.k.values]
EV["bin"] = pd.cut(EV.sue, [-np.inf, -.03, -.01, 0, .01, .03, np.inf], labels=["≤−3%", "−3~−1%", "−1~0%", "0~+1%", "+1~+3%", "≥+3%"])


def cci(g, col, k=2000):
    a = g.groupby("d0")[col].agg(["sum", "count"]); n = len(a); idx = np.random.default_rng(7).integers(0, n, (k, n))
    return np.quantile(a["sum"].values[idx].sum(1) / a["count"].values[idx].sum(1), [.025, .975])


print("[실적 놀람(영업이익 증가분 ÷ 시총) 크기별 — 같은 날 전 종목 대비 초과%p, 보유 5/10/20/40/60봉 · 20봉 +20% 비율]")
for b, g in EV.groupby("bin", observed=True):
    lo, hi = cci(g, "x20"); lo6, hi6 = cci(g, "x60")
    print(f"  {b:<8} n {len(g):>5} · " + " · ".join(f"{h}봉 {g[f'x{h}'].mean():+.2f}" for h in (5, 10, 20, 40, 60)) + f" · 20봉 CI [{lo:+.2f},{hi:+.2f}] · 60봉 CI [{lo6:+.2f},{hi6:+.2f}] · +20% {np.mean(g.r20 >= 20)*100:.1f}%")
pos = EV[EV.sue >= .01]
print("\n[놀람 ≥ +1% 를 시총 순위로 나눔 — 20봉·60봉 초과%p]")
for nm, m in (("시총 하위 50%", pos.mcap_pct < .5), ("상위 50~80%", (pos.mcap_pct >= .5) & (pos.mcap_pct < .8)), ("상위 20%", pos.mcap_pct >= .8)):
    g = pos[m]; lo, hi = cci(g, "x20"); print(f"  {nm:<12} n {len(g):>5} · 20봉 {g.x20.mean():+.2f} [{lo:+.2f},{hi:+.2f}] · 60봉 {g.x60.mean():+.2f} · +20%(20봉) {np.mean(g.r20>=20)*100:.1f}% · 60봉 종료 양(+) {np.mean(g.r60>0)*100:.0f}%")
ss = pos.groupby("season").x60.mean(); print(f"  놀람 ≥ +1% 의 60봉 초과: 분기 묶음 {len(ss)}개 중 양(+) {int((ss>0).sum())}개 · 묶음 평균 {ss.mean():+.2f}%p · 묶음 표준오차 {ss.std()/np.sqrt(len(ss)):.2f}")
ss = pos.groupby("season").x20.mean(); print(f"  놀람 ≥ +1% 의 20봉 초과: 분기 묶음 {len(ss)}개 중 양(+) {int((ss>0).sum())}개 · 묶음 평균 {ss.mean():+.2f}%p · 묶음 표준오차 {ss.std()/np.sqrt(len(ss)):.2f}")
EV.drop(columns=["bin"]).to_parquet(HERE / "events_earnings_horizons.parquet", index=False)

# ② 120일선 규칙: 전환 횟수와 길이 민감도
D = pd.read_csv(HERE / "daily_tranche_series.csv", index_col=0); D.index = D.index.astype(str)
kq = s.idx[:, 1]; days = np.array([s.di[d] for d in D.index]); bench = D["지수 반반"].values
print("\n[코스닥 N일선 위에서만 보유 — 길이 민감도(사후). 전환 = 켜짐↔꺼짐 바뀐 횟수]")
for w in (40, 60, 80, 100, 120, 150):
    sig = kq > pd.Series(kq).rolling(w, min_periods=w).mean().values; e = np.r_[0, sig[:-1].astype(float)][days]; sw = int(np.abs(np.diff(e)).sum())
    line = f"  {w:>3}일선: 켜짐 {e.mean():.0%} · 전환 {sw:>2}회"
    for col in ("고베타+고점 근접", "거래대금 상위10", "지수 반반"):
        x = e * D[col].values - np.abs(np.r_[0, np.diff(e)]) * COST / 2; n = len(x) // 20
        xs = np.array([np.prod(1 + x[i*20:(i+1)*20]) - 1 for i in range(n)]); bs = np.array([np.prod(1 + bench[i*20:(i+1)*20]) - 1 for i in range(n)]); up = bs > 0
        cum = np.cumprod(1 + x); line += f" | {col}: up {xs[up].mean()/bs[up].mean():.2f} dn {xs[~up].mean()/bs[~up].mean():.2f} 누적 {(cum[-1]-1)*100:+.0f}% 낙폭 {(cum/np.maximum.accumulate(cum)-1).min()*100:.0f}%"
    print(line)
sig = kq > pd.Series(kq).rolling(120, min_periods=120).mean().values; e = np.r_[0, sig[:-1].astype(float)][days]
ch = np.where(np.diff(e) != 0)[0] + 1; print("  120일선 전환 날짜:", [f"{D.index[i]}{'↑' if e[i] else '↓'}" for i in ch])
