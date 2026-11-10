"""REQUEST_20261110_first_week_round2: offline reproduction only.

Run with python -B -X utf8 ... {a,long,dactual}. Output confined to handoff.
Operational source files and all databases are read only. No network calls.
"""
import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
import types

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'out_20261110_first_week'
KST = dt.timezone(dt.timedelta(hours=9))


def guard():
    now = dt.datetime.now(KST)
    # Stop a minute early, including long computations, before the forbidden slot.
    if now.weekday() < 5 and dt.time(20, 9) <= now.time() < dt.time(22, 31):
        raise RuntimeError('Batch protection: research stopped until 22:31 KST')


def watchdog():
    while True:
        try:
            guard()
        except RuntimeError:
            os._exit(75)
        time.sleep(2)


guard()
threading.Thread(target=watchdog, daemon=True).start()
sys.dont_write_bytecode = True
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'research'))
_connect = sqlite3.connect


def readonly_connect(db, *args, **kwargs):
    guard()
    if not str(db).startswith('file:') or 'mode=ro' not in str(db) or not kwargs.get('uri'):
        raise RuntimeError('Only mode=ro URI connections allowed')
    con = _connect(db, *args, **kwargs)
    con.execute('PRAGMA query_only=ON')
    return con


sqlite3.connect = readonly_connect


def safe_lb():
    """Use exact audited leaderboard helpers without importing scoring modules."""
    mod = types.ModuleType('leaderboard')
    mod.__dict__.update(np=np, pd=pd, sqlite3=sqlite3,
                        DB=ROOT / 'history.db',
                        OHLCV_DB=ROOT.parent / 'dh-q7m3k-data' / 'ohlcv.db',
                        GATE_FRAC=.30, ENTRY_LAG=1, JUMP_CAP=.32, MIN_GROUP=8,
                        TRACKS={'v3': ('v3_scores', 'final_score_v3', 'stage3_final'),
                                'lowvol': ('lowvol_scores', 'lowvol_score', 'stage3_final'),
                                'wu': ('wu_scores', 'wu_score', None)})
    tree = ast.parse((ROOT / 'leaderboard.py').read_text(encoding='utf-8-sig'))
    names = {'load_ohlcv', 'build_gates', 'anchor', 'dedupe_by_anchor'}
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(body) == len(names)
    exec(compile(ast.Module(body=body, type_ignores=[]), 'leaderboard_selected', 'exec'), mod.__dict__)
    regtree = ast.parse((ROOT / 'checkup.py').read_text(encoding='utf-8-sig'))
    regnode = next(n for n in regtree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'REG_DATE' for t in n.targets))
    mod.REG_DATE = ast.literal_eval(regnode.value)
    sys.modules['leaderboard'] = mod
    return mod


def save(df, name):
    guard()
    df.to_csv(OUT / (name + '.csv'), index=False, encoding='utf-8-sig')


def metadata(name, data):
    guard()
    data['calculated_at'] = dt.datetime.now(KST).isoformat()
    (OUT / (name + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def interval(s, alpha=.05, kind='month', draws=4000, seed=7):
    """Date-weighted mean; whole month resampling or original circular blocks."""
    s = s.dropna().sort_index()
    n = len(s)
    if n < 4:
        return (np.nan, np.nan)
    x = s.to_numpy(float)
    rng = np.random.default_rng(seed)
    if kind == 'month':
        months = np.array([str(i)[:6] for i in s.index])
        u, inv = np.unique(months, return_inverse=True)
        sums = np.bincount(inv, weights=x)
        counts = np.bincount(inv)
        ix = rng.integers(0, len(u), (draws, len(u)))
        means = sums[ix].sum(1) / counts[ix].sum(1)
    elif kind == 'block20':
        starts = rng.integers(0, n, (draws, int(np.ceil(n / 20))))
        ix = ((starts[:, :, None] + np.arange(20)) % n).reshape(draws, -1)[:, :n]
        means = x[ix].mean(1)
    elif kind == 'iid':
        means = x[rng.integers(0, n, (draws, n))].mean(1)
    else:
        raise ValueError(kind)
    return tuple(np.quantile(means, [alpha / 2, 1 - alpha / 2]))


def stats(s, alpha=.05, kind='month', draws=4000):
    s = s.dropna().sort_index()
    lo, hi = interval(s, kind=kind, draws=draws)
    blo, bhi = interval(s, alpha=alpha, kind=kind, draws=draws)
    if kind == 'month':
        front, back = s[s.index < '20210101'], s[s.index >= '20210101']
    else:
        mid = np.median(s.index) if len(s) else np.nan
        front, back = s[s.index <= mid], s[s.index > mid]
    flo, fhi = interval(front, kind=kind, draws=draws)
    b_lo, b_hi = interval(back, kind=kind, draws=draws)
    return dict(n=len(s), mean=s.mean(), lo=lo, hi=hi, bonf_lo=blo, bonf_hi=bhi,
                front=front.mean(), front_n=len(front), front_lo=flo, front_hi=fhi,
                back=back.mean(), back_n=len(back), back_lo=b_lo, back_hi=b_hi,
                bonf_pass=bool(blo > 0 or bhi < 0),
                halves_same=bool(np.sign(front.mean()) == np.sign(back.mean())),
                back_pass=bool(b_lo > 0 or b_hi < 0))


def run_a():
    lb = safe_lb()
    close, _ = lb.load_ohlcv()
    dates = list(close.index)
    didx = {d: i for i, d in enumerate(dates)}
    rets = close.pct_change(fill_method=None).abs()
    con = readonly_connect(f'file:{lb.DB}?mode=ro', uri=True)
    partial, double, _ = lb.build_gates(con, dates)
    rows, audits, ties = [], [], []
    for track, (table, scorecol, _) in lb.TRACKS.items():
        scores = pd.read_sql(f'SELECT run_id,market,ticker,model_id,{scorecol} AS score FROM {table}', con)
        scores['ticker'] = scores.ticker.astype(str).str.zfill(6)
        scores['market'] = scores.market.str.upper()
        for model, gmod in scores.groupby('model_id', sort=True):
            guard()
            assert model in lb.REG_DATE, model
            keep = lb.dedupe_by_anchor(gmod, didx, partial | double, reg=lb.REG_DATE[model])
            for rid, g in gmod[gmod.run_id.isin(keep)].groupby('run_id', sort=True):
                t = lb.anchor(str(rid), didx)
                e = t + lb.ENTRY_LAG
                if e + 5 >= len(close):
                    continue
                fwd = close.iloc[e + 5] / close.iloc[e] - 1
                jumps = rets.iloc[e + 1:e + 6].max()
                fwd = fwd.where(jumps <= lb.JUMP_CAP)
                path_prices = close.iloc[e + 1:e + 6]
                path = path_prices.ge(close.iloc[e]).all().astype(float)
                path[path_prices.isna().any() | close.iloc[e].isna()] = np.nan
                for mk, gm in g.groupby('market', sort=True):
                    s = gm.set_index('ticker').score.astype(float)
                    b = fwd.reindex(s.index)
                    valid = s.notna() & b.notna()
                    if valid.sum() < lb.MIN_GROUP or s[valid].nunique() < 3 or b[valid].nunique() < 3:
                        continue
                    s, b = s[valid], b[valid]
                    # Match leaderboard's score-only sort, retaining input order for ties.
                    top = s.sort_values(ascending=False).head(10).index
                    stable = pd.DataFrame({'score': s}).reset_index().sort_values(['score','ticker'], ascending=[False, True]).head(10).ticker
                    if set(top) != set(stable):
                        ties.append(dict(model=model, run_id=rid, market=mk,
                                         delta_up5=((b.loc[stable] > 0).mean() - (b.loc[top] > 0).mean()) * 100))
                    rows.append(dict(track=track, model=model, run_id=rid, date=dates[t], market=mk,
                                     n_universe=len(s), n_top=len(top),
                                     up5=(b.loc[top] > 0).mean() * 100,
                                     baseline=(b > 0).mean() * 100,
                                     diff=((b.loc[top] > 0).mean() - (b > 0).mean()) * 100,
                                     excess=(b.loc[top].mean() - b.median()) * 100,
                                     path5=path.reindex(top).mean() * 100,
                                     path_base=path.reindex(s.index).mean() * 100))
            audits.append(dict(model=model, registered=lb.REG_DATE[model], eligible_anchors=len(keep)))
    con.close()
    daily_market = pd.DataFrame(rows)
    daily = daily_market.groupby(['track','model','run_id','date'], as_index=False)[['up5','baseline','diff','excess','path5','path_base']].mean()
    summary = []
    for (track, model), g in daily.groupby(['track','model']):
        rec = dict(track=track, model=model, n=len(g), start=g.date.min(), end=g.date.max())
        for col in ['up5','baseline','diff','excess','path5','path_base']:
            s = g.set_index('date')[col]
            lo, hi = interval(s, kind='iid', draws=2000)
            rec.update({col:s.mean(), col+'_lo':lo, col+'_hi':hi})
        summary.append(rec)
    save(daily_market, 'A_market_days'); save(daily, 'A_days')
    save(pd.DataFrame(summary), 'A_summary'); save(pd.DataFrame(audits), 'A_audit')
    save(pd.DataFrame(ties, columns=['model','run_id','market','delta_up5']), 'A_ties')
    metadata('A_meta', dict(price_start=dates[0], price_end=dates[-1], partial=sorted(partial), double=sorted(double),
                            models=len(summary), tie_groups=len(ties), read_only=True))
    print(pd.DataFrame(summary)[['model','n','up5','baseline','diff','diff_lo','diff_hi','excess','path5']].to_string(index=False), flush=True)


def correlate(x, y, min_n):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < min_n or np.unique(x[m]).size < 2 or np.unique(y[m]).size < 2:
        return np.nan
    return float(np.corrcoef(pd.Series(x[m]).rank(), pd.Series(y[m]).rank())[0,1])


def qdiff(x, y, min_n=50, min_group=5, min_unique=2):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < min_n or np.unique(x[m]).size < min_unique:
        return np.nan
    q1, q4 = np.quantile(x[m], [.2,.8])
    if q1 == q4:
        return np.nan
    lo, hi = m & (x <= q1), m & (x >= q4)
    if min(lo.sum(), hi.sum()) < min_group:
        return np.nan
    return float(y[hi].mean() - y[lo].mean())


def summarize_long(days, variables, name, targets, alpha, draws):
    results = []
    days = days.set_index('date')
    for v in variables:
        for target in targets:
            st = stats(days[f'ic_{target}_{v}'], alpha=alpha, draws=draws)
            st.update(var=v, target=target)
            for metric in ['q','topbase']:
                col = f'{metric}_{target}_{v}'
                if col in days:
                    qs = stats(days[col], alpha=alpha, draws=draws)
                    st.update({metric+'_'+k: val for k, val in qs.items()})
            st['stat_candidate'] = st['bonf_pass'] and st['halves_same'] and st['back_pass']
            results.append(st)
    result = pd.DataFrame(results)
    save(result, name + '_summary')
    return result


def run_long():
    from lib import tenyr
    tenyr.reset_rng()
    P = tenyr.load_panel()
    con = readonly_connect(f'file:{tenyr.DB}?mode=ro', uri=True)
    mats = {}
    for col in ['open','high','low']:
        px = pd.read_sql(f'SELECT ticker,date,{col} FROM prices', con)
        mats[col] = px.pivot_table(index='date', columns='ticker', values=col, aggfunc='last').reindex(index=P.dates, columns=P.tick)
        del px
    con.close()
    c, v = P.cu, P.vu
    # B definitions fixed before calculating outcomes. nh252 agrees with wu_score.
    B = {'nh252': (c / c.rolling(252, min_periods=120).max() - 1) * 100,
         'r20': (c / c.shift(20) - 1) * 100,
         'r5': (c / c.shift(5) - 1) * 100}
    positive_candle = (c > mats['open']).to_numpy()
    streak = np.zeros(c.shape, dtype=np.int16)
    for i in range(P.N):
        streak[i] = np.where(positive_candle[i], (streak[i-1] if i else 0) + 1, 0)
    B['up_streak'] = pd.DataFrame(streak, index=c.index, columns=c.columns).where(c.notna() & mats['open'].notna())
    B['vol_ratio'] = v / v.rolling(20).mean().replace(0, np.nan)
    highest20 = c.rolling(20).max()
    B['brk20'] = (c >= highest20).astype(float).where(highest20.notna() & c.notna())
    sma20 = c.rolling(20).mean()
    B['sma20_above'] = (c > sma20).astype(float).where(sma20.notna() & c.notna())
    B['hl_range'] = (mats['high'] - mats['low']) / c * 100
    B = {k: x.to_numpy() for k, x in B.items()}
    del streak, positive_candle, highest20, sma20
    # Reuse original D feature formulas only; never execute its load/write/scan body.
    source = (ROOT / 'research/early_rise_scan_10y_20261108.py').read_text(encoding='utf-8-sig')
    feature_text = source[source.index('sig = list(range'):source.index('\nrows = []')]
    ns = dict(np=np, pd=pd, cu=c, vu=v, hu=mats['high'], lu=mats['low'], cf=pd.DataFrame(P.CF, index=c.index, columns=c.columns),
              N=P.N, STEP=5, dates=P.dates, MIN_N=50, time=time, t0=time.time())
    exec(compile(feature_text, 'original_D_features', 'exec'), ns)
    DV, dsig = ns['V'], ns['sig']
    dmap = {i: k for k, i in enumerate(dsig)}
    brows, drows = [], []
    for i in range(tenyr.START, P.N - tenyr.H - 1, tenyr.STEP):
        guard()
        e = P.CU[i+1]
        ok = np.isfinite(P.R20[i]) & (P.VU[i] != 0) & (P.VU[i+1] != 0) & ~P.PEN[i] & np.isfinite(e) & (e > 0) & np.isfinite(P.CF[i+41])
        if ok.sum() < tenyr.MIN_OK:
            continue
        with np.errstate(divide='ignore', invalid='ignore'):
            f5 = P.CF[i+6] / e - 1
            f40 = P.CF[i+41] / e - 1
        T1 = (f5 - tenyr.COST - np.mean(f5[ok] - tenyr.COST)) * 100
        T4 = (f40 - tenyr.COST - np.mean(f40[ok] - tenyr.COST)) * 100
        up5 = (f5 > 0).astype(float)
        up5[~np.isfinite(f5)] = np.nan
        path = (P.CF[i+2:i+7] >= e).all(axis=0).astype(float)
        path[~np.isfinite(P.CF[i+2:i+7]).all(axis=0)] = np.nan
        row = dict(date=P.dates[i], n_ok=int(ok.sum()), up5=float(np.nanmean(up5[ok])*100))
        for name, mat in B.items():
            x = mat[i,ok]
            for target, y in [('T1',T1[ok]), ('up5',up5[ok]), ('T4',T4[ok])]:
                row[f'ic_{target}_{name}'] = correlate(x, y, 50)
                if target == 'up5':
                    row[f'q_{target}_{name}'] = qdiff(x, y*100)
                    valid = np.isfinite(x) & np.isfinite(y)
                    q80 = np.quantile(x[valid], .8) if valid.sum() else np.nan
                    row[f'topbase_{target}_{name}'] = (y[valid & (x>=q80)].mean() - np.nanmean(y))*100 if valid.any() else np.nan
        brows.append(row)
        if i in dmap:
            osmask = ok & (P.R20[i] <= np.quantile(P.R20[i,ok], .2))
            drow = dict(date=P.dates[i], n_ok=int(ok.sum()), n_os=int(osmask.sum()), path5=np.nanmean(path[osmask])*100)
            for name, mat in DV.items():
                x = mat[dmap[i],osmask].astype(float)
                for target, y in [('path5',path[osmask]), ('T4',T4[osmask])]:
                    drow[f'ic_{target}_{name}'] = correlate(x, y, 50)
                    if target == 'path5':
                        drow[f'q_{target}_{name}'] = qdiff(x, y*100)
            drows.append(drow)
    bd, dd = pd.DataFrame(brows), pd.DataFrame(drows)
    save(bd, 'B_days'); save(dd, 'D_proxy_days')
    br = summarize_long(bd, list(B), 'B', ['T1','up5','T4'], .05/16, 4000)
    dr = summarize_long(dd, list(DV), 'D_proxy', ['path5','T4'], .05/(2*len(DV)), 4000)
    metadata('long_meta', dict(price_start=P.dates[0], price_end=P.dates[-1], tickers=len(P.tick),
                              B_days=len(bd), B_start=bd.date.min(), B_end=bd.date.max(),
                              D_days=len(dd), D_start=dd.date.min(), D_end=dd.date.max(),
                              B_vars=list(B), D_vars=list(DV), B_cost=tenyr.COST,
                              B_start_index=tenyr.START, D_start_index=260,
                              definitions={'up_streak':'close > open consecutive candles',
                                           'nh252':'close / rolling_max(close,252,min_periods=120)-1',
                                           'brk20':'close >= rolling_max(close,20), inclusive t',
                                           'up5':'gross f5 > 0; cost cancels between stock and same-cost EW for T1/T4'},
                              D_source_sha256=hashlib.sha256(source.encode()).hexdigest()))
    print('B', br[['var','target','n','mean','lo','hi','bonf_pass','front','back','q_mean','q_lo','q_hi']].to_string(index=False), flush=True)
    print('D proxy', dr[dr.target=='path5'][['var','n','mean','lo','hi','bonf_pass','stat_candidate']].to_string(index=False), flush=True)


def run_dactual(frozen=False):
    lb = safe_lb()
    original_load = lb.load_ohlcv
    def load_cut():
        c, m = original_load()
        return c.loc[:'20261106'], m
    lb.load_ohlcv = load_cut
    source_path = ROOT / 'research/early_rise_scan_20261108.py'
    source = source_path.read_text(encoding='utf-8-sig')
    prefix = source[:source.index('S3.to_pickle')]
    prefix = prefix.replace('OUT = HERE / "out_early_rise_scan"; OUT.mkdir(exist_ok=True)', 'OUT = HANDOFF_OUT')
    prefix = prefix.replace("WHERE run_id>='20260602'", "WHERE run_id>='20260602' AND run_id<='20261106'")
    ns = dict(__file__=str(source_path), HANDOFF_OUT=OUT)
    exec(compile(prefix, 'original_D_panel_readonly', 'exec'), ns)
    df, variables, C, N = ns['S3'], ns['VARS'], ns['C'], ns['N']
    prefix_name = 'D_actual'
    if frozen:
        original_panel = pd.read_pickle(ROOT / 'research/out_early_rise_scan/panel.pkl')
        key = ['run_id','ticker']
        oldkeys = original_panel.set_index(key).sort_index()
        newkeys = df.set_index(key).sort_index()
        assert oldkeys.index.equals(newkeys.index)
        assert np.array_equal(oldkeys[['t','j']].values, newkeys[['t','j']].values)
        df = original_panel.copy()
        prefix_name = 'D_actual_frozen'
    t, j = df.t.to_numpy(), df.j.to_numpy()
    valid = t + 6 < N
    df['path5'] = np.nan
    ti, ji = t[valid], j[valid]
    path_prices = np.stack([C[ti+1+k,ji] for k in range(1,6)])
    path = (path_prices >= C[ti+1,ji]).all(axis=0).astype(float)
    path[~np.isfinite(path_prices).all(axis=0) | ~np.isfinite(C[ti+1,ji])] = np.nan
    df.loc[valid,'path5'] = path
    all_results, dayrows, sample_meta = [], [], []
    for label, sub, group, min_n in [('stage3',df,['t','mk'],20), ('v30_top10',df[df.in_v30_top10==1],['t'],12)]:
        sample_meta.append(dict(sample=label, rows=len(sub), anchors=int(sub.t.nunique()), path_rows=int(sub.path5.notna().sum()), T4_rows=int(sub.T4.notna().sum()),
                                path_base=float(sub.groupby('t').path5.mean().mean()*100)))
        for idx, var in enumerate(variables):
            guard()
            records = []
            for key, g in sub.groupby(group):
                ti = key[0] if isinstance(key, tuple) else key
                x = g[var].to_numpy(float)
                row = dict(t=ti, ic=correlate(x,g.path5.to_numpy(float),min_n),
                           t4=correlate(x,g.T4.to_numpy(float),min_n),
                           q=qdiff(x,g.path5.to_numpy(float)*100,min_n,3,5))
                records.append(row)
            daily = pd.DataFrame(records).groupby('t').mean()
            st = stats(daily.ic, alpha=.05/(2*len(variables)), kind='block20', draws=2000)
            st.update(sample=label, var=var, cover=float(sub[var].notna().mean()))
            st['stat_candidate'] = st['bonf_pass'] and st['halves_same'] and st['back_pass']
            s4 = stats(daily.t4, kind='block20', draws=2000)
            st.update({'T4_'+k:v for k,v in s4.items()})
            sq = stats(daily.q, kind='block20', draws=2000)
            st.update({'q_'+k:v for k,v in sq.items()})
            all_results.append(st)
            daily = daily.reset_index(); daily['sample']=label; daily['var']=var
            dayrows.append(daily)
            if idx % 20 == 0:
                print(label, idx, '/', len(variables), flush=True)
    save(pd.DataFrame(all_results), prefix_name + '_summary')
    save(pd.concat(dayrows, ignore_index=True), prefix_name + '_days')
    metadata(prefix_name + '_meta',dict(asof='20261106', variables=variables, variable_count=len(variables), samples=sample_meta,
                                 source_sha256=hashlib.sha256(source.encode()).hexdigest(), rebuilt=not frozen,
                                 original_panel_used=frozen, path_days='t+2..t+6 vs entry t+1; current read-only price DB',
                                 top10_pool='original two-market pooled; not market-neutral'))
    print(pd.DataFrame(all_results).query('stat_candidate')[['sample','var','n','mean','lo','hi','front','back','T4_mean','q_mean']].to_string(index=False), flush=True)


if __name__ == '__main__':
    mode = sys.argv[1]
    {'a':run_a, 'long':run_long, 'dactual':run_dactual,
     'dfrozen':lambda:run_dactual(frozen=True)}[mode]()
