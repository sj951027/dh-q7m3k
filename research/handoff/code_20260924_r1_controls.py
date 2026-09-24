"""R1 controls and self-financing monthly 1/6 allocation. Exploratory only.
Today's batch-window exception requires explicit --batch-skipped-date 20260924.
"""
from pathlib import Path
import argparse,json,sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from code_20260924_pattern_scan import block_ci

args=argparse.ArgumentParser();args.add_argument('--batch-skipped-date');args=args.parse_args()
now=datetime.now(ZoneInfo('Asia/Seoul'))
blocked=now.weekday()<5 and '20:10'<=now.strftime('%H:%M')<='22:30'
if blocked and not(args.batch_skipped_date==now.strftime('%Y%m%d')=='20260924'):
    raise RuntimeError('Batch window; no explicit exception for this date')
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).with_name('r1_controls_20260924');OUT.mkdir(exist_ok=True)
con=sqlite3.connect((ROOT.parent/'dh-q7m3k-data/ohlcv.db').as_uri()+'?mode=ro',uri=True);con.execute('PRAGMA query_only=ON')
df=pd.read_sql_query('SELECT ticker,date,close,volume,shares,is_suspended,market FROM daily_ohlcv',con)
md=pd.read_sql_query('SELECT series,date,close FROM market_daily',con);con.close()
df=df[df.ticker.str.fullmatch(r'\d{6}')]
dates=np.array(sorted(df.date.unique()));ticks=np.array(sorted(df.ticker.unique()));T,N=len(dates),len(ticks)
rr=df.date.map({d:i for i,d in enumerate(dates)}).to_numpy();cc=df.ticker.map({t:i for i,t in enumerate(ticks)}).to_numpy()
def mat(k):
    x=np.full((T,N),np.nan,np.float32);x[rr,cc]=df[k].to_numpy(dtype=np.float32);return x
c32=mat('close');c=c32.astype(float);v=mat('volume');shares=mat('shares');susp=mat('is_suspended')
mk=df.groupby('ticker').market.last().reindex(ticks).to_numpy();ki=mk=='KOSPI';del df
md=md.pivot(index='date',columns='series',values='close').reindex(dates);kp=md.KOSPI.to_numpy();kq=md.KOSDAQ.to_numpy()
def lag(x,n):
    a=np.full_like(x,np.nan,dtype=float);a[n:]=x[:-n];return a
def roll(x,n,op='mean',minp=None):return getattr(pd.DataFrame(x).rolling(n,min_periods=minp or n),op)().to_numpy()
def rank(x):return pd.DataFrame(x).rank(axis=1,pct=True).to_numpy()
ret=c/lag(c,1)-1;amt=roll(c32*v,20,minp=10)
ok=(roll((abs(ret)<1e-9).astype(float),63,minp=20)<=.5)&(roll((abs(ret)>.32).astype(float),21,'max',5)<=0)&(roll(ret,21,'std',15)>=.003)&(amt>=5e8)&(susp==0)&np.isfinite(c)
mi=np.where(ki,(kp/lag(kp,1)-1)[:,None],(kq/lag(kq,1)-1)[:,None])
beta=(roll(ret*mi,60,minp=40)-roll(ret,60,minp=40)*roll(mi,60,minp=40))/roll(mi,60,'std',40)**2
high=roll(c,252,'max',120);dsh=np.full_like(c,np.nan);cnt=np.full(N,np.nan)
for t in range(T):cnt=np.where(c[t]>=high[t]*.999,0,cnt+1);dsh[t]=cnt
F={'mom':c/lag(c,252)-c/lag(c,21),'beta':beta,'near':-dsh,'amount':np.log(amt),'size':np.log(c32*shares)}
# Preserve original tie direction for days_since_high: 1 - rank(days_since_high).
R={k:rank(np.where(ok,x,np.nan)) for k,x in F.items()};R['near']=1-rank(np.where(ok,dsh,np.nan))
def score(keys):
    sc=R[keys[0]].copy()
    for k in keys[1:]:sc+=np.where(np.isfinite(R[k]),R[k],.5)
    return sc
specs={'R1':['mom','beta','near'],'R1_amount':['mom','beta','near','amount'],
       'beta_near':['beta','near'],'size_only':['size'],'amount_only':['amount'],
       'beta_only':['beta'],'momentum_only':['mom'],'near_only':['near']}
scores={k:score(vv) for k,vv in specs.items()}
prior=pd.read_csv(Path(__file__).with_name('bigwinner_audit_20260924')/'portfolio_audit.csv',dtype={'date':str})
prior=prior[(prior.name=='R1')&(prior['mode']=='causal_uncapped')]
anchors=[int(np.searchsorted(dates,d)) for d in prior.date]
mark=pd.DataFrame(c).ffill().to_numpy();cost=.005
picks={};cohorts=[];holdings=[]
for name,sc in scores.items():
    for t in anchors:
        e,end=t+1,t+121;s=np.where(ok[t],sc[t],np.nan)
        assert np.isfinite(s).sum()>=40
        ids=np.argsort(-np.where(np.isfinite(s),s,-np.inf))[:20];picks[name,t]=ids
        filled=np.isfinite(c[e,ids])&(c[e,ids]>0)&(v[e,ids]>0)
        gross=np.where(filled,mark[end,ids]/c[e,ids]-1,0.);net=float(np.mean(gross)-cost*filled.mean())
        w=ki[ids].mean();bench=w*(kp[end]/kp[e]-1)+(1-w)*(kq[end]/kq[e]-1)
        cohorts.append(dict(name=name,date=dates[t],net=net,benchmark=bench,excess=net-bench,kospi=w,
                            n_filled=int(filled.sum()),missing_exit=int(np.sum(~np.isfinite(c[end,ids])))))
        for j,ident in enumerate(ids):holdings.append(dict(name=name,date=dates[t],ticker=ticks[ident],gross=float(gross[j]),filled=bool(filled[j])))
C=pd.DataFrame(cohorts);C.to_csv(OUT/'cohorts.csv',index=False)
H=pd.DataFrame(holdings);H.to_csv(OUT/'holdings.csv',index=False)
repro=C[C.name=='R1'].merge(prior,on='date')
assert np.max(np.abs(repro.net_x-repro.net_y))<1e-10
summary=[]
for name,g in C.groupby('name',sort=False):
    row={'name':name,'n':len(g)}
    for k in ['net','excess']:
        mu,lo,hi,n=block_ci(g[k],6);row.update({k:mu,k+'_lo':lo,k+'_hi':hi})
    summary.append(row)
S=pd.DataFrame(summary);S.to_csv(OUT/'summary.csv',index=False)
paired=[]
for a in ['R1','R1_amount','beta_near']:
    for b in specs:
        if a==b:continue
        x=C[C.name==a].set_index('date');y=C[C.name==b].set_index('date')
        for metric in ['net','excess']:
            mu,lo,hi,n=block_ci(x[metric]-y[metric],6)
            paired.append(dict(a=a,b=b,metric=metric,difference=mu,lo=lo,hi=hi,n=n))
pd.DataFrame(paired).to_csv(OUT/'paired.csv',index=False)
print(S.round(4).to_string(index=False),flush=True)

# Simulation uses actual cash: spend <= available cash, never reset weights daily.
# Stock exit after day120 occurs only on a day with volume>0 and observed price.
start=min(anchors)+1;finish=max(anchors)+121
schedule={t+1:t for t in anchors};half=cost/2
def simulate(name,index_match=False):
    cash=1.;positions=[];path=[];buys=[];limited=0;delayed=0
    for day in range(start,finish+1):
        keep=[]
        for pos in positions:
            price=(kp[day] if pos['id']==-1 else kq[day] if pos['id']==-2 else mark[day,pos['id']])
            tradable=pos['id']<0 or (v[day,pos['id']]>0 and np.isfinite(c[day,pos['id']]))
            if day>=pos['due'] and tradable:cash+=pos['units']*price*(1-half)
            else:
                if day==pos['due'] and not tradable:delayed+=1
                keep.append(pos)
        positions=keep
        equity_before=cash+sum(p['units']*(kp[day] if p['id']==-1 else kq[day] if p['id']==-2 else mark[day,p['id']]) for p in positions)
        if day in schedule:
            t=schedule[day];ids=picks[name,t]
            target=equity_before/6;budget=min(target,cash/(1+half))
            limited+=int(budget<target-1e-10)
            weights={-1:float(ki[ids].mean()),-2:float((~ki[ids]).mean())} if index_match else {int(j):.05 for j in ids}
            invested=0.
            for ident,weight in weights.items():
                if weight<=0:continue
                tradable=ident<0 or (np.isfinite(c[day,ident]) and c[day,ident]>0 and v[day,ident]>0)
                if not tradable:continue
                price=kp[day] if ident==-1 else kq[day] if ident==-2 else c[day,ident]
                val=budget*weight;positions.append({'id':ident,'units':val/price,'due':day+120});cash-=val*(1+half);invested+=val
            buys.append(dict(name=name,matched=index_match,date=dates[day],nav_before=equity_before,target=target,invested=invested,cash_after=cash))
        value=sum(p['units']*(kp[day] if p['id']==-1 else kq[day] if p['id']==-2 else mark[day,p['id']]) for p in positions)
        nav=cash+value
        assert cash>=-1e-10 and np.isfinite(nav) and nav>0
        path.append(dict(name=name,matched=index_match,date=dates[day],nav=nav,cash=cash,exposure=value/nav,positions=len(positions)))
    assert len(buys)==len(anchors)
    ar=np.r_[1.,[x['nav'] for x in path]]
    result=dict(name=name,matched=index_match,start=dates[start],end=dates[finish],n_entries=len(buys),
                total=float(ar[-1]-1),cagr=float(ar[-1]**(252/(finish-start))-1),mdd=float(np.min(ar/np.maximum.accumulate(ar)-1)),
                average_exposure=float(np.mean([x['exposure'] for x in path])),cash_limited_entries=limited,delayed_exits=delayed,
                remaining_positions=len(positions),final_cash=cash)
    return result,path,buys
accounts=[];paths=[];orders=[]
for name in specs:
    for matched in [False,True]:
        s,p,b=simulate(name,matched);accounts.append(s);paths.extend(p);orders.extend(b)
A=pd.DataFrame(accounts);A.to_csv(OUT/'accounts.csv',index=False)
pd.DataFrame(paths).to_csv(OUT/'account_paths.csv',index=False);pd.DataFrame(orders).to_csv(OUT/'orders.csv',index=False)
# Separate fully invested buy-and-hold index reference (different cash profile).
indexnav=.5*kp[start:finish+1]/kp[start]+.5*kq[start:finish+1]/kq[start]
indexnav=indexnav/(1+half);indexnav[-1]*=1-half
idxar=np.r_[1.,indexnav]
benchmark=dict(total=float(indexnav[-1]-1),cagr=float(indexnav[-1]**(252/(finish-start))-1),mdd=float(np.min(idxar/np.maximum.accumulate(idxar)-1)))
contribution=H.groupby(['name','ticker']).gross.sum()/400
contribution.rename('mean_cohort_gross_contribution').reset_index().to_csv(OUT/'ticker_contributions.csv',index=False)
meta=dict(batch_exception='User explicitly stated 2026-09-24 batch was skipped and authorized continuation',
          selection_start=dates[min(anchors)],selection_end=dates[max(anchors)],account_start=dates[start],account_end=dates[finish],
          horizon=120,n_months=len(anchors),cost_roundtrip=.005,stock_slots=20,allocation='NAV/6 monthly, capped by cash including entry fee; no borrowing',
          benchmark_buyhold_50_50=benchmark,reproduction_max_error=float(np.max(np.abs(repro.net_x-repro.net_y))),
          latest_listing_market='Same last-observed market labels as R1 source; historical market transfers not audited',
          notes=['No fresh OOS: these periods and candidates already inspected','Estimated historical shares and survivor/backfill bias remain',
                 'Entry at next close; no realistic limit-up fill or price impact model','Cohort exit marks last close; account exits postpone if suspended',
                 'Monthly cohort returns subtract fixed cost; account charges actual buy/sell value at 0.25% per side',
                 'No dividends, no cash interest. Account metrics are descriptive, not confidence intervals',
                 '20 complete entry cohorts: entry stops in March2026 and remaining positions run off; this is a closed study window'])
(OUT/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
print('ACCOUNTS\n',A.round(4).to_string(index=False),flush=True);print('BENCHMARK',benchmark,flush=True)
