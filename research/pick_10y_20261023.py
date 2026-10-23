# -*- coding: utf-8 -*-
"""무엇을 고르나 — 10년 재검증 (2026-10-23, 사후 관측 · 채택 아님). 10년 DB(ohlcv_10y.db, 2015~, 폐지 포함·수정주가)만 읽는다.

A) 과매도 유니버스 정의 두 가지의 40일 바구니(동일가중, t+1 매수 → t+41 매도):
   원시 = 20일 수익 하위 20% · 업종 잔차 = (20일 수익 − 같은 업종 중앙값) 하위 20% (업종 = sector_cache.json, 없는 종목 '미분류' 한 묶음)
   → 각각 '전 종목' 대비 초과(%p), 두 정의의 짝차이(같은 날), 겹치는 종목 비율. 코스피 급락(A) 날 / 그 밖 / 앞반(2015~2020)·뒤반(2021~).
B) 원시 과매도 안에서 2차 기준 5분위 Q5−Q1 (10/20 넓은 훑기의 '남은 후보' 재검증): 거래량 급증(5일/60일) · 60일 변동성 · 20일 거래대금 · 120일 수익.
신호일 5거래일 간격. 구간 = 월 블록 부트스트랩 2,000회 seed 7, 95%. 출력 research/out_pick_10y/*.csv + 표준출력."""
import json, sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO)); import regime_ad
OUT = HERE / "out_pick_10y"; OUT.mkdir(exist_ok=True)
H = 40; STEP = 5; Q = 5; SPLIT = "20210101"; rng = np.random.default_rng(7)


def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); um = np.unique(months)
    if len(um) < 2 or len(vals) < 2: return (np.nan, np.nan)
    by = {m: vals[months == m] for m in um}
    ms = [np.concatenate([by[m] for m in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


def nonov(pos, gap=H):
    c = 0; last = -10 ** 9
    for p in sorted(pos):
        if p - last >= gap: c += 1; last = p
    return c


t0 = time.time()
con = sqlite3.connect(f"file:{regime_ad.HIST_DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con); con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index)
dates = list(close.index); N = len(dates)
sec = json.loads((REPO / "sector_cache.json").read_text(encoding="utf-8"))
secs = pd.Series({t: sec.get(t, "미분류") for t in close.columns})
ks = regime_ad.load_index_long("KOSPI"); ks_r20 = (ks / ks.shift(20) - 1).reindex(dates)
ret = close.pct_change(fill_method=None)
r20 = close / close.shift(20) - 1; r120 = close / close.shift(120) - 1
vol60 = ret.rolling(60, min_periods=40).std(); amt20 = (close * vol).rolling(20, min_periods=10).mean()
vsurge = vol.rolling(5, min_periods=3).mean() / vol.rolling(60, min_periods=30).mean()
fwd40 = (close.shift(-1 - H) / close.shift(-1) - 1) * 100
print(f"close {close.shape} · 업종 있는 종목 {(secs != '미분류').sum()} / {len(secs)} · {time.time()-t0:.0f}s")

rowsA, rowsB = [], []
for i in range(130, N - H - 1, STEP):
    f = fwd40.iloc[i]; r = r20.iloc[i]; ok = f.notna() & r.notna()
    if ok.sum() < 300: continue
    d = dates[i]; A = bool(ks_r20.iloc[i] == ks_r20.iloc[i] and ks_r20.iloc[i] <= -0.05)
    allm = float(f[ok].mean())
    raw = ok & (r <= r[ok].quantile(0.20))
    rel = r - r.groupby(secs.reindex(r.index)).transform("median")
    res = ok & rel.notna() & (rel <= rel[ok & rel.notna()].quantile(0.20))
    rowsA.append(dict(date=d, month=d[:6], i=i, A=A, half=("앞" if d < SPLIT else "뒤"), all=allm, raw=float(f[raw].mean()), res=float(f[res].mean()),
                      n_raw=int(raw.sum()), n_res=int(res.sum()), overlap=float((raw & res).sum() / max(1, raw.sum()))))
    # B) 원시 과매도 안 5분위
    for nm, F, hi_good in (("거래량 급증(5일/60일)", vsurge, True), ("60일 변동성(낮을수록)", vol60, False), ("20일 거래대금(적을수록)", amt20, False), ("120일 수익(낮을수록)", r120, False)):
        x = F.iloc[i][raw].replace([np.inf, -np.inf], np.nan).dropna()
        if len(x) < 60 or x.nunique() < Q: continue
        q = pd.qcut(x.rank(method="first"), Q, labels=False); g = f[x.index].groupby(q.values).mean()
        if 0 not in g.index or Q - 1 not in g.index: continue
        spread = (g[Q - 1] - g[0]) if hi_good else (g[0] - g[Q - 1])      # '좋다고 본 쪽' − 반대쪽
        rowsB.append(dict(date=d, month=d[:6], i=i, A=A, half=("앞" if d < SPLIT else "뒤"), feat=nm, spread=spread, n=int(len(x))))
RA = pd.DataFrame(rowsA); RB = pd.DataFrame(rowsB)
RA.to_csv(OUT / "A_days.csv", index=False, encoding="utf-8-sig"); RB.to_csv(OUT / "B_days.csv", index=False, encoding="utf-8-sig")
print(f"신호일 {len(RA)} · 비겹침 {nonov(RA.i)} · {time.time()-t0:.0f}s")

print("\nA) 과매도 유니버스 — 전 종목 대비 초과(%p)와 두 정의의 짝차이")
out = []
for scope, sub in (("전체", RA), ("코스피 급락 날", RA[RA.A]), ("그 밖", RA[~RA.A]), ("앞반 2015~20", RA[RA.half == "앞"]), ("뒤반 2021~", RA[RA.half == "뒤"])):
    if len(sub) < 8: continue
    e1 = sub.raw - sub["all"]; e2 = sub.res - sub["all"]; dd = sub.res - sub.raw
    out.append(dict(범위=scope, 날수=len(sub), 비겹침=nonov(sub.i), 전종목=sub["all"].mean(), 원시과매도=sub.raw.mean(), 원시초과=e1.mean(), 원시초과_CI=block_ci(e1, sub.month),
                    업종잔차=sub.res.mean(), 잔차초과=e2.mean(), 잔차초과_CI=block_ci(e2, sub.month), 잔차_원시_짝차이=dd.mean(), 짝차이_CI=block_ci(dd, sub.month), 양수비율=(dd > 0).mean(), 겹침=sub.overlap.mean()))
TA = pd.DataFrame(out); pd.set_option("display.width", 260); print(TA.round(2).to_string(index=False)); TA.to_csv(OUT / "A_summary.csv", index=False, encoding="utf-8-sig")

print("\nB) 원시 과매도 안 2차 기준 — '좋다고 본 쪽' Q − 반대 Q (40일 %p)")
out = []
for (nm), g in RB.groupby("feat"):
    for scope, sub in (("전체", g), ("코스피 급락 날", g[g.A]), ("그 밖", g[~g.A])):
        if len(sub) < 8: continue
        lo, hi = block_ci(sub.spread, sub.month); fr, bk = sub[sub.half == "앞"], sub[sub.half == "뒤"]
        out.append(dict(기준=nm, 범위=scope, 날수=len(sub), 비겹침=nonov(sub.i), 차이=sub.spread.mean(), 하한=lo, 상한=hi, 양수비율=(sub.spread > 0).mean(),
                        앞반=fr.spread.mean() if len(fr) else np.nan, 뒤반=bk.spread.mean() if len(bk) else np.nan))
TB = pd.DataFrame(out); print(TB.round(2).to_string(index=False)); TB.to_csv(OUT / "B_summary.csv", index=False, encoding="utf-8-sig")
print(f"\n끝 {time.time()-t0:.0f}s")
