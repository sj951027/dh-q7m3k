# -*- coding: utf-8 -*-
"""E4c — 실적 시험을 '처음 알려진 날' 기준으로 다시 (2026-10-04, 사용자 승인으로 DART 공시목록 날짜 수집 후).
날짜 3종: ① 정기보고서 원본 접수일(정정본 아님) ② 잠정실적(공정공시)·손익구조 변동 공시가 있으면 그 날 ③ 둘 중 이른 날 = 처음 알려진 날.
놀람 값은 정기보고서 숫자(잠정치 ≈ 확정치로 가정 — 근사). 진입 = 그 날 이후 첫 거래일(d0)의 다음날 시가. 대조 = 같은 날 전 종목.
python e4c_first_disclosure.py"""
import io, contextlib, importlib, re, sqlite3
import numpy as np, pandas as pd
from w20lib import *

with contextlib.redirect_stdout(io.StringIO()):
    e4 = importlib.import_module("e4_events")
s = e4.s; T, N = s.T, s.N; c, o, ok, ff = s.c, s.o, s.ok, s.ff; dates = s.d; tix = e4.tix; shares = e4.shares; rep = e4.rep
con = sqlite3.connect(f"file:{ROOT / 'research/dart_history/dart_hist.db'}?mode=ro", uri=True)
F = pd.read_sql("SELECT kind, stock_code, report_nm, rcept_dt FROM filings", con); con.close()
F["report_nm"] = F.report_nm.str.strip(); F["amend"] = F.report_nm.str.contains("정정")
print("[수집된 공시] ", F.groupby("kind").size().to_dict(), "· 기간", F.rcept_dt.min(), "~", F.rcept_dt.max())
# 정기보고서: 제목의 (YYYY.MM) → (연도, 보고서 종류). 12월 결산만.
A = F[F.kind.isin(["A001", "A002", "A003"])].copy(); m = A.report_nm.str.extract(r"\((\d{4})\.(\d{2})\)")
A["year"] = pd.to_numeric(m[0], errors="coerce"); A["mm"] = m[1]; A["reprt"] = A.mm.map({"03": "Q1", "06": "H1", "09": "Q3", "12": "Y"})
A = A.dropna(subset=["year", "reprt"]); A["year"] = A.year.astype(int)
A = A[((A.kind == "A001") & (A.reprt == "Y")) | ((A.kind == "A002") & (A.reprt == "H1")) | ((A.kind == "A003") & A.reprt.isin(["Q1", "Q3"]))]
orig = A.sort_values(["amend", "rcept_dt"]).groupby(["stock_code", "year", "reprt"]).first()          # 원본(정정 아님) 가운데 가장 이른 것, 없으면 가장 이른 정정본
P = F[(F.kind == "I002") & F.report_nm.str.contains("잠정")]; Sx = F[F.kind == "I001"]
pre_by = {k: np.sort(g.rcept_dt.values) for k, g in P.groupby("stock_code")}; st_by = {k: np.sort(g.rcept_dt.values) for k, g in Sx.groupby("stock_code")}
END = e4.END; PREV = e4.PREV


def first_in(arr, lo, hi):   # lo < d <= hi 인 가장 이른 날
    if arr is None: return None
    i = np.searchsorted(arr, lo, side="right")
    return arr[i] if i < len(arr) and arr[i] <= hi else None


rows = []
for (stock, year, reprt), x in rep.items():
    if stock not in tix or (stock, year, reprt) not in orig.index: continue
    if reprt == "Y":
        q3 = rep.get((stock, year, "Q3"))
        if not q3: continue
        q_this = x["th"] - q3["th_add"]; q_prev = x["fr"] - q3["fr_add"]
    else:
        q_this = x["th"]; q_prev = x["fr_q"]
        if not np.isfinite(q_prev):
            py = rep.get((stock, year - 1, reprt)); q_prev = py["th"] if py else np.nan
        if not np.isfinite(q_prev):
            if reprt == "Q1": q_prev = x["fr_add"]
            else:
                pr = rep.get((stock, year, PREV[reprt])); q_prev = x["fr_add"] - pr["fr_add"] if pr else np.nan
    if not (np.isfinite(q_this) and np.isfinite(q_prev)): continue
    end = f"{year}{END[reprt]}"; d_rep = orig.loc[(stock, year, reprt), "rcept_dt"]
    if not (d_rep > end and d_rep <= (pd.Timestamp(end) + pd.Timedelta(days=130)).strftime("%Y%m%d")): continue     # 원본이 분기 말 뒤 130일 안
    d_pre = first_in(pre_by.get(stock), end, d_rep); d_st = first_in(st_by.get(stock), end, d_rep) if reprt == "Y" else None
    cand = [d for d in (d_pre, d_st, d_rep) if d]; d_first = min(cand)
    rows.append(dict(stock=stock, k=tix[stock], season=f"{year}{reprt}", q_this=q_this, q_prev=q_prev, d_rep=d_rep, d_pre=d_pre or "", d_st=d_st or "", d_first=d_first,
                     early=d_first < d_rep, stored=x["rcept"]))
EV = pd.DataFrame(rows)
print(f"[사건] {len(EV)}건 · 분기 묶음 {EV.season.nunique()} · 원본 접수일이 저장된(정정본) 접수일과 다른 것 {int((EV.d_rep != EV.stored).sum())}건 "
      f"· 정기보고서보다 먼저 알려진 것 {int(EV.early.sum())}건({EV.early.mean():.0%}: 잠정실적 {int((EV.d_pre != '').sum())} · 손익구조 변동 {int((EV.d_st != '').sum())})")


def attach(EV, col):
    """날짜 열(col) 기준 d0·놀람·시총 순위·보유 5/20/60봉 초과(같은 날 전 종목 대비)를 붙인다."""
    E = EV.copy(); E["d0"] = np.searchsorted(dates, E[col].values)
    E = E[(E.d0 >= max(s.t0, 1)) & (E.d0 < T - 62)]; E = E[ok[E.d0.values, E.k.values]]
    f = np.array([entry_ok(s, t)[k] for t, k in zip(E.d0, E.k)], bool); E = E[f]
    mc = c[E.d0.values - 1, E.k.values] * shares[E.d0.values - 1, E.k.values]; E = E[np.isfinite(mc) & (mc > 0)]; mc = mc[np.isfinite(mc) & (mc > 0)]
    E["sue"] = (E.q_this - E.q_prev) / mc; E["mcap_pct"] = rank(np.log(c * shares), ok)[E.d0.values, E.k.values]
    base = o[E.d0.values + 1, E.k.values]; um = {}
    for h in (5, 20, 60):
        E[f"r{h}"] = (ff[E.d0.values + h, E.k.values] / base - 1 - COST) * 100
        for t in E.d0.unique():
            fo = entry_ok(s, t) & ok[t]; um[(t, h)] = np.mean(ff[t + h, fo] / o[t + 1, fo] - 1 - COST) * 100
        E[f"x{h}"] = E[f"r{h}"] - [um[(t, h)] for t in E.d0]
    return E


def cci(g, col, k=2000):
    a = g.groupby("d0")[col].agg(["sum", "count"]); n = len(a)
    if n < 5: return (np.nan, np.nan)
    idx = np.random.default_rng(7).integers(0, n, (k, n)); return tuple(np.quantile(a["sum"].values[idx].sum(1) / a["count"].values[idx].sum(1), [.025, .975]))


def line(nm, g):
    if len(g) < 30: return f"  {nm:<34} n {len(g):>5} (표본 부족)"
    lo, hi = cci(g, "x20"); lo6, hi6 = cci(g, "x60"); ss = g.groupby("season").x20.mean()
    return (f"  {nm:<34} n {len(g):>5} · 날짜 {g.d0.nunique():>3} · 5봉 {g.x5.mean():+.2f} · 20봉 {g.x20.mean():+.2f} [{lo:+.2f},{hi:+.2f}] · 60봉 {g.x60.mean():+.2f} [{lo6:+.2f},{hi6:+.2f}]"
            f" · +20%(20봉) {np.mean(g.r20 >= 20)*100:.1f}% · 묶음 양(+) {int((ss > 0).sum())}/{len(ss)}")


R = {"원본 접수일": attach(EV, "d_rep"), "처음 알려진 날": attach(EV, "d_first")}
for nm, E in R.items():
    print(f"\n[기준 = {nm}] 같은 날 전 종목 대비 초과 %p")
    print(line("전체(놀람 무관)", E)); print(line("놀람 ≥ +1%", E[E.sue >= .01])); print(line("놀람 ≥ +3%", E[E.sue >= .03])); print(line("놀람 ≤ −1%", E[E.sue <= -.01]))
    print(line("놀람 ≥ +1% ∩ 시총 상위 20%", E[(E.sue >= .01) & (E.mcap_pct >= .8)])); print(line("놀람 ≥ +1% ∩ 시총 50~80%", E[(E.sue >= .01) & (E.mcap_pct >= .5) & (E.mcap_pct < .8)]))
    print(line("놀람 ≥ +1% ∩ 시총 하위 50%", E[(E.sue >= .01) & (E.mcap_pct < .5)]))
    yy = E[E.sue >= .01].assign(y=lambda d: dates[d.d0.values].astype("U4")).groupby("y").x20.agg(["mean", "count"]).round(2); print("  놀람 ≥ +1% 연도별 20봉:", {k: (float(v["mean"]), int(v["count"])) for k, v in yy.iterrows()})
# 같은 사건을 두 날짜로: 먼저 알려진 사건만
ea = EV[EV.early]; a1 = attach(ea, "d_first"); a2 = attach(ea, "d_rep")
print(f"\n[먼저 알려진 사건만 — 같은 사건을 '처음 알려진 날'에 산 것 vs '정기보고서 날'에 산 것]  (앞선 거래일 수 중앙값 {int(np.median(np.searchsorted(dates, ea.d_rep.values) - np.searchsorted(dates, ea.d_first.values)))}일)")
for nm, cond in (("놀람 ≥ +1%", lambda E: E.sue >= .01), ("놀람 ≥ +1% ∩ 시총 상위 20%", lambda E: (E.sue >= .01) & (E.mcap_pct >= .8)), ("놀람 ≤ −1%", lambda E: E.sue <= -.01)):
    print(line(nm + " · 처음 알려진 날", a1[cond(a1)])); print(line(nm + " · 정기보고서 날", a2[cond(a2)]))
lt = EV[~EV.early]; a3 = attach(lt, "d_rep")
print("\n[정기보고서가 처음인 사건만(잠정실적 없음)]"); print(line("놀람 ≥ +1%", a3[a3.sue >= .01])); print(line("놀람 ≤ −1%", a3[a3.sue <= -.01]))
cov = R["처음 알려진 날"].assign(grp=lambda d: np.where(d.mcap_pct >= .8, "시총 상위 20%", np.where(d.mcap_pct >= .5, "50~80%", "하위 50%"))).groupby("grp").early.mean().round(2).to_dict()
print("\n먼저 알려진 비율(시총별):", cov)
R["처음 알려진 날"].to_parquet(HERE / "events_first_disclosure.parquet", index=False)
