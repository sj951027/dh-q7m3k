# -*- coding: utf-8 -*-
"""v30 버킷·등급별 20일 성적 (2026-09-14, 관측 전용 · 읽기 전용 DB)

질문: 등급(A+/A/B/C/WATCH/EXCLUDE)·버킷(BUY/WAIT/OBSERVE/WATCH/EXCLUDE)이 실제 20일 수익에 어떤 차이를 만드나.
규약은 §11/리더보드와 같게: run_id → 거래일 앵커 t, 진입 t+1 종가, 청산 t+21 종가(h=20), 보유 중 일간 |수익| > 0.32 종목 제외,
게이트 run(20260608 부분실행·20260703 이중실행) 제외, 등록일(20260606) 이전 run 제외. 시장별로 잰 뒤 두 시장 평균 = 앵커값.
초과수익(%p) = 그룹 평균 20일 수익 − 같은 시장 v30 채점 종목 전체의 중간값(리더보드 exc20 과 같은 잣대).
CI = 앵커 단위 iid 부트스트랩 95% (2000회, seed 7). 판정 아님 — 관측 기록.
실행: python research/v30_bucket_grade_20260914.py  (표준출력 + research/RESEARCH_v30_bucket_grade_20260914.md)
"""
import bisect, sqlite3, io
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REG, EXCLUDE, H, JUMP = "20260606", {"20260608", "20260703"}, 20, 0.32
SAFE_OUT = {"WATCH", "EXCLUDE"}

def ro(p): return sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)

con = ro(ROOT.parent / "dh-q7m3k-data" / "ohlcv.db")
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
floor = dates[max(0, bisect.bisect_right(dates, REG) - 1)]
raw = pd.read_sql_query("SELECT ticker,date,close FROM daily_ohlcv WHERE date>=?", con, params=(floor,)); con.close()
raw["ticker"] = raw["ticker"].astype(str).str.zfill(6)
close = raw.pivot(index="date", columns="ticker", values="close").reindex(dates)
P = close.to_numpy(float); col = {t: i for i, t in enumerate(close.columns)}

con = ro(ROOT / "history.db")
sc = pd.read_sql_query("SELECT run_id,market,ticker,final_score_v3 AS s,grade,bucket FROM v3_scores WHERE model_id='v30'", con); con.close()
sc["ticker"] = sc["ticker"].astype(str).str.zfill(6); sc["market"] = sc["market"].str.lower()

# 앵커 선택(run_id → 거래일, 같은 거래일 복수 run 이면 거래일과 같은 run_id 우선, 없으면 최소)
cand = {}
for run in sorted(sc.run_id.unique()):
    if run < REG or run in EXCLUDE: continue
    t = bisect.bisect_right(dates, run) - 1
    if t >= 0: cand.setdefault(t, []).append(run)
chosen = {t: (dates[t] if dates[t] in runs else min(runs)) for t, runs in cand.items()}

def fwd_for(t):
    blk = P[t + 1:t + H + 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        fwd = blk[-1] / blk[0] - 1
        jumps = np.abs(blk[1:] / blk[:-1] - 1)
    ok = np.isfinite(fwd) & (blk[0] > 0) & (blk[-1] > 0) & (np.nanmax(np.where(np.isnan(jumps), -np.inf, jumps), axis=0) <= JUMP)
    return fwd, ok

GROUPS = {
    "bucket": ["BUY", "WAIT", "OBSERVE", "WATCH", "EXCLUDE"],
    "grade": ["A+", "A", "B", "C", "WATCH", "EXCLUDE"],
}
BASKETS = {
    "상위10 (점수순, WATCH·EXCLUDE 제외) = 권고10": lambda g: g[~g.bucket.isin(SAFE_OUT)].nlargest(10, "s"),
    "상위10 (점수순, 필터 없음)":                lambda g: g.nlargest(10, "s"),
    "상위10 (BUY+WAIT 안에서)":                  lambda g: g[g.bucket.isin(["BUY", "WAIT"])].nlargest(10, "s"),
    "상위10 (OBSERVE 안에서)":                   lambda g: g[g.bucket == "OBSERVE"].nlargest(10, "s"),
    "BUY 우선 + 점수순 채움 10 (WATCH·EXCLUDE 제외)": lambda g: pd.concat([g[g.bucket == "BUY"].nlargest(10, "s"),
                                                       g[~g.bucket.isin(SAFE_OUT) & (g.bucket != "BUY")].nlargest(10, "s")]).head(10),
    "상위20 (점수순, WATCH·EXCLUDE 제외)":       lambda g: g[~g.bucket.isin(SAFE_OUT)].nlargest(20, "s"),
    "BUY 전부":                                  lambda g: g[g.bucket == "BUY"],
    "WAIT 전부":                                 lambda g: g[g.bucket == "WAIT"],
}
rec = {k: {} for k in GROUPS}; rec_b = {}; counts = {k: {} for k in GROUPS}; cnt_b = {}
n_anchor = 0
for t, run in sorted(chosen.items()):
    if t + H + 1 >= len(dates): continue
    fwd, ok = fwd_for(t)
    g_all = sc[sc.run_id == run].copy()
    g_all["ci"] = g_all.ticker.map(col)
    g_all = g_all[g_all.ci.notna()]
    g_all["ci"] = g_all.ci.astype(int)
    g_all = g_all[ok[g_all.ci.values]]
    g_all["f"] = fwd[g_all.ci.values] * 100
    mkt_vals = {}
    for mkt, g in g_all.groupby("market"):
        if len(g) < 8: continue
        med = g.f.median()
        for kind, cats in GROUPS.items():
            for c in cats:
                sub = g[g[kind] == c]
                if len(sub) == 0: continue
                mkt_vals.setdefault((kind, c), []).append(sub.f.mean() - med)
                counts[kind].setdefault(c, []).append(len(sub))
        for name, fn in BASKETS.items():
            sub = fn(g)
            if len(sub) == 0: continue
            mkt_vals.setdefault(("basket", name), []).append(sub.f.mean() - med)
            cnt_b.setdefault(name, []).append(len(sub))
    if not mkt_vals: continue
    n_anchor += 1
    for key, vals in mkt_vals.items():
        v = float(np.mean(vals))
        if key[0] == "basket": rec_b.setdefault(key[1], []).append(v)
        else: rec[key[0]].setdefault(key[1], []).append(v)

rng = np.random.default_rng(7)
def ci(vals):
    a = np.asarray(vals)
    if len(a) < 2: return (np.nan, np.nan)
    b = rng.choice(a, size=(2000, len(a))).mean(axis=1)
    return tuple(np.quantile(b, [0.025, 0.975]))
def row(name, vals, cnt):
    lo, hi = ci(vals)
    flag = "범위 모두 양수" if lo > 0 else ("범위 모두 음수" if hi < 0 else "0 걸침")
    return f"| {name} | {np.mean(vals):+.2f} | {len(vals)} | [{lo:+.2f}, {hi:+.2f}] | {flag} | {np.mean(cnt):.0f} |"

out = [f"# RESEARCH — v30 버킷·등급별 20일 성적 (2026-09-14, 관측 전용)", "",
       f"- 규약: §11/리더보드와 동일(진입 t+1·h=20·점프컷 0.32·게이트 run 제외). 앵커 {n_anchor}개 (등록 20260606~, 마지막 유효 앵커 {dates[max(t for t in chosen if t + H + 1 < len(dates))]}).",
       "- 값 = 그룹 평균 20일 수익 − 같은 시장 v30 채점 종목 중간값(%p). 시장별 계산 후 두 시장 평균. CI = 앵커 iid 부트스트랩 95%(2000회).",
       "- **판정 아님.** 그룹은 점수식의 결과물이라 '버킷을 고르면 이만큼 번다'가 아니라 '그 시점 그 표에서 그랬다'로 읽는다.", "",
       "## A. 버킷별 (%p, 후보군 중간값 대비)", "", "| 버킷 | 평균 초과 | 앵커 n | 95% CI | 읽기 | 앵커당 종목 |", "|---|---:|---:|---|---|---:|"]
for c in GROUPS["bucket"]:
    if c in rec["bucket"]: out.append(row(c, rec["bucket"][c], counts["bucket"][c]))
out += ["", "## B. 등급별", "", "| 등급 | 평균 초과 | 앵커 n | 95% CI | 읽기 | 앵커당 종목 |", "|---|---:|---:|---|---|---:|"]
for c in GROUPS["grade"]:
    if c in rec["grade"]: out.append(row(c, rec["grade"][c], counts["grade"][c]))
out += ["", "## C. 바구니 비교 — 실제로 사는 방식끼리", "", "| 바구니 | 평균 초과 | 앵커 n | 95% CI | 읽기 | 앵커당 종목 |", "|---|---:|---:|---|---|---:|"]
for name in BASKETS:
    if name in rec_b: out.append(row(name, rec_b[name], cnt_b[name]))
# 짝비교: 권고10 vs BUY+WAIT 상위10, 권고10 vs 필터없음
def pair(a, b):
    n = min(len(rec_b[a]), len(rec_b[b])); d = np.asarray(rec_b[a][:n]) - np.asarray(rec_b[b][:n]); lo, hi = ci(d)
    return f"| {a} − {b} | {d.mean():+.2f} | {n} | [{lo:+.2f}, {hi:+.2f}] |"
out += ["", "### 짝비교(같은 앵커끼리 차이)", "", "| 비교 | 차이 %p | n | 95% CI |", "|---|---:|---:|---|"]
for a, b in [("상위10 (점수순, WATCH·EXCLUDE 제외) = 권고10", "상위10 (점수순, 필터 없음)"),
             ("상위10 (점수순, WATCH·EXCLUDE 제외) = 권고10", "상위10 (BUY+WAIT 안에서)"),
             ("상위10 (점수순, WATCH·EXCLUDE 제외) = 권고10", "상위10 (OBSERVE 안에서)"),
             ("BUY 우선 + 점수순 채움 10 (WATCH·EXCLUDE 제외)", "상위10 (점수순, WATCH·EXCLUDE 제외) = 권고10")]:
    if a in rec_b and b in rec_b: out.append(pair(a, b))
md = "\n".join(out) + "\n"
print(md)
io.open(ROOT / "research" / "RESEARCH_v30_bucket_grade_20260914.md", "w", encoding="utf-8").write(md)
