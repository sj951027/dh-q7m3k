# -*- coding: utf-8 -*-
"""거래량 미수정 결함 대조 (2026-10-23 밤): 겹침 구간(2023-06~)에서 20일 거래대금을 10년 DB(수정가×원거래량) vs 운영 DB(원시가×원거래량)로
각각 계산해 ① 같은 날 순위 상관 ② 과매도 안 '아래 절반' 판정이 몇 % 갈리나 ③ 효과(아래 절반 − 과매도, 40일)가 어떻게 달라지나.
수익·과매도 판정은 둘 다 10년 DB(같은 값), 거래대금만 바꿔 끼운다. 운영 DB 는 19:58 스냅샷(pkl)을 읽는다(배치 중 DB 안 건드림)."""
import os, sqlite3
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; DATA = HERE.parent.parent / "dh-q7m3k-data"
DB = os.environ.get("OHLCV_10Y_DB", str(DATA / "ohlcv_10y.db")); SNAP = os.environ.get("OPS_SNAP")   # 스냅샷이 없으면 운영 DB 를 mode=ro 로(배치 시간 밖에서만)
H = 40; rng = np.random.default_rng(7)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', '부동산투자', '스팩']
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices WHERE date >= '20230501'", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker"); con.close()
if SNAP: op = pd.read_pickle(SNAP)
else:
    oc = sqlite3.connect(f"file:{DATA / 'ohlcv.db'}?mode=ro", uri=True); op = pd.read_sql("SELECT ticker, date, close, volume FROM daily_ohlcv", oc); oc.close()
c10 = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); c10 = c10.where(c10 > 0)
v10 = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(c10.index)
cop = op.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").reindex(index=c10.index, columns=c10.columns)
vop = op.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(index=c10.index, columns=c10.columns)
t = list(c10.columns); mk = meta.market.reindex(t); nm = meta.name.reindex(t).fillna("")
u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and k.endswith("0") and not any(w in n for w in FIN_KW) and "SPAC" not in n.upper() for k, m, n in zip(t, mk, nm)], index=t)
a10 = (c10 * v10).rolling(20, min_periods=10).mean(); aop = (cop * vop).rolling(20, min_periods=10).mean()
r20 = c10 / c10.shift(20) - 1
dl = meta.note.reindex(t).fillna("").str.contains("delisted"); cf = c10.copy(); cf.loc[:, dl.values] = cf.loc[:, dl.values].ffill()
fwd = (cf.shift(-1 - H) / c10.shift(-1) - 1) * 100
dates = list(c10.index); rows = []
vol_ratio = (v10 / vop).replace([np.inf, -np.inf], np.nan)
print(f"거래량 10년/운영 비율: 중앙 {np.nanmedian(vol_ratio.values):.3f} · 1% 넘게 다른 칸 {(np.abs(vol_ratio - 1) > 0.01).sum().sum()} / {vol_ratio.notna().sum().sum()}")
for i in range(40, len(dates) - H - 1, 5):
    a, b, r, f = a10.iloc[i], aop.iloc[i], r20.iloc[i], fwd.iloc[i]
    m = u & a.notna() & b.notna() & r.notna() & f.notna() & (c10.iloc[i] >= 1000)
    if m.sum() < 300: continue
    q05 = a[m].quantile(0.05); m = m & (a > q05)
    osd = m & (r <= r[m].quantile(0.20)); x1, x2 = a[osd], b[osd]
    lo1 = x1 <= x1.median(); lo2 = x2 <= x2.median(); om = f[osd].mean()
    rows.append(dict(date=dates[i], month=dates[i][:6], rho=x1.rank().corr(x2.rank()), disagree=float((lo1 != lo2).mean()),
                     eff10=float(f[osd][lo1].mean() - om), effop=float(f[osd][lo2].mean() - om), n=int(osd.sum())))
R = pd.DataFrame(rows)
def ci(v, mo, k=2000):
    um = np.unique(mo); by = {x: v[mo == x] for x in um}
    s = [np.concatenate([by[x] for x in rng.choice(um, len(um))]).mean() for _ in range(k)]; return np.percentile(s, [2.5, 97.5])
print(f"신호일 {len(R)} ({R.date.min()}~{R.date.max()}) · 과매도 중앙 {int(R.n.median())}")
print(f"과매도 안 거래대금 순위 상관(10년 vs 운영) 평균 {R.rho.mean():.4f} · 최소 {R.rho.min():.4f}")
print(f"'아래 절반' 판정이 갈리는 종목 비율 평균 {100*R.disagree.mean():.2f}% · 최대 {100*R.disagree.max():.2f}%")
for c_ in ("eff10", "effop"):
    lo, hi = ci(R[c_].values, R.month.values); print(f"아래 절반 − 과매도 ({'10년 DB 거래대금' if c_=='eff10' else '운영 DB(원시) 거래대금'}): {R[c_].mean():+.2f} [{lo:+.2f}, {hi:+.2f}]")
R.to_csv(HERE / "out_pick_amt" / "amt_raw_vs_adj_days.csv", index=False, encoding="utf-8-sig")
