# -*- coding: utf-8 -*-
"""E5 — 계좌 노출 조절로 '하락장 덜 하락·상승장 더 상승'(목표 3)을 잴 수 있나. 20일 겹쳐 보유 일별 계열 + 전일 종가 신호. 탐색. python e5_overlay.py"""
import numpy as np, pandas as pd
from w20lib import *

s = study(); T, N = s.T, s.N; c, o, ok = s.c, s.o, s.ok; ff = s.ff
shares = s.z["shares"].astype(float); mc = rank(np.log(c * shares), ok)
picks = {k: s.picks[k] for k in RULES3}
sc = s.rules["highbeta_high"]; mk = s.masks["highbeta_high"] & (mc >= .8); pk = []
for t in range(T):
    ix = np.where(mk[t] & np.isfinite(sc[t]))[0]; pk.append(ix[np.argsort(-sc[t, ix], kind="stable")[:10]])
picks["highbeta_large"] = pk; NAMES = dict(RULES3, highbeta_large="공격형∩시총 상위20%(사후)", index="지수 반반", univ="전 종목 동일가중")
dr = ff[1:] / ff[:-1] - 1; dr = np.vstack([np.full((1, N), np.nan), dr]); dr[~np.isfinite(dr)] = 0     # 종가→종가
d_open = np.where((o > 0) & np.isfinite(o), ff / o - 1, 0.0)                                              # 진입일: 시가→종가


def tranche_series(pkk):
    """매일 1/20씩 새로 사서 20봉 보유. R[d] = 살아 있는 20개 묶음의 평균 일수익(묶음 = 10자리, 미체결 현금) − 회전 비용."""
    R = np.full(T, np.nan)
    for d in range(s.t0 + H + 1, T):
        acc = 0.0
        for t in range(d - H, d):          # 목록일 t → 진입 t+1 … t+20
            ix = pkk[t]
            if len(ix) == 0: continue
            f = entry_ok(s, t)[ix]; ix = ix[f]
            if len(ix) == 0: continue
            acc += (d_open[d, ix] if d == t + 1 else dr[d, ix]).sum() / 10
        R[d] = acc / H - COST / H
    return R


ser = {k: tranche_series(v) for k, v in picks.items()}
idx = np.nanmean(np.vstack([np.r_[np.nan, s.idx[1:, j] / s.idx[:-1, j] - 1] for j in (0, 1)]), axis=0); ser["index"] = idx
uni = np.full(T, np.nan)
for d in range(1, T): uni[d] = np.mean(dr[d, ok[d - 1]])
ser["univ"] = uni
# 신호(전일 종가까지): d 의 노출 = sig[d-1]
kq = s.idx[:, 1]; i50 = np.cumprod(1 + np.nan_to_num(idx)); sma = lambda x, w: pd.Series(x).rolling(w, min_periods=w).mean().values
br = np.nanmean(np.where(ok, (c > rolling(c, 20, 15)).astype(float), np.nan), axis=1)
SIG = {"항상 보유": np.ones(T), "코스닥>20일선": kq > sma(kq, 20), "코스닥>60일선": kq > sma(kq, 60), "코스닥>120일선": kq > sma(kq, 120),
       "반반지수 20일 수익>0": np.r_[np.zeros(20), i50[20:] / i50[:-20] - 1] > 0, "20일선 위 종목>50%": br > .5,
       "60일선 위 그리고 20일 수익>0": (kq > sma(kq, 60)) & (np.r_[np.zeros(20), i50[20:] / i50[:-20] - 1] > 0)}
D0 = s.t0 + H + 1; days = np.arange(D0, T); dates = s.d[days]; yr = np.array([x[:4] for x in dates])


def overlay(R, sig, alt=None, floor=0.0):
    e = np.r_[0, sig[:-1].astype(float)]; e = floor + (1 - floor) * e
    x = e * np.nan_to_num(R) + ((1 - e) * np.nan_to_num(alt) if alt is not None else 0) - np.abs(np.r_[0, np.diff(e)]) * COST / 2
    return x[days]


def stats(x, bench, w=20):
    n = len(x) // w; xs = np.array([np.prod(1 + x[i * w:(i + 1) * w]) - 1 for i in range(n)]); bs = np.array([np.prod(1 + bench[i * w:(i + 1) * w]) - 1 for i in range(n)])
    up = bs > 0; cum = np.cumprod(1 + x); dd = (cum / np.maximum.accumulate(cum) - 1).min()
    upc = xs[up].mean() / bs[up].mean(); dnc = xs[~up].mean() / bs[~up].mean()
    rng = np.random.default_rng(7); bt = []
    for _ in range(2000):
        ii = rng.integers(0, n, n); u = bs[ii] > 0
        if u.sum() < 3 or (~u).sum() < 3: continue
        bt.append(xs[ii][u].mean() / bs[ii][u].mean() - xs[ii][~u].mean() / bs[ii][~u].mean())
    lo, hi = np.quantile(bt, [.025, .975])
    return dict(n_win=n, n_up=int(up.sum()), n_dn=int((~up).sum()), up_ret=xs[up].mean() * 100, dn_ret=xs[~up].mean() * 100, up_cap=upc, dn_cap=dnc, asym=upc - dnc, asym_lo=lo, asym_hi=hi,
                total=(cum[-1] - 1) * 100, mdd=dd * 100, vol=x.std() * np.sqrt(252) * 100, win_beat_up=(xs[up] > bs[up]).mean(), win_beat_dn=(xs[~up] > bs[~up]).mean())


bench = np.nan_to_num(idx)[days]; rows = []
for nm, R in ser.items():
    for sn, sg in SIG.items():
        rows.append(dict(series=NAMES[nm], rule=sn, on=float(np.r_[0, sg[:-1]][days].mean()), **stats(overlay(R, sg), bench)))
    if nm in ("highbeta_high", "highbeta_large", "control_amount"):
        for sn in ("코스닥>60일선", "반반지수 20일 수익>0", "코스닥>20일선"):
            rows.append(dict(series=NAMES[nm], rule=f"바벨: {sn} 이면 공격, 아니면 가격4요소", on=float(np.r_[0, SIG[sn][:-1]][days].mean()), **stats(overlay(R, SIG[sn], alt=ser["control_price4"]), bench)))
        rows.append(dict(series=NAMES[nm], rule="고정 반반: 공격 50 + 가격4요소 50", on=.5, **stats(.5 * np.nan_to_num(R)[days] + .5 * np.nan_to_num(ser["control_price4"])[days], bench)))
        rows.append(dict(series=NAMES[nm], rule="고정 반반: 공격 50 + 현금 50", on=.5, **stats(.5 * np.nan_to_num(R)[days], bench)))
O = pd.DataFrame(rows); O.to_csv(HERE / "overlay_summary.csv", index=False, encoding="utf-8-sig")
pd.DataFrame({NAMES[k]: np.nan_to_num(v)[days] for k, v in ser.items()}, index=dates).to_csv(HERE / "daily_tranche_series.csv", encoding="utf-8-sig")
pd.set_option("display.width", 280); pd.set_option("display.max_rows", 300); pd.set_option("display.max_colwidth", 50)
b = stats(bench, bench)
print(f"기간 {dates[0]}~{dates[-1]} · {len(days)}거래일 · 20일 비겹침 구간 {b['n_win']}개(상승 {b['n_up']} · 하락 {b['n_dn']}) · 지수 반반: 상승 구간 평균 {b['up_ret']:+.2f}% · 하락 구간 {b['dn_ret']:+.2f}% · 누적 {b['total']:+.1f}% · 최대 낙폭 {b['mdd']:.1f}%")
print("읽는 법: up_cap>1 = 상승 구간에 지수보다 더 오름 · dn_cap<1 = 하락 구간에 지수보다 덜 떨어짐 · asym = up_cap − dn_cap (목표 3 은 asym>0 이면서 up_cap>1·dn_cap<1) [구간 재추출 95%]")
O["asym_ci"] = O.apply(lambda x: f"{x.asym:+.2f} [{x.asym_lo:+.2f},{x.asym_hi:+.2f}]", axis=1)
cols = ["series", "rule", "on", "up_ret", "dn_ret", "up_cap", "dn_cap", "asym_ci", "total", "mdd", "vol", "win_beat_up", "win_beat_dn"]
print(O[cols].round(2).to_string(index=False))
# 연도별 안정성: 목표 3 을 만족한 줄(up_cap>1 & dn_cap<1)만 연도별로 다시
print("\n[up_cap>1 이고 dn_cap<1 인 줄 — 연도별 (구간 수가 적다: 해마다 12개 안팎)]")
good = O[(O.up_cap > 1) & (O.dn_cap < 1)]
for _, g in good.iterrows():
    nm = [k for k, v in NAMES.items() if v == g.series][0]; R = ser[nm]
    if g.rule in SIG: x = overlay(R, SIG[g.rule])
    elif g.rule.startswith("바벨"): x = overlay(R, SIG[g.rule.split(": ")[1].split(" 이면")[0]], alt=ser["control_price4"])
    elif "가격4요소 50" in g.rule: x = .5 * np.nan_to_num(R)[days] + .5 * np.nan_to_num(ser["control_price4"])[days]
    else: x = .5 * np.nan_to_num(R)[days]
    line = []
    for y in ("2024", "2025", "2026"):
        m = yr == y; st = stats(x[m], bench[m]); line.append(f"{y}: up {st['up_cap']:.2f}·dn {st['dn_cap']:.2f}·누적 {st['total']:+.0f}%(지수 {(np.prod(1+bench[m])-1)*100:+.0f}%)·낙폭 {st['mdd']:.0f}%")
    print(f"  {g.series} / {g.rule}: " + " | ".join(line))
