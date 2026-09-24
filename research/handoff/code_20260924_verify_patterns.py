"""Independent long-form reconstruction of four selected baskets, no main-script import."""
from pathlib import Path
import sqlite3
import json
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

now=datetime.now(ZoneInfo('Asia/Seoul'))
assert not (now.weekday()<5 and '20:10'<=now.strftime('%H:%M')<='22:30')
root=Path(__file__).resolve().parents[2]
out=Path(__file__).with_name('pattern_scan_20260924')
con=sqlite3.connect((root.parent/'dh-q7m3k-data/ohlcv.db').as_uri()+'?mode=ro',uri=True)
con.execute('PRAGMA query_only=ON')
dates=[r[0] for r in con.execute('SELECT DISTINCT date FROM daily_ohlcv ORDER BY date')]
coh=pd.read_csv(out/'cohorts.csv',dtype={'date':str})
picks=pd.read_csv(out/'contributions.csv',dtype={'date':str,'ticker':str})
results=[]
for d in ['20250103','20260304']:
    t=dates.index(d);e=dates[t+1];end=dates[t+41]
    history=pd.read_sql_query('SELECT ticker,date,close,volume,shares,market FROM daily_ohlcv WHERE date BETWEEN ? AND ? ORDER BY ticker,date',con,params=(dates[t-120],d))
    benchmark=pd.read_sql_query('SELECT series,date,close FROM market_daily WHERE date IN (?,?,?,?)',con,params=(dates[t-20],d,e,end)).pivot(index='date',columns='series',values='close')
    features=[]
    for ticker,g in history.groupby('ticker',sort=True):
        g=g.set_index('date').reindex(dates[t-120:t+1])
        if (g.close.iloc[-120:].notna().sum()!=120 or (g.volume.iloc[-60:]==0).sum()>5
            or (g.close*g.volume).iloc[-20:].mean()<5e8 or not g.volume.iloc[-1]>0):continue
        market=g.market.iloc[-1]
        if market not in ['KOSPI','KOSDAQ']:continue
        r=g.close.pct_change(fill_method=None)
        features.append(dict(ticker=ticker,market=market,quiet=-r.iloc[-60:].std(),
            rs20=g.close.iloc[-1]/g.close.iloc[-21]-benchmark.loc[d,market]/benchmark.loc[dates[t-20],market],
            size=g.close.iloc[-1]*g.shares.iloc[-1]))
    f=pd.DataFrame(features).set_index('ticker')
    f['score']=f.groupby('market')[['quiet','rs20','size']].rank(pct=True).mean(axis=1)
    for m in ['KOSPI','KOSDAQ']:
        ids=f[f.market==m].sort_values('score',ascending=False,kind='stable').head(20).index.tolist()
        expected=picks[(picks.name=='quiet_strength_with_size')&(picks.offset==0)&(picks.date==d)&(picks.market==m)].ticker.tolist()
        assert set(ids)==set(expected),(d,m,'selection mismatch')
        returns=[]
        for ticker in ids:
            g=pd.read_sql_query('SELECT date,close,volume FROM daily_ohlcv WHERE ticker=? AND date BETWEEN ? AND ? ORDER BY date',con,params=(ticker,e,end))
            if not len(g) or g.iloc[0].date!=e or g.iloc[0].volume<=0:returns.append(0.);continue
            returns.append(g.iloc[-1].close/g.iloc[0].close-1-.0035)
        net=sum(returns)/20
        original=coh[(coh.name=='quiet_strength_with_size')&(coh.date==d)&(coh.market==m)&(coh.h==40)].iloc[0]
        err=abs(net-original.net)
        assert err<1e-12,(d,m,err)
        results.append(dict(date=d,market=m,selected=20,net=net,abs_error=err))
con.close()
(out/'verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
