# -*- coding: utf-8 -*-
"""
short_credit_scan.py — 공매도·신용·수급 팩터 전수 스캔 (§14 탐색 전용, 2026-08-12)
===================================================================================
동기: "lv_b보다 IC 높은 것" 요청. 가격 재조합 전수조사는 기완료(산출물 px_a) — 이번엔
      직교 데이터(공매도 short_flows·신용잔고·수급 daily_flows)를 전수 스캔.
데이터 한계(커버리지 실측): short_flows 전종목은 2026-03부터(그 전 2~30종목뿐).
  → 스캔창 = 2026-03-02 ~ 2026-08-10 (~110거래일, 하락→폭락→반등 국면 포함). 전부 in-sample.
  credit_bal_rate 는 2026년 31% 종목만(수집 서브셋) — 별도 표기.
PIT: 공매도·신용은 공표 지연 감안 2거래일 랙, 수급은 1거래일 랙.
프로토콜: 주간 앵커(h20은 창 겹침 — CI 과신 금지), Spearman IC, 앵커 부트스트랩 CI,
  월별 일관성, 서브셋 3종(전체 가드 유니버스 / 저변동 하위⅓ / 거래대금 상위½).
  벤치마크로 lv63·nh252·r20 병기(새 팩터가 이들 대비 나은지 맥락).
실행: python research/short_credit_scan.py
"""
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
OHLCV = HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"
RNG = np.random.default_rng(20260812)

def ic(x, y, min_n=30):
    m = x.notna() & y.notna()
    if m.sum() < min_n:
        return np.nan, int(m.sum())
    return x[m].rank().corr(y[m].rank()), int(m.sum())

def bci(v, nb=3000):
    v = np.asarray([x for x in v if np.isfinite(x)])
    if len(v) < 3:
        return (np.nan, np.nan)
    i = RNG.integers(0, len(v), (nb, len(v)))
    mm = v[i].mean(axis=1)
    return float(np.quantile(mm, .025)), float(np.quantile(mm, .975))

oc = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
print("[로드] ohlcv / short_flows / daily_flows")
px = pd.read_sql("SELECT ticker,date,close,volume,change_pct FROM daily_ohlcv WHERE date>='20251001'", oc)
dts = sorted(px.date.unique())
C = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").reindex(dts)
V = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(dts)
R = px.pivot_table(index="date", columns="ticker", values="change_pct", aggfunc="last").reindex(dts)

sf = pd.read_sql("SELECT ticker,date,short_vol_ratio,short_val,credit_bal_rate FROM short_flows WHERE date>='20260101'", oc)
SV = sf.pivot_table(index="date", columns="ticker", values="short_vol_ratio", aggfunc="last").reindex(dts).reindex(columns=C.columns)
SVAL = sf.pivot_table(index="date", columns="ticker", values="short_val", aggfunc="last").reindex(dts).reindex(columns=C.columns)
CB = sf.pivot_table(index="date", columns="ticker", values="credit_bal_rate", aggfunc="last").reindex(dts).reindex(columns=C.columns)

fl = pd.read_sql("SELECT ticker,date,foreign_net_val,inst_net_val,person_net_val FROM daily_flows", oc)
FG = fl.pivot_table(index="date", columns="ticker", values="foreign_net_val", aggfunc="last").reindex(dts).reindex(columns=C.columns)
IN_ = fl.pivot_table(index="date", columns="ticker", values="inst_net_val", aggfunc="last").reindex(dts).reindex(columns=C.columns)
PS = fl.pivot_table(index="date", columns="ticker", values="person_net_val", aggfunc="last").reindex(dts).reindex(columns=C.columns)
print(f"  패널 {C.shape}, 창 {dts[0]}~{dts[-1]}")

anchors = []
wk = set()
for i, d in enumerate(dts):
    if d < '20260302' or d > '20260810':
        continue
    w = pd.Timestamp(d).isocalendar()[:2]
    if w not in wk:
        wk.add(w)
        anchors.append(i)
print(f"  주간 앵커 {len(anchors)}개")

LAG_S, LAG_F = 2, 1   # 공매도/신용 2일, 수급 1일 랙(PIT 보수)

def factors(t):
    c = C.iloc[:t+1]; v = V.iloc[:t+1]; r = R.iloc[:t+1]
    ts = t - LAG_S; tf = t - LAG_F
    f = pd.DataFrame(index=C.columns)
    amt20 = (c*v).iloc[-20:].mean()/1e8
    f["_amt20"] = amt20
    f["_lv63"] = r.iloc[-63:].std()
    f["lv63"] = f["_lv63"]
    f["nh252"] = c.iloc[-1]/c.iloc[-252:].max()-1 if len(c) >= 252 else c.iloc[-1]/c.max()-1
    f["r20"] = (1+r.iloc[-20:]).prod()-1
    f["sv5"] = SV.iloc[max(0,ts-4):ts+1].mean()
    f["sv20"] = SV.iloc[max(0,ts-19):ts+1].mean()
    f["sv_chg"] = f["sv5"] - f["sv20"]
    a5 = (c*v).iloc[-5:].mean()
    f["sval_amt"] = SVAL.iloc[max(0,ts-4):ts+1].mean() / a5.replace(0, np.nan)
    f["credit"] = CB.iloc[:ts+1].ffill(limit=10).iloc[-1]
    cb20 = CB.iloc[:max(1,ts-19)].ffill(limit=10).iloc[-1]
    f["credit_chg"] = f["credit"] - cb20
    f["fgn5"] = FG.iloc[max(0,tf-4):tf+1].sum(min_count=3)
    f["fgn20"] = FG.iloc[max(0,tf-19):tf+1].sum(min_count=10)
    f["inst20"] = IN_.iloc[max(0,tf-19):tf+1].sum(min_count=10)
    f["person20"] = PS.iloc[max(0,tf-19):tf+1].sum(min_count=10)
    return f

FACT = ["sv5","sv20","sv_chg","sval_amt","credit","credit_chg",
        "fgn5","fgn20","inst20","person20","lv63","nh252","r20"]
SUBS = ["전체","저변동⅓","대금상위½"]
res = {h: {s: {f: [] for f in FACT} for s in SUBS} for h in (5, 20)}
mon = {f: {} for f in FACT}   # 전체 h20 월별

nb_anchor = {5: 0, 20: 0}
for t in anchors:
    F = factors(t)
    guard = (F["_amt20"] >= 5) & F["_lv63"].notna()
    base = F[guard]
    lowv = base[base["_lv63"] <= base["_lv63"].quantile(1/3)]
    big = base[base["_amt20"] >= base["_amt20"].median()]
    for h in (5, 20):
        if t + h >= len(R):
            continue
        y = (1 + R.iloc[t+1:t+1+h]).prod() - 1
        nb_anchor[h] += 1
        for s, sub in zip(SUBS, (base, lowv, big)):
            yy = y.reindex(sub.index)
            for f in FACT:
                v, n = ic(sub[f], yy)
                res[h][s][f].append(v)
                if h == 20 and s == "전체" and np.isfinite(v):
                    mon[f].setdefault(dts[t][:6], []).append(v)

print(f"\n닫힌 앵커: h5 {nb_anchor[5]} / h20 {nb_anchor[20]} (h20 주간앵커 창 겹침 주의)")
out_rows = []
for h in (5, 20):
    for s in SUBS:
        for f in FACT:
            v = [x for x in res[h][s][f] if np.isfinite(x)]
            if not v:
                continue
            lo, hi = bci(v)
            out_rows.append(dict(h=h, subset=s, factor=f, mean_ic=np.mean(v),
                                 n_anchor=len(v), ci_lo=lo, ci_hi=hi,
                                 pos=np.mean([x > 0 for x in v])))
O = pd.DataFrame(out_rows)
for h in (5, 20):
    print(f"\n===== h{h} =====")
    for s in SUBS:
        d = O[(O.h == h) & (O.subset == s)].sort_values("mean_ic", key=lambda x: x.abs(), ascending=False)
        print(f"\n--- {s} ---")
        print(d[["factor","mean_ic","n_anchor","ci_lo","ci_hi","pos"]].to_string(index=False,
              float_format=lambda x: f"{x:+.3f}"))

print("\n=== 전체 h20 월별 IC (일관성) ===")
mtab = pd.DataFrame({f: {m: np.mean(v) for m, v in mon[f].items()} for f in FACT}).T
print(mtab.round(3).to_string())

O.to_csv(HERE / "research" / "short_credit_scan_out.csv", index=False)
n_tests = len(FACT) * len(SUBS) * 2
print(f"\nBonferroni 참고: 검정 {n_tests}건 — CI 벗어나도 '기움'까지만. 전부 in-sample 단일 5.5개월.")
