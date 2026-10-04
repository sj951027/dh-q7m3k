# -*- coding: utf-8 -*-
"""E6 — 사후 조합(E1~E5 결과를 본 뒤): '최근 60봉 안에 실적 놀람(+)'을 후보 조건으로 얹으면 달라지나. 같은 패널 → 독립 검증 아님. python e6_combo.py"""
import io, contextlib, importlib
import numpy as np, pandas as pd
from w20lib import *
from orders import *

s = study(); sim = Sim(s); T, N = s.T, s.N; c, ok = s.c, s.ok; dates = s.d
with contextlib.redirect_stdout(io.StringIO()):
    e4 = importlib.import_module("e4_events")
EV = e4.EV
POS = np.zeros((T, N), bool); NEG = np.zeros((T, N), bool)
for d0, k, sue in zip(EV.d0.values, EV.k.values, EV.sue.values):      # 공시 다음 거래일 저녁 목록부터 60봉 동안
    a, b = d0 + 1, min(d0 + 61, T)
    if sue >= .01: POS[a:b, k] = True
    elif sue <= -.01: NEG[a:b, k] = True
shares = s.z["shares"].astype(float); mc = rank(np.log(c * shares), ok); sc = s.rules["highbeta_high"]; nh = s.feats["nh252"]
M = fwd_metrics(s); valid = ok & np.isfinite(M["term"]); yr = np.broadcast_to(s.year[:, None], c.shape)
pool = valid & (rank(sc, ok) >= .9)
print("[칸 비교 — 시가 진입·20봉 보유: n · 종가 +20% · 5~20봉 닿음 · 첫날↑ · 평균 · 종가 최저 낙폭 | 연도별 평균]")
for nm, m in (("전 종목", valid), ("전 종목 ∩ 실적 놀람(+)", valid & POS), ("전 종목 ∩ 실적 놀람(−)", valid & NEG), ("공격 풀(상위10%)", pool), ("공격 풀 ∩ 놀람(+)", pool & POS), ("공격 풀 ∩ 놀람(−)", pool & NEG),
              ("공격 풀 ∩ 시총 상위20%", pool & (mc >= .8)), ("공격 풀 ∩ 시총 상위20% ∩ 놀람(+)", pool & (mc >= .8) & POS), ("놀람(+) ∩ 시총 상위20%", valid & POS & (mc >= .8))):
    g = lambda k_, mm=m: np.nanmean(M[k_][mm]) * 100
    print(f"  {nm:<26} n {int(m.sum()):>7} · {g('hit'):5.1f}% · {g('touch'):5.1f}% · {g('first_up'):5.1f}% · {g('term'):+6.2f}% · {g('mae'):6.1f}% | " + " ".join(f"{y} {np.nanmean(M['term'][m & (yr == y)])*100:+.2f}%({int((m & (yr == y)).sum())})" for y in ("2024", "2025", "2026")))


def top10(mask, score):
    out = []
    for t in range(T):
        ix = np.where(mask[t] & np.isfinite(score[t]))[0]; out.append(ix[np.argsort(-score[t, ix], kind="stable")[:10]])
    return out


picks = {"highbeta_high": s.picks["highbeta_high"], "control_amount": s.picks["control_amount"],
         "pos_highbeta": top10(s.masks["highbeta_high"] & POS, sc), "pos_nearhigh": top10(ok & POS, nh), "pos_large_nearhigh": top10(ok & POS & (mc >= .8), nh)}
NAMES = {"highbeta_high": "고베타+고점 근접(기준)", "control_amount": "거래대금 상위10(기준)", "pos_highbeta": "놀람(+) ∩ 고베타+고점 점수순", "pos_nearhigh": "놀람(+) → 고점 근접순", "pos_large_nearhigh": "놀람(+) ∩ 시총 상위20% → 고점 근접순"}
TS = np.arange(s.t0, s.t1); listd = dates[TS]; res = {}
for nm, pkk in picks.items():
    t = np.concatenate([np.full(len(pkk[x]), x) for x in TS]); k = np.concatenate([pkk[x] for x in TS]).astype(int)
    res[nm] = run(sim, nm, t, k, dates, entries=("open",), exits=("hold", "tp"))
print(f"\n[상위10 목록으로 — 목록일 {len(listd)}일 · slot = 10자리 평균(빈 자리 현금) · 차이 = 같은 날 '고베타+고점 근접' 대비]")
base = {x: (res["highbeta_high"][res["highbeta_high"].exit == x].groupby("date").net.sum() / 10 * 100).reindex(listd, fill_value=0.0) for x in ("hold", "tp")}
rows = []
for nm, TR in res.items():
    TR["year"] = TR.date.str[:4]
    for xm, g in TR.groupby("exit"):
        d = (g.groupby("date").net.sum() / 10 * 100).reindex(listd, fill_value=0.0); lo, hi = block_ci(d.values); dl, dh = block_ci((d - base[xm]).values)
        yy = " ".join(f"{y}: {g[g.year == y].net.mean()*100:+.2f}%/{(g[g.year == y].net >= .1999).mean()*100:.0f}%" for y in ("2024", "2025", "2026"))
        print(f"  {NAMES[nm]:<30} {EXITS[xm]:<10} 체결 {len(g):>5}(하루 {len(g)/len(listd):.1f}) · +20% 청산 {(g.net >= .1999).mean()*100:5.1f}% · 거래당 {g.net.mean()*100:+.2f}% · 중앙 {g.net.median()*100:+.2f}% · 손실 {(g.net < 0).mean()*100:.0f}% · 낙폭 {g.mae.mean()*100:.1f}% · slot {d.mean():+.2f} [{lo:+.2f},{hi:+.2f}] · 차이 {(d - base[xm]).mean():+.2f} [{dl:+.2f},{dh:+.2f}] | 연도 거래당/적중 {yy}")
pd.concat(res.values()).to_parquet(HERE / "combo_trades.parquet", index=False)
