# -*- coding: utf-8 -*-
"""verdict_package.py — §11 첫 판정 계산 (v31a~d·f·g, 오프라인 정본 보조)
- 점수 챌린저(b/d/f/g): 짝지은 IC diff(챌린저-v30) h20 주지표 + h10(post-hoc 재현용),
  95% CI와 Bonferroni(0.05/6 ≈ 99.2%) CI, 주별 방향 일관성, 보조 BUY+WAIT 수익.
- v31a(E2): v30 BUY 중 차단된 행들의 h20 수익 vs 유지된 BUY vs 유니버스 중앙값.
- v31c(E4): OBSERVE 강등 행들의 h20 수익 vs 유니버스 중앙값 + BUY+WAIT 세트 수익 짝비교.
게이트: 교정된 stage1 기준(leaderboard.build_gates). reg 필터 각 모델 등록일."""
import sys, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path('/sessions/eager-inspiring-planck/mnt/dh-q7m3k')
sys.path.insert(0, str(REPO))
import leaderboard as lb

BOOT = 4000

def boot_ci(a, levels=(2.5, 97.5), seed=7):
    a = np.asarray(a, float); rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(BOOT)]
    return [float(np.percentile(b, p)) for p in levels]

close, _ = lb.load_ohlcv()
dates = list(close.index); N = len(dates)
con = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
partial, dbl, didx = lb.build_gates(con, dates)
excl = partial | dbl

S = pd.read_sql("SELECT run_id, market, ticker, model_id, final_score_v3 AS score, bucket "
                "FROM v3_scores", con)
S['ticker'] = S['ticker'].astype(str)

def fwd(t, h=20):
    if t + lb.ENTRY_LAG + h >= N: return None
    f = close.iloc[t + lb.ENTRY_LAG + h] / close.iloc[t + lb.ENTRY_LAG] - 1
    j = close.pct_change(fill_method=None).abs().iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + h + 1].max()
    return f.where(j <= lb.JUMP_CAP)

def kept_anchors(mid, reg):
    s = S[S.model_id == mid]
    keep = lb.dedupe_by_anchor(s, didx, excl, reg=reg)
    return sorted(keep)

def ic_series(mid, reg, h):
    out = {}
    for rid in kept_anchors(mid, reg):
        t = lb.anchor(rid, didx)
        if t is None: continue
        f = fwd(t, h)
        if f is None: continue
        g = S[(S.model_id == mid) & (S.run_id == rid)]
        day = []
        for mk, gm in g.groupby('market'):
            sc = gm.set_index('ticker')['score']; b = f.reindex(sc.index)
            m = sc.notna() & b.notna()
            if m.sum() < lb.MIN_GROUP: continue
            day.append(np.corrcoef(sc[m].rank(), b[m].rank())[0, 1])
        if day: out[rid] = float(np.mean(day))
    return out

def bw_ret(mid, reg, h=20):
    """BUY+WAIT 세트 평균 시장초과(중앙값 대비) — 보조지표"""
    out = {}
    for rid in kept_anchors(mid, reg):
        t = lb.anchor(rid, didx)
        f = fwd(t, h)
        if t is None or f is None: continue
        g = S[(S.model_id == mid) & (S.run_id == rid)]
        sel = g[g.bucket.isin(['BUY', 'WAIT'])]['ticker']
        uni = g['ticker']
        r_sel = f.reindex(sel).dropna(); r_uni = f.reindex(uni).dropna()
        if len(r_sel) >= 5 and len(r_uni) >= 30:
            out[rid] = float(r_sel.mean() - r_uni.median())
    return out

print('========== A) 점수 챌린저 §11 판정 (h20 주지표) ==========')
v30_20 = ic_series('v30', '20260606', 20)
v30_10 = ic_series('v30', '20260606', 10)
for mid, reg in [('v31b', '20260606'), ('v31d', '20260606'),
                 ('v31f', '20260622'), ('v31g', '20260622')]:
    c20 = ic_series(mid, reg, 20)
    com = sorted(set(c20) & set(v30_20))
    d = np.array([c20[k] - v30_20[k] for k in com])
    ci95 = boot_ci(d); ci_bon = boot_ci(d, (0.417, 99.583))
    wk = pd.Series(d, index=pd.to_datetime(com)).groupby(pd.Grouper(freq='W')).mean().dropna()
    cons = float((wk > 0).mean()) if len(wk) else np.nan
    bw_c = bw_ret(mid, reg); bw_0 = bw_ret('v30', reg)
    comb = sorted(set(bw_c) & set(bw_0))
    bwd = np.mean([bw_c[k] - bw_0[k] for k in comb]) if comb else np.nan
    line1 = (f'{mid}: n={len(d)} diff(h20) {d.mean():+.4f} 95%CI[{ci95[0]:+.4f},{ci95[1]:+.4f}] '
             f'Bonf CI[{ci_bon[0]:+.4f},{ci_bon[1]:+.4f}] 주별일관 {cons:.0%}({len(wk)}주) '
             f'보조 BUY+WAIT diff {bwd*100:+.2f}%p(n={len(comb)})')
    print(line1)
    if mid in ('v31f', 'v31g'):
        c10 = ic_series(mid, reg, 10)
        com10 = sorted(set(c10) & set(v30_10))
        d10 = np.array([c10[k] - v30_10[k] for k in com10])
        ci10 = boot_ci(d10)
        print(f'   (post-hoc 재현 h10) n={len(d10)} diff {d10.mean():+.4f} CI[{ci10[0]:+.4f},{ci10[1]:+.4f}]')

print()
print('========== B) v31a (E2 반전확인 BUY 게이트) ==========')
reg = '20260606'
blocked_r, kept_r, med_r, nb_tot = [], [], [], 0
buy_counts = []
for rid in kept_anchors('v30', reg):
    t = lb.anchor(rid, didx); f = fwd(t, 20)
    if t is None or f is None: continue
    a = S[(S.model_id == 'v31a') & (S.run_id == rid)][['ticker', 'bucket']].set_index('ticker')
    b = S[(S.model_id == 'v30') & (S.run_id == rid)][['ticker', 'bucket']].set_index('ticker')
    j = b.join(a, lsuffix='_v30', rsuffix='_a')
    blocked = j[(j.bucket_v30 == 'BUY') & (j.bucket_a == 'WAIT')].index
    keptbuy = j[(j.bucket_v30 == 'BUY') & (j.bucket_a == 'BUY')].index
    buy_counts.append((rid, len(j[j.bucket_v30 == 'BUY']), len(blocked)))
    rb = f.reindex(blocked).dropna(); rk = f.reindex(keptbuy).dropna()
    med = f.reindex(j.index).dropna().median()
    blocked_r += list(rb.values); kept_r += list(rk.values)
    if len(rb): med_r += [med] * len(rb)
    nb_tot += len(blocked)
print(f'OOS BUY 총수: {sum(c[1] for c in buy_counts)}건 · 차단된 BUY: {nb_tot}건 (앵커 {len(buy_counts)}개)')
if blocked_r:
    br = np.array(blocked_r); ci = boot_ci(br)
    print(f'차단된 BUY의 h20 수익: 평균 {br.mean()*100:+.2f}% CI[{ci[0]*100:+.2f},{ci[1]*100:+.2f}] (n={len(br)})')
if kept_r:
    kr = np.array(kept_r); ci = boot_ci(kr)
    print(f'유지된 BUY의 h20 수익: 평균 {kr.mean()*100:+.2f}% CI[{ci[0]*100:+.2f},{ci[1]*100:+.2f}] (n={len(kr)})')
if blocked_r and med_r:
    exc = np.array(blocked_r) - np.array(med_r); ci = boot_ci(exc)
    print(f'차단분 시장초과: {exc.mean()*100:+.2f}%p CI[{ci[0]*100:+.2f},{ci[1]*100:+.2f}]')

print()
print('========== C) v31c (E4 유동성 하한 → OBSERVE 강등) ==========')
dem_exc = []
bw_c = bw_ret('v31c', reg); bw_0 = bw_ret('v30', reg)
for rid in kept_anchors('v30', reg):
    t = lb.anchor(rid, didx); f = fwd(t, 20)
    if t is None or f is None: continue
    a = S[(S.model_id == 'v31c') & (S.run_id == rid)][['ticker', 'bucket']].set_index('ticker')
    b = S[(S.model_id == 'v30') & (S.run_id == rid)][['ticker', 'bucket']].set_index('ticker')
    j = b.join(a, lsuffix='_v30', rsuffix='_c')
    dem = j[(j.bucket_v30.isin(['BUY', 'WAIT'])) & (j.bucket_c == 'OBSERVE')].index
    r = f.reindex(dem).dropna()
    med = f.reindex(j.index).dropna().median()
    dem_exc += list(r.values - med)
if dem_exc:
    de = np.array(dem_exc); ci = boot_ci(de)
    print(f'강등(제외)된 종목의 h20 시장초과: {de.mean()*100:+.2f}%p CI[{ci[0]*100:+.2f},{ci[1]*100:+.2f}] (n={len(de)})')
    print('  해석: 양(+)이면 좋은 종목을 뺀 것(v31c 불리), 음(-)이면 나쁜 종목을 뺀 것(v31c 유리)')
comb = sorted(set(bw_c) & set(bw_0))
d = np.array([bw_c[k] - bw_0[k] for k in comb])
ci = boot_ci(d)
print(f'BUY+WAIT 세트 시장초과 짝비교(v31c-v30): {d.mean()*100:+.2f}%p CI[{ci[0]*100:+.2f},{ci[1]*100:+.2f}] (n={len(comb)})')
