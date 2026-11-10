# -*- coding: utf-8 -*-
"""사후 점검(결과 본 뒤 추가 — '사후' 표기) — `event_after_20261110.py` 가 후보로 낸 bb_trust_new(자사주 신탁계약 체결) 가 진짜인지.
① 연도별·시장별 ② 경로(h=1·3·5·10·20·40 초과) ③ 공시 반응(t−1→t+1) ④ 가짜 날짜 대조(같은 종목의 60거래일 전·120거래일 전) ⑤ 사건 단위(날 묶지 않음) ⑥ 겹침 제거(같은 종목 직전 60거래일 안 체결 공시가 또 있으면 제외)
읽기 전용. 재현: python research/event_after_checks_20261110.py → research/out_event_after/checks.txt"""
import sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
import leaderboard as lb
from lib import tenyr
tenyr.reset_rng(); LOG = []
pd.set_option("display.width", 240)


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


con = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
px = pd.concat([pd.read_sql("SELECT ticker,date,close,volume,is_suspended,market FROM daily_ohlcv", con),
                pd.read_sql("SELECT ticker,date,close,volume,is_suspended,NULL AS market FROM daily_ohlcv_extra", con)], ignore_index=True)
ev = pd.read_sql("SELECT rcept_dt, ticker, event_type, report_nm, market FROM dart_events WHERE event_type='buyback'", con); con.close()
px["ticker"] = px.ticker.astype(str).str.zfill(6); ev["ticker"] = ev.ticker.astype(str).str.zfill(6)
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index).fillna(0)
susp = px.pivot_table(index="date", columns="ticker", values="is_suspended", aggfunc="max").reindex(close.index).fillna(0)
dates = [str(d) for d in close.index]; N = len(dates); tick = list(close.columns); col = {t: k for k, t in enumerate(tick)}
C = close.values; V = vol.values; S = susp.values


def sh(a, k):
    out = np.full_like(a, np.nan, dtype=float)
    if k >= 0: out[:N - k] = a[k:]
    else: out[-k:] = a[:N + k]
    return out


C1 = sh(C, 1); V1 = sh(V, 1); Cm1 = sh(C, -1)
base_ok = (C >= 1000) & (V > 0) & (np.nan_to_num(V1) > 0) & (S == 0) & ~np.isnan(C1)
HS = (1, 3, 5, 10, 20, 40)
RET = {h: (sh(C, 1 + h) / C1 - 1) * 100 for h in HS}
REACT = (C1 / Cm1 - 1) * 100            # t−1 종가 → t+1 종가(공시 반응, 진입 전에 이미 오른 몫)
dts = pd.to_datetime(dates)
ev = ev[ev.report_nm.fillna("").str.contains("신탁계약체결") & ~ev.report_nm.fillna("").str.strip().str.startswith("[")]
ev["i"] = [int(p) if p < N else None for p in dts.searchsorted(pd.to_datetime(ev.rcept_dt.astype(str)))]
ev = ev.dropna(subset=["i"]); ev["i"] = ev.i.astype(int); ev = ev[ev.ticker.isin(col)].drop_duplicates(["ticker", "i"]).sort_values(["ticker", "i"])
ev["prev_gap"] = ev.groupby("ticker").i.diff()
say(f"체결 원공시 {len(ev)} · 종목 {ev.ticker.nunique()} · 직전 60거래일 안 또 있음 {(ev.prev_gap <= 60).sum()}")


def rows_for(evs, offset=0, hs=HS):
    out = []
    for i0, g in evs.groupby("i"):
        i = i0 + offset
        if i < 1 or i >= N: continue
        idx = np.array([col[t] for t in g.ticker]); row = dict(date=dates[i], month=dates[i][:6], year=dates[i][:4], n=0)
        for h in hs:
            ok = base_ok[i] & ~np.isnan(RET[h][i])
            if ok.sum() < 300: continue
            s = idx[ok[idx]]
            if len(s) == 0: continue
            r = RET[h][i]; row["n"] = max(row["n"], len(s))
            row[f"x{h}"] = r[s].mean() - r[ok].mean()
            if h == 5:
                row["d_up5"] = (r[s] > 0).mean() * 100 - (r[ok] > 0).mean() * 100
                okr = ok & ~np.isnan(REACT[i]); sr = idx[okr[idx]]
                if len(sr): row["react"] = REACT[i][sr].mean() - REACT[i][okr].mean()
        if row["n"]: out.append(row)
    return pd.DataFrame(out)


def line(lab, g, c):
    g = g.dropna(subset=[c])
    if len(g) < 10: return f"{lab}: 사건일 {len(g)} (적음)"
    lo, hi = tenyr.block_ci(g[c], g.month)
    return f"{lab}: 사건일 {len(g)} · {g[c].mean():+.2f} [{lo:+.2f}, {hi:+.2f}]"


D = rows_for(ev)
say("\n① 연도별 up5 차(%p) / 40일 초과(%p)")
for y, g in D.groupby("year"):
    say("  ", line(f"{y} up5차", g, "d_up5"), "|", line("40일", g, "x40"))
say("\n①' 시장별(공시 표의 market)")
for mk, g in ev.groupby(ev.market.fillna("?")):
    Dm = rows_for(g)
    say("  ", line(f"{mk} up5차", Dm, "d_up5"), "|", line("40일", Dm, "x40"))
say("\n② 경로 — 진입(t+1 종가) 뒤 h거래일 초과수익(%p, 같은 날 유니버스 대비)")
for h in HS:
    say("  ", line(f"h={h}", D, f"x{h}"))
say("\n③ 공시 반응 — t−1 종가 → t+1 종가 초과(진입 전에 이미 오른 몫, 못 먹는 부분)")
say("  ", line("반응", D, "react"))
say("\n④ 가짜 날짜 대조 — 같은 종목을 공시 60·120거래일 '전'에 샀다면")
for off in (-60, -120):
    P = rows_for(ev, offset=off)
    say("  ", line(f"{off}일 up5차", P, "d_up5"), "|", line("40일", P, "x40"))
say("\n⑤ 사건 단위(날로 묶지 않음) — 참고")
allr = []
for _, r in ev.iterrows():
    i = r.i; k = col[r.ticker]
    ok5 = base_ok[i] & ~np.isnan(RET[5][i])
    if ok5.sum() < 300 or not ok5[k]: continue
    allr.append(dict(up=RET[5][i][k] > 0, base=(RET[5][i][ok5] > 0).mean(), x5=RET[5][i][k] - RET[5][i][ok5].mean(),
                     x40=(RET[40][i][k] - RET[40][i][base_ok[i] & ~np.isnan(RET[40][i])].mean()) if not np.isnan(RET[40][i][k]) else np.nan, r40=RET[40][i][k]))
E = pd.DataFrame(allr)
say(f"   사건 {len(E)} · 5일째 진입가 위 {E.up.mean()*100:.1f}% (같은 날 기준율 평균 {E.base.mean()*100:.1f}%) · 5일 초과 평균 {E.x5.mean():+.2f} 중앙 {E.x5.median():+.2f} · 40일 초과 평균 {E.x40.mean():+.2f} 중앙 {E.x40.median():+.2f} · 40일 초과>0 비율 {(E.x40.dropna()>0).mean()*100:.1f}% · 40일 −20% 이하 {(E.r40.dropna()<=-20).mean()*100:.1f}%")
say("\n⑥ 겹침 제거 — 같은 종목 직전 60거래일 안에 체결 공시가 또 있던 건 제외")
D6 = rows_for(ev[~(ev.prev_gap <= 60)])
say("  ", line("up5차", D6, "d_up5"), "|", line("40일", D6, "x40"))
(HERE / "out_event_after" / "checks.txt").write_text("\n".join(LOG), encoding="utf-8")
