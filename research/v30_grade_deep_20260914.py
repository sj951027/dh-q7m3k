# -*- coding: utf-8 -*-
"""v30 등급·버킷 심층 (2026-09-14, 관측 전용 · 읽기 전용)

앞선 v30_bucket_grade 의 후속. 질문: (1) BUY·A 가 정말 더 좋았나 — 평균 말고 승률·중앙값·앵커 일관성으로.
(2) 등급의 어느 조건이 효과를 내나 — 품질·반전·수급·턴어라운드·밸류·반전확인(E2)을 하나씩 분해.
(3) 점수 순위와 겹치는 정보인가 — 순위 구간 안에서 버킷 차이. (4) 반등 구간 편중인가 — 앵커 전반/후반.
규약은 §11 과 동일(진입 t+1·h=20·점프컷 0.32·게이트 run 제외). 초과 = 종목 20일 수익 − 같은 시장 v30 채점 종목 중간값(%p).
입력: v3_archive/v3_{mkt}_{run}.csv (세부 점수) · ohlcv.db. CI = 앵커 iid 부트스트랩 95%(2000회, seed 7). 판정 아님.
"""
import bisect, sqlite3, io, glob
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REG, EXCLUDE, JUMP = "20260606", {"20260608", "20260703"}, 0.32
SAFE_OUT = {"WATCH", "EXCLUDE"}
rng = np.random.default_rng(7)

def ro(p): return sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
con = ro(ROOT.parent / "dh-q7m3k-data" / "ohlcv.db")
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
floor = dates[max(0, bisect.bisect_right(dates, REG) - 1)]
raw = pd.read_sql_query("SELECT ticker,date,close FROM daily_ohlcv WHERE date>=?", con, params=(floor,)); con.close()
raw["ticker"] = raw["ticker"].astype(str).str.zfill(6)
close = raw.pivot(index="date", columns="ticker", values="close").reindex(dates)
P = close.to_numpy(float); col = {t: i for i, t in enumerate(close.columns)}

runs = sorted({Path(f).stem.split("_")[-1] for f in glob.glob(str(ROOT / "v3_archive" / "v3_kospi_*.csv"))})
cand = {}
for run in runs:
    if run < REG or run in EXCLUDE: continue
    t = bisect.bisect_right(dates, run) - 1
    if t >= 0: cand.setdefault(t, []).append(run)
chosen = {t: (dates[t] if dates[t] in runs else min(r)) for t, r in cand.items()}

def fwd_ok(t, H):
    blk = P[t + 1:t + H + 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        fwd = blk[-1] / blk[0] - 1; jumps = np.abs(blk[1:] / blk[:-1] - 1)
    ok = np.isfinite(fwd) & (blk[0] > 0) & (blk[-1] > 0) & (np.nanmax(np.where(np.isnan(jumps), -np.inf, jumps), axis=0) <= JUMP)
    return fwd, ok

def ci(vals):
    a = np.asarray(vals, float); a = a[np.isfinite(a)]
    if len(a) < 2: return (np.nan, np.nan)
    b = rng.choice(a, size=(2000, len(a))).mean(axis=1); return tuple(np.quantile(b, [0.025, 0.975]))
def flag(lo, hi): return "모두 양수" if lo > 0 else ("모두 음수" if hi < 0 else "0 걸침")

# ---- 앵커별 종목 표 만들기 (h=20 주, h=5 보조)
frames = []
for t, run in sorted(chosen.items()):
    if t + 21 >= len(dates): continue
    f20, ok20 = fwd_ok(t, 20); f5, ok5 = fwd_ok(t, 5)
    for mkt in ("kospi", "kosdaq"):
        p = ROOT / "v3_archive" / f"v3_{mkt}_{run}.csv"
        if not p.exists(): continue
        g = pd.read_csv(p, dtype={"ticker": str}, encoding="utf-8-sig")
        g["ticker"] = g["ticker"].astype(str).str.zfill(6)
        g["ci_"] = g.ticker.map(col); g = g[g.ci_.notna()]; g["ci_"] = g.ci_.astype(int)
        g = g[ok20[g.ci_.values]].copy()
        if len(g) < 8: continue
        g["ex20"] = f20[g.ci_.values] * 100; g["ex20"] -= g["ex20"].median()
        g["ex5"] = np.where(ok5[g.ci_.values], f5[g.ci_.values] * 100, np.nan); g["ex5"] -= np.nanmedian(g["ex5"])
        g["rank"] = g["final_score_v3"].rank(ascending=False, method="first")
        g["anchor"] = dates[t]; g["mkt"] = mkt
        g["e2"] = (pd.to_numeric(g.get("reversal_above_sma5"), errors="coerce").fillna(0) > 0) & (pd.to_numeric(g.get("reversal_vol_up_candle"), errors="coerce").fillna(0) > 0)
        frames.append(g)
D = pd.concat(frames, ignore_index=True)
for c in ["quality_score", "reversal_score", "supply_score_v2", "turnaround_score", "value_score", "final_score_v3"]:
    D[c] = pd.to_numeric(D[c], errors="coerce")
anchors = sorted(D.anchor.unique()); nA = len(anchors)
half = anchors[len(anchors) // 2]

def anchor_mean(sub, colname="ex20"):
    """시장별 평균 → 앵커 평균 리스트."""
    m = sub.groupby(["anchor", "mkt"])[colname].mean().groupby("anchor").mean()
    return m.reindex(anchors)

def grp_row(name, sub, colname="ex20"):
    am = anchor_mean(sub, colname); v = am.dropna().values
    lo, hi = ci(v)
    win = (sub[colname] > 0).mean() * 100
    per_anchor = (am.dropna() > 0).mean() * 100
    cnt = sub.groupby(["anchor", "mkt"]).size().mean()
    return f"| {name} | {v.mean():+.2f} | [{lo:+.2f}, {hi:+.2f}] {flag(lo, hi)} | {sub[colname].median():+.2f} | {win:.0f}% | {per_anchor:.0f}% ({len(v)}) | {cnt:.0f} |"

HDR = "| 그룹 | 앵커평균 초과 | 95% CI | 종목 중앙값 | 종목 승률 | 앵커 승률(n) | 앵커당 종목 |\n|---|---:|---|---:|---:|---:|---:|"
out = ["# RESEARCH — v30 등급·버킷 심층: 무엇을 골라야 하나 (2026-09-14, 관측 전용)", "",
       f"- 앵커 {nA}개({anchors[0]}~{anchors[-1]}), 규약 §11 동일. 초과 = 종목 20일 수익 − 같은 시장 v30 채점 종목 중간값(%p).",
       "- '종목 승률' = 초과>0 인 종목 비율. '앵커 승률' = 그룹 평균이 양수였던 앵커 비율. CI = 앵커 부트스트랩 95%. **판정 아님.**", ""]

# 1. 버킷·등급 (h20) + h5
out += ["## 1. BUY·A 는 정말 더 좋았나 — 평균 말고 분포로", "", HDR]
for b in ["BUY", "WAIT", "OBSERVE"]: out.append(grp_row(f"버킷 {b}", D[D.bucket == b]))
for gr in ["A+", "A", "B", "C"]: out.append(grp_row(f"등급 {gr}", D[D.grade == gr]))
out += ["", "5일 뒤(h=5) 같은 표 — 반전 신호가 짧게만 먹는지 확인", "", HDR.replace("초과", "초과(5일)")]
for b in ["BUY", "WAIT", "OBSERVE"]: out.append(grp_row(f"버킷 {b}", D[D.bucket == b], "ex5"))
for gr in ["A+", "A"]: out.append(grp_row(f"등급 {gr}", D[D.grade == gr], "ex5"))

# 2. 조건 분해 (WATCH·EXCLUDE 제외 풀 안에서)
E = D[~D.bucket.isin(SAFE_OUT)]
conds = {
    "반전 ≥8 (A 조건)": E.reversal_score >= 8, "반전 ≥4 (WAIT 조건)": E.reversal_score >= 4,
    "반전확인 E2 (5일선 회복 & 거래량 양봉)": E.e2,
    "품질 ≥15 (A 조건)": E.quality_score >= 15, "품질 ≥18 (A+ 조건)": E.quality_score >= 18,
    "수급 ≥0": E.supply_score_v2 >= 0, "수급 ≥8 (A+ 조건)": E.supply_score_v2 >= 8,
    "턴어라운드 ≥0": E.turnaround_score >= 0, "턴어라운드 ≥5 (A+ 조건)": E.turnaround_score >= 5,
    "밸류 ≥12 (A 조건)": E.value_score >= 12, "위험등급 안전": E.risk_level.astype(str) == "안전",
}
out += ["", "## 2. 등급의 어느 조건이 효과를 내나 (WATCH·EXCLUDE 제외 풀, 조건 충족 − 미충족 짝비교)", "",
        "| 조건 | 충족 평균 | 미충족 평균 | 차이(짝) | 95% CI | 읽기 | 충족 종목/앵커 |", "|---|---:|---:|---:|---|---|---:|"]
for name, m in conds.items():
    a = anchor_mean(E[m]); b = anchor_mean(E[~m]); d = (a - b).dropna().values
    if len(d) < 5: continue
    lo, hi = ci(d)
    out.append(f"| {name} | {a.mean():+.2f} | {b.mean():+.2f} | {d.mean():+.2f} | [{lo:+.2f}, {hi:+.2f}] | {flag(lo, hi)} | {E[m].groupby(['anchor','mkt']).size().mean():.0f} |")

# 3. 순위 구간 × 버킷
out += ["", "## 3. 점수 순위와 겹치는 정보인가 — 순위 구간 안에서 버킷", "", HDR]
bands = [(1, 10), (11, 20), (21, 40), (41, 80), (81, 10**6)]
for lo_, hi_ in bands:
    sub = E[(E["rank"] >= lo_) & (E["rank"] <= hi_)]
    out.append(grp_row(f"순위 {lo_}~{'' if hi_ > 1000 else hi_} 전체", sub))
    for b in ["BUY", "WAIT", "OBSERVE"]:
        s2 = sub[sub.bucket == b]
        if s2.groupby("anchor").ngroups >= 10: out.append(grp_row(f"　└ {b}", s2))
top20 = E[E["rank"] <= 20]
a = anchor_mean(top20[top20.bucket.isin(["BUY", "WAIT"])]); b = anchor_mean(top20[top20.bucket == "OBSERVE"]); d = (a - b).dropna().values
lo, hi = ci(d)
out += ["", f"순위 1~20 안에서 (BUY+WAIT) − OBSERVE 짝비교: {d.mean():+.2f}%p, 95% CI [{lo:+.2f}, {hi:+.2f}] ({flag(lo, hi)}, n={len(d)})"]

# 4. 시기 분할
out += ["", f"## 4. 반등 구간 편중인가 — 앵커 전반({anchors[0]}~) vs 후반({half}~)", "",
        "| 그룹 | 전반 평균 [CI] | 후반 평균 [CI] |", "|---|---|---|"]
def half_row(name, sub):
    r = []
    for part in [sub[sub.anchor < half], sub[sub.anchor >= half]]:
        v = anchor_mean(part).dropna().values; lo, hi = ci(v)
        r.append(f"{v.mean():+.2f} [{lo:+.2f}, {hi:+.2f}] n={len(v)}")
    return f"| {name} | {r[0]} | {r[1]} |"
out.append(half_row("버킷 BUY", D[D.bucket == "BUY"])); out.append(half_row("버킷 WAIT", D[D.bucket == "WAIT"]))
out.append(half_row("버킷 OBSERVE", D[D.bucket == "OBSERVE"])); out.append(half_row("등급 A+/A", D[D.grade.isin(["A+", "A"])]))
reco = E[E["rank"] <= 10]; out.append(half_row("권고10 (순위 1~10, 안전필터)", reco))
# 5. 밸류 조건 심층 — 시기 안정성 + 바구니
out += ["", "## 5. 밸류(저평가 ≥12) — 유일하게 살아남은 조건의 시기 안정성과 바구니", "",
        "| 비교 | 전반 차이 [CI] | 후반 차이 [CI] | 전체 차이 [CI] |", "|---|---|---|---|"]
def paired_by_half(m, pool):
    r = []
    for part in [pool.anchor < half, pool.anchor >= half, pool.anchor == pool.anchor]:
        a = anchor_mean(pool[m & part]); b = anchor_mean(pool[~m & part]); d = (a - b).dropna().values; lo, hi = ci(d)
        r.append(f"{d.mean():+.2f} [{lo:+.2f}, {hi:+.2f}] n={len(d)}")
    return r
r = paired_by_half(E.value_score >= 12, E); out.append(f"| 풀 전체: 밸류≥12 − 미만 | {r[0]} | {r[1]} | {r[2]} |")
top20 = E[E["rank"] <= 20]; r = paired_by_half(top20.value_score >= 12, top20); out.append(f"| 순위 1~20 안: 밸류≥12 − 미만 | {r[0]} | {r[1]} | {r[2]} |")
def basket_series(fn):
    vals = {}
    for (an, mk), g in E.groupby(["anchor", "mkt"]):
        sub = fn(g)
        if len(sub) >= 5: vals.setdefault(an, []).append(sub.ex20.mean())
    return pd.Series({k: np.mean(v) for k, v in vals.items()}).reindex(anchors)
B = {"권고10": basket_series(lambda g: g.nsmallest(10, "rank")),
     "밸류≥12 우선 + 점수순 채움 10": basket_series(lambda g: pd.concat([g[g.value_score >= 12].nsmallest(10, "rank"), g[g.value_score < 12].nsmallest(10, "rank")]).head(10)),
     "밸류≥12 안에서 상위10": basket_series(lambda g: g[g.value_score >= 12].nsmallest(10, "rank"))}
out += ["", "| 바구니 | 전체 평균 [CI] | 전반 | 후반 | 권고10 대비 짝차이 [CI] |", "|---|---|---|---|---|"]
for k, sr in B.items():
    v = sr.dropna(); lo, hi = ci(v.values); f1 = v[v.index < half]; f2 = v[v.index >= half]
    d = (sr - B["권고10"]).dropna().values; dlo, dhi = ci(d)
    out.append(f"| {k} | {v.mean():+.2f} [{lo:+.2f}, {hi:+.2f}] n={len(v)} | {f1.mean():+.2f} | {f2.mean():+.2f} | {d.mean():+.2f} [{dlo:+.2f}, {dhi:+.2f}] |")
md = "\n".join(out) + "\n"
print(md)
io.open(ROOT / "research" / "RESEARCH_v30_grade_deep_20260914.md", "w", encoding="utf-8").write(md)
