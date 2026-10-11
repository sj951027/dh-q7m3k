"""Offline label permutation of CLOSED verdict windows only.

python -B research/handoff/code_20261012_placebo_null.py --reps 2000 --boot 20000
No project imports, collectors, network, production writes or actual model IC.
Only the companion REPLY markdown is written. SQLite mode=ro + query_only.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse
import ast
import hashlib
import re
import sqlite3
import time

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('REPLY_20261012_placebo_null.md')
SEED = 20261012
SPECS = [
    ('v30', 'v3_scores', 'final_score_v3', '20260606', '20260809', (6, 7), .1235),
    ('lv_b', 'lowvol_scores', 'lowvol_score', '20260625', '20260829', (10,), .0687),
    ('sv_a', 'wu_scores', 'wu_score', '20260715', '20260913', (11, 6), .0330),
]


def guard():
    now = datetime.now(timezone(timedelta(hours=9)))
    if now.weekday() < 5 and (20, 10) <= (now.hour, now.minute) < (22, 30):
        raise SystemExit('평일 20:10~22:30 KST: 실행 중단(휴일도 보수적으로 중단)')


def ro(path):
    guard()
    c = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    c.execute('PRAGMA query_only=ON')
    return c


def anchor(rid, didx):
    if rid in didx:
        return didx[rid]
    d = datetime.strptime(rid, '%Y%m%d')
    return next((didx[x] for k in range(1, 6)
                 if (x := (d-timedelta(days=k)).strftime('%Y%m%d')) in didx), None)


def gate(c, end):
    cnt = pd.read_sql_query('SELECT run_id,count(*) n FROM stage1_oversold '
                            'WHERE run_id<=? GROUP BY run_id', c, params=(end,))
    partial = set(cnt.loc[cnt.n < cnt.n.median()*.30, 'run_id'])
    double = set()
    for tb in ('v3_scores', 'lowvol_scores', 'wu_scores'):
        f = pd.read_sql_query(f'SELECT run_id,model_id,frozen_at FROM {tb} '
                              'WHERE run_id<=?', c, params=(end,))
        f['ts'] = pd.to_datetime(f.frozen_at, utc=True, errors='coerce')
        z = f.dropna(subset=['ts']).groupby(['run_id', 'model_id']).ts.agg(['min', 'max'])
        double.update(z.index.get_level_values(0)[(z['max']-z['min']).dt.total_seconds() >= 3600])
    return partial, double


def prepare(spec):
    mid, tb, sc, start, end, denoms, actual = spec
    with ro(ROOT/'history.db') as c:
        # SQL itself enforces the blind boundary; no pending score rows loaded.
        s = pd.read_sql_query(f'SELECT run_id,market,ticker,{sc} score FROM {tb} '
                              'WHERE model_id=? AND run_id BETWEEN ? AND ?',
                              c, params=(mid, start, end))
        partial, double = gate(c, end)
    s[['run_id', 'market', 'ticker']] = s[['run_id', 'market', 'ticker']].astype(str)
    assert not s.duplicated(['run_id', 'market', 'ticker']).any()
    assert s.run_id.between(start, end).all()
    with ro(ROOT.parent/'dh-q7m3k-data'/'ohlcv.db') as c:
        # Only the main price table. No post-verdict prices, including for jumps.
        p = pd.read_sql_query('SELECT ticker,date,close,shares FROM daily_ohlcv '
                              'WHERE date BETWEEN ? AND ?', c, params=('20260525', end))
    close = p.pivot_table(index='date', columns='ticker', values='close', aggfunc='last').sort_index()
    dates = list(close.index)
    didx = {d: i for i, d in enumerate(dates)}
    cand = {}
    excluded = partial | double
    for rid in s.run_id.unique():
        t = anchor(rid, didx)
        if rid not in excluded and t is not None:
            cand.setdefault(t, []).append(rid)
    keep = {min([r for r in rs if r in didx] or rs) for rs in cand.values()}
    # Price completion, not score run date, limits the h20 sample.
    rids = sorted(r for r in keep if anchor(r, didx)+21 < len(dates))
    times = np.array([anchor(r, didx) for r in rids])
    pct = close.pct_change(fill_method=None).abs()
    fwd, missing, jumpcut = [], [], []
    for t in times:
        raw = close.iloc[t+21]/close.iloc[t+1]-1
        jump = pct.iloc[t+2:t+22].max()
        missing.append(raw.isna().to_numpy())
        jumpcut.append((raw.notna() & ~(jump <= .32)).to_numpy())
        fwd.append(raw.where(jump <= .32).to_numpy())
    ret = np.array(fwd)
    pmiss, pjump = np.array(missing), np.array(jumpcut)
    panels = []
    stratum = []
    size_coverage = []
    for mk, g in s.groupby('market'):
        tickers = sorted(g.ticker.unique())
        piv = g.pivot(index='run_id', columns='ticker', values='score').reindex(columns=tickers)
        scores = piv.reindex(rids).to_numpy(float)
        # Every appearance counts, including incomplete/duplicate/excluded runs.
        counts = g.groupby('ticker').run_id.nunique().reindex(tickers).to_numpy()
        ix = close.columns.get_indexer(tickers)
        rr = np.full(scores.shape, np.nan)
        mm = np.ones(scores.shape, bool)
        jj = np.zeros(scores.shape, bool)
        exists = ix >= 0
        rr[:, exists] = ret[:, ix[exists]]
        mm[:, exists] = pmiss[:, ix[exists]]
        jj[:, exists] = pjump[:, ix[exists]]
        # One fixed PIT size class per trajectory: first available window quote.
        # No current shares, no changing daily mapping. Missing size is a 6th class.
        caps = p[p.ticker.isin(tickers) & p.date.between(start, end)].copy()
        caps['cap'] = caps.close*caps.shares
        caps = caps[caps.cap > 0].sort_values('date').drop_duplicates('ticker')
        cs = caps.set_index('ticker').cap.reindex(tickers)
        bins = np.full(len(tickers), 5, dtype=int)
        ok = cs.notna().to_numpy()
        bins[ok] = np.clip(np.ceil(cs[ok].rank(method='average', pct=True).to_numpy()*5).astype(int)-1, 0, 4)
        size_coverage.append([mk, int(ok.sum()), len(tickers)])
        panels.append(dict(market=mk, tickers=tickers, score=scores, ret=rr,
                           missing=mm, jumpcut=jj, count=counts, capbin=bins))
        for method, labels in [('전체', np.zeros(len(tickers), int)),
                               ('출현5run', (counts-1)//5), ('시총5분위', bins)]:
            for label in np.unique(labels):
                n = int((labels == label).sum())
                stratum.append([mid, method, mk, int(label), n])
    non = []
    for i, t in enumerate(times):
        if not non or t-times[non[-1]] >= 20:
            non.append(i)
    original_counts = np.column_stack([np.sum(np.isfinite(x['score']) & np.isfinite(x['ret']), axis=1)
                                       for x in panels])
    return dict(mid=mid, start=start, end=end, price_end=dates[-1], rids=rids, times=times,
                panels=panels, denoms=denoms, actual=actual, non=np.array(non),
                oos=len(keep), partial=sorted(partial), double=sorted(double),
                kept=sorted(keep), raw_runs=s.run_id.nunique(), strata=stratum,
                capcoverage=size_coverage, counts=original_counts,
                date_digest=hashlib.sha256(('|'.join(rids)).encode()).hexdigest())


def correlations(scores, returns):
    """Batch exact Spearman with pairwise removal BEFORE reranking, ties average."""
    valid = np.isfinite(scores) & np.isfinite(returns)
    n = valid.sum(axis=1)
    x = np.where(valid, scores, np.inf)
    y = np.where(valid, returns, np.inf)
    rx = np.where(valid, rankdata(x, axis=1)-(n[:, None]+1)/2, 0)
    ry = np.where(valid, rankdata(y, axis=1)-(n[:, None]+1)/2, 0)
    # Exact number of distinct finite values, mirroring MIN_GROUP/nunique gates.
    sx, sy = np.sort(x, axis=1), np.sort(y, axis=1)
    ux = np.isfinite(sx[:, 0]).astype(int) + ((sx[:, 1:] != sx[:, :-1]) & np.isfinite(sx[:, 1:])).sum(axis=1)
    uy = np.isfinite(sy[:, 0]).astype(int) + ((sy[:, 1:] != sy[:, :-1]) & np.isfinite(sy[:, 1:])).sum(axis=1)
    div = np.sqrt((rx*rx).sum(axis=1)*(ry*ry).sum(axis=1))
    out = np.divide((rx*ry).sum(axis=1), div, out=np.full(len(n), np.nan), where=div > 0)
    out[(n < 8) | (ux < 3) | (uy < 3)] = np.nan
    return out


def permutation(case, method, reps, seed):
    rng = np.random.default_rng(seed)
    n = len(case['rids'])
    out = np.zeros((reps, n))
    markets = np.zeros((reps, n), int)
    loss_missing = np.zeros(reps)
    loss_jump = np.zeros(reps)
    count = np.zeros(reps)
    fixed = np.zeros(reps)
    pools = 0
    for panel in case['panels']:
        s, ret = panel['score'], panel['ret']
        size = s.shape[1]
        pools += size
        labels = {'전체': np.zeros(size, int), '출현5run': (panel['count']-1)//5,
                  '시총5분위': panel['capbin']}[method]
        groups = [np.flatnonzero(labels == k) for k in np.unique(labels)]
        for lo in range(0, reps, 64):
            guard()
            hi = min(lo+64, reps)
            maps = np.tile(np.arange(size), (hi-lo, 1))
            for ids in groups:
                maps[:, ids] = rng.permuted(np.tile(ids, (hi-lo, 1)), axis=1)
            assert np.all(np.sort(maps, axis=1) == np.arange(size))
            fixed[lo:hi] += (maps == np.arange(size)).sum(axis=1)
            # maps[source] = recipient. Same map at every run: entire trajectory moves.
            for t in range(n):
                ss = np.broadcast_to(s[t], (hi-lo, size))
                rr = ret[t, maps]
                exists = np.isfinite(ss)
                count[lo:hi] += exists.sum(axis=1)
                loss_missing[lo:hi] += (exists & panel['missing'][t, maps]).sum(axis=1)
                loss_jump[lo:hi] += (exists & panel['jumpcut'][t, maps]).sum(axis=1)
                ic = correlations(ss, rr)
                ok = np.isfinite(ic)
                out[lo:hi, t] += np.where(ok, ic, 0)
                markets[lo:hi, t] += ok
    out = np.divide(out, markets, out=np.full_like(out, np.nan), where=markets > 0)
    return out, dict(missing=loss_missing/count, jump=loss_jump/count,
                     fixed=fixed/pools, dropped=(markets == 0).sum(axis=1),
                     one_market=(markets == 1).sum(axis=1))


def weeks(rids):
    labs = [datetime.strptime(r, '%Y%m%d').isocalendar()[:2] for r in rids]
    return np.array([sorted(set(labs)).index(x) for x in labs])


def banks(n, labs, boot):
    # Same iid percentile and week-concatenation distributions as canonical tools.
    rng = np.random.default_rng(7)
    iid = rng.multinomial(n, np.full(n, 1/n), size=boot)/n
    nw = len(np.unique(labs))
    sizes = np.bincount(labs)
    rng = np.random.default_rng(7)
    picks = rng.multinomial(nw, np.full(nw, 1/nw), size=boot)
    week = picks[:, labs]/(picks@sizes)[:, None]
    return iid, week


def stats(x, rids, denoms, boot):
    # Group by surviving-anchor pattern; missing anchors are removed canonically.
    result = {('date', 1): np.zeros(len(x), bool), ('week', 1): np.zeros(len(x), bool)}
    for d in denoms:
        result[('date', d)] = np.zeros(len(x), bool)
        result[('week', d)] = np.zeros(len(x), bool)
    ses = np.full(len(x), np.nan)
    direction = np.zeros(len(x), bool)
    masks, inverse = np.unique(np.isfinite(x), axis=0, return_inverse=True)
    for group, mask in enumerate(masks):
        ii = np.flatnonzero(inverse == group)
        n = int(mask.sum())
        if not n:
            continue
        rr = np.array(rids)[mask].tolist()
        lab = weeks(rr)
        iid, week = banks(n, lab, boot)
        vals = x[np.ix_(ii, mask)]
        direction[ii] = np.mean(np.column_stack([vals[:, lab == w].mean(axis=1)
                                                for w in np.unique(lab)]) > 0, axis=1) >= .60
        for bank, name in [(iid, 'date'), (week, 'week')]:
            for lo in range(0, len(ii), 64):
                guard()
                zz = vals[lo:lo+64]@bank.T
                for d in (1,)+tuple(denoms):
                    result[(name, d)][ii[lo:lo+64]] = np.quantile(zz, .025/d, axis=1) > 0
                if name == 'date':
                    ses[ii[lo:lo+64]] = zz.std(axis=1, ddof=1)
    for d in (1,)+tuple(denoms):
        result[('both', d)] = result[('date', d)] & result[('week', d)]
    return dict(flags=result, direction=direction, se=ses, mean=np.nanmean(x, axis=1),
                n=np.isfinite(x).sum(axis=1))


def fake(ns, times, reps, seed, target=None):
    """Exact synthetic Gaussian prices + AR(.9) scores; no real score/return inputs."""
    rng = np.random.default_rng(seed)
    target = len(ns) if target is None else target
    out = np.zeros((reps, target))
    for lo in range(0, reps, 40):
        guard()
        hi = min(lo+40, reps)
        for mk in range(2):
            pool = int(ns[:, mk].max())
            daily = rng.standard_normal((hi-lo, pool, int(times[-1]+20)))
            acc = np.concatenate([np.zeros((hi-lo, pool, 1)), daily.cumsum(axis=2)], axis=2)
            y = (acc[:, :, times+20]-acc[:, :, times])/np.sqrt(20)
            z = np.empty_like(y)
            z[:, :, 0] = rng.standard_normal((hi-lo, pool))
            for t in range(1, len(ns)):
                a = .9**int(times[t]-times[t-1])
                z[:, :, t] = a*z[:, :, t-1]+np.sqrt(1-a*a)*rng.standard_normal((hi-lo, pool))
            for t, n in enumerate(ns[:target, mk]):
                out[lo:hi, t] += .5*correlations(z[:, :n, t], y[:, :n, t])
    return out


def verify():
    # No real pairings: tie/missing/rank thresholds and permutations on toy inputs.
    x = np.array([[1,1,2,3,5,8,13,21,34,55], [1]*10, np.arange(10)])
    y = np.array([[3,2,1,4,8,5,7,9,np.nan,6], np.arange(10), [np.nan]*3+list(range(7))])
    a = correlations(x, y)
    assert np.isclose(a[0], spearmanr(x[0], y[0], nan_policy='omit').statistic)
    assert np.isnan(a[1:]).all()
    # Check source functions without executing/importing project modules.
    tree = ast.parse((ROOT/'leaderboard.py').read_text(encoding='utf-8-sig'))
    funcs = [z for z in tree.body if isinstance(z, ast.FunctionDef) and z.name in ('anchor', 'dedupe_by_anchor', 'build_gates')]
    env = dict(np=np, pd=pd, GATE_FRAC=.30,
               TRACKS={'v3':('v3_scores','final_score_v3',None),
                       'lv':('lowvol_scores','lowvol_score',None), 'wu':('wu_scores','wu_score',None)})
    exec(compile(ast.Module(body=funcs, type_ignores=[]), '<read-only canonical helpers>', 'exec'), env)
    return env


def table(head, rows):
    return '\n'.join(['| '+' | '.join(head)+' |', '|'+ '|'.join(['---']*len(head))+'|']+
                     ['| '+' | '.join(map(str, row))+' |' for row in rows])


def pct(a):
    return f'{100*np.mean(a):.2f}'


def rate_rows(label, s, denoms):
    rows = []
    for d in (1,)+tuple(denoms):
        for name in ('date', 'week', 'both'):
            f = s['flags'][(name, d)]
            rows.append([label, d, {'date':'날짜', 'week':'주', 'both':'둘 다'}[name],
                         pct(f), pct(f & s['direction'])])
    return rows


def distribution(label, s, actual):
    mu = s['mean']
    sd = mu.std(ddof=1)
    se = np.nanmedian(s['se'])
    p = (1+np.sum(mu >= actual))/(len(mu)+1)
    return [label, *[f'{q:+.5f}' for q in np.quantile(mu, [.025, .5, .975])],
            f'{sd:.5f}', f'{se:.5f}', f'{sd/se:.2f}', f'{100*np.mean(mu < actual):.2f}',
            f'{p:.6f} ({int(np.sum(mu >= actual))}/{len(mu)})']


def append_original(args):
    """Recreate the OLD synthetic T40 experiment, no additional database reads.

    Counts only come from the previously published markdown table. Generate
    100 anchors exactly as the old exact_panels main case, but rank only the
    first 20. For R<=4000 this is the original run's prefix, same outer seeds.
    """
    old = (ROOT/'research/handoff/REPLY_20261011_verdict_power.md').read_text(encoding='utf-8')
    raw = []
    for line in old.splitlines():
        cells = [z.strip() for z in line.strip('|').split('|')]
        if len(cells) == 5 and re.fullmatch('2026[0-9]{4}', cells[0]) and all('/' in z for z in cells[1:]):
            raw.append([[int(a) for a in cells[j].split('/')] for j in (1,2,3)])
    raw = np.asarray(raw)
    assert raw.shape == (16, 3, 2), raw.shape
    # Calendar labels replicate old group_labels([5,3,5,3],20) exactly.
    dates = []
    base = datetime(2020,1,6)
    for week, size in enumerate((5,3,5,3,4)):
        dates.extend([(base+timedelta(days=7*week+i)).strftime('%Y%m%d') for i in range(size)])
    sections = ['\n## [5-추가] 원래 가짜 q=0.9·T40 실험의 모든 칸 재계산',
                f'이 절은 이전 보고서의 가짜 생성 조건 그대로(100 합성 앵커를 생성한 뒤 앞 20개 사용, 원래 외부 seed 20281011~13, 시장별 종목 수는 이전 보고서에 공개한 16run의 행 수를 반복) {args.reps:,}회 계산했다. 실제 자료의 점수·수익은 읽지 않는다. 기존 4,000회 실험의 앞 {min(args.reps,4000):,}회에 해당하며 재표집은 이번 보고서와 같은 {args.boot:,}회라 기존 6,000회 표와 경계에서 차이가 날 수 있다. 날짜20·주블록5·비겹침1. 이 절로 원래 모의실험과 실제 자리바꿈 표의 요청 칸을 나란히 비교할 수 있다. 합성분포 내 정본 숫자의 위치는 실제 자료 자리바꿈 p값이 아니다.']
    for ti, spec in enumerate(SPECS):
        mid, *_, denoms, actual = spec
        print('original synthetic T40',mid,flush=True)
        ns = raw[np.arange(100)%16, ti, :]
        x = fake(ns,np.arange(100),args.reps,20261011+20000+ti,target=20)
        st = stats(x,dates,denoms,args.boot)
        sn = stats(x[:,:1],dates[:1],denoms,args.boot)
        sections += ['\n### 원 가짜 모의실험: '+mid+' 모양',
                     table(['방식','분모','구간','방향 제외%','주 방향60% 포함%'],rate_rows('원 가짜T40',st,denoms)),
                     table(['방식','2.5%','50%','97.5%','평균 SD','날짜 SE 중앙값','SD/SE','정본 숫자 백분위','합성 우측 확률'],
                           [distribution('원 가짜T40',st,actual)]),
                     '비겹침1개(원래 모의실험의 20연속 앵커에서 h20 간격):',
                     table(['방식','분모','구간','방향 제외%','주 방향60% 포함%'],rate_rows('원 가짜T40 비겹침',sn,denoms))]
    guard()
    report = OUT.read_text(encoding='utf-8')
    # Place benchmarks next to other results, before limitations and reproduction.
    boundary = report.index('## 한계·확인 못 함')
    report = report[:boundary]+'\n\n'.join(sections)+'\n\n'+report[boundary:]
    report = report.replace('원래 T40·합성 20앵커와 실제 세 창의 n·주 구성·종목 수가 달라',
                            '아래 추가 절에서 원래 가짜 T40의 누락 칸도 재계산했다. 원래 T40·합성 20앵커와 실제 세 창의 n·주 구성·종목 수가 달라')
    report = report.replace('현재 주식수를 과거에 붙이지 않았다.',
                            '각 date 행에 저장된 shares를 사용했다. 수집 당시 주식수가 사후 수정되지 않았는지와 엄밀한 당시 시총 일치는 확인 못 함.')
    report = report.replace('시총 층에서 평균이 0일 필요는 없다(종목 특성 일부 유지).',
                            '출현/시총 층에서 평균이 0일 필요는 없다. 층 사이 점수·수익 차이가 남으며, 출현 층은 창 전체의 뒤쪽 출현 정보도 사용한다.')
    report = report.replace('단일 과거 시장창에 조건을 건 비율이다.',
                            '출현 run 수 제한 역시 층 사이 점수·수익 관계를 남길 수 있다. 따라서 그 방식의 100% 통과 같은 값도 효과0 전체의 오류율로 볼 수 없다. 단일 과거 시장창에 조건을 건 비율이다.')
    report = report.replace('날짜 Bonf(주 분모)', '날짜 Bonf(분모6·10·11)')
    report = report.replace('실행시간 ', '본 계산 실행시간(원 가짜T40 추가 계산 제외) ')
    report = report.replace('실제 자리바꿈과 직접 같은 생성분포가 아니다.',
                            '실제 자리바꿈과 직접 같은 생성분포가 아니다. 가짜 행의 p는 합성분포 안 위치이며 실제 자료 자리바꿈 p값이 아니다.')
    report = report.replace('비겹침 k가 작으면 기존 부트스트랩의 점 구간/불안정성이 그대로 나타난다.',
                            '비겹침 k가 작으면 기존 부트스트랩의 점 구간/불안정성이 그대로 나타난다. k=1은 한 IC>0 여부이고, k=2의 이 구간 하단은 두 IC 중 작은 값이다. 그래서 이 표의 비겹침 결과는 보정 분모에 따라 달라지지 않는다.')
    OUT.write_text(report,encoding='utf-8')


def main():
    global ROOT, OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--reps', type=int, default=2000)
    parser.add_argument('--boot', type=int, default=20000)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--root', type=Path, help='Repository path when running a delivered copy elsewhere')
    parser.add_argument('--append-original', action='store_true', help='Append original synthetic benchmark to an existing REPLY; no DB reads')
    args = parser.parse_args()
    if args.root is not None:
        ROOT = args.root.resolve()
        OUT = ROOT/'research/handoff/REPLY_20261012_placebo_null.md'
    guard()
    assert args.reps >= 2000 and args.boot >= 4000
    if args.append_original:
        append_original(args)
        return
    begin = time.monotonic()
    env = verify()
    cases = [prepare(s) for s in SPECS]
    # Canonical gate/dedupe equivalence on exactly the same as-of input scope.
    for c, spec in zip(cases, SPECS):
        with ro(ROOT/'history.db') as conn:
            end = spec[4]
            # Bound canonical build_gates SELECTs without creating/writing tables.
            class BoundedPandas:
                def __getattr__(self, key):
                    return getattr(pd, key)

                def read_sql(self, sql, connection):
                    bounded = re.sub(r'FROM (stage1_oversold|v3_scores|lowvol_scores|wu_scores)',
                                     r'FROM (SELECT * FROM \1 WHERE run_id<=?)', sql)
                    return pd.read_sql_query(bounded, connection, params=(end,))
            env['pd'] = BoundedPandas()
            pa, db, _ = env['build_gates'](conn, [])
            assert pa == set(c['partial']) and db == set(c['double'])
            env['pd'] = pd
            scores = pd.read_sql_query(f'SELECT run_id FROM {spec[1]} WHERE model_id=? AND run_id BETWEEN ? AND ?',
                                      conn, params=(spec[0], spec[3], spec[4]))
        # Matching dates sufficient for anchor/dedupe, including holiday start.
        with ro(ROOT.parent/'dh-q7m3k-data'/'ohlcv.db') as pc:
            dates = [r[0] for r in pc.execute('SELECT DISTINCT date FROM daily_ohlcv WHERE date BETWEEN ? AND ? ORDER BY date', ('20260525', end))]
        di = {d:i for i,d in enumerate(dates)}
        assert set(c['kept']) == env['dedupe_by_anchor'](scores, di, set(c['partial'])|set(c['double']), reg=c['start'])
        print(c['mid'], 'OOS',c['oos'],'h20',len(c['rids']),c['rids'][0],c['rids'][-1],
              'nonoverlap',[c['rids'][i] for i in c['non']], 'cap',c['capcoverage'],
              'gates',c['partial'],c['double'], flush=True)
    if args.inspect:
        return
    sections = [
        '# 이미 판정한 창의 종목 이름표 자리바꿈 시험',
        '\n작성일 2026-10-11 KST · 파일명은 요청의 20261012를 유지. **실측**은 아래 고정 자료에 조건을 건 자리바꿈 실험이다. 실제 모델을 새로 판정하지 않는다.',
        '\n## 범위·계산 규약',
        '- v30 20260606~20260809, lv_b 20260625~20260829, sv_a 20260715~20260913의 점수만 SQL에서 읽었다. 시세도 각 판정일까지만 읽었다. 판정일 뒤 점수·수익의 순위 상관, v30 2차 창·lv_e·sv_b 성과는 계산하지 않았다. 루트 `VERDICT_202610*_v30*.md`는 열지 않았다.',
        '- DB 두 개를 `mode=ro`·`query_only=ON`으로 열었다. 외부 호출·수집기·배치 실행 없음. 운영 코드·docs·정본·worklog 수정 없음. 지정된 연구 코드와 이 보고서만 생성한다.',
        '- 각 시장에서 **창 안 모든 run의 합집합**을 1:1로 순열한다. 한 시도에서 source→recipient 이름표를 고정해 점수의 전체 흐름과 출현/결측 흐름을 함께 옮긴다. recipient가 그날 원래 점수 대상일 필요는 없다. 시장별 평균 IC에 동일한 가중치를 준다.',
        '- 전체: 시장만 제한. 출현5run: 시장×출현 run 수 1~5,6~10,… 안에서만 섞음(최대 차이 4run). 시총5분위: 시장×창 안 첫 유효 close×shares의 5분위 안에서만 섞음. 시총 결측은 별도 6번째 층. 이름표가 그대로인 경우도 허용하는 일반 순열이며, 그 비율을 기록한다.',
        '- h20, t+1 종가 진입→t+21 종가 청산. t+2~t+21 일간 등락률 최대 절댓값≤0.32. `pct_change(fill_method=None)`·시세 보충표 미사용. pairwise 결측 제거 **후** 동점 평균 순위. 시장별 8쌍 이상·점수/수익 고유값 각각 3개 이상. 살아 있는 시장 IC 평균→앵커 동일가중 평균. 게이트는 stage1 전체 과거 run의 행 수 중앙값×0.30, run×model 안 frozen_at 최대 차≥60분. 중앙값 자료도 판정일까지로 제한. 등록 필터→휴일 직전 앵커→중복 제거 순서.',
        f'- 자리바꿈 **각 모델×각 방식 {args.reps:,}회**, seed={SEED}+모델번호×100+방식번호. 각 시도의 날짜/주 부트스트랩 {args.boot:,}회, seed=7. 날짜는 앵커 n개 복원추출, 주는 실제 달력 주 블록 수만큼 복원추출 후 연결한 앵커 평균. 같은 n에는 같은 재표집 가중치 사용. 아래 유의는 **구간 하단>0**의 통계 조건을 뜻한다. 방향 포함은 주별 평균 IC>0인 주≥60%. 음의 유의·정성 관전 포인트·챌린저 채택/짝비교·보조지평은 이 비율에 포함하지 않는다.',
        '- Bonferroni는 날짜 구간의 0.025/분모 분위수 하단(양측 보정). 주·둘 다에도 같은 보정을 추가 병기했다. v30는 첫 정본 챌린저 분모6, 당시 v3 등록모델 7은 감도(챔피언 단독 유의에 정본이 별도 분모를 명시하지 않아 이 적용은 분석상 선택). lv_b는 판정 당시10. sv_a는 정본 사전등록11·당시 실측6 **둘 다**. 현재 분모로 바꾸지 않았다. `leaderboard.verdict`의 간이 하단0.02 문턱은 정본의 보정 구간과 달라 적용하지 않았다.',
        '- 비겹침은 완결 가능 앵커를 거래일순으로 두고 첫 앵커부터 앞서 고른 앵커와≥20거래일인 것만 선택. OOS40 자격은 원래 창에서 유지하고, CI/방향에 들어가는 앵커만 줄인다. k=1에도 기존 부트스트랩 규약을 그대로 적용해 점 구간이 된다(추가 최소 k 조건을 만들지 않음).',
        f'- 반복 비율의 95% Monte Carlo 오차는 50% 근처에서 최대 약 ±{100*1.96*np.sqrt(.25/args.reps):.2f}%p. 분포 백분위는 경험분포, p는 양의 관측값에 대한 우측 `(1+평균≥정본 숫자인 횟수)/(R+1)`이며 최솟값 {1/(args.reps+1):.6f}. 시총 층에서 평균이 0일 필요는 없다(종목 특성 일부 유지).',
        '\n## 정본의 실제 값(인용만; 재계산 안 함)',
        '- v30 **+0.1235**: `VERDICT_20260809.md` 각주④ 교정 후 값(n=23, 앵커≤20260710 **근사**); 같은 각주 교정 전 +0.1315. 본문은 리더보드 +0.148을 별도 언급한다. 현재 DB·판정일 가격 제한으로 만든 null과 각주의 n/게이트가 정확히 일치하는지 **확인 못 함**. 따라서 v30 백분위/p는 인용 숫자의 null 내 위치이며, 당시 원자료에 대한 엄밀한 동일통계량 검정으로 단정하지 않는다.',
        '- lv_b **+0.0687**: `VERDICT_20260829_lowvol.md` §1·각주④(n=22). sv_a **+0.0330**: `VERDICT_20260913_wu_sv_le.md` §1(n=20). 정본은 각각 기움·기움이다. 여기서 라벨을 다시 내리지 않는다.',
        '\n## 창과 앵커(실측)',
        table(['모델','점수 창','가격 끝','원 run','유효 OOS 앵커','h20 가능 앵커','범위','비겹침 앵커'],
              [[c['mid'],c['start']+'~'+c['end'],c['price_end'],c['raw_runs'],c['oos'],len(c['rids']),
                c['rids'][0]+'~'+c['rids'][-1],', '.join(c['rids'][i] for i in c['non'])] for c in cases]),
    ]
    summary = []
    for ci, c in enumerate(cases):
        rows, nonrows, distrows, lossrows, nrows = [], [], [], [], []
        for mi, method in enumerate(('전체','출현5run','시총5분위')):
            print(c['mid'],method,'permutations start',flush=True)
            x, loss = permutation(c, method, args.reps, SEED+ci*100+mi)
            st = stats(x, c['rids'], c['denoms'], args.boot)
            non = c['non']
            stn = stats(x[:, non], [c['rids'][i] for i in non], c['denoms'], args.boot)
            rows += rate_rows(method, st, c['denoms'])
            nonrows += rate_rows(method, stn, c['denoms'])
            distrows.append(distribution(method, st, c['actual']))
            lossrows.append([method,pct(loss['missing']),pct(loss['jump']),
                             pct(loss['missing']+loss['jump']),pct(loss['fixed']),
                             f"{loss['dropped'].min()}~{loss['dropped'].max()}",
                             f"{loss['one_market'].min()}~{loss['one_market'].max()}"])
            nrows.append([method,f"{st['n'].min()}~{st['n'].max()}",f"{stn['n'].min()}~{stn['n'].max()}"])
            summary.append([c['mid'],method,*[pct(st['flags'][(name,1)] & st['direction']) for name in ('date','week','both')],
                            pct(st['flags'][('date',c['denoms'][0])] & st['direction'])])
            print(c['mid'],method,'rates',summary[-1],flush=True)
        # Same synthetic process as prior work, but counts/times of THIS closed window.
        print(c['mid'],'synthetic q=.9 same closed shape',flush=True)
        fx = fake(c['counts'], c['times']-c['times'][0], args.reps, SEED+10000+ci)
        fs = stats(fx, c['rids'], c['denoms'], args.boot)
        fsn = stats(fx[:, c['non']], [c['rids'][i] for i in c['non']], c['denoms'], args.boot)
        rows += rate_rows('ガ짜q=.9(동일 창 모양)', fs, c['denoms'])
        nonrows += rate_rows('ガ짜q=.9(동일 창 모양)', fsn, c['denoms'])
        distrows.append(distribution('가짜q=.9(동일 창 모양)',fs,c['actual']))
        sections += ['\n## '+c['mid']+' — '+c['start']+'~'+c['end'],
                     f"게이트: 부분실행 {c['partial']}, 이중실행 {c['double']}. 앵커 날짜 SHA256 `{c['date_digest']}`.",
                     '\n### [1] 뒤섞은 점수의 양(+) 유의 비율(%) · [5] 가짜q=0.9 대조',
                     table(['방식','분모','구간','방향 제외','주 방향60% 포함'],rows),
                     '\n분모1=95%; 각 정본 분모>1 행=Bonferroni. `둘 다`는 해당 분모의 날짜·주 구간 하단이 모두 양수.',
                     '\n### [2] null 평균 IC 분포·SD / 날짜 부트스트랩 SE · [3] 정본 숫자의 위치',
                     table(['방식','2.5%','50%','97.5%','null 평균 SD','날짜 SE 중앙값','SD/SE 배수','실제 백분위','우측 p (초과/R)'],distrows),
                     '\nSD/SE는 자리바꿈한 평균의 시도간 SD ÷ 각 시도 날짜 부트스트랩 평균의 SD 중앙값. 전체 변동에 비해 날짜 구간이 얼마나 좁은지의 비교값이며, 시총 제한 등으로 남는 평균 이동은 별도다.',
                     '\n### 결측·점프컷·고정 이름표(실측; 비율 분모 명시)',
                     table(['방식','가격결측%','추가 점프컷%','총 제외%','이름표 그대로%','무시장 앵커/시도','한 시장만/시도'],lossrows),
                     '\n가격결측/점프컷은 h20 가능 앵커에 출현한 비결측 source 점수 행을 분모로 한 시도별 제외율의 평균. 가격결측에는 recipient가 시세 본 표에 없거나 진입/청산 종가가 없는 경우 포함. 점프컷은 가격결측과 중복 없이 계산. 이름표 그대로는 시장별 전체 종목 합집합을 분모로 한다.',
                     table(['방식','실제 IC 앵커 n 범위','비겹침 IC 앵커 k 범위'],nrows),
                     '\n### [4] h20 간격의 겹치지 않는 앵커에서 같은 조건(%)',
                     table(['방식','분모','구간','방향 제외','주 방향60% 포함'],nonrows),
                     '\n### 층과 시총 자료(실측)',
                     table(['시장','시총 있는 종목','합집합 종목'],c['capcoverage']),
                     table(['방식','시장','층 수','층 크기 최소~최대','혼자여서 안 바뀌는 종목'],
                           [[method,mk,len(z),f'{min(z)}~{max(z)}',sum(n == 1 for n in z)]
                            for method in ('전체','출현5run','시총5분위') for mk in sorted({r[2] for r in c['strata']})
                            if (z := [r[4] for r in c['strata'] if r[1] == method and r[2] == mk])]),
                     '\n가짜q=.9 대조는 가짜 독립 정규 일수익의 20일 합과 가짜 AR(1) 점수를 정확 순위로 계산한다(진짜 상관0). 시장별 원점수×시세 유효 행 수·실제 거래일 간격·달력 주를 이 창에 맞췄다. 원자료의 업종·종목 교체·점수 동점·두꺼운 꼬리를 보존하지 않는다. 시세는 실제 종가가 아니므로 점프컷을 적용하지 않는다. 실제 자리바꿈과 직접 같은 생성분포가 아니다.']
    sections += ['\n## 모델·창별 사실 요약(방향60% 포함, %)',
                 table(['모델','자리바꿈 방식','날짜95%','주95%','둘 다95%','날짜 Bonf(주 분모)'],summary),
                 '\n## [5] 이전 가짜자료 q=0.9 표와의 대조',
                 '앞선 `REPLY_20261011_verdict_power.md` 표2의 정확 가짜순위·T40·4,000회 값(인용)은 v3 날짜/주 **29.7/22.2%**, lowvol **29.6/21.6%**, wu **29.9/21.9%**(분모1·방향 포함). 분모7 날짜/주 v3 **23.6/17.2%**, lowvol **23.6/16.0%**, wu **24.3/16.6%**; 분모11 v3 **22.4/16.4%**, lowvol **22.6/15.4%**, wu **23.2/15.8%**。위 각 모델 표는 같은 가짜 자료 생성 원리를 해당 과거 창의 모양에 맞춰 모든 요청 칸을 다시 계산한 것으로, 이전 숫자의 누락 칸을 임의로 채운 것이 아니다. 이전 보고서에 없는 비겹침/SE/분모6·10/방향 제외 값은 당시 결과만으로 **확인 못 함**. 원래 T40·합성 20앵커와 실제 세 창의 n·주 구성·종목 수가 달라 숫자를 같은 실험의 재현으로 간주하지 않는다.',
                 '\n## 한계·확인 못 함',
                 '- **자리바꿈은 점수가 종목 특성(변동성·시총·업종)과 얽힌 부분도 끊는다. 그 특성이 수익과 관계가 있으면 실제 헛짚는 비율은 이 숫자와 다를 수 있다.** 시총 제한 감도는 시총 한 갈래만 일부 보존하며 변동성·업종은 통제하지 않는다. 시총은 첫 유효 관측일이 종목별로 달라 엄밀한 공통 기준일 시총 층은 아니다. 현재 주식수를 과거에 붙이지 않았다.',
                 '- 과거 창·현 DB의 수정된 종목코드·현 시세 저장값에 조건을 건 결과. 판정일 당시 DB 원본 스냅샷과 시세 수정 전 값은 **확인 못 함**. v30 각주 숫자와 null의 앵커 n가 다르면 정본 p의 엄밀한 동일표본 의미는 성립하지 않는다. lv_b·sv_a도 정본 IC를 재계산하지 않아 숫자 일치 자체는 **확인 못 함**.',
                 '- 시도마다 일부 이름표가 그대로 남으며 출현/시총 층은 교환 가능한 종목 집합을 줄인다. 따라서 실제 관계가 완전히 사라졌다고 증명하는 실험은 아니다. 특히 층별 수익 차이는 남을 수 있다. 합집합 순열은 recipient의 당일 원래 유니버스 소속을 요구하지 않아 점수의 출현 흐름은 source를 따르고 recipient의 원래 포함/배제 규칙은 보존하지 않는다.',
                 '- 단일 과거 시장창에 조건을 건 비율이다. 실제 효과0 모델 전체의 보편적인 오류율·새 모델 성능·미판정 창의 결과는 **확인 못 함**. 주 구간도 인접 주 사이 h20 겹침을 없애지 못한다. 비겹침 k가 작으면 기존 부트스트랩의 점 구간/불안정성이 그대로 나타난다.',
                 '- sv_a의 정성 경계/상승장 관전 조건은 수치화된 유의 판정식이 없어 이 실험에서 재현한 것은 명시된 통계 조건뿐이다. 전체 최종 라벨의 자동 재현은 **확인 못 함**. 새 판정 의견·규칙 변경 제안 없음.',
                 '\n## 검증·재현',
                 '- 가짜 입력에서 동점·pairwise 결측·최소8쌍/3고유값을 scipy Spearman과 대조. 운영 모듈 import 없이 AST에서 읽은 정본 anchor/dedupe 함수와 실제 허용 범위의 앵커 집합이 일치. 매 순열이 1:1인지 assert. 실제 원래 점수-수익 IC는 계산 안 함.',
                 f'- 재현: `python -B research/handoff/code_20261012_placebo_null.py --reps {args.reps} --boot {args.boot}`. 사전 범위 확인만: 같은 명령에 `--inspect`. 기본 쓰기 대상은 이 REPLY 한 파일뿐. 중간 대형 파일 없음. 실행시간 {time.monotonic()-begin:.1f}초.',
                 '- 주 결과의 원자료 경로: `history.db`, `../dh-q7m3k-data/ohlcv.db`의 `daily_ohlcv`. 정본 출처: `VERDICT_20260809.md`, `VERDICT_20260829_lowvol.md`, `VERDICT_20260913_wu_sv_le.md`; 규약 `leaderboard.py`, `research/verdict_blockboot_20260829.py`, `PROJECT_KNOWLEDGE.md` §11.']
    guard()
    OUT.write_text('\n\n'.join(sections).replace('ガ짜','가짜').replace('。','.'),encoding='utf-8')
    append_original(args)
    print('WROTE',OUT,'elapsed',round(time.monotonic()-begin,1),flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=2):
        main()
