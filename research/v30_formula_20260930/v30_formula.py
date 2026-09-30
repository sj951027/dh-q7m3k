# v30 재가중 공식 백테스트 — 관측 전용. (1) 같은 기간 고정 공식(낙관적) (2) 앞으로만 학습(walk-forward) (3) 무작위 가중 300개 플라시보
import os, sys, numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__))
import tempfile as _tf
_WORK=os.path.join(_tf.gettempdir(),'dh_v30_formula_20260930'); os.makedirs(_WORK,exist_ok=True)   # 큰 중간파일(pkl·npy)은 저장소 밖
sys.path.insert(0, os.path.join(HERE,'..','downside_20260930')); import flags as fl
D=pd.read_pickle(os.path.join(_WORK,('v30_panel.pkl')))
num=['final_score_v3','value_score','quality_score','turnaround_score','reversal_score','supply_score_v2','oversold_component','PBR','amt_avg_1m_억','distance_to_52w_low_%','return_3m_%','foreign_20d_억','inst_20d_억','realized_vol']
for c in num: D[c]=pd.to_numeric(D[c],errors='coerce')
# 희석 60일 제외(운용 규약) · 풀 = WATCH·EXCLUDE 제외
cols={t:j for j,t in enumerate(fl.C.columns)}; DIL=fl.DIL60
D['dil']=[bool(DIL.at[a,t]) if (a in DIL.index and t in DIL.columns) else False for a,t in zip(D.anchor,D.ticker)]
POOL=D[(~D.bucket.isin(['WATCH','EXCLUDE']))&(~D.dil)].copy()
# 앵커·시장별 백분위(클수록 좋게 방향 맞춤)
def pr(g,c,high_good=True): return g[c].rank(pct=True,ascending=high_good).fillna(0.5)
COMP=['value_score','quality_score','turnaround_score','reversal_score','supply_score_v2','oversold_component']
RAW={'PBR':False,'amt_avg_1m_억':False,'distance_to_52w_low_%':False,'return_3m_%':False,'foreign_20d_억':False,'inst_20d_억':True}
parts=[]
for (a,m),g in POOL.groupby(['anchor','mkt']):
    g=g.copy()
    for c in COMP: g['r_'+c]=pr(g,c)
    for c,hg in RAW.items(): g['r_'+c]=pr(g,c,hg)
    parts.append(g)
POOL=pd.concat(parts)
W30={'value_score':1,'quality_score':1,'turnaround_score':1,'reversal_score':1,'supply_score_v2':1,'oversold_component':1}  # v30 은 원점수 합(가중 1)
def raw_sum(g,w): return sum(g[c].fillna(0)*wt for c,wt in w.items())
FORM={
 'v30(기준)':lambda g: g.final_score_v3,
 'A 가치×2':lambda g: raw_sum(g,{**W30,'value_score':2}),
 'B 품질 제외':lambda g: raw_sum(g,{**W30,'quality_score':0}),
 'C 가치×2·품질0·수급0':lambda g: raw_sum(g,{**W30,'value_score':2,'quality_score':0,'supply_score_v2':0}),
 'D 원자료4(PBR↓·거래대금↓·저점근접·3개월↓)':lambda g: g['r_PBR']+g['r_amt_avg_1m_억']+g['r_distance_to_52w_low_%']+g['r_return_3m_%'],
 'E v30순위+원자료4':lambda g: g.final_score_v3.rank(pct=True)+0.25*(g['r_PBR']+g['r_amt_avg_1m_억']+g['r_distance_to_52w_low_%']+g['r_return_3m_%']),
}
A=sorted(POOL.anchor.unique()); aidx={a:i for i,a in enumerate(A)}
TI=fl.TI
def top_basket(g,score,H,k=10):
    s=score(g) if callable(score) else score
    t=g.assign(_s=s).dropna(subset=[f'ex{H}']).nlargest(k,'_s'); return t[f'ex{H}'].mean(), set(t.ticker)
# (2) walk-forward: 과거(결과 확정된 앵커만) FM 회귀 계수로 점수
WFX=['r_'+c for c in COMP]+['r_'+c for c in RAW]
def fm_coef(train,H=20):
    co=[]
    for (a,m),g in train.groupby(['anchor','mkt']):
        g=g.dropna(subset=[f'ex{H}'])
        if len(g)<40: continue
        Z=np.column_stack([g[c].values-0.5 for c in WFX]+[np.ones(len(g))]); b,*_=np.linalg.lstsq(Z,g[f'ex{H}'].values,rcond=None); co.append(b[:-1])
    return np.mean(co,axis=0) if len(co)>=10 else None
rows=[]; rng=np.random.default_rng(930); RW=rng.dirichlet(np.ones(6),300)
for a in A:
    t=TI[a]
    known=[x for x in A if TI[x]+21<=t]   # h20 결과가 a 시점에 이미 확정된 앵커
    coef=fm_coef(POOL[POOL.anchor.isin(known)]) if known else None
    for H in (20,40):
        rec={'anchor':a,'H':H}; ok=True
        for m,g in POOL[POOL.anchor==a].groupby('mkt'):
            if g[f'ex{H}'].notna().sum()<20: ok=False; break
            for nm,f in FORM.items():
                rec.setdefault(nm,[]).append(top_basket(g,f,H)[0])
            if coef is not None:
                rec.setdefault('W 앞으로만 학습',[]).append(top_basket(g,(g[WFX].values-0.5)@coef,H)[0])
            # 무작위 가중(구성6 원점수) 플라시보
            pl=[top_basket(g,raw_sum(g,dict(zip(COMP,w*6))),H)[0] for w in RW]
            rec.setdefault('_pl',[]).append(pl)
        if not ok: continue
        out={'anchor':a,'H':H}
        for k,v in rec.items():
            if k in('anchor','H'): continue
            out[k]=np.mean(v,axis=0) if k=='_pl' else np.mean(v)
        rows.append(out)
R=pd.DataFrame(rows); R.to_pickle(os.path.join(_WORK,('formula_results.pkl')))
def bboot(x,block=5,reps=3000,seed=7):
    x=np.asarray(x,float); x=x[np.isfinite(x)]; L=len(x)
    if L<6: return (np.nan,np.nan)
    b=max(1,min(block,L//3)); r=np.random.default_rng(seed); st=r.integers(0,L,(reps,int(np.ceil(L/b)))); ix=(st[:,:,None]+np.arange(b))%L
    m=x[ix.reshape(reps,-1)[:,:L]].mean(1); return tuple(np.quantile(m,[.025,.975]))
for H in (20,40):
    g=R[R.H==H]; half=g.anchor.iloc[len(g)//2]
    base=g['v30(기준)']; plm=np.stack(g['_pl'].values)   # 앵커×300
    print(f"\n=== h{H}: 앵커 {len(g)} (후보 중앙값 대비 top10 초과 %p · v30 대비 짝 차이 · 전반/후반 · 무작위 가중 300개 중 백분위)")
    print(f"   무작위 가중 top10 평균: {plm.mean():+.2f} (v30 대비 {plm.mean()-base.mean():+.2f}, 무작위 간 표준편차 {(plm.mean(0)).std():.2f})")
    for nm in list(FORM)+['W 앞으로만 학습']:
        if nm not in g: continue
        s=g[nm]; ok=s.notna(); d=(s-base)[ok]; lo,hi=bboot(d.values)
        pct=(plm[ok.values].mean(0)<s[ok].mean()).mean()
        h1=d[g.anchor[ok]<half].mean(); h2=d[g.anchor[ok]>=half].mean()
        print(f"   {nm:<34} top10 {s[ok].mean():+.2f} | v30 대비 {d.mean():+.2f} [{lo:+.2f},{hi:+.2f}] 이긴날 {(d>0).mean():.0%} | 전반 {h1:+.2f} 후반 {h2:+.2f} | 무작위 대비 {pct:.0%} (n{ok.sum()})")
