# -*- coding: utf-8 -*-
"""Independent read-only supply-sign audit. Run from repository root:
python -B research/handoff/code_20261108_supply_sign_review.py
No output files, collectors, secrets, or operational imports. Prints JSON records.
"""
import sys,json,sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
sys.stdout.reconfigure(encoding="utf-8")
ROOT=Path(__file__).resolve().parents[2]
ASOF="20261106"
def emit(label,value):
 print(label,json.dumps(value,ensure_ascii=False,allow_nan=True),flush=True)
def ro(p):
 c=sqlite3.connect(p.resolve().as_uri()+"?mode=ro",uri=True)
 c.execute("PRAGMA query_only=ON")
 return c
paths=[ROOT/"history.db",ROOT.parent/"dh-q7m3k-data/ohlcv.db"]
before={str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in paths}
h,o=map(ro,paths)
p=pd.read_sql_query("SELECT ticker,date,close,market FROM daily_ohlcv WHERE date<=? ORDER BY date,ticker",o,params=(ASOF,))
c=p.pivot(index="date",columns="ticker",values="close").sort_index()
dates=list(c.index); di={d:i for i,d in enumerate(dates)}
mk=p.groupby("ticker").market.last(); cols={t:j for j,t in enumerate(c.columns)}
arr=c.to_numpy(); ff=c.ffill().to_numpy()
returns=c.pct_change(fill_method=None)
ew={m:(1+returns.loc[:,mk.reindex(c.columns).eq(m)].mean(axis=1).fillna(0)).cumprod().to_numpy() for m in ["KOSPI","KOSDAQ"]}
del p,returns
names={"f5":"foreign_5d_억","f20":"foreign_20d_억","i5":"inst_5d_억","i20":"inst_20d_억"}
fields=",".join('"'+v+'" AS '+k for k,v in names.items())
d=pd.read_sql_query('SELECT run_id,market,ticker,"amt_avg_1m_억" AS amt,supply_fetched,'+fields+" FROM stage3_final WHERE run_id>='20260602' AND run_id<=?",h,params=(ASOF,))
s=pd.read_sql_query("SELECT run_id,ticker,market,final_score_v3 score FROM v3_scores WHERE model_id='v30'",h)
cnt=pd.read_sql_query("SELECT run_id,COUNT(*) n FROM stage1_oversold GROUP BY run_id",h)
partial=set(cnt.loc[cnt.n<cnt.n.median()*.3,"run_id"]); double=set()
for tab in ["v3_scores","lowvol_scores","wu_scores"]:
 q=pd.read_sql_query("SELECT run_id,model_id,MIN(frozen_at) lo,MAX(frozen_at) hi FROM "+tab+" GROUP BY run_id,model_id",h)
 gap=(pd.to_datetime(q.hi,utc=True)-pd.to_datetime(q.lo,utc=True)).dt.total_seconds()
 double.update(q.loc[gap>=3600,"run_id"])
cand={}
for rid in sorted(d.run_id.unique()):
 if rid in partial|double:continue
 i=np.searchsorted(dates,rid,side="right")-1
 if i>=0 and (pd.Timestamp(rid)-pd.Timestamp(dates[i])).days<=5:cand.setdefault(i,[]).append(rid)
keep={i:next((r for r in ls if r==dates[i]),min(ls)) for i,ls in cand.items()}
d=d[d.run_id.isin(keep.values())].copy()
d.ticker=d.ticker.str.zfill(6);s.ticker=s.ticker.str.zfill(6)
d=d.merge(s[["run_id","ticker","score"]],on=["run_id","ticker"],how="left",validate="one_to_one")
d["t"]=d.run_id.map({r:i for i,r in keep.items()});d["j"]=d.ticker.map(cols)
d=d[d.j.notna()].copy();d.j=d.j.astype(int);d["month"]=d.run_id.str[:6];d.market=d.market.str.upper()
d["top"]=False
for _,g in d.dropna(subset=["score"]).groupby(["run_id","market"]):
 d.loc[g.sort_values(["score","ticker"],ascending=[False,True]).head(10).index,"top"]=True
d["target"]=np.nan;d["strict_target"]=np.nan;d["bench"]=np.nan
valid=d.t+41<len(dates)
ix=d.index[valid];tt=d.loc[ix,"t"].to_numpy()+1;jj=d.loc[ix,"j"].to_numpy()
b=np.array([ew[m][e+40]/ew[m][e]-1 for m,e in zip(d.loc[ix,"market"],tt)])
d.loc[ix,"bench"]=b*100
d.loc[ix,"target"]=(ff[tt+40,jj]/ff[tt,jj]-1-b)*100
d.loc[ix,"strict_target"]=(arr[tt+40,jj]/arr[tt,jj]-1-b)*100
flows=pd.read_sql_query("SELECT ticker,date,close,foreign_net_qty,inst_net_qty,foreign_net_val,inst_net_val FROM daily_flows WHERE date<=?",o,params=(ASOF,))
bad_codes=flows[~flows.ticker.str.fullmatch(r"[0-9A-Z]{6}")]
emit("FLOW_CODE_QUALITY",dict(rows=len(bad_codes),nonzero_foreign=int(bad_codes.foreign_net_val.fillna(0).ne(0).sum()),missing_close=int(bad_codes.close.isna().sum())))
# Keep original six-character ticker identities. Do not merge malformed short-code
# zero rows into genuine ticker observations by applying zfill here.
for who,short in [("foreign","f"),("inst","i")]:
 pv=flows.pivot(index="date",columns="ticker",values=who+"_net_val").reindex(index=dates,columns=c.columns)
 qv=flows.assign(v=flows[who+"_net_qty"]*flows.close).pivot(index="date",columns="ticker",values="v").reindex(index=dates,columns=c.columns)
 for window in [5,20]:
  key=short+str(window); r=pv.rolling(window,min_periods=window).sum()/100 # million KRW -> 100m KRW
  n=pv.rolling(window,min_periods=1).count()
  approx=qv.rolling(window,min_periods=window).sum()/1e8
  ti=d.t.to_numpy();ji=d.j.to_numpy()
  d["cash_"+key]=r.to_numpy()[ti,ji]
  d["count_"+key]=n.to_numpy()[ti,ji]
  d["qty_"+key]=approx.to_numpy()[ti,ji]
del pv,qv,r,n,approx
def ic(g,x,y,min_n):
 z=g[[x,y]].replace([np.inf,-np.inf],np.nan).dropna()
 if len(z)<min_n or z[x].nunique()<2 or z[y].nunique()<2:return None
 return float(spearmanr(z[x],z[y]).statistic),len(z)
def series(frame,x,pool=False,min_n=None,y="target"):
 rows=[]
 group=["run_id"] if pool else ["run_id","market"]
 minimum=min_n if min_n is not None else (12 if pool else 12)
 for key,g in frame.groupby(group):
  v=ic(g,x,y,minimum)
  if v is not None:rows.append((key[0],key[1] if len(key)>1 else "pooled",v[0],v[1]))
 return pd.DataFrame(rows,columns=["run_id","market","ic","n"])
def ci(a,block=5):
 a=np.asarray(a,float);n=len(a)
 if n<2:return [None,None]
 rng=np.random.default_rng(20261108);block=min(block,max(1,n//2))
 ix=(rng.integers(n,size=(4000,int(np.ceil(n/block))))[:,:,None]+np.arange(block))%n
 values=a[ix.reshape(4000,-1)[:,:n]].mean(axis=1)
 return list(map(float,np.quantile(values,[.025,.975])))
def stats(z,block=5):
 if len(z)==0:return {}
 days=z.groupby("run_id").ic.mean()
 return dict(ic=float(days.mean()),ci=ci(days,block),n_days=len(days),n_groups=len(z),n_pairs=int(z.n.sum()),positive_days=float((days>0).mean()*100),
             group_mean=float(z.ic.mean()),positive_groups=float((z.ic>0).mean()*100))
emit("SAMPLE",dict(rows=len(d),anchors=d.run_id.nunique(),mature_rows=int(d.target.notna().sum()),mature_dates=d.loc[d.target.notna(),"run_id"].nunique(),partial=sorted(partial),double=sorted(double),last=dates[-1]))
reference=pd.read_csv(ROOT/"research/out_early_rise_scan/supply_sign_monthly.csv")
monthly=[]
for lab,frame,pool in [("stage3",d,False),("v30_top10",d[d.top],True)]:
 for month,g in frame[frame.month.between("202606","202609")].groupby("month"):
  for key in names:
   old=reference[(reference["표본"]==lab)&(reference["목표"]=="T4")&(reference["월"]==int(month))]
   row=dict(sample=lab,month=month,var=key,claimed=float(old[names[key]].iloc[0]),frozen=stats(series(g,key,pool)),cash=stats(series(g,"cash_"+key,pool)))
   if pool:
    row["within_frozen"]=stats(series(g,key,False,min_n=8))
    row["within_cash"]=stats(series(g,"cash_"+key,False,min_n=8))
   monthly.append(row)
emit("MONTHLY",monthly)
totals=[]
for lab,frame,pool in [("stage3",d,False),("top_pooled",d[d.top],True),("top_within_market",d[d.top],False)]:
 for key in names:
  for source in ["","cash_"]:
   z=series(frame,source+key,pool,min_n=(8 if lab=="top_within_market" else None))
   totals.append(dict(sample=lab,var=source+key,**stats(z,20)))
emit("TOTALS",totals)
# September actual completed windows and group IC (not the uncompleted 19 dates)
sep=d[(d.month=="202609")&d.target.notna()]
emit("SEPTEMBER",dict(input_rows=int((d.month=="202609").sum()),mature_rows=len(sep),top_rows=int(sep.top.sum()),windows=[dict(run=r,entry=dates[int(g.t.iloc[0])+1],exit=dates[int(g.t.iloc[0])+41]) for r,g in sep.groupby("run_id")],
 per_day=[dict(var=k,values=series(sep[sep.top],k,True)[["run_id","ic","n"]].to_dict("records"),iid_ci=ci(series(sep[sep.top],k,True).ic,1)) for k in names]))
# Scale / missingness / proxy differences
audit=[]
for key in names:
 z=d[d.target.notna()]
 mask=z[[key,"qty_"+key]].notna().all(axis=1)
 audit.append(dict(var=key,stored_null=int(z[key].isna().sum()),stored_zero=int(z[key].eq(0).sum()),cash_missing=int(z["cash_"+key].isna().sum()),
  cash_zero=int(z["cash_"+key].eq(0).sum()),cash_missing_stored_zero=int((z["cash_"+key].isna()&z[key].eq(0)).sum()),
  qty_round_match=float((z.loc[mask,key].round(1)==z.loc[mask,"qty_"+key].round(1)).mean()),n_qty_compare=int(mask.sum()),
  qty_spearman=float(z.loc[mask,key].corr(z.loc[mask,"qty_"+key],method="spearman"))))
emit("NULL_PROXY",audit)
emit("SUPPLY_FETCHED",d.groupby("supply_fetched",dropna=False).size().to_dict())
q=flows.dropna(subset=["foreign_net_val","foreign_net_qty","close"])
q=q[(q.foreign_net_val.abs()>100)&(q.foreign_net_qty.abs()>1000)]
ratio=(q.foreign_net_qty*q.close/q.foreign_net_val).abs()
emit("UNIT",dict(ratio_median=float(ratio.median()),ratio_q10=float(ratio.quantile(.1)),ratio_q90=float(ratio.quantile(.9)),n=len(q),
 sign_same=float((np.sign(q.foreign_net_qty)==np.sign(q.foreign_net_val)).mean())))
# Tradable amount tertiles, defined separately within each anchor/market
rank=d.groupby(["run_id","market"]).amt.rank(method="first",pct=True)
d["stratum"]=np.ceil(rank*3).clip(1,3)
strat=[]
for label,frame,pool in [("stage3",d,False),("top_pooled",d[d.top],True)]:
 for source in ["","cash_"]:
  for key in ["f5","f20","i5"]:
   for tier,g in frame.groupby("stratum"):
    z=series(g,source+key,pool,min_n=4 if pool else 12)
    strat.append(dict(sample=label,var=source+key,tier=int(tier),**stats(z,20)))
emit("STRATA",strat)
# Same-pair and endpoint sensitivities (remove full-window missingness as sole cause)
sens=[]
for lab,frame,pool in [("stage3",d,False),("top",d[d.top],True)]:
 for key in ["f5","f20","i5"]:
  common=frame[frame["cash_"+key].notna()]
  sens.append(dict(sample=lab,var=key,frozen_common=stats(series(common,key,pool),20),cash_common=stats(series(common,"cash_"+key,pool),20),
    frozen_strict_price=stats(series(frame,key,pool,y="strict_target"),20)))
emit("SENSITIVITY",sens)
# A no-price row with zero flow can be an unavailable response, not a true zero.
# Exclude these conservatively and recheck the same full-window cash variables.
clean_sens=[]
for who,short in [("foreign","f"),("inst","i")]:
 clean=flows.copy();clean.loc[clean.close.isna()|clean.close.le(0),who+"_net_val"]=np.nan
 mat=clean.pivot(index="date",columns="ticker",values=who+"_net_val").reindex(index=dates,columns=c.columns)
 for w in [5,20]:
  key=short+str(w);rr=mat.rolling(w,min_periods=w).sum()/100
  d["clean"]=rr.to_numpy()[d.t.to_numpy(),d.j.to_numpy()]
  for lab,frame,pool in [("stage3",d,False),("top",d[d.top],True)]:
   clean_sens.append(dict(sample=lab,var=key,extra_missing=int((frame.target.notna()&frame["cash_"+key].notna()&frame.clean.isna()).sum()),**stats(series(frame,"clean",pool),20)))
emit("ZERO_PLACEHOLDER_SENS",clean_sens)
emit("SEP_WITHIN_MARKET",[dict(var=src+key,**stats(series(sep[sep.top],src+key,False,min_n=8),1)) for src in ["","cash_"] for key in names])
# Overall available-stock monthly flows, not claimed as exchange-wide complete
flows["month"]=flows.date.str[:6]
flows["market"]=flows.ticker.map(mk)
flow_month=[]
for month,g in flows[flows.month.between("202606","202611")].groupby("month"):
 counts=g.groupby("date").ticker.nunique()
 flow_month.append(dict(month=month,days=len(counts),min_tickers=int(counts.min()),max_tickers=int(counts.max()),foreign_trillion=float(g.foreign_net_val.sum()/1e6),inst_trillion=float(g.inst_net_val.sum()/1e6)))
emit("MONTH_FLOW",flow_month)
emit("SEP_WINDOW_FLOW",[dict(run=rid,entry=dates[int(g.t.iloc[0])+1],exit=dates[int(g.t.iloc[0])+41],foreign_trillion=float(flows.loc[flows.date.between(dates[int(g.t.iloc[0])+1],dates[int(g.t.iloc[0])+41]),"foreign_net_val"].sum()/1e6)) for rid,g in sep.groupby("run_id")])
market=pd.read_sql_query("SELECT series,date,close FROM market_daily WHERE series IN ('KOSPI','KOSDAQ') AND date<=? ORDER BY date",o,params=(ASOF,))
market_rows=[]
for m,g in market.groupby("series"):
 z=g.set_index("date").close
 for month in ["202606","202607","202608","202609","202610","202611"]:
  a=z[z.index.str.startswith(month)]
  prev=z[z.index<a.index[0]] if len(a) else z.iloc[:0]
  if len(a) and len(prev):market_rows.append(dict(market=m,month=month,first=a.index[0],last=a.index[-1],ret=float((a.iloc[-1]/prev.iloc[-1]-1)*100)))
 for rid,gsep in sep.groupby("run_id"):
  e=dates[int(gsep.t.iloc[0])+1];end=dates[int(gsep.t.iloc[0])+41]
  if e in z.index and end in z.index:
   market_rows.append(dict(market=m,anchor=rid,entry=e,exit=end,ret40=float((z[end]/z[e]-1)*100)))
emit("INDEX",market_rows)
# For a fixed set of tickers with all days present, test monthly flow direction
window_dates=[dt for dt in dates if "20260601"<=dt<="20261031"]
counts=flows[flows.date.isin(window_dates)].groupby("ticker").date.nunique()
fixed=set(counts[counts==len(window_dates)].index)
fixed_flows=flows[flows.ticker.isin(fixed)&flows.date.isin(window_dates)]
emit("FIXED_FLOW",dict(tickers=len(fixed),days=len(window_dates),months=(fixed_flows.groupby("month")[["foreign_net_val","inst_net_val"]].sum()/1e6).to_dict("index")))
emit("IMMUTABLE",before=={str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in paths})
h.close();o.close()

