"""Offline decomposition requested in REQUEST_20261021_kosdaq_only_a.md.
Run: python -B research/handoff/code_20261021_kosdaq_only_a.py
Writes only the companion REPLY. Reuses prior independent pure helpers.
No collectors, network, model/score changes, extra OHLCV, or DB writes.
All definitions below are fixed before inspecting the results.
"""
from pathlib import Path
import hashlib
import json
import warnings
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from code_20261020_entry_regime_blind import (
    ROOT, guard, ro, extract, classify, count_separate, MonthBoot,
    nanmean, f, iv, valci, tab, B, SEED,
)

START, END = '20230626', '20261019'
OUT = Path(__file__).with_name('REPLY_20261021_kosdaq_only_a.md')


def run():
    guard()
    db = ROOT.parent / 'dh-q7m3k-data/ohlcv.db'
    before = (db.stat().st_size, db.stat().st_mtime_ns)
    with ro(db) as con:
        columns = {r[1] for r in con.execute('PRAGMA table_info(daily_ohlcv)')}
        assert {'date', 'ticker', 'close', 'volume', 'shares', 'market'} <= columns
        p = pd.read_sql_query(
            'SELECT date,ticker,close,volume,shares,market FROM daily_ohlcv '
            'WHERE date BETWEEN ? AND ? ORDER BY date,ticker', con, params=(START, END))
        ix = pd.read_sql_query(
            "SELECT date,series,close FROM market_daily WHERE series IN ('KOSPI','KOSDAQ') "
            'AND date<=? ORDER BY date,series', con, params=(END,))
    con.close()
    guard()
    dates = pd.Index(sorted(p.date.unique()))
    ticks = pd.Index(sorted(p.ticker.unique()))
    T, N = len(dates), len(ticks)
    assert not p.duplicated(['date', 'ticker']).any()

    def panel(col):
        return p.pivot(index='date', columns='ticker', values=col).reindex(index=dates, columns=ticks)

    C = panel('close').astype(float).where(lambda x: x > 0)
    c = C.to_numpy()
    volume = panel('volume').to_numpy(float)
    shares = panel('shares').to_numpy(float)
    market = panel('market').to_numpy()
    live = np.isfinite(c)
    R20 = (C / C.shift(20) - 1).to_numpy() * 100
    R40 = np.full_like(c, np.nan)
    valid40 = live[:-41] & live[1:-40] & live[41:]
    R40[:-41] = np.where(valid40, (c[41:] / c[1:-40] - 1) * 100, np.nan)
    y = nanmean(R40, axis=1)
    indices = ix.pivot(index='date', columns='series', values='close').sort_index()
    assert set(dates) == set(indices.index[indices.index >= START])
    r20 = {k: indices[k].pct_change(20, fill_method=None).reindex(dates).to_numpy()
           for k in ['KOSPI', 'KOSDAQ']}
    cats = {k: classify(v) for k, v in r20.items()}
    op = extract('regime_ad.py', ['cell_of'], {'TH_DOWN': -.05, 'TH_UP': .05})['cell_of']
    assert all((op(v) or '?') == cat for k in cats for v, cat in zip(r20[k], cats[k]))
    mature = np.isfinite(y) & (cats['KOSPI'] != '?') & (cats['KOSDAQ'] != '?')
    ka, qa = cats['KOSPI'] == 'A', cats['KOSDAQ'] == 'A'
    groups = {'K+Q': mature & ka & qa, 'K만': mature & ka & ~qa,
              'Q만': mature & ~ka & qa, '비교 기준': mature & ~(ka & qa)}
    ref = groups['비교 기준']
    qonly = groups['Q만']
    boot = MonthBoot(dates)

    def mask(x, g):
        return np.asarray(g, bool) & np.isfinite(x)

    def ns(x, g):
        m = mask(x, g)
        return f'{m.sum()} ({count_separate(np.flatnonzero(m), 40)})'

    def estimate(x, g):
        m = mask(x, g)
        return valci(nanmean(np.asarray(x)[m]), boot.means(x, m))

    def difference(x, a, b):
        ma, mb = mask(x, a), mask(x, b)
        z = boot.means(x, ma) - boot.means(x, mb)
        return valci(nanmean(np.asarray(x)[ma]) - nanmean(np.asarray(x)[mb]), z)

    def boot_n(x, a, b):
        return int(np.isfinite(boot.means(x, mask(x,a))-boot.means(x,mask(x,b))).sum())

    def extent(g):
        ds = dates[g]
        return f'{ds[0]}~{ds[-1]}' if len(ds) else '없음'

    def count_range(arr, g):
        n = np.isfinite(arr[g]).sum(axis=1)
        return f'{n.min()}~{n.max()}; {n.sum():,}' if len(n) else '0; 0'

    # Fixed features available on t. Ratios never use future endpoint availability.
    amount = np.where(live & np.isfinite(volume) & (volume >= 0), c * volume, np.nan)
    total_amount = np.nansum(amount, axis=1)
    amount20 = pd.Series(total_amount).rolling(20, min_periods=20).mean().to_numpy()
    amount_ratio = np.divide(total_amount, amount20, out=np.full(T, np.nan), where=amount20 > 0)
    dd = {k: (indices[k] / indices[k].rolling(60, min_periods=60).max() - 1)
          .reindex(dates).to_numpy() * 100 for k in r20}
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        q20 = np.nanquantile(R20, .2, axis=1)
    bottom = (R20 <= q20[:, None]) & np.isfinite(R20)
    bottom_ratio = bottom.sum(axis=1) / live.sum(axis=1) * 100
    bottom_ratio[np.isfinite(R20).sum(axis=1) == 0] = np.nan
    ma20 = C.rolling(20, min_periods=20).mean().to_numpy()
    breadth_valid = live & np.isfinite(ma20)
    breadth_den = breadth_valid.sum(axis=1)
    breadth = np.divide(((c < ma20) & breadth_valid).sum(axis=1) * 100,
                        breadth_den, out=np.full(T, np.nan), where=breadth_den > 0)
    cap = np.where(live & np.isfinite(shares) & (shares > 0), c * shares, np.nan)
    # One cross-market cap ranking per t, THEN intersect with market. Ties use average rank.
    ranks = pd.DataFrame(cap).rank(axis=1, method='average', pct=True).to_numpy()
    quintile = np.where(np.isfinite(ranks), np.ceil(ranks * 5), 0).astype(np.int8)
    sector_path = ROOT / 'sector_cache.json'
    sector_bytes = sector_path.read_bytes()
    sector_map = json.loads(sector_bytes.decode('utf-8-sig'))
    sectors = np.array([sector_map.get(t, '미분류') or '미분류' for t in ticks])
    known = sectors != '미분류'
    missing_key = np.array([t not in sector_map for t in ticks])

    # Validate the prior result before decomposing it. Do not alter input to match it.
    for g, expected_n, rounded_mean in [('K+Q', 64, 7.27), ('K만', 19, 5.14), ('Q만', 103, -.63)]:
        assert groups[g].sum() == expected_n, (g, groups[g].sum())
        assert abs(nanmean(y[groups[g]]) - rounded_mean) < .005, (g, nanmean(y[groups[g]]))
    rng = np.random.default_rng(20261021)
    tt, ss = np.where(np.isfinite(R40))
    for j in rng.choice(len(tt), 50, replace=False):
        t, s = tt[j], ss[j]
        assert np.isclose(R40[t, s], (c[t+41, s] / c[t+1, s] - 1) * 100)
    for t in rng.choice(np.flatnonzero(qonly), 20, replace=False):
        assert np.isclose(amount_ratio[t], total_amount[t] / total_amount[t-19:t+1].mean())
        ids = np.flatnonzero(breadth_valid[t])
        assert np.isclose(breadth[t], np.mean(c[t, ids] < np.mean(c[t-19:t+1, ids], axis=0)) * 100)
        # Truncating at t leaves every signal and classification unchanged.
        assert np.allclose(ma20[t], C.iloc[:t+1].rolling(20, min_periods=20).mean().iloc[-1], equal_nan=True)
    for b in range(3):
        direct = np.repeat(y[qonly], boot.w[b, boot.mi[qonly]])
        assert np.isclose(direct.mean(), boot.means(y, qonly)[b])

    sec = ['# REPLY — 코스닥만 급락인 날의 전 종목 바스켓 분해 (2026-10-21)',
           '## 0. 범위·고정 정의·자료 한계',
           '- **사후 탐색이며 규칙 채택·판정이 아니다.** 운영·점수·판정·게이트·docs는 수정하지 않았다. '
           '금지된 Claude 연구·게이트 초안·모의 계좌 설계 파일은 열지 않았다. 다만 필수 최신 worklog에는 해당 연구 요약이 있어 노출됐다. '
           '따라서 완전한 눈가림은 아니다. 요청에 정해진 문턱과 아래 집계 정의를 결과 확인 전에 고정했다.',
           f'- 실측 입력: daily_ohlcv {len(p):,}행, {N:,}종목, {T} 로컬 거래일({START}~{END}). '
           '이전 답을 재현하기 위해 종료일을 20261019로 고정했다. daily_ohlcv_extra·history.db·PTW는 사용하지 않았다. '
           '지수는 같은 DB의 market_daily이며 R20·60일 고점에는 시작일 이전 지수도 썼다.',
           '- 매수 t+1 종가, 매도 t+41 종가. t에 가격이 있는 종목의 수익을 날짜별 동일가중하고 그 날짜 평균을 다시 동일가중했다. '
           '모든 수익은 비용 전 %. 점프·거래정지 필터 없음. 미래 가격 누락은 수익 계산에서만 제외하며 특징·종목군은 t까지 자료로 정한다. '
           '이 때문에 특징 분모와 수익 분모가 조금 다르다. 배당·실거래 체결·외부 달력은 확인 못 함.',
           '- A는 regime_ad.py 그대로 R20≤−5%. K+Q=두 시장 A, K만=코스피만 A, Q만=코스닥만 A. '
           '**비교 기준은 요청의 “둘 다 A 아님”을 문자 그대로 NOT(K A AND Q A)로 해석했다.** '
           '따라서 K만·Q만이 비교 기준에 포함된다. “두 시장 모두 비A”와 다르며 차이는 독립 두 집단 비교가 아니다. '
           '그날 모양에는 Q만−K+Q와 Q만−K만 차이도 별도 행으로 붙였다.',
           f'- [ ]는 월 블록 {B:,}회 seed {SEED}의 95% 구간. 원 날짜축 {len(boot.months)}개월을 동일한 추출로 모든 집합에 적용한다. '
           'n(비겹침)은 유효 신호일 수와 시간순 최소 40거래일 간격으로 고른 수이며 경제적으로 독립인 사건 수는 아니다. '
           '빈 집합이 생긴 반복은 그 통계에서 제외한다. 월을 넘는 40일 수익 겹침과 여러 비교를 보정하지 않은 탐색 구간이다.',
           '- 시총=DB 해당 날짜 close×shares. 수집기 코드상 shares는 적재 시점 마스터 주식수를 기록하는 근사값이며 '
           '과거 최초 적재 때 당시 주식수였는지는 확인 못 함. 가격도 나중 수정주가 재조정 가능성이 있어 완전한 당시자료 재현을 보장하지 않는다. '
           '업종은 현재 sector_cache.json의 고정 분류로 과거 날짜에 붙였다. 업종 이력·당시 분류는 확인 못 함. '
           '따라서 업종 분해는 설명용이고 t 시점에 알 수 있었던 예측변수라는 증거가 아니다.']

    intro = []
    for g, m in groups.items():
        intro.append([g, extent(m), ns(y, m), len(set(boot.labels[m])), estimate(y, m),
                      difference(y, m, ref) if g != '비교 기준' else '—', count_range(R40, m)])
    sec += [tab(['날짜 집합', '신호일 범위', 'n(비겹침)', '관측월', '40일 평균 [95%]',
                 '비교 기준 대비 %p [95%]', '날별 종목 n; 종목×날 n'], intro)]
    print('BASE', intro, flush=True)

    guard()
    sec += ['## 1. 그날의 모양',
            '- 거래대금 비율=전 종목 close×volume 합(t) / 그 합의 직전 20일 평균(t 포함). 개별 비율의 평균이 아니다. '
            '60일 고점 낙폭은 각 지수의 t 포함 60일 최고 종가 대비다. 두 지수 모두 표시한다. '
            '하위20% 비율은 t의 유효 R20 횡단면 20% 분위값 이하 종목 수 / t의 가격 있는 전체 종목 수이며 동률을 포함한다. '
            '**정의상 약 20%로 고정되는 지표**라 하락의 확산 정도를 재지 못한다. 수익률≤−20% 등 다른 문턱으로 바꾸지 않았다. '
            '새 상장·과거가격 결측으로 분모 차이가 생기므로 R20 자료 비율도 함께 적었다.']
    feats = {'코스닥 R20 %': r20['KOSDAQ']*100, '코스피 R20 %': r20['KOSPI']*100,
             'R20 하위20% 종목 비율 %': bottom_ratio, 'R20 유효자료 비율 %': np.isfinite(R20).sum(axis=1)/live.sum(axis=1)*100,
             '거래대금 / 20일 평균 (배)': amount_ratio, '코스닥 60일 고점 낙폭 %': dd['KOSDAQ'],
             '코스피 60일 고점 낙폭 %': dd['KOSPI']}
    shape = []
    for name, x in feats.items():
        for g, m in groups.items():
            shape.append([name, g, ns(x, m), estimate(x, m),
                          difference(x, m, ref) if g != '비교 기준' else '—'])
        for g in ['K+Q', 'K만']:
            shape.append([name, f'Q만−{g}', f'{ns(x,qonly)} / {ns(x,groups[g])}', '—', difference(x,qonly,groups[g])])
    sec += [tab(['변수', '집합/차이', 'n(비겹침)', '평균 [95%]', '기준 대비 차이 또는 명시한 집합차 [95%]'], shape),
            f'- 실측: Q만의 코스피 R20은 {estimate(feats["코스피 R20 %"],qonly)}%, n(비겹침)={ns(y,qonly)}. '
            f'Q만−K+Q 코스피 R20 차이는 {difference(feats["코스피 R20 %"],qonly,groups["K+Q"])}%p다. '
            '그 차이는 집합 정의에도 들어 있으므로 독립적인 원인 발견으로 해석하지 않는다.',
            f'- 실측: Q만의 거래대금 비율은 {estimate(amount_ratio,qonly)}배, 코스닥 고점 낙폭은 {estimate(dd["KOSDAQ"],qonly)}%, '
            f'각 n(비겹침)={ns(amount_ratio,qonly)}/{ns(dd["KOSDAQ"],qonly)}. 하위20% 비율은 군 구성상 거의 고정되어 §6의 20일선 아래 비율로 확산 정도를 따로 본다.']

    guard()
    sec += ['## 2. 누가 떨어졌나 — 같은 시총 경계 × 종목시장',
            '- 매일 t의 두 시장 전체 시총을 합쳐 5분위(1=작음, 5=큼)를 정한 뒤 코스피/코스닥 종목으로 나눈다. '
            '시장마다 새 5분위를 만들지 않았다. 동률은 평균 순위이며 시총 결측은 별도 분류불가다. '
            '과거 R20=종목 close(t)/close(t−20)−1, 이후 R40=close(t+41)/close(t+1)−1. '
            '시총군은 t에 고정하며 보유 중 바꾸지 않는다. 아래 n은 R20/R40 순서다.']
    cells = []
    cell_results = {}
    decomposition = np.zeros(T)
    for mk in ['KOSPI', 'KOSDAQ']:
        for q in range(1,6):
            pick = (market == mk) & (quintile == q)
            past = np.where(pick, R20, np.nan)
            future = np.where(pick, R40, np.nan)
            a, z = nanmean(past, axis=1), nanmean(future, axis=1)
            contrib = np.divide(np.nansum(future,axis=1),np.isfinite(R40).sum(axis=1),
                                out=np.full(T,np.nan),where=np.isfinite(R40).sum(axis=1)>0)
            decomposition += np.nan_to_num(contrib)
            cell_results[mk,q] = (z,contrib)
            for g,m in groups.items():
                cells.append([g,mk,q,f'{ns(a,m)} / {ns(z,m)}',count_range(past,m),count_range(future,m),
                              estimate(a,m),estimate(z,m),difference(z,m,ref) if g!='비교 기준' else '—',
                              estimate(contrib,m)])
    unclassified = live & ((quintile == 0) | ~np.isin(market,['KOSPI','KOSDAQ']))
    remainder = np.divide(np.nansum(np.where(unclassified,R40,np.nan),axis=1),np.isfinite(R40).sum(axis=1),
                          out=np.full(T,np.nan),where=np.isfinite(R40).sum(axis=1)>0)
    assert np.allclose((decomposition+np.nan_to_num(remainder))[mature],y[mature],atol=1e-10)
    sec += [tab(['집합','종목시장','시총분위','날 n(비겹침) 과거 / 이후','과거 종목 n범위; 합',
                 '이후 종목 n범위; 합','과거20일 % [95%]','이후40일 % [95%]','이후−기준 %p [95%]',
                 '전종목 이후수익 기여 %p [95%]'],cells)]
    neg_cells = [(mk,q) for (mk,q),(z,_) in cell_results.items() if nanmean(z[qonly])<0]
    cell_text = ', '.join(f'{mk} {q}분위 {estimate(cell_results[mk,q][0],qonly)}%' for mk,q in neg_cells)
    qmarket = {mk:nanmean(np.where(market==mk,R40,np.nan),axis=1) for mk in ['KOSPI','KOSDAQ']}
    sec += [f'- 실측: Q만에서 40일 평균이 음수인 칸은 10칸 중 {len(neg_cells)}칸이다: {cell_text}. '
            f'각 날 n(비겹침)={ns(y,qonly)}이며 각 구간이 0을 지나는지는 표와 구별해서 읽는다.',
            f'- 실측: Q만 날의 코스피 종목 전체는 {estimate(qmarket["KOSPI"],qonly)}%, 코스닥 종목 전체는 '
            f'{estimate(qmarket["KOSDAQ"],qonly)}%, 각각 n(비겹침)={ns(qmarket["KOSPI"],qonly)}/{ns(qmarket["KOSDAQ"],qonly)}. '
            f'시총/시장 분류불가 종목×날은 세 A 집합 합계 {int(unclassified[groups["K+Q"]|groups["K만"]|qonly].sum()):,}건이다.']
    print('CELLS QONLY',[(mk,q,estimate(z,qonly),estimate(co,qonly)) for (mk,q),(z,co) in cell_results.items()],flush=True)

    guard()
    sec += ['## 3. 업종 — Q만 날짜의 하락 기여 상위 5개',
            '- 업종별 하락 기여=그 업종의 종목 R20 합 / 그날 전체 유효 R20 종목 수. '
            'Q만 날짜 평균 기여가 가장 음수인 분류된 업종 5개를 순서대로 뽑았다. 종목 수가 많은 업종의 영향도 포함하며 '
            '지수의 시가총액 가중 기여가 아니다. 양의 종목도 합산한 순기여다. 미분류는 순위에서 빼되 별도 행으로 보존한다. '
            '이후 기여도는 같은 방식으로 전체 유효 R40 종목 수를 분모로 한다. 비중은 R20 유효 종목 기준이다.']
    den20,den40=np.isfinite(R20).sum(axis=1),np.isfinite(R40).sum(axis=1)

    def sector_stats(pick):
        a=np.where(pick[None,:],R20,np.nan)
        z=np.where(pick[None,:],R40,np.nan)
        co=np.divide(np.nansum(a,axis=1),den20,out=np.full(T,np.nan),where=den20>0)
        cz=np.divide(np.nansum(z,axis=1),den40,out=np.full(T,np.nan),where=den40>0)
        weight=np.divide(np.isfinite(a).sum(axis=1)*100,den20,out=np.full(T,np.nan),where=den20>0)
        return a,z,co,cz,weight

    ranking=[]
    for s in sorted(set(sectors[known])):
        data=sector_stats(sectors==s)
        ranking.append((nanmean(data[2][qonly]),s))
    top=[s for _,s in sorted(ranking)[:5]]
    picks=[(s,sectors==s) for s in top]+[('나머지 분류 업종',known&~np.isin(sectors,top)),
                                       ('미분류',~known),('전체',np.ones(N,bool))]
    srows=[];sector_decomp20=np.zeros(T);sector_decomp40=np.zeros(T)
    for s,pick in picks:
        a,z,co,cz,weight=sector_stats(pick)
        if s!='전체':
            sector_decomp20+=np.nan_to_num(co);sector_decomp40+=np.nan_to_num(cz)
        srows.append([s,ns(nanmean(z,axis=1),qonly),count_range(a,qonly)+' / '+count_range(z,qonly),
                      estimate(weight,qonly),estimate(co,qonly),estimate(nanmean(a,axis=1),qonly),
                      estimate(nanmean(z,axis=1),qonly),estimate(cz,qonly)])
    assert np.allclose(sector_decomp20[qonly],nanmean(R20,axis=1)[qonly],atol=1e-10)
    assert np.allclose(sector_decomp40[qonly],y[qonly],atol=1e-10)
    absent_weight=sector_stats(missing_key)[4]
    unknown_weight=sector_stats(~known)[4]
    sec += [tab(['업종','n(비겹침)','종목 n범위; 합 (과거 / 이후)','종목비중 % [95%]',
                 '20일 하락 순기여 %p [95%]','업종 과거20일 % [95%]','업종 이후40일 % [95%]',
                 '이후40일 전종목 기여 %p [95%]'],srows),
            f'- 실측: 과거 하락 기여 상위 5개는 {", ".join(top)}다. 각각의 이후 평균과 기여는 표에 기재했다. '
            '하락 기여로 순위를 고른 뒤 같은 날짜의 이후 성과를 본 사후 설명이며 산업 원인을 증명하지 않는다.',
            f'- 실측: 캐시 총 {len(sector_map):,}종목, 분석자료 {N:,}종목 중 키 없음 {missing_key.sum():,}종목, '
            f'키 없음 또는 미분류 {int((~known).sum()):,}종목. Q만의 업종 범위 밖 비율은 {estimate(unknown_weight,qonly)}%, '
            f'그중 키 없음 {estimate(absent_weight,qonly)}%, n(비겹침)={ns(unknown_weight,qonly)}. 현재 분류를 과거 분류로 검증하지 못했다.']
    print('SECTOR',srows,flush=True)

    guard()
    sec += ['## 4. t까지 변수 하나로 앞으로 구별할 수 있나 — 후보 셋만',
            '- 코스피 R20은 0 이상/미만, 거래대금 비율은 1 이상/미만, 고점 낙폭은 **코스닥 지수**의 −10% 이하/초과로 고정했다. '
            'Q만에서의 분할이므로 고점 낙폭의 대상은 코스닥으로 정했다. 경계의 등호를 위와 같이 배정했으며 문턱을 조정하지 않았다. '
            '코스닥 60일 지수 이력이 부족한 Q만 날짜는 '+', '.join(dates[qonly&~np.isfinite(dd['KOSDAQ'])])+': '
            '이 후보에서만 빠지며 103일 중 101일을 사용한다. '
            '차이는 첫 갈래−둘째 갈래. 서로 다른 날짜의 분할이며 짝비교가 아니다. 모든 갈래는 t까지 값만으로 정했고 '
            '미래 플러스/마이너스는 결과 열에만 사용했다. 정확히 0인 수익은 승률에서 비양수로 세고 횟수는 따로 적었다.']
    candidates=[('코스피 R20 부호',r20['KOSPI'],r20['KOSPI']>=0,'0 이상','0 미만'),
                ('거래대금 비율',amount_ratio,amount_ratio>=1,'1 이상','1 미만'),
                ('코스닥 60일 고점 낙폭',dd['KOSDAQ'],dd['KOSDAQ']<=-10,'−10% 이하','−10% 초과')]
    predictive=[];predictive_diffs=[]
    for name,x,split,first,second in candidates:
        valid=qonly&np.isfinite(x); a=valid&split;b=valid&~split
        d=difference(y,a,b);predictive_diffs.append((name,d,ns(y,a),ns(y,b)))
        for label,m in [(first,a),(second,b)]:
            positive=int(np.sum(y[m]>0));negative=int(np.sum(y[m]<0));zero=int(np.sum(y[m]==0))
            predictive.append([name,label,extent(m),ns(y,m),len(set(boot.labels[m])),estimate(y,m),
                               f'{positive}/{negative}/{zero}',estimate((y>0).astype(float)*100,m),d,boot_n(y,a,b)])
    sec += [tab(['변수','갈래','신호일 범위','n(비겹침)','관측월','40일 수익 % [95%]',
                 '플러스/마이너스/0 날','플러스 날 비율 % [95%]','첫−둘째 %p [95%]','차이 유효 재표집'],predictive),
            '- 실측: 두 갈래 수익 차이는 '+ '; '.join(f'{name} {value}, n(비겹침) {na}/{nb}' for name,value,na,nb in predictive_diffs)+'다.',
            '- 실측과 한계: 변수는 새 신호일 종가까지 계산할 수 있지만 이 표는 같은 과거에서 평균 차이를 확인한 것이다. '
            '미래 날짜를 맞힌 별도 검증이 아니며, 평균 차이가 나더라도 플러스/마이너스를 완전히 가르는지는 횟수 열로 구분해야 한다. '
            '어느 갈래도 다음 신호의 40일 수익 부호를 보장하지 않는다.']
    print('PREDICTIVE',predictive,flush=True)

    guard()
    sign_positive=qonly&(r20['KOSPI']>=0)
    sign_negative=qonly&(r20['KOSPI']<0)
    qcap45=cell_results['KOSDAQ',4][1]+cell_results['KOSDAQ',5][1]
    qcontrib=np.divide(np.nansum(np.where(market=='KOSDAQ',R40,np.nan),axis=1),np.isfinite(R40).sum(axis=1),
                       out=np.full(T,np.nan),where=np.isfinite(R40).sum(axis=1)>0)
    kcontrib=np.divide(np.nansum(np.where(market=='KOSPI',R40,np.nan),axis=1),np.isfinite(R40).sum(axis=1),
                       out=np.full(T,np.nan),where=np.isfinite(R40).sum(axis=1)>0)
    assert np.allclose((kcontrib+qcontrib)[mature],y[mature])
    sec += ['## 5. 해석 — 실측과 의견 분리',
            tab(['쟁점','직접 관측한 것','해석의 한계'],[
                ['코스닥 쪽의 기여',f'Q만 n(비겹침)={ns(y,qonly)}; 전체 기여 코스닥 {estimate(qcontrib,qonly)}%p, 코스피 {estimate(kcontrib,qonly)}%p',
                 '음수 평균의 산술적 출처는 코스닥 쪽이다. 두 기여의 구간은 모두 0을 포함한다.'],
                ['어떤 크기인가',f'같은 Q만 표본에서 코스닥 시총 4·5분위 합산 기여 {estimate(qcap45,qonly)}%p',
                 '큰 쪽이 더 나빴다는 관찰이다. 결과를 보고 두 칸을 묶은 설명이므로 별도 예측 후보로 만들지 않는다.'],
                ['코스피 상태',f'코스피 R20 음수−비음수 차이 {difference(y,sign_negative,sign_positive)}%p; n(비겹침)={ns(y,sign_negative)}/{ns(y,sign_positive)}',
                 '동일 과거의 조건부 연관이다. 비음수 갈래는 6개월·비겹침 4개뿐이며 인과·미래 예측 증명은 아니다.'],
                ['특정 업종인가','§3의 상위5 업종 이후수익 구간은 모두 0을 포함한다.',
                 '어느 한 업종이 지속 하락의 원인이라고 가르지 못한다. 현재 업종 분류라는 한계도 있다.']]),
            f'- 실측: Q만−비교 기준 수익 차이는 {difference(y,qonly,ref)}%p, n(비겹침)={ns(y,qonly)}/{ns(y,ref)}. '
            'Q만이 평소보다 확실히 나쁘다기보다 두 지수 동반 급락에서 보인 반등 우위가 확인되지 않는다는 읽기가 맞다.',
            f'- 실측: 코스피 R20≥0인 Q만 날은 플러스 {int(np.sum(y[sign_positive]>0))}일·마이너스 '
            f'{int(np.sum(y[sign_positive]<0))}일이고, R20<0인 날도 플러스 {int(np.sum(y[sign_negative]>0))}일·마이너스 '
            f'{int(np.sum(y[sign_negative]<0))}일이 섞여 있다. 평균·구간·n은 §4와 같으며 부호를 완전히 가르지는 못한다.',
            '### (a) 자료가 가르는 것과 못 가르는 것',
            f'- 실측: Q만의 전 종목 40일 평균은 {estimate(y,qonly)}%, n(비겹침)={ns(y,qonly)}. '
            '평균이 0보다 작다는 점 추정과 “계속 하락했다”는 결론은 다르다. 구간이 양수도 포함한다. '
            '§2의 시장·시총별 평균과 전체 기여는 어떤 칸이 평균을 낮췄는지에 대한 산술 분해다.',
            '- 검토 의견: “코스피가 멀쩡해서 반등하지 않았다”와 “코스닥 특정 칸의 약세 때문”이라는 인과 설명은 '
            '이 조건부 평균만으로 서로 배타적으로 판별할 수 없다. 코스피 비A는 −5%보다 덜 떨어졌다는 뜻일 뿐 상승을 뜻하지 않는다. '
            '코스피 지수의 구성·가중과 이 바스켓의 동일가중도 다르다. §4 부호 분할은 그 설명의 관측 가능한 단서만 검사한다.',
            '### (b) 가장 큰 사후 낙관',
            '- 검토 의견: 이미 눈에 띈 Q만을 고른 뒤 같은 기간을 시총×시장·업종·변수 셋·시장 폭으로 더 쪼갰다. '
            '수익 창이 겹치는 많은 날짜를 독립적인 반복 성공처럼 읽는 것이 가장 큰 낙관이다. '
            '월 블록 구간과 40일 간격 수조차 같은 하락·회복을 공유할 수 있고, 업종 상위5 선택과 여러 비교의 선택 편향을 보정하지 않았다. '
            '미래 끝값 결측 제외, 당시 주식수/업종 이력 불명, 원 DB의 상장폐지·수집대상 편향도 남는다.',
            '### (c) 사전등록 후보',
            '- **검토 의견 — 후보 하나:** Q만인 신호일에서 코스피 R20<0일 때의 전 종목 40일 수익이 '
            '코스피 R20≥0일 때보다 높다는 가설. 새로 추가하는 변수는 코스피 R20 부호 하나이며, '
            'Q만 정의·0 문턱·t+1 진입·40일 보유는 고정한다. 후보 셋 중 구간이 0을 벗어난 것을 보고 고른 사후 선택이다. '
            '등록할 가치가 있는 재확인 질문이지 이미 검증된 예측 규칙은 아니다.',
            '- 최소 관측량 제안: 승인·등록 다음 거래일부터 새 자료만 사용. 시간순 첫 Q만 신호를 고르고 '
            '직전 선택 뒤 40거래일이 지나기 전 신호는 건너뛴다. 선택일의 코스피 R20 부호로 한 번 분류한다. '
            '두 갈래 각각 비겹침 사건 8개 이상, 전체 최소 2개 달력연도를 채운 뒤 1회 평가한다. '
            '8개·2년은 검정력이 입증된 기준이 아니라 최소 수집량 제안이며 실제 확보에는 훨씬 오래 걸릴 수 있다. '
            '상장·가격누락 처리와 관측 종료일도 등록 전에 고정하고, 종료 시 부족하면 자료 부족으로 남긴다.',
            '- 반증 기준 제안: 주지표는 사건 동일가중 40일 순수익(왕복 0.5% 차감)의 '
            '“코스피 R20 음수−비음수” 차이. 고정 월 블록 4,000회 seed 7의 95% 구간 상단≤0이면 가설을 기각, '
            '그 외 0을 포함하면 미확인, 하단>0이면 후보를 지지하는 새 관측으로만 남긴다. 두 갈래에 같은 비용을 빼므로 차이는 비용 전과 같다. '
            '관측 중 문턱 변경·중간 채택은 하지 않는다. 실제 사전등록·모델·운영 반영 없음.',
            '### (d) 표시 제안',
            '- 제안만: “코스닥만 급락: 코스피 급락과 겹친 경우의 반등 기록을 그대로 적용하기 어려움”을 덧붙일 수 있다. '
            '표시를 바꾼다면 긴 통계는 상세에 두고 두 지수의 A 여부만 구분하는 편이 낫다. '
            'Q만의 음수 점 추정을 확정적인 매수 금지나 하락 예측으로 표시할 근거는 부족하다. 코드 수정 없음.']

    guard()
    sec += ['## 6. 시장 폭 하나 — 20일선 아래 비율 85%로 고정',
            '- 시장 폭은 코스피·코스닥을 합친 모든 종목 중 close(t)<직전20일 종가평균(t 포함)인 비율이다. '
            '20개 종가가 모두 있는 종목을 분모로 하며 새 상장·자료 결손으로 계산 못 한 종목은 분모에서 제외하고 수를 공개한다. '
            '정지 종목도 가격 이력이 있으면 포함한다. 이 하나의 전 종목 비율을 코스피 A와 코스닥 A 날짜에서 각각 '
            '85% 이상/미만으로 나눴다. 짝비교가 아니며 문턱 변경 없음.']
    brows=[];breadth_diffs=[]
    for k in ['KOSPI','KOSDAQ']:
        m=mature&(cats[k]=='A')&np.isfinite(breadth)
        a=m&(breadth>=85);b=m&(breadth<85)
        diff=difference(y,a,b);breadth_diffs.append((k,diff,ns(y,a),ns(y,b)))
        for label,g in [('85% 이상',a),('85% 미만',b)]:
            omitted=(live.sum(axis=1)-breadth_den)[g]
            brows.append([k,label,extent(g),ns(y,g),len(set(boot.labels[g])),estimate(breadth,g),estimate(y,g),diff,
                          f'{breadth_den[g].min()}~{breadth_den[g].max()}' if g.any() else '0',
                          f'{omitted.min()}~{omitted.max()}' if g.any() else '0',boot_n(y,a,b)])
    sec += [tab(['A 지수','시장 폭','신호일 범위','n(비겹침)','관측월','폭 평균 % [95%]',
                 '40일 평균 % [95%]','이상−미만 %p [95%]','폭 분모 종목 n범위','날별 분모 제외 종목 n','차이 유효 재표집'],brows),
            '- 실측: '+ '; '.join(f'{k}의 85% 이상−미만 수익 차이 {value}, n(비겹침)={na}/{nb}' for k,value,na,nb in breadth_diffs)+'다.',
            '- 실측과 한계: 같은 전 종목 폭과 바스켓을 두 지수의 A 날짜로 나눈 결과라 두 표는 독립 검증이 아니다. '
            '당일 종가 자료로 85% 이상인지 알 수는 있으나 이 표만으로 다음 하락의 반등 예측력이 검증된 것은 아니다.']
    print('BREADTH',brows,flush=True)

    sec += ['## 7. 재현·결측·검증',
            f'- 공통 완결 신호일 {int(mature.sum())}일(비겹침 {count_separate(np.flatnonzero(mature),40)}), '
            f'범위 {extent(mature)}. §1~§6은 이 중 각 집합에 해당하는 날만 썼다. 특징 결측이 있으면 해당 행만 제외한다. '
            '종목 R20은 분석 시작 이후 자료로 계산하므로 초기20일의 R20이 없다. 세 A 집합에는 이 초기일이 없으며 '
            '비교 기준 R20 특성 표에는 그만큼 날짜가 줄어든다.',
            f'- 공통 완결일의 t 종가 유효 종목×날 {int(live[mature].sum()):,}개 중 '
            f't+1/t+41 가격 결측 {int((live & ~np.isfinite(R40))[mature].sum()):,}개 '
            f'({(live & ~np.isfinite(R40))[mature].sum()/live[mature].sum()*100:.4f}%). '
            '이는 전수 결측 집계이므로 표본 신뢰구간을 붙이지 않는다. 실제 손실을 버린 것인지 이 자료만으로 확인 못 함.',
            f'- Q만에서 R20 유효 종목×날 {int(np.isfinite(R20[qonly]).sum()):,}, R40 유효 '
            f'{int(np.isfinite(R40[qonly]).sum()):,}; 거래대금 누락 종목×날 '
            f'{int((live & ~np.isfinite(amount))[qonly].sum()):,}. 업종 범위 밖은 §3, 시총 분류불가는 §2 참조.',
            '- 검증: 이전 답의 64/19/103일과 40일 평균을 반올림 오차 안에서 재현; regime_ad 순수 cell_of와 전체 날짜 분류 일치; '
            '임의50쌍 매수/매도 인덱스 직접 계산 일치; 20개 Q만 날짜의 거래대금·시장 폭 독립 합산 일치; '
            't 이후를 자른 이동평균 일치; 월 재표집 평균을 실제 반복 표본과 대조; '
            '시총×시장 기여 합=전체 수익, 업종 기여 합=전체 과거/이후 수익 확인.',
            f'- 날짜축 SHA256 `{hashlib.sha256("|".join(dates).encode()).hexdigest()}`; '
            f'업종 캐시 SHA256 `{hashlib.sha256(sector_bytes).hexdigest()}`. '
            'DB 과거 값이나 업종 캐시가 바뀌면 같은 종료일에서도 결과가 달라질 수 있다.',
            '- 재현 명령: `python -B research/handoff/code_20261021_kosdaq_only_a.py`. '
            'numpy·pandas·threadpoolctl 및 기존 `code_20261020_entry_regime_blind.py`의 순수 함수가 필요하다. '
            '기존 스크립트 main은 실행하지 않는다. 입력 DB는 mode=ro/query_only; 외부 호출·수집기·배치 실행 없음. '
            '평일 제한시간 시작 전후 가드가 있으며 제한시간에는 실행하지 않는다. 큰 중간 파일을 저장하지 않는다.',
            '## 결론·다음 요청 후보',
            f'- **실측 결론:** Q만의 전 종목 평균은 {estimate(y,qonly)}%, n(비겹침)={ns(y,qonly)}로 재현됐다. '
            '음수 평균의 산술적 출처는 코스닥 종목, 특히 큰 시총 쪽이지만 그 칸의 구간은 모두 0을 포함한다. '
            f'후보 셋 중 코스피 R20 음수−비음수 차이만 {difference(y,sign_negative,sign_positive)}%p로 0을 벗어났다 '
            f'(n(비겹침)={ns(y,sign_negative)}/{ns(y,sign_positive)}). '
            '거래대금·고점 낙폭·시장 폭 85%는 평균 차이의 구간이 0을 포함한다. '
            '코스피 부호 하나를 새 자료에서 재확인할 후보로 제안할 뿐 원인·미래 예측을 확정하거나 규칙을 채택하지 않는다.',
            '- 다음 요청 후보: 동일 정의를 그대로 고정하고 새로 쌓이는 비겹침 사건에서만 재확인(추가 문턱 탐색 없음).']
    assert before == (db.stat().st_size, db.stat().st_mtime_ns), 'Input DB changed'
    sec += ['- 실측: 입력 DB의 실행 전후 크기·수정시각이 동일했다(전체 파일 해시 검사는 아님). '
            '이번 요청은 검토·재현이므로 지정 REPLY와 재현 코드만 남기며 worklog·운영 파일은 수정하지 않았다.']
    guard()
    OUT.write_text('\n\n'.join(sec)+'\n',encoding='utf-8')
    print('WROTE',OUT,OUT.stat().st_size,flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=2):
        run()
