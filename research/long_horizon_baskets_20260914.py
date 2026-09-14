# -*- coding: utf-8 -*-
"""오래 들수록 좋은가 — 모델별 상위10 바구니의 20·40·60거래일 초과수익 (2026-09-14, 관측 전용·읽기 전용)
규약: 진입 t+1 종가, 청산 t+1+H 종가, 점프컷 0.32(보유 전 구간), 게이트 run 제외, 각 모델 등록일 이후.
초과 = 바구니 평균 − 같은 시장 채점 종목 중간값(%p). 시장별 → 앵커 평균. CI = 앵커 iid 부트스트랩 95%(2000회). 판정 아님.
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
lf_cols = [c[1] for c in h.execute("pragma table_info(large_final)")]
ls_col = next((c for c in lf_cols if c in ("large_score", "ls_t1", "final_score_large", "score_ls_t1")), None) or next((c for c in lf_cols if "score" in c.lower()), None)
SPECS = {
    "v30 (과매도)":   ("SELECT run_id,market,ticker,final_score_v3 s FROM v3_scores WHERE model_id='v30'", "20260606"),
    "lv_b (저변동)":  ("SELECT run_id,market,ticker,lowvol_score s FROM lowvol_scores WHERE model_id='lv_b'", "20260625"),
    "sv_a (공매도비중)": ("SELECT run_id,market,ticker,wu_score s FROM wu_scores WHERE model_id='sv_a'", "20260715"),
    "px_a (가격4팩터)": ("SELECT run_id,market,ticker,wu_score s FROM wu_scores WHERE model_id='px_a'", "20260810"),
}
# ls_t1: leaderboard.py 와 같은 정의 — run 내 ep(1/PER)·bp(1/PBR)·rim_spread·div_yield 백분위 랭크 동일가중 평균(결측 제외, 최소 2개)
lg = pd.read_sql_query("SELECT run_id,market,ticker,per,pbr,rim_spread,div_yield FROM large_final", h)
fz = pd.DataFrame({"ep": 1.0 / lg["per"].where(lg["per"] > 0), "bp": 1.0 / lg["pbr"].where(lg["pbr"] > 0), "rim": lg["rim_spread"], "dv": lg["div_yield"]})
rk = fz.groupby(lg["run_id"]).rank(pct=True)
lg["s"] = rk.mean(axis=1, skipna=True).where(rk.notna().sum(axis=1) >= 2)
LS = lg[["run_id", "market", "ticker", "s"]].dropna()
SPECS["ls_t1 (대형밸류, 60~120일 설계)"] = ("__LS__", "20260806")
SPECS["(참고) 같은 밸류점수, 대형 전 run 6/10~ (등록 전 포함 = in-sample 성격)"] = ("__LS__", "20260610")
def ci(v):
    a = np.asarray(v, float); a = a[np.isfinite(a)]
    if len(a) < 2: return (np.nan, np.nan)
    return tuple(np.quantile(rng.choice(a, size=(2000, len(a))).mean(axis=1), [0.025, 0.975]))
out = ["# RESEARCH — 오래 들수록 좋은가: 상위10 바구니의 20·40·60거래일 초과수익 (2026-09-14, 관측 전용)", "",
       "- 초과 = 상위10 평균 − 같은 시장 채점 종목 중간값(%p, 수수료 전). 진입 t+1, 점프컷 0.32. 앵커 n = 그 지평의 결과가 닫힌 날 수. **판정 아님.**",
       "- '20일 환산' = 초과 × 20/H. 보유를 늘려 얻는 게 시간당으로도 남는지 보는 열.", "",
       "| 모델 | H | 초과(%p) | 95% CI | 20일 환산 | 앵커 n | 앵커 승률 |", "|---|---:|---:|---|---:|---:|---:|"]
for name, (sql, reg) in SPECS.items():
    if sql is None: out.append(f"| {name} | — | 점수 열 못 찾음 | | | | |"); continue
    sc = LS.copy() if sql == "__LS__" else pd.read_sql_query(sql, h); sc["ticker"] = sc.ticker.astype(str).str.zfill(6); sc["market"] = sc.market.str.lower(); sc["s"] = pd.to_numeric(sc.s, errors="coerce")
    cand = {}
    for run in sorted(sc.run_id.astype(str).unique()):
        if run < reg or run in EXCL: continue
        t = bisect.bisect_right(dates, run) - 1
        if t >= 0: cand.setdefault(t, []).append(run)
    chosen = {t: (dates[t] if dates[t] in r else min(r)) for t, r in cand.items()}
    for H in ((20, 40, 60, 90) if "ls_t1" in name or "대형" in name else (20, 40, 60)):
        vals = []
        for t, run in sorted(chosen.items()):
            if t + H + 1 >= len(dates): continue
            blk = P[t + 1:t + H + 2]
            with np.errstate(divide="ignore", invalid="ignore"):
                fwd = blk[-1] / blk[0] - 1; jumps = np.abs(blk[1:] / blk[:-1] - 1)
            ok = np.isfinite(fwd) & (blk[0] > 0) & (blk[-1] > 0) & (np.nanmax(np.where(np.isnan(jumps), -np.inf, jumps), axis=0) <= JUMP)
            g = sc[sc.run_id.astype(str) == run].copy(); g["ci_"] = g.ticker.map(cols); g = g[g.ci_.notna() & g.s.notna()]; g["ci_"] = g.ci_.astype(int)
            g = g[ok[g.ci_.values]]; g["f"] = fwd[g.ci_.values] * 100
            mv = []
            for mkt, gg in g.groupby("market"):
                if len(gg) < 8: continue
                mv.append(gg.nlargest(10, "s").f.mean() - gg.f.median())
            if mv: vals.append(float(np.mean(mv)))
        if len(vals) < 3: out.append(f"| {name} | {H} | (앵커 {len(vals)}개 — 아직 안 닫힘) | | | | |"); continue
        lo, hi = ci(vals); v = np.asarray(vals)
        out.append(f"| {name} | {H} | {v.mean():+.2f} | [{lo:+.2f}, {hi:+.2f}] {'모두 양수' if lo>0 else ('모두 음수' if hi<0 else '0 걸침')} | {v.mean()*20/H:+.2f} | {len(v)} | {(v>0).mean()*100:.0f}% |")
h.close()
md = "\n".join(out) + "\n"; print(md)
io.open(ROOT / "research" / "RESEARCH_long_horizon_baskets_20260914.md", "w", encoding="utf-8").write(md)
