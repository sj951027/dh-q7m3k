"""Offline helpers for the event/open-search handoff; no operational writes."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'dh-q7m3k-data'
OUT=ROOT/'research/handoff/out_20261110_event_open'
KST=dt.timezone(dt.timedelta(hours=9))
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'research'))
from lib import tenyr

def now(): return dt.datetime.now(KST).isoformat()
def ro(path):
    c=sqlite3.connect(f'file:{Path(path).as_posix()}?mode=ro',uri=True)
    c.execute('PRAGMA query_only=ON')
    return c
def save(df,name):
    OUT.mkdir(exist_ok=True)
    df.to_csv(OUT/(name+'.csv'),index=False,encoding='utf-8-sig')
def meta(name, obj):
    OUT.mkdir(exist_ok=True)
    obj['saved_at']=now()
    (OUT/(name+'.json')).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def stat(s,split='20250101',alpha=.05/16,k=2000):
    s=s.dropna().sort_index()
    if not len(s): return dict(n=0,mean=np.nan,lo=np.nan,hi=np.nan,blo=np.nan,bhi=np.nan,front=np.nan,back=np.nan,front_n=0,back_n=0)
    dates=np.asarray(s.index).astype(str); months=np.array([x[:6] for x in dates])
    x=s.to_numpy(float)
    tenyr.reset_rng(7)
    lo,hi=tenyr.block_ci(x,months,k=k)
    um, inv=np.unique(months,return_inverse=True)
    sums=np.bincount(inv,weights=x); counts=np.bincount(inv)
    ix=np.random.default_rng(7).integers(0,len(um),(k,len(um)))
    means=sums[ix].sum(1)/counts[ix].sum(1)
    # Both implementations use the identical month draws; check the shared helper.
    assert np.allclose([lo,hi],np.quantile(means,[.025,.975]),atol=1e-10)
    blo,bhi=np.quantile(means,[alpha/2,1-alpha/2])
    front=x[dates<split]; back=x[dates>=split]
    result=dict(n=len(s),months=len(um),mean=x.mean(),lo=lo,hi=hi,blo=blo,bhi=bhi,
                front=front.mean() if len(front) else np.nan,back=back.mean() if len(back) else np.nan,
                front_n=len(front),back_n=len(back))
    for label,mask in [('front',dates<split),('back',dates>=split)]:
        tenyr.reset_rng(7)
        a,b=tenyr.block_ci(x[mask],months[mask],k=k)
        result[label+'_lo']=a; result[label+'_hi']=b
    return result

def inspect():
    info={}
    for path in [DATA/'ohlcv.db',ROOT/'history.db',DATA/'earnings.db']:
        if not path.exists(): continue
        con=ro(path)
        tables=[x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        info[str(path)]={}
        for tb in tables:
            if tb not in ['daily_ohlcv','daily_ohlcv_extra','market_daily','dart_events','daily_flows','short_flows','stage3_final','runs','earnings','quarterly','filings','universe_events']: continue
            cols=[tuple(x) for x in con.execute(f'PRAGMA table_info({tb})')]
            info[str(path)][tb]=cols
            print(path.name,tb,[x[1] for x in cols],flush=True)
        if 'dart_events' in tables:
            print(pd.read_sql('SELECT event_type,COUNT(*) n,MIN(rcept_dt) first,MAX(rcept_dt) last FROM dart_events GROUP BY event_type',con).to_string(index=False))
        con.close()
    meta('schema_inspection',info)

if __name__=='__main__': inspect()
