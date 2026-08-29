# -*- coding: utf-8 -*-
"""regime_overlay_20260829.py — §14-4 백로그 3순위 실측 (RESEARCH_forward_levers_20260829.md C 재현)

3년 market_daily로 SMA 레짐 필터(전일 종가>SMA면 보유, 아니면 현금 0%) 백테스트.
PIT: 신호는 전일 종가까지만 사용(shift 1). 전종목EW는 현재 수집종목 백필이라 생존편향 주의.
SMA 창 3개를 함께 보므로 창 선택 자유도가 있음 — 결론은 'MDD 축소 강건' 수준까지만.
"""
import sqlite3
import pandas as pd
from pathlib import Path

pd.set_option('future.no_silent_downcasting', True)
HERE = Path(__file__).resolve().parent
oc = sqlite3.connect(f'file:{HERE.parent.parent/"dh-q7m3k-data"/"ohlcv.db"}?mode=ro', uri=True)
md = pd.read_sql("SELECT series,date,close FROM market_daily WHERE series IN ('KOSPI','KOSDAQ')", oc)
piv = md.pivot(index='date', columns='series', values='close').sort_index().astype(float)
ew = pd.read_sql("SELECT date, avg(change_pct) r FROM daily_ohlcv GROUP BY date", oc).set_index('date').sort_index()

def overlay(close, smas=(20, 60, 120)):
    r = close.pct_change()
    nav = (1 + r.dropna()).cumprod()
    print(f"  BH     누적 {(nav.iloc[-1]-1)*100:+7.1f}%  MDD {(nav/nav.cummax()-1).min()*100:+6.1f}%  노출 100%")
    for w in smas:
        sig = (close > close.rolling(w).mean()).shift(1).fillna(False).infer_objects(copy=False)
        rr = r.where(sig, 0.0).dropna()
        nav = (1 + rr).cumprod()
        sw = int(sig.astype(int).diff().abs().sum())
        print(f"  SMA{w:<3d} 누적 {(nav.iloc[-1]-1)*100:+7.1f}%  MDD {(nav/nav.cummax()-1).min()*100:+6.1f}%"
              f"  노출 {sig.mean()*100:3.0f}%  스위치 {sw}회")

for name, ser in [('KOSPI', piv['KOSPI']), ('KOSDAQ', piv['KOSDAQ']),
                  ('전종목EW(생존편향 주의)', (1 + ew.r).cumprod())]:
    print(f"[{name}]")
    overlay(ser.dropna())
