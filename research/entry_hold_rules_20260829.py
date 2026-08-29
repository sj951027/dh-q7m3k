# -*- coding: utf-8 -*-
"""entry_hold_rules_20260829.py — RESEARCH_entry_hold_20260829.md E1~E4 재현 (읽기 전용)

E1: k=20/10 시작일 offset 전수 경로(비용후 0.5%) 분포
E2: 앵커별 20일 바스켓 수익 vs 진입일 시장 조건(직전5일·선정일 KOSDAQ 수익, PIT)
E3: 다음날 시가 vs 종가 진입 차이
E4: 20일 보유 + 익절/손절 그리드(재투자 없음·종가 체결 단순화)
한계: 단일 국면, h20 앵커 창 겹침, n 22~35, 조건 다중검정.
"""
import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOPN, H, COST = 20, 20, 0.005
hc = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
oc = sqlite3.connect(f'file:{REPO.parent/"dh-q7m3k-data"/"ohlcv.db"}?mode=ro', uri=True)
px = pd.read_sql("SELECT ticker,date,open,close,change_pct FROM daily_ohlcv WHERE date>='20260501'", oc)
px['ticker'] = px.ticker.astype(str)
dts = sorted(px.date.unique()); didx = {d: i for i, d in enumerate(dts)}
C = px.pivot_table(index='date', columns='ticker', values='close', aggfunc='last').reindex(dts)
O = px.pivot_table(index='date', columns='ticker', values='open', aggfunc='last').reindex(dts); O = O.where(O > 0)
R = px.pivot_table(index='date', columns='ticker', values='change_pct', aggfunc='last').reindex(dts)
kq = pd.read_sql("SELECT date,close FROM market_daily WHERE series='KOSDAQ'", oc)\
       .set_index('date')['close'].astype(float).sort_index()
MODELS = {
    'v30':  (pd.read_sql("SELECT run_id,ticker,final_score_v3 s FROM v3_scores WHERE model_id='v30' AND run_id>='20260606'", hc), '20260606'),
    'lv_b': (pd.read_sql("SELECT run_id,ticker,lowvol_score s FROM lowvol_scores WHERE model_id='lv_b' AND run_id>='20260625'", hc), '20260625'),
}
for df, _ in MODELS.values():
    df['ticker'] = df.ticker.astype(str); df['run_id'] = df.run_id.astype(str)

def path_cum(m, khold, offset):
    df, start = MODELS[m]; runset = set(df.run_id)
    rets, turns, held, next_reb = {}, {}, None, offset
    for i, t in enumerate([d for d in dts if d >= start]):
        j = didx[t]
        if j + 1 >= len(dts): break
        nxt = dts[j + 1]
        if t in runset and i >= next_reb:
            sel = [c for c in df[df.run_id == t].nlargest(TOPN, 's').ticker if c in R.columns]
            if sel:
                turns[nxt] = 1.0 if held is None else 1 - len(set(sel) & set(held)) / len(sel)
                held, next_reb = sel, i + khold
        if held: rets[nxt] = float(R.loc[nxt, held].mean(skipna=True))
    s = pd.Series(rets).sort_index()
    net = s - pd.Series(turns).reindex(s.index).fillna(0) * COST
    return ((1 + net).cumprod().iloc[-1] - 1) * 100 if len(net) else np.nan

print("== E1. 시작일 경로 분포 (비용후 0.5%) ==")
for m in MODELS:
    for k in (20, 10):
        cs = [c for c in (path_cum(m, k, o) for o in range(k)) if not np.isnan(c)]
        print(f"{m:5s} k={k:2d} n={len(cs)} 최소 {min(cs):+.1f} 중앙 {np.median(cs):+.1f} 최대 {max(cs):+.1f}")

print("\n== E2·E3. 진입일 조건 / 시가 vs 종가 ==")
kf = kq.reindex(dts).ffill()
for m in MODELS:
    df, _ = MODELS[m]; rows = []
    for rid, g in df.groupby('run_id'):
        if rid not in didx or didx[rid] + 1 + H >= len(dts): continue
        t = didx[rid]; e = dts[t + 1]
        sel = [c for c in g.nlargest(TOPN, 's').ticker if c in C.columns]
        rows.append(dict(
            fwdC=float((C.loc[dts[t + 1 + H], sel] / C.loc[e, sel] - 1).mean()),
            fwdO=float((C.loc[dts[t + 1 + H], sel] / O.loc[e, sel] - 1).mean()),
            m5=kf.loc[:rid].iloc[-1] / kf.loc[:rid].iloc[-6] - 1,
            m1=kf.loc[:rid].iloc[-1] / kf.loc[:rid].iloc[-2] - 1))
    A = pd.DataFrame(rows).dropna()
    d = A.fwdO - A.fwdC
    print(f"[{m}] n={len(A)} 평균20일 {A.fwdC.mean()*100:+.1f}% | 시가−종가 {d.mean()*100:+.2f}%p"
          f" (t≈{d.mean()/(d.std(ddof=1)/np.sqrt(len(d))):.2f})")
    for name, mask in [('직전5일 하락', A.m5 < 0), ('직전5일 상승', A.m5 >= 0),
                       ('선정일 급락<-1.5%', A.m1 < -0.015), ('선정일 그 외', A.m1 >= -0.015)]:
        g = A[mask]
        if len(g) > 2: print(f"  {name:14s} n={len(g):2d} {g.fwdC.mean()*100:+6.1f}%")

print("\n== E4. 익절/손절 그리드 (만기보유 대비 %p) ==")
for m in MODELS:
    df, _ = MODELS[m]; outs = {}
    for rid, g in df.groupby('run_id'):
        if rid not in didx or didx[rid] + 1 + H >= len(dts): continue
        t = didx[rid]
        sel = [c for c in g.nlargest(TOPN, 's').ticker if c in C.columns]
        pathm = C.iloc[t + 1:t + 2 + H][sel] / C.loc[dts[t + 1], sel] - 1
        for gee, el in [(None, None), (0.10, None), (0.15, None), (None, 0.10),
                        (0.10, 0.10), (0.15, 0.10), (None, 0.07), (0.15, 0.07)]:
            rets = []
            for c in sel:
                pr = pathm[c].dropna()
                if len(pr) < 2: continue
                exit_r = pr.iloc[-1]
                for v in pr.iloc[1:]:
                    if gee is not None and v >= gee: exit_r = v; break
                    if el is not None and v <= -el: exit_r = v; break
                rets.append(exit_r)
            outs.setdefault((gee, el), []).append(np.mean(rets))
    base = np.mean(outs[(None, None)])
    print(f"[{m}] 앵커 n={len(outs[(None, None)])} 만기보유 {base*100:+.1f}%")
    for (gee, el), v in outs.items():
        if (gee, el) == (None, None): continue
        lab = (f"익절{int(gee*100)}" if gee else "익절X") + "/" + (f"손절{int(el*100)}" if el else "손절X")
        print(f"  {lab:12s} {np.mean(v)*100:+5.1f}% (차 {np.mean(v)*100-base*100:+.1f}%p)")
