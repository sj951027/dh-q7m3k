# -*- coding: utf-8 -*-
"""공시(사건) 뒤 5일·40일 — 조건은 `EVENT_AFTER_20261110.md` §0 (2026-11-10 21:55 고정). 읽기 전용, 관측·채택 아님.

사건 8종(원공시만) · 사건일 t = 접수일 또는 다음 첫 거래일 · 진입 t+1 종가 · 같은 날 유니버스(종가≥1,000·거래량>0·정지 아님) 대비
up5 차 / T1(5일 초과) / T4(40일 초과) · 날 단위 동일가중 · 월 블록 2,000 seed 7(tenyr.block_ci) · 앞/뒤 2025-01-01.
재현: python research/event_after_20261110.py → research/out_event_after/ (약 1분)."""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
import leaderboard as lb
from lib import tenyr

OUT = HERE / "out_event_after"; OUT.mkdir(exist_ok=True)
H5, H40 = 5, 40; SPLIT = "20250101"; A_TH, D_TH = -5.0, 5.0; M = 8; ALPHA_C = 0.05 / (2 * M)
CLASSES = ["bb_trust_new", "bb_trust_end", "bb_direct", "bb_sell", "paid_in", "cb", "bonus", "reduction"]
pd.set_option("display.width", 260); LOG = []
tenyr.reset_rng()


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


def block_q(vals, months, qs, k=tenyr.K):
    """tenyr.block_ci 와 같은 월 블록 재표집 — 보정 구간(임의 분위)용. 난수는 tenyr.rng 를 쓴다."""
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    if len(um) < 2:
        return [np.nan] * len(qs)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in tenyr.rng.choice(um, len(um))]).mean() for _ in range(k)]
    return [float(np.percentile(ms, q)) for q in qs]


def classify(et, nm):
    if et == "buyback":
        if "신탁계약체결" in nm: return "bb_trust_new"
        if "신탁계약해지" in nm: return "bb_trust_end"
        return "bb_direct"
    return {"buyback_sell": "bb_sell", "paid_in": "paid_in", "cb": "cb", "bonus": "bonus", "reduction": "reduction"}.get(et)


t0 = time.time()
con = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
px = pd.concat([pd.read_sql("SELECT ticker,date,close,volume,is_suspended FROM daily_ohlcv", con),
                pd.read_sql("SELECT ticker,date,close,volume,is_suspended FROM daily_ohlcv_extra", con)], ignore_index=True)
ev = pd.read_sql("SELECT rcept_no, rcept_dt, ticker, event_type, report_nm FROM dart_events", con)
ks = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index(); con.close()
px["ticker"] = px.ticker.astype(str).str.zfill(6); ev["ticker"] = ev.ticker.astype(str).str.zfill(6)
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index).fillna(0)
susp = px.pivot_table(index="date", columns="ticker", values="is_suspended", aggfunc="max").reindex(close.index).fillna(0); del px
dates = [str(d) for d in close.index]; N = len(dates); tick = list(close.columns); col = {t: k for k, t in enumerate(tick)}
C = close.values; V = vol.values; S = susp.values
ks_r20 = ((ks / ks.shift(20) - 1) * 100); ks_r20.index = ks_r20.index.astype(str); ks_r20 = ks_r20.reindex(dates).values


def shift(a, k):
    out = np.full_like(a, np.nan, dtype=float); out[:N - k] = a[k:]; return out


C1, C6, C41 = shift(C, 1), shift(C, 1 + H5), shift(C, 1 + H40); V1 = shift(V, 1)
base_ok = (C >= 1000) & (V > 0) & (np.nan_to_num(V1) > 0) & (S == 0) & ~np.isnan(C1)
OK5 = base_ok & ~np.isnan(C6); OK40 = OK5 & ~np.isnan(C41)
with np.errstate(invalid="ignore", divide="ignore"):
    R5 = (C6 / C1 - 1) * 100; R40 = (C41 / C1 - 1) * 100
    R20 = np.full_like(C, np.nan); R20[20:] = C[20:] / C[:-20] - 1
UP5 = (R5 > 0).astype(float)
# 같은 날 유니버스
U = {}
for i in range(N):
    o5, o40 = OK5[i], OK40[i]
    if o5.sum() < 300:
        continue
    r20 = R20[i]; v = o5 & ~np.isnan(r20)
    os_ = np.zeros(len(tick), bool)
    if v.sum() >= 300:
        os_ = v & (r20 <= np.quantile(r20[v], 0.20))
    d = dict(n5=int(o5.sum()), up5=UP5[i][o5].mean() * 100, r5=R5[i][o5].mean(), os=os_)
    if o40.sum() >= 300:
        m40 = R40[i][o40].mean()
        d.update(n40=int(o40.sum()), r40=m40, tail=(R40[i][o40] <= -20).mean() * 100, both=((UP5[i][o40] > 0) & (R40[i][o40] > m40)).mean() * 100,
                 r40_os=(R40[i][o40 & os_].mean() if (o40 & os_).sum() >= 30 else np.nan), r40_nos=(R40[i][o40 & ~os_].mean() if (o40 & ~os_).sum() >= 30 else np.nan))
    U[i] = d
say(f"시세 {C.shape} · {dates[0]}~{dates[-1]} · 유니버스 유효일 {len(U)} · {time.time()-t0:.0f}s")

# 사건
dts = pd.to_datetime(dates)
def to_i(d):
    # [11/10 22:40 정정 — Codex 대조] 시세 시작일(2023-06-26)보다 앞선 공시는 제외한다. 하한을 안 보면 searchsorted 가 전부 첫 시세일로 몰아넣는다(원공시 83건).
    ts = pd.Timestamp(str(d))
    if ts < dts[0]:
        return None
    pos = dts.searchsorted(ts)
    return int(pos) if pos < N else None
ev["cls"] = [classify(a, b or "") for a, b in zip(ev.event_type, ev.report_nm.fillna(""))]
ev = ev.dropna(subset=["cls"])
ev["orig"] = ~ev.report_nm.fillna("").str.strip().str.startswith("[")
ev["i"] = ev.rcept_dt.map(to_i); ev = ev.dropna(subset=["i"]); ev["i"] = ev.i.astype(int)
ev = ev[ev.ticker.isin(col)]
say("공시 건수(원공시/정정 포함):", {c: (int(((ev.cls == c) & ev.orig).sum()), int((ev.cls == c).sum())) for c in CLASSES})


def day_rows(evs, tag):
    evs = evs.drop_duplicates(["ticker", "cls", "i"])
    rows = []
    for (c, i), g in evs.groupby(["cls", "i"]):
        u = U.get(i)
        if u is None:
            continue
        idx = np.array([col[t] for t in g.ticker]); s5 = idx[OK5[i][idx]]
        if len(s5) == 0:
            continue
        d = dates[i]; kr = ks_r20[i]
        row = dict(tag=tag, cls=c, date=d, month=d[:6], half=("앞" if d < SPLIT else "뒤"), i=i, n=len(s5),
                   cell=("A" if kr <= A_TH else "D" if kr > D_TH else "BC") if kr == kr else None,
                   up5=UP5[i][s5].mean() * 100, base=u["up5"], d_up5=UP5[i][s5].mean() * 100 - u["up5"], t1=R5[i][s5].mean() - u["r5"])
        s40 = idx[OK40[i][idx]]
        if len(s40) and "r40" in u:
            r = R40[i][s40]
            row.update(n40=len(s40), r40=r.mean(), t4=r.mean() - u["r40"], d_tail=(r <= -20).mean() * 100 - u["tail"],
                       d_both=((UP5[i][s40] > 0) & (r > u["r40"])).mean() * 100 - u["both"])
            o = u["os"][s40]
            if o.any() and u["r40_os"] == u["r40_os"]:
                row.update(n_os=int(o.sum()), t4_os=r[o].mean() - u["r40_os"])
            if (~o).any() and u["r40_nos"] == u["r40_nos"]:
                row.update(n_nos=int((~o).sum()), t4_nos=r[~o].mean() - u["r40_nos"])
        rows.append(row)
    return pd.DataFrame(rows)


D = day_rows(ev[ev.orig], "orig"); D2 = day_rows(ev, "with_corr")
pd.concat([D, D2]).to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
QC = [100 * ALPHA_C / 2, 100 * (1 - ALPHA_C / 2)]


def summarize(Dx):
    out = []
    for c in CLASSES:
        g = Dx[Dx.cls == c]
        if g.empty:
            continue
        lo, hi = tenyr.block_ci(g.d_up5, g.month); clo, chi = block_q(g.d_up5, g.month, QC)
        t1lo, t1hi = tenyr.block_ci(g.t1, g.month); t1clo, t1chi = block_q(g.t1, g.month, QC)
        g4 = g.dropna(subset=["t4"]); t4lo, t4hi = tenyr.block_ci(g4.t4, g4.month) if len(g4) else (np.nan, np.nan)
        fa, fb = g[g.half == "앞"].d_up5.mean(), g[g.half == "뒤"].d_up5.mean()
        cand = (lo > 5) and (len(g) >= 200) and (fa * fb > 0) and (clo > 0) and not (t4hi < 0)
        out.append(dict(cls=c, 사건=int(g.n.sum()), 사건일=len(g), up5=g.up5.mean(), 기준율=g.base.mean(), up5차=g.d_up5.mean(), 하한=lo, 상한=hi, 보정하한=clo, 보정상한=chi,
                        앞=fa, 뒤=fb, T1=g.t1.mean(), T1하한=t1lo, T1상한=t1hi, T1보정하한=t1clo, T1보정상한=t1chi,
                        사건일40=len(g4), T4=g4.t4.mean() if len(g4) else np.nan, T4하한=t4lo, T4상한=t4hi,
                        T4앞=g4[g4.half == "앞"].t4.mean(), T4뒤=g4[g4.half == "뒤"].t4.mean(),
                        꼬리차=g4.d_tail.mean() if len(g4) else np.nan, 둘다차=g4.d_both.mean() if len(g4) else np.nan, 후보=cand))
    return pd.DataFrame(out)


T = summarize(D); T.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
say("\n### 표 1 — 원공시만 (주 판정)")
say(T.round(2).to_string(index=False))
T2 = summarize(D2); T2.to_csv(OUT / "summary_with_corrections.csv", index=False, encoding="utf-8-sig")
say("\n### 감도 — 정정 공시 포함")
say(T2[["cls", "사건", "사건일", "up5차", "하한", "상한", "T1", "T4", "T4하한", "T4상한", "후보"]].round(2).to_string(index=False))

say("\n### 표 2 — 재측정(관측): 자사주 3종 칸별·과매도 안/밖 T4")
rows = []
for c in ("bb_trust_new", "bb_trust_end", "bb_direct"):
    g = D[(D.cls == c)].dropna(subset=["t4"])
    for lab, sub, colname in ([("전체", g, "t4")] + [(f"칸 {k}", g[g.cell == k], "t4") for k in ("A", "BC", "D")]
                              + [("과매도 안(vs 과매도 유니버스)", g.dropna(subset=["t4_os"]) if "t4_os" in g else g.iloc[:0], "t4_os"),
                                 ("과매도 밖(vs 그 밖 유니버스)", g.dropna(subset=["t4_nos"]) if "t4_nos" in g else g.iloc[:0], "t4_nos")]):
        if len(sub) < 5:
            rows.append(dict(cls=c, 범위=lab, 사건일=len(sub))); continue
        lo, hi = tenyr.block_ci(sub[colname], sub.month)
        rows.append(dict(cls=c, 범위=lab, 사건일=len(sub), 월수=sub.month.nunique(), T4=sub[colname].mean(), 하한=lo, 상한=hi, 양수비율=(sub[colname] > 0).mean() * 100))
Cx = pd.DataFrame(rows); Cx.to_csv(OUT / "cells.csv", index=False, encoding="utf-8-sig")
say(Cx.round(2).to_string(index=False))
say(f"\n후보: {list(T[T.후보].cls) or '없음'} · {time.time()-t0:.0f}s")
(OUT / "stdout.txt").write_text("\n".join(LOG), encoding="utf-8")
