# -*- coding: utf-8 -*-
"""E2·E3 — 진입·청산 주문 방식. 후보 3개(Codex 고정) + 사후 추가 1개(E1 을 본 뒤: 공격형 ∩ 시총 상위 20%). python e23_orders.py"""
import numpy as np, pandas as pd
from w20lib import *
from orders import *

s = study(); sim = Sim(s); dates = s.d
shares = s.z["shares"].astype(float); mc = rank(np.log(s.c * shares), s.ok)
picks = {k: s.picks[k] for k in RULES3}
sc = s.rules["highbeta_high"]; mk = s.masks["highbeta_high"] & (mc >= .8); pk = []
for t in range(s.T):
    ix = np.where(mk[t] & np.isfinite(sc[t]))[0]; pk.append(ix[np.argsort(-sc[t, ix], kind="stable")[:10]])
picks["highbeta_large"] = pk; NAMES = dict(RULES3, highbeta_large="공격형∩시총 상위20%(사후 추가)")
TS = np.arange(s.t0, s.t1); listd = dates[TS]

# 밤사이·장중 분해(전 종목·후보별): 목록 다음날 '종가→시가'와 '시가→종가'
print("[밤사이 vs 장중] 목록 다음날 평균 수익 %(가드 통과 종목)")
_o = np.where(s.o > 0, s.o, np.nan); on = _o[1:] / s.c[:-1] - 1; intr = s.c[1:] / _o[1:] - 1
for nm, pkk in [("전 종목", None)] + list(picks.items()):
    a, b = [], []
    for t in TS:
        ix = np.where(s.ok[t])[0] if pkk is None else pkk[t]
        a.append(np.nanmean(on[t, ix])); b.append(np.nanmean(intr[t, ix]))
    print(f"  {NAMES.get(nm, nm):<28} 밤사이 {np.nanmean(a)*100:+.3f}% · 장중 {np.nanmean(b)*100:+.3f}% · 장중 양(+)인 날 {np.mean(np.array(b)>0):.0%}")

allr = []
for nm, pkk in picks.items():
    t = np.concatenate([np.full(len(pkk[x]), x) for x in TS]); k = np.concatenate([pkk[x] for x in TS])
    allr.append(run(sim, nm, t, k, dates))
TR = pd.concat(allr, ignore_index=True); TR["year"] = TR.date.str[:4]
TR.to_parquet(HERE / "orders_trades.parquet", index=False)
nsig = {nm: {x: len(pkk[x]) for x in TS} for nm, pkk in picks.items()}


def daily(g):   # 날짜별 slot 수익(%) — 미체결·신호 없음 = 0
    return (g.groupby("date").net.sum() / 10 * 100).reindex(listd, fill_value=0.0)


rows = []; base = {}
for (rule, em, xm), g in TR.groupby(["rule", "entry", "exit"]):
    d = daily(g)
    if em == "open" and xm == "hold": base[rule] = d
for (rule, em, xm), g in TR.groupby(["rule", "entry", "exit"]):
    d = daily(g); diff = d - base[rule]
    for per in ("all", "2024", "2025", "2026"):
        gg = g if per == "all" else g[g.year == per]; m = np.ones(len(listd), bool) if per == "all" else np.array([x[:4] == per for x in listd])
        ns = sum(v for x, v in nsig[rule].items() if m[x - s.t0])
        lo, hi = block_ci(d[m].values); dlo, dhi = block_ci(diff[m].values)
        rows.append(dict(rule=rule, entry=em, exit=xm, period=per, n_dates=int(m.sum()), n_signal=ns, n_fill=len(gg), fill=len(gg) / max(ns, 1),
                         win20=(gg.net >= .1999).mean(), win20_per_signal=(gg.net >= .1999).sum() / max(ns, 1), mean=gg.net.mean() * 100, median=gg.net.median() * 100,
                         slot=d[m].mean(), slot_lo=lo, slot_hi=hi, d_slot=diff[m].mean(), d_lo=dlo, d_hi=dhi, loss=(gg.net < 0).mean(), p10=gg.net.quantile(.1) * 100,
                         worst=gg.net.min() * 100, mae=gg.mae.mean() * 100, bars=gg.bars.mean(), d0_up=gg.d0_up.mean(), d1_up=gg.d1_up.mean(), unresolved=int(gg.unresolved.sum())))
R = pd.DataFrame(rows); R.to_csv(HERE / "orders_summary.csv", index=False, encoding="utf-8-sig")
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 300)


def show(df, cols):
    x = df.copy()
    for c_ in ("fill", "win20", "win20_per_signal", "loss", "d0_up", "d1_up"): x[c_] = (x[c_] * 100).round(1)
    x["slot_ci"] = x.apply(lambda r_: f"{r_.slot:+.2f} [{r_.slot_lo:+.2f},{r_.slot_hi:+.2f}]", axis=1)
    x["vs_base"] = x.apply(lambda r_: f"{r_.d_slot:+.2f} [{r_.d_lo:+.2f},{r_.d_hi:+.2f}]", axis=1)
    x["rule"] = x.rule.map(NAMES); return x[cols].round(2).to_string(index=False)


A = R[R.period == "all"]
print(f"\n목록일 {len(listd)}일 ({listd[0]}~{listd[-1]}) · slot = 하루 10자리 평균 수익%(미체결 0) · vs_base = 같은 후보의 '시가·20봉 보유' 대비(같은 날짜 짝, 20일 블록 CI)")
print("\n[E2 진입 방식 — 청산은 20봉 보유 고정]")
print(show(A[A.exit == "hold"], ["rule", "entry", "n_fill", "fill", "win20", "win20_per_signal", "mean", "slot_ci", "vs_base", "loss", "mae", "d0_up", "d1_up"]))
print("\n[E3 청산 방식 — 진입은 다음날 시가 고정]")
print(show(A[A.entry == "open"], ["rule", "exit", "n_fill", "win20", "mean", "median", "slot_ci", "vs_base", "loss", "p10", "worst", "mae", "bars", "unresolved"]))
print("\n[조합 전체 중 실제 청산 +20% 비율 상위 12 (체결 500건 이상)]")
print(show(A[A.n_fill >= 500].sort_values("win20", ascending=False).head(12), ["rule", "entry", "exit", "n_fill", "fill", "win20", "mean", "slot_ci", "vs_base", "loss", "mae", "bars"]))
print("\n[조합 전체 중 거래당 평균 수익 상위 12 (체결 500건 이상)]")
print(show(A[A.n_fill >= 500].sort_values("mean", ascending=False).head(12), ["rule", "entry", "exit", "n_fill", "fill", "win20", "mean", "slot_ci", "vs_base", "loss", "mae", "bars"]))
Y = R[R.period != "all"].pivot_table(index=["rule", "entry", "exit"], columns="period", values=["win20", "mean", "d_slot"])
sel = [(r_, e_, x_) for r_ in ("highbeta_high", "control_amount", "highbeta_large") for e_, x_ in (("open", "hold"), ("open", "tp"), ("open", "tp_stop"), ("open", "tp_time10"), ("stop1", "hold"), ("stop1", "tp"), ("limit3", "hold"), ("limit3", "tp"), ("close_up", "tp"))]
print("\n[연도별 — 실제 +20% 청산 비율(win20, 0~1) · 거래당 평균% · 기준 대비 slot 차이%p]"); print(Y.loc[sel].round(3).to_string())
