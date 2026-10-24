# -*- coding: utf-8 -*-
"""ETF 슬리브(외부 조사 H7) 10년 검증 (2026-10-23, 사후 관측 · 채택 아님).
질문: 코스피 20일 수익 ≤ −5% 첫 진입(사건, 사건 사이 40거래일) 다음날 지수 ETF 를 사서 40거래일 들고 있으면 어떤가 —
  ① 사건 평균·플러스 수·최악·보유 중 최저점 ② 아무 날이나 샀을 때(무조건 40일)보다 나은가 ③ 같은 사건의 전 종목 동일가중 바구니와 비교
  ④ 매수 시점 두 가지(t+1 시가 ≈ 09:05 · t+1 종가) ⑤ 코스닥 사건엔 코스닥150 ETF ⑥ 앞반(~2020)·뒤반(2021~).
자료: ETF·KOSPI200 = FDR(NAVER) 일별 — 분배금 미반영 원가격(연 1.5~2% 배당 → 40일 ≈ +0.2~0.3%p 덜 잡힘, 보수적) ·
  신호 = 10년 DB index_daily(KOSPI·KOSDAQ) · 바구니 = 10년 DB 스크리너 유니버스(코넥스·우선주·금융/리츠/스팩 제외), 40일 안 상폐는 마지막 가격 청산.
구간 = 사건 단순 부트스트랩 4,000회 seed 7, 95%. 무조건 기준선 = 2015~ 모든 날 40일 수익 평균(겹침)."""
import os, sqlite3, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("DH_REPO", HERE.parent))
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
ETF = Path(os.environ.get("ETF_DIR", HERE / "out_etf_sleeve" / "etf_data"))   # FDR(NAVER) 2026-10-23 받은 사본
OUT = Path(os.environ.get("OUT_DIR", HERE / "out_etf_sleeve")); OUT.mkdir(exist_ok=True, parents=True)
H = 40; SPLIT = "20210101"; rng = np.random.default_rng(7); t0 = time.time()
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', '부동산투자', '스팩']


def boot(v, k=4000):
    v = np.asarray(v, float); v = v[~np.isnan(v)]
    if len(v) < 3: return (np.nan, np.nan)
    m = [rng.choice(v, len(v)).mean() for _ in range(k)]
    return (float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)))


def load_etf(nm):
    df = pd.read_csv(ETF / f"{nm}.csv", parse_dates=[0], index_col=0)
    df.index = df.index.strftime("%Y%m%d"); return df[["Open", "Close"]].astype(float)


con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
idx = pd.read_sql("SELECT series, date, close FROM index_daily", con).pivot(index="date", columns="series", values="close").sort_index()
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker"); con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
tick = list(close.columns); mk = meta.market.reindex(tick); nm_ = meta.name.reindex(tick).fillna("")
in_u = [(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and not any(k in n for k in FIN_KW) and "SPAC" not in n.upper() and "REIT" not in n.upper()
        for t, m, n in zip(tick, mk, nm_)]
close = close.loc[:, in_u]
dl = meta.note.reindex(close.columns).fillna("").str.contains("delisted")
cf = close.copy(); cf.loc[:, dl.values] = cf.loc[:, dl.values].ffill()
dates = [d for d in close.index if d in idx.index]
etfs = {k: load_etf(k) for k in ("KODEX200", "TIGER200", "KODEX_KQ150", "KOSPI200")}
cal = dates  # 거래일 달력 = 10년 DB(종목 시세) 날짜, ETF 는 그 날짜로 맞춤
pos = {d: i for i, d in enumerate(cal)}
print(f"바구니 유니버스 {close.shape[1]}종목 · 달력 {cal[0]}~{cal[-1]} {len(cal)}일 · {time.time()-t0:.0f}s")


def fwd(series_close, series_open, i, entry="close"):
    """신호일 위치 i → t+1 (시가|종가) 매수, t+41 종가 매도, 보유 중 최저 종가 수익."""
    if i + 1 + H >= len(cal): return (np.nan, np.nan)
    d1, d41 = cal[i + 1], cal[i + 1 + H]
    if d1 not in series_close.index or d41 not in series_close.index: return (np.nan, np.nan)
    e = series_open.get(d1, np.nan) if entry == "open" else series_close[d1]
    if not e or np.isnan(e): return (np.nan, np.nan)
    path = series_close.reindex(cal[i + 1:i + 2 + H]).dropna()
    return ((series_close[d41] / e - 1) * 100, (path.min() / e - 1) * 100)


def basket(i):
    if i + 1 + H >= len(cal): return np.nan
    a = close.loc[cal[i + 1]]; b = cf.loc[cal[i + 1 + H]]; ok = a.notna() & b.notna()
    return float(((b[ok] / a[ok] - 1) * 100).mean())


def events(series, thr=-0.05):
    s = idx[series].dropna(); r20 = (s / s.shift(20) - 1).reindex(cal); A = (r20 <= thr).fillna(False)   # 지수는 2014-11~ 이라 2015-01 사건도 잡힘
    ev = []; last = -10 ** 9
    for i in range(1, len(cal)):
        if A.iloc[i] and not A.iloc[i - 1] and i - last >= H: ev.append(i); last = i
    return ev, r20


rows = []
for mkt, series, etf_list in (("코스피", "KOSPI", ("KODEX200", "TIGER200", "KOSPI200")), ("코스닥", "KOSDAQ", ("KODEX_KQ150",))):
    ev, r20 = events(series)
    for i in ev:
        rec = dict(시장=mkt, 날짜=cal[i], R20=round(float(r20.iloc[i]) * 100, 1), 반=("앞" if cal[i] < SPLIT else "뒤"), 바구니=basket(i))
        for k in etf_list:
            c, o = etfs[k].Close, etfs[k].Open
            rec[f"{k}_종가"], rec[f"{k}_최저"] = fwd(c, o, i, "close")
            rec[f"{k}_시가"], _ = fwd(c, o, i, "open")
        rows.append(rec)
E = pd.DataFrame(rows); E.to_csv(OUT / "events.csv", index=False, encoding="utf-8-sig")

# 무조건 기준선(모든 날 t+1 종가 → t+41 종가)
base = {}
for k in ("KODEX200", "TIGER200", "KODEX_KQ150", "KOSPI200"):
    c = etfs[k].Close.reindex(cal); f = (c.shift(-1 - H) / c.shift(-1) - 1) * 100
    base[k] = (float(f.mean()), float((f > 0).mean() * 100), int(f.notna().sum()))
cb = close.reindex(cal); cfb = cf.reindex(cal)
bk_all = [basket(i) for i in range(0, len(cal) - H - 1, 5)]
base["바구니"] = (float(np.nanmean(bk_all)), float(np.mean(np.array(bk_all) > 0) * 100), len(bk_all))

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print("\n사건별:"); print(E.round(1).to_string(index=False))
out = []
for mkt, g in E.groupby("시장", sort=False):
    cols = ["바구니"] + [c for c in g.columns if c.endswith(("_종가", "_시가", "_최저"))]
    for scope, sub in (("전체", g), ("앞반", g[g.반 == "앞"]), ("뒤반", g[g.반 == "뒤"])):
        for c in cols:
            v = sub[c].dropna()
            if len(v) < 3: continue
            lo, hi = boot(v); k = c.split("_")[0] if c != "바구니" else "바구니"
            if c.startswith("KODEX_KQ150"): k = "KODEX_KQ150"
            b = base.get(k, (np.nan, np.nan, 0))
            out.append(dict(시장=mkt, 범위=scope, 항목=c, 사건=len(v), 평균=v.mean(), 하한=lo, 상한=hi, 플러스=f"{int((v > 0).sum())}/{len(v)}",
                            중앙=v.median(), 최악=v.min(), 무조건평균=b[0] if not c.endswith("_최저") else np.nan))
T = pd.DataFrame(out); T.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
print("\n요약:"); print(T.round(2).to_string(index=False))
# 바구니 − ETF 짝차이(같은 사건)
for mkt, etf in (("코스피", "KODEX200_종가"), ("코스닥", "KODEX_KQ150_종가")):
    g = E[E.시장 == mkt].dropna(subset=[etf]); d = g.바구니 - g[etf]; lo, hi = boot(d)
    print(f"{mkt} 바구니 − {etf}: {d.mean():+.2f} [{lo:+.2f}, {hi:+.2f}] · 바구니가 나은 사건 {int((d > 0).sum())}/{len(d)} · 사건 {len(d)}")
# 무조건 대비 초과의 구간: 사건 수익 − 무조건 평균(상수) → 같은 구간을 평균만 이동. 그래서 '사건 평균 vs 무조건 평균'을 겹침 포함 일별로도 본다
for k, series in (("KODEX200", "KOSPI"), ("KODEX_KQ150", "KOSDAQ")):
    c = etfs[k].Close.reindex(cal); f = (c.shift(-1 - H) / c.shift(-1) - 1) * 100
    s = idx[series].dropna(); r20 = ((s / s.shift(20) - 1) * 100).reindex(cal)
    bins = pd.cut(r20, [-99, -10, -5, 0, 5, 10, 99], labels=["≤−10", "−10~−5", "−5~0", "0~5", "5~10", ">10"])
    g = pd.DataFrame(dict(f=f, b=bins)).dropna().groupby("b", observed=True).f.agg(["count", "mean", lambda x: (x > 0).mean() * 100])
    g.columns = ["날수", "40일 평균", "플러스%"]; print(f"\n{k} — {series} R20 칸별(겹침 포함):"); print(g.round(2).to_string())
print("\n무조건 기준선(모든 날 40일):", {k: tuple(round(x, 2) for x in v) for k, v in base.items()})
# ETF 추종 확인: KODEX200 vs KOSPI200 지수 40일 수익 차이(분배금 미반영 효과)
c1 = etfs["KODEX200"].Close.reindex(cal); c2 = etfs["KOSPI200"].Close.reindex(cal)
dd = ((c1.shift(-41) / c1.shift(-1)) - (c2.shift(-41) / c2.shift(-1))) * 100
print(f"KODEX200 − KOSPI200 지수 40일 차이 평균 {dd.mean():+.2f}%p (중앙 {dd.median():+.2f})")
print(f"끝 {time.time()-t0:.0f}s")
