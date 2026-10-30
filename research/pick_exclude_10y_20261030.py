# -*- coding: utf-8 -*-
"""과매도 후보에서 '무엇을 빼면' 나아지나 — 외부 조사 카드 A1(상·하한가 도달)·A2(복권형 고변동) 10년 검증 (2026-10-30, 사후 관측 · 채택 아님)

10년 DB(ohlcv_10y.db, 2015~, 폐지 포함·수정주가)만 읽는다. 10/23 `pick_10y_20261023.py`·`pick_amt_recheck_20261023.py` 와 같은 틀:
  유니버스 = 스크리너와 같게(코스피·코스닥 보통주, 금융/리츠/스팩 제외) · 신호일·매수일 거래량 0 제외 · 동전주(<1,000원) 제외
  · 40일 안 상폐 = 마지막 가격(+ −90% 감도) · 신호일 5거래일 간격 · t+1 종가 매수 → t+41 종가 매도 · 동일가중.
과매도 = 그날 유니버스 안 20일 수익 하위 20%(v30 대리). 제외 후보(그날 알 수 있는 것만):
  A1  지난 20거래일 안 상한가 또는 하한가 마감이 있는 종목(일수익 ≥ +29.5% / ≤ −29.5%, 2015-06-15 전은 ±14.5%)
  A1a 하한가만 · A1b 상한가만
  A2  지난 20거래일 최대 일수익이 유니버스 상위 10%('복권형')
  A2b 지난 20거래일 최대 일수익이 과매도 안 상위 20%
주지표 D = (과매도 − 제외군 평균 수익) − (과매도 전체 평균 수익) [%p, 신호일 평균] — 챌린저가 v30 대리 위에 얹을 몫.
  보조: 제외군 수익 − 유지군 수익(제외한 종목이 실제로 나빴나) · 제외 비율. 구간 = 월 블록 부트스트랩 2,000회 seed 7.
나눠 보기: 전체 / 코스피 급락 날(R20 ≤ −5%) / 그 밖 / 앞반(~2020)·뒤반(2021~).
재현: python research/pick_exclude_10y_20261030.py → research/out_pick_exclude/*.csv (약 1분)."""
import os, sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("DH_REPO", HERE.parent))
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
OUT = Path(os.environ.get("OUT_DIR", HERE / "out_pick_exclude")); OUT.mkdir(exist_ok=True, parents=True)
H = 40; STEP = 5; SPLIT = "20210101"; LIMIT_DATE = "20150615"; rng = np.random.default_rng(7)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)


def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    if len(um) < 2 or len(vals) < 2:
        return (np.nan, np.nan)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


def nonov(pos, gap=H):
    c = 0; last = -10 ** 9
    for p in sorted(pos):
        if p - last >= gap:
            c += 1; last = p
    return c


t0 = time.time()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index()
con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
dates = list(close.index); N = len(dates); tick = list(close.columns)
ks_r20 = (ks / ks.shift(20) - 1).reindex(dates)

mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, vol
tick = list(cu.columns)
dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
cf = cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()
fwd = (cf.shift(-1 - H) / cu.shift(-1) - 1) * 100                      # 상폐 = 마지막 가격
lp = np.array([np.where(cu.iloc[:, j].notna())[0].max() if cu.iloc[:, j].notna().any() else -1 for j in range(cu.shape[1])])
P = np.arange(N)[:, None]; hit = dl[None, :] & (lp[None, :] >= P + 1) & (lp[None, :] < P + 1 + H)
fwd90 = fwd.where(~hit, -90.0); del cf, hit
ret = cu.pct_change(fill_method=None)
r20 = cu / cu.shift(20) - 1
lim = pd.Series([0.295 if d >= LIMIT_DATE else 0.145 for d in dates], index=dates)
up20 = (ret.ge(lim, axis=0)).astype(float).rolling(20, min_periods=1).max() > 0      # 지난 20일(오늘 포함) 상한가 마감 있음
dn20 = (ret.le(-lim, axis=0)).astype(float).rolling(20, min_periods=1).max() > 0     # 하한가 마감 있음
max20 = ret.rolling(20, min_periods=10).max()
penny = cu < 1000
print(f"유니버스 {cu.shape[1]} 종목 · 날 {N} · {time.time()-t0:.0f}s")

FILTERS = ["A1 상·하한가 20일 안 도달", "A1a 하한가만", "A1b 상한가만", "A2 복권형(20일 최대 일수익 유니버스 상위 10%)", "A2b 복권형(과매도 안 상위 20%)"]
rows = []
for i in range(130, N - H - 1, STEP):
    f = fwd.iloc[i]; f90 = fwd90.iloc[i]; r = r20.iloc[i]
    v0 = (vu.iloc[i].fillna(0) == 0) | (vu.iloc[i + 1].fillna(0) == 0)
    ok = f.notna() & r.notna() & ~v0 & ~penny.iloc[i].fillna(True)
    if ok.sum() < 300:
        continue
    d = dates[i]; A = bool(ks_r20.iloc[i] == ks_r20.iloc[i] and ks_r20.iloc[i] <= -0.05)
    os_ = ok & (r <= r[ok].quantile(0.20))
    base, base90, n_os = float(f[os_].mean()), float(f90[os_].mean()), int(os_.sum())
    mx = max20.iloc[i]
    ex = {
        FILTERS[0]: (up20.iloc[i] | dn20.iloc[i]),
        FILTERS[1]: dn20.iloc[i],
        FILTERS[2]: up20.iloc[i],
        FILTERS[3]: mx >= mx[ok].quantile(0.90),
        FILTERS[4]: mx >= mx[os_].quantile(0.80),
    }
    for name, e in ex.items():
        e = e.fillna(False)
        keep = os_ & ~e; drop = os_ & e
        if keep.sum() < 30:
            continue
        rows.append(dict(date=d, month=d[:6], i=i, A=A, half=("앞" if d < SPLIT else "뒤"), filt=name, n_os=n_os, share=float(drop.sum() / n_os),
                         D=float(f[keep].mean() - base), D90=float(f90[keep].mean() - base90),
                         drop_minus_keep=(float(f[drop].mean() - f[keep].mean()) if drop.sum() >= 3 else np.nan),
                         base=base, keep_ret=float(f[keep].mean()), all_ret=float(f[ok].mean())))
R = pd.DataFrame(rows); R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
print(f"신호일 {R.date.nunique()} · 비겹침 {nonov(R.i.unique())} · {time.time()-t0:.0f}s")

out = []
for name in FILTERS:
    g = R[R.filt == name]
    for scope, sub in (("전체", g), ("코스피 급락 날", g[g.A]), ("그 밖", g[~g.A]), ("앞반 2015~20", g[g.half == "앞"]), ("뒤반 2021~", g[g.half == "뒤"])):
        if len(sub) < 8:
            continue
        lo, hi = block_ci(sub.D, sub.month)
        out.append(dict(제외후보=name, 범위=scope, 날수=len(sub), 비겹침=nonov(sub.i), 제외비율=sub.share.mean() * 100, 과매도전체=sub.base.mean(), 제외뒤=sub.keep_ret.mean(),
                        D=sub.D.mean(), 하한=lo, 상한=hi, 양수비율=(sub.D > 0).mean() * 100, D_상폐m90=sub.D90.mean(), 제외군_유지군=sub.drop_minus_keep.mean(), 전종목=sub.all_ret.mean()))
T = pd.DataFrame(out)
print("\n과매도(20일 수익 하위 20%) 안에서 후보를 뺐을 때 — D = 제외 뒤 − 과매도 전체 (40일 %p, 신호일 평균)")
print(T.round(2).to_string(index=False)); T.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
print(f"\n끝 {time.time()-t0:.0f}s")
