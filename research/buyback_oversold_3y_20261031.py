# -*- coding: utf-8 -*-
"""가 갈래 ① — 자사주 취득 공시(DART) 뒤 20거래일 안의 과매도 vs 그 밖 과매도 (운영 DB 3.3년 · 2023-07~2026-08 신호) (2026-10-31, 사후 관측 · 채택 아님)

설계(결과 보기 전 고정):
  자료: 운영 시세 daily_ohlcv + daily_ohlcv_extra(2023-06-26~) · DART dart_events(2023-06-01~; event_type buyback = 자기주식취득결정/취득신탁계약체결(연장·정정 포함), buyback_sell = 처분) · 코스피 지수(market_daily).
  신호일 t: 5거래일 격자. 조건 통과 = t·t+1 양수 종가·거래량, 종가 ≥ 1,000, R20 유효, 정지 아님. 과매도 = 조건 통과 중 R20 하위 20%.
  B(t, 종목) = 직전 20거래일(t 포함) 안에 자사주 취득 공시 접수. S = 같은 기간 처분 공시. 둘 다 있으면 양쪽 표시.
  비교(주): 과매도 ∧ B  vs  과매도 ∧ ¬B ∧ ¬S — 40일 수익(t+1 → t+41 종가, %), −20% 이하 비율, 양수 비율. 날 단위 동일가중(양쪽 다 있는 날) · 월 블록 2,000(seed 7).
  칸별(코스피 R20 A ≤ −5 / BC / D > +5) · 감도 = 처분(S) vs 없음 · 창 60일 · 공시 유형(직접 취득 vs 신탁) 둘.
  맥락: 과매도 아닌 종목에서 B vs 없음(공시 효과 자체).
  한계: 3.3년(A 사건 ≈6개) · 공시 접수일 = 결정일 가정(장 마감 뒤 접수면 t+1 반영이 맞지만 하루 차이) · 취득 '결정' 이지 실제 매수량 아님.
재현: python research/buyback_oversold_3y_20261031.py → research/out_buyback/ (1분)."""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent; sys.path.insert(0, str(REPO))
import leaderboard as lb
OUT = HERE / "out_buyback"; OUT.mkdir(exist_ok=True)
H = 40; STEP = 5; A_TH = -5.0; rng = np.random.default_rng(7)
pd.set_option("display.width", 240); LOG = []


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    if len(um) < 2:
        return (np.nan, np.nan)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


t0 = time.time()
con = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
px = pd.concat([pd.read_sql("SELECT ticker,date,close,volume,is_suspended FROM daily_ohlcv", con), pd.read_sql("SELECT ticker,date,close,volume,is_suspended FROM daily_ohlcv_extra", con)], ignore_index=True)
ev = pd.read_sql("SELECT rcept_dt, ticker, event_type, report_nm FROM dart_events WHERE event_type IN ('buyback','buyback_sell')", con)
ks = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index(); con.close()
px["ticker"] = px.ticker.astype(str).str.zfill(6); ev["ticker"] = ev.ticker.astype(str).str.zfill(6)
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index)
susp = px.pivot_table(index="date", columns="ticker", values="is_suspended", aggfunc="max").reindex(close.index).fillna(0)
dates = list(close.index); N = len(dates); tick = list(close.columns); didx = {d: i for i, d in enumerate(dates)}
ks_r20 = ((ks / ks.shift(20) - 1) * 100).reindex(dates)
fwd = (close.shift(-1 - H) / close.shift(-1) - 1) * 100
r20 = close / close.shift(20) - 1
ok_all = (close >= 1000) & (vol.fillna(0) > 0) & (vol.shift(-1).fillna(0) > 0) & (susp == 0) & r20.notna() & close.shift(-1).notna()
# 공시 → 거래일 인덱스(접수일이 휴장일이면 다음 거래일)
dser = pd.Series(range(N), index=pd.to_datetime(dates))
def to_i(d):
    t = pd.Timestamp(d); pos = dser.index.searchsorted(t)
    return int(dser.iloc[pos]) if pos < N else None
ev["i"] = ev.rcept_dt.map(to_i); ev = ev.dropna(subset=["i"]); ev["i"] = ev.i.astype(int)
ev["kind"] = np.where(ev.report_nm.str.contains("신탁"), "trust", "direct")
buy = ev[ev.event_type == "buyback"]; sell = ev[ev.event_type == "buyback_sell"]
say(f"시세 {close.shape} · 취득 공시 {len(buy)}(직접 {(buy.kind=='direct').sum()} · 신탁 {(buy.kind=='trust').sum()}) · 처분 {len(sell)} · 종목(취득) {buy.ticker.nunique()} · {time.time()-t0:.0f}s")


def flag_matrix(evs, window):
    """날×종목 bool: 직전 window 거래일(t 포함) 안에 공시 있음."""
    M = np.zeros((N, len(tick)), dtype=bool); col = {t: k for k, t in enumerate(tick)}
    for _, r in evs.iterrows():
        c = col.get(r.ticker)
        if c is None: continue
        M[r.i:min(N, r.i + window), c] = True
    return pd.DataFrame(M, index=dates, columns=tick)


B20, S20, B60 = flag_matrix(buy, 20), flag_matrix(sell, 20), flag_matrix(buy, 60)
Bd20, Bt20 = flag_matrix(buy[buy.kind == "direct"], 20), flag_matrix(buy[buy.kind == "trust"], 20)
rows = []
for i in range(25, N - H - 1, STEP):
    d = dates[i]; k = ks_r20.iloc[i]
    if k != k: continue
    ok = ok_all.iloc[i]
    if ok.sum() < 300: continue
    r = r20.iloc[i]; f = fwd.iloc[i]
    os_ = ok & (r <= r[ok].quantile(0.20)); b = B20.iloc[i]; s = S20.iloc[i]; b60 = B60.iloc[i]; bd = Bd20.iloc[i]; bt = Bt20.iloc[i]
    g_b, g_n, g_s = os_ & b, os_ & ~b & ~s, os_ & s & ~b
    no_b, no_n = ok & ~os_ & b, ok & ~os_ & ~b & ~s
    row = dict(date=d, month=d[:6], ks_r20=float(k), cell=("A" if k <= A_TH else ("D" if k > 5 else "BC")),
               n_os=int(os_.sum()), n_b=int(g_b.sum()), n_s=int(g_s.sum()), n_n=int(g_n.sum()),
               os_b=float(f[g_b].mean()) if g_b.sum() else np.nan, os_n=float(f[g_n].mean()) if g_n.sum() else np.nan, os_s=float(f[g_s].mean()) if g_s.sum() else np.nan,
               tail_b=float((f[g_b] <= -20).mean()) if g_b.sum() else np.nan, tail_n=float((f[g_n] <= -20).mean()) if g_n.sum() else np.nan,
               pos_b=float((f[g_b] > 0).mean()) if g_b.sum() else np.nan, pos_n=float((f[g_n] > 0).mean()) if g_n.sum() else np.nan,
               os_b60=float(f[os_ & b60].mean()) if (os_ & b60).sum() else np.nan, os_n60=float(f[os_ & ~b60 & ~s].mean()) if (os_ & ~b60 & ~s).sum() else np.nan,
               os_bd=float(f[os_ & bd].mean()) if (os_ & bd).sum() else np.nan, os_bt=float(f[os_ & bt].mean()) if (os_ & bt).sum() else np.nan,
               nos_b=float(f[no_b].mean()) if no_b.sum() else np.nan, nos_n=float(f[no_n].mean()) if no_n.sum() else np.nan,
               r20_b=float(r[g_b].mean() * 100) if g_b.sum() else np.nan, r20_n=float(r[g_n].mean() * 100) if g_n.sum() else np.nan, all_mean=float(f[ok].mean()))
    rows.append(row)
R = pd.DataFrame(rows); R["d_b"] = R.os_b - R.os_n; R["d_s"] = R.os_s - R.os_n; R["d_tail"] = R.tail_b - R.tail_n; R["d_pos"] = R.pos_b - R.pos_n
R["d_b60"] = R.os_b60 - R.os_n60; R["d_bd"] = R.os_bd - R.os_n; R["d_bt"] = R.os_bt - R.os_n; R["d_nos"] = R.nos_b - R.nos_n
R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
say(f"신호일 {len(R)} ({R.date.iloc[0]}~{R.date.iloc[-1]}) · 과매도 중 자사주 취득 20일 안 종목 수 중앙 {R.n_b.median():.0f}(비율 {(R.n_b/R.n_os).mean():.1%}) · 처분 {R.n_s.median():.0f} · {time.time()-t0:.0f}s")


def tbl(df, label):
    def ci(c):
        d = df.dropna(subset=[c]); lo, hi = block_ci(d[c], d.month); return f"{d[c].mean():+.2f} [{lo:+.2f}, {hi:+.2f}] (n {len(d)})"
    say(f"\n-- {label} · 날 {len(df)} · 과매도∧취득 {df.os_b.mean():+.2f} · 과매도∧없음 {df.os_n.mean():+.2f} · 과매도∧처분 {df.os_s.mean():+.2f} · 전 종목 {df.all_mean.mean():+.2f}")
    say(f"   취득−없음 {ci('d_b')} · 처분−없음 {ci('d_s')} · 60일 창 {ci('d_b60')} · 직접 {ci('d_bd')} · 신탁 {ci('d_bt')}")
    say(f"   −20% 비율 차 {ci('d_tail')} · 양수 비율 차 {ci('d_pos')} · R20 취득/없음 {df.r20_b.mean():+.1f}/{df.r20_n.mean():+.1f} · (과매도 아님) 취득−없음 {ci('d_nos')}")


for label, df in [("전체", R), ("A 급락 뒤", R[R.cell == "A"]), ("B·C", R[R.cell == "BC"]), ("D 급등 뒤", R[R.cell == "D"]),
                  ("2023-07~2024", R[R.date < "20250101"]), ("2025~", R[R.date >= "20250101"])]:
    if len(df): tbl(df, label)
say("\n순위상관(날 단위): 과매도 중 취득 비율 ↔ 과매도 40일 " + f"{R[['n_b','os_n']].assign(share=R.n_b/R.n_os)[['share','os_n']].corr(method='spearman').iloc[0,1]:+.2f}")
(OUT / "run_20261031.txt").write_text("\n".join(LOG), encoding="utf-8"); say(f"\n끝 {time.time()-t0:.0f}s → {OUT}")
