# step22 (2026-09-05): '완전히 다른 방식' 1차 타진 — 순위 매기기(cross-section)가 아닌 접근들 (3년 OHLC·DART·환율·업종맵)
#  A 오버나이트 vs 장중 수익 분해  B 변동성 돌파(일중, 당일 청산)  C 이벤트 포트(자사주 취득 결정 → 60일)  D 달력(월말/월초, 12월/1월 소형)
#  E 환율 선행(USDKRW 5일 변화 → 다음날·5일)  F 업종 상대 반전(5일 업종 대비 처짐 → 20일)
import numpy as np, pandas as pd, os, json, sqlite3, time
HERE_=os.path.dirname(os.path.abspath(__file__))
from fslib import *
t0=time.time(); P=Panel(); ok=guards(P); R=regimes(P); F=factors(P); start=P.idx("20240101")
c=P.close.astype(np.float64); o=P.open.astype(np.float64); h=P.high.astype(np.float64); l=P.low.astype(np.float64); N=P.N
with np.errstate(all="ignore"):
    on=o/np.vstack([np.full((1,N),np.nan),c[:-1]])-1; intra=c/o-1
for a in (on,intra): a[~np.isfinite(a)]=np.nan; a[np.abs(a)>0.5]=np.nan
quiet=rank_sum(F,["lv60","to20"],HYP,ok); rq=rank01(np.where(ok,quiet,np.nan)); rs=rank01(np.where(ok,F["size"],np.nan))
def qstat(mask,arr):
    v=np.where(mask&ok,arr,np.nan)[start:]; d=np.nanmean(v,axis=1); d=d[np.isfinite(d)]
    return float(np.mean(d))*252*100, float(np.mean(d>0))
print("== A. 오버나이트(전일종가→시가) vs 장중(시가→종가) 연환산 %, 양(+)일 비율")
for lab,m in [("전체",np.ones_like(ok)),("조용함 상위20%",rq>=0.8),("조용함 하위20%",rq<=0.2),("대형 상위20%",rs>=0.8),("소형 하위20%",rs<=0.2)]:
    a1,p1=qstat(m,on); a2,p2=qstat(m,intra); print(f"  {lab:10s} 오버나이트 {a1:+6.1f}%/년({p1:.0%})  장중 {a2:+6.1f}%/년({p2:.0%})")
if os.environ.get("SKIP_BC"): pass
print("== B. 변동성 돌파(시가+k×전일진폭 돌파 시 매수, 당일 종가 청산, 비용 0.3% 왕복) — 종목별 일수익 평균, 진입 빈도")
prev_rng=np.vstack([np.full((1,N),np.nan),(h-l)[:-1]])
for k in [0.3,0.5,0.7]:
    lvl=o+k*prev_rng; hit=(h>=lvl)&ok&np.isfinite(lvl)
    with np.errstate(all="ignore"): r=np.where(hit,c/lvl-1,np.nan)-0.003
    for lab,m in [("전체",np.ones_like(ok)),("조용함 상위20%",rq>=0.8),("소형 하위20%",rs<=0.2)]:
        v=np.where(m,r,np.nan)[start:]; d=np.nanmean(v,axis=1); d=d[np.isfinite(d)]; freq=float(np.nanmean(np.where(m&ok,hit,np.nan)[start:]))
        print(f"  k={k} {lab:10s} 일평균 {np.mean(d)*100:+.3f}% (양일 {np.mean(d>0):.0%}, 진입빈도 {freq:.0%}, 연환산 {np.mean(d)*252*100:+.1f}%)")
print("== C. 이벤트 포트 — 자사주 취득 결정(신탁+직접) t+1 종가 진입·60일 보유 동일가중(가드 통과만), 비용 0.5%")
oc=sqlite3.connect(f"file:{os.path.join(HERE_,'..','..','..','dh-q7m3k-data','ohlcv.db')}?mode=ro",uri=True)
ev=pd.read_sql("SELECT ticker,rcept_dt,event_type FROM dart_events WHERE event_type IN ('buyback') AND (report_nm IS NULL OR report_nm NOT LIKE '%정정%')",oc)
ev["ticker"]=ev.ticker.astype(str).str.zfill(6); tick={t:i for i,t in enumerate(P.tick)}
T=P.T; series=np.zeros(T); cnt=np.zeros(T); nev=0
for _,e in ev.iterrows():
    j=tick.get(e.ticker); 
    if j is None or e.rcept_dt not in P.di: continue
    t=P.di[e.rcept_dt]
    if t<start or not ok[t,j]: continue
    nev+=1; a=t+1
    for d in range(a+1,min(a+61,T)):
        with np.errstate(all="ignore"): rr=c[d,j]/c[d-1,j]-1
        if np.isfinite(rr) and abs(rr)<1: series[d]+=rr; cnt[d]+=1
port=np.where(cnt>0,series/np.maximum(cnt,1),np.nan)-0.005/60; ew=np.nanmean(np.where(ok,P.ret,np.nan),axis=1)
def st(r):
    r=pd.Series(r).dropna(); eq=(1+r).cumprod(); yrs=len(r)/252; return f"CAGR {eq.iloc[-1]**(1/yrs)-1:+.1%} 변동성 {r.std()*np.sqrt(252):.1%} MDD {(eq/eq.cummax()-1).min():+.1%} n={len(r)}"
print(f"  이벤트 {nev}건 · 평균 보유 종목수 {np.nanmean(cnt[start:]):.0f} · 포트 {st(port[start:])} | 전종목EW {st(ew[start:])}")
print("== D. 달력 — 전종목EW·조용함top20·소형 하위20% 일평균(bp): 월말 3거래일 / 월초 3거래일 / 나머지 · 12월 vs 1월")
dts=pd.to_datetime(P.dates); mon=dts.month.values; ym=(dts.year*100+dts.month).values
pos_in_month=np.zeros(T,int); last_in_month=np.zeros(T,bool)
for i in range(T):
    same=np.where(ym==ym[i])[0]; pos_in_month[i]=np.searchsorted(same,i); last_in_month[i]=(i>=same[-min(3,len(same))])
first3=pos_in_month<3
def mask_series(m): v=np.where(m&ok,P.ret,np.nan); return np.nanmean(v,axis=1)
for lab,ser in [("전종목EW",ew),("조용함상위20%",mask_series(rq>=0.8)),("소형하위20%",mask_series(rs<=0.2))]:
    s=ser.copy(); s[:start]=np.nan
    g=lambda m: np.nanmean(s[m])*1e4
    print(f"  {lab:9s} 월말3일 {g(last_in_month):+.0f}bp 월초3일 {g(first3):+.0f}bp 나머지 {g(~(last_in_month|first3)):+.0f}bp | 12월 {g(mon==12):+.0f}bp 1월 {g(mon==1):+.0f}bp 그외 {g((mon!=12)&(mon!=1)):+.0f}bp")
print("== E. 환율 선행 — USDKRW 5일 변화 상위/하위 20% 날 → 다음날·5일 뒤 EW·소형·대형 수익(bp)")
fx=pd.Series(P.usdkrw).ffill().values; fx5=np.r_[np.full(5,np.nan),fx[5:]/fx[:-5]-1]; q=pd.Series(fx5[start:]).quantile([0.2,0.8]).values
ew1=np.r_[ew[1:],np.nan]; ew5=np.array([np.nanprod(1+ew[i+1:i+6])-1 if i+6<T else np.nan for i in range(T)])
big=mask_series(rs>=0.8); small=mask_series(rs<=0.2); big1=np.r_[big[1:],np.nan]; small1=np.r_[small[1:],np.nan]
for lab,m in [("환율 급등(상위20%)",fx5>=q[1]),("환율 급락(하위20%)",fx5<=q[0]),("중간",(fx5>q[0])&(fx5<q[1]))]:
    mm=m.copy(); mm[:start]=False
    print(f"  {lab:12s} n={mm.sum()} 다음날 EW {np.nanmean(ew1[mm])*1e4:+.0f}bp 소형 {np.nanmean(small1[mm])*1e4:+.0f} 대형 {np.nanmean(big1[mm])*1e4:+.0f} | 5일 EW {np.nanmean(ew5[mm])*1e4:+.0f}bp")
print("== F. 업종 상대 반전 — (종목 5일수익 − 업종 5일 평균) 낮을수록 좋다는 가설, h20 IC(국면별)")
sec=json.load(open(os.path.join(HERE_,"..","..","sector_cache.json"),encoding="utf-8")); secv=np.array([sec.get(t,sec.get(t.lstrip("0"),"")) for t in P.tick],dtype=object)
r5=F["ret5"]; rel=np.full_like(r5,np.nan)
for s_ in set(secv):
    if not s_: continue
    cols=np.where(secv==s_)[0]
    if len(cols)<8: continue
    m=np.nanmean(np.where(ok[:,cols],r5[:,cols],np.nan),axis=1,keepdims=True); rel[:,cols]=r5[:,cols]-m
f20=excess(fwd(P,20),ok); ic=spearman_rows(-rel,f20,ok); icr=spearman_rows(-r5,f20,ok)
v=ic[start:]; v=v[np.isfinite(v)]; m,lo,hi,n=boot_ci(v,500,block=20); v2=icr[start:]; v2=v2[np.isfinite(v2)]; m2,lo2,hi2,_=boot_ci(v2,500,block=20)
rg=R.regime_pit.values
print(f"  업종상대반전 IC {m:+.4f} [{lo:+.4f},{hi:+.4f}] n={n} | 단순5일반전 IC {m2:+.4f} [{lo2:+.4f},{hi2:+.4f}] | 국면별(상대): "+" ".join(f"{g} {np.nanmean(ic[(rg==g)&(np.arange(T)>=start)]):+.3f}" for g in ["강세","조정","반등","약세"]))
print("done",round(time.time()-t0,1))
