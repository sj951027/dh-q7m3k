# step17 (2026-09-05): 레짐 규칙 추가 점검 — ① 확인일수×SMA창 격자(국소최적 여부) ② 연도별 안정성 ③ '신규 진입만 50%'(트랜치 단위, 매매비용 0) vs '전체 노출 50%'
#   ④ 스위치 비용 반영 ⑤ off 상태 다음날 바스켓 수익 조건부 평균(신호가 실제로 나쁜 날을 가리키나)
import numpy as np, pandas as pd, os
from fslib import *
P=Panel(); ok=guards(P); R=regimes(P); F=factors(P); start=P.idx("20240101"); c=P.close.astype(np.float64)
quiet=rank_sum(F,["lv60","to20"],HYP,ok); M=pd.DataFrame(np.where(ok,quiet,np.nan)).rank(axis=1,ascending=False).values<=20
kq=pd.Series(P.kosdaq).ffill()
def sig(win,n):   # True=on. n일 연속 아래면 off, 위로 1일이면 on. 전일 종가 기준(shift 1)
    below=(kq/kq.rolling(win).mean()-1<0)
    off=(below.astype(float).rolling(n).sum()==n) if n>1 else below
    return (~off).shift(1).fillna(True).values.astype(bool)
def series(M,on=None,mode="whole",k=20,tr=4,low=0.5):
    """mode=whole: 매일 노출×w · mode=entry: 트랜치 진입일 신호로 그 트랜치 전체 기간 비중 고정(매매비용 0)"""
    T=P.T; s=np.zeros(T); n=np.zeros(T)
    for j in range(tr):
        t=start+j*(k//tr)
        while t+ENTRY_LAG+1<T:
            hold=M[t]; a=t+ENTRY_LAG
            wt=1.0 if (on is None or mode!="entry" or on[a]) else low   # entry: 진입일(a) 아침에 아는 전일 신호
            for d in range(a+1,min(a+k+1,T)):
                with np.errstate(all="ignore"): r=c[d]/c[d-1]-1
                v=r[hold]; v=v[np.isfinite(v)&(np.abs(v)<1)]
                if len(v):
                    w=wt if mode=="entry" else (1.0 if (on is None or on[d]) else low)
                    s[d]+=v.mean()*w; n[d]+=1
            t+=k
    out=np.where(n>0,s/np.maximum(n,1),np.nan); out[:start+2]=np.nan; return out
def stats(r,cost_per_switch=0.0,on=None):
    r=pd.Series(r).copy()
    if on is not None and cost_per_switch>0:
        sw=np.r_[False,np.diff(on.astype(int))!=0]; r=r-np.where(sw,cost_per_switch,0)
    r=r.dropna(); eq=(1+r).cumprod(); mdd=(eq/eq.cummax()-1).min(); yrs=len(r)/252; cagr=eq.iloc[-1]**(1/yrs)-1; vol=r.std()*np.sqrt(252)
    return dict(cagr=round(cagr,4),vol=round(vol,4),sharpe=round(cagr/vol,3) if vol else np.nan,mdd=round(mdd,4))
base=series(M)
# ① 격자
g=[]
for win in [10,15,20,25,30,40]:
    for n in [1,2,3,4,5]:
        on=sig(win,n); st=stats(base*np.where(on,1.0,0.5)); st.update(win=win,confirm=n); g.append(st)
G=pd.DataFrame(g); G.to_csv(os.path.join(OUT,"regime_grid.csv"),index=False)
print("① 격자 — 샤프 (행=SMA창, 열=확인일수)"); print(G.pivot(index="win",columns="confirm",values="sharpe").to_string())
print("   CAGR"); print(G.pivot(index="win",columns="confirm",values="cagr").round(3).to_string()); print("   MDD"); print(G.pivot(index="win",columns="confirm",values="mdd").round(3).to_string())
# ② 연도별 + ③ 신규진입만 + ④ 비용
on20=sig(20,1); on3=sig(20,3)
variants={"없음":(base,None),"전체노출 SMA20":(base*np.where(on20,1,0.5),on20),"전체노출 확인3일":(base*np.where(on3,1,0.5),on3),
          "신규진입만 SMA20":(series(M,on20,"entry"),None),"신규진입만 확인3일":(series(M,on3,"entry"),None)}
rows=[]
for nm,(r,on) in variants.items():
    st=stats(r); st.update(variant=nm,cut="전체"); rows.append(st)
    if on is not None:
        st=stats(r,0.0025,on); st.update(variant=nm+" (스위치당 0.25%)",cut="전체"); rows.append(st)
    for y in ["2024","2025","2026"]:
        m=np.array([d.startswith(y) for d in P.dates]); rr=np.where(m,r,np.nan); st=stats(rr); st.update(variant=nm,cut=y); rows.append(st)
V=pd.DataFrame(rows); V.to_csv(os.path.join(OUT,"regime_variants_year.csv"),index=False)
print("\n②③④ 변형 × 연도"); print(V.pivot_table(index="variant",columns="cut",values=["cagr","mdd"],sort=False).round(3).to_string())
# ⑤ 조건부 일평균: 신호 off 인 날 vs on 인 날의 바스켓·EW 수익
ew=np.nanmean(np.where(ok,P.ret,np.nan),axis=1)
for nm,on in [("SMA20",on20),("확인3일",on3)]:
    for lab,arr in [("조용함top20",base),("전종목EW",ew)]:
        a=arr[start:]; o=on[start:]; offv=a[(~o)&np.isfinite(a)]; onv=a[o&np.isfinite(a)]
        m1,l1,h1,n1=boot_ci(offv,500,block=5); m2,l2,h2,n2=boot_ci(onv,500,block=5)
        print(f"⑤ {nm:6s} {lab:9s} off일 평균 {m1*1e4:+.1f}bp CI[{l1*1e4:+.0f},{h1*1e4:+.0f}] n={n1} | on일 {m2*1e4:+.1f}bp CI[{l2*1e4:+.0f},{h2*1e4:+.0f}] n={n2} | 양(+)비율 off {np.mean(offv>0):.0%} on {np.mean(onv>0):.0%}")
