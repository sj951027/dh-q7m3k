# step11: 문헌(arXiv 2512.14134) 검증 — 기관/외국인 순매수를 '시총'으로 정규화하면 단조 신호가 나온다는 주장. 2026-04~ 단일 국면.
import numpy as np, pandas as pd, os
from fslib import *
P=Panel(); ok=guards(P); F=factors(P)
H=[5,10,20]; FW={h:excess(fwd(P,h),ok) for h in H}
ti={k:i for i,k in enumerate(P.tick)}; di={d:i for i,d in enumerate(P.dates)}
fl=pd.read_sql("select ticker,date,foreign_net_val,inst_net_val,person_net_val from daily_flows",ro(OHLCV))
def to_mat(d,col):
    m=np.full((P.T,P.N),np.nan); d=d[d.ticker.isin(ti)&d.date.isin(di)]
    m[d.date.map(di).values,d.ticker.map(ti).values]=d[col].values.astype(float); return m
amt20=roll_mean(P.amt,20,10); mcap=P.mcap
rows=[]; start=P.idx("20260501")
for c in ["foreign","inst","person"]:
    m=to_mat(fl,c+"_net_val"); cov=roll_mean(np.isfinite(m).astype(float),20,10)>0.5
    for w in [5,20,60]:
        s=roll_mean(np.nan_to_num(m),w,max(3,w//2))*w
        for norm,den in [("amt",amt20*w),("mcap",mcap),("none",1.0)]:
            with np.errstate(all="ignore"): x=s/den
            x=np.where(cov,x,np.nan)
            for un,M in [("전체",ok),("대형30%",ok&(rank01(np.where(ok,F["size"],np.nan))>=0.7)),("중소형",ok&(rank01(np.where(ok,F["size"],np.nan))<0.7))]:
                for h in H:
                    ic=spearman_rows(x,FW[h],M)[start:]; ic=ic[np.isfinite(ic)]; mm,lo,hi,n=boot_ci(ic,400,block=5)
                    rows.append(dict(inv=c,w=w,norm=norm,uni=un,h=h,n=n,ic=mm,lo=lo,hi=hi,pos=float(np.mean(ic>0))))
df=pd.DataFrame(rows); df.to_csv(os.path.join(OUT,"flows_mcap_norm.csv"),index=False)
pd.set_option("display.width",250); pd.set_option("display.max_rows",300)
d=df[df.h==20].copy(); d["cell"]=d.apply(lambda r: f"{r.ic:+.3f}[{r.lo:+.2f},{r.hi:+.2f}]",axis=1)
print(d.pivot_table(index=["inv","w","norm"],columns="uni",values="cell",aggfunc="first").to_string())
# 십분위(대형, inst mcap 20d)
m=to_mat(fl,"inst_net_val"); cov=roll_mean(np.isfinite(m).astype(float),20,10)>0.5
x=np.where(cov,roll_mean(np.nan_to_num(m),20,10)*20/mcap,np.nan); M=ok
r=rank01(np.where(M,x,np.nan))
for dcl in range(10):
    sel=(r>dcl/10)&(r<=(dcl+1)/10)
    v=[np.nanmean(np.where(sel[t],FW[20][t],np.nan)) for t in range(start,P.T-21)]
    print("inst/mcap 20d 십분위",dcl+1,round(float(np.nanmean(v))*100,2),"%p")
