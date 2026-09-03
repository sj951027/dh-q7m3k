# step10: 새 모델 전수 — 팩터 29종 단일·2중(전수)·3중(상위12 기반) 순위합, walk-forward(train 2024-01~2025-06 / test 2025-07~2026-09), h20·h60.
import numpy as np, pandas as pd, os, time, itertools
from fslib import *
t0=time.time(); P=Panel(); ok=guards(P); F=factors(P); R=regimes(P)
ret=P.ret; c=P.close.astype(np.float64)
F["downvol60"]=roll_std(np.where(ret<0,ret,0.0),60,40); F["hl_range20"]=roll_mean((P.high-P.low)/P.close,20,10)
F["volvol20"]=roll_std(np.log1p(P.vol),20,10)
F["amihud20"]=roll_mean(np.abs(ret)/np.maximum(P.amt,1),20,10)
kq=pd.Series(P.kosdaq).ffill().values; kqr=np.r_[np.nan,kq[1:]/kq[:-1]-1]; x=pd.Series(kqr)
cov=pd.DataFrame(ret*kqr[:,None]).rolling(60,min_periods=40).mean().values-pd.DataFrame(ret).rolling(60,min_periods=40).mean().values*x.rolling(60,min_periods=40).mean().values[:,None]
F["beta60"]=cov/x.rolling(60,min_periods=40).var().values[:,None]
F["skew60"]=pd.DataFrame(ret).rolling(60,min_periods=40).skew().values
ev=pd.read_csv(os.path.join(OUT,"dart_events_aligned.csv"),dtype={"ticker":str})
def flag_of(subs,days=60):
    f=np.zeros((P.T,P.N),bool)
    for r in ev[ev["sub"].isin(subs)].itertuples(): f[r.t:min(P.T,r.t+days+1),r.j]=True
    return f
F["ev_buyback60"]=flag_of(["buyback_trust","buyback_direct","buyback_trust_cancel","buyback_direct_cancel"]).astype(float)
F["ev_dilution60"]=flag_of(["cb","paid_in","bw","eb","paid_bonus_mix"]).astype(float)
HYP2=dict(HYP); HYP2.update({"ev_buyback60":+1,"ev_dilution60":-1,"downvol60":-1,"hl_range20":-1,"volvol20":-1,"amihud20":+1,"beta60":-1,"skew60":-1})
for k in ["dd52","rv21"]: HYP2.pop(k)   # 중복(nh252, lv20/lv60) 제거
names=list(HYP2.keys()); print(len(names),names)
H=[20,60]; FW={h:excess(fwd(P,h),ok) for h in H}
tr0,tr1,te0=P.idx("20240101"),P.idx("20250701"),P.idx("20250701")
sel_tr=np.zeros(P.T,bool); sel_tr[tr0:tr1]=True; sel_te=np.zeros(P.T,bool); sel_te[te0:]=True
rg=R.regime_pit.values
RK={n:rank01(np.where(ok,F[n]*HYP2[n],np.nan)) for n in names}
RKf={n:np.where(np.isfinite(RK[n]),RK[n],0.5) for n in names}
def evaluate(combo):
    sc=RK[combo[0]].copy()
    for n in combo[1:]: sc=sc+RKf[n]
    out=dict(combo="+".join(combo),k=len(combo))
    for h in H:
        ic=spearman_rows(sc,FW[h],ok)
        tr=ic[sel_tr]; tr=tr[np.isfinite(tr)]; te=ic[sel_te]; te=te[np.isfinite(te)]
        out[f"train_ic{h}"]=float(tr.mean()) if len(tr) else np.nan
        m,lo,hi,n=boot_ci(te,300,block=5); out[f"test_ic{h}"]=m; out[f"test_lo{h}"]=lo; out[f"test_n{h}"]=n
        mins=[]
        for g in ["강세","조정","반등","약세"]:
            s=sel_te&(rg==g)&np.isfinite(ic); mins.append(float(ic[s].mean()) if s.sum()>=10 else np.nan)
        out[f"test_regmin{h}"]=np.nanmin(mins); out[f"test_reg{h}"]="/".join(f"{v:+.2f}" for v in mins)
        if h==20:
            r=rank01(np.where(ok,sc,np.nan)); top=[]
            for t in range(te0,P.T-21,5):
                nn=np.sum(np.isfinite(r[t])); 
                if nn<100: continue
                top.append(np.nanmean(np.where(r[t]>=1-50/nn,FW[20][t],np.nan)))
            out["test_top50_ex20"]=float(np.nanmean(top))
    return out
CSV=os.path.join(OUT,"new_model_search.csv")
done=set(); rows=[]
if os.path.exists(CSV):
    prev=pd.read_csv(CSV); rows=prev.to_dict("records"); done=set(prev.combo)
def run(combos,tag):
    global rows
    cnt=0
    for cb in combos:
        key="+".join(cb)
        if key in done: continue
        rows.append(evaluate(cb)); done.add(key); cnt+=1
        if cnt%10==0:
            pd.DataFrame(rows).to_csv(CSV,index=False); print(tag,len(done),round(time.time()-t0),flush=True)
        if time.time()-t0>150:
            pd.DataFrame(rows).to_csv(CSV,index=False); print("TIME BUDGET — 재실행 필요",tag,len(done),flush=True); raise SystemExit(0)
    pd.DataFrame(rows).to_csv(CSV,index=False)
run([(n,) for n in names],"singles")
run(list(itertools.combinations(names,2)),"pairs")
df=pd.DataFrame(rows)
top12=df[df.k==1].sort_values("train_ic20",ascending=False).combo.head(12).tolist()
print("top12 singles(train)",top12,flush=True)
run(list(itertools.combinations(top12,3)),"triples")
df=pd.DataFrame(rows)
pd.set_option("display.width",260); pd.set_option("display.max_rows",200)
cols=["combo","k","train_ic20","test_ic20","test_lo20","test_regmin20","test_reg20","test_top50_ex20","train_ic60","test_ic60","test_regmin60"]
print("=== train_ic20 상위 30 → test 성적 ==="); print(df.sort_values("train_ic20",ascending=False).head(30)[cols].round(3).to_string())
print("=== test_regmin20(4국면 최소) 상위 30 ==="); print(df.sort_values("test_regmin20",ascending=False).head(30)[cols].round(3).to_string())
print("=== test_top50_ex20 상위 30 ==="); print(df.sort_values("test_top50_ex20",ascending=False).head(30)[cols].round(3).to_string())
print("done",time.time()-t0)
