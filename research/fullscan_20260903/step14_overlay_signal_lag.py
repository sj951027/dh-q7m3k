# step14 (2026-09-05): ① 노출 조절 신호 변형 — KOSDAQ / KOSPI / 시장별 / 둘다 / 둘중하나 × (50%·0%) · 조용함 top20(전체·코스피만·코스닥만)
#                     ② 진입 지연(스크리너 다음날 매수) 유효성 — 조용함 top20 h20 초과: lag0(불가능 참조)·t+1시가·t+1종가·t+2·t+3·t+5
# 3년 패널(2024-01~), 20일 리밸·4트랜치, 비용 전. 산출 out/overlay_signal.csv · out/entry_lag_quiet.csv
import numpy as np, pandas as pd, os, time
from fslib import *
t0=time.time(); P=Panel(); ok=guards(P); R=regimes(P); F=factors(P)
start=P.idx("20240101"); c=P.close.astype(np.float64); o=P.open.astype(np.float64)
quiet=rank_sum(F,["lv60","to20"],HYP,ok)
def topN_mask(score,N=20):
    r=pd.DataFrame(score).rank(axis=1,ascending=False).values; return r<=N
isKP=(P.mk=="KOSPI")[None,:]; isKQ=~isKP
masks={"조용함top20(전체)":topN_mask(np.where(ok,quiet,np.nan)),
       "조용함top20(코스피만)":topN_mask(np.where(ok&isKP,quiet,np.nan)),
       "조용함top20(코스닥만)":topN_mask(np.where(ok&isKQ,quiet,np.nan))}
def daily_series(M,k=20,tranches=4,lag=ENTRY_LAG,wfun=None):
    """일별 바스켓 수익. wfun(d, ticker_mask)->종목별 비중(0~1) — 시장별 신호용. 없으면 1."""
    T=P.T; series=np.zeros(T); cnt=np.zeros(T)
    for tr in range(tranches):
        t=start+tr*(k//tranches)
        while t+lag+1<T:
            hold=M[t]; a=t+lag
            for d in range(a+1,min(a+k+1,T)):
                with np.errstate(all="ignore"): r=c[d]/c[d-1]-1
                w=np.ones(P.N) if wfun is None else wfun(d)
                v=(r*w)[hold]; m=np.isfinite(v)&(np.abs(v)<1)
                if m.sum(): series[d]+=v[m].mean(); cnt[d]+=1
            t+=k
    out=np.where(cnt>0,series/np.maximum(cnt,1),np.nan); out[:start+2]=np.nan; return out
def stats(r):
    r=pd.Series(r).dropna(); eq=(1+r).cumprod(); mdd=(eq/eq.cummax()-1).min()
    yrs=len(r)/252; cagr=eq.iloc[-1]**(1/yrs)-1; vol=r.std()*np.sqrt(252)
    return dict(days=len(r),cagr=cagr,vol=vol,sharpe=cagr/vol if vol else np.nan,mdd=mdd,total=eq.iloc[-1]-1)
kq=pd.Series(P.kosdaq).ffill().values; kp=pd.Series(P.kospi).ffill().values
kq_up=kq>pd.Series(kq).rolling(20).mean().values; kp_up=kp>pd.Series(kp).rolling(20).mean().values
# 신호는 '전일 종가' 기준(스크리너 20:10 실행 → 다음날 적용) = shift(1)
kq_up1=pd.Series(kq_up).shift(1).fillna(True).values; kp_up1=pd.Series(kp_up).shift(1).fillna(True).values
kq_up2=pd.Series(kq_up).shift(2).fillna(True).values; kp_up2=pd.Series(kp_up).shift(2).fillna(True).values
def wmk(low, kqv, kpv):   # 시장별: 종목의 시장 지수 신호
    def f(d):
        w=np.ones(P.N); w[isKQ[0]&(~kqv[d])]=low; w[isKP[0]&(~kpv[d])]=low; return w
    return f
rows=[]
for nm,M in masks.items():
    base=daily_series(M)
    variants={"없음":np.ones(P.T)}
    for low,tag in [(0.5,"50%"),(0.0,"0%")]:
        variants[f"KOSDAQ<SMA20→{tag}"]=np.where(kq_up1,1.0,low)
        variants[f"KOSPI<SMA20→{tag}"]=np.where(kp_up1,1.0,low)
        variants[f"둘다<SMA20→{tag}"]=np.where(kq_up1|kp_up1,1.0,low)
        variants[f"둘중하나<SMA20→{tag}"]=np.where(kq_up1&kp_up1,1.0,low)
    for vn,w in variants.items():
        st=stats(base*w); st.update(basket=nm,overlay=vn,avg_w=float(np.nanmean(w[start:]))); rows.append(st)
    for low,tag in [(0.5,"50%"),(0.0,"0%")]:
        s=daily_series(M,wfun=wmk(low,kq_up1,kp_up1)); st=stats(s); st.update(basket=nm,overlay=f"시장별<SMA20→{tag}",avg_w=np.nan); rows.append(st)
    # 하루 더 늦게(신호 2일 전) — 신호 시효
    st=stats(base*np.where(kq_up2,1.0,0.5)); st.update(basket=nm,overlay="KOSDAQ<SMA20→50% (신호 2일전)",avg_w=float(np.nanmean(np.where(kq_up2,1.0,0.5)[start:]))); rows.append(st)
    print(nm,round(time.time()-t0,1),flush=True)
S=pd.DataFrame(rows); S.to_csv(os.path.join(OUT,"overlay_signal.csv"),index=False)
print(S[["basket","overlay","cagr","vol","sharpe","mdd","avg_w","days"]].round(3).to_string())
# ---- ② 진입 지연 유효성: 조용함 top20(전체) h20 초과수익(유니버스 중앙값 대비), 진입 시점 변형 ----
M=masks["조용함top20(전체)"]; H=20
def fwd_lag(lag,use_open=False):
    out=np.full_like(c,np.nan); a=lag; b=lag+H
    if b<P.T:
        entry=(o if use_open else c)
        with np.errstate(all="ignore"): out[:P.T-b]=c[b:]/entry[a:P.T-b+a]-1
    out[np.abs(out)>5]=np.nan; return out
lrows=[]
for lab,lag,uo in [("t 종가(불가능·참조)",0,False),("t+1 시가",1,True),("t+1 종가(현행)",1,False),("t+2 종가",2,False),("t+3 종가",3,False),("t+5 종가",5,False)]:
    f=fwd_lag(lag,uo); ex=excess(f,ok)
    top=np.array([np.nanmean(ex[t][M[t]]) if M[t].sum()>=5 else np.nan for t in range(start,P.T)])
    rg=R.regime_pit.values[start:P.T]
    for cut,sel in [("전체",np.ones(len(top),bool))]+[(g,rg==g) for g in ["강세","조정","반등","약세"]]:
        v=top[sel]; v=v[np.isfinite(v)]
        if len(v)<10: continue
        m,lo,hi,n=boot_ci(v,600,block=20)
        lrows.append(dict(entry=lab,cut=cut,n=n,exc20=m,lo=lo,hi=hi,win=float(np.mean(v>0))))
L=pd.DataFrame(lrows); L.to_csv(os.path.join(OUT,"entry_lag_quiet.csv"),index=False)
print(L.round(4).to_string()); print("done",round(time.time()-t0,1))
