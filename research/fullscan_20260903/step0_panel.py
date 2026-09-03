# step0: daily_ohlcv -> numpy panel cache (dates x tickers). read-only.
import sqlite3, numpy as np, pandas as pd, time, os, sys
_HERE=os.path.dirname(os.path.abspath(__file__)); _REPO=os.path.abspath(os.path.join(_HERE,"..",".."))
OHLCV=os.path.join(_REPO,"..","dh-q7m3k-data","ohlcv.db")
OUT=sys.argv[1] if len(sys.argv)>1 else os.path.join(_HERE,"panel.npz")
t=time.time()
con=sqlite3.connect(f"file:{OHLCV}?mode=ro",uri=True)
df=pd.read_sql("select ticker,date,open,high,low,close,volume,shares,is_suspended,market from daily_ohlcv",con)
print("rows",len(df),time.time()-t)
df=df[df.ticker.str.fullmatch(r"\d{6}")]
dates=np.array(sorted(df.date.unique())); tick=np.array(sorted(df.ticker.unique()))
di={d:i for i,d in enumerate(dates)}; ti={k:i for i,k in enumerate(tick)}
r=df.date.map(di).values; c=df.ticker.map(ti).values
def mat(col,dtype=np.float32,fill=np.nan):
    m=np.full((len(dates),len(tick)),fill,dtype=dtype); m[r,c]=df[col].values.astype(dtype); return m
close=mat("close"); open_=mat("open"); high=mat("high"); low=mat("low"); vol=mat("volume"); shares=mat("shares"); susp=mat("is_suspended",np.float32,0)
mk=df.groupby("ticker").market.last().reindex(tick).values.astype(str)
md=pd.read_sql("select series,date,close from market_daily",con).pivot(index="date",columns="series",values="close").reindex(dates)
np.savez_compressed(OUT,dates=dates,tick=tick,close=close,open=open_,high=high,low=low,vol=vol,shares=shares,susp=susp,mk=mk,kospi=md["KOSPI"].values,kosdaq=md["KOSDAQ"].values,usdkrw=md["USDKRW"].values)
print("saved",OUT,close.shape,time.time()-t)
