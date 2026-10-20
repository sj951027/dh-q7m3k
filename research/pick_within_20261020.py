# -*- coding: utf-8 -*-
"""무엇을 고르나 — 1차 사후 관측 (2026-10-20 밤). 읽기 전용(history.db·ohlcv.db mode=ro). 규칙 채택 아님.

(A) 3년 전 종목: 'v30 성격' 후보군 = 그날 20일 수익 하위 20%. 그 안에서 2차 기준(시총·60일 변동성·20일 거래대금·60일 고점 낙폭)의
    위/아래 절반이 40일 뒤 수익(다음날 종가 매수·40일 뒤 종가 매도·동일가중)에서 얼마나 다른가. 전체 날 / 코스피 급락(A) 날.
    신호일은 5거래일 간격으로 뽑는다(겹침 완화). 구간 = 월 블록 부트스트랩 2,000회 seed 7, 95%.
(B) 2026 v30 등록 후 앵커(leaderboard 규약: 부분·이중 실행 제외, 앵커 중복 제거)에서 시장별 상위 목록을 다르게 골랐을 때의
    40일 수익 짝차이(규칙 − 기준). 기준 = 상위10 동일가중(성적표와 같음). 비교 = 상위5 · 상위20 · 순위 가중(10…1) · 변동성 역가중 ·
    업종 상한(한 업종 2종목까지, 상위 30 안에서) · 희석 제외는 모두 동일 적용 안 함(성적표와 같은 조건).
출력: research/out_pick_within/*.csv + 표준출력 요약. 파일은 덮어쓴다.
"""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO))
import leaderboard as lb, regime_ad
OUT = HERE / "out_pick_within"; OUT.mkdir(exist_ok=True)
H = 40; TOP = 10; SEED = 7; K = 2000
rng = np.random.default_rng(SEED)


def month_block_ci(vals, months, k=K):
    """월 블록 복원추출로 평균의 95% 구간. vals/months 길이 같음."""
    vals = np.asarray(vals, float); months = np.asarray(months)
    um = np.unique(months)
    if len(um) < 2 or len(vals) < 2:
        return (np.nan, np.nan)
    by = {m: vals[months == m] for m in um}
    means = []
    for _ in range(k):
        pick = rng.choice(um, len(um))
        arr = np.concatenate([by[m] for m in pick])
        means.append(arr.mean())
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def nonov(pos, gap=H):
    c = 0; last = -10 ** 9
    for p in sorted(pos):
        if p - last >= gap:
            c += 1; last = p
    return c


print("자료 읽기…")
ocon = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker,date,close,volume,shares,market FROM daily_ohlcv", ocon); ocon.close()
px["ticker"] = px.ticker.astype(str).str.zfill(6)
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index)
shares = px.pivot_table(index="date", columns="ticker", values="shares", aggfunc="last").reindex(close.index).ffill()
mkt = px.groupby("ticker")["market"].last().str.lower()
dates = list(close.index); N = len(dates); didx = {d: i for i, d in enumerate(dates)}
close = close.where(close > 0)
ret = close.pct_change(fill_method=None)
r20 = close / close.shift(20) - 1
vol60 = ret.rolling(60, min_periods=40).std()
amt20 = (close * vol).rolling(20, min_periods=10).mean()
dd60 = close / close.rolling(60, min_periods=40).max() - 1
mcap = close * shares
fwd40 = close.shift(-1 - H) / close.shift(-1) - 1          # 신호일 기준 40일 수익
ks = regime_ad.load_index("KOSPI", lb.OHLCV_DB)
ks_r20 = (ks / ks.shift(20) - 1).reindex(dates)
months = pd.Series([d[:6] for d in dates], index=dates)
print(f"  close {close.shape} · {dates[0]}~{dates[-1]}")

# ---------------- (A) 3년 후보군 안 2차 기준 ----------------
print("\n(A) 3년 · 후보군(20일 수익 하위 20%) 안에서 2차 기준 위/아래 절반의 40일 수익 차이")
rowsA = []
sig_days = [i for i in range(60, N - H - 1, 5)]
crit = {"시총 큰 쪽": (mcap, True), "변동성 낮은 쪽": (vol60, False), "거래대금 많은 쪽": (amt20, True), "60일 낙폭 깊은 쪽": (dd60, False)}
per_day = {k: [] for k in crit}
for i in sig_days:
    d = dates[i]
    f = fwd40.iloc[i]; r = r20.iloc[i]
    ok = f.notna() & r.notna()
    if ok.sum() < 200:
        continue
    thr = r[ok].quantile(0.20)
    U = ok & (r <= thr)                                     # 후보군
    base = float(f[U].mean())
    a_day = bool(ks_r20.iloc[i] == ks_r20.iloc[i] and ks_r20.iloc[i] <= -0.05)
    for k, (feat, high_is_yes) in crit.items():
        x = feat.iloc[i][U].dropna()
        if len(x) < 40:
            continue
        med = x.median()
        yes = x.index[(x >= med) if high_is_yes else (x <= med)]
        no = x.index[(x < med) if high_is_yes else (x > med)]
        fy, fn = f[yes].mean(), f[no].mean()
        per_day[k].append(dict(date=d, month=d[:6], i=i, A=a_day, base=base * 100, yes=fy * 100, no=fn * 100, diff=(fy - fn) * 100, n_u=int(U.sum())))
for k, lst in per_day.items():
    df = pd.DataFrame(lst)
    df.to_csv(OUT / f"A_{k}.csv", index=False, encoding="utf-8-sig")
    for scope, sub in (("전체", df), ("코스피 A", df[df.A])):
        if not len(sub):
            continue
        lo, hi = month_block_ci(sub["diff"], sub["month"])
        rowsA.append(dict(기준=k, 범위=scope, 날수=len(sub), 비겹침=nonov(sub.i), 후보군평균=sub.base.mean(), 예=sub.yes.mean(), 아니오=sub.no.mean(), 차이=sub["diff"].mean(), 하한=lo, 상한=hi, 양수비율=(sub["diff"] > 0).mean()))
A = pd.DataFrame(rowsA); A.to_csv(OUT / "A_summary.csv", index=False, encoding="utf-8-sig")
print(A.round(2).to_string(index=False))

# ---------------- (B) 2026 v30 목록 안 ----------------
print("\n(B) 2026 v30 등록 후 앵커 · 시장별 상위 목록을 다르게 골랐을 때 40일 수익 짝차이(규칙 − 상위10 동일가중)")
hcon = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
S = pd.read_sql("SELECT run_id, market, ticker, final_score_v3 AS score FROM v3_scores WHERE model_id='v30'", hcon)
sec = {}
try:
    sec = json.loads((REPO / "sector_cache.json").read_text(encoding="utf-8"))
except Exception:
    pass
S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str); S["market"] = S.market.str.lower()
partial, dbl, _ = lb.build_gates(hcon, dates); hcon.close()
keep = lb.dedupe_by_anchor(S, didx, partial | dbl, reg="20260606")
rowsB = []
for rid in sorted(keep):
    t = lb.anchor(rid, didx)
    if t is None or t + 1 + H >= N:
        continue
    f = fwd40.iloc[t]
    g = S[S.run_id == rid].dropna(subset=["score"])
    res = {}
    for m, gm in g.groupby("market"):
        gm = gm.sort_values(["score", "ticker"], ascending=[False, True])
        gm = gm[gm.ticker.isin(f.dropna().index)]            # 40일 수익 있는 종목만(모든 규칙 공통)
        if len(gm) < 20:
            continue
        top = lambda n: gm.ticker.head(n).tolist()
        base = f[top(10)].mean()
        out = {"상위5": f[top(5)].mean(), "상위20": f[top(20)].mean()}
        w = np.arange(10, 0, -1, dtype=float); out["순위가중10"] = float((f[top(10)].values * w).sum() / w.sum())
        v = vol60.iloc[t][top(10)]
        if v.notna().all() and (v > 0).all():
            iw = 1.0 / v.values; out["변동성역가중10"] = float((f[top(10)].values * iw).sum() / iw.sum())
        # 업종 상한: 상위 30 안에서 한 업종 최대 2종목
        cnt, pick = {}, []
        for tk in top(30):
            s_ = sec.get(tk, "미분류")
            if cnt.get(s_, 0) >= 2:
                continue
            cnt[s_] = cnt.get(s_, 0) + 1; pick.append(tk)
            if len(pick) == 10:
                break
        if len(pick) == 10:
            out["업종상한10"] = f[pick].mean()
        for k_, val in out.items():
            res.setdefault(k_, []).append((val - base) * 100)
    for k_, lst in res.items():
        rowsB.append(dict(run=rid, month=rid[:6], i=t, 규칙=k_, 짝차이=float(np.mean(lst))))   # 두 시장 평균(성적표 규약)
B = pd.DataFrame(rowsB); B.to_csv(OUT / "B_pairs.csv", index=False, encoding="utf-8-sig")
summ = []
for k_, sub in B.groupby("규칙"):
    lo, hi = month_block_ci(sub["짝차이"], sub["month"])
    summ.append(dict(규칙=k_, 앵커=len(sub), 비겹침=nonov(sub.i), 짝차이평균=sub["짝차이"].mean(), 하한=lo, 상한=hi, 양수비율=(sub["짝차이"] > 0).mean(), 최악=sub["짝차이"].min()))
Bs = pd.DataFrame(summ); Bs.to_csv(OUT / "B_summary.csv", index=False, encoding="utf-8-sig")
print(Bs.round(2).to_string(index=False))
print("\n끝. 출력:", OUT)
