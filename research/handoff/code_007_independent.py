"""REQUEST_007 independent offline audit. No imports of project calculations.
Run: python research/handoff/code_007_independent.py
Only reads npz/csv/parquet and SQLite mode=ro; writes nothing. Units: percentage points.
"""
from pathlib import Path
import sys, json, hashlib, sqlite3, warnings
import numpy as np
import pandas as pd
from scipy.stats import rankdata
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore', category=RuntimeWarning)
ROOT = Path(__file__).resolve().parents[2]
FS = ROOT/'research/fullscan_20260903'
DH = ROOT/'research/dart_history'

def emit(label, obj):
    print(label, json.dumps(obj, ensure_ascii=False, default=lambda x: x.item() if hasattr(x,'item') else str(x)), flush=True)

def roll(a,w,minp=None,kind='mean'):
    return getattr(pd.DataFrame(a).rolling(w,min_periods=minp or w),kind)().to_numpy().squeeze() if np.ndim(a)==1 else getattr(pd.DataFrame(a).rolling(w,min_periods=minp or w),kind)().to_numpy()

def lagret(a,k):
    out=np.full(a.shape,np.nan,dtype=float); out[k:]=a[k:]/a[:-k]-1; return out

def boot_indices(n,k):
    starts=np.random.default_rng(7).integers(0,max(n-40+1,1),(k,int(np.ceil(n/40))))
    return (starts[:,:,None]+np.arange(min(40,n))[None,None,:]).reshape(k,-1)[:,:n]

def ci(v,k=2000):
    v=np.asarray(v); return np.quantile(v[boot_indices(len(v),k)].mean(axis=1),[.025,.975]).tolist()

def rho(x,y):
    return float(np.corrcoef(rankdata(x),rankdata(y))[0,1])

def rhoboot(x,y):
    ix=boot_indices(len(x),1000)
    a=rankdata(x[ix],axis=1); b=rankdata(y[ix],axis=1)
    a-=a.mean(axis=1,keepdims=True); b-=b.mean(axis=1,keepdims=True)
    vals=(a*b).sum(axis=1)/np.sqrt((a*a).sum(axis=1)*(b*b).sum(axis=1))
    return np.quantile(vals,[.025,.975]).tolist()

def stats(v):
    return dict(n=len(v),mean=float(np.mean(v)),ci=ci(v))

def run():
    emit('ENV',dict(python=sys.version,numpy=np.__version__,pandas=pd.__version__))
    for p in [FS/'panel.npz',DH/'v30_hist_scores.parquet',DH/'v30_bars_3yr.csv']:
        emit('INPUT',dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest()))
    z=np.load(FS/'panel.npz',allow_pickle=True)
    d=z['dates'].astype(str); c=z['close'].astype(float); v=z['vol']; T,N=c.shape
    r=lagret(c,1); r[~np.isfinite(r)]=np.nan
    amt=z['close']*v
    ok=(roll((np.abs(r)<1e-9).astype(float),63,20)<=.5)&(roll((np.abs(r)>.32).astype(float),21,5,kind='max')<=0)&(roll(r,21,15,'std')>=.003)&(roll(amt,20,10)>=5e8)&(z['susp']==0)&np.isfinite(c)
    lv60=roll(r,60,40,'std'); lv20=roll(r,20,15,'std')
    hi=roll(c,252,120,'max'); lo=roll(c,252,120,'min')
    to=roll(v/z['shares'],20,10)
    obv=roll(np.sign(np.nan_to_num(r))*v,63,30)/roll(v,63,30)
    up=pd.DataFrame(np.where(r>0,r,0.)).ewm(alpha=1/14,min_periods=14).mean().to_numpy()
    dn=pd.DataFrame(np.where(r<0,-r,0.)).ewm(alpha=1/14,min_periods=14).mean().to_numpy()
    rsi=100-100/(1+up/dn)
    raw={'quiet':[-lv60,-to],'price4':[-lv60,-to,-lv20,c/hi-1],'rebound':[-(c/lo-1),-obv],'rsi':[-rsi]}
    start=int(np.searchsorted(d,'20240102'))
    f=np.full_like(c,np.nan); f[:-41]=(c[41:]/c[1:-40]-1)*100; f[np.abs(f)>500]=np.nan
    market=np.nanmean(np.where(ok,f,np.nan),axis=1)
    endret=(c[-1][None,:]/c-1)*100; endret[~np.isfinite(endret)|(np.abs(endret)>500)]=np.nan
    def terminal(mask):
        vals=[]
        for t in range(start,T-1):
            sel=mask[t]&np.isfinite(c[t+1])
            if sel.sum()>=5: vals.append(np.nanmean(endret[t+1,sel]))
        return float(np.nanmean(vals)),len(vals)
    mfinal,nfinal=terminal(ok)
    bars={}; names={'quiet':'조용함(lv_e뼈대)','price4':'가격4팩터(px_a)','rebound':'저점탈출(le_a뼈대)','rsi':'과매도프록시(RSI)'}
    saved=pd.read_csv(FS/'out/accumulate_3yr_bars.csv',dtype={'list_date':str})
    for nm,fac in raw.items():
        score=None
        for a in fac:
            ranks=pd.DataFrame(np.where(ok,a,np.nan)).rank(axis=1,pct=True).to_numpy()
            score=ranks if score is None else score+np.nan_to_num(ranks,nan=.5)
        select=pd.DataFrame(np.where(ok,score,np.nan)).rank(axis=1,ascending=False).to_numpy()<=20
        returns=np.where(select,f,np.nan); enough=np.isfinite(returns).sum(axis=1)>=5
        x=np.nanmean(returns,axis=1)-market
        mask=(np.arange(T)>=start)&(np.arange(T)<T-41)&enough
        bars[nm]=pd.Series(x[mask],index=d[mask]); last,nn=terminal(select)
        ref=saved[saved.skeleton==names[nm]].set_index('list_date').excess
        emit('R3',dict(model=nm,basket=last,market=mfinal,excess=last-mfinal,tranches=nn,max_csv_error=float((bars[nm]-ref).abs().max()),years={y:stats(s.to_numpy()) for y,s in bars[nm].groupby(bars[nm].index.str[:4])}))
    # Independently derive v30 basket returns from stored scores, not Claude's return CSV.
    sc=pd.read_parquet(DH/'v30_hist_scores.parquet'); sc=sc[sc.final_score_v3>-900].copy()
    ti={s:i for i,s in enumerate(z['tick'].astype(str))}; di={s:i for i,s in enumerate(d)}
    mk=pd.Series(z['mk']).str.lower().to_numpy(); vb={}; vm={}
    for (dt,m),g in sc.groupby(['run_id','market']):
        t=di.get(dt,-1)
        if t<0 or t+41>=T: continue
        # Original tie order is explicitly retained, not a new ticker tie rule.
        top=g.sort_values('final_score_v3',ascending=False,kind='stable').head(10)
        ix=[ti[s] for s in top.ticker if s in ti]
        a=c[t+41,ix]/c[t+1,ix]-1; b=c[t+41,mk==m]/c[t+1,mk==m]-1
        a=a[np.isfinite(a)]; b=b[np.isfinite(b)]
        if len(a)>=5 and len(b):
            vb.setdefault(dt,[]).append(100*(a.mean()-b.mean()))
            vm.setdefault(dt,[]).append(100*b.mean())
    bars['v30']=pd.Series({dt:np.mean(a) for dt,a in vb.items()})
    vr=pd.read_csv(DH/'v30_bars_3yr.csv',dtype={'list_date':str}).set_index('list_date').excess
    emit('V30_RETURN_CHECK',dict(n=len(bars['v30']),max_csv_error=float((bars['v30']-vr).abs().max())))
    W=pd.DataFrame(bars).sort_index(); low=W[['quiet','price4']].mean(axis=1); reb=W[['rebound','rsi','v30']].mean(axis=1); S=low-reb
    D=W.index; years=D.str[:4]; loc=np.array([di[s] for s in D]); oos=years>='2025'
    benchmark_term=(pd.Series({dt:np.mean(a) for dt,a in vm.items()}).reindex(D)-market[loc])/3
    for year in ('2024','2025','2026'):
        emit('BENCHMARK_DECOMPOSITION',dict(year=year,style_excess_gap=S[years==year].mean(),benchmark_contribution=benchmark_term[years==year].mean(),raw_basket_gap=(S-benchmark_term)[years==year].mean()))
    # Features are constructed independently from the raw panel.
    kq=pd.Series(z['kosdaq']).ffill().to_numpy(); kp=pd.Series(z['kospi']).ffill().to_numpy(); fx=pd.Series(z['usdkrw']).ffill().to_numpy()
    qr=lagret(kq,1); vol20=roll(qr,20,kind='std')*np.sqrt(252)
    goodr=ok&np.isfinite(r); upday=np.nanmean(np.where(goodr,(r>0).astype(float),np.nan),axis=1)
    nh=np.nanmean(np.where(ok,(c>=hi*.98).astype(float),np.nan),axis=1); nl=np.nanmean(np.where(ok,(c<=lo*1.02).astype(float),np.nan),axis=1)
    ret20=lagret(c,20); q=np.nanpercentile(np.where(ok,lv60,np.nan),[20,80],axis=1)
    spread=np.nanmean(np.where(ok&(lv60<=q[0,:,None]),ret20,np.nan),axis=1)-np.nanmean(np.where(ok&(lv60>=q[1,:,None]),ret20,np.nan),axis=1)
    al=np.nanmean(np.where(ok,amt,np.nan),axis=1)
    feats={'코스닥 5일 수익':lagret(kq,5),'코스닥 20일 수익':lagret(kq,20),'코스닥 60일 수익':lagret(kq,60),'코스피 20일 수익':lagret(kp,20),
      '코스닥 vs 20일선':kq/roll(kq,20)-1,'코스닥 vs 60일선':kq/roll(kq,60)-1,'코스닥 vs 120일선':kq/roll(kq,120)-1,
      '코스닥 20일 변동성':vol20,'코스닥 변동성 변화(20/60)':vol20/(roll(qr,60,kind='std')*np.sqrt(252)),
      '코스닥 252일 고점 대비':kq/roll(kq,252,120,'max')-1,
      '20일선 위 종목 비율':np.nanmean(np.where(ok,(c>roll(c,20,15)).astype(float),np.nan),axis=1),
      '60일선 위 종목 비율':np.nanmean(np.where(ok,(c>roll(c,60,40)).astype(float),np.nan),axis=1),
      '상승일 비율(5일)':roll(upday,5),'상승일 비율(20일)':roll(upday,20), '신고가 근접 비율':nh,'신저가 근접 비율':nl,'신고가−신저가':nh-nl,
      '종목 간 흩어짐(20일 수익 표준편차)':np.nanstd(np.where(ok,ret20,np.nan),axis=1),
      '지수 동행 비율(20일 평균)':roll(np.nanmean(np.where(goodr,np.sign(r)==np.sign(np.nan_to_num(qr))[:,None],np.nan),axis=1),20),
      '거래대금 수준(20/60)':roll(al,20)/roll(al,60),'환율 20일 변화':lagret(fx,20),'환율 vs 60일선':fx/roll(fx,60)-1,
      '저변동−고변동 최근 20일 수익':spread,'저변동−고변동 최근 60일 수익':roll(spread,60),
      '스타일 모멘텀(끝난 S 최근 20)':S.reindex(d).shift(41).rolling(20,min_periods=10).mean().to_numpy()}
    X=pd.DataFrame(feats,index=d).loc[D].replace([np.inf,-np.inf],np.nan)
    ref=pd.read_csv(FS/'out/style_predictors_3yr.csv').set_index('feature')
    stars=[]; corr_error=[]
    for name in X:
        valid=X[name].notna()&S.notna(); xx=X.loc[valid,name].to_numpy(); yy=S[valid].to_numpy()
        corr=rho(xx,yy); bounds=rhoboot(xx,yy); corr_error.append(abs(corr-ref.loc[name,'rho']))
        if bounds[0]>0 or bounds[1]<0:
            stars.append(name); emit('R6_STAR',dict(name=name,n=len(xx),rho=corr,ci=bounds,csv_rho=float(ref.loc[name,'rho'])))
    emit('R6_ALL',dict(n=len(S),feature_count=len(X.columns),stars=stars,max_rho_error=max(corr_error)))
    for y in ('2024','2025','2026'):
        sel=years==y; emit('BASELINE',dict(year=y,low=stats(low[sel]),S=stats(S[sel]),low_vs_5mix=float((low-W.mean(axis=1))[sel].mean())))
    known=S.shift(41); weights={'always_low':pd.Series(1.,index=D),'always_rebound':pd.Series(0.,index=D),'mix':pd.Series(.5,index=D)}
    for n in (10,20,40):
        mean=known.rolling(n,min_periods=n//2).mean()
        weights[f'winner{n}']=(mean>0).astype(float).where(mean.notna(),.5)
        weights[f'loser{n}']=(mean<0).astype(float).where(mean.notna(),.5)
    for th in (2,4):
        cur=1.; a=[]
        for val in known.rolling(20,min_periods=10).mean():
            if val>th:cur=1.
            elif val<-th:cur=0.
            a.append(cur)
        weights[f'hysteresis{th}']=pd.Series(a,index=D)
    kp20=X['코스피 20일 수익']; qvol=X['코스닥 변동성 변화(20/60)']; high=X['코스닥 252일 고점 대비']
    weights['kospi20']=(kp20>0).astype(float); weights['kosdaq20']=(X['코스닥 20일 수익']>0).astype(float)
    for th in (.03,.05,.10):weights[f'high{th}']=(high>-th).astype(float)
    weights['ma120']=(X['코스닥 vs 120일선']>0).astype(float)
    for n in (10,20):weights[f'vol{n}']=1-(qvol>1.2).astype(float).rolling(n,min_periods=1).max()
    weights['high_or_kp']=((high>-.05)|(kp20>0)).astype(float)
    weights['down_and_vol']=1-((kp20<0)&(qvol>1.2)).astype(float)
    a=low.shift(41).rolling(60,min_periods=20).std(); b=reb.shift(41).rolling(60,min_periods=20).std()
    weights['risk']=(b/(a+b)).fillna(.5); weights['70:30']=pd.Series(.7,index=D)
    from sklearn.linear_model import Ridge,LogisticRegression
    for kind in ('ridge','logit'):
        w=pd.Series(.5,index=D)
        for month in sorted(set(D.str[:6])):
            if month<'202407':continue
            te=D.str[:6]==month; first=np.where(te)[0][0]; bound=first-41
            tr=(np.arange(len(D))<=bound)&(known.notna())&X.notna().all(axis=1)&S.notna()
            if tr.sum()<80:continue
            xt=X[tr].to_numpy(); xtest=X[te].fillna(X[tr].median()).to_numpy(); mu=xt.mean(0); sd=xt.std(0)+1e-9
            xt=(xt-mu)/sd; xtest=(xtest-mu)/sd
            if kind=='ridge': pred=Ridge(alpha=10).fit(xt,S[tr]).predict(xtest)>0
            else:pred=LogisticRegression(C=.1,max_iter=500).fit(xt,S[tr]>0).predict_proba(xtest)[:,1]>.5
            w[te]=pred.astype(float)
        weights[kind]=w
    def evaluate(name,w,tag):
        diff=-(1-w)*S; a=diff[years=='2025']; b=diff[years=='2026']; v=diff[oos]
        row=dict(name=name,y2025=float(a.mean()),y2026=float(b.mean()),**stats(v))
        row['star']=bool(row['y2025']>0 and row['y2026']>0 and row['ci'][0]>0)
        emit(tag,row); return row
    r7rows=[evaluate(name,w,'R7') for name,w in weights.items()]
    ref7=pd.read_csv(FS/'out/selection_lab_3yr.csv')
    actual=np.array([[a['mean'],a['y2025'],a['y2026'],*a['ci']] for a in sorted(r7rows,key=lambda a:a['mean'])])
    expected=ref7.sort_values('oos_vs_low')[['oos_vs_low','2025_vs_low','2026_vs_low','oos_ci_lo','oos_ci_hi']].to_numpy()
    emit('R7_COMPARE',dict(rules=len(r7rows),max_csv_error=float(np.max(np.abs(actual-expected)))))
    dd=(-(1-weights['kospi20'])*S)[oos].to_numpy(); boot=dd[boot_indices(len(dd),2000)].mean(axis=1)
    emit('BOOT_EDGE',dict(sample_mean=dd.mean(),bootstrap_mean=boot.mean(),first40=dd[:40].mean(),last40=dd[-40:].mean()))
    # Distinguish replication from repairing the information set; same targets and yardsticks.
    for name in stars:
        x=X[name]; wraw=pd.Series(np.nan,index=D); wpit=wraw.copy()
        for year in ('2025','2026'):
            test=years==year; first=np.where(test)[0][0]
            rawtrain=(years<year)&x.notna(); pittrain=rawtrain&(loc+41<=loc[first])
            for train,ww in [(rawtrain,wraw),(pittrain,wpit)]:
                sign=np.sign(rho(x[train],S[train])); med=x[train].median(); ww[test]=(sign*(x[test]-med)>0).astype(float)
            emit('WF_TRAIN',dict(feature=name,year=year,unmatured=int((rawtrain&~pittrain).sum()),raw_n=int(rawtrain.sum()),pit_n=int(pittrain.sum())))
        evaluate(name,wraw,'R6_RAW_WF'); evaluate(name,wpit,'R6_MATURE_ONLY')
    # Four additional fixed hypotheses. No grid search or retuning after seeing results.
    crossing=(qvol>1.2)&(qvol.shift(1)<=1.2)
    new={'crossing_5days':1-crossing.astype(float).rolling(5,min_periods=1).max(),
         'reversal_60':(known.rolling(60,min_periods=30).mean()<0).astype(float).where(known.rolling(60,min_periods=30).mean().notna(),.5)}
    for kind in ('avoid_bad','dispersion_terciles'):
        w=pd.Series(1.,index=D)
        for year in ('2025','2026'):
            test=years==year; first=np.where(test)[0][0]; train=(years<year)&(loc+41<=loc[first])
            x=high if kind=='avoid_bad' else X['종목 간 흩어짐(20일 수익 표준편차)']
            if kind=='avoid_bad':
                cut=x[train].median(); group=(x>cut).astype(int)
                rates=[(reb[train&(group==g)]<-3).mean() for g in (0,1)]
                # pick rebound only in lower-bad-frequency bin; no tuned threshold.
                safe=int(np.argmin(rates)); w[test]=(group[test]!=safe).astype(float)
            else:
                cuts=x[train].quantile([1/3,2/3]).to_numpy(); group=np.digitize(x,cuts)
                for g in range(3):w[test&(group==g)]=float(S[train&(group==g)].mean()>0)
        new[kind]=w
    for name,w in new.items():evaluate(name,w,'NEW')
    for nm,s in bars.items():
        firsthalf=s[(s.index>='20240101')&(s.index<'20240701')]
        post=s[s.index>='20260810']
        emit('SELECTION_WINDOWS',dict(model=nm,firsthalf2024=stats(firsthalf),post20260810_n=len(post),last_complete=s.index.max()))
    # RO audit of backdated reports; no API calls, imports or financial amounts printed.
    con=sqlite3.connect(f'file:{DH / "dart_hist.db"}?mode=ro',uri=True)
    reports=con.execute("SELECT stock_code,year,reprt,api,fs,rcept_no,items FROM reports WHERE status='000' AND kept>0").fetchall();con.close()
    counts={}; examples=[]; delays=[]; dls={'Q1':'0515','H1':'0814','Q3':'1114','Y':'0331'}
    for stock,year,period,api,fs,rc,items in reports:
        deadline=pd.Timestamp(f'{int(year)+(period=="Y")}{dls[period]}')+pd.Timedelta(days=10); rec=str(rc or '')[:8]
        if len(rec)==8 and rec>deadline.strftime('%Y%m%d'):
            counts[period]=counts.get(period,0)+1; delays.append((pd.Timestamp(rec)-deadline).days)
            if len(examples)<4:examples.append(dict(stock=stock,year=year,period=period,actual_receipt=rec,assigned=deadline.strftime('%Y%m%d')))
    emit('PIT_BACKDATED',dict(total_reports=len(reports),backdated=sum(counts.values()),by_period=counts,median_days=float(np.median(delays)),max_days=max(delays),examples=examples))
    hist=sqlite3.connect(f'file:{ROOT/"history.db"}?mode=ro',uri=True)
    data=pd.read_sql_query("""SELECT v.run_id,v.market,v.ticker,v.final_score_v3,
        s.[foreign_5d_억] AS foreign5,s.[inst_5d_억] AS inst5,s.[amt_avg_1m_억] AS amount
        FROM v3_scores v LEFT JOIN stage3_final s
        ON v.run_id=s.run_id AND v.market=s.market AND v.ticker=s.ticker
        WHERE v.model_id='v30' AND v.run_id>='20260428'""",hist); hist.close()
    foreign=pd.to_numeric(data.foreign5,errors='coerce').fillna(0); inst=pd.to_numeric(data.inst5,errors='coerce').fillna(0)
    amount=pd.to_numeric(data.amount,errors='coerce').fillna(0).clip(lower=.1)
    intensity=(foreign+inst)/amount
    supply=np.select([intensity<=-.15,intensity>=.30,intensity>=.15,intensity>=.05],[-10,15,10,5],default=0)
    supply=np.clip(supply+3*((foreign>0)&(inst>0)),-10,15)
    data['nosupply']=data.final_score_v3-supply
    pairs={}; overlaps=[]; unusable=0; missing_groups=0
    for (dt,m),g in data[data.final_score_v3>-900].groupby(['run_id','market']):
        t=di.get(dt,-1)
        if t<0 or t+41>=T:continue
        if g.amount.isna().any():
            missing_groups+=1; continue
        picks=[]; vals=[]
        for field in ('final_score_v3','nosupply'):
            tickers=g.sort_values([field,'ticker'],ascending=[False,True],kind='stable').head(10).ticker.tolist()
            ix=[ti[s] for s in tickers if s in ti]; picks.append(set(tickers))
            if len(ix)!=10:unusable+=1;break
            rr=(c[t+41,ix]/c[t+1,ix]-1)*100
            if not np.isfinite(rr).all():unusable+=1;break
            vals.append(rr.mean())
        if len(vals)==2:pairs.setdefault(dt,[]).append(vals);overlaps.append(len(picks[0]&picks[1]))
    ab=pd.DataFrame({dt:np.mean(vals,axis=0) for dt,vals in pairs.items()}).T.sort_index()
    emit('SUPPLY_ABLATION',dict(data_start=data.run_id.min(),data_end=data.run_id.max(),missing_amount=int(data.amount.isna().sum()),missing_groups=missing_groups,unusable_groups=unusable,first=ab.index.min(),last=ab.index.max(),n=len(ab),full_mean=ab[0].mean(),nosupply_mean=ab[1].mean(),full_minus_removed=stats(ab[0]-ab[1]),mean_overlap=np.mean(overlaps),markets_per_day=pd.Series([len(pairs[dt]) for dt in ab.index]).value_counts().to_dict()))
    emit('SUPPLY_MISSING',data[data.amount.isna()].groupby(['run_id','market']).size().to_string())
    balanced=ab.loc[[dt for dt in ab.index if len(pairs[dt])==2]]
    emit('SUPPLY_BALANCED',dict(n=len(balanced),mean=float((balanced[0]-balanced[1]).mean()),note='Descriptive only: fewer than 40 dates; no block CI inference.'))
    from scipy.stats import binom
    emit('MULTIPLICITY',dict(R6_expected=25*.05,R6_independent_atleast4=float(binom.sf(3,25,.05)),R6_independent_any=1-.95**25,R7_positive_CI_expected_upper=24*.025,R7_independent_any_before_year_filter=1-.975**24))

if __name__=='__main__':run()
