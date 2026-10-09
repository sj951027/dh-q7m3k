"""Independent offline replication. No project imports, network, or DB writes.
Run: python research/handoff/code_20261009_verdict_blind.py
Only output: REPLY_20261009_verdict_blind.md. Snapshot cutoff fixed to 20261008.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import sqlite3
import hashlib
import sys
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('REPLY_20261009_verdict_blind.md')
CUTOFF = '20261008'
BOOT, SEED = 4000, 7
TABLES = {'v3': ('v3_scores', 'final_score_v3'),
          'lowvol': ('lowvol_scores', 'lowvol_score'), 'wu': ('wu_scores', 'wu_score')}
LEDGER_IDS = {
    'v3': 'v30 v31a v31b v31c v31d v31f v31g'.split(),
    'lowvol': 'lv_a lv_a3 lv_b lv_c lv_d lv_short hv_a sm_a mom_a mom_b lv_e'.split(),
    'wu': 'wu_a wu_b sv_a le_a qs_a px_a sv_b'.split()}


def guard():
    now = datetime.now(timezone(timedelta(hours=9)))
    if now.weekday() < 5 and '20:10' <= now.strftime('%H:%M') < '22:30':
        raise SystemExit('KST batch window: no file/DB access allowed')
    return now.isoformat()


def ro(path):
    con = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    con.execute('PRAGMA query_only=ON')
    return con


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(map(str, r)) + ' |' for r in rows])


def ci(samples, alpha=.05):
    return np.quantile(samples, [alpha / 2, 1 - alpha / 2])


def interval(x):
    return f'[{x[0]:+.8f}, {x[1]:+.8f}]'


def stats(sr):
    sr = sr.sort_index().dropna()
    a = sr.to_numpy(float)
    if len(a) == 0:
        raise ValueError('empty sample')
    rng = np.random.default_rng(SEED)
    draws = a[rng.integers(0, len(a), (BOOT, len(a)))]
    weeks = pd.to_datetime(sr.index).to_period('W-SUN')
    blocks = [g.to_numpy() for _, g in sr.groupby(weeks)]
    rng = np.random.default_rng(SEED)
    pick = rng.integers(0, len(blocks), (BOOT, len(blocks)))
    sums = np.array([b.sum() for b in blocks])
    sizes = np.array([len(b) for b in blocks])
    wboot = sums[pick].sum(axis=1) / sizes[pick].sum(axis=1)
    weekly = sr.groupby(weeks).agg(['mean', 'size'])
    return dict(n=len(a), mean=a.mean(), median=np.median(a), pos=(a > 0).mean(),
                iid=draws.mean(axis=1), block=wboot, medci=ci(np.median(draws, axis=1)),
                posci=ci((draws > 0).mean(axis=1)), weekly=weekly)


def main():
    started = guard()
    sys.stdout.reconfigure(encoding='utf-8')
    hist_path = ROOT / 'history.db'
    px_path = ROOT.parent / 'dh-q7m3k-data/ohlcv.db'
    before = [(p.stat().st_size, p.stat().st_mtime_ns) for p in (hist_path, px_path)]
    con, pc = ro(hist_path), ro(px_path)
    px = pd.read_sql_query('SELECT date,ticker,close FROM daily_ohlcv WHERE date<=?', pc,
                           params=(CUTOFF,))
    assert not px.duplicated(['date', 'ticker']).any()
    close = px.pivot(index='date', columns='ticker', values='close').sort_index()
    dates = close.index.tolist()
    didx = {d: i for i, d in enumerate(dates)}
    changes = close.pct_change(fill_method=None).abs()
    denom_ids = {k: sorted(r[0] for r in con.execute(f'SELECT DISTINCT model_id FROM {t}'))
                 for k, (t, _) in TABLES.items()}
    for k in LEDGER_IDS:
        assert set(denom_ids[k]) == set(LEDGER_IDS[k]), (k, denom_ids[k])
    counts = pd.read_sql_query('SELECT run_id,COUNT(*) n FROM stage1_oversold GROUP BY run_id', con)
    med = counts.n.median()
    partial = set(counts.loc[counts.n < .30 * med, 'run_id'])
    double = set()
    for tb, _ in TABLES.values():
        fa = pd.read_sql_query(f'SELECT run_id,model_id,frozen_at FROM {tb}', con)
        fa['ts'] = pd.to_datetime(fa.frozen_at, errors='coerce', utc=True)
        spans = fa.groupby(['run_id', 'model_id']).ts.agg(['min', 'max'])
        double.update(spans.loc[(spans['max'] - spans['min']).dt.total_seconds() >= 3600].index.get_level_values(0))
    excluded = partial | double
    scores = {}
    for mid, tr in [('v30', 'v3'), ('lv_b', 'lowvol'), ('px_a', 'wu')]:
        tb, col = TABLES[tr]
        scores[mid] = pd.read_sql_query(
            f'SELECT run_id,market,ticker,{col} score FROM {tb} WHERE model_id=? AND run_id<=?',
            con, params=(mid, CUTOFF))
        # DB uses upper-case markets for wu, lower-case for v3/lowvol.
        scores[mid]['market'] = scores[mid].market.str.lower()
        assert not scores[mid].duplicated(['run_id', 'market', 'ticker']).any()

    def anchor(rid):
        for delta in range(6):
            d = (datetime.strptime(rid, '%Y%m%d') - timedelta(days=delta)).strftime('%Y%m%d')
            if d in didx:
                return d
        return None

    def keep(mid, start, end=CUTOFF):
        candidates = {}
        for rid in sorted(scores[mid].run_id.unique()):
            if start <= rid <= end and rid not in excluded:
                d = anchor(rid)
                if d is not None:
                    candidates.setdefault(d, []).append(rid)
        return {d: d if d in rs else min(rs) for d, rs in candidates.items()}

    def frame(mid, rid):
        return scores[mid].loc[scores[mid].run_id == rid, ['market', 'ticker', 'score']].set_index(['market', 'ticker'])

    def measure(mid, start, h=20, end=CUTOFF, peer=None):
        kept = keep(mid, start, end)
        peers = keep(peer, start, end) if peer else None
        result, spread, audits, group_records = {}, {}, [], []
        for d, rid in kept.items():
            guard()
            t = didx[d]
            if t + 1 + h >= len(dates) or dates[t + 1 + h] > end:
                continue
            gm = frame(mid, rid)
            if peer:
                if d not in peers:
                    continue
                gm = gm.join(frame(peer, peers[d]).rename(columns={'score': 'peer'}), how='inner')
            entry, final = close.iloc[t+1], close.iloc[t+1+h]
            raw = final / entry - 1
            jump = changes.iloc[t+2:t+2+h].max()
            tickers = gm.index.get_level_values('ticker')
            gm['ret'] = raw.reindex(tickers).to_numpy()
            gm['jump'] = jump.reindex(tickers).to_numpy()
            score_bad = gm.score.isna() | (gm.peer.isna() if peer else False)
            missing_ticker = ~tickers.isin(close.columns)
            endpoints = gm.ret.isna()
            jump_bad = ~(gm.jump <= .32)
            mask = ~score_bad & ~endpoints & ~jump_bad
            used, ics, spreads, n_groups = 0, [], [], 0
            for mk, g in gm.loc[mask].groupby(level='market'):
                if len(g) < 8 or g.score.nunique() < 3 or g.ret.nunique() < 3 or (peer and g.peer.nunique() < 3):
                    continue
                rho = float(spearmanr(g.score, g.ret).statistic)
                # Pearson of average ranks is an independent identity check.
                assert np.isclose(rho, np.corrcoef(g.score.rank(), g.ret.rank())[0, 1], atol=1e-12)
                if peer:
                    rho -= float(spearmanr(g.peer, g.ret).statistic)
                ics.append(rho)
                used += len(g)
                n_groups += 1
                # Descriptive top/bottom ceil(n/10), deterministic ticker tie-break.
                ordered = g.reset_index().sort_values(['score', 'ticker'], kind='stable')
                q = int(np.ceil(len(ordered) / 10))
                spreads.append(ordered.ret.iloc[-q:].mean() - ordered.ret.iloc[:q].mean())
                group_records.append((d, mk, len(g), rho))
            audits.append([d, rid, len(gm), int(missing_ticker.sum()), int((endpoints & ~missing_ticker).sum()),
                           int((~endpoints & jump_bad).sum()), int(score_bad.sum()), int(mask.sum())-used,
                           used, n_groups])
            if ics:
                result[d] = float(np.mean(ics))
                spread[d] = float(np.mean(spreads) * 100)
        audit = pd.DataFrame(audits, columns=['date', 'run', 'rows', 'no_ticker', 'endpoint_na', 'jump_cut',
                                             'score_na', 'group_cut', 'used', 'groups'])
        return pd.Series(result, dtype=float), pd.Series(spread, dtype=float), audit, group_records

    cases = [('px_a', 'px_a', '20260810', CUTOFF, 7),
             ('v30 W2b 중간 관측', 'v30', '20260810', CUTOFF, 7),
             ('v30 W1 재계산(8/09 당시 종료일)', 'v30', '20260606', '20260807', 7)]
    results = {}
    for name, mid, start, end, den in cases:
        for h in [20, 10, 5]:
            results[name, h] = measure(mid, start, h, end)
    pair_px = {h: measure('px_a', '20260810', h, peer='lv_b') for h in [20, 10]}
    pair_v30 = measure('lv_b', '20260810', 20, peer='v30')
    # W2b preregistration requires same-anchor native-universe difference as a reference.
    lv_native = measure('lv_b', '20260810', 20)[0]
    v_native = results[cases[1][0], 20][0]
    common_dates = lv_native.index.intersection(v_native.index)
    pair_v_native = lv_native.loc[common_dates] - v_native.loc[common_dates]
    con.close(); pc.close()
    assert before == [(p.stat().st_size, p.stat().st_mtime_ns) for p in (hist_path, px_path)]

    lines = ['# REPLY — 1번: px_a·v30 W2b 독립 재계산 (2026-10-09)',
             '\n## 범위·독립성·자료',
             f'- 실행 시작(KST): {started}. 가격·점수 종료일 {CUTOFF}. 모든 숫자는 현재 DB를 직접 계산한 **실측**이다.',
             '- 금지된 `VERDICT_202610*.md` 및 `research/verdict_v30_w2_px_a_20261009.py`는 열거나 실행하지 않았다.',
             '- 다만 필수 선행 문서인 worklog/README.md·최신 작업 기록·MODELS_LEDGER.md에 기존 계산값이 실려 있어 읽게 되었다. 따라서 **완전 맹검은 성립하지 않는다**. 결과를 그 값에 맞추지 않고 독립 구현했다.',
             '- 읽은 규약: PREREGISTER_v30_w2.md·PREREGISTER_px_a.md·PROJECT_KNOWLEDGE.md §11/25, leaderboard.py, 사전등록이 지정한 9/06 준비 코드, VERDICT_20260809.md 및 첫 판정 계산 코드. 운영 모듈 import/실행 없이 numpy·pandas·scipy로 재구현했다.',
             '- history.db·ohlcv.db는 mode=ro + query_only로 연결. 본 시세표 daily_ohlcv만 사용(대형 전용 보충표 미혼합). 실행 전후 두 DB의 크기·수정 시각 동일 확인.',
             '- 표본 n은 날짜 수. 시장별 Spearman을 먼저 구하고, 그날 통과 시장을 동일가중 평균. t+1 종가 진입→t+21 종가 청산. 수익 기간 일간 변동 절댓값 >32% 제외. 시장별 유효 쌍 ≥8, 점수·수익 고유값 각각 ≥3.',
             f'- CI: seed={SEED}, {BOOT:,}회. 날짜 복원추출 평균 및 월~일 주 블록 복원추출(주 안 날짜 모두 유지, 날짜 수로 가중). 주블록은 사전등록 감도이며 20일 겹침 의존성을 완전히 없애지는 않는다. 중앙값·양수 비율에는 날짜 재표본 95% 구간을 붙였다.',
             '\n## (a) 40거래일 자격 및 날짜 목록']
    pdates = [d for d in dates if '20260810' <= d <= CUTOFF]
    eligibility = []
    for mid in ['px_a', 'v30']:
        kept = keep(mid, '20260810')
        eligibility.append([mid, len(kept), len(pdates)-1,
                            '리더보드 기준 충족' if mid == 'px_a' else '**중간 관측 — 사전등록 40일 미달**'])
    lines += [table(['모델', '유효 앵커 수(리더보드)', '가격 날짜 차(사전등록 도구)', '상태'], eligibility),
              f'\n가격 날짜 양 끝 포함은 {len(pdates)}개, 날짜 차는 {len(pdates)-1}일이다. v30 도구의 40일을 양 끝 포함 40개로 대체하지 않았다. px_a는 실제 첫 적재 20260810부터 유효 앵커 40개를 세는 리더보드 정의에 따라 자격 충족으로 구분한다. 두 문서의 “40거래일” 표현만으로 동일 정의라고 볼 수 없다.',
              '가격 날짜 목록: ' + ', '.join(pdates)]
    for mid in ['px_a', 'v30']:
        kept = keep(mid, '20260810')
        absent = sorted(set(pdates) - set(kept))
        lines += [f'\n**{mid} 유효 앵커({len(kept)}개)**: ' + ', '.join(kept),
                  f'- 가격 날짜 중 유효 앵커 없음({len(absent)}개): ' + (', '.join(absent) or '없음'),
                  '- 앵커와 run_id가 다른 건: ' + str({d:r for d,r in kept.items() if d != r})]
    w1_kept = keep('v30', '20260606', '20260807')
    lines += [f'\nW1 당시 유효 앵커 {len(w1_kept)}개(비교용): ' + ', '.join(w1_kept),
              f'W1의 40번째 유효 앵커는 {list(w1_kept)[39]}. 실제 8/09 판정은 42개 시점이므로 W1 재계산도 그 종료일을 사용했다.']
    lines += ['\n## (b)(c)(e) IC·날짜/주블록 CI·Bonferroni',
              '원장에 명시된 ID를 현역·은퇴 합집합으로 직접 세고 DB distinct model_id와 일치 확인. v30 W2b는 새 ID가 아니며, 운용 채택은 모델 ID가 아니다.']
    lines += [table(['트랙', '분모', '근거 ID'], [[k, len(v), ', '.join(v)] for k,v in denom_ids.items()]),
              'large는 원장 ls_t1 1개, lead는 ld_a 1개이며 §11과 분리(이번 보정에 합산하지 않음).',
              'v30 사전등록 /7 고정. px_a 등록 당시 /6은 당시 모델 수이며 sv_b 등록 후 현재 원장 /7. /7을 본표, /6을 사전등록 당시 분모 감도로 함께 제시한다. lowvol /11은 lv_b 참고 수치에만 해당한다.']
    rows, extra = [], []
    for name, mid, start, end, den in cases:
        sr = results[name, 20][0]; s = stats(sr)
        rows.append([name, s['n'], f"{s['mean']:+.8f}", interval(ci(s['iid'])), interval(ci(s['block'])),
                     interval(ci(s['iid'], .05/den)), interval(ci(s['block'], .05/den))])
        extra.append([name, f"{s['median']:+.8f}", interval(s['medci']), f"{(sr>0).sum()}/{len(sr)} ({s['pos']:.2%})", interval(s['posci'])])
    lines += [table(['창', 'n', '평균 IC', '날짜 95%', '주블록 95%', '날짜 보정 /7 (99.285714%)', '주블록 보정 /7'], rows),
              table(['창', '중앙값', '중앙값 95%', '양수 날짜 비율', '비율 95% (0~1)'], extra)]
    s = stats(results['px_a',20][0])
    lines += [f"px_a /6 감도(99.166667%): 날짜 {interval(ci(s['iid'], .05/6))}, 주블록 {interval(ci(s['block'], .05/6))}.",
              '\n보조 호라이즌(주지표 대체 아님):']
    rows = []
    for name, *_ in cases:
        for h in [10, 5]:
            s = stats(results[name,h][0])
            rows.append([name, h, s['n'], f"{s['mean']:+.8f}", interval(ci(s['iid'])), interval(ci(s['block']))])
    lines += [table(['창', 'h', 'n', '평균 IC', '날짜 95%', '주블록 95%'], rows), '\n## (d) 주별 평균 부호']
    for name, *_ in cases:
        s = stats(results[name,20][0]); w = s['weekly']
        lines += [f"\n{name}: 양수 {(w['mean']>0).sum()}/{len(w)}주 ({(w['mean']>0).mean():.2%}); 날짜는 앵커 거래일로 묶음.",
                  table(['주', 'n', '주 평균 IC', '부호'], [[str(i), int(r['size']), f"{r['mean']:+.8f}", '+' if r['mean']>0 else '−' if r['mean']<0 else '0'] for i,r in w.iterrows()])]
    lines += ['\n## (f) 짝비교 및 1차 창과의 비교',
              'px_a−lv_b는 **같은 앵커·시장·종목 교집합에서 두 점수를 다시 순위화**했다. 서로 다른 유니버스의 IC 수준을 빼서 우위라고 해석하지 않는다. v30은 사전등록 도구의 원래 유니버스·같은 앵커 차이를 참고로 재현하고, 공통 종목 계산도 병기했다.']
    lines += ['시장명은 wu의 KOSPI/KOSDAQ와 lowvol·v3의 kospi/kosdaq를 소문자로 맞춘 뒤 병합했다. DB는 수정하지 않았다.']
    paired = [('px_a−lv_b 공통 종목 h20', pair_px[20][0]), ('px_a−lv_b 공통 종목 h10', pair_px[10][0]),
              ('lv_b−v30 같은 앵커/각자 유니버스 h20(사전등록 참고)', pair_v_native),
              ('lv_b−v30 공통 종목 h20(감도)', pair_v30[0])]
    rows=[]
    for name, sr in paired:
        s=stats(sr)
        rows.append([name, s['n'], f"{s['mean']:+.8f}", interval(ci(s['iid'])), interval(ci(s['block'])),
                     f"{(s['weekly']['mean']>0).sum()}/{len(s['weekly'])}"])
    lines += [table(['차이', 'n', '평균 ΔIC', '날짜 95%', '주블록 95%', '양수 주'],rows),
              '짝비교는 참고이며 새로운 채택 검정을 추가하지 않는다. 위 95% 구간을 다중검정 통과라고 부르지 않는다.',
              '\nW1은 8/09 판정 당시 마지막 가격일 20260807까지만 가격·run을 잘라 현재의 교정된 DB로 재계산했다. W2b는 20260810~20261008. 앞의 IC 표가 두 창의 나란한 비교다. W1을 현재까지 누적하거나 임의로 첫 40개 성숙 앵커로 바꾸지 않았다.',
              '8/09 문서는 본문 n=21 및 교정 전 수치, 각주④는 “앵커≤7/10 근사, n=23”이라고 스스로 적고 있다. 현재 DB에는 종목코드 교정·게이트 상태 변화가 반영되어 있으므로 그 당시 원본 스냅샷을 정확히 복원했다고 주장하지 않는다.']
    lines += ['\n## (g) 십분위 수익 스프레드(참고)',
              'h20, 통과 시장 각각에서 점수 상위 ceil(n/10) 종목 평균 − 하위 같은 수 종목 평균을 구한 뒤 시장 동일가중·날짜 평균. 동점은 ticker 오름차순으로 고정. 비용 차감 전 %p이며 작은 시장(n<10)도 최소 1종목이다. §11 판정 기준으로 쓰지 않는다.']
    rows=[]
    for name,*_ in cases:
        s=stats(results[name,20][1])
        rows.append([name,s['n'],f"{s['mean']:+.8f}",interval(ci(s['iid'])),interval(ci(s['block']))])
    lines += [table(['창','n','상위−하위 (%p)','날짜 95%','주블록 95%'],rows), '\n## 결손·게이트·날짜별 감사표',
              f'전체 stage1 run 수 {len(counts)}, 중앙값 {med:g}행, 부분실행 기준 <{.30*med:g}행. 부분실행 run: {sorted(partial)}; 이중실행 run: {sorted(double)}.']
    for name, mid, start, end, _ in cases:
        raw_runs=set(scores[mid].loc[scores[mid].run_id.between(start,end),'run_id'])
        kept=keep(mid,start,end)
        sr,sp,au,gr=results[name,20]
        gate=sorted(raw_runs & excluded)
        lines += [f'\n**{name}**: 해당 창 점수 run {len(raw_runs)}, 게이트 제외 {len(gate)}건 {gate}, 중복/앵커 없음 {len(raw_runs)-len(gate)-len(kept)}건, 유효 앵커 {len(kept)}, h20 결과 날짜 {len(sr)}, 아직 수익기간 미완결 {len(kept)-len(au)}개.']
        lines += ['중복/앵커 없음으로 제외한 run: ' + str(sorted(raw_runs - excluded - set(kept.values())))]
        sums=au.iloc[:,2:].sum()
        lines += [table(['점수 행','시세 종목 없음','종목은 있으나 끝점 결손','점프/검사 불가','점수 결손','시장그룹 탈락','최종 쌍','시장그룹 수'],[sums.tolist()]),
                  '행 수는 날짜×종목 관측 수(중복 종목 포함). 점수 결손은 다른 열과 겹칠 수 있다. 끝점 결손과 점프 제외는 상호 배타적. 미완결 앵커는 결손으로 세지 않았다.',
                  table(['앵커','run_id','종목쌍','시장수','IC','스프레드 %p'],
                        [[r.date,r.run,r.used,r.groups,f'{sr.get(r.date,np.nan):+.8f}',f'{sp.get(r.date,np.nan):+.8f}'] for r in au.itertuples()])]
    lines += ['\n공통 종목 짝비교 표본:']
    for label, obj in [('px_a−lv_b h20',pair_px[20]),('px_a−lv_b h10',pair_px[10]),('lv_b−v30 h20',pair_v30)]:
        au=obj[2]
        active = au[au.groups > 0]
        lines += [f'- {label}: 검사 날짜 {len(au)}, IC 날짜 {len(obj[0])}, 교집합 행 {int(au.rows.sum())}, 최종 쌍 {int(au.used.sum())}, 유효 날짜별 쌍 {int(active.used.min())}~{int(active.used.max())}.',
                  f'  시세 종목 없음 {int(au.no_ticker.sum())}, 끝점 결손 {int(au.endpoint_na.sum())}, 점프 제외 {int(au.jump_cut.sum())}, 그룹 기준 탈락 쌍 {int(au.group_cut.sum())}. 모든 시장 탈락 날짜: {au.loc[au.groups==0,"date"].tolist()}; 한 시장만 통과한 날짜: {au.loc[au.groups==1,"date"].tolist()}.']
        if 'h20' in label:
            lines += [table(['앵커', '최종 쌍', '통과 시장 수', 'ΔIC'],
                            [[r.date,r.used,r.groups,f'{obj[0].get(r.date,np.nan):+.8f}'] for r in au.itertuples()])]
    lines += ['\n## 의견(실측 숫자와 분리)',
              '- **px_a: 역작동 방향이나 유의 아님(§11 통과 근거 없음)**. 40 유효 앵커 자격은 충족했지만 보정 CI·주블록 CI가 0을 포함하고 h10 양의 재현도 유의하지 않다. 채택·은퇴·운영 라벨 확정은 하지 않는다.',
              '- **v30 W2b: 중간 관측**. 사전등록 도구 39/40이므로 유의/기움/노이즈의 확정 판정을 내리지 않는다. 현재 구간은 0을 포함한다. W1 기록은 유지하고 현재의 약화를 관측 사실로만 적는다.',
              '\n## 못 한 것·의심스러운 점·질문',
              '1. W2b의 40번째 가격 날짜 차는 아직 관측되지 않았다. 10/12 배치 완료 뒤 도달 여부부터 다시 확인해야 한다(예정일을 실제 도달로 간주하지 않음).',
              '2. 완전 맹검 불가: 필수 선행 기록에 기존 값이 노출되었다. 금지 파일은 미열람이며 계산 구현은 별도이나, 정보 미노출 조건까지 충족했다고 볼 수 없다.',
              '3. “40거래일”에 앵커 수와 날짜 차 두 정의가 있다. 또한 v30 W2b 해석표는 IC<0이고 CI가 0을 걸치는 경우를 명시하지 않는다. 이번에는 자격 미달이라 판정하지 않았고 규칙을 임의 보완하지 않았다.',
              '4. 첫 판정 당시 DB 스냅샷은 제공되지 않았다. W1 역사 수치의 완전 복원·당시 누락 원인별 분해는 못 했다. 현 DB의 같은 종료일 재계산만 제공했다.',
              '5. 시장별 최소 8종목 때문에 유효 앵커 수와 실제 IC 날짜 수는 다를 수 있다. 짝비교 상세 표에 한 시장만 남거나 모든 시장이 탈락한 날짜를 표시했다. v30 W2b에는 본 시세표에 없는 종목 234관측행이 빠졌으므로 결과가 전체 추천 종목을 완전히 대표한다고 볼 수 없다.',
              '6. h20 주블록은 px_a/W2b 4주, W1 6주의 적은 표본이며 수익 창이 서로 겹친다. 소수점 자릿수를 독립 표본 수가 충분하다는 뜻으로 해석하면 안 된다.',
              '7. 사전등록상 20260911 수급 0 동결 기록은 이번 h20 미성숙 구간이다. 후속 판정에서 해당 날짜가 성숙하면 별도 확인이 필요하다. 점수 재작성은 하지 않았다.',
              '\n## 제안',
              '- 다음 맹검 요청에서는 최신 작업 기록과 원장에서 결과 수치를 가린 입력을 제공하면 정보 노출을 피할 수 있다. 이번 작업에서 문서는 수정하지 않았다.',
              '\n## 재현·검증·다음 시작점',
              '- 재현: `python research/handoff/code_20261009_verdict_blind.py` (고정 종료일 20261008, 출력 REPLY 1개). 기존 판정 코드 import 없음, 네트워크 없음, DB 쓰기 없음.',
              '- 입력 키 중복 없음, 원장 ID 집합=DB distinct 집합, Spearman=평균순위 Pearson 일치(오차 1e-12), DB 크기·수정 시각 불변을 실행 중 검증했다.',
              '- bootstrap 난수·횟수는 사전등록 도구와 동일. 큰 중간 파일 생성 없음. 산출물은 이 REPLY와 계산 코드 두 개뿐이며 운영 파일·docs·worklog는 수정하지 않았다.',
              '- 1번 완료 후 정지. 사용자가 “다음”이라고 하면 2번을 시작한다. 3번 미착수. v30 최종 숫자는 10/12 배치 이후 별도 요청 때 재계산한다.']
    guard()
    OUT.write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    print(OUT)
    for name,*_ in cases:
        s=stats(results[name,20][0])
        print(name, 'n=',s['n'],'mean=',s['mean'],'iid=',ci(s['iid']),'block=',ci(s['block']))
    print('PAIRS', [(name,len(sr),sr.mean()) for name,sr in paired])
    print('SHA256 code',hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
