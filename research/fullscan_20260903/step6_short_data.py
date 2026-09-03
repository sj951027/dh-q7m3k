# step6: 짧은 데이터(수급 주체별·공매도·신용·대차·밸류·컨센서스) 현재 시점 전수 스캔 — 주간 앵커, h5/h10/h20, 유니버스 3종.
import numpy as np, pandas as pd, os, time
from fslib import *
t0=time.time(); P=Panel(); ok=guards(P); F=factors(P)
H=[5,10,20]; FW={h:excess(fwd(P,h),ok) for h in H}
ti={k:i for i,k in enumerate(P.tick)}; di={d:i for i,d in enumerate(P.dates)}
def to_mat(df,col):
    m=np.full((P.T,P.N),np.nan); d=df[df.ticker.isin(ti)&df.date.isin(di)]
    m[d.date.map(di).values,d.ticker.map(ti).values]=d[col].values.astype(float); return m
con=ro(OHLCV)
fl=pd.read_sql("select ticker,date,foreign_net_val,inst_net_val,person_net_val,pension_net_val,trust_net_val,secfirm_net_val,prveq_net_val,insu_net_val,bank_net_val from daily_flows",con)
sf=pd.read_sql("select ticker,date,short_vol_ratio,short_val,credit_bal_rate,credit_bal_amt,loan_bal_qty from short_flows where date>='20260101'",con)
va=pd.read_sql("select ticker,date,pbr,per,div,eps,bps from valuation_daily",con)
cs=pd.read_sql("select ticker,date,opinion_score,target_price,coverage from consensus_daily",con)
amt20=roll_mean(P.amt,20,10)
X={}
for c in ["foreign","inst","person","pension","trust","secfirm","prveq","insu","bank"]:
    m=to_mat(fl,c+"_net_val")
    X[f"fl_{c}5n"]=roll_mean(np.nan_to_num(m),5,3)/amt20*5   # 5일 순매수/거래대금
    X[f"fl_{c}20n"]=roll_mean(np.nan_to_num(m),20,10)/amt20*20
    # 결측을 0으로 두면 미수집 종목이 중립 취급 — 커버 없는 날은 마스크
    cov=roll_mean(np.isfinite(m).astype(float),20,10)>0.5
    X[f"fl_{c}5n"][~cov]=np.nan; X[f"fl_{c}20n"][~cov]=np.nan
svr=to_mat(sf,"short_vol_ratio"); X["sh_svr5"]=roll_mean(svr,5,3); X["sh_svr20"]=roll_mean(svr,20,10)
X["sh_svr_chg"]=X["sh_svr5"]-X["sh_svr20"]
cr=to_mat(sf,"credit_bal_rate"); cr=pd.DataFrame(cr).ffill(limit=5).values; X["cr_rate"]=cr
X["cr_rate_chg20"]=cr-np.vstack([np.full((20,P.N),np.nan),cr[:-20]])
ln=to_mat(sf,"loan_bal_qty"); ln=pd.DataFrame(ln).ffill(limit=5).values
with np.errstate(all="ignore"): X["loan_ratio"]=ln/P.shares; X["loan_chg20"]=(ln-np.vstack([np.full((20,P.N),np.nan),ln[:-20]]))/P.shares
per=to_mat(va,"per"); pbr=to_mat(va,"pbr"); dv=to_mat(va,"div"); eps=to_mat(va,"eps"); bps=to_mat(va,"bps")
per[per==0]=np.nan; pbr[pbr==0]=np.nan
with np.errstate(all="ignore"):
    X["va_ep"]=1/per; X["va_bp"]=1/pbr; X["va_div"]=dv; X["va_roe"]=eps/bps*100
    X["va_roe"][(bps<=0)]=np.nan
tp=to_mat(cs,"target_price"); tp=pd.DataFrame(tp).ffill(limit=10).values
with np.errstate(all="ignore"): X["cs_gap"]=tp/P.close-1
X["cs_gap"][~np.isfinite(X["cs_gap"])]=np.nan
X["cs_cov"]=pd.DataFrame(to_mat(cs,"coverage")).ffill(limit=10).values
X["cs_op"]=pd.DataFrame(to_mat(cs,"opinion_score")).ffill(limit=10).values
HY={k:+1 for k in X}; 
for k in ["fl_foreign5n","fl_foreign20n","fl_pension5n","fl_pension20n","fl_inst20n","fl_inst5n"]: HY[k]=-1   # 기존 관측(역신호) 가설
HY["sh_svr_chg"]=-1
mc=rank01(np.where(ok,F["size"],np.nan)); quiet=rank01(np.where(ok,-(rank01(np.where(ok,F["lv60"],np.nan))+rank01(np.where(ok,F["to20"],np.nan))),np.nan))
U={"전체(가드)":ok,"대형(시총상위20%)":ok&(mc>=0.8),"조용함상위30%":ok&(quiet>=0.7),"과매도(RSI<40)":ok&(F["rsi14"]<40)}
start=P.idx("20260301"); rows=[]
for nm,x in X.items():
    for un,M in U.items():
        for h in H:
            ic=spearman_rows(x*HY[nm],FW[h],M); v=ic[start:]; fin=np.isfinite(v)
            if fin.sum()<3: continue
            first=P.dates[start+np.argmax(fin)]
            w=v[::5]; w=w[np.isfinite(w)]   # 주간 앵커
            m,lo,hi,n=boot_ci(w,800)
            rows.append(dict(factor=nm,universe=un,h=h,hyp=HY[nm],first_anchor=first,n_week=n,ic=m,lo=lo,hi=hi,pos=float(np.mean(w>0)),n_daily=int(fin.sum())))
    print(nm,round(time.time()-t0,1),flush=True)
df=pd.DataFrame(rows); df.to_csv(os.path.join(OUT,"short_data_ic.csv"),index=False)
pd.set_option("display.width",250); pd.set_option("display.max_rows",1000)
d=df[df.h==20].copy(); d["cell"]=d.apply(lambda r: f"{r.ic:+.3f}[{r.lo:+.2f},{r.hi:+.2f}]n{int(r.n_week)}",axis=1)
print(d.pivot(index="factor",columns="universe",values="cell").to_string())
d=df[df.h==10].copy(); d["cell"]=d.apply(lambda r: f"{r.ic:+.3f}[{r.lo:+.2f},{r.hi:+.2f}]n{int(r.n_week)}",axis=1)
print("h10"); print(d.pivot(index="factor",columns="universe",values="cell").to_string())
print("done",time.time()-t0)
