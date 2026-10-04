"""Research-only triple grid, past-selected checks, and contemporaneous sector audit."""
import sys,itertools,json,sqlite3,warnings,gzip
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np,pandas as pd
from code_target20_20261003 import block_idx
warnings.filterwarnings('ignore',category=RuntimeWarning)
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'research/target20_extended_20261004'
O=pd.read_parquet(P/'outcomes.parquet');Q=pd.read_parquet(P/'feature_quintiles.parquet');AV=pd.read_parquet(P/'absolute_values.parquet')
FEATURES=['rs20','rs60','rsi14','nh252','lv20','lv60','log_amount','market_cap','turnover20','amihud60','up_fraction','annual_roe','op_yoy','annual_pe_approx','operating_yield','cashflow_yield','liability_ratio','volume_ratio']
DATES=np.array(sorted(O.date.unique()));di={x:i for i,x in enumerate(DATES)};day=O.date.map(di).to_numpy();yr=np.array([x[:4] for x in DATES]);D=len(DATES)
q=Q[FEATURES].to_numpy('int16');Y=O[['ret','hit','first','mae','joint']].to_numpy(dtype=float);sz=Q.market_cap.to_numpy();market=O.market.to_numpy();counts=[];representatives=[];allpast=[]
def div(a,b):return np.divide(a,b,out=np.full(np.broadcast_shapes(np.shape(a),np.shape(b)),np.nan),where=b>0)
def stats(mask,values=Y[:,0]):
 n=np.bincount(day[mask],minlength=D);s=np.bincount(day[mask],weights=values[mask],minlength=D)
 return n,s
for m in ['kospi','kosdaq']:
 out=P/f'triples_{m}.csv.gz';prior=[];checks=[]
 with gzip.open(out,'wt',encoding='utf-8',newline='') as handle:
  for ci,cols in enumerate(itertools.combinations(range(len(FEATURES)),3)):
   idx=np.where((market==m)&(q[:,cols]>0).all(axis=1))[0];qq=q[idx][:,cols]-1;codes=qq[:,0]*25+qq[:,1]*5+qq[:,2];dd=day[idx];ix=dd*125+codes
   N=np.bincount(ix,minlength=D*125).reshape(D,125)
   S=np.stack([np.bincount(ix,weights=Y[idx,k],minlength=D*125).reshape(D,125) for k in range(5)],axis=2)
   base=div(S.sum(axis=1),N.sum(axis=1)[:,None]);diff=S-N[:,:,None]*np.nan_to_num(base[:,None,:])
   parts=[]
   for per in ['all','2024','2025','2026']:
    ds=np.ones(D,bool) if per=='all' else yr==per;n=N[ds].sum(axis=0);avg=div(S[ds].sum(axis=0),n[:,None]);ex=div(diff[ds].sum(axis=0),n[:,None])
    r=pd.DataFrame(dict(combo_id=ci,feature_a=FEATURES[cols[0]],feature_b=FEATURES[cols[1]],feature_c=FEATURES[cols[2]],bin_a=np.arange(125)//25+1,bin_b=np.arange(125)//5%5+1,bin_c=np.arange(125)%5+1,period=per,n=n,n_dates=(N[ds]>0).sum(axis=0),ret=avg[:,0],hit=avg[:,1],first=avg[:,2],mae=avg[:,3],joint=avg[:,4],excess=ex[:,0],joint_excess=ex[:,4]));parts.append(r)
   pd.concat(parts).to_csv(handle,index=False,header=ci==0,float_format='%.7g')
   a,b,c=parts[1:];ok=np.ones(125,bool)
   for z in [a,b]:ok&=(z.n>=200)&(z.n_dates>=40)&(z.excess>0)&(z.joint_excess>0)
   for k in np.where(ok)[0]:
    row=c.iloc[k].to_dict();row.update(market=m,rank_score=float(min(a.excess.iloc[k],b.excess.iloc[k])),ret2024=float(a.ret.iloc[k]),ret2025=float(b.ret.iloc[k]),excess2024=float(a.excess.iloc[k]),excess2025=float(b.excess.iloc[k]),joint_excess2024=float(a.joint_excess.iloc[k]),joint_excess2025=float(b.joint_excess.iloc[k]));prior.append(row)
   if ci in [0,123,500,815] and len(idx):
    k=int(codes[len(codes)//2]);actual=Y[idx[codes==k],0].mean();calc=parts[0].ret.iloc[k];assert abs(actual-calc)<1e-8;checks.append(float(abs(actual-calc)))
   if ci%150==0:print('TRIPLES',m,ci,'/816',flush=True)
 p=pd.DataFrame(prior).sort_values('rank_score',ascending=False);p.to_csv(P/f'past_triples_{m}.csv.gz',index=False,compression='gzip');allpast.append(p)
 counts.append(dict(market=m,cases=816*125,past_selected=len(p),available2026=int((p.n>0).sum()),positive_ret2026=int((p.ret>0).sum()),positive_both2026=int(((p.excess>0)&(p.joint_excess>0)).sum()),raw_checks=len(checks),max_error=max(checks)))
 representatives.extend(p.head(20).to_dict('records'))
 print('TRIPLES_DONE',counts[-1],flush=True)
pd.DataFrame(counts).to_csv(P/'triple_counts.csv',index=False)
# Detailed held-period comparisons use same availability and preserve calendar gaps.
detail=[]
for row in representatives:
 a,b,c=[row['feature_'+x] for x in 'abc'];aa,bb,cc=[int(row['bin_'+x]) for x in 'abc'];qa,qb,qc=[Q[k].to_numpy() for k in [a,b,c]]
 pool=(market==row['market'])&(qa>0)&(qb>0)&(qc>0);sel=pool&(qa==aa)&(qb==bb)&(qc==cc)
 for per in ['all','2024','2025','2026']:
  days=np.arange(D) if per=='all' else np.where(yr==per)[0];scope=np.isin(day,days);s=sel&scope;eligible=pool&scope
  r={k:row[k] for k in ['market','feature_a','feature_b','feature_c','bin_a','bin_b','bin_c','rank_score']};r['period']=per;r['n']=int(s.sum());r['n_dates']=int(np.unique(day[s]).size)
  if not s.any():detail.append(r);continue
  n,ss=stats(s);r['ret']=Y[s,0].mean();r['hit']=Y[s,1].mean();r['first']=Y[s,2].mean();r['mae']=Y[s,3].mean();r['fee1_ret']=r['ret']-.5
  bix=block_idx(len(days),20);den=n[days][bix].sum(axis=1);bs=div(ss[days][bix].sum(axis=1),den);r['ret_lo'],r['ret_hi']=np.nanquantile(bs,[.025,.975])
  pools={'base':eligible,'without_a':eligible&(qb==bb)&(qc==cc),'without_b':eligible&(qa==aa)&(qc==cc),'without_c':eligible&(qa==aa)&(qb==bb)}
  for label,pm in pools.items():
   nn,ps=stats(pm);dd=ss-n*np.nan_to_num(div(ps,nn));r[label+'_ex']=dd.sum()/s.sum();b=div(dd[days][bix].sum(axis=1),den);r[label+'_lo'],r[label+'_hi']=np.nanquantile(b,[.025,.975])
  group=day*6+sz;nn=np.bincount(group[eligible],minlength=D*6);ps=np.bincount(group[eligible],weights=Y[eligible,0],minlength=D*6);means=div(ps,nn);vals=Y[s,0]-means[group[s]];r['size_matched_ex']=np.mean(vals)
  ds=np.bincount(day[s],weights=vals,minlength=D);b=div(ds[days][bix].sum(axis=1),den);r['size_matched_lo'],r['size_matched_hi']=np.nanquantile(b,[.025,.975])
  for label,groups in [('stock',O.j.to_numpy()),('month',O.date.str[:6].to_numpy())]:
   agg=pd.DataFrame(dict(g=groups[s],v=Y[s,0])).groupby('g').v.agg(['sum','count']);best=agg['sum'].idxmax();keep=s&(groups!=best);r['remove_best_'+label+'_ret']=float(Y[keep,0].mean()) if keep.any() else np.nan;r['best_'+label]=str(best)
  detail.append(r)
pd.DataFrame(detail).to_csv(P/'triple_representatives.csv',index=False)
# Sector labels only from timely same-date stage1 snapshots; no carrying current classifications backward.
con=sqlite3.connect('file:'+str(ROOT/'history.db')+'?mode=ro',uri=True)
se=pd.read_sql_query('SELECT run_id,run_timestamp,ticker,sector FROM stage1_oversold',con);con.close()
z=np.load(ROOT/'research/fullscan_20260903/panel.npz',allow_pickle=True);dates=z['dates'].astype(str);ticks=z['tick'].astype(str);tmap={x:i for i,x in enumerate(dates)};jmap={x:i for i,x in enumerate(ticks)}
se['t']=se.run_id.astype(str).map(tmap);se['j']=se.ticker.astype(str).str.zfill(6).map(jmap);se=se[se.t.notna()&se.j.notna()&(se.t<len(dates)-1)].copy()
stamp=pd.to_datetime(se.run_timestamp,format='%Y%m%d_%H%M',errors='coerce').dt.tz_localize('Asia/Seoul');cut=pd.to_datetime([dates[int(t)+1]+' 09:00' for t in se.t]).tz_localize('Asia/Seoul');se=se[stamp.notna()&(stamp.to_numpy()<=cut.to_numpy())]
se=se[se.sector.notna()&~se.sector.astype(str).isin(['','nan','Unknown','기타','미분류'])].drop_duplicates(['t','j'],keep='last')
joined=O.merge(se[['t','j','sector']],on=['t','j'],how='inner');joined['year']=joined.date.str[:4]
if len(joined):
 joined['matched_ex']=joined.ret-joined.groupby(['date','market']).ret.transform('mean')
 joined.groupby(['market','sector','year']).agg(n=('ret','size'),n_dates=('date','nunique'),ret=('ret','mean'),hit=('hit','mean'),first=('first','mean'),mae=('mae','mean'),excess=('matched_ex','mean')).reset_index().to_csv(P/'sector_snapshots.csv',index=False,encoding='utf-8-sig')
(P/'extension_meta.json').write_text(json.dumps(dict(features=FEATURES,triple_cases=204000,triple_period_rows=816000,sector_rows=len(joined),sector_dates=int(joined.date.nunique()),sector_groups=int(joined.sector.nunique())),indent=2),encoding='utf-8')
print('DONE triples and sectors',flush=True)
