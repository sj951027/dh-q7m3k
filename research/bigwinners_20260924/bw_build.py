# bigwin.py — "시장을 크게 이긴 종목"(h60/h120/h250)의 선행조건 스캔. 읽기 전용. 산출: scratchpad/out_bw/*.csv
import os, sys, time, sqlite3, numpy as np, pandas as pd
S=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(S,"out_bw"); os.makedirs(OUT,exist_ok=True)
REPO=r"C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k"; sys.path.insert(0,os.path.join(REPO,"research","fullscan_20260903"))
os.environ["FS_PANEL"]=os.path.join(S,"panel.npz")
import fslib as fs
t0=time.time()
P=fs.Panel(os.path.join(S,"panel.npz")); T,N=P.T,P.N
ok=fs.guards(P)
c=P.close.astype(np.float64); ret=P.ret
yr=np.array([d[:4] for d in P.dates])
idx=np.where(P.mk=="KOSPI",0,1)  # 종목별 시장
kp=P.kospi.astype(np.float64); kq=P.kosdaq.astype(np.float64)

def fwd_idx(x,h):
    o=np.full(T,np.nan); a=1;b=1+h
    if b<T: o[:T-b]=x[b:]/x[a:T-b+a]-1
    return o
def fwd_mdd(h):
    """진입(t+1) 후 h일 경로의 최대낙폭(음수). O(h) 벡터 루프."""
    run=np.full((T,N),np.nan); mdd=np.zeros((T,N));
    base=np.full((T,N),np.nan); base[:T-1]=c[1:]
    run=base.copy()
    for k in range(2,h+2):
        cur=np.full((T,N),np.nan); cur[:T-k]=c[k:]
        run=np.fmax(run,cur)
        with np.errstate(all="ignore"): dd=cur/run-1
        mdd=np.fmin(mdd,np.where(np.isfinite(dd),dd,0))
    mdd[:T-h-1][~np.isfinite(base[:T-h-1])]=np.nan; mdd[T-h-1:]=np.nan
    return mdd

H={60:0.5,120:1.0,250:1.0}
FW={}; EX={}; EV={}
for h,thr in H.items():
    f=fs.fwd(P,h); ik=fwd_idx(kp,h); iq=fwd_idx(kq,h)
    im=np.where(idx[None,:]==0,ik[:,None],iq[:,None])
    ex=f-im
    FW[h]=f; EX[h]=ex
    EV[h]=(f>=thr)&(ex>=thr)   # 절대 +thr AND 지수대비 +thr
    EV[h][~np.isfinite(f)]=False
MDD120=fwd_mdd(120)
EV["120s"]=EV[120]&(MDD120>=-0.25)   # 완만한 위너: 경로 낙폭 25% 이내
print("panel ready",time.time()-t0)

# ---------- 팩터 (t까지 정보) ----------
F=fs.factors(P)
o=P.open.astype(np.float64); hi=P.high.astype(np.float64); lo=P.low.astype(np.float64); v=P.vol.astype(np.float64)
def lag(x,k):
    o=np.full_like(x,np.nan); o[k:]=x[:-k]; return o
with np.errstate(all="ignore"):
    F["mom126"]=c/lag(c,126)-1; F["mom252"]=c/lag(c,252)-1
    F["sma60gap"]=c/fs.roll_mean(c,60,40)-1; F["sma120gap"]=c/fs.roll_mean(c,120,80)-1
    F["range120"]=fs.roll_max(c,120,80)/fs.roll_min(c,120,80)-1     # 120일 박스 폭(작을수록 타이트)
    F["range60"]=fs.roll_max(c,60,40)/fs.roll_min(c,60,40)-1
    F["bbw60"]=fs.roll_std(c,60,40)/fs.roll_mean(c,60,40)
    F["vol_dry"]=fs.roll_mean(v,20,10)/fs.roll_mean(v,120,80)         # 거래량 마름(작을수록)
    F["vol_surge5"]=fs.roll_mean(v,5,3)/fs.roll_mean(v,60,40)
    F["hl_range20"]=fs.roll_mean((hi-lo)/c,20,10)
    F["clv20"]=fs.roll_mean(np.where(hi>lo,(2*c-hi-lo)/(hi-lo),0),20,10)
    F["upvol20"]=fs.roll_mean(np.where(ret>0,v,0),20,10)/fs.roll_mean(v,20,10)
    F["amihud20"]=np.log(fs.roll_mean(np.abs(ret)/np.where(P.amt>0,P.amt,np.nan),20,10))
    F["logprice"]=np.log(c)
    # 지수 대비 상대강도
    im63=np.where(idx[None,:]==0,(kp/lag(kp,63)-1)[:,None],(kq/lag(kq,63)-1)[:,None])
    F["rs63"]=F["mom63"]-im63
    im21=np.where(idx[None,:]==0,(kp/lag(kp,21)-1)[:,None],(kq/lag(kq,21)-1)[:,None])
    F["rs21"]=F["mom21"]-im21
    # 52주 고점 이후 경과일
    rm=fs.roll_max(c,252,120); ishigh=(c>=rm*0.999)
    dsh=np.full((T,N),np.nan); cnt=np.full(N,np.nan)
    for t in range(T):
        cnt=np.where(ishigh[t],0,cnt+1); dsh[t]=cnt
    F["days_since_high"]=dsh
    # 회귀 베타 60 (지수)
    mi=np.where(idx[None,:]==0,np.r_[np.nan,kp[1:]/kp[:-1]-1][:,None],np.r_[np.nan,kq[1:]/kq[:-1]-1][:,None])
    cov=fs.roll_mean(ret*mi,60,40)-fs.roll_mean(ret,60,40)*fs.roll_mean(mi,60,40)
    var=fs.roll_std(mi,60,40)**2
    F["beta60"]=cov/var
    F["ipo_age"]=np.cumsum(np.isfinite(c),axis=0).astype(float)   # 데이터 시작 후 일수(상장 나이 근사)
# DART / universe 이벤트 플래그
con=fs.ro(fs.OHLCV)
de=pd.read_sql("select rcept_dt,ticker,event_type from dart_events",con)
ue=pd.read_sql("select date,ticker,event from universe_events",con); con.close()
ti={k:i for i,k in enumerate(P.tick)}
def flag_within(df,dcol,types,win):
    m=np.zeros((T,N),bool)
    d=df[df.iloc[:,2].isin(types)] if types else df
    for dt,tk in zip(d[dcol],d.ticker):
        if tk not in ti: continue
        j=ti[tk]; i=P.idx(dt)
        m[i:min(T,i+win),j]=True
    return m
FLAG={"buyback60":flag_within(de,"rcept_dt",["buyback"],60),
      "dilution120":flag_within(de,"rcept_dt",["cb","bw","eb","paid_in","paid_bonus_mix"],120),
      "reduction120":flag_within(de,"rcept_dt",["reduction"],120),
      "resumed60":flag_within(ue,"date",["RESUMED"],60),
      "bonus120":flag_within(de,"rcept_dt",["bonus"],120)}
print("factors ready",time.time()-t0, len(F))


R={n:fs.rank01(np.where(ok,F[n],np.nan)) for n in F}
names=pd.read_csv(os.path.join(S,'names.csv'),dtype=str).set_index('ticker')['name'].to_dict()
