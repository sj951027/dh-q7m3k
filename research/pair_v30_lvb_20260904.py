# -*- coding: utf-8 -*-
"""
pair_v30_lvb_20260904.py — v30(과매도 챔피언) vs lv_b(저변동) '같은 창·같은 종목' 짝비교 (관측 전용, 읽기 전용)
질문: "v30이 메인인 건 단순히 더 오래 쟀기 때문 아닌가?" → 공통 앵커(lv_b 등록 20260625 이후)에서
  ① 각자 유니버스 h20 IC 짝비교  ② v30 점수를 lv_b 유니버스(부분집합)로 제한한 '같은 종목' 짝비교
  ③ v30 IC를 lv_b 등록 전/후로 쪼갬  ④ 상위20 초과수익(같은 종목군 중앙값 기준) 짝비교
leaderboard.py 의 게이트·앵커·중복제거·h20·JUMP_CAP 그대로 import. 산출: research/fullscan_20260903/out/pair_v30_lvb.csv
"""
import os, sys, sqlite3
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import leaderboard as lb
H = 20; TOP = 20
close, _ = lb.load_ohlcv(); dates = list(close.index); N = len(dates); didx = {d: i for i, d in enumerate(dates)}
con = sqlite3.connect(f"file:{lb.DB}?mode=ro", uri=True)
partial, dbl, _ = lb.build_gates(con, dates); excl = partial | dbl
v = pd.read_sql("SELECT run_id, market, ticker, final_score_v3 AS score FROM v3_scores WHERE model_id='v30'", con)
l = pd.read_sql("SELECT run_id, market, ticker, lowvol_score AS score FROM lowvol_scores WHERE model_id='lv_b'", con)
for df in (v, l): df["ticker"] = df.ticker.astype(str); df["run_id"] = df.run_id.astype(str)
REG_V, REG_L = lb.REG_DATE["v30"], lb.REG_DATE["lv_b"]
keep_v = lb.dedupe_by_anchor(v, didx, excl, reg=REG_V); keep_l = lb.dedupe_by_anchor(l, didx, excl, reg=REG_L)
jump_all = close.pct_change(fill_method=None).abs()
def fwd_at(t):
    if t + lb.ENTRY_LAG + H >= N: return None
    f = close.iloc[t + lb.ENTRY_LAG + H] / close.iloc[t + lb.ENTRY_LAG] - 1
    j = jump_all.iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + H + 1].max()
    return f.where(j <= lb.JUMP_CAP)
def ic_exc(s, b):
    m = s.notna() & b.notna()
    if m.sum() < lb.MIN_GROUP or s[m].nunique() < 3 or b[m].nunique() < 3: return None, None
    ic = np.corrcoef(s[m].rank(), b[m].rank())[0, 1]
    top = s[m].sort_values(ascending=False).head(TOP).index
    return float(ic), float(b[m].reindex(top).mean() - b[m].median())
rows = []
for rid in sorted(set(keep_v) | set(keep_l)):
    t = lb.anchor(rid, didx); f = fwd_at(t)
    if f is None: continue
    gv = v[v.run_id == rid]; gl = l[l.run_id == rid]
    r = dict(run_id=rid, in_common=(rid in keep_v and rid in keep_l))
    for mk in ("kospi", "kosdaq"):
        sv = gv[gv.market == mk].set_index("ticker")["score"].astype(float); sv = sv[~sv.index.duplicated()]
        sl = gl[gl.market == mk].set_index("ticker")["score"].astype(float); sl = sl[~sl.index.duplicated()]
        r[f"n_v_{mk}"] = len(sv); r[f"n_l_{mk}"] = len(sl)
        if len(sv): r[f"ic_v_{mk}"], r[f"exc_v_{mk}"] = ic_exc(sv, f.reindex(sv.index))
        if len(sl):
            r[f"ic_l_{mk}"], r[f"exc_l_{mk}"] = ic_exc(sl, f.reindex(sl.index))
            # 같은 종목: v30 점수를 lv_b 유니버스로 제한
            svr = sv.reindex(sl.index)
            r[f"ic_vr_{mk}"], r[f"exc_vr_{mk}"] = ic_exc(svr, f.reindex(sl.index))
            r[f"cover_{mk}"] = float(svr.notna().mean())
    rows.append(r)
df = pd.DataFrame(rows)
def mk_mean(df, key):  # 시장별 IC 평균 → 앵커 IC (leaderboard 와 동일 사상)
    return df[[f"{key}_kospi", f"{key}_kosdaq"]].mean(axis=1, skipna=True)
for k in ("ic_v", "ic_l", "ic_vr", "exc_v", "exc_l", "exc_vr"):
    df[k] = mk_mean(df, k)
os.makedirs("research/fullscan_20260903/out", exist_ok=True)
df.to_csv("research/fullscan_20260903/out/pair_v30_lvb.csv", index=False)
def boot(a, block=1, B=2000, seed=7):
    a = np.asarray(a, float); a = a[np.isfinite(a)]; n = len(a)
    if n == 0: return (np.nan, np.nan, np.nan, 0)
    rng = np.random.default_rng(seed); out = []
    if block <= 1:
        for _ in range(B): out.append(rng.choice(a, n).mean())
    else:
        nb = int(np.ceil(n / block))
        for _ in range(B):
            st = rng.integers(0, max(1, n - block + 1), nb)
            out.append(np.concatenate([a[s:s + block] for s in st])[:n].mean())
    return (a.mean(), np.percentile(out, 2.5), np.percentile(out, 97.5), n)
def rep(label, a, block=1):
    m, lo, hi, n = boot(a, block); pos = float(np.nanmean(np.asarray(a, float) > 0)) if n else np.nan
    print(f"  {label:38s} {m:+.4f} CI[{lo:+.4f},{hi:+.4f}] n={n} 양(+)비율 {pos:.0%}")
c = df[df.in_common]
print(f"[공통 앵커] {len(c)}일 ({c.run_id.min()}~{c.run_id.max()}) · lv_b 유니버스 대비 v30 점수 커버 "
      f"{c[['cover_kospi','cover_kosdaq']].mean().mean():.0%}")
print("① 각자 유니버스 h20 IC")
rep("v30", c.ic_v); rep("lv_b", c.ic_l); rep("lv_b − v30 (iid)", c.ic_l - c.ic_v); rep("lv_b − v30 (주블록5)", c.ic_l - c.ic_v, 5)
print("② 같은 종목(lv_b 유니버스)에서 순위만 다르게")
rep("v30@lv_b유니버스", c.ic_vr); rep("lv_b", c.ic_l); rep("lv_b − v30@같은종목 (iid)", c.ic_l - c.ic_vr); rep("lv_b − v30@같은종목 (주블록5)", c.ic_l - c.ic_vr, 5)
print("③ 상위20 초과수익(같은 종목군 중앙값 대비, 20일, 소수=비율)")
rep("v30@lv_b유니버스 exc", c.exc_vr); rep("lv_b exc", c.exc_l); rep("lv_b − v30@같은종목 exc (iid)", c.exc_l - c.exc_vr); rep("(주블록5)", c.exc_l - c.exc_vr, 5)
print("④ v30 단독 IC — lv_b 등록 전/후")
pre = df[(~df.in_common) & (df.run_id < REG_L)]
rep(f"v30 등록전({REG_V}~{REG_L} 이전)", pre.ic_v); rep("v30 공통창", c.ic_v)
print("⑤ 주별 일관성(공통창, lv_b − v30@같은종목)")
c2 = c.copy(); c2["wk"] = pd.to_datetime(c2.run_id).dt.strftime("%G-W%V")
w = c2.groupby("wk").apply(lambda g: (g.ic_l - g.ic_vr).mean())
print("  주별 평균 diff:", " ".join(f"{k}:{x:+.3f}" for k, x in w.items()), f"→ 양(+) {int((w>0).sum())}/{len(w)}주")
