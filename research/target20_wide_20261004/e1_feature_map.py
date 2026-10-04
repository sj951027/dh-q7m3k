# -*- coding: utf-8 -*-
"""E1 특성 지도 — 어떤 특성이 '+20% 적중'과 '중간 낙폭'을 같이 움직이나. 탐색(판정 아님). python research/target20_wide_20261004/e1_feature_map.py"""
import numpy as np, pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from w20lib import *

s = study(choose=False); c, o, h, l, v, r, ok = s.c, s.o, s.h, s.l, s.v, s.r, s.ok
M = fwd_metrics(s)
F = dict(s.feats)
mr = returns(s.idx, 1)[:, s.mi]; shares = s.z["shares"].astype(float); turn = v / np.where(shares > 0, shares, np.nan)
ma20 = rolling(c, 20); ma60 = rolling(c, 60); gap = o / lag(c) - 1
tr = np.nanmax(np.stack([h - l, np.abs(h - lag(c)), np.abs(l - lag(c))]), axis=0)
up = np.where(r > 0, r, 0.0); dn = np.where(r < 0, -r, 0.0)
au = pd.DataFrame(up).ewm(alpha=1 / 14, min_periods=14).mean().values; ad = pd.DataFrame(dn).ewm(alpha=1 / 14, min_periods=14).mean().values
cfill = np.nan_to_num(c, nan=-np.inf); w = sliding_window_view(cfill, 252, axis=0)   # (T-251, N, 252)
dsh = np.full(c.shape, np.nan); dsh[251:] = 251 - np.argmax(w, axis=2)
streak = np.zeros(c.shape)
for t in range(1, s.T): streak[t] = np.where(r[t] > 0, streak[t - 1] + 1, 0)
F.update(dict(
    ret1=r, gap=gap, range1=(h - l) / c, atr14=rolling(tr, 14, 10) / c, max21=rolling(r, 21, 15, "max"), min21=rolling(r, 21, 15, "min"),
    dlow252=c / rolling(c, 252, 120, "min") - 1, rsi14=100 - 100 / (1 + au / ad), turn20=rolling(turn, 20, 10), vol5_60=rolling(v, 5, 4) / rolling(v, 60, 40),
    mcap=np.log(c * shares), price=np.log(c), days_since_high=dsh, obv63=rolling(np.sign(np.nan_to_num(r)) * v, 63, 30) / rolling(v, 63, 30),
    ma60gap=c / ma60 - 1, ma20slope=ma20 / lag(ma20, 5) - 1, bbw20=rolling(c, 20, 15, "std") / ma20, up_streak=streak,
    limitup60=rolling((r >= .295).astype(float), 60, 20, "sum"), ivol60=rolling(r - s.feats["beta"] * mr, 60, 40, "std"),
    skew60=pd.DataFrame(r).rolling(60, min_periods=40).skew().values, body20=rolling((c - o) / o, 20, 15), on60=rolling(gap, 60, 40),
    rs5=returns(c, 5) - returns(s.idx, 5)[:, s.mi], mom120_20=s.feats["ret120"] - s.feats["ret20"], hi20gap=c / rolling(c, 20, 15, "max") - 1,
    amihud20=rolling(np.abs(r) / np.where(s.amt > 0, s.amt, np.nan), 20, 10) * 1e9,
))
sl = slice(s.t0, s.t1 - 0); T0, T1 = s.t0, min(s.t1, s.T - H - 1)
valid = ok & np.isfinite(M["term"]); valid[:T0] = False; valid[T1:] = False
yr = np.broadcast_to(s.year[:, None], c.shape)
keys = ("hit", "touch", "first_up", "term", "mae", "frac", "joint")


def agg(mask):
    return {k: float(np.nanmean(M[k][mask])) for k in keys} | {"n": int(mask.sum())}


base = {p: agg(valid & ((yr == p) if p != "all" else True)) for p in ("all", "2024", "2025", "2026")}
print("기준(전 종목):", {p: {k: round(b[k] * (100 if k != "n" and k != "frac" else 1), 2) for k in ("n", "hit", "touch", "first_up", "term", "mae")} for p, b in base.items()})
rows = []
for name, a in F.items():
    pct = rank(a, ok); dec = np.ceil(pct * 10).clip(1, 10)
    for k in range(1, 11):
        for p in ("all", "2024", "2025", "2026"):
            m = valid & (dec == k) & ((yr == p) if p != "all" else True)
            if m.sum() < 500: continue
            rows.append(dict(feature=name, decile=k, period=p, **agg(m)))
D = pd.DataFrame(rows); D.to_csv(HERE / "e1_deciles.csv", index=False, encoding="utf-8-sig")

A = D[D.period == "all"].copy()
# (적중, 낙폭) 관계: 모든 (특성,등분) 칸에서 hit ~ mae 직선. 선 위쪽(낙폭 대비 적중이 높은) 칸이 '공짜 점심' 후보.
b1, b0 = np.polyfit(A.mae, A.hit, 1); A["hit_resid"] = A.hit - (b0 + b1 * A.mae)
print(f"\n[적중률 ~ 낙폭] 칸 {len(A)}개: 적중 = {b0*100:.1f}% + {b1:.2f} × 낙폭 · 상관 {np.corrcoef(A.mae, A.hit)[0,1]:+.2f}")
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
def show(df):
    x = df.copy()
    for k in ("hit", "touch", "first_up", "term", "mae", "joint", "hit_resid"):
        if k in x: x[k] = (x[k] * 100).round(2)
    return x
print("\n[낙폭 대비 적중이 높은 칸 상위 15]"); print(show(A.sort_values("hit_resid", ascending=False).head(15))[["feature", "decile", "n", "hit", "touch", "first_up", "term", "mae", "joint", "hit_resid"]].to_string(index=False))
print("\n[적중률 상위 15 칸]"); print(show(A.sort_values("hit", ascending=False).head(15))[["feature", "decile", "n", "hit", "touch", "first_up", "term", "mae", "joint", "hit_resid"]].to_string(index=False))
print("\n[첫날 상승 비율 상위 10 칸]"); print(show(A.sort_values("first_up", ascending=False).head(10))[["feature", "decile", "n", "hit", "first_up", "term", "mae"]].to_string(index=False))
print("\n[평균 수익 상위 10 칸]"); print(show(A.sort_values("term", ascending=False).head(10))[["feature", "decile", "n", "hit", "first_up", "term", "mae"]].to_string(index=False))
# 연도 일관성: 상위 칸들이 세 연도 모두 기준보다 나은가
Y = D[D.period != "all"].pivot_table(index=["feature", "decile"], columns="period", values=["hit", "term", "mae"])
top = A.sort_values("hit_resid", ascending=False).head(15)[["feature", "decile"]].apply(tuple, axis=1)
print("\n[위 '낙폭 대비 적중' 상위 15 칸의 연도별 적중·평균수익 (기준: " + " / ".join(f"{p} 적중 {base[p]['hit']*100:.1f}% 평균 {base[p]['term']*100:+.2f}%" for p in ("2024", "2025", "2026")) + ")]")
print((Y.loc[list(top)] * 100).round(2).to_string())

# 2단: 공격 풀(고베타+고점 근접 점수 상위 10%) 안에서 둘째 특성 5등분
sc = s.rules["highbeta_high"]; pool = ok & (rank(sc, ok) >= .9) & valid
pb = agg(pool); print(f"\n[공격 풀] n {pb['n']} · 적중 {pb['hit']*100:.1f}% · 닿음 {pb['touch']*100:.1f}% · 첫날↑ {pb['first_up']*100:.1f}% · 평균 {pb['term']*100:+.2f}% · 낙폭 {pb['mae']*100:.1f}%")
rows = []
for name, a in F.items():
    q = np.ceil(rank(a, pool) * 5).clip(1, 5)
    for k in range(1, 6):
        for p in ("all", "2024", "2025", "2026"):
            m = pool & (q == k) & ((yr == p) if p != "all" else True)
            if m.sum() < 300: continue
            rows.append(dict(feature=name, quintile=k, period=p, **agg(m)))
Q = pd.DataFrame(rows); Q.to_csv(HERE / "e1_pool_quintiles.csv", index=False, encoding="utf-8-sig")
QA = Q[Q.period == "all"].copy(); QA["d_hit"] = QA.hit - pb["hit"]; QA["d_mae"] = QA.mae - pb["mae"]; QA["d_term"] = QA.term - pb["term"]
both = QA[(QA.d_hit > 0) & (QA.d_mae > 0)].sort_values("d_term", ascending=False)
print("\n[풀 안에서 적중↑ 이면서 낙폭↓ 인 칸 — 평균수익 개선 순 상위 15]")
x = both.head(15).copy()
for k in ("hit", "touch", "first_up", "term", "mae", "d_hit", "d_mae", "d_term"): x[k] = (x[k] * 100).round(2)
print(x[["feature", "quintile", "n", "hit", "touch", "first_up", "term", "mae", "d_hit", "d_mae", "d_term"]].to_string(index=False))
QY = Q[Q.period != "all"].pivot_table(index=["feature", "quintile"], columns="period", values=["hit", "term", "mae"])
py = {p: agg(pool & (yr == p)) for p in ("2024", "2025", "2026")}
print("\n[그 칸들의 연도별 (풀 기준: " + " / ".join(f"{p} 적중 {py[p]['hit']*100:.1f}% 평균 {py[p]['term']*100:+.2f}% 낙폭 {py[p]['mae']*100:.1f}%" for p in py) + ")]")
print((QY.loc[list(both.head(15)[["feature", "quintile"]].apply(tuple, axis=1))] * 100).round(2).to_string())
