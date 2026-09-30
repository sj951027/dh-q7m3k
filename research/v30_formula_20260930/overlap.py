# F1~F4 상위10 겹침 수별 이후 흐름 — 관측(같은 기간에서 고른 공식이라 낙관적)
import os, sys, numpy as np, pandas as pd
import tempfile as _tf
_WORK=os.path.join(_tf.gettempdir(),'dh_v30_formula_20260930'); os.makedirs(_WORK,exist_ok=True)
HERE=os.path.dirname(os.path.abspath(__file__))
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE,'..','downside_20260930')); import flags as fl
exec(open(os.path.join(HERE,'v30_formula.py'),encoding='utf-8').read().split("A=sorted(POOL.anchor.unique())")[0])
FS={'F1':['amt_avg_1m_억','return_3m_%','return_1m_%'],'F2':['PBR','drawdown_52w_high_%','return_3m_%'],'F3':['amt_avg_1m_억','return_3m_%','vs_SMA200_%'],'F4':['value_score','PBR','return_3m_%']}
for c in set(sum(FS.values(),[])): POOL[c]=pd.to_numeric(POOL[c],errors='coerce')
C=fl.C; TI=fl.TI; G=fl.GUARD; MK=fl.MK; N=len(fl.DATES); last=N-1
mark=C.ffill()
# 시장 동일가중(유동) 누적 경로용
rows=[]
for (a,m),g in POOL.groupby(['anchor','mkt']):
    g=g.copy(); t=TI[a]
    if t+1>last: continue
    cnt=pd.Series(0,index=g.index)
    for k,p in FS.items():
        s=sum(-(g[c].rank(pct=True).fillna(.5)) for c in p); cnt+= (s.rank(ascending=False,method='first')<=10).astype(int)
    g['n']=cnt; g['v30top']=g.final_score_v3.rank(ascending=False,method='first')<=10
    idx=MK.index[MK==m]; e=C.iloc[t+1]
    path={}
    for k in (1,2,3,5,10,15,20,30,40):
        if t+1+k>last: break
        r=mark.iloc[t+1+k]/e-1; bench=r[idx][G.iloc[t][idx]].mean()
        path[k]=(r-bench)*100
    rnow=(mark.iloc[last]/e-1); bnow=rnow[idx][G.iloc[t][idx]].mean()
    for _,x in g[(g.n>0)|g.v30top].iterrows():
        rec=dict(anchor=a,mkt=m,ticker=x.ticker,n=int(x.n),v30top=bool(x.v30top),now=(rnow.get(x.ticker,np.nan)-bnow)*100,held=last-(t+1))
        for k,v in path.items(): rec[f'd{k}']=v.get(x.ticker,np.nan)
        rows.append(rec)
Z=pd.DataFrame(rows); Z.to_pickle(os.path.join(_WORK,'overlap.pkl'))
def grp(df,lab):
    out={}
    for k in (5,20,40): 
        c=f'd{k}'; s=df[c].dropna(); out[f'{k}일']=f"{s.mean():+.2f} (중앙 {s.median():+.1f}, 승 {(s>0).mean():.0%}, n{len(s)})" if len(s) else '-'
    return pd.Series(out,name=lab)
T=[grp(Z[Z.v30top],'v30 상위10')]+[grp(Z[Z.n==k],f'공식 {k}개 겹침') for k in (1,2,3,4)]+[grp(Z[Z.n>=2],'2개 이상')]
print("[시장 동일가중 대비 초과수익 %p · 매수=다음날 종가] (같은 기간 공식 → 낙관적)")
print(pd.DataFrame(T).to_string())
print("\n[누적 흐름: 매수 후 k거래일 평균 초과 %p]")
P=pd.DataFrame({lab:[sub[f'd{k}'].mean() for k in (1,2,3,5,10,15,20,30,40)] for lab,sub in [('v30상위10',Z[Z.v30top]),('1개',Z[Z.n==1]),('2개',Z[Z.n==2]),('3개',Z[Z.n==3]),('4개',Z[Z.n==4])]},index=[f'{k}일' for k in (1,2,3,5,10,15,20,30,40)])
print(P.round(2).to_string())
print("\n[월별 20일 초과 %p (n)]")
Z['mon']=Z.anchor.str[4:6]
for lab,sub in [('v30상위10',Z[Z.v30top]),('1개',Z[Z.n==1]),('2개',Z[Z.n==2]),('3개',Z[Z.n==3]),('4개',Z[Z.n==4])]:
    print(f" {lab}: "+" · ".join(f"{m}월 {s.mean():+.1f}({s.notna().sum()})" for m,s in sub.groupby('mon').d20))
print("\n[9/29까지 중간 성과 — 9월 매수분]")
for lab,sub in [('v30상위10',Z[Z.v30top]),('1개',Z[Z.n==1]),('2개',Z[Z.n==2]),('3개',Z[Z.n==3]),('4개',Z[Z.n==4])]:
    s=sub[sub.anchor>='20260901'].now; print(f" {lab}: {s.mean():+.2f} (중앙 {s.median():+.1f}, 승 {(s>0).mean():.0%}, n{len(s)})")
print("\n[겹침 종목이 v30 상위10과도 겹치는 비율]", Z[Z.n>=2].v30top.mean().round(3), " · 앵커당 평균 개수(시장별):", Z.groupby(['anchor','mkt']).apply(lambda d:pd.Series({f'{k}개':(d.n==k).sum() for k in (1,2,3,4)})).mean().round(1).to_dict())
