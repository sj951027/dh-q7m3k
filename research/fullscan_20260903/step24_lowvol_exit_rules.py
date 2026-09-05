# step24 (2026-09-05): #저변동 프로필 재채점용 — 조용함 상위10% 픽(3년, 5일 앵커, t+1 종가 진입)에 대해 '상태별' 이후 수익
#  상태(보유 k일 시점): 시장대비 rs ≤ −10%p / 손익 ≤ −7% / 손익 ≥ +15% / RSI 5일 −10pt 급락 / 20일선 아래 → 이후 20일 초과(유니버스 중앙값 대비)와 40일까지의 총 초과.
import numpy as np, pandas as pd, os
from fslib import *
P=Panel(); ok=guards(P); R=regimes(P); F=factors(P); start=P.idx("20240101"); c=P.close.astype(np.float64); N=P.N; T=P.T
quiet=rank_sum(F,["lv60","to20"],HYP,ok); rq=rank01(np.where(ok,quiet,np.nan))
med=np.nanmedian(np.where(ok,c,np.nan),axis=1)  # dummy
def cumret(a,b): 
    with np.errstate(all="ignore"): return c[b]/c[a]-1
def uni_med(a,b,mask):
    r=cumret(a,b); r=np.where(mask,r,np.nan); r[np.abs(r)>5]=np.nan; return np.nanmedian(r)
rsi=F["rsi14"]; s20=roll_mean(c,20,15)
anch=np.arange(start,T-41)[::5]
rows=[]
for k in [10,15,20]:
    conds={"전체":lambda i,a,e: np.ones(len(i),bool)}
    def rs_state(i,a,e,thr):   # e=a+k 시점 상태
        r=c[e,i]/c[a,i]-1; m=uni_med(a,e,ok[a]); return (r-m)<=thr
    conds[f"시장대비 ≤−10%p"]=lambda i,a,e: rs_state(i,a,e,-0.10)
    conds[f"시장대비 ≥+10%p"]=lambda i,a,e: ~rs_state(i,a,e,0.10)
    conds["손익 ≤−7%"]=lambda i,a,e: (c[e,i]/c[a,i]-1)<=-0.07
    conds["손익 ≥+15%"]=lambda i,a,e: (c[e,i]/c[a,i]-1)>=0.15
    conds["RSI 5일 −10pt↓"]=lambda i,a,e: (rsi[e,i]-rsi[e-5,i])<=-10
    conds["20일선 아래"]=lambda i,a,e: c[e,i]<s20[e,i]
    for nm,fn in conds.items():
        nxt=[]; tot40=[]; hold_vs_sell=[]; cnt=0; tot=0
        for a0 in anch:
            a=a0+1; e=a+k
            if e+20>=T: continue
            pick=np.where(rq[a0]>=0.9)[0]; pick=pick[np.isfinite(c[a,pick])&np.isfinite(c[e,pick])]
            if len(pick)<20: continue
            sel=pick[fn(pick,a,e)]; tot+=len(pick); cnt+=len(sel)
            if len(sel)<3: continue
            m20=uni_med(e,e+20,ok[e]); r20=c[e+20,sel]/c[e,sel]-1; r20=r20[np.isfinite(r20)&(np.abs(r20)<5)]
            nxt.append(np.nanmean(r20)-m20)
            b=a+40; m40=uni_med(a,b,ok[a]); r40=c[b,sel]/c[a,sel]-1; r40=r40[np.isfinite(r40)&(np.abs(r40)<5)]; tot40.append(np.nanmean(r40)-m40)
        m,lo,hi,n=boot_ci(nxt,500,block=4); m2,lo2,hi2,_=boot_ci(tot40,500,block=4)
        rows.append(dict(k=k,state=nm,share=cnt/max(tot,1),n_anchor=n,next20_exc_pp=m*100,lo=lo*100,hi=hi*100,total40_exc_pp=m2*100))
D=pd.DataFrame(rows); pd.set_option("display.width",250)
print("조용함 상위10% 픽 — 보유 k일 시점 상태별: 그 뒤 20일 초과(팔지 않았을 때 얻는 것, %p) · 40일 총 초과")
print(D.round(2).to_string(index=False)); D.to_csv(os.path.join(OUT,"lowvol_exit_states.csv"),index=False)
