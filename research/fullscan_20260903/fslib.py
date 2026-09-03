# fslib — 전수 스캔 공용 함수 (읽기 전용, numpy/pandas만). 규약: ENTRY_LAG=1, 초과수익=유니버스 중앙값 차감,
# 가드 §22-2(거래정지·점프·저변동하한) + 거래대금20d≥5억, 스피어만 IC = 순위 피어슨.
import numpy as np, pandas as pd, os, sqlite3
_HERE=os.path.dirname(os.path.abspath(__file__)); REPO=os.path.abspath(os.path.join(_HERE,"..",".."))
HIST=os.path.join(REPO,"history.db"); OHLCV=os.path.join(REPO,"..","dh-q7m3k-data","ohlcv.db")
OUT=os.path.join(_HERE,"out"); os.makedirs(OUT,exist_ok=True)
PANEL=os.environ.get("FS_PANEL",os.path.join(_HERE,"panel.npz"))
ENTRY_LAG=1; JUMP_CAP=0.32; AMT_FLOOR=5e8

def ro(path): return sqlite3.connect(f"file:{path}?mode=ro",uri=True)

class Panel:
    def __init__(self,path=PANEL):
        z=np.load(path,allow_pickle=True)
        for k in z.files: setattr(self,k,z[k])
        self.dates=self.dates.astype(str); self.tick=self.tick.astype(str)
        self.T,self.N=self.close.shape
        c=self.close.astype(np.float64)
        with np.errstate(all="ignore"):
            self.ret=np.vstack([np.full((1,self.N),np.nan),c[1:]/c[:-1]-1])
        self.ret[~np.isfinite(self.ret)]=np.nan
        self.amt=self.close*self.vol
        self.mcap=self.close*self.shares
        self.di={d:i for i,d in enumerate(self.dates)}
    def idx(self,d):
        """date str -> first index with dates>=d"""
        return int(np.searchsorted(self.dates,d))

def roll_mean(a,w,minp=None):
    minp=minp or w
    return pd.DataFrame(a).rolling(w,min_periods=minp).mean().values
def roll_std(a,w,minp=None):
    minp=minp or w
    return pd.DataFrame(a).rolling(w,min_periods=minp).std().values
def roll_max(a,w,minp=None):
    minp=minp or w
    return pd.DataFrame(a).rolling(w,min_periods=minp).max().values
def roll_min(a,w,minp=None):
    minp=minp or w
    return pd.DataFrame(a).rolling(w,min_periods=minp).min().values

def guards(P):
    """§22-2 가드: True=사용 가능. 거래정지(63일 내 무변화>50%), 점프(21일 내 |ret|>32%), rv21<0.003, amt20<5억, 정지."""
    ret=P.ret
    flat=roll_mean((np.abs(ret)<1e-9).astype(float),63,20)>0.5
    jump=roll_max((np.abs(ret)>JUMP_CAP).astype(float),21,5)>0
    rv21=roll_std(ret,21,15)
    amt20=roll_mean(P.amt,20,10)
    ok=(~flat)&(~jump)&(rv21>=0.003)&(amt20>=AMT_FLOOR)&(P.susp==0)&np.isfinite(P.close)
    return ok

def fwd(P,h):
    """forward h-day return entering at t+ENTRY_LAG close, exit t+ENTRY_LAG+h close. shape (T,N), NaN where unavailable."""
    c=P.close.astype(np.float64); out=np.full_like(c,np.nan)
    a=ENTRY_LAG; b=ENTRY_LAG+h
    if b<P.T:
        with np.errstate(all="ignore"): out[:P.T-b]=c[b:]/c[a:P.T-b+a]-1
    out[np.abs(out)>5]=np.nan
    return out

def excess(f,ok):
    """유니버스(가드 통과) 일별 중앙값 차감"""
    m=np.where(ok,f,np.nan); med=np.nanmedian(m,axis=1,keepdims=True)
    return f-med

def rank01(x):
    """행별 0~1 순위(NaN 유지)"""
    return pd.DataFrame(x).rank(axis=1,pct=True).values

def spearman_rows(x,y,mask):
    """행(날짜)별 스피어만 IC. returns array T (NaN if <30 obs)"""
    T=x.shape[0]; out=np.full(T,np.nan)
    xm=np.where(mask,x,np.nan); ym=np.where(mask,y,np.nan)
    rx=pd.DataFrame(xm).rank(axis=1).values; ry=pd.DataFrame(ym).rank(axis=1).values
    for t in range(T):
        m=np.isfinite(rx[t])&np.isfinite(ry[t])
        if m.sum()<30: continue
        a=rx[t][m]; b=ry[t][m]
        a=a-a.mean(); b=b-b.mean()
        d=np.sqrt((a*a).sum()*(b*b).sum())
        if d>0: out[t]=(a*b).sum()/d
    return out

def boot_ci(v,n=2000,seed=0,block=1):
    """평균의 부트스트랩 95% CI. block>1 이면 연속 블록 리샘플(주블록 등)."""
    v=np.asarray(v,float); v=v[np.isfinite(v)]
    if len(v)<3: return (np.nan,np.nan,np.nan,len(v))
    rng=np.random.default_rng(seed); L=len(v)
    block=min(block,max(1,L//3))
    if block<=1:
        idx=rng.integers(0,L,(n,L)); means=v[idx].mean(axis=1)
    else:
        nb=int(np.ceil(L/block)); means=np.empty(n)
        for i in range(n):
            st=rng.integers(0,L-block+1,nb); sel=np.concatenate([np.arange(s,s+block) for s in st])[:L]
            means[i]=v[sel].mean()
    return (float(v.mean()),float(np.percentile(means,2.5)),float(np.percentile(means,97.5)),L)

def regimes(P):
    """국면 라벨(코스닥 기준, PIT): 전일까지 정보. 4상태 + breadth."""
    kq=pd.Series(P.kosdaq).ffill().values; kp=pd.Series(P.kospi).ffill().values
    def sma(x,w): return pd.Series(x).rolling(w,min_periods=w).mean().values
    r20=np.r_[np.full(20,np.nan),kq[20:]/kq[:-20]-1]
    above60=kq>sma(kq,60); above20=kq>sma(kq,20)
    ok=guards(P)
    c=P.close; s20=roll_mean(c,20,15)
    br=np.nanmean(np.where(ok,(c>s20).astype(float),np.nan),axis=1)  # 20일선 위 종목 비율
    up=np.nanmean(np.where(ok,(P.ret>0).astype(float),np.nan),axis=1); up5=pd.Series(up).rolling(5).mean().values
    lab=np.where(above60,np.where(r20>0,"강세","조정"),np.where(r20>0,"반등","약세"))
    df=pd.DataFrame({"date":P.dates,"kospi":kp,"kosdaq":kq,"kq_ret20":r20,"kq_above60":above60,"kq_above20":above20,
                     "breadth20":br,"upratio5":up5,"regime":lab})
    # 국면은 '전일 종가' 기준으로 써야 PIT → shift 1
    df["regime_pit"]=df.regime.shift(1); df["breadth20_pit"]=df.breadth20.shift(1); df["kq_above20_pit"]=df.kq_above20.shift(1)
    return df

def factors(P):
    """전종목 가격팩터 (t 시점까지 정보만). dict name->(T,N) array, 값 클수록 '가설상 좋음'으로 부호 정렬은 하지 않음(원값)."""
    ret=P.ret; c=P.close.astype(np.float64); o=P.open.astype(np.float64)
    F={}
    F["lv60"]=roll_std(ret,60,40); F["lv20"]=roll_std(ret,20,15); F["rv21"]=roll_std(ret,21,15)
    with np.errstate(all="ignore"):
        turn=P.vol/P.shares
    F["to20"]=roll_mean(turn,20,10)
    F["nh252"]=c/roll_max(c,252,120)-1          # 0에 가까울수록 고점 근접
    F["dlow252"]=c/roll_min(c,252,120)-1        # 저점 대비 거리
    F["mom12_1"]=np.r_[np.full((252,P.N),np.nan),c[252:]/c[:-252]-1]-np.r_[np.full((21,P.N),np.nan),c[21:]/c[:-21]-1][:]
    F["mom21"]=np.r_[np.full((21,P.N),np.nan),c[21:]/c[:-21]-1]
    F["mom63"]=np.r_[np.full((63,P.N),np.nan),c[63:]/c[:-63]-1]
    F["ret5"]=np.r_[np.full((5,P.N),np.nan),c[5:]/c[:-5]-1]
    F["upratio63"]=roll_mean((ret>0).astype(float),63,40)
    with np.errstate(all="ignore"):
        on=o/np.vstack([np.full((1,P.N),np.nan),c[:-1]])-1
    on[~np.isfinite(on)]=np.nan
    F["on60"]=roll_mean(on,60,40)
    F["size"]=np.log(P.mcap); F["amt20"]=np.log(roll_mean(P.amt,20,10))
    F["max5_21"]=roll_max(ret,21,15)   # 복권성 근사(21일 최대 일수익)
    s20=roll_mean(c,20,15); F["bbw20"]=roll_std(c,20,15)/s20; F["sma20gap"]=c/s20-1
    # RSI14
    up=np.where(ret>0,ret,0.0); dn=np.where(ret<0,-ret,0.0)
    au=pd.DataFrame(up).ewm(alpha=1/14,min_periods=14).mean().values; ad=pd.DataFrame(dn).ewm(alpha=1/14,min_periods=14).mean().values
    with np.errstate(all="ignore"): F["rsi14"]=100-100/(1+au/ad)
    F["dd52"]=F["nh252"]
    return F

# 가설 부호: +1 = 값 클수록 수익↑ 가설, -1 = 값 작을수록 수익↑
HYP={"lv60":-1,"lv20":-1,"rv21":-1,"to20":-1,"nh252":+1,"dlow252":-1,"mom12_1":+1,"mom21":+1,"mom63":+1,"ret5":-1,
     "upratio63":+1,"on60":-1,"size":+1,"amt20":-1,"max5_21":-1,"bbw20":-1,"sma20gap":+1,"rsi14":-1,"dd52":+1}

def rank_sum(F,names,signs,ok):
    """순위합 점수(높을수록 좋음). signs: dict name->+1/-1 (가설 부호). 핵심팩터 결측은 제외(첫 이름), 보조 NaN=0.5"""
    sc=None
    for i,n in enumerate(names):
        x=F[n]*signs[n]; x=np.where(ok,x,np.nan); r=rank01(x)
        if i==0: sc=r.copy()
        else: sc=sc+np.where(np.isfinite(r),r,0.5)
    return sc
