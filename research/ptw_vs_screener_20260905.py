# -*- coding: utf-8 -*-
"""ptw_vs_screener_20260905.py — 포지션 트래커 실거래(청산 62·보유 10) vs 스크리너 데이터 (관측 전용, 읽기 전용)
① 실현 수익률 vs 같은 기간 시장평균(전종목 EW)·lv_b 상위20 따라사기  ② 매수일 직전 run 에서 그 종목의 lv_b 순위(어디쯤을 샀나)
③ 보유기간 분포(40일 규약 대비)  ④ 보유 종목 현황 vs 유니버스 중앙값"""
import sqlite3, pandas as pd, numpy as np
oc=sqlite3.connect("file:../dh-q7m3k-data/ohlcv.db?mode=ro",uri=True); hc=sqlite3.connect("file:history.db?mode=ro",uri=True)
px=pd.read_sql("select ticker,date,close,change_pct from daily_ohlcv where date>='20260501'",oc); px["ticker"]=px.ticker.astype(str)
C=px.pivot_table(index="date",columns="ticker",values="close",aggfunc="last"); R=px.pivot_table(index="date",columns="ticker",values="change_pct",aggfunc="last")
amt=pd.read_sql("select ticker,date,close*volume amt from daily_ohlcv where date>='20260401'",oc); amt["ticker"]=amt.ticker.astype(str)
A=amt.pivot_table(index="date",columns="ticker",values="amt").rolling(20,min_periods=10).mean()/1e8
dates=list(C.index)
def d2(s,y="2026"): return y+s.replace("-","")
def ew_ret(a,b):  # a<b, 가드 유니버스(amt20>=5억) EW 누적
    ds=[d for d in dates if a<d<=b]
    if not ds: return np.nan
    r=1.0
    for d in ds:
        sel=A.loc[d][A.loc[d]>=5].index.intersection(R.columns); r*=1+R.loc[d,sel].astype(float).mean()
    return (r-1)*100
lvb=pd.read_sql("select run_id,market,ticker,lowvol_score from lowvol_scores where model_id='lv_b'",hc); lvb["ticker"]=lvb.ticker.astype(str); lvb["run_id"]=lvb.run_id.astype(str)
lvb["rank"]=lvb.groupby(["run_id","market"]).lowvol_score.rank(ascending=False,method="min"); lvb["n"]=lvb.groupby(["run_id","market"]).ticker.transform("count")
runs=sorted(lvb.run_id.unique())
def top20_ret(a,b):  # 매수일 직전 run 의 lv_b 상위20(시장 합산) 을 a 종가에 사서 b 종가에 판 평균
    prev=[r for r in runs if r<a]
    if not prev: return np.nan
    rid=prev[-1]; top=lvb[(lvb.run_id==rid)&(lvb["rank"]<=10)].ticker.tolist()   # 시장별 10 → 합 20
    top=[t for t in top if t in C.columns and a in C.index and b in C.index]
    if not top: return np.nan
    return float((C.loc[b,top]/C.loc[a,top]-1).mean()*100)
def lvb_rank(code,a):
    prev=[r for r in runs if r<a]
    if not prev: return (None,None)
    g=lvb[(lvb.run_id==prev[-1])&(lvb.ticker==code)]
    return (int(g["rank"].iloc[0]),int(g["n"].iloc[0])) if len(g) else (None,None)
cl=pd.read_csv("research/ptw_closed_20260905.csv",dtype={"code":str}); cl["a"]=cl.first_buy.map(d2); cl["b"]=cl.closed_at.map(d2)
cl["hold_td"]=[sum(1 for d in dates if a<d<=b) for a,b in zip(cl.a,cl.b)]
cl["mkt"]=[ew_ret(a,b) for a,b in zip(cl.a,cl.b)]; cl["lvb_top20"]=[top20_ret(a,b) for a,b in zip(cl.a,cl.b)]
rk=[lvb_rank(c,a) for c,a in zip(cl.code,cl.a)]; cl["lvb_rank"]=[r[0] for r in rk]; cl["lvb_n"]=[r[1] for r in rk]
cl["exc_mkt"]=cl.ret_pct-cl.mkt; cl["vs_top20"]=cl.ret_pct-cl.lvb_top20
pd.set_option("display.width",250)
print("== 청산 62건 · 전략별 (실현수익% 평균 / 시장초과 %p / lv_b top20 대비 %p / 승률 / 보유 거래일 중앙값)")
g=cl.groupby("strategy").agg(n=("ret_pct","size"),ret=("ret_pct","mean"),exc_mkt=("exc_mkt","mean"),vs_top20=("vs_top20","mean"),win=("ret_pct",lambda x:(x>0).mean()),hold_td=("hold_td","median"),pnl=("realized_pnl","sum")).round(2); print(g.to_string())
print("\n== 월별(청산월) 실현 손익 합·건수·시장초과 평균")
cl["m"]=cl.b.str[4:6]; print(cl.groupby("m").agg(n=("ret_pct","size"),ret=("ret_pct","mean"),exc_mkt=("exc_mkt","mean"),pnl=("realized_pnl","sum")).round(2).to_string())
lv=cl[cl.strategy=="저변동"].copy()
print(f"\n== #저변동 {len(lv)}건: 평균 {lv.ret_pct.mean():+.2f}% (중앙값 {lv.ret_pct.median():+.2f}) · 시장초과 {lv.exc_mkt.mean():+.2f}%p · 같은 기간 lv_b top20 따라사기 대비 {lv.vs_top20.mean():+.2f}%p · 승률 {(lv.ret_pct>0).mean():.0%} · 보유 거래일 중앙값 {lv.hold_td.median():.0f} (≥40일 {int((lv.hold_td>=40).sum())}건)")
print("   매수 직전 run lv_b 순위(시장 내):", lv[["code","a","lvb_rank","lvb_n","hold_td","ret_pct","exc_mkt"]].sort_values("a").to_string(index=False))
# 보유 중
po=pd.read_csv("research/ptw_positions_20260905.csv",dtype={"code":str}); po["a"]=po.first_buy.str.replace("-","")
last=dates[-1]; po["mkt"]=[ew_ret(a,last) for a in po.a]; po["lvb_top20"]=[top20_ret(a,last) for a in po.a]
rk=[lvb_rank(c,a) for c,a in zip(po.code,po.a)]; po["lvb_rank"]=[r[0] for r in rk]; po["lvb_n"]=[r[1] for r in rk]
po["exc_mkt"]=po.pnl-po.mkt
print("\n== 보유 10건 (평가수익% / 같은 기간 시장 / 초과 / lv_b top20 / 매수 직전 순위)")
print(po[["code","name","strategy","first_buy","tdays","pnl","mkt","exc_mkt","lvb_top20","lvb_rank","lvb_n","signal"]].round(2).to_string(index=False))
print(f"\n보유 합계 평가손익 {po.pnl_amt.sum():,.0f}원 / 평가액 {po.eval_amt.sum():,.0f}원 → {po.pnl_amt.sum()/ (po.eval_amt.sum()-po.pnl_amt.sum())*100:+.2f}%")
cl.to_csv("research/fullscan_20260903/out/ptw_closed_vs_screener.csv",index=False); po.to_csv("research/fullscan_20260903/out/ptw_positions_vs_screener.csv",index=False)
