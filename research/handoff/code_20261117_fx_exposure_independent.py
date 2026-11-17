"""Independent blind reproduction; read-only databases, no other implementation read.

Frozen before running (2026-11-17): exact complete 52/104-week endpoint grid;
CU for estimation (no delisting forward-fill); qcut(rank(method='first'),5);
FX horizon anchored on actual observed FX date; primary OS membership before
beta availability. Partial initial history and alternate quintile partition are
interpretation checks only, never replacements of the registered primary.
Expectation: insufficient robust evidence; no numeric expectation added.
Run: python -B -X utf8 research/handoff/code_20261117_fx_exposure_independent.py
"""
import sys
sys.dont_write_bytecode = True
import json
import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research'))
from lib import tenyr

OUT = Path(__file__).resolve().parent / 'out_20261117_fx_exposure'


def fx_panel(dates):
    db = (ROOT.parent / 'dh-q7m3k-data' / 'macro_10y.db').resolve()
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as con:
        f = pd.read_sql_query("SELECT date,close FROM series_daily WHERE series='USDKRW' ORDER BY date", con)
    assert f.date.is_unique and (f.close > 0).all()
    fd = pd.to_datetime(f.date, format='%Y%m%d').to_numpy(dtype='datetime64[D]')
    fv = f.close.to_numpy(float)
    ds = pd.to_datetime(dates, format='%Y%m%d').to_numpy(dtype='datetime64[D]')
    ix = np.searchsorted(fd, ds - np.timedelta64(1, 'D'), side='right') - 1
    assert (ix >= 0).all()
    obs = fd[ix]
    assert (obs < ds).all()
    horizons = {}
    for days in (28, 84):
        j = np.searchsorted(fd, obs - np.timedelta64(days, 'D'), side='right') - 1
        z = np.full(len(ds), np.nan)
        ok = j >= 0
        z[ok] = (fv[ix[ok]] / fv[j[ok]] - 1) * 100
        assert (fd[j[ok]] <= obs[ok] - np.timedelta64(days, 'D')).all()
        horizons[days] = z
    info = dict(rows=len(f), first=f.date.iloc[0], last=f.date.iloc[-1],
                max_lag_calendar_days=int((ds - obs).astype(int).max()))
    return fv[ix], horizons, obs, info


def quintiles(x, y, eligible, split='qcut'):
    ix = np.flatnonzero(eligible & np.isfinite(x) & np.isfinite(y))
    if len(ix) < 5:
        return dict(n=len(ix), diff=np.nan, rho=np.nan, q=[np.nan]*5, ties=0)
    ranks = pd.Series(x[ix]).rank(method='first')
    if split == 'qcut':
        labels = pd.qcut(ranks, 5, labels=False).to_numpy()
    else:
        order = np.argsort(x[ix], kind='stable')
        labels = np.empty(len(ix), int)
        for k, part in enumerate(np.array_split(order, 5)):
            labels[part] = k
    q = [float(y[ix[labels == k]].mean()) for k in range(5)]
    rho = float(spearmanr(x[ix], y[ix]).statistic) if np.ptp(x[ix]) else np.nan
    return dict(n=len(ix), diff=q[4]-q[0], rho=rho, q=q,
                ties=len(ix)-len(np.unique(x[ix])))


def main():
    t0 = time.time()
    P = tenyr.load_panel()
    F, fx, obs, fx_info = fx_panel(P.dates)
    ks = P.ks.reindex(P.dates).to_numpy(float)
    with np.errstate(invalid='ignore', divide='ignore'):
        logp = np.log(P.CU)
        logm = np.log(ks)
        logf = np.log(F)
    cache = {}
    diagnostics = dict(ols_checked=0, ols_max_abs_error=0.0,
                       signal_future_exit_missing=0, signal_entry_excluded=0,
                       eligible_delisted_rows=0, os_delisted_rows=0,
                       eligible_ffill_exit_rows=0, os_ffill_exit_rows=0)
    dl = P.meta.note.reindex(P.tick).fillna('').str.contains('delisted').to_numpy()

    def beta(i, weeks=52, partial=False):
        key = (i, weeks, partial)
        if key in cache:
            return cache[key]
        out = np.full(len(P.tick), np.nan)
        required = 40 if weeks == 52 else 80
        if i < weeks*5 and not partial:
            cache[key] = out
            return out
        endpoints = np.arange(i, max(-1, i-weeks*5-1), -5)[::-1]
        if len(endpoints)-1 < required:
            cache[key] = out
            return out
        Y = np.diff(logp[endpoints], axis=0)
        M = np.diff(logm[endpoints])[:, None]
        X = np.diff(logf[endpoints])[:, None]
        valid = np.isfinite(Y) & np.isfinite(M) & np.isfinite(X)
        W = valid.astype(float)
        n = W.sum(axis=0)
        # Centered normal equations for intercept + market + currency.
        yy = np.where(valid, Y, 0)
        mm = np.where(valid, M, 0)
        xx = np.where(valid, X, 0)
        den_n = np.maximum(n, 1)
        sy, sm, sx = yy.sum(0), mm.sum(0), xx.sum(0)
        mm2 = (mm*mm).sum(0)-sm*sm/den_n
        xx2 = (xx*xx).sum(0)-sx*sx/den_n
        mx = (mm*xx).sum(0)-sm*sx/den_n
        my = (mm*yy).sum(0)-sm*sy/den_n
        xy = (xx*yy).sum(0)-sx*sy/den_n
        det = mm2*xx2-mx*mx
        good = (n >= required) & (det > 0)
        out[good] = (mm2[good]*xy[good]-mx[good]*my[good])/det[good]
        candidates = np.flatnonzero(good)
        if len(candidates):
            for j in np.unique(candidates[[0, len(candidates)//2, -1]]):
                v = valid[:, j]
                A = np.column_stack([np.ones(v.sum()), M[v, 0], X[v, 0]])
                reference = np.linalg.lstsq(A, Y[v, j], rcond=None)[0][2]
                err = float(abs(reference-out[j]))
                diagnostics['ols_checked'] += 1
                diagnostics['ols_max_abs_error'] = max(diagnostics['ols_max_abs_error'], err)
                assert np.isclose(reference, out[j], rtol=1e-9, atol=1e-9)
        cache[key] = out
        return out

    def extra(panel, i, ok):
        r = P.R20[i]
        osmask = ok & (r <= np.quantile(r[ok], .2))
        y = (P.CF[i+41]/P.CU[i+1]-1-tenyr.COST)*100
        b = beta(i)
        b104 = beta(i, 104)
        bpartial = beta(i, partial=True)
        result = dict(n_all=int(ok.sum()), n_os_base=int(osmask.sum()),
                      fx20=float(fx[28][i]), fx60=float(fx[84][i]),
                      fx_observed=str(obs[i]).replace('-', ''),
                      n_beta_all=int((ok & np.isfinite(b)).sum()),
                      n_beta_os=int((osmask & np.isfinite(b)).sum()))
        variants = [('main', b, fx[28][i], osmask),
                    ('all', b, fx[28][i], ok),
                    ('w104', b104, fx[28][i], osmask),
                    ('fx60', b, fx[84][i], osmask),
                    ('beta_only', b, 1., osmask),
                    ('partial', bpartial, fx[28][i], osmask)]
        for name, bb, f, universe in variants:
            x = bb*f if np.isfinite(f) and f != 0 else np.full(len(bb), np.nan)
            q = quintiles(x, y, universe)
            result.update({name+'_diff':q['diff'], name+'_n':q['n']})
            if name == 'main':
                result['rho'] = q['rho']
                result['ties'] = q['ties']
                for k, val in enumerate(q['q'], 1):
                    result['q'+str(k)] = val
                result['array_split_diff'] = quintiles(x, y, universe, 'array_split')['diff']
        # Calendar anniversary, latest Korean trading day not after that date.
        prior = (pd.Timestamp(P.dates[i])-pd.DateOffset(years=1)).strftime('%Y%m%d')
        j = int(np.searchsorted(P.dates, prior, side='right')-1)
        old = beta(j) if j >= 0 else np.full_like(b, np.nan)
        common = ok & np.isfinite(b) & np.isfinite(old)
        result['beta_year_n'] = int(common.sum())
        result['beta_year_rho'] = float(spearmanr(b[common], old[common]).statistic) if common.sum() >= 5 else np.nan
        sig = np.isfinite(r) & (P.VU[i] > 0) & ~P.PEN[i]
        diagnostics['signal_entry_excluded'] += int((sig & ((P.VU[i+1] == 0) | ~np.isfinite(P.CU[i+1]))).sum())
        diagnostics['signal_future_exit_missing'] += int((sig & ~np.isfinite(P.CF[i+41])).sum())
        diagnostics['eligible_delisted_rows'] += int((ok & dl).sum())
        diagnostics['os_delisted_rows'] += int((osmask & dl).sum())
        fill = ~np.isfinite(P.CU[i+41]) & np.isfinite(P.CF[i+41])
        diagnostics['eligible_ffill_exit_rows'] += int((ok & fill).sum())
        diagnostics['os_ffill_exit_rows'] += int((osmask & fill).sum())
        if i % 250 == 130:
            print('progress', P.dates[i], round(time.time()-t0, 1), flush=True)
        return result

    R = tenyr.signal_days(P, extra=extra)
    assert np.allclose(R.os40-R.all40, R.exc)
    print('panel calculations complete', round(time.time()-t0, 1), flush=True)

    def summary(col, mask=None):
        S = R.loc[np.isfinite(R[col]) & (True if mask is None else mask)]
        if S.empty:
            return dict(n=0)
        tenyr.reset_rng(7)  # Each reported interval has its own documented seed 7.
        ci = tenyr.block_ci(S[col], S.month, k=2000)
        return dict(n=len(S), months=int(S.month.nunique()), first=S.date.iloc[0],
                    last=S.date.iloc[-1], mean=float(S[col].mean()),
                    lo=ci[0], hi=ci[1], positive_pct=float((S[col]>0).mean()*100))

    stats = {}
    for col in ['main_diff','all_diff','w104_diff','fx60_diff','beta_only_diff',
                'rho','beta_year_rho','partial_diff','array_split_diff']:
        stats[col] = summary(col)
    for half in ['앞', '뒤']:
        stats['main_'+half] = summary('main_diff', R.half == half)
    main_ok = np.isfinite(R.main_diff)
    threshold = float(R.loc[main_ok, 'fx20'].abs().quantile(2/3))
    stats['high_abs_fx20'] = summary('main_diff', R.fx20.abs() >= threshold)
    stats['beta_only_common_main'] = summary('beta_only_diff', main_ok)
    yearly = []
    for year in sorted(R.date.str[:4].unique()):
        z = summary('beta_year_rho', R.date.str.startswith(year))
        if z['n']:
            z['year'] = year
            yearly.append(z)
    M = stats['main_diff']
    sign = np.sign(M['mean'])
    conditions = dict(size=abs(M['mean'])>=1., ci_excludes_zero=M['lo']>0 or M['hi']<0,
                      early=np.sign(stats['main_앞']['mean'])==sign,
                      late=np.sign(stats['main_뒤']['mean'])==sign,
                      all=np.sign(stats['all_diff']['mean'])==sign,
                      w104=np.sign(stats['w104_diff']['mean'])==sign,
                      fx60=np.sign(stats['fx60_diff']['mean'])==sign)
    conditions = {name: bool(value) for name, value in conditions.items()}
    coverage = {}
    for name, mask in [('grid', np.ones(len(R),bool)), ('main',main_ok)]:
        S = R.loc[mask]
        coverage[name] = dict(days=len(S), first=S.date.iloc[0],last=S.date.iloc[-1],
            mean_os=float(S.n_os_base.mean()), min_os=int(S.n_os_base.min()), max_os=int(S.n_os_base.max()),
            mean_beta_os=float(S.n_beta_os.mean()),
            beta_os_pct_pooled=float(S.n_beta_os.sum()/S.n_os_base.sum()*100),
            beta_os_pct_mean=float((S.n_beta_os/S.n_os_base).mean()*100),
            beta_all_pct_pooled=float(S.n_beta_all.sum()/S.n_all.sum()*100),
            mean_beta_all=float(S.n_beta_all.mean()))
    report = dict(spec=dict(full_window=True, quintiles='qcut(first rank)',
                  beta_prices='CU, positive raw adjusted close, no ffill',
                  fx_anchor='actual observed date', ci='reset seed 7 for each row; 2000 monthly blocks',
                  beta_year='calendar anniversary, latest prior Korean trading date; current ok universe'),
                  panel=dict(stocks=len(P.tick), dates=P.N, first=P.dates[0],last=P.dates[-1]),
                  fx=fx_info, coverage=coverage, stats=stats, conditions=conditions,
                  verdict='열림' if all(conditions.values()) else '닫음',
                  high_fx_threshold=threshold, zero_fx20_grid=int((R.fx20 == 0).sum()),
                  diagnostics=diagnostics, beta_yearly=yearly,
                  beta_year_pairs=int(R.beta_year_n.sum()), main_ties=int(R.loc[main_ok,'ties'].sum()))
    OUT.mkdir(exist_ok=True)
    R.to_csv(OUT/'days.csv', index=False, encoding='utf-8-sig')
    (OUT/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), flush=True)
    print('elapsed_seconds',round(time.time()-t0,1),flush=True)


if __name__ == '__main__':
    main()
