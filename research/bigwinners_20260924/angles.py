# angles.py — 다양한 관점 7종 (A~G). 신호일 정보만, 수익 절단 없음, 픽비중 지수, 비용 0.5%. 산출 out_bw/angles_*.csv
import os, sys, numpy as np, pandas as pd, time
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from bw_build import *
t0=time.time()
cf=c.astype(float); mark=pd.DataFrame(cf).ffill().values
def fwd_raw(h):
    o=np.full_like(cf,np.nan); o[:T-1-h]=cf[1+h:]/cf[1:T-h]-1; return o
FR={h:fwd_raw(h) for h in [20,60,120,250]}
def fwd_idx(x,h):
    o=np.full(T,np.nan); o[:T-1-h]=x[1+h:]/x[1:T-h]-1; return o
IK={h:fwd_idx(kp,h) for h in FR}; IQ={h:fwd_idx(kq,h) for h in FR}
IDX={h:np.where(idx[None,:]==0,IK[h][:,None],IQ[h][:,None]) for h in FR}   # 종목별 같은 시장 지수
EXR={h:FR[h]-IDX[h] for h in FR}
def rs(nd):
    sc=None
    for n,d in nd:
        r=R[n] if d>0 else 1-R[n]; sc=r.copy() if sc is None else sc+np.where(np.isfinite(r),r,0.5)
    return sc
BNH=rs([("beta60",1),("days_since_high",-1)])
def bci(x,block=6,n=3000,seed=924):
    x=np.asarray(x,float); x=x[np.isfinite(x)]; L=len(x)
    if L<4: return (np.nan,np.nan,np.nan,L)
    rng=np.random.default_rng(seed); st=rng.integers(0,L,(n,int(np.ceil(L/block)))); ix=(st[:,:,None]+np.arange(block))%L
    mm=x[ix.reshape(n,-1)[:,:L]].mean(axis=1); return (x.mean(),np.quantile(mm,.025),np.quantile(mm,.975),L)
def fmt(t): return f"{t[0]*100:+.2f} [{t[1]*100:+.2f}, {t[2]*100:+.2f}] n={t[3]}"
months=sorted(set(d[:6] for d in P.dates)); MA=[]
for mo in months:
    i=P.idx(mo+"01")
    if i<T and P.dates[i][:6]==mo and P.dates[i]>="20240101": MA.append(i)
def port(score,h,anchors,N=20,extra_mask=None,cap_cluster=None,clusters=None):
    out=[]
    for a in anchors:
        e=a+1; end=a+1+h
        if end>=T: continue
        cand=ok[a].copy()
        if extra_mask is not None: cand&=extra_mask[a]
        s=np.where(cand,score[a],np.nan)
        if np.isfinite(s).sum()<40: continue
        order=np.argsort(-np.where(np.isfinite(s),s,-np.inf))
        if cap_cluster:
            pick=[]; cnt={}
            for j in order:
                if not np.isfinite(s[j]): break
                k=clusters[a].get(j,-1);
                if cnt.get(k,0)>=cap_cluster: continue
                pick.append(j); cnt[k]=cnt.get(k,0)+1
                if len(pick)==N: break
            pick=np.array(pick)
        else: pick=order[:N]
        entered=np.isfinite(cf[e,pick])&(cf[e,pick]>0)&(P.vol[e,pick]>0)
        net=float(np.mean(np.where(entered,mark[end,pick]/cf[e,pick]-1,0.)))-0.005
        pp=np.mean(idx[pick]); out.append(dict(date=P.dates[a],net=net,ex=net-((1-pp)*IK[h][a]+pp*IQ[h][a]),kospi=pp))
    return pd.DataFrame(out)
LOG=[]
def say(s): print(s); LOG.append(s)

# ---------- A. 상관 클러스터 ----------
say("=== A. 상관 클러스터 (120일 수익률 상관, 월간, k=25 간이 k-means on 상위 고유벡터)")
def kmeans(X,k,seed=0,it=30):
    rng=np.random.default_rng(seed); C_=X[rng.choice(len(X),k,replace=False)]
    for _ in range(it):
        d=((X[:,None,:]-C_[None,:,:])**2).sum(-1); lab=d.argmin(1)
        for i in range(k):
            if (lab==i).any(): C_[i]=X[lab==i].mean(0)
    return lab
CL={}; CLRET={}   # anchor -> {j:label}, cluster 60d 수익
rows=[]
for a in MA:
    if a<130: continue
    m=ok[a]&np.isfinite(cf[a]); js=np.where(m)[0]
    r=ret[a-119:a+1][:,js]; r=np.where(np.isfinite(r),r,0)
    r=(r-r.mean(0))/(r.std(0)+1e-9); Cm=(r.T@r)/len(r)
    w,v=np.linalg.eigh(Cm); X=v[:,-10:]*np.sqrt(np.maximum(w[-10:],0))
    lab=kmeans(X,25,seed=a)
    CL[a]={j:int(l) for j,l in zip(js,lab)}
    # 그룹 모멘텀: 그룹 평균 60일 수익 ; 대장: 그룹 내 시총 최대 종목의 20일 수익
    mom60=F["mom63"][a][js]; mom20=F["mom21"][a][js]; size=P.mcap[a][js]
    for k in range(25):
        mem=np.where(lab==k)[0]
        if len(mem)<8: continue
        gm=np.nanmean(mom60[mem]); leader=mem[np.nanargmax(size[mem])]; lm=mom20[leader]
        for i in mem:
            j=js[i]
            rows.append(dict(date=P.dates[a],cluster=k,ticker=j,is_leader=int(i==leader),size_pct=R["size"][a][j],
                grp_mom60=gm,leader_mom20=lm,own_mom20=mom20[i],own_mom60=mom60[i],rel_to_grp=mom60[i]-gm,
                ex60=EXR[60][a,j],ex120=EXR[120][a,j],fw60=FR[60][a,j],fw120=FR[120][a,j]))
A=pd.DataFrame(rows); A.to_csv(os.path.join(OUT,"angles_A_clusters.csv"),index=False)
def daily_ic(df,x,y):
    v=[]
    for d,g in df.groupby("date"):
        g=g[[x,y]].dropna()
        if len(g)<100: continue
        v.append(g[x].rank().corr(g[y].rank()))
    return bci(v,block=6)
for h in ["ex60","ex120"]:
    say(f"  그룹모멘텀60→{h} IC {fmt(daily_ic(A,'grp_mom60',h))} | 자기모멘텀60→{h} IC {fmt(daily_ic(A,'own_mom60',h))} | 그룹대비상대→{h} IC {fmt(daily_ic(A,'rel_to_grp',h))}")
    fol=A[(A.is_leader==0)&(A.size_pct<0.5)]
    say(f"  대장주 20일수익 → 소형 졸병 {h} IC {fmt(daily_ic(fol,'leader_mom20',h))} (자기 20일 IC {fmt(daily_ic(fol,'own_mom20',h))})")
# 그룹 상위 분위 포트: 그룹모멘텀 상위 5그룹의 종목 EW vs 하위
for h in ["ex120"]:
    v_top=[]; v_bot=[]
    for d,g in A.groupby("date"):
        gq=g.groupby("cluster").grp_mom60.first().sort_values()
        top=gq.index[-5:]; bot=gq.index[:5]
        v_top.append(g[g.cluster.isin(top)][h].mean()); v_bot.append(g[g.cluster.isin(bot)][h].mean())
    say(f"  그룹모멘텀 상위5그룹 종목 EW 지수초과120 {fmt(bci(v_top))} | 하위5그룹 {fmt(bci(v_bot))}")
# 후보 규칙 그룹 상한
for cap in [None,4,2]:
    g=port(BNH,120,[a for a in MA if a in CL],cap_cluster=cap,clusters=CL)
    say(f"  고베타×신고가 top20 h120, 그룹당 상한 {cap}: net {fmt(bci(g.net))} | 지수초과 {fmt(bci(g.ex))}")
say(f"[A done {time.time()-t0:.0f}s]")

# ---------- B. 돌파 신선도 ----------
say("=== B. 돌파 신선도: 근고점(days_since_high≤10) 종목을 '직전 120일 중 최대 무신고가 일수'(base 길이)로 3분할, h120 지수초과 EW")
dsh=F["days_since_high"]; base_len=fs.roll_max(dsh,120,60)
near=ok&(dsh<=10)&np.isfinite(EXR[120])
anch5=list(range(P.idx("20240201"),T-121,5))
rows=[]
for a in anch5:
    js=np.where(near[a])[0]
    if len(js)<60: continue
    bl=base_len[a][js]; q=pd.qcut(pd.Series(bl),3,labels=False,duplicates="drop").values
    for k in range(3):
        sel=js[q==k]
        if len(sel)<10: continue
        rows.append(dict(date=P.dates[a],tercile=k,n=len(sel),base_med=float(np.median(bl[q==k])),ex120=float(np.nanmean(EXR[120][a][sel])),ex60=float(np.nanmean(EXR[60][a][sel])),
                         win=float(np.nanmean(EXR[120][a][sel]>=1.0))))
B=pd.DataFrame(rows); B.to_csv(os.path.join(OUT,"angles_B_freshness.csv"),index=False)
for k,g in B.groupby("tercile"):
    say(f"  base길이 3분위 {k} (중앙 {g.base_med.median():.0f}일): 지수초과60 {fmt(bci(g.ex60,block=12))} | 120 {fmt(bci(g.ex120,block=24))} | W120률 {g.win.mean()*100:.2f}%")
# 고베타 조건 안에서
rows=[]
for a in anch5:
    js=np.where(near[a]&(R["beta60"][a]>=0.7))[0]
    if len(js)<40: continue
    bl=base_len[a][js]; q=pd.qcut(pd.Series(bl),3,labels=False,duplicates="drop").values
    for k in range(3):
        sel=js[q==k]
        if len(sel)<8: continue
        rows.append(dict(date=P.dates[a],tercile=k,ex120=float(np.nanmean(EXR[120][a][sel]))))
B2=pd.DataFrame(rows)
for k,g in B2.groupby("tercile"): say(f"  [고베타 상위30% 안] base 3분위 {k}: 지수초과120 {fmt(bci(g.ex120,block=24))}")

# ---------- C. 돌파 때 거래량 ----------
say("=== C. 근고점(≤10일) 종목: 거래량 상태 3분위별 h120 지수초과")
rows=[]
for nm in ["vol_surge5","vol_dry","upvol20","to20"]:
    for a in anch5:
        js=np.where(near[a]&np.isfinite(F[nm][a]))[0]
        if len(js)<60: continue
        x=F[nm][a][js]; q=pd.qcut(pd.Series(x),3,labels=False,duplicates="drop").values
        for k in range(3):
            sel=js[q==k]
            if len(sel)<10: continue
            rows.append(dict(f=nm,date=P.dates[a],tercile=k,ex120=float(np.nanmean(EXR[120][a][sel])),ex60=float(np.nanmean(EXR[60][a][sel]))))
Cc=pd.DataFrame(rows); Cc.to_csv(os.path.join(OUT,"angles_C_volume.csv"),index=False)
for nm,g0 in Cc.groupby("f"):
    say("  "+nm+": "+" | ".join(f"T{k} ex60 {bci(g.ex60,block=12)[0]*100:+.1f} ex120 {fmt(bci(g.ex120,block=24))}" for k,g in g0.groupby("tercile")))

# ---------- D. 국면 조건 ----------
say("=== D. 고베타×신고가 top20 h120, 5일 앵커, 진입일 국면(PIT)별")
reg=fs.regimes(P); reg["breadth_q"]=pd.qcut(reg.breadth20_pit,3,labels=["저","중","고"])
g=port(BNH,120,anch5); g=g.merge(reg[["date","regime_pit","breadth_q","kq_above20_pit"]],on="date")
say(f"  전체 5일앵커: 지수초과 {fmt(bci(g.ex,block=24))}")
for k,gg in g.groupby("regime_pit"): say(f"  국면 {k}: net {bci(gg.net,block=24)[0]*100:+.1f} 지수초과 {fmt(bci(gg.ex,block=24))}")
for k,gg in g.groupby("breadth_q"): say(f"  20일선 위 비율(breadth) {k}: 지수초과 {fmt(bci(gg.ex,block=24))}")
for k,gg in g.groupby("kq_above20_pit"): say(f"  코스닥>20일선 {k}: 지수초과 {fmt(bci(gg.ex,block=24))}")
g.to_csv(os.path.join(OUT,"angles_D_regime.csv"),index=False)

# ---------- E. 이벤트 × 상태 ----------
say("=== E. 이벤트×상태")
quiet=rs([("lv60",-1),("to20",-1)])
for h in [60,120]:
    g1=port(quiet,h,MA); g2=port(quiet,h,MA,extra_mask=FLAG["buyback60"]); g3=port(quiet,h,MA,extra_mask=~FLAG["dilution120"])
    say(f"  h{h} 조용함 top20: 지수초과 {fmt(bci(g1.ex))} | 자사주취득60일 내로 한정 {fmt(bci(g2.ex))} | 희석공시120일 제외 {fmt(bci(g3.ex))}")
    b1=port(BNH,h,MA); b3=port(BNH,h,MA,extra_mask=~FLAG["dilution120"]); b4=port(BNH,h,MA,extra_mask=~FLAG["resumed60"])
    say(f"  h{h} 고베타×신고가 top20: {fmt(bci(b1.ex))} | 희석 제외 {fmt(bci(b3.ex))} | 거래재개 제외 {fmt(bci(b4.ex))}")
    # 자사주 이벤트 유니버스 EW 자체
    v=[]
    for a in MA:
        if a+1+h>=T: continue
        js=np.where(ok[a]&FLAG["buyback60"][a])[0]
        if len(js)<10: continue
        v.append(np.nanmean(EXR[h][a][js]))
    say(f"  h{h} 자사주취득60일 유니버스 EW 지수초과 {fmt(bci(v))}")

# ---------- F. 보유 규칙 ----------
say("=== F. 고베타×신고가 top20 (월간): 보유 규칙별 비용후 수익·지수초과")
def port_rule(score,anchors,rule,N=20):
    out=[]
    for a in anchors:
        e=a+1
        s=np.where(ok[a],score[a],np.nan)
        if np.isfinite(s).sum()<40: continue
        pick=np.argsort(-np.where(np.isfinite(s),s,-np.inf))[:N]
        H=rule["h"]
        if e+H>=T: continue
        rets=[]; exits=[]
        for j in pick:
            if not(np.isfinite(cf[e,j]) and cf[e,j]>0 and P.vol[e,j]>0): rets.append(0.); continue
            path=mark[e:e+H+1,j]/cf[e,j]-1
            k=H
            if rule.get("trail"):
                pk=np.maximum.accumulate(1+path); dd=(1+path)/pk-1
                hit=np.where(dd<=-rule["trail"])[0]
                if len(hit): k=min(H,hit[0]+1)
            if rule.get("stop"):
                hit=np.where(path<=-rule["stop"])[0]
                if len(hit): k=min(k,min(H,hit[0]+1))
            if rule.get("take"):
                hit=np.where(path>=rule["take"])[0]
                if len(hit): k=min(k,min(H,hit[0]+1))
            rets.append(path[k]); exits.append(k)
        net=float(np.mean(rets))-0.005; pp=np.mean(idx[pick])
        ir=(1-pp)*IK[H][a]+pp*IQ[H][a]
        out.append(dict(date=P.dates[a],net=net,ex=net-ir,avg_exit=np.mean(exits) if exits else np.nan))
    return pd.DataFrame(out)
for nm,rule in [("120일 고정",dict(h=120)),("120일+추적손절20%",dict(h=120,trail=0.20)),("120일+추적손절30%",dict(h=120,trail=0.30)),
                ("120일+고정손절15%",dict(h=120,stop=0.15)),("120일+익절+50%",dict(h=120,take=0.5)),("120일+익절+100%",dict(h=120,take=1.0)),
                ("250일 고정",dict(h=250)),("250일+추적손절25%",dict(h=250,trail=0.25)),("60일 고정",dict(h=60))]:
    g=port_rule(BNH,MA,rule); say(f"  {nm:18s}: net {fmt(bci(g.net))} | 지수초과(같은 기간 지수) {fmt(bci(g.ex))} | 평균 보유일 {g.avg_exit.mean():.0f}")

# ---------- G. 신규 상장 나이 ----------
say("=== G. 신규 상장(universe_events NEW) 이후 경과 개월별 h60·h120 지수초과 (t = 상장 후 k개월 시점, 그 시점부터 보유)")
con=fs.ro(fs.OHLCV); ue=pd.read_sql("select date,ticker from universe_events where event='NEW'",con); con.close()
ti={k:i for i,k in enumerate(P.tick)}
rows=[]
for d,tk in zip(ue.date,ue.ticker):
    if tk not in ti: continue
    j=ti[tk]; i0=P.idx(d)
    for k in [1,2,3,6,9,12]:
        a=i0+21*k
        if a>=T or not ok[a,j]: continue
        rows.append(dict(ticker=tk,listed=d,k=k,date=P.dates[a],ex60=EXR[60][a,j],ex120=EXR[120][a,j],mom_since=cf[a,j]/cf[i0,j]-1))
G=pd.DataFrame(rows); G.to_csv(os.path.join(OUT,"angles_G_ipo.csv"),index=False)
for k,g in G.groupby("k"):
    gg=g.dropna(subset=["ex120"]); say(f"  상장 후 {k:2d}개월: n={len(gg)} 지수초과60 {bci(g.ex60.dropna(),block=1)[0]*100:+.1f} | 120 {fmt(bci(gg.ex120,block=1))} | 중앙값120 {gg.ex120.median()*100:+.1f} | 상장가대비 누적 중앙 {gg.mom_since.median()*100:+.0f}%")
# 상장 후 3개월 시점에 이미 오른 vs 내린
g3=G[(G.k==3)].dropna(subset=["ex120"])
for lab,sel in [("상장후3개월 +30%↑",g3.mom_since>=0.3),("−30%↓",g3.mom_since<=-0.3),("중간",(g3.mom_since>-0.3)&(g3.mom_since<0.3))]:
    say(f"  {lab}: n={sel.sum()} 지수초과120 {fmt(bci(g3[sel].ex120,block=1))}")
open(os.path.join(OUT,"angles_log.txt"),"w",encoding="utf-8").write("\n".join(LOG))
print("done",time.time()-t0)
