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

# ---------- 기저율 ----------
rows=[]
for k,E in EV.items():
    m=ok&np.isfinite(FW[120 if k=="120s" else k])
    for y in ["2023","2024","2025","2026","all"]:
        mm=m if y=="all" else m&(yr==y)[:,None]
        if mm.sum()==0: continue
        rows.append(dict(event=k,year=y,obs=int(mm.sum()),events=int((E&mm).sum()),rate=float((E&mm).sum()/mm.sum())))
    # 에피소드(종목별 h일 갭 dedupe)
    h=120 if k=="120s" else k
    ep=0; tks=set()
    for j in range(N):
        w=np.where(E[:,j]&m[:,j])[0]
        if len(w)==0: continue
        tks.add(j); last=-10**9
        for t in w:
            if t-last>=h: ep+=1; last=t
    rows[-1].update(episodes=ep,tickers=len(tks))
pd.DataFrame(rows).to_csv(os.path.join(OUT,"base_rates.csv"),index=False)
print(pd.DataFrame(rows).to_string())

# ---------- 단일팩터 lift (앵커내 10분위) ----------
R={n:fs.rank01(np.where(ok,F[n],np.nan)) for n in F}
def lift_table(E,mask,tag):
    out=[]
    base=E[mask].mean()
    for n,r in R.items():
        for d,(lo_,hi_) in {"D1":(0,0.1),"D10":(0.9,1.01)}.items():
            sel=mask&(r>=lo_)&(r<hi_)
            if sel.sum()<500: continue
            p=E[sel].mean();
            ys={}
            for y in ["2023","2024","2025","2026"]:
                s2=sel&(yr==y)[:,None]; b2=mask&(yr==y)[:,None]
                ys[y]=float(E[s2].mean()/E[b2].mean()) if s2.sum()>=300 and E[b2].sum()>=20 else np.nan
            out.append(dict(tag=tag,factor=n,decile=d,n=int(sel.sum()),rate=float(p),lift=float(p/base),
                            **{"lift_"+y:ys[y] for y in ys}))
    for n,fl in FLAG.items():
        sel=mask&fl
        if sel.sum()<500: continue
        p=E[sel].mean(); out.append(dict(tag=tag,factor=n,decile="flag",n=int(sel.sum()),rate=float(p),lift=float(p/base)))
    return pd.DataFrame(out)
LT=[]
for k,E in EV.items():
    h=120 if k=="120s" else k
    m=ok&np.isfinite(FW[h])
    LT.append(lift_table(E,m,f"{k}_all"))
    cold=m&(F["mom63"]<0.10)
    LT.append(lift_table(E,cold,f"{k}_cold"))
LT=pd.concat(LT); LT.to_csv(os.path.join(OUT,"single_lifts.csv"),index=False)
print("lifts done",time.time()-t0)

# ---------- 십분위 EV (h120, 초과수익 분포) ----------
rows=[]
for k in [60,120,250]:
    ex=EX[k]; m=ok&np.isfinite(ex)
    for n,r in R.items():
        for d,(lo_,hi_) in {"D1":(0,0.1),"D10":(0.9,1.01)}.items():
            sel=m&(r>=lo_)&(r<hi_)
            if sel.sum()<500: continue
            x=ex[sel]
            rows.append(dict(h=k,factor=n,decile=d,n=int(sel.sum()),mean_ex=float(np.mean(x)),med_ex=float(np.median(x)),
                             p_ex_gt50=float((x>=0.5).mean()),p_ex_lt_m30=float((x<=-0.3).mean()),p_beat=float((x>0).mean())))
pd.DataFrame(rows).to_csv(os.path.join(OUT,"decile_ev.csv"),index=False)

# ---------- 결합(상위 후보 쌍·삼중, 앵커내 5분위) + 플라시보 ----------
rng=np.random.default_rng(0)
def shuffled_within_anchor(E,mask):
    Es=E.copy()
    for t in range(T):
        w=np.where(mask[t])[0]
        if len(w)<2: continue
        Es[t,w]=E[t,rng.permutation(w)]
    return Es
combo_rows=[]
for k in [120,"120s",60]:
    E=EV[k]; h=120 if k=="120s" else k; m=ok&np.isfinite(FW[h]); ex=EX[h]
    lt=LT[(LT.tag==f"{k}_all")&(LT.decile!="flag")].copy()
    # 방향 결정: D10 lift > D1 lift 면 상위, 아니면 하위
    piv=lt.pivot(index="factor",columns="decile",values="lift")
    piv["best"]=piv[["D1","D10"]].max(axis=1); piv["dir"]=np.where(piv.D10>=piv.D1,1,-1)
    top=piv.sort_values("best",ascending=False).head(10)
    masks={}
    for n,rw in top.iterrows():
        r=R[n]; masks[n]=(r>=0.8) if rw.dir==1 else (r<=0.2)
    names=list(masks); base=E[m].mean()
    Es=shuffled_within_anchor(E,m)
    import itertools
    for combo in list(itertools.combinations(names,2))+list(itertools.combinations(names,3)):
        sel=m.copy()
        for n in combo: sel&=masks[n]
        if sel.sum()<300: continue
        # 에피소드 수
        ep=0
        for j in np.where(sel.any(axis=0))[0]:
            w=np.where(sel[:,j]&E[:,j])[0]; last=-10**9
            for t in w:
                if t-last>=h: ep+=1; last=t
        ys={y:float(E[sel&(yr==y)[:,None]].mean()/E[m&(yr==y)[:,None]].mean()) if (sel&(yr==y)[:,None]).sum()>=100 else np.nan for y in ["2023","2024","2025","2026"]}
        x=ex[sel]
        combo_rows.append(dict(event=k,combo="&".join(f"{n}{'↑' if top.loc[n,'dir']==1 else '↓'}" for n in combo),n=int(sel.sum()),
            events=int(E[sel].sum()),episodes=ep,lift=float(E[sel].mean()/base),placebo=float(Es[sel].mean()/base),
            mean_ex=float(x.mean()),med_ex=float(np.median(x)),p_beat=float((x>0).mean()),p_lt_m30=float((x<=-0.3).mean()),
            **{"lift_"+y:ys[y] for y in ys}))
CB=pd.DataFrame(combo_rows); CB.to_csv(os.path.join(OUT,"combos.csv"),index=False)
print("combos done",time.time()-t0)

# ---------- 지속성: 연도별 초과수익 순위의 자기상관 / 상위 5% 재발 ----------
rows=[]
# 6개월 블록(126일) 비겹침
blocks=list(range(0,T-126,126))
ex126=None
with np.errstate(all="ignore"):
    br=[]
    for b in blocks:
        e=b+126
        if e>=T: break
        r_=c[e]/c[b]-1; im=np.where(idx==0,kp[e]/kp[b]-1,kq[e]/kq[b]-1); br.append(r_-im)
    br=np.array(br)  # (B,N)
for i in range(len(br)-1):
    a=br[i]; b=br[i+1]; mm=np.isfinite(a)&np.isfinite(b)&ok[blocks[i]]&ok[blocks[i+1]]
    ra=pd.Series(a[mm]).rank(pct=True).values; rb=pd.Series(b[mm]).rank(pct=True).values
    rho=np.corrcoef(ra,rb)[0,1]
    top=ra>=0.95; nxt_top=(rb>=0.95)
    rows.append(dict(block=f"{P.dates[blocks[i]]}-{P.dates[blocks[i+1]]}",n=int(mm.sum()),rank_corr=float(rho),
        top5_repeat=float(nxt_top[top].mean()),top5_base=0.05,top5_next_mean_ex=float(b[mm][top].mean()),
        top5_next_med_ex=float(np.median(b[mm][top])),bottom5_next_mean_ex=float(b[mm][ra<=0.05].mean())))
PS=pd.DataFrame(rows); PS.to_csv(os.path.join(OUT,"persistence.csv"),index=False); print(PS.to_string())

# ---------- 위너 경로 해부 (h120 위너: 수익이 언제 났나, 진입 전 20일 상대강도) ----------
E=EV[120]; m=ok&np.isfinite(FW[120]); w=np.where(E&m)
f20=fs.fwd(P,20); f60=FW[60]
an=dict(n=len(w[0]),frac_gain_first20=float(np.nanmedian(f20[w]/FW[120][w])),frac_gain_first60=float(np.nanmedian(f60[w]/FW[120][w])),
        med_rs21_before=float(np.nanmedian(F["rs21"][w])),med_rs63_before=float(np.nanmedian(F["rs63"][w])),
        med_nh252=float(np.nanmedian(F["nh252"][w])),med_dlow252=float(np.nanmedian(F["dlow252"][w])),
        med_size_pct=float(np.nanmedian(R["size"][w])),med_amt_pct=float(np.nanmedian(R["amt20"][w])),
        med_rv21_pct=float(np.nanmedian(R["rv21"][w])),med_range120_pct=float(np.nanmedian(R["range120"][w])),
        med_mdd_path=float(np.nanmedian(MDD120[w])),p_mdd_worse_25=float(np.nanmean(MDD120[w]<-0.25)),
        base_med_size_pct=float(np.nanmedian(R["size"][m])),base_med_amt_pct=float(np.nanmedian(R["amt20"][m])))
pd.Series(an).to_csv(os.path.join(OUT,"anatomy_h120.csv")); print(an)
# 국면(코스닥 fw120)과 위너 생산률
reg=pd.DataFrame({"date":P.dates,"rate":np.where(m.sum(1)>200,(E&m).sum(1)/np.maximum(m.sum(1),1),np.nan),"kq_fw120":fwd_idx(kq,120),"kp_fw120":fwd_idx(kp,120)})
reg.to_csv(os.path.join(OUT,"daily_rate_h120.csv"),index=False)
rr=reg.dropna(); print("corr(rate,kq_fw120)=",np.corrcoef(rr.rate,rr.kq_fw120)[0,1],"corr(rate,kp_fw120)=",np.corrcoef(rr.rate,rr.kp_fw120)[0,1])
print("done",time.time()-t0)
