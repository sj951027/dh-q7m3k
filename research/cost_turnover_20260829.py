# -*- coding: utf-8 -*-
"""cost_turnover_20260829.py — §14-4 백로그 1·2순위 실측 (RESEARCH_forward_levers_20260829.md A·B 재현)

A: v30·lv_b 상위20 EW 모의계좌의 일회전율 실측 + 왕복비용(0.3/0.5/0.8%) 후 누적,
   리밸런스 주기 k=1/5/20 비교. B: 일수익 OLS로 베타·잔차알파.
읽기 전용(mode=ro). change_pct는 소수 단위(0.01=1%). ENTRY_LAG=1(선정 익일 수익부터).
한계: 관측창 단일 국면, k>1은 시작일 1개 경로, 슬리피지는 시나리오.
"""
import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOPN = 20
COSTS = (0.003, 0.005, 0.008)   # 왕복(매도세 0.15%+수수료+슬리피지 시나리오)

hc = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
oc = sqlite3.connect(f'file:{REPO.parent/"dh-q7m3k-data"/"ohlcv.db"}?mode=ro', uri=True)
px = pd.read_sql("SELECT ticker,date,close,volume,change_pct FROM daily_ohlcv WHERE date>='20260520'", oc)
px['ticker'] = px.ticker.astype(str)
dts = sorted(px.date.unique()); didx = {d: i for i, d in enumerate(dts)}
R = px.pivot_table(index='date', columns='ticker', values='change_pct', aggfunc='last').reindex(dts)
C = px.pivot_table(index='date', columns='ticker', values='close', aggfunc='last').reindex(dts)
V = px.pivot_table(index='date', columns='ticker', values='volume', aggfunc='last').reindex(dts)
amt20 = (C * V).rolling(20, min_periods=10).mean() / 1e8

MODELS = {
    'v30':  ("SELECT run_id,ticker,final_score_v3 s FROM v3_scores WHERE model_id='v30' AND run_id>='20260606'", '20260606'),
    'lv_b': ("SELECT run_id,ticker,lowvol_score s FROM lowvol_scores WHERE model_id='lv_b' AND run_id>='20260625'", '20260625'),
}

def series_and_turnover(sql, start, khold=1):
    df = pd.read_sql(sql, hc)
    df['ticker'] = df.ticker.astype(str); df['run_id'] = df.run_id.astype(str)
    runset = set(df.run_id)
    rets, turns, amts = {}, {}, []
    held, next_reb = None, 0
    for i, t in enumerate([d for d in dts if d >= start]):
        j = didx[t]
        if j + 1 >= len(dts): break
        nxt = dts[j + 1]
        if t in runset and i >= next_reb:
            sel = [c for c in df[df.run_id == t].nlargest(TOPN, 's').ticker if c in R.columns]
            if sel:
                turns[nxt] = 1.0 if held is None else 1 - len(set(sel) & set(held)) / len(sel)
                held, next_reb = sel, i + khold
                amts.append(float(amt20.loc[t, sel].median()))
        if held:
            rets[nxt] = float(R.loc[nxt, held].mean(skipna=True))
    s = pd.Series(rets).sort_index()
    tu = pd.Series(turns).reindex(s.index).fillna(0)
    return s, tu, (np.median(amts) if amts else None)

cum = lambda s: ((1 + s).cumprod().iloc[-1] - 1) * 100
mdd = lambda s: (lambda nav: (nav / nav.cummax() - 1).min() * 100)((1 + s).cumprod())

bser = {}
for t in dts:
    j = didx[t]
    if t < '20260606' or j + 1 >= len(dts): continue
    sel = amt20.loc[t][amt20.loc[t] >= 5].index.intersection(R.columns)
    bser[dts[j + 1]] = float(R.loc[dts[j + 1], sel].mean(skipna=True))
bench = pd.Series(bser).sort_index()

print("== A. 회전율·비용 후 생존 ==")
res = {}
for m, (sql, start) in MODELS.items():
    for k in (1, 5, 20):
        s, tu, amed = series_and_turnover(sql, start, k)
        res[(m, k)] = (s, tu)
        nets = [f"{cum(s - tu * c):+7.1f}" for c in COSTS]
        print(f"{m:5s} k={k:2d} n={len(s):3d} 회전/일 {tu.mean():.2f} 비용전 {cum(s):+7.1f}%"
              f" | 비용후 {'/'.join(nets)} | MDD {mdd(s):+6.1f}% | 픽중위대금 {amed:.1f}억")

print("\n== B. 알파/베타 (k=1 비용 전) ==")
for m in MODELS:
    s, _ = res[(m, 1)]
    com = s.index.intersection(bench.index)
    y, x = s[com].values, bench[com].values
    b, a = np.polyfit(x, y, 1)
    resid = y - (a + b * x)
    ta = a / (resid.std(ddof=2) / np.sqrt(len(y)))
    print(f"{m:5s} n={len(y)} beta={b:.2f} 일알파={a*100:+.3f}% t≈{ta:.2f}"
          f" | 벤치 {cum(bench[com]):+.1f}% 모델 {cum(s[com]):+.1f}%")
