# step9: sv_a(공매도비중5d 단독, 전체 가드 유니버스) 강화 전수 — 창·정의 변형, 변수 1개 추가, 유니버스 변형. 2026-03~ 단일 국면.
import numpy as np, pandas as pd, os, time
from fslib import *
t0=time.time(); P=Panel(); ok=guards(P); F=factors(P); R=regimes(P)
H=[5,10,20]; FW={h:excess(fwd(P,h),ok) for h in H}
ti={k:i for i,k in enumerate(P.tick)}; di={d:i for i,d in enumerate(P.dates)}
o=ro(OHLCV)
def to_mat(d,col):
    m=np.full((P.T,P.N),np.nan); d=d[d.ticker.isin(ti)&d.date.isin(di)]
    m[d.date.map(di).values,d.ticker.map(ti).values]=d[col].values.astype(float); return m
sf=pd.read_sql("select ticker,date,short_qty,short_vol_ratio,short_val,credit_bal_rate,credit_bal_amt,loan_bal_qty,loan_chg from short_flows where date>='20260101'",o)
fl=pd.read_sql("select ticker,date,foreign_net_val,inst_net_val,person_net_val,pension_net_val,trust_net_val,secfirm_net_val,prveq_net_val from daily_flows",o)
va=pd.read_sql("select ticker,date,per,pbr,div from valuation_daily",o)
svr=to_mat(sf,"short_vol_ratio"); sval=to_mat(sf,"short_val"); sq=to_mat(sf,"short_qty")
amt20=roll_mean(P.amt,20,10)
X={}
X["svr5"]=roll_mean(svr,5,3); X["svr10"]=roll_mean(svr,10,5); X["svr20"]=roll_mean(svr,20,10); X["svr60"]=roll_mean(svr,60,30)
X["svr1"]=svr
with np.errstate(all="ignore"):
    X["sval5_amt"]=roll_mean(sval,5,3)/amt20; X["sq5_shares"]=roll_mean(sq,5,3)/P.shares; X["sq5_vol"]=roll_mean(sq,5,3)/roll_mean(P.vol,5,3)
X["svr5_minus_60"]=X["svr5"]-X["svr60"]; X["svr_z60"]=(X["svr5"]-roll_mean(svr,60,30))/roll_std(svr,60,30)
X["svr5_rank_chg"]=None
cr=pd.DataFrame(to_mat(sf,"credit_bal_rate")).ffill(limit=5).values; X["cr_rate"]=cr; X["cr_chg20"]=cr-np.vstack([np.full((20,P.N),np.nan),cr[:-20]])
ln=pd.DataFrame(to_mat(sf,"loan_bal_qty")).ffill(limit=5).values
with np.errstate(all="ignore"): X["loan_ratio"]=ln/P.shares; X["loan_chg20"]=(ln-np.vstack([np.full((20,P.N),np.nan),ln[:-20]]))/P.shares
for c in ["foreign","inst","person","pension","trust","secfirm","prveq"]:
    m=to_mat(fl,c+"_net_val"); cov=roll_mean(np.isfinite(m).astype(float),20,10)>0.5
    for w in [5,20]:
        z=roll_mean(np.nan_to_num(m),w,max(3,w//2))/amt20*w; z[~cov]=np.nan; X[f"fl_{c}{w}n"]=z
per=to_mat(va,"per"); pbr=to_mat(va,"pbr"); per[per==0]=np.nan; pbr[pbr==0]=np.nan
with np.errstate(all="ignore"): X["va_ep"]=1/per; X["va_bp"]=1/pbr; X["va_div"]=to_mat(va,"div")
del X["svr5_rank_chg"]
ev=pd.read_csv(os.path.join(OUT,"dart_events_aligned.csv"),dtype={"ticker":str})
def flag_of(subs,days=60):
    f=np.zeros((P.T,P.N),bool)
    for r in ev[ev["sub"].isin(subs)].itertuples(): f[r.t:min(P.T,r.t+days+1),r.j]=True
    return f
X["ev_buyback60"]=flag_of(["buyback_trust","buyback_direct","buyback_trust_cancel","buyback_direct_cancel"]).astype(float)
X["ev_dilution60"]=flag_of(["cb","paid_in","bw","eb","paid_bonus_mix"]).astype(float)
for k,v in F.items(): X["px_"+k]=v
start=P.idx("20260301")
base=rank01(np.where(ok,X["svr5"],np.nan))   # sv_a 재현(핵심 svr5 실측 필수)
M=ok&np.isfinite(base)
rows=[]
def rec(name,kind,score,mask=None):
    mm=M if mask is None else (M&mask)
    for h in H:
        ic=spearman_rows(score,FW[h],mm); bic=spearman_rows(base,FW[h],M if mask is None else mm)
        d=(ic-bic)[start:]; d=d[np.isfinite(d)]; m,lo,hi,n=boot_ci(d,500,block=5)
        rows.append(dict(variant=name,kind=kind,h=h,n=n,ic_var=float(np.nanmean(ic[start:])),ic_base=float(np.nanmean(bic[start:])),diff=m,lo=lo,hi=hi,pos=float(np.mean(d>0)) if n else np.nan))
# 정의/창 변형(대체)
for k in ["svr1","svr10","svr20","svr60","sval5_amt","sq5_shares","sq5_vol","svr5_minus_60","svr_z60"]:
    rec(k,"replace",rank01(np.where(ok,X[k],np.nan)))
# 추가(순위합, 보조 NaN=0.5)
for k in X:
    if k.startswith("svr") or k in ("sval5_amt","sq5_shares","sq5_vol"): continue
    for sgn,sn in [(1,"+"),(-1,"-")]:
        r=rank01(np.where(ok,sgn*X[k],np.nan)); r=np.where(np.isfinite(r),r,0.5)
        rec(f"{sn}{k}","add",base+r)
    print(k,round(time.time()-t0),flush=True)
# 유니버스 변형
qz=rank01(np.where(ok,-(rank01(np.where(ok,F["lv60"],np.nan))+rank01(np.where(ok,F["to20"],np.nan))),np.nan))
mc=rank01(np.where(ok,F["size"],np.nan))
for un,mk in {"조용함상위50%":qz>=0.5,"조용함하위50%":qz<0.5,"대형30%":mc>=0.7,"중소형70%":mc<0.7,"코스닥":(P.mk=="KOSDAQ")[None,:].repeat(P.T,0),"코스피":(P.mk=="KOSPI")[None,:].repeat(P.T,0),
              "희석60d제외":X["ev_dilution60"]==0,"RSI<50":F["rsi14"]<50,"RSI>=50":F["rsi14"]>=50,"거래대금20억↑":amt20>=2e9,"svr5>0(공매도 있는 종목만)":X["svr5"]>0}.items():
    rec(f"uni:{un}","universe",base,mk)
res=pd.DataFrame(rows); res.to_csv(os.path.join(OUT,"sv_enhance.csv"),index=False)
pd.set_option("display.width",250); pd.set_option("display.max_rows",600)
res["cell"]=res.apply(lambda x: f"{x['diff']:+.3f}[{x.lo:+.2f},{x.hi:+.2f}]{int(x.pos*100)}%",axis=1)
for kind in ["replace","universe","add"]:
    p=res[res.kind==kind].pivot(index="variant",columns="h",values="cell"); dm=res[res.kind==kind].pivot(index="variant",columns="h",values="diff"); lo=res[res.kind==kind].pivot(index="variant",columns="h",values="lo")
    p["CI>0지평수"]=(lo>0).sum(axis=1); p["min"]=dm.min(axis=1)
    print("=====",kind); print(p.sort_values("min",ascending=False).to_string())
print("base IC(h5/10/20):",[round(float(np.nanmean(spearman_rows(base,FW[h],M)[start:])),3) for h in H],"n anchors",int(np.isfinite(spearman_rows(base,FW[20],M)[start:]).sum()))
print("done",time.time()-t0)
