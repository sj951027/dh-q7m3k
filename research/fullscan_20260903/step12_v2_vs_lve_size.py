# step12: 조용함 v2(to20+hl_range20+volvol20) vs lv_e(lv60+to20) 같은 앵커 짝비교 + 비용 후 수익 + 용량 + size 심층(소형 주도 달에 어떻게 되나)
import numpy as np, pandas as pd, os
from fslib import *
P=Panel(); ok=guards(P); F=factors(P); R=regimes(P); ret=P.ret; c=P.close.astype(np.float64)
F["hl_range20"]=roll_mean((P.high-P.low)/P.close,20,10); F["volvol20"]=roll_std(np.log1p(P.vol),20,10)
H2=dict(HYP); H2.update({"hl_range20":-1,"volvol20":-1})
FW={h:excess(fwd(P,h),ok) for h in [20,60]}; start=P.idx("20240101"); rg=R.regime_pit.values
models={"lv_e":["lv60","to20"],"v2":["to20","hl_range20","volvol20"],"v2+lv60":["lv60","to20","hl_range20","volvol20"],"lv_e+size":["lv60","to20","size"],"v2+size":["to20","hl_range20","volvol20","size"],"size":["size"]}
S={k:rank_sum(F,v,H2,ok) for k,v in models.items()}
IC={k:{h:spearman_rows(S[k],FW[h],ok) for h in [20,60]} for k in S}
ICm={k:{h:{mk:spearman_rows(S[k],FW[h],ok&(P.mk==mk)[None,:]) for mk in ["KOSPI","KOSDAQ"]} for h in [20,60]} for k in S}
print("=== 같은 앵커 짝비교 diff (A − lv_e), 5일 블록 부트 ===")
rows=[]
for k in ["v2","v2+lv60","lv_e+size","v2+size"]:
    for h in [20,60]:
        d=IC[k][h]-IC["lv_e"][h]; o=dict(model=k,h=h)
        for g in ["전체","강세","조정","반등","약세"]:
            s=np.isfinite(d); s[:start]=False
            if g!="전체": s&=(rg==g)
            m,lo,hi,n=boot_ci(d[s],400,block=5); o[g]=f"{m:+.3f}[{lo:+.2f},{hi:+.2f}]{int(np.mean(d[s]>0)*100)}%"
        for mk in ["KOSPI","KOSDAQ"]:
            dm=ICm[k][h][mk]-ICm["lv_e"][h][mk]; s=np.isfinite(dm); s[:start]=False; m,lo,hi,n=boot_ci(dm[s],400,block=5); o[mk]=f"{m:+.3f}[{lo:+.2f},{hi:+.2f}]"
        rows.append(o)
pd.set_option("display.width",300); print(pd.DataFrame(rows).to_string())
# 연도별 diff
print("=== 연도별 h20 diff(A−lv_e) ===")
for k in ["v2","v2+size"]:
    d=IC[k][20]-IC["lv_e"][20]
    print(k,{y:round(float(np.nanmean(d[np.array([x.startswith(y) for x in P.dates])])),3) for y in ["2024","2025","2026"]})
# top20 k=40 비용후 + 용량 + 회전
amt20=roll_mean(P.amt,20,10)
def topmask(sc,N=20): return pd.DataFrame(np.where(ok,sc,np.nan)).rank(axis=1,ascending=False).values<=N
def kret(mask,k,t):
    a=t+1; b=a+k
    if b>=P.T: return np.nan
    with np.errstate(all="ignore"): r=c[b]/c[a]-1
    v=r[mask[t]]; v=v[np.isfinite(v)&(np.abs(v)<5)]; return v.mean() if len(v)>=5 else np.nan
ewm=ok
print("=== top20 40일 보유 (20일 환산, 비용 왕복 0.5%) · 용량 · 회전 ===")
rows=[]
for k in models:
    M=topmask(S[k]); rr=np.array([kret(M,40,t) for t in range(start,P.T)]); ew=np.array([kret(ewm,40,t) for t in range(start,P.T)])
    o=dict(model=k)
    for g in ["전체","강세","조정","반등","약세"]:
        s=np.isfinite(rr)&np.isfinite(ew)
        if g!="전체": s&=(rg[start:P.T]==g)
        net=rr[s]*0.5-0.0025; m,lo,hi,n=boot_ci(net,300,block=40); o[g]=f"{m*100:+.2f}[{lo*100:+.1f},{hi*100:+.1f}] (EW초과 {np.mean((rr[s]-ew[s])*0.5)*100:+.2f})"
    med=[np.nanmedian(amt20[t][M[t]]) for t in range(start,P.T,20)]; o["픽 중위 거래대금(억)"]=round(float(np.nanmedian(med))/1e8,1)
    med2=[np.nanmedian(P.mcap[t][M[t]]) for t in range(start,P.T,20)]; o["픽 중위 시총(조)"]=round(float(np.nanmedian(med2))/1e12,2)
    ov=[len(set(np.where(M[t])[0])&set(np.where(M[t+20])[0]))/20 for t in range(start,P.T-20,20)]; o["20일 후 잔류율"]=round(float(np.mean(ov)),2)
    kq=[np.mean(P.mk[M[t]]=="KOSDAQ") for t in range(start,P.T,20)]; o["코스닥 비중"]=round(float(np.mean(kq)),2)
    rows.append(o)
print(pd.DataFrame(rows).to_string())
# size 심층: 월별 size IC vs (코스닥−코스피) 월수익
print("=== size(대형) h20 IC — 소형주도 달 vs 대형주도 달 ===")
ic=pd.Series(IC["size"][20],index=P.dates); kp=pd.Series(P.kospi,index=P.dates).ffill(); kq=pd.Series(P.kosdaq,index=P.dates).ffill()
ym=ic.index.str[:6]
mret=pd.DataFrame({"kospi":kp.groupby(ym).apply(lambda s:s.iloc[-1]/s.iloc[0]-1),"kosdaq":kq.groupby(ym).apply(lambda s:s.iloc[-1]/s.iloc[0]-1),"size_ic":ic.groupby(ym).mean(),
                   "lve_ic":pd.Series(IC["lv_e"][20],index=P.dates).groupby(ym).mean(),"v2_ic":pd.Series(IC["v2"][20],index=P.dates).groupby(ym).mean(),"v2size_ic":pd.Series(IC["v2+size"][20],index=P.dates).groupby(ym).mean()})
mret=mret[mret.index>="202401"]; mret["kq_minus_kp"]=mret.kosdaq-mret.kospi
print(mret.round(3).to_string())
small_led=mret[mret.kq_minus_kp>0]; large_led=mret[mret.kq_minus_kp<=0]
print("소형주도 달(코스닥>코스피) n=%d: size IC %.3f, lv_e %.3f, v2 %.3f, v2+size %.3f"%(len(small_led),small_led.size_ic.mean(),small_led.lve_ic.mean(),small_led.v2_ic.mean(),small_led.v2size_ic.mean()))
print("대형주도 달 n=%d: size IC %.3f, lv_e %.3f, v2 %.3f, v2+size %.3f"%(len(large_led),large_led.size_ic.mean(),large_led.lve_ic.mean(),large_led.v2_ic.mean(),large_led.v2size_ic.mean()))
# 시장 내부에서의 size IC (코스닥 안에서 대형이 이기나)
for mk in ["KOSPI","KOSDAQ"]:
    v=ICm["size"][20][mk][start:]; v=v[np.isfinite(v)]; m,lo,hi,n=boot_ci(v,300,block=5); print(f"size IC within {mk}: {m:+.3f}[{lo:+.2f},{hi:+.2f}]")
# 규모별 조용함(v2) IC
mc=rank01(np.where(ok,F["size"],np.nan))
for nm,mk in {"대형30%":mc>=0.7,"중형":(mc>=0.3)&(mc<0.7),"소형30%":mc<0.3}.items():
    for k in ["lv_e","v2"]:
        v=spearman_rows(S[k],FW[20],ok&mk)[start:]; v=v[np.isfinite(v)]; m,lo,hi,n=boot_ci(v,300,block=5); print(f"{k} h20 IC within {nm}: {m:+.3f}[{lo:+.2f},{hi:+.2f}]")
