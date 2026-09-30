# v30 전수 탐색 — 관측 전용. 약 7.5만 공식 × 앵커. (1) 같은기간 최고 (2) 수익 섞기 귀무 최고치 (3) 매번 과거로만 1등 골라 적용(walk-forward)
import os, sys, itertools, time, numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE,'..','downside_20260930')); import flags as fl
import tempfile as _tf
_WORK=os.path.join(_tf.gettempdir(),'dh_v30_formula_20260930'); os.makedirs(_WORK,exist_ok=True)   # 큰 중간파일(pkl·npy)은 저장소 밖
exec(open(os.path.join(HERE,'v30_formula.py'),encoding='utf-8').read().split("A=sorted(POOL.anchor.unique())")[0])
FE=['value_score','quality_score','turnaround_score','reversal_score','supply_score_v2','oversold_component',
    'PBR','PER','roe_value','DIV','amt_avg_1m_억','distance_to_52w_low_%','drawdown_52w_high_%','return_3m_%','return_1m_%','vs_SMA200_%','RSI','foreign_20d_억','inst_20d_억']
for c in FE: POOL[c]=pd.to_numeric(POOL[c],errors='coerce')
K=len(FE)
# ---- 공식 정의: (base_v30 여부, {feat_idx: w}, filter(feat_idx, side) or None)
forms=[]
WS=(-0.7,-0.3,0.3,0.7)
for r in (1,2,3):
    for S in itertools.combinations(range(K),r):
        for ws in itertools.product(WS,repeat=r): forms.append((1,dict(zip(S,ws)),None))
for r in (1,2,3):
    for S in itertools.combinations(range(K),r):
        for sg in itertools.product((-1,1),repeat=r): forms.append((0,dict(zip(S,sg)),None))
for i in range(K):
    for side in ('hi','lo'):
        forms.append((1,{},(i,side)))
        for j in range(K):
            if j==i: continue
            for w in (-0.5,0.5): forms.append((1,{j:w},(i,side)))
M=len(forms); print('공식 수',M,flush=True)
Wm=np.zeros((K,M),np.float32); B=np.zeros(M,np.float32); FI=np.full(M,-1); FS=np.zeros(M,np.int8)
for m,(b,w,flt) in enumerate(forms):
    B[m]=b
    for i,x in w.items(): Wm[i,m]=x
    if flt: FI[m]=flt[0]; FS[m]=1 if flt[1]=='hi' else -1
C_=fl.C; TI=fl.TI; last=len(fl.DATES)-1
anchors=sorted(POOL.anchor.unique()); AI={a:i for i,a in enumerate(anchors)}
groups=[]
for (a,mk),g in POOL.groupby(['anchor','mkt']):
    t=TI[a]; g=g.reset_index(drop=True)
    F=np.column_stack([g[c].rank(pct=True).fillna(0.5).values for c in FE]).astype(np.float32)
    v30=g.final_score_v3.rank(pct=True).fillna(0).values.astype(np.float32)
    now=np.full(len(g),np.nan)
    if t+1<=last:
        r=(C_.iloc[last]/C_.iloc[t+1]-1)*100; now=g.ticker.map(r).values.astype(float); now=now-np.nanmedian(now)
    Y=np.column_stack([g.ex20.values,g.ex40.values,g.ex5.values,now]).astype(np.float32)
    groups.append((AI[a],F,v30,Y))
def run(groups,perm_seed=None,chunk=15000):
    out=np.full((4,M,len(anchors)),np.nan,np.float32); cnt=np.zeros((M,len(anchors)),np.float32)
    rng=np.random.default_rng(perm_seed) if perm_seed is not None else None
    acc=np.zeros((4,M,len(anchors)),np.float32)
    for ai,F,v30,Y in groups:
        if rng is not None: Y=Y[rng.permutation(len(Y))]
        n=len(v30)
        for s in range(0,M,chunk):
            e=min(M,s+chunk)
            Sc=v30[:,None]*B[None,s:e]+F@Wm[:,s:e]
            fi=FI[s:e]; has=fi>=0
            if has.any():
                cols=np.where(has)[0]; f=F[:,fi[cols]]; side=FS[s:e][cols]
                bad=np.where(side[None,:]>0,f>0.8,f<=0.2)
                sub=Sc[:,cols]; sub[bad]=-1e9; Sc[:,cols]=sub
            top=np.argpartition(-Sc,min(9,n-1),axis=0)[:10]            # 10×m
            for k in range(4):
                acc[k,s:e,ai]+=np.nanmean(Y[top,k],axis=0)
        cnt[:,ai]+=1
    return acc/np.maximum(cnt,1)[None]
t0=time.time()
R=run(groups); np.save(os.path.join(_WORK,('search_real.npy')),R); print('real done',round(time.time()-t0),'s',flush=True)
# 기준 v30 성적(동일 풀·동일 방식)
base=np.zeros((4,len(anchors)),np.float32); cntb=np.zeros(len(anchors))
for ai,F,v30,Y in groups:
    top=np.argsort(-v30)[:10]; base[:,ai]+=np.nanmean(Y[top],axis=0); cntb[ai]+=1
base/=cntb; np.save(os.path.join(_WORK,('search_base.npy')),base)
import pickle; pickle.dump((forms,FE,anchors),open(os.path.join(_WORK,('search_meta.pkl')),'wb'))
# 귀무: 앵커·시장 안에서 수익을 섞어 신호 제거 후 같은 탐색 → 최고치 분포
NP=int(os.environ.get('NPERM','12')); nullmax=[]
for p in range(NP):
    Rn=run(groups,perm_seed=1000+p)
    bn=np.zeros((4,len(anchors)),np.float32)
    rng=np.random.default_rng(1000+p)
    for ai,F,v30,Y in groups:
        Yp=Y[rng.permutation(len(Y))]; bn[:,ai]+=np.nanmean(Yp[np.argsort(-v30)[:10]],axis=0)
    bn/=cntb
    d=np.nanmean(Rn[0]-bn[0][None],axis=1); nullmax.append((float(np.nanmax(d)),float(np.nanpercentile(d,99.9)),float(np.nanpercentile(d,99))))
    print('perm',p,'best',round(nullmax[-1][0],2),round(time.time()-t0),'s',flush=True)
np.save(os.path.join(_WORK,('search_null.npy')),np.array(nullmax))
print('ALL DONE',round(time.time()-t0),'s')
