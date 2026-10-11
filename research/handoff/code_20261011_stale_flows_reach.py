# -*- coding: utf-8 -*-
"""수급 입력 도달 범위 감사. 외부 호출/운영 모듈 import/점수 재계산 없음.

python -B research/handoff/code_20261011_stale_flows_reach.py
DB는 mode=ro. 산출물은 같은 폴더의 REPLY 한 파일뿐이다.
점수 열은 SQL ORDER BY에서만 사용한다. Python으로 점수/가격/수익을 가져오지 않는다.
ls_t1은 git에 이미 저장된 HTML의 행 순서를 읽으며 점수식을 실행하지 않는다.
"""
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('REPLY_20261011_stale_flows_reach.md')
START, END = '20260914', '20261008'
MODELS = ['v30', 'lv_b', 'lv_e', 'sv_a', 'sv_b', 'le_a', 'qs_a', 'px_a', 'ls_t1']
MISSING = ['20260626', '20260702', '20260813', '20260820', '20260910']


def guard():
    now = datetime.now(timezone(timedelta(hours=9)))
    skip = set((ROOT / 'skip_dates.txt').read_text(encoding='utf-8-sig').split())
    minute = now.hour * 60 + now.minute
    if now.weekday() < 5 and 1210 <= minute < 1350 and now.strftime('%Y%m%d') not in skip:
        raise SystemExit('평일 배치 시간: 실행 중단')


def ro(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, encoding='utf-8', errors='replace')


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(map(str, headers)) + ' |',
                      '| ' + ' | '.join('---' for _ in headers) + ' |'] +
                     ['| ' + ' | '.join(map(str, row)) + ' |' for row in rows])


def hist(counter):
    return ' · '.join(f'{k}일:{v}종목' for k, v in sorted(counter.items()))


class StoredLargeOrder(HTMLParser):
    """기존 HTML에서 순번/코드만 추출한다. 점수 텍스트/속성은 버린다."""
    def __init__(self):
        super().__init__()
        self.rows, self.cells, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.cells = []
        if tag == 'td' and self.cells is not None:
            self.cell = ''

    def handle_data(self, data):
        if self.cell is not None and self.cells is not None and len(self.cells) < 2:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.cells.append(self.cell)
            self.cell = None
        if tag == 'tr' and self.cells is not None:
            if len(self.cells) > 1 and self.cells[0].strip().isdigit():
                codes = re.findall(r'\b[0-9A-Z]{6}\b', self.cells[1])
                if codes:
                    self.rows.append((int(self.cells[0].strip()), codes[-1]))
            self.cells = None


def stored_large_orders(runs, valid_sets):
    found = {}
    refs = git('log', '--all', '--format=%H', '--since=2026-09-13',
               '--', 'docs/_large_test.html').splitlines()
    for ref in refs:
        if len(found) == len(runs):
            break
        page = git('show', f'{ref}:docs/_large_test.html')
        title = re.search(r'<title>ls_t1[^<]*?(\d{8})[^<]*</title>', page)
        if not title or title[1] not in runs or title[1] in found:
            continue
        rid = title[1]
        parser = StoredLargeOrder()
        parser.feed(page)
        ids = {t for _, t in parser.rows}
        if ids == valid_sets[rid] and len(parser.rows) == len(ids):
            found[rid] = (ref[:8], parser.rows)
    return found


def main():
    guard()
    sys.stdout.reconfigure(encoding='utf-8')
    hpath, opath = ROOT / 'history.db', ROOT.parent / 'dh-q7m3k-data/ohlcv.db'
    cachepath = opath.with_name('listing_cache.json')
    watched = [hpath, opath, cachepath]
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in watched}
    h, o = ro(hpath), ro(opath)
    extra = {t for t, in o.execute('SELECT ticker FROM daily_ohlcv_extra WHERE date=?', (END,))}
    assert len(extra) == 136, '보충표 고정 집합이 바뀜: 정의 재검토 필요'
    ticks = sorted(extra)
    placeholders = ','.join('?' for _ in ticks)
    flows = defaultdict(list)
    validflows = defaultdict(list)
    fetched_dates = {}
    for t, d, valid in o.execute(
        f'SELECT ticker,date,(close IS NOT NULL AND foreign_net_qty IS NOT NULL '
        f'AND inst_net_qty IS NOT NULL) FROM daily_flows WHERE ticker IN ({placeholders}) '
        'AND date<=? ORDER BY ticker,date', (*ticks, END)):
        flows[t].append(d)
        if valid:
            validflows[t].append(d)
    for t, d, fetched in o.execute(
        f'SELECT ticker,date,fetched_at FROM daily_flows WHERE ticker IN ({placeholders}) AND date<=?', (*ticks, END)):
        fetched_dates[(t, d)] = str(fetched or '')[:8]
    flowdays = [d for d, in o.execute('SELECT DISTINCT date FROM daily_flows WHERE date<=? ORDER BY date', (END,))]
    pricedays = [d for d, in o.execute('SELECT DISTINCT date FROM daily_ohlcv WHERE date<=? ORDER BY date', (END,))]
    runs = [d for d, in h.execute('SELECT DISTINCT run_id FROM runs WHERE run_id BETWEEN ? AND ? ORDER BY run_id', (START, END))]

    def last(t, rid):
        ds = flows[t]
        n = bisect_right(ds, rid)
        return ds[n - 1] if n else None

    def statuses(ids, rid):
        ids = set(ids) & extra
        return len(ids), sum(last(t, rid) is not None and last(t, rid) < rid for t in ids), sum(last(t, rid) is None for t in ids)

    def bins(rows, rid, stale_only=False):
        counts = [0, 0, 0]
        for t, rank in rows:
            if t not in extra or (stale_only and not (last(t, rid) and last(t, rid) < rid)):
                continue
            counts[0 if rank <= 20 else 1 if rank <= 50 else 2] += 1
        return '/'.join(map(str, counts))

    spec = {
        'stage3(v2)': ('stage3_final', 'final_score', None),
        'v30': ('v3_scores', 'final_score_v3', 'v30'),
        'lv_b': ('lowvol_scores', 'lowvol_score', 'lv_b'),
        'lv_e': ('lowvol_scores', 'lowvol_score', 'lv_e'),
        **{m: ('wu_scores', 'wu_score', m) for m in ['sv_a', 'sv_b', 'le_a', 'qs_a', 'px_a']},
    }
    score_rows = {}
    for label, (tb, sc, mid) in spec.items():
        filt = ' AND model_id=?' if mid else ''
        params = (START, END, mid) if mid else (START, END)
        rows = h.execute(
            f'SELECT run_id,market,ticker,ROW_NUMBER() OVER(PARTITION BY run_id ORDER BY "{sc}" DESC,ticker,market) '
            f'FROM {tb} WHERE run_id BETWEEN ? AND ?{filt} AND "{sc}" IS NOT NULL', params).fetchall()
        groups = defaultdict(list)
        for rid, market, t, rank in rows:
            groups[rid].append((t, rank))
        score_rows[label] = groups
    large_all, large_valid, large_missing, large_extra_missing = {}, {}, {}, {}
    for rid in runs:
        rows = h.execute('SELECT ticker,(foreign_20d IS NULL AND inst_20d IS NULL),'
                         '((CASE WHEN per>0 THEN 1 ELSE 0 END)+(CASE WHEN pbr>0 THEN 1 ELSE 0 END)'
                         '+(rim_spread IS NOT NULL)+(div_yield IS NOT NULL)>=2) '
                         'FROM large_final WHERE run_id=?', (rid,)).fetchall()
        large_all[rid] = {t for t, missing, valid in rows}
        large_valid[rid] = {t for t, missing, valid in rows if valid}
        large_missing[rid] = sum(missing for t, missing, valid in rows)
        large_extra_missing[rid] = sum(missing for t, missing, valid in rows if t in extra)
    lsorders = stored_large_orders(runs, large_valid)
    assert len(lsorders) == len(runs), 'ls_t1 저장 순위 일부 확인 못 함: 재계산 없이 종료'
    score_rows['ls_t1'] = {rid: [(t, rank) for rank, t in lsorders[rid][1]] for rid in runs}

    report = [
        '# 낡은 수급 입력의 도달 범위 — 2026-10-11', '',
        '## 범위·세는 기준', '',
        '- **실측**: 현재 로컬 DB·코드·보존 로그·git 저장본을 읽었다. DB 연결은 모두 `mode=ro`. 외부 호출·수집기·배치 실행·운영 코드/DB/docs 수정은 하지 않았다.',
        '- **눈가림 범위**: 수익·순위 상관·신뢰구간 등 성과 숫자는 계산하지 않았다. 지정한 금지 파일 2종은 열지 않았다. 선행 규칙을 따르며 읽은 작업 기록·원장에는 기존 성과 숫자가 있어 정보 노출까지 차단한 눈가림은 아니다. 이 보고서는 그 숫자를 재사용하지 않는다.',
        '- 고정 대상 E = `daily_ohlcv_extra(date=20261008)`의 136종목. 과거 날짜에도 같은 집합을 쓴다. 당시 보충표 멤버였다는 뜻은 아니다.',
        '- 기간은 20260914~20261008, runs의 서로 다른 날짜 16개. 모든 모델에서 점수가 저장된 날짜 집합도 이 16개와 같다.',
        '- `N/E/D/Z` = 비NULL 점수 행 수 / E 소속 행 수 / 그중 마지막 daily_flows 날짜가 run보다 앞선 행 수 / 그중 run 이하 daily_flows가 한 번도 없는 행 수. D와 Z는 별개이며 뒤늦게 적재된 과거 행의 존재와 당시 실행 시 가용성은 구분한다.',
        '- 행 수는 날짜×종목 관측행이다. 같은 종목이 여러 run에 나오면 여러 번 센다. 시장은 합쳐 세되 트랙 사이 점수·성과를 비교하지 않았다.',
        '- 순위 위치는 저장된 점수의 내림차순, 동점은 ticker·market 오름차순으로 자른 **전체 시장 합산 행 위치**다. `a/b/c` = 1~20위 / 21~50위 / 51위 밖. 상위50 누계는 a+b. ls_t1만 당시 저장 HTML의 행 순서를 그대로 썼다(동점의 원래 페이지 순서). 점수 자체는 출력하지 않았다.',
        '- ls_t1은 DB에 점수가 동결된 모델이 아니므로, 점수식을 다시 계산하지 않고 입력 4개 중 유효 2개 이상인 행 수와 git에 이미 저장된 페이지 순서만 사용했다. 16일 모두 페이지의 종목 집합이 현재 유효 입력 집합과 일치했다. 당시 원자료 값·정렬 구현까지 현재와 동일했는지는 확인 못 함.', '',
        '## 1. 입력 경로 지도 — 코드 실측', '',
        '수집 경로: `run_all_and_diversify.bat:51,71,77`의 본 표 수집 → 일별 수급 수집 → 스크리너 순서. '
        '`screener_fdr_v2_6.py:953~980`은 전체 daily_flows에서 run 이하 최근 20개 날짜를 고른 뒤, 종목별 마지막 최대 5개/20개 유효 행을 합산한다. '
        '종목의 마지막 날짜가 당일인지·20일을 모두 채웠는지는 요구하지 않고 행이 있으면 supply_fetched=True다. '
        '따라서 **5일 값도 달력 최근 5일이 아니라 최근 20일 창 안의 종목별 마지막 최대 5행**이다. '
        '`screener_fdr_v2_6.py:997~999,1083~1100`에서 없는 종목은 EMPTY_SUPPLY·supply_score=0이 된다.', '',
        table(['모델', 'daily_flows 계열', 'short_flows 계열', '파일·줄 근거'], [
            ['v30', '점수식에 사용: foreign/inst 5d → supply_score_v2, entry_score·등급에도 사용. 20d·smartmoney는 점수식 밖', '안 씀', '`v3_rescore.py:87~101,266~267,295~303,334~341,376~388`'],
            ['lv_b', '표시만; 점수는 realized_vol·roe', '안 씀(공통 로더는 읽지만 이 모델 팩터에 없음)', '`lowvol_score.py:43~47,83,214~218,226~250`; `build_lowvol_filter.py:42~43,135~136`'],
            ['lv_e', '표시만; 점수는 realized_vol·roe·to20', '안 씀(공통 로더만)', '`lowvol_score.py:69~74,142`; `build_lowvol_filter.py:42~43,135~136`'],
            ['sv_a', '표시만; stage3를 점수 입력으로 읽지 않음', '점수식에 공매도비중 svr5 사용', '`wu_score.py:68,83,125~140,165,184~191`; `build_wu_filter.py:113~158,240`'],
            ['sv_b', '표시만; stage3를 점수 입력으로 읽지 않음', '점수식에 공매도 svr5 + 신용 crb5 사용; 대차 안 씀', '`wu_score.py:68~71,87,133~140,165~166,184~191`; `build_wu_filter.py:113~158,240`'],
            ['le_a', '표시만; 점수는 dlow52·obv63·amt20f(가격/거래량)', '안 씀(공통 로더만)', '`wu_score.py:82,125~127,161~164,184~191`; `build_wu_filter.py:113~158,240`'],
            ['qs_a', '표시만; 점수는 lv63·nh252·amt20l', '안 씀(공통 로더만)', '`wu_score.py:88,156~157,168,184~191`; `build_wu_filter.py:113~158,240`'],
            ['px_a', '표시만; 점수는 lv60·to20·lv20·nh252', '안 씀(공통 로더만)', '`wu_score.py:92,157,170~172,184~191`; `build_wu_filter.py:113~158,240`'],
            ['ls_t1', '표시용 5/20d·stage3 운반 수급; 4개 점수 팩터에는 없음', '안 씀', '`large_score.py:109~130,208~219`; `build_large_test.py:35~48,53~70`; `large_verdict.py:46~56`'],
        ]), '',
        '**직접 수식과 후보 선별을 구분**: 위 “표시만”은 같은 후보 집합에서 해당 모델 점수식을 볼 때의 분류다. '
        '`screener_fdr_v2_6.py:1336~1343`의 composite_score에는 종목 수급과 시장 regime_score가 들어가고, '
        '`stage2_risk_filter_v2_6.py:289~292`가 이 값으로 후보를 거른다. '
        '따라서 stage3 후보를 물려받는 **v30·lv_b·lv_e에는 후보 진입의 간접 경로도 있다**. '
        'lowvol은 후보 안에서 백분위 점수를 매기므로 후보 집합이 달라지면 다른 종목의 점수도 달라질 수 있다. '
        '신선한 대체 수급을 만들지 않았으므로 실제 후보·점수가 바뀌는 행 수는 확인 못 함. '
        'wu 모델들은 본 표 시세 유니버스를 쓰므로 이 stage2 경로를 거치지 않는다.', '',
        '### 그 밖의 점수·팩터 사용처(운영 루트 Python 전수 검색)', '',
        table(['사용처', '도달 항목', '점수 투입/관측 구분'], [
            ['`screener_fdr_v2_6.py:1083~1100,1297,1341`; `stage3_fundamental_momentum_v2_6.py:829~848`', 'supply_score → stage1 stock_score → stage3 stock_score/final_score', '기존 v2 점수 경로. v30은 별도 supply_score_v2로 다시 조립'],
            ['`screener_fdr_v2_6.py:579~594`', '프록시 종목 foreign_5d → 시장 외인 수급 → regime_flow_score', '시장 환경 경로. 이번 136종목 직접 경로와 구분(아래 별도 집합 대조)'],
            ['`v3_rescore.py:193~252,256~345`; `shadow_run.py`', 'v30과 같은 엔진을 쓰는 v31 계열', '공통 수급 팩터 사용; 요청 기간 v3_scores 적재 model_id는 v30 하나. 은퇴 모델 재계산 안 함'],
            ['`catalyst_observe.py:67~92,200~214`', 'foreign/inst 5d → smartmoney_score·smartmoney_trigger', '관측값. 요청 9개 모델 점수식은 이 값을 읽지 않음. catalyst_score는 별도 저장 필드이며 smartmoney 합산 점수가 아님'],
            ['`large_score.py:109~130,208~219`', 'stage3 foreign/inst 20d → supply20_net·supply20_pos', '관측. 종목별 최신 stage3를 운반하므로 run보다 더 오래된 표시가 가능'],
            ['`lowvol_score.py:68,117,226~250`', 'short_vol_ratio → lv_short', '요청 밖 기존 모델의 공매도 점수 경로. lv_b·lv_e에는 미투입'],
            ['`whole_score.py:75,85,225~238,299~306`', '최신 short_vol_ratio → whole 유니버스 lv_short', '기존 연구/독립 유니버스 점수 경로; 기존 stage3 수급 미사용'],
            ['`factor_scan.py:181~204,218~235`', 'short_ratio_20·short_surge·credit_rate·credit_chg_20·loan_chg_20; frgn_20·inst_20·pension_20', '팩터 탐색용. 실행 안 함'],
            ['`wu_factor_scan.py:209~240,245~248`', '외국인·기관·연기금 20행 수급/시총, 신용잔고비율', '팩터 탐색용. loan_chg는 로드되지만 이 절의 팩터 계산에는 미사용. 실행 안 함'],
            ['`compute_ic.py:38,43`; `validate_scores.py:62~100`', 'supply_score·smartmoney_score·foreign/inst 20d·regime_score', '저장 관측팩터의 평가 입력. 이번에 평가를 실행하지 않음'],
            ['`build_large_report.py:38~58,103`; `build_large_test.py:53~70`; `build_wu_filter.py:113~158,240`; `build_lowvol_filter.py:42~43,135~136`; `build_mom_filter.py:40,72~73`', '일별 수급 직접 합산 또는 stage3 5/20d 열', '화면 표시/필터. wu 화면은 daily_flows 금액열, v30은 수량×종가이므로 표시 입력 정의까지 같다고 단정하지 않음'],
        ]), '',
        '로더에서 표를 읽는 것과 특정 모델 점수에 투입하는 것은 다르다. 특히 wu 공통 로더는 short를 읽지만 le_a·qs_a·px_a는 해당 팩터를 선택하지 않는다. '
        '위 전수 검색 범위는 현재 운영 루트의 Python 파일이며, 모든 과거 연구 파일의 성과 코드를 열어 조사한 것은 아니다.', '',
        '## 2. run·모델별 도달 행 수 — 실측', '',
        '각 칸은 `N/E/D/Z`. stage3는 v30 점수가 아니라 저장된 기존 v2 final_score 행이며, v30 동결 행은 별도로 센다.', '',
    ]
    labels = ['stage3(v2)', *MODELS]
    count_rows, totals = [], {m: [0, 0, 0, 0] for m in labels}
    for rid in runs:
        line = [rid]
        for m in labels:
            ids = [t for t, rank in score_rows[m][rid]]
            numbers = [len(ids), *statuses(ids, rid)]
            totals[m] = [a + b for a, b in zip(totals[m], numbers)]
            line.append('/'.join(map(str, numbers)))
        count_rows.append(line)
    count_rows.append(['행 합계', *('/'.join(map(str, totals[m])) for m in labels)])
    report += [table(['run', *labels], count_rows), '',
               '### 대형 large_final의 수급 없음(관측 표시) — 실측', '',
               '`수급 없음`은 저장된 foreign_20d와 inst_20d가 모두 NULL인 행. 원자료 자체 없음과 stage3 운반값 없음은 다른 개념이다. '
               '`원자료 E/D/Z`는 large_final 전체 500행 가운데 세며, 위 ls_t1 표는 유효 점수 입력을 가진 행만 센다.', '',
               table(['run', 'large_final 전체', '원자료 E/D/Z', '운반 수급 없음 전체', '운반 수급 없음 E'],
                     [[rid, len(large_all[rid]), '/'.join(map(str, statuses(large_all[rid], rid))), large_missing[rid], large_extra_missing[rid]] for rid in runs]), '']

    winrows = []
    for rid in ['20260911', *runs]:
        end = bisect_right(flowdays, rid)
        lo = flowdays[max(0, end - 20)]
        co = Counter(bisect_right(validflows[t], rid) - bisect_left(validflows[t], lo) for t in ticks)
        rowids = [t for t, in h.execute('SELECT ticker FROM stage3_final WHERE run_id=?', (rid,)) if t in extra]
        fetched = h.execute(f'SELECT COUNT(*) FROM stage3_final WHERE run_id=? AND ticker IN ({placeholders}) AND supply_fetched=1', (rid, *ticks)).fetchone()[0]
        wc = Counter(bisect_right(validflows[t], rid) - bisect_left(validflows[t], lo) for t in rowids)
        winrows.append([rid, lo, hist(co), hist(wc), fetched])
    report += ['## 3. 20일 창에서 낡아지는 정도 — 실측과 달력 추정', '',
               table(['run', '전체 최근20일 창 시작', 'E 전체: 유효 수급일 수별 종목 수', '그날 stage3의 E', 'stage3 E 확보=True'], winrows), '',
               '**실측**: 행 자체의 마지막 날짜는 130종목 20260911·1종목 20260910·5종목 이력 없음이다. '
               '9/11 종료 130종목의「행이 있는 날짜 수」는 20 → 19 → 4일이지만, 로더가 실제 쓰는 유효일 수는 NULL 행 때문에 일부 다르다. '
               '**126종목은 20 → 19 → 4일**, 3종목은 14 → 14 → 4일, 1종목은 2 → 2 → 2일이다(9/11·9/14·10/8 순서). '
               '9/10 종료 1종목은 19 → 18 → 3일이다. 위 표는 실제 로더의 dropna(close, foreign_net_qty, inst_net_qty)와 같은 조건의 **유효일 수**다. '
               '요청 기간 stage3에 실제 나온 E는 매일 11~27종목이며 이 모두 유효 수급을 가진 126종목 집합에 속한다. '
               '현재 9/11 stage3에는 E 18행이 수급 확보=True로 남아 있다. 이후 수동 재실행 시각의 stage3 상태이므로 과거 기록의 “9/11 동결 수급 0”과 같은 상태라고 취급하지 않는다.', '',
               '**달력 추정**: 10/8 뒤에도 수집 누락이 계속되고, 국내 새 거래일마다 전체 daily_flows 날짜가 추가되며, 10/12·13·14·15에 정상 run이 생긴다고 가정하면 '
               '9/10 종료 1종목은 **10/14**, 9/11 종료 130종목은 **10/15**에 전체 최근20일 창에서 처음 빠진다. '
               '10/9는 skip_dates에 있고 국내 휴장으로 가정했다. 이후 휴장·배치 누락·전체 수급 누락 또는 과거 보충 적재가 있으면 첫 run은 달라진다. 미래 실제 run은 확인 못 함. '
               '창 이탈 뒤 stage3는 EMPTY_SUPPLY와 supply_score=0 경로를 탄다. v30은 5일 입력을 0으로 채우지만 최종 점수 전체가 0이 된다는 뜻은 아니다.', '']

    # 저장 입력의 동일성만 비교한다. 금액/점수 재계산과 원자료 합산은 하지 않는다.
    prior5, prior20 = {}, {}
    eqrows = []
    for rid in runs:
        rows = h.execute('SELECT ticker,"foreign_5d_억","inst_5d_억","foreign_20d_억","inst_20d_억" '
                         f'FROM stage3_final WHERE run_id=? AND ticker IN ({placeholders})', (rid, *ticks)).fetchall()
        compared5 = same5 = compared20 = same20 = 0
        for t, f5, i5, f20, i20 in rows:
            if t in prior5:
                compared5 += 1
                same5 += prior5[t] == (f5, i5)
            if t in prior20:
                compared20 += 1
                same20 += prior20[t] == (f20, i20)
            prior5[t], prior20[t] = (f5, i5), (f20, i20)
        eqrows.append([rid, compared5, same5, compared20, same20])
    report += ['### 저장 입력의 동일성 — 실측', '',
               '기간 안에서 같은 종목의 직전 stage3 출현과 비교했다(반드시 직전 거래일은 아님). 두 열 모두 같을 때만 동일로 센다. 합산값·점수를 다시 계산하지 않았다.', '',
               table(['run', '5d 쌍 비교행', '5d 쌍 동일행', '20d 쌍 비교행', '20d 쌍 동일행'], eqrows), '',
               '## 4. 저장 점수 순위 위치 — 실측(성과 아님)', '',
               '각 칸 `상위20 / 21~50 / 51위 밖`. 대상은 각 모델 점수행 중 E이다. 이 기간 실제 점수행의 E는 모두 원자료 날짜가 뒤처져 E=D이고 Z=0이므로, 같은 표가 낡은 입력 보유 행의 위치표다. '
               '수급과 무관한 점수에서도 E의 위치를 센 것으로, 그 모델 점수가 낡은 daily_flows에 오염됐다는 뜻은 아니다.', '',
               table(['run', *labels], [[rid, *(bins(score_rows[m][rid], rid) for m in labels)] for rid in runs]), '',
               'ls_t1 저장 순위 출처(해당 날짜 제목·유효 종목 집합 대조):', '',
               table(['run', 'git 커밋', '저장 전체 순위 행 수'], [[rid, lsorders[rid][0], len(lsorders[rid][1])] for rid in runs]), '']

    oldruns = [d for d, in h.execute("SELECT DISTINCT run_id FROM runs WHERE run_id BETWEEN '20260810' AND '20260911' ORDER BY run_id")]
    oldrows = []
    for rid in oldruns:
        same = sum(last(t, rid) == rid for t in ticks)
        behind = sum(last(t, rid) is not None and last(t, rid) < rid for t in ticks)
        none = sum(last(t, rid) is None for t in ticks)
        saved_by_run = sum(last(t, rid) == rid and fetched_dates.get((t, rid), '').isdigit()
                           and fetched_dates[(t, rid)] <= rid for t in ticks)
        oldrows.append([rid, same, behind, none, saved_by_run])
    cov = Counter(d for t in ticks for d in flows[t] if '20260629' <= d <= '20260911')
    coverage_rows = [[d, cov[d]] for d in flowdays if '20260629' <= d <= '20260911']
    report += ['## 5. 9/11 이전의 원자료 보유 — 실측', '',
               '현재 DB에 있는 daily_flows를 run 날짜로 자른 결과다. 당일 원자료 행의 현재 fetched_at도 함께 비교했다. '
               '특히 수급 소스는 9/11 네이버에서 KIS로 바뀌었으므로, 8월 daily_flows가 당일까지 있다는 사실만으로 당시 stage3 입력 정상까지 확정할 수 없다.', '',
               table(['run', 'E 당일 원자료 있음', 'E 뒤처짐', 'E 이전 이력 없음', '당일 행 중 fetched_at≤run 날짜'], oldrows), '',
               '**실측**: 7/30~9/11의 E 원자료 3,930행은 현재 fetched_at 날짜가 모두 **20260912**다. '
               '그러므로 원자료의 date가 8월 당일이라고 해서 당시 DB에 그 행이 있었다고 결론 낼 수 없다. '
               '9/12에 과거 날짜를 보충한 보존 상태와 일치한다. 그 전에 같은 내용이 있었다가 재기록됐는지는 확인 못 함. '
               '8/10~9/11 stage3의 실제 수급은 당시 네이버 경로·재실행 이력을 별도로 확인해야 하므로 “9/11 이전에는 수급 입력이 모두 정상”은 확정하지 않는다.', '',
               '8/17은 본 표 가격 날짜와 국내 KOSPI/KOSDAQ 지수 날짜에 없고 USDKRW만 있어 휴장 run의 날짜 라벨 차이로 본다(달력 해석). '
               '이 날의 131종목 뒤처짐을 거래일 수급 중단으로 세지 않는다. 5종목은 이 기간 내내 이력이 없다.', '',
               '### 6/29~9/11: 국내 전체 daily_flows 날짜별 E 원자료 종목 수', '',
               table(['날짜', 'E 원자료 종목 수'], coverage_rows), '',
               '**실측**: 요청에서 지적한 7/10~7/29만의 문제가 아니다. 6/29에는 58종목, **6/30~7/29의 전체 수급 날짜 21개에서 E가 모두 0**, '
               '7/30에는 1종목, 7/31~9/10에는 국내 수급 날짜마다 131종목, 9/11에는 130종목이다. '
               '이 공백은 현 DB의 보존 상태이며 실제 당시 미수집인지 나중 정리·보충의 결과인지 확인 못 함. 당일 원자료가 없다는 사실을 네이버 경로의 당시 실패 증거로 쓰지 않는다.', '']

    cache = json.loads(cachepath.read_text(encoding='utf-8'))
    cached = {str(r.get('code') or '').strip().zfill(6) for r in cache['rows']}
    mainids = {t for t, in o.execute('SELECT ticker FROM daily_ohlcv WHERE date=?', (END,))}
    active = {t for t, in o.execute('SELECT ticker FROM daily_ohlcv WHERE date=? AND is_suspended=0 AND close IS NOT NULL', (END,))}
    suspended = {t for t, in o.execute('SELECT ticker FROM daily_ohlcv WHERE date=? AND is_suspended=1', (END,))}
    reconstructed = (cached & mainids) - active
    report += ['## 6. 원인과 10/8의 보충 111종목', '',
               table(['현재 파일/집합 실측', '종목 수'], [
                   ['listing_cache KRX 전체(중복 제거)', len(cached)],
                   ['현재 cache ∩ E', len(cached & extra)],
                   ['현재 cache에서 빠진 E', len(extra - cached)],
                   ['본 표 10/8 전체', len(mainids)],
                   ['본 표 활발·종가 있음', len(active)],
                   ['본 표 거래정지', len(suspended)],
                   ['현재 cache − 활발 본 표', len(cached - active)],
                   ['현재 cache ∩ 본 표 − 활발 본 표(수집 시점 캐시 재구성)', len(reconstructed)],
                   ['재구성 보충 집합 ∩ 거래정지', len(reconstructed & suspended)],
                   ['재구성 보충 집합 △ 거래정지', len(reconstructed ^ suspended)],
                   ['재구성 보충 집합 ∩ E', len(reconstructed & extra)],
               ]), '',
               f'현재 캐시 saved_at은 `{cache["saved_at"]}`이고 E 136종목이 모두 있다. **현재 파일 그대로 load_all_tickers를 실행하면**(실제로 실행 안 함) 보충 대상은 111이 아니라 {len(cached-active)}종목이다. '
               '즉 현재 캐시와 20:10 수집 시점 캐시를 같은 것으로 취급하면 안 된다.', '',
               '**코드·로그로 확인한 누락 구조**:', '',
               '1. `universe_ohlcv.py:105~125`은 KRX 원목록을 숫자 6자리·Market 정확히 KOSPI/KOSDAQ로 제한한 뒤 그 **필터 결과**를 listing_cache.save("KRX", out)에 준다. `listing_cache.py:48~61`에서 KRX 저장은 전체 교체다.',
               '2. 본 표 수집이 앞서 실행되고(`run_all_and_diversify.bat:51`), 수급 수집이 그 다음(`:71`) 실행된다. `kis_flows.py:298~320`은 활발 본 표 + 그 시점 캐시의 차집합만 사용하며 **daily_ohlcv_extra의 기존 집합은 읽지 않는다**.',
               '3. 10/8 로그 `logs/auto_run_20261008_2010.log:17,54~55,81,84`에 본 표 2,629종목·20:10:10 캐시의 본 표 밖 종목 0·상장목록 보충 111·수급 대상 2,629가 차례로 남아 있다. 이때 캐시가 본 표 집합이고 활발 본 표가 2,518이므로 보충은 111이다.',
               '4. 스크리너는 나중에 시장별 **필터 전 원목록**을 캐시에 다시 저장한다(`screener_fdr_v2_6.py:328~336`). 캐시의 시장별 교체(`listing_cache.py:59~61`)로 136종목이 되돌아온다. 현재 캐시는 20:42:28 상태다. `patch_note/20261007_extra_ohlcv_targets.md:8~10`에도 같은 단계별 캐시 차이가 기록돼 있다.', '',
               f'**집합 대조 실측**: 본 표 기반으로 재구성한 보충 111종목과 거래정지 111종목의 대칭차는 {len(reconstructed ^ suspended)}, E와 교집합은 {len(reconstructed & extra)}이다. '
               '따라서 “보충 111”은 이 날 보충표 누락 136종목이 아니라 활발 본 표에서 제외된 거래정지 집합을 다시 더한 것으로 설명된다. '
               '당시 20:10 캐시 파일 자체는 보존본을 찾지 못했으므로, **당시 개별 명단 직접 대조는 확인 못 함**. 숫자만으로의 추측이 아니라 코드·단계 로그·현 본 표 집합으로 재구성한 결과다. '
               '일별 수급 수집 단계가 136종목을 놓치는 구조는 확인했지만, 모든 과거 날짜의 제공자 응답까지 확인한 것은 아니다.', '',
               '공매도 전용 호출은 `kis_flows.py:311~312,634~636`의 --no-daily일 때 보충 자체를 생략한다. '
               'short의 소스 범위 문제와 일별 수급 캐시 순서 문제는 별도다. 요청 9개 모델 중 short 점수 사용은 sv_a·sv_b뿐이고, 그 점수 유니버스는 본 표 가격 열로 제한된다(`wu_score.py:125~140`).', '']

    missingrows = []
    for rid in MISSING:
        counts = [h.execute(f'SELECT COUNT(*) FROM {tb} WHERE run_id=?', (rid,)).fetchone()[0]
                  for tb in ['runs', 'stage1_oversold', 'v3_scores', 'wu_scores']]
        missingrows.append([rid, *counts])
    report += ['## 7. run이 없는 날짜의 경위', '',
               table(['날짜', 'runs', 'stage1', 'v3_scores', 'wu_scores'], missingrows), '',
               table(['날짜', '요청 분류', '실측 근거와 한계'], [
                   ['20260626', '확인 못 함(삭제·배치 실패라는 분류는 부적합)', '`PROJECT_KNOWLEDGE.md:654~665`에 금요일 몫을 6/27 새벽 실행해 토요일 run_id로 저장한 기록. 현재 runs의 6/27 시간 00:39·00:49 확인. 날짜 라벨 이동은 확인; 일부러 지운 증거 없음'],
                   ['20260702', '확인 못 함(삭제·배치 실패라는 분류는 부적합)', '`PROJECT_KNOWLEDGE.md:1182~1197`에 7/2 몫이 7/3 새벽으로 밀린 뒤 같은 날 저녁 재실행해 stage 덮어쓰기·동결 혼재한 기록. 현재 runs 7/3은 21:18·21:24. git의 7/3 새벽/저녁 자동 커밋도 존재. 별도 7/2 라벨 유실은 확인; 일부러 삭제 증거 없음'],
                   ['20260813', '배치 실패(미발화)', '`patch_note/20260814_leaderboard_redesign_crosssim.md:14`에 스케줄러 미발화(전원/조건)와 설정 조치 기록. 당시 로그 원본은 확인 못 함; 문서 근거'],
                   ['20260820', '배치 실패(미실행)', '`patch_note/20260821_intraday_run_cleanup.md:4~9`에 컴퓨터 이상으로 8/20 완전 미실행, 8/21 장중 캐치업 행 삭제 기록. 삭제된 날짜는 8/21이며 8/20을 일부러 지웠다는 증거 아님'],
                   ['20260910', '확인 못 함', '현 DB에 세 표 모두 0. logs 및 git에 이 날짜의 배치 로그 파일을 찾지 못함. clean_partial_run의 존재만으로 해당 날짜 삭제를 입증할 수 없음'],
               ]), '',
               '`research/clean_partial_run.py:23~24,59~76`은 지정 날짜 삭제·백업 도구다. '
               '`git log --all -- research/clean_partial_run.py`의 이력은 9/9 도입·9/12 회전 보강이고, 다섯 대상 날짜에 실행했다는 기록은 찾지 못했다. '
               '`git log --all --name-only -- logs patch_note research/clean_partial_run.py`에도 다섯 날짜가 이름에 들어간 보존 로그/패치 경로는 없었다. '
               '현재 남은 backup 파일명에도 다섯 대상 날짜의 clean 백업이 있는지는 아래 별도로 센다. 백업은 회전 삭제되므로 흔적 없음은 미실행 증명이 아니다.', '',
               '**40거래일 세기 한 줄**: `leaderboard.py:137~170,174~180`의 유효 앵커 수는 모델별 저장 run을 세므로 v3의 8/13·8/20·9/10은 늘지 않고, '
               '6/27은 6/26에 매핑되며 7/3은 혼재 동결 게이트 대상이다; 반면 `research/verdict_v30_window2_prep_20260906.py:84~91`의 가격 날짜 차는 run 없는 거래일도 센다. '
               'wu에는 네 날짜의 저장 행이 있으므로 모든 모델의 관측일이 동시에 빠졌다고 단정할 수 없다. **금지된 10/9 판정 도구의 현재 세기는 열지 않아 확인 못 함**.', '']

    hard = h.execute(f"SELECT COUNT(*) FROM v3_scores WHERE model_id='v30' AND run_id BETWEEN ? AND ? "
                     f"AND ticker IN ({placeholders}) AND final_score_v3=-999", (START, END, *ticks)).fetchone()[0]
    uniquev30 = {t for rid in runs for t, rank in score_rows['v30'][rid] if t in extra}
    report += ['## 결론 — 모델별 한 줄', '',
               f'- **v30**: 낡은 daily_flows 보유 입력이 점수 계산 경로에 들어간 동결 **{totals["v30"][2]}행/{len(uniquev30)}종목**. 그중 하드 제외 최종값 **{hard}행**은 수급과 무관하게 덮어쓰는 출력이므로, 수급 성분을 남기는 수식 경로는 **{totals["v30"][2]-hard}행**. 신선한 자료로 실제 값이 바뀌는 행 수는 확인 못 함. 후보 진입 간접 경로도 있음.',
               *[f'- **{m}**: daily_flows는 직접 점수식에 쓰지 않고 표시에 사용; E의 낡은 원자료 보유 {totals[m][2]}행, 직접 점수 투입 0행.' +
                 (' stage3 후보 진입·후보 내 백분위의 간접 영향은 확인 못 함.' if m in ['lv_b', 'lv_e'] else
                  ' short_flows는 별도 점수 입력; 이번 E의 점수행은 0행.' if m in ['sv_a', 'sv_b'] else
                  ' 이번 E의 낡은 daily_flows와 점수식은 무관.') for m in MODELS if m != 'v30'], '',
               '### 판정문 각주 초안', '',
               f'> 입력 감사에서 2026-09-14~10-08의 16개 run 중 보충표 136종목의 일별 수급은 130종목이 9/11, 1종목이 9/10에서 끝났고 5종목은 이력이 없었다. '
               f'이 중 v30 동결 {totals["v30"][2]}관측행({len(uniquev30)}종목)이 낡은 수급 입력으로 계산 경로를 통과했으며, 하드 제외 출력 {hard}행을 구분했다. '
               '종목별 최신일·유효일 수를 확인하지 않는 로더 때문에 이 행들은 수급 확보로 표시됐다. '
               'lv_b·lv_e·le_a·qs_a·px_a·ls_t1은 해당 일별 수급을 직접 점수식에 쓰지 않고, sv_a·sv_b는 별도 short_flows를 사용한다. '
               '단 v30·lv_b·lv_e의 공통 후보 선별과 시장 수급 프록시에는 간접 경로가 있어 후보 집합의 영향은 별도다. '
               '이 감사는 저장 입력의 날짜·행 수·위치만 확인했으며 성과나 판정 변화는 계산하지 않았다.', '',
               '### 고치는 안(선택·적용하지 않음)', '',
               '1. 수집 대상에 기존 daily_ohlcv_extra 집합을 합치거나, KRX 원목록 캐시와 시세 필터 결과 캐시를 분리하거나, 원목록 저장을 필터 전에 하도록 하는 안. 각 안의 포함 범위·거래정지 처리·short 영향은 별도 검토 대상이다.',
               '2. 원자료 마지막 날짜·20일 창 유효일 수를 입력과 함께 기록하고, 낡은 값과 이력 없음을 분리해 표시하는 안. 최신일/최소 유효일 조건을 점수 경로에 요구하는 변경은 모델 입력 정의가 바뀌므로 별도 승인·사전등록 검토가 필요하다.',
               '3. “5일”을 전체 최근5개 거래일로 자를지 기존 종목별5행으로 유지할지, 과거 행을 보충할지, 기존 동결행을 유지하며 각주만 붙일지는 선택하지 않았다. 제공자 과거 자료 가용성은 확인 못 함. 동결 점수·판정은 이번에 수정하지 않았다.', '',
               '## 재현·한계', '',
               '- 명령: `python -B research/handoff/code_20261011_stale_flows_reach.py` (표준 라이브러리만, 로컬 git 읽기). 생성 파일은 이 REPLY 하나. 점수 엔진·판정 도구를 import/실행하지 않는다.',
               '- 성과 평가·점수 재계산·DB 쓰기·외부 호출 0회. 순위 위치는 이미 저장된 값/순서만 사용한다. 원자료의 당시 제공자 응답·수집 시각 캐시 보존본·미래 실제 run은 확인 못 함.',
    ]

    # 추가 집합 검증: 프록시 종목에 E가 포함되어 시장 공통 경로로 번지는지.
    source = (ROOT / 'screener_fdr_v2_6.py').read_text(encoding='utf-8-sig')
    import ast
    tree = ast.parse(source)
    proxies = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'KOSPI_PROXY', 'KOSDAQ_PROXY'} for t in node.targets):
            for value in ast.walk(node.value):
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and re.fullmatch(r'[0-9A-Z]{6}', value.value):
                    proxies.add(value.value)
    report += [f'- 시장 수급 프록시 **예비 고정 집합**과 E 교집합은 {len(proxies & extra)}종목. '
               '실제 선택은 시장별 원목록의 시총 순 동적 구성 우선(`screener_fdr_v2_6.py:253~288`)이며, 9/14·10/8 로그에는 두 시장 모두 동적 구성 성공 기록이 있다. '
               '실제 날짜별 10개 프록시 명단은 저장표/로그에서 확인 못 함. '
               '따라서 E가 시장 공통 입력→regime_score→기존 v2 final_score·stage2 후보 선별로 번지는 **코드 경로는 있음**; '
               '실제 시장별 포함 종목 수·간접 영향 행 수는 확인 못 함. 고정 예비 집합의 교집합을 실제 명단으로 대체하지 않았다.',
               f'- 20일 로더 날짜 집합과 본 표 가격 날짜 집합은 대상 기간에 동일: {set(d for d in flowdays if START <= d <= END) == set(d for d in pricedays if START <= d <= END)}. 미래 추정은 이 날짜 진전이 계속된다는 가정이다.']
    backups = list((ROOT / 'backup').glob('history_before_clean_*.db'))
    report += [f'- 현재 clean 백업 파일 중 다섯 대상 날짜가 이름에 들어간 파일 수: {sum(any(d in p.name for d in MISSING) for p in backups)}. 내용은 열지 않았다.']
    for label, (tb, sc, mid) in spec.items():
        filt = ' AND model_id=?' if mid else ''
        params = (START, END, mid) if mid else (START, END)
        nulls = h.execute(f'SELECT COUNT(*) FROM {tb} WHERE run_id BETWEEN ? AND ?{filt} AND "{sc}" IS NULL', params).fetchone()[0]
        assert nulls == 0, f'{label} 비NULL 행과 전체 행 차이: {nulls}'
    for rid in runs:
        assert {t for t, rank in score_rows['stage3(v2)'][rid]} == {t for t, rank in score_rows['v30'][rid]}, 'stage3/v30 종목 불일치'
    report += ['- stage3와 v30 동결의 날짜별 종목 집합 동일, 요청 점수표의 점수 NULL 행 0. 수급 창 내 원자료의 유효/비유효 구분은 로더와 같은 NULL 조건을 사용했다.']
    h.close()
    o.close()
    after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in watched}
    assert before == after, '감사 중 입력 파일 크기/수정시각 변화: 동시 작업 여부 확인 필요'
    report += ['- 실행 전후 history.db·ohlcv.db·listing_cache.json의 크기/수정시각 동일. 파일 전체 내용 해시를 계산한 검증은 아니다.', '']
    guard()
    OUT.write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps({'runs': len(runs), 'totals_N_E_D_Z': totals, 'v30_hard_excluded': hard,
                      'v30_unique_extra': len(uniquev30), 'ls_saved_days': len(lsorders),
                      'reply': str(OUT)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
