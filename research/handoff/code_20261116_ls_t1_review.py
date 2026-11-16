"""Independent h20-only ls_t1 review. Reads SQLite mode=ro; prints only.
Run: python -X utf8 -B research/handoff/code_20261116_ls_t1_review.py
No production imports, no h60/h120 return or IC calculation.
"""
import sqlite3, datetime as dt, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
H, REG, BOOT, SEED = 20, "20260806", 2000, 7
assert H == 20
def ro(p):
    return sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
def stats(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if not len(x): return {"n": 0}
    bs = np.random.default_rng(SEED).choice(x, (BOOT, len(x))).mean(axis=1)
    return dict(n=len(x),mean=float(x.mean()),ci=np.percentile(bs,[2.5,97.5]).tolist(),
                positive=float((x>0).mean()),sd=float(x.std(ddof=1)))
def rho(s,r):
    m=s.notna()&r.notna(); s=s[m];r=r[m]
    if len(s)<8 or s.nunique()<3 or r.nunique()<3:return np.nan
    return float(np.corrcoef(s.rank(),r.rank())[0,1])
def correlation(x,y):
    xy=np.array([x,y],float).T
    xy=xy[np.isfinite(xy).all(axis=1)]
    n=len(xy); rng=np.random.default_rng(SEED)
    z=xy[rng.integers(n,size=(BOOT,n))]
    z=z-z.mean(axis=1,keepdims=True)
    den=np.sqrt((z[:,:,0]**2).sum(axis=1)*(z[:,:,1]**2).sum(axis=1))
    b=(z[:,:,0]*z[:,:,1]).sum(axis=1)/den
    b=b[np.isfinite(b)]
    return dict(n=n,r=float(np.corrcoef(xy.T)[0,1]),ci=np.percentile(b,[2.5,97.5]).tolist())

with ro(ROOT/"history.db") as con:
    lg=pd.read_sql_query("select run_id,market,ticker,per,pbr,rim_spread,div_yield from large_final",con)
    cnt=pd.read_sql_query("select run_id,count(*) n from stage1_oversold group by run_id",con)
    partial=set(cnt.loc[cnt.n<cnt.n.median()*.30,"run_id"].astype(str))
    double=set()
    for table in ("v3_scores","lowvol_scores","wu_scores"):
        fa=pd.read_sql_query("select run_id,model_id,min(frozen_at) lo,max(frozen_at) hi from "+table+" group by run_id,model_id",con)
        gap=(pd.to_datetime(fa.hi,utc=True)-pd.to_datetime(fa.lo,utc=True)).dt.total_seconds()
        double.update(fa.loc[gap>=3600,"run_id"].astype(str))
with ro(ROOT.parent/"dh-q7m3k-data"/"ohlcv.db") as con:
    px=pd.read_sql_query("select date,ticker,close from daily_ohlcv",con)
    ex=pd.read_sql_query("select date,ticker,close from daily_ohlcv_extra",con)
p=px.pivot_table(index="date",columns="ticker",values="close",aggfunc="last").sort_index()
ex=ex[~ex.ticker.isin(p.columns)]
e=ex.pivot_table(index="date",columns="ticker",values="close",aggfunc="last")
p=p.join(e.reindex(p.index))
days=list(p.index); didx={d:i for i,d in enumerate(days)}
jump=p.pct_change(fill_method=None).abs()
def anchor(rid):
    if rid in didx:return didx[rid]
    d=dt.datetime.strptime(rid,"%Y%m%d")
    return next((didx[x] for k in range(1,6) if (x:=(d-dt.timedelta(days=k)).strftime("%Y%m%d")) in didx),None)
lg["ticker"]=lg.ticker.astype(str); lg["run_id"]=lg.run_id.astype(str)
fz=pd.DataFrame({"ep":1/lg.per.where(lg.per>0),"bp":1/lg.pbr.where(lg.pbr>0),"rim":lg.rim_spread,"dv":lg.div_yield})
rk=fz.groupby(lg.run_id).rank(pct=True)
lg["score"]=rk.mean(axis=1).where(rk.notna().sum(axis=1)>=2)
lg=lg.dropna(subset=["score"])
candidate={}
for rid in sorted(lg.run_id.unique()):
    if rid<REG or rid in partial|double:continue
    t=anchor(rid)
    if t is not None:candidate.setdefault(t,[]).append(rid)
keep={min([r for r in rs if r in didx] or rs) for rs in candidate.values()}
weekly={}
for rid in sorted(keep):
    wk=dt.datetime.strptime(days[anchor(rid)],"%Y%m%d").isocalendar()[:2]
    weekly.setdefault(wk,rid)
weekset=set(weekly.values())
rows=[]; comp=[]; memo_comp=[]
for rid,g in lg[lg.run_id.isin(keep)].groupby("run_id",sort=True):
    q=g.sort_values(["score","ticker"],ascending=[False,True])
    item={"run":rid,"kp_score":g.loc[g.market=="kospi","score"].mean(),
          "kq_score":g.loc[g.market=="kosdaq","score"].mean(),
          "kp_n":int((g.market=="kospi").sum()),"kq_n":int((g.market=="kosdaq").sum())}
    for n in (10,20,50):item["top%d_kp"%n]=float((q.head(n).market=="kospi").mean())
    comp.append(item)
    t=anchor(rid)
    if t+1+H>=len(days):continue
    ret=(p.iloc[t+1+H]/p.iloc[t+1]-1).where(jump.iloc[t+2:t+2+H].max()<=.32)
    v=g[["ticker","market","score"]].copy();v["ret"]=ret.reindex(v.ticker).to_numpy()
    v=v.dropna(subset=["ret","score"])
    subsets={m:v[v.market==m] for m in ("kospi","kosdaq")}
    memo_comp.append(dict(run=rid,
        kp_score=subsets["kospi"].score.mean(),kq_score=subsets["kosdaq"].score.mean(),
        kp_n=len(subsets["kospi"]),kq_n=len(subsets["kosdaq"]),
        top20_kp=float((v.sort_values("score",ascending=False).head(20).market=="kospi").mean())))
    by={m:rho(z.score,z.ret) for m,z in subsets.items()}
    avg=float(np.nanmean(list(by.values()))); pool=rho(v.score,v.ret)
    xr=v.score.rank();yr=v.ret.rank()
    x=(xr-xr.mean())/xr.std(ddof=0);y=(yr-yr.mean())/yr.std(ddof=0)
    between=sum(len(z)/len(v)*x.loc[z.index].mean()*y.loc[z.index].mean() for z in subsets.values())
    rows.append(dict(run=rid,avg=avg,pool=pool,kospi=by["kospi"],kosdaq=by["kosdaq"],
        delta=pool-avg,ret_gap=subsets["kospi"].ret.mean()-subsets["kosdaq"].ret.mean(),
        ret_median_gap=subsets["kospi"].ret.median()-subsets["kosdaq"].ret.median(),
        score_gap=subsets["kospi"].score.mean()-subsets["kosdaq"].score.mean(),
        kp_share=len(subsets["kospi"])/len(v),count=len(v),between=between,
        within_adjustment=pool-between-avg,**{"n_"+m:len(z) for m,z in subsets.items()}))
a=pd.DataFrame(rows); c=pd.DataFrame(comp)
result={"protocol":{"h":H,"reg":REG,"last_price":days[-1],"last_run":max(keep),
        "gate_partial":sorted(partial),"gate_double":sorted(double),
        "daily_anchors":len(keep),"weekly_anchors":len(weekset),"price_columns":len(p.columns),
        "closed_first":a.run.min(),"closed_last":a.run.max()},
        "daily":{},"weekly":{},"composition":{},"gap_correlations":{}}
for name,sub in [("daily",a),("weekly",a[a.run.isin(weekset)])]:
    for col in ["avg","pool","kospi","kosdaq","delta","between","within_adjustment"]:
        result[name][col]=stats(sub[col])
for name,sub in [("all",c),("closed",c[c.run.isin(a.run)])]:
    result["composition"][name]={"n":len(sub),**{col:float(sub[col].mean()) for col in sub.columns if col!="run"}}
for col in ["ret_gap","ret_median_gap","score_gap","kp_share","count"]:
    result["gap_correlations"][col]=correlation(a.delta,a[col])
result["valid_counts"]={col:[int(a[col].min()),int(a[col].max())] for col in ["n_kospi","n_kosdaq"]}
result["diagnostic_weekly_rows"]=a[a.run.isin(weekset)][["run","avg","pool","kospi","kosdaq"]].to_dict("records")
mc=pd.DataFrame(memo_comp)
result["memo_matching_valid_composition"]={k:float(mc[k].mean()) for k in mc.columns if k!="run"}
result["memo_comparison"]={}
for tag,z in [("daily",a),("weekly",a[a.run.isin(weekset)])]:
    result["memo_comparison"][tag]=dict(n=len(z),sign_disagreements=int((np.sign(z.avg)!=np.sign(z.pool)).sum()),
        correlation=float(np.corrcoef(z.avg,z.pool)[0,1]),
        ci_width_ratio=float(np.diff(stats(z.pool)["ci"])[0]/np.diff(stats(z.avg)["ci"])[0]))
result["memo_comparison"]["kp_ahead_share"]=float((a.ret_median_gap>0).mean())
print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))

