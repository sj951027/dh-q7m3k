# T2 — 실제 모델 동결 점수(OOS, 등록일 이후) × 플래그: 제외 후 다음 순위 − 기준(희석 60일 제외 top10), 무작위 교체 300회
import sys, sqlite3, numpy as np, pandas as pd, flags as fl, basket as bk
import os as _os; sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "../..")))
import leaderboard as lb
F=fl.build(); FN=list(F); C=fl.C; dates=fl.DATES; didx=fl.TI
hc=sqlite3.connect(f"file:{fl.panel.HIST}?mode=ro",uri=True)
partial,dbl,_=lb.build_gates(hc,dates); excl=partial|dbl
def ld(tb,col,mid):
    s=pd.read_sql(f"select run_id,market,ticker,{col} as score from {tb} where model_id=?",hc,params=(mid,))
    s['ticker']=s.ticker.astype(str).str.zfill(6); s['market']=s.market.str.lower(); s['run_id']=s.run_id.astype(str); return s
def ld_large():
    lg=pd.read_sql("select run_id,market,ticker,per,pbr,rim_spread,div_yield from large_final",hc)
    fz=pd.DataFrame({"ep":1/lg.per.where(lg.per>0),"bp":1/lg.pbr.where(lg.pbr>0),"rim":lg.rim_spread,"dv":lg.div_yield})
    rkk=fz.groupby(lg.run_id).rank(pct=True); lg['score']=rkk.mean(axis=1,skipna=True).where(rkk.notna().sum(axis=1)>=2)
    lg['ticker']=lg.ticker.astype(str).str.zfill(6); lg['market']=lg.market.str.lower(); lg['run_id']=lg.run_id.astype(str)
    return lg[['run_id','market','ticker','score']]
MODELS={'v30':ld('v3_scores','final_score_v3','v30')}
for m in('lv_b','lv_e','lv_a','mom_a','sm_a'): MODELS[m]=ld('lowvol_scores','lowvol_score',m)
for m in('le_a','px_a','qs_a','sv_a'): MODELS[m]=ld('wu_scores','wu_score',m)
MODELS['ls_t1']=ld_large()
REG=dict(lb.REG_DATE); REG.setdefault('ls_t1','20260806')
mark=C.ffill().values; Cv=C.values; cols={t:j for j,t in enumerate(C.columns)}
Farr={k:v.values for k,v in F.items()}; DIL=fl.DIL60.values
rng=np.random.default_rng(930); recs=[]
for mid,S in MODELS.items():
    keep=lb.dedupe_by_anchor(S,didx,excl,reg=REG.get(mid))
    for rid in sorted(keep):
        t=lb.anchor(rid,didx)
        if t is None: continue
        for h in(20,40):
            e=t+1
            if e+h>=len(dates): continue
            ret=np.clip(mark[e+h]/Cv[e]-1,-0.95,3.0)
            per=[]
            for m,g in S[S.run_id==rid].dropna(subset=['score']).groupby('market'):
                g=g.sort_values('score',ascending=False)
                js=[cols[x] for x in g.ticker if x in cols]
                js=[j for j in js if np.isfinite(ret[j]) and not DIL[t,j]]
                if len(js)<15: continue
                base,out=bk.run_one(js,ret,{f:Farr[f][t] for f in FN},n_pl=300,rng=rng)
                per.append(out)
            if per:
                rec=dict(model=mid,date=dates[t],h=h)
                for f in FN:
                    rec[f]=np.mean([p[f][0] for p in per]); rec[f+'_k']=np.mean([p[f][1] for p in per]); rec[f+'_pl']=np.mean([p[f][2] for p in per],axis=0)
                recs.append(rec)
D=pd.DataFrame(recs); rows=[]
for (m,h),g in D.groupby(['model','h']):
    for f in FN:
        ci=bk.bci(g[f].values,max(1,h//4)); plm=np.stack(g[f+'_pl'].values).mean(axis=0); pct=float((plm<g[f].mean()).mean())
        rows.append(dict(model=m,h=h,n=len(g),flag=f,k=g[f+'_k'].mean(),diff=ci[0],lo=ci[1],hi=ci[2],pl_mean=plm.mean(),pl_pct=pct))
out=pd.DataFrame(rows); out.to_csv('t2_models.csv',index=False)
o=out.copy()
for c_ in('diff','lo','hi','pl_mean'): o[c_]=(o[c_]*100).round(2)
o['k']=o.k.round(2); o['pl_pct']=(o.pl_pct*100).round(0)
pd.set_option('display.width',200); pd.set_option('display.max_rows',600)
print(o[(o.k>=0.3)].to_string(index=False))
print("\n(k<0.3 조합 수:", int((o.k<0.3).sum()), ")")
print(o.groupby(['model','h']).n.first().to_string())
