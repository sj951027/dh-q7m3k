# step21 (2026-09-05): 포트 구성 격자 — 종목수 N(10/20/40) × 보유 k(20/40) × 비중(동일/순위가중/저변동가중) × 비용(0/0.5%왕복). 조용함 기준 + 조용함+nh252(추세 기울기).
import numpy as np, pandas as pd, os, time
from fslib import *
exec(open("step18_factor_zoo2.py",encoding="utf-8").read().split("H=[5,20,40,60]")[0])
HYP2=dict(HYP); HYP2["hl_range20"]=-1
scores={"조용함(lv60+to20)":rank_sum(F,["lv60","to20"],HYP2,ok),"조용함+nh252":rank_sum(F,["lv60","to20","nh252"],HYP2,ok),"조용함v2(to20+hl+volvol)":rank_sum(F,["to20","hl_range20","volvol20"],dict(HYP2,volvol20=-1),ok)}
lv=F["lv60"]
def run(sc,Nn,k,wmode,cost):
    r=rank01(np.where(ok,sc,np.nan)); T=P.T; s=np.zeros(T); n=np.zeros(T); tr=4
    for j in range(tr):
        t=start+j*(k//tr)
        while t+2<T:
            m=np.isfinite(r[t]); nn=m.sum()
            if nn<50: t+=k; continue
            sel=np.where(r[t]>=1-Nn/nn)[0]
            if wmode=="equal": w=np.ones(len(sel))
            elif wmode=="rank": w=r[t][sel]-(1-Nn/nn)+1e-6
            else: w=1/np.maximum(lv[t][sel],1e-4); w[~np.isfinite(w)]=0
            w=w/w.sum(); a=t+1
            for d in range(a+1,min(a+k+1,T)):
                with np.errstate(all="ignore"): rr=c[d]/c[d-1]-1
                v=rr[sel]; good=np.isfinite(v)&(np.abs(v)<1)
                if good.sum(): s[d]+=np.sum(v[good]*w[good])/w[good].sum(); n[d]+=1
            t+=k
    out=np.where(n>0,s/np.maximum(n,1),np.nan); out[:start+2]=np.nan
    out=out-cost/k   # 왕복비용을 보유기간에 균등 배분
    rs=pd.Series(out).dropna(); eq=(1+rs).cumprod(); yrs=len(rs)/252; cagr=eq.iloc[-1]**(1/yrs)-1; vol=rs.std()*np.sqrt(252); mdd=(eq/eq.cummax()-1).min()
    return dict(cagr=cagr,vol=vol,sharpe=cagr/vol,mdd=mdd)
rows=[]
for sn,sc in scores.items():
    for Nn in [10,20,40]:
        for k in [20,40]:
            for wm in ["equal","rank","invvol"]:
                for cost in [0.0,0.005]:
                    st=run(sc,Nn,k,wm,cost); st.update(score=sn,N=Nn,k=k,weight=wm,cost=cost); rows.append(st)
    print(sn,round(time.time()-t0,1),flush=True)
D=pd.DataFrame(rows); D.to_csv(os.path.join(OUT,"construction_grid.csv"),index=False)
pd.set_option("display.width",250)
print(D[D.cost==0.005].pivot_table(index=["score","N","k"],columns="weight",values=["cagr","sharpe","mdd"]).round(3).to_string())
print("done",round(time.time()-t0,1))
