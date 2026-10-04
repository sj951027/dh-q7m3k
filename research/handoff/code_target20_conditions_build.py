"""Broad point-in-time feature inventory. Research-only writes; DB connections read-only."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json,sqlite3,hashlib,warnings
import numpy as np,pandas as pd
from code_target20_20261003 import Study,ROOT,rolling,lag,returns
warnings.filterwarnings('ignore',category=RuntimeWarning)
P=ROOT/'research/target20_conditions_20261004';P.mkdir(exist_ok=True)
s=Study();s.features();F={k:v.astype('float32') for k,v in s.feats.items()};meta={k:dict(family='price',source='panel',timing='signal close') for k in F}
def add(k,a,family='price',source='panel',timing='signal close'):
 F[k]=np.asarray(a,dtype='float32');meta[k]=dict(family=family,source=source,timing=timing)
c,o,h,l,v,r=s.c,s.o,s.h,s.l,s.v,s.r;sh=s.z['shares'];cap=c*sh;delta=c-lag(c)
for n in (6,14,28):
 gain=pd.DataFrame(np.maximum(delta,0)).ewm(alpha=1/n,adjust=False,min_periods=n).mean().to_numpy();loss=pd.DataFrame(np.maximum(-delta,0)).ewm(alpha=1/n,adjust=False,min_periods=n).mean().to_numpy()
 add('rsi'+str(n),100*gain/(gain+loss))
for n in (5,20,60,120,200):add('ma_gap'+str(n),c/rolling(c,n,max(4,int(n*.8)))-1)
for n in (1,10,120,252):add('return'+str(n),returns(c,n))
for n in (20,60):
 add('efficiency'+str(n),abs(c-lag(c,n))/rolling(abs(delta),n,n,'sum'))
 add('amihud'+str(n),rolling(abs(r)/np.where(s.amt>0,s.amt,np.nan),n,max(10,n//2))*1e9)
 add('turnover'+str(n),rolling(v/np.where(sh>0,sh,np.nan),n,max(10,n//2)))
 add('vwap_gap'+str(n),c/(rolling(c*v,n,max(10,n//2),'sum')/rolling(v,n,max(10,n//2),'sum'))-1)
add('market_cap',cap,'size','price * panel shares (historical shares approximate)');add('price',c,'size')
add('low252_distance',c/rolling(c,252,120,'min')-1);add('low20_distance',c/rolling(c,20,15,'min')-1)
add('high20_distance',c/rolling(c,20,15,'max')-1)
tr=np.fmax(h-l,np.fmax(abs(h-lag(c)),abs(l-lag(c))));atr=rolling(tr,14,10)
add('atr14_pct',atr/c);add('range_pct',(h-l)/c);add('body_pct',(c-o)/o);add('gap',o/lag(c)-1)
add('bollinger_position',(c-rolling(c,20,15))/(2*rolling(c,20,15,'std')));add('bollinger_width',4*rolling(c,20,15,'std')/rolling(c,20,15))
add('stochastic14',100*(c-rolling(l,14,10,'min'))/(rolling(h,14,10,'max')-rolling(l,14,10,'min')))
add('macd_pct',(pd.DataFrame(c).ewm(span=12,adjust=False).mean()-pd.DataFrame(c).ewm(span=26,adjust=False).mean()).to_numpy()/c)
add('amount5_20',rolling(s.amt,5,4)/rolling(s.amt,20,15));add('volume20_60',rolling(v,20,15)/rolling(v,60,40))
add('upside_vol60',np.sqrt(rolling(np.maximum(r,0)**2,60,40)));add('skew60',pd.DataFrame(r).rolling(60,min_periods=40).skew().to_numpy())
add('obv_pressure20',rolling(np.sign(r)*v,20,15)/rolling(v,20,15));add('limitups60',rolling((r>=.295).astype(float),60,40,'sum'))
add('max_return20',rolling(r,20,15,'max'));add('min_return20',rolling(r,20,15,'min'));add('gap_mean20',rolling(o/lag(c)-1,20,15))
for n in (20,60,120):
 add('index_ma_gap'+str(n),(s.idx/rolling(s.idx,n)-1)[:,s.mi],'regime')
 add('index_return'+str(n),returns(s.idx,n)[:,s.mi],'regime')
add('index_vol20',rolling(returns(s.idx,1),20,15,'std')[:,s.mi],'regime')
fx=s.z['usdkrw'];add('fx_return20',np.broadcast_to(returns(fx,20)[:,None],c.shape),'regime')
ti={k:i for i,k in enumerate(s.tick)};audit=[]
def ro(path):return sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
def matrix(df,col,datecol='date',tickcol='ticker'):
 a=np.full(c.shape,np.nan,dtype='float32');d=df[datecol].astype(str).map(s.di);j=df[tickcol].astype(str).str.zfill(6).map(ti);m=d.notna()&j.notna()
 a[d[m].astype(int),j[m].astype(int)]=pd.to_numeric(df.loc[m,col],errors='coerce');return a
con=ro(ROOT.parent/'dh-q7m3k-data/ohlcv.db')
val=pd.read_sql_query('SELECT * FROM valuation_daily',con)
for col in ['per','pbr','div','eps','bps']:add('daily_'+col,lag(matrix(val,col)),'valuation','valuation_daily','previous trading day, no carry')
flow=pd.read_sql_query('SELECT * FROM daily_flows',con)
for col in ['foreign','inst','person','pension','trust','secfirm','prveq','insu','bank']:
 a=matrix(flow,col+'_net_val')
 for n in [5,20]:add(col+'_flow'+str(n),lag(rolling(a,n,n,'sum')/rolling(s.amt,20,15)),'flow','daily_flows','lag1, complete window, amount20 normalized')
add('foreign_inst_flow5',F['foreign_flow5']+F['inst_flow5'],'flow','daily_flows','lag1')
short=pd.read_sql_query('SELECT * FROM short_flows',con)
for col in ['short_vol_ratio','credit_bal_rate','loan_chg']:
 a=matrix(short,col)
 add(col,lag(a),'short_credit','short_flows','lag1, no carry')
 add(col+'_mean5',lag(rolling(a,5,3)),'short_credit','short_flows','lag1, >=3/5 observations')
cons=pd.read_sql_query('SELECT * FROM consensus_daily',con)
for col in ['coverage','opinion_score']:add('analyst_'+col,lag(matrix(cons,col)),'analyst','consensus_daily','lag1, no carry')
add('analyst_target_gap',lag(matrix(cons,'target_price'))/c-1,'analyst','consensus_daily','lagged target / signal close')
con.close()
# Annual accounting only; never move corrected values back to original filing dates.
con=ro(ROOT/'research/dart_history/dart_hist.db')
reps=pd.read_sql_query("SELECT stock_code,year,fs,api,rcept_no,items FROM reports WHERE status='000' AND kept>0 AND reprt='Y'",con);con.close()
reps['priority']=(reps.fs=='CFS').astype(int)*2+(reps.api=='ALL').astype(int)
reps=reps.sort_values('priority').drop_duplicates(['stock_code','year'],keep='last')
def number(x):
 try:return float(str(x).replace(',',''))
 except:return np.nan
def item(items,ids,sections):
 for aid in ids:
  for x in items:
   if x.get('account_id')==aid and x.get('sj_div') in sections:return x
 return {}
events=[]
for row in reps.itertuples():
 if row.stock_code not in ti:continue
 it=json.loads(row.items);receipt=max([str(row.rcept_no)[:8]]+[str(x.get('rcept_no',''))[:8] for x in it])
 if len(receipt)!=8 or not receipt.isdigit():continue
 d=int(np.searchsorted(s.d,receipt,side='right'))
 if d>=s.T:continue
 op=item(it,['dart_OperatingIncomeLoss','ifrs-full_ProfitLossFromOperatingActivities'],['IS','CIS'])
 ni=item(it,['ifrs-full_ProfitLossAttributableToOwnersOfParent','ifrs-full_ProfitLoss'],['IS','CIS'])
 eq=item(it,['ifrs-full_Equity'],['BS']);asset=item(it,['ifrs-full_EquityAndLiabilities'],['BS'])
 rev=item(it,['ifrs-full_Revenue'],['IS','CIS']);cf=item(it,['ifrs-full_CashFlowsFromUsedInOperatingActivities'],['CF'])
 nums=[number(x.get('thstrm_amount')) for x in [ni,eq,asset,rev,op,cf]];prev=number(op.get('frmtrm_amount'))
 events.append((d,ti[row.stock_code],int(row.year),receipt,*nums,prev))
annual=[np.full(c.shape,np.nan,dtype='float32') for _ in range(7)];age=np.full(c.shape,np.nan,dtype='float32')
for j in range(s.N):
 ev=sorted([x for x in events if x[1]==j]);latestyear=-1
 for e in ev:
  d,_,year,rc,*nums=e
  if year<latestyear:continue
  latestyear=year
  for a,value in zip(annual,nums):a[d:,j]=value
  age[d:,j]=(pd.to_datetime(s.d[d:])-pd.Timestamp(rc)).days
ni,eq,assets,revenue,op,cf,prevop=annual;known=(age<=550)&(age>=0)
def annual_add(k,a):add(k,np.where(known,a,np.nan),'annual_pit','DART annual + panel approximate market cap','max receipt +1 trading day; <=550 calendar days old')
annual_add('annual_pe_approx',cap/np.where(ni!=0,ni,np.nan));annual_add('annual_pb_approx',cap/np.where(eq>0,eq,np.nan));annual_add('annual_roe',ni/np.where(eq>0,eq,np.nan))
annual_add('earnings_yield',ni/cap);annual_add('operating_yield',op/cap);annual_add('cashflow_yield',cf/cap)
annual_add('operating_margin',op/np.where(revenue>0,revenue,np.nan));annual_add('liability_ratio',(assets-eq)/np.where(assets>0,assets,np.nan));annual_add('op_yoy',np.where(abs(prevop)>0,(op-prevop)/abs(prevop),np.nan));annual_add('cf_to_op',cf/np.where(abs(op)>0,abs(op),np.nan))
pd.DataFrame(events,columns=['t','j','year','available_receipt','net_income','equity','assets','revenue','op','ocf','prev_op']).to_csv(P/'annual_availability.csv',index=False)
del annual,ni,eq,assets,revenue,op,cf,prevop,age
# Recorded models: reject scores produced after the intended opening trade.
con=ro(ROOT/'history.db')
for table,score in [('v3_scores','final_score_v3'),('lowvol_scores','lowvol_score'),('wu_scores','wu_score')]:
 d=pd.read_sql_query(f'SELECT run_id,ticker,model_id,{score} AS score,frozen_at FROM {table}',con)
 d['t']=d.run_id.astype(str).map(s.di);d=d[d.t.notna()&(d.t<s.T-1)].copy();d['j']=d.ticker.astype(str).str.zfill(6).map(ti)
 cutoff=pd.to_datetime([str(s.d[int(t)+1])+' 09:00:00+09:00' for t in d.t],utc=True)
 frozen=pd.to_datetime(d.frozen_at,format='mixed',utc=True,errors='coerce');d['ontime']=frozen.notna()&(frozen.to_numpy()<=cutoff.to_numpy())
 for model,g in d.groupby('model_id'):
  a=g[g.ontime&g.j.notna()];add('model_'+model,matrix(a,'score','run_id'),'model_'+table,table,'frozen_at <= next panel trading day 09:00 KST; no carry')
  audit.append(dict(source=table,model=model,rows=len(g),late_rows=int((~g.ontime).sum()),ontime_rows=len(a),ontime_dates=a.run_id.nunique()))
# Additional original snapshot fields, kept separate from complete-universe price factors.
cols=['oversold_score','trend_score','supply_score','fundamental_score','ocf_score','momentum_score','smartmoney_score','roe_value','catalyst_score','ocf_to_op_ratio','annual_yoy_%','quarterly_yoy_%']
d=pd.read_sql_query('SELECT run_id,run_timestamp,ticker,'+','.join('['+x+']' for x in cols)+' FROM stage3_final',con)
d['t']=d.run_id.astype(str).map(s.di);d=d[d.t.notna()&(d.t<s.T-1)].copy()
cutoff=pd.to_datetime([str(s.d[int(t)+1])+' 09:00:00+09:00' for t in d.t],utc=True);stamp=pd.to_datetime(d.run_timestamp,format='%Y%m%d_%H%M',errors='coerce').dt.tz_localize('Asia/Seoul').dt.tz_convert('UTC');d=d[stamp.notna()&(stamp.to_numpy()<=cutoff.to_numpy())]
for col in cols:add('snapshot_'+col.replace('%','pct'),matrix(d,col,'run_id'),'snapshot','stage3_final','run_timestamp before entry; historical rewrite cannot be excluded')
con.close();pd.DataFrame(audit).to_csv(P/'model_timing_audit.csv',index=False)
# Outcomes; no future outcomes are used to determine feature ranks.
t0=s.start;t1=s.T-26;valid=np.zeros(c.shape,bool);metrics={k:np.full(c.shape,np.nan,dtype='float32') for k in ['ret','hit','touch','first','mae','mdd','joint']}
for t in range(t0,t1):
 path,filled=s.paths(t,20);valid[t]=s.ok[t]&filled&np.isfinite(path[-1]);net=path[-1]-.005
 peak=np.maximum.accumulate(np.vstack([np.ones((1,s.N)),1+path]),axis=0)[1:];mae=np.min(path,axis=0);mdd=np.min((1+path)/peak-1,axis=0)
 for k,a in dict(ret=net*100,hit=(net>=.2)*100,touch=(np.max(path[4:],axis=0)-.005>=.2)*100,first=(path[0]>0)*100,mae=mae*100,mdd=mdd*100,joint=((net>=.2)&(mae>=-.1)&((path>0).mean(axis=0)>=.8)&(path[0]>0))*100).items():metrics[k][t]=a
tt,jj=np.where(valid);data=dict(t=tt.astype('int16'),j=jj.astype('int16'),date=s.d[tt],market=s.mk[jj]);data.update({k:a[valid] for k,a in metrics.items()});flat=pd.DataFrame(data)
# Feature rank is formed before the entry-feasibility filter, within market.
bins={};coverage=[];absolutes={}
for k,a in F.items():
 raw_a=a
 if k in ['daily_per','daily_pbr','annual_pe_approx','annual_pb_approx']:a=np.where(a>0,a,np.nan)
 q=np.zeros(c.shape,dtype='uint8')
 for m in ['kospi','kosdaq']:
  mask=s.ok&(s.mk==m)[None,:]
  if meta[k]['family']=='regime':
   j=np.where(s.mk==m)[0][0];rank1=pd.Series(a[:,j]).rolling(252,min_periods=60).rank(pct=True).to_numpy();ranks=np.where(mask,rank1[:,None],np.nan)
  else:ranks=pd.DataFrame(np.where(mask,a,np.nan)).rank(axis=1,pct=True).to_numpy()
  q=np.where(np.isfinite(ranks),np.ceil(ranks*5).clip(1,5),q).astype('uint8')
 bins[k]=q[valid]
 x=a[valid];coverage.append(dict(feature=k,**meta[k],n=int(np.isfinite(x).sum()),n_dates=int(np.unique(tt[np.isfinite(x)]).size),first=str(s.d[tt[np.isfinite(x)].min()]) if np.isfinite(x).any() else '',last=str(s.d[tt[np.isfinite(x)].max()]) if np.isfinite(x).any() else ''))
 if k in ['rsi6','rsi14','rsi28','daily_per','daily_pbr','annual_pe_approx','annual_pb_approx','annual_roe','op_yoy','index_ma_gap20','index_ma_gap60','index_ma_gap120']:absolutes[k]=raw_a[valid]
flat.to_parquet(P/'outcomes.parquet',index=False);pd.DataFrame(bins).to_parquet(P/'feature_quintiles.parquet',index=False);pd.DataFrame(absolutes).to_parquet(P/'absolute_values.parquet',index=False)
pd.DataFrame(coverage).to_csv(P/'feature_inventory.csv',index=False,encoding='utf-8-sig')
info=dict(n_features=len(F),n_rows=len(flat),n_dates=flat.date.nunique(),first=flat.date.min(),last=flat.date.max(),panel_sha256=hashlib.file_digest((ROOT/'research/fullscan_20260903/panel.npz').open('rb'),'sha256').hexdigest())
(P/'build_info.json').write_text(json.dumps(info,indent=2),encoding='utf-8');print('BUILD_DONE',info,flush=True)
