"""Stored scores in their own recorded universes, without the common liquidity/price guard."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import sqlite3,numpy as np,pandas as pd,json
from code_target20_20261003 import rolling,block_idx
R=Path(__file__).resolve().parents[2];P=R/'research/target20_conditions_20261004'
z=np.load(R/'research/fullscan_20260903/panel.npz',allow_pickle=True);dates=z['dates'].astype(str);tick=z['tick'].astype(str);di={x:i for i,x in enumerate(dates)};ji={x:i for i,x in enumerate(tick)}
c=z['close'].astype(float);o=z['open'];v=z['vol'];ff=pd.DataFrame(c).ffill().to_numpy();delta=pd.DataFrame(c).diff();gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean();loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean();rsi=(100*gain/(gain+loss)).to_numpy();amount=rolling(c*v,20,15)
db=sqlite3.connect(f'file:{R/"history.db"}?mode=ro',uri=True);parts=[]
for table,col in [('v3_scores','final_score_v3'),('lowvol_scores','lowvol_score'),('wu_scores','wu_score')]:parts.append(pd.read_sql_query(f'SELECT run_id,market,ticker,model_id,{col} AS score,frozen_at FROM {table}',db))
db.close();d=pd.concat(parts,ignore_index=True);allmodels=sorted(d.model_id.unique());d['t']=d.run_id.map(di);d['j']=d.ticker.map(ji);d=d[d.t.notna()&d.j.notna()&(d.t<len(dates)-26)].copy();d.t=d.t.astype(int);d.j=d.j.astype(int)
f=pd.to_datetime(d.frozen_at,format='mixed',utc=True,errors='coerce');cut=pd.to_datetime([str(dates[t+1])+' 09:00:00+09:00' for t in d.t],utc=True);d=d[f.notna()&(f.to_numpy()<=cut.to_numpy())].copy()
d['market']=d.market.str.lower();d['rank']=d.groupby(['model_id','run_id','market']).score.rank(pct=True);d['bin']=np.ceil(d['rank']*5)
t=d.t.to_numpy();j=d.j.to_numpy();entry=o[t+1,j];filled=np.isfinite(entry)&(entry>0)&(v[t+1,j]>0)&~((abs(z['high'][t+1,j]-z['low'][t+1,j])<1e-8)&(abs(entry/c[t,j]-1)>=.295))
d['filled']=filled;d['ret']=np.where(filled,(ff[t+20,j]/entry-1-.005)*100,np.nan);d['hit']=np.where(filled,(d.ret>=20)*100,np.nan);d['rsi14']=rsi[t,j];d['amount20']=amount[t,j]
db=sqlite3.connect(f'file:{R.parent/"dh-q7m3k-data/ohlcv.db"}?mode=ro',uri=True);val=pd.read_sql_query('SELECT ticker,date,per FROM valuation_daily',db);db.close();val=val.drop_duplicates(['date','ticker']);d['previous_date']=dates[np.maximum(d.t.to_numpy()-1,0)];d=d.merge(val,left_on=['previous_date','ticker'],right_on=['date','ticker'],how='left')
conditions={f'score_q{i}':(d.bin==i).to_numpy() for i in range(1,6)};top=(d.bin==5).to_numpy()
for field,edges in [('rsi14',[-np.inf,20,30,50,70,80,np.inf]),('per',[-np.inf,0,5,10,20,40,np.inf]),('amount20',[0,5e8,5e9,np.inf])]:
 x=d[field].to_numpy()
 for lo,hi in zip(edges[:-1],edges[1:]):conditions[f'score_q5 & {field}({lo},{hi}]']=top&np.isfinite(x)&(x>lo)&(x<=hi)
rows=[]
for model in allmodels:
 for market in ['kospi','kosdaq']:
  scope=(d.model_id==model)&(d.market==market);pool=d[scope];base=pool.groupby('run_id').ret.mean()
  for name,mask in conditions.items():
   g=d[scope&mask];filledg=g[g.filled];n=len(filledg);out=dict(model=model,market=market,condition=name,n_selected=len(g),n=n,n_dates=filledg.run_id.nunique(),ret=filledg.ret.mean(),hit=filledg.hit.mean(),excess=np.nan,ret_lo=np.nan,ret_hi=np.nan,excess_lo=np.nan,excess_hi=np.nan)
   if n:
    g=filledg.assign(excess=filledg.ret-filledg.run_id.map(base));out['excess']=g.excess.mean();daily=g.groupby('run_id').agg(n=('ret','size'),ret=('ret','sum'),excess=('excess','sum')).reindex(sorted(pool.run_id.unique()),fill_value=0)
    if len(daily)>20:
     ix=block_idx(len(daily),20);den=daily.n.to_numpy()[ix].sum(axis=1)
     for field in ['ret','excess']:
      num=daily[field].to_numpy()[ix].sum(axis=1);bs=np.divide(num,den,out=np.full(len(ix),np.nan),where=den>0);out[field+'_lo'],out[field+'_hi']=np.nanquantile(bs,[.025,.975])
   rows.append(out)
pd.DataFrame(rows).to_csv(P/'models_own_universe.csv',index=False,encoding='utf-8-sig');print('DONE models own',len(rows),len(d),flush=True)
