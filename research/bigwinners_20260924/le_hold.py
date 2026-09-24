# le_hold.py — le_a 보유기간별 성과. (A) 실제 동결 점수 OOS(wu_scores le_a, 2026-07-15~) 시장별 상위10 · h=5..40
#                                  (B) 3년 패널 in-sample 재현(dlow252↑+obv63↓+amt20↑), 월간/5일 앵커, h=5..120, 경로 곡선
import os, sys, sqlite3, numpy as np, pandas as pd
S=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,S)
REPO=r"C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k"
print("=== (A) 실제 OOS — wu_scores le_a, 시장별 상위10, 다음날 종가 진입, 비용 0.35%(성적표와 동일 가정)")
hc=sqlite3.connect(f"file:{REPO}/history.db?mode=ro",uri=True)
S_=pd.read_sql("SELECT run_id,market,ticker,wu_score AS score FROM wu_scores WHERE model_id='le_a'",hc); hc.close()
oc=sqlite3.connect(f"file:{REPO}/../dh-q7m3k-data/ohlcv.db?mode=ro",uri=True)
px=pd.read_sql("SELECT ticker,date,close,market FROM daily_ohlcv WHERE date>='20260701'",oc)
md=pd.read_sql("SELECT series,date,close FROM market_daily WHERE date>='20260701'",oc).pivot(index="date",columns="series",values="close"); oc.close()
C=px.pivot(index="date",columns="ticker",values="close").sort_index(); dates=list(C.index)
mk=px.groupby("ticker").market.last().str.upper()
S_["ticker"]=S_.ticker.astype(str).str.zfill(6); S_["market"]=S_.market.str.upper()
rows=[]
for rid,g in S_.groupby("run_id"):
    if rid not in dates: continue
    t=dates.index(rid)
    for h in [3,5,10,15,20,30,40]:
        if t+1+h>=len(dates): continue
        e=C.iloc[t+1]; r=C.iloc[t+1+h]/e-1
        ex_ew=[]; ex_idx=[]; ret=[]
        for m,gm in g.groupby("market"):
            top=gm.nlargest(10,"score").ticker; a=r.reindex(top).dropna()
            if len(a)<5: continue
            uni=r[mk.reindex(r.index)==m].dropna()
            idx=md[m].loc[dates[t+1+h]]/md[m].loc[dates[t+1]]-1
            ret.append(a.mean()-0.0035); ex_ew.append(a.mean()-0.0035-(uni.mean()-0.0035)); ex_idx.append(a.mean()-0.0035-idx)
        if ret: rows.append(dict(run_id=rid,h=h,ret=np.mean(ret),ex_ew=np.mean(ex_ew),ex_idx=np.mean(ex_idx)))
A=pd.DataFrame(rows)
def bci(x,block,n=3000,seed=924):
    x=np.asarray(x,float); L=len(x); rng=np.random.default_rng(seed); block=max(1,min(block,L))
    st=rng.integers(0,L,(n,int(np.ceil(L/block)))); ix=(st[:,:,None]+np.arange(block))%L
    mm=x[ix.reshape(n,-1)[:,:L]].mean(axis=1); return f"{x.mean()*100:+.2f} [{np.quantile(mm,.025)*100:+.2f}, {np.quantile(mm,.975)*100:+.2f}]"
for h,g in A.groupby("h"):
    print(f"  h={h:2d}: 매수일 {len(g):2d} · 수익 {g.ret.mean()*100:+.2f}% · 시장평균 대비 {bci(g.ex_ew,h)} · 지수 대비 {bci(g.ex_idx,h)} · 이긴 날 {(g.ex_ew>0).mean()*100:.0f}% · 1일당 {g.ex_ew.mean()/h*100:+.3f}%p")
print("  (매수일 = 그 h 가 9/23 까지 마감된 날 수. h 마다 표본이 달라 직접 비교엔 주의)")

print("\n=== (B) 3년 패널 in-sample — le_a 규칙 재현(dlow252↑ + obv63↓ + amt20↑ 순위합), 시장별 상위10, 비용 0.35%")
os.environ["FS_PANEL"]=os.path.join(S,"panel.npz")
sys.path.insert(0,os.path.join(REPO,"research","fullscan_20260903")); import fslib as fs
P=fs.Panel(os.path.join(S,"panel.npz")); T,N=P.T,P.N; ok=fs.guards(P); cf=P.close.astype(float); ret=P.ret
v=P.vol.astype(float); sgn=np.sign(np.where(np.isfinite(ret),ret,0))
obv63=fs.roll_mean(sgn*v,63,40)/fs.roll_mean(v,63,40)
dlow=cf/fs.roll_min(cf,252,120)-1; amt20=fs.roll_mean(cf*v,20,10)
idx=np.where(P.mk=="KOSPI",0,1); kp=P.kospi.astype(float); kq=P.kosdaq.astype(float)
def rank_m(x,m):
    return pd.DataFrame(np.where(m,x,np.nan)).rank(axis=1,pct=True).values
score=np.full((T,N),np.nan)
for mkt in [0,1]:
    m=ok&(idx==mkt)[None,:]
    r1=rank_m(dlow,m); r2=rank_m(-obv63,m); r3=rank_m(amt20,m)
    sc=r1+np.where(np.isfinite(r2),r2,0.5)+np.where(np.isfinite(r3),r3,0.5)
    score=np.where(m&np.isfinite(r1),sc,score)
mark=pd.DataFrame(cf).ffill().values
anch5=list(range(P.idx("20240201"),T-6,5))
H=[3,5,10,15,20,30,40,60,90,120]
rows=[]
for a in anch5:
    e=a+1
    for h in H:
        end=e+h
        if end>=T: continue
        rr=[]; ee=[]; ii=[]
        for mkt,ix_ in [(0,kp),(1,kq)]:
            m=ok[a]&(idx==mkt); s=np.where(m,score[a],np.nan)
            if np.isfinite(s).sum()<40: continue
            pick=np.argsort(-np.where(np.isfinite(s),s,-np.inf))[:10]
            ent=np.isfinite(cf[e,pick])&(cf[e,pick]>0)
            r=np.where(ent,mark[end,pick]/cf[e,pick]-1,0.).mean()-0.0035
            uni=np.where(m)[0]; ue=np.isfinite(cf[e,uni])&(cf[e,uni]>0); u=np.where(ue,mark[end,uni]/cf[e,uni]-1,0.).mean()-0.0035
            rr.append(r); ee.append(r-u); ii.append(r-(ix_[end]/ix_[e]-1))
        if rr: rows.append(dict(date=P.dates[a],h=h,ret=np.mean(rr),ex_ew=np.mean(ee),ex_idx=np.mean(ii)))
B=pd.DataFrame(rows); B.to_csv(os.path.join(S,"out_bw","le_hold_insample.csv"),index=False)
for h,g in B.groupby("h"):
    print(f"  h={h:3d}: 앵커 {len(g):3d} · 수익 {g.ret.mean()*100:+.2f}% · 시장평균 대비 {bci(g.ex_ew,max(1,h//5))} · 지수 대비 {bci(g.ex_idx,max(1,h//5))} · 1일당 {g.ex_ew.mean()/h*100:+.3f}%p")
for y in ["2024","2025","2026"]:
    g=B[B.date.str.startswith(y)]
    print("  연도",y," | ".join(f"h{h}:{gg.ex_ew.mean()*100:+.1f}" for h,gg in g.groupby("h")))
# 경로 곡선: 일자별 평균 초과(시장평균 대비) — 어디서 정점인가
curve=[]
for k in range(1,121):
    vals=[]
    for a in anch5[::2]:
        e=a+1; end=e+k
        if end>=T: continue
        tot=[]
        for mkt in [0,1]:
            m=ok[a]&(idx==mkt); s=np.where(m,score[a],np.nan)
            if np.isfinite(s).sum()<40: continue
            pick=np.argsort(-np.where(np.isfinite(s),s,-np.inf))[:10]
            ent=np.isfinite(cf[e,pick])&(cf[e,pick]>0); r=np.where(ent,mark[end,pick]/cf[e,pick]-1,0.).mean()
            uni=np.where(m)[0]; ue=np.isfinite(cf[e,uni])&(cf[e,uni]>0); u=np.where(ue,mark[end,uni]/cf[e,uni]-1,0.).mean()
            tot.append(r-u)
        if tot: vals.append(np.mean(tot))
    curve.append((k,np.mean(vals),len(vals)))
cv=pd.DataFrame(curve,columns=["day","ex_ew","n"]); cv.to_csv(os.path.join(S,"out_bw","le_hold_curve.csv"),index=False)
pk=cv.iloc[cv.ex_ew.idxmax()]
print(f"  경로 곡선(시장평균 대비, 비용 전): 정점 {int(pk.day)}일째 {pk.ex_ew*100:+.2f}%p · 20일 {cv.ex_ew[cv.day==20].item()*100:+.2f} · 40일 {cv.ex_ew[cv.day==40].item()*100:+.2f} · 60일 {cv.ex_ew[cv.day==60].item()*100:+.2f} · 120일 {cv.ex_ew[cv.day==120].item()*100:+.2f}")
print("  곡선 10일 간격:", " ".join(f"{int(r.day)}d:{r.ex_ew*100:+.1f}" for _,r in cv[cv.day%10==0].iterrows()))
