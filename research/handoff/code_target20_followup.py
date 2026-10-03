"""Declared follow-up experiment; all writes confined to research/target20_20261004."""
import sys
sys.dont_write_bytecode=True
import numpy as np,pandas as pd,json
from code_target20_20261003 import Study,ROOT,interval,block_idx
OUT=ROOT/'research/target20_20261004';OUT.mkdir(exist_ok=True)
RULES=['control_amount','highbeta_high','control_price4']
POLICIES=['hold20','take20','take20_stop10','trail10_after20']
s=Study();s.features();s.choose();start=np.searchsorted(s.d,'20250101');end=s.T-27

def buyable(d,j):
 p=s.o[d,j]
 return bool(np.isfinite(p) and p>0 and s.v[d,j]>0 and not(abs(s.h[d,j]-s.l[d,j])<1e-8 and abs(p/s.c[d-1,j]-1)>=.295))

def sellable(d,j,atclose=False):
 p=s.c[d,j] if atclose else s.o[d,j]
 return bool(np.isfinite(p) and p>0 and s.v[d,j]>0 and not(abs(s.h[d,j]-s.l[d,j])<1e-8 and p/s.ff[d-1,j]-1<=-.295))

def trade(t,j,policy='hold20',delay=0):
 entry=t+1+delay
 if not buyable(entry,j):return None
 price=s.o[entry,j];last=entry+19;planned=last;atclose=True;reason='expiry';armed=False;peak=price;seen=False
 for d in range(entry,last):
  net=s.ff[d,j]/price-1-.005;held=d-entry+1;peak=max(peak,s.ff[d,j])
  target=held>=5 and net>=.2;seen=seen or target
  if policy=='take20_stop10' and net<=-.10:planned=d+1;atclose=False;reason='stop';break
  if policy in ('take20','take20_stop10') and target:planned=d+1;atclose=False;reason='target';break
  if policy=='trail10_after20':
   armed=armed or target
   if armed and s.ff[d,j]/peak-1<=-.1:planned=d+1;atclose=False;reason='trail';break
 exitday=planned;closed=sellable(exitday,j,atclose)
 if not closed:
  atclose=False
  for d in range(planned+1,min(planned+6,s.T)):
   exitday=d
   if sellable(d,j):closed=True;break
 outprice=(s.c[exitday,j] if atclose else s.o[exitday,j]) if closed else s.ff[exitday,j]
 path=np.r_[price,s.ff[entry:exitday,j],outprice];peakpath=np.maximum.accumulate(path)
 ret=outprice/price-1-.005
 return dict(t=t,j=j,date=s.d[t],ticker=s.tick[j],entry=entry,exit=exitday,entry_price=price,exit_price=outprice,exit_close=atclose,closed=closed,reason=reason,lag=exitday-planned,days=exitday-entry+1,ret=ret*100,hit=bool(ret>=.2),target_seen=seen,mdd=float(np.min(path/peakpath-1)*100),mae=float(np.min(path/price-1)*100))

rows=[];trades=[];lookup={}
for rule in RULES:
 for policy in POLICIES:
  for t in range(start,end+1):
   bag=[]
   for j in s.picks[rule][t]:
    r=trade(t,j,policy)
    if r:
     r.update(rule=rule,policy=policy);bag.append(r);trades.append(r);lookup[(rule,policy,t,j)]=r
   rows.append(dict(rule=rule,policy=policy,date=s.d[t],n=len(bag),ret=sum(r['ret'] for r in bag)/10,hit=sum(r['hit'] for r in bag),mean_mdd=np.mean([r['mdd'] for r in bag]),unclosed=sum(not r['closed'] for r in bag)))
 print('EXIT_DONE',rule,flush=True)
td=pd.DataFrame(trades);dd=pd.DataFrame(rows);td.to_parquet(OUT/'exit_trades.parquet',index=False);dd.to_csv(OUT/'exit_daily.csv',index=False)
summary=[]
for (rule,policy),g in dd.groupby(['rule','policy']):
 for year in ['all','2025','2026']:
  q=g if year=='all' else g[g.date.str.startswith(year)];tt=td[(td.rule==rule)&(td.policy==policy)&td.date.isin(q.date)]
  lo,hi=interval(q.ret,20);r=dict(rule=rule,policy=policy,period=year,n_dates=len(q),n=len(tt),ret=q.ret.mean(),lo=lo,hi=hi,hit=tt.hit.mean(),mdd=tt.mdd.mean(),avg_days=tt.days.mean(),unclosed=int((~tt.closed).sum()),lagged=int((tt.lag>0).sum()),target_count=int((tt.reason=='target').sum()),target_below20=int(((tt.reason=='target')&~tt.hit).sum()))
  base=g if policy=='hold20' else dd[(dd.rule==rule)&(dd.policy=='hold20')]
  diff=q.set_index('date').ret-base.set_index('date').ret;diff=diff.dropna();r['diff']=diff.mean();r['diff_lo'],r['diff_hi']=interval(diff,20)
  r['unclosed_zero']=float(np.where(tt.closed,tt.ret,-100.5).sum()/10/len(q));summary.append(r)
pd.DataFrame(summary).to_csv(OUT/'exit_summary.csv',index=False)
# Delayed entry: signals fixed on t, no reranking after observing day1.
delayed=[]
for rule in RULES:
 for mode in ['day1_open','day2_open','day2_if_day1_up']:
  for t in range(start,end+1):
   bag=[]
   for j in s.picks[rule][t]:
    if mode=='day2_if_day1_up' and not(s.v[t+1,j]>0 and s.c[t+1,j]>s.o[t+1,j]>0):continue
    r=trade(t,j,delay=int(mode!='day1_open'))
    if r:bag.append(r)
   delayed.append(dict(rule=rule,mode=mode,date=s.d[t],n=len(bag),ret=sum(r['ret'] for r in bag)/10,hit=sum(r['hit'] for r in bag)))
de=pd.DataFrame(delayed);de.to_csv(OUT/'entry_daily.csv',index=False);sums=[]
for (rule,mode),g in de.groupby(['rule','mode']):
 lo,hi=interval(g.ret,20);sums.append(dict(rule=rule,mode=mode,n_dates=len(g),n=int(g.n.sum()),ret=g.ret.mean(),lo=lo,hi=hi,hit=g.hit.sum()/g.n.sum(),avg_slots=g.n.mean()))
pd.DataFrame(sums).to_csv(OUT/'entry_summary.csv',index=False)
# Fixed capital, no repeated purchase while held. Future exit schedule is only acted
# on at its observed date. Portfolio admission depends on current cash/ranks only.
accounts=[];accountstats=[]
for rule in RULES:
 for policy in POLICIES:
  cash=1.;pos=[];curve=[];ntrade=0;skippedheld=0;skippedfull=0
  for d in range(start+1,s.T):
   for q in list(pos):
    r=q['r']
    if r['exit']==d and not r['exit_close'] and r['closed']:
     cash+=q['units']*r['exit_price']-.005*q['invested'];pos.remove(q)
   navopen=cash+sum(q['units']*(s.o[d,q['r']['j']] if np.isfinite(s.o[d,q['r']['j']]) and s.o[d,q['r']['j']]>0 else s.ff[d-1,q['r']['j']])-.005*q['invested'] for q in pos)
   t=d-1
   if t<=end:
    for j in s.picks[rule][t]:
     if any(q['r']['j']==j for q in pos):skippedheld+=1;continue
     if len(pos)>=10 or cash<1e-8:skippedfull+=1;continue
     r=lookup.get((rule,policy,t,j))
     if r is None:continue
     allocation=min(cash,max(navopen,0)/10)
     if allocation<1e-8:continue
     cash-=allocation;pos.append(dict(r=r,units=allocation/r['entry_price'],invested=allocation));ntrade+=1
   for q in list(pos):
    r=q['r']
    if r['exit']==d and r['exit_close'] and r['closed']:
     cash+=q['units']*r['exit_price']-.005*q['invested'];pos.remove(q)
   nav=cash+sum(q['units']*s.ff[d,q['r']['j']]-.005*q['invested'] for q in pos)
   curve.append(dict(rule=rule,policy=policy,date=s.d[d],nav=nav,cash=cash,n_held=len(pos)))
  a=pd.DataFrame(curve);values=np.r_[1,a.nav];rets=values[1:]/values[:-1]-1
  ix=block_idx(len(rets),20);totals=np.prod(1+rets[ix],axis=1)-1
  lo,hi=np.quantile(totals,[.025,.975])*100
  accountstats.append(dict(rule=rule,policy=policy,n_days=len(a),n_trades=ntrade,total=(values[-1]-1)*100,total_lo=lo,total_hi=hi,mdd=np.min(values/np.maximum.accumulate(values)-1)*100,avg_held=a.n_held.mean(),avg_cash=np.mean(a.cash/a.nav),skipped_held=skippedheld,skipped_full=skippedfull,unclosed=len(pos)))
  accounts.extend(curve)
pd.DataFrame(accounts).to_csv(OUT/'account_daily.csv',index=False);pd.DataFrame(accountstats).to_csv(OUT/'account_summary.csv',index=False)
# Assertions target event ordering and independent reproduction of fixed hold returns.
assert (td.exit>=td.entry).all();assert (td[td.reason!='expiry'].exit>td[td.reason!='expiry'].entry).all()
base=pd.read_parquet(ROOT/'research/target20_20261003/trades20.parquet');check=td[(td.policy=='hold20')&td.closed&(td.lag==0)].merge(base,on=['rule','date','ticker'],suffixes=('_new','_old'))
assert np.allclose(check.ret_new,check.ret_old,equal_nan=True)
assert pd.DataFrame(accounts).cash.min()>-1e-9
meta=dict(start=str(s.d[start]),end=str(s.d[end]),dates=int(end-start+1),hold_replication_rows=len(check),max_error=float(np.max(np.abs(check.ret_new-check.ret_old))),no_negative_cash=True)
(OUT/'verification.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');print('DONE',json.dumps(meta),flush=True)
