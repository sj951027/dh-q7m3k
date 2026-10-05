"""Post-hoc hypothesis: frozen learner reranks fixed fundamental top50; no refit."""
from pathlib import Path
import numpy as np,pandas as pd
from code_target20_20261003 import block_idx
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'research/target20_discovery_20261004';rows=[];daily=[]
for market in ['kospi','kosdaq']:
 df=pd.read_parquet(P/f'predictions_{market}.parquet');df=df.dropna(subset=['control_fundamental'])
 ordered=df.sort_values(['date','control_fundamental','amount','ticker'],ascending=[True,False,False,True]);pool=ordered.groupby('date').head(50);base=ordered.groupby('date').head(10).groupby('date')[['ret','hit','first','mae','joint']].mean()
 for target in ['first','joint','ret']:
  chosen=pool.sort_values(['date','learn_'+target,'amount','ticker'],ascending=[True,False,False,True]).groupby('date').head(10)
  d=chosen.groupby(['date','fold'])[['ret','hit','first','mae','joint']].mean().reset_index();d['market']=market;d['method']='hybrid_'+target;daily.append(d)
  for period in ['all','2025','2026']+sorted(d.fold.unique().tolist()):
   s=d if period=='all' else d[d.date.str.startswith(period)] if len(period)==4 else d[d.fold==period];ix=block_idx(len(s),20);r=dict(market=market,method='hybrid_'+target,period=period,n_dates=len(s),n=len(chosen[chosen.date.isin(s.date)]))
   for metric in ['ret','hit','first','mae','joint']:
    a=s[metric].to_numpy();r[metric]=a.mean();r[metric+'_lo'],r[metric+'_hi']=np.quantile(a[ix].mean(axis=1),[.025,.975]);delta=a-base.reindex(s.date)[metric].to_numpy();r['vs_fund_'+metric]=delta.mean();r['vs_fund_'+metric+'_lo'],r['vs_fund_'+metric+'_hi']=np.quantile(delta[ix].mean(axis=1),[.025,.975])
   rows.append(r)
pd.DataFrame(rows).to_csv(P/'hybrid_summary.csv',index=False);pd.concat(daily).to_csv(P/'hybrid_daily.csv',index=False)
print(pd.DataFrame(rows).query("period=='all'").round(3).to_string(index=False))
