"""Independent row checks, explicit-feature detail, and temporal shortlist audit."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np,pandas as pd,json
from code_target20_20261003 import block_idx
P=Path(__file__).resolve().parents[2]/'research/target20_conditions_20261004';G=P/'fullgrid'
O=pd.read_parquet(P/'outcomes.parquet');Q=pd.read_parquet(P/'feature_quintiles.parquet');AV=pd.read_parquet(P/'absolute_values.parquet');C=pd.read_csv(G/'conditions.csv').set_index('name')
DATES=np.array(sorted(O.date.unique()));dmap={x:i for i,x in enumerate(DATES)};d=O.date.map(dmap).to_numpy();market=O.market.to_numpy()
casebook=[]
def masks(name):
 row=C.loc[name];feature=row.feature
 if row.kind=='quintile':v=Q[feature].to_numpy();return v==int(row.level),v>0
 v=AV[feature].to_numpy();a,b=str(row.level)[1:-1].split(',');a,b=float(a),float(b);return np.isfinite(v)&(v>a)&(v<=b),np.isfinite(v)
def detailed(mkt,a=None,b=None,label=None):
 casebook.append((mkt,a,b,label))
 mm=market==mkt
 aa,va=masks(a) if a else (np.ones(len(O),bool),np.ones(len(O),bool))
 bb,vb=masks(b) if b else (np.ones(len(O),bool),np.ones(len(O),bool))
 baseline=mm&va&vb;selected=baseline&aa&bb;parent_a=baseline&aa;parent_b=baseline&bb
 out=[]
 for per in ['all','2024','2025','2026']:
  days=np.arange(len(DATES)) if per=='all' else np.where(np.char.startswith(DATES,per))[0];count=np.bincount(d[selected],minlength=len(DATES))[days];n=count.sum();present=(count>0).sum()
  row=dict(market=mkt,a=a or 'ALL',b=b or '',label=label or '',period=per,n=int(n),n_dates=int(present))
  ix=block_idx(len(days),20);den=count[ix].sum(axis=1)
  for metric in ['ret','hit','first','mae','mdd','joint']:
   values=O[metric].to_numpy();sums=np.bincount(d[selected],weights=values[selected],minlength=len(DATES))[days]
   row[metric]=sums.sum()/n if n else np.nan
   if n and present>20:
    boots=np.divide(sums[ix].sum(axis=1),den,out=np.full(len(ix),np.nan),where=den>0);row[metric+'_lo'],row[metric+'_hi']=np.nanquantile(boots,[.025,.975])
   for pname,pool in [('base',baseline),('a',parent_a),('b',parent_b)]:
    if metric not in ['ret','hit','joint']:continue
    nc=np.bincount(d[pool],minlength=len(DATES))[days];ns=np.bincount(d[pool],weights=values[pool],minlength=len(DATES))[days];means=np.divide(ns,nc,out=np.zeros(len(days)),where=nc>0);delta=sums-count*means
    field=metric+'_vs_'+pname;row[field]=delta.sum()/n if n else np.nan
    if n and present>20:
     boots=np.divide(delta[ix].sum(axis=1),den,out=np.full(len(ix),np.nan),where=den>0);row[field+'_lo'],row[field+'_hi']=np.nanquantile(boots,[.025,.975])
  out.append(row)
 return out

selection=[];counts=[];details=[]
for mkt in ['kospi','kosdaq']:
 details+=detailed(mkt,label='market baseline')
 # All explicitly requested RSI14/PER/market-cap cells, not just favourable cells.
 for name,row in C.iterrows():
  if (row.feature in ['rsi14','daily_per','annual_pe_approx'] and row.kind=='absolute') or (row.feature=='market_cap'):
   details+=detailed(mkt,name,label='explicit user feature')
 a=pd.read_parquet(G/f'pairs_{mkt}.parquet');pivot=a[a.period.isin(['2024','2025'])].pivot(index=['a','b'],columns='period',values=['n','n_dates','excess','joint_excess'])
 # These rules label a shortlist; the full unfiltered grid is always retained.
 good=(pivot['n']>=200).all(axis=1)&(pivot['n_dates']>=40).all(axis=1)&(pivot['excess']>0).all(axis=1)&(pivot['joint_excess']>0).all(axis=1)
 train=pivot[good].copy();score=train['joint_excess'].mean(axis=1);ranked=score.sort_values(ascending=False)
 test=a[a.period=='2026'].set_index(['a','b']).reindex(ranked.index).copy();test['train_rank']=np.arange(1,len(test)+1);test['train_joint_excess']=ranked.values;test['selected_using']='2024+2025 only';selection.append(test.reset_index())
 counts.append(dict(market=mkt,total_pairs=len(pivot),past_consistent=len(train),in2026_available=int((test.n>0).sum()),in2026_both_positive=int(((test.excess>0)&(test.joint_excess>0)).sum()),in2026_mean_return_positive=int((test.ret>0).sum())))
 for x,y in ranked.head(12).index:details+=detailed(mkt,x,y,label='past-selected representative')
 # Independent re-aggregation, including parent-conditional incremental effect.
 sample=a[(a.period=='all')&(a.n>0)].sample(80,random_state=20261004)
 errors=[]
 for row in sample.itertuples():
  aa,va=masks(row.a);bb,vb=masks(row.b);sel=(market==mkt)&aa&bb;pool=(market==mkt)&va&vb
  assert sel.sum()==row.n
  ret=O.ret.to_numpy();nc=np.bincount(d[pool],minlength=len(DATES));ns=np.bincount(d[pool],weights=ret[pool],minlength=len(DATES));mean=np.divide(ns,nc,out=np.zeros(len(DATES)),where=nc>0)
  calc=(ret[sel]-mean[d[sel]]).mean();errors.append(abs(calc-row.excess));assert abs(calc-row.excess)<.002
  parent=(market==mkt)&aa&vb;nc=np.bincount(d[parent],minlength=len(DATES));ns=np.bincount(d[parent],weights=ret[parent],minlength=len(DATES));mean=np.divide(ns,nc,out=np.zeros(len(DATES)),where=nc>0)
  assert abs((ret[sel]-mean[d[sel]]).mean()-row.added_b_ret)<.002
 print('CHECK',mkt,max(errors),flush=True)
pd.concat(selection,ignore_index=True).to_csv(P/'past_selected_2026.csv',index=False,encoding='utf-8-sig');pd.DataFrame(counts).to_csv(P/'selection_counts.csv',index=False);pd.DataFrame(details).to_csv(P/'detailed_moving_blocks.csv',index=False,encoding='utf-8-sig')
# Fresh direct price-path checks, independent of the outcome constructor.
z=np.load(P.parents[0]/'fullscan_20260903/panel.npz',allow_pickle=True);price=z['close'];op=z['open'];ff=pd.DataFrame(price).ffill().to_numpy();maxerr=0
for row in O.sample(300,random_state=20261004).itertuples():
 path=ff[row.t+1:row.t+21,row.j]/op[row.t+1,row.j]-1;ret=(path[-1]-.005)*100
 maxerr=max(maxerr,abs(ret-row.ret));assert np.isclose(ret,row.ret,atol=1e-4)
 assert bool(path[0]>0)==bool(row.first);assert bool(path[-1]-.005>=.2)==bool(row.hit)
 assert bool(path[-1]-.005>=.2 and path.min()>=-.1 and (path>0).mean()>=.8 and path[0]>0)==bool(row.joint)
ann=pd.read_csv(P/'annual_availability.csv',dtype={'available_receipt':str});dates=z['dates'].astype(str);assert all(dates[t]>rc for t,rc in zip(ann.t,ann.available_receipt))
# Other holding horizons for the explicit cells and past-selected representatives.
hrows=[];tt=O.t.to_numpy();jj=O.j.to_numpy();entry=op[tt+1,jj];boot=block_idx(len(DATES),20)
for horizon in [5,10,40,60]:
 good=tt+horizon<len(price);ret=np.full(len(O),np.nan);ret[good]=(ff[tt[good]+horizon,jj[good]]/entry[good]-1-.005)*100
 bix=block_idx(len(DATES),horizon)
 for mkt,a,b,label in casebook:
  aa,va=masks(a) if a else (np.ones(len(O),bool),np.ones(len(O),bool));bb,vb=masks(b) if b else (np.ones(len(O),bool),np.ones(len(O),bool))
  pool=(market==mkt)&va&vb&good;sel=pool&aa&bb;n=int(sel.sum())
  if n==0:continue
  counts=np.bincount(d[sel],minlength=len(DATES));sums=np.bincount(d[sel],weights=ret[sel],minlength=len(DATES));nc=np.bincount(d[pool],minlength=len(DATES));ns=np.bincount(d[pool],weights=ret[pool],minlength=len(DATES));mean=np.divide(ns,nc,out=np.zeros(len(DATES)),where=nc>0);delta=sums-counts*mean
  den=counts[bix].sum(axis=1);bs=np.divide(delta[bix].sum(axis=1),den,out=np.full(len(bix),np.nan),where=den>0);lo,hi=np.nanquantile(bs,[.025,.975]);rs=np.divide(sums[bix].sum(axis=1),den,out=np.full(len(bix),np.nan),where=den>0);rl,rh=np.nanquantile(rs,[.025,.975])
  hrows.append(dict(market=mkt,a=a or 'ALL',b=b or '',label=label,h=horizon,n=n,n_dates=int((counts>0).sum()),ret=float(ret[sel].mean()),ret_lo=rl,ret_hi=rh,hit=float((ret[sel]>=20).mean()*100),positive=float((ret[sel]>0).mean()*100),excess=float(delta.sum()/n),excess_lo=lo,excess_hi=hi))
 print('HORIZON',horizon,flush=True)
pd.DataFrame(hrows).to_csv(P/'selected_horizons.csv',index=False)
(P/'verification.json').write_text(json.dumps(dict(pair_checks=160,price_checks=300,max_return_error=float(maxerr),annual_availability_checks=len(ann)),indent=2),encoding='utf-8')
print('DONE detail; verification.json and selected_horizons.csv saved',flush=True)
