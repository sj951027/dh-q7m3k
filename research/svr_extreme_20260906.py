# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행. 읽기 전용, 관측 전용(모델 아님).
"""svr_extreme_20260906.py — '공매도비중(svr5) 극단 상위에서 꺾이는가' 를 sv_a 등록 전 기간까지 넓혀 확인.
short_flows 전종목 적재 시작(2026-04) ~ h20 완결일까지, 주 1회 앵커(월요일 직후 거래일), 시장별 백분위 구간 초과수익.
sv_a 스펙(svr5 = rolling 5, min 3)을 그대로 재계산 — 판정 아님, sv_b/변형 설계 참고용."""
from pathlib import Path as _P
import sys, sqlite3
import numpy as np, pandas as pd
_HERE=_P(__file__).resolve().parent; REPO=_HERE.parent; sys.path.insert(0,str(REPO))
import leaderboard as lb
close,mkt=lb.load_ohlcv(); dates=list(close.index); N=len(dates)
ocon=sqlite3.connect(f'file:{lb.OHLCV_DB}?mode=ro',uri=True)
sf=pd.read_sql("SELECT ticker,date,short_vol_ratio FROM short_flows WHERE date>='20260320'",ocon)
sf['short_vol_ratio']=pd.to_numeric(sf.short_vol_ratio,errors='coerce')
svr=sf.pivot_table(index='date',columns='ticker',values='short_vol_ratio',aggfunc='last').reindex(close.index)
svr5=svr.rolling(5,min_periods=3).mean()
jump_all=close.pct_change(fill_method=None).abs()
BINS=[(0,10),(10,50),(50,80),(80,90),(90,95),(95,98),(98,100)]
def boot(a,seed=7):
    a=np.asarray(a,float); a=a[~np.isnan(a)]
    if len(a)<3: return (np.nan,np.nan)
    rng=np.random.default_rng(seed); b=[rng.choice(a,len(a)).mean() for _ in range(3000)]; return np.percentile(b,2.5),np.percentile(b,97.5)
anchors=[i for i,d in enumerate(dates) if d>='20260410' and pd.Timestamp(d).dayofweek==0 or (d>='20260410' and i>0 and pd.Timestamp(dates[i-1]).dayofweek>=4 and pd.Timestamp(d).dayofweek<=1)]
anchors=sorted(set(a for a in anchors if a+21<N))
for h in (10,20):
    rec=[]
    for t in anchors:
        if t+1+h>=N: continue
        f=close.iloc[t+1+h]/close.iloc[t+1]-1; j=jump_all.iloc[t+2:t+2+h].max(); f=f.where(j<=lb.JUMP_CAP)
        s=svr5.iloc[t]
        for mk in ('KOSPI','KOSDAQ'):
            cols=[c for c in s.index if str(mkt.get(c,'')).upper()==mk]
            sc=s[cols].dropna(); b=f.reindex(sc.index); m=b.notna(); sc,b=sc[m],b[m]
            if len(sc)<100: continue
            ex=(b-b.median())*100; pct=sc.rank(pct=True)*100
            for lo,hi in BINS: rec.append((dates[t],mk,f"{lo}-{hi}",ex[(pct>lo)&(pct<=hi)].mean()))
            rec.append((dates[t],mk,"top20",ex.reindex(sc.sort_values(ascending=False).head(20).index).mean()))
    df=pd.DataFrame(rec,columns=['d','mk','bin','ex']); per=df.groupby(['d','bin']).ex.mean().unstack()
    print(f"\n=== svr5 백분위 구간별 h{h} 초과(유니버스 중앙값 대비 %p) — 주간 앵커 n={per.shape[0]} ({per.index.min()}~{per.index.max()}) ===")
    for b in [f"{lo}-{hi}" for lo,hi in BINS]+["top20"]:
        x=per[b].dropna(); lo_,hi_=boot(x.values); print(f"   {b:>7s}: {x.mean():+6.2f}  [{lo_:+.2f},{hi_:+.2f}]  양(+) {100*(x>0).mean():.0f}%")
    pre=per[per.index<'20260715']; post=per[per.index>='20260715']
    for lab,pp in (("등록 전(4/10~7/14)",pre),("등록 후(7/15~)",post)):
        if len(pp)<3: continue
        print(f"   [{lab} n={len(pp)}] 90-95 {pp['90-95'].mean():+.2f} · 95-98 {pp['95-98'].mean():+.2f} · 98-100 {pp['98-100'].mean():+.2f} · top20 {pp['top20'].mean():+.2f} · 0-10 {pp['0-10'].mean():+.2f}")
