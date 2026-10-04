"""All inventoried feature bins and cross-feature low/high/absolute-bin pairs."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np,pandas as pd,json,warnings
from threadpoolctl import threadpool_limits
warnings.filterwarnings('ignore',category=RuntimeWarning)
P=Path(__file__).resolve().parents[2]/'research/target20_conditions_20261004'
O=pd.read_parquet(P/'outcomes.parquet');Q=pd.read_parquet(P/'feature_quintiles.parquet');ABS=pd.read_parquet(P/'absolute_values.parquet');features=list(Q)
FULL='--full' in sys.argv
if FULL:P=P/'fullgrid';P.mkdir(exist_ok=True)
dates=sorted(O.date.unique());di={d:i for i,d in enumerate(dates)};dt=O.date.map(di).to_numpy();years=np.array([x[:4] for x in dates]);block=[];by=[]
for y in sorted(set(years)):
 for ix in np.array_split(np.where(years==y)[0],int(np.ceil((years==y).sum()/20))):
  # Every block spans at most20 consecutive listed trading days, within a year.
  for t in ix:block.append((t,len(by)))
  by.append(y)
bm=dict(block);B=len(by);by=np.array(by)
conds=[];maps=[];avraw=[];avnames=[]
q=Q.to_numpy(dtype='uint8');Kf=q.shape[1]
for j,k in enumerate(features):
 avnames.append(k);avraw.append(q[:,j]>0)
 for level in range(1,6):conds.append(dict(name=k+'__q'+str(level),feature=k,kind='quintile',level=level,availability=j,pair=level in [1,5]));maps.append(q[:,j]==level)
for k in ABS:
 a=ABS[k].to_numpy();av=len(avraw);avraw.append(np.isfinite(a));avnames.append(k+'__absolute')
 if k.startswith('rsi'):edges=[-np.inf,20,30,50,70,80,np.inf]
 elif k in ['daily_per','annual_pe_approx']:edges=[-np.inf,0,5,10,20,40,np.inf]
 elif k in ['daily_pbr','annual_pb_approx']:edges=[-np.inf,0,.5,1,2,4,np.inf]
 elif k=='annual_roe':edges=[-np.inf,0,.05,.1,.2,np.inf]
 elif k=='op_yoy':edges=[-np.inf,-.5,0,.5,1,np.inf]
 else:edges=[-np.inf,0,np.inf]
 for left,right in zip(edges[:-1],edges[1:]):
  conds.append(dict(name=f'{k}__abs({left},{right}]',feature=k,kind='absolute',level=f'({left},{right}]',availability=av,pair=True));maps.append(np.isfinite(a)&(a>left)&(a<=right))
C=pd.DataFrame(conds)
if FULL:C['pair']=True
C.to_csv(P/'conditions.csv',index=False);A=np.stack(maps,axis=1);V=np.stack(avraw,axis=1);del maps,avraw,Q,ABS
pcols=np.where(C['pair'])[0];pc=C.iloc[pcols].reset_index(drop=True);pi,pj=np.triu_indices(len(pc),1);distinct=(pc.feature.to_numpy()[pi]!=pc.feature.to_numpy()[pj]);pi,pj=pi[distinct],pj[distinct]
PC=pd.DataFrame(dict(a=pc.name.to_numpy()[pi],b=pc.name.to_numpy()[pj],feature_a=pc.feature.to_numpy()[pi],feature_b=pc.feature.to_numpy()[pj]));PC.to_csv(P/'pair_conditions.csv',index=False)
metrics=['ret','hit','mae','mdd','first','joint','touch'];fields=['n','n_base']+metrics+['excess','hit_excess','joint_excess']+['added_'+side+'_'+metric for side in ['a','b'] for metric in ['ret','hit','joint']];fi={x:i for i,x in enumerate(fields)}
Y=O[metrics].to_numpy(dtype='float32');avindex=C.availability.to_numpy();pai=pc.availability.to_numpy();markets=O.market.to_numpy()
print('SCAN_SIZE',json.dumps(dict(features=len(features),single_conditions=len(C),pair_conditions=len(PC),markets=2,blocks=B)),flush=True)

def summarize(arr,active,case,market,kind):
 # arr: blocks x fields x cases. Bootstrap preserves whole20-day date blocks.
 outputs=[]
 for per in ['all','2024','2025','2026']:
  bs=np.where(np.ones(B,bool) if per=='all' else by==per)[0];z=arr[bs];tot=z.sum(axis=0);n=tot[fi['n']];nb=(z[:,fi['n']]>0).sum(axis=0)
  out=case.copy();out['market']=market;out['period']=per;out['n']=n.astype(int);out['n_dates']=active[bs].sum(axis=0).astype(int);out['n_blocks']=nb
  for field in fields[2:]:out[field]=np.divide(tot[fi[field]],n,out=np.full(len(n),np.nan),where=n>0)
  w=np.random.default_rng(20261004).multinomial(len(bs),np.ones(len(bs))/len(bs),size=2000).astype('float32')
  low={k:np.full(len(n),np.nan) for k in ['ret','excess','hit']};high={k:a.copy() for k,a in low.items()};obs=np.full(len(n),np.nan);maxstat=np.full(2000,-np.inf)
  eligible=np.where(nb>=3)[0]
  for chunk in np.array_split(eligible,max(1,int(np.ceil(len(eligible)/512)))):
   if not len(chunk):continue
   den=w@z[:,fi['n'],chunk];den=np.where(den>0,den,np.nan)
   for field in low:
    samples=(w@z[:,fi[field],chunk])/den;lo,hi=np.nanquantile(samples,[.025,.975],axis=0);low[field][chunk]=lo;high[field][chunk]=hi
    if field=='excess':
     sd=np.nanstd(samples,axis=0,ddof=1);mean=out[field].to_numpy()[chunk];good=(nb[chunk]>=6)&(sd>1e-9)
     obs[chunk[good]]=mean[good]/sd[good]
     if good.any():maxstat=np.fmax(maxstat,np.nanmax((samples[:,good]-mean[good])/sd[good],axis=1))
  for field in low:out[field+'_lo']=low[field];out[field+'_hi']=high[field]
  # Approximate simultaneous one-sided excess test, within market+period+kind.
  out['maxT_p']=[(1+np.sum(maxstat>=a))/2001 if np.isfinite(a) else np.nan for a in obs]
  outputs.append(out);print('SUMMARY',market,kind,per,len(out),flush=True)
 result=pd.concat(outputs,ignore_index=True)
 if kind=='single':
  result['level']=result.level.astype(str)
  for col in result:
   if col.startswith('added_'):result[col]=np.nan
 if FULL:result.to_parquet(P/f'{kind}_{market}.parquet',index=False)
 else:result.to_csv(P/f'{kind}_{market}.csv',index=False,encoding='utf-8-sig')

with threadpool_limits(limits=2):
 for market in ['kospi','kosdaq']:
  single=np.zeros((B,len(fields),len(C)),dtype='float32');pair=np.zeros((B,len(fields),len(PC)),dtype='float32');sa=np.zeros((B,len(C)),dtype='uint8');pa=np.zeros((B,len(PC)),dtype='uint8')
  for t,date in enumerate(dates):
   ix=np.where((dt==t)&(markets==market))[0]
   if len(ix)==0:continue
   aa=A[ix].astype('float32');vv=V[ix].astype('float32');yy=Y[ix];ap=aa[:,pcols];b=bm[t]
   live=np.where(ap.any(axis=0))[0];inv=np.full(len(pc),-1);inv[live]=np.arange(len(live));sp=np.where((inv[pi]>=0)&(inv[pj]>=0))[0];ii=inv[pi[sp]];jj=inv[pj[sp]];ap=ap[:,live]
   sn=aa.sum(axis=0);vn=vv.sum(axis=0);pn=ap.T@ap;bn=vv.T@vv;parent_n=ap.T@vv;ns=pn[ii,jj];base_n=bn[pai[pi[sp]],pai[pj[sp]]]
   single[b,fi['n']]+=sn;single[b,fi['n_base']]+=vn[avindex];sa[b]+=(sn>0).astype('uint8')
   pair[b,fi['n'],sp]+=ns;pair[b,fi['n_base'],sp]+=base_n;pa[b,sp]+=(ns>0).astype('uint8')
   for k,field in enumerate(metrics):
    sums=yy[:,k]@aa;vs=yy[:,k]@vv;ss=(ap*yy[:,k,None]).T@ap;bb=(vv*yy[:,k,None]).T@vv;ps=ss[ii,jj];bs=bb[pai[pi[sp]],pai[pj[sp]]]
    single[b,fi[field]]+=sums;pair[b,fi[field],sp]+=ps
    ef={'ret':'excess','hit':'hit_excess','joint':'joint_excess'}.get(field)
    if ef:
     single[b,fi[ef]]+=sums-sn*np.divide(vs[avindex],vn[avindex],out=np.zeros(len(C)),where=vn[avindex]>0)
     pair[b,fi[ef],sp]+=ps-ns*np.divide(bs,base_n,out=np.zeros(len(sp)),where=base_n>0)
     psum=(ap*yy[:,k,None]).T@vv
     for side,x,y in [('b',ii,pj[sp]),('a',jj,pi[sp])]:
      denom=parent_n[x,pai[y]];parentmean=np.divide(psum[x,pai[y]],denom,out=np.zeros(len(sp)),where=denom>0)
      pair[b,fi['added_'+side+'_'+field],sp]+=ps-ns*parentmean
   if t%80==0:print('DAY',market,date,flush=True)
  np.savez_compressed(P/f'blocks_{market}.npz',single=single,pair=pair,single_active=sa,pair_active=pa,block_year=by,fields=np.array(fields))
  summarize(single,sa,C[['name','feature','kind','level']],market,'single')
  summarize(pair,pa,PC,market,'pairs')
info=dict(features=len(features),single_conditions=len(C),pair_conditions=len(PC),market_cases=2*(len(C)+len(PC)),dates=len(dates),rows=len(O),block_count=B)
(P/'scan_info.json').write_text(json.dumps(info,indent=2),encoding='utf-8');print('DONE',info,flush=True)
