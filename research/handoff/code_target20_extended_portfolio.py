"""Finite capital, 10 equal slots, previous-day signals, close execution; research only."""
import sys,json,sqlite3,warnings
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np,pandas as pd
from code_target20_20261003 import rolling
warnings.filterwarnings('ignore',category=RuntimeWarning)
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'research/target20_extended_20261004'
O=pd.read_parquet(P/'outcomes.parquet');Q=pd.read_parquet(P/'feature_quintiles.parquet');A=pd.read_parquet(P/'absolute_values.parquet');z=np.load(ROOT/'research/fullscan_20260903/panel.npz',allow_pickle=True)
dates=z['dates'].astype(str);ticks=z['tick'].astype(str);c=z['close'].astype(float);o=z['open'];h=z['high'];l=z['low'];v=z['vol'];ff=pd.DataFrame(c).ffill().to_numpy();T,N=c.shape;idx=np.column_stack([z['kospi'],z['kosdaq']]);ma=rolling(idx,120);amount=rolling(c*v,20,15)
t=O.t.to_numpy();j=O.j.to_numpy();m=O.market.to_numpy();rs=A.rsi14.to_numpy();start=int(t.min())+1;end=int(t.max())+1
rules={'all':np.ones(len(O),bool),'rsi_le20':rs<=20,'rsi_20_30':(rs>20)&(rs<=30),'rsi_gt80':rs>80,'size_q5':Q.market_cap.to_numpy()==5,'size_q5_high_q5':(Q.market_cap.to_numpy()==5)&(Q.nh252.to_numpy()==5),'roe_q5_growth_q5':(Q.annual_roe.to_numpy()==5)&(Q.op_yoy.to_numpy()==5),'lowvol_q1_high_q5':(Q.lv20.to_numpy()==1)&(Q.nh252.to_numpy()==5),'amount_q5_rsi_le30':(Q.log_amount.to_numpy()==5)&(rs<=30),'per_0_5':(A.annual_pe_approx.to_numpy()>0)&(A.annual_pe_approx.to_numpy()<=5),'growth_q5':Q.op_yoy.to_numpy()==5,'low_impact_q1_rsi_gt80':(Q.amihud60.to_numpy()==1)&(rs>80)}
rows=[];curves={};checks=[]
for market in ['kospi','kosdaq']:
 mi=0 if market=='kospi' else 1
 for name,mask in rules.items():
  choices={}
  for ti in range(start-1,end):
   jj=j[(t==ti)&(m==market)&mask];choices[ti]=jj[np.argsort(-amount[ti,jj],kind='stable')[:10]]
  for every in [5,10,20]:
   for gate in [False,True]:
    for fee in [.001,.0025,.005]:
     cash=1.;units=np.zeros(N);nav=[];exposure=[];turn=0.;blocked=0
     for ti in range(start,end+1):
      value=float(np.nansum(units*ff[ti]));pre=cash+value
      if (ti-start)%every==0:
       target=choices[ti-1] if not gate or idx[ti-1,mi]>ma[ti-1,mi] else np.array([],int)
       trade=np.isfinite(c[ti])&(c[ti]>0)&(v[ti]>0)&~((h[ti]==l[ti])&(abs(c[ti]/ff[ti-1]-1)>=.295))
       # Liquidate tradable slots at scheduled rebalance. Blocked positions remain marked.
       held=np.where(units>0)[0];blocked+=int((~trade[held]).sum());sell=held[trade[held]];proceeds=float((units[sell]*c[ti,sell]).sum());cash+=proceeds*(1-fee);units[sell]=0;turn+=proceeds/pre
       for k in target:
        if units[k]>0 or not trade[k]:continue
        spend=min(pre/10,cash/(1+fee));units[k]=spend/c[ti,k];cash-=spend*(1+fee);turn+=spend/pre
      post=cash+float(np.nansum(units*ff[ti]));assert cash>=-1e-10 and post>0
      nav.append(post);exposure.append((post-cash)/post)
     nv=np.array(nav);dr=nv/np.r_[1,nv[:-1]]-1;benchmark=idx[start:end+1,mi]/idx[start,mi];bdr=np.r_[0,benchmark[1:]/benchmark[:-1]-1];peak=np.maximum.accumulate(np.r_[1,nv])[1:]
     key=f'{market}|{name}|{every}|{int(gate)}|{fee}';curves[key]=nv.astype('float32')
     for period in ['all','2024','2025','2026']:
      ds=np.ones(len(nv),bool) if period=='all' else np.array([x.startswith(period) for x in dates[start:end+1]])
      if not ds.any():continue
      ix=np.where(ds)[0];base=1 if ix[0]==0 else nv[ix[0]-1];eq=nv[ix]/base;pk=np.maximum.accumulate(np.r_[1,eq])[1:];ret=(eq[-1]-1)*100;br=(np.prod(1+bdr[ix])-1)*100
      down=ix[bdr[ix]<0];up=ix[bdr[ix]>0]
      rows.append(dict(market=market,rule=name,rebalance=every,above120_gate=gate,oneway_fee=fee,period=period,n_days=len(ix),total_return=ret,index_return=br,index_excess=ret-br,max_drawdown=float(np.min(eq/pk-1)*100),daily_mean=float(dr[ix].mean()*100),daily_std=float(dr[ix].std()*100),avg_exposure=float(np.mean(np.array(exposure)[ix])*100),down_day_excess=float(np.mean(dr[down]-bdr[down])*100),up_day_excess=float(np.mean(dr[up]-bdr[up])*100),blocked_sells=blocked,total_turnover=turn))
 print('PORTFOLIO_DONE',market,flush=True)
pd.DataFrame(rows).to_csv(P/'portfolio_results.csv',index=False)
pd.DataFrame(curves,index=dates[start:end+1]).to_csv(P/'portfolio_curves.csv.gz',index_label='date',compression='gzip')
(P/'portfolio_meta.json').write_text(json.dumps(dict(cases=len(curves),rows=len(rows),first=str(dates[start]),last=str(dates[end]),signals='Prior condition-study eligible pool; no new outcomes or universe reconstruction',execution='next close; cash slots for missing signals; no borrowed capital; blocked sells carried; no dividends; fee charged on traded notional each way'),indent=2),encoding='utf-8')
# Additional contemporaneous sector coverage: labels from large-universe records only.
con=sqlite3.connect('file:'+str(ROOT/'history.db')+'?mode=ro',uri=True)
se=pd.read_sql_query('SELECT run_id,run_timestamp,ticker,sector FROM large_universe',con);con.close();tm={x:i for i,x in enumerate(dates)};jm={x:i for i,x in enumerate(ticks)}
se['t']=se.run_id.astype(str).map(tm);se['j']=se.ticker.astype(str).str.zfill(6).map(jm);se=se[se.t.notna()&se.j.notna()&(se.t<T-1)].copy();stamp=pd.to_datetime(se.run_timestamp,format='%Y%m%d_%H%M',errors='coerce').dt.tz_localize('Asia/Seoul');cut=pd.to_datetime([dates[int(x)+1]+' 09:00' for x in se.t]).tz_localize('Asia/Seoul');se=se[stamp.notna()&(stamp.to_numpy()<=cut.to_numpy())];se=se[se.sector.notna()&~se.sector.astype(str).isin(['','nan','Unknown','기타','미분류'])].drop_duplicates(['t','j'],keep='last')
joined=O.merge(se[['t','j','sector']],on=['t','j'],how='inner');joined['year']=joined.date.str[:4]
if len(joined):
 joined['excess']=joined.ret-joined.groupby(['date','market']).ret.transform('mean');joined.groupby(['market','sector','year']).agg(n=('ret','size'),n_dates=('date','nunique'),ret=('ret','mean'),hit=('hit','mean'),mae=('mae','mean'),excess=('excess','mean')).reset_index().to_csv(P/'sector_large_metadata.csv',index=False,encoding='utf-8-sig')
(P/'sector_large_meta.json').write_text(json.dumps(dict(rows=len(joined),dates=int(joined.date.nunique()),groups=int(joined.sector.nunique()),first=str(joined.date.min()),last=str(joined.date.max()),note='Metadata from large_universe only; large-model scores and verdicts not used or compared.'),indent=2),encoding='utf-8')
print('DONE portfolio and sector metadata',flush=True)
