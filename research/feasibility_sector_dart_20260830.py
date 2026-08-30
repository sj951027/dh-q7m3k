# -*- coding: utf-8 -*-
"""2026-08-30 타당성 점검 (관측 전용 — 점수식 무접촉)
A) 업종 분류 정비 → OCF 산업 보정의 기대 가치 (large 트랙, h20 참고·정본은 h60/120)
B) DART 공시 이벤트 수집의 기대 가치 — 상장주식수 증가(희석)를 프록시로 사후수익 실측
사용: python research/feasibility_sector_dart_20260830.py  (repo 루트에서)
"""
import sqlite3, numpy as np, pandas as pd

rng = np.random.default_rng(20260830)
H = sqlite3.connect("history.db")
O = sqlite3.connect("../dh-q7m3k-data/ohlcv.db")

px = pd.read_sql("select ticker,date,close,shares from daily_ohlcv where close>0", O)
piv = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
dates = piv.index.to_list(); didx = {d:i for i,d in enumerate(dates)}
entry = piv.shift(-1)                      # ENTRY_LAG=1
def fwd(h):                                # 진입 t+1 종가 → t+1+h 종가
    return piv.shift(-(1+h)) / entry - 1.0

FWD20 = fwd(20); FWD5 = fwd(5); FWD60 = fwd(60)

def boot_ci(vals, n=4000):
    vals = np.asarray(vals, float); vals = vals[~np.isnan(vals)]
    if len(vals) < 3: return (np.nan, np.nan)
    idx = rng.integers(0, len(vals), (n, len(vals)))
    means = vals[idx].mean(axis=1)
    return tuple(np.percentile(means, [2.5, 97.5]))

print("="*70); print("A) OCF 산업 보정 — large_final 실측 (h20 참고 지표)")
lf = pd.read_sql("select run_id,ticker,sector,sector_raw,ocf_to_op_ratio from large_final", H)
runs = sorted(lf.run_id.unique())
wk = runs[::5]                             # 주 1회 샘플로 중복창 완화
lf = lf[lf.run_id.isin(wk)].copy()
lf["ocf"] = pd.to_numeric(lf.ocf_to_op_ratio, errors="coerce")
lf = lf.dropna(subset=["ocf"])
lf = lf[lf.run_id.isin([r for r in wk if r in didx])]
print(f"주간 샘플 run {len([r for r in wk if r in didx])}개, ocf 보유 {len(lf)}행")

def get_fwd(F, r, t):
    try: return F.at[r, t]
    except KeyError: return np.nan
lf["f20"] = [get_fwd(FWD20, r, t) for r,t in zip(lf.run_id, lf.ticker)]
lf = lf.dropna(subset=["f20"])
# run별 시장 평균 제거(초과수익)
lf["ex20"] = lf.f20 - lf.groupby("run_id").f20.transform("mean")
lf["gate_raw"] = ((lf.ocf>=0.7)&(lf.ocf<=5.0)).astype(int)
med = lf.groupby(["run_id","sector"]).ocf.transform("median")
lf["rel"] = lf.ocf/med
lf["gate_ind"] = ((lf.rel>=0.5)&(lf.rel<=3.0)).astype(int)   # 업종상대 밴드(동폭 로그스케일 근사)

for g in ["gate_raw","gate_ind"]:
    a = lf.loc[lf[g]==1,"ex20"]; b = lf.loc[lf[g]==0,"ex20"]
    d = a.mean()-b.mean()
    # run 블록 부트스트랩(창 중복 감안)
    rs = lf.run_id.unique(); diffs=[]
    for _ in range(2000):
        pick = rng.choice(rs, len(rs), replace=True)
        sub = pd.concat([lf[lf.run_id==r] for r in pick])
        x=sub.loc[sub[g]==1,"ex20"].mean(); y=sub.loc[sub[g]==0,"ex20"].mean()
        diffs.append(x-y)
    lo,hi = np.percentile(diffs,[2.5,97.5])
    print(f"  {g}: 통과-탈락 초과수익차 {d*100:+.2f}%p  CI[{lo*100:+.2f},{hi*100:+.2f}] "
          f"(통과 {int((lf[g]==1).sum())} / 탈락 {int((lf[g]==0).sum())})")

resc = lf[(lf.gate_raw==0)&(lf.rel.between(0.7,1.5))]
truf = lf[(lf.gate_raw==0)&(~lf.rel.between(0.7,1.5))]
print(f"  '업종 아티팩트 탈락'(고정밴드 탈락이지만 업종 정상범위): {len(resc)}행 "
      f"ex20 {resc.ex20.mean()*100:+.2f}%p CI{tuple(round(x*100,2) for x in boot_ci(resc.ex20))}")
print(f"  '진성 탈락': {len(truf)}행 ex20 {truf.ex20.mean()*100:+.2f}%p CI{tuple(round(x*100,2) for x in boot_ci(truf.ex20))}")
# 커버리지 현황
last = runs[-1]
cur = pd.read_sql(f"select sector,sector_raw from large_final where run_id='{last}'", H)
print(f"  커버리지(최근 run): sector_raw 미분류 {int(((cur.sector_raw.isna())|(cur.sector_raw=='미분류')).sum())}/500, "
      f"오버레이 후 {int(((cur.sector.isna())|(cur.sector=='미분류')).sum())}/500")

print("="*70); print("B) 희석 이벤트(상장주식수 증가) — DART 공시 수집의 프록시 실측")
sh = px.pivot_table(index="date", columns="ticker", values="shares", aggfunc="last").sort_index()
chg = sh/sh.shift(1) - 1.0
ev = chg.stack()
ev = ev[ev > 0.005].reset_index(); ev.columns=["date","ticker","dilu"]
ev = ev[ev.date <= dates[-(1+20+1)]]        # h20 관측 가능한 이벤트만
ev["f20"] = [get_fwd(FWD20, d, t) for d,t in zip(ev.date, ev.ticker)]
ev["f5"]  = [get_fwd(FWD5 , d, t) for d,t in zip(ev.date, ev.ticker)]
mkt20 = FWD20.mean(axis=1); mkt5 = FWD5.mean(axis=1)
ev["ex20"] = ev.f20 - ev.date.map(mkt20); ev["ex5"] = ev.f5 - ev.date.map(mkt5)
ev = ev.dropna(subset=["ex20"])
ev["bin"] = pd.cut(ev.dilu, [0.005,0.02,0.10,np.inf], labels=["0.5~2%","2~10%",">10%"])
print(f"이벤트 수(≥0.5% 증가, h20 관측가능): {len(ev)}  기간 {ev.date.min()}~{ev.date.max()}")
for b,sub in ev.groupby("bin", observed=True):
    lo,hi = boot_ci(sub.ex20)
    lo5,hi5 = boot_ci(sub.ex5)
    print(f"  {b}: n={len(sub)}  ex_h20 {sub.ex20.mean()*100:+.2f}%p CI[{lo*100:+.2f},{hi*100:+.2f}]"
          f"  ex_h5 {sub.ex5.mean()*100:+.2f}%p CI[{lo5*100:+.2f},{hi5*100:+.2f}]")
# 과매도 유니버스 내 해당 여부: 이벤트 후 20일 내 stage1 진입 종목
s1 = pd.read_sql("select distinct run_id, ticker from stage1_oversold", H)
s1_dates = sorted(s1.run_id.unique())
ev["near_s1"] = 0
s1set = set(zip(s1.run_id, s1.ticker))
for i,row in ev.iterrows():
    if row.date not in didx: continue
    di = didx[row.date]
    later = [d for d in s1_dates if d >= row.date and d in didx and didx[d] <= di+20]
    if any((d,row.ticker) in s1set for d in later):
        ev.at[i,"near_s1"] = 1
sub = ev[ev.near_s1==1]
lo,hi = boot_ci(sub.ex20)
print(f"  이벤트 후 20일 내 과매도 유니버스 진입: n={len(sub)}  ex_h20 {sub.ex20.mean()*100:+.2f}%p CI[{lo*100:+.2f},{hi*100:+.2f}]")
# 감소(소각·감자) 쪽도 참고
dv = chg.stack(); dv = dv[dv < -0.005].reset_index(); dv.columns=["date","ticker","chg"]
dv = dv[dv.date <= dates[-(1+20+1)]]
dv["f20"] = [get_fwd(FWD20, d, t) for d,t in zip(dv.date, dv.ticker)]
dv["ex20"] = dv.f20 - dv.date.map(mkt20); dv = dv.dropna(subset=["ex20"])
lo,hi = boot_ci(dv.ex20)
print(f"  (참고) 주식수 감소 이벤트: n={len(dv)}  ex_h20 {dv.ex20.mean()*100:+.2f}%p CI[{lo*100:+.2f},{hi*100:+.2f}]")
