"""Evaluate frozen quarterly predictions, paired day blocks and long horizon."""
import sys,json,warnings
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np,pandas as pd
from code_target20_20261003 import block_idx
warnings.filterwarnings('ignore',category=RuntimeWarning)
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'research/target20_discovery_20261004'
methods=['learn_hit','learn_first','learn_joint','learn_ret','learn_balanced','cluster_shape','control_amount','control_fundamental','control_rsi'];allrows=[];daily=[];picks=[];reliability=[];all_checks=0
z=np.load(ROOT/'research/fullscan_20260903/panel.npz',allow_pickle=True);c=z['close'].astype(float);o=z['open'].astype(float);ff=pd.DataFrame(c).ffill().to_numpy();N,T=c.shape[1],c.shape[0]
for market in ['kospi','kosdaq']:
 df=pd.read_parquet(P/f'predictions_{market}.parquet');df['market']=market
 for metric in ['ret','hit','first','mae','joint']:
  df['base_'+metric]=df.groupby('date')[metric].transform('mean')
 df['size_base_ret']=df.groupby(['date','size_bin']).ret.transform('mean')
 for method in methods:
  # Stable pre-outcome ranking. Ties are resolved by known amount, then ticker.
  chosen=df.dropna(subset=[method]).sort_values(['date',method,'amount','ticker'],ascending=[True,False,False,True]).groupby('date').head(10).copy();chosen['method']=method
  assert chosen.groupby('date').size().max()<=10
  all_checks+=chosen.date.nunique()
  for metric in ['ret','hit','first','mae','joint']:chosen['ex_'+metric]=chosen[metric]-chosen['base_'+metric]
  chosen['size_ex_ret']=chosen.ret-chosen.size_base_ret
  tt=chosen.t.to_numpy(int);jj=chosen.j.to_numpy(int);entry=o[tt+1,jj];h40=np.minimum(tt+40,T-1);valid=tt+40<T;chosen['ret40']=np.where(valid,(ff[h40,jj]/entry-1-.005)*100,np.nan)
  chosen['score']=chosen[method];picks.append(chosen[['market','method','fold','date','t','j','ticker','score','ret','hit','first','mae','joint','ret40']])
  columns=['ret','hit','first','mae','joint','ex_ret','ex_hit','ex_first','ex_mae','ex_joint','size_ex_ret','ret40'];g=chosen.groupby(['date','fold'])[columns].mean().reset_index();g['market']=market;g['method']=method;g['n']=chosen.groupby('date').size().reindex(g.date).to_numpy();daily.append(g)
  for y in ['hit','first','joint']:
   if method!='learn_'+y:continue
   score=df[method];edges=np.linspace(0,1,11);binid=np.clip(np.digitize(score,edges)-1,0,9)
   for b in range(10):
    sel=binid==b
    if sel.any():reliability.append(dict(market=market,target=y,prob_bin=b,n=int(sel.sum()),predicted=float(score[sel].mean()),observed=float((df.loc[sel,y]>0).mean())))
day=pd.concat(daily,ignore_index=True);selected=pd.concat(picks,ignore_index=True);selected.to_csv(P/'selected_predictions.csv.gz',index=False,compression='gzip');day.to_csv(P/'daily_results.csv',index=False);pd.DataFrame(reliability).to_csv(P/'probability_reliability.csv',index=False)
for market in ['kospi','kosdaq']:
 for method in methods:
  d=day[(day.market==market)&(day.method==method)].sort_values('date')
  ctl=day[(day.market==market)&(day.method=='control_amount')].set_index('date')
  for period in ['all','2025','2026']+sorted(d.fold.unique().tolist()):
   s=d if period=='all' else d[d.date.str.startswith(period)] if len(period)==4 else d[d.fold==period]
   r=dict(market=market,method=method,period=period,n=int(s.n.sum()),n_dates=len(s),n_dates40=int(s.ret40.notna().sum()))
   if not len(s):continue
   ix=block_idx(len(s),20)
   for col in ['ret','hit','first','mae','joint','ex_ret','ex_hit','ex_joint','size_ex_ret','ret40']:
    a=s[col].to_numpy();r[col]=float(np.nanmean(a));bs=np.nanmean(a[ix],axis=1);r[col+'_lo'],r[col+'_hi']=np.nanquantile(bs,[.025,.975])
   for col in ['ret','hit','first','joint']:
    a=s[col].to_numpy()-ctl.reindex(s.date)[col].to_numpy();r['vs_amount_'+col]=a.mean();r['vs_amount_'+col+'_lo'],r['vs_amount_'+col+'_hi']=np.quantile(a[ix].mean(axis=1),[.025,.975])
   stocks=selected[(selected.market==market)&(selected.method==method)&selected.date.isin(s.date)].groupby('ticker').agg(n=('ret','size'),sum_ret=('ret','sum'))
   r['unique_stocks']=len(stocks);r['largest_stock_share']=float(stocks.n.max()/stocks.n.sum()*100);r['best_stock']=stocks.sum_ret.idxmax();sub=selected[(selected.market==market)&(selected.method==method)&selected.date.isin(s.date)&(selected.ticker!=r['best_stock'])];r['without_best_stock_ret']=sub.groupby('date').ret.mean().mean()
   allrows.append(r)
pd.DataFrame(allrows).to_csv(P/'summary.csv',index=False)
audit=pd.concat([pd.read_csv(P/f'fold_audit_{m}.csv') for m in ['kospi','kosdaq']]);assert (audit.train_last_outcome<audit.test_first_signal).all()
# Explicit raw-path checks on independently selected random prediction rows.
sample=selected.sample(200,random_state=20261004);error=0
for row in sample.itertuples():
 ret=(ff[row.t+20,row.j]/o[row.t+1,row.j]-1-.005)*100;error=max(error,abs(ret-row.ret));assert abs(ret-row.ret)<1e-4
(P/'verification.json').write_text(json.dumps(dict(folds=len(audit),selected_day_checks=all_checks,raw_price_checks=len(sample),max_price_error=error,dates=int(day.date.nunique()),selected_rows=len(selected),methods=methods),indent=2),encoding='utf-8')
print('EVALUATED',len(allrows),len(selected),flush=True)
