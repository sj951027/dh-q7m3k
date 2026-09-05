# step25: "5~6% 올랐다가 되밀려 횡보" 상태 — 조용함 상위10% 픽, 보유 k일 시점에 '최고 도달 수익(MFE) ≥ +5%인데 지금 손익 ≤ +1%' 인 종목의 이후 20일 초과 / 40일 총초과
import numpy as np, pandas as pd, os
from fslib import *
P=Panel(); ok=guards(P); F=factors(P); start=P.idx("20240101"); c=P.close.astype(np.float64); T=P.T
quiet=rank_sum(F,["lv60","to20"],HYP,ok); rq=rank01(np.where(ok,quiet,np.nan))
def uni_med(a,b):
    with np.errstate(all="ignore"): r=c[b]/c[a]-1
    r=np.where(ok[a],r,np.nan); r[np.abs(r)>5]=np.nan; return np.nanmedian(r)
anch=np.arange(start,T-41)[::5]; rows=[]
for k in [10,15,20]:
    for lab,fn in {"전체":lambda p,a,e,mfe,pnl: np.ones(len(p),bool),
                   "MFE≥5% & 지금≤+1% (되밀림)":lambda p,a,e,mfe,pnl:(mfe>=0.05)&(pnl<=0.01),
                   "MFE≥5% & 지금 ≥+3% (유지)":lambda p,a,e,mfe,pnl:(mfe>=0.05)&(pnl>=0.03),
                   "MFE<3% (한 번도 안 오름)":lambda p,a,e,mfe,pnl:(mfe<0.03),
                   "MFE≥5% & 고점대비 −5%↓ (트레일링 조건)":lambda p,a,e,mfe,pnl:(mfe>=0.05)&((1+pnl)/(1+mfe)-1<=-0.05)}.items():
        nxt=[]; tot=[]; share=[]
        for a0 in anch:
            a=a0+1; e=a+k
            if e+20>=T: continue
            p=np.where(rq[a0]>=0.9)[0]; p=p[np.isfinite(c[a,p])&np.isfinite(c[e,p])]
            if len(p)<20: continue
            with np.errstate(all="ignore"):
                mfe=np.nanmax(c[a+1:e+1,p],axis=0)/c[a,p]-1; pnl=c[e,p]/c[a,p]-1
            sel=p[fn(p,a,e,mfe,pnl)]; share.append(len(sel)/len(p))
            if len(sel)<3: continue
            r20=c[e+20,sel]/c[e,sel]-1; r20=r20[np.isfinite(r20)&(np.abs(r20)<5)]; nxt.append(np.nanmean(r20)-uni_med(e,e+20))
            r40=c[a+40,sel]/c[a,sel]-1; r40=r40[np.isfinite(r40)&(np.abs(r40)<5)]; tot.append(np.nanmean(r40)-uni_med(a,a+40))
        m,lo,hi,n=boot_ci(nxt,500,block=4); m2,_,_,_=boot_ci(tot,300,block=4)
        rows.append(dict(k=k,state=lab,share=np.mean(share),n=n,next20_exc_pp=m*100,lo=lo*100,hi=hi*100,total40_exc_pp=m2*100))
D=pd.DataFrame(rows); pd.set_option("display.width",250); print(D.round(2).to_string(index=False)); D.to_csv(os.path.join(OUT,"lowvol_giveback_states.csv"),index=False)
