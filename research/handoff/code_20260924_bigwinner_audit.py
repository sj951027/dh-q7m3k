"""Independent audit of Claude big-winner research. No imports from its scripts.
Reads SQLite read-only; writes only research/handoff/bigwinner_audit_20260924.
"""
from pathlib import Path
import sqlite3,json
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore',category=RuntimeWarning)

now=datetime.now(ZoneInfo('Asia/Seoul'))
assert not(now.weekday()<5 and '20:10'<=now.strftime('%H:%M')<='22:30')
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).with_name('bigwinner_audit_20260924');OUT.mkdir(exist_ok=True)
SOURCE=ROOT/'research/bigwinners_20260924/out_bw'
con=sqlite3.connect((ROOT.parent/'dh-q7m3k-data/ohlcv.db').as_uri()+'?mode=ro',uri=True)
con.execute('PRAGMA query_only=ON')
df=pd.read_sql_query('SELECT ticker,date,close,open,high,low,volume,shares,is_suspended,market FROM daily_ohlcv',con)
md=pd.read_sql_query('SELECT series,date,close FROM market_daily',con);con.close()
df=df[df.ticker.str.fullmatch(r'\d{6}')]
dates=np.array(sorted(df.date.unique()));ticks=np.array(sorted(df.ticker.unique()))
di={d:i for i,d in enumerate(dates)};ti={t:i for i,t in enumerate(ticks)}
r=df.date.map(di).to_numpy();j=df.ticker.map(ti).to_numpy();T,N=len(dates),len(ticks)
def mat(k):
    x=np.full((T,N),np.nan,dtype=np.float32);x[r,j]=df[k].to_numpy(dtype=np.float32);return x
c32=mat('close');c=c32.astype(float);v=mat('volume');shares=mat('shares');susp=mat('is_suspended')
mk=df.groupby('ticker').market.last().reindex(ticks).to_numpy();ki=mk=='KOSPI'
hi=mat('high').astype(float);lo=mat('low').astype(float)
md=md.pivot(index='date',columns='series',values='close').reindex(dates)
kp=md.KOSPI.to_numpy();kq=md.KOSDAQ.to_numpy()
del df
def lag(x,n):
    z=np.full_like(x,np.nan,dtype=float);z[n:]=x[:-n];return z
def roll(x,n,op='mean',minp=None):return getattr(pd.DataFrame(x).rolling(n,min_periods=minp or n),op)().to_numpy()
def rank(x):return pd.DataFrame(x).rank(axis=1,pct=True).to_numpy()
ret=c/lag(c,1)-1
flat=roll((abs(ret)<1e-9).astype(float),63,minp=20)>.5
jump=roll((abs(ret)>.32).astype(float),21,'max',5)>0
rv21=roll(ret,21,'std',15);amt20=roll(c32*v,20,minp=10)
ok=(~flat)&(~jump)&(rv21>=.003)&(amt20>=5e8)&(susp==0)&np.isfinite(c)
f=np.full_like(c,np.nan);f[:-121]=c[121:]/c[1:-120]-1
fc=f.copy();fc[abs(fc)>5]=np.nan
ik=np.full(T,np.nan);iq=ik.copy();ik[:-121]=kp[121:]/kp[1:-120]-1;iq[:-121]=kq[121:]/kq[1:-120]-1
ix=np.where(ki,ik[:,None],iq[:,None]);ex=fc-ix
E=(fc>=1)&(ex>=1);mask=ok&np.isfinite(fc)
episodes=0;unique=0
for jj in range(N):
    ws=np.flatnonzero(mask[:,jj]&E[:,jj]);last=-10000
    if len(ws):unique+=1
    for t in ws:
        if t-last>=120:episodes+=1;last=t
summary={'shape':[T,N],'base_obs':int(mask.sum()),'base_events':int((E&mask).sum()),'base_rate':float(E[mask].mean()),'episodes':episodes,'unique':unique,
    'excluded_above500':int((ok&(f>5)).sum()),'missing_future':int((ok[:-121]&~np.isfinite(f[:-121])).sum())}
rawmask=ok&np.isfinite(f);rawE=(f>=1)&(f-ix>=1)
summary['raw_rate']=float(rawE[rawmask].mean());summary['raw_events']=int(rawE[rawmask].sum())
mom252=c/lag(c,252)-1;mom21=c/lag(c,21)-1;mom=mom252-mom21
true_skip=lag(c,21)/lag(c,252)-1
lv60=roll(ret,60,'std',40)
mi=np.where(ki,(kp/lag(kp,1)-1)[:,None],(kq/lag(kq,1)-1)[:,None])
beta=(roll(ret*mi,60,minp=40)-roll(ret,60,minp=40)*roll(mi,60,minp=40))/roll(mi,60,'std',40)**2
rm=roll(c,252,'max',120);at_high=c>=rm*.999;cnt=np.full(N,np.nan);dsh=np.full_like(c,np.nan)
for t in range(T):cnt=np.where(at_high[t],0,cnt+1);dsh[t]=cnt
F={'mom12_1':mom,'mom252':mom252,'beta60':beta,'days_since_high':dsh,'size':np.log(c32*shares),
   'amt20':np.log(amt20),'lv60':lv60,'hl_range20':roll((hi-lo)/c,20,minp=10),'true_skip':true_skip}
R={n:rank(np.where(ok,x,np.nan)) for n,x in F.items()}
lift=[]
for n,direction in [('mom12_1',1),('mom252',1),('beta60',1),('lv60',-1),('hl_range20',-1)]:
    sel=mask&((R[n]>=.9) if direction==1 else(R[n]<.1))
    available=mask&np.isfinite(R[n])
    # Same date weighting as selected candidates, exact conditional null expectation.
    day_rate=(E&available).sum(1)/np.maximum(available.sum(1),1)
    expected=float(np.sum(sel.sum(1)*day_rate)/sel.sum())
    lift.append(dict(factor=n,n=int(sel.sum()),events=int((E&sel).sum()),selected_rate=float(E[sel].mean()),
        original_lift=float(E[sel].mean()/E[mask].mean()),availability_matched_lift=float(E[sel].mean()/E[available].mean()),
        date_matched_lift=float(E[sel].mean()/expected),expected_rate=expected))
pd.DataFrame(lift).to_csv(OUT/'lift_audit.csv',index=False)
print('base',summary,flush=True);print('lift',lift,flush=True)

def score(items):
    out=R[items[0][0]] if items[0][1]>0 else 1-R[items[0][0]]
    out=out.copy()
    for n,d in items[1:]:
        x=R[n] if d>0 else 1-R[n];out+=np.where(np.isfinite(x),x,.5)
    return out
base=[('mom12_1',1),('beta60',1),('days_since_high',-1)]
rules={'R1':score(base),'R1_amt':score(base+[('amt20',1)]),'R1_small_tilt':score(base+[('size',-1)]),
       'R1_minus_mom':score(base[1:]),'R1_true_skip':score([('true_skip',1),*base[1:]])}
anchors=[int(np.searchsorted(dates,mo+'01')) for mo in sorted({d[:6] for d in dates}) if mo>='202401']
mark=pd.DataFrame(c).ffill().to_numpy()
rows=[];selected=[]
for name,sc in rules.items():
    for t in anchors:
        end=t+121;e=t+1
        if end>=T:continue
        universe=ok[t]&np.isfinite(fc[t]);univ_p=ki[universe].mean()
        original_bench=univ_p*ik[t]+(1-univ_p)*iq[t]
        for mode in ['original','causal_uncapped']:
            cand=universe if mode=='original' else ok[t]
            s=np.where(cand,sc[t],np.nan)
            if np.isfinite(s).sum()<40:continue
            pick=np.argsort(-np.where(np.isfinite(s),s,-np.inf))[:20]
            pick_p=ki[pick].mean()
            fixed_bench=pick_p*ik[t]+(1-pick_p)*iq[t]
            entered=np.isfinite(c[e,pick])&(c[e,pick]>0)&(v[e,pick]>0)
            realized=fc[t,pick] if mode=='original' else np.where(entered,mark[end,pick]/c[e,pick]-1,0.)
            net=float(np.mean(realized))-.005
            rows.append(dict(name=name,mode=mode,date=dates[t],net=net,index_original=original_bench,
                index_matched=fixed_bench,ex_original=net-original_bench,ex_matched=net-fixed_bench,
                ex_ew=net-float(np.nanmean(fc[t,universe])),kospi_pick=pick_p,kospi_universe=univ_p,
                known_later_exclusions=int(np.sum(~np.isfinite(fc[t,pick]))),cap_exclusions=int(np.sum(f[t,pick]>5)),
                missing_exit=int(np.sum(~np.isfinite(c[end,pick]))),entry_failed=int((~entered).sum()),
                size_min=float(np.nanmin(R['size'][t,pick])),size_max=float(np.nanmax(R['size'][t,pick])),size_median=float(np.nanmedian(R['size'][t,pick]))))
            if name in ['R1','R1_amt']:
                for ident in pick:selected.append(dict(name=name,mode=mode,date=dates[t],ticker=ticks[ident]))
PT=pd.DataFrame(rows);PT.to_csv(OUT/'portfolio_audit.csv',index=False);pd.DataFrame(selected).to_csv(OUT/'picks.csv',index=False)
source=pd.read_csv(SOURCE/'r1_monthly_h120.csv',dtype={'anchor':str})
orig=PT[(PT.name=='R1')&(PT['mode']=='original')].merge(source,left_on='date',right_on='anchor',suffixes=('_audit','_claude'))
summary['reproduction_max_net_error']=float((orig.net-orig.ret).abs().max())
summary['reproduction_max_benchmark_error']=float((orig.index_original-orig.idx).abs().max())
assert summary['reproduction_max_net_error']<1e-9
assert summary['reproduction_max_benchmark_error']<1e-9
print('portfolios',PT.groupby(['name','mode'])[['net','ex_original','ex_matched','kospi_pick','kospi_universe','known_later_exclusions']].mean().round(5).to_string(),flush=True)

# Winners' drawdown from running peak vs loss from purchase price are different.
wt,wj=np.where(E&mask)
paths=np.stack([c[wt+1+k,wj]/c[wt+1,wj] for k in range(121)],axis=1)
dd=paths/np.fmax.accumulate(paths,axis=1)-1
pathmdd=np.nanmin(dd,axis=1);entrylow=np.nanmin(paths,axis=1)-1
summary['winner_paths']=dict(n=len(wt),median_mdd=float(np.median(pathmdd)),median_entry_low=float(np.median(entrylow)),
    p_mdd25=float(np.mean(pathmdd<-.25)),p_entry25=float(np.mean(entrylow<-.25)),
    p_entry10=float(np.mean(entrylow<=-.10)),p_mdd10=float(np.mean(pathmdd<=-.10)),
    p_entry7=float(np.mean(entrylow<=-.07)))
ep=pd.read_csv(SOURCE/'winner_episodes_h120.csv',dtype={'ticker':str,'date':str})
summary['episode_median_mdd']=float(ep.mdd_path.median())
summary['episode_score_available']=int(ep.R1_pct.notna().sum())
summary['episode_r1top20']=int((ep.R1_pct>=.8).sum())
summary['episode_top_rate_with_score']=float((ep.loc[ep.R1_pct.notna(),'R1_pct']>=.8).mean())

# Fixed stop simulation on ALL R1 monthly picks; close-based signal, sell next close.
# It is a diagnostic, not intraday execution. Never decide to sell using winner status.
stops=[]
for name in ['R1','R1_amt']:
    sc=rules[name]
    for t in anchors:
        e,end=t+1,t+121
        if end>=T:continue
        s=np.where(ok[t],sc[t],np.nan)
        if np.isfinite(s).sum()<40:continue
        pick=np.argsort(-np.where(np.isfinite(s),s,-np.inf))[:20]
        for threshold in [.07,.10,.25]:
            hold=[];sold=[];hits=0
            for ident in pick:
                if not(np.isfinite(c[e,ident]) and c[e,ident]>0 and v[e,ident]>0):hold.append(0.);sold.append(0.);continue
                path=mark[e:end+1,ident]/c[e,ident]-1
                hold.append(float(path[-1]-.005))
                hit=np.flatnonzero((path<=-threshold)&(np.arange(121)<120))
                exit_k=120
                if len(hit):
                    possible=np.flatnonzero((np.arange(121)>hit[0])&(v[e:end+1,ident]>0)&np.isfinite(c[e:end+1,ident]))
                    if len(possible):exit_k=int(possible[0]);hits+=1
                sold.append(float(path[exit_k]-.005))
            stops.append(dict(name=name,date=dates[t],stop=threshold,hold=float(np.mean(hold)),stop_return=float(np.mean(sold)),
                              difference=float(np.mean(sold)-np.mean(hold)),hits=hits))
pd.DataFrame(stops).to_csv(OUT/'stop_diagnostic.csv',index=False)
summary['stop_note']='All picked names; fixed loss from entry; trigger on close, execute at next tradable close; cash thereafter; no reinvestment'
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('summary',json.dumps(summary,ensure_ascii=False),flush=True)
print('DONE',OUT,flush=True)
