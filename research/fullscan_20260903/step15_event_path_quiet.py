# step15 (2026-09-05): 3년 조용함 top20(lv60+to20, lv_b 뼈대) — 진입(t+1 종가) 후 k일 누적 초과(유니버스 중앙값 대비)·절대수익 경로. 국면별.
import numpy as np, pandas as pd, os
from fslib import *
P=Panel(); ok=guards(P); R=regimes(P); F=factors(P); start=P.idx("20240101"); c=P.close.astype(np.float64)
quiet=rank_sum(F,["lv60","to20"],HYP,ok); r=pd.DataFrame(np.where(ok,quiet,np.nan)).rank(axis=1,ascending=False).values; M=r<=20
K=40; rows=[]; rel=[]; ab=[]; rg=[]
for t in range(start,P.T-1-K):
    a=t+1; base=c[a]; 
    with np.errstate(all="ignore"): cum=c[a:a+K+1]/base-1   # (K+1,N)
    cum[np.abs(cum)>5]=np.nan
    u=ok[t]; m=M[t]
    if m.sum()<5: continue
    med=np.nanmedian(np.where(u,cum,np.nan),axis=1); top=np.nanmean(np.where(m,cum,np.nan),axis=1)
    rel.append(top-med); ab.append(top); rg.append(R.regime_pit.values[t])
rel=np.array(rel); ab=np.array(ab); rg=np.array(rg); print("anchors",len(rel))
for cut,sel in [("전체",np.ones(len(rg),bool))]+[(g,rg==g) for g in ["강세","조정","반등","약세"]]:
    if sel.sum()<10: continue
    for k in [1,2,3,5,10,15,20,25,30,40]:
        m,lo,hi,n=boot_ci(rel[sel,k],500,block=20)
        rows.append(dict(cut=cut,k=k,n=n,rel_cum_pct=round(m*100,2),lo=round(lo*100,2),hi=round(hi*100,2),abs_cum_pct=round(float(np.nanmean(ab[sel,k]))*100,2),
                         day_rel_bp=round(float(np.nanmean(rel[sel,k]-rel[sel,k-1]))*1e4,1)))
df=pd.DataFrame(rows); df.to_csv(os.path.join(OUT,"event_path_quiet.csv"),index=False)
print(df.to_string(index=False))
d=(rel[:,1:]-rel[:,:-1]).mean(axis=0)*1e4; print("일별 마진 초과(bp) k=1..40:"," ".join(f"{x:+.0f}" for x in d))
