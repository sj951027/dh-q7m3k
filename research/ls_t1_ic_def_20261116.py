"""ls_t1 순위 상관 정의 두 가지(전 유니버스 vs 시장별 평균)의 실제 차이 — 읽기 전용.
h20(참고 호라이즌, 이미 공개)만 본다. 판정 호라이즌 h60 의 전 유니버스 값은 일부러 계산하지 않는다.
"""
import sys
import sqlite3
import numpy as np
import pandas as pd

ROOT = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
import leaderboard as L          # noqa: E402
import large_verdict as V        # noqa: E402

H = 20
close = V.load_close_with_extra()
dates = list(close.index); N = len(dates)
con = sqlite3.connect(f"file:{L.DB}?mode=ro", uri=True)
partial, dbl, didx = L.build_gates(con, dates)
excl = partial | dbl
s = V.ls_t1_scores(con)
con.close()
reg = L.REG_DATE.get("ls_t1")
keep_daily = L.dedupe_by_anchor(s, didx, excl, reg=reg)
keep_weekly = V.weekly_subset(keep_daily, didx, dates)
chg = close.pct_change(fill_method=None).abs()


def sp(a, b):
    return float(np.corrcoef(a.rank(), b.rank())[0, 1])


rows = []
for rid, g in s.groupby("run_id"):
    rid = str(rid)
    if rid not in keep_daily:
        continue
    t = L.anchor(rid, didx)
    if t is None or t + L.ENTRY_LAG + H >= N:
        continue
    fwd = close.iloc[t + L.ENTRY_LAG + H] / close.iloc[t + L.ENTRY_LAG] - 1
    jump = chg.iloc[t + L.ENTRY_LAG + 1:t + L.ENTRY_LAG + H + 1].max()
    fwd = fwd.where(jump <= L.JUMP_CAP)
    g = g.copy(); g["ticker"] = g["ticker"].astype(str)
    g["fwd"] = fwd.reindex(g["ticker"]).values
    v = g.dropna(subset=["score", "fwd"])
    r = dict(rid=rid, weekly=rid in keep_weekly, n=len(v))
    ics = []
    for mk, gm in v.groupby("market"):
        mk = str(mk).lower()
        if len(gm) >= L.MIN_GROUP and gm["score"].nunique() >= 3 and gm["fwd"].nunique() >= 3:
            r[f"ic_{mk}"] = sp(gm["score"], gm["fwd"]); ics.append(r[f"ic_{mk}"])
        r[f"n_{mk}"] = len(gm)
        r[f"score_{mk}"] = gm["score"].mean()
        r[f"ret_{mk}"] = gm["fwd"].median() * 100
    r["ic_within"] = float(np.mean(ics)) if ics else np.nan
    r["ic_pooled"] = sp(v["score"], v["fwd"])
    # 시장 안에서 수익 중앙값을 뺀 뒤 한데 모아 본 상관(시장 차이만 걷어낸 전 유니버스)
    adj = v["fwd"] - v.groupby("market")["fwd"].transform("median")
    r["ic_pooled_mktadj"] = sp(v["score"], adj)
    top = v.sort_values("score", ascending=False).head(20)
    r["top20_kospi_share"] = (top["market"].str.lower() == "kospi").mean()
    r["univ_kospi_share"] = (v["market"].str.lower() == "kospi").mean()
    rows.append(r)

D = pd.DataFrame(rows).sort_values("rid")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)


def summ(x, name):
    a = x.dropna().values
    rng = np.random.default_rng(7)
    bo = [rng.choice(a, len(a)).mean() for _ in range(L.BOOT)]
    return f"{name:22s} n={len(a):2d} 평균 {a.mean():+.4f} [{np.percentile(bo, 2.5):+.4f}, {np.percentile(bo, 97.5):+.4f}] 양수 {np.mean(a > 0):.0%}"


for tag, X in (("일간 앵커", D), ("주간 앵커", D[D["weekly"]])):
    print(f"\n== h{H} · {tag} ({X['rid'].min()}~{X['rid'].max()}) ==")
    for c in ("ic_within", "ic_pooled", "ic_pooled_mktadj", "ic_kospi", "ic_kosdaq"):
        print(" ", summ(X[c], c))
    d = X["ic_pooled"] - X["ic_within"]
    print(" ", summ(d, "pooled - within"))
    print(f"  앵커별 두 값의 상관 {np.corrcoef(X['ic_pooled'], X['ic_within'])[0, 1]:+.3f} · 부호가 다른 앵커 {(np.sign(X['ic_pooled']) != np.sign(X['ic_within'])).sum()}개")

print("\n== 점수의 시장 쏠림(앵커 평균) ==")
print(f"  평균 점수: 코스피 {D['score_kospi'].mean():.3f} · 코스닥 {D['score_kosdaq'].mean():.3f}")
print(f"  유효 종목 수: 코스피 {D['n_kospi'].mean():.0f} · 코스닥 {D['n_kosdaq'].mean():.0f} (코스피 비중 {D['univ_kospi_share'].mean():.0%})")
print(f"  점수 상위 20종목 중 코스피 비중 {D['top20_kospi_share'].mean():.0%}")
print(f"  20일 수익 중앙값(%): 코스피 {D['ret_kospi'].mean():+.2f} · 코스닥 {D['ret_kosdaq'].mean():+.2f} · 코스피가 앞선 앵커 {(D['ret_kospi'] > D['ret_kosdaq']).mean():.0%}")
gap = D["ret_kospi"] - D["ret_kosdaq"]; dd = D["ic_pooled"] - D["ic_within"]
print(f"  (전 유니버스 − 시장별) 과 (코스피−코스닥 수익 차) 의 앵커별 상관 {np.corrcoef(gap, dd)[0, 1]:+.3f}")
print("\n주간 앵커별:")
print(D[D["weekly"]][["rid", "n", "ic_kospi", "ic_kosdaq", "ic_within", "ic_pooled", "ic_pooled_mktadj", "ret_kospi", "ret_kosdaq"]].round(3).to_string(index=False))
