# -*- coding: utf-8 -*-
"""사건 뒤 심층 — 조건은 `EVENT_AFTER_DEEP_20261110.md` §0 (2026-11-10 22:35 고정). 읽기 전용, 관측·채택 아님.
자사주 신탁계약 체결 원공시 사건 1건 = 1행 · 조건 9개(같은 날 유니버스 백분위 하/중/상) · 발견(<2025-01-01) → 확인(이후).
재현: python research/event_after_deep_20261110.py → research/out_event_after/deep_*.csv·deep_stdout.txt"""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
import leaderboard as lb
from lib import tenyr
tenyr.reset_rng(); LOG = []; SPLIT = "20250101"
OUT = HERE / "out_event_after"; OUT.mkdir(exist_ok=True)
pd.set_option("display.width", 260)


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


t0 = time.time()
con = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
xcols = [r[1] for r in con.execute("pragma table_info(daily_ohlcv_extra)")]
sh_x = "shares" if "shares" in xcols else "NULL AS shares"
px = pd.concat([pd.read_sql("SELECT ticker,date,close,volume,is_suspended,shares FROM daily_ohlcv", con),
                pd.read_sql(f"SELECT ticker,date,close,volume,is_suspended,{sh_x} FROM daily_ohlcv_extra", con)], ignore_index=True)
ev = pd.read_sql("SELECT rcept_dt, ticker, report_nm, market FROM dart_events WHERE event_type='buyback'", con); con.close()
px["ticker"] = px.ticker.astype(str).str.zfill(6); ev["ticker"] = ev.ticker.astype(str).str.zfill(6)
piv = lambda v, agg="last": px.pivot_table(index="date", columns="ticker", values=v, aggfunc=agg).sort_index()
close = piv("close"); close = close.where(close > 0)
vol = piv("volume").reindex(close.index).fillna(0); susp = piv("is_suspended", "max").reindex(close.index).fillna(0); shares = piv("shares").reindex(close.index)
dates = [str(d) for d in close.index]; N = len(dates); tick = list(close.columns); col = {t: k for k, t in enumerate(tick)}
ret = close.pct_change(fill_method=None)
F = dict(mcap=(close * shares).values, amt20=(close * vol).rolling(20).mean().values,
         react=(close.shift(-1) / close.shift(1) - 1).values, r20=(close.shift(1) / close.shift(21) - 1).values, r60=(close.shift(1) / close.shift(61) - 1).values,
         vol20=ret.rolling(20).std().shift(1).values, vspike=(vol.shift(-1) / vol.rolling(20).mean().shift(1)).values)
C = close.values; V = vol.values; S = susp.values


def sh(a, k):
    out = np.full_like(a, np.nan, dtype=float); out[:N - k] = a[k:]; return out


C1 = sh(C, 1); V1 = sh(V, 1)
base_ok = (C >= 1000) & (V > 0) & (np.nan_to_num(V1) > 0) & (S == 0) & ~np.isnan(C1)
with np.errstate(invalid="ignore", divide="ignore"):
    R5 = (sh(C, 6) / C1 - 1) * 100; R40 = (sh(C, 41) / C1 - 1) * 100
dts = pd.to_datetime(dates)
ev = ev[ev.report_nm.fillna("").str.contains("신탁계약체결") & ~ev.report_nm.fillna("").str.strip().str.startswith("[")]
ev["i"] = [int(p) if p < N else None for p in dts.searchsorted(pd.to_datetime(ev.rcept_dt.astype(str)))]
ev = ev.dropna(subset=["i"]); ev["i"] = ev.i.astype(int); ev = ev[ev.ticker.isin(col)].drop_duplicates(["ticker", "i"]).sort_values(["ticker", "i"])
ev["gap"] = ev.groupby("ticker").i.diff()

rows = []
for r in ev.itertuples(index=False):
    i, k = r.i, col[r.ticker]
    ok5 = base_ok[i] & ~np.isnan(R5[i])
    if ok5.sum() < 300 or not ok5[k]:
        continue
    ok40 = base_ok[i] & ~np.isnan(R40[i])
    row = dict(ticker=r.ticker, date=dates[i], month=dates[i][:6], period=("발견" if dates[i] < SPLIT else "확인"), market=r.market,
               repeat=("반복" if (r.gap == r.gap and r.gap <= 250) else "처음"),
               dup5=(100.0 if R5[i][k] > 0 else 0.0) - (R5[i][ok5] > 0).mean() * 100,
               x40=(R40[i][k] - R40[i][ok40].mean()) if (ok40[k] and ok40.sum() >= 300) else np.nan,
               mcap_raw=F["mcap"][i][k], amt20_raw=F["amt20"][i][k])
    for f, A in F.items():
        v = A[i][k]; u = A[i][base_ok[i] & ~np.isnan(A[i])]
        p = (u < v).mean() if (v == v and len(u) >= 300) else np.nan
        row[f + "_pct"] = p
        row[f] = (None if p != p else "하" if p < 1 / 3 else "상" if p > 2 / 3 else "중")
    rows.append(row)
E = pd.DataFrame(rows); E.to_csv(OUT / "deep_events.csv", index=False, encoding="utf-8-sig")
say(f"사건 {len(E)} (발견 {(E.period=='발견').sum()} · 확인 {(E.period=='확인').sum()}) · x40 있는 사건 {E.x40.notna().sum()} · {time.time()-t0:.0f}s")

say("\n### 실행 가능성 — 사건 종목의 규모·유동성 [§0 고정 문턱]")
say(f"시총 중앙값 {E.mcap_raw.median()/1e8:,.0f}억 · 유니버스 백분위 중앙 {E.mcap_pct.median()*100:.0f} (하 {(E.mcap=='하').mean()*100:.0f}% · 중 {(E.mcap=='중').mean()*100:.0f}% · 상 {(E.mcap=='상').mean()*100:.0f}%)")
say(f"거래대금(20일 평균) 중앙값 {E.amt20_raw.median()/1e8:,.1f}억 · 백분위 중앙 {E.amt20_pct.median()*100:.0f} (하 {(E.amt20=='하').mean()*100:.0f}% · 중 {(E.amt20=='중').mean()*100:.0f}% · 상 {(E.amt20=='상').mean()*100:.0f}%)")


def ci_line(lab, g):
    a = g.dropna(subset=["dup5"]); b = g.dropna(subset=["x40"])
    l1, h1 = tenyr.block_ci(a.dup5, a.month); l2, h2 = tenyr.block_ci(b.x40, b.month)
    return f"{lab}: 사건 {len(a)} ({len(a)/len(E)*100:.0f}%) · dup5 {a.dup5.mean():+.2f} [{l1:+.2f}, {h1:+.2f}] · x40 {b.x40.mean():+.2f} [{l2:+.2f}, {h2:+.2f}] (n={len(b)}) · x40 중앙 {b.x40.median():+.2f}"


say(ci_line("전체(사건 단위)", E))
for th, lab in ((5e8, "거래대금 ≥ 5억"), (2e9, "거래대금 ≥ 20억")):
    say(ci_line(lab, E[E.amt20_raw >= th]))
say(ci_line("거래대금 < 5억", E[E.amt20_raw < 5e8]))

CONDS = [("mcap", "시총", "상", "하"), ("amt20", "거래대금", "상", "하"), ("react", "공시 반응", "상", "하"), ("r20", "직전 20일 수익", "상", "하"), ("r60", "직전 60일 수익", "상", "하"),
         ("vol20", "변동성", "상", "하"), ("vspike", "거래량 급증", "상", "하"), ("market", "시장(코스닥−코스피)", "K", "Y"), ("repeat", "반복(처음−반복)", "처음", "반복")]
tests = []
for key, name, hi, lo in CONDS:
    for tgt in ("x40", "dup5"):
        rec = dict(조건=name, 목표=tgt)
        for per in ("발견", "확인"):
            g = E[(E.period == per)].dropna(subset=[tgt])
            a, b = g[g[key] == hi], g[g[key] == lo]
            if len(a) < 20 or len(b) < 20:
                rec.update({f"{per}_n": f"{len(a)}/{len(b)}", f"{per}_차": np.nan}); continue
            d = a[tgt].mean() - b[tgt].mean(); l, h = tenyr.diff_ci(a, b, col=tgt)
            rec.update({f"{per}_n": f"{len(a)}/{len(b)}", f"{per}_상": a[tgt].mean(), f"{per}_하": b[tgt].mean(), f"{per}_차": d, f"{per}_lo": l, f"{per}_hi": h})
        found = rec.get("발견_lo", np.nan) == rec.get("발견_lo", np.nan) and (rec["발견_lo"] > 0 or rec["발견_hi"] < 0)
        conf = found and rec.get("확인_lo", np.nan) == rec.get("확인_lo", np.nan) and (rec["확인_차"] * rec["발견_차"] > 0) and (rec["확인_lo"] > 0 or rec["확인_hi"] < 0)
        rec["판정"] = "살아남음" if conf else ("우연 후보(버림)" if found else "—")
        tests.append(rec)
T = pd.DataFrame(tests); T.to_csv(OUT / "deep_tests.csv", index=False, encoding="utf-8-sig")
say("\n### 조건 9 × 목표 2 — 발견(<2025) → 확인(2025~)  [차 = 상−하 / 코스닥−코스피 / 처음−반복]")
say(T.round(2).to_string(index=False))

say("\n### 읽기용 — 전체 기간 칸별 평균(판정 아님)")
for key, name, hi, lo in CONDS:
    parts = []
    for lv in (["하", "중", "상"] if hi == "상" else [lo, hi]):
        g = E[E[key] == lv]
        parts.append(f"{lv}: n={len(g)} dup5 {g.dup5.mean():+.1f} x40 {g.x40.mean():+.1f}")
    say(f"  {name} — " + " | ".join(parts))
say(f"\n살아남은 조건: {[(r.조건, r.목표) for r in T.itertuples() if r.판정 == '살아남음'] or '없음'} · 우연 후보: {[(r.조건, r.목표) for r in T.itertuples() if r.판정.startswith('우연')] or '없음'} · {time.time()-t0:.0f}s")
(OUT / "deep_stdout.txt").write_text("\n".join(LOG), encoding="utf-8")
