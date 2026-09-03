# step7: lv_b / lv_a 강화 전수 — 실동결 유니버스(lowvol_scores lv_b, 2026-06-05~) 위에서 변수 1개 추가/교체/가중/유니버스 변형 짝비교.
import numpy as np, pandas as pd, os, time, warnings
warnings.filterwarnings("ignore")
from fslib import *
t0=time.time(); P=Panel(); ok=guards(P); F=factors(P); R=regimes(P)
H=[5,10,20]; FWr={h:fwd(P,h) for h in H}
ti={k:i for i,k in enumerate(P.tick)}; di={d:i for i,d in enumerate(P.dates)}
hc=ro(HIST)
lv=pd.read_sql("select run_id,market,ticker,model_id,lowvol_score from lowvol_scores where model_id in ('lv_b','lv_a','lv_e')",hc)
lv=lv.pivot_table(index=["run_id","market","ticker"],columns="model_id",values="lowvol_score").reset_index()
s3=pd.read_sql("select * from stage3_final",hc)
num=[c for c in s3.select_dtypes("number").columns if c not in ("corp_code",)]
s3=s3[["run_id","market","ticker"]+num]
df=lv.merge(s3,on=["run_id","market","ticker"],how="left")
df=df[df.run_id.isin(di)&df.ticker.isin(ti)].copy()
df["t"]=df.run_id.map(di); df["j"]=df.ticker.map(ti)
tt=df.t.values; jj=df.j.values
for h in H: df[f"fwd{h}"]=FWr[h][tt,jj]
for k,v in F.items(): df["px_"+k]=v[tt,jj]
# 짧은 데이터
o=ro(OHLCV)
fl=pd.read_sql("select ticker,date,foreign_net_val,inst_net_val,person_net_val,pension_net_val,trust_net_val,secfirm_net_val,prveq_net_val from daily_flows",o)
sf=pd.read_sql("select ticker,date,short_vol_ratio,credit_bal_rate,loan_bal_qty from short_flows where date>='20260101'",o)
va=pd.read_sql("select ticker,date,per,pbr,div from valuation_daily",o)
def to_mat(d,col):
    m=np.full((P.T,P.N),np.nan); d=d[d.ticker.isin(ti)&d.date.isin(di)]
    m[d.date.map(di).values,d.ticker.map(ti).values]=d[col].values.astype(float); return m
amt20=roll_mean(P.amt,20,10)
X={}
for c in ["foreign","inst","person","pension","trust","secfirm","prveq"]:
    m=to_mat(fl,c+"_net_val"); cov=roll_mean(np.isfinite(m).astype(float),20,10)>0.5
    for w in [5,20]:
        z=roll_mean(np.nan_to_num(m),w,max(3,w//2))/amt20*w; z[~cov]=np.nan; X[f"fl_{c}{w}n"]=z
svr=to_mat(sf,"short_vol_ratio"); X["sh_svr5"]=roll_mean(svr,5,3); X["sh_svr20"]=roll_mean(svr,20,10)
cr=pd.DataFrame(to_mat(sf,"credit_bal_rate")).ffill(limit=5).values; X["cr_rate"]=cr; X["cr_chg20"]=cr-np.vstack([np.full((20,P.N),np.nan),cr[:-20]])
ln=pd.DataFrame(to_mat(sf,"loan_bal_qty")).ffill(limit=5).values
with np.errstate(all="ignore"): X["loan_ratio"]=ln/P.shares
per=to_mat(va,"per"); pbr=to_mat(va,"pbr"); per[per==0]=np.nan; pbr[pbr==0]=np.nan
with np.errstate(all="ignore"): X["va_ep"]=1/per; X["va_bp"]=1/pbr; X["va_div"]=to_mat(va,"div")
ev=pd.read_csv(os.path.join(OUT,"dart_events_aligned.csv"),dtype={"ticker":str})
def flag_of(subs,days=60):
    f=np.zeros((P.T,P.N),bool)
    for r in ev[ev["sub"].isin(subs)].itertuples(): f[r.t:min(P.T,r.t+days+1),r.j]=True
    return f
X["ev_buyback60"]=flag_of(["buyback_trust","buyback_direct","buyback_trust_cancel","buyback_direct_cancel"]).astype(float)
X["ev_dilution60"]=flag_of(["cb","paid_in","bw","eb","paid_bonus_mix"]).astype(float)
for k,v in X.items(): df["x_"+k]=v[tt,jj]
df["mkt_kq"]=(df.market=="KOSDAQ").astype(float)
g=df.groupby(["run_id","market"])
def grank(s): return s.groupby([df.run_id,df.market]).rank(pct=True)
def ic_by_group(x,y):
    """(run,market)별 스피어만 → run별 평균(시장 평균) 시리즈"""
    d=pd.DataFrame({"r":df.run_id,"m":df.market,"x":x,"y":y}).dropna()
    d["rx"]=d.groupby(["r","m"]).x.rank(); d["ry"]=d.groupby(["r","m"]).y.rank()
    vals={}
    for (r,m),q in d.groupby(["r","m"]):
        if len(q)>=15: vals.setdefault(r,[]).append(np.corrcoef(q.rx,q.ry)[0,1])
    return pd.Series({r:float(np.mean(v)) for r,v in vals.items()},dtype=float)
base_rank_rv=grank(-df.realized_vol); base_rank_roe=grank(df.roe_value).fillna(0.5)
base=base_rank_rv+base_rank_roe    # lv_b 재현(핵심 rv 결측은 NaN)
fw={h:df[f"fwd{h}"] for h in H}
ic_base={h:ic_by_group(base,fw[h]) for h in H}
ic_frozen={h:ic_by_group(df.lv_b,fw[h]) for h in H}
print("lv_b 재현 vs 동결 IC 상관:",{h:round(np.corrcoef(ic_base[h].dropna(),ic_frozen[h].reindex(ic_base[h].dropna().index))[0,1],3) for h in H})
cands=[c for c in df.columns if c.startswith("px_") or c.startswith("x_")]+[c for c in num if c not in ("realized_vol","roe_value")]
rows=[]
def record(name,kind,score,extra=None):
    for h in H:
        ic=ic_by_group(score,fw[h]); d=(ic-ic_base[h]).dropna()
        m,lo,hi,n=boot_ci(d.values,500,block=5)
        rows.append(dict(variant=name,kind=kind,h=h,n=n,ic_var=float(ic.reindex(d.index).mean()),ic_base=float(ic_base[h].reindex(d.index).mean()),diff=m,lo=lo,hi=hi,pos=float(np.mean(d>0)),**(extra or {})))
SKIP=os.environ.get("SKIP_MAIN")=="1"
for c in ([] if SKIP else cands):
    x=df[c]
    if x.notna().mean()<0.3 or x.nunique()<5: continue
    for sign,sn in [(1,"+"),(-1,"-")]:
        r=grank(sign*x).fillna(0.5)
        record(f"{sn}{c}","add",base+r)
        record(f"{sn}{c}","replace_roe",base_rank_rv+r)
    print(c,round(time.time()-t0),flush=True)
# 가중 변형
for w in [0.5,1.5,2,3]: record(f"rv×{w}","weight",base_rank_rv*w+base_rank_roe)
record("rv 단독","weight",base_rank_rv)
# lv_e 동결 대조
record("lv_e(동결)","ref",df.lv_e); record("lv_a(동결)","ref",df.lv_a)
res=pd.DataFrame(rows)
if not SKIP: res.to_csv(os.path.join(OUT,"lvb_enhance.csv"),index=False)
else: res=pd.read_csv(os.path.join(OUT,"lvb_enhance.csv"))
# 유니버스 변형: 절대 IC + top20 초과 (같은 날 lv_b top20 대비)
urows=[]
def top20_ex(score,mask,h):
    d=pd.DataFrame({"r":df.run_id,"m":df.market,"s":np.where(mask,score,np.nan),"y":fw[h],"yall":fw[h]})
    d["rk"]=d.groupby(["r","m"]).s.rank(ascending=False)
    top=d[d.rk<=20].groupby("r")["y"].mean(); med=d.groupby("r")["yall"].median()
    out=(top-med); out=pd.Series(np.asarray(out,float),index=out.index); return out.dropna()
for un,mask in {"기본":np.ones(len(df),bool),"과매도30~60":df.oversold_score<60,"과매도30~50":df.oversold_score<50,"과매도40~70":df.oversold_score>=40,
                "유동성≥10억":df["amt_avg_1m_억"]>=10,"유동성≥20억":df["amt_avg_1m_억"]>=20,"RSI<40":df.RSI<40,"RSI<35":df.RSI<35,"코스닥만":df.market=="KOSDAQ","코스피만":df.market=="KOSPI",
                "희석60d제외":df.x_ev_dilution60==0,"on60상위10%제외":grank(df.px_on60)<0.9,"낙폭>25%":df["drawdown_52w_high_%"]<-25,"ocf_score상위":df.ocf_score>=df.ocf_score.median()}.items():
    for h in H:
        mk=np.asarray(mask,bool)
        ic=pd.Series(ic_by_group(pd.Series(np.where(mk,base.values,np.nan),index=df.index),fw[h])).astype(float); d=(ic-ic_base[h]).dropna(); m,lo,hi,n=boot_ci(d.values,500,block=5)
        e=top20_ex(base,mk,h); e0=top20_ex(base,np.ones(len(df),bool),h); dd=(e-e0).dropna(); m2,lo2,hi2,n2=boot_ci(dd.values,500,block=5)
        urows.append(dict(universe=un,h=h,n=int(n),share=float(mk.mean()),ic_abs=float(ic.mean()),ic_diff=m,ic_lo=lo,ic_hi=hi,top20_ex=float(np.nanmean(e.values)),top20_diff=m2,t_lo=lo2,t_hi=hi2,pos=float(np.mean(dd.values>0))))
ures=pd.DataFrame(urows); ures.to_csv(os.path.join(OUT,"lvb_universe_variants.csv"),index=False)
pd.set_option("display.width",250); pd.set_option("display.max_rows",400)
print(ures.round(4).to_string())
r20=res[(res.h==20)].sort_values("diff",ascending=False)
print("=== h20 상위 25 (add/replace) ==="); print(r20.head(25).round(4).to_string())
print("=== h20 하위 10 ==="); print(r20.tail(10).round(4).to_string())
print("done",time.time()-t0)
