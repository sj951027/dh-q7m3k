import sys
sys.dont_write_bytecode=True
import numpy as np,pandas as pd,json
from code_target20_20261003 import Study,ROOT,block_idx
P=ROOT/'research/target20_20261004';s=Study();s.features();s.choose()
td=pd.read_parquet(P/'exit_trades.parquet');first=int(td.t.min())+1;lastentry=int(td.t.max())+1
rows=[];checks=[]
for (rule,policy),g in td.groupby(['rule','policy']):
 lookup={(int(r.entry),int(r.j)):r for r in g.itertuples()}
 scenarios=[(i,.005,0) for i in range(20)]+[(0,.01,0)]
 if policy=='take20_stop10':scenarios += [(i,.005,5) for i in range(20)]
 for offset,fee,cooldown in scenarios:
  cash=1.;positions={};navs=[1.];ntrade=0;laststop={};immediate=0;within5=0
  for d in range(first,s.T):
   for j,(r,units,spent) in list(positions.items()):
    if r.closed and r.exit==d and not r.exit_close:
     cash+=units*r.exit_price-fee*spent;del positions[j]
     if r.reason=='stop':laststop[j]=d
   # Same declared fractional-share, open-value allocation convention.
   openvalue=cash
   for j,(r,units,spent) in positions.items():
    price=s.o[d,j]
    if not(np.isfinite(price) and price>0):price=s.ff[d-1,j]
    openvalue+=units*price-fee*spent
   if first+offset<=d<=lastentry:
    for j in s.picks[rule][d-1]:
     if j in positions or len(positions)>=10:continue
     if cooldown and j in laststop and d<=laststop[j]+cooldown:continue
     r=lookup.get((d,int(j)))
     if r is None:continue
     allocation=min(cash,openvalue/10)
     if allocation<1e-8:continue
     if j in laststop:
      immediate+=int(d==laststop[j]);within5+=int(d-laststop[j]<=5)
     cash-=allocation;positions[j]=(r,allocation/r.entry_price,allocation);ntrade+=1
   for j,(r,units,spent) in list(positions.items()):
    if r.closed and r.exit==d and r.exit_close:
     cash+=units*r.exit_price-fee*spent;del positions[j]
   navs.append(cash+sum(units*s.ff[d,j]-fee*spent for j,(r,units,spent) in positions.items()))
   assert cash>=-1e-9
  a=np.asarray(navs);mdd=np.min(a/np.maximum.accumulate(a)-1)*100
  lo=hi=np.nan
  if offset==0:
   daily=a[1:]/a[:-1]-1;ix=block_idx(len(daily),20);lo,hi=np.quantile(np.prod(1+daily[ix],axis=1)-1,[.025,.975])*100
  rows.append(dict(rule=rule,policy=policy,offset=offset,cost=fee,cooldown=cooldown,n_trades=ntrade,total=(a[-1]-1)*100,total_lo=lo,total_hi=hi,mdd=mdd,unclosed=len(positions),total_unclosed_zero=(cash-sum(fee*spent for r,units,spent in positions.values())-1)*100,immediate_after_stop=immediate,within5_after_stop=within5))
 print('ACCOUNT_CHECK',rule,policy,flush=True)
r=pd.DataFrame(rows);r.to_csv(P/'account_sensitivity.csv',index=False)
old=pd.read_csv(P/'account_summary.csv');pair=r[(r.offset==0)&(r.cost==.005)&(r.cooldown==0)].merge(old,on=['rule','policy'],suffixes=('_check','_original'))
assert np.allclose(pair.total_check,pair.total_original);assert np.allclose(pair.mdd_check,pair.mdd_original)
agg=r[r.cost==.005].groupby(['rule','policy','cooldown']).agg(n_starts=('total','count'),return_min=('total','min'),return_median=('total','median'),return_max=('total','max'),mdd_best=('mdd','max'),mdd_median=('mdd','median'),mdd_worst=('mdd','min')).reset_index()
agg.to_csv(P/'account_start_ranges.csv',index=False)
stop=td[td.reason=='stop'].groupby('rule').ret.agg(['count','mean','min',lambda a:a.quantile(.05)])
stop.to_csv(P/'stop_realized.csv')
z=s.idx;startclose=first-1;end=s.T-1
benchmark=np.mean(z[startclose:end+1]/z[startclose],axis=1)-.005
out=dict(account_crosscheck_rows=len(pair),max_total_error=float(np.max(np.abs(pair.total_check-pair.total_original))),index_mix_total=float((benchmark[-1]-1)*100),index_mix_mdd=float(np.min(benchmark/np.maximum.accumulate(np.r_[1,benchmark])[1:]-1)*100),benchmark_start=str(s.d[startclose]),benchmark_end=str(s.d[end]))
(P/'account_verification.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print('DONE',out)
