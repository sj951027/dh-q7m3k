# -*- coding: utf-8 -*-
"""
entry_lag_models_20260905.py — 실모델(v30·lv_b·sv_a·lv_a) '스크리너 다음날 매수' 유효성 (관측 전용, 읽기 전용)
진입 변형: t 종가(불가능·참조) · t+1 시가 · t+1 종가(현행 §11) · t+2 종가 · t+3 종가 · t+5 종가. 청산은 진입+20거래일 종가.
지표: 앵커별 상위20 초과(유니버스 중앙값 대비, 시장별 평균)·h20 IC. 게이트·앵커·중복제거·REG_DATE·JUMP_CAP 은 leaderboard.py 그대로.
"""
import os, sys, sqlite3
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import leaderboard as lb
H=20; TOP=20
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
VARS=[("t 종가(불가능·참조)",0,False),("t+1 시가",1,True),("t+1 종가(현행)",1,False),("t+2 종가",2,False),("t+3 종가",3,False),("t+5 종가",5,False)]
def boot(a,B=2000,seed=7):
    a=np.asarray(a,float); a=a[np.isfinite(a)]; n=len(a)
    if n==0: return (np.nan,np.nan,np.nan,0)
    rng=np.random.default_rng(seed); bs=[rng.choice(a,n).mean() for _ in range(B)]
    return (a.mean(),np.percentile(bs,2.5),np.percentile(bs,97.5),n)
rows=[]
for mid,tb,sc in MODELS:
    s=pd.read_sql(f"SELECT run_id,market,ticker,{sc} AS score FROM {tb} WHERE model_id=?",con,params=(mid,))
    s["ticker"]=s.ticker.astype(str); s["run_id"]=s.run_id.astype(str)
    reg=lb.REG_DATE.get(mid); keep=lb.dedupe_by_anchor(s,didx,excl,reg=reg)
    for lab,lag,uo in VARS:
        exc_l=[]; ic_l=[]
        for rid,g in s.groupby("run_id"):
            if rid not in keep: continue
            t=lb.anchor(rid,didx)
            if t is None or t+lag+H>=N: continue
            entry=(O if uo else C).iloc[t+lag]; exitp=C.iloc[t+lag+H]
            f=exitp/entry-1
            j=jump.iloc[t+lag+1:t+lag+H+1].max(); f=f.where(j<=lb.JUMP_CAP)
            de=[]; di=[]
            for mk,gm in g.groupby("market"):
                sv=gm.set_index("ticker")["score"].astype(float); sv=sv[~sv.index.duplicated()]
                b=f.reindex(sv.index); m=sv.notna()&b.notna()
                if m.sum()<lb.MIN_GROUP or sv[m].nunique()<3 or b[m].nunique()<3: continue
                di.append(np.corrcoef(sv[m].rank(),b[m].rank())[0,1])
                top=sv[m].sort_values(ascending=False).head(TOP).index
                de.append(float(b[m].reindex(top).mean()-b[m].median()))
            if de: exc_l.append(np.mean(de)); ic_l.append(np.mean(di))
        m,lo,hi,n=boot(exc_l); mi,ilo,ihi,_=boot(ic_l)
        rows.append(dict(model=mid,entry=lab,n=n,exc20_pct=round(m*100,2),lo=round(lo*100,2),hi=round(hi*100,2),
                         win=round(float(np.mean(np.array(exc_l)>0)),2) if n else None,ic20=round(mi,4),ic_lo=round(ilo,4),ic_hi=round(ihi,4)))
    print(mid,"done",flush=True)
df=pd.DataFrame(rows); os.makedirs("research/fullscan_20260903/out",exist_ok=True)
df.to_csv("research/fullscan_20260903/out/entry_lag_models.csv",index=False)
print(df.to_string(index=False))
