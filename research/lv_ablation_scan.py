# -*- coding: utf-8 -*-
"""
lv_ablation_scan.py — lv_a/lv_b 성분 절제·추가 실험 (§14 탐색 전용, 2026-08-12)
================================================================================
질문: lv_a(저변동+ROE+반전)/lv_b(저변동+ROE)에서 성분을 빼거나 더해 더 좋은 모델이 되는가?
방법: lv_b 실동결 유니버스(lowvol_scores, 44 run) 위에서 변형 10종을 동일 규약
  (pct-rank 합, 핵심 rv 실측필수, 보조 NaN=0.5)으로 재계산 → 일별 앵커 IC →
  **lv_b 기준 짝비교 diff** + 주단위 블록 부트스트랩 CI (§11 동일 정신).
정직성: 탐색·in-sample. OOS 창 자체가 6/05~8/11(폭락+반등 국면 편중), h20 닫힌 앵커
  적음·창 겹침. 변형 10×h3=30검정 — Bonferroni 감안 '기움'까지만. 승격은 새 model id
  + PREREGISTER 만. sv 방향(높을수록↑)은 어제 스캔·sv_a와 정합이나 lv_short(반대 방향)
  전례처럼 국면 의존 위험 있음.
실행: python research/lv_ablation_scan.py
"""
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
RNG = np.random.default_rng(20260812)

hc = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
oc = sqlite3.connect(f"file:{HERE.parent/'dh-q7m3k-data'/'ohlcv.db'}?mode=ro", uri=True)

print("[로드]")
lv = pd.read_sql("SELECT run_id, ticker, lowvol_score FROM lowvol_scores WHERE model_id='lv_b'", hc)
runs = sorted(lv.run_id.unique())
s3 = pd.read_sql(
    'SELECT run_id, ticker, realized_vol, roe_value, "return_1w_%" AS rev FROM stage3_final', hc)
tk = sorted(lv.ticker.unique()); ph = ",".join("?"*len(tk))
px = pd.read_sql(f"SELECT ticker,date,close,volume,change_pct,shares FROM daily_ohlcv "
                 f"WHERE ticker IN ({ph}) AND date>='20250601'", oc, params=tk)
dts = sorted(px.date.unique())
C = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").reindex(dts)
V = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(dts)
R = px.pivot_table(index="date", columns="ticker", values="change_pct", aggfunc="last").reindex(dts)
SH = px.pivot_table(index="date", columns="ticker", values="shares", aggfunc="last").reindex(dts)
sf = pd.read_sql(f"SELECT ticker,date,short_vol_ratio FROM short_flows WHERE date>='20260101' "
                 f"AND ticker IN ({ph})", oc, params=tk)
SVR = sf.pivot_table(index="date", columns="ticker", values="short_vol_ratio", aggfunc="last").reindex(dts).reindex(columns=C.columns)
print(f"  lv_b {len(runs)} runs · 가격패널 {C.shape}")

def rk(s, asc_good, aux=True):
    """pct-rank (asc_good=True→작을수록 점수↑). aux=True면 NaN=0.5, 핵심은 NaN 유지."""
    p = s.rank(pct=True)
    p = (1 - p) if asc_good else p
    return p.fillna(0.5) if aux else p

VARIANTS = {
    "V0 rv단독":          lambda f: f["rv_r"],
    "V1 rv+roe (=lv_b)":  lambda f: f["rv_r"] + f["roe_r"],
    "V2 +rev (=lv_a)":    lambda f: f["rv_r"] + f["roe_r"] + f["rev_r"],
    "V3 +nh252":          lambda f: f["rv_r"] + f["roe_r"] + f["nh_r"],
    "V4 +sv5":            lambda f: f["rv_r"] + f["roe_r"] + f["sv_r"],
    "V5 +nh252+sv5":      lambda f: f["rv_r"] + f["roe_r"] + f["nh_r"] + f["sv_r"],
    "V6 +to20":           lambda f: f["rv_r"] + f["roe_r"] + f["to_r"],
    "V7 rv+nh (roe제거)": lambda f: f["rv_r"] + f["nh_r"],
    "V8 rv+sv (roe제거)": lambda f: f["rv_r"] + f["sv_r"],
    "V9 +lv20":           lambda f: f["rv_r"] + f["roe_r"] + f["lv20_r"],
}
BASE = "V1 rv+roe (=lv_b)"

ics = {h: {v: {} for v in VARIANTS} for h in (5, 10, 20)}   # {h:{variant:{run:ic}}}
sanity = []
for rid in runs:
    if rid not in C.index:
        continue
    t = C.index.get_loc(rid)
    uni = lv[lv.run_id == rid].set_index("ticker")["lowvol_score"]
    uni = uni[uni.index.isin(C.columns)]
    if len(uni) < 15:
        continue
    comp = s3[s3.run_id == rid].set_index("ticker").reindex(uni.index)
    c = C.iloc[:t+1]; r = R.iloc[:t+1]; v = V.iloc[:t+1]
    f = pd.DataFrame(index=uni.index)
    f["rv_r"] = rk(comp["realized_vol"], True, aux=False)          # 핵심: NaN 유지
    f["roe_r"] = rk(comp["roe_value"], False)
    f["rev_r"] = rk(comp["rev"], True)                              # 지난주 더 빠졌을수록↑
    nh = (c[uni.index].iloc[-1] / c[uni.index].iloc[-252:].max() - 1)
    f["nh_r"] = rk(nh, False)                                       # 고점 근접↑
    ts = t - 2                                                      # 공매도 PIT 2일 랙
    sv5 = SVR[uni.index].iloc[max(0, ts-4):ts+1].mean()
    f["sv_r"] = rk(sv5, False)                                      # 공매도비중 높을수록↑
    to20 = (v[uni.index] / SH[uni.index].iloc[:t+1]).iloc[-20:].mean()
    f["to_r"] = rk(to20, True)                                      # 저회전↑
    f["lv20_r"] = rk(r[uni.index].iloc[-20:].std(), True)           # 단기 저변동↑
    for h in (5, 10, 20):
        if t + h >= len(R):
            continue
        y = ((1 + R[uni.index].iloc[t+1:t+1+h]).prod() - 1)
        for vn, fn in VARIANTS.items():
            s = fn(f)
            m = s.notna() & y.notna()
            if m.sum() < 15:
                continue
            ics[h][vn][rid] = s[m].rank().corr(y[m].rank())
    # 재현 검증: V1 vs 동결 lv_b 점수 순위상관
    s1 = VARIANTS[BASE](f)
    m = s1.notna() & uni.notna()
    if m.sum() >= 15:
        sanity.append(s1[m].rank().corr(uni[m].rank()))

print(f"\n[재현 검증] V1(재계산) vs 동결 lv_b 점수 순위상관: 평균 {np.mean(sanity):.3f} "
      f"(min {np.min(sanity):.3f}, n={len(sanity)} runs) — 1.0 근접이어야 계산 규약 재현 성공")

def week_block_boot(diffs_by_run, nb=3000):
    wk = {}
    for rid, d in diffs_by_run.items():
        w = pd.Timestamp(rid).isocalendar()[:2]
        wk.setdefault(w, []).append(d)
    blocks = [np.mean(v) for v in wk.values()]
    if len(blocks) < 3:
        return (np.nan, np.nan, len(blocks))
    b = np.asarray(blocks)
    i = RNG.integers(0, len(b), (nb, len(b)))
    mm = b[i].mean(axis=1)
    return float(np.quantile(mm, .025)), float(np.quantile(mm, .975)), len(blocks)

for h in (5, 10, 20):
    print(f"\n===== h{h} — 변형별 IC와 lv_b 짝비교(diff, 주블록 부트스트랩) =====")
    base = ics[h][BASE]
    rows = []
    for vn in VARIANTS:
        d = ics[h][vn]
        common = sorted(set(d) & set(base))
        if not common:
            continue
        vals = [d[r] for r in common]
        diffs = {r: d[r] - base[r] for r in common}
        lo, hi, nw = week_block_boot(diffs)
        rows.append(dict(variant=vn, ic=np.mean(vals), n_run=len(common),
                         diff=np.mean(list(diffs.values())), ci_lo=lo, ci_hi=hi, n_week=nw,
                         wk_pos=np.mean([np.mean([diffs[r] for r in common
                                        if pd.Timestamp(r).isocalendar()[:2] == w]) > 0
                                        for w in {pd.Timestamp(r).isocalendar()[:2] for r in common}])))
    df = pd.DataFrame(rows).sort_values("diff", ascending=False)
    print(df.to_string(index=False, float_format=lambda x: f"{x:+.4f}" if abs(x) < 5 else f"{x:.0f}"))
    df.to_csv(HERE / "research" / f"lv_ablation_h{h}.csv", index=False)

print("\n검정 수 ≈ 30 (10변형×3지평) — Bonferroni 감안, CI 전부 0 초과 + 주별일관 ≥60% + "
      "지평 간 재현이어야 '강한 기움'. 결론이 좋아도 승격은 새 model id + PREREGISTER 로만.")
