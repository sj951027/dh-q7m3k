# -*- coding: utf-8 -*-
"""첫 주 상승 예측 변수 전수 스캔 — 11년 대리(B 표본) (2026-11-08, 탐색·읽기 전용 · 채택 아님). 틀: research/EARLY_RISE_SCAN_20261108.md §0.

10년 DB(ohlcv_10y.db, 2015~, 폐지 포함·수정주가, OHLCV)만 읽는다. 유니버스·과매도 대리(20일 수익 하위 20%)·신호일 5거래일 간격·거래량 0·동전주 제외·상폐 ffill 은
pick_exec_hold_10y_20261030.py 와 같다. 신호일 t 는 인덱스 260 부터(200일 SMA·52주 창) N−42 까지.
변수(t 기준, §0-3 B): rsi14(단순평균) · r1 · r5 · r20 · r60 · vs_sma20/50/200 · dd_52w_high · dist_52w_low · vol5_vol60 · volt_vol20 · rv20 · range_t · above_sma5 · rebound3(r1≥3%)
 · accel(= r5 − r20/4; r5/r20 비는 r20≈0 에서 불안정해 차로 대체) · log_amount · dist_20d_low · down_streak.
목표(진입 t+1 종가, 시장 = 그날 ok 전 종목 동일가중): T1 5일 초과(%p) · T2 성공 = 5일째 비용 0.5% 뒤 > 0 and c[t+21] > c[t+6] · T3 20일 초과 · T4 40일 초과.
날짜별(과매도 안, n≥50) 스피어만 IC + 상위20%−하위20% 차이 → 날짜 평균, 월 블록 부트스트랩 4,000회 seed 7(95% 와 Bonferroni 1−0.05/(2M)).
출력 research/out_early_rise_scan/tenyr_summary.csv · tenyr_stdout.txt. 실행 약 2~4분."""
import os, sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
OUT = HERE / "out_early_rise_scan"; OUT.mkdir(exist_ok=True)
STEP = 5; SPLIT = "20210101"; COST = 0.005; NB = 4000; MIN_N = 50
rng = np.random.default_rng(7)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)

t0 = time.time()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, high, low, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
high = px.pivot_table(index="date", columns="ticker", values="high", aggfunc="last").reindex(close.index)
low = px.pivot_table(index="date", columns="ticker", values="low", aggfunc="last").reindex(close.index)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
dates = list(close.index); N = len(dates); tick = list(close.columns)
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; hu = high.loc[:, in_u.values]; lu = low.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, high, low, vol
tick = list(cu.columns)
dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
cf = cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()
print(f"유니버스 {cu.shape[1]} 종목 · 날 {N} ({dates[0]}~{dates[-1]}) · {time.time()-t0:.0f}s")

sig = list(range(260, N - 42, STEP))
S = np.array(sig)

def at(df):  # 신호일 행만 (float32 절약)
    return df.values[S].astype(np.float32)

# ---- 변수(신호일 행만 보관) ----
ret = cu.pct_change(fill_method=None)
V = {}
V["r1"] = at(ret * 100)
V["r5"] = at((cu / cu.shift(5) - 1) * 100)
r20 = (cu / cu.shift(20) - 1) * 100; V["r20"] = at(r20)
V["r60"] = at((cu / cu.shift(60) - 1) * 100)
sma5 = cu.rolling(5).mean(); V["above_sma5"] = at((cu > sma5).astype(float).where(cu.notna() & sma5.notna())); del sma5
for w in (20, 50, 200):
    s = cu.rolling(w).mean(); V[f"vs_sma{w}"] = at((cu / s - 1) * 100); del s
hi52 = cu.rolling(250, min_periods=120).max(); V["dd_52w_high"] = at((cu / hi52 - 1) * 100); del hi52
lo52 = cu.rolling(250, min_periods=120).min(); V["dist_52w_low"] = at((cu / lo52 - 1) * 100); del lo52
lo20 = cu.rolling(20).min(); V["dist_20d_low"] = at((cu / lo20 - 1) * 100); del lo20
v5 = vu.rolling(5).mean(); v60 = vu.rolling(60).mean(); V["vol5_vol60"] = at(v5 / v60.where(v60 > 0)); del v5, v60
v20 = vu.rolling(20).mean(); V["volt_vol20"] = at(vu / v20.where(v20 > 0)); del v20
V["rv20"] = at(ret.rolling(20).std() * 100)
V["range_t"] = at(((hu - lu) / cu * 100).where(hu.notna() & lu.notna())); del hu, lu
V["rebound3"] = at((ret * 100 >= 3).astype(float).where(ret.notna()))
V["accel"] = V["r5"] - V["r20"] / 4
V["log_amount"] = at(np.log1p(cu * vu))
# RSI14(단순평균)
d = cu.diff(); up = d.clip(lower=0).rolling(14).mean(); dn = (-d.clip(upper=0)).rolling(14).mean()
V["rsi14"] = at(100 - 100 / (1 + up / dn.where(dn > 0))); del d, up, dn
# 하락 연속일수(t 포함, 종가 기준)
neg = (ret < 0).values
streak = np.zeros(ret.shape, dtype=np.int16)
for i in range(1, N):
    streak[i] = np.where(neg[i], streak[i - 1] + 1, 0)
V["down_streak"] = streak[S].astype(np.float32); del streak, neg
VARS = list(V.keys()); M = len(VARS)
print(f"변수 {M}개: {VARS} · {time.time()-t0:.0f}s")

CU = cu.values; CF = cf.values; VU = vu.fillna(0).values; R20 = r20.values; PEN = (cu < 1000).fillna(True).values
del ret, r20

def spearman_cols(X, y):
    """X: (n, M) 변수(NaN 허용), y: (n,) 목표 → 변수별 스피어만 (NaN 은 변수별 제외)."""
    out = np.full(X.shape[1], np.nan)
    ry = pd.Series(y).rank().values
    for j in range(X.shape[1]):
        x = X[:, j]; m = ~np.isnan(x)
        if m.sum() < MIN_N or np.nanstd(x[m]) == 0:
            continue
        rx = pd.Series(x[m]).rank().values; yy = ry[m]
        out[j] = np.corrcoef(rx, yy)[0, 1]
    return out

rows = []
for k, i in enumerate(sig):
    r = R20[i]
    e = CU[i + 1]
    ok = ~np.isnan(r) & (VU[i] > 0) & (VU[i + 1] > 0) & ~PEN[i] & ~np.isnan(e) & (e > 0) & ~np.isnan(CF[i + 41])
    if ok.sum() < 300:
        continue
    thr = np.quantile(r[ok], 0.20); os_ = ok & (r <= thr)
    if os_.sum() < MIN_N:
        continue
    c1, c6, c21, c41 = CF[i + 1], CF[i + 6], CF[i + 21], CF[i + 41]
    f5 = c6 / c1 - 1; f20 = c21 / c1 - 1; f40 = c41 / c1 - 1
    m5, m20, m40 = np.nanmean(f5[ok]), np.nanmean(f20[ok]), np.nanmean(f40[ok])
    T1 = (f5[os_] - m5) * 100; T3 = (f20[os_] - m20) * 100; T4 = (f40[os_] - m40) * 100
    T2 = ((f5[os_] - COST > 0) & (c21[os_] > c6[os_])).astype(float)
    X = np.column_stack([V[v][k][os_] for v in VARS]).astype(float)
    row = dict(date=dates[i], month=dates[i][:6], n_os=int(os_.sum()), n_ok=int(ok.sum()), succ=T2.mean() * 100, t1=T1.mean(), t4=T4.mean())
    for tn, T in (("T1", T1), ("T2", T2), ("T3", T3), ("T4", T4)):
        ic = spearman_cols(X, T)
        for j, v in enumerate(VARS):
            row[f"ic_{tn}_{v}"] = ic[j]
    # 상위 20% − 하위 20% (변수 기준) 의 T1·T2 차이
    for j, v in enumerate(VARS):
        x = X[:, j]; m = ~np.isnan(x)
        if m.sum() < MIN_N:
            row[f"q_T1_{v}"] = np.nan; row[f"q_T2_{v}"] = np.nan; continue
        q1, q4 = np.quantile(x[m], [0.2, 0.8])
        lo_, hi_ = m & (x <= q1), m & (x >= q4)
        if lo_.sum() < 5 or hi_.sum() < 5 or q1 == q4:
            row[f"q_T1_{v}"] = np.nan; row[f"q_T2_{v}"] = np.nan; continue
        row[f"q_T1_{v}"] = T1[hi_].mean() - T1[lo_].mean(); row[f"q_T2_{v}"] = (T2[hi_].mean() - T2[lo_].mean()) * 100
    rows.append(row)
D = pd.DataFrame(rows); D.to_csv(OUT / "tenyr_days.csv", index=False, encoding="utf-8-sig")
print(f"신호일 {len(D)} ({D.date.min()}~{D.date.max()}) · 과매도 n 중앙값 {D.n_os.median():.0f} · 성공률 평균 {D.succ.mean():.1f}% · T1 평균 {D.t1.mean():+.2f} · T4 {D.t4.mean():+.2f} · {time.time()-t0:.0f}s")

# ---- 월 블록 부트스트랩(벡터화: 월별 합/개수 → 추출) ----
BONF = 0.05 / (2 * M)
def boot(sub, cols, levels=((0.025, 0.975), (BONF / 2, 1 - BONF / 2))):
    """sub: 날짜 DataFrame, cols: 통계 열 → 각 열의 평균과 구간들. 월 블록 재추출 NB 회(공통 추출)."""
    X = sub[cols].values.astype(float); months = sub["month"].values; um = np.unique(months)
    mi = np.searchsorted(um, months)
    Xz = np.nan_to_num(X); cnt_m = np.zeros((len(um), X.shape[1])); sum_m = np.zeros_like(cnt_m)
    np.add.at(sum_m, mi, Xz); np.add.at(cnt_m, mi, ~np.isnan(X))
    draws = rng.integers(0, len(um), size=(NB, len(um)))
    means = sum_m[draws].sum(1) / np.where(cnt_m[draws].sum(1) == 0, np.nan, cnt_m[draws].sum(1))
    res = {"mean": np.nanmean(X, axis=0)}
    for a, b in levels:
        res[f"lo{a:.5f}"] = np.nanpercentile(means, a * 100, axis=0); res[f"hi{b:.5f}"] = np.nanpercentile(means, b * 100, axis=0)
    return res

out = []
A, B = D[D.date < SPLIT], D[D.date >= SPLIT]
for tn in ("T1", "T2", "T3", "T4"):
    cols = [f"ic_{tn}_{v}" for v in VARS]
    full = boot(D, cols); fa = boot(A, cols, levels=((0.025, 0.975),)); fb = boot(B, cols, levels=((0.025, 0.975),))
    lo95, hi95 = full["lo0.02500"], full["hi0.97500"]
    lob, hib = full[f"lo{BONF/2:.5f}"], full[f"hi{1-BONF/2:.5f}"]
    for j, v in enumerate(VARS):
        out.append(dict(target=tn, var=v, ic=full["mean"][j], lo=lo95[j], hi=hi95[j], bonf_lo=lob[j], bonf_hi=hib[j],
                        front=fa["mean"][j], front_lo=fa["lo0.02500"][j], front_hi=fa["hi0.97500"][j],
                        back=fb["mean"][j], back_lo=fb["lo0.02500"][j], back_hi=fb["hi0.97500"][j],
                        q_diff=D[f"q_{tn}_{v}"].mean() if tn in ("T1", "T2") else np.nan))
T = pd.DataFrame(out)
# 후보: 주목표(T1 또는 T2)에서 Bonferroni 구간이 0 을 안 걸치고, 앞/뒤 부호 같고, 뒤반 95% 구간이 0 을 안 걸침
T["bonf_excl0"] = (T.bonf_lo > 0) | (T.bonf_hi < 0)
T["halves_same"] = np.sign(T.front) == np.sign(T.back)
T["back_excl0"] = (T.back_lo > 0) | (T.back_hi < 0)
T["candidate"] = T.target.isin(["T1", "T2"]) & T.bonf_excl0 & T.halves_same & T.back_excl0
T.to_csv(OUT / "tenyr_summary.csv", index=False, encoding="utf-8-sig")

W = T.pivot(index="var", columns="target", values="ic")
order = W["T1"].abs().sort_values(ascending=False).index
def fmt(tn, v):
    r = T[(T.target == tn) & (T["var"] == v)].iloc[0]
    flag = "★" if r.candidate else ("✓" if r.bonf_excl0 else "")
    return f"{r.ic:+.3f} [{r.lo:+.3f},{r.hi:+.3f}]{flag}"
print(f"\n### 11년 대리 — 변수별 날짜평균 스피어만 IC [95%] (Bonferroni 수준 1−0.05/{2*M}; ✓ = Bonferroni 구간 0 제외, ★ = 후보 규칙 통과) · |T1| 내림차순")
print(f"{'변수':14s} {'T1 5일초과':30s} {'T2 성공':30s} {'T3 20일':30s} {'T4 40일':30s} {'q차 T1(%p)':>10s} {'q차 T2(%p)':>10s}")
for v in order:
    q1 = T[(T.target == 'T1') & (T["var"] == v)].q_diff.iloc[0]; q2 = T[(T.target == 'T2') & (T["var"] == v)].q_diff.iloc[0]
    print(f"{v:14s} {fmt('T1', v):30s} {fmt('T2', v):30s} {fmt('T3', v):30s} {fmt('T4', v):30s} {q1:+10.2f} {q2:+10.2f}")
print("\n### 앞반(2015~20) / 뒤반(2021~) — T1·T2 IC [95%]")
for v in order:
    s = []
    for tn in ("T1", "T2"):
        r = T[(T.target == tn) & (T["var"] == v)].iloc[0]
        s.append(f"{tn} 앞 {r.front:+.3f} [{r.front_lo:+.3f},{r.front_hi:+.3f}] / 뒤 {r.back:+.3f} [{r.back_lo:+.3f},{r.back_hi:+.3f}]")
    print(f"{v:14s} " + " | ".join(s))
cand = T[T.candidate]
print(f"\n### 후보(§0 규칙): {len(cand)}개")
for _, r in cand.iterrows():
    r4 = T[(T.target == 'T4') & (T["var"] == r["var"])].iloc[0]
    print(f"  {r['var']} ({r.target}) IC {r.ic:+.3f} Bonf [{r.bonf_lo:+.3f},{r.bonf_hi:+.3f}] · 뒤반 [{r.back_lo:+.3f},{r.back_hi:+.3f}] · 대가 T4 IC {r4.ic:+.3f} [{r4.lo:+.3f},{r4.hi:+.3f}]")
print(f"\n신호일 {len(D)} · 앞반 {len(A)} · 뒤반 {len(B)} · 변수 {M} · 부트스트랩 {NB}회 seed 7 · {time.time()-t0:.0f}s")
