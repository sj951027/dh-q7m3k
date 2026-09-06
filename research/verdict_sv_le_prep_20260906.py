# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent

"""verdict_sv_le_prep_20260906.py — sv_a·le_a §11 판정 사전 준비(OOS<40, 판정 아님)

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
S = pd.read_sql("SELECT run_id, market, ticker, model_id, wu_score AS score FROM wu_scores", con)
S['ticker'] = S.ticker.astype(str); S['run_id'] = S.run_id.astype(str)
REG = lb.REG_DATE
DENOM_PRE = 11                          # PREREGISTER_wu.md (정본, 2026-07-04 정정 포함)
DENOM_OBS = con.execute("SELECT COUNT(DISTINCT model_id) FROM wu_scores").fetchone()[0]
print(f"[분모] 사전등록 {DENOM_PRE} / wu_scores 실측 {DENOM_OBS}")

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

MODELS = ["sv_a", "le_a"]          # 판정 예정(D-4 기준 준비) — 오늘은 "판정 아님"
REF   = ["qs_a", "px_a", "wu_a"]     # wu_a 는 은퇴(행 보존) — sv_a 짝비교 참조용

print("\n=== ① h20 주지표 (iid CI · 주별일관 · Bonferroni 두 분모) ===")
base = {}
for mid in MODELS + REF:
    sr = per_anchor_ic(mid, REG.get(mid)); base[mid] = sr
    if len(sr) == 0: print(f"  {mid}: 표본 없음"); continue
    ic = sr.mean(); c95 = boot_ci(sr.values); wpos, nw = weekly_pos(sr)
    tag = "준비(OOS<40)" if mid in MODELS else "참고"
    line = f"  {mid:5s} [{tag}] n={len(sr):2d}  IC {ic:+.4f}  CI95[{c95[0]:+.4f},{c95[1]:+.4f}]  주별양 {wpos:.0%}({nw}주)"
    if mid in MODELS:
        for dn in (DENOM_PRE, DENOM_OBS):
            a = 0.05 / dn
            cb = boot_ci(sr.values, 100*a/2, 100*(1-a/2))
            line += f"  Bonf(/{dn})[{cb[0]:+.4f},{cb[1]:+.4f}]"
    print(line)

print("\n=== ② 보조 지평 — sv_a h10(post-hoc: 9/05 진입지연 실측 '10일 정점') · le_a h5(사전등록 보조 1순위) ===")
for mid, hh in (("sv_a", 10), ("sv_a", 5), ("le_a", 5), ("le_a", 10)):
    sr = per_anchor_ic(mid, REG.get(mid), h=hh)
    if len(sr) == 0: print(f"  {mid} h{hh}: 표본 없음"); continue
    c = boot_ci(sr.values); wpos, nw = weekly_pos(sr)
    print(f"  {mid} h{hh:2d}: n={len(sr)}  IC {sr.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]  주별양 {wpos:.0%}({nw}주)")

print("\n=== ③ 짝비교 (같은 앵커 diff h20) — sv_a−wu_a(은퇴 모델, 행 보존) · sv_a−le_a ===")
for x, y in (("sv_a", "wu_a"), ("sv_a", "le_a")):
    a, b = base[x], base[y]
    common = a.index.intersection(b.index)
    if len(common) < 3: print(f"  {x}-{y}: 공통 앵커 부족({len(common)})"); continue
    d = (a[common] - b[common]).values
    c = boot_ci(d)
    print(f"  {x}-{y}: n={len(common)}  diff {d.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]")

print("\n=== ④ 주블록 부트스트랩 감도 (각주③ 관례) ===")
for mid in MODELS:
    lo, hi, nb = week_block_ci(base[mid])
    print(f"  {mid}: 주블록 {nb}개  CI[{lo:+.4f},{hi:+.4f}]")

print("\n=== ⑤ 표본 시간 분포 · OOS 진행 ===")
last = dates[-1].strftime("%Y%m%d") if hasattr(dates[-1], "strftime") else str(dates[-1])
for mid in MODELS:
    sr = base[mid]
    reg = REG.get(mid); t_reg = didx.get(reg)
    if t_reg is None:
        t_reg = next((i for i, d in enumerate(dates) if str(d)[:10].replace("-", "") >= reg), None)
    oos = (N - 1 - t_reg) if t_reg is not None else None
    print(f"  {mid}: 등록 {reg}  가격 마지막 {last}  OOS 거래일 {oos}  (40 도달까지 {None if oos is None else max(0, 40-oos)}일)"
          f"  앵커 {sr.index.min()}~{sr.index.max()} ({len(sr)}개, h20 완결분)")

print("\n=== ⑥ 국면 분할 (사전 서약 관전 포인트: le_a — KOSDAQ<SMA20 소멸?, sv_a — 상승장 부호 유지?) ===")
try:
    import sqlite3 as _sq
    ocon = _sq.connect(f'file:{REPO.parent/"dh-q7m3k-data"/"ohlcv.db"}?mode=ro', uri=True)
    kq = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSDAQ' ORDER BY date", ocon)
    ocon.close()
    kq['date'] = kq.date.astype(str).str.replace('-', '')
    kq = kq.set_index('date')['close'].astype(float)
    sma = kq.rolling(20).mean()
    above = (kq > sma)
    for mid in MODELS:
        sr = base[mid]
        st = above.reindex(sr.index)
        for lab, m in (("KOSDAQ>SMA20", st == True), ("KOSDAQ<SMA20", st == False)):
            x = sr[m.fillna(False).values]
            if len(x) < 3: print(f"  {mid} {lab}: n={len(x)} (부족)"); continue
            c = boot_ci(x.values)
            print(f"  {mid} {lab}: n={len(x)}  IC {x.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]")
except Exception as e:
    print(f"  국면 분할 생략: {e}")
