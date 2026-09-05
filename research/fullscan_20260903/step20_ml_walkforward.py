# step20 (2026-09-05): 심화 — 걸어가며 학습(walk-forward) 릿지 회귀 vs 순위합. 훈련 12개월(월간 앵커, h20 초과 순위 타깃) → 다음 3개월 예측, 2025-01~2026-09.
#   비교: 조용함 순위합(lv60+to20) / 릿지-전체팩터(30) / 릿지-조용함군 제외 / 로짓형 대손실 회피 타깃. 지표: 일별 h20 IC(블록CI), top20 초과, 국면별.
import numpy as np, pandas as pd, os, time
from fslib import *
exec(open("step18_factor_zoo2.py",encoding="utf-8").read().split("H=[5,20,40,60]")[0])
def fwdh(hh):
    f=np.full_like(c,np.nan); a=1; b=1+hh
    with np.errstate(all="ignore"): f[:P.T-b]=c[b:]/c[a:P.T-b+a]-1
    f[np.abs(f)>5]=np.nan; return excess(f,ok)
FW=fwdh(20); Y=rank01(np.where(ok,FW,np.nan))            # 타깃: 그날 초과수익 순위(0~1)
LOSS=np.where(ok,(FW<-0.10).astype(float),np.nan)         # 대손실 지표
names=[k for k in F if k not in ("rsi14",)]; X=np.stack([rank01(np.where(ok,F[k],np.nan)) for k in names],axis=-1)   # (T,N,K) 순위 특징
X=np.where(np.isfinite(X),X,0.5)-0.5
quiet=["lv60","to20","hl_range20","ivol60","volvol20","max5_21","min_ret20","gap_abs20","skew60","lv_ratio","idio_share"]
sets={"릿지 전체30":list(range(len(names))),"릿지 조용함군 제외":[i for i,k in enumerate(names) if k not in quiet],"릿지 조용함군만":[i for i,k in enumerate(names) if k in quiet]}
base=rank_sum(F,["lv60","to20"],HYP,ok)
t_start=P.idx("20250101"); TRAIN=252; TEST=63; LAM=50.0
pred={k:np.full((P.T,N),np.nan) for k in sets}; pred_loss=np.full((P.T,N),np.nan)
t=t_start
while t<P.T:
    tr_anchors=[a for a in range(t-TRAIN,t-20,21) if a>=P.idx("20240101")]   # h20 창이 t 전에 닫히는 앵커만(룩어헤드 방지)
    if len(tr_anchors)>=6:
        Xtr=np.concatenate([X[a][ok[a]&np.isfinite(Y[a])] for a in tr_anchors]); ytr=np.concatenate([Y[a][ok[a]&np.isfinite(Y[a])] for a in tr_anchors])-0.5
        ltr=np.concatenate([LOSS[a][ok[a]&np.isfinite(Y[a])] for a in tr_anchors])
        for k,cols in sets.items():
            A=Xtr[:,cols]; w=np.linalg.solve(A.T@A+LAM*np.eye(len(cols)),A.T@ytr)
            for d in range(t,min(t+TEST,P.T)): pred[k][d]=X[d][:,cols]@w
        A=Xtr; wl=np.linalg.solve(A.T@A+LAM*np.eye(A.shape[1]),A.T@(0.5-ltr))   # 대손실 회피(손실이면 낮게)
        for d in range(t,min(t+TEST,P.T)): pred_loss[d]=X[d]@wl
        if t==t_start or (t-t_start)%(TEST*4)==0:
            w=np.linalg.solve(Xtr.T@Xtr+LAM*np.eye(Xtr.shape[1]),Xtr.T@ytr); top=np.argsort(-np.abs(w))[:8]
            print(P.dates[t],"릿지 상위 가중:"," ".join(f"{names[i]}{w[i]:+.3f}" for i in top),flush=True)
    t+=TEST
rg=R.regime_pit.values
def top_exc(sc,N_=20):
    r=rank01(np.where(ok,sc,np.nan)); out=np.full(P.T,np.nan)
    for tt in range(t_start,P.T):
        m=np.isfinite(r[tt]); n=m.sum()
        if n<50: continue
        sel=r[tt]>=1-N_/n; v=FW[tt][sel]; v=v[np.isfinite(v)]
        if len(v)>=5: out[tt]=v.mean()
    return out
rows=[]
cands={"순위합 lv60+to20(기준)":base,**pred,"릿지 대손실회피 타깃":pred_loss}
ic_base=spearman_rows(base,FW,ok)
for nm,sc in cands.items():
    ic=spearman_rows(sc,FW,ok); v=ic[t_start:]; v=v[np.isfinite(v)]; m,lo,hi,n=boot_ci(v,500,block=20)
    te=top_exc(sc); tv=te[t_start:]; tv=tv[np.isfinite(tv)]; mt,lt,ht,_=boot_ci(tv,500,block=20)
    d=(ic-ic_base)[t_start:]; md,ld,hd,_=boot_ci(d,500,block=20)
    rec=dict(model=nm,ic=m,lo=lo,hi=hi,n=n,top20_exc_pp=mt*100,te_lo=lt*100,te_hi=ht*100,dIC_vs_base=md,d_lo=ld,d_hi=hd)
    for g in ["강세","조정","반등","약세"]:
        s=(rg==g); s[:t_start]=False; rec[f"ic_{g}"]=float(np.nanmean(ic[s]))
    rows.append(rec)
D=pd.DataFrame(rows); D.to_csv(os.path.join(OUT,"ml_walkforward.csv"),index=False)
pd.set_option("display.width",250); print(D.round(4).to_string(index=False)); print("done",round(time.time()-t0,1))
