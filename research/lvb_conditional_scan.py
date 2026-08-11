# -*- coding: utf-8 -*-
"""
lvb_conditional_scan.py — lv_b 유니버스 내 조건부 요인 탐색 (§14 탐색 전용, 2026-08-11)
=======================================================================================
질문: lv_b(저변동+ROE)가 고른/보는 종목들 '안에서', 어떤 추가 특성(RSI·수급·모멘텀·공매도
신용 등)을 가진 종목이 이후에 더 올랐는가?

[A] OOS 실적재 구간: lowvol_scores(lv_b) 38 run(20260605~20260803) — 실제 동결 점수 유니버스.
    요인: 가격계(RSI14·단기수익·고점근접·모멘텀·거래량) + 수급(daily_flows 외인/기관/개인)
        + 공매도/신용(short_flows) + lv_b 점수 자체.
    forward: h5·h20 (change_pct 복리, 데이터 한계 8/10).
[B] 3년 패널 근사: daily_ohlcv 3y, 월간 앵커. 가드(거래대금 20일 평균 ≥5억) 내
    lv63 하위 30%(저변동 서브셋 — lv_b 핵심축 근사, ROE·과매도 게이트는 재구성 불가라 제외)
    안에서 가격계+공매도/신용 요인 조건부 IC.

정직성: 탐색(§14) — 전부 in-sample 가설. 다중검정(요인 다수) 감안해 Bonferroni 참고선 제시.
        A는 표본이 작고(주간앵커 h20 n≈5주) 하락→반등 단일 국면. B는 생존편향 부분(상폐 후
        수익 단절), ROE 부재로 lv_b 정확 재구성 아님. 어떤 결과도 점수식 반영 금지(새 모델
        id+사전등록 경로만).
실행: python research/lvb_conditional_scan.py  (repo 루트 기준, history.db·ohlcv.db 읽기 전용)
"""
import sqlite3, sys, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
HIST = HERE / "history.db"
OHLCV = HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"
RNG = np.random.default_rng(20260811)
NBOOT = 3000

def sconn(p):
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)

def rsi14(close):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1/14, min_periods=14).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/14, min_periods=14).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def spearman_ic(x, y):
    m = x.notna() & y.notna()
    if m.sum() < 15:
        return np.nan, int(m.sum())
    return x[m].rank().corr(y[m].rank()), int(m.sum())

def boot_ci(vals, nboot=NBOOT):
    v = np.asarray([x for x in vals if np.isfinite(x)])
    if len(v) < 3:
        return (np.nan, np.nan)
    idx = RNG.integers(0, len(v), (nboot, len(v)))
    means = v[idx].mean(axis=1)
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)))

print("=" * 70)
print("[0] 데이터 로드")
hc, oc = sconn(HIST), sconn(OHLCV)
lv = pd.read_sql("SELECT run_id, market, ticker, lowvol_score FROM lowvol_scores WHERE model_id='lv_b'", hc)
runs = sorted(lv.run_id.unique())
tickers = sorted(lv.ticker.unique())
print(f"lv_b: {len(runs)} runs {runs[0]}~{runs[-1]}, 고유종목 {len(tickers)}")

ph = ",".join("?" * len(tickers))
px = pd.read_sql(f"SELECT ticker,date,close,volume,change_pct,shares,is_suspended FROM daily_ohlcv "
                 f"WHERE ticker IN ({ph}) AND date>='20250501'", oc, params=tickers)
dates = sorted(px.date.unique())
C = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").reindex(dates)
V = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(dates)
CH = px.pivot_table(index="date", columns="ticker", values="change_pct", aggfunc="last").reindex(dates)
SH = px.pivot_table(index="date", columns="ticker", values="shares", aggfunc="last").reindex(dates)
R = CH  # ⚠ change_pct 는 소수(0.025=2.5%) — 검증: 005930 20260805 close비 2.5% = 0.025
print(f"ohlcv: {C.shape} ({dates[0]}~{dates[-1]})")

fl = pd.read_sql(f"SELECT ticker,date,foreign_net_val,inst_net_val,person_net_val FROM daily_flows "
                 f"WHERE ticker IN ({ph})", oc, params=tickers)
FG = fl.pivot_table(index="date", columns="ticker", values="foreign_net_val", aggfunc="last").reindex(dates)
IN_ = fl.pivot_table(index="date", columns="ticker", values="inst_net_val", aggfunc="last").reindex(dates)
PS = fl.pivot_table(index="date", columns="ticker", values="person_net_val", aggfunc="last").reindex(dates)
sf = pd.read_sql(f"SELECT ticker,date,short_vol_ratio,credit_bal_rate FROM short_flows "
                 f"WHERE ticker IN ({ph}) AND date>='20260101'", oc, params=tickers)
SV = sf.pivot_table(index="date", columns="ticker", values="short_vol_ratio", aggfunc="last").reindex(dates)
CB = sf.pivot_table(index="date", columns="ticker", values="credit_bal_rate", aggfunc="last").reindex(dates)
print(f"flows: {fl.date.min()}~{fl.date.max()} | short: {sf.date.min()}~{sf.date.max()}")

print("=" * 70)
print("[A] OOS 실적재 lv_b 유니버스 조건부 요인")

def factors_at(t_idx):
    """t_idx 시점(포함) 이전 데이터만으로 요인 계산 — PIT."""
    c = C.iloc[: t_idx + 1]
    v = V.iloc[: t_idx + 1]
    r = R.iloc[: t_idx + 1]
    f = pd.DataFrame(index=C.columns)
    f["rsi14"] = rsi14(c).iloc[-1]
    f["r5_%"] = ((1 + r.iloc[-5:]).prod() - 1) * 100
    f["r20_%"] = ((1 + r.iloc[-20:]).prod() - 1) * 100
    f["mom12_%"] = (c.iloc[-21] / c.iloc[-252] - 1) * 100 if len(c) >= 252 else np.nan
    f["nh252_%"] = (c.iloc[-1] / c.iloc[-252:].max() - 1) * 100
    f["volr_5_20"] = v.iloc[-5:].mean() / v.iloc[-20:].mean()
    f["amt20_억"] = (c * v).iloc[-20:].mean() / 1e8
    f["mcap_조"] = c.iloc[-1] * SH.iloc[t_idx] / 1e12
    f["lv20"] = r.iloc[-20:].std()
    f["fgn5_억"] = FG.iloc[max(0, t_idx - 4): t_idx + 1].sum(min_count=3) / 1e8
    f["fgn20_억"] = FG.iloc[max(0, t_idx - 19): t_idx + 1].sum(min_count=10) / 1e8
    f["inst5_억"] = IN_.iloc[max(0, t_idx - 4): t_idx + 1].sum(min_count=3) / 1e8
    f["inst20_억"] = IN_.iloc[max(0, t_idx - 19): t_idx + 1].sum(min_count=10) / 1e8
    f["person20_억"] = PS.iloc[max(0, t_idx - 19): t_idx + 1].sum(min_count=10) / 1e8
    f["short_ratio5"] = SV.iloc[max(0, t_idx - 4): t_idx + 1].mean()
    f["credit_rate"] = CB.iloc[: t_idx + 1].ffill().iloc[-1]
    return f

def fwd_ret(t_idx, h):
    if t_idx + h >= len(R):
        return None
    return ((1 + R.iloc[t_idx + 1: t_idx + 1 + h]).prod() - 1) * 100

FNAMES = ["rsi14", "r5_%", "r20_%", "mom12_%", "nh252_%", "volr_5_20", "amt20_억", "mcap_조",
          "lv20", "fgn5_억", "fgn20_억", "inst5_억", "inst20_억", "person20_억",
          "short_ratio5", "credit_rate", "lvb_score"]

# 주간 앵커(겹침 축소): 각 ISO주 첫 run만
wk, anchors = set(), []
for rid in runs:
    w = pd.Timestamp(rid).isocalendar()[:2]
    if w not in wk:
        wk.add(w); anchors.append(rid)
print(f"주간 앵커 {len(anchors)}개: {anchors}")

results = {h: {f: [] for f in FNAMES} for h in (5, 20)}
qout = {h: {f: [] for f in FNAMES} for h in (5, 20)}
top_results = {h: {f: [] for f in FNAMES} for h in (5, 20)}
used = {5: [], 20: []}
for rid in anchors:
    if rid not in C.index:
        continue
    t = C.index.get_loc(rid)
    uni = lv[lv.run_id == rid].set_index("ticker")["lowvol_score"]
    uni = uni[uni.index.isin(C.columns)]
    F = factors_at(t).reindex(uni.index)
    F["lvb_score"] = uni
    for h in (5, 20):
        fr = fwd_ret(t, h)
        if fr is None:
            continue
        y = fr.reindex(uni.index)
        used[h].append(rid)
        top = uni.rank(ascending=False) <= 50
        for f in FNAMES:
            ic, n = spearman_ic(F[f], y)
            results[h][f].append(ic)
            ict, nt = spearman_ic(F[f][top], y[top])
            top_results[h][f].append(ict)
            x = F[f]
            m = x.notna() & y.notna()
            if m.sum() >= 30:
                q = pd.qcut(x[m].rank(method="first"), 3, labels=False)
                qout[h][f].append((y[m][q == 2].mean(), y[m][q == 0].mean(),
                                   (y[m][q == 2] > 0).mean(), (y[m][q == 0] > 0).mean()))

print(f"h5 앵커 {len(used[5])}개 / h20 앵커 {len(used[20])}개")

def table(res, qres, h, label):
    rows = []
    for f in FNAMES:
        ics = [x for x in res[h][f] if np.isfinite(x)]
        if not ics:
            continue
        lo, hi = boot_ci(ics)
        pos = np.mean([x > 0 for x in ics])
        row = dict(factor=f, mean_ic=np.mean(ics), n_anchor=len(ics), ci_lo=lo, ci_hi=hi, pos_share=pos)
        if qres is not None and qres[h][f]:
            row["top_terc_%"] = np.nanmean([t[0] for t in qres[h][f]])
            row["bot_terc_%"] = np.nanmean([t[1] for t in qres[h][f]])
            row["top_win"] = np.nanmean([t[2] for t in qres[h][f]])
            row["bot_win"] = np.nanmean([t[3] for t in qres[h][f]])
        rows.append(row)
    df = pd.DataFrame(rows).sort_values("mean_ic", key=lambda s: s.abs(), ascending=False)
    print(f"\n--- {label} h{h} (IC + 대비 |IC| 정렬) ---")
    print(df.to_string(index=False, float_format=lambda x: f"{x:+.3f}" if abs(x) < 10 else f"{x:.1f}"))
    return df

A_out = {}
for h in (5, 20):
    A_out[f"uni_h{h}"] = table(results, qout, h, "[A] lv_b 전체 유니버스")
    A_out[f"top_h{h}"] = table(top_results, None, h, "[A] lv_b 상위50 내부")

print("=" * 70)
print("[B] 3년 패널 — 저변동 서브셋(가드 내 lv63 하위 30%) 조건부, h20")
pxall = pd.read_sql("SELECT ticker,date,close,volume,change_pct FROM daily_ohlcv WHERE date>='20230626'", oc)
dts = sorted(pxall.date.unique())
Ca = pxall.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").reindex(dts)
Va = pxall.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(dts)
Ra = pxall.pivot_table(index="date", columns="ticker", values="change_pct", aggfunc="last").reindex(dts)  # 소수 단위
sfa = pd.read_sql("SELECT ticker,date,short_vol_ratio,credit_bal_rate FROM short_flows WHERE date>='20230601'", oc)
SVa = sfa.pivot_table(index="date", columns="ticker", values="short_vol_ratio", aggfunc="last").reindex(dts).reindex(columns=Ca.columns)
CBa = sfa.pivot_table(index="date", columns="ticker", values="credit_bal_rate", aggfunc="last").reindex(dts).reindex(columns=Ca.columns)
print(f"전체 패널 {Ca.shape}")

monthly = []
seen = set()
for i, d in enumerate(dts):
    if i < 260 or i + 20 >= len(dts):
        continue
    ym = d[:6]
    if ym not in seen:
        seen.add(ym); monthly.append(i)
print(f"월간 앵커 {len(monthly)}개 ({dts[monthly[0]]}~{dts[monthly[-1]]})")

BF = ["rsi14", "r5_%", "r20_%", "mom12_%", "nh252_%", "volr_5_20", "mcap억지수", "short_ratio5", "credit_rate"]
bres = {f: [] for f in BF}
bq = {f: [] for f in BF}
byear = {f: {} for f in BF}
for t in monthly:
    c = Ca.iloc[: t + 1]; v = Va.iloc[: t + 1]; r = Ra.iloc[: t + 1]
    amt20 = (c * v).iloc[-20:].mean() / 1e8
    lv63 = r.iloc[-63:].std()
    guard = (amt20 >= 5) & lv63.notna() & (c.iloc[-1] > 0)
    sub = lv63[guard].nsmallest(max(30, int(guard.sum() * 0.30))).index
    F = pd.DataFrame(index=sub)
    cc = c[sub]; rr = r[sub]
    F["rsi14"] = rsi14(cc).iloc[-1]
    F["r5_%"] = ((1 + rr.iloc[-5:]).prod() - 1) * 100
    F["r20_%"] = ((1 + rr.iloc[-20:]).prod() - 1) * 100
    F["mom12_%"] = (cc.iloc[-21] / cc.iloc[-252] - 1) * 100
    F["nh252_%"] = (cc.iloc[-1] / cc.iloc[-252:].max() - 1) * 100
    F["volr_5_20"] = v[sub].iloc[-5:].mean() / v[sub].iloc[-20:].mean()
    F["mcap억지수"] = amt20[sub]
    F["short_ratio5"] = SVa[sub].iloc[max(0, t - 4): t + 1].mean()
    F["credit_rate"] = CBa[sub].iloc[: t + 1].ffill().iloc[-1]
    y = ((1 + Ra[sub].iloc[t + 1: t + 21]).prod() - 1) * 100
    yr = dts[t][:4]
    for f in BF:
        ic, n = spearman_ic(F[f], y)
        bres[f].append(ic)
        byear[f].setdefault(yr, []).append(ic)
        x = F[f]; m = x.notna() & y.notna()
        if m.sum() >= 30:
            q = pd.qcut(x[m].rank(method="first"), 3, labels=False)
            bq[f].append((y[m][q == 2].mean(), y[m][q == 0].mean(),
                          (y[m][q == 2] > 0).mean(), (y[m][q == 0] > 0).mean()))

rows = []
for f in BF:
    ics = [x for x in bres[f] if np.isfinite(x)]
    lo, hi = boot_ci(ics)
    yrs = {y: np.nanmean(v) for y, v in byear[f].items()}
    rows.append(dict(factor=f, mean_ic=np.mean(ics), n_anchor=len(ics), ci_lo=lo, ci_hi=hi,
                     pos_share=np.mean([x > 0 for x in ics]),
                     top_terc_pct=np.nanmean([t[0] for t in bq[f]]) if bq[f] else np.nan,
                     bot_terc_pct=np.nanmean([t[1] for t in bq[f]]) if bq[f] else np.nan,
                     top_win=np.nanmean([t[2] for t in bq[f]]) if bq[f] else np.nan,
                     bot_win=np.nanmean([t[3] for t in bq[f]]) if bq[f] else np.nan,
                     **{f"y{y}": v for y, v in sorted(yrs.items())}))
B_out = pd.DataFrame(rows).sort_values("mean_ic", key=lambda s: s.abs(), ascending=False)
print(B_out.to_string(index=False, float_format=lambda x: f"{x:+.3f}" if abs(x) < 10 else f"{x:.1f}"))

nb_tests = len(FNAMES) * 4 + len(BF)
print("\nBonferroni 참고: 총 검정 수 ≈", nb_tests, "→ 개별 CI가 0을 확실히 벗어나도 다중검정 감안해 '기움'으로만.")
out = HERE / "research" / "lvb_conditional_out"
out.mkdir(exist_ok=True)
for k, df in A_out.items():
    df.to_csv(out / f"A_{k}.csv", index=False)
B_out.to_csv(out / "B_panel_h20.csv", index=False)
print("저장:", out)
