# -*- coding: utf-8 -*-
# [경로 이식] research/fullscan_20260903/ 에서 실행. 읽기 전용. 관측·가설 생성 — 판정 아님.
"""step29_style_predictors_3yr.py — "다음 40일에 저변동 계열이 이길지, 반등 계열이 이길지"를 매수 시점에 아는 변수가 있나 (2026-10-03)

맞힐 것: S(t) = 저변동 계열(가격4팩터·조용함 평균 40일 초과) − 반등 계열(저점탈출·과매도프록시·v30뼈대 평균). 양수 = 저변동이 이김.
재료 X(t): 매수일 t 종가까지의 시장 변수 ~25개(아래 feats). 전부 t 이전 정보.
방법: ① 변수별 스피어만 상관(40일 블록 부트스트랩 CI) ② 변수 3등분 상·하위의 S 평균 차이 ③ 규칙 walk-forward(2024→2025, 2024~25→2026): 변수 부호·중앙값 기준으로 '저변동/반등' 고르기 → 실현 초과 vs 섞기
      ④ 묶음: ①에서 2024~25 로 뽑은 상위 3개 변수의 순위 평균 → 2026 적용. ⑤ 꼴찌 피하기: 반등 계열 40일 초과 < −3%p 를 맞히는 변수.
주의: 독립 40일 구간 14개. 변수 25개면 우연히 1~2개는 CI 가 0을 안 걸친다 → 2026 OOS 와 방향 일관성을 같이 봐야 한다.
"""
import numpy as np, pandas as pd
from pathlib import Path
from fslib import *

HERE = Path(__file__).resolve().parent
P = Panel(); ok = guards(P); c = P.close.astype(np.float64); T, N = P.T, P.N; dates = list(P.dates)
B = pd.read_csv(HERE / "out" / "accumulate_3yr_bars.csv", dtype={"list_date": str})
V = pd.read_csv(HERE.parent / "dart_history" / "v30_bars_3yr.csv", dtype={"list_date": str}); V["skeleton"] = "v30뼈대"
A = pd.concat([B[["list_date", "skeleton", "excess"]], V[["list_date", "skeleton", "excess"]]])
W = A.pivot_table(index="list_date", columns="skeleton", values="excess").sort_index()
LOW = ["가격4팩터(px_a)", "조용함(lv_e뼈대)"]; REB = ["저점탈출(le_a뼈대)", "과매도프록시(RSI)", "v30뼈대"]
S = (W[LOW].mean(axis=1) - W[REB].mean(axis=1)).dropna(); REBX = W[REB].mean(axis=1)

# ---------------------------------------------------------------- 재료
def sma(x, w): return pd.Series(x).rolling(w, min_periods=w).mean().values
kq = pd.Series(P.kosdaq).ffill().values; kp = pd.Series(P.kospi).ffill().values; fx = pd.Series(P.usdkrw).ffill().values
def ret(x, n): return np.r_[np.full(n, np.nan), x[n:] / x[:-n] - 1]
r = P.ret; okf = ok & np.isfinite(r)
up = np.nanmean(np.where(okf, (r > 0).astype(float), np.nan), axis=1)
s20 = roll_mean(c, 20, 15); s60 = roll_mean(c, 60, 40)
br20 = np.nanmean(np.where(ok, (c > s20).astype(float), np.nan), axis=1); br60 = np.nanmean(np.where(ok, (c > s60).astype(float), np.nan), axis=1)
hi252 = roll_max(c, 252, 120); lo252 = roll_min(c, 252, 120)
nh = np.nanmean(np.where(ok, (c >= hi252 * 0.98).astype(float), np.nan), axis=1); nl = np.nanmean(np.where(ok, (c <= lo252 * 1.02).astype(float), np.nan), axis=1)
r20m = np.r_[np.full((20, N), np.nan), c[20:] / c[:-20] - 1]
disp20 = np.nanstd(np.where(ok, r20m, np.nan), axis=1)                      # 종목 간 흩어짐
corr_proxy = np.nanmean(np.where(okf, np.sign(r) == np.sign(np.nan_to_num(ret(kq, 1))[:, None]), np.nan), axis=1)  # 지수와 같은 방향인 종목 비율
amt = P.amt; amt_lvl = np.nanmean(np.where(ok, amt, np.nan), axis=1); amt_ratio = pd.Series(amt_lvl).rolling(20).mean().values / pd.Series(amt_lvl).rolling(60).mean().values
lv60 = roll_std(r, 60, 40); q = np.nanpercentile(np.where(ok, lv60, np.nan), [20, 80], axis=1)
lowv = np.where(ok & (lv60 <= q[0][:, None]), r20m, np.nan); highv = np.where(ok & (lv60 >= q[1][:, None]), r20m, np.nan)
lv_spread = np.nanmean(lowv, axis=1) - np.nanmean(highv, axis=1)            # 최근 20일 저변동−고변동 수익 차이
kqvol20 = pd.Series(ret(kq, 1)).rolling(20).std().values * np.sqrt(252)
feats = {
    "코스닥 5일 수익": ret(kq, 5), "코스닥 20일 수익": ret(kq, 20), "코스닥 60일 수익": ret(kq, 60), "코스피 20일 수익": ret(kp, 20),
    "코스닥 vs 20일선": kq / sma(kq, 20) - 1, "코스닥 vs 60일선": kq / sma(kq, 60) - 1, "코스닥 vs 120일선": kq / sma(kq, 120) - 1,
    "코스닥 20일 변동성": kqvol20, "코스닥 변동성 변화(20/60)": kqvol20 / (pd.Series(ret(kq, 1)).rolling(60).std().values * np.sqrt(252)),
    "코스닥 252일 고점 대비": kq / pd.Series(kq).rolling(252, min_periods=120).max().values - 1,
    "20일선 위 종목 비율": br20, "60일선 위 종목 비율": br60, "상승일 비율(5일)": pd.Series(up).rolling(5).mean().values, "상승일 비율(20일)": pd.Series(up).rolling(20).mean().values,
    "신고가 근접 비율": nh, "신저가 근접 비율": nl, "신고가−신저가": nh - nl,
    "종목 간 흩어짐(20일 수익 표준편차)": disp20, "지수 동행 비율(20일 평균)": pd.Series(corr_proxy).rolling(20).mean().values,
    "거래대금 수준(20/60)": amt_ratio, "환율 20일 변화": ret(fx, 20), "환율 vs 60일선": fx / sma(fx, 60) - 1,
    "저변동−고변동 최근 20일 수익": lv_spread, "저변동−고변동 최근 60일 수익": pd.Series(lv_spread).rolling(60).mean().values,
}
# 스타일 모멘텀: 끝난 S 의 최근 20개 평균(결정일 t 에 아는 것 = 매수일 ≤ t−41)
Sf = S.reindex(dates); known = pd.Series(Sf.values).shift(41).rolling(20, min_periods=10).mean().values; feats["스타일 모멘텀(끝난 S 최근 20)"] = known
X = pd.DataFrame(feats, index=dates).reindex(S.index); y = S.copy(); yr = REBX.reindex(S.index)
X = X.replace([np.inf, -np.inf], np.nan)


def block_ci(fn, n, h=40, k=1000, seed=7):
    rng = np.random.default_rng(seed); nb = int(np.ceil(n / h)); res = []
    for _ in range(k):
        st = rng.integers(0, max(n - h + 1, 1), nb); idx = np.concatenate([np.arange(s, min(s + h, n)) for s in st])[:n]; res.append(fn(idx))
    return np.percentile(res, [2.5, 97.5])


rows = []
for f in X.columns:
    m = X[f].notna() & y.notna(); x = X.loc[m, f].values; yy = y[m].values; n = len(x)
    if n < 100: continue
    rho = pd.Series(x).corr(pd.Series(yy), method="spearman"); ci = block_ci(lambda idx: pd.Series(x[idx]).corr(pd.Series(yy[idx]), method="spearman"), n)
    t1, t3 = np.nanpercentile(x, [33.3, 66.7]); hi = yy[x >= t3].mean(); lo = yy[x <= t1].mean()
    # walk-forward 규칙: 학습 구간 중앙값 기준으로 "변수가 중앙값보다 크면 저변동, 작으면 반등"(부호는 학습 상관으로)
    d = np.array(S.index[m]); res = {}
    for name, tr_end, te_start, te_end in (("2025", "20250101", "20250101", "20260101"), ("2026", "20260101", "20260101", "29991231")):
        # [2026-10-03 REPLY_007 §2 반영] 학습은 평가 시작일에 '끝난' 성적만: 목록일이 평가 시작보다 41거래일 이상 앞선 것
        _cut = dates[max(dates.index(min(dd for dd in dates if dd >= te_start)) - 41, 0)] if any(dd >= te_start for dd in dates) else te_start
        tr = d <= _cut; te = (d >= te_start) & (d < te_end)
        if tr.sum() < 60 or te.sum() < 40: continue
        sign = np.sign(pd.Series(x[tr]).corr(pd.Series(yy[tr]), method="spearman") or 0); med = np.median(x[tr])
        pick_low = (sign * (x[te] - med)) > 0            # 저변동 고름
        realized = np.where(pick_low, W.loc[d[te], LOW].mean(axis=1).values, W.loc[d[te], REB].mean(axis=1).values)
        mix = W.loc[d[te]].mean(axis=1).values
        res[name] = (realized.mean() - mix.mean(), (np.sign(yy[te]) == np.where(pick_low, 1, -1)).mean())
    # 꼴찌 피하기: 반등 계열 < −3 를 변수로 맞히나 (상관 부호 반대 방향)
    rb = yr[m].values; bad = rb < -3; rho_bad = pd.Series(x).corr(pd.Series(bad.astype(float)), method="spearman")
    rows.append(dict(feature=f, n=n, rho=rho, ci_lo=ci[0], ci_hi=ci[1], top_minus_bottom=hi - lo,
                     wf2025_excess=res.get("2025", (np.nan, np.nan))[0], wf2025_hit=res.get("2025", (np.nan, np.nan))[1],
                     wf2026_excess=res.get("2026", (np.nan, np.nan))[0], wf2026_hit=res.get("2026", (np.nan, np.nan))[1], rho_avoid_bad=rho_bad))
R = pd.DataFrame(rows).sort_values("rho", key=lambda s: s.abs(), ascending=False)
R.to_csv(HERE / "out" / "style_predictors_3yr.csv", index=False, encoding="utf-8-sig")
pd.set_option("display.width", 220)
print(f"표본: 결정일 {len(y)} ({S.index.min()}~{S.index.max()}) · 독립 40일 구간 약 {len(y)//40} · S 평균 {y.mean():+.2f}%p(양수 {(y>0).mean():.0%}) · 반등 계열 <−3 비율 {(yr<-3).mean():.0%}")
print("\n[①②③] 변수별 — 상관 ρ [블록 CI] · 상위3등분−하위3등분 S 차이 · walk-forward(규칙으로 고른 실현 − 섞기, 적중률) 2025 / 2026 · 꼴찌피하기 ρ")
for _, r_ in R.iterrows():
    flag = "★" if (r_.ci_lo > 0 or r_.ci_hi < 0) else " "
    print(f" {flag} {r_.feature:<24} ρ {r_.rho:+.2f} [{r_.ci_lo:+.2f},{r_.ci_hi:+.2f}] · 상−하 {r_.top_minus_bottom:+5.2f}%p · WF25 {r_.wf2025_excess:+5.2f}%p({r_.wf2025_hit:.0%}) · WF26 {r_.wf2026_excess:+5.2f}%p({r_.wf2026_hit:.0%}) · 꼴찌 {r_.rho_avoid_bad:+.2f}")
# ④ 묶음: 2024~25 상관 상위 3개(절대값) 순위평균 → 2026
_cut26 = dates[dates.index(min(dd for dd in dates if dd >= "20260101")) - 41]
tr = S.index <= _cut26; sc = {}   # [REPLY_007] 끝난 성적만 학습
for f in X.columns:
    m = X[f].notna() & tr; sc[f] = pd.Series(X.loc[m, f].values).corr(pd.Series(y[m].values), method="spearman")
top3 = sorted(sc, key=lambda k: -abs(sc[k]))[:3]
def _rank_by_train(f):   # [REPLY_007] 순위 척도는 학습 구간 분포로(평가 구간 X 가 척도에 들어가지 않게)
    base = np.sort(X.loc[tr & X[f].notna(), f].values); return pd.Series(np.searchsorted(base, X[f].values, side="right") / max(len(base), 1), index=X.index)
Z = pd.DataFrame({f: _rank_by_train(f) * np.sign(sc[f]) for f in top3}).mean(axis=1)
te = (S.index >= "20260101") & Z.notna(); pick_low = Z[te] > Z[tr & Z.notna()].median()
realized = np.where(pick_low, W.loc[S.index[te], LOW].mean(axis=1).values, W.loc[S.index[te], REB].mean(axis=1).values); mix = W.loc[S.index[te]].mean(axis=1).values
print(f"\n[④] 2024~25 상관 상위3 {top3} 순위평균 → 2026 적용({te.sum()}일): 실현 − 섞기 {realized.mean()-mix.mean():+.2f}%p · 적중 {(np.sign(y[te].values)==np.where(pick_low,1,-1)).mean():.0%} · 2026 S 평균 {y[te].mean():+.2f}(양수 {(y[te]>0).mean():.0%})")
print("\n읽는 법: ★ = 3년 전체 상관 CI 가 0 을 안 걸침(25개 중 1~2개는 우연으로 나옴). 믿을 만하려면 ★ 이면서 WF25·WF26 둘 다 양수여야 한다.")
