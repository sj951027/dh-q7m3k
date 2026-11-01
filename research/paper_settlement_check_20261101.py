# -*- coding: utf-8 -*-
"""다 갈래 J11 — 모의 계좌가 '당일(또는 전날) 매도대금'으로 당일 매수한 돈이 얼마나 되나 (실제 결제는 T+2 라 그 돈은 못 쓴다) (2026-11-01, 사후 관측 · 채택 아님)

엔진(paper_engine.simulate)은 날 i 에 ① 만기 청산으로 현금을 받고 ② 같은 날 신규 진입에 그 현금을 바로 쓴다. 실제 증권사 주문가능액은 매도대금이 T+2 에 들어오므로
(일부 증권사는 매도 당일 재매수를 허용하지만 결제 전 현금은 아님) 엔진이 과대 투자할 수 있다.
센다(계좌별, 2026-08-10~): 날마다 진입액 E_i · 전날 종가 현금 C_{i−1} · 당일 청산 대금 P_i · 전날·전전날 대금 P_{i−1}, P_{i−2}.
  '당일 대금에 기댄 진입' = max(0, E_i − C_{i−1}) — 전날 현금만으로 못 채운 몫. T+2 기준으론 C_{i−1} 에서 P_{i−1}+P_{i−2}(아직 미결제)를 뺀 것이 진짜 가용액 → '미결제 포함 기댄 진입' = max(0, E_i − (C_{i−1} − P_{i−1} − P_{i−2})).
  비율 = 그 돈 / 전체 진입액. 또 그런 날의 수와, 그 돈이 만든 포지션의 40일 손익(기여, %p)도.
재현: python research/paper_settlement_check_20261101.py → research/out_settlement/ (20초). DB 읽기만."""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent))
import leaderboard as lb, regime_ad, paper_engine as pe, paper_account as pa
OUT = HERE / "out_settlement"; OUT.mkdir(exist_ok=True); LOG = []


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


t0 = time.time()
close, tradable, shares, mkt = pa.load_prices()
dates_all = list(close.index); didx_all = {d: i for i, d in enumerate(dates_all)}
ks = regime_ad.load_index("KOSPI", lb.OHLCV_DB); cells = regime_ad.classify(ks)["cell"]
excl = pa.load_gates(dates_all); start = pa.START_DEFAULT
i0 = next(i for i, d in enumerate(dates_all) if d >= start); dates = dates_all[i0:]; sub = close.loc[dates]; trd = tradable.loc[dates]
picks = {d: v for d, v in pa.v30_picks(dates_all, didx_all, excl).items() if d >= start}
mp = {}
for mid in pa.MODEL_ACCOUNTS:
    tb, col = pa.MODEL_SRC[mid]; mp[mid] = {d: v for d, v in pa.model_picks(mid, tb, col, dates_all, didx_all, excl, reg=None).items() if d >= start}
sw, _ = pe.switch_picks(dates, cells.reindex(dates), picks, mp["lv_b"], a_cells=pa.SWITCH_A_CELLS)
defs = {"v30": picks, **{m: mp[m] for m in pa.MODEL_ACCOUNTS}, pa.SWITCH_ID: sw}
say(f"되감기 {dates[0]}~{dates[-1]} · 계좌 {len(defs)} · {time.time()-t0:.0f}s")
rows = []
for aid, pk in defs.items():
    nav, led = pe.simulate(dates, sub, pk, tradable=trd)
    L = pd.DataFrame(led)
    N = len(dates); E = np.zeros(N); P = np.zeros(N); ret_w = np.zeros(N)
    for p in led:
        E[p["entry_i"]] += p["invested"]
        if p.get("status") == "closed":
            P[didx(p) if False else p["exit_i"]] += p["proceeds"]
    cash = nav.cash.to_numpy(float); C_prev = np.concatenate([[1.0], cash[:-1]])
    P1 = np.concatenate([[0.0], P[:-1]]); P2 = np.concatenate([[0.0, 0.0], P[:-2]])
    dep0 = np.maximum(0.0, E - C_prev)                               # 당일 대금에 기댄 몫
    dep2 = np.maximum(0.0, E - (C_prev - P1 - P2))                   # T+2 미결제까지 빼면 못 쓰는 몫
    tot = E.sum()
    # 그 돈이 만든 포지션의 손익 기여(근사): 해당 날 진입 포지션 손익 × (기댄 몫 / 그날 진입액)
    contrib = 0.0; n_cl = n_op = 0
    for p in led:
        if E[p["entry_i"]] > 0 and dep2[p["entry_i"]] > 1e-12:
            if p.get("status") == "closed":
                contrib += p["invested"] * p["ret"] * (dep2[p["entry_i"]] / E[p["entry_i"]]); n_cl += 1
            else:
                n_op += 1
    first_dep = next((dates[i] for i in range(N) if dep2[i] > 1e-12), None)
    rows.append(dict(account=aid, entries=float(tot * 100), dep_sameday_pct=float(dep0.sum() / tot * 100) if tot else np.nan, days_sameday=int((dep0 > 1e-12).sum()),
                     dep_t2_pct=float(dep2.sum() / tot * 100) if tot else np.nan, days_t2=int((dep2 > 1e-12).sum()), entry_days=int((E > 0).sum()), first_dep_day=first_dep,
                     contrib_t2_pp=float(contrib * 100), n_closed=n_cl, n_open=n_op, avg_cash=float(cash.mean() * 100), min_cash=float(cash.min() * 100)))
    say(f"  {aid:<16} 진입 총 {tot*100:6.1f}%NAV · 진입일 {int((E>0).sum())} · 당일 대금 기댄 {dep0.sum()/tot*100:5.2f}%({int((dep0>1e-12).sum())}일) · T+2 미결제까지 {dep2.sum()/tot*100:5.2f}%({int((dep2>1e-12).sum())}일, 첫날 {first_dep}) · 그 진입 포지션 끝남 {n_cl}/열림 {n_op}(끝난 몫 손익 기여 {contrib*100:+.3f}%p) · 현금 평균 {cash.mean()*100:.1f}% 최소 {cash.min()*100:.1f}%")
S = pd.DataFrame(rows); S.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
(OUT / "run_20261101.txt").write_text("\n".join(LOG), encoding="utf-8"); say(f"끝 {time.time()-t0:.0f}s")
