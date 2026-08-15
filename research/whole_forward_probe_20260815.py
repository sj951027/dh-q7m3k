# -*- coding: utf-8 -*-
"""
whole_forward_probe_20260815.py — '전체 유니버스 전환' 가치 프로브 (§14 탐색 전용)
====================================================================================
질문: lowvol/v3 를 전체 유니버스로 전환할 가치가 forward 데이터로 확인되는가?
방법: 전체 상장(거래대금≥5억)에서 저변동(lv63 낮을수록↑)·반전(r20 더 빠졌을수록↑) 단독
     신호의 주간앵커 forward IC, 2026-04~08 (h5·h20, 앵커 부트스트랩 CI, 월별 분해).
결과(실행일 2026-08-15):
  - 저변동 h20 IC +0.401 CI[+0.311,+0.475] · 11/11주 양수 (h5 +0.221) — 전체에서도 최강 재확인
  - 반전   h20 IC −0.028 CI[−0.111,+0.050] — 전체 유니버스에서 죽음(v3 전체 전환 근거 없음)
주의: 폭락 국면 포함 창이라 저변동 IC엔 베타 효과(급락장에서 고변동주가 더 빠짐)가 섞임.
     h20 주간앵커는 창 겹침 — CI 과신 금지. 채택 판단 금지: 공식 답은 이미 등록된
     전체 유니버스 구현체 qs_a(판정 ~9월 말)·px_a(~10월 초)의 §11 판정.
실행: python research/whole_forward_probe_20260815.py
"""
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
oc = sqlite3.connect(f"file:{HERE.parent/'dh-q7m3k-data'/'ohlcv.db'}?mode=ro", uri=True)
RNG = np.random.default_rng(20260815)

px = pd.read_sql("SELECT ticker,date,close,volume,change_pct FROM daily_ohlcv WHERE date>='20260201'", oc)
dts = sorted(px.date.unique())
C = px.pivot_table(index='date', columns='ticker', values='close', aggfunc='last').reindex(dts)
V = px.pivot_table(index='date', columns='ticker', values='volume', aggfunc='last').reindex(dts)
R = px.pivot_table(index='date', columns='ticker', values='change_pct', aggfunc='last').reindex(dts)
amt20 = (C * V).rolling(20, min_periods=10).mean() / 1e8

wk, anchors = set(), []
for i, d in enumerate(dts):
    if d < '20260401' or i < 63:
        continue
    w = pd.Timestamp(d).isocalendar()[:2]
    if w not in wk:
        wk.add(w)
        anchors.append(i)

res = {f: {h: [] for h in (5, 20)} for f in ('저변동(낮을수록↑)', '반전(더 빠졌을수록↑)')}
mon = {f: {} for f in res}
for t in anchors:
    r = R.iloc[:t + 1]
    lv63 = r.iloc[-63:].std()
    r20 = (1 + r.iloc[-20:]).prod() - 1
    g = (amt20.iloc[t] >= 5) & lv63.notna()
    idx = g[g].index
    F = {'저변동(낮을수록↑)': -lv63[idx], '반전(더 빠졌을수록↑)': -r20[idx]}
    for h in (5, 20):
        if t + h >= len(R):
            continue
        y = ((1 + R[idx].iloc[t + 1:t + 1 + h]).prod() - 1)
        for f, s in F.items():
            m = s.notna() & y.notna()
            if m.sum() < 50:
                continue
            ic = s[m].rank().corr(y[m].rank())
            res[f][h].append(ic)
            if h == 20:
                mon[f].setdefault(dts[t][:6], []).append(ic)

def ci(v):
    v = np.array([x for x in v if np.isfinite(x)])
    if len(v) < 3:
        return (np.nan, np.nan)
    i = RNG.integers(0, len(v), (3000, len(v)))
    return tuple(np.quantile(v[i].mean(axis=1), [.025, .975]))

print("=== 전체 유니버스(거래대금≥5억) forward IC — 주간앵커 ===")
for f in res:
    for h in (5, 20):
        v = res[f][h]
        lo, hi = ci(v)
        print(f"  {f} h{h}: IC {np.mean(v):+.3f} CI[{lo:+.3f},{hi:+.3f}] "
              f"(주 {len(v)}개, pos {np.mean([x > 0 for x in v]):.0%})")
print("\n월별 h20 IC:")
md = pd.DataFrame({f: {m: np.mean(v) for m, v in mon[f].items()} for f in res}).T
print(md.round(3).to_string())
