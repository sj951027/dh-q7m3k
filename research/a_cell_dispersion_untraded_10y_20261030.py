# -*- coding: utf-8 -*-
"""갈래 가 첫 실험 — A 칸(코스피 R20 ≤ −5%) 안에서 '종목 간 동반 하락 정도'(P15)와 '거래 끊긴 종목 비율'(P18)이
40일 바구니의 손실 집중·진입 가능성을 가르나 (2026-10-30 밤, 사후 관측 · 채택 아님 · Codex 아이디어 P15·P18 채택)

설계(결과 보기 전 고정):
  축 ① P15 동반 하락 = 과거 20일 일수익에서 동일가중 바구니 분산 / 종목 분산 평균 (평균 상관의 근사, 0~1). 창 60일은 감도.
  축 ② P18 거래 끊김 = 신호일 t 에 '살아 있는' 종목(최근 20일 안 양수 종가) 중 그날 거래량 0 또는 행 없음 비율.
  문턱 = 앞반(2015~2020) A 날의 각 축 중앙값 하나(학습구간 고정). 전체 중앙값은 감도. 연속값 순위상관은 보조.
  결과값(신호일 t → t+1 종가 매수 → t+41 종가 매도, 동일가중, 정리 유니버스 · 거래량 0 · 동전주 제외 · 상폐 = 마지막 가격):
    과매도(R20 하위 20%) 바구니 평균 · 전 종목 평균 · 과매도 안 −20% 이하 종목 비율(손실 집중) · 과매도 하위 10% 분위 ·
    진입 불가 비율 = 신호일엔 거래된 과매도 후보 중 t+1 거래량 0 비율(체결 가능성) · 코스피 40일.
  단위: A 날(5거래일 간격, 겹침) 월 블록 부트스트랩 2,000(seed 7) · A 사건(직전 사건과 ≥40거래일) 사건 부트스트랩 4,000(seed 20261030).
  그룹 차이에 구간을 붙인다(그룹 각각의 구간으로 판단하지 않음).
재현: python research/a_cell_dispersion_untraded_10y_20261030.py → research/out_a_cell_axes/ (약 1분)."""
import os, sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("DH_REPO", HERE.parent))
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
OUT = Path(os.environ.get("OUT_DIR", HERE / "out_a_cell_axes")); OUT.mkdir(exist_ok=True, parents=True)
H = 40; STEP = 5; SPLIT = "20210101"; A_TH = -5.0
rng = np.random.default_rng(7); rng_ev = np.random.default_rng(20261030)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
LOG = []


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


def block_diff_ci(df, col, grp, k=2000):
    """월 블록 부트스트랩: mean(col | grp=high) − mean(col | grp=low)."""
    d = df[[col, grp, "month"]].dropna(); um = d.month.unique()
    if len(um) < 2 or d[grp].nunique() < 2:
        return (np.nan, np.nan)
    by = {u: d[d.month == u] for u in um}; out = []
    for _ in range(k):
        s = pd.concat([by[u] for u in rng.choice(um, len(um))])
        hi, lo = s[s[grp] == "high"][col], s[s[grp] == "low"][col]
        if len(hi) and len(lo):
            out.append(hi.mean() - lo.mean())
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))) if out else (np.nan, np.nan)


def ev_diff_ci(df, col, grp, k=4000):
    """사건 부트스트랩(사건 복원추출): mean(high) − mean(low)."""
    d = df[[col, grp]].dropna(); out = []
    if d[grp].nunique() < 2:
        return (np.nan, np.nan)
    v = d[col].values; g = (d[grp] == "high").values; n = len(v)
    for _ in range(k):
        idx = rng_ev.integers(0, n, n); vv, gg = v[idx], g[idx]
        if gg.any() and (~gg).any():
            out.append(vv[gg].mean() - vv[~gg].mean())
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)))


def events_of(df):
    """A 날 중 직전 사건과 ≥H 거래일 떨어진 첫 날 = 사건."""
    keep = []; last = -10 ** 9
    for _, r in df.sort_values("i").iterrows():
        if r.i - last >= H:
            keep.append(r.name); last = r.i
    return df.loc[keep]


t0 = time.time()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index()
con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
dates = list(close.index); N = len(dates); tick = list(close.columns)
ks_r20 = ((ks / ks.shift(20) - 1) * 100).reindex(dates); ks_f40 = ((ks.shift(-1 - H) / ks.shift(-1) - 1) * 100).reindex(dates)
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, vol
tick = list(cu.columns)
dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
cf = cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()
fwd = (cf.shift(-1 - H) / cu.shift(-1) - 1) * 100; del cf
ret = cu.pct_change(fill_method=None)
r20 = cu / cu.shift(20) - 1
penny = cu < 1000
alive = cu.rolling(20, min_periods=1).max().notna()           # 최근 20일 안 양수 종가가 있었나
v0 = vu.fillna(0) == 0
say(f"유니버스 {cu.shape[1]} · 날 {N} · {time.time()-t0:.0f}s")


def avg_corr(i, w):
    """과거 w 일 창(끝 = i)의 동일가중 바구니 분산 / 종목 분산 평균 — 완전한 창이 있는 종목만."""
    R = ret.iloc[i - w + 1:i + 1]
    R = R.loc[:, R.notna().all() & (~penny.iloc[i].fillna(True))]
    if R.shape[1] < 200:
        return np.nan
    vi = R.var(ddof=1); vi = vi[vi > 0]
    if len(vi) < 200:
        return np.nan
    ew = R[vi.index].mean(axis=1).var(ddof=1)
    return float(ew / vi.mean())


rows = []
for i in range(130, N - H - 1, STEP):
    k = ks_r20.iloc[i]
    if k != k:
        continue
    f = fwd.iloc[i]; r = r20.iloc[i]; pn = penny.iloc[i].fillna(True)
    ok0 = f.notna() & r.notna() & ~pn & ~v0.iloc[i]                       # 신호일엔 거래됨(진입 가능 여부는 t+1 로 따로)
    ok = ok0 & ~v0.iloc[i + 1]                                           # 본 바구니: t+1 도 거래됨(기존 연구와 같음)
    if ok.sum() < 300:
        continue
    d = dates[i]
    os0 = ok0 & (r <= r[ok0].quantile(0.20))                             # 신호일 정보만으로 고른 과매도 후보
    os_ = ok & (r <= r[ok].quantile(0.20))
    fo = f[os_]
    al = alive.iloc[i]
    rows.append(dict(date=d, month=d[:6], i=i, half=("앞" if d < SPLIT else "뒤"), ks_r20=float(k), cell=("A" if k <= A_TH else ("D" if k > 5 else "BC")),
                     rho20=avg_corr(i, 20), rho60=avg_corr(i, 60), zero_share=float((v0.iloc[i] & al).sum() / max(1, al.sum())),
                     n_ok=int(ok.sum()), os_mean=float(fo.mean()), all_mean=float(f[ok].mean()), os_tail20=float((fo <= -20).mean()),
                     os_p10=float(fo.quantile(0.10)), os_pos=float((fo > 0).mean()),
                     untradable=float((v0.iloc[i + 1] & os0).sum() / max(1, os0.sum())), ks_f40=float(ks_f40.iloc[i])))
R = pd.DataFrame(rows); R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
say(f"신호일 {len(R)} · A 날 {(R.cell=='A').sum()} · {time.time()-t0:.0f}s")

# ── 0. 칸별 축 수준 (A 날이 다른 칸과 다른가 — 맥락)
say("\n== 0. 칸별 축 평균 [동반 하락 rho20 · rho60 · 거래 끊김 비율 · 진입 불가 비율] ==")
say(R.groupby("cell")[["rho20", "rho60", "zero_share", "untradable", "os_mean", "all_mean", "os_tail20"]].mean().round(3).to_string())

A = R[R.cell == "A"].copy()
OUTC = ["os_mean", "all_mean", "os_tail20", "os_p10", "os_pos", "untradable", "ks_f40"]
th = {}
for ax in ["rho20", "zero_share"]:
    th[ax] = dict(front=float(A[A.half == "앞"][ax].median()), full=float(A[ax].median()))
say("\n문턱(중앙값): " + " · ".join(f"{ax} 앞반 {v['front']:.3f} / 전체 {v['full']:.3f}" for ax, v in th.items()))


def group_table(df, ax, thv, label, unit):
    df = df.copy(); df["g"] = np.where(df[ax] > thv, "high", "low")
    n_hi, n_lo = int((df.g == "high").sum()), int((df.g == "low").sum())
    lines = [f"\n-- {label} · 축 {ax} · 문턱 {thv:.3f} · high {n_hi} / low {n_lo} --",
             f"{'결과값':<12}{'high':>9}{'low':>9}{'차이':>9}  95%"]
    for c in OUTC:
        hi, lo = df[df.g == "high"][c].mean(), df[df.g == "low"][c].mean()
        ci = block_diff_ci(df, c, "g") if unit == "day" else ev_diff_ci(df, c, "g")
        lines.append(f"{c:<12}{hi:>9.2f}{lo:>9.2f}{hi-lo:>9.2f}  [{ci[0]:+.2f}, {ci[1]:+.2f}]")
    say("\n".join(lines))
    return df


# ── 1. A 날(겹침) — 앞반 문턱(본문) · 전체 문턱(감도)
say("\n== 1. A 날 단위(5거래일 간격, 겹침, 월 블록 부트스트랩) ==")
for ax in ["rho20", "zero_share"]:
    group_table(A, ax, th[ax]["front"], "A 날 · 앞반 문턱(본문)", "day")
    group_table(A, ax, th[ax]["full"], "A 날 · 전체 문턱(감도)", "day")
say("\n[감도] rho60 앞반 문턱:")
th60 = float(A[A.half == "앞"]["rho60"].median()); group_table(A, "rho60", th60, "A 날 · rho60", "day")

# ── 2. A 사건 단위
E = events_of(A)
say(f"\n== 2. A 사건 단위(직전 사건과 ≥{H} 거래일) — 사건 {len(E)} ==")
for ax in ["rho20", "zero_share"]:
    g = group_table(E, ax, th[ax]["front"], "A 사건 · 앞반 문턱(본문)", "event")
    say(g[["date", "ks_r20", ax, "g", "os_mean", "all_mean", "os_tail20", "untradable", "ks_f40"]].round(3).to_string(index=False))
E.to_csv(OUT / "events.csv", index=False, encoding="utf-8-sig")

# ── 3. 연속값 순위상관(보조) — A 날·A 사건
say("\n== 3. 순위상관(Spearman, 보조) — 축 ↔ 결과값 ==")
for name, df in [("A 날", A), ("A 사건", E)]:
    for ax in ["rho20", "zero_share"]:
        s = " · ".join(f"{c} {df[[ax, c]].corr(method='spearman').iloc[0, 1]:+.2f}" for c in ["os_mean", "os_tail20", "untradable", "ks_f40"])
        say(f"{name:<5} {ax:<11} n={len(df):<4} {s}")

# ── 4. 두 축의 관계·깊이와의 관계(중복 점검)
say("\n== 4. 축끼리·깊이와의 순위상관(A 날) ==")
say(A[["rho20", "zero_share", "ks_r20"]].corr(method="spearman").round(2).to_string())

# ── 5. 전 기간(모든 칸) 참고: 축 고저가 과매도 바구니를 가르나
say("\n== 5. 참고 — 모든 칸 신호일에서 같은 문턱 ==")
for ax in ["rho20", "zero_share"]:
    group_table(R, ax, th[ax]["front"], "전체 날", "day")

(OUT / "run_20261030.txt").write_text("\n".join(LOG), encoding="utf-8")
say(f"\n끝 {time.time()-t0:.0f}s → {OUT}")
