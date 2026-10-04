# -*- coding: utf-8 -*-
"""E8 — (가) '피할 것' 표시가 장(시기·국면)마다 다른가 (나) 실적 악화 표시를 실제 목록에 얹으면? (읽기 전용 · 관측 · 2026-10-04)
(가) 전 종목(가드 통과) 3년에서 표시 종목의 20봉 초과(같은 날·같은 시장 평균 대비)를 연도·반기·국면별로 쪼갠다.
     국면 = 목록일의 코스닥이 120일선 위/아래(그날 알 수 있는 값) + 참고로 '그 뒤 20봉 시장 평균이 올랐나/내렸나'(사후 구분).
     E7 이 본 2026-06~09 를 전 종목으로도 따로 본다 → 목록 안에서만 그런지, 그 시기 전체가 그랬는지.
(나) 실적 표시: 처음 알려진 날 다음 거래일부터 60봉 동안 '실적 악화(영업이익 감소분 ≥ 시총 1%)'·'실적 개선(증가분 ≥ 1%)'. E7 과 같은 방식으로 실제 목록에.
python e8_flags_regime_earnings.py"""
import io, contextlib, importlib, sqlite3
import numpy as np, pandas as pd
from w20lib import *

with contextlib.redirect_stdout(io.StringIO()):
    e7 = importlib.import_module("e7_avoid_flags_on_lists"); e4c = importlib.import_module("e4c_first_disclosure")
s = e7.s; T, N = s.T, s.N; ok, dates = s.ok, s.d; ret, mean_mk = e7.ret, e7.mean_mk; c = s.c; shares = e7.shares
exc = ret - mean_mk[:, s.mi]                                   # 같은 날·같은 시장 전 종목 평균 대비
valid = ok & np.isfinite(exc); valid[:s.t0] = False
# ---- 실적 표시(처음 알려진 날 d0 → d0+1 … d0+60)
EV = e4c.EV.copy(); EV["d0"] = np.searchsorted(dates, EV.d_first.values); EV = EV[(EV.d0 >= 1) & (EV.d0 < T - 1)]
mc = c[EV.d0.values - 1, EV.k.values] * shares[EV.d0.values - 1, EV.k.values]; EV = EV[np.isfinite(mc) & (mc > 0)]; EV["sue"] = (EV.q_this - EV.q_prev) / mc[np.isfinite(mc) & (mc > 0)]
NEG = np.zeros((T, N), bool); POS = np.zeros((T, N), bool); KNOWN = np.zeros((T, N), bool)
for d0, k, sue in zip(EV.d0.values, EV.k.values, EV.sue.values):
    a, b = d0 + 1, min(d0 + 61, T); KNOWN[a:b, k] = True
    if sue <= -.01: NEG[a:b, k] = True
    elif sue >= .01: POS[a:b, k] = True
FL = dict(e7.FLAGS); FL["실적 악화(60봉)"] = NEG; FL["실적 개선(60봉)"] = POS
kq = s.idx[:, 1]; above120 = kq > pd.Series(kq).rolling(120, min_periods=120).mean().values
mkt_up = np.nanmean(mean_mk, axis=1) > 0                          # 사후: 그 뒤 20봉 전 종목 평균이 올랐나
ym = np.array([d[:6] for d in dates]); yr = np.array([d[:4] for d in dates])
half = np.array([d[:4] + ("상" if d[4:6] <= "06" else "하") for d in dates])


def ci_days(x_by_day, k=2000):
    v = np.asarray(x_by_day, float); v = v[np.isfinite(v)]
    return block_ci(v, h=20, k=k) if len(v) > 40 else (np.nan, np.nan)


def spread(flag, days):
    """날짜별 (표시 종목 평균 초과 − 비표시 종목 평균 초과) 의 평균과 구간. days = 날짜 선택(bool, 길이 T)."""
    out = []
    for t in np.where(days)[0]:
        m = valid[t]; a = flag[t] & m; b = ~flag[t] & m
        if a.sum() >= 5 and b.sum() >= 5: out.append(np.mean(exc[t, a]) - np.mean(exc[t, b]))
    return (np.mean(out) if out else np.nan), ci_days(out), len(out)


alld = np.zeros(T, bool); alld[s.t0:T - H - 1] = True
print("(가) 전 종목 3년 — 표시 종목 − 비표시 종목의 20봉 초과 차이 %p (음수 = 표시 종목이 못함) [20일 블록 95%] · 날짜 수")
print(f"    국면 일수: 120일선 위 {int((alld & above120).sum())} · 아래 {int((alld & ~above120).sum())} | 그 뒤 시장 상승 {int((alld & mkt_up).sum())} · 하락 {int((alld & ~mkt_up).sum())}")
rows = []
for nm, fl in FL.items():
    line = f"  {nm:<12}"
    for lab, dsel in [("전체", alld), ("2024", alld & (yr == "2024")), ("2025", alld & (yr == "2025")), ("2026", alld & (yr == "2026")), ("2026-06~09", alld & (ym >= "202606") & (ym <= "202609")),
                      ("120일선 위", alld & above120), ("120일선 아래", alld & ~above120), ("뒤에 시장↑", alld & mkt_up), ("뒤에 시장↓", alld & ~mkt_up)]:
        m, (lo, hi), n = spread(fl, dsel); rows.append(dict(flag=nm, split=lab, diff=m, lo=lo, hi=hi, n_days=n))
        line += f" | {lab} {m:+.2f}" + (f" [{lo:+.1f},{hi:+.1f}]" if np.isfinite(lo) else "")
    print(line)
print("\n    반기별(차이 %p):")
for nm, fl in FL.items():
    print(f"  {nm:<12} " + " · ".join(f"{h} {spread(fl, alld & (half == h))[0]:+.2f}" for h in sorted(set(half[alld]))))
pd.DataFrame(rows).to_csv(HERE / "flags_by_regime.csv", index=False, encoding="utf-8-sig")

# ---- (나) 실적 표시를 실제 목록에
print("\n(나) 실제 모델 목록(상위 10, 제때 저장된 점수, 2026-06~09)에 실적 표시를 얹으면")
hc = sqlite3.connect(f"file:{ROOT / 'history.db'}?mode=ro", uri=True); di = s.di; tix = e7.tix; rows = []
for model, (tab, col) in e7.SRC.items():
    d = pd.read_sql(f"SELECT run_id, market, ticker, {col} AS score, frozen_at FROM {tab} WHERE model_id=?", hc, params=(model,))
    d = d[d.score > -900]; d["ticker"] = d.ticker.astype(str).str.zfill(6); d["market"] = d.market.str.lower(); d = d[d.run_id.isin(di)]
    t_idx = d.run_id.map(di); nxt = pd.Series(dates[np.minimum(t_idx.values + 1, T - 1)], index=d.index)
    fz = pd.to_datetime(d.frozen_at.astype(str).str.slice(0, 19), errors="coerce"); dead = pd.to_datetime(nxt + " 09:00:00", format="%Y%m%d %H:%M:%S")
    d = d[(fz <= dead) & (t_idx < T - 1)]
    for (run, mkt), g in d.groupby(["run_id", "market"]):
        t = di[run]
        if t >= T - H - 1: continue
        g = g[g.ticker.isin(tix)].sort_values("score", ascending=False)
        if len(g) < 10: continue
        k = g.ticker.map(tix).values; m = 0 if mkt == "kospi" else 1; top = k[:10]; clean = [x for x in k if not NEG[t, x]][:10]
        for x in top: rows.append(dict(model=model, run=run, kind="pick", k=int(x), exc=ret[t, x] - mean_mk[t, m], ret=ret[t, x], neg=bool(NEG[t, x]), pos=bool(POS[t, x]), known=bool(KNOWN[t, x])))
        rows.append(dict(model=model, run=run, kind="basket", basket=np.nanmean(ret[t, top]), clean=np.nanmean(ret[t, clean]) if len(clean) >= 5 else np.nan, swapped=10 - len(set(top) & set(clean))))
hc.close()
D = pd.DataFrame(rows); P = D[D.kind == "pick"].dropna(subset=["ret"]).copy(); B = D[D.kind == "basket"].dropna(subset=["basket"])
for c_ in ("neg", "pos", "known"): P[c_] = P[c_].astype(bool)
P.to_csv(HERE / "earnings_flag_picks.csv", index=False, encoding="utf-8-sig")
for model, g in P.groupby("model"):
    a, b, p_ = g[g.neg], g[~g.neg], g[g.pos]; bb = B[B.model == model]; dd = (bb.clean - bb.basket).dropna(); lo, hi = e7.ci_dates(bb.loc[dd.index].assign(d=dd), "d")
    print(f"  {model:<5} 목록일 {g.run.nunique():>2} · 실적 악화 {g.neg.mean()*100:4.1f}%" + (f" (초과 {a.exc.mean():+.1f} vs 나머지 {b.exc.mean():+.1f})" if len(a) >= 15 else " (적음)")
          + f" · 실적 개선 {g.pos.mean()*100:4.1f}%" + (f" (초과 {p_.exc.mean():+.1f})" if len(p_) >= 15 else " (적음)")
          + f" · 악화 종목 빼고 채우면 {bb.clean.mean():+.2f}% vs 원래 {bb.basket.mean():+.2f}% (차이 {dd.mean():+.2f} [{lo:+.2f},{hi:+.2f}], 바뀐 종목 {bb.swapped.mean():.1f}개)")
a, b, p_ = P[P.neg], P[~P.neg], P[P.pos]; la, ha = e7.ci_dates(a, "exc"); lp, hp = e7.ci_dates(p_, "exc"); lb, hb = e7.ci_dates(b, "exc")
print(f"  [모델 합] 실적 악화 n {len(a)}({len(a)/len(P)*100:.0f}%) 초과 {a.exc.mean():+.2f} [{la:+.2f},{ha:+.2f}] | 실적 개선 n {len(p_)}({len(p_)/len(P)*100:.0f}%) 초과 {p_.exc.mean():+.2f} [{lp:+.2f},{hp:+.2f}] | 악화 아닌 종목 n {len(b)} 초과 {b.exc.mean():+.2f} [{lb:+.2f},{hb:+.2f}]")
print("  [표시 종목이 서로 다른 종목 몇 개인가] " + " · ".join(f"{m}: 악화 {g[g.neg].k.nunique()}종목/{int(g.neg.sum())}건" for m, g in P.groupby("model")))
v = P[(P.model == "v30") & P.neg].groupby("k").agg(n=("exc", "size"), exc=("exc", "mean")).sort_values("n", ascending=False)
print(f"  v30 실적 악화 종목별: 종목 {len(v)}개 · 종목 평균의 평균 {v.exc.mean():+.2f}%p · 초과가 음(−)인 종목 {int((v.exc < 0).sum())}개 · 가장 많이 나온 3종목이 차지하는 건수 {int(v.n.head(3).sum())}/{int(v.n.sum())}")
