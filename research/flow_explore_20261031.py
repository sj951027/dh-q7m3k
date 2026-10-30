# -*- coding: utf-8 -*-
"""시장 수급 × 국면 — **탐색**(사전 고정 아님 · 결론 아님 · 다음 사전 고정 후보를 고르기 위한 둘러보기) (2026-10-31 새벽)

자료: market_flows_10y.db(KRX 투자자별, 코스피·코스닥 2015~2026-10-30) + 10년 DB 정리 바구니(flow_regime_a_10y_20261031.py 와 같은 코드).
보는 것(전부 사후):
  E1 지금 사건(2026-10): 10/30 기준 20일·60일 누적 순매수(11구분, 조원·거래대금 대비 %)와, 과거 A 날 분포에서의 위치(백분위).
  E2 급등 뒤(D 칸) 역효과의 주체: D 날에서 외국인 20일 순매수 양/음 → 과매도·전 종목 40일. B·C 도.
  E3 연기금 쪼개기: A 날 3분위 · 앞/뒤반 · 깊이 통제(A 날을 R20 중앙값으로 둘로 나눈 안에서 부호 비교) · 60일 창.
  E4 개인(F04): A 사건·A 날 개인 20일 순매수 부호.
  E5 기관 세부(금융투자·투신·사모·보험·은행·기타금융) + 기타법인: A 날 부호별 과매도 40일 — 7개를 한꺼번에 보므로 다중비교 경고.
  E6 코스닥 수급(외국인·연기금·개인, KOSDAQ 시장 합계): 코스피 A 날에서 부호별 과매도 40일(합동 바구니 · 코스닥만 바구니).
  E7 누가 받아냈나: A 사건 22개 각각의 11구분 20일 누적(조원) 표.
  E8 외국인 '순매수 전환'(C20 이 음→양으로 바뀐 날, 모든 칸) 뒤 20·40일 코스피·과매도 바구니.
재현: python research/flow_explore_20261031.py → research/out_flow_explore/ (2분)."""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
DB10 = str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"); DBF = str(REPO / ".." / "dh-q7m3k-data" / "market_flows_10y.db")
OUT = HERE / "out_flow_explore"; OUT.mkdir(exist_ok=True)
H = 40; STEP = 5; SPLIT = "20210101"; A_TH = -5.0
rng = np.random.default_rng(7); rng_ev = np.random.default_rng(20261030)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
INV = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금", "기타법인", "개인", "외국인", "기타외국인"]
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
LOG = []


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


def block_diff_ci(df, col, grp, k=1000):
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


def ev_diff_ci(df, col, grp, k=3000):
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


def split_table(df, flag_col, label, unit, outc=("os_mean", "all_mean", "os_tail20", "ks_f40")):
    d = df.copy(); d["g"] = np.where(d[flag_col] > 0, "high", "low")
    n_hi, n_lo = int((d.g == "high").sum()), int((d.g == "low").sum())
    parts = []
    for c in outc:
        hi, lo = d[d.g == "high"][c].mean(), d[d.g == "low"][c].mean()
        ci = block_diff_ci(d, c, "g") if unit == "day" else ev_diff_ci(d, c, "g")
        parts.append(f"{c} {hi:+.2f}/{lo:+.2f} 차 {hi-lo:+.2f} [{ci[0]:+.2f},{ci[1]:+.2f}]")
    say(f"  {label:<28} >0 {n_hi:>3} / ≤0 {n_lo:>3} · " + " · ".join(parts))


t0 = time.time()
cf = sqlite3.connect(f"file:{DBF}?mode=ro", uri=True)
F = pd.read_sql("SELECT market, date, investor, net_val, buy_val FROM investor_daily", cf); cf.close()
flows = {}
for mkt in ["KOSPI", "KOSDAQ"]:
    f = F[F.market == mkt]; net = f.pivot(index="date", columns="investor", values="net_val").sort_index()
    T = f[f.investor == "전체"].set_index("date").buy_val.sort_index()
    fl = pd.DataFrame(index=net.index); fl["T20"] = T.rolling(20).sum(); fl["T60"] = T.rolling(60).sum()
    for inv in INV:
        fl[f"{inv}_20"] = net[inv].rolling(20).sum() / fl.T20; fl[f"{inv}_60"] = net[inv].rolling(60).sum() / fl.T60
        fl[f"{inv}_C20"] = net[inv].rolling(20).sum(); fl[f"{inv}_C60"] = net[inv].rolling(60).sum()
    flows[mkt] = fl
FK, FQ = flows["KOSPI"], flows["KOSDAQ"]
say(f"수급 적재 {time.time()-t0:.0f}s")

# ── E1 지금 사건
say("\n== E1. 지금(2026-10-30 기준) 누가 팔고 누가 받나 — 20일·60일 누적 순매수 ==")
last = FK.index[-1]
tab = pd.DataFrame({"20일 누적(조원)": [FK.at[last, f"{i}_C20"] / 1e12 for i in INV], "20일/거래대금(%)": [FK.at[last, f"{i}_20"] * 100 for i in INV],
                    "60일 누적(조원)": [FK.at[last, f"{i}_C60"] / 1e12 for i in INV], "60일/거래대금(%)": [FK.at[last, f"{i}_60"] * 100 for i in INV]}, index=INV).round(2)
say(f"[KOSPI {last}] 20일 거래대금 {FK.at[last,'T20']/1e12:.0f}조"); say(tab.to_string())
tq = pd.DataFrame({"20일 누적(조원)": [FQ.at[last, f"{i}_C20"] / 1e12 for i in INV], "20일/거래대금(%)": [FQ.at[last, f"{i}_20"] * 100 for i in INV]}, index=INV).round(2)
say(f"[KOSDAQ {last}]"); say(tq.to_string())

# ── 10년 바구니
con = sqlite3.connect(f"file:{DB10}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index()
kq = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSDAQ'", con).set_index("date")["close"].sort_index(); con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
dates = list(close.index); N = len(dates); tick = list(close.columns)
ks_r20 = ((ks / ks.shift(20) - 1) * 100).reindex(dates); ks_f40 = ((ks.shift(-1 - H) / ks.shift(-1) - 1) * 100).reindex(dates); ks_f20 = ((ks.shift(-21) / ks.shift(-1) - 1) * 100).reindex(dates)
kq_r20 = ((kq / kq.shift(20) - 1) * 100).reindex(dates)
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, vol
tick = list(cu.columns); dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
is_q = (meta.market.reindex(tick).isin(["KOSDAQ", "KOSDAQ GLOBAL"])).values
cff = cu.copy(); cff.loc[:, dl] = cff.loc[:, dl].ffill()
fwd = (cff.shift(-1 - H) / cu.shift(-1) - 1) * 100; del cff
r20 = cu / cu.shift(20) - 1; penny = cu < 1000; v0 = vu.fillna(0) == 0
say(f"유니버스 {cu.shape[1]} · 날 {N} · {time.time()-t0:.0f}s")

rows = []
for i in range(130, N - H - 1, STEP):
    k = ks_r20.iloc[i]; d = dates[i]
    if k != k or d not in FK.index or d not in FQ.index:
        continue
    f = fwd.iloc[i]; r = r20.iloc[i]; ok = f.notna() & r.notna() & ~penny.iloc[i].fillna(True) & ~v0.iloc[i] & ~v0.iloc[i + 1]
    if ok.sum() < 300:
        continue
    os_ = ok & (r <= r[ok].quantile(0.20)); fo = f[os_]; okq = ok & is_q; osq = okq & (r <= r[okq].quantile(0.20))
    row = dict(date=d, month=d[:6], i=i, half=("앞" if d < SPLIT else "뒤"), ks_r20=float(k), kq_r20=float(kq_r20.iloc[i]), cell=("A" if k <= A_TH else ("D" if k > 5 else "BC")),
               os_mean=float(fo.mean()), all_mean=float(f[ok].mean()), os_tail20=float((fo <= -20).mean()), osq_mean=float(f[osq].mean()), ks_f40=float(ks_f40.iloc[i]), ks_f20=float(ks_f20.iloc[i]))
    for inv in INV:
        row[f"k_{inv}"] = FK.at[d, f"{inv}_20"]; row[f"k60_{inv}"] = FK.at[d, f"{inv}_60"]; row[f"q_{inv}"] = FQ.at[d, f"{inv}_20"]
    row["k_fxC20"] = FK.at[d, "외국인_C20"]
    rows.append(row)
R = pd.DataFrame(rows).dropna(subset=["k_외국인"]); R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
A = R[R.cell == "A"].copy(); D = R[R.cell == "D"].copy(); BC = R[R.cell == "BC"].copy(); E = events_of(A)
say(f"신호일 {len(R)} · A {len(A)}(사건 {len(E)}) · BC {len(BC)} · D {len(D)} · {time.time()-t0:.0f}s")

# E1 보조: 지금 값이 과거 A 날 분포에서 어디쯤
say("\n[E1 보조] 지금 20일 누적/거래대금 이 과거 A 날(58) 분포에서 차지하는 백분위:")
for inv in ["외국인", "연기금", "개인", "금융투자", "투신", "기타법인"]:
    cur = FK.at[last, f"{inv}_20"]; pct = (A[f"k_{inv}"] < cur).mean() * 100
    say(f"  {inv:<6} 지금 {cur*100:+.2f}% · A 날 중앙값 {A[f'k_{inv}'].median()*100:+.2f}% · 지금은 아래에서 {pct:.0f} 백분위")

# ── E2 급등 뒤 역효과의 주체
say("\n== E2. 칸별 외국인·연기금·개인 부호 → 과매도 40일 (날 단위, 월 블록) ==")
for cname, df in [("A", A), ("BC", BC), ("D", D)]:
    for inv in ["외국인", "연기금", "개인"]:
        split_table(df, f"k_{inv}", f"{cname} 칸 · {inv} 20일", "day")

# ── E3 연기금 쪼개기
say("\n== E3. 연기금 쪼개기 (A 날 58) ==")
A["pen_ter"] = pd.qcut(A["k_연기금"], 3, labels=["하", "중", "상"])
say(A.groupby("pen_ter", observed=True)[["os_mean", "all_mean", "os_tail20", "ks_f40"]].mean().round(2).assign(n=A.pen_ter.value_counts()).to_string())
for h in ["앞", "뒤"]:
    split_table(A[A.half == h], "k_연기금", f"{h}반 · 연기금 20일", "day")
med = A.ks_r20.median()
split_table(A[A.ks_r20 <= med], "k_연기금", f"깊은 A(R20≤{med:.1f}) · 연기금", "day"); split_table(A[A.ks_r20 > med], "k_연기금", f"얕은 A(R20>{med:.1f}) · 연기금", "day")
split_table(E, "k60_연기금", "A 사건 · 연기금 60일", "event"); split_table(A, "k60_연기금", "A 날 · 연기금 60일", "day")
say(f"  A 날 순위상관: 연기금20↔과매도 {A[['k_연기금','os_mean']].corr(method='spearman').iloc[0,1]:+.2f} · 연기금60↔과매도 {A[['k60_연기금','os_mean']].corr(method='spearman').iloc[0,1]:+.2f} · 연기금20↔깊이 {A[['k_연기금','ks_r20']].corr(method='spearman').iloc[0,1]:+.2f}")

# ── E4 개인
say("\n== E4. 개인(F04) ==")
split_table(E, "k_개인", "A 사건 · 개인 20일", "event"); split_table(A, "k_개인", "A 날 · 개인 20일", "day"); split_table(R, "k_개인", "모든 날 · 개인 20일", "day")

# ── E5 기관 세부·기타법인 (다중비교 — 7개 한꺼번에)
say("\n== E5. 기관 세부·기타법인 — A 날 부호별 (⚠ 7개 동시 비교, 어느 한 칸이 0 을 벗어나도 근거 아님) ==")
for inv in ["금융투자", "투신", "사모", "보험", "은행", "기타금융", "기타법인"]:
    split_table(A, f"k_{inv}", f"A 날 · {inv}", "day", outc=("os_mean", "os_tail20"))
say("  A 사건 단위:")
for inv in ["금융투자", "투신", "사모", "기타법인"]:
    split_table(E, f"k_{inv}", f"A 사건 · {inv}", "event", outc=("os_mean", "os_tail20"))

# ── E6 코스닥 수급
say("\n== E6. 코스닥 시장 수급(외국인·연기금·개인) — 코스피 A 날 · 합동 바구니 / 코스닥만 바구니 ==")
for inv in ["외국인", "연기금", "개인"]:
    split_table(A, f"q_{inv}", f"A 날 · 코스닥 {inv} 20일", "day", outc=("os_mean", "osq_mean", "os_tail20"))
AQ = R[R.kq_r20 <= A_TH]
say(f"  (코스닥 R20 ≤ −5 날 {len(AQ)}):")
for inv in ["외국인", "연기금", "개인"]:
    split_table(AQ, f"q_{inv}", f"코스닥 A 날 · 코스닥 {inv}", "day", outc=("osq_mean", "os_mean"))

# ── E7 누가 받아냈나
say("\n== E7. A 사건 22개 — 20일 누적 순매수(조원, KOSPI) ==")
t7 = E[["date", "ks_r20", "os_mean"]].copy()
for inv in ["외국인", "연기금", "개인", "금융투자", "투신", "사모", "기타법인"]:
    t7[inv] = [FK.at[d, f"{inv}_C20"] / 1e12 for d in E.date]
say(t7.round(2).to_string(index=False))
say("  사건 평균(조원): " + " · ".join(f"{c} {t7[c].mean():+.2f}" for c in ["외국인", "연기금", "개인", "금융투자", "투신", "사모", "기타법인"]))

# ── E8 외국인 순매수 전환(모든 칸)
say("\n== E8. 외국인 20일 누적이 음(−)에서 양(+)으로 바뀐 날(격자 기준 직전 격자일 음 → 이번 양) ==")
R2 = R.sort_values("i").copy(); R2["prev_fx"] = R2.k_fxC20.shift(1); R2["prev_i"] = R2.i.shift(1)
turn = R2[(R2.prev_fx < 0) & (R2.k_fxC20 > 0) & (R2.i - R2.prev_i == STEP)]
say(f"  전환 날 {len(turn)} · 과매도 40일 {turn.os_mean.mean():+.2f} (모든 날 {R.os_mean.mean():+.2f}) · 전 종목 {turn.all_mean.mean():+.2f} ({R.all_mean.mean():+.2f}) · 코스피 20일 {turn.ks_f20.mean():+.2f} ({R.ks_f20.mean():+.2f}) · 40일 {turn.ks_f40.mean():+.2f} ({R.ks_f40.mean():+.2f})")
say("  칸별 전환 날 수: " + str(turn.cell.value_counts().to_dict()) + " · 전환 뒤 코스피 20일 플러스 비율 " + f"{(turn.ks_f20>0).mean():.0%} (모든 날 {(R.ks_f20>0).mean():.0%})")
(OUT / "run_20261031.txt").write_text("\n".join(LOG), encoding="utf-8")
say(f"\n끝 {time.time()-t0:.0f}s → {OUT}")
