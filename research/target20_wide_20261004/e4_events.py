# -*- coding: utf-8 -*-
"""E4 — 사건 후보: (a) 실적 공시(dart_hist.db, 접수일) (b) 상한가 마감 (c) 60일 만의 첫 252일 신고가+거래량 2배 (d) 무상증자·자사주 취득 공시.
대조 = 같은 목록일의 가드 통과 전 종목(같은 진입·청산). 탐색(판정 아님). python e4_events.py"""
import json, sqlite3
import numpy as np, pandas as pd
from w20lib import *
from orders import *

s = study(choose=False); sim = Sim(s); dates = s.d; T, N = s.T, s.N; c, o, h, l, v, r, ok = s.c, s.o, s.h, s.l, s.v, s.r, s.ok
tix = {t: i for i, t in enumerate(s.tick)}; shares = s.z["shares"].astype(float)
EX = ("hold", "tp")


def first_td(d8):   # d8 이후(포함) 첫 거래일 index
    return int(np.searchsorted(dates, d8))


# ---------------------------------------------------------------- 대조: 날짜별 전 종목(시가 진입) hold·tp
def universe_base(ts):
    rows = []
    for chunk in np.array_split(np.array(sorted(set(ts))), max(1, len(set(ts)) // 40)):
        t = np.concatenate([np.full(int(ok[x].sum()), x) for x in chunk]); k = np.concatenate([np.where(ok[x])[0] for x in chunk])
        e, p = sim.entry("open", t, k); f = e >= 0; ex = sim.exits(e[f], p[f], k[f], EX)
        for xm, d in ex.items():
            g = pd.DataFrame(dict(t=t[f], net=d["net"], d0=d["d0_up"], mae=d["mae"])).groupby("t")
            rows.append(pd.DataFrame(dict(exit=xm, u_mean=g.net.mean() * 100, u_win=g.net.apply(lambda x: (x >= .1999).mean()), u_d0=g.d0.mean(), u_mae=g.mae.mean() * 100)).reset_index())
    return pd.concat(rows, ignore_index=True)


def evaluate(name, t, k, extra=None):
    """사건 신호(t=목록일, k) → 시가 진입 hold·tp, 같은 날 전 종목 대조와 짝."""
    t = np.asarray(t); k = np.asarray(k); m = (t >= s.t0) & (t < s.t1) & ok[np.clip(t, 0, T - 1), k]; t, k = t[m], k[m]
    if extra is not None: extra = extra[m]
    if len(t) == 0: return None
    e, p = sim.entry("open", t, k); f = e >= 0; ex = sim.exits(e[f], p[f], k[f], EX); out = []
    for xm, d in ex.items():
        df = pd.DataFrame(dict(event=name, exit=xm, t=t[f], date=dates[t[f]], ticker=s.tick[k[f]], net=d["net"] * 100, win=d["net"] >= .1999, d0_up=d["d0_up"], mae=d["mae"] * 100, bars=d["bars"]))
        if extra is not None: df["tag"] = extra[f]
        out.append(df)
    return pd.concat(out, ignore_index=True)


def cluster_ci(df, col, by="date", k=2000, seed=7):   # 날짜(또는 묶음) 단위 재추출
    g = df.groupby(by)[col].agg(["sum", "count"]); rng = np.random.default_rng(seed); n = len(g)
    if n < 5: return (np.nan, np.nan)
    idx = rng.integers(0, n, (k, n)); return tuple(np.quantile(g["sum"].values[idx].sum(1) / g["count"].values[idx].sum(1), [.025, .975]))


def report(E, U, label):
    rows = []
    for (ev, xm), g in E.groupby(["event", "exit"]):
        g = g.merge(U[U.exit == xm], on="t", how="left"); g["x"] = g.net - g.u_mean
        for per in ("all", "2024", "2025", "2026"):
            gg = g if per == "all" else g[g.date.str[:4] == per]
            if len(gg) < 20: continue
            lo, hi = cluster_ci(gg, "x")
            rows.append(dict(event=ev, exit=xm, period=per, n=len(gg), n_dates=gg.date.nunique(), win20=gg.win.mean() * 100, u_win20=gg.u_win.mean() * 100, mean=gg.net.mean(), u_mean=gg.u_mean.mean(),
                             excess=gg.x.mean(), ex_lo=lo, ex_hi=hi, d0_up=gg.d0_up.mean() * 100, u_d0=gg.u_d0.mean() * 100, mae=gg.mae.mean(), u_mae=gg.u_mae.mean(), bars=gg.bars.mean()))
    R = pd.DataFrame(rows); R.to_csv(HERE / f"events_{label}.csv", index=False, encoding="utf-8-sig"); return R


# ---------------------------------------------------------------- (a) 실적
def op_item(items):
    for it in items:
        if it.get("account_id") == "dart_OperatingIncomeLoss" and it.get("sj_div") in ("IS", "CIS"): return it
    for it in items:
        if it.get("sj_div") in ("IS", "CIS") and (it.get("account_nm") or "").replace(" ", "") in ("영업이익", "영업이익(손실)", "영업손익", "영업손실"): return it
    return None


def num(x):
    try: return float(str(x).replace(",", "")) if x not in (None, "", "-") else np.nan
    except ValueError: return np.nan


con = sqlite3.connect(f"file:{ROOT / 'research/dart_history/dart_hist.db'}?mode=ro", uri=True)
rep = {}
for stock, year, reprt, fs, rc, items in con.execute("SELECT stock_code, year, reprt, fs, rcept_no, items FROM reports WHERE status='000' AND kept>0 AND api='ALL'"):
    key = (stock, int(year), reprt)
    if key in rep and rep[key]["fs"] == "CFS": continue
    it = op_item(json.loads(items))
    if it is None: continue
    rep[key] = dict(fs=fs, rcept=(rc or "")[:8], th=num(it.get("thstrm_amount")), th_add=num(it.get("thstrm_add_amount")), fr=num(it.get("frmtrm_amount")),
                    fr_q=num(it.get("frmtrm_q_amount")), fr_add=num(it.get("frmtrm_add_amount")))
con.close()
PREV = {"H1": "Q1", "Q3": "H1", "Y": "Q3"}; END = {"Q1": "0331", "H1": "0630", "Q3": "0930", "Y": "1231"}; DL = {"Q1": "0515", "H1": "0814", "Q3": "1114", "Y": "0331"}
ev = []; drop = dict(no_prev=0, window=0, notick=0)
for (stock, year, reprt), x in rep.items():
    if stock not in tix: drop["notick"] += 1; continue
    if reprt == "Y":
        q3 = rep.get((stock, year, "Q3"))
        if not q3: drop["no_prev"] += 1; continue
        q_this = x["th"] - q3["th_add"]; q_prev = x["fr"] - q3["fr_add"]
    else:
        q_this = x["th"]
        q_prev = x["fr_q"]
        if not np.isfinite(q_prev):
            py = rep.get((stock, year - 1, reprt)); q_prev = py["th"] if py else np.nan
        if not np.isfinite(q_prev):
            if reprt == "Q1": q_prev = x["fr_add"]
            else:
                pr = rep.get((stock, year, PREV[reprt])); q_prev = x["fr_add"] - pr["fr_add"] if pr else np.nan
    if not (np.isfinite(q_this) and np.isfinite(q_prev)): drop["no_prev"] += 1; continue
    end = f"{year}{END[reprt]}"; dl = pd.Timestamp(f"{year + (reprt == 'Y')}{DL[reprt]}") + pd.Timedelta(days=7)
    if not (x["rcept"] > end and x["rcept"] <= dl.strftime("%Y%m%d")): drop["window"] += 1; continue
    d0 = first_td(x["rcept"])
    if d0 < 1 or d0 >= T - 2: continue
    k = tix[stock]; mcap = c[d0 - 1, k] * shares[d0 - 1, k]
    if not np.isfinite(mcap) or mcap <= 0: continue
    ev.append(dict(k=k, d0=d0, season=f"{year}{reprt}", q_this=q_this, q_prev=q_prev, sue=(q_this - q_prev) / mcap, react=c[d0 + 1, k] / c[d0 - 1, k] - 1))
EV = pd.DataFrame(ev)
print(f"[실적 사건] 보고서 {len(rep)} → 사건 {len(EV)} (버림: 전년 동기 없음 {drop['no_prev']} · 접수일 창 밖 {drop['window']} · 패널에 없는 종목 {drop['notick']}) · 분기 묶음 {EV.season.nunique()}개 · d0 {dates[EV.d0.min()]}~{dates[EV.d0.max()]}")
print("  묶음별 사건 수:", EV.groupby("season").size().to_dict())
sig = {"실적:전체": np.ones(len(EV), bool), "실적:흑자 전환": ((EV.q_prev <= 0) & (EV.q_this > 0)).values, "실적:증가분≥시총1%": (EV.sue >= .01).values,
       "실적:YoY≥+50%(전년 흑자)": ((EV.q_prev > 0) & (EV.q_this / EV.q_prev - 1 >= .5)).values, "실적:감소분≥시총1%(반대쪽)": (EV.sue <= -.01).values}
parts = []
for nm, m in sig.items():
    g = EV[m]
    parts.append(evaluate(nm + " · d0+1 시가", g.d0.values, g.k.values, g.season.values))
    g2 = g[g.react >= .03]
    parts.append(evaluate(nm + " · 반응 +3% 확인 뒤 d0+2 시가", g2.d0.values + 1, g2.k.values, g2.season.values))
E_a = pd.concat([p_ for p_ in parts if p_ is not None], ignore_index=True)

# ---------------------------------------------------------------- (b)(c)(d)
parts = []
lim = (r >= .295); tt, kk = np.where(lim); parts.append(evaluate("상한가 마감 다음날", tt, kk))
hi252 = rolling(c, 252, 120, "max"); newhigh = np.isfinite(c) & (c >= hi252 - 1e-9)
prior = rolling(lag(newhigh.astype(float)), 60, 60, "max")      # 직전 60일 안에 신고가가 있었나
vr = v / lag(rolling(v, 20, 15))
tt, kk = np.where(newhigh & (prior == 0) & (vr >= 2)); parts.append(evaluate("60일 만의 첫 신고가+거래량 2배", tt, kk))
tt, kk = np.where(newhigh & (prior == 0)); parts.append(evaluate("60일 만의 첫 신고가(거래량 무관)", tt, kk))
oc = sqlite3.connect(f"file:{ROOT.parent / 'dh-q7m3k-data/ohlcv.db'}?mode=ro", uri=True)
de = pd.read_sql("SELECT rcept_dt, ticker, event_type, report_nm FROM dart_events WHERE event_type IN ('bonus','buyback','paid_in','cb')", oc); oc.close()
de = de[~de.report_nm.str.contains("정정")]; de["ticker"] = de.ticker.astype(str).str.zfill(6); de = de[de.ticker.isin(tix)]
for et, nm in (("bonus", "무상증자 공시"), ("buyback", "자사주 취득 공시"), ("paid_in", "유상증자 공시(반대쪽)"), ("cb", "전환사채 공시(반대쪽)")):
    g = de[de.event_type == et].drop_duplicates(["rcept_dt", "ticker"]); tt = np.array([first_td(x) for x in g.rcept_dt]); kk = g.ticker.map(tix).values
    m = tt < T - 2; parts.append(evaluate(nm + " 다음날", tt[m], kk[m]))
E_b = pd.concat([p_ for p_ in parts if p_ is not None], ignore_index=True)

E = pd.concat([E_a, E_b], ignore_index=True); E.to_parquet(HERE / "events_trades.parquet", index=False)
U = universe_base(E.t.unique()); U.to_csv(HERE / "events_universe_base.csv", index=False, encoding="utf-8-sig")
R = report(E, U, "summary")
pd.set_option("display.width", 280); pd.set_option("display.max_rows", 300); pd.set_option("display.max_colwidth", 60)
R["excess_ci"] = R.apply(lambda x: f"{x.excess:+.2f} [{x.ex_lo:+.2f},{x.ex_hi:+.2f}]", axis=1)
cols = ["event", "n", "n_dates", "win20", "u_win20", "mean", "u_mean", "excess_ci", "d0_up", "u_d0", "mae", "u_mae", "bars"]
for xm in EX:
    print(f"\n[사건별 — 청산 {EXITS[xm]} · 전체 기간 · win20 = 실제 청산 +20% 비율% · u_ = 같은 날 전 종목 · excess CI = 날짜 묶음 재추출]")
    print(R[(R.period == "all") & (R.exit == xm)][cols].round(2).to_string(index=False))
Y = R[R.period != "all"].pivot_table(index=["event", "exit"], columns="period", values=["n", "win20", "excess"]).round(2)
print("\n[연도별 n · win20 · 대조 대비 초과%p]"); print(Y.to_string())
# 실적: 분기 묶음별(같은 묶음 안은 사실상 한 번의 시장)
Ea = E_a.merge(U, on=["t", "exit"], how="left"); Ea["x"] = Ea.net - Ea.u_mean
S = Ea[Ea.exit == "hold"].pivot_table(index="event", columns="tag", values="x", aggfunc="mean").round(2)
print("\n[실적 — 분기 묶음별 대조 대비 초과%p(20봉 보유)]"); print(S.to_string())
print("\n[실적 — 묶음 평균의 평균 · 양(+)인 묶음 수]"); print(pd.DataFrame(dict(mean_of_seasons=S.mean(axis=1).round(2), pos=(S > 0).sum(axis=1), n_seasons=S.notna().sum(axis=1))).to_string())
