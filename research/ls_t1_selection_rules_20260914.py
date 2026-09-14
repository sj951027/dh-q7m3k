# -*- coding: utf-8 -*-
"""ls_t1(대형 밸류) — 상위 10 이 최선인가, 다른 기준이 더 나은가 (2026-09-14, 관측 전용·읽기 전용)
바구니 후보를 같은 규약(진입 t+1·h=20/40·점프컷 0.32·게이트 run 제외)으로 재고 '상위10' 과 같은 앵커끼리 짝비교.
초과 = 바구니 평균 − 같은 시장(대형 유니버스) 채점 종목 중간값(%p). CI = 앵커 iid 부트스트랩 95%. 판정 아님.
기간: (참고) 6/10~ 전 run — 등록(8/06) 전 포함이라 in-sample 성격. 등록 후만 따로 표기(h20, n 작음).
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
lg = pd.read_sql_query("SELECT run_id,market,ticker,sector,per,pbr,rim_spread,div_yield,roe_value,quality_gate,rim_quadrant,buyback_cancel_flag,is_financial,is_holding,is_cyclical,supply20_pos,foreign_20d,inst_20d,marcap_rank FROM large_final", h); h.close()
lg["ticker"] = lg.ticker.astype(str).str.zfill(6); lg["market"] = lg.market.str.lower()
fz = pd.DataFrame({"ep": 1.0 / lg["per"].where(lg["per"] > 0), "bp": 1.0 / lg["pbr"].where(lg["pbr"] > 0), "rim": lg["rim_spread"], "dv": lg["div_yield"]})
rk = fz.groupby(lg["run_id"]).rank(pct=True)
for c in fz: lg["r_" + c] = rk[c]
lg["s"] = rk.mean(axis=1, skipna=True).where(rk.notna().sum(axis=1) >= 2)
lg = lg[lg.s.notna()].copy()

def cand_map(reg):
    cand = {}
    for run in sorted(lg.run_id.astype(str).unique()):
        if run < reg or run in EXCL: continue
        t = bisect.bisect_right(dates, run) - 1
        if t >= 0: cand.setdefault(t, []).append(run)
    return {t: (dates[t] if dates[t] in r else min(r)) for t, r in cand.items()}

def sector_neutral(g, n=10, cap=2):
    out, cnt = [], {}
    for _, r in g.sort_values("s", ascending=False).iterrows():
        if cnt.get(r.sector, 0) >= cap: continue
        out.append(r.name); cnt[r.sector] = cnt.get(r.sector, 0) + 1
        if len(out) >= n: break
    return g.loc[out]
BASKETS = {
    "상위10 (기준)": lambda g: g.nlargest(10, "s"),
    "상위5": lambda g: g.nlargest(5, "s"),
    "상위20": lambda g: g.nlargest(20, "s"),
    "상위30": lambda g: g.nlargest(30, "s"),
    "상위10 · 품질게이트 통과만": lambda g: g[g.quality_gate == 1].nlargest(10, "s"),
    "상위10 · 금융·지주 제외": lambda g: g[(g.is_financial != 1) & (g.is_holding != 1)].nlargest(10, "s"),
    "상위10 · 경기민감 제외": lambda g: g[g.is_cyclical != 1].nlargest(10, "s"),
    "상위10 · 업종당 최대 2": lambda g: sector_neutral(g),
    "상위10 · 수급20일 양(+)만": lambda g: g[g.supply20_pos == 1].nlargest(10, "s"),
    "상위10 · RIM 사분면 1만": lambda g: g[g.rim_quadrant == 1].nlargest(10, "s"),
    "상위10 · 시총 상위 100 안": lambda g: g[g.marcap_rank <= 100].nlargest(10, "s"),
    "상위10 · 시총 101~500": lambda g: g[g.marcap_rank > 100].nlargest(10, "s"),
    "팩터 단독: 1/PER 상위10": lambda g: g.nlargest(10, "r_ep"),
    "팩터 단독: 1/PBR 상위10": lambda g: g.nlargest(10, "r_bp"),
    "팩터 단독: RIM 상위10": lambda g: g.nlargest(10, "r_rim"),
    "팩터 단독: 배당 상위10": lambda g: g.nlargest(10, "r_dv"),
    "하위10 (거울)": lambda g: g.nsmallest(10, "s"),
}
def ci(v):
    a = np.asarray(v, float); a = a[np.isfinite(a)]
    if len(a) < 2: return (np.nan, np.nan)
    return tuple(np.quantile(rng.choice(a, size=(2000, len(a))).mean(axis=1), [0.025, 0.975]))
def run_block(reg, H, title):
    chosen = cand_map(reg); series = {k: {} for k in BASKETS}; n_anchor = 0
    for t, run in sorted(chosen.items()):
        if t + H + 1 >= len(dates): continue
        blk = P[t + 1:t + H + 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            fwd = blk[-1] / blk[0] - 1; jumps = np.abs(blk[1:] / blk[:-1] - 1)
        ok = np.isfinite(fwd) & (blk[0] > 0) & (blk[-1] > 0) & (np.nanmax(np.where(np.isnan(jumps), -np.inf, jumps), axis=0) <= JUMP)
        g = lg[lg.run_id.astype(str) == run].copy(); g["ci_"] = g.ticker.map(cols); g = g[g.ci_.notna()]; g["ci_"] = g.ci_.astype(int)
        g = g[ok[g.ci_.values]].copy(); g["f"] = fwd[g.ci_.values] * 100
        if len(g) < 30: continue
        n_anchor += 1
        med = g.f.median()   # 대형 유니버스는 코스피·코스닥 합쳐 한 후보군(설계상 시장 구분 없이 상위 N)
        for k, fn in BASKETS.items():
            sub = fn(g)
            if len(sub) >= 3: series[k][dates[t]] = sub.f.mean() - med
    base = pd.Series(series["상위10 (기준)"])
    rows = [f"### {title} — H={H}, 앵커 {n_anchor}개", "", "| 바구니 | 초과(%p) | 95% CI | 앵커 승률 | 기준 대비 짝차이 | 짝 CI | n |", "|---|---:|---|---:|---:|---|---:|"]
    for k in BASKETS:
        sr = pd.Series(series[k]); 
        if len(sr) < 3: rows.append(f"| {k} | (n<3) | | | | | |"); continue
        lo, hi = ci(sr.values); d = (sr - base).dropna(); dlo, dhi = ci(d.values)
        mark = "**" if (dlo > 0 or dhi < 0) else ""
        rows.append(f"| {k} | {sr.mean():+.2f} | [{lo:+.2f}, {hi:+.2f}] | {(sr>0).mean()*100:.0f}% | {mark}{d.mean():+.2f}{mark} | [{dlo:+.2f}, {dhi:+.2f}] | {len(sr)} |")
    return rows
out = ["# RESEARCH — ls_t1(대형 밸류): 상위10 이 최선인가 (2026-09-14, 관측 전용)", "",
       "- 초과 = 바구니 평균 − 대형 유니버스(500) 채점 종목 중간값(%p, 수수료 전). 진입 t+1, 점프컷 0.32. 짝차이 = 같은 앵커에서 (바구니 − 상위10). **굵게** = 짝 CI 가 0 을 안 걸침.",
       "- '참고(6/10~)' 는 등록(8/06) 전 run 포함 → in-sample 성격·2026 여름 대형 가치주 강세 편중 가능. '등록 후' 는 앵커가 적다. **판정 아님.**", ""]
out += run_block("20260610", 20, "참고: 전 run 6/10~") + [""]
out += run_block("20260610", 40, "참고: 전 run 6/10~") + [""]
out += run_block("20260806", 20, "등록 후 8/06~") + [""]
md = "\n".join(out) + "\n"; print(md)
io.open(ROOT / "research" / "RESEARCH_ls_t1_selection_rules_20260914.md", "w", encoding="utf-8").write(md)
