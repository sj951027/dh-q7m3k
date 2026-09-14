# -*- coding: utf-8 -*-
"""ls_t1 페이지 '관측용 필터' 조합이 실제로 나은가 (2026-09-14, 관측 전용·읽기 전용)
조합 바구니 vs '합성 상위10' 을 같은 앵커 짝비교. 전반/후반 분할로 국면 의존 확인. 초과 = 바구니 평균 − 대형 유니버스 중간값(%p).
참고 6/10~(등록 전 포함)·등록 후 8/06~ 각각. 앵커 중첩 → CI 과소. 판정 아님.
"""
import bisect, sqlite3, io
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]; EXCL = {"20260608", "20260703"}; JUMP = 0.32
rng = np.random.default_rng(7)
def ro(p): return sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
con = ro(ROOT.parent / "dh-q7m3k-data" / "ohlcv.db")
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
raw = pd.read_sql_query("SELECT ticker,date,close FROM daily_ohlcv WHERE date>='20260601'", con); con.close()
raw["ticker"] = raw["ticker"].astype(str).str.zfill(6)
P = raw.pivot(index="date", columns="ticker", values="close").reindex(dates); cols = {t: i for i, t in enumerate(P.columns)}; P = P.to_numpy(float)
h = ro(ROOT / "history.db")
lg = pd.read_sql_query("SELECT run_id,ticker,per,pbr,rim_spread,div_yield,quality_gate,rim_quadrant,is_financial,is_holding,marcap_rank FROM large_final", h); h.close()
lg["ticker"] = lg.ticker.astype(str).str.zfill(6)
fz = pd.DataFrame({"ep": 1.0 / lg["per"].where(lg["per"] > 0), "bp": 1.0 / lg["pbr"].where(lg["pbr"] > 0), "rim": lg["rim_spread"], "dv": lg["div_yield"]})
rk = fz.groupby(lg["run_id"]).rank(pct=True)
for c in fz: lg["r_" + c] = rk[c]
lg["s"] = rk.mean(axis=1, skipna=True).where(rk.notna().sum(axis=1) >= 2); lg = lg[lg.s.notna()].copy()
mid = lambda g: g[(g.marcap_rank > 100) & (g.marcap_rank <= 500)]
rq = lambda g: g[g.rim_quadrant == 1]
nofin = lambda g: g[(g.is_financial != 1) & (g.is_holding != 1)]
B = {
 "합성 상위10 (기준)": lambda g: g.nlargest(10, "s"),
 "합성 상위5": lambda g: g.nlargest(5, "s"),
 "합성 상위10 · 시총101~500": lambda g: mid(g).nlargest(10, "s"),
 "합성 상위10 · RIM사분면1": lambda g: rq(g).nlargest(10, "s"),
 "합성 상위10 · 시총101~500 · RIM사분면1": lambda g: rq(mid(g)).nlargest(10, "s"),
 "합성 상위10 · 시총101~500 · RIM사분면1 · 금융지주 제외": lambda g: nofin(rq(mid(g))).nlargest(10, "s"),
 "합성 상위5 · 시총101~500 · RIM사분면1": lambda g: rq(mid(g)).nlargest(5, "s"),
 "RIM 단독 상위10": lambda g: g.nlargest(10, "r_rim"),
 "RIM 단독 상위10 · 시총101~500": lambda g: mid(g).nlargest(10, "r_rim"),
 "RIM 단독 상위10 · 시총101~500 · RIM사분면1": lambda g: rq(mid(g)).nlargest(10, "r_rim"),
 "1/PER 단독 상위10 · 시총101~500": lambda g: mid(g).nlargest(10, "r_ep"),
 "1/PER 단독 상위10 · 시총101~500 · RIM사분면1": lambda g: rq(mid(g)).nlargest(10, "r_ep"),
}
def ci(v):
    a = np.asarray(v, float); a = a[np.isfinite(a)]
    if len(a) < 2: return (np.nan, np.nan)
    return tuple(np.quantile(rng.choice(a, size=(2000, len(a))).mean(axis=1), [0.025, 0.975]))
def block(reg, H):
    cand = {}
    for run in sorted(lg.run_id.astype(str).unique()):
        if run < reg or run in EXCL: continue
        t = bisect.bisect_right(dates, run) - 1
        if t >= 0: cand.setdefault(t, []).append(run)
    chosen = {t: (dates[t] if dates[t] in r else min(r)) for t, r in cand.items()}
    S = {k: {} for k in B}
    for t, run in sorted(chosen.items()):
        if t + H + 1 >= len(dates): continue
        blk = P[t + 1:t + H + 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            fwd = blk[-1] / blk[0] - 1; jumps = np.abs(blk[1:] / blk[:-1] - 1)
        ok = np.isfinite(fwd) & (blk[0] > 0) & (blk[-1] > 0) & (np.nanmax(np.where(np.isnan(jumps), -np.inf, jumps), axis=0) <= JUMP)
        g = lg[lg.run_id.astype(str) == run].copy(); g["ci_"] = g.ticker.map(cols); g = g[g.ci_.notna()]; g["ci_"] = g.ci_.astype(int)
        g = g[ok[g.ci_.values]].copy(); g["f"] = fwd[g.ci_.values] * 100
        if len(g) < 30: continue
        med = g.f.median()
        for k, fn in B.items():
            sub = fn(g)
            if len(sub) >= 3: S[k][dates[t]] = sub.f.mean() - med
    base = pd.Series(S["합성 상위10 (기준)"]); anchors = sorted(base.index); half = anchors[len(anchors) // 2] if anchors else None
    rows = [f"### {'등록 후 8/06~' if reg=='20260806' else '참고 6/10~'} — H={H}, 앵커 {len(base)}개 (후반 시작 {half})", "",
            "| 바구니 | 초과 | 기준 대비 짝차이 [CI] | 전반 짝차이 | 후반 짝차이 | 후반 초과 | 종목/앵커 |", "|---|---:|---|---:|---:|---:|---:|"]
    for k in B:
        sr = pd.Series(S[k])
        if len(sr) < 3: rows.append(f"| {k} | (n<3) | | | | | |"); continue
        d = (sr - base).dropna(); lo, hi = ci(d.values); mark = "**" if (lo > 0 or hi < 0) else ""
        d1 = d[d.index < half]; d2 = d[d.index >= half]; s2 = sr[sr.index >= half]
        rows.append(f"| {k} | {sr.mean():+.2f} | {mark}{d.mean():+.2f}{mark} [{lo:+.2f}, {hi:+.2f}] | {d1.mean():+.2f} | {d2.mean():+.2f} | {s2.mean():+.2f} | — |")
    return rows
out = ["# RESEARCH — ls_t1 관측용 필터 조합 검증 (2026-09-14, 관측 전용)", "",
       "- 초과 = 바구니 평균 − 대형 유니버스 중간값(%p, 수수료 전). 짝차이 = 같은 앵커에서 (조합 − 합성 상위10). **굵게** = CI 가 0 을 안 걸침(앵커 중첩이라 실제보다 좁음). **판정 아님.**", ""]
out += block("20260610", 20) + [""] + block("20260610", 40) + [""] + block("20260806", 20)
md = "\n".join(out) + "\n"; print(md)
io.open(ROOT / "research" / "RESEARCH_ls_t1_filter_combo_20260914.md", "w", encoding="utf-8").write(md)
