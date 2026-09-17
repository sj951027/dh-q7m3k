# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent

"""verdict_mom_b_qs_a_prep_20260917.py — mom_b(lowvol)·qs_a(wu) §11 판정 준비 (OOS 40 도달, 2026-09-17)

verdict_sv_le_prep_20260906.py 규약 그대로:
  ① h20 주지표 IC · iid 95% CI(4,000) · 주별 일관 · Bonferroni 보정 CI
     — 분모: mom_b = lowvol distinct 11(사전등록 '트랙 동시검정 수' = 실측 11)
             qs_a  = 사전등록 5 / wu_scores 실측 7 병기
  ② 보조 지평 h5(둘 다 사전등록 보조)·h10
  ③ 짝비교(같은 앵커): mom_b−mom_a(관전 ①, 같은 유니버스) · mom_b−lv_b · qs_a−sv_a
  ④ 주블록 부트스트랩 감도(각주③ 관례)  ⑤ 국면 분할 KOSDAQ>SMA20(관전: 추세장 소멸?)
  ⑥ 관전 포인트 보조: mom_b 상위5 거래대금 중앙값 vs mom_a(관전 ③ 저유동성 쏠림) · qs_a 상위10 h20 초과수익(관전 ③ 수익 크기)
읽기 전용(mode=ro)·seed 고정 — 점수·판정 산출물 미변경. 출력만.
"""
import sys, sqlite3
import numpy as np
import pandas as pd

REPO = _P(str(_REPO)); sys.path.insert(0, str(REPO))
import leaderboard as lb

BOOT = 4000
close, mktmap = lb.load_ohlcv()
dates = list(close.index); N = len(dates)
con = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
LV = pd.read_sql("SELECT run_id, market, ticker, model_id, lowvol_score AS score FROM lowvol_scores", con)
WU = pd.read_sql("SELECT run_id, market, ticker, model_id, wu_score AS score FROM wu_scores", con)
for S in (LV, WU):
    S['ticker'] = S.ticker.astype(str).str.zfill(6); S['run_id'] = S.run_id.astype(str); S['market'] = S.market.str.lower()
TBL = {"mom_b": LV, "mom_a": LV, "lv_b": LV, "qs_a": WU, "sv_a": WU}
REG = lb.REG_DATE
DENOM = {"mom_b": [("lowvol 실측", con.execute("SELECT COUNT(DISTINCT model_id) FROM lowvol_scores").fetchone()[0])],
         "qs_a": [("사전등록", 5), ("wu 실측", con.execute("SELECT COUNT(DISTINCT model_id) FROM wu_scores").fetchone()[0])]}
print(f"[분모] mom_b {DENOM['mom_b']} · qs_a {DENOM['qs_a']}")
pct = close.pct_change(fill_method=None).abs()


def boot_ci(a, lo=2.5, hi=97.5, seed=7):
    a = np.asarray(a, float); rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(BOOT)]
    return float(np.percentile(b, lo)), float(np.percentile(b, hi))


def per_anchor_ic(mid, h=20):
    S = TBL[mid]; s = S[S.model_id == mid]
    keep = lb.dedupe_by_anchor(s, didx, excl, reg=REG.get(mid))
    out = {}
    for rid, g in s.groupby("run_id"):
        if rid in excl or rid not in keep: continue
        t = lb.anchor(rid, didx)
        if t is None or t + lb.ENTRY_LAG + h >= N: continue
        fwd = close.iloc[t + lb.ENTRY_LAG + h] / close.iloc[t + lb.ENTRY_LAG] - 1
        jump = pct.iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + h + 1].max()
        fwd = fwd.where(jump <= lb.JUMP_CAP)
        ics = []
        for mk, gm in g.groupby("market"):
            sc = gm.set_index("ticker")["score"].astype(float)
            b = fwd.reindex(sc.index); m = sc.notna() & b.notna()
            if m.sum() < lb.MIN_GROUP or sc[m].nunique() < 3 or b[m].nunique() < 3: continue
            ics.append(np.corrcoef(sc[m].rank(), b[m].rank())[0, 1])
        if ics: out[rid] = float(np.mean(ics))
    return pd.Series(out).sort_index()


def weekly_pos(sr):
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W")
    w = sr.groupby(wk).mean(); return float((w > 0).mean()), len(w)


def week_block_ci(sr, seed=7):
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W")
    blocks = [g.values for _, g in sr.groupby(wk)]; rng = np.random.default_rng(seed)
    means = [np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))]).mean() for _ in range(BOOT)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), len(blocks)


MODELS = ["mom_b", "qs_a"]; REF = ["mom_a", "lv_b", "sv_a"]
print("\n=== ① h20 주지표 (iid CI · 주별일관 · Bonferroni) ===")
base = {}
for mid in MODELS + REF:
    sr = per_anchor_ic(mid); base[mid] = sr
    if len(sr) == 0: print(f"  {mid}: 표본 없음"); continue
    c95 = boot_ci(sr.values); wpos, nw = weekly_pos(sr)
    line = f"  {mid:5s} [{'판정' if mid in MODELS else '참고'}] n={len(sr):2d}  IC {sr.mean():+.4f}  CI95[{c95[0]:+.4f},{c95[1]:+.4f}]  주별양 {wpos:.0%}({nw}주)"
    for lab, dn in DENOM.get(mid, []):
        a = 0.05 / dn; cb = boot_ci(sr.values, 100 * a / 2, 100 * (1 - a / 2)); line += f"  Bonf({lab}/{dn})[{cb[0]:+.4f},{cb[1]:+.4f}]"
    print(line)

print("\n=== ② 보조 지평 h5 · h10 ===")
for mid in MODELS:
    for hh in (5, 10):
        sr = per_anchor_ic(mid, h=hh)
        if len(sr) == 0: print(f"  {mid} h{hh}: 표본 없음"); continue
        c = boot_ci(sr.values); wpos, nw = weekly_pos(sr)
        print(f"  {mid} h{hh:2d}: n={len(sr)}  IC {sr.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]  주별양 {wpos:.0%}({nw}주)")

print("\n=== ③ 짝비교 (같은 앵커 h20 diff) ===")
for x, y in (("mom_b", "mom_a"), ("mom_b", "lv_b"), ("qs_a", "sv_a")):
    a, b = base[x], base[y]; common = a.index.intersection(b.index)
    if len(common) < 3: print(f"  {x}-{y}: 공통 앵커 부족({len(common)})"); continue
    d = (a[common] - b[common]).values; c = boot_ci(d)
    print(f"  {x}-{y}: n={len(common)}  diff {d.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]")

print("\n=== ④ 주블록 부트스트랩 감도 (각주③) ===")
for mid in MODELS:
    lo, hi, nb = week_block_ci(base[mid]); print(f"  {mid}: 주블록 {nb}개  CI[{lo:+.4f},{hi:+.4f}]")

print("\n=== ⑤ OOS 진행 · 표본 창 ===")
for mid in MODELS:
    sr = base[mid]; reg = REG.get(mid); t_reg = didx.get(reg) or next((i for i, d in enumerate(dates) if str(d) >= reg), None)
    print(f"  {mid}: 등록 {reg}  가격 마지막 {dates[-1]}  OOS {N-1-t_reg}거래일  앵커 {sr.index.min()}~{sr.index.max()} ({len(sr)}개, h20 완결분)")

print("\n=== ⑥ 국면 분할 KOSDAQ>SMA20 (관전: 추세장에서 소멸?) ===")
ocon = sqlite3.connect(f'file:{REPO.parent/"dh-q7m3k-data"/"ohlcv.db"}?mode=ro', uri=True)
kq = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSDAQ' ORDER BY date", ocon)
kq['date'] = kq.date.astype(str).str.replace('-', ''); kq = kq.set_index('date')['close'].astype(float)
above = kq > kq.rolling(20).mean()
for mid in MODELS:
    sr = base[mid]; st = above.reindex(sr.index)
    for lab, m in (("KOSDAQ>SMA20", st == True), ("KOSDAQ<SMA20", st == False)):
        x = sr[m.fillna(False).values]
        if len(x) < 3: print(f"  {mid} {lab}: n={len(x)} (부족)"); continue
        c = boot_ci(x.values); print(f"  {mid} {lab}: n={len(x)}  IC {x.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]")

print("\n=== ⑦ 관전 포인트 보조 ===")
vol = pd.read_sql("SELECT ticker,date,close,volume FROM daily_ohlcv WHERE date>='20260601'", ocon)
vol['ticker'] = vol.ticker.astype(str).str.zfill(6)
amt = vol.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").reindex(dates) * vol.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(dates)
amt20 = amt.rolling(20, min_periods=10).mean() / 1e8
ocon.close()
for mid in ("mom_b", "mom_a"):
    s = LV[LV.model_id == mid]; keep = lb.dedupe_by_anchor(s, didx, excl, reg=REG.get(mid)); meds = []
    for rid, g in s.groupby("run_id"):
        if rid in excl or rid not in keep: continue
        t = lb.anchor(rid, didx)
        if t is None: continue
        top5 = [tk for mk, gm in g.groupby("market") for tk in gm.nlargest(5, "score").ticker]
        row = amt20.iloc[t].reindex(top5).dropna()
        if len(row): meds.append(float(row.median()))
    print(f"  {mid} 상위5 20일 평균 거래대금 중앙값(억): 앵커 중앙값 {np.median(meds):.1f} · 최소 {np.min(meds):.1f} (앵커 {len(meds)})")
# qs_a 상위10 h20 초과수익(후보군 중앙값 대비)
s = WU[WU.model_id == "qs_a"]; keep = lb.dedupe_by_anchor(s, didx, excl, reg=REG["qs_a"]); ex = []
for rid, g in s.groupby("run_id"):
    if rid in excl or rid not in keep: continue
    t = lb.anchor(rid, didx)
    if t is None or t + lb.ENTRY_LAG + 20 >= N: continue
    fwd = close.iloc[t + lb.ENTRY_LAG + 20] / close.iloc[t + lb.ENTRY_LAG] - 1
    jump = pct.iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + 21].max(); fwd = fwd.where(jump <= lb.JUMP_CAP)
    per = []
    for mk, gm in g.groupby("market"):
        b = fwd.reindex(gm.ticker).dropna()
        if len(b) < 8: continue
        top = fwd.reindex(gm.nlargest(10, "score").ticker).dropna()
        if len(top): per.append((top.mean() - b.median()) * 100)
    if per: ex.append(np.mean(per))
c = boot_ci(ex); print(f"  qs_a 상위10 h20 초과(후보군 중앙값 대비): n={len(ex)}  {np.mean(ex):+.2f}%p  CI95[{c[0]:+.2f},{c[1]:+.2f}]  양(+) {100*np.mean(np.array(ex)>0):.0f}%")
