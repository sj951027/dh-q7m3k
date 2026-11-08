# -*- coding: utf-8 -*-
"""종합 신호판 근거 — 11년 대리 (2026-11-08, 읽기 전용 · 표시 규칙 근거 · 채택 아님). SIGNAL_BOARD_20261108.md §0-3 E1·E2.

틀은 `hold_early_exit_10y_20261108.py` 그대로(정리 유니버스 · 과매도 대리 = 20일 수익 하위 20% · 5거래일 격자 · t+1 진입 40일 · 비용 0.35% · 월 블록 부트스트랩 2,000회 seed 7).
E1: 코스피 R20 6칸(A2 ≤−10 · A1 · B · C · D1 · D2 >+10, buy_context 관례값) × 과매도 40일·전 종목 40일·초과.
E2: 코스피 20일 실현변동성(일수익 표준편차×√250) 5분위(전 신호일 기준) × 초과 · 칸 고정 비교.
출력: research/out_signal_board/tenyr_days.csv · e1_cells.csv · e2_vol.csv · e2b_vol_within_cell.csv · stdout."""
import os, sqlite3, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
OUT = HERE / "out_signal_board"; OUT.mkdir(exist_ok=True)
STEP = 5; SPLIT = "20210101"; H = 40; COST = 0.0035; rng = np.random.default_rng(7)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
pd.set_option("display.width", 240)


def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    if len(um) == 0:
        return (np.nan, np.nan)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5))


def diff_ci(a, b, k=2000):
    """두 집단(exc, month) 을 월 블록으로 각각 재표집한 평균 차이의 CI."""
    ua, ub = a.month.unique(), b.month.unique()
    ga = {u: a.exc[a.month == u].values for u in ua}; gb = {u: b.exc[b.month == u].values for u in ub}
    d = [np.concatenate([ga[u] for u in rng.choice(ua, len(ua))]).mean() - np.concatenate([gb[u] for u in rng.choice(ub, len(ub))]).mean() for _ in range(k)]
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def cell6(x):
    if x != x:
        return None
    for k, hi in (("A2", -10), ("A1", -5), ("B", 0), ("C", 5), ("D1", 10)):
        if x <= hi:
            return k
    return "D2"


t0 = time.time()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index()
con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
dates = list(close.index); N = len(dates); tick = list(close.columns)
ks_r20 = (ks / ks.shift(20) - 1).reindex(dates) * 100
ks_rv = (np.log(ks).diff().rolling(20).std() * np.sqrt(250)).reindex(dates) * 100
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, vol
tick = list(cu.columns)
dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
cf = cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()
r20 = cu / cu.shift(20) - 1
penny = cu < 1000
CF = cf.values; CU = cu.values; VU = vu.fillna(0).values; PEN = penny.fillna(True).values; R20 = r20.values
print(f"유니버스 {cu.shape[1]} 종목 · 날 {N} · {time.time()-t0:.0f}s")

rows = []
for i in range(130, N - H - 1, STEP):
    r = R20[i]
    v0 = (VU[i] == 0) | (VU[i + 1] == 0)
    e = CU[i + 1]; p40 = CF[i + 1 + H]
    ok = ~np.isnan(r) & ~v0 & ~PEN[i] & ~np.isnan(e) & (e > 0) & ~np.isnan(p40)
    if ok.sum() < 300:
        continue
    d = dates[i]
    thr = np.quantile(r[ok], 0.20); os_ = ok & (r <= thr)
    g = p40 / e - 1 - COST
    os40 = g[os_].mean() * 100; all40 = g[ok].mean() * 100
    rows.append(dict(date=d, month=d[:6], half=("앞" if d < SPLIT else "뒤"), r20=ks_r20.iloc[i], cell=cell6(ks_r20.iloc[i]), rv=ks_rv.iloc[i],
                     n_os=int(os_.sum()), os40=os40, all40=all40, exc=os40 - all40))
R = pd.DataFrame(rows); R = R[R.cell.notna() & R.rv.notna()].copy()
R["cell4"] = R.cell.map({"A2": "A", "A1": "A", "B": "B", "C": "C", "D1": "D", "D2": "D"})
R["vq"] = pd.qcut(R.rv, 5, labels=["Q1 낮음", "Q2", "Q3", "Q4", "Q5 높음"])
R.to_csv(OUT / "tenyr_days.csv", index=False, encoding="utf-8-sig")
print(f"신호일 {len(R)} · {time.time()-t0:.0f}s")


def summ(sub):
    lo, hi = block_ci(sub.exc, sub.month); mlo, mhi = block_ci(sub.all40, sub.month); olo, ohi = block_ci(sub.os40, sub.month)
    return dict(날수=len(sub), 월수=sub.month.nunique(), 과매도40=sub.os40.mean(), 과매도하한=olo, 과매도상한=ohi, 시장40=sub.all40.mean(), 시장하한=mlo, 시장상한=mhi,
                시장플러스비율=(sub.all40 > 0).mean() * 100, 초과=sub.exc.mean(), 초과하한=lo, 초과상한=hi, 초과양수비율=(sub.exc > 0).mean() * 100)


print("\n### E1 코스피 20일 등락 칸별 (11년 대리 · 과매도 = 20일 수익 하위 20% · 40일 · 비용 뒤)")
e1 = []
for scope, sub0 in (("전체", R), ("앞반 2015~20", R[R.half == "앞"]), ("뒤반 2021~", R[R.half == "뒤"])):
    for c in ["A2", "A1", "B", "C", "D1", "D2", "A", "D", "모두"]:
        sub = sub0 if c == "모두" else (sub0[sub0.cell4 == c] if c in ("A", "D") else sub0[sub0.cell == c])
        if len(sub) < 4:
            continue
        e1.append(dict(범위=scope, 칸=c, **summ(sub)))
E1 = pd.DataFrame(e1); E1.to_csv(OUT / "e1_cells.csv", index=False, encoding="utf-8-sig")
print(E1.round(2).to_string(index=False))

print("\n### E2 코스피 20일 실현변동성 5분위 × 초과 (전 신호일 기준 5분위)")
e2 = []
for scope, sub0 in (("전체", R), ("앞반 2015~20", R[R.half == "앞"]), ("뒤반 2021~", R[R.half == "뒤"])):
    for q in R.vq.cat.categories:
        sub = sub0[sub0.vq == q]
        if len(sub) < 4:
            continue
        e2.append(dict(범위=scope, 분위=str(q), 변동성평균=sub.rv.mean(), **summ(sub)))
    a, b = sub0[sub0.vq == "Q5 높음"], sub0[sub0.vq == "Q1 낮음"]
    if len(a) >= 4 and len(b) >= 4:
        lo, hi = diff_ci(a, b)
        e2.append(dict(범위=scope, 분위="Q5−Q1 차이", 변동성평균=np.nan, 날수=len(a) + len(b), 월수=np.nan, 초과=a.exc.mean() - b.exc.mean(), 초과하한=lo, 초과상한=hi))
E2 = pd.DataFrame(e2); E2.to_csv(OUT / "e2_vol.csv", index=False, encoding="utf-8-sig")
print(E2[["범위", "분위", "변동성평균", "날수", "과매도40", "시장40", "초과", "초과하한", "초과상한", "초과양수비율"]].round(2).to_string(index=False))

print("\n### E2-b 칸 고정: 같은 A~D 칸 안에서 변동성 상위 절반 − 하위 절반 (초과 %p)")
e2b = []
for c in ["A", "B", "C", "D"]:
    sub = R[R.cell4 == c]
    if len(sub) < 8:
        continue
    med = sub.rv.median(); hi_, lo_ = sub[sub.rv > med], sub[sub.rv <= med]
    dlo, dhi = diff_ci(hi_, lo_)
    e2b.append(dict(칸=c, 날수=len(sub), 변동성중앙=med, 상위초과=hi_.exc.mean(), 하위초과=lo_.exc.mean(), 차이=hi_.exc.mean() - lo_.exc.mean(), 차하한=dlo, 차상한=dhi))
E2b = pd.DataFrame(e2b); E2b.to_csv(OUT / "e2b_vol_within_cell.csv", index=False, encoding="utf-8-sig")
print(E2b.round(2).to_string(index=False))

print("\n### 칸 × 변동성 교차표 (날수)")
print(pd.crosstab(R.cell4, R.vq))
print(f"\n{time.time()-t0:.0f}s")
