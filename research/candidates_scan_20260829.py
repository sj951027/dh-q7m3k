# -*- coding: utf-8 -*-
"""candidates_scan_20260829.py — §28 후보 3종 예비 스캔 재현 (RESEARCH_candidates_scan_20260829.md)

va_ep(eps/price) · fl_inst20n(기관 20일 순매수/거래대금) · sh_credit_rate(신용잔고비율).
프로토콜: 전체 유니버스 amt20>=5억, 일별 앵커(겹침), ENTRY_LAG=1, |1d|>32% 컷,
단일 유니버스 스피어만, iid 부트스트랩 2000(seed 7). sh_credit 는 변동성·유동성 통제 병행.
읽기 전용. ⚠ 창이 짧고 단일 국면 — 결과는 가설. 등록은 별도 사전등록 경로로만.
"""
import sqlite3
from pathlib import Path
import numpy as np
import numpy.linalg as la
import pandas as pd

HERE = Path(__file__).resolve().parent
oc = sqlite3.connect(f"file:{HERE.parent.parent/'dh-q7m3k-data'/'ohlcv.db'}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker,date,close,volume FROM daily_ohlcv WHERE date>='20260401'", oc)
px['ticker'] = px.ticker.astype(str)
C = px.pivot_table(index='date', columns='ticker', values='close', aggfunc='last').sort_index()
V = px.pivot_table(index='date', columns='ticker', values='volume', aggfunc='last').sort_index()
dts = list(C.index); N = len(dts)
AMT = (C * V).rolling(20, min_periods=10).mean() / 1e8
RV = C.pct_change(fill_method=None).rolling(63, min_periods=40).std()
JUMP = C.pct_change(fill_method=None).abs()

va = pd.read_sql("SELECT ticker,date,eps FROM valuation_daily", oc); va['ticker'] = va.ticker.astype(str)
F_ep = (va.pivot_table(index='date', columns='ticker', values='eps', aggfunc='last').reindex(dts) / C).where(C > 0)
fl = pd.read_sql("SELECT ticker,date,inst_net_val FROM daily_flows", oc); fl['ticker'] = fl.ticker.astype(str)
INST = fl.pivot_table(index='date', columns='ticker', values='inst_net_val', aggfunc='last').reindex(dts)
F_fl = (INST.rolling(20, min_periods=15).sum() / (C * V).rolling(20, min_periods=15).sum())\
    .replace([np.inf, -np.inf], np.nan)
sh = pd.read_sql("SELECT ticker,date,credit_bal_rate FROM short_flows WHERE date>='20260713'", oc)
sh['ticker'] = sh.ticker.astype(str)
F_cr = sh.pivot_table(index='date', columns='ticker', values='credit_bal_rate', aggfunc='last').reindex(dts)

def anchors(F, start, h):
    for i, d in enumerate(dts):
        if d < start or i + 1 + h >= N:
            continue
        f = F.loc[d].dropna()
        uni = f.index.intersection(AMT.loc[d][AMT.loc[d] >= 5].index)
        if len(uni) < 300:
            continue
        fwd = (C.iloc[i + 1 + h] / C.iloc[i + 1] - 1).reindex(uni)
        fwd = fwd.where(JUMP.iloc[i + 2:i + 2 + h].max().reindex(uni) <= 0.32)
        m = f.reindex(uni).notna() & fwd.notna()
        if m.sum() < 300:
            continue
        yield d, f.reindex(uni)[m], fwd[m]

def ci(arr, seed=7, boot=2000):
    rng = np.random.default_rng(seed)
    a = np.array(arr)
    bs = [rng.choice(a, len(a)).mean() for _ in range(boot)]
    return a.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5), len(a), float(np.mean(a > 0))

def scan(F, start, name, controls=False):
    print(f"\n[{name}] 앵커 {start}~")
    for h in (5, 10, 20):
        raw, ctl = [], []
        for d, f, y in anchors(F, start, h):
            fr, yr = f.rank(), y.rank()
            raw.append(np.corrcoef(fr, yr)[0, 1])
            if controls:
                rv = RV.loc[d].reindex(f.index).rank()
                am = AMT.loc[d].reindex(f.index).rank()
                msk = rv.notna() & am.notna()
                X = np.column_stack([np.ones(int(msk.sum())), rv[msk], am[msk]])
                beta, *_ = la.lstsq(X, fr[msk], rcond=None)
                ctl.append(np.corrcoef(fr[msk] - X @ beta, yr[msk])[0, 1])
        if not raw:
            print(f"  h{h}: 앵커 부족"); continue
        m, lo, hi, n, pos = ci(raw)
        line = f"  h{h:2d}: n={n:2d} IC={m:+.4f} CI[{lo:+.4f},{hi:+.4f}] 양(+){pos*100:.0f}%"
        if controls and ctl:
            m2, lo2, hi2, *_ = ci(ctl)
            line += f"  | 변동성+유동성 통제 {m2:+.4f} [{lo2:+.4f},{hi2:+.4f}]"
        print(line)

scan(F_ep, '20260706', 'va_ep (eps/price)')
scan(F_fl, '20260622', 'fl_inst20n (기관 20일 순매수/거래대금)')
scan(F_cr, '20260713', 'sh_credit_rate (신용잔고비율)', controls=True)
