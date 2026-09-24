# bigwin2.py — (a) 동일가중 유니버스 대비 초과 (b) 월간 앵커 top-N 규칙 포트 (c) 위너 사례 (d) cold 결합 (e) 합성점수 십분위
import os, sys, itertools, numpy as np, pandas as pd
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from bw_build import *
pd.set_option('display.width',250); pd.set_option('display.max_rows',300)

# 동일가중 유니버스 중앙값/평균 대비 초과
EXU={}; IDXM={}
for h in [60,120]:
    f=FW[h]; m=np.where(ok,f,np.nan)
    EXU[h]=f-np.nanmedian(m,axis=1,keepdims=True)
    IDXM[h]=np.nanmean(m,axis=1)  # EW 유니버스 평균 수익
# 지수 fw (시장 혼합: 종목별 시장 지수)
def fwd_idx(x,h):
    o=np.full(T,np.nan); o[:T-1-h]=x[1+h:]/x[1:T-h]-1; return o
IK={h:fwd_idx(kp,h) for h in [60,120]}; IQ={h:fwd_idx(kq,h) for h in [60,120]}

# ---------- (e) 합성 규칙 ----------
def rs(names_dirs):
    sc=None
    for n,d in names_dirs:
        r=R[n] if d>0 else 1-R[n]
        sc=r.copy() if sc is None else sc+np.where(np.isfinite(r),r,0.5)
    return sc
RULES={
 "R1_달리는말(mom12_1↑+beta60↑+근고점)":rs([("mom12_1",1),("beta60",1),("days_since_high",-1)]),
 "R2_장기추세(mom252↑+sma120gap↑+amt20↑)":rs([("mom252",1),("sma120gap",1),("amt20",1)]),
 "R3_조용함(lv60↓+to20↓)":rs([("lv60",-1),("to20",-1)]),
 "R4_고베타단독":rs([("beta60",1)]),
 "R5_mom12_1단독":rs([("mom12_1",1)]),
 "R6_쉬는말(cold: mom126↑, mom63<10%)":np.where(F["mom63"]<0.10,rs([("mom126",1)]),np.nan),
 "R7_저점탈출+미매집(dlow252↑+upvol20↓+amt20↑)":rs([("dlow252",1),("upvol20",-1),("amt20",1)]),
}
rows=[]
for h in [60,120]:
    E=EV[h]; ex=EX[h]; exu=EXU[h]; m=ok&np.isfinite(ex)
    base=E[m].mean()
    for nm,sc in RULES.items():
        r=fs.rank01(np.where(m,sc,np.nan))
        for d in range(10):
            sel=m&(r>=d/10)&(r<(d+1)/10+1e-9)
            if sel.sum()<300: continue
            rows.append(dict(h=h,rule=nm,decile=d+1,n=int(sel.sum()),win_lift=float(E[sel].mean()/base),
                mean_ex_idx=float(ex[sel].mean()),med_ex_idx=float(np.median(ex[sel])),p_beat_idx=float((ex[sel]>0).mean()),
                mean_ex_ew=float(exu[sel].mean()),med_ex_ew=float(np.median(exu[sel])),p_beat_ew=float((exu[sel]>0).mean()),
                p_lt_m30=float((ex[sel]<=-0.3).mean())))
DEC=pd.DataFrame(rows); DEC.to_csv(os.path.join(OUT,"rule_deciles.csv"),index=False)
for h in [120,60]:
    print("===== rule deciles h",h)
    d=DEC[(DEC.h==h)&(DEC.decile.isin([1,5,10]))]
    print(d.round(3).to_string(index=False))

# ---------- (b) 월간 앵커 top-N 포트 ----------
# 앵커: 매월 첫 거래일 (2024-01~), 진입 t+1 종가, h 보유, EW, 비용 0.5% 왕복
months=sorted(set(d[:6] for d in P.dates)); anchors=[]
for mo in months:
    i=P.idx(mo+"01")
    if i<T and P.dates[i][:6]==mo: anchors.append(i)
anchors=[a for a in anchors if P.dates[a]>="20240101"]
COST=0.005
rng=np.random.default_rng(1)
port=[]
for h in [60,120]:
    f=FW[h]
    for nm,sc in list(RULES.items())+[("R0_무작위20",None)]:
        for a in anchors:
            m=ok[a]&np.isfinite(f[a])
            if m.sum()<300 or not np.isfinite(f[a][m]).any(): continue
            if a+1+h>=T: continue
            if nm.startswith("R0"):
                cand=np.where(m)[0]; rets=[]
                for _ in range(50):
                    pick=rng.choice(cand,20,replace=False); rets.append(np.nanmean(f[a][pick]))
                pr=float(np.mean(rets))
            else:
                s=np.where(m,sc[a],np.nan)
                if np.isfinite(s).sum()<40: continue
                pick=np.argsort(-np.where(np.isfinite(s),s,-np.inf))[:20]
                pr=float(np.nanmean(f[a][pick]))
            mk_mix=np.mean(idx[np.where(m)[0]])  # 코스닥 비중
            ir=(1-mk_mix)*IK[h][a]+mk_mix*IQ[h][a]
            port.append(dict(h=h,rule=nm,anchor=P.dates[a],ret=pr-COST,idx=float(ir),ew=float(IDXM[h][a]),ex_idx=pr-COST-ir,ex_ew=pr-COST-float(IDXM[h][a])))
PT=pd.DataFrame(port); PT.to_csv(os.path.join(OUT,"monthly_topN.csv"),index=False)
summ=[]
for (h,nm),g in PT.groupby(["h","rule"]):
    blk=max(1,h//21)  # 겹침 보정 블록(앵커 월 단위)
    mi=fs.boot_ci(g.ex_idx.values,block=blk); me=fs.boot_ci(g.ex_ew.values,block=blk)
    d=dict(h=h,rule=nm,n_anchor=len(g),mean_ret=g.ret.mean(),mean_idx=g.idx.mean(),mean_ew=g.ew.mean(),
           ex_idx=mi[0],ex_idx_lo=mi[1],ex_idx_hi=mi[2],p_beat_idx=(g.ex_idx>0).mean(),
           ex_ew=me[0],ex_ew_lo=me[1],ex_ew_hi=me[2],p_beat_ew=(g.ex_ew>0).mean(),worst=g.ret.min(),best=g.ret.max())
    for y in ["2024","2025","2026"]:
        gy=g[g.anchor.str[:4]==y]; d["ex_idx_"+y]=gy.ex_idx.mean() if len(gy) else np.nan
    summ.append(d)
SM=pd.DataFrame(summ); SM.to_csv(os.path.join(OUT,"monthly_topN_summary.csv"),index=False)
print("===== monthly top20 (비용 0.5% 후) 요약"); print(SM.round(3).to_string(index=False))

# ---------- (d) cold 결합 ----------
E=EV[120]; h=120; m=ok&np.isfinite(FW[120])&(F["mom63"]<0.10); ex=EX[120]
cands=["mom126","mom252","mom12_1","dlow252","sma120gap","amt20","beta60","lv60","on60","bbw20","upvol20","vol_dry","size"]
lt=[]
for n in cands:
    r=R[n]
    for d,(lo_,hi_) in {"D1":(0,0.2),"D10":(0.8,1.01)}.items():
        sel=m&(r>=lo_)&(r<hi_)
        if sel.sum()>=500: lt.append((n,d,E[sel].mean()/E[m].mean()))
lt=pd.DataFrame(lt,columns=["f","d","lift"]); piv=lt.pivot(index="f",columns="d",values="lift")
piv["dir"]=np.where(piv.D10>=piv.D1,1,-1); piv["best"]=piv[["D1","D10"]].max(axis=1)
top=piv.sort_values("best",ascending=False).head(9)
masks={n:((R[n]>=0.8) if top.loc[n,"dir"]==1 else (R[n]<=0.2)) for n in top.index}
base=E[m].mean(); out=[]
for combo in list(itertools.combinations(list(masks),2))+list(itertools.combinations(list(masks),3)):
    sel=m.copy()
    for n in combo: sel&=masks[n]
    if sel.sum()<300: continue
    ep=0
    for j in np.where(sel.any(axis=0))[0]:
        w=np.where(sel[:,j]&E[:,j])[0]; last=-10**9
        for t in w:
            if t-last>=h: ep+=1; last=t
    x=ex[sel]; xu=EXU[120][sel]
    ys={y:float(E[sel&(yr==y)[:,None]].mean()/E[m&(yr==y)[:,None]].mean()) if (sel&(yr==y)[:,None]).sum()>=100 else np.nan for y in ["2023","2024","2025","2026"]}
    out.append(dict(combo="&".join(f"{n}{'↑' if top.loc[n,'dir']==1 else '↓'}" for n in combo),n=int(sel.sum()),events=int(E[sel].sum()),episodes=ep,
        lift=float(E[sel].mean()/base),mean_ex_idx=float(x.mean()),med_ex_idx=float(np.median(x)),mean_ex_ew=float(xu.mean()),p_beat_idx=float((x>0).mean()),p_lt_m30=float((x<=-0.3).mean()),**{"lift_"+y:v for y,v in ys.items()}))
CC=pd.DataFrame(out); CC.to_csv(os.path.join(OUT,"combos_cold.csv"),index=False)
print("===== cold combos (h120, episodes>=25)"); print(CC[CC.episodes>=25].sort_values("lift",ascending=False).head(12).round(3).to_string(index=False))
print(CC[CC.episodes>=25].sort_values("mean_ex_idx",ascending=False).head(6).round(3).to_string(index=False))

# ---------- (c) 위너 사례 — h120 에피소드 상위 (초과수익 기준), 시작 시점의 모습 ----------
E=EV[120]; m=ok&np.isfinite(FW[120]); ex=EX[120]
eps=[]
for j in range(N):
    w=np.where(E[:,j]&m[:,j])[0]
    if len(w)==0: continue
    last=-10**9; cur=None
    for t in w:
        if t-last>=120:
            if cur: eps.append(cur)
            cur=dict(j=j,t=t,best=ex[t,j]); last=t
        else:
            if ex[t,j]>cur["best"]: cur.update(t=t,best=ex[t,j])
    if cur: eps.append(cur)
rows=[]
for e in eps:
    j,t=e["j"],e["t"]
    rows.append(dict(ticker=P.tick[j],name=names.get(P.tick[j],""),market=P.mk[j],date=P.dates[t],fw120=FW[120][t,j],ex_idx=ex[t,j],
        mom12_1=F["mom12_1"][t,j],mom63=F["mom63"][t,j],nh252=F["nh252"][t,j],dlow252=F["dlow252"][t,j],
        beta60=F["beta60"][t,j],rv21_pct=R["rv21"][t,j],size_pct=R["size"][t,j],amt20_pct=R["amt20"][t,j],
        dsh=F["days_since_high"][t,j],range120_pct=R["range120"][t,j],mdd_path=MDD120[t,j],
        R1_pct=np.nan))
EP=pd.DataFrame(rows).sort_values("ex_idx",ascending=False)
r1=fs.rank01(np.where(ok,RULES["R1_달리는말(mom12_1↑+beta60↑+근고점)"],np.nan))
EP["R1_pct"]=[r1[P.idx(d),list(P.tick).index(tk)] for d,tk in zip(EP.date,EP.ticker)]
EP.to_csv(os.path.join(OUT,"winner_episodes_h120.csv"),index=False,encoding="utf-8-sig")
print("===== 위너 에피소드", len(EP)); print(EP.head(25).round(2).to_string(index=False))
print("에피소드 전체 중앙값:"); print(EP[["mom12_1","mom63","nh252","dlow252","beta60","rv21_pct","size_pct","amt20_pct","dsh","range120_pct","mdd_path","R1_pct"]].median().round(3))
print("R1 상위 20% 안에 있던 위너 비율:",(EP.R1_pct>=0.8).mean().round(3),"| 하위 50%:",(EP.R1_pct<0.5).mean().round(3))
print("연도별 에피소드:",EP.date.str[:4].value_counts().sort_index().to_dict())
