import os, numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__))
import tempfile as _tf
_WORK=os.path.join(_tf.gettempdir(),'dh_v30_formula_20260930'); os.makedirs(_WORK,exist_ok=True)   # 큰 중간파일(pkl·npy)은 저장소 밖
D=pd.read_pickle(os.path.join(_WORK,'v30_panel.pkl'))
A=sorted(D.anchor.unique()); half=A[len(A)//2]
def bboot(x,block=5,reps=3000,seed=7):
    x=np.asarray(x,float); x=x[np.isfinite(x)]; L=len(x)
    if L<6: return (np.nan,np.nan)
    b=max(1,min(block,L//3)); r=np.random.default_rng(seed); st=r.integers(0,L,(reps,int(np.ceil(L/b)))); ix=(st[:,:,None]+np.arange(b))%L
    m=x[ix.reshape(reps,-1)[:,:L]].mean(1); return tuple(np.quantile(m,[.025,.975]))
out=[]
# 1) 등급·버킷
print("=== 1) 버킷·등급별 (후보 중앙값 대비 %p, 앵커 평균 · 블록 CI · 종목 승률)")
for key in ('bucket','grade'):
    for H in (20,40,5):
        rows=[]
        for gv,g in D.dropna(subset=[f'ex{H}']).groupby(key):
            am=g.groupby('anchor')[f'ex{H}'].mean(); lo,hi=bboot(am.values)
            rows.append(f"{gv}:{am.mean():+.2f}[{lo:+.2f},{hi:+.2f}] 중앙{g[f'ex{H}'].median():+.2f} 승{(g[f'ex{H}']>0).mean():.0%} n{len(g)}")
        print(f" {key} h{H}: "+" | ".join(rows))
# 2) 변수별 앵커 IC
VARS=['final_score_v3','entry_score','value_score','quality_score','turnaround_score','reversal_score','supply_score_v2','supply_intensity','oversold_component','oversold_score',
 'RSI','Stoch_K','BB_pct','drawdown_52w_high_%','distance_to_52w_low_%','return_1w_%','return_1m_%','return_3m_%','vs_SMA20_%','vs_SMA200_%','volume_vs_avg','amt_avg_1m_억',
 'realized_vol','roe_value','PBR','PER','DIV','fundamental_score','ocf_score','momentum_score','catalyst_score','smartmoney_score','composite_score','stock_score_stage1',
 'trend_score','acc_score','os_count_20d','os_streak','drop_acuteness','foreign_20d_억','inst_20d_억','quarterly_yoy_%','annual_yoy_%','risk_level_num']
D['risk_level_num']=D.risk_level.map({'안전':0,'주의':1,'경고':2,'위험':3})
for v in VARS: D[v]=pd.to_numeric(D[v],errors='coerce')
def anchor_ic(sub,v,H):
    r=[]
    for (a,m),g in sub.groupby(['anchor','mkt']):
        x=g[v]; y=g[f'ex{H}']; ok=x.notna()&y.notna()
        if ok.sum()<20 or x[ok].nunique()<3: continue
        r.append((a,x[ok].rank().corr(y[ok].rank())))
    s=pd.DataFrame(r,columns=['a','ic']).groupby('a').ic.mean(); return s
def qspread(sub,v,H):
    r=[]
    for (a,m),g in sub.groupby(['anchor','mkt']):
        g=g.dropna(subset=[v,f'ex{H}'])
        if len(g)<25 or g[v].nunique()<5: continue
        q=g[v].rank(pct=True); r.append((a,g[q>0.8][f'ex{H}'].mean()-g[q<=0.2][f'ex{H}'].mean()))
    return pd.DataFrame(r,columns=['a','s']).groupby('a').s.mean()
for pool,sub in (('safe(WATCH·EXCLUDE 제외)',D[~D.bucket.isin(['WATCH','EXCLUDE'])]),('top20',D[D['rank']<=20])):
    rows=[]
    for v in VARS:
        s20=anchor_ic(sub,v,20)
        if len(s20)<10: continue
        lo,hi=bboot(s20.values); s40=anchor_ic(sub,v,40); s5=anchor_ic(sub,v,5)
        q=qspread(sub,v,20) if pool.startswith('safe') else pd.Series(dtype=float)
        rows.append(dict(pool=pool,var=v,n=len(s20),ic20=s20.mean(),lo=lo,hi=hi,pos=(s20>0).mean(),h1=s20[s20.index<half].mean(),h2=s20[s20.index>=half].mean(),
                         ic40=s40.mean(),ic5=s5.mean(),q5_q1=q.mean() if len(q) else np.nan,cover=sub[v].notna().mean()))
    R=pd.DataFrame(rows).sort_values('ic20',key=lambda s:-s.abs())
    out.append(R)
    print(f"\n=== 2) {pool}: 변수별 앵커 IC (h20 기준 절대값 정렬) — 양수=클수록 수익↑")
    pd.set_option('display.width',250)
    print(R.round(3).to_string(index=False))
pd.concat(out).to_csv(os.path.join(HERE,'v30_var_ic.csv'),index=False)
# 3) 다변량 — 6개 구성점수 순위 회귀(앵커별 Fama-MacBeth)
comps=['value_score','quality_score','turnaround_score','reversal_score','supply_score_v2','oversold_component']
extra=['realized_vol','return_1m_%','roe_value']
for label,X in (('구성6',comps),('구성6+변동성·1개월수익·ROE',comps+extra)):
    for H in (20,40):
        co=[]
        for (a,m),g in D[~D.bucket.isin(['WATCH','EXCLUDE'])].groupby(['anchor','mkt']):
            g=g.dropna(subset=[f'ex{H}'])
            if len(g)<40: continue
            Z=np.column_stack([ (g[c].rank(pct=True).fillna(0.5)-0.5).values for c in X]+[np.ones(len(g))])
            b,*_=np.linalg.lstsq(Z,g[f'ex{H}'].values,rcond=None); co.append((a,*b[:-1]))
        C=pd.DataFrame(co,columns=['a']+X).groupby('a').mean()
        print(f"\n=== 3) 다변량 {label} h{H} (앵커 {len(C)}): 순위 0→1 이동 시 초과수익 %p [95%]")
        print("   "+" | ".join(f"{c}: {C[c].mean():+.2f}[{bboot(C[c].values)[0]:+.2f},{bboot(C[c].values)[1]:+.2f}]" for c in X))
