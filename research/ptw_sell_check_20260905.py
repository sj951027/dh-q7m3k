# -*- coding: utf-8 -*-
"""실제 매도 시점 검증 — 판 뒤에 어떻게 됐나 (종목 5/10/20일 vs 시장, '40일까지 들고 갔다면' 대비), 매도 시점 상태(손익·RSI 5일 변화·시장대비)"""
import sqlite3, pandas as pd, numpy as np
oc=sqlite3.connect("file:../dh-q7m3k-data/ohlcv.db?mode=ro",uri=True)
px=pd.read_sql("select ticker,date,close,change_pct from daily_ohlcv where date>='20260401'",oc); px["ticker"]=px.ticker.astype(str)
C=px.pivot_table(index="date",columns="ticker",values="close"); R=px.pivot_table(index="date",columns="ticker",values="change_pct")
amt=pd.read_sql("select ticker,date,close*volume a from daily_ohlcv where date>='20260301'",oc); amt["ticker"]=amt.ticker.astype(str)
A=amt.pivot_table(index="date",columns="ticker",values="a").rolling(20,min_periods=10).mean()/1e8
dates=list(C.index); di={d:i for i,d in enumerate(dates)}; N=len(dates)
ew=pd.Series({d: R.loc[d, A.loc[d][A.loc[d]>=5].index.intersection(R.columns)].astype(float).mean() for d in dates if d in A.index})
def ewret(a,b): s=ew[(ew.index>a)&(ew.index<=b)]; return float(np.prod(1+s)-1)*100 if len(s) else np.nan
def rsi(series,n=14):
    d=series.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0); au=up.ewm(alpha=1/n,min_periods=n).mean(); ad=dn.ewm(alpha=1/n,min_periods=n).mean(); return 100-100/(1+au/ad)
cl=pd.read_csv("research/ptw_closed_20260905.csv",dtype={"code":str}); cl["a"]="2026"+cl.first_buy.str.replace("-",""); cl["b"]="2026"+cl.closed_at.str.replace("-","")
rows=[]
for _,r in cl.iterrows():
    t=r.code
    if t not in C.columns or r.a not in di or r.b not in di: continue
    ia,ib=di[r.a],di[r.b]; s=C[t]; rs_=rsi(s)
    rec=dict(code=t,strategy=r.strategy,buy=r.first_buy,sell=r.closed_at,hold_td=ib-ia,ret=r.ret_pct)
    rec["pnl_at_sell"]=(s.iloc[ib]/s.iloc[ia]-1)*100
    rec["rsi_sell"]=rs_.iloc[ib]; rec["rsi_chg5"]=rs_.iloc[ib]-rs_.iloc[ib-5]
    rec["rs_vs_mkt"]=rec["pnl_at_sell"]-ewret(r.a,r.b)
    for k in (5,10,20):
        j=min(ib+k,N-1); rec[f"after{k}"]=(s.iloc[j]/s.iloc[ib]-1)*100; rec[f"after{k}_mkt"]=ewret(r.b,dates[j]); rec[f"after{k}_exc"]=rec[f"after{k}"]-rec[f"after{k}_mkt"]
        rec[f"closed{k}"]=ib+k<=N-1
    j40=min(ia+40,N-1); rec["hold40_ret"]=(s.iloc[j40]/s.iloc[ia]-1)*100; rec["hold40_closed"]=ia+40<=N-1
    rec["sell_vs_hold40"]=rec["pnl_at_sell"]-rec["hold40_ret"]
    rows.append(rec)
D=pd.DataFrame(rows); pd.set_option("display.width",260)
D["type"]=np.where(D.rsi_chg5<=-10,"RSI급락",np.where(D.pnl_at_sell>=15,"+15%↑",np.where(D.rs_vs_mkt<=-10,"시장대비약세",np.where(D.pnl_at_sell<=-7,"손실컷","기타"))))
lv=D[D.strategy.isin(["저변동","모멘텀","모멘텀b","공매도"])].copy()
print("== 7월 이후(비스윙) 매도 %d건 — 판 뒤 20일 종목수익 / 시장 / 초과, '40일까지 들고 갔다면' 대비 (양수=잘 판 것)"%len(lv))
cols=["code","strategy","buy","sell","hold_td","pnl_at_sell","rsi_sell","rsi_chg5","rs_vs_mkt","type","after5_exc","after10_exc","after20_exc","closed20","hold40_ret","hold40_closed","sell_vs_hold40"]
print(lv[cols].round(1).sort_values("sell").to_string(index=False))
def summ(d,lab):
    c20=d[d.closed20]; print(f"  {lab:12s} n={len(d):2d} | 판 뒤 20일 종목 {d.after20.mean():+.1f}% 시장 {d.after20_mkt.mean():+.1f}% → 초과 {d.after20_exc.mean():+.1f}%p (창 닫힌 {len(c20)}건 {c20.after20_exc.mean() if len(c20) else float('nan'):+.1f}) | 판 뒤 초과 음(잘 판) 비율 {(d.after20_exc<0).mean():.0%} | 매도 vs 40일보유 {d.sell_vs_hold40.mean():+.1f}%p (창 닫힌 {d.hold40_closed.sum()}건 {d[d.hold40_closed].sell_vs_hold40.mean() if d.hold40_closed.any() else float('nan'):+.1f})")
print("\n== 매도 시점 유형별")
for lab,g in lv.groupby("type"): summ(g,lab)
summ(lv,"전체(비스윙)"); summ(D[D.strategy=="스윙"],"스윙(5~6월)")
D.to_csv("research/fullscan_20260903/out/ptw_sell_check.csv",index=False)
