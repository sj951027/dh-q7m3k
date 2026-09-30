# 공정 시험: (S) 앞 절반에서 항목 선택 → 뒤 절반 시험, (W2) 매 앵커 과거 IC 상위 4개 방향만(동일가중) 사용
import os, sys, numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE,'..','downside_20260930')); import flags as fl
exec(open(os.path.join(HERE,'v30_formula.py'),encoding='utf-8').read().split("A=sorted(POOL.anchor.unique())")[0])   # POOL·r_ 컬럼·FORM 재사용
CAND=['value_score','quality_score','turnaround_score','reversal_score','supply_score_v2','oversold_component','PBR','amt_avg_1m_억','distance_to_52w_low_%','return_3m_%','foreign_20d_억','inst_20d_억','realized_vol','RSI','return_1m_%','vs_SMA200_%','DIV','PER','roe_value','drawdown_52w_high_%']
for c in CAND: POOL[c]=pd.to_numeric(POOL[c],errors='coerce')
parts=[]
for (a,m),g in POOL.groupby(['anchor','mkt']):
    g=g.copy()
    for c in CAND: g['p_'+c]=g[c].rank(pct=True)
    parts.append(g)
POOL=pd.concat(parts)
A=sorted(POOL.anchor.unique()); TI=fl.TI
def ic_table(sub,H=20):
    out={}
    for c in CAND:
        r=[]
        for (a,m),g in sub.groupby(['anchor','mkt']):
            x=g['p_'+c]; y=g[f'ex{H}']; ok=x.notna()&y.notna()
            if ok.sum()>=20 and x[ok].nunique()>=3: r.append(x[ok].corr(y[ok].rank()))
        out[c]=np.mean(r) if len(r)>=6 else np.nan
    return pd.Series(out)
def pick4(ic): s=ic.dropna(); top=s.abs().sort_values(ascending=False).index[:4]; return {c:np.sign(s[c]) for c in top}
def score_from(g,sel): return sum(((g['p_'+c].fillna(0.5)-0.5)*sg) for c,sg in sel.items())
def top(g,s,H): t=g.assign(_s=s).dropna(subset=[f'ex{H}']).nlargest(10,'_s'); return t[f'ex{H}'].mean()
def bboot(x,block=5,reps=3000,seed=7):
    x=np.asarray(x,float); x=x[np.isfinite(x)]; L=len(x)
    if L<6: return (np.nan,np.nan)
    b=max(1,min(block,L//3)); r=np.random.default_rng(seed); st=r.integers(0,L,(reps,int(np.ceil(L/b)))); ix=(st[:,:,None]+np.arange(b))%L
    m=x[ix.reshape(reps,-1)[:,:L]].mean(1); return tuple(np.quantile(m,[.025,.975]))
# (S) 분할: h20 결과가 있는 앵커를 시간순 절반. 학습 구간의 마지막 앵커 +21거래일 이후부터 시험(겹침 제거)
for H in (20,40):
    AH=[a for a in A if POOL[POOL.anchor==a][f'ex{H}'].notna().any()]
    cut=AH[len(AH)//2]; train=[a for a in AH if a<cut]; gap_end=fl.DATES[TI[train[-1]]+21]
    test=[a for a in AH if a>gap_end]
    ic=ic_table(POOL[POOL.anchor.isin(train)],H); sel=pick4(ic)
    d=[];rows=[]
    for a in test:
        v=[];b=[]
        for m,g in POOL[POOL.anchor==a].groupby('mkt'):
            v.append(top(g,score_from(g,sel),H)); b.append(top(g,g.final_score_v3,H))
        d.append(np.mean(v)-np.mean(b)); rows.append((np.mean(v),np.mean(b)))
    lo,hi=bboot(d)
    print(f"[S h{H}] 학습 앵커 {len(train)}({train[0]}~{train[-1]}) → 시험 {len(test)}({test[0] if test else '-'}~) · 고른 항목 {', '.join(c+('↑' if s>0 else '↓') for c,s in sel.items())}")
    print(f"        시험 구간 top10: 공식 {np.mean([r[0] for r in rows]):+.2f} vs v30 {np.mean([r[1] for r in rows]):+.2f} → 차이 {np.mean(d):+.2f} [{lo:+.2f},{hi:+.2f}] 이긴날 {(np.array(d)>0).mean():.0%}")
    print("        학습 구간 IC 상위:", ", ".join(f"{k} {v:+.3f}" for k,v in ic.dropna().sort_values(key=abs,ascending=False).head(6).items()))
# (W2) 매 앵커: 그 시점에 h20 결과가 확정된 과거 앵커로 IC → 상위 4개 방향만
res={20:[],40:[]}; picks=[]
for a in A:
    known=[x for x in A if TI[x]+21<=TI[a]]
    if len(known)<8: continue
    sel=pick4(ic_table(POOL[POOL.anchor.isin(known)],20)); picks.append((a,tuple(sel)))
    for H in (20,40):
        g0=POOL[POOL.anchor==a]
        if g0[f'ex{H}'].notna().sum()<40: continue
        v=[top(g,score_from(g,sel),H) for m,g in g0.groupby('mkt')]; b=[top(g,g.final_score_v3,H) for m,g in g0.groupby('mkt')]
        res[H].append((a,np.mean(v)-np.mean(b)))
for H in (20,40):
    d=np.array([x[1] for x in res[H]]); lo,hi=bboot(d)
    print(f"[W2 h{H}] 시험 앵커 {len(d)} · v30 대비 {d.mean():+.2f} [{lo:+.2f},{hi:+.2f}] 이긴날 {(d>0).mean():.0%}")
from collections import Counter
print("W2 가 고른 항목 빈도:", Counter(c for _,p in picks for c in p).most_common(8))
