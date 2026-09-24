"""Offline exploratory pattern scan. DB is read-only; outputs only beside this file.

User-authorized 2026-09-24. Historical screening, NOT fresh OOS or model registration.
Run: python research/handoff/code_20260924_pattern_scan.py
"""
from pathlib import Path
import json
import sqlite3
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore', category=RuntimeWarning)
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('pattern_scan_20260924')


def allowed():
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    if now.weekday() < 5 and '20:10' <= now.strftime('%H:%M') <= '22:30':
        raise RuntimeError('Scheduled batch window: no file/DB access permitted')


def rolling(x, w, op='mean', minimum=None):
    r = pd.DataFrame(x).rolling(w, min_periods=minimum or w)
    return getattr(r, op)().to_numpy()


def lag(x, k):
    y = np.full_like(x, np.nan)
    y[k:] = x[:-k]
    return y


def rank(x, valid, markets):
    z = np.full_like(x, np.nan)
    for m in ('KOSPI', 'KOSDAQ'):
        mask = valid & (markets == m)
        z = np.where(mask, pd.DataFrame(np.where(mask, x, np.nan)).rank(axis=1, pct=True).to_numpy(), z)
    return z


def block_ci(x, block=8, reps=3000):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 5:
        return [float(np.mean(x)) if len(x) else None, None, None, len(x)]
    rng = np.random.default_rng(924)
    starts = rng.integers(0, len(x), (reps, int(np.ceil(len(x) / block))))
    ix = (starts[:, :, None] + np.arange(block)) % len(x)
    means = x[ix.reshape(reps, -1)[:, :len(x)]].mean(axis=1)
    return [float(x.mean()), *map(float, np.quantile(means, [.025, .975])), len(x)]


def main():
    allowed()
    OUT.mkdir(exist_ok=True)
    con = sqlite3.connect((ROOT.parent / 'dh-q7m3k-data/ohlcv.db').as_uri() + '?mode=ro', uri=True)
    con.execute('PRAGMA query_only=ON')
    df = pd.read_sql_query('SELECT ticker,date,close,high,low,volume,shares,market FROM daily_ohlcv', con)
    md = pd.read_sql_query('SELECT series,date,close FROM market_daily', con)
    con.close()
    dates = np.array(sorted(df.date.unique()))
    tickers = np.array(sorted(df.ticker.unique()))
    di = {d: i for i, d in enumerate(dates)}
    ti = {t: i for i, t in enumerate(tickers)}
    rr, cc = df.date.map(di).to_numpy(), df.ticker.map(ti).to_numpy()
    shape = (len(dates), len(tickers))

    def mat(col):
        a = np.full(shape, np.nan)
        a[rr, cc] = df[col].to_numpy()
        return a

    c, hi, lo, v, shares = [mat(k) for k in ['close', 'high', 'low', 'volume', 'shares']]
    # Market membership is read from each historical row, not today's listing.
    markets = np.full(shape, '', dtype='<U6')
    markets[rr, cc] = df.market.fillna('').to_numpy()
    del df
    mark = pd.DataFrame(c).ffill().to_numpy()  # valuation only; not signal or entry eligibility
    md = md.pivot(index='date', columns='series', values='close').reindex(dates)
    ix = np.where(markets == 'KOSPI', md.KOSPI.to_numpy()[:, None], md.KOSDAQ.to_numpy()[:, None])
    ret = c / lag(c, 1) - 1
    amount20 = rolling(c * v, 20)
    obs120 = rolling(np.isfinite(c).astype(float), 120, 'sum')
    susp60 = rolling((v == 0).astype(float), 60, 'sum')
    valid = (obs120 == 120) & (susp60 <= 5) & (amount20 >= 5e8) & (c > 0) & (v > 0)
    anchors = np.arange(np.searchsorted(dates, '20240101'), len(dates) - 21, 5)
    adates, mk, ok = dates[anchors], markets[anchors], valid[anchors]
    F = {}

    def feature(name, x, sign=1):
        F[name] = rank(sign * x[anchors], ok, mk)

    vol5, vol20, vol60 = [rolling(ret, k, 'std') for k in [5, 20, 60]]
    range1 = (hi - lo) / c
    range5, range20 = rolling(range1, 5), rolling(range1, 20)
    ma5, ma20, ma60 = [rolling(c, k) for k in [5, 20, 60]]
    r5, r20, r60, r120 = [c / lag(c, k) - 1 for k in [5, 20, 60, 120]]
    rs5 = r5 - (ix / lag(ix, 5) - 1)
    rs20 = r20 - (ix / lag(ix, 20) - 1)
    rs60 = r60 - (ix / lag(ix, 60) - 1)
    high20, high60, high120 = [rolling(c, k, 'max') for k in [20, 60, 120]]
    low60 = rolling(c, 60, 'min')
    vv5, vv20, vv60 = [rolling(v, k) for k in [5, 20, 60]]
    turn20 = rolling(v / shares, 20)
    clv = np.divide(2 * c - hi - lo, hi - lo, out=np.full_like(c, np.nan), where=hi > lo)
    features = {
        'quiet': (-vol60, 1), 'quiet20': (-vol20, 1),
        'prior_quiet': (-lag(vol60, 5), 1),
        'compression': (-vol5 / vol60, 1), 'range_compression': (-range5 / range20, 1),
        'prior_compression': (-lag(vol5 / vol60, 5), 1),
        'rs5': (rs5, 1), 'rs20': (rs20, 1), 'rs60': (rs60, 1),
        'acceleration': (rs5 - lag(rs5, 5), 1),
        'break20': (c / lag(high20, 1) - 1, 1), 'break60': (c / lag(high60, 1) - 1, 1),
        'nearhigh': (c / high120, 1),
        'dry': (-vv5 / vv60, 1), 'prior_dry': (-lag(vv5 / vv60, 5), 1),
        'volume_restart': (vv5 / lag(vv20, 5), 1),
        'turn_low': (-turn20, 1), 'size': (c * shares, 1),
        'amount': (amount20, 1),
        'steady': (rolling((ret > 0).astype(float), 60), 1),
        'clv': (rolling(clv, 20, minimum=15), 1),
        'efficiency': ((c / lag(c, 60) - 1) / rolling(np.abs(ret), 60, 'sum'), 1),
        'pullback': (-r5, 1), 'rebound': (c / lag(c, 2) - 1, 1),
        'prior_pullback': (-lag(r5, 2), 1),
        'low_recovery': (c / low60 - 1, 1),
        'range_quiet': (-range20, 1),
        'upvolume': (rolling(np.where(ret > 0, v, 0), 20) / vv20, 1),
        'ma_slope': (ma20 / lag(ma20, 10) - 1, 1),
    }
    for name, (value, sign) in features.items():
        feature(name, value, sign)
    del features
    # Each recipe was fixed before seeing its returns. Equal rank weights, no fitting.
    specs = []

    def add(name, family, keys, mask=None):
        score = np.mean([F[k] for k in keys], axis=0)
        score = np.where(ok & (mask if mask is not None else True), score, np.nan)
        specs.append(dict(name=name, family=family, keys=keys, score=score))

    add('base_quiet', 'baseline', ['quiet'])
    add('base_quiet_turn', 'baseline', ['quiet', 'turn_low'])
    add('base_relative60', 'baseline', ['rs60'])
    add('base_nearhigh', 'baseline', ['nearhigh'])
    for suffix, keys in [
        ('rs5', ['prior_quiet', 'rs5']), ('rs20', ['prior_quiet', 'rs20']),
        ('accelerate', ['prior_quiet', 'acceleration']),
        ('steady', ['quiet', 'steady', 'rs20']),
        ('clv', ['quiet', 'clv', 'rs20']),
    ]:
        add('quiet_strength_' + suffix, 'quiet_strength', keys)
    for suffix, keys in [
        ('20', ['prior_compression', 'break20']), ('60', ['prior_compression', 'break60']),
        ('volume', ['prior_compression', 'break20', 'volume_restart']),
        ('relative', ['prior_compression', 'break20', 'rs20']),
        ('range', ['range_compression', 'nearhigh', 'rs20']),
    ]:
        add('squeeze_' + suffix, 'squeeze', keys)
    for suffix, keys in [
        ('dry', ['rs60', 'pullback', 'dry']), ('quiet', ['rs60', 'pullback', 'quiet20']),
        ('rebound', ['rs60', 'prior_pullback', 'rebound']),
        ('high', ['nearhigh', 'pullback', 'dry']),
        ('resume', ['rs60', 'prior_pullback', 'rebound', 'prior_dry']),
    ]:
        add('pullback_' + suffix, 'pullback', keys, (ma20 > ma60)[anchors])
    for suffix, keys in [
        ('clv', ['dry', 'clv', 'nearhigh']), ('restart', ['prior_dry', 'volume_restart', 'rs5']),
        ('quiet_restart', ['prior_quiet', 'prior_dry', 'rs5', 'volume_restart']),
        ('upvolume', ['upvolume', 'quiet', 'rs20']),
        ('hold', ['prior_dry', 'nearhigh', 'rs20']),
    ]:
        add('volume_' + suffix, 'volume_sequence', keys)
    for suffix, keys in [
        ('quiet', ['rs20', 'quiet']), ('persistent', ['rs60', 'rs20', 'steady']),
        ('accelerate', ['rs60', 'acceleration']), ('high', ['rs20', 'nearhigh']),
        ('efficient', ['rs20', 'efficiency', 'quiet']),
    ]:
        add('relative_' + suffix, 'relative_strength', keys)
    for suffix, keys in [
        ('quiet', ['low_recovery', 'quiet20']), ('slope', ['low_recovery', 'ma_slope', 'dry']),
        ('rebound', ['prior_pullback', 'rebound', 'quiet']),
        ('cross', ['rs20', 'ma_slope', 'prior_quiet']),
    ]:
        add('recovery_' + suffix, 'recovery', keys)
    # Strong quietness gate tests conditional information, not another equal-weight blend.
    for suffix, keys in [
        ('steady', ['steady', 'nearhigh']), ('rs20', ['rs20']),
        ('accelerate', ['acceleration', 'nearhigh']), ('size', ['size', 'steady']),
        ('no_size', ['steady']), ('turn', ['turn_low', 'rs20']),
    ]:
        add('quiet_gate_' + suffix, 'quiet_gate', keys, F['quiet'] >= .8)
    # Direct ablations for approximate shares: otherwise identical formulas.
    add('quiet_strength_with_size', 'share_approx', ['quiet', 'rs20', 'size'])
    add('quiet_strength_with_turn', 'share_approx', ['quiet', 'rs20', 'turn_low'])
    add('quiet_strength_no_shares', 'share_approx', ['quiet', 'rs20'])
    # Follow-up controls added after inspecting the original 42 recipes.
    # They are explanatory checks, never eligible for 2024 family selection.
    add('control_size', 'posthoc_control', ['size'])
    add('control_amount', 'posthoc_control', ['amount'])
    add('control_quiet_size', 'posthoc_control', ['quiet', 'size'])
    add('control_rs20_size', 'posthoc_control', ['rs20', 'size'])
    assert len({s['name'] for s in specs}) == len(specs)
    allowed()
    (OUT / 'recipes.json').write_text(json.dumps([{k: val for k, val in s.items() if k != 'score'} for s in specs], indent=2), encoding='utf-8')
    print('panel', shape, 'anchors', len(anchors), 'recipes', len(specs), flush=True)

    rows, picks = [], {}
    cost = .0035  # assumed round-trip cost, not an assertion of current brokerage/tax rates
    for s in specs:
        for m in ('KOSPI', 'KOSDAQ'):
            ps = []
            for ai, t in enumerate(anchors):
                candidates = np.flatnonzero((mk[ai] == m) & np.isfinite(s['score'][ai]))
                order = candidates[np.argsort(-s['score'][ai, candidates], kind='stable')][:20]
                ps.append(order)
            picks[s['name'], m] = ps
    for ai, t in enumerate(anchors):
        e = t + 1
        for m in ('KOSPI', 'KOSDAQ'):
            bench_series = md[m].to_numpy()
            universe = np.flatnonzero(ok[ai] & (mk[ai] == m))
            for h in [20, 40, 60]:
                end = e + h
                if end >= len(dates):
                    continue
                index_ret = bench_series[end] / bench_series[e] - 1
                entry_ok = np.isfinite(c[e]) & (c[e] > 0) & (v[e] > 0)
                # Signals picked on t; unavailable t+1 entry holds cash (no replacement).
                returns = np.where(entry_ok, mark[end] / c[e] - 1 - cost, 0.)
                ew = float(np.mean(returns[universe]))
                base_ids = picks['base_quiet', m][ai]
                base = float(returns[base_ids].sum() / 20)
                for s in specs:
                    ids = picks[s['name'], m][ai]
                    selected = returns[ids]
                    net = float(selected.sum() / 20)
                    # Cash completes all baskets to 20 slots, avoiding hidden concentration.
                    loss_stress = np.where(~np.isfinite(c[end, ids]) & entry_ok[ids], -1-cost, selected)
                    rows.append(dict(name=s['name'], family=s['family'], market=m, date=dates[t], exit_date=dates[end],
                        year=int(dates[t][:4]), h=h, n_selected=len(ids), n_filled=int(entry_ok[ids].sum()),
                        net=net, excess_index=net-index_ret, excess_ew=net-ew, delta_quiet=net-base,
                        index=index_ret, ew=ew, win_fraction=float(np.sum(selected > 0)/20),
                        missing_exit=int((~np.isfinite(c[end, ids]) & entry_ok[ids]).sum()),
                        stress_missing_net=float(loss_stress.sum()/20)))
    R = pd.DataFrame(rows)
    allowed()
    R.to_csv(OUT / 'cohorts.csv', index=False)
    # Select only on 2024 entries whose complete 40-day outcome was known in 2024.
    dev = R[(R.year == 2024) & (R.exit_date < '20250101') & (R.h == 40)]
    dev_scores = dev.groupby(['family','name']).excess_index.mean()
    winners = {family: group.droplevel(0).idxmax() for family, group in dev_scores.groupby(level=0) if family not in ('baseline','posthoc_control')}
    chosen = list(dict.fromkeys(['base_quiet', 'base_quiet_turn', *winners.values()]))
    print('2024 selected', winners, flush=True)
    summary = []
    for (name, m, h, year), g in R.groupby(['name','market','h','year']):
        rec = dict(name=name, market=m, h=int(h), year=int(year), n=len(g), mean_slots=float(g.n_filled.mean()))
        for metric in ['net','excess_index','excess_ew','delta_quiet']:
            mu, low, high, n = block_ci(g[metric], max(1, h//5), reps=1500)
            rec.update({metric:mu, metric+'_lo':low, metric+'_hi':high})
        summary.append(rec)
    S = pd.DataFrame(summary)
    allowed()
    S.to_csv(OUT / 'summary_all.csv', index=False)
    # Pool markets on each date BEFORE resampling; they are not independent samples.
    validation = []
    for name in chosen:
        for period, mask in [('2025',R.year==2025),('2026',R.year==2026),('2025_2026',R.year>=2025)]:
            for h in [20,40,60]:
                g = R[(R.name==name)&mask&(R.h==h)].groupby('date').mean(numeric_only=True)
                rec=dict(name=name, period=period, h=h, n_anchors=len(g), mean_filled=float(g.n_filled.mean()*2))
                for metric in ['net','excess_index','excess_ew','delta_quiet','stress_missing_net']:
                    mu, low, high, n = block_ci(g[metric], h//5)
                    rec.update({metric:mu, metric+'_lo':low, metric+'_hi':high})
                validation.append(rec)
    V = pd.DataFrame(validation)
    V.to_csv(OUT / 'validation_selected.csv', index=False)
    # Liquidity / share approximation / abnormal historical price-move sensitivity.
    sensitivities=[]
    byname={s['name']:s for s in specs}
    sens_names=list(dict.fromkeys(chosen+['quiet_strength_with_size','quiet_strength_with_turn','quiet_strength_no_shares']))
    pastjump=rolling((np.abs(ret)>.35).astype(float),60,'sum')[anchors]
    for name in sens_names:
        for label, extra in [('main', np.ones_like(ok)), ('amount_20억', amount20[anchors]>=2e9),
                             ('exclude_past_jump35',pastjump==0),('top10',np.ones_like(ok)),('top40',np.ones_like(ok))]:
            N=10 if label=='top10' else 40 if label=='top40' else 20
            vals=[]
            for ai,t in enumerate(anchors):
                e,end=t+1,t+41
                if dates[t]<'20250101' or end>=len(dates):continue
                per=[]
                for m in ('KOSPI','KOSDAQ'):
                    s=byname[name]['score'][ai]
                    ids=np.flatnonzero((mk[ai]==m)&extra[ai]&np.isfinite(s))
                    ids=ids[np.argsort(-s[ids],kind='stable')][:N]
                    eo=np.isfinite(c[e,ids])&(c[e,ids]>0)&(v[e,ids]>0)
                    net=np.where(eo,mark[end,ids]/c[e,ids]-1-cost,0.).sum()/N
                    per.append(net-(md[m].iloc[end]/md[m].iloc[e]-1))
                vals.append(np.mean(per))
            mu,low,high,n=block_ci(vals,8)
            sensitivities.append(dict(name=name,variant=label,excess_index=mu,lo=low,hi=high,n=n))
    pd.DataFrame(sensitivities).to_csv(OUT/'sensitivities.csv',index=False)
    # Fully invested non-overlapping 40-day portfolios with four starting dates.
    # Each market gets half the capital, equal 20 slots. Cash if entry impossible.
    portfolios=[]
    contributions=[]
    valid_ai=[a for a,t in enumerate(anchors) if dates[t]>='20250101' and t+41<len(dates)]
    for name in chosen:
        for offset in [0,2,4,6]:
            ais=valid_ai[offset::8]
            wealth=1.; path=[]; indexpath=[]; ewpath=[]; start=None
            ew_wealth=1.
            for ai in ais:
                t=anchors[ai];e,end=t+1,t+41
                if start is None:start=e
                curves=[]; ewcurves=[]
                for m in ('KOSPI','KOSDAQ'):
                    ids=picks[name,m][ai]
                    eo=np.isfinite(c[e,ids])&(c[e,ids]>0)&(v[e,ids]>0)
                    gains=np.where(eo[None,:],mark[e:end+1,ids]/c[e,ids][None,:]-1,0.)
                    curve=1+gains.sum(axis=1)/20-cost/2*eo.sum()/20
                    curve[-1]-=cost/2*eo.sum()/20
                    curves.append(curve)
                    uid=np.flatnonzero(ok[ai]&(mk[ai]==m))
                    ueo=np.isfinite(c[e,uid])&(c[e,uid]>0)&(v[e,uid]>0)
                    ug=np.where(ueo[None,:],mark[e:end+1,uid]/c[e,uid][None,:]-1,0.)
                    uc=1+ug.mean(axis=1)-cost/2*ueo.mean();uc[-1]-=cost/2*ueo.mean()
                    ewcurves.append(uc)
                    for j,ident in enumerate(ids):
                        if eo[j]: contributions.append(dict(name=name,offset=offset*5,date=dates[t],ticker=tickers[ident],market=m,gross=float(gains[-1,j])))
                curve=np.mean(curves,axis=0);uc=np.mean(ewcurves,axis=0)
                # At shared boundary use the next cohort's post-entry-cost value.
                if path:path.pop();ewpath.pop();indexpath.pop()
                path.extend((wealth*curve).tolist());ewpath.extend((ew_wealth*uc).tolist())
                b=.5*(md.KOSPI.iloc[e:end+1].to_numpy()/md.KOSPI.iloc[start]+md.KOSDAQ.iloc[e:end+1].to_numpy()/md.KOSDAQ.iloc[start])
                indexpath.extend(b.tolist())
                wealth*=curve[-1];ew_wealth*=uc[-1]
            ar=np.array([1.,*path]);br=np.array([1.,*indexpath]);ur=np.array([1.,*ewpath])
            days=len(path)-1
            portfolios.append(dict(name=name,offset=offset*5,n_cohorts=len(ais),start=dates[start],end=dates[anchors[ais[-1]]+41],
                cagr=wealth**(252/days)-1,mdd=float(np.min(ar/np.maximum.accumulate(ar)-1)),total=wealth-1,
                index_cagr=br[-1]**(252/days)-1,index_mdd=float(np.min(br/np.maximum.accumulate(br)-1)),
                ew_cagr=ur[-1]**(252/days)-1,ew_mdd=float(np.min(ur/np.maximum.accumulate(ur)-1))))
    P=pd.DataFrame(portfolios);P.to_csv(OUT/'portfolios.csv',index=False)
    C=pd.DataFrame(contributions);C.to_csv(OUT/'contributions.csv',index=False)
    meta=dict(rows=int(np.isfinite(c).sum()),tickers=len(tickers),dates=len(dates),first=dates[0],last=dates[-1],
        recipes=len(specs),winners=winners,chosen=chosen,missing_exits=int(R.missing_exit.sum()),
        cost_roundtrip=cost,selection='2024 h40 mean excess over own-market index; outcome closed by 2024-12-31',
        limitations=['Historical data already explored in earlier research; NOT untouched OOS',
            'Surviving/backfilled universe; historical delisted coverage not proven',
            'Adjusted historical OHLCV can differ from what was known then',
            'shares and turnover use approximate historical shares',
            'Price-only returns; dividends excluded for stocks and index',
            'Close*volume is approximate trading value; adjusted-price volume basis may differ',
            '95% block intervals are nominal, uncorrected for multiple research choices',
            'Last observed close marks missing exits; separate total-loss sensitivity provided',
            'Daily OHLCV cannot fully model limit-up fills, slippage, or suspension liquidation'])
    allowed();(OUT/'metadata.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    print(V[(V.h==40)&(V.period=='2025_2026')][['name','n_anchors','net','excess_index','excess_index_lo','excess_index_hi','delta_quiet']].round(4).to_string(index=False),flush=True)
    print('portfolio averages\n',P.groupby('name')[['cagr','mdd','index_cagr','ew_cagr']].mean().round(4).to_string(),flush=True)
    print('DONE',OUT,flush=True)


if __name__=='__main__':
    main()
