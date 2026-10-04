"""Independent sparse-holdings implementation; checks every rebalance start offset."""
import sys,json,warnings
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np,pandas as pd
from code_target20_20261003 import rolling
warnings.filterwarnings('ignore',category=RuntimeWarning)
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'research/target20_extended_20261004'
O=pd.read_parquet(P/'outcomes.parquet');Q=pd.read_parquet(P/'feature_quintiles.parquet');A=pd.read_parquet(P/'absolute_values.parquet');z=np.load(ROOT/'research/fullscan_20260903/panel.npz',allow_pickle=True)
c=z['close'].astype(float);ff=pd.DataFrame(c).ffill().to_numpy();v=z['vol'];hi=z['high'];lo=z['low'];dates=z['dates'].astype(str);idx=np.column_stack([z['kospi'],z['kosdaq']]);ma=rolling(idx,120);amount=rolling(c*v,20,15)
t=O.t.to_numpy();j=O.j.to_numpy();m=O.market.to_numpy();rs=A.rsi14.to_numpy();start=int(t.min())+1;end=int(t.max())+1
rules={'all':np.ones(len(O),bool),'rsi_le20':rs<=20,'rsi_20_30':(rs>20)&(rs<=30),'rsi_gt80':rs>80,'size_q5':Q.market_cap.to_numpy()==5,'size_q5_high_q5':(Q.market_cap.to_numpy()==5)&(Q.nh252.to_numpy()==5),'roe_q5_growth_q5':(Q.annual_roe.to_numpy()==5)&(Q.op_yoy.to_numpy()==5),'lowvol_q1_high_q5':(Q.lv20.to_numpy()==1)&(Q.nh252.to_numpy()==5),'amount_q5_rsi_le30':(Q.log_amount.to_numpy()==5)&(rs<=30),'per_0_5':(A.annual_pe_approx.to_numpy()>0)&(A.annual_pe_approx.to_numpy()<=5),'growth_q5':Q.op_yoy.to_numpy()==5,'low_impact_q1_rsi_gt80':(Q.amihud60.to_numpy()==1)&(rs>80)}
trade=np.isfinite(c)&(c>0)&(v>0);trade[1:]&=~((hi[1:]==lo[1:])&(abs(c[1:]/ff[:-1]-1)>=.295));prev=pd.read_csv(P/'portfolio_results.csv');rows=[];errs=[]
for market in ['kospi','kosdaq']:
 mi=0 if market=='kospi' else 1
 for name,mask in rules.items():
  choices={}
  for ti in range(start-1,end):
   jj=j[(t==ti)&(m==market)&mask];choices[ti]=jj[np.argsort(-amount[ti,jj],kind='stable')[:10]]
  for every in [5,10,20]:
   for gate in [False,True]:
    for phase in range(every):
     cash=1.;held={};nav=[]
     for ti in range(start,end+1):
      pre=cash+sum(units*ff[ti,k] for k,units in held.items())
      if (ti-start)%every==phase:
       target=choices[ti-1] if not gate or idx[ti-1,mi]>ma[ti-1,mi] else []
       for k in list(held):
        if trade[ti,k]:cash+=held.pop(k)*c[ti,k]*(1-.0025)
       for k in target:
        if k in held or not trade[ti,k]:continue
        spend=min(pre/10,cash/1.0025);held[k]=spend/c[ti,k];cash-=spend*1.0025
      assert cash>=-1e-10
      nav.append(cash+sum(units*ff[ti,k] for k,units in held.items()))
     nv=np.array(nav);pk=np.maximum.accumulate(np.r_[1,nv])[1:];total=(nv[-1]-1)*100
     if phase==0:
      ref=prev[(prev.market==market)&(prev.rule==name)&(prev.rebalance==every)&(prev.above120_gate==gate)&(prev.oneway_fee==.0025)&(prev.period.astype(str)=='all')].iloc[0];err=abs(total-ref.total_return);assert err<1e-7;errs.append(err)
     r=dict(market=market,rule=name,rebalance=every,above120_gate=gate,phase=phase,total_return=total,max_drawdown=float(np.min(nv/pk-1)*100))
     for y in ['2024','2025','2026']:
      ii=np.where(np.char.startswith(dates[start:end+1],y))[0];r['ret'+y]=(nv[ii[-1]]/(1 if ii[0]==0 else nv[ii[0]-1])-1)*100
     rows.append(r)
  print('PHASE',market,name,flush=True)
d=pd.DataFrame(rows);d.to_csv(P/'rebalance_phases.csv',index=False)
d.groupby(['market','rule','rebalance','above120_gate']).agg(n_phases=('phase','size'),min_return=('total_return','min'),median_return=('total_return','median'),max_return=('total_return','max'),worst_drawdown=('max_drawdown','min'),positive2026=('ret2026',lambda x:int((x>0).sum()))).reset_index().to_csv(P/'phase_summary.csv',index=False)
(P/'phase_validation.json').write_text(json.dumps(dict(cases=len(rows),independent_phase0_checks=len(errs),max_return_error=max(errs)),indent=2),encoding='utf-8')
print('DONE phases',len(rows),flush=True)
