# -*- coding: utf-8 -*-
"""가 갈래 — 2026 체제 감도: 코스피 A 사건을 '외국인 20일 순매도 강도'(거래대금 대비) 분위로 나눠 보면 2026 두 사건(3월·7월)이 과거 사건과 같은 칸인가 (2026-11-01, 사후 관측)

Codex 10/31 지적: 원화 금액이 커졌다는 사실만으로 2026 을 별도 체제로 보지 말고 **거래대금 대비 강도**와 자료 범위를 맞춰 보라.
자료: research/out_flow_regime/days.csv·events.csv(10/31 사전 고정 연구 산출, 코스피 A 날 58·사건 22, fx20 = 외국인 20일 순매수/20일 거래대금).
본다: ① 사건별 fx20 순위 — 2026 두 사건이 어디쯤인가 ② 강도 3분위별 과매도 40일·전 종목·코스피 40일 ③ 강도 하위(가장 센 매도) 7사건 vs 나머지 — 사건 부트스트랩 4,000.
재현: python research/regime2026_sensitivity_20261101.py → research/out_flow_regime/regime2026.txt (1초)."""
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; OUT = HERE / "out_flow_regime"
rng = np.random.default_rng(20261030); LOG = []


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


def ev_diff_ci(v, g, k=4000):
    v = np.asarray(v, float); g = np.asarray(g, bool); n = len(v); out = []
    for _ in range(k):
        idx = rng.integers(0, n, n); vv, gg = v[idx], g[idx]
        if gg.any() and (~gg).any(): out.append(vv[gg].mean() - vv[~gg].mean())
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


E = pd.read_csv(OUT / "events.csv", dtype={"date": str}); A = pd.read_csv(OUT / "days.csv", dtype={"date": str}); A = A[A.cell == "A"]
E["fx_pct"] = E.fx20 * 100; E["rank"] = E.fx_pct.rank()
say(f"A 사건 {len(E)} · 외국인 20일 순매수/거래대금(%) 분포: 최소 {E.fx_pct.min():+.2f} · 중앙 {E.fx_pct.median():+.2f} · 최대 {E.fx_pct.max():+.2f}")
say(E.sort_values("fx_pct")[["date", "ks_r20", "fx_pct", "pen20", "os_mean", "all_mean", "ks_f40"]].assign(pen20=lambda x: (x.pen20 * 100).round(2)).round(2).to_string(index=False))
say(f"\n2026 두 사건 순위(센 매도부터): " + " · ".join(f"{d} {int(r)}/{len(E)}위 ({f:+.2f}%)" for d, r, f in E[E.date.str.startswith('2026')][['date','rank','fx_pct']].itertuples(index=False)))
E["ter"] = pd.qcut(E.fx_pct, 3, labels=["센 매도", "보통", "약함/매수"])
say("\n강도 3분위(사건 단위 평균):"); say(E.groupby("ter", observed=True)[["os_mean", "all_mean", "os_tail20", "ks_f40"]].mean().round(2).assign(n=E.ter.value_counts()).to_string())
strong = E.fx_pct <= E.fx_pct.quantile(1 / 3)
for c in ["os_mean", "all_mean", "os_tail20", "ks_f40"]:
    lo, hi = ev_diff_ci(E[c].values, strong.values); say(f"  센 매도 7 − 나머지 15: {c} {E[strong][c].mean()-E[~strong][c].mean():+.2f} [{lo:+.2f}, {hi:+.2f}]")
# 날 단위도(A 날 58)
A = A.assign(fx_pct=A.fx20 * 100); A["ter"] = pd.qcut(A.fx_pct, 3, labels=["센 매도", "보통", "약함/매수"])
say("\nA 날 58 · 강도 3분위:"); say(A.groupby("ter", observed=True)[["os_mean", "all_mean", "os_tail20", "ks_f40"]].mean().round(2).assign(n=A.ter.value_counts()).to_string())
say(f"  날 단위 순위상관 fx20↔과매도 {A[['fx_pct','os_mean']].corr(method='spearman').iloc[0,1]:+.2f} · fx20↔깊이 {A[['fx_pct','ks_r20']].corr(method='spearman').iloc[0,1]:+.2f}")
(OUT / "regime2026.txt").write_text("\n".join(LOG), encoding="utf-8")
