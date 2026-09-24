# bigwin4_causal.py — 정오표 ①⑤⑥ 정본: 월간 top20 h120, 신호일 정보만으로 선정(미래 수익 필터 없음), 수익 절단 없음,
# 픽비중/유니버스비중 지수 병기, 6개월 원형블록 CI. Codex 검토(handoff/REPLY_20260924_bigwinners_review.md) 반영.
import os, sys, numpy as np, pandas as pd
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from bw_build import *
def rs(nd):
    sc=None
    for n,d in nd:
        r=R[n] if d>0 else 1-R[n]; sc=r.copy() if sc is None else sc+np.where(np.isfinite(r),r,0.5)
    return sc
base=[("mom12_1",1),("beta60",1),("days_since_high",-1)]
RULES={"R1":rs(base),"R1_amt":rs(base+[("amt20",1)]),"R1_small_tilt":rs(base+[("size",-1)]),"R1_minus_mom":rs(base[1:])}
h=120; cf=c.astype(float); mark=pd.DataFrame(cf).ffill().values
def fwd_idx(x,h):
    o=np.full(T,np.nan); o[:T-1-h]=x[1+h:]/x[1:T-h]-1; return o
ik=fwd_idx(kp,h); iq=fwd_idx(kq,h)
months=sorted(set(d[:6] for d in P.dates)); anchors=[]
for mo in months:
    i=P.idx(mo+"01")
    if i<T and P.dates[i][:6]==mo and P.dates[i]>="20240101": anchors.append(i)
rows=[]
for nm,sc in RULES.items():
    for a in anchors:
        e=a+1; end=a+1+h
        if end>=T: continue
        for mode in ["원본","인과"]:
            cand=ok[a]&np.isfinite(FW[h][a]) if mode=="원본" else ok[a]
            s=np.where(cand,sc[a],np.nan)
            if np.isfinite(s).sum()<40: continue
            pick=np.argsort(-np.where(np.isfinite(s),s,-np.inf))[:20]
            entered=np.isfinite(cf[e,pick])&(cf[e,pick]>0)&(P.vol[e,pick]>0)
            realized=FW[h][a,pick] if mode=="원본" else np.where(entered,mark[end,pick]/cf[e,pick]-1,0.)
            net=float(np.nanmean(realized))-0.005
            up=np.mean(idx[np.where(cand)[0]]); pp=np.mean(idx[pick])
            rows.append(dict(rule=nm,mode=mode,date=P.dates[a],net=net,ex_univmix=net-((1-up)*ik[a]+up*iq[a]),ex_pickmix=net-((1-pp)*ik[a]+pp*iq[a])))
D=pd.DataFrame(rows); D.to_csv(os.path.join(OUT,"r1_causal_recheck.csv"),index=False)
def bci(x,block=6,n=3000,seed=924):
    x=np.asarray(x,float); rng=np.random.default_rng(seed); L=len(x)
    st=rng.integers(0,L,(n,int(np.ceil(L/block)))); ix=(st[:,:,None]+np.arange(block))%L
    mm=x[ix.reshape(n,-1)[:,:L]].mean(axis=1); return f"{x.mean()*100:+.2f} [{np.quantile(mm,.025)*100:+.2f}, {np.quantile(mm,.975)*100:+.2f}]"
for (nm,mode),g in D.groupby(["rule","mode"]):
    print(f"{nm:14s} {mode} n={len(g)} net {bci(g.net)} | 유니버스비중지수 {bci(g.ex_univmix)} | 픽비중지수 {bci(g.ex_pickmix)}")
a1=D[(D.rule=="R1")&(D['mode']=="인과")].set_index("date"); a2=D[(D.rule=="R1_minus_mom")&(D['mode']=="인과")].set_index("date").reindex(a1.index)
print("짝차이 R1 − (mom 제거), 같은 20개월, 픽비중지수 초과:", bci((a1.ex_pickmix-a2.ex_pickmix).values))
E=EV[120]; m=ok&np.isfinite(FW[120])
for n,d in [("mom12_1",1),("mom252",1),("beta60",1),("amt20",1),("dlow252",1),("lv60",-1),("hl_range20",-1),("to20",-1)]:
    sel=m&((R[n]>=.9) if d>0 else (R[n]<.1)); av=m&np.isfinite(R[n])
    print(f"lift {n:11s} 원본 {E[sel].mean()/E[m].mean():.2f} / 가용성일치 {E[sel].mean()/E[av].mean():.2f}")
