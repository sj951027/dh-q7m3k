# step4: 보유기간 k × 비용 × 국면 (조용함 top20 / 과매도 프록시 top20) + step5: 노출 조절(변동성 타게팅·breadth·SMA) 3년.
import numpy as np, pandas as pd, os, time
from fslib import *
t0=time.time(); P=Panel(); ok=guards(P); R=regimes(P); F=factors(P)
start=P.idx("20240101")
quiet=rank_sum(F,["lv60","to20"],HYP,ok)
os_ok=ok&(F["rsi14"]<40)
osc=np.where(os_ok,-F["rsi14"],np.nan)   # RSI 낮을수록 상위
c=P.close.astype(np.float64)
def topN_mask(score,N=20):
    r=pd.DataFrame(score).rank(axis=1,ascending=False).values
    return r<=N
masks={"조용함top20":topN_mask(np.where(ok,quiet,np.nan)),"과매도프록시top20(RSI최저)":topN_mask(osc),"조용함top20&RSI<50":topN_mask(np.where(ok&(F["rsi14"]<50),quiet,np.nan))}
ewm=ok
rows=[]
def kret(mask,k,t):
    a=t+ENTRY_LAG; b=a+k
    if b>=P.T: return np.nan
    with np.errstate(all="ignore"): r=c[b]/c[a]-1
    v=r[mask[t]]; v=v[np.isfinite(v)&(np.abs(v)<5)]
    return v.mean() if len(v)>=5 else np.nan
for nm,M in masks.items():
    for k in [1,5,10,20,40,60]:
        rr=np.array([kret(M,k,t) for t in range(start,P.T)]); ew=np.array([kret(ewm,k,t) for t in range(start,P.T)])
        rg=R.regime_pit.values[start:P.T]
        for cut,sel in [("전체",np.ones(len(rr),bool))]+[(g,rg==g) for g in ["강세","조정","반등","약세"]]:
            v=rr[sel]; e=ew[sel]; m=np.isfinite(v)&np.isfinite(e); v=v[m]; e=e[m]
            if len(v)<10: continue
            per20=v*20/k; ex20=(v-e)*20/k
            for cost in [0.0,0.005,0.008]:
                net=per20-cost*20/k
                mm,lo,hi,n=boot_ci(net,400,block=max(5,k))
                rows.append(dict(basket=nm,k=k,cut=cut,cost_rt=cost,n=n,ret_per20d=mm,lo=lo,hi=hi,excess_per20d=float(ex20.mean()),ew_per20d=float((e*20/k).mean()),win=float(np.mean(v>0))))
    print(nm,time.time()-t0,flush=True)
pd.DataFrame(rows).to_csv(os.path.join(OUT,"hold_k_cost.csv"),index=False)
# ---- step5: 일별 수익 시계열 (20일 리밸, 4트랜치) + 오버레이
def daily_series(M,k=20,tranches=4):
    T=P.T; series=np.zeros(T); cnt=np.zeros(T)
    for tr in range(tranches):
        t=start+tr*(k//tranches)
        while t+ENTRY_LAG+1<T:
            hold=M[t]; a=t+ENTRY_LAG
            for d in range(a+1,min(a+k+1,T)):
                with np.errstate(all="ignore"): r=c[d]/c[d-1]-1
                v=r[hold]; v=v[np.isfinite(v)&(np.abs(v)<1)]
                if len(v): series[d]+=v.mean(); cnt[d]+=1
            t+=k
    out=np.where(cnt>0,series/np.maximum(cnt,1),np.nan); out[:start+2]=np.nan
    return out
def stats(r):
    r=pd.Series(r).dropna(); eq=(1+r).cumprod(); mdd=(eq/eq.cummax()-1).min()
    yrs=len(r)/252; cagr=eq.iloc[-1]**(1/yrs)-1; vol=r.std()*np.sqrt(252)
    return dict(days=len(r),cagr=cagr,vol=vol,sharpe=cagr/vol if vol else np.nan,mdd=mdd,total=eq.iloc[-1]-1)
kq=pd.Series(P.kosdaq).ffill().values; kq_r=np.r_[np.nan,kq[1:]/kq[:-1]-1]; kq_r[:start+2]=np.nan
kp=pd.Series(P.kospi).ffill().values; kp_r=np.r_[np.nan,kp[1:]/kp[:-1]-1]; kp_r[:start+2]=np.nan
ew_r=np.nanmean(np.where(ok,P.ret,np.nan),axis=1); ew_r=np.r_[np.nan,ew_r[1:]]; ew_r[:start+2]=np.nan   # 가드 유니버스 EW(전일 가드 기준 아님 — 근사)
series={"KOSDAQ":kq_r,"KOSPI":kp_r,"전종목EW(가드)":ew_r,"조용함top20":daily_series(masks["조용함top20"]),"과매도프록시top20":daily_series(masks["과매도프록시top20(RSI최저)"])}
srows=[]
def overlay(r,w):
    w=pd.Series(w).shift(1).values  # 전일 정보로 오늘 비중
    return r*np.where(np.isfinite(w),w,1.0)
for nm,r in series.items():
    rs=pd.Series(r); vol20=rs.rolling(20).std()*np.sqrt(252)
    kq_sma20=kq>pd.Series(kq).rolling(20).mean().values; kq_sma60=kq>pd.Series(kq).rolling(60).mean().values
    br=R.breadth20.values
    variants={"없음":np.ones(P.T),
              "변동성타겟12%":np.minimum(1,0.12/vol20.values),"변동성타겟15%":np.minimum(1,0.15/vol20.values),"변동성타겟20%":np.minimum(1,0.20/vol20.values),
              "KOSDAQ>SMA20 아니면 0":kq_sma20.astype(float),"KOSDAQ>SMA60 아니면 0":kq_sma60.astype(float),
              "KOSDAQ<SMA20이면 50%":np.where(kq_sma20,1.0,0.5),"breadth<25%면 50%":np.where(br<0.25,0.5,1.0),"breadth<25%면 0":np.where(br<0.25,0.0,1.0),
              "변동성타겟15%+breadth<25%면 50%":np.minimum(1,0.15/vol20.values)*np.where(br<0.25,0.5,1.0)}
    for vn,w in variants.items():
        st=stats(overlay(r,w)); st.update(series=nm,overlay=vn,avg_w=float(np.nanmean(np.minimum(w,1)[start:]))); srows.append(st)
    # 국면별 일평균
S=pd.DataFrame(srows); S.to_csv(os.path.join(OUT,"overlay_stats.csv"),index=False)
pd.DataFrame({k:v for k,v in series.items()},index=P.dates).to_csv(os.path.join(OUT,"daily_series.csv"))
print(S.round(3).to_string()); print("done",time.time()-t0)
