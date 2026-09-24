"""Multi-view price-pattern hypotheses, fixed before reading their performance.
Offline exploration; no model registration. Explicit today's batch exception only.
"""
from pathlib import Path
import argparse,json,sqlite3,warnings
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from code_20260924_pattern_scan import block_ci
warnings.filterwarnings('ignore',category=RuntimeWarning)
a=argparse.ArgumentParser();a.add_argument('--batch-skipped-date');a=a.parse_args()
now=datetime.now(ZoneInfo('Asia/Seoul'))
if now.weekday()<5 and '20:10'<=now.strftime('%H:%M')<='22:30':
    assert a.batch_skipped_date==now.strftime('%Y%m%d')=='20260924'
ROOT=Path(__file__).resolve().parents[2];O=Path(__file__).with_name('multiview_20260924');O.mkdir(exist_ok=True)
con=sqlite3.connect((ROOT.parent/'dh-q7m3k-data/ohlcv.db').as_uri()+'?mode=ro',uri=True);con.execute('PRAGMA query_only=ON')
df=pd.read_sql_query('SELECT ticker,date,close,high,low,volume,shares,is_suspended,market FROM daily_ohlcv',con)
md=pd.read_sql_query('SELECT series,date,close FROM market_daily',con);con.close()
df=df[df.ticker.str.fullmatch(r'\d{6}')];dates=np.array(sorted(df.date.unique()));ticks=np.array(sorted(df.ticker.unique()));T,N=len(dates),len(ticks)
rr=df.date.map({d:i for i,d in enumerate(dates)}).to_numpy();cc=df.ticker.map({t:i for i,t in enumerate(ticks)}).to_numpy()
def mat(k):
    x=np.full((T,N),np.nan,np.float32);x[rr,cc]=df[k].to_numpy(dtype=np.float32);return x
c32=mat('close');c=c32.astype(float);v=mat('volume');shares=mat('shares');susp=mat('is_suspended');hi=mat('high');lo=mat('low')
mk=df.groupby('ticker').market.last().reindex(ticks).to_numpy();ki=mk=='KOSPI';del df
md=md.pivot(index='date',columns='series',values='close').reindex(dates);kp=md.KOSPI.to_numpy();kq=md.KOSDAQ.to_numpy()
def lag(x,n):
    z=np.full_like(x,np.nan,dtype=float);z[n:]=x[:-n];return z
def roll(x,n,op='mean',minp=None):return getattr(pd.DataFrame(x).rolling(n,min_periods=minp or n),op)().to_numpy()
def rank(x):return pd.DataFrame(x).rank(axis=1,pct=True).to_numpy()
ret=c/lag(c,1)-1;amt=roll(c32*v,20,minp=10)
ok=(roll((abs(ret)<1e-9).astype(float),63,minp=20)<=.5)&(roll((abs(ret)>.32).astype(float),21,'max',5)<=0)&(roll(ret,21,'std',15)>=.003)&(amt>=5e8)&(susp==0)&np.isfinite(c)
im=np.where(ki,kp[:,None],kq[:,None]);mi=im/lag(im,1)-1
beta=(roll(ret*mi,60,minp=40)-roll(ret,60,minp=40)*roll(mi,60,minp=40))/roll(mi,60,'std',40)**2
high=roll(c,252,'max',120);newhigh=c>=high*.999;cnt=np.full(N,np.nan);dsh=np.full_like(c,np.nan)
for t in range(T):cnt=np.where(newhigh[t],0,cnt+1);dsh[t]=cnt
def conditional_beta(up):
    m=(mi>0) if up else (mi<0)
    y=np.where(m,ret,np.nan);x=np.where(m,mi,np.nan)
    return (roll(x*y,60,minp=12)-roll(x,60,minp=12)*roll(y,60,minp=12))/roll(x,60,'std',12)**2
upb=conditional_beta(True);downb=conditional_beta(False)
vol5=roll(ret,5,'std');vol60=roll(ret,60,'std',40);vol20=roll(ret,20,'std',15)
r5=c/lag(c,5)-1;r20=c/lag(c,20)-1;r60=c/lag(c,60)-1
rs20=r20-(im/lag(im,20)-1);rs60=r60-(im/lag(im,60)-1)
v5=roll(v,5);v20=roll(v,20,minp=10);v60=roll(v,60,minp=40)
clv=np.where(hi>lo,(2*c-hi-lo)/(hi-lo),0)
logret=np.log(c/lag(c,1))
F={'beta':beta,'near':-dsh,'amount':np.log(amt),'size':np.log(c32*shares),
   'mom':c/lag(c,252)-c/lag(c,21),'up_beta':upb,'low_down_beta':-downb,'asym_beta':upb-downb,
   'resilience':roll(np.where(mi<0,ret-mi,np.nan),60,minp=12),
   'relative20':rs20,'relative60':rs60,'steady60':roll((ret>0).astype(float),60),
   'steady126':roll((ret>0).astype(float),126,minp=80),
   'drift_without_bestday':np.log(c/lag(c,120))-roll(logret,120,'max',80),
   'efficient60':np.log(c/lag(c,60))/roll(np.abs(logret),60,'sum',40),
   'quiet20':-vol20,'quiet60':-vol60,'small_worstday':roll(ret,60,'min',40),
   'repeat_high':roll(newhigh.astype(float),60,minp=40),
   'near_price':c/high,'prior_squeeze':-lag(vol5/vol60,10),'compression':-vol5/vol60,
   'prior_dry':-lag(v5/v60,10),'dry':-v5/v60,'volume_restart':v5/lag(v20,5),
   'clv20':roll(clv,20,minp=10),'breakout20':c/lag(roll(c,20,'max'),1)-1,
   'low_short_return':-r5,'prior_pullback':-lag(r5,3),'rebound3':c/lag(c,3)-1,
   'acceleration':rs20-lag(rs20,20)}
R={k:rank(np.where(ok,x,np.nan)) for k,x in F.items()};R['near']=1-rank(np.where(ok,dsh,np.nan))
specs=[]
def add(name,family,keys,gate=None,slots=20,delay=1,corr=None):
    sc=R[keys[0]].copy()
    for k in keys[1:]:sc+=np.where(np.isfinite(R[k]),R[k],.5)
    sc=np.where(ok & (gate if gate is not None else True),sc,np.nan)
    specs.append(dict(name=name,family=family,keys=keys,slots=slots,delay=delay,corr=corr,score=sc))
B=['beta','near']
add('base_beta_near','baseline',B);add('base_amount','baseline',['amount']);add('base_R1_amount','baseline',['mom',*B,'amount'])
for nm,keys in [('up_capture',['up_beta','near']),('asymmetry',['asym_beta','near']),
                ('downside_filter',[*B,'low_down_beta']),('resilience',[*B,'resilience']),
                ('relative_resilience',['relative60','resilience','near'])]:add(nm,'market_response',keys)
for nm,keys in [('steady60',[*B,'steady60']),('steady126',[*B,'steady126']),('efficient',[*B,'efficient60']),
                ('drift',[*B,'drift_without_bestday']),('small_losses',[*B,'small_worstday']),
                ('quiet_recent',[*B,'quiet20'])]:add(nm,'trend_quality',keys)
for nm,keys in [('repeated_high',['beta','repeat_high']),('price_nearness',['beta','near_price']),
                ('multi_horizon',[*B,'relative20','relative60']),('accelerating',[*B,'acceleration'])]:add(nm,'trend_persistence',keys)
for nm,keys in [('squeeze_then_strength',['prior_squeeze','relative20','breakout20']),
                ('squeeze_in_leaders',[*B,'prior_squeeze']),('tight_now',[*B,'compression']),
                ('dry_then_strength',['prior_dry','relative20','near']),('dry_in_leaders',[*B,'prior_dry']),
                ('dry_now',[*B,'dry']),('restart',[*B,'volume_restart']),('firm_close',[*B,'clv20'])]:add(nm,'price_volume_sequence',keys)
for nm,keys,gate in [('pullback_dry',[*B,'low_short_return','dry'],r60>0),
                     ('pullback_rebound',[*B,'prior_pullback','rebound3'],r60>0),
                     ('leaders_only',B,R['amount']>=.8),('large_only',B,R['size']>=.8),
                     ('mid_only',B,(R['size']>=.2)&(R['size']<.8)),
                     ('kospi_only',B,np.broadcast_to(ki,(T,N))),('kosdaq_only',B,np.broadcast_to(~ki,(T,N))),
                     ('up_market_only',B,im>roll(im,60)),
                     ('quiet_gate_leaders',B,R['quiet60']>=.5)]:add(nm,'conditional_universe',keys,gate)
for slots in [10,40]:add('slots_'+str(slots),'construction',B,slots=slots)
for rho in [.70,.85]:add('diversify_'+str(rho),'construction',B,corr=rho)
for delay in [5,10]:add('delay_'+str(delay),'entry_timing',B,delay=delay)
# Fixed common entry dates. Same 20 complete h120 monthly cohorts as preceding audit.
prior=pd.read_csv(Path(__file__).with_name('r1_controls_20260924')/'cohorts.csv',dtype={'date':str})
anchors=[int(np.searchsorted(dates,d)) for d in prior[prior.name=='R1'].date]
manifest=[{k:vv for k,vv in s.items() if k!='score'} for s in specs]
(O/'recipes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('FIXED RECIPES',len(specs),'before outcome evaluation',flush=True)
mark=pd.DataFrame(c).ffill().to_numpy();rows=[];picks=[];paths={}
for s in specs:
    for t in anchors:
        sc=s['score'][t];cand=np.flatnonzero(np.isfinite(sc));order=cand[np.argsort(-sc[cand],kind='stable')]
        if s['corr'] is None:ids=order[:s['slots']]
        else:
            order=order[:100];cor=pd.DataFrame(ret[t-59:t+1,order]).corr(min_periods=40).to_numpy();chosen=[]
            for i in range(len(order)):
                if not chosen or (np.all(np.isfinite(cor[i,chosen])) and np.max(cor[i,chosen])<s['corr']):chosen.append(i)
                if len(chosen)==s['slots']:break
            ids=order[chosen]
        e=t+s['delay'];fill=np.isfinite(c[e,ids])&(c[e,ids]>0)&(v[e,ids]>0)
        for ident in ids:picks.append(dict(name=s['name'],date=dates[t],ticker=ticks[ident]))
        for h in [60,120,180]:
            end=e+h
            if end>=T:continue
            gross=np.where(fill,mark[end,ids]/c[e,ids]-1,0.)
            net=(gross.sum()-.005*fill.sum())/s['slots']
            # Every stock slot gets its own market index. Empty slots remain cash.
            kp_w=np.sum(ki[ids])/s['slots'];kq_w=np.sum(~ki[ids])/s['slots']
            bench=kp_w*(kp[end]/kp[e]-1)+kq_w*(kq[end]/kq[e]-1)
            win=((gross>=1)&(gross-np.where(ki[ids],kp[end]/kp[e]-1,kq[end]/kq[e]-1)>=1)&fill).sum()/s['slots']
            sort=np.sort(gross);trimmed=(gross.sum()-(sort[-2:].sum() if len(sort)>=2 else sort.sum())-.005*fill.sum())/s['slots']
            bad=np.sum((gross<=-.3)&fill)/s['slots']
            rows.append(dict(name=s['name'],family=s['family'],date=dates[t],year=int(dates[t][:4]),h=h,net=float(net),excess=float(net-bench),
                benchmark=float(bench),slots=s['slots'],filled=int(fill.sum()),win2x=float(win),loss30=float(bad),
                top2_to_cash=float(trimmed),missing_exit=int(np.sum(~np.isfinite(c[end,ids])&fill)),
                kospi_weight=float(kp_w),kosdaq_weight=float(kq_w)))
            if h==120:
                pp=np.where(fill[None,:],mark[e:end+1,ids]/c[e,ids][None,:]-1,0.).sum(axis=1)/s['slots']-.005*fill.sum()/s['slots']
                paths[s['name'],dates[t]]=pp
C=pd.DataFrame(rows);C.to_csv(O/'cohorts.csv',index=False);pd.DataFrame(picks).to_csv(O/'picks.csv',index=False)
base=C[(C.name=='base_beta_near')&(C.h==120)].set_index('date');old=prior[prior.name=='beta_near'].set_index('date')
assert np.max(np.abs(base.net-old.net))<1e-10
summary=[]
for h in [60,120,180]:
    for s in specs:
        g=C[(C.name==s['name'])&(C.h==h)].set_index('date').sort_index()
        b=C[(C.name=='base_beta_near')&(C.h==h)].set_index('date').reindex(g.index)
        am=C[(C.name=='base_amount')&(C.h==h)].set_index('date').reindex(g.index)
        row=dict(name=s['name'],family=s['family'],h=h,n=len(g),filled=g.filled.mean(),win2x=g.win2x.mean(),loss30=g.loss30.mean(),
                 top2_to_cash=g.top2_to_cash.mean(),kospi_weight=g.kospi_weight.mean())
        for nm,x in [('net',g.net),('excess',g.excess),('delta_base',g.net-b.net),('delta_amount',g.net-am.net),
                     ('delta_base_excess',g.excess-b.excess)]:
            mu,low,high,n=block_ci(x,max(1,int(np.ceil(h/21))))
            row.update({nm:mu,nm+'_lo':low,nm+'_hi':high})
        for y in [2024,2025,2026]:
            q=g[g.year==y];row['delta_'+str(y)]=(q.net-b.net.reindex(q.index)).mean();row['n_'+str(y)]=len(q)
        summary.append(row)
S=pd.DataFrame(summary)
# Simultaneous error band only across this batch of h120 net-return comparisons.
# Not correction for all earlier research; not a formal adoption test.
piv=C[C.h==120].pivot(index='date',columns='name',values='net');D=piv.subtract(piv.base_beta_near,axis=0)
rng=np.random.default_rng(924);starts=rng.integers(0,len(D),(3000,4));ix=((starts[:,:,None]+np.arange(6))%len(D)).reshape(3000,-1)[:,:len(D)]
boot=D.to_numpy()[ix].mean(axis=1);err=boot-D.mean().to_numpy();band=float(np.quantile(np.max(np.abs(err),axis=1),.95))
S.loc[S.h==120,'batch_simultaneous_lo']=S.loc[S.h==120,'delta_base']-band
S.loc[S.h==120,'batch_simultaneous_hi']=S.loc[S.h==120,'delta_base']+band
S.to_csv(O/'summary.csv',index=False)
metadata=dict(recipes=len(specs),new_recipes=len(specs)-3,monthly_anchors=len(anchors),raw_span=[dates[0],dates[-1]],
    cohort_window=[dates[min(anchors)],dates[max(anchors)]],simultaneous_halfwidth=band,
    hypotheses='Asymmetric market response, trend quality, persistent highs, price-volume sequence, conditional universe, diversification, entry delay',
    bias='All historical exploratory: no untouched test set; 46 earlier recipes plus original bigwinner research already inspected',
    exception='User authorized research after confirming 2026-09-24 batch skipped; only today bypassed',
    details='Future price is used only for evaluation. Suspended/missing entries remain cash. Exits marked at last price. Dividends excluded. Slots with no signal remain cash.',
    stability='h180 has fewer mature cohorts, compare each recipe to baseline on its own identical dates. top2_to_cash is a hindsight stress, never a trade rule.')
(O/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
print(S[S.h==120].sort_values('delta_base',ascending=False)[['name','family','n','net','excess','delta_base','delta_base_lo','delta_base_hi','delta_amount','delta_amount_lo','delta_amount_hi','delta_2024','delta_2025','delta_2026']].round(4).to_string(index=False),flush=True)
