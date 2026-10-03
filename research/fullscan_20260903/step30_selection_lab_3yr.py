# -*- coding: utf-8 -*-
# [경로 이식] research/fullscan_20260903/ 에서 실행. 읽기 전용. 관측·가설 생성 — 판정 아님.
"""step30_selection_lab_3yr.py — "지금 기간에 어느 스타일(저변동/반등)로 살지" 고르는 방식 20여 가지를 같은 틀에서 (2026-10-03)
잣대: 결정일 t 에 고른 스타일의 다음 40일 초과(%p). 비교 = "항상 저변동"(기준선)과 "섞기". 평가 구간 2025(2024 로 학습)·2026(2024~25 로 학습) — 미리 못 본 자료.
스타일: 저변동 = 가격4팩터·조용함 평균 / 반등 = 저점탈출·과매도프록시·v30뼈대 평균 (step27·v30_accumulate 산출). 비중 w ∈ [0,1] = 저변동 몫.
주의: 규칙 ~22개 → 우연으로 1~2개는 좋아 보임. 2025·2026 둘 다 기준선 이상 + 블록 CI 하단 > 0 이어야 '후보'.
"""
import numpy as np, pandas as pd, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
exec(open(HERE / "step29_style_predictors_3yr.py", encoding="utf-8").read().split("rows = []")[0])   # X(재료)·S·W·LOW·REB·dates·feats 재사용
D = S.index; low = W[LOW].mean(axis=1).reindex(D); reb = W[REB].mean(axis=1).reindex(D); mix = (low + reb) / 2
Sk = pd.Series(S.values, index=D); known = Sk.shift(41)   # 결정일에 아는 '끝난' S
F = X.copy()
yr = pd.Series(D.str[:4], index=D)


def block_ci(x, h=40, k=2000, seed=7):
    x = np.asarray(x, float); n = len(x); rng = np.random.default_rng(seed); nb = int(np.ceil(n / h)); res = []
    for _ in range(k):
        st = rng.integers(0, max(n - h + 1, 1), nb); res.append(np.concatenate([x[s:s + h] for s in st])[:n].mean())
    return np.percentile(res, [2.5, 97.5])


rules = {}
# --- 고정
rules["항상 저변동(기준선)"] = lambda: pd.Series(1.0, index=D)
rules["항상 반등"] = lambda: pd.Series(0.0, index=D)
rules["섞기 50:50"] = lambda: pd.Series(0.5, index=D)
# --- 성적 기반
for L in (10, 20, 40):
    rules[f"최근 1등(끝난 S 최근 {L})"] = (lambda L=L: (known.rolling(L, min_periods=L // 2).mean() > 0).astype(float).where(known.rolling(L, min_periods=L // 2).mean().notna(), 0.5))
    rules[f"되돌림(최근 {L} 꼴찌)"] = (lambda L=L: (known.rolling(L, min_periods=L // 2).mean() < 0).astype(float).where(known.rolling(L, min_periods=L // 2).mean().notna(), 0.5))
def hyst(th):
    m = known.rolling(20, min_periods=10).mean(); w = []; cur = 1.0
    for v in m.values:
        if np.isfinite(v):
            if v > th: cur = 1.0
            elif v < -th: cur = 0.0
        w.append(cur)
    return pd.Series(w, index=D)
rules["전환 히스테리시스(±2%p)"] = lambda: hyst(2.0)
rules["전환 히스테리시스(±4%p)"] = lambda: hyst(4.0)
# --- 시장 기반(학습 없음, 부호는 직관으로 고정: 상승·고점권·거래대금↑ → 저변동 / 하락·변동성 급등 → 반등)
rules["코스피 20일 ↑→저변동 ↓→반등"] = lambda: (F["코스피 20일 수익"] > 0).astype(float)
rules["코스닥 20일 ↑→저변동"] = lambda: (F["코스닥 20일 수익"] > 0).astype(float)
for th in (0.03, 0.05, 0.10):
    rules[f"지수 고점권(252일 고점 −{int(th*100)}% 안)→저변동, 밖→반등"] = (lambda th=th: (F["코스닥 252일 고점 대비"] > -th).astype(float))
rules["코스닥 120일선 위→저변동"] = lambda: (F["코스닥 vs 120일선"] > 0).astype(float)
def volspike(k, ratio=1.2):
    sp = (F["코스닥 변동성 변화(20/60)"] > ratio).astype(float).rolling(k, min_periods=1).max(); return 1.0 - sp
rules["변동성 급등(20/60>1.2) 뒤 10일 반등"] = lambda: volspike(10)
rules["변동성 급등 뒤 20일 반등"] = lambda: volspike(20)
rules["고점권(−5%) 또는 코스피20↑ → 저변동"] = lambda: (((F["코스닥 252일 고점 대비"] > -0.05) | (F["코스피 20일 수익"] > 0))).astype(float)
rules["저변동 기본, 코스피20↓ 그리고 변동성급등 때만 반등"] = lambda: 1.0 - ((F["코스피 20일 수익"] < 0) & (F["코스닥 변동성 변화(20/60)"] > 1.2)).astype(float)
# --- 비중 기반
def riskparity():
    sl = low.shift(41).rolling(60, min_periods=20).std(); sr = reb.shift(41).rolling(60, min_periods=20).std()
    return ((1 / sl) / (1 / sl + 1 / sr)).fillna(0.5)
rules["위험 균형(최근 변동성 역수 비중)"] = riskparity
rules["저변동 70 : 반등 30"] = lambda: pd.Series(0.7, index=D)
# --- 학습 기반(월별 재학습, 확장 창, 결정일 기준 끝난 S 만 학습)
def ml(kind):
    from sklearn.linear_model import Ridge, LogisticRegression
    cols = list(F.columns); w = pd.Series(np.nan, index=D)
    months = sorted(set(D.str[:6]))
    for mth in months:
        if mth < "202407": continue
        te = D.str[:6] == mth; first = D[te][0]
        tr = (D < first) & (Sk.shift(41).notna()) & (D <= pd.Series(D).shift(41).reindex(range(len(D))).fillna("00000000").values[list(D).index(first)])
        trm = tr & F.notna().all(axis=1) & Sk.notna()
        if trm.sum() < 80: continue
        Xtr = F[trm].values; ytr = Sk[trm].values; Xte = F[te].fillna(F[trm].median()).values
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9; Xtr = (Xtr - mu) / sd; Xte = (Xte - mu) / sd
        if kind == "ridge":
            p = Ridge(alpha=10.0).fit(Xtr, ytr).predict(Xte); w[te] = (p > 0).astype(float)
        else:
            p = LogisticRegression(C=0.1, max_iter=500).fit(Xtr, (ytr > 0).astype(int)).predict_proba(Xte)[:, 1]; w[te] = (p > 0.5).astype(float)
    return w.fillna(0.5)
rules["릿지 회귀(변수 25·월별 재학습)"] = lambda: ml("ridge")
rules["로지스틱(변수 25·월별 재학습)"] = lambda: ml("logit")

base = low  # 기준선 실현
out = []
for name, fn in rules.items():
    try:
        w = fn().reindex(D).astype(float)
    except Exception as e:
        print("skip", name, e); continue
    real = w * low + (1 - w) * reb
    row = dict(rule=name)
    for y in ("2024", "2025", "2026"):
        m = (yr == y) & real.notna() & base.notna()
        row[f"{y}_vs_low"] = (real[m] - base[m]).mean(); row[f"{y}_vs_mix"] = (real[m] - mix[m]).mean(); row[f"{y}_lowshare"] = w[m].mean()
    m = (yr >= "2025") & real.notna(); d = (real[m] - base[m]).values; ci = block_ci(d)
    row.update(oos_vs_low=d.mean(), oos_ci_lo=ci[0], oos_ci_hi=ci[1], oos_pos_days=(d > 0).mean(), oos_abs=real[m].mean())
    out.append(row)
R = pd.DataFrame(out).sort_values("oos_vs_low", ascending=False)
R.to_csv(HERE / "out" / "selection_lab_3yr.csv", index=False, encoding="utf-8-sig")
print(f"규칙 {len(R)}개 · 평가 2025~26 결정일 {int(((yr>='2025')).sum())} (독립 40일 구간 약 {int((yr>='2025').sum())//40}) · 기준선 '항상 저변동' 40일 초과: 2025 {low[yr=='2025'].mean():+.2f} · 2026 {low[yr=='2026'].mean():+.2f}%p")
print(f"{'규칙':<40} {'2024(학습기)':>10} {'2025':>8} {'2026':>8} {'OOS 25~26 vs 항상저변동 [블록CI]':>34} {'이긴날':>6} {'저변동 비중 25/26':>14}")
for _, r in R.iterrows():
    flag = "★" if (r.oos_ci_lo > 0 and r["2025_vs_low"] > 0 and r["2026_vs_low"] > 0) else " "
    print(f"{flag}{r.rule:<40} {r['2024_vs_low']:>+9.2f} {r['2025_vs_low']:>+8.2f} {r['2026_vs_low']:>+8.2f} {r.oos_vs_low:>+10.2f} [{r.oos_ci_lo:+.2f},{r.oos_ci_hi:+.2f}] {r.oos_pos_days:>8.0%} {r['2025_lowshare']:>6.0%}/{r['2026_lowshare']:.0%}")
print("\n읽는 법: 숫자 = 그 규칙 − '항상 저변동'(%p, 40일 초과). ★ = 2025·2026 둘 다 양(+) 이고 OOS 블록 CI 하단 > 0. 규칙 20여 개라 우연으로 1~2개는 좋아 보인다.")
