# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent

"""verdict_lowvol_20260829.py — lowvol 트랙 §11 판정 계산 (오프라인 정본 보조)

대상: 등록 후 OOS 40거래일에 도달한 lowvol 모델(lv_b·lv_a·lv_a3·lv_c·lv_d·lv_short·hv_a·mom_a).
계산: leaderboard.py 정본 함수 재사용(게이트·앵커·dedupe·IC 동일) +
  ① h20 주지표 IC·95% CI·주별 방향 일관성
  ② Bonferroni 보정 CI(1-0.05/denom 수준) — leaderboard 의 '경계 강등' 규칙보다 엄밀
  ③ post-hoc 재현용 h10 별도 호라이즌
  ④ lv_b 대비 짝비교 diff(같은 앵커일) — 계열 내 서열의 통계적 근거
읽기 전용(사본 아님, mode=ro). 점수·판정 산출물 미변경.
"""
import sys, sqlite3
import numpy as np
import pandas as pd

REPO = _P(str(_REPO))
sys.path.insert(0, str(REPO))
import leaderboard as lb

BOOT = 4000
H = lb.H_PRIMARY

def boot_ci(a, lo=2.5, hi=97.5, seed=7):
    a = np.asarray(a, float)
    rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(BOOT)]
    return float(np.percentile(b, lo)), float(np.percentile(b, hi))

close, _ = lb.load_ohlcv()
dates = list(close.index); N = len(dates)
con = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
partial, dbl, didx = lb.build_gates(con, dates)
excl = partial | dbl
denom = con.execute("SELECT COUNT(DISTINCT model_id) FROM lowvol_scores").fetchone()[0]
print(f"[게이트] partial={sorted(partial)} · double={sorted(dbl)} · lowvol 동시검정 분모={denom}")

S = pd.read_sql("SELECT run_id, market, ticker, model_id, lowvol_score AS score FROM lowvol_scores", con)
S['ticker'] = S['ticker'].astype(str); S['run_id'] = S['run_id'].astype(str)

def per_anchor_ic(mid, reg, h=H):
    """앵커 거래일별 그룹평균 IC 시계열 (leaderboard.model_ic 와 동일 규약)."""
    s = S[S.model_id == mid]
    keep = lb.dedupe_by_anchor(s, didx, excl, reg=reg)
    out = {}
    for rid, g in s.groupby("run_id"):
        if rid in excl or rid not in keep:
            continue
        t = lb.anchor(rid, didx)
        if t is None or t + lb.ENTRY_LAG + h >= N:
            continue
        fwd = close.iloc[t + lb.ENTRY_LAG + h] / close.iloc[t + lb.ENTRY_LAG] - 1
        jump = close.pct_change(fill_method=None).abs()\
            .iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + h + 1].max()
        fwd = fwd.where(jump <= lb.JUMP_CAP)
        ics = []
        for mk, gm in g.groupby("market"):
            sc = gm.set_index("ticker")["score"].astype(float)
            b = fwd.reindex(sc.index)
            m = sc.notna() & b.notna()
            if m.sum() < lb.MIN_GROUP or sc[m].nunique() < 3 or b[m].nunique() < 3:
                continue
            ics.append(np.corrcoef(sc[m].rank(), b[m].rank())[0, 1])
        if ics:
            out[rid] = float(np.mean(ics))
    return pd.Series(out).sort_index(), len(keep)

REG = lb.REG_DATE
MODELS = [m for (m,) in con.execute("SELECT DISTINCT model_id FROM lowvol_scores ORDER BY model_id")]

def weekly_pos(sr):
    if len(sr) == 0: return None, 0
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W")
    w = sr.groupby(wk).mean()
    return float((w > 0).mean()), len(w)

print("\n=== ① h20 주지표 · 주별 일관성 · Bonferroni 보정 CI ===")
alpha_b = 0.05 / denom
lo_p, hi_p = 100 * alpha_b / 2, 100 * (1 - alpha_b / 2)
print(f"  Bonferroni: alpha={0.05}/{denom}={alpha_b:.4f} → CI 백분위 [{lo_p:.2f}, {hi_p:.2f}]")
base = {}
rows = []
for mid in MODELS:
    reg = REG.get(mid)
    sr, oos = per_anchor_ic(mid, reg)
    base[mid] = sr
    if len(sr) == 0:
        rows.append((mid, reg, oos, 0, None, None, None, None, None, None)); continue
    ic = sr.mean()
    c95 = boot_ci(sr.values)
    cbf = boot_ci(sr.values, lo_p, hi_p)
    wpos, nw = weekly_pos(sr)
    rows.append((mid, reg, oos, len(sr), ic, c95[0], c95[1], cbf[0], cbf[1], f"{wpos:.0%}({nw}주)"))
df = pd.DataFrame(rows, columns=["model","reg","oos_days","n_h20","ic_h20","ci95_lo","ci95_hi",
                                 "bonf_lo","bonf_hi","주별양(+)"])
df = df.sort_values("ic_h20", ascending=False, na_position="last")
pd.set_option("display.width", 200)
print(df.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

print("\n=== ② post-hoc 재현 호라이즌 h10 ===")
r10 = []
for mid in MODELS:
    sr, _ = per_anchor_ic(mid, REG.get(mid), h=10)
    if len(sr) == 0:
        r10.append((mid, 0, None, None, None)); continue
    c = boot_ci(sr.values)
    wpos, nw = weekly_pos(sr)
    r10.append((mid, len(sr), sr.mean(), c[0], c[1]))
print(pd.DataFrame(r10, columns=["model","n_h10","ic_h10","ci95_lo","ci95_hi"])
      .sort_values("ic_h10", ascending=False, na_position="last")
      .to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

print("\n=== ③ lv_b 대비 짝비교(같은 앵커일 diff, h20) ===")
b = base["lv_b"]
pr = []
for mid in MODELS:
    if mid == "lv_b": continue
    sr = base[mid]
    common = sr.index.intersection(b.index)
    if len(common) < 10:
        pr.append((mid, len(common), None, None, None)); continue
    d = (sr[common] - b[common]).values
    c = boot_ci(d)
    pr.append((mid, len(common), float(d.mean()), c[0], c[1]))
print(pd.DataFrame(pr, columns=["model","n_공통","diff_h20","ci95_lo","ci95_hi"])
      .sort_values("diff_h20", ascending=False, na_position="last")
      .to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

print("\n=== ④ 판정 표본의 시간 분포(각주 근거) ===")
print(f"  lv_b h20 앵커: n={len(b)} · {b.index.min()}~{b.index.max()}")
uni = pd.read_sql("SELECT run_id, market, COUNT(*) n FROM lowvol_scores WHERE model_id='lv_b' "
                  "GROUP BY run_id, market", con)
uni['run_id'] = uni.run_id.astype(str)
p = uni.pivot(index="run_id", columns="market", values="n").fillna(0).astype(int)
thin = p[(p < lb.MIN_GROUP).any(axis=1)]
print(f"  lv_b 유니버스가 시장별 MIN_GROUP({lb.MIN_GROUP}) 미만인 run: {len(thin)}건")
print(thin.tail(15).to_string())
con.close()

# ---- ⑤ v30 ↔ lv_b 앵커 IC 상관 · 유니버스 포함관계 (각주 ② 근거) ----
print("\n=== ⑤ v30 ↔ lv_b 독립성 점검 ===")
con2 = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
V = pd.read_sql("SELECT run_id, market, ticker, final_score_v3 AS score FROM v3_scores "
                "WHERE model_id='v30'", con2)
V['ticker'] = V.ticker.astype(str); V['run_id'] = V.run_id.astype(str)
_S_bak = S
S = V.assign(model_id='v30')
v_sr, _ = per_anchor_ic('v30', REG.get('v30'))
S = _S_bak
common = v_sr.index.intersection(b.index)
print(f"  공통 앵커일 n={len(common)} ({common.min()}~{common.max()})")
print(f"  앵커별 IC 상관: pearson {np.corrcoef(v_sr[common], b[common])[0,1]:+.3f} · "
      f"rank {np.corrcoef(v_sr[common].rank(), b[common].rank())[0,1]:+.3f}")
wk = pd.to_datetime(pd.Series(common, index=common), format="%Y%m%d").dt.to_period("W")
A = v_sr[common].groupby(wk).mean(); B = b[common].groupby(wk).mean()
print(f"  주간 평균 IC 상관: n={len(A)}주 · pearson {np.corrcoef(A, B)[0,1]:+.3f} · "
      f"rank {np.corrcoef(A.rank(), B.rank())[0,1]:+.3f}")
lvt = pd.read_sql("SELECT run_id, ticker FROM lowvol_scores WHERE model_id='lv_b'", con2)
v3t = pd.read_sql("SELECT run_id, ticker FROM v3_scores WHERE model_id='v30'", con2)
for d in (lvt, v3t):
    d['run_id'] = d.run_id.astype(str); d['ticker'] = d.ticker.astype(str)
fr = []
for rid, g in lvt.groupby('run_id'):
    s2 = set(v3t[v3t.run_id == rid].ticker)
    if s2: fr.append(len(set(g.ticker) & s2) / len(set(g.ticker)))
print(f"  lv_b 종목의 v30 유니버스 포함비율: run {len(fr)}개 · 평균 {np.mean(fr):.4f} · 최소 {min(fr):.4f}")
con2.close()
