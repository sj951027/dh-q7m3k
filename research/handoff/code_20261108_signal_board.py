"""Independent offline review. Reads DB mode=ro; writes nothing; JSON to stdout.
Run: python -B research/handoff/code_20261108_signal_board.py
No imports from the reviewed research or operational engine.
Alternative chosen before computation: KOSPI 60-session log-return std, ddof=1.
"""
from pathlib import Path
import json
import sqlite3
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT.parent / 'dh-q7m3k-data' / 'ohlcv_10y.db'
NBOOT = 2000
EXCLUDE = ('금융','은행','증권','보험','캐피탈','캐피털','카드','손해보험',
           '생명','화재','저축','여신','신탁','리츠','REIT','부동산투자','스팩','SPAC')


def panel():
    with sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True) as con:
        con.execute('PRAGMA query_only=ON')
        days = [r[0] for r in con.execute('SELECT DISTINCT date FROM prices ORDER BY date')]
        meta = con.execute('SELECT ticker,name,market,note FROM meta ORDER BY ticker').fetchall()
        chosen = []
        for t, name, market, note in meta:
            name = name or ''
            if (market in ('KOSPI','KOSDAQ','KOSDAQ GLOBAL') and t.endswith('0')
                    and t not in ('055550','001450')
                    and not any(k in (name.upper() if k in ('SPAC','REIT') else name) for k in EXCLUDE)):
                chosen.append((t, 'delisted' in (note or '')))
        dmap = {d:i for i,d in enumerate(days)}
        p = np.full((len(days),len(chosen)),np.nan)
        v = np.zeros_like(p)
        for j,(ticker,_) in enumerate(chosen):
            for date,price,volume in con.execute('SELECT date,close,volume FROM prices WHERE ticker=? ORDER BY date',(ticker,)):
                i=dmap[date]
                if price is not None and price>0: p[i,j]=price
                if volume is not None: v[i,j]=volume
        ix = pd.read_sql_query("SELECT date,close FROM index_daily WHERE series='KOSPI' ORDER BY date",con).set_index('date').close
    future = p.copy()
    for j,(_,delisted) in enumerate(chosen):
        if delisted:
            last = np.maximum.accumulate(np.where(np.isfinite(p[:,j]),np.arange(len(days)),0))
            future[:,j] = p[last,j]
    r20 = (ix/ix.shift(20)-1)*100
    vols = {n:np.log(ix).diff().rolling(n).std(ddof=1)*np.sqrt(250)*100 for n in (20,60)}
    rows=[]
    exits_removed=0
    for i in range(130,len(days)-41,5):
        r=p[i]/p[i-20]-1
        base=(np.isfinite(r)&(v[i]!=0)&(v[i+1]!=0)&(p[i]>=1000)&np.isfinite(p[i+1])&(p[i+1]>0))
        eligible=base&np.isfinite(future[i+41])
        exits_removed += int((base&~eligible).sum())
        if eligible.sum()<300: continue
        cutoff=np.percentile(r[eligible],20)
        pick=eligible&(r<=cutoff)
        date=days[i]
        k=r20.get(date,np.nan)
        rv=vols[20].get(date,np.nan)
        if not np.isfinite(k) or not np.isfinite(rv): continue
        cell=['A2','A1','B','C','D1','D2'][np.searchsorted([-10,-5,0,5,10],k,side='left')]
        net=(future[i+41]/p[i+1]-1-.0035)*100
        a,b=float(net[pick].mean()),float(net[eligible].mean())
        rows.append(dict(date=date,month=date[:6],half='앞' if date<'20210101' else '뒤',
                         cell=cell,cell4=cell[0],r20=k,rv=rv,rv60=vols[60].get(date,np.nan),
                         n_os=int(pick.sum()),os40=a,all40=b,exc=a-b))
    return pd.DataFrame(rows),dict(universe=len(chosen),calendar=len(days),db_last=days[-1],exit_missing_removed=exits_removed)


def aggregates(sub,col):
    g=sub.groupby('month',sort=True)[col].agg(['sum','count'])
    return g['sum'].to_numpy(),g['count'].to_numpy()


def ci(sub,col,rng):
    sums,ns=aggregates(sub,col)
    draw=rng.choice(len(ns),(NBOOT,len(ns)))
    return np.percentile(sums[draw].sum(1)/ns[draw].sum(1),[2.5,97.5]).tolist()


def difference(a,b,rng):
    sa,na=aggregates(a,'exc'); sb,nb=aggregates(b,'exc')
    # Interleave A/B draws as in the reviewed definition, independently resampling groups.
    vals=[]
    for _ in range(NBOOT):
        x=rng.choice(len(na),len(na)); y=rng.choice(len(nb),len(nb))
        vals.append(sa[x].sum()/na[x].sum()-sb[y].sum()/nb[y].sum())
    return dict(n_hi=len(a),n_lo=len(b),months_hi=a.month.nunique(),months_lo=b.month.nunique(),
                hi=a.exc.mean(),lo=b.exc.mean(),diff=a.exc.mean()-b.exc.mean(),ci=np.percentile(vals,[2.5,97.5]).tolist())


def summary(sub,rng):
    ec=ci(sub,'exc',rng); ac=ci(sub,'all40',rng); oc=ci(sub,'os40',rng)
    return dict(n=len(sub),months=sub.month.nunique(),exc=sub.exc.mean(),ci=ec,
                os=sub.os40.mean(),os_ci=oc,market=sub.all40.mean(),market_ci=ac)


def volcheck(r,col,rng):
    q=pd.qcut(r[col],5,labels=False)
    out={}
    for scope,mask in [('all',np.ones(len(r),bool)),('first',r.half=='앞'),('second',r.half=='뒤')]:
        groups=[]
        for j in range(5):
            sub=r[mask&(q==j)]
            groups.append(summary(sub,rng))
        out[scope]=dict(groups=groups,diff=difference(r[mask&(q==4)],r[mask&(q==0)],rng))
    within={}
    for c in 'ABCD':
        sub=r[r.cell4==c]; med=sub[col].median()
        within[c]=difference(sub[sub[col]>med],sub[sub[col]<=med],rng)
    out['within']=within
    return out


def main():
    r,info=panel()
    info.update(n=len(r),first=r.date.min(),last=r.date.max(),months=r.month.nunique())
    rng=np.random.default_rng(7)
    e1={}
    for scope,sub0 in [('all',r),('first',r[r.half=='앞']),('second',r[r.half=='뒤'])]:
        e1[scope]={}
        for c in ['A2','A1','B','C','D1','D2','A','D','all']:
            s=sub0 if c=='all' else sub0[(sub0.cell4==c) if c in ('A','D') else (sub0.cell==c)]
            if len(s)>=4: e1[scope][c]=summary(s,rng)
    e2=volcheck(r,'rv',rng)
    alt=volcheck(r,'rv60',np.random.default_rng(7))
    # Existing results are opened only after independently reconstructing everything.
    ref=pd.read_csv(ROOT/'research/out_signal_board/tenyr_days.csv',dtype={'date':str})
    joined=r.merge(ref,on='date',suffixes=('_new','_ref'),validate='one_to_one')
    compare=dict(matched=len(joined),reference=len(ref),max_abs={
        k:float(np.max(np.abs(joined[k+'_new']-joined[k+'_ref']))) for k in ['r20','rv','n_os','os40','all40','exc']},
        cell_mismatch=int((joined.cell_new!=joined.cell_ref).sum()))
    print(json.dumps(dict(info=info,comparison=compare,e1=e1,e2=e2,alternative60=alt),ensure_ascii=False,indent=2,default=lambda x:x.item()))


if __name__=='__main__': main()
