# -*- coding: utf-8 -*-
"""오버나이트/장중 분해 팩터 스캔 (연구 모드, 등록 아님) — 2026-08-22
가설(문헌): 오버나이트 수익 누적↑(개인 수요 쏠림) 종목은 이후 cross-section 수익↓.
프로토콜: 3년 패널, 월간(21거래일) 비중첩 앵커, h=20d, ENTRY_LAG=1, |ret|>32% 컷,
유니버스 가드 amt20>=5억. IC=단일 유니버스 스피어만. 연도별 분해 병기."""
import sqlite3, numpy as np, pandas as pd
oh = sqlite3.connect("file:../dh-q7m3k-data/ohlcv.db?mode=ro", uri=True)
P = pd.read_sql("SELECT ticker,date,open,close,volume FROM daily_ohlcv WHERE date>='20230601'", oh)
C = P.pivot_table(index="date",columns="ticker",values="close")
O = P.pivot_table(index="date",columns="ticker",values="open")
V = P.pivot_table(index="date",columns="ticker",values="volume")
O = O.where(O>0)
on = (O/C.shift(1)-1).clip(-0.35,0.35)   # 오버나이트
intr = (C/O-1).clip(-0.35,0.35)          # 장중
amt20 = (C*V).rolling(20,min_periods=10).mean()/1e8
F = {"on60": on.rolling(60,min_periods=40).mean()*252,
     "on20": on.rolling(20,min_periods=14).mean()*252,
     "in60": intr.rolling(60,min_periods=40).mean()*252}
F["tug60"] = F["on60"]-F["in60"]
dates = list(C.index)
anchors = list(range(80, len(dates)-21, 21))
res = {k: [] for k in F}
for i in anchors:
    d = dates[i]
    entry, exit_ = C.iloc[i+1], C.iloc[i+21]
    ret = ((exit_/entry-1)*100)
    ret = ret.where(ret.abs()<=32)
    ok = (amt20.iloc[i]>=5) & ret.notna()
    for k, M in F.items():
        f = M.iloc[i][ok]; rr = ret[ok]
        m = f.notna() & rr.notna()
        if m.sum()<300: res[k].append((d,np.nan,0)); continue
        ic = float(f[m].rank().corr(rr[m].rank()))
        res[k].append((d, ic, int(m.sum())))
rng = np.random.default_rng(42)
print(f"앵커 {len(anchors)}개, 유니버스 중앙값 {int(np.median([x[2] for x in res['on60'] if x[2]>0]))}종목")
for k in F:
    arr = pd.DataFrame(res[k], columns=["d","ic","n"]).dropna()
    ics = arr.ic.values
    boot = [rng.choice(ics,len(ics),replace=True).mean() for _ in range(2000)]
    lo,hi = np.percentile(boot,[2.5,97.5])
    yr = arr.assign(y=arr.d.str[:4]).groupby("y").ic.mean().round(3).to_dict()
    print(f"{k:6}: IC평균 {ics.mean():+.4f} CI[{lo:+.3f},{hi:+.3f}] n앵커={len(ics)} 음수앵커 {(ics<0).sum()}/{len(ics)} | 연도별 {yr}")
