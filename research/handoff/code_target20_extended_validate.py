"""Cross-check aggregates and save size/share-count and account uncertainty diagnostics."""
import sys,json,warnings
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np,pandas as pd
from code_target20_20261003 import block_idx
warnings.filterwarnings('ignore',category=RuntimeWarning)
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'research/target20_extended_20261004';O=pd.read_parquet(P/'outcomes.parquet');Q=pd.read_parquet(P/'feature_quintiles.parquet')
z=np.load(ROOT/'research/fullscan_20260903/panel.npz',allow_pickle=True);sh=z['shares'].astype(float);r=sh[1:]/np.where(sh[:-1]>0,sh[:-1],np.nan);flag=np.any((r>1.5)|(r<1/1.5),axis=0)
d=pd.read_csv(P/'triple_representatives.csv');rows=[]
for a in d[d.period.astype(str)=='2026'].itertuples():
 mask=(O.market==a.market)&O.date.str.startswith('2026')
 for k in 'abc':mask&=Q[getattr(a,'feature_'+k)]==getattr(a,'bin_'+k)
 clean=mask&~flag[O.j.to_numpy()]
 rows.append(dict(market=a.market,feature_a=a.feature_a,feature_b=a.feature_b,feature_c=a.feature_c,bin_a=a.bin_a,bin_b=a.bin_b,bin_c=a.bin_c,n=int(mask.sum()),clean_n=int(clean.sum()),ret=a.ret,exclude_share_jump_ret=float(O.loc[clean,'ret'].mean())))
pd.DataFrame(rows).to_csv(P/'share_jump_sensitivity.csv',index=False)
errors=[];checks=0
for market in ['kospi','kosdaq']:
 full=pd.read_csv(P/f'triples_{market}.csv.gz');sample=full.sample(60,random_state=20261004)
 for row in sample.itertuples():
  pool=O.market.to_numpy()==market
  if str(row.period)!='all':pool&=O.date.str.startswith(str(row.period)).to_numpy()
  sel=pool.copy()
  for k in 'abc':
   q=Q[getattr(row,'feature_'+k)].to_numpy();pool&=q>0;sel&=q==getattr(row,'bin_'+k)
  sel&=pool;assert sel.sum()==row.n
  if sel.any():
   means=O[pool].groupby('date').ret.mean();ex=O.loc[sel,'ret'].astype(float)-O.loc[sel,'date'].map(means);err=abs(ex.mean()-row.excess);errors.append(err);assert err<2e-4
  checks+=1
curves=pd.read_csv(P/'portfolio_curves.csv.gz',index_col=0);pr=pd.read_csv(P/'portfolio_results.csv');dates=curves.index.astype(str).to_numpy(dtype=str);di={d:i for i,d in enumerate(z['dates'].astype(str))};ix=np.array([di[d] for d in dates]);out=[]
for key in curves:
 market,rule,reb,gate,fee=key.split('|');nv=curves[key].to_numpy(dtype=float);dr=nv/np.r_[1,nv[:-1]]-1;index=z[market][ix].astype(float);bdr=np.r_[0,index[1:]/index[:-1]-1]
 for per in ['all','2024','2025','2026']:
  ds=np.ones(len(nv),bool) if per=='all' else np.char.startswith(dates,per);vals=dr[ds]*100;diff=(dr-bdr)[ds]*100;bi=block_idx(len(vals),20);rl,rh=np.quantile(vals[bi].mean(axis=1),[.025,.975]);el,eh=np.quantile(diff[bi].mean(axis=1),[.025,.975])
  out.append(dict(market=market,rule=rule,rebalance=int(reb),above120_gate=bool(int(gate)),oneway_fee=float(fee),period=per,daily_mean=vals.mean(),daily_mean_lo=rl,daily_mean_hi=rh,daily_index_excess=diff.mean(),daily_excess_lo=el,daily_excess_hi=eh))
  ref=pr[(pr.market==market)&(pr.rule==rule)&(pr.rebalance==int(reb))&(pr.above120_gate==bool(int(gate)))&np.isclose(pr.oneway_fee,float(fee))&(pr.period.astype(str)==per)].iloc[0];assert abs(ref.daily_mean-vals.mean())<1e-5
pd.DataFrame(out).to_csv(P/'portfolio_daily_intervals.csv',index=False)
(P/'validation.json').write_text(json.dumps(dict(triple_random_checks=checks,max_triple_excess_rounding_error=max(errors),share_jump_tickers=int(flag.sum()),share_jump_note='Ex post sensitivity only; full-panel adjacent shares ratio >1.5 or <1/1.5, not a tradable filter',portfolio_mean_checks=len(out),bootstrap='20-day moving blocks, 2000 draws; exploratory, not multiplicity adjusted'),indent=2),encoding='utf-8')
print('VALIDATED',checks,len(out),max(errors),flush=True)
