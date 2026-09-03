# step2: 전종목 가격팩터 3년 안정성 — 국면별·연도별·시장별 h20 signed IC, 십분위 초과수익, 조합 순위합.
# 앵커: 월간 비중첩(21일 간격) 주표 + 전일 앵커(주블록 부트) 보조. 산출 out/factor_*.csv
import numpy as np, pandas as pd, os, time
from fslib import *
t0=time.time(); P=Panel(); ok=guards(P); R=regimes(P); F=factors(P)
H=[5,20,60]; FW={h:excess(fwd(P,h),ok) for h in H}
names=list(HYP.keys())
start=P.idx("20240101")   # 252일 룩백 확보 후
anchors_all=np.arange(start,P.T)
anchors_m=anchors_all[::21]
rows=[]
def summarize(ic,mask_name,sel):
    v=ic[sel]; m,lo,hi,n=boot_ci(v,1000)
    return dict(n=n,ic=m,lo=lo,hi=hi,pos=float(np.nanmean(v>0)) if n else np.nan)
for nm in names:
    x=F[nm]*HYP[nm]
    for h in H:
        ic=spearman_rows(x,FW[h],ok)
        base=dict(factor=nm,h=h)
        sel=np.zeros(P.T,bool); sel[anchors_m]=True
        rows.append({**base,"cut":"all_monthly",**summarize(ic,"",sel&np.isfinite(ic))})
        v=ic[start:]; v=v[np.isfinite(v)]; m,lo,hi,n=boot_ci(v,600,block=5)
        rows.append(dict(base,cut="all_daily_block5",n=n,ic=m,lo=lo,hi=hi,pos=float(np.mean(v>0))))
        for y in ["2024","2025","2026"]:
            s=sel&np.array([d.startswith(y) for d in P.dates])&np.isfinite(ic)
            rows.append({**base,"cut":"year_"+y,**summarize(ic,"",s)})
        for rg in ["강세","조정","반등","약세"]:
            s=(R.regime_pit.values==rg)&np.isfinite(ic); s[:start]=False
            v=ic[s]; m,lo,hi,n=boot_ci(v,600,block=5)
            rows.append(dict(base,cut="regime_"+rg,n=n,ic=m,lo=lo,hi=hi,pos=float(np.mean(v>0)) if n else np.nan))
        for mk in ["KOSPI","KOSDAQ"]:
            mm=ok&(P.mk==mk)[None,:]
            icm=spearman_rows(x,FW[h],mm)
            rows.append({**base,"cut":"mkt_"+mk,**summarize(icm,"",sel&np.isfinite(icm))})
    print(nm,round(time.time()-t0,1),flush=True)
pd.DataFrame(rows).to_csv(os.path.join(OUT,"factor_ic.csv"),index=False)
dec=[]
for nm in names:
    x=np.where(ok,F[nm]*HYP[nm],np.nan); r=rank01(x)
    for d in range(10):
        m=(r>d/10)&(r<=(d+1)/10)
        vals=[np.nanmean(np.where(m[t],FW[20][t],np.nan)) for t in anchors_m]
        dec.append(dict(factor=nm,decile=d+1,ex20=np.nanmean(vals),pos=np.nanmean(np.array(vals)>0)))
pd.DataFrame(dec).to_csv(os.path.join(OUT,"factor_deciles.csv"),index=False)
combos={"lv60":["lv60"],"lv60+to20(lv_e형)":["lv60","to20"],"lv60+lv20":["lv60","lv20"],
        "px4":["lv60","to20","lv20","nh252"],"lv60+upratio63":["lv60","upratio63"],"lv60+to20+upratio63":["lv60","to20","upratio63"],
        "upratio63":["upratio63"],"nh252+mom12":["nh252","mom12_1"],"lv60+nh252":["lv60","nh252"],"to20":["to20"],"lv60+to20+on60cut":["lv60","to20"],
        "lv60+size":["lv60","size"],"lv60+to20+lv20+upratio63":["lv60","to20","lv20","upratio63"]}
crow=[]
for cn,fl in combos.items():
    okc=ok.copy()
    if "on60cut" in cn:
        r=rank01(np.where(ok,F["on60"],np.nan)); okc=ok&~(r>0.9)
    sc=rank_sum(F,fl,HYP,okc)
    for h in [5,20,60]:
        ic=spearman_rows(sc,FW[h],okc)
        sel=np.zeros(P.T,bool); sel[anchors_m]=True
        base=dict(combo=cn,h=h)
        crow.append({**base,"cut":"all_monthly",**summarize(ic,"",sel&np.isfinite(ic))})
        for y in ["2024","2025","2026"]:
            s=sel&np.array([d.startswith(y) for d in P.dates])&np.isfinite(ic); crow.append({**base,"cut":"year_"+y,**summarize(ic,"",s)})
        for rg in ["강세","조정","반등","약세"]:
            s=(R.regime_pit.values==rg)&np.isfinite(ic); s[:start]=False; v=ic[s]; m,lo,hi,n=boot_ci(v,600,block=5)
            crow.append(dict(base,cut="regime_"+rg,n=n,ic=m,lo=lo,hi=hi,pos=float(np.mean(v>0)) if n else np.nan))
        r=rank01(np.where(okc,sc,np.nan))
        top=[np.nanmean(np.where((r[t]>0)&(r[t]>=1-50/np.sum(np.isfinite(r[t]))),FW[h][t],np.nan)) for t in anchors_m]
        m,lo,hi,n=boot_ci(top,600); crow.append(dict(base,cut="top50_excess",n=n,ic=m,lo=lo,hi=hi,pos=float(np.nanmean(np.array(top)>0))))
    print(cn,round(time.time()-t0,1),flush=True)
pd.DataFrame(crow).to_csv(os.path.join(OUT,"combo_ic.csv"),index=False)
print("done",time.time()-t0)
