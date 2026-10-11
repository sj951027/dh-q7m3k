"""Blind, local Monte Carlo; database SELECTs return counts only.

Run: python -B research/handoff/code_20261011_verdict_power.py
Only this script and REPLY_20261011_verdict_power.md are deliverables.
No project module imports, network, actual scores, prices or realized returns.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse
import sqlite3
import sys
import time

import numpy as np
from scipy.stats import rankdata, norm
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('REPLY_20261011_verdict_power.md')
SEED = 20261011
RHOS = (0., .01, .02, .03, .05)
DENOMS = (1, 7, 11)
LENGTHS = (40, 60, 80, 120)
Q_MAIN = .9


def guard():
    now = datetime.now(timezone(timedelta(hours=9)))
    if now.weekday() < 5 and (20, 10) <= (now.hour, now.minute) < (22, 30):
        raise SystemExit('평일 20:10~22:30 KST: 실행 중단')


def shapes():
    """Only grouped counts leave SQLite; no ticker, score or price SELECT."""
    guard()
    result = {}
    with sqlite3.connect((ROOT / 'history.db').resolve().as_uri() + '?mode=ro', uri=True) as c:
        c.execute('PRAGMA query_only=ON')
        specs = {
            'v3': ('stage3_final', '', ()),
            'lowvol': ('lowvol_scores', ' AND model_id=?', ('lv_b',)),
            'wu': ('wu_scores', ' AND model_id=?', ('sv_a',)),
            # Eligibility count only: same >=2 nonmissing factor rule, no ranking.
            'large': ('large_final', ' AND (coalesce(per>0,0)+coalesce(pbr>0,0)'
                      '+(rim_spread IS NOT NULL)+(div_yield IS NOT NULL))>=2', ()),
        }
        for label, (table, where, params) in specs.items():
            rows = c.execute(
                f'SELECT run_id,lower(market),count(*) FROM {table} '
                f'WHERE run_id BETWEEN ? AND ?{where} '
                'GROUP BY run_id,lower(market) ORDER BY run_id,lower(market)',
                ('20260914', '20261008') + params).fetchall()
            by_date = {}
            for date, market, count in rows:
                assert market in ('kospi', 'kosdaq')
                by_date.setdefault(date, {})[market] = count
            result[label] = (list(by_date), np.array([
                [d.get('kospi', 0), d.get('kosdaq', 0)] for d in by_date.values()], dtype=int))
    return result


def group_labels(counts, n):
    labels = []
    w = 0
    while len(labels) < n:
        labels.extend([w] * counts[w % len(counts)])
        w += 1
    return np.array(labels[:n])


def spearman_gaussian(r):
    return 6 / np.pi * np.arcsin(np.asarray(r) / 2)


def covariance(ns, times, h, q):
    """Local Gaussian approximation to finite-N, two-market mean Spearman.

    Null covariance of rank products: score rank persistence times return
    rank persistence, with nested stock pools and actual per-market counts.
    Each stock and each market is otherwise independent. Small alternatives
    translate this distribution; exact fake-panel checks quantify the error.
    """
    lag = np.abs(times[:, None] - times[None, :])
    temporal = spearman_gaussian(q ** lag) * spearman_gaussian(np.maximum(1 - lag / h, 0))
    cov = np.zeros_like(temporal)
    for m in range(2):
        n = ns[:, m] - 1
        cov += .25 * np.minimum(n[:, None], n[None, :]) / (n[:, None] * n[None, :])
    return cov * temporal


def weights(n, labels, b, seed):
    rng = np.random.default_rng(seed)
    iid = rng.multinomial(n, np.full(n, 1 / n), size=b).astype(np.float32) / n
    nw = int(labels.max()) + 1
    counts = np.bincount(labels)
    if nw == n:
        return iid, iid  # one weekly anchor per week: identical procedures
    picks = rng.multinomial(nw, np.full(nw, 1 / nw), size=b)
    block = (picks[:, labels] / (picks @ counts)[:, None]).astype(np.float32)
    assert np.allclose(iid.sum(axis=1), 1)
    assert np.allclose(block.sum(axis=1), 1)
    return iid, block


def direction_boundary(x, labels):
    weeks = np.column_stack([x[:, labels == w].mean(axis=1) for w in np.unique(labels)])
    need = int(np.ceil(.6 * weeks.shape[1]))
    return -np.sort(weeks, axis=1)[:, weeks.shape[1] - need]


def boundaries(x, labels, banks):
    direction = direction_boundary(x, labels)
    ci = []
    full = []
    qs = [.025 / d for d in DENOMS]
    previous = None
    for bank in banks:
        if bank is previous:
            ci.append(ci[-1].copy())
        else:
            boots = x.astype(np.float32) @ bank.T
            ci.append(-np.quantile(boots, qs, axis=1).T)
            del boots
        full.append(np.maximum(ci[-1], direction[:, None]))
        previous = bank
    return {'date': full[0], 'week': full[1], 'both': np.maximum(full[0], full[1]),
            'date_ci': ci[0], 'week_ci': ci[1]}


def sample_case(ns, times, h, q, labels, reps, b, seed):
    cov = covariance(ns, times, h, q)
    root = np.linalg.cholesky(cov + np.eye(len(ns)) * 1e-14)
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((reps, len(ns))) @ root.T
    banks = weights(len(ns), labels, b, seed + 1)
    bd = boundaries(x, labels, banks)
    return bd, cov, banks


def pct(a):
    return f'{100 * np.mean(a):.1f}'


def rates(bd, rho):
    return [pct(bd[s][:, j] < rho) for s in ('date', 'week') for j in range(3)]


def wilson(hits, n):
    p = hits / n
    z = 1.959963984540054
    center = (p + z*z/(2*n)) / (1+z*z/n)
    half = z * np.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1+z*z/n)
    return f'{100*(center-half):.1f}~{100*(center+half):.1f}'


def table(header, rows):
    return '\n'.join(['| ' + ' | '.join(header) + ' |',
                      '|' + '|'.join(['---'] * len(header)) + '|'] +
                     ['| ' + ' | '.join(map(str, row)) + ' |' for row in rows])


def exact_panels(ns, times, h, q, reps, rhos, seed):
    """All prices, returns and scores in this function are synthetic.

    Gaussian daily increments -> overlapping forward sums Y. AR(1) noise Z.
    X = r*Y + sqrt(1-r*r)*Z; r=2sin(pi*rho/6), hence population Spearman rho.
    Market ICs are calculated from exact ranks, then equally averaged.
    """
    rng = np.random.default_rng(seed)
    output = {rho: np.zeros((reps, len(ns))) for rho in rhos}
    for start in range(0, reps, 40):
        guard()
        count = min(40, reps-start)
        for market in range(2):
            pool = int(ns[:, market].max())
            daily = rng.standard_normal((count, pool, int(times[-1] + h)))
            acc = np.concatenate([np.zeros((count, pool, 1)), daily.cumsum(axis=2)], axis=2)
            y = (acc[:, :, times+h] - acc[:, :, times]) / np.sqrt(h)
            z = np.empty_like(y)
            z[:, :, 0] = rng.standard_normal((count, pool))
            for t in range(1, len(ns)):
                a = q ** int(times[t] - times[t-1])
                z[:, :, t] = a*z[:, :, t-1] + np.sqrt(1-a*a)*rng.standard_normal((count, pool))
            for t, n in enumerate(ns[:, market]):
                ry = rankdata(y[:, :n, t], axis=1) - (n+1)/2
                div = n*(n*n-1)/12
                for rho in rhos:
                    r = 2 * np.sin(np.pi*rho/6)
                    score = r*y[:, :n, t] + np.sqrt(1-r*r)*z[:, :n, t]
                    rx = rankdata(score, axis=1) - (n+1)/2
                    output[rho][start:start+count, t] += .5*(rx*ry).sum(axis=1)/div
    return output


def exact_pairs(ns, times, h, q, reps, seed):
    """Exact fake rank-IC differences; population score Spearman c and IC delta."""
    rng = np.random.default_rng(seed)
    settings = [(c, d) for c in (.9, .95, .99) for d in (.01, .02)]
    result = {s: np.zeros((reps, len(ns))) for s in settings}
    for start in range(0, reps, 40):
        guard()
        count = min(40, reps-start)
        for market in range(2):
            pool = int(ns[:, market].max())
            daily = rng.standard_normal((count, pool, int(times[-1]+h)))
            acc = np.concatenate([np.zeros((count,pool,1)), daily.cumsum(axis=2)], axis=2)
            y = (acc[:,:,times+h]-acc[:,:,times])/np.sqrt(h)
            za, zb = np.empty_like(y), np.empty_like(y)
            za[:,:,0] = rng.standard_normal((count,pool))
            zb[:,:,0] = rng.standard_normal((count,pool))
            for t in range(1,len(ns)):
                a = q**int(times[t]-times[t-1])
                za[:,:,t] = a*za[:,:,t-1]+np.sqrt(1-a*a)*rng.standard_normal((count,pool))
                zb[:,:,t] = a*zb[:,:,t-1]+np.sqrt(1-a*a)*rng.standard_normal((count,pool))
            for t,n in enumerate(ns[:,market]):
                ry = rankdata(y[:,:n,t],axis=1)-(n+1)/2
                ra = rankdata(za[:,:n,t],axis=1)-(n+1)/2
                div = n*(n*n-1)/12
                for c,d in settings:
                    rd = 2*np.sin(np.pi*d/6)
                    rc = 2*np.sin(np.pi*c/6)
                    noise_c = rc/np.sqrt(1-rd*rd)
                    assert noise_c < 1
                    score_b = rd*y[:,:n,t]+np.sqrt(1-rd*rd)*(
                        noise_c*za[:,:n,t]+np.sqrt(1-noise_c*noise_c)*zb[:,:n,t])
                    rb = rankdata(score_b,axis=1)-(n+1)/2
                    result[(c,d)][start:start+count,t] += .5*((rb-ra)*ry).sum(axis=1)/div
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reps', type=int, default=4000)
    parser.add_argument('--boot', type=int, default=6000)
    parser.add_argument('--exact-reps', type=int, default=1000)
    args = parser.parse_args()
    guard()
    begun = time.monotonic()
    empirical = shapes()
    dates = empirical['v3'][0]
    weeks = {}
    for date in dates:
        wk = datetime.strptime(date, '%Y%m%d').isocalendar()[:2]
        weeks[wk] = weeks.get(wk, 0) + 1
    week_counts = list(weeks.values())
    assert week_counts == [5, 3, 5, 3], week_counts
    cases = {}
    exact_main = {}
    power_rows, null_rows, mde_rows, pair_rows, sensitivity_rows = [], [], [], [], []
    shape_rows = []
    for ti, track in enumerate(('v3', 'lowvol', 'wu')):
        ds, raw = empirical[track]
        assert ds == dates
        totals = raw.sum(axis=1)
        shape_rows.append([track, len(ds), f'{totals.min()}~{totals.max()}', f'{totals.mean():.2f}',
                           f'{100*raw[:,0].sum()/raw.sum():.2f}%', '5·3·5·3'])
        ns100 = raw[np.arange(100) % len(raw)]
        print(f'정확 순위 본 실험 시작: {track}, {args.reps}회×100앵커×5효과', flush=True)
        true_panels = exact_panels(ns100, np.arange(100), 20, Q_MAIN, args.reps, RHOS, SEED+20000+ti)
        for length in LENGTHS:
            guard()
            n = length - 20  # elapsed T, entry lag1: anchors0..T-21 mature
            ns = raw[np.arange(n) % len(raw)]
            labels = group_labels(week_counts, n)
            seed = SEED + ti*1000 + length
            bd, cov, banks = sample_case(ns, np.arange(n), 20, Q_MAIN, labels,
                                         args.reps, args.boot, seed)
            cases[(track, length)] = (bd, cov, banks, ns, labels)
            exact_bds = {}
            for rho in RHOS:
                exact_bds[rho] = boundaries(true_panels[rho][:,:n], labels, banks)
                power_rows.append([track, length, n, int(labels.max()+1), f'{rho:.2f}', *rates(exact_bds[rho], 0)])
            exact_main[(track,length)] = exact_bds
            null_bd = exact_bds[0.]
            for s in ('date', 'week'):
                for j, den in enumerate(DENOMS):
                    hit = int((null_bd[s][:, j] < 0).sum())
                    hit_ci = int((null_bd[s+'_ci'][:, j] < 0).sum())
                    null_rows.append([track, length, s, den, f'{100*hit/args.reps:.1f}',
                                      wilson(hit, args.reps), '초과' if hit/args.reps > .05 else '이하',
                                      f'{100*hit_ci/args.reps:.1f}'])
            if length == 40:
                for j, den in enumerate(DENOMS):
                    mde_rows.append([track, den, *[f'{np.quantile(bd[s][:,j], .8):.4f}'
                                                   for s in ('date', 'week', 'both')]])
                pairs = exact_pairs(ns, np.arange(20), 20, Q_MAIN, args.reps, SEED+21000+ti)
                for (corr,delta), xp in pairs.items():
                    pairbd = boundaries(xp,labels,banks)
                    pair_rows.append([track,f'{corr:.2f}',f'{delta:.2f}',*rates(pairbd,0)])
            print(f'정확 순위 모의실험 완료: {track}, T={length}, n={n}', flush=True)
        del true_panels
        for q in (0., .5, 1.):
            bd0, _, _, ns, labels = cases[(track, 40)]
            bd, _, _ = sample_case(ns, np.arange(20), 20, q, labels, args.reps, args.boot,
                                   SEED+ti*1000+int(q*100)+900)
            for j, den in enumerate(DENOMS):
                sensitivity_rows.append([track, q, den, pct(bd['date'][:,j]<0), pct(bd['week'][:,j]<0),
                                         f'{np.quantile(bd["date"][:,j],.8):.4f}',
                                         f'{np.quantile(bd["week"][:,j],.8):.4f}'])
        bd = cases[(track, 40)][0]
        for j, den in enumerate(DENOMS):
            sensitivity_rows.append([track, Q_MAIN, den, pct(bd['date'][:,j]<0), pct(bd['week'][:,j]<0),
                                     f'{np.quantile(bd["date"][:,j],.8):.4f}',
                                     f'{np.quantile(bd["week"][:,j],.8):.4f}'])

    # Independent shorter exact panels validate the approximation used for continuous MDE.
    calibration_rows = []
    mde_check_rows = []
    exact_results = {}
    for ti, track in enumerate(('v3', 'lowvol', 'wu')):
        approx, cov, banks, ns, labels = cases[(track, 40)]
        panels = exact_panels(ns, np.arange(20), 20, Q_MAIN, args.exact_reps, RHOS, SEED+8000+ti)
        exact_results[track] = {}
        for rho, x in panels.items():
            bdx = boundaries(x, labels, banks)
            exact_results[track][rho] = bdx
            calibration_rows.append([track, f'{rho:.2f}', f'{x.mean():.4f}',
                                     *rates(bdx, 0),
                                     f'{100*np.mean(approx["date"][:,0]<rho):.1f}',
                                     f'{100*np.mean(approx["week"][:,0]<rho):.1f}'])
        targets = {(s,j):float(np.quantile(approx[s][:,j],.8))
                   for s in ('date','week','both') for j in range(3)}
        checks = exact_panels(ns,np.arange(20),20,Q_MAIN,args.exact_reps,
                              sorted(set(targets.values())),SEED+24000+ti)
        for (s,j),rho in targets.items():
            check = boundaries(checks[rho],labels,banks)
            hit = int((check[s][:,j]<0).sum())
            mde_check_rows.append([track,s,DENOMS[j],f'{rho:.4f}',
                                  f'{100*hit/args.exact_reps:.1f}',wilson(hit,args.exact_reps)])
        print(f'정확 순위 가짜 패널 확인 완료: {track}, {args.exact_reps}회×5효과', flush=True)

    # Large: first weekly anchor; empirical 5/3/5/3 holiday-week template repeated.
    ds, raw = empirical['large']
    totals = raw.sum(axis=1)
    shape_rows.append(['large 유효요인≥2', len(ds), f'{totals.min()}~{totals.max()}', f'{totals.mean():.2f}',
                       f'{100*raw[:,0].sum()/raw.sum():.2f}%', '주마다 첫 앵커 1개'])
    times = np.r_[0, np.cumsum((week_counts*2)[:7])]
    ns = raw[times % len(raw)]
    labels = np.arange(8)
    large_bd, large_cov, large_banks = sample_case(ns, times, 60, Q_MAIN, labels,
                                                 args.reps, args.boot, SEED+10000)
    large_exact = exact_panels(ns,times,60,Q_MAIN,args.reps,RHOS,SEED+22000)
    large_exact_bds = {rho:boundaries(x,labels,large_banks) for rho,x in large_exact.items()}
    large_rows = [[f'{rho:.2f}', *rates(large_exact_bds[rho], 0), '0.0'] for rho in RHOS]
    large_mde = [[den, *[f'{np.quantile(large_bd[s][:,j],.8):.4f}' for s in ('date','week')],
                  '없음(비겹침 1개)'] for j, den in enumerate(DENOMS)]
    large_sens = []
    for q in (0., .5, .9, 1.):
        bd = large_bd if q == .9 else sample_case(ns, times, 60, q, labels,
                      args.reps, args.boot, SEED+11000+int(q*100))[0]
        large_sens.append([q, *[pct(bd['date'][:,j]<0) for j in range(3)],
                           *[f'{np.quantile(bd["date"][:,j],.8):.4f}' for j in range(3)]])
    large_pair_rows = []
    for (corr,delta),x in exact_pairs(ns,times,60,Q_MAIN,args.reps,SEED+23000).items():
        pairbd = boundaries(x,labels,large_banks)
        large_pair_rows.append([f'{corr:.2f}',f'{delta:.2f}',*rates(pairbd,0),'0.0'])

    # Bank sensitivity: different outer and bootstrap seed, twice the bootstrap count.
    bd0, _, _, ns, labels = cases[('v3',40)]
    alt, _, _ = sample_case(ns, np.arange(20), 20, Q_MAIN, labels, args.reps, args.boot*2, SEED+12000)
    bank_rows = [[s, den, pct(bd0[s][:,j]<0), pct(alt[s][:,j]<0),
                  f'{np.quantile(bd0[s][:,j],.8):.4f}', f'{np.quantile(alt[s][:,j],.8):.4f}']
                 for s in ('date','week') for j,den in enumerate(DENOMS)]

    # Known-covariance null control: a diagnostic benchmark, not a rule proposal.
    oracle_rows = []
    for track in ('v3','lowvol','wu'):
        bd, cov, _, _, _ = cases[(track,40)]
        se = np.sqrt(cov.mean())
        oracle_rows.append([track, *[f'{(norm.ppf(1-.025/d)+norm.ppf(.8))*se:.4f}' for d in DENOMS]])

    header = ['트랙','OOS T','완결 앵커','주 수','진짜 ρ','날짜 /1','날짜 /7','날짜 /11','주 /1','주 /7','주 /11']
    mde_by_track = {t: [r for r in mde_rows if r[0] == t and r[1] == 1][0] for t in ('v3','lowvol','wu')}
    fpr = {t: [float(pct(exact_main[(t,40)][0.][s][:,0]<0)) for s in ('date','week')] for t in ('v3','lowvol','wu')}
    text = f'''# §11 판정 검정력: 눈가림 가짜 자료 모의실험

작성일: 2026-10-11. **실측**은 DB의 모양과 코드 규칙 확인뿐이다. 이하 검정력·잘못된 유의 비율·효과 크기는 모두 **가정하의 모의 추정**이며 실제 모델 성과가 아니다.

## 결론과 해석 범위

- 주 가정(가짜 점수 잡음의 하루 지속성 q=0.9)에서 OOS 40거래일·완결 h20 앵커 20개·분모 1일 때 80% 발견률 최소 진짜 상관의 **근사값**은 v3 모양 날짜/주 기준 {mde_by_track['v3'][2]}/{mde_by_track['v3'][3]}, lowvol 모양 {mde_by_track['lowvol'][2]}/{mde_by_track['lowvol'][3]}, wu 모양 {mde_by_track['wu'][2]}/{mde_by_track['wu'][3]}이다. 정확 가짜 순위로 이 효과를 심은 대조와 오차는 표 3-B. 각 트랙의 모양에 조건을 건 값이며 트랙·실제 모델의 성과 우열을 뜻하지 않는다. 분모 7·11과 두 구간 동시 통과는 표 3 참조.
- 같은 조건에서 진짜 상관 0의 잘못된 유의 비율(날짜/주)은 v3 {fpr['v3'][0]:.1f}/{fpr['v3'][1]:.1f}%, lowvol {fpr['lowvol'][0]:.1f}/{fpr['lowvol'][1]:.1f}%, wu {fpr['wu'][0]:.1f}/{fpr['wu'][1]:.1f}%다. **이 상태의 80% 발견률은 잘못된 유의가 통제된 검정의 80% 검정력과 구분해야 한다.**
- **결론이 뒤집히는 조건:** 점수가 매일 새로 뽑혀 q=0이면 수익창은 19/20 겹쳐도 **진짜ρ=0인 기준에서** IC의 시간 의존성이 사라진다. 반대로 고정에 가까운 점수·종목 구성에서는 주 하나씩 재표집해도 주 사이 의존성이 남는다. 실제 점수 지속성·종목 교체율은 눈가림 때문에 **확인 못 함**. 따라서 ‘현재 실제 모델의 잘못된 유의 비율’이나 단 하나의 실제 최소 효과 크기는 **확인 못 함**.
- 연속 8주 h60 앵커는 60거래일 안에 모두 들어가 비겹침 앵커가 1개다. 현재 `large_verdict.py`의 추가 게이트까지 적용하면 유의 발견률은 효과와 무관하게 **0%**다. 표 5는 통계 조건만의 발견률과 실제 추가 게이트를 구분한다.

## 실측: 모양과 규칙

`history.db`를 `mode=ro`·`query_only=ON`으로 열어 20260914~20261008의 `run_id, market, COUNT(*)`만 받았다. v3는 stage3 전체, lowvol은 lv_b, wu는 sv_a를 모양 대표로 택했다. ls_t1은 양수 PER/PBR 또는 비결측 RIM/배당 중 2개 이상인 **행 수**만 셌다. 실제 요인값·점수·종목 식별자·시세·모델 수익·모델 순위 상관은 Python으로 가져오지 않았다. 가격 완결성 필터 이후의 실제 종목 수는 **확인 못 함**.

{table(['모양','일간 앵커 수','앵커별 종목 수','평균 종목 수','KOSPI 행 비율','관측 주별 앵커 수'], shape_rows)}

시장 비율은 합산 행 수 기준이고 IC 통계량은 두 시장 IC의 **동일 가중 평균**이다(`leaderboard.py:199~212`). 아래는 재현에 사용한 앵커별 두 시장 종목 수이며 시장 비율·앵커 수 외 실제 자료를 담지 않는다.

{table(['run','v3 K/Q','lowvol K/Q','wu K/Q','large K/Q'], [[d]+[f'{empirical[t][1][i,0]}/{empirical[t][1][i,1]}' for t in ('v3','lowvol','wu','large')] for i,d in enumerate(dates)])}

규칙 근거와 차이:

1. `PROJECT_KNOWLEDGE.md:367~375`: OOS 40, h20, 원래 챌린저−챔피언 IC 차이의 날짜 재표집 구간, 주별 방향 ≥60%, Bonferroni. 본 요청의 단일 ρ 표는 평균 IC가 0보다 큰지의 실험이며, 원래 **짝비교**는 표 4로 분리했다. 보조 수익 방향·h10 재현 조건은 눈가림/요청 범위 때문에 모의 판정에 넣지 않았다. 전체 채택률과는 다르다.
2. `PREREGISTER_v30_w2.md:19~33`: 분모 7, 날짜와 주 블록 구간 **둘 다** 하단>0 및 주별 ≥60%. 표 1은 요청대로 각 구간을 따로, 표 3은 동시 통과도 제시한다.
3. `leaderboard.py:230~255`: 구현은 날짜 95% 구간·**앵커별** 양수 ≥60%, 분모>1이면 하단<0.02를 보류하는 방식이다. 실제 Bonferroni 분위수·주별 60%와 다르다. 아래 표를 현재 리더보드 라벨의 재현으로 읽으면 안 된다.
4. `research/verdict_v30_window2_prep_20260906.py:66~77`: 달력 주별 평균의 방향, 한 주 전체를 뽑아 연결한 행 평균의 백분위 구간. 아래 주 블록은 이 방식이며 가변 주 크기도 유지했다.
5. `leaderboard.py:54,191~192`, `large_verdict.py:71~93,130~140`: 진입 지연 1거래일, 완결 수익만 사용, 대형은 주별 첫 앵커·최소 8개·비겹침 계산 앵커≥2와 그 구간 하단>0을 추가 확인한다. 운영 분모는 대형 1이며 7·11은 가상 감도이다.

## 모의실험 정의와 가정 전체 목록

1. 실제 16앵커의 종목 수·시장 구성을 순서대로 반복한다. 이후 창의 실제 모양을 예측한 것이 아니다. 관측 주의 5·3·5·3앵커 배열도 반복한다. 휴일 모양을 반복하는 **가정**이며 미래 달력을 조회하지 않았다. T는 최초 앵커 이후 경과 거래일, 마지막 시점 인덱스 T: 진입 지연 1·h20에서 완결 앵커는 T−20개(40→20, 60→40, 80→60, 120→100). 처음 앵커까지 포함해 거래일을 세는 관례이면 각각 1개 줄어든다.
2. 매 거래일·종목별 가짜 수익 증분은 서로 독립인 정규변수, h일 가짜 수익은 그 합이다. 인접 h20 수익의 Pearson 상관은 정확히 19/20, 가짜 순위 수익의 상관은 Gaussian copula 변환값이다. 수익의 단위·퍼짐은 Spearman에 영향을 주지 않아 1로 정했다. 실제 가격의 분포·자기상관은 사용하거나 추정하지 않았다. 두꺼운 꼬리·지속적인 시장 국면은 **확인 못 함**.
3. 가짜 점수 잡음 Z는 정상 AR(1), 하루 잠재 정규 상관 q. 주 가정 0.9, 감도 0·0.5·1. 가짜 점수 지속성을 실제 점수 지속성으로 취급하지 않는다. 구성은 각 시장 고정 종목 풀의 앞 n개여서 인접 앵커의 교집합은 min(nₜ,nₛ). 실제 교집합·교체율은 읽지 않았다. **이 가정을 바꾸면 잘못된 유의 비율과 최소 효과 결론이 크게 바뀐다.**
4. 종목·두 시장은 서로 독립, 양 시장의 진짜 IC는 같은 ρ, 효과는 기간 내 고정이다. 가격 결측·거래정지·급등락 제외·점수 동점·산업별 묶음·효과 변동은 없다. 양 시장 모두 종목 쌍 8개 이상이다. 이러한 조건의 현실 충족은 **확인 못 함**. 동일 시장 내 독립 종목 수가 줄면 발견률이 낮아질 수 있다.
5. **표 1·2·4·5의 발견률은 가짜 종목별 점수와 수익의 정확한 순위를 계산**했다. 연속값 최소 효과(표 3)와 감도 표는 유한 종목 Spearman의 **국소 정규 근사**를 이용했다. 근사의 ρ=0 시장별 분산은 1/(n−1), 평균 IC 분산은 두 시장 분산 합/4. 시간 공분산은 종목 교집합 계수 × 점수 순위 지속성 × 수익 순위 지속성. 정규 상관 c의 순위 상관은 6/π·asin(c/2). 작은 효과는 null IC에 ρ를 더한다. **큰 효과까지 정확한 보장이 없으며**, 표 3-B·6에서 정확 가짜 순위와 대조한다.
6. 정확 가짜 패널은 Y=겹치는 h일 정규합, X=rY+√(1−r²)Z, r=2sin(πρ/6)로 생성하여 모집단 Spearman을 지정 ρ로 심었다. 실제 미래 수익을 사용하지 않는다. 작은 표본의 표본 Spearman 평균은 모수와 조금 다를 수 있다. 이 가짜 효과는 시간 내내 같은 국면에 유지된다고 가정한다. 효과가 양수일 때 X의 지속성은 잡음 q뿐 아니라 Y도 반영하므로 근사의 단순 이동과 약간 다르다.
7. ‘유의’는 (선택한 방식의 재표집 평균 구간 하단>0) AND (주별 평균 IC 양수인 주 비율≥60%). 양측 구간의 아래 꼬리는 0.025/분모. 따라서 독립·정상 근사에서 **양의 방향 한 건**의 명목 잘못된 유의는 최대 2.5/분모%, 5/분모%는 양방향 전체다. 표의 5% 비교는 요청대로 병기했다. 분모 1·7·11은 동일 한 건의 기준만 바꾸며 가족 전체 오류율이 아니다. 여러 모델 간 의존성을 확인하지 않아 실제 가족 전체 오류율은 **확인 못 함**.
8. 주 블록은 독립인 주를 가정하는 **주 하나씩의 비중첩 재표집**이다. 20일 또는 60일 길이의 이동 블록과 다르다. 두 구간 동시 통과는 유의 확률의 교집합이지 독립 확률의 곱이 아니다. 주별60%의 필요 양수 주 수는 ceil(0.6×관측 주 수), 경계는 엄격히 >0이다.
9. 짝비교는 공통 종목·날짜, 진짜 IC A=0, B=차이, 점수끼리의 **가짜 Spearman** c=0.9/0.95/0.99. A=Zₐ, B=rΔY+√(1−rΔ²)·(cₙZₐ+√(1−cₙ²)Zᵦ), cₙ=2sin(πc/6)/√(1−rΔ²)로 가짜 점수를 생성하고 각각 정확한 순위를 계산한다. 두 잡음은 같은 q의 독립 AR(1)이다. 실제 모델 간 상관·기준 모델 IC는 읽지 않았다. 양의 큰 기준 IC, 서로 다른 유니버스·결측·시간 지속성에서는 이 결과를 보장하지 못한다. 표 4의 주별 방향은 두 모델 IC **차이**의 주별 방향이다.
10. 대형은 h60이 **이미 완결된** 연속 8주 첫 앵커이다. 관측 5·3·5·3 배열 반복 시 거래일 위치는 {times.tolist()}, 마지막 앵커 완결은 최초 앵커 이후 {int(times[-1])+61}거래일, 휴일 없는 5일 주이면 96거래일이다. 같은 8개를 각자 날짜로 뽑거나 한 주 블록으로 뽑는 것은 같아 두 열은 정확히 일치한다. 실제 운영 추가 게이트의 0% 결론은 **연속 8주**에 한정하며, 60거래일 이상 떨어진 주가 포함되면 바뀐다.
11. 본 모의실험 {args.reps:,}회, 재표집 {args.boot:,}회, 독립 정확 순위 대조 {args.exact_reps:,}회/모양/효과, 고정 seed {SEED}. 같은 경우의 효과·분모·짝비교는 공통 난수를 재사용한다. 각 경우 모든 바깥 반복에 공통인 재표집 가중치 묶음을 사용한다. 바깥 반복의 이항 95% 오차는 최대 약 ±{100*1.96*.5/np.sqrt(args.reps):.2f}%p, 독립 정확 순위 대조는 ±{100*1.96*.5/np.sqrt(args.exact_reps):.2f}%p. 이는 모형 불확실성·공통 재표집 묶음의 근사 오차를 포함하지 않는다. 분모11 아래 꼬리는 재표집 평균 {args.boot*.025/11:.1f}개에 해당하여 불안정할 수 있어 다른 seed·재표집 2배 대조를 표 7에 제시한다.
12. 판정 시점은 한 번으로 고정한다. 40일 이후 매일 반복해서 유의한 날을 고르거나 여러 창·기간·효과를 탐색한 뒤 선택하는 오류는 모의실험에 포함하지 않았다. 매일 재판정하면 누적 오류율이 더 높아질 수 있다. 본 표는 그러한 순차 판정의 오류 통제를 주장하지 않는다.

## 표 1. 진짜 상관 × OOS 창: 유의 발견률(%)

주 가정 q=0.9, **가짜 종목별 점수·수익의 정확 순위** 사용. 각 열 모두 주별 방향≥60%를 함께 요구. `/m`은 Bonferroni 분모. 완결 전 앵커는 사용하지 않았다.

{table(header, power_rows)}

## 표 2. 진짜 상관 0: 잘못된 유의 비율(%)

‘구간만’은 방향60%를 생략한 비율로 구간 자체의 과신 여부를 확인한다. 날짜·주 두 방식 모두 주변 자료가 강하게 겹치면 표본 평균의 변동을 과소평가할 수 있다. Wilson 구간은 바깥 반복의 이항 불확실성만 표시한다.

분모7·11의 ‘5% 이하’는 **한 건의 비율**을 비교한 표시일 뿐 가족 전체 오류가 5% 이하라는 뜻이 아니다. 한 건부터 5%를 넘으면 전체 오류도 5%를 넘는다. 전체 오류를 계산하려면 가짜 검정 간 의존성도 추가로 정해야 하며, 실제 모델 간 의존성은 **확인 못 함**.

{table(['모양','T','구간','분모','유의 오류%','95% 모의 오차 구간','5%와 비교','구간만 오류%'], null_rows)}

## 표 3. 완결 앵커 20개: 80% 발견률 최소 진짜 상관

각 모의 null 패널을 상수만큼 이동시킬 때 통과하는 최소 효과의 80백분위. 0.01 간격 중 첫 통과를 찍은 값이 아니다. 국소 근사의 연속 효과값이며 소수 넷째 자리는 정확성을 뜻하지 않는다. 날짜·주 동시 통과도 같은 모의 패널에서 계산했다. **오류가 높으면 작은 최소 효과가 검정의 우수성을 뜻하지 않는다.**

{table(['모양','분모','날짜 기준','주 기준','둘 다 기준'], mde_rows)}

### 3-B. 위 근사 최소 효과를 실제로 심은 정확 가짜 순위 대조

같은 효과를 독립 가짜 패널에 심어 다시 순위를 계산한 발견률이다. 80% 부근의 모의 오차와 국소 근사의 편차를 드러낸다. 따라서 표 3의 값을 실제의 정확한 80% 경계라고 단정하지 않는다.

{table(['모양','기준','분모','심은 근사80%ρ','정확 발견률%','95% 모의 오차 구간'], mde_check_rows)}

비교용으로 **모의 공분산을 정확히 안다**고 가정하고 평균의 정규검정만 사용할 때(방향 조건 제외) 명목 오류를 맞춘 80% 최소 효과는 다음과 같다. 현재 규칙의 결과가 아니며, 재표집에서 누락한 의존성의 대가를 보여주는 참고치다.

{table(['모양','분모1','분모7','분모11'], oracle_rows)}

## 표 4. 40거래일 짝비교: 차이 발견률(%)

두 모델의 가짜 점수 상관 c만 바꾸었다. 같은 공통 표본에서의 차이이며 실제 모델 짝의 성과가 아니다. 기준 IC=0, 상대 IC=Δ. 분모·구간·방향 조건은 표 1과 같다.

{table(['모양','점수 상관 c','진짜 차이 Δ','날짜 /1','날짜 /7','날짜 /11','주 /1','주 /7','주 /11'], pair_rows)}

## 표 5. h60 완결 주간 앵커 8개: 같은 통계 조건

통계 조건만의 유의 발견률(%). 날짜와 주가 같은 이유는 각 주에 앵커가 하나뿐이기 때문이다. 마지막 열은 현재 대형 추가 비겹침 게이트까지 적용한 비율이며 운영 분모1이다.

{table(['진짜 ρ','날짜 /1','날짜 /7','날짜 /11','주 /1','주 /7','주 /11','운영 전체 유의%'], large_rows)}

{table(['분모','날짜80% 최소ρ','주80% 최소ρ','현재 전체 규칙80% 최소ρ'], large_mde)}

진짜ρ=0의 비율은 위 표 첫 행이다. 위 최소 효과 표와 아래 h60 점수 지속성 감도는 **국소 정규 근사**이며 통계 조건만 적용했다(날짜=주).

{table(['q','오류 /1%','오류 /7%','오류 /11%','80%ρ /1','80%ρ /7','80%ρ /11'], large_sens)}

h60 8개 짝비교도 같은 조건으로 계산했다. 두 번째 실제 모델은 존재한다고 가정한 것이며 ls_t1의 실제 비교 상대를 만든 것이 아니다.

{table(['가짜 점수 상관 c','차이 Δ','날짜 /1','날짜 /7','날짜 /11','주 /1','주 /7','주 /11','운영 전체 유의%'], large_pair_rows)}

## 표 6. 결론을 바꾸는 가정과 정확 가짜 순위 대조

### 6-A. h20 점수 지속성 감도(40거래일)

다음 감도 표는 **국소 정규 근사**다. q=0에서도 가짜 h20 수익은 19/20 겹친다. 표의 변화는 **점수/구성 지속성까지 알아야** 판정 오류를 설명할 수 있음을 보여준다. q=0에서도 주 기준 오류는 분모1에서 약 7~8%여서, 적은 주 수의 백분위 재표집 오차와 겹침으로 인한 오차를 구분해야 한다.

{table(['모양','q','분모','날짜 오류%','주 오류%','날짜80%ρ','주80%ρ'], sensitivity_rows)}

같은 근사 모형에서 분산을 4배(독립 정보가 약 1/4인 가상 묶음)로 두면 잡음과 모든 발견 임계값이 2배다. 따라서 표 3의 80% 최소 상관도 2배이고 ρ=0의 오류율은 그대로다. **결론 뒤집힘:** v3 모양·날짜·분모1에서 가짜 효과 0.05는 기본 가정의 80% 경계보다 크지만, 분산4배 가정의 경계보다 작다. 실제 묶음 구조는 **확인 못 함**. 이는 종목 수가 많다는 것만으로 작은 효과의 검출을 보장할 수 없다는 조건부 계산이다.

### 6-B. 정확한 가짜 점수·수익의 순위로 다시 계산(40거래일)

독립 대조에서도 각 효과의 **순위를 다시 계산**했다. ‘심은ρ’는 모집단 모수, ‘평균 표본IC’는 정확 가짜 패널 평균이다. 처음 6개 비율 열은 정확 가짜 패널의 유의 발견률, 끝 두 열은 표3에 사용한 국소 정규 근사 모형의 분모1 값이다. 표1·2·4·5의 발견률은 긴 창과 짝비교까지 정확 가짜 순위로 계산했다. 연속 최소 효과·감도에는 근사 오차가 남는다.

{table(['모양','심은ρ','평균 표본IC','정확 날짜/1','정확 날짜/7','정확 날짜/11','정확 주/1','정확 주/7','정확 주/11','근사 날짜/1','근사 주/1'], calibration_rows)}

정확 가짜 패널조차 실제 주가·실제 점수의 대조가 아니므로 실제 검정력 검증으로 확대하지 않는다. 표 4·5의 짝비교도 가짜 점수를 두 벌 생성하고 각각 순위를 계산했으며, 실제 모델 짝의 상관은 **확인 못 함**.

## 표 7. 재표집 묶음·난수 감도

v3 모양·T40·q0.9의 **국소 정규 근사 모형**: 기본 {args.boot:,}회 대 다른 바깥 seed·재표집 {args.boot*2:,}회. 기본 오류값은 표6-A의 근사값으로 표2의 정확 가짜 순위 값과 구분한다. 두 변화가 함께 들어 있어 차이를 재표집 횟수만의 효과로 해석하지 않는다.

{table(['구간','분모','기본 오류%','대조 오류%','기본80%ρ','대조80%ρ'], bank_rows)}

## 선택지와 대가(선택·규칙 변경 제안 없음)

| 선택지 | 얻는 것 | 대가·확인할 점 |
|---|---|---|
| 현재 날짜 재표집과 한 번의 판정 | 빠른 결과, 많은 앵커 행 | 지속적 점수와 겹치는 수익창에서는 오류가 명목보다 커질 수 있음; 표 2 조건부 |
| 날짜와 주 구간을 모두 확인 | 주 안의 겹침 일부 반영 | 주 사이 20/60일 겹침은 남음; 관측 주 수가 적고 발견률 낮아짐 |
| 창을 60·80·120으로 늘림 | 완결 앵커·주 수 증가(표 1) | 기다리는 기간 증가, 효과가 기간 내 고정이라는 가정 강화 |
| 수익창 길이에 맞춰 더 긴 묶음·비겹침을 확인 | 시간 의존성을 더 많이 보존 | 독립 묶음 수 감소; 20앵커만이면 h20 묶음은 사실상 한 개여서 재표집이 불안정 |
| 공통 표본의 짝비교 | 높은 점수 상관에서 공통 잡음 상쇄(표 4) | 같은 종목·날짜가 필요하고 작은 차이·유니버스 불일치에 민감; 실제 상관 확인 못 함 |
| 분모1·7·11을 사전 기준대로 유지 | 다중검정 기준 명시 | 분모가 커질수록 발견률 감소; 잘못된 시간 독립 가정을 Bonferroni만으로 해결하지 못함 |
| 대형의 현재 비겹침 추가 게이트 | 한 덩어리의 겹친 8주만으로 유의를 주지 않음 | 연속 8주 h60만으로는 효과가 있어도 유의가 0%; 더 떨어진 완결 앵커가 필요 |

## 재현·경계 확인

명령: `python -B research/handoff/code_20261011_verdict_power.py`.
numpy {np.__version__}; Python {sys.version.split()[0]}; 바깥 {args.reps:,}, bootstrap {args.boot:,}, 정확 순위 {args.exact_reps:,}; seed {SEED}. 계산 시간 {time.monotonic()-begun:.1f}초(환경에 따라 달라짐).

검증: 본 모의실험 정상 종료, 보고서의 창×효과 60행·오류72행·h20 짝비교18행·h60 효과5행 확인, 효과 증가/분모 증가에 따른 발견률 방향 확인, h60의 날짜/주 열 동일 및 추가 게이트0% 확인. 코드 구문 검사 통과. 연속 최소 효과의 정확 가짜 순위 대조는 표3-B.

코드는 이 보고서만 저장하고 중간 파일·DB 복제·캐시를 만들지 않는다. 운영 모듈을 import/실행하지 않고 모든 실제 DB SELECT는 집계된 모양만 반환한다. 수집기·배치·외부 호출·점수/판정/게이트 코드·docs·금지 판정문은 실행하거나 수정하지 않았다. 실제 모델의 상관·수익은 계산하지 않았다. 평일 20:10~22:30 KST에는 시작·각 계산 단계·저장 전에 중단하도록 검사한다.
'''
    guard()
    OUT.write_text(text, encoding='utf-8')
    print(f'저장 완료: {OUT.name}; {time.monotonic()-begun:.1f}초', flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    with threadpool_limits(limits=4):
        main()
