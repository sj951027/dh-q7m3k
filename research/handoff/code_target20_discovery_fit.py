"""Quarterly expanding, purged, continuous-data discovery; no production imports."""
import sys,json,warnings
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier,HistGradientBoostingRegressor
from sklearn.cluster import MiniBatchKMeans
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeRegressor,export_text
from sklearn.metrics import roc_auc_score,brier_score_loss
from threadpoolctl import threadpool_limits
warnings.filterwarnings('ignore',category=RuntimeWarning)
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'research/target20_discovery_20261004';market=sys.argv[1]
O=pd.read_parquet(P/'outcomes.parquet');X=pd.read_parquet(P/'raw_features.parquet');Q=pd.read_parquet(P/'feature_quintiles.parquet');metadata=pd.read_csv(P/'feature_inventory.csv').set_index('feature')
mask=O.market==market;O=O[mask].reset_index(drop=True);X=X[mask].reset_index(drop=True);Q=Q[mask].reset_index(drop=True)
z=np.load(ROOT/'research/fullscan_20260903/panel.npz',allow_pickle=True);dates=z['dates'].astype(str);tick=z['tick'].astype(str);c=z['close'].astype(float);v=z['vol'].astype(float);t=O.t.to_numpy(int);j=O.j.to_numpy(int)
quarter=O.date.str[:4]+'Q'+((O.date.str[4:6].astype(int)-1)//3+1).astype(str);folds=sorted(x for x in quarter.unique() if x>='2025Q1');first=int(t[quarter==folds[0]].min());initial=t+20<first
coverage=X[initial].notna().mean();features=coverage[coverage>=.6].index.tolist();features=[f for f in features if X.loc[initial,f].nunique()>1];X=X[features].to_numpy(dtype='float32');X[~np.isfinite(X)]=np.nan
pd.DataFrame(dict(feature=features,family=[metadata.loc[f,'family'] for f in features],initial_coverage=[coverage[f] for f in features])).to_csv(P/f'learned_inputs_{market}.csv',index=False)
offset=np.arange(-19,1);prices=c[t[:,None]+offset,j[:,None]];volumes=v[t[:,None]+offset,j[:,None]]
shape=np.concatenate([np.log(prices/c[t,j,None]),np.log((volumes+1)/(np.nanmean(volumes,axis=1)[:,None]+1))],axis=1);shape=np.nan_to_num(shape,nan=0,posinf=0,neginf=0).clip(-10,10).astype('float32');del prices,volumes
params=dict(max_iter=80,learning_rate=.06,max_leaf_nodes=15,min_samples_leaf=200,l2_regularization=10,early_stopping=False,random_state=20261004)
preds=[];audit=[];cal=[];importance=[];centers=[]
with threadpool_limits(limits=3):
 for fold in folds:
  te=np.where(quarter.to_numpy()==fold)[0];firsttest=int(t[te].min());tr=np.where(t+20<firsttest)[0];assert int((t[tr]+20).max())<firsttest
  _,count=np.unique(t[tr],return_counts=True);cnt=pd.Series(t[tr]).value_counts();weights=1/np.array([cnt[x] for x in t[tr]]);weights*=len(weights)/weights.sum()
  out=O.iloc[te].copy();out['fold']=fold;out['row_id']=te;out['ticker']=tick[j[te]];out['size_bin']=Q.market_cap.iloc[te].to_numpy();out['amount']=X[te,features.index('log_amount')]
  for target in ['hit','first','joint','ret']:
   y=O[target].to_numpy(dtype=float);clf=HistGradientBoostingRegressor(**params) if target=='ret' else HistGradientBoostingClassifier(**params)
   clf.fit(X[tr],y[tr] if target=='ret' else (y[tr]>0).astype(int),sample_weight=weights)
   score=clf.predict(X[te]) if target=='ret' else clf.predict_proba(X[te])[:,1];out['learn_'+target]=score
   gains=np.zeros(len(features))
   for pp in clf._predictors:
    for tree in pp:
     nd=tree.nodes;ok=~nd['is_leaf'].astype(bool);np.add.at(gains,nd['feature_idx'][ok],np.maximum(nd['gain'][ok],0))
   for k in np.argsort(-gains)[:15]:importance.append(dict(market=market,fold=fold,target=target,feature=features[k],gain=float(gains[k]),share=float(gains[k]/max(gains.sum(),1e-9))))
   if target!='ret':
    truth=(y[te]>0).astype(int);cal.append(dict(market=market,fold=fold,target=target,n=len(te),auc=roc_auc_score(truth,score),brier=brier_score_loss(truth,score),baseline_brier=brier_score_loss(truth,np.full(len(te),np.average((y[tr]>0),weights=weights))),predicted_mean=score.mean(),observed_mean=truth.mean()))
   if target=='joint' and fold==folds[-1]:
    # Description only, trained from past predictions; not used to select stocks.
    take=tr[::max(1,len(tr)//30000)];med=np.nanmedian(X[tr],axis=0);sur=DecisionTreeRegressor(max_depth=3,min_samples_leaf=500,random_state=20261004);xx=np.where(np.isfinite(X[take]),X[take],med);sur.fit(xx,clf.predict_proba(X[take])[:,1]);(P/f'surrogate_{market}.txt').write_text(export_text(sur,feature_names=features,decimals=4),encoding='utf-8')
  ranks=out.groupby('date')[['learn_hit','learn_first','learn_joint']].rank(pct=True);out['learn_balanced']=ranks.mean(axis=1)
  scaler=StandardScaler().fit(shape[tr]);cl=MiniBatchKMeans(n_clusters=32,n_init=3,batch_size=4096,max_iter=100,random_state=20261004);trainshape=scaler.transform(shape[tr]);cl.fit(trainshape,sample_weight=weights);groups=cl.predict(trainshape);testgroups=cl.predict(scaler.transform(shape[te]));counts=np.bincount(groups,weights=weights,minlength=32);wins=np.bincount(groups,weights=weights*(O.joint.to_numpy()[tr]>0),minlength=32);base=np.average(O.joint.to_numpy()[tr]>0,weights=weights);rates=(wins+200*base)/(counts+200);out['cluster_shape']=rates[testgroups];out['cluster_id']=testgroups
  for k in range(32):centers.append(dict(market=market,fold=fold,cluster=k,weighted_n=float(counts[k]),train_joint=float(rates[k]),train_ret=float(np.average(O.ret.to_numpy()[tr][groups==k],weights=weights[groups==k])) if (groups==k).any() else np.nan))
  out['control_amount']=out.amount;out['control_fundamental']=(Q.annual_roe.iloc[te].to_numpy()+Q.op_yoy.iloc[te].to_numpy())/2;out.loc[(Q.annual_roe.iloc[te].to_numpy()==0)|(Q.op_yoy.iloc[te].to_numpy()==0),'control_fundamental']=np.nan;out['control_rsi']=-X[te,features.index('rsi14')]
  preds.append(out);audit.append(dict(market=market,fold=fold,n_train=len(tr),n_test=len(te),train_last_signal=dates[t[tr].max()],train_last_outcome=dates[(t[tr]+20).max()],test_first_signal=dates[firsttest],test_last_signal=dates[t[te].max()],n_features=len(features)))
  pd.concat(preds).to_parquet(P/f'predictions_{market}.parquet',index=False)
  pd.DataFrame(audit).to_csv(P/f'fold_audit_{market}.csv',index=False)
  print('LEARNED',market,fold,'train',len(tr),'test',len(te),'features',len(features),flush=True)
pd.DataFrame(cal).to_csv(P/f'calibration_{market}.csv',index=False);pd.DataFrame(importance).to_csv(P/f'training_importance_{market}.csv',index=False);pd.DataFrame(centers).to_csv(P/f'clusters_{market}.csv',index=False)
print('DONE',market,flush=True)
