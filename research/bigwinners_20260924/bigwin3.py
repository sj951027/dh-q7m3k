# bigwin3.py — R1 규칙 해부: 시장별 분해 · 성분 제거 · 비겹침 창 · 픽 구성 · 위너 명단(utf-8 파일)
import os, sys, numpy as np, pandas as pd
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from bw_build import *
def rs(names_dirs):
    sc=None
    for n,d in names_dirs:
        r=R[n] if d>0 else 1-R[n]
        sc=r.copy() if sc is None else sc+np.where(np.isfinite(r),r,0.5)
    return sc
VAR={"R1 full (mom12_1+beta60+near_high)":rs([("mom12_1",1),("beta60",1),("days_since_high",-1)]),
     "R1-beta (mom12_1+near_high)":rs([("mom12_1",1),("days_since_high",-1)]),
     "R1-mom (beta60+near_high)":rs([("beta60",1),("days_since_high",-1)]),
     "R1-nearhigh (mom12_1+beta60)":rs([("mom12_1",1),("beta60",1)]),
     "R1 + amt20 (유동성 추가)":rs([("mom12_1",1),("beta60",1),("days_since_high",-1),("amt20",1)]),
     "R1 + size↓ (소형 한정)":rs([("mom12_1",1),("beta60",1),("days_since_high",-1),("size",-1)]),
     "R1 with mom126 instead":rs([("mom126",1),("beta60",1),("days_since_high",-1)]),
     "near_high only":rs([("days_since_high",-1)]),
    }
def fwd_idx(x,h):
    o=np.full(T,np.nan); o[:T-1-h]=x[1+h:]/x[1:T-h]-1; return o
COST=0.005
def run(sc,h,anchors,market=None,N=20):
    f=FW[h]; out=[]
    for a in anchors:
        m=ok[a]&np.isfinite(f[a])
        if market is not None: m&=(P.mk==market)
        s=np.where(m,sc[a],np.nan)
        if np.isfinite(s).sum()<40 or a+1+h>=T: continue
        pick=np.argsort(-np.where(np.isfinite(s),s,-np.inf))[:N]
        pr=float(np.nanmean(f[a][pick]))-COST
        ew=float(np.nanmean(np.where(m,f[a],np.nan)))
        if market is None:
            mix=np.mean(idx[np.where(m)[0]]); ir=(1-mix)*fwd_idx(kp,h)[a]+mix*fwd_idx(kq,h)[a]
        else: ir=(fwd_idx(kp,h) if market=="KOSPI" else fwd_idx(kq,h))[a]
        out.append(dict(anchor=P.dates[a],ret=pr,idx=float(ir),ew=ew,ex_idx=pr-ir,ex_ew=pr-ew,
                        kospi_share=float(np.mean(idx[pick]==0)),size_pct=float(np.nanmedian(R["size"][a][pick])),amt_pct=float(np.nanmedian(R["amt20"][a][pick])),
                        n_win=int(EV[h][a][pick].sum()),worst_pick=float(np.nanmin(f[a][pick])),best_pick=float(np.nanmax(f[a][pick]))))
    return pd.DataFrame(out)
months=sorted(set(d[:6] for d in P.dates)); anchors=[]
for mo in months:
    i=P.idx(mo+"01")
    if i<T and P.dates[i][:6]==mo and P.dates[i]>="20240101": anchors.append(i)
rows=[]
for nm,sc in VAR.items():
    for h in [60,120]:
        for mk in [None,"KOSPI","KOSDAQ"]:
            g=run(sc,h,anchors,mk)
            if len(g)==0: continue
            blk=max(1,h//21); ci=fs.boot_ci(g.ex_idx.values,block=blk); ce=fs.boot_ci(g.ex_ew.values,block=blk)
            rows.append(dict(variant=nm,h=h,market=mk or "ALL",n_anchor=len(g),ret=g.ret.mean(),idx=g.idx.mean(),ew=g.ew.mean(),
                ex_idx=ci[0],ex_idx_lo=ci[1],ex_idx_hi=ci[2],p_beat_idx=(g.ex_idx>0).mean(),ex_ew=ce[0],ex_ew_lo=ce[1],ex_ew_hi=ce[2],
                kospi_share=g.kospi_share.mean(),size_pct=g.size_pct.mean(),amt_pct=g.amt_pct.mean(),avg_winners_of20=g.n_win.mean(),worst=g.ret.min()))
AB=pd.DataFrame(rows); AB.to_csv(os.path.join(OUT,"r1_ablation.csv"),index=False)
# 비겹침 창(120일 간격) R1 full
sc=VAR["R1 full (mom12_1+beta60+near_high)"]
start=P.idx("20240701")  # mom12_1 가용 시점부터
nonov=list(range(start,T-121,120))
g=run(sc,120,nonov); g.to_csv(os.path.join(OUT,"r1_nonoverlap_h120.csv"),index=False)
g2=run(sc,60,list(range(start,T-61,60))); g2.to_csv(os.path.join(OUT,"r1_nonoverlap_h60.csv"),index=False)
# 월별 앵커 전체 기록(R1 full h120) — 연도별·앵커별
g3=run(sc,120,anchors); g3.to_csv(os.path.join(OUT,"r1_monthly_h120.csv"),index=False)
# 최신 앵커에서 R1 상위 20 (오늘 기준 참고용, 판정 아님)
a=T-1; m=ok[a]; s=np.where(m,sc[a],np.nan); pick=np.argsort(-np.where(np.isfinite(s),s,-np.inf))[:20]
cur=pd.DataFrame(dict(ticker=P.tick[pick],name=[names.get(t,"") for t in P.tick[pick]],market=P.mk[pick],mom12_1=F["mom12_1"][a][pick],beta60=F["beta60"][a][pick],days_since_high=F["days_since_high"][a][pick],size_pct=R["size"][a][pick],amt_pct=R["amt20"][a][pick]))
cur.to_csv(os.path.join(OUT,"r1_current_top20.csv"),index=False,encoding="utf-8-sig")
with open(os.path.join(OUT,"summary3.txt"),"w",encoding="utf-8") as fh:
    fh.write(AB.round(3).to_string(index=False)+"\n\n비겹침 h120:\n"+g.round(3).to_string(index=False)+"\n\n비겹침 h60:\n"+g2.round(3).to_string(index=False)+"\n\n월별 h120:\n"+g3.round(3).to_string(index=False)+"\n\n현재 R1 top20 (2026-09-23):\n"+cur.round(2).to_string(index=False))
print("ok")
