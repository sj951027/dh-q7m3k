# step16 (2026-09-05): 레짐 규칙 강건성 — "하루 빠졌다고 기회 놓침(휩소)" vs "구렁텅이(대폭락) 방어" 를 같은 표로.
#   신호 변형: SMA20 / 확인 2·3일 / 밴드 ±1·2% / SMA60 / 20일수익<-5% 폭락감지 / 변동성 급등 / 조합. 바스켓: 조용함 top20 · 과매도프록시 top20 · 전종목EW.
#   지표: CAGR·변동성·샤프·MDD·연간 스위치·짧은(≤2일) 에피소드 수·기회비용(50%일에 바스켓이 오른 날 놓친 수익)·회피손실 + 대폭락 에피소드별 손실.
import numpy as np, pandas as pd, os
from fslib import *
P=Panel(); ok=guards(P); R=regimes(P); F=factors(P); start=P.idx("20240101"); c=P.close.astype(np.float64)
quiet=rank_sum(F,["lv60","to20"],HYP,ok)
def topN(score,N=20): return pd.DataFrame(score).rank(axis=1,ascending=False).values<=N
masks={"조용함top20":topN(np.where(ok,quiet,np.nan)),"과매도프록시top20(RSI최저)":topN(np.where(ok&(F["rsi14"]<40),-F["rsi14"],np.nan))}
def daily_series(M,k=20,tranches=4):
    T=P.T; s=np.zeros(T); n=np.zeros(T)
    for tr in range(tranches):
        t=start+tr*(k//tranches)
        while t+ENTRY_LAG+1<T:
            hold=M[t]; a=t+ENTRY_LAG
            for d in range(a+1,min(a+k+1,T)):
                with np.errstate(all="ignore"): r=c[d]/c[d-1]-1
                v=r[hold]; v=v[np.isfinite(v)&(np.abs(v)<1)]
                if len(v): s[d]+=v.mean(); n[d]+=1
            t+=k
    out=np.where(n>0,s/np.maximum(n,1),np.nan); out[:start+2]=np.nan; return out
ew=np.nanmean(np.where(ok,P.ret,np.nan),axis=1); ew=np.r_[np.nan,ew[1:]]; ew[:start+2]=np.nan
series={"조용함top20":daily_series(masks["조용함top20"]),"과매도프록시top20":daily_series(masks["과매도프록시top20(RSI최저)"]),"전종목EW":ew}
kq=pd.Series(P.kosdaq).ffill(); s20=kq.rolling(20).mean(); s60=kq.rolling(60).mean()
gap20=(kq/s20-1).values; gap60=(kq/s60-1).values
kqr=kq.pct_change(); ret20=(kq/kq.shift(20)-1).values; vol20=(kqr.rolling(20).std()*np.sqrt(252)).values
def confirm(below,n):  # n일 연속 아래일 때만 off, 위로 1일이면 on
    b=pd.Series(below).astype(float); return (b.rolling(n).sum()==n).values
def band(gap,lo,hi):  # 히스테리시스: gap<lo 면 off, gap>hi 면 on, 사이는 유지
    st=np.ones(len(gap)); cur=1.0
    for i,g in enumerate(gap):
        if not np.isfinite(g): st[i]=cur; continue
        if g< lo: cur=0.0
        elif g> hi: cur=1.0
        st[i]=cur
    return st.astype(bool)
below20=gap20<0
SIG={"없음":np.ones(P.T,bool),"SMA20(기본)":~below20,
     "SMA20 확인2일":~confirm(below20,2),"SMA20 확인3일":~confirm(below20,3),"SMA20 확인5일":~confirm(below20,5),
     "SMA20 밴드±1%":band(gap20,-0.01,0.01),"SMA20 밴드±2%":band(gap20,-0.02,0.02),
     "SMA20 -1%아래만 off/위로 즉시 on":band(gap20,-0.01,0.0),
     "SMA60":gap60>=0,"SMA20 and SMA60 둘다 아래일 때만 off":~(below20&(gap60<0)),
     "20일수익<-5% 폭락감지":~(ret20<-0.05),"변동성>30% 급등":~(vol20>0.30),
     "SMA20 확인2일 or 20일수익<-5%":~(confirm(below20,2)|(ret20<-0.05))}
def stats(r):
    r=pd.Series(r).dropna(); eq=(1+r).cumprod(); mdd=(eq/eq.cummax()-1).min(); yrs=len(r)/252
    return dict(cagr=eq.iloc[-1]**(1/yrs)-1,vol=r.std()*np.sqrt(252),sharpe=(eq.iloc[-1]**(1/yrs)-1)/(r.std()*np.sqrt(252)),mdd=mdd)
# 대폭락 에피소드: 전종목EW 누적곡선의 '신고점 사이 구간' 중 가장 깊은 4개(겹침 없음)
eqew=pd.Series(ew).fillna(0).add(1).cumprod().values; hi=np.maximum.accumulate(eqew); dd=eqew/hi-1
segs=[]; st_=start
for i in range(start,P.T):
    if eqew[i]>=hi[i]-1e-12:   # 신고점 → 구간 마감
        if i>st_+1:
            tr=st_+int(np.argmin(dd[st_:i])); segs.append((st_,tr,dd[tr]))
        st_=i
tr=st_+int(np.argmin(dd[st_:P.T])); segs.append((st_,tr,dd[tr]))
eps=[(a,b) for a,b,d in sorted(segs,key=lambda x:x[2])[:4]]
eps=sorted(eps)
print("대폭락 에피소드(전종목EW 고점→저점):",[(P.dates[a],P.dates[b],round(float(dd[b]),3)) for a,b in eps])
rows=[]
for bn,r in series.items():
    for sn,on in SIG.items():
        w=np.where(pd.Series(on).shift(1).fillna(True).values,1.0,0.5)   # 전일 종가 신호 → 오늘 적용, off=50%
        rr=r*w; st=stats(rr); st.update(basket=bn,signal=sn)
        onv=pd.Series(on.astype(float)).shift(1).fillna(1).values[start:]; sw=int(np.sum(np.abs(np.diff(onv))>0)); yrs=(P.T-start)/252
        # off 에피소드 길이
        off=(onv==0).astype(int); ep_len=[]; k=0
        for x in off:
            if x: k+=1
            elif k: ep_len.append(k); k=0
        if k: ep_len.append(k)
        rs=np.nan_to_num(r[start:]); offm=(onv==0)
        st.update(switch_per_yr=round(sw/yrs,1),off_days_pct=round(float(offm.mean()),3),n_off_ep=len(ep_len),short_ep_le2=int(sum(1 for e in ep_len if e<=2)),
                  forgone_up_pct=round(float(np.sum(np.where(offm&(rs>0),rs*0.5,0)))*100,1),avoided_loss_pct=round(float(-np.sum(np.where(offm&(rs<0),rs*0.5,0)))*100,1))
        for j,(a,b) in enumerate(eps):
            seg=rr[a:b+1]; seg=seg[np.isfinite(seg)]; st[f"ep{j+1}_{P.dates[a][2:6]}"]=round(float(np.prod(1+seg)-1)*100,1)
        rows.append(st)
S=pd.DataFrame(rows); S.to_csv(os.path.join(OUT,"regime_robust.csv"),index=False)
pd.set_option("display.width",250)
cols=["basket","signal","cagr","vol","sharpe","mdd","switch_per_yr","off_days_pct","n_off_ep","short_ep_le2","forgone_up_pct","avoided_loss_pct"]+[k for k in S.columns if k.startswith("ep")]
print(S[cols].round(3).to_string(index=False))
