# -*- coding: utf-8 -*-
"""
event_path_models_20260905.py — 실모델 상위20 '앵커 이후 날짜별 누적 초과수익 경로' (관측 전용, 읽기 전용)
질문: "lv_b 가 지연에 약하다 = 하루만 오르고 그 뒤 빠지는 것 아닌가?" → 진입(t+1 종가) 후 k=1..40일 누적 초과(유니버스 중앙값 대비)와
      하루 단위(마진) 초과를 앵커 평균으로 본다. 앵커 집합은 k 상한별로 고정(창이 닫힌 앵커만) — 표본 혼합 방지.
"""
import os, sys, sqlite3
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import leaderboard as lb
TOP=20
oc=sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro",uri=True)
px=pd.read_sql("SELECT ticker,date,open,close FROM daily_ohlcv WHERE date>='20260401'",oc); oc.close()
px["ticker"]=px.ticker.astype(str)
C=px.pivot_table(index="date",columns="ticker",values="close",aggfunc="last").sort_index()
O=px.pivot_table(index="date",columns="ticker",values="open",aggfunc="last").sort_index().reindex(columns=C.columns)
dates=list(C.index); N=len(dates); didx={d:i for i,d in enumerate(dates)}
con=sqlite3.connect(f"file:{lb.DB}?mode=ro",uri=True)
partial,dbl,_=lb.build_gates(con,dates); excl=partial|dbl
jump=C.pct_change(fill_method=None).abs()
MODELS=[("v30","v3_scores","final_score_v3"),("lv_b","lowvol_scores","lowvol_score"),("lv_a","lowvol_scores","lowvol_score"),("sv_a","wu_scores","wu_score")]
def boot(a,B=1500,seed=7):
    a=np.asarray(a,float); a=a[np.isfinite(a)]; n=len(a)
    if n==0: return (np.nan,np.nan,np.nan,0)
    rng=np.random.default_rng(seed); bs=[rng.choice(a,n).mean() for _ in range(B)]
    return (a.mean(),np.percentile(bs,2.5),np.percentile(bs,97.5),n)
rows=[]
for mid,tb,sc in MODELS:
    s=pd.read_sql(f"SELECT run_id,market,ticker,{sc} AS score FROM {tb} WHERE model_id=?",con,params=(mid,))
    s["ticker"]=s.ticker.astype(str); s["run_id"]=s.run_id.astype(str)
    reg=lb.REG_DATE.get(mid); keep=lb.dedupe_by_anchor(s,didx,excl,reg=reg)
    for KMAX in (20,40):
        paths=[]   # 앵커별 (KMAX+1,) 누적 초과 경로 (k=0 = t+1 종가 진입 시점 0)
        open_gap=[]  # t+1 시가→종가 초과(진입 지연 손실분)
        for rid,g in s.groupby("run_id"):
            if rid not in keep: continue
            t=lb.anchor(rid,didx)
            if t is None or t+1+KMAX>=N: continue
            e=C.iloc[t+1]; eo=O.iloc[t+1]
            j=jump.iloc[t+2:t+2+KMAX].max(); okj=(j<=lb.JUMP_CAP)
            per_mk=[]; per_gap=[]
            for mk,gm in g.groupby("market"):
                sv=gm.set_index("ticker")["score"].astype(float); sv=sv[~sv.index.duplicated()]
                uni=[x for x in sv.index if x in C.columns]
                if len(uni)<lb.MIN_GROUP: continue
                sv=sv[uni]; top=sv.sort_values(ascending=False).head(TOP).index
                cum=np.array([(C.iloc[t+1+k][uni]/e[uni]-1).where(okj[uni]) for k in range(KMAX+1)])  # (K+1, n_uni)
                med=np.nanmedian(cum,axis=1); topm=np.nanmean(cum[:,[uni.index(x) for x in top]],axis=1)
                per_mk.append(topm-med)
                g0=(e[uni]/eo[uni]-1).where(okj[uni]); per_gap.append(float(np.nanmean(g0[top])-np.nanmedian(g0)))
            if per_mk: paths.append(np.mean(per_mk,axis=0)); open_gap.append(np.mean(per_gap))
        if not paths: continue
        P_=np.array(paths); n=len(P_)
        for k in ([1,2,3,5,10,15,20] if KMAX==20 else [1,3,5,10,20,25,30,35,40]):
            m,lo,hi,_=boot(P_[:,k]); marg=P_[:,k]-P_[:,k-1] if k>0 else P_[:,k]
            rows.append(dict(model=mid,kmax=KMAX,n=n,k=k,cum_exc_pct=round(m*100,2),lo=round(lo*100,2),hi=round(hi*100,2),
                             win=round(float(np.mean(P_[:,k]>0)),2),day_exc_bp=round(float(np.nanmean(marg))*1e4,1)))
        # 하루 단위 경로(1~KMAX) 콤팩트 출력
        daily=(P_[:,1:]-P_[:,:-1]).mean(axis=0)*1e4
        print(f"{mid} KMAX={KMAX} n={n} | t+1 시가→종가 상위20 초과 {np.mean(open_gap)*1e4:+.0f}bp | 일별 마진 초과(bp) k=1..{KMAX}: "+" ".join(f"{x:+.0f}" for x in daily), flush=True)
df=pd.DataFrame(rows); df.to_csv("research/fullscan_20260903/out/event_path_models.csv",index=False)
print(df.to_string(index=False))
