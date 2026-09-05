# -*- coding: utf-8 -*-
"""lv_b 상위(시장별 30) 안에서 수급(외인·기관·연기금 5일/20일 순매수, 거래대금 대비)이 이후 20일 초과수익과 관련 있나 — 라이브 6~9월(관측, 소표본)"""
import sqlite3, pandas as pd, numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import leaderboard as lb
oc=sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro",uri=True); hc=sqlite3.connect(f"file:{lb.DB}?mode=ro",uri=True)
fl=pd.read_sql("select ticker,date,foreign_net_val f,inst_net_val i,pension_net_val p from daily_flows",oc); fl["ticker"]=fl.ticker.astype(str)
px=pd.read_sql("select ticker,date,close,volume from daily_ohlcv where date>='20260401'",oc); px["ticker"]=px.ticker.astype(str)
C=px.pivot_table(index="date",columns="ticker",values="close"); AMT=(px.assign(a=px.close*px.volume)).pivot_table(index="date",columns="ticker",values="a").rolling(20,min_periods=10).mean()
dates=list(C.index); didx={d:i for i,d in enumerate(dates)}; N=len(dates)
FV={k:fl.pivot_table(index="date",columns="ticker",values=k).reindex(dates) for k in "fip"}
lvb=pd.read_sql("select run_id,market,ticker,lowvol_score from lowvol_scores where model_id='lv_b'",hc); lvb["ticker"]=lvb.ticker.astype(str); lvb["run_id"]=lvb.run_id.astype(str)
lvb["rank"]=lvb.groupby(["run_id","market"]).lowvol_score.rank(ascending=False,method="min")
jump=C.pct_change(fill_method=None).abs()
rows=[]
for rid,g in lvb[lvb["rank"]<=30].groupby("run_id"):
    if rid not in didx: continue
    t=didx[rid]
    if t+21>=N or t<20: continue
    f=C.iloc[t+21]/C.iloc[t+1]-1; j=jump.iloc[t+2:t+22].max(); f=f.where(j<=lb.JUMP_CAP)
    uni=lvb[lvb.run_id==rid].ticker; med=f.reindex(uni).median()
    for _,r in g.iterrows():
        tk=r.ticker
        if tk not in C.columns or not np.isfinite(f.get(tk,np.nan)): continue
        a=AMT.iloc[t].get(tk,np.nan)
        rec=dict(run_id=rid,ticker=tk,exc=f[tk]-med)
        for k,nm in zip("fip",["foreign","inst","pension"]):
            s=FV[k][tk] if tk in FV[k].columns else None
            if s is None: rec[nm+"5"]=np.nan; rec[nm+"20"]=np.nan; continue
            rec[nm+"5"]=s.iloc[t-4:t+1].sum()/a if a and np.isfinite(a) else np.nan
            rec[nm+"20"]=s.iloc[t-19:t+1].sum()/a if a and np.isfinite(a) else np.nan
        rows.append(rec)
D=pd.DataFrame(rows); print("표본 행",len(D),"앵커",D.run_id.nunique(),"기간",D.run_id.min(),"~",D.run_id.max())
def boot(a,B=1500):
    a=np.asarray(a,float); a=a[np.isfinite(a)]; rng=np.random.default_rng(7); bs=[rng.choice(a,len(a)).mean() for _ in range(B)]; return a.mean(),np.percentile(bs,2.5),np.percentile(bs,97.5),len(a)
out=[]
for col in ["foreign5","foreign20","inst5","inst20","pension5","pension20"]:
    d=D.dropna(subset=[col]); 
    if d.empty: continue
    # 앵커별: 순매수 상위 1/3 − 하위 1/3 초과 차이 + 부호(>0 vs ≤0)
    diffs=[]; pos_neg=[]
    for rid,g in d.groupby("run_id"):
        if len(g)<9: continue
        q=g[col].quantile([1/3,2/3]).values; hi=g[g[col]>=q[1]].exc.mean(); lo=g[g[col]<=q[0]].exc.mean(); diffs.append(hi-lo)
        a1=g[g[col]>0].exc.mean(); a0=g[g[col]<=0].exc.mean()
        if np.isfinite(a1) and np.isfinite(a0): pos_neg.append(a1-a0)
    m,lo_,hi_,n=boot(diffs); m2,lo2,hi2,n2=boot(pos_neg)
    ic=d.groupby("run_id").apply(lambda g: g[[col,"exc"]].corr(method="spearman").iloc[0,1] if len(g)>=9 else np.nan).dropna()
    out.append(dict(flow=col,n_anchor=n,top3_minus_bot3_pp=m*100,lo=lo_*100,hi=hi_*100,buy_minus_sell_pp=m2*100,lo2=lo2*100,hi2=hi2*100,rank_ic=ic.mean(),ic_pos=(ic>0).mean()))
pd.set_option("display.width",250); print(pd.DataFrame(out).round(3).to_string(index=False))
