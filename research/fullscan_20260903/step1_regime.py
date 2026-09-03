# step1: 3년 국면 표 (D4) — 코스닥 4상태 + breadth. 산출 out/regime_daily.csv, out/regime_summary.csv
import numpy as np, pandas as pd, os
from fslib import *
P=Panel(); R=regimes(P)
R.to_csv(os.path.join(OUT,"regime_daily.csv"),index=False)
R["ym"]=R.date.str[:6]
m=R.groupby("ym").agg(kospi_ret=("kospi",lambda s: s.iloc[-1]/s.iloc[0]-1),kosdaq_ret=("kosdaq",lambda s: s.iloc[-1]/s.iloc[0]-1),
                      breadth=("breadth20","mean"),regime=("regime_pit",lambda s: s.value_counts().index[0] if s.notna().any() else None),days=("date","count"))
m.to_csv(os.path.join(OUT,"regime_summary.csv"))
print(m.round(3).to_string())
print(R.regime_pit.value_counts())
