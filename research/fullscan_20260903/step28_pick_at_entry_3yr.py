# -*- coding: utf-8 -*-
# [경로 이식] research/fullscan_20260903/ 에서 실행. 읽기 전용. 관측·판정 아님.
"""step28_pick_at_entry_3yr.py — "매수 시점에 어느 뼈대가 좋을지 고를 수 있나" 3년 시험 (2026-10-03)
재료: out/accumulate_3yr_bars.csv(뼈대 4개의 매수일별 40일 초과, 국면 라벨) + ../dart_history/v30_bars_3yr.csv(재계산 v30 뼈대).
규칙(결과 보기 전 고정):
  · 결정일 t 에 알 수 있는 것 = 매수일 ≤ t−41 인 목록의 40일 초과(끝난 것만). '폼' = 최근 L=20개 평균.
  · 전략 A 최근 1등 따라가기 · B 꼴찌 따라가기 · C 고르게 섞기 · D 국면 규칙(2024년 자료로 국면별 1등을 정해 2025~26 에 적용 — 사후 아님)
    · E 하늘이 알려줬다면(그날 실제 1등 — 상한선, 실행 불가).
  · 성적 = 그 뼈대의 그날 40일 초과(%p). 비겹침 40일 블록 부트스트랩 CI(2,000회, seed 7). 폼 순위 ↔ 실제 순위 상관(스피어만) 도 적는다.
"""
import numpy as np, pandas as pd
from pathlib import Path

HERE = Path(__file__).resolve().parent
B = pd.read_csv(HERE / "out" / "accumulate_3yr_bars.csv", dtype={"list_date": str})
V = pd.read_csv(HERE.parent / "dart_history" / "v30_bars_3yr.csv", dtype={"list_date": str}); V["skeleton"] = "v30뼈대(수급·배당 제외)"
V = V.merge(B[["list_date", "regime_pit"]].drop_duplicates("list_date"), on="list_date", how="left")
A = pd.concat([B[["list_date", "skeleton", "excess", "regime_pit"]], V[["list_date", "skeleton", "excess", "regime_pit"]]])
W = A.pivot_table(index="list_date", columns="skeleton", values="excess").sort_index()
reg = A.drop_duplicates("list_date").set_index("list_date")["regime_pit"].reindex(W.index)
dates = list(W.index); L = 20; H = 40; names = list(W.columns)


def block_ci(x, h=40, k=2000, seed=7):
    x = np.asarray(x, float); n = len(x); rng = np.random.default_rng(seed); nb = int(np.ceil(n / h)); res = []
    for _ in range(k):
        st = rng.integers(0, max(n - h + 1, 1), nb); res.append(np.concatenate([x[s:s + h] for s in st])[:n].mean())
    return np.percentile(res, [2.5, 97.5])


# 2024 국면별 1등(사전 고정용)
_cut25 = dates[dates.index(min(dd for dd in dates if dd >= "20250101")) - 41]   # [REPLY_007] 2025-01-01 에 끝난 성적만
train = W[W.index <= _cut25]; rtrain = reg[reg.index <= _cut25]
best_by_regime = {rg: train[rtrain == rg].mean().idxmax() for rg in rtrain.dropna().unique() if (rtrain == rg).sum() >= 10}
print("2024 국면별 1등(규칙 D 에 고정):", best_by_regime)
rows = []
for i, t in enumerate(dates):
    known = W.iloc[:i][W.index[:i] <= dates[max(i - H - 1, 0)]] if i > H else W.iloc[:0]
    known = known.tail(L)
    if len(known) < L // 2: continue
    form = known.mean(); y = W.loc[t]
    if y.isna().any() or form.isna().any(): continue
    lead = form.idxmax(); lag = form.idxmin()
    d = dict(t=t, leader=y[lead], laggard=y[lag], mix=y.mean(), oracle=y.max(), rank_corr=pd.Series(form).rank().corr(y.rank(), method="spearman"))
    rg = reg.loc[t]
    if t >= "20250101" and rg in best_by_regime: d["regime_rule"] = y[best_by_regime[rg]]; d["mix_test"] = y.mean()
    rows.append(d)
R = pd.DataFrame(rows)
print(f"\n결정일 {len(R)}일({R.t.min()}~{R.t.max()}) · 독립 40일 구간 약 {len(R)//H} · 뼈대 {len(names)}개")
for k, nm in (("leader", "A 최근 1등 따라가기"), ("laggard", "B 꼴찌 따라가기"), ("mix", "C 고르게 섞기"), ("oracle", "E 그날 실제 1등(상한, 실행 불가)")):
    x = R[k].values; ci = block_ci(x); print(f"  {nm:<22} 40일 초과 평균 {x.mean():+.2f}%p [{ci[0]:+.2f}, {ci[1]:+.2f}] · 양수 {(x>0).mean():.0%}")
d = (R.leader - R.mix).values; ci = block_ci(d); print(f"  A − C: {d.mean():+.2f}%p [{ci[0]:+.2f}, {ci[1]:+.2f}] · A가 C 이긴 날 {(d>0).mean():.0%}")
print(f"  폼 순위 ↔ 실제 순위 상관(일평균): {R.rank_corr.mean():+.3f}")
Rt = R.dropna(subset=["regime_rule"])
if len(Rt):
    d2 = (Rt.regime_rule - Rt.mix_test).values; ci = block_ci(d2); x = Rt.regime_rule.values
    print(f"  D 국면 규칙(2024 학습 → 2025~26 적용, {len(Rt)}일): 평균 {x.mean():+.2f}%p · D − C {d2.mean():+.2f}%p [{ci[0]:+.2f}, {ci[1]:+.2f}] · 이긴 날 {(d2>0).mean():.0%}")
for n in names:
    x = W[n].dropna().values; print(f"    고정 {n:<22} {x.mean():+.2f}%p · 양수 {(x>0).mean():.0%}")
# 연도별 1등
print("\n연도별 1등(사후):", {y: W[W.index.str[:4] == y].mean().idxmax() for y in ("2024", "2025", "2026")})
R.to_csv(HERE / "out" / "pick_at_entry_3yr.csv", index=False, encoding="utf-8-sig")
