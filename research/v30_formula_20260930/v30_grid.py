# v30 변형 공식 체계적 격자 — 관측 전용. 모든 변형 결과를 공개하고 무작위 가중 분포와 비교.
import os, sys, numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE,'..','downside_20260930')); import flags as fl
import tempfile as _tf
_WORK=os.path.join(_tf.gettempdir(),'dh_v30_formula_20260930'); os.makedirs(_WORK,exist_ok=True)   # 큰 중간파일(pkl·npy)은 저장소 밖
exec(open(os.path.join(HERE,'v30_formula.py'),encoding='utf-8').read().split("A=sorted(POOL.anchor.unique())")[0])
RAWX={'PBR':False,'amt_avg_1m_억':False,'distance_to_52w_low_%':False,'return_3m_%':False,'return_1m_%':True,'foreign_20d_억':False,'inst_20d_억':True,
      'realized_vol':False,'RSI':True,'DIV':True,'vs_SMA200_%':False,'oversold_score':False}
for c in RAWX: POOL[c]=pd.to_numeric(POOL[c],errors='coerce')
parts=[]
for (a,m),g in POOL.groupby(['anchor','mkt']):
    g=g.copy(); g['r_v30']=g.final_score_v3.rank(pct=True)
    for c,hg in RAWX.items(): g['q_'+c]=g[c].rank(pct=True,ascending=hg).fillna(0.5)
    parts.append(g)
POOL=pd.concat(parts)
V={}
V['v30']=lambda g: g.final_score_v3
for c in COMP:
    for w in (0,0.5,2,3):
        V[f'1.{c.split("_")[0]}×{w}']=(lambda c,w: lambda g: raw_sum(g,{**W30,c:w}))(c,w)
for c in COMP:
    if c!='value_score': V[f'2.value×2+{c.split("_")[0]}×0']=(lambda c: lambda g: raw_sum(g,{**W30,'value_score':2,c:0}))(c)
for c in RAWX:
    for lam in (0.25,0.5):
        V[f'3.v30+{lam}·{c}']=(lambda c,lam: lambda g: g.r_v30+lam*g['q_'+c])(c,lam)
BAD={'amt_avg_1m_억':True,'realized_vol':True,'PBR':True,'distance_to_52w_low_%':True,'foreign_20d_억':True,'return_3m_%':True}
for c in BAD:
    V[f'4.v30,{c}상위20%제외']=(lambda c: lambda g: g.final_score_v3.where(g[c].rank(pct=True)<=0.8,-1e9))(c)
V['4.v30,value≥12우선']=lambda g: g.final_score_v3+1e6*(g.value_score>=12)
V['5.BUY우선']=lambda g: g.final_score_v3+1e6*(g.bucket=='BUY')
V['5.A·A+우선']=lambda g: g.final_score_v3+1e6*g.grade.isin(['A','A+'])
V['5.WAIT·BUY우선']=lambda g: g.final_score_v3+1e6*g.bucket.isin(['BUY','WAIT'])
for c in RAWX: V[f'6.단독 {c}']=(lambda c: lambda g: g['q_'+c])(c)
rng=np.random.default_rng(930); RW=rng.dirichlet(np.ones(6),200)
for i,w in enumerate(RW): V[f'_rand{i}']=(lambda w: lambda g: raw_sum(g,dict(zip(COMP,w*6))))(w)
C_=fl.C; TI=fl.TI; last=len(fl.DATES)-1
rows=[]
for a in sorted(POOL.anchor.unique()):
    t=TI[a]
    rnow=(C_.iloc[last]/C_.iloc[t+1]-1)*100 if t+1<=last else None
    for m,g in POOL[POOL.anchor==a].groupby('mkt'):
        g=g.copy()
        if rnow is not None: g['now']=g.ticker.map(rnow); g['now']=g['now']-g['now'].median()
        else: g['now']=np.nan
        for nm,f in V.items():
            t10=g.assign(_s=f(g)).nlargest(10,'_s')
            rows.append((a,m,nm,t10.ex20.mean(),t10.ex40.mean(),t10.ex5.mean(),t10.now.mean()))
X=pd.DataFrame(rows,columns=['anchor','mkt','v','ex20','ex40','ex5','now']).groupby(['anchor','v']).mean(numeric_only=True).reset_index()
X.to_pickle(os.path.join(_WORK,('grid_raw.pkl')))
base=X[X.v=='v30'].set_index('anchor')
X=X.join(base[['ex20','ex40','ex5','now']],on='anchor',rsuffix='_b')
for k in ('ex20','ex40','ex5','now'): X['d'+k]=X[k]-X[k+'_b']
def per(msk,col): return X[msk].groupby('v')[col].mean()
S=pd.DataFrame({
 'h20전체':per(X.ex20.notna(),'dex20'),
 'h20_6월':per(X.anchor.str[4:6].eq('06')&X.ex20.notna(),'dex20'),
 'h20_7월':per(X.anchor.str[4:6].eq('07')&X.ex20.notna(),'dex20'),
 'h20_8월':per(X.anchor.str[4:6].eq('08')&X.ex20.notna(),'dex20'),
 'h40전체':per(X.ex40.notna(),'dex40'),
 '지금_8초':per((X.anchor>='20260803')&(X.anchor<'20260818'),'dnow'),
 '지금_8말':per((X.anchor>='20260818')&(X.anchor<'20260901'),'dnow'),
 '지금_9월':per(X.anchor>='20260901','dnow'),
 '9월이긴날':X[X.anchor>='20260901'].groupby('v').dnow.apply(lambda s:(s>0).mean()),
})
per_cols=['h20_6월','h20_7월','h20_8월','지금_8말','지금_9월']
S['양수기간수']=(S[per_cols]>0).sum(axis=1); S['최악기간']=S[per_cols].min(axis=1)
S.to_csv(os.path.join(HERE,'grid_summary.csv'))
R_=S[S.index.str.startswith('_rand')]; M=S[~S.index.str.startswith('_rand')&(S.index!='v30')]
print(f"변형 {len(M)}개 · 무작위 가중 {len(R_)}개 (v30 대비 %p)")
print("무작위 분포: h20전체 중앙 {:+.2f} / 상위5% {:+.2f} / 최대 {:+.2f} · 지금_9월 중앙 {:+.2f} / 최대 {:+.2f} · 5개 기간 모두 양수인 무작위 {}개".format(
  R_['h20전체'].median(),R_['h20전체'].quantile(.95),R_['h20전체'].max(),R_['지금_9월'].median(),R_['지금_9월'].max(),int((R_['양수기간수']==5).sum())))
pd.set_option('display.width',260); pd.set_option('display.max_rows',200)
print("\n=== 최악 기간 기준 정렬(일관성 우선) 상위 25")
print(M.sort_values('최악기간',ascending=False).head(25).round(2).to_string())
print("\n=== 9월(지금까지) 기준 상위 12")
print(M.sort_values('지금_9월',ascending=False).head(12)[['h20전체','h20_6월','h20_7월','h20_8월','지금_8말','지금_9월','9월이긴날','양수기간수']].round(2).to_string())
print("\n=== h20전체 기준 상위 12(과거 성적만 보면)")
print(M.sort_values('h20전체',ascending=False).head(12)[['h20전체','h20_6월','h20_7월','h20_8월','h40전체','지금_8말','지금_9월','양수기간수']].round(2).to_string())
print("\n양수기간수 분포(변형):", M['양수기간수'].value_counts().sort_index().to_dict(), "· 무작위:", R_['양수기간수'].value_counts().sort_index().to_dict())
