# screener_fdr_v2_6.calculate_oversold_score 의 패널 재현(가격만) — 연구용 근사
import numpy as np, pandas as pd, flags as fl
C=fl.C; V=fl.V
Hh=fl.P['high']; Ll=fl.P['low']
d=C.diff(); gain=d.where(d>0,0).rolling(14).mean(); loss=(-d.where(d<0,0)).rolling(14).mean()
RSI=100-100/(1+gain/loss.replace(0,np.nan))
mid=C.rolling(20).mean(); sd=C.rolling(20).std(); bu=mid+2*sd; bl=mid-2*sd; rngb=bu-bl
BB=((C-bl)/rngb*100).where(rngb>0,50)
DD=(C-Hh.rolling(252,min_periods=50).max())/Hh.rolling(252,min_periods=50).max()*100
R1M=(C/C.shift(21)-1)*100
VVA=V/V.rolling(20).mean()
STO=100*(C-Ll.rolling(14).min())/(Hh.rolling(14).max()-Ll.rolling(14).min()).replace(0,np.nan)
def clip(x,lo,hi): return x.clip(lower=lo,upper=hi)
OS=(clip((50-RSI)*1.5,0,30).fillna(0)+clip((50-BB)*0.4,0,20).fillna(0)+clip(DD.abs()*0.4,0,20).fillna(0)
    +clip((-R1M).where(R1M<0,0)*0.5,0,15).fillna(0)+clip((VVA-1).where(VVA>1,0)*5,0,10).fillna(0)+clip((30-STO)*0.25,0,5).fillna(0))
OS=OS.where(C.notna()&(C>=1000))
RV21=fl.R.rolling(21,min_periods=8).std()
