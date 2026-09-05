# step19 (2026-09-05): 신규 팩터의 '추가 기여' — 기준 조용함(lv60+to20) 순위합에 X 를 더했을 때 h20 IC 짝차이(전일 앵커, 블록CI) + 국면별 + 직교 IC + top20 초과.
import numpy as np, pandas as pd, os, time
from fslib import *
exec(open("step18_factor_zoo2.py",encoding="utf-8").read().split("H=[5,20,40,60]")[0])   # F 재구성(동일 코드)
SIGN={"hl_range20":-1,"clv20":+1,"gap_abs20":-1,"upvol20":-1,"amihud20":-1,"vol_dry":-1,"vol_spike5":-1,"skew60":-1,"volvol20":-1,"lv_ratio":-1,
      "sma60gap":-1,"sma120gap":-1,"min_ret20":+1,"to_trend":-1,"logprice":+1,"ivol60":-1,"idio_share":-1,"mom_consist":+1,"size":+1,"max5_21":-1,"nh252":+1,"rsi14":-1,"beta60":-1}
def fwdh(hh):
    f=np.full_like(c,np.nan); a=1; b=1+hh
    with np.errstate(all="ignore"): f[:P.T-b]=c[b:]/c[a:P.T-b+a]-1
    f[np.abs(f)>5]=np.nan; return excess(f,ok)
FW20=fwdh(20); FW40=fwdh(40)
HYP2=dict(HYP); HYP2.update(SIGN)
base=rank_sum(F,["lv60","to20"],HYP2,ok); ic_b=spearman_rows(base,FW20,ok)
rb=rank01(np.where(ok,base,np.nan))
def top_exc(sc,fw,N=20):
    r=rank01(np.where(ok,sc,np.nan)); out=np.full(P.T,np.nan)
    for t in range(start,P.T):
        m=np.isfinite(r[t]); n=m.sum()
        if n<50: continue
        sel=r[t]>=1-N/n; v=fw[t][sel]; v=v[np.isfinite(v)]
        if len(v)>=5: out[t]=v.mean()
    return out
te_b=top_exc(base,FW20); te_b40=top_exc(base,FW40)
rg=R.regime_pit.values
rows=[]
for nm in SIGN:
    if nm in ("lv60","to20"): continue
    sc=rank_sum(F,["lv60","to20",nm],HYP2,ok); ic=spearman_rows(sc,FW20,ok)
    d=(ic-ic_b)[start:]; m,lo,hi,n=boot_ci(d,500,block=20)
    # 직교 IC: X 순위를 base 순위로 회귀한 잔차의 IC
    x=rank01(np.where(ok,F[nm]*SIGN[nm],np.nan)); res=np.full_like(x,np.nan)
    for t in range(start,P.T):
        mm=np.isfinite(x[t])&np.isfinite(rb[t])
        if mm.sum()<50: continue
        A=np.c_[np.ones(mm.sum()),rb[t][mm]]; beta=np.linalg.lstsq(A,x[t][mm],rcond=None)[0]; res[t][mm]=x[t][mm]-A@beta
    ico=spearman_rows(res,FW20,ok); vo=ico[start:]; vo=vo[np.isfinite(vo)]; mo,loo,hio,_=boot_ci(vo,300,block=20)
    te=top_exc(sc,FW20); dte=(te-te_b)[start:]; mt,lt,ht,_=boot_ci(dte,300,block=20)
    te40=top_exc(sc,FW40); dte40=(te40-te_b40)[start:]; mt4,lt4,ht4,_=boot_ci(dte40,300,block=40)
    rec=dict(add=nm,dIC=m,lo=lo,hi=hi,n=n,pos=float(np.mean(d[np.isfinite(d)]>0)),ortho_ic=mo,ortho_lo=loo,ortho_hi=hio,
             dTop20_exc_pp=mt*100,dTop20_lo=lt*100,dTop20_hi=ht*100,dTop20_h40_pp=mt4*100,dTop20_h40_lo=lt4*100,dTop20_h40_hi=ht4*100)
    for g in ["강세","조정","반등","약세"]:
        s=(rg==g); s[:start]=False; dd=(ic-ic_b)[s]; rec[f"d_{g}"]=float(np.nanmean(dd))
    rows.append(rec); print(nm,round(time.time()-t0,1),flush=True)
D=pd.DataFrame(rows).sort_values("dIC",ascending=False); D.to_csv(os.path.join(OUT,"marginal_zoo2.csv"),index=False)
pd.set_option("display.width",250)
print("기준 lv60+to20: h20 IC",round(float(np.nanmean(ic_b[start:])),4),"top20 초과/20d",round(float(np.nanmean(te_b[start:]))*100,2),"%p  h40",round(float(np.nanmean(te_b40[start:]))*100,2))
print(D.round(3).to_string(index=False)); print("done",round(time.time()-t0,1))
