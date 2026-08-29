# -*- coding: utf-8 -*-
"""ensemble_map_20260829.py — 트랙 앙상블 지도 (RESEARCH_ensemble_map_20260829.md 재현)

전 트랙 상위20 EW 일수익(등록일 이후, ENTRY_LAG=1, 비용 0)의 쌍별 상관 +
코스닥 국면 라벨(선정일) 조건부 평균 일수익. 읽기 전용. IC 절대값 비교 아님(§ 규칙) —
수익 시계열의 상관·국면 구조만 본다. ls_t1 점수는 build_large_test.build_scores 정본 재사용.
⚠ 창 짧음(최장 55일)·비용 0·국면 라벨은 이동평균 기반이라 지연 — 관측 참고.
"""
import sqlite3, sys, importlib.util as iu
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
MIN_N = 8
hc = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
oc = sqlite3.connect(f"file:{REPO.parent/'dh-q7m3k-data'/'ohlcv.db'}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker,date,close,volume,change_pct FROM daily_ohlcv WHERE date>='20260520'", oc)
px['ticker'] = px.ticker.astype(str)
C = px.pivot_table(index='date', columns='ticker', values='close', aggfunc='last').sort_index()
V = px.pivot_table(index='date', columns='ticker', values='volume', aggfunc='last').sort_index()
R = px.pivot_table(index='date', columns='ticker', values='change_pct', aggfunc='last').sort_index()
dts = list(C.index); didx = {d: i for i, d in enumerate(dts)}
AMT = (C * V).rolling(20, min_periods=10).mean() / 1e8

Q = {'v30':  "SELECT run_id,ticker,final_score_v3 s FROM v3_scores WHERE model_id='v30' AND run_id>='20260606'",
     'lv_b': "SELECT run_id,ticker,lowvol_score s FROM lowvol_scores WHERE model_id='lv_b' AND run_id>='20260625'",
     'mom_a':"SELECT run_id,ticker,lowvol_score s FROM lowvol_scores WHERE model_id='mom_a' AND run_id>='20260627'",
     'wu_a': "SELECT run_id,ticker,wu_score s FROM wu_scores WHERE model_id='wu_a' AND run_id>='20260702'",
     'sv_a': "SELECT run_id,ticker,wu_score s FROM wu_scores WHERE model_id='sv_a' AND run_id>='20260715'",
     'qs_a': "SELECT run_id,ticker,wu_score s FROM wu_scores WHERE model_id='qs_a' AND run_id>='20260723'",
     'px_a': "SELECT run_id,ticker,wu_score s FROM wu_scores WHERE model_id='px_a' AND run_id>='20260810'"}

def series(df):
    df = df.copy(); df['ticker'] = df.ticker.astype(str); df['run_id'] = df.run_id.astype(str)
    out = {}
    for rid, g in df.groupby('run_id'):
        if rid not in didx or didx[rid] + 1 >= len(dts):
            continue
        sel = [c for c in g.nlargest(20, 's').ticker if c in R.columns]
        if sel:
            out[dts[didx[rid] + 1]] = float(R.loc[dts[didx[rid] + 1], sel].mean(skipna=True))
    return pd.Series(out).sort_index()

S = {m: series(pd.read_sql(q, hc)) for m, q in Q.items()}
spec = iu.spec_from_file_location('blt', REPO / 'build_large_test.py')
blt = iu.module_from_spec(spec); spec.loader.exec_module(blt)
lg = blt.build_scores(hc)
scol = [c for c in lg.columns if c in ('score', 'ls_t1', 'final')] or [lg.columns[-1]]
lgs = lg.rename(columns={scol[0]: 's'})[['run_id', 'ticker', 's']]
S['ls_t1'] = series(lgs[lgs.run_id.astype(str) >= '20260806'])
bser = {}
for t in dts:
    i = didx[t]
    if t < '20260606' or i + 1 >= len(dts):
        continue
    sel = AMT.loc[t][AMT.loc[t] >= 5].index.intersection(R.columns)
    bser[dts[i + 1]] = float(R.loc[dts[i + 1], sel].mean(skipna=True))
S['시장EW'] = pd.Series(bser).sort_index()

names = list(S)
print(f"== 일수익 상관 행렬 (쌍별 공통일 n>={MIN_N}; *=n<15 참고) ==")
print("      " + " ".join(f"{n:>7s}" for n in names))
for a in names:
    row = []
    for b in names:
        com = S[a].index.intersection(S[b].index)
        if len(com) >= 15:
            row.append(f"{S[a][com].corr(S[b][com]):+.2f} ")
        elif len(com) >= MIN_N:
            row.append(f"{S[a][com].corr(S[b][com]):+.2f}*")
        else:
            row.append("    · ")
    print(f"{a:6s} " + " ".join(f"{x:>7s}" for x in row))

reg = pd.read_sql("SELECT run_id,market_regime FROM runs WHERE market='kosdaq'", hc)
reg['run_id'] = reg.run_id.astype(str)
rmap = dict(zip(reg.run_id, reg.market_regime))
print("\n== 코스닥 국면 라벨(선정일) × 트랙 평균 일수익% (n) ==")
labs = ['약세', '조정', '반등', '강세']
print("      " + " ".join(f"{l:>10s}" for l in labs))
for m in names:
    row = []
    for l in labs:
        days = [d for d in S[m].index if didx.get(d, 0) > 0 and rmap.get(dts[didx[d] - 1]) == l]
        v = S[m].reindex(days).dropna()
        row.append(f"{v.mean()*100:+.2f}({len(v)})" if len(v) >= 3 else "     ·")
    print(f"{m:6s} " + " ".join(f"{x:>10s}" for x in row))
