# step8: 3년 프록시 — 저변동 뼈대(lv60 / lv60+to20)에 변수 1개 추가 시 국면별 짝비교. 유니버스: 전체 / 과매도 프록시.
import numpy as np, pandas as pd, os, time
from fslib import *
t0=time.time(); P=Panel(); ok=guards(P); F=factors(P); R=regimes(P)
H=[5,20,60]; FW={h:excess(fwd(P,h),ok) for h in H}
ev=pd.read_csv(os.path.join(OUT,"dart_events_aligned.csv"),dtype={"ticker":str})
def flag_of(subs,days=60):
    f=np.zeros((P.T,P.N),bool)
    for r in ev[ev["sub"].isin(subs)].itertuples(): f[r.t:min(P.T,r.t+days+1),r.j]=True
    return f
F["ev_buyback60"]=flag_of(["buyback_trust","buyback_direct","buyback_trust_cancel","buyback_direct_cancel"]).astype(float)
F["ev_dilution60"]=flag_of(["cb","paid_in","bw","eb","paid_bonus_mix"]).astype(float)
# 추가 팩터
ret=P.ret; c=P.close.astype(np.float64)
dn=np.where(ret<0,ret,0.0); F["downvol60"]=roll_std(dn,60,40)
F["hl_range20"]=roll_mean((P.high-P.low)/P.close,20,10)
F["volvol20"]=roll_std(np.log1p(P.vol),20,10)
F["gapfreq60"]=roll_mean((np.abs(np.nan_to_num(P.open/np.vstack([np.full((1,P.N),np.nan),P.close[:-1]])-1))>0.03).astype(float),60,40)
F["amihud20"]=roll_mean(np.abs(ret)/np.maximum(P.amt,1),20,10)
kq=pd.Series(P.kosdaq).ffill().values; kqr=np.r_[np.nan,kq[1:]/kq[:-1]-1]
def beta60():
    x=pd.Series(kqr); out=np.full((P.T,P.N),np.nan)
    xv=x.rolling(60,min_periods=40).var().values
    cov=pd.DataFrame(ret*kqr[:,None]).rolling(60,min_periods=40).mean().values-pd.DataFrame(ret).rolling(60,min_periods=40).mean().values*x.rolling(60,min_periods=40).mean().values[:,None]
    return cov/xv[:,None]
F["beta60"]=beta60()
F["skew60"]=pd.DataFrame(ret).rolling(60,min_periods=40).skew().values
F["price_lvl"]=np.log(P.close)
HYP2=dict(HYP); HYP2.update({"ev_buyback60":+1,"ev_dilution60":-1,"downvol60":-1,"hl_range20":-1,"volvol20":-1,"gapfreq60":-1,"amihud20":+1,"beta60":-1,"skew60":-1,"price_lvl":+1})
start=P.idx("20240101")
osp=ok&(F["rsi14"]<50)&(F["dd52"]<-0.2)   # 과매도 프록시
U={"전체":ok,"과매도프록시":osp}
rows=[]
def ic_diff(sc,base_ic,M,h,label,extra):
    ic=spearman_rows(sc,FW[h],M); d=ic-base_ic; 
    for rg in ["전체","강세","조정","반등","약세"]:
        s=np.isfinite(d); s[:start]=False
        if rg!="전체": s&=(R.regime_pit.values==rg)
        v=d[s]; m,lo,hi,n=boot_ci(v,400,block=5)
        rows.append(dict(**extra,label=label,h=h,regime=rg,n=n,ic_base=float(np.nanmean(base_ic[s])),diff=m,lo=lo,hi=hi,pos=float(np.mean(v>0)) if n else np.nan))
for un,M in U.items():
    for bname,bf in [("lv60",["lv60"]),("lv60+to20",["lv60","to20"])]:
        base=rank_sum(F,bf,HYP2,M)
        for h in H:
            bic=spearman_rows(base,FW[h],M)
            for nm in HYP2:
                if nm in bf: continue
                x=np.where(M,F[nm]*HYP2[nm],np.nan); r=rank01(x); r=np.where(np.isfinite(r),r,0.5)
                ic_diff(base+r,bic,M,h,f"+{nm}",dict(universe=un,base=bname))
                if nm in ("ev_dilution60","on60"):   # 컷 형태
                    cut=M&~(F[nm]>0) if nm=="ev_dilution60" else M&~(rank01(np.where(M,F[nm],np.nan))>0.9)
                    ic=spearman_rows(base,FW[h],cut); d=ic-bic
                    for rg in ["전체","강세","조정","반등","약세"]:
                        s=np.isfinite(d); s[:start]=False
                        if rg!="전체": s&=(R.regime_pit.values==rg)
                        v=d[s]; m,lo,hi,n=boot_ci(v,400,block=5)
                        rows.append(dict(universe=un,base=bname,label=f"cut:{nm}",h=h,regime=rg,n=n,ic_base=float(np.nanmean(bic[s])),diff=m,lo=lo,hi=hi,pos=float(np.mean(v>0)) if n else np.nan))
            print(un,bname,h,round(time.time()-t0),flush=True)
res=pd.DataFrame(rows); res.to_csv(os.path.join(OUT,"lv_3yr_additive.csv"),index=False)
pd.set_option("display.width",250); pd.set_option("display.max_rows",600)
for un in U:
    for bname in ["lv60","lv60+to20"]:
        x=res[(res.universe==un)&(res.base==bname)&(res.h==20)].copy()
        x["cell"]=x.apply(lambda r: f"{r['diff']:+.3f}[{r.lo:+.2f},{r.hi:+.2f}]",axis=1)
        p=x.pivot(index="label",columns="regime",values="cell")
        dm=x.pivot(index="label",columns="regime",values="diff"); lo=x.pivot(index="label",columns="regime",values="lo")
        p["4국면CI>0"]=(lo[["강세","조정","반등","약세"]]>0).sum(axis=1); p["min"]=dm[["강세","조정","반등","약세"]].min(axis=1)
        print(f"===== {un} / base={bname} / h20"); print(p.sort_values("min",ascending=False).to_string())
print("done",time.time()-t0)
