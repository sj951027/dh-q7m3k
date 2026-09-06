# step26 (2026-09-06): 분할 진입(트랜치) 효과 — 조용함(lv60+to20) N10/N20 · k=40 · 동일가중 · 왕복 0.5%.
#   tr=1(한 번에 전량) vs tr=2 vs tr=4, 시작일 오프셋을 바꿔 '어느 날 시작했느냐'에 따른 결과 분산(경로 의존)을 잰다.
#   OPS_GUIDE §1 '4트랜치' 항목의 근거 수치용. 관측 전용.
import numpy as np, pandas as pd, os, time
from fslib import *
exec(open("step18_factor_zoo2.py",encoding="utf-8").read().split("H=[5,20,40,60]")[0])
HYP2=dict(HYP); HYP2["hl_range20"]=-1
sc=rank_sum(F,["lv60","to20"],HYP2,ok)
def run(Nn,k,tr,off,cost=0.005):
    r=rank01(np.where(ok,sc,np.nan)); T=P.T; s=np.zeros(T); n=np.zeros(T)
    for j in range(tr):
        t=start+off+j*(k//tr)
        while t+2<T:
            m=np.isfinite(r[t]); nn=m.sum()
            if nn<50: t+=k; continue
            sel=np.where(r[t]>=1-Nn/nn)[0]; w=np.ones(len(sel))/len(sel); a=t+1
            for d in range(a+1,min(a+k+1,T)):
                with np.errstate(all="ignore"): rr=c[d]/c[d-1]-1
                v=rr[sel]; good=np.isfinite(v)&(np.abs(v)<1)
                if good.sum(): s[d]+=np.sum(v[good]*w[good])/w[good].sum(); n[d]+=1
            t+=k
    out=np.where(n>0,s/np.maximum(n,1),np.nan); out[:start+off+2]=np.nan; out=out-cost/k
    rs=pd.Series(out).dropna(); eq=(1+rs).cumprod(); yrs=len(rs)/252; cagr=eq.iloc[-1]**(1/yrs)-1; vol=rs.std()*np.sqrt(252); mdd=(eq/eq.cummax()-1).min()
    return dict(cagr=cagr,sharpe=cagr/vol if vol>0 else np.nan,mdd=mdd)
rows=[]
for Nn in (10,20):
    for tr,offs in ((1,range(0,40,5)),(2,range(0,20,5)),(4,range(0,10,2))):
        for off in offs:
            st=run(Nn,40,tr,off); st.update(N=Nn,tr=tr,off=off); rows.append(st)
    print("N",Nn,round(time.time()-t0,1),flush=True)
D=pd.DataFrame(rows); D.to_csv(os.path.join(OUT,"tranche_grid.csv"),index=False)
g=D.groupby(["N","tr"]).agg(cagr_mean=("cagr","mean"),cagr_min=("cagr","min"),cagr_max=("cagr","max"),cagr_sd=("cagr","std"),sharpe=("sharpe","mean"),mdd_mean=("mdd","mean"),mdd_worst=("mdd","min"),n=("off","count"))
print((g*1).round(3).to_string()); print("done",round(time.time()-t0,1))
