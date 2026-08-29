# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent

"""verdict_blockboot_20260829.py — lowvol §11 판정의 주블록 부트스트랩 감도 (VERDICT 각주 ③ 재현)

배경: VERDICT_20260829_lowvol.md 본문 CI는 iid 부트스트랩(leaderboard.py 규약)인데,
h20 앵커 창이 겹쳐(자기상관) iid CI가 과소일 수 있다. 주(week) 단위 블록 부트스트랩으로
단독 h20 CI와 lv_b 짝비교 diff CI를 재계산해 결론의 강건성을 본다.
⚠ 블록 6개뿐 — 이 감도 자체도 거친 추정. 정본 수치는 verdict_lowvol_20260829.py(iid).
읽기 전용(mode=ro). seed 고정(7) — 결정적 재현.
"""
import sys, sqlite3
import numpy as np
import pandas as pd

REPO = _P(str(_REPO))
sys.path.insert(0, str(REPO))
import leaderboard as lb

BOOT = 4000

close, _ = lb.load_ohlcv()
dates = list(close.index); N = len(dates)
con = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
partial, dbl, didx = lb.build_gates(con, dates)
excl = partial | dbl
S = pd.read_sql("SELECT run_id, market, ticker, model_id, lowvol_score AS score FROM lowvol_scores", con)
S['ticker'] = S.ticker.astype(str); S['run_id'] = S.run_id.astype(str)
REG = lb.REG_DATE

def per_anchor(mid, h=20):
    """verdict_lowvol_20260829.per_anchor_ic 와 동일 규약."""
    s = S[S.model_id == mid]
    keep = lb.dedupe_by_anchor(s, didx, excl, reg=REG.get(mid)); out = {}
    for rid, g in s.groupby("run_id"):
        if rid in excl or rid not in keep: continue
        t = lb.anchor(rid, didx)
        if t is None or t + lb.ENTRY_LAG + h >= N: continue
        fwd = close.iloc[t + lb.ENTRY_LAG + h] / close.iloc[t + lb.ENTRY_LAG] - 1
        jump = close.pct_change(fill_method=None).abs()\
            .iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + h + 1].max()
        fwd = fwd.where(jump <= lb.JUMP_CAP); ics = []
        for mk, gm in g.groupby("market"):
            sc = gm.set_index("ticker")["score"].astype(float)
            b = fwd.reindex(sc.index)
            m = sc.notna() & b.notna()
            if m.sum() < lb.MIN_GROUP or sc[m].nunique() < 3 or b[m].nunique() < 3: continue
            ics.append(np.corrcoef(sc[m].rank(), b[m].rank())[0, 1])
        if ics: out[rid] = float(np.mean(ics))
    return pd.Series(out).sort_index()

def week_block_ci(sr, boot=BOOT, seed=7, lo=2.5, hi=97.5):
    """주 단위 블록 리샘플 → 평균 분포의 백분위 CI."""
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W")
    blocks = [sr[wk == w].values for w in wk.unique()]; nb = len(blocks)
    rng = np.random.default_rng(seed)
    bs = [np.concatenate([blocks[i] for i in rng.integers(0, nb, nb)]).mean() for _ in range(boot)]
    return float(np.percentile(bs, lo)), float(np.percentile(bs, hi)), nb

MIDS = ["lv_b", "lv_a3", "lv_a", "sm_a", "mom_a", "lv_short", "lv_d", "hv_a", "lv_c"]
ser = {m: per_anchor(m) for m in MIDS}

print("=== 단독 h20 — 주블록 95% CI ===")
for m in MIDS:
    a, b, nb = week_block_ci(ser[m])
    print(f"{m:8s} n={len(ser[m]):2d} ic={ser[m].mean():+.4f} [{a:+.4f},{b:+.4f}] 블록={nb}")

print("\n=== lv_b 짝비교 diff — 주블록 95% CI ===")
b0 = ser["lv_b"]
for m in MIDS[1:]:
    common = ser[m].index.intersection(b0.index)
    d = ser[m][common] - b0[common]
    a, b, nb = week_block_ci(d)
    lab = "CI<0 생존" if b < 0 else "CI 0 걸침"
    print(f"{m:8s} n={len(d):2d} diff={d.mean():+.4f} [{a:+.4f},{b:+.4f}] {lab}")
con.close()
