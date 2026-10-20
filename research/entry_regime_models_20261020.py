# -*- coding: utf-8 -*-
"""entry_regime_models_20261020.py — ② 모델 상위10 의 보유 수익을 '진입 국면'별로 (2026-10-20, 읽기 전용 · 관측)

entry_regime_20261020.py 의 ② 가 운용 채택 도구의 옛 앵커 파일(6~8월 초, 전부 '급락 뒤')만 읽어 비교가 안 돼, 등록 후 앵커 전부로 다시 계산한다.
규칙(사전등록 §1 과 같게, 희석 배지 제외만 생략): 앵커 run t(등록 후·게이트 통과·중복 제거) → 시장별 점수 상위 10 동일가중 → t+1 종가 매수 → t+1+h 종가(h=20·40).
  절대수익 = 바구니 평균 · 초과 = 바구니 평균 − 같은 시장 전 종목 동일가중(그날 시세 있는 종목) · 점프컷 없음(돈 잣대는 실제 보유 결과).
진입 국면 = 앵커일 전 20거래일 코스닥 수익(A ≤−5 · B −5~0 · C 0~+5 · D >+5) 과 코스닥 종가 vs 20일선.
출력: research/out_entry_regime/models_summary.md · model_anchors_all.csv
"""
import sys, sqlite3
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import leaderboard as lb  # noqa: E402

OUT = HERE / "out_entry_regime"; OUT.mkdir(exist_ok=True)
BOOT, SEED, TOP_N = 4000, 7, 10
BUCKETS = [("A 급락 뒤(≤−5%)", -np.inf, -5.0), ("B 약세(−5~0%)", -5.0, 0.0), ("C 강세(0~+5%)", 0.0, 5.0), ("D 급등 뒤(>+5%)", 5.0, np.inf)]
MODELS = {"v30": ("v3_scores", "final_score_v3"), "lv_b": ("lowvol_scores", "lowvol_score"), "le_a": ("wu_scores", "wu_score")}


def bucket_of(x):
    for name, lo, hi in BUCKETS:
        if (lo == -np.inf and x <= hi) or (lo < x <= hi):
            return name
    return None


def month_block_ci(vals, dates):
    df = pd.DataFrame({"v": vals, "m": [str(d)[:6] for d in dates]}).dropna()
    groups = [g.v.values for _, g in df.groupby("m")]
    if len(groups) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(SEED); b = []
    for _ in range(BOOT):
        pick = rng.integers(0, len(groups), len(groups))
        b.append(np.concatenate([groups[i] for i in pick]).mean())
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def nonoverlap(idx_sorted, h):
    k, last = 0, -10**9
    for i in idx_sorted:
        if i - last >= h:
            k += 1; last = i
    return k


con_o = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
idx = pd.read_sql("SELECT series, date, close FROM market_daily WHERE series='KOSDAQ'", con_o).set_index("date")["close"].sort_index()
close, mkt = lb.load_ohlcv(); con_o.close()
mkt = mkt.str.lower()
dates = list(close.index); N = len(dates); pos = {d: i for i, d in enumerate(dates)}
kq = idx.reindex(dates).ffill(); kq_sma20 = kq.rolling(20).mean(); r20 = (kq / kq.shift(20) - 1) * 100
con = sqlite3.connect(f"file:{REPO / 'history.db'}?mode=ro", uri=True)
partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl

recs = []
for mid, (tb, sc) in MODELS.items():
    S = pd.read_sql(f"SELECT run_id, market, ticker, {sc} AS score FROM {tb} WHERE model_id=?", con, params=(mid,))
    S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str); S["market"] = S.market.str.lower()
    S["score"] = S.score.astype(float).where(S.score.astype(float) > -999)
    keep = lb.dedupe_by_anchor(S, didx, excl, reg=lb.REG_DATE[mid])
    for rid, g in S.groupby("run_id"):
        if rid not in keep:
            continue
        t = lb.anchor(rid, didx)
        if t is None:
            continue
        rec = {"model": mid, "run_id": rid, "anchor": dates[t], "i": t, "r20": float(r20.iloc[t]) if not np.isnan(r20.iloc[t]) else np.nan,
               "below_sma20": bool(kq.iloc[t] < kq_sma20.iloc[t])}
        rec["bucket"] = bucket_of(rec["r20"]) if not np.isnan(rec["r20"]) else None
        for h in (20, 40):
            if t + 1 + h >= N:
                rec[f"abs_{h}"] = rec[f"exc_{h}"] = rec[f"kq_{h}"] = np.nan
                continue
            f = (close.iloc[t + 1 + h] / close.iloc[t + 1] - 1) * 100
            rec[f"kq_{h}"] = float((kq.iloc[t + 1 + h] / kq.iloc[t + 1] - 1) * 100)
            absr, exc = [], []
            for m, gm in g.groupby("market"):
                s = gm.dropna(subset=["score"]).set_index("ticker")["score"].sort_values(ascending=False)
                top = [x for x in s.index if x in f.index and not np.isnan(f.get(x, np.nan))][:TOP_N]
                if len(top) < 5:
                    continue
                uni = f[(mkt.reindex(f.index) == m) & f.notna()]
                absr.append(f[top].mean()); exc.append(f[top].mean() - uni.mean())
            rec[f"abs_{h}"] = float(np.mean(absr)) if absr else np.nan
            rec[f"exc_{h}"] = float(np.mean(exc)) if exc else np.nan
        recs.append(rec)
A = pd.DataFrame(recs).sort_values(["model", "anchor"])
A.to_csv(OUT / "model_anchors_all.csv", index=False, encoding="utf-8-sig")

lines = ["# ② 모델 상위10(시장별 동일가중) 보유 수익 — 진입 국면별 (2026-10-20, 등록 후 앵커 전부 · 관측)", "",
         f"가격 ~{dates[-1]} · 매수 = 앵커 다음 거래일 종가 · 초과 = 같은 시장 전 종목 동일가중 대비 · 구간 = 월 블록 부트스트랩 95% · 겹치지 않는 앵커 = h 거래일 간격", ""]
for h in (40, 20):
    lines += [f"## 보유 {h}거래일", "",
              "| 모델 | 진입 국면 | 앵커 n(겹치지 않는) | 앵커 기간 | 절대수익(%) [95%] | 승률 | 초과(%p) [95%] | 승률(초과) | 보유 중 코스닥(%) |",
              "|---|---|---|---|---|---|---|---|---|"]
    for mid in MODELS:
        a = A[(A.model == mid)].dropna(subset=[f"abs_{h}"])
        groups = [(n, a[a.bucket == n]) for n, *_ in BUCKETS] + [("코스닥 < 20일선", a[a.below_sma20]), ("코스닥 ≥ 20일선", a[~a.below_sma20]), ("전체", a)]
        for name, g in groups:
            if g.empty:
                continue
            c1 = month_block_ci(g[f"abs_{h}"].values, g.anchor.values); c2 = month_block_ci(g[f"exc_{h}"].values, g.anchor.values)
            lines.append(f"| {mid} | {name} | {len(g)}({nonoverlap(sorted(g.i.values), h)}) | {g.anchor.min()[4:]}~{g.anchor.max()[4:]} | {g[f'abs_{h}'].mean():+.2f} [{c1[0]:+.2f},{c1[1]:+.2f}] | {(g[f'abs_{h}'] > 0).mean():.0%} | {g[f'exc_{h}'].mean():+.2f} [{c2[0]:+.2f},{c2[1]:+.2f}] | {(g[f'exc_{h}'] > 0).mean():.0%} | {g[f'kq_{h}'].mean():+.2f} |")
    lines.append("")
lines += ["주의: 2026-06 이후 한 사이클이라 '급락 뒤'=6월, '강세·급등 뒤'=7~8월과 거의 같다(국면 효과 ≠ 시기 효과). 희석 배지 제외는 생략. 비용 미차감. 판정 아님.", ""]
(OUT / "models_summary.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
