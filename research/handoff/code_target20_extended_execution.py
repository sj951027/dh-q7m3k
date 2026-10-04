"""Offline entry/horizon/regime sensitivity. Same mature signal pool across settings."""
import sys,json,warnings
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np,pandas as pd
from code_target20_20261003 import rolling,block_idx
warnings.filterwarnings('ignore',category=RuntimeWarning)
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'research/target20_extended_20261004'
O=pd.read_parquet(P/'outcomes.parquet');Q=pd.read_parquet(P/'feature_quintiles.parquet');A=pd.read_parquet(P/'absolute_values.parquet')
z=np.load(ROOT/'research/fullscan_20260903/panel.npz',allow_pickle=True);dates=z['dates'].astype(str);T=len(dates)
keep=O.t.to_numpy()+62<T;O=O[keep].reset_index(drop=True);Q=Q[keep].reset_index(drop=True);A=A[keep].reset_index(drop=True)
t=O.t.to_numpy(dtype=int);j=O.j.to_numpy(dtype=int);n=len(O);mkt=O.market.to_numpy();mi=np.where(mkt=='kospi',0,1)
o=z['open'].astype(float);c=z['close'].astype(float);lo=z['low'].astype(float);hi=z['high'].astype(float);v=z['vol'].astype(float);ff=pd.DataFrame(c).ffill().to_numpy();idx=np.column_stack([z['kospi'],z['kosdaq']]);ma=rolling(idx,120);up=idx[t,mi]>ma[t,mi]
D=np.unique(t);day=np.searchsorted(D,t);nd=len(D);years=np.array([dates[x][:4] for x in D]);rs=A.rsi14.to_numpy()
rules={'all':np.ones(n,bool),'rsi_le20':rs<=20,'rsi_20_30':(rs>20)&(rs<=30),'rsi_gt80':rs>80,'size_q5':Q.market_cap.to_numpy()==5,'size_q5_high_q5':(Q.market_cap.to_numpy()==5)&(Q.nh252.to_numpy()==5),'roe_q5_growth_q5':(Q.annual_roe.to_numpy()==5)&(Q.op_yoy.to_numpy()==5),'lowvol_q1_high_q5':(Q.lv20.to_numpy()==1)&(Q.nh252.to_numpy()==5),'amount_q5_rsi_le30':(Q.log_amount.to_numpy()==5)&(rs<=30),'per_0_5':(A.annual_pe_approx.to_numpy()>0)&(A.annual_pe_approx.to_numpy()<=5),'growth_q5':Q.op_yoy.to_numpy()==5,'low_impact_q1_rsi_gt80':(Q.amihud60.to_numpy()==1)&(rs>80)}
amount=rolling(c*v,20,15)[t,j]
top={}
for name,mask in rules.items():
 picked=np.zeros(n,bool)
 for market in ['kospi','kosdaq']:
  ii=np.where(mask&(mkt==market))[0];order=np.lexsort((j[ii],-amount[ii],t[ii]));ii=ii[order];ds=day[ii];starts=np.r_[0,np.where(ds[1:]!=ds[:-1])[0]+1];rank=np.arange(len(ii))-np.repeat(starts,np.diff(np.r_[starts,len(ii)]));picked[ii[rank<10]]=True
 top[name]=picked
rows=[];tops=[];verify=[]
scopes={'all':np.ones(n,bool),**{y:O.date.str.startswith(y).to_numpy() for y in ['2024','2025','2026']}}
def aggregate(mask,ret,hit,first,mae,joint,ex,filled,entry,horizon,rule,regime,period,selected=False):
 attempted=int(mask.sum());s=mask&filled;nfilled=int(s.sum());r=dict(entry=entry,h=horizon,rule=rule,market=market,regime=regime,period=period,attempts=attempted,n=nfilled,fill_rate=nfilled/attempted*100 if attempted else np.nan,n_dates=int(np.unique(day[s]).size))
 if not nfilled:return r
 for name,values in [('ret',ret),('hit',hit),('first',first),('mae',mae),('joint',joint),('aligned_index_excess',ex)]:r[name]=float(np.mean(values[s]))
 r['fee1_ret']=r['ret']-.5;r['attempt_ret_zero_cash']=float(np.sum(ret[s])/attempted)
 counts=np.bincount(day[s],minlength=nd);sums=np.bincount(day[s],weights=ret[s],minlength=nd);r['equal_signal_day_ret']=float(np.mean(sums[counts>0]/counts[counts>0]))
 if horizon==20 and regime=='all' and r['n_dates']>=40:
  ds=np.arange(nd) if period=='all' else np.where(years==period)[0];bix=block_idx(len(ds),20);den=counts[ds][bix].sum(axis=1);boots=np.divide(sums[ds][bix].sum(axis=1),den,out=np.full(len(bix),np.nan),where=den>0);r['ret_lo'],r['ret_hi']=np.nanquantile(boots,[.025,.975])
 return r
for entry in ['next_open','next_close','third_open','limit_minus2','limit_minus5']:
 e=t+1;price=o[e,j].copy();valid=np.isfinite(price)&(price>0)&(v[e,j]>0);locked=(hi[e,j]==lo[e,j])&(abs(price/c[t,j]-1)>=.295);valid&=~locked
 if entry=='next_close':price=c[e,j].copy();valid&=np.isfinite(price)&(price>0)
 elif entry=='third_open':
  e=t+3;price=o[e,j].copy();valid=np.isfinite(price)&(price>0)&(v[e,j]>0)&~((hi[e,j]==lo[e,j])&(abs(price/c[e-1,j]-1)>=.295))
 elif entry.startswith('limit'):
  limit=c[t,j]*(.98 if entry=='limit_minus2' else .95);valid=np.zeros(n,bool);price=np.full(n,np.nan);e=t+1
  for delay in [1,2,3]:
   et=t+delay;op=o[et,j];locked=(hi[et,j]==lo[et,j])&(abs(op/c[et-1,j]-1)>=.295)
   touch=(lo[et,j]<=limit)&np.isfinite(op)&(op>0)&(v[et,j]>0)&~locked;take=~valid&touch;e[take]=et[take];price[take]=np.minimum(op[take],limit[take]);valid[take]=True
 price[~valid]=np.nan
 start=(e+1) if entry=='next_close' else e
 minret=np.full(n,np.inf);positive=np.zeros(n);first=np.full(n,np.nan)
 for h in range(1,61):
  end=start+h-1;path=ff[end,j]/price-1;minret=np.minimum(minret,path);positive+=(path>0)
  if h==1:first=(path>0)*100.
  if h not in [5,10,15,20,30,40,60]:continue
  ret=(path-.005)*100;hit=(ret>=20)*100.;joint=((ret>=20)&(minret>=-.1)&(positive/h>=.8)&(first>0))*100.;mae=minret*100
  # Both legs start at entry-day close, eliminating unavailable index-open mismatch.
  index_return=idx[end,mi]/idx[e,mi]-1;ex=((ff[end,j]/ff[e,j]-1)-index_return-.005)*100
  filled=valid&np.isfinite(ret)&np.isfinite(ex)
  regimes={'all':np.ones(n,bool),'above120':up,'below120':~up,'future_index_up':index_return>0,'future_index_down':index_return<=0}
  for market in ['kospi','kosdaq']:
   mm=mkt==market
   for rule,mask in rules.items():
    for regime,reg in regimes.items():
     for period in (['all','2024','2025','2026'] if regime=='all' else ['all']):
      scope=scopes[period]
      rows.append(aggregate(mm&mask&reg&scope,ret,hit,first,mae,joint,ex,filled,entry,h,rule,regime,period))
    if h==20 and entry in ['next_open','next_close']:
     for period in ['all','2024','2025','2026']:
      scope=scopes[period]
      tops.append(aggregate(mm&top[rule]&scope,ret,hit,first,mae,joint,ex,filled,entry,h,rule,'all',period,True))
  if h==20:
   for k in np.where(filled)[0][::max(1,int(filled.sum()/20))][:20]:
    raw=(float(ff[int(end[k]),int(j[k])])/float(price[k])-1-.005)*100;assert abs(raw-ret[k])<1e-9;verify.append(abs(raw-ret[k]))
  print('EXEC',entry,h,flush=True)
pd.DataFrame(rows).to_csv(P/'entry_horizon_regime.csv',index=False)
pd.DataFrame(tops).to_csv(P/'top10_liquidity.csv',index=False)
(P/'execution_meta.json').write_text(json.dumps(dict(rows=len(rows),top10_rows=len(tops),signals=n,dates=nd,first=str(O.date.min()),last=str(O.date.max()),price_checks=len(verify),max_error=max(verify),note='Common original20-day-fillable pool; end t+62<T; close entry skips entry close, requires t+61; limits wait max3; no intraday queue evidence. Index excess aligns both returns entry close to exit close.'),indent=2),encoding='utf-8')
print('DONE execution',len(rows),flush=True)
