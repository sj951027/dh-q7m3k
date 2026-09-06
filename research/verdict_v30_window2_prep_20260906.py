# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent

"""verdict_v30_window2_prep_20260906.py — v30 2차 창 판정 준비(관측 전용, 판정 아님)

verdict_lowvol_20260829.py 의 규약을 wu_scores 에 그대로 이식:
  ① h20 주지표 IC·iid 95% CI·주별 일관성·Bonferroni 보정 CI
     — 분모는 두 기준 병기: PREREGISTER_wu.md 사전등록 분모 11(정본) / wu_scores 실측 distinct 6(감도)
  ② post-hoc h10  ③ wu_a vs wu_b 짝비교(사전등록 조항)  ④ 주블록 부트스트랩 감도(각주③ 관례)
sv_a·le_a·qs_a·px_a 는 OOS<40 → 오늘 판정 대상 아님(참고 출력만).
읽기 전용(mode=ro)·seed 고정 — 점수·판정 산출물 미변경.
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
S = pd.concat([pd.read_sql("SELECT run_id, market, ticker, model_id, final_score_v3 AS score FROM v3_scores WHERE model_id='v30'", con),
               pd.read_sql("SELECT run_id, market, ticker, model_id, lowvol_score AS score FROM lowvol_scores WHERE model_id='lv_b'", con)])
S['ticker'] = S.ticker.astype(str); S['run_id'] = S.run_id.astype(str)
REG = lb.REG_DATE
DENOM_V3 = con.execute("SELECT COUNT(DISTINCT model_id) FROM v3_scores").fetchone()[0]
DENOM_LV = con.execute("SELECT COUNT(DISTINCT model_id) FROM lowvol_scores").fetchone()[0]
print(f"[분모] v3 실측 {DENOM_V3} / lowvol 실측 {DENOM_LV} (행 보존 — 은퇴로 안 줄어듦)")

def boot_ci(a, lo=2.5, hi=97.5, seed=7):
    a = np.asarray(a, float)
    rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(BOOT)]
    return float(np.percentile(b, lo)), float(np.percentile(b, hi))

def per_anchor_ic(mid, reg, h=20):
    s = S[S.model_id == mid]
    keep = lb.dedupe_by_anchor(s, didx, excl, reg=reg)
    out = {}
    for rid, g in s.groupby("run_id"):
        if rid in excl or rid not in keep: continue
        t = lb.anchor(rid, didx)
        if t is None or t + lb.ENTRY_LAG + h >= N: continue
        fwd = close.iloc[t + lb.ENTRY_LAG + h] / close.iloc[t + lb.ENTRY_LAG] - 1
        jump = close.pct_change(fill_method=None).abs()\
            .iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + h + 1].max()
        fwd = fwd.where(jump <= lb.JUMP_CAP)
        ics = []
        for mk, gm in g.groupby("market"):
            sc = gm.set_index("ticker")["score"].astype(float)
            b = fwd.reindex(sc.index)
            m = sc.notna() & b.notna()
            if m.sum() < lb.MIN_GROUP or sc[m].nunique() < 3 or b[m].nunique() < 3: continue
            ics.append(np.corrcoef(sc[m].rank(), b[m].rank())[0, 1])
        if ics: out[rid] = float(np.mean(ics))
    return pd.Series(out).sort_index()

def weekly_pos(sr):
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W")
    w = sr.groupby(wk).mean()
    return float((w > 0).mean()), len(w)

def week_block_ci(sr, boot=BOOT, seed=7, lo=2.5, hi=97.5):
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W")
    blocks = [g.values for _, g in sr.groupby(wk)]
    rng = np.random.default_rng(seed)
    means = [np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))]).mean()
             for _ in range(boot)]
    return float(np.percentile(means, lo)), float(np.percentile(means, hi)), len(blocks)


# 두 창:
#  W2a = 20260625~ : lv_b 등록 이후 '공통 창'. 9/04 짝비교(pair_v30_lvb)에서 "v30 유의는 첫 13앵커(6/06~6/24)가 만들었다"를
#        본 뒤 고른 경계 → **post-hoc 분할**. 참고용.
#  W2b = 20260810~ : 8/09 정본 판정 **이후** 적재분 = 판정 대비 진짜 OOS. 이것이 '2차 창 판정'의 정본 후보.
WINDOWS = {"W2a(6/25~, post-hoc)": "20260625", "W2b(8/10~, 판정 후 OOS)": "20260810"}
DEN = {"v30": DENOM_V3, "lv_b": DENOM_LV}
last = str(dates[-1])
for wname, reg in WINDOWS.items():
    print(f"\n=== 창 {wname} ===")
    t_reg = next((i for i, d in enumerate(dates) if str(d) >= reg), None)
    oos = N - 1 - t_reg
    print(f"  OOS 거래일 {oos} (가격 마지막 {last}) — 40 도달까지 {max(0, 40-oos)}일")
    base = {}
    for mid in ("v30", "lv_b"):
        sr = per_anchor_ic(mid, reg); base[mid] = sr
        if len(sr) == 0: print(f"  {mid}: 표본 없음"); continue
        ic = sr.mean(); c95 = boot_ci(sr.values); wpos, nw = weekly_pos(sr); blo, bhi, nb = week_block_ci(sr)
        a = 0.05 / DEN[mid]; cb = boot_ci(sr.values, 100*a/2, 100*(1-a/2))
        print(f"  {mid:5s} h20 n={len(sr):2d}  IC {ic:+.4f}  iid CI[{c95[0]:+.4f},{c95[1]:+.4f}]  주블록({nb}) [{blo:+.4f},{bhi:+.4f}]"
              f"  Bonf(/{DEN[mid]}) [{cb[0]:+.4f},{cb[1]:+.4f}]  주별양 {wpos:.0%}({nw}주)")
        s10 = per_anchor_ic(mid, reg, h=10)
        if len(s10): c = boot_ci(s10.values); print(f"        h10 n={len(s10):2d}  IC {s10.mean():+.4f}  CI[{c[0]:+.4f},{c[1]:+.4f}]")
    a, b = base.get("v30", pd.Series(dtype=float)), base.get("lv_b", pd.Series(dtype=float))
    common = a.index.intersection(b.index)
    if len(common) >= 3:
        d = (b[common] - a[common]).values; c = boot_ci(d)
        wk = pd.Series(d, index=common); blo, bhi, nb = week_block_ci(wk)
        print(f"  짝비교 lv_b−v30 (같은 앵커 h20): n={len(common)}  diff {d.mean():+.4f}  iid CI[{c[0]:+.4f},{c[1]:+.4f}]  주블록({nb}) [{blo:+.4f},{bhi:+.4f}]")
    if len(a): print(f"  앵커 범위 v30 {a.index.min()}~{a.index.max()}")

print("\n=== 참고: 1차 창(정본, 등록 20260602~) 전체 누적 ===")
for mid in ("v30",):
    sr = per_anchor_ic(mid, REG.get(mid)); c = boot_ci(sr.values); blo, bhi, nb = week_block_ci(sr)
    print(f"  {mid} h20 n={len(sr)}  IC {sr.mean():+.4f}  iid CI[{c[0]:+.4f},{c[1]:+.4f}]  주블록({nb}) [{blo:+.4f},{bhi:+.4f}]")
    first = sr.iloc[:13]; rest = sr.iloc[13:]
    print(f"     첫 13앵커 IC {first.mean():+.4f} / 이후 {len(rest)}앵커 IC {rest.mean():+.4f}  CI{boot_ci(rest.values)}")
