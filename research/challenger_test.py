# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션에서 작성 — research/ 에서 실행하면 경로 자동 해결.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent
_DATA = _REPO.parent / 'dh-q7m3k-data'

"""
challenger_test.py — 신모델 후보의 결정 테스트 (탐색 전용, 채택 아님)
A) 가격조합(px4 = lowvol60+turnover_low+lowvol20+high52_prox 동일가중 랭크)을
   lv_b 동결점수와 '같은 앵커·같은 유니버스'에서 짝비교 (h5/h10/h20)
B) large_final 유니버스: 밸류(ep+bp+rim+dv=ls_t1) vs ls_t1+저변동 vs 저변동 (h10/h20)
C) 2026 주간 앵커(전시장): px4 vs px4+va_ep vs px4+short_ratio (h10, 자기상관 주의)
"""
import sys, json, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(str(_REPO))
DATA = Path(str(_DATA / 'ohlcv.db'))
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(_HERE))
import leaderboard as lb
from trend_scan import boot_mean_ci

con_o = sqlite3.connect(f'file:{DATA}?mode=ro', uri=True)
px = pd.read_sql('SELECT ticker,date,close,volume,shares FROM daily_ohlcv', con_o)
piv = lambda c: px.pivot_table(index='date', columns='ticker', values=c, aggfunc='last').sort_index()
close, vol, shares = piv('close'), piv('volume'), piv('shares')
dates = list(close.index); N = len(dates); didx = {d: i for i, d in enumerate(dates)}
ret = close.pct_change(fill_method=None)
tval = close * vol

# px4 성분
f_lowvol60 = -ret.rolling(60, min_periods=30).std()
f_lowvol20 = -ret.rolling(20, min_periods=10).std()
f_turn = -(vol / shares).rolling(20, min_periods=10).mean()
f_h52 = close / close.rolling(250, min_periods=120).max()
PX4 = {'lowvol60': f_lowvol60, 'turnover_low': f_turn, 'lowvol20': f_lowvol20, 'high52_prox': f_h52}

va = pd.read_sql('SELECT ticker,date,per FROM valuation_daily', con_o)
vep = va.pivot_table(index='date', columns='ticker', values='per', aggfunc='last').sort_index()
vep = (1.0 / vep.where(vep > 0)).reindex(index=close.index).ffill(limit=5)
sf = pd.read_sql("SELECT ticker,date,short_vol_ratio FROM short_flows WHERE date>='20260101'", con_o)
svr = sf.pivot_table(index='date', columns='ticker', values='short_vol_ratio', aggfunc='last').sort_index()
svr5 = svr.rolling(5, min_periods=3).mean().reindex(index=close.index)

def fwd(t, h):
    if t + lb.ENTRY_LAG + h >= N: return None
    f = close.iloc[t + lb.ENTRY_LAG + h] / close.iloc[t + lb.ENTRY_LAG] - 1
    j = ret.abs().iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + h + 1].max()
    return f.where(j <= lb.JUMP_CAP)

def rank_combo(t, mats, tickers):
    rk = None
    for m in mats:
        s = m.iloc[t].reindex(tickers)
        r = s.rank(pct=True)
        rk = r if rk is None else rk + r
    return rk

def ic_group(sub_scores, fwd_r, groups):
    day = []
    for g, tk in groups.items():
        s = sub_scores.reindex(tk); b = fwd_r.reindex(tk)
        m = s.notna() & b.notna()
        if m.sum() < lb.MIN_GROUP: continue
        day.append(np.corrcoef(s[m].rank(), b[m].rank())[0, 1])
    return float(np.mean(day)) if day else None

def stats(arr, seed=7):
    a = np.asarray(arr, float)
    return dict(n=len(a), ic=float(a.mean()), ci=boot_mean_ci(a, seed), pos=float((a > 0).mean()))

print('=== A) lv_b 동결점수 vs px4 — 같은 앵커·같은 유니버스 짝비교 ===')
con_h = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
partial, dbl, dd = lb.build_gates(con_h, dates)   # 교정된 stage1 게이트
excl = partial | dbl
lvb = pd.read_sql("SELECT run_id, market, ticker, lowvol_score FROM lowvol_scores WHERE model_id='lv_b'", con_h)
lvb['ticker'] = lvb['ticker'].astype(str)
keep = lb.dedupe_by_anchor(lvb, dd, excl, reg='20260625')
for h in (5, 10, 20):
    d_lv, d_px = {}, {}
    for rid, g in lvb.groupby('run_id'):
        rid = str(rid)
        if rid not in keep: continue
        t = lb.anchor(rid, dd)
        if t is None: continue
        f = fwd(t, h)
        if f is None: continue
        groups = {mk: gm['ticker'].tolist() for mk, gm in g.groupby('market')}
        s_lv = g.set_index('ticker')['lowvol_score']
        tickers = g['ticker'].tolist()
        s_px = rank_combo(t, PX4.values(), tickers)
        v1 = ic_group(s_lv, f, groups); v2 = ic_group(s_px, f, groups)
        if v1 is not None and v2 is not None:
            d_lv[rid] = v1; d_px[rid] = v2
    com = sorted(d_lv)
    diff = np.array([d_px[k] - d_lv[k] for k in com])
    ci = boot_mean_ci(diff, 21)
    print(f'  h{h}: n={len(com)}  lv_b IC{np.mean(list(d_lv.values())):+.3f}  px4 IC{np.mean(list(d_px.values())):+.3f}'
          f'  diff{diff.mean():+.4f} CI[{ci[0]:+.4f},{ci[1]:+.4f}] pos{(diff>0).mean():.0%}')

print()
print('=== B) large 유니버스: 밸류(ls_t1) vs 밸류+저변동 vs 저변동 (h10/h20) ===')
lg = pd.read_sql('SELECT run_id, ticker, per, pbr, rim_spread, div_yield FROM large_final', con_h)
lg['ticker'] = lg['ticker'].astype(str)
for h in (10, 20):
    r_val, r_mix, r_lvol = {}, {}, {}
    for rid, g in lg.groupby('run_id'):
        rid = str(rid)
        if rid in excl: continue
        t = lb.anchor(rid, dd)
        if t is None: continue
        f = fwd(t, h)
        if f is None: continue
        tickers = g['ticker'].tolist()
        fz = pd.DataFrame(index=g.index)
        fz['ep'] = 1 / g['per'].where(g['per'] > 0); fz['bp'] = 1 / g['pbr'].where(g['pbr'] > 0)
        fz['rim'] = g['rim_spread']; fz['dv'] = g['div_yield']
        val = fz.rank(pct=True).mean(axis=1); val.index = g['ticker'].values
        lvol = f_lowvol60.iloc[t].reindex(tickers).rank(pct=True)
        mix = val.reindex(tickers).rank(pct=True) + lvol
        groups = {'L': tickers}
        v1 = ic_group(val, f, groups); v2 = ic_group(mix, f, groups); v3 = ic_group(lvol, f, groups)
        if None not in (v1, v2, v3):
            r_val[rid], r_mix[rid], r_lvol[rid] = v1, v2, v3
    com = sorted(r_val)
    a = np.array([r_val[k] for k in com]); b = np.array([r_mix[k] for k in com]); c = np.array([r_lvol[k] for k in com])
    dmb = b - a
    ci = boot_mean_ci(dmb, 21)
    print(f'  h{h}: n={len(com)}  밸류 IC{a.mean():+.3f}  밸류+저변동 IC{b.mean():+.3f}  저변동 IC{c.mean():+.3f}'
          f'  (밸류+저변동 − 밸류) diff{dmb.mean():+.4f} CI[{ci[0]:+.4f},{ci[1]:+.4f}]')

print()
print('=== C) 2026 주간 앵커(전시장): px4 / px4+va_ep / px4+short (h10, 겹침 주의) ===')
aval20 = tval.rolling(20, min_periods=10).mean()
mkt = pd.read_sql('SELECT ticker, market FROM daily_ohlcv GROUP BY ticker', con_o).set_index('ticker')['market']
anchors = [didx[d] for d in dates if d >= '20260415' and didx[d] % 5 == 0 and didx[d] + 11 < N]
res = {k: {} for k in ('px4', 'px4+vep', 'px4+short', 'vep')}
for t in anchors:
    c0 = close.iloc[t]
    u = (c0 >= 500) & (aval20.iloc[t] >= 1e8)
    tickers = u.index[u.fillna(False)].tolist()
    f = fwd(t, 10)
    if f is None: continue
    groups = {g: [tk for tk in tickers if mkt.get(tk) == g] for g in ('KOSPI', 'KOSDAQ')}
    s_px = rank_combo(t, PX4.values(), tickers)
    s_v = vep.iloc[t].reindex(tickers).rank(pct=True) if dates[t] in vep.index else None
    s_sh = svr5.iloc[t].reindex(tickers).rank(pct=True)
    combos = {'px4': s_px}
    if s_v is not None and s_v.notna().sum() > 500:
        combos['px4+vep'] = s_px.rank(pct=True) + s_v
        combos['vep'] = s_v
    if s_sh.notna().sum() > 500:
        combos['px4+short'] = s_px.rank(pct=True) + s_sh
    for k, s in combos.items():
        v = ic_group(s, f, groups)
        if v is not None:
            res[k][dates[t]] = v
for k, d in res.items():
    if not d: continue
    st = stats(list(d.values()))
    print(f'  {k:10s} n={st["n"]:2d} IC{st["ic"]:+.3f} CI[{st["ci"][0]:+.3f},{st["ci"][1]:+.3f}] pos{st["pos"]:.0%}')
com = sorted(set(res['px4']) & set(res.get('px4+vep', {})))
if len(com) > 3:
    diff = np.array([res['px4+vep'][k] - res['px4'][k] for k in com])
    ci = boot_mean_ci(diff, 9)
    print(f'  (px4+vep − px4) diff{diff.mean():+.4f} CI[{ci[0]:+.4f},{ci[1]:+.4f}] n={len(com)}')
com = sorted(set(res['px4']) & set(res.get('px4+short', {})))
if len(com) > 3:
    diff = np.array([res['px4+short'][k] - res['px4'][k] for k in com])
    ci = boot_mean_ci(diff, 9)
    print(f'  (px4+short − px4) diff{diff.mean():+.4f} CI[{ci[0]:+.4f},{ci[1]:+.4f}] n={len(com)}')
