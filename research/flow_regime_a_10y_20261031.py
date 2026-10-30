# -*- coding: utf-8 -*-
"""시장 수급 × 국면 — 사전 고정 질문 3개(F01 외국인 강도 · F03 연기금 강도 · S2 외국인 순매도 완화)를 코스피 A 칸 사건 안에서 (2026-10-31, 사후 관측 · 채택 아님)

정의(Codex 명세 REPLY_20261031_flow_data_spec.md §8 그대로, 결과 보기 전 고정):
  C20(i,t) = 신호일 t 까지 최근 20거래일(KRX 거래일, t 포함) 주체 i 의 순매수 대금 합(원) · T20(t) = 같은 20일의 '전체' 매수 대금 합(= 거래대금).
  F01: C20(외국인)/T20 > 0 (그룹 high) vs ≤ 0 (low).   F03: C20(연기금)/T20 > 0 vs ≤ 0.
  S2 : C20(외국인) < 0 인 날만 대상, D = C20(t) − C20(t−20)(겹치지 않는 두 구간) > 0 (완화) vs ≤ 0 (심화).
  문턱은 0 하나. 감도로 창 60일(C60/T60) 한 벌만 병기. 주체는 상세 '외국인'·'연기금'(기관합계 아님). 시장 = KOSPI(A 칸이 코스피 기준).
결과값(기존 정의 그대로 — a_cell_dispersion_untraded_10y 와 같은 코드): 10년 DB 정리 유니버스 · 과매도(R20 하위 20%) 바구니 t+1 종가 → t+41 종가 동일가중 · 전 종목 바구니 · 코스피 40일 ·
  손실 집중 = 바구니 −20% 이하 종목 비율 · 사건 수익 음수 비율. 단위 = A 사건(≥40거래일 간격, 사건 부트스트랩 4,000 seed 20261030) 본문 · A 날(5거래일 격자, 월 블록 2,000 seed 7) 참고 · 모든 칸 참고.
시간: t 의 수급은 t 장 마감 뒤 확정 → t+1 종가 주문에 쓸 수 있다고 가정(공개 시각 미확인 — 한계에 적음).
재현: python research/flow_regime_a_10y_20261031.py → research/out_flow_regime/ (2분)."""
import os, sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
DB10 = str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"); DBF = str(REPO / ".." / "dh-q7m3k-data" / "market_flows_10y.db")
OUT = HERE / "out_flow_regime"; OUT.mkdir(exist_ok=True)
H = 40; STEP = 5; SPLIT = "20210101"; A_TH = -5.0
rng = np.random.default_rng(7); rng_ev = np.random.default_rng(20261030)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
LOG = []


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


def block_diff_ci(df, col, grp, k=2000):
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
    d = df[[col, grp]].dropna()
    if d[grp].nunique() < 2:
        return (np.nan, np.nan)
    v = d[col].values; g = (d[grp] == "high").values; n = len(v); out = []
    for _ in range(k):
        idx = rng_ev.integers(0, n, n); vv, gg = v[idx], g[idx]
        if gg.any() and (~gg).any():
            out.append(vv[gg].mean() - vv[~gg].mean())
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)))


def events_of(df):
    keep = []; last = -10 ** 9
    for _, r in df.sort_values("i").iterrows():
        if r.i - last >= H:
            keep.append(r.name); last = r.i
    return df.loc[keep]


t0 = time.time()
# ── 수급
cf = sqlite3.connect(f"file:{DBF}?mode=ro", uri=True)
F = pd.read_sql("SELECT date, investor, net_val, buy_val FROM investor_daily WHERE market='KOSPI'", cf); cf.close()
net = F.pivot(index="date", columns="investor", values="net_val").sort_index(); T = F[F.investor == "전체"].set_index("date").buy_val.sort_index()
flow = pd.DataFrame({"fx": net["외국인"], "pen": net["연기금"], "T": T})
for w in (20, 60):
    flow[f"fx{w}"] = flow.fx.rolling(w).sum() / flow["T"].rolling(w).sum()
    flow[f"pen{w}"] = flow.pen.rolling(w).sum() / flow["T"].rolling(w).sum()
flow["fxC20"] = flow.fx.rolling(20).sum(); flow["fxD"] = flow.fxC20 - flow.fxC20.shift(20)
say(f"수급 KOSPI {flow.index[0]}~{flow.index[-1]} {len(flow)}일 · {time.time()-t0:.0f}s")

# ── 10년 바구니(기존 코드)
con = sqlite3.connect(f"file:{DB10}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index(); con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
dates = list(close.index); N = len(dates); tick = list(close.columns)
ks_r20 = ((ks / ks.shift(20) - 1) * 100).reindex(dates); ks_f40 = ((ks.shift(-1 - H) / ks.shift(-1) - 1) * 100).reindex(dates)
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, vol
tick = list(cu.columns); dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
cff = cu.copy(); cff.loc[:, dl] = cff.loc[:, dl].ffill()
fwd = (cff.shift(-1 - H) / cu.shift(-1) - 1) * 100; del cff
r20 = cu / cu.shift(20) - 1; penny = cu < 1000; v0 = vu.fillna(0) == 0
say(f"유니버스 {cu.shape[1]} · 날 {N} · {time.time()-t0:.0f}s")

rows = []
for i in range(130, N - H - 1, STEP):
    k = ks_r20.iloc[i]; d = dates[i]
    if k != k or d not in flow.index:
        continue
    f = fwd.iloc[i]; r = r20.iloc[i]; ok = f.notna() & r.notna() & ~penny.iloc[i].fillna(True) & ~v0.iloc[i] & ~v0.iloc[i + 1]
    if ok.sum() < 300:
        continue
    os_ = ok & (r <= r[ok].quantile(0.20)); fo = f[os_]; fl = flow.loc[d]
    rows.append(dict(date=d, month=d[:6], i=i, half=("앞" if d < SPLIT else "뒤"), ks_r20=float(k), cell=("A" if k <= A_TH else ("D" if k > 5 else "BC")),
                     fx20=fl.fx20, pen20=fl.pen20, fx60=fl.fx60, pen60=fl.pen60, fxC20=fl.fxC20, fxD=fl.fxD,
                     os_mean=float(fo.mean()), all_mean=float(f[ok].mean()), os_tail20=float((fo <= -20).mean()), os_pos=float((fo > 0).mean()), ks_f40=float(ks_f40.iloc[i])))
R = pd.DataFrame(rows).dropna(subset=["fx20", "pen20"]); R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
A = R[R.cell == "A"].copy(); E = events_of(A); E.to_csv(OUT / "events.csv", index=False, encoding="utf-8-sig")
say(f"신호일 {len(R)} · A 날 {len(A)} · A 사건 {len(E)} · {time.time()-t0:.0f}s")
OUTC = ["os_mean", "all_mean", "os_tail20", "os_pos", "ks_f40"]


def grp(df, q):
    df = df.copy()
    if q == "F01": df["g"] = np.where(df.fx20 > 0, "high", "low")
    elif q == "F03": df["g"] = np.where(df.pen20 > 0, "high", "low")
    elif q == "S2": df = df[df.fxC20 < 0].copy(); df["g"] = np.where(df.fxD > 0, "high", "low")
    elif q == "F01_60": df["g"] = np.where(df.fx60 > 0, "high", "low")
    elif q == "F03_60": df["g"] = np.where(df.pen60 > 0, "high", "low")
    return df


def table(df, q, label, unit):
    d = grp(df, q); n_hi, n_lo = int((d.g == "high").sum()), int((d.g == "low").sum())
    lines = [f"\n-- {label} · {q} · high {n_hi} / low {n_lo} --", f"{'결과값':<10}{'high':>9}{'low':>9}{'차이':>9}  95%"]
    for c in OUTC:
        hi, lo = d[d.g == "high"][c].mean(), d[d.g == "low"][c].mean()
        ci = block_diff_ci(d, c, "g") if unit == "day" else ev_diff_ci(d, c, "g")
        lines.append(f"{c:<10}{hi:>9.2f}{lo:>9.2f}{hi-lo:>9.2f}  [{ci[0]:+.2f}, {ci[1]:+.2f}]")
    if unit == "event":
        lines.append(f"  사건 수익 음수: high {(d[d.g=='high'].os_mean<0).sum()}/{n_hi} · low {(d[d.g=='low'].os_mean<0).sum()}/{n_lo}")
    say("\n".join(lines)); return d


say("\n== 0. 칸별 수급 수준(평균) ==")
say(R.groupby("cell")[["fx20", "pen20", "fx60", "pen60"]].mean().mul(100).round(2).rename(columns=lambda c: c + "(%)").to_string())
say(f"A 날 fx20>0 비율 {(A.fx20>0).mean():.0%} · pen20>0 비율 {(A.pen20>0).mean():.0%} · 모든 날 fx20>0 {(R.fx20>0).mean():.0%}")

say("\n== 1. 본문 — A 사건 단위 ==")
for q in ["F01", "F03", "S2"]:
    d = table(E, q, "A 사건", "event")
    say(d[["date", "ks_r20", "fx20", "pen20", "fxD", "g", "os_mean", "all_mean", "os_tail20", "ks_f40"]].assign(fx20=lambda x: (x.fx20 * 100).round(2), pen20=lambda x: (x.pen20 * 100).round(2), fxD=lambda x: (x.fxD / 1e12).round(2)).round(2).to_string(index=False))
say("\n== 2. 참고 — A 날(겹침, 월 블록) ==")
for q in ["F01", "F03", "S2"]:
    table(A, q, "A 날", "day")
say("\n== 3. 감도 — 창 60일 (A 사건) ==")
for q in ["F01_60", "F03_60"]:
    table(E, q, "A 사건", "event")
say("\n== 4. 참고 — 모든 칸 신호일 ==")
for q in ["F01", "F03", "S2"]:
    table(R, q, "전체 날", "day")
say("\n== 5. 순위상관(보조) ==")
for name, df in [("A 날", A), ("A 사건", E), ("전체", R)]:
    say(f"{name:<5} n={len(df):<4} " + " · ".join(f"{a}↔{b} {df[[a, b]].corr(method='spearman').iloc[0, 1]:+.2f}" for a, b in [("fx20", "os_mean"), ("pen20", "os_mean"), ("fx20", "ks_f40"), ("fx20", "ks_r20"), ("fxD", "os_mean")]))
(OUT / "run_20261031.txt").write_text("\n".join(LOG), encoding="utf-8")
say(f"\n끝 {time.time()-t0:.0f}s → {OUT}")
