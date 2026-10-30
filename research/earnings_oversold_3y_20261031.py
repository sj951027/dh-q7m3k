# -*- coding: utf-8 -*-
"""나 갈래 ① — 실적 발표 × 과매도: 직전 20거래일 안에 분기 실적이 나온 과매도(개별 사유) vs 안 나온 과매도(시장 사유), 나왔으면 악화 vs 개선 (운영 DB 3.2년) (2026-10-31, 사후 관측 · 채택 아님)

설계(결과 보기 전 고정):
  자료: 운영 시세(본표+보충표) · `../dh-q7m3k-data/earnings.db` earnings_q(ticker, rcept_dt 접수일, q_op 분기 영업이익, q_op_prev 전년 동기, mcap_prev, sue = (q_op − q_op_prev)/mcap_prev 추정 — 열 그대로 씀) · 코스피 지수.
  신호일 t 5거래일 격자 · 조건 통과 = t·t+1 양수 종가·거래량, ≥1,000원, 정지 아님, R20 유효 · 과매도 = R20 하위 20%.
  E(t,종목) = 직전 20거래일(t 포함) 안 실적 접수. 나뉨: 악화 = sue < 0 · 개선 = sue ≥ 0(sue 없으면 '발표 있음·부호 없음' 으로만).
  주 비교: 과매도∧E vs 과매도∧¬E (40일 수익·−20% 비율·양수 비율) · 2차: 과매도∧악화 vs 과매도∧개선 · 감도 창 10일 · 칸별(A/BC/D) · 맥락 = 과매도 아닌 종목에서 E vs ¬E, 악화 vs 개선.
  날 단위 동일가중(양쪽 다 있는 날) · 월 블록 2,000(seed 7). 3.2년이라 A 칸은 참고만.
재현: python research/earnings_oversold_3y_20261031.py → research/out_earnings_oversold/ (15초)."""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent; sys.path.insert(0, str(REPO))
import leaderboard as lb
EDB = REPO / ".." / "dh-q7m3k-data" / "earnings.db"
OUT = HERE / "out_earnings_oversold"; OUT.mkdir(exist_ok=True)
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
ks = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index(); con.close()
ec = sqlite3.connect(f"file:{EDB}?mode=ro", uri=True)
E = pd.read_sql("SELECT ticker, rcept_dt, sue, q_op, q_op_prev FROM earnings_q WHERE rcept_dt IS NOT NULL", ec); ec.close()
px["ticker"] = px.ticker.astype(str).str.zfill(6); E["ticker"] = E.ticker.astype(str).str.zfill(6); E["rcept_dt"] = E.rcept_dt.astype(str).str.replace("-", "").str[:8]
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index)
susp = px.pivot_table(index="date", columns="ticker", values="is_suspended", aggfunc="max").reindex(close.index).fillna(0)
dates = list(close.index); N = len(dates); tick = list(close.columns); col = {t: k for k, t in enumerate(tick)}
ks_r20 = ((ks / ks.shift(20) - 1) * 100).reindex(dates)
fwd = (close.shift(-1 - H) / close.shift(-1) - 1) * 100; r20 = close / close.shift(20) - 1
ok_all = (close >= 1000) & (vol.fillna(0) > 0) & (vol.shift(-1).fillna(0) > 0) & (susp == 0) & r20.notna() & close.shift(-1).notna()
dser = pd.Series(range(N), index=pd.to_datetime(dates))
def to_i(d):
    try:
        pos = dser.index.searchsorted(pd.Timestamp(d)); return int(dser.iloc[pos]) if pos < N else None
    except Exception:
        return None
E["i"] = E.rcept_dt.map(to_i); E = E.dropna(subset=["i"]); E["i"] = E.i.astype(int); E = E[E.ticker.isin(col)]
say(f"시세 {close.shape} · 실적 접수 {len(E)}건 · 종목 {E.ticker.nunique()} · sue 있는 건 {E.sue.notna().sum()} (음수 {int((E.sue<0).sum())} · 양수 {int((E.sue>=0).sum())}) · {E.rcept_dt.min()}~{E.rcept_dt.max()} · {time.time()-t0:.0f}s")


def flags(window):
    """날×종목: 최근 window 거래일 안 발표 있음 / 그 발표의 sue 부호(마지막 발표 기준: -1, +1, 0=부호 없음)."""
    has = np.zeros((N, len(tick)), dtype=bool); sgn = np.zeros((N, len(tick)), dtype=np.int8)
    for _, r in E.sort_values("i").iterrows():
        c = col[r.ticker]; a, b = r.i, min(N, r.i + window)
        has[a:b, c] = True; sgn[a:b, c] = (-1 if (r.sue == r.sue and r.sue < 0) else (1 if (r.sue == r.sue) else 0))
    return pd.DataFrame(has, index=dates, columns=tick), pd.DataFrame(sgn, index=dates, columns=tick)


H20, S20 = flags(20); H10, S10 = flags(10)
rows = []
for i in range(25, N - H - 1, STEP):
    d = dates[i]; k = ks_r20.iloc[i]
    if k != k: continue
    ok = ok_all.iloc[i]
    if ok.sum() < 300: continue
    r = r20.iloc[i]; f = fwd.iloc[i]; os_ = ok & (r <= r[ok].quantile(0.20))
    e, sg = H20.iloc[i], S20.iloc[i]; e10 = H10.iloc[i]
    g = dict(os_e=os_ & e, os_n=os_ & ~e, os_bad=os_ & e & (sg == -1), os_good=os_ & e & (sg == 1), os_e10=os_ & e10, os_n10=os_ & ~e10,
             no_e=ok & ~os_ & e, no_n=ok & ~os_ & ~e, no_bad=ok & ~os_ & e & (sg == -1), no_good=ok & ~os_ & e & (sg == 1))
    row = dict(date=d, month=d[:6], ks_r20=float(k), cell=("A" if k <= A_TH else ("D" if k > 5 else "BC")), n_os=int(os_.sum()), all_mean=float(f[ok].mean()))
    for name, m in g.items():
        row[f"n_{name}"] = int(m.sum()); row[name] = float(f[m].mean()) if m.sum() else np.nan
        if name in ("os_e", "os_n", "os_bad", "os_good"):
            row[f"tail_{name}"] = float((f[m] <= -20).mean()) if m.sum() else np.nan; row[f"pos_{name}"] = float((f[m] > 0).mean()) if m.sum() else np.nan
            row[f"r20_{name}"] = float(r[m].mean() * 100) if m.sum() else np.nan
    rows.append(row)
R = pd.DataFrame(rows)
R["d_e"] = R.os_e - R.os_n; R["d_bg"] = R.os_bad - R.os_good; R["d_e10"] = R.os_e10 - R.os_n10; R["d_tail"] = R.tail_os_e - R.tail_os_n; R["d_pos"] = R.pos_os_e - R.pos_os_n
R["d_tail_bg"] = R.tail_os_bad - R.tail_os_good; R["d_noe"] = R.no_e - R.no_n; R["d_nobg"] = R.no_bad - R.no_good
R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
say(f"신호일 {len(R)} ({R.date.iloc[0]}~{R.date.iloc[-1]}) · 과매도 중 20일 안 발표 비율 평균 {(R.n_os_e/R.n_os).mean():.1%} (중앙 {R.n_os_e.median():.0f}종목 · 악화 {R.n_os_bad.median():.0f} · 개선 {R.n_os_good.median():.0f}) · {time.time()-t0:.0f}s")


def tbl(df, label):
    def ci(c):
        d = df.dropna(subset=[c]); lo, hi = block_ci(d[c], d.month); return f"{d[c].mean():+.2f} [{lo:+.2f}, {hi:+.2f}] (n {len(d)})"
    say(f"\n-- {label} · 날 {len(df)} · 과매도∧발표 {df.os_e.mean():+.2f} · 과매도∧없음 {df.os_n.mean():+.2f} · 악화 {df.os_bad.mean():+.2f} · 개선 {df.os_good.mean():+.2f} · 전 종목 {df.all_mean.mean():+.2f}")
    say(f"   발표−없음 {ci('d_e')} · 악화−개선 {ci('d_bg')} · 10일 창 발표−없음 {ci('d_e10')} · R20 발표/없음/악화/개선 {df.r20_os_e.mean():+.1f}/{df.r20_os_n.mean():+.1f}/{df.r20_os_bad.mean():+.1f}/{df.r20_os_good.mean():+.1f}")
    say(f"   −20% 비율 차 발표−없음 {ci('d_tail')} · 악화−개선 {ci('d_tail_bg')} · 양수 비율 차 {ci('d_pos')} · (과매도 아님) 발표−없음 {ci('d_noe')} · 악화−개선 {ci('d_nobg')}")


for label, df in [("전체", R), ("A 급락 뒤", R[R.cell == "A"]), ("B·C", R[R.cell == "BC"]), ("D 급등 뒤", R[R.cell == "D"]), ("2023-08~2024", R[R.date < "20250101"]), ("2025~", R[R.date >= "20250101"])]:
    if len(df): tbl(df, label)
m = R.month.str[4:6]; R["season"] = m.isin(["02", "03", "05", "08", "11"])        # 분기 보고 몰리는 달(접수 기준)
tbl(R[R.season], "실적 시즌 달(2·3·5·8·11월)"); tbl(R[~R.season], "그 밖 달")
(OUT / "run_20261031.txt").write_text("\n".join(LOG), encoding="utf-8"); say(f"\n끝 {time.time()-t0:.0f}s → {OUT}")
