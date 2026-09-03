# step3: DART 공시 이벤트 스터디 (3년, 유형별, PIT) + 희석 회피 컷 효과. 산출 out/dart_*.csv
import numpy as np, pandas as pd, os, time, re
from fslib import *
t0=time.time(); P=Panel(); ok=guards(P); R=regimes(P); F=factors(P)
H=[5,20,60]; FWr={h:fwd(P,h) for h in H}; FW={h:excess(FWr[h],ok) for h in H}
c=P.close.astype(np.float64)
pre20=np.full_like(c,np.nan); pre20[20:]=c[20:]/c[:-20]-1; pre20=excess(pre20,ok)   # t-20 -> t
react=np.full_like(c,np.nan); react[1:-1]=c[2:]/c[:-2]-1                              # t-1 -> t+1 (공시 반응)
react=excess(react,ok)
ev=pd.read_sql("select rcept_no,rcept_dt,ticker,corp_name,market,event_type,report_nm from dart_events",ro(OHLCV))
ev=ev[ev.ticker.str.fullmatch(r"\d{6}")]
ev["corr"]=ev.report_nm.str.contains("기재정정|정정")
ev["ext"]=ev.report_nm.str.contains("연장")
ev["trust"]=ev.report_nm.str.contains("신탁")
ev["cancel"]=ev.report_nm.str.contains("소각")
ev["sub"]=ev.event_type
ev.loc[(ev.event_type=="buyback")&ev.trust,"sub"]="buyback_trust"
ev.loc[(ev.event_type=="buyback")&~ev.trust,"sub"]="buyback_direct"
ev.loc[ev.cancel,"sub"]=ev.loc[ev.cancel,"sub"]+"_cancel"
n0=len(ev); ev=ev[~ev["corr"]].copy()
ev=ev.sort_values(["ticker","sub","rcept_dt"])
# 같은 (ticker,sub) 30일 내 중복 → 첫 건만
ev["dt"]=pd.to_datetime(ev.rcept_dt)
keep=[]; last={}
for r in ev.itertuples():
    k=(r.ticker,r.sub); 
    if k in last and (r.dt-last[k]).days<=30: keep.append(False)
    else: keep.append(True); last[k]=r.dt
ev=ev[keep].copy(); print("events",n0,"->",len(ev))
ti={k:i for i,k in enumerate(P.tick)}
ev=ev[ev.ticker.isin(ti)].copy()
ev["t"]=[P.idx(d) for d in ev.rcept_dt]; ev=ev[(ev.t<P.T-2)&(ev.t>=P.idx("20230801"))]
ev["j"]=ev.ticker.map(ti)
tt=ev.t.values; jj=ev.j.values
ev["ok_t"]=ok[tt,jj]
for h in H:
    ev[f"ex{h}"]=FW[h][tt,jj]; ev[f"raw{h}"]=FWr[h][tt,jj]
    um=np.nanmean(np.where(ok,FW[h],np.nan),axis=1); ev[f"exm{h}"]=ev[f"ex{h}"]-um[tt]   # 유니버스 평균 대비
ev["pre20"]=pre20[tt,jj]; ev["react"]=react[tt,jj]
ev["year"]=ev.rcept_dt.str[:4]; ev["regime"]=R.regime_pit.values[tt]
sz=rank01(np.where(ok,F["size"],np.nan)); ev["size_q"]=pd.cut(sz[tt,jj],[0,1/3,2/3,1.01],labels=["소","중","대"])
lvp=rank01(np.where(ok,-(rank01(np.where(ok,F["lv60"],np.nan))+rank01(np.where(ok,F["to20"],np.nan))),np.nan))  # 조용함 상위=1
ev["quiet_q"]=pd.cut(lvp[tt,jj],[0,0.5,0.8,1.01],labels=["하위50","50~80","상위20"])
ev["rsi"]=F["rsi14"][tt,jj]
ev.to_csv(os.path.join(OUT,"dart_events_aligned.csv"),index=False)
def cb(v,tick,n=1000,seed=0):
    """종목 클러스터 부트스트랩"""
    v=np.asarray(v,float); m=np.isfinite(v); v=v[m]; tick=np.asarray(tick)[m]
    if len(v)<5: return (np.nan,np.nan,np.nan,len(v))
    u,inv=np.unique(tick,return_inverse=True); rng=np.random.default_rng(seed)
    sums=np.bincount(inv,weights=v); cnts=np.bincount(inv)
    means=[]
    for _ in range(n):
        s=rng.integers(0,len(u),len(u)); means.append(sums[s].sum()/cnts[s].sum())
    return (float(v.mean()),float(np.percentile(means,2.5)),float(np.percentile(means,97.5)),len(v))
rows=[]
def add(df,grp,label):
    for key,g in df.groupby(grp,observed=True):
        for h in ["pre20","react","ex5","ex20","ex60","raw20","exm20","exm60"]:
            m,lo,hi,n=cb(g[h],g.ticker); rows.append(dict(cut=label,key=str(key),metric=h,n=n,mean=m,lo=lo,hi=hi,pos=float(np.nanmean(g[h]>0)) if n else np.nan))
base=ev[ev.ok_t]   # 가드 통과 종목만(유동성 5억↑ 등)
add(base,"sub","type"); add(base,["sub","year"],"type_year"); add(base,["sub","regime"],"type_regime"); add(base,["sub","size_q"],"type_size"); add(base,["sub","quiet_q"],"type_quiet")
add(base[base.ext],"sub","type_ext_only"); add(base[~base.ext],"sub","type_noext")
add(ev[~ev.ok_t],"sub","type_guardfail")
pd.DataFrame(rows).to_csv(os.path.join(OUT,"dart_event_study.csv"),index=False)
# ---- 회피 컷 효과 (3년 일별): 직전 60거래일 내 희석 결정 공시 있는 종목 제외
dil=ev[ev.event_type.isin(["paid_in","cb","bw","eb","paid_bonus_mix"])]
flag=np.zeros((P.T,P.N),bool)
for r in dil.itertuples():
    flag[r.t:min(P.T,r.t+61),r.j]=True
flag_any=np.zeros((P.T,P.N),bool)
for r in ev[ev.event_type.isin(["paid_in","cb","bw","eb","paid_bonus_mix","bonus","reduction"])].itertuples():
    flag_any[r.t:min(P.T,r.t+61),r.j]=True
start=P.idx("20240101")
sets={"전체(가드)":ok,"조용함상위20%":ok&(lvp>=0.8),"과매도프록시(RSI<35)":ok&(F["rsi14"]<35),"저변동상위20%&RSI<45":ok&(lvp>=0.8)&(F["rsi14"]<45)}
crow=[]
for nm,S in sets.items():
    for fl,fln in [(flag,"희석(유상·CB·BW·EB·혼합)60d"),(flag_any,"희석+무상+감자60d")]:
        for h in [20,60]:
            a=[];b=[];frac=[]
            for t in range(start,P.T):
                s=S[t]; 
                if s.sum()<30: continue
                x=FW[h][t]
                v_all=np.nanmean(x[s]); v_cut=np.nanmean(x[s&~fl[t]]); 
                if np.isfinite(v_all) and np.isfinite(v_cut): a.append(v_all); b.append(v_cut); frac.append((s&fl[t]).sum()/s.sum())
            a=np.array(a); b=np.array(b); d=b-a; m,lo,hi,n=boot_ci(d,600,block=5)
            for rg in ["강세","약세","반등","조정"]: pass
            crow.append(dict(universe=nm,cut=fln,h=h,n_days=n,excluded_frac=float(np.mean(frac)),mean_all=float(a.mean()),mean_cut=float(b.mean()),diff=m,lo=lo,hi=hi,pos=float(np.mean(d>0))))
            # 플래그 종목 자체의 초과수익
            fv=[np.nanmean(FW[h][t][S[t]&fl[t]]) for t in range(start,P.T) if (S[t]&fl[t]).sum()>=3]
            m2,lo2,hi2,n2=boot_ci(fv,600,block=5)
            crow.append(dict(universe=nm,cut=fln+"_플래그종목자체",h=h,n_days=n2,excluded_frac=np.nan,mean_all=np.nan,mean_cut=np.nan,diff=m2,lo=lo2,hi=hi2,pos=float(np.mean(np.array(fv)>0))))
pd.DataFrame(crow).to_csv(os.path.join(OUT,"dart_avoid_cut.csv"),index=False)
print(pd.DataFrame(crow).round(4).to_string()); print("done",time.time()-t0)
