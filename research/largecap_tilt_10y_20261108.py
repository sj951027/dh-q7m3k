# -*- coding: utf-8 -*-
"""대형주 쏠림 — 코스피 지수(시총 가중) R20 − 코스피 종목 동일가중 R20 격차 × 과매도 초과 (2026-11-08 저녁, 읽기 전용 · 지도 P4 대리). LARGECAP_TILT_20261108.md §0.

틀은 `signal_board_10y_20261108.py` 그대로. 쏠림 낮음(더 음수) = 대형주 쏠림, 높음 = 골고루.
본검정: 코스피 R20 ≤ −5 신호일을 쏠림 중앙값으로 하/상 절반 → 차이(하−상)·월 블록 CI·앞/뒤반 부호·A1 고정 부호.
출력: research/out_largecap_tilt/days.csv · main.csv · ref.csv · stdout."""
import os, sqlite3, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
OUT = HERE / "out_largecap_tilt"; OUT.mkdir(exist_ok=True)
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
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, vol
tick = list(cu.columns)
dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
is_kospi = (meta.market.reindex(tick) == "KOSPI").values
cf = cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()
r20 = cu / cu.shift(20) - 1
penny = cu < 1000
CF = cf.values; CU = cu.values; VU = vu.fillna(0).values; PEN = penny.fillna(True).values; R20 = r20.values
print(f"유니버스 {cu.shape[1]} 종목(코스피 {is_kospi.sum()}) · 날 {N} · {time.time()-t0:.0f}s")

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
    kv = ~np.isnan(r) & ~PEN[i] & is_kospi
    ew_k = r[kv].mean() * 100 if kv.sum() >= 100 else np.nan
    kr = ks_r20.iloc[i]
    rows.append(dict(date=d, month=d[:6], half=("앞" if d < SPLIT else "뒤"), r20=kr, cell=cell6(kr), ew_kospi=ew_k, n_kospi=int(kv.sum()),
                     tilt=kr - ew_k, n_os=int(os_.sum()), os40=os40, all40=all40, exc=os40 - all40))
R = pd.DataFrame(rows); R = R[R.cell.notna() & R.tilt.notna()].copy()
R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
print(f"신호일 {len(R)} · 코스피 종목 수 중앙 {R.n_kospi.median():.0f} · 쏠림 중앙 {R.tilt.median():.2f} · {time.time()-t0:.0f}s")


def split_test(sub, label):
    """쏠림 중앙값으로 하위(쏠림)/상위(골고루) 절반 → 차이(하−상)."""
    med = sub.tilt.median(); lo_ = sub[sub.tilt <= med]; hi_ = sub[sub.tilt > med]
    out = dict(표=label, 날수=len(sub), 월수=sub.month.nunique(), 중앙값=med, 쏠림날수=len(lo_), 골고루날수=len(hi_))
    if len(hi_) == 0 or len(lo_) == 0:
        return out
    ll, lh = block_ci(lo_.exc, lo_.month); hl, hh = block_ci(hi_.exc, hi_.month); dlo, dhi = diff_ci(lo_, hi_)
    out.update(쏠림초과=lo_.exc.mean(), 쏠림하한=ll, 쏠림상한=lh, 쏠림과매도40=lo_.os40.mean(), 쏠림시장40=lo_.all40.mean(), 쏠림평균값=lo_.tilt.mean(),
               골고루초과=hi_.exc.mean(), 골고루하한=hl, 골고루상한=hh, 골고루과매도40=hi_.os40.mean(), 골고루시장40=hi_.all40.mean(), 골고루평균값=hi_.tilt.mean(),
               차이=lo_.exc.mean() - hi_.exc.mean(), 차하한=dlo, 차상한=dhi)
    for h in ("앞", "뒤"):
        a, b = lo_[lo_.half == h], hi_[hi_.half == h]
        out[f"{h}반쏠림날수"] = len(a); out[f"{h}반골고루날수"] = len(b)
        out[f"{h}반차이"] = (a.exc.mean() - b.exc.mean()) if len(a) and len(b) else np.nan
    a1 = sub[sub.r20 > -10]
    if len(a1) >= 8:
        m1 = a1.tilt.median(); l1, h1 = a1[a1.tilt <= m1], a1[a1.tilt > m1]
        d1lo, d1hi = diff_ci(l1, h1)
        out.update(A1날수=len(a1), A1차이=l1.exc.mean() - h1.exc.mean(), A1차하한=d1lo, A1차상한=d1hi)
    else:
        out.update(A1날수=len(a1), A1차이=np.nan, A1차하한=np.nan, A1차상한=np.nan)
    sg = np.sign(out["차이"])
    out["CI_0제외"] = bool(dlo > 0 or dhi < 0)
    out["앞뒤부호일치"] = bool(np.sign(out["앞반차이"]) == sg == np.sign(out["뒤반차이"])) if out["앞반차이"] == out["앞반차이"] and out["뒤반차이"] == out["뒤반차이"] else False
    out["A1부호일치"] = bool(np.sign(out["A1차이"]) == sg) if out["A1차이"] == out["A1차이"] else False
    out["절반≥20"] = bool(len(hi_) >= 20 and len(lo_) >= 20)
    out["통과"] = bool(out["CI_0제외"] and out["앞뒤부호일치"] and out["A1부호일치"] and out["절반≥20"])
    out["순위상관_쏠림vs초과"] = sub[["tilt", "exc"]].corr(method="spearman").iloc[0, 1]
    out["순위상관_쏠림vsR20"] = sub[["tilt", "r20"]].corr(method="spearman").iloc[0, 1]
    return out


A = R[R.r20 <= -5]
print("\n### 본검정 — 코스피 R20 ≤ −5 신호일 · 쏠림(지수 R20 − 코스피 종목 동일가중 R20) 하위 절반(대형주 쏠림) − 상위 절반(골고루) · 초과 %p")
main = pd.DataFrame([split_test(A, "본검정 R20≤−5")])
main.to_csv(OUT / "main.csv", index=False, encoding="utf-8-sig")
print(main.T.to_string())
print("\n본검정 신호일 목록:")
print(A[["date", "r20", "ew_kospi", "tilt", "os40", "all40", "exc"]].round(2).to_string(index=False))

print("\n### 참고표 (판정 밖)")
ref = pd.DataFrame([split_test(R[R.r20 <= 0], "(c) R20≤0"), split_test(R, "(참고) 전 신호일")])
ref.to_csv(OUT / "ref.csv", index=False, encoding="utf-8-sig")
print(ref.T.to_string())
print("\n(a) 전 신호일 쏠림 5분위 × 초과")
R["tq"] = pd.qcut(R.tilt, 5, labels=["Q1 쏠림", "Q2", "Q3", "Q4", "Q5 골고루"])
qa = []
for q in R.tq.cat.categories:
    sub = R[R.tq == q]; lo, hi = block_ci(sub.exc, sub.month)
    qa.append(dict(분위=str(q), 날수=len(sub), 쏠림평균=sub.tilt.mean(), R20평균=sub.r20.mean(), 과매도40=sub.os40.mean(), 시장40=sub.all40.mean(), 초과=sub.exc.mean(), 하한=lo, 상한=hi))
QA = pd.DataFrame(qa); QA.to_csv(OUT / "quintiles.csv", index=False, encoding="utf-8-sig"); print(QA.round(2).to_string(index=False))
print("\n칸별 쏠림 중앙값:"); print(R.groupby("cell").agg(날수=("tilt", "size"), 쏠림중앙=("tilt", "median"), 초과평균=("exc", "mean")).round(2))
print(f"\n{time.time()-t0:.0f}s")
