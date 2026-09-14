# -*- coding: utf-8 -*-
"""ls_t1 상위 10%(50종목) 안에서 무엇이 더 좋았나 (2026-09-14, 관측 전용·읽기 전용)
상위 50 풀을 만든 뒤, 풀 안에서 조건별로 나눠 같은 앵커 짝비교(조건 충족 − 미충족). 초과 = 종목 20/40일 수익 − 대형 유니버스 중간값(%p).
참고 기간 6/10~(등록 전 포함, 앵커 중첩 → CI 과소). 판정 아님.
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
lg = pd.read_sql_query("SELECT run_id,market,ticker,sector,per,pbr,rim_spread,div_yield,roe_value,quality_gate,rim_quadrant,buyback_cancel_flag,is_financial,is_holding,is_cyclical,supply20_pos,supply20_net,foreign_20d,inst_20d,marcap_rank,ocf_to_op_ratio,annual_yoy,quarterly_yoy FROM large_final", h); h.close()
lg["ticker"] = lg.ticker.astype(str).str.zfill(6)
fz = pd.DataFrame({"ep": 1.0 / lg["per"].where(lg["per"] > 0), "bp": 1.0 / lg["pbr"].where(lg["pbr"] > 0), "rim": lg["rim_spread"], "dv": lg["div_yield"]})
rk = fz.groupby(lg["run_id"]).rank(pct=True)
for c in fz: lg["r_" + c] = rk[c]
lg["s"] = rk.mean(axis=1, skipna=True).where(rk.notna().sum(axis=1) >= 2)
lg = lg[lg.s.notna()].copy()
for c in ["roe_value", "ocf_to_op_ratio", "annual_yoy", "quarterly_yoy", "supply20_net", "foreign_20d", "inst_20d"]: lg[c] = pd.to_numeric(lg[c], errors="coerce")
def ci(v):
    a = np.asarray(v, float); a = a[np.isfinite(a)]
    if len(a) < 2: return (np.nan, np.nan)
    return tuple(np.quantile(rng.choice(a, size=(2000, len(a))).mean(axis=1), [0.025, 0.975]))
cand = {}
for run in sorted(lg.run_id.astype(str).unique()):
    if run < "20260610" or run in EXCL: continue
    t = bisect.bisect_right(dates, run) - 1
    if t >= 0: cand.setdefault(t, []).append(run)
chosen = {t: (dates[t] if dates[t] in r else min(r)) for t, r in cand.items()}
def pool_frames(H):
    frames = []
    for t, run in sorted(chosen.items()):
        if t + H + 1 >= len(dates): continue
        blk = P[t + 1:t + H + 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            fwd = blk[-1] / blk[0] - 1; jumps = np.abs(blk[1:] / blk[:-1] - 1)
        ok = np.isfinite(fwd) & (blk[0] > 0) & (blk[-1] > 0) & (np.nanmax(np.where(np.isnan(jumps), -np.inf, jumps), axis=0) <= JUMP)
        g = lg[lg.run_id.astype(str) == run].copy(); g["ci_"] = g.ticker.map(cols); g = g[g.ci_.notna()]; g["ci_"] = g.ci_.astype(int)
        g = g[ok[g.ci_.values]].copy(); g["ex"] = fwd[g.ci_.values] * 100 - np.median(fwd[g.ci_.values] * 100)
        if len(g) < 30: continue
        top = g.nlargest(50, "s").copy(); top["anchor"] = dates[t]; top["rank_in"] = np.arange(1, len(top) + 1)
        frames.append(top)
    return pd.concat(frames, ignore_index=True)
def paired(D, m):
    a = D[m].groupby("anchor").ex.mean(); b = D[~m].groupby("anchor").ex.mean(); d = (a - b).dropna()
    lo, hi = ci(d.values); mark = "**" if (lo > 0 or hi < 0) else ""
    return f"{a.mean():+.2f} | {b.mean():+.2f} | {mark}{d.mean():+.2f}{mark} | [{lo:+.2f}, {hi:+.2f}] | {len(d)} | {D[m].groupby('anchor').size().mean():.0f}"
out = ["# RESEARCH — ls_t1 상위 10%(50종목) 안에서 무엇이 더 좋았나 (2026-09-14, 관측 전용)", "",
       "- 풀 = 매 앵커 ls_t1 상위 50. 초과 = 종목 수익 − 대형 유니버스 중간값(%p, 수수료 전). 짝차이 = 같은 앵커에서 (조건 충족 평균 − 미충족 평균). **굵게** = CI 가 0 을 안 걸침.",
       "- 참고 기간 6/10~(등록 전 포함). 앵커가 매일 겹쳐 CI 는 실제보다 좁다. **판정 아님.**", ""]
for H in (20, 40):
    D = pool_frames(H)
    med = lambda c: D[c].median()
    conds = {
        "순위 1~10 (vs 11~50)": D.rank_in <= 10, "순위 1~25 (vs 26~50)": D.rank_in <= 25,
        "1/PER 상위 절반 (풀 안 중앙값 기준)": D.r_ep >= med("r_ep"), "1/PBR 상위 절반": D.r_bp >= med("r_bp"),
        "RIM 상위 절반": D.r_rim >= med("r_rim"), "배당 상위 절반": D.r_dv >= med("r_dv"),
        "RIM 사분면 1": D.rim_quadrant == 1, "품질게이트 통과": D.quality_gate == 1,
        "ROE 상위 절반": D.roe_value >= med("roe_value"), "OCF/영업이익 상위 절반": D.ocf_to_op_ratio >= med("ocf_to_op_ratio"),
        "연간 이익 증가(yoy>0)": D.annual_yoy > 0, "분기 이익 증가(yoy>0)": D.quarterly_yoy > 0,
        "수급20일 양(+)": D.supply20_pos == 1, "외인20일 순매수>0": D.foreign_20d > 0, "기관20일 순매수>0": D.inst_20d > 0,
        "자사주 소각 플래그": D.buyback_cancel_flag == 1,
        "금융·지주 아님": (D.is_financial != 1) & (D.is_holding != 1), "경기민감 아님": D.is_cyclical != 1,
        "시총 101~500위 (vs 상위 100)": D.marcap_rank > 100, "시총 301~500위": D.marcap_rank > 300,
    }
    out += [f"## H={H} — 앵커 {D.anchor.nunique()}개, 풀 평균 초과 {D.groupby('anchor').ex.mean().mean():+.2f}%p", "",
            "| 조건 (풀 안에서) | 충족 | 미충족 | 짝차이 | 95% CI | n | 충족 종목/앵커 |", "|---|---:|---:|---:|---|---:|---:|"]
    for k, m in conds.items():
        m = m.fillna(False)
        if D[m].groupby("anchor").ngroups < 5 or D[~m].groupby("anchor").ngroups < 5: out.append(f"| {k} | (표본 부족) | | | | | |"); continue
        out.append(f"| {k} | {paired(D, m)} |")
    # 업종별
    sec = D.groupby(["sector"]).agg(n=("ex", "size"), ex=("ex", "mean")).query("n >= 40").sort_values("ex", ascending=False)
    out += ["", f"업종별(풀 안, 종목-앵커 40개 이상): " + " · ".join(f"{s} {r.ex:+.1f}({int(r.n)})" for s, r in sec.head(8).iterrows()) + " … 하위: " + " · ".join(f"{s} {r.ex:+.1f}" for s, r in sec.tail(3).iterrows()), ""]
md = "\n".join(out) + "\n"; print(md)
io.open(ROOT / "research" / "RESEARCH_ls_t1_top_decile_20260914.md", "w", encoding="utf-8").write(md)
