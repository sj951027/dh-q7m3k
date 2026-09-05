# step18 (2026-09-05): 팩터 동물원 2차 — 가격·거래량·미시구조·리스크 신규 25종. 지평 h5/h20/h40/h60, 국면·연도·시장 안정성, 대손실 회피력.
#   채택 기준(사전): 전체 블록CI 0 제외 + 4국면 부호 일치 + 3연도 부호 일치. 산출 out/zoo2_ic.csv
import numpy as np, pandas as pd, os, time
from fslib import *
t0=time.time(); P=Panel(); ok=guards(P); R=regimes(P); F0=factors(P)
c=P.close.astype(np.float64); o=P.open.astype(np.float64); h=P.high.astype(np.float64); l=P.low.astype(np.float64); v=P.vol.astype(np.float64); ret=P.ret
N=P.N; start=P.idx("20240101")
def lag(a,k): return np.r_[np.full((k,N),np.nan),a[:-k]]
def rmean(a,w,m=None): return roll_mean(a,w,m or max(2,int(w*0.6)))
F={}
with np.errstate(all="ignore"):
    hl=(h-l)/c; F["hl_range20"]=rmean(hl,20)                                  # 일중 진폭(조용함 v2 성분)
    clv=np.where(h>l,(c-l)/(h-l),0.5); F["clv20"]=rmean(clv,20)                # 종가 위치(고가 쪽 마감 비율)
    gap=np.abs(o/lag(c,1)-1); F["gap_abs20"]=rmean(gap,20)                       # 야간 갭 크기
    F["upvol20"]=rmean(np.where(ret>0,v,0.0),20)/rmean(v,20)                     # 상승일 거래량 비중
    F["amihud20"]=np.log(rmean(np.abs(ret)/np.maximum(P.amt,1),20)+1e-12)       # 비유동성(가격충격)
    F["vol_dry"]=rmean(v,20)/rmean(v,120,60)                                     # 거래량 고갈(<1)
    F["vol_spike5"]=roll_max(v,5,3)/rmean(v,60,30)                               # 최근 거래량 급증
    F["updays5"]=rmean((ret>0).astype(float),5,5)                                # 최근 5일 상승일 비율
    F["skew60"]=pd.DataFrame(ret).rolling(60,min_periods=40).skew().values        # 수익 왜도
    F["volvol20"]=roll_std(roll_std(ret,5,4),20,15)                              # 변동성의 변동성
    F["lv_ratio"]=F0["lv20"]/F0["lv60"]                                         # 변동성 국면(단기/장기)
    F["sma60gap"]=c/rmean(c,60)-1; F["sma120gap"]=c/rmean(c,120,60)-1
    F["range_pos60"]=(c-roll_min(c,60,40))/(roll_max(c,60,40)-roll_min(c,60,40))
    F["min_ret20"]=roll_min(ret,20,15)                                           # 최근 최악 하루
    F["to_trend"]=F0["to20"]/rmean(P.vol/P.shares,120,60)                        # 회전율 추세
    F["logprice"]=np.log(c)
    dh=np.zeros_like(c); mx=roll_max(c,252,120); ishigh=(c>=mx*0.999)
    cnt=np.zeros(N)
    for t in range(P.T):
        cnt=np.where(ishigh[t],0,cnt+1); dh[t]=cnt
    F["days_since_high"]=dh
    # 지수 대비 베타·고유변동성 (시장별 지수, 60일)
    kq=pd.Series(P.kosdaq).ffill().pct_change().values; kp=pd.Series(P.kospi).ffill().pct_change().values
    idx=np.where((P.mk=="KOSPI")[None,:],kp[:,None],kq[:,None])
    cov=rmean(ret*idx,60,40)-rmean(ret,60,40)*rmean(idx,60,40); var=rmean(idx*idx,60,40)-rmean(idx,60,40)**2
    F["beta60"]=cov/var; resid=ret-F["beta60"]*idx; F["ivol60"]=roll_std(resid,60,40)
    F["idio_share"]=F["ivol60"]/F0["lv60"]                                       # 고유변동 비중
    F["mom_consist"]=rmean((ret>0).astype(float),126,80)                         # 6개월 상승일 비율
    F["ret_252"]=c/lag(c,252)-1
    F["down_beta"]=np.where(True, rmean(np.where(idx<0,ret*idx,0),60,40)/np.maximum(rmean(np.where(idx<0,idx*idx,0),60,40),1e-10),np.nan)
for k in F: F[k][~np.isfinite(F[k])]=np.nan
F.update({k:F0[k] for k in ["lv60","to20","nh252","mom12_1","size","max5_21","rsi14"]})   # 기준 팩터 동반
H=[5,20,40,60]; FW={}
for hh in H:
    globals()["ENTRY_LAG"]=1
    f=np.full_like(c,np.nan); a=1; b=1+hh
    with np.errstate(all="ignore"): f[:P.T-b]=c[b:]/c[a:P.T-b+a]-1
    f[np.abs(f)>5]=np.nan; FW[hh]=excess(f,ok)
loss20=(FW[20]<-0.10).astype(float); loss20[~np.isfinite(FW[20])]=np.nan   # 대손실(20일 −10%p 이하) 지표
anch_m=np.arange(start,P.T)[::21]
rows=[]
for nm,x in F.items():
    for hh in H:
        ic=spearman_rows(x,FW[hh],ok)
        vv=ic[start:]; vv=vv[np.isfinite(vv)]; m,lo,hi,n=boot_ci(vv,500,block=hh)
        rec=dict(factor=nm,h=hh,ic=m,lo=lo,hi=hi,n=n,pos=float(np.mean(vv>0)))
        rg=R.regime_pit.values
        for g in ["강세","조정","반등","약세"]:
            s=(rg==g)&np.isfinite(ic); s[:start]=False; rec[f"ic_{g}"]=float(np.nanmean(ic[s])) if s.sum()>=10 else np.nan
        for y in ["2024","2025","2026"]:
            s=np.array([d.startswith(y) for d in P.dates])&np.isfinite(ic); rec[f"ic_{y}"]=float(np.nanmean(ic[s])) if s.sum()>=10 else np.nan
        for mk in ["KOSPI","KOSDAQ"]:
            icm=spearman_rows(x,FW[hh],ok&(P.mk==mk)[None,:]); rec[f"ic_{mk}"]=float(np.nanmean(icm[start:]))
        if hh==20:
            icl=spearman_rows(x,-loss20,ok); rec["ic_avoid_loss"]=float(np.nanmean(icl[start:]))   # +면 값 클수록 대손실 회피
        sg=np.sign(m); same_rg=all(np.sign(rec[f"ic_{g}"])==sg for g in ["강세","조정","반등","약세"] if np.isfinite(rec[f"ic_{g}"]))
        same_yr=all(np.sign(rec[f"ic_{y}"])==sg for y in ["2024","2025","2026"] if np.isfinite(rec[f"ic_{y}"]))
        rec["robust"]=bool((lo>0 or hi<0) and same_rg and same_yr)
        rows.append(rec)
    print(nm,round(time.time()-t0,1),flush=True)
D=pd.DataFrame(rows); D.to_csv(os.path.join(OUT,"zoo2_ic.csv"),index=False)
pd.set_option("display.width",250)
show=D[D.h==20].sort_values("ic",key=abs,ascending=False)[["factor","ic","lo","hi","pos","ic_강세","ic_조정","ic_반등","ic_약세","ic_2024","ic_2025","ic_2026","ic_KOSPI","ic_KOSDAQ","ic_avoid_loss","robust"]]
print(show.round(3).to_string(index=False))
print("\nrobust(전체CI·4국면·3연도 부호 일치) by h:"); print(D[D.robust].groupby("h").factor.apply(list).to_string())
print("done",round(time.time()-t0,1))
