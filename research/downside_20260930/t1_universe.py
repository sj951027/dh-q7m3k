# T1 — 전 종목 3년: 플래그 종목의 이후 시장 초과·하위10% 적중 배수·변동성 분위 통제·연도별
import numpy as np, pandas as pd, flags as fl
F=fl.build(); C=fl.C; R=fl.R; G=fl.GUARD; MK=fl.MK
def fwd(h):
    e=C.shift(-1); x=C.shift(-1-h); f=x/e-1
    jm=R.abs()[::-1].rolling(h+1,min_periods=1).max()[::-1].shift(-1)
    return f.where(jm<=0.5)   # 보유 중 ±50% 점프(데이터 오류·액면) 제외
FW={20:fwd(20),40:fwd(40)}
lv60=R.rolling(60,min_periods=40).std()
def bci(x,block,reps=3000,seed=930):
    x=np.asarray(x,float); x=x[np.isfinite(x)]; L=len(x)
    if L<8: return (np.nan,np.nan,np.nan)
    rng=np.random.default_rng(seed); st=rng.integers(0,L,(reps,int(np.ceil(L/block)))); ix=(st[:,:,None]+np.arange(block))%L
    mm=x[ix.reshape(reps,-1)[:,:L]].mean(axis=1); return (x.mean(),np.quantile(mm,.025),np.quantile(mm,.975))
start=fl.TI[[d for d in fl.DATES if d>='20231002'][0]]
rows=[]
for name,Fm in F.items():
    for h in(20,40):
        f=FW[h]; days=[]
        for i in range(start,len(fl.DATES)-h-2):
            d=fl.DATES[i]; ex=[];lift=[];crash=[];ctl=[];prev=[]
            for m in('kospi','kosdaq'):
                idx=MK.index[MK==m]
                g=G.iloc[i][idx].values; fi=f.iloc[i][idx].values; fg=Fm.iloc[i][idx].values; lv=lv60.iloc[i][idx].values
                ok=g&np.isfinite(fi)
                if ok.sum()<100: continue
                prev.append(fg[ok].mean())
                if (fg&ok).sum()<1: continue
                base=fi[ok].mean(); ex.append(fi[fg&ok].mean()-base)
                q10=np.quantile(fi[ok],0.10); lift.append(((fi[fg&ok]<=q10).mean())/0.10)
                crash.append((fi[fg&ok]<=-0.20).mean()/max(1e-9,(fi[ok]<=-0.20).mean()))
                okv=ok&np.isfinite(lv); qs=pd.qcut(pd.Series(lv[okv]).rank(method='first'),5,labels=False).values
                fv=fi[okv]; fgv=fg[okv]; cd=[]
                for b in range(5):
                    a=fv[(qs==b)&fgv]; c_=fv[(qs==b)&~fgv]
                    if len(a)>=2 and len(c_)>=10: cd.append(a.mean()-c_.mean())
                if cd: ctl.append(np.mean(cd))
            if ex: days.append((d,np.mean(ex),np.mean(lift),np.mean(crash),np.mean(ctl) if ctl else np.nan,np.mean(prev)))
        D=pd.DataFrame(days,columns=['d','ex','lift','crash','ctl','prev'])
        if D.empty: continue
        e=bci(D.ex,h); c=bci(D.ctl.dropna(),h)
        yr=D.groupby(D.d.str[:4]).ex.mean()
        rows.append(dict(flag=name,h=h,days=len(D),prev=D.prev.mean(),ex=e[0],ex_lo=e[1],ex_hi=e[2],lift10=D.lift.mean(),crash20=D.crash.mean(),
                         ctl=c[0],ctl_lo=c[1],ctl_hi=c[2],**{f"y{y}":v for y,v in yr.items()}))
out=pd.DataFrame(rows); out.to_csv("t1_universe.csv",index=False)
pd.set_option('display.width',250); pd.set_option('display.max_columns',30)
fmt=out.copy()
for c_ in [c for c in out.columns if c.startswith(('ex','ctl','y2'))]: fmt[c_]=(out[c_]*100).round(2)
fmt['prev']=(out.prev*100).round(1); fmt['lift10']=out.lift10.round(2); fmt['crash20']=out.crash20.round(2)
print(fmt.to_string(index=False))
