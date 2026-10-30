"""Offline independent reproduction. Only writes the paired REPLY markdown.

Run: python -B research/handoff/code_20261030_crash_depth_blind.py
2026-10-30 user explicitly allowed work after confirming the batch finished.
No production code imports, network calls, or writable SQLite connections.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / 'dh-q7m3k-data'
REPORT = Path(__file__).with_name('REPLY_20261030_crash_depth_blind.md')
CUTOFF = '20261022'
SEED = 20261030
B = 4000
POLICIES = ('last', 'loss90')
LABEL = {'last': '마지막 가격', 'loss90': '−90%'}
EXCLUDED = '금융|은행|증권|보험|캐피탈|캐피털|카드|생명|화재|저축|여신|신탁|리츠|REIT|부동산투자|스팩|SPAC'
COMPARE_MARKER = '\n## 7. 기존 연구와 사후 대조'


def guard(override=False):
    now = datetime.now(timezone(timedelta(hours=9)))
    if now.weekday() < 5 and '20:10' <= now.strftime('%H:%M') < '22:30' and not override:
        raise SystemExit('평일 배치 시간: 중단. 사용자가 실제 배치 종료를 확인한 경우에만 --batch-finished 사용.')


def connect(path):
    c = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    c.execute('PRAGMA query_only=ON')
    assert c.execute('PRAGMA query_only').fetchone()[0] == 1
    return c


def fingerprint(path):
    st = path.stat()
    return {'bytes': st.st_size, 'mtime_ns': st.st_mtime_ns}


def fmt(x, digits=2):
    return f'{x:+.{digits}f}' if np.isfinite(x) else '확인 못 함'


def stats(values):
    a = np.asarray(values, float)
    a = a[np.isfinite(a)]
    if not len(a):
        return dict(n=0, mean=np.nan, lo=np.nan, hi=np.nan, pos=0, worst=np.nan, median=np.nan)
    boot = a[np.random.default_rng(SEED).integers(0, len(a), size=(B, len(a)))].mean(axis=1)
    lo, hi = np.quantile(boot, [.025, .975])
    return dict(n=len(a), mean=a.mean(), lo=lo, hi=hi, pos=int((a > 0).sum()), worst=a.min(), median=np.median(a))


def cell(values):
    s = stats(values)
    return f"{fmt(s['mean'])} [{fmt(s['lo'])}, {fmt(s['hi'])}]"


def rho(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return np.nan
    return float(np.corrcoef(rankdata(x), rankdata(y))[0, 1])


def rho_ci(x, y):
    x, y = np.asarray(x), np.asarray(y)
    vals = []
    for ix in np.random.default_rng(SEED).integers(0, len(x), (B, len(x))):
        r = rho(x[ix], y[ix])
        if np.isfinite(r):
            vals.append(r)
    return np.quantile(vals, [.025, .975]) if vals else (np.nan, np.nan)


def select_events(signal, threshold):
    chosen = []
    for t in np.flatnonzero(signal <= threshold):
        if not chosen or t - chosen[-1] >= 40:
            chosen.append(int(t))
    return np.array(chosen, int)


def table(lines, headers, rows):
    lines.extend(['', '| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'])
    lines.extend('| ' + ' | '.join(map(str, row)) + ' |' for row in rows)
    lines.append('')


class Study:
    def __init__(self):
        path = DATA / 'ohlcv_10y.db'
        self.before = fingerprint(path)
        c = connect(path)
        idx = pd.read_sql_query('SELECT series,date,close FROM index_daily WHERE date<=?', c, params=(CUTOFF,))
        self.meta = pd.read_sql_query('SELECT ticker,name,market,listed,delisted FROM meta', c).set_index('ticker')
        self.price_bounds = c.execute('SELECT min(date),max(date),count(*) FROM prices').fetchone()
        self.index_bounds = idx.groupby('series')['date'].agg(['min', 'max', 'count']).to_dict('index')
        index = idx.pivot(index='date', columns='series', values='close').sort_index()[['KOSPI', 'KOSDAQ']]
        assert index.notna().all().all(), '두 지수의 거래일 불일치'
        self.dates = index.index.to_numpy()
        self.index = index.to_numpy(float)
        self.T = len(self.dates)
        m = self.meta
        market = m.market.fillna('').replace({'KOSDAQ GLOBAL': 'KOSDAQ'})
        keep = market.isin(['KOSPI', 'KOSDAQ']) & m.index.str.endswith('0') & ~m.name.fillna('').str.contains(EXCLUDED, case=False, regex=True)
        self.meta = m.loc[keep].copy()
        self.meta['market'] = market[keep]
        self.tickers = self.meta.index.sort_values().to_numpy()
        self.meta = self.meta.reindex(self.tickers)
        self.N = len(self.tickers)
        self.p = np.full((self.T, self.N), np.nan)
        self.v = self.p.copy()
        mapping = {x: i for i, x in enumerate(self.tickers)}
        dmap = {x: i for i, x in enumerate(self.dates)}
        kept_rows = 0
        for chunk in pd.read_sql_query('SELECT ticker,date,close,volume FROM prices WHERE date<=?', c, params=(CUTOFF,), chunksize=300000):
            chunk = chunk[chunk.ticker.isin(mapping) & chunk.date.isin(dmap)]
            rr = chunk.date.map(dmap).to_numpy(int)
            cc = chunk.ticker.map(mapping).to_numpy(int)
            self.p[rr, cc] = chunk.close.to_numpy(float)
            self.v[rr, cc] = chunk.volume.to_numpy(float)
            kept_rows += len(chunk)
        c.close()
        self.p[self.p <= 0] = np.nan
        self.kept_rows = kept_rows
        self.active_days = np.flatnonzero(np.isfinite(self.p).any(axis=1))
        self.start = int(self.active_days[0])
        self.last = np.max(np.where(np.isfinite(self.p), np.arange(self.T)[:, None], -1), axis=0)
        self.delist = self.meta.delisted.fillna('').str.replace('-', '').to_numpy(str)
        self.r20 = np.full_like(self.p, np.nan)
        self.r20[20:] = (self.p[20:] / self.p[:-20] - 1) * 100
        self.signals = {}
        for w in (7, 20):
            a = np.full_like(self.index, np.nan)
            a[w:] = (self.index[w:] / self.index[:-w] - 1) * 100
            self.signals[w] = a
        # Gap spanning changes are not single-day changes. Missing endpoints stay missing.
        jump = np.zeros_like(self.p, dtype=bool)
        jump[1:] = np.abs(self.p[1:] / self.p[:-1] - 1) > .35
        # Keep terminal collapse prices: excluding liquidation jumps would remove real losses.
        dd = pd.to_datetime(self.delist, format='%Y%m%d', errors='coerce')
        dt = pd.to_datetime(self.dates, format='%Y%m%d')
        delta = (dd.to_numpy()[None, :] - dt.to_numpy()[:, None]) / np.timedelta64(1, 'D')
        terminal = (delta >= 0) & (delta <= 30)
        self.jump_count = int(jump.sum())
        self.nonterminal_jump_count = int((jump & ~terminal).sum())
        self.jump_cum = np.cumsum(jump & ~terminal, axis=0, dtype=np.int32)
        self.cache = {}
        self.audit = {}
        self.market_q = self.meta.market.eq('KOSDAQ').to_numpy()
        print('loaded', self.T, self.N, kept_rows, flush=True)

    def events(self, market, window, threshold):
        sig = self.signals[window][:, market].copy()
        # Do not let index-only dates before the stock panel consume event spacing.
        sig[:self.start] = np.nan
        return select_events(sig, threshold)

    def returns(self, t, h=40, policy='last', clean=False):
        key = (t, h, policy, clean)
        if key in self.cache:
            return self.cache[key]
        out = np.full(self.N, np.nan)
        if t + h + 1 > self.active_days[-1]:
            return out
        entry, end = t + 1, t + h + 1
        valid = np.isfinite(self.p[t]) & np.isfinite(self.p[entry]) & (self.v[entry] > 0)
        # Exclude entry after recorded delisting, including inconsistent metadata.
        valid &= (self.delist == '') | (self.delist > self.dates[entry])
        mature = (self.delist > self.dates[entry]) & (self.delist <= self.dates[end])
        endpoint = self.p[end].copy()
        terminal = valid & mature & (self.last >= entry) & (self.last <= end)
        cols = np.flatnonzero(terminal)
        endpoint[cols] = self.p[self.last[cols], cols]
        out[valid] = (endpoint[valid] / self.p[entry, valid] - 1) * 100
        if policy == 'loss90':
            out[terminal] = -90.0
        badpath = (self.jump_cum[end] - self.jump_cum[entry]) > 0
        if clean:
            out[badpath] = np.nan
        self.audit[key] = dict(entry=int(valid.sum()), missing=int((valid & ~np.isfinite(out)).sum()), terminal=int(terminal.sum()), terminal_zero=int((terminal & (self.v[np.maximum(self.last, 0), np.arange(self.N)] == 0)).sum()), badpath=int((valid & badpath).sum()))
        self.cache[key] = out
        return out

    def basket(self, t, h=40, policy='last', q=False, clean=False):
        a = self.returns(int(t), h, policy, clean)
        if q:
            a = a[self.market_q]
        return float(np.nanmean(a)) if np.isfinite(a).any() else np.nan

    def index_return(self, t, h, market):
        if t + h + 1 >= self.T:
            return np.nan
        return (self.index[t + h + 1, market] / self.index[t + 1, market] - 1) * 100

    def complete(self, events, h=40):
        return np.array([t for t in events if t + h + 1 <= self.active_days[-1] and np.isfinite(self.basket(t, h))], int)


def comparison_audit(batch_finished=False):
    """Post-unblinding only: independently align definitions, never run original code."""
    guard(batch_finished)
    body = REPORT.read_text(encoding='utf-8').split(COMPARE_MARKER)[0]
    independent_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()
    s = Study()
    c = connect(DATA / 'ohlcv_10y.db')
    notes = pd.read_sql_query('SELECT ticker,note FROM meta', c).set_index('ticker').note.reindex(s.tickers).fillna('')
    c.close()
    dl = notes.str.contains('delisted').to_numpy()
    f = pd.DataFrame(s.p).ffill().to_numpy()
    aligned = np.full(s.T, np.nan)
    no_volume = np.full(s.T, np.nan)
    main_basket = np.full(s.T, np.nan)
    for t in range(s.start, int(s.active_days[-1])-40):
        entry, end = t+1, t+41
        endpoint = s.p[end].copy()
        endpoint[dl] = f[end, dl]
        r = (endpoint / s.p[entry] - 1) * 100
        aligned[t] = np.nanmean(r)
        # One change only from the independent baseline: permit zero-volume entry.
        valid = np.isfinite(s.p[t]) & np.isfinite(s.p[entry]) & ((s.delist == '') | (s.delist > s.dates[entry]))
        endpoint2 = s.p[end].copy()
        terminal = valid & (s.delist > s.dates[entry]) & (s.delist <= s.dates[end]) & (s.last >= entry) & (s.last <= end)
        cols = np.flatnonzero(terminal)
        endpoint2[cols] = s.p[s.last[cols], cols]
        no_volume[t] = np.nanmean(np.where(valid, (endpoint2 / s.p[entry] - 1)*100, np.nan))
        main_basket[t] = s.basket(t)
    # Original R20 starts only after truncating index history to stock-panel dates.
    aligned_signal = s.signals[20].copy()
    aligned_signal[:s.start+20] = np.nan
    out = ROOT / 'research' / 'out_crash_depth'
    original_bins = pd.read_csv(out / 'bins_KOSPI.csv')
    original_th = {market: pd.read_csv(out / f'thresholds_{market}.csv') for market in ('KOSPI', 'KOSDAQ')}
    lines = [COMPARE_MARKER.strip(), '',
             '**사후 대조 순서:** §0~6 본문을 저장한 뒤에만 기존 연구 보고서와 계산 코드, 지정 표의 CSV를 열었다. 기존 코드는 실행하지 않았다. 대조 직전 본문 SHA256: `' + independent_hash + '`.', '',
             '원문 표는 한 자리로 반올림되어 있어 아래 Claude 값은 같은 연구의 `out_crash_depth/bins_KOSPI.csv`, `thresholds_KOSPI.csv`, `thresholds_KOSDAQ.csv` 두 자리 저장값을 썼다. 기본판은 모두 마지막 가격 판이며 95%는 각 분석의 사건 구간이다. **정의 정렬 재계산**은 사후 원인 점검으로, 앞의 독립 결과를 교체하지 않는다.', '',
             '### 7-1. 기존 §1 코스피 날 표 대조']
    rows, checks, causes = [], [], []
    for i, (lower, upper, label) in enumerate([(-10,-5,'(−10,−5]'),(-15,-10,'(−15,−10]'),(-20,-15,'(−20,−15]'),(-np.inf,-20,'≤−20')]):
        own_mask = (s.signals[20][:,0] > lower) & (s.signals[20][:,0] <= upper) & np.isfinite(main_basket)
        aligned_mask = (aligned_signal[:,0] > lower) & (aligned_signal[:,0] <= upper) & np.isfinite(aligned)
        original = original_bins.iloc[i]
        own = main_basket[own_mask].mean()
        matched = aligned[aligned_mask].mean()
        checks.append(abs(matched - original['바구니평균']))
        assert int(aligned_mask.sum()) == original['날수']
        rows.append([label, f"{int(original['날수'])}/{int(own_mask.sum())}", f"{original['바구니평균']:+.2f}", fmt(own), fmt(own-original['바구니평균']), f"{original['중앙']:+.2f}/{np.median(main_basket[own_mask]):+.2f}", f"{original['플러스비율']:.0f}%/{100*(main_basket[own_mask]>0).mean():.1f}%", f"{original['최악']:+.1f}/{main_basket[own_mask].min():+.2f}", fmt(matched)])
        causes.append([f'KOSPI 날 {label}', int(own_mask.sum()), fmt(own), fmt(no_volume[own_mask].mean()), fmt(aligned[own_mask].mean()), fmt(matched)])
    table(lines, ['깊이', 'n날 Claude/Codex', 'Claude 평균', 'Codex 평균', '차이 %p', '중앙 C/Cx', '플러스 C/Cx', '최악 C/Cx', '정의 정렬 재계산'], rows)
    lines += ['### 7-2. 기존 §2 코스피 사건 표 대조']
    for market, name in enumerate(('KOSPI', 'KOSDAQ')):
        if market:
            lines += ['### 7-3. 기존 §4 코스닥 사건 표 대조']
        rows = []
        for i, threshold in enumerate((-5,-10,-15,-20)):
            ts = s.complete(s.events(market, 20, threshold))
            sig = aligned_signal[:,market].copy()
            sig[~np.isfinite(aligned)] = np.nan
            matched_ts = select_events(sig, threshold)
            orig = original_th[name].iloc[i]
            original_mean = float(orig['사건평균'])
            own = main_basket[ts]
            matched = aligned[matched_ts]
            checks.append(abs(matched.mean()-original_mean))
            assert len(matched_ts) == orig['사건']
            st = stats(own)
            rows.append([threshold, f"{int(orig['사건'])}/{len(ts)}", f"{original_mean:+.2f} {orig['구간']}", cell(own), fmt(own.mean()-original_mean), f"{orig['플러스']}/{st['pos']}·{st['n']}", f"{orig['최악']:+.1f}/{st['worst']:+.2f}", fmt(matched.mean())])
            if market == 0 and threshold == -5:
                missing = sorted(set(ts)-set(matched_ts))
                missing_text = ', '.join(f'{s.dates[t]} (R20 {s.signals[20][t,0]:+.2f}, 바구니 {main_basket[t]:+.2f})' for t in missing)
            causes.append([f'{name} 사건 ≤{threshold}', len(ts), fmt(own.mean()), fmt(no_volume[ts].mean()), fmt(aligned[ts].mean()), fmt(matched.mean())])
        table(lines, ['문턱', 'n사건 Claude/Codex', 'Claude 평균 [95%]', 'Codex 평균 [95%]', '차이 %p', '플러스 Claude/Codex', '최악 Claude/Codex', '정의 정렬 재계산'], rows)
    assert max(checks) <= .0050001
    lines += ['### 차이 원인 — 직접 확인과 해석', '',
              f'**직접 확인 1 — 지수 과거 이력 절단:** 기존 코드는 지수를 종목 가격 날짜(20150102~)로 먼저 줄인 뒤 shift(20)을 계산한다. 그래서 첫 20거래일의 원래 존재하는 지수 신호를 버린다. 독립 계산은 2014-11부터의 지수 이력을 보존해 R20을 구한다. 추가된 ≤−5 사건은 {missing_text}. 같은 이유로 첫 깊이 구간 날수 215→217, 사건 26→27이 된다. 이는 사건 간격의 불확실한 추정이 아니라 코드 및 날짜로 확인한 이력 절단 차이다.', '',
              '**직접 확인 2 — 거래량 0 진입:** 기존 코드는 거래량을 읽지 않아 양수 종가만 있으면 진입에 포함한다. 독립 기본판은 다음날 거래량>0을 요구한다. 아래에서 이 조건 하나만 풀면 수익 차이 대부분이 사라진다. 깊은 구간의 >0.5%p 차이를 같은 정의의 계산 오류라고 볼 수 없다.', '',
              '**직접 확인 3 — 종목 진입·상폐 세부:** 기존판은 신호일 가격 없이 다음날 신규 관측된 종목도 포함하고 `meta.note`의 delisted 표식 종목 가격을 전방채움한다. 독립판은 신호일 가격을 요구하고 실제 meta.delisted 날짜가 보유기간 안인 경우에만 말기 끝값을 쓴다. 이 정의들까지 정렬하고 지수 시작 이력도 기존판과 맞추면 아래 세 표의 평균·사건 수가 모두 CSV 반올림 범위 안에서 재현된다.', '',
              '아래 A→B는 진입 거래량 조건만 변경, B→C는 종목 진입·상폐 세부를 정렬, C→D는 지수 이력 시작점까지 정렬한 단계다. A~C는 Codex 사건/날 집합 고정이고 D에서만 기존 집합으로 바뀐다. 원인 분해용 기술통계이며 새 성과 추정이 아니므로 별도 CI를 붙이지 않았다.']
    table(lines, ['표/집합', 'n(A~C)', 'A 독립 기본', 'B 거래량0 허용', 'C 진입·상폐도 정렬', 'D 지수 시작도 정렬'], causes)
    lines += [f'정렬 후 12개 표 행 평균과 기존 CSV 저장값의 최대 절대차 = {max(checks):.6f}%p(두 자리 반올림 범위 0.005%p 이내), 날수·사건 수 전부 일치. 원래 독립 본문의 0.5%p 초과 차이는 코스피 날 (−15,−10]·(−20,−15]·≤−20, 코스피 사건 ≤−5·≤−15·≤−20, 코스닥 사건 ≤−15·≤−20이다. 사건 수 차이는 코스피 ≤−5 한 칸이다.', '',
              '**해석:** 코스피 하한을 둘 증거가 없다는 제한적 결론은 일치한다. 다만 코스닥의 “단독 하락은 실패”라는 일반화는 추가한 분리표(단독 4/5 플러스, 넓은 구간)가 뒷받침하지 않는다. 특정 2026-05 하락 실패 사례와 단독 하락 전체의 효과는 구분해야 한다. 상폐 −90%판·불연속 제외판은 두 연구의 세부 처리도 달라, 값이 정확히 같은 감도 실험으로 부르지 않는다.', '',
              '수정 범위: 이 REPLY 및 동명의 재현 Python 두 파일만 새로 작성. 저장소 기존 파일·DB·docs·worklog·운영 코드는 변경하지 않았다. 커밋·푸시·전송 없음. 계산 중간 대용량 파일 없음.', '',
              '사후 정렬 재현: `python -B research/handoff/code_20261030_crash_depth_blind.py --comparison-audit` (본문 REPLY와 원 연구 CSV가 필요하며 §7만 갱신). 최초 독립 재현에는 이 옵션을 쓰지 않는다.']
    assert fingerprint(DATA / 'ohlcv_10y.db') == s.before
    guard(batch_finished)
    REPORT.write_text(body.rstrip() + '\n\n' + '\n'.join(lines) + '\n', encoding='utf-8')
    print('comparison max difference', max(checks))
    print('comparison source body sha256', independent_hash)
    print('written', REPORT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-finished', action='store_true', help='Only after explicit user confirmation that the batch finished.')
    parser.add_argument('--comparison-audit', action='store_true', help='Only AFTER independent report is complete; reads original table CSVs and appends comparison.')
    args = parser.parse_args()
    guard(args.batch_finished)
    if args.comparison_audit:
        comparison_audit(args.batch_finished)
        return
    previous = REPORT.read_text(encoding='utf-8') if REPORT.exists() else ''
    comparison = COMPARE_MARKER + previous.split(COMPARE_MARKER, 1)[1] if COMPARE_MARKER in previous else ''
    s = Study()
    lines = ['# REPLY — 급락 깊이 독립 재현과 세 갈래 확장', '',
             '요청: `REQUEST_20261030_crash_depth_blind.md`. 작성일: 2026-10-30. 아래 숫자는 지정 DB를 직접 계산한 **실측**이다. 표본 밖 예측·새 규칙·매매 권고가 아니다.', '',
             '**눈가림 한계:** 저장소 필수 시작 절차로 읽은 `worklog/README.md`와 최신 기록에 Claude의 핵심 수치·결론이 이미 실려 있었다. 따라서 완전한 눈가림 재현이라고 부를 수 없다. 지정된 연구 보고서·코드·출력 폴더는 본문 계산·해석을 작성한 뒤 §7 대조 단계에서만 접근한다. 계산 코드는 요청서 정의로 새로 작성했고 기존 연구 함수를 가져오지 않았다.', '',
             '**작업 시간:** 사용자가 배치 종료를 확인하고 진행을 명시적으로 허용했다. DB는 전부 `mode=ro` + `PRAGMA query_only=ON`. history.db·PTW·수집기·운영 점수 코드는 열거나 실행하지 않았다.', '',
             '## 0. 정의와 자료 품질 처리', '',
             f"주 자료: `{DATA / 'ohlcv_10y.db'}`. 가격 원표 범위/행수 `{s.price_bounds}`. 지수 `{json.dumps(s.index_bounds, ensure_ascii=False)}`. 20261022 이후 자료는 사용하지 않는다. 필터 후 종목 {s.N:,}개, 가격 {s.kept_rows:,}행, 실제 바구니 시작일 {s.dates[s.start]}. 지수 시작일부터 빈 바구니 사건을 선택하지 않는다.", '',
             '신호일 t → t+1 종가 진입 → t+h+1 종가 청산(주 분석 h=40). 거래일은 두 지수 공통 날짜 축이다. 비용·배당은 반영하지 않은 종가 수익이며, 기간마다 동일가중 바구니를 새로 계산한다. 사건은 같은 문턱을 만족하는 날짜 중 마지막 **선택한 사건**에서 ≥40거래일인 첫날이다. 미완결 사건도 먼저 선택하고 이후 해당 보유기간의 결과에서 제외한다. 따라서 기간 간 사건 선택 기준은 같다. 40일 간격의 두 투자 창은 경계 종가 한 번을 공유할 수 있다.', '',
             '사건 평균 95% 구간은 사건 동일확률 복원추출 4,000회(시드 20261030)의 백분위다. 시장·문턱·기간을 가로지르는 다중비교 보정은 없고, 적은 사건의 구간은 미관측 위기를 포괄하지 않는다. n=1 구간이 한 점인 경우 불확실성이 없다는 뜻이 아니다. 날 표는 겹침 때문에 구간을 붙이지 않는다. 수익 단위 %, 차이 단위 %p.']
    table(lines, ['쟁점', '이번 처리', '남는 한계'], [
        ['유니버스', '코스피·코스닥(+KOSDAQ GLOBAL), 코드 끝 0, 요청서 이름 제외어(대소문자 무관)', '종목명 문자열은 업종 판별 대리값이다'],
        ['가격 불연속', f'기본판은 저장 종가 유지. 인접 거래일 절대변화 >35% {s.jump_count}셀 중 폐지 전 30달력일 밖 {s.nonterminal_jump_count}셀을 통과한 보유 건 제외 감도 별도', '원인 미확인. 청산 전 급락을 제거해 손실을 지우지 않도록 폐지 전 30일은 유지. 감도는 사후 자료 품질 점검이며 실행 규칙 아님'],
        ['진입·중간 결측', 't 가격과 t+1 양수 종가·양수 거래량 필요. 내부 결측 전방채움 없음', '정지 중 신호라도 다음날 거래되면 진입 가능하다고 가정. 가격 없는 신규상장은 제외'],
        ['40일 안 상폐', 'meta.delisted가 진입 다음~목표 청산일 사이이면 마지막 저장 가격 / 진입금액 대비 −90% 두 판', '폐지 사유·현금 회수액 미확인. −90%는 손실 상한도 하한도 아님'],
        ['폐지 끝값 거래량 0', '마지막 가격 판에 유지하되 건수 집계, −90%판 병기', '실제 그 가격에 매도 가능함을 뜻하지 않음'],
        ['목표일 결측·미완결', 't+h+1이 종목 가격 원표 마지막 날 이후면 날/사건 제외. 개별 종목은 상폐 처리 외 목표 종가 없으면 그 종목 제외', '미상 결측 종목을 빼는 편향은 별도 건수로 공개. 청산일 거래량 0인 저장 가격도 평가에 쓰므로 실제 체결 성과가 아님'],
        ['영문 코드 누락 88', '10/23 품질 답의 누락을 인정하고 외부·운영 자료로 메우지 않음', '88종목을 포함한 결과는 확인 못 함'],
        ['현재 시장명 소급', 'meta.market를 명시적인 대리 분류로 사용. 합동 바구니를 주 결과로, 코스닥만은 보조로', '과거 시장 소속 이력이 없으므로 코스닥 단독 바구니를 당시 구성의 재현으로 부르지 않음'],
        ['과매도·상위20%', '신호일 종목 R20 유효 종목을 정렬, floor(0.2×n)개씩. 동률은 코드순', '신호일 정보만으로 분류. 전 종목 비교와 R20 가용 종목 비교를 함께 제시'],
    ])
    lines += ['## 1. 깊이 구간별 날 단위', '', '두 시장 모두 합동 바구니를 사용한다. 지수 자체는 신호를 낸 시장 지수이며 같은 t+1→t+41 기준이다. n종목은 날별 결과 유효 종목 수의 최소~최대다.']
    rows = []
    depth_bins = [(-10, -5, '(−10,−5]'), (-15, -10, '(−15,−10]'), (-20, -15, '(−20,−15]'), (-np.inf, -20, '≤−20')]
    daysets = {}
    for market, name in enumerate(('KOSPI', 'KOSDAQ')):
        signal = s.signals[20][:, market]
        for lower, upper, label in depth_bins:
            ts = np.flatnonzero((signal > lower) & (signal <= upper))
            ts = s.complete(ts[ts >= s.start])
            daysets[(market, label)] = ts
            for policy in POLICIES:
                a = np.array([s.basket(t, policy=policy) for t in ts])
                ns = [int(np.isfinite(s.returns(t, policy=policy)).sum()) for t in ts]
                ir = [s.index_return(t, 40, market) for t in ts]
                rows.append([name, label, LABEL[policy], len(ts), f'{min(ns)}~{max(ns)}' if ns else '0', fmt(np.mean(a)), fmt(np.median(a)), f'{(a>0).sum()}/{len(a)} ({100*(a>0).mean():.1f}%)', fmt(a.min()), fmt(np.mean(ir))])
    table(lines, ['신호', 'R20%', '상폐판', 'n날', 'n종목', '평균', '중앙', '플러스', '최악', '지수 평균'], rows)

    lines += ['## 2. 누적 문턱별 사건 단위']
    eventsets = {}
    rows, dates_rows = [], []
    for market, name in enumerate(('KOSPI', 'KOSDAQ')):
        for threshold in (-5, -10, -15, -20):
            events = s.events(market, 20, threshold)
            ts = s.complete(events)
            eventsets[market, threshold] = ts
            for policy in POLICIES:
                a = [s.basket(t, policy=policy) for t in ts]
                st = stats(a)
                rows.append([name, threshold, LABEL[policy], len(ts), cell(a), f"{st['pos']}/{st['n']}", fmt(st['worst']), cell([s.index_return(t, 40, market) for t in ts])])
            dates_rows.append([name, threshold, ', '.join(s.dates[ts]), ', '.join(s.dates[np.setdiff1d(events, ts)]) or '없음'])
    table(lines, ['신호', 'R20≤', '상폐판', 'n사건', '바구니 평균 [95%]', '플러스', '최악', '지수 평균 [95%]'], rows)
    table(lines, ['신호', '문턱', '완결 사건 날짜', '미완결/바구니 없음'], dates_rows)

    lines += ['## 3. 깊이와 수익의 순위상관', '', 'R20 원래 부호로 계산하므로 **음수 상관 = 더 깊은 낙폭일수록 이후 수익이 높았음**이다. 날은 R20≤−5인 완결 날 전부, 사건은 ≤−5 사건만 사용한다. 누적 문턱의 사건을 합쳐 중복 집계하지 않는다.']
    rows = []
    for market, name in enumerate(('KOSPI', 'KOSDAQ')):
        sig = s.signals[20][:, market]
        days = np.flatnonzero((sig <= -5) & (np.arange(s.T) >= s.start))
        for unit, ts in [('날', s.complete(days)), ('사건', eventsets[market, -5])]:
            for policy in POLICIES:
                a = np.array([s.basket(t, policy=policy) for t in ts])
                r = rho(sig[ts], a)
                interval = '겹침: 미제공'
                if unit == '사건':
                    lo, hi = rho_ci(sig[ts], a)
                    interval = f'[{fmt(lo, 3)}, {fmt(hi, 3)}]'
                rows.append([name, unit, LABEL[policy], len(ts), fmt(r, 3), interval])
    table(lines, ['신호', '단위', '상폐판', 'n', 'Spearman ρ', '95%'], rows)
    lines += ['해석: 두 시장 모두 날 평균은 깊을수록 높았지만 사건 단위 상관의 95% 구간은 0을 포함한다. 따라서 이 표본에서 하한은 발견하지 못했으며, 깊을수록 반드시 좋아진다는 일반 법칙까지 가를 수 없다. 날 단위 상관은 서로 겹치는 보유기간의 기술통계다.']

    lines += ['## 4. 확장 세 갈래', '', '### ① 코스닥 단독 하락과 동반 하락', '', '코스닥 R20≤−10 사건을 먼저 40일 간격으로 뽑고, 그날 코스피 R20≤−5이면 동반으로 나눈다. 각 그룹 안에서 사건을 새로 뽑지 않는다.']
    qts = eventsets[1, -10]
    groups = {'동반': qts[s.signals[20][qts, 0] <= -5], '단독': qts[s.signals[20][qts, 0] > -5]}
    rows = []
    for group, ts in groups.items():
        for q, basket_name in [(False, '합동'), (True, '코스닥만')]:
            for policy in POLICIES:
                a = [s.basket(t, policy=policy, q=q) for t in ts]
                st = stats(a)
                rows.append([group, basket_name, LABEL[policy], len(ts), cell(a), f"{st['pos']}/{st['n']}", fmt(st['worst'])])
    table(lines, ['그룹', '바구니', '상폐판', 'n사건', '평균 [95%]', '플러스', '최악'], rows)
    lines += ['사건 날짜: ' + ' / '.join(k + ': ' + ', '.join(s.dates[v]) for k, v in groups.items()) + '。']
    lines += ['해석: 단독도 5건 중 4건이 플러스여서 “단독이면 실패”는 재현되지 않았다. 단독 평균은 동반보다 낮고 손실 사건이 크지만 구간이 넓어 제외 규칙의 효과를 확정할 수 없다.']

    lines += ['### ② 7거래일 정의와 20거래일 정의', '',
              '외부 원문은 요청에 따라 조회하지 않았다. **요청서에 제시된 7거래일 지수 수익 문턱을 재계산**한 것이며 유안타 원문의 기간·사건 추출·진입시점까지 재현했다는 뜻은 아니다. 두 지수, 두 신호 기간, 두 문턱만 사용한다. 모든 보유기간은 t+1 종가 진입이고 사건 간격은 40일로 고정한다. n은 해당 보유기간 완결 사건 수; 괄호의 공통n은 40일도 완결인 사건 수다.']
    rows = []
    ext = {}
    for market, name in enumerate(('KOSPI', 'KOSDAQ')):
        for window in (7, 20):
            for threshold in (-10, -15):
                events = s.events(market, window, threshold)
                common = s.complete(events)
                for h in (5, 20, 40):
                    ts = s.complete(events, h)
                    ix = [s.index_return(t, h, market) for t in ts]
                    last = [s.basket(t, h, 'last') for t in ts]
                    loss = [s.basket(t, h, 'loss90') for t in ts]
                    ext[market, window, threshold, h] = (ts, ix, last, loss)
                    rows.append([name, f'R{window}≤{threshold}', h, f'{len(ts)} ({len(common)})', cell(ix), f'{sum(x>0 for x in ix)}/{len(ix)}', cell(last), cell(loss)])
    table(lines, ['신호', '정의', '보유일', 'n(공통n)', '지수 [95%]', '지수 플러스', '바구니 마지막 [95%]', '바구니 −90 [95%]'], rows)
    lines += ['7거래일 사건 날짜(40일 완결 / 미완결):']
    for market, name in enumerate(('KOSPI', 'KOSDAQ')):
        for threshold in (-10, -15):
            e = s.events(market, 7, threshold)
            done = s.complete(e)
            lines.append(f'- {name} ≤{threshold}: ' + ', '.join(s.dates[done]) + ' / ' + (', '.join(s.dates[np.setdiff1d(e, done)]) or '없음'))
    lines += ['', '공통 사건만의 5일·20일 결과(최근 미완결 사건이 단기 평균에만 들어가는 영향 분리):']
    rows = []
    for market, name in enumerate(('KOSPI', 'KOSDAQ')):
        for window in (7, 20):
            for threshold in (-10, -15):
                ts = s.complete(s.events(market, window, threshold))
                for h in (5, 20):
                    rows.append([name, f'R{window}≤{threshold}', h, len(ts), cell([s.index_return(t, h, market) for t in ts]), cell([s.basket(t, h) for t in ts])])
    table(lines, ['신호', '정의', '보유일', '공통n', '지수 [95%]', '바구니 마지막 [95%]'], rows)
    e7_10_20 = ext[0, 7, -10, 20]
    e7_10_40 = ext[0, 7, -10, 40]
    e7_15_20 = ext[0, 7, -15, 20]
    lines += [f"해석: 코스피 R7≤−10의 같은 완결 n={len(e7_10_20[0])}사건에서 20일 지수 {cell(e7_10_20[1])}가 40일 {cell(e7_10_40[1])}로 부호가 바뀐다(기간 효과). R7≤−15·20일은 같은 n={len(e7_15_20[0])}사건이라도 지수 {cell(e7_15_20[1])}, 바구니 {cell(e7_15_20[2])}로 크기가 다르다(대상 효과). R20 정의는 사건 날짜와 개수 자체가 달라진다. 외부 1/5는 이 DB·기간·40일 간격 정의에서 재현되지 않았으며, 원문 미확인으로 그 다섯 건과 왜 다른지는 확정할 수 없다."]

    lines += ['### ③ 깊은 코스피 사건 안의 종목 선택', '',
              '코스피 ≤−10 사건을 기준으로 그 사건일 R20≤−15인 하위 집합을 깊은 사건으로 정의한다. **≤−15 문턱으로 따로 추출한 사건과 다르다.** 따라서 두 집합 모두 보고하며 서로 합치지 않는다. 과매도·상위 20% 구성은 미래 수익이 없는 종목까지 신호일 R20으로 먼저 정하고, 결과 가용 여부는 그 뒤 적용한다. `R20 가용 전체`와의 차이는 종목 이력 부족의 영향을 분리한 짝비교다.']
    picksets = {'≤−10 사건': eventsets[0, -10], '그중 신호일 ≤−15': eventsets[0, -10][s.signals[20][eventsets[0, -10], 0] <= -15], '별도 ≤−15 사건': eventsets[0, -15]}
    picks = {}
    event_rows, summary_rows = [], []
    for setname, ts in picksets.items():
        for policy in POLICIES:
            values = []
            for t in ts:
                ret = s.returns(t, policy=policy)
                # Construct groups from signal-day information, before examining future returns.
                eligible = np.flatnonzero(np.isfinite(s.r20[t]) & np.isfinite(s.p[t]))
                ranked = eligible[np.argsort(s.r20[t, eligible], kind='stable')]
                k = int(len(ranked) * .2)
                lo, hi = ranked[:k], ranked[-k:]
                all_mean = np.nanmean(ret)
                matched = np.nanmean(ret[ranked])
                low, high = np.nanmean(ret[lo]), np.nanmean(ret[hi])
                vals = [all_mean, matched, low, high, low-all_mean, high-all_mean, low-matched, high-matched]
                values.append(vals)
                if setname in ('≤−10 사건', '별도 ≤−15 사건'):
                    event_rows.append([setname, s.dates[t], LABEL[policy], fmt(s.signals[20][t, 0]), f'{np.isfinite(ret).sum()}/{len(ranked)}/{k}', f'{np.isfinite(ret[lo]).sum()}/{np.isfinite(ret[hi]).sum()}', *[fmt(x) for x in vals]])
            arr = np.array(values).reshape((-1, 8))
            picks[setname, policy] = arr
            summary_rows.append([setname, LABEL[policy], len(ts)] + [cell(arr[:, j]) for j in range(8)])
    table(lines, ['사건 집합', '상폐판', 'n사건', '전 종목 [95%]', 'R20 가용 전체 [95%]', '과매도 [95%]', '상위20 [95%]', '과매도−전체 [95%]', '상위−전체 [95%]', '과매도−가용 [95%]', '상위−가용 [95%]'], summary_rows)
    table(lines, ['집합', '날짜', '상폐판', '지수R20', 'n전체/순위가능/선정각각', 'n과매도/상위 결과', '전체', '가용전체', '과매도', '상위', '과−전체', '상−전체', '과−가용', '상−가용'], event_rows)
    lines += ['해석: ≤−10의 첫 진입 사건 중 그날 이미 ≤−15인 사건은 0건이다. 별도 ≤−15 문턱의 4사건에서는 과매도 바구니가 전 종목보다 모두 더 반등했다. 이를 처음 −10%를 넘던 시점에 알 수 있는 분류로 바꿔 읽으면 안 된다.']

    lines += ['### 보조. 이번 2026-10 사건의 운영 지수 경로', '', '운영 `ohlcv.db.market_daily`의 KOSPI만 별도 계산했다. 주 자료나 바구니와 이어 붙이지 않았다. 같은 달 첫 문턱 도달을 기점으로 하며 과거 40일 간격 사건의 연장이 아니다. 현재값은 조회 시 저장된 마지막 종가다.']
    op = DATA / 'ohlcv.db'
    op_before = fingerprint(op)
    c = connect(op)
    frame = pd.read_sql_query("SELECT date,close FROM market_daily WHERE series='KOSPI' ORDER BY date", c)
    c.close()
    op_after = fingerprint(op)
    dates = frame.date.to_numpy()
    p = frame.close.to_numpy()
    r = np.full(len(p), np.nan)
    r[20:] = (p[20:] / p[:-20] - 1) * 100
    rows = []
    for threshold in (-5, -10, -15, -20):
        candidates = np.flatnonzero((dates >= '20261001') & (dates <= '20261031') & (r <= threshold))
        if len(candidates):
            t = candidates[0]
            current = (p[-1] / p[t+1] - 1) * 100 if t+1 < len(p) else np.nan
            rows.append([threshold, dates[t], fmt(r[t]), dates[t+1] if t+1 < len(p) else '없음', f'{p[t+1]:.2f}' if t+1<len(p) else '없음', dates[-1], f'{p[-1]:.2f}', fmt(current), f'{len(p)-t-2}/40'])
    table(lines, ['R20≤', '첫 도달', '당일R20', '다음날 매수', '매수 종가', '최신일', '최신 종가', '누적%', '경과'], rows)
    lines += ['이 네 행은 같은 10월 하락 경로의 문턱별 표시이며 독립 사건 4개가 아니다. 미완결 값에 과거 사건 부트스트랩 구간을 붙이지 않는다.']

    lines += ['## 5. 의견 — 관측 범위 안의 답', '']
    kp10 = [s.basket(t) for t in eventsets[0, -10]]
    kp20 = [s.basket(t) for t in eventsets[0, -20]]
    q_alone = [s.basket(t) for t in groups['단독']]
    q_together = [s.basket(t) for t in groups['동반']]
    e7 = ext[0, 7, -15, 20]
    e20 = ext[0, 20, -15, 20]
    lowdeep = picks['별도 ≤−15 사건', 'last'][:, 4]
    lines += [f"코스피 ≤−10 사건은 n={len(kp10)}, 평균 {cell(kp10)}, 플러스 {sum(x>0 for x in kp10)}/{len(kp10)}이며 ≤−20은 n={len(kp20)}, {cell(kp20)}다. 이 표본에서는 깊은 낙폭을 제외할 하한 근거를 찾지 못했지만 가장 깊은 사건 수가 적어 안전한 하한을 확정할 수는 없다. 코스닥 단독은 n={len(q_alone)}, {cell(q_alone)}, 동반은 n={len(q_together)}, {cell(q_together)}로 비교된다. 단독도 4/5가 플러스이므로 단독 실패 주장은 지지하지 않는다. 기존 제외 규칙은 이번 검토에서 변경하지 않지만, 이 비무작위 소표본이 그 효과를 입증한 것도 아니다. 외부 정의의 코스피 R7≤−15·20일 지수는 n={len(e7[0])}, {cell(e7[1])}, 상승 {sum(x>0 for x in e7[1])}/{len(e7[1])}; R20≤−15는 n={len(e20[0])}, {cell(e20[1])}다. 따라서 요청서의 외부 주장 1/5와의 비교는 지수/바구니, 신호·보유기간, 사건 날짜 및 조사기간 차이를 함께 봐야 한다. 원문과 그 다섯 날짜가 없어 차이의 단일 원인은 확인 못 함이다. 별도 ≤−15 사건에서 과매도−전체는 n={len(lowdeep)}, {cell(lowdeep)}이며, 이는 대리 바구니 결과이지 v30의 재현이나 채택 판정이 아니다. 새 규칙은 제안하지 않는다."]

    lines += ['## 6. 자료 품질 감도와 검증', '', '아래 감도는 보유 중 폐지 전 30일 밖의 >35% 불연속이 있는 종목만 그 보유 건에서 뺀다. 기본판의 종료값이나 사건 날짜는 바꾸지 않는다. 기본/감도 차이는 같은 사건의 평균 차이를 부트스트랩했다.']
    rows = []
    for market, name in enumerate(('KOSPI', 'KOSDAQ')):
        for threshold in (-5, -10, -15, -20):
            ts = eventsets[market, threshold]
            for policy in POLICIES:
                base = np.array([s.basket(t, policy=policy) for t in ts])
                clean = np.array([s.basket(t, policy=policy, clean=True) for t in ts])
                rows.append([name, threshold, LABEL[policy], len(ts), cell(base), cell(clean), cell(clean-base)])
    table(lines, ['신호', '문턱', '상폐판', 'n', '기본 [95%]', '불연속 제외 [95%]', '제외−기본 [95%]'], rows)
    # Quality counters cover unique main-analysis signal dates, not repeated tables or policies.
    ts = sorted(set(t for v in daysets.values() for t in v))
    counts = {k: 0 for k in ('entry', 'missing', 'terminal', 'terminal_zero', 'badpath')}
    for t in ts:
        s.returns(t)
        for key in counts:
            counts[key] += s.audit[t, 40, 'last', False][key]
    lines += [f"날 단위 두 시장 급락 신호 합집합 {len(ts)}일의 중복 없는 종목×진입 집계: `{json.dumps(counts, ensure_ascii=False)}`. entry=진입 가능, missing=상폐 처리 후에도 목표 수익 결측, terminal=기간 내 상폐, terminal_zero=그중 마지막 저장 거래량 0, badpath=비말기 불연속 통과. 사건 표끼리 또는 상폐판끼리 중복해서 센 값이 아니다.", '']
    # Independent scalar SQL check for sample event baskets (no matrix used).
    verify = []
    c = connect(DATA / 'ohlcv_10y.db')
    for t in [eventsets[0, -10][0], eventsets[0, -20][0], eventsets[1, -10][-1]]:
        d0, d1, d2 = s.dates[t], s.dates[t+1], s.dates[t+41]
        sql = '''SELECT p.ticker,p.close,e.close,e.volume,z.close,m.delisted,
                 (SELECT close FROM prices q WHERE q.ticker=p.ticker AND q.date<=? ORDER BY date DESC LIMIT 1)
                 FROM prices p JOIN prices e ON e.ticker=p.ticker AND e.date=?
                 JOIN meta m ON m.ticker=p.ticker LEFT JOIN prices z ON z.ticker=p.ticker AND z.date=?
                 WHERE p.date=?'''
        raw = c.execute(sql, (CUTOFF, d1, d2, d0)).fetchall()
        a, b = [], []
        for ticker, p0, buy, vol, sell, dl, last_price in raw:
            if ticker not in set(s.tickers) or not p0 or p0<=0 or not buy or buy<=0 or not vol or vol<=0:
                continue
            dl = (dl or '').replace('-', '')
            if dl and dl <= d1:
                continue
            terminal = d1 < dl <= d2
            if terminal:
                sell = last_price
            if sell and sell > 0:
                a.append((sell/buy-1)*100)
                b.append(-90.0 if terminal else (sell/buy-1)*100)
        assert len(a) == np.isfinite(s.returns(t)).sum()
        assert abs(np.mean(a)-s.basket(t)) < 1e-10
        assert abs(np.mean(b)-s.basket(t, policy='loss90')) < 1e-10
        verify.append([d0, len(a), fmt(np.mean(a), 8), fmt(np.mean(b), 8), '<1e−10'])
    c.close()
    table(lines, ['별도 SQL 검산 사건', 'n종목', '마지막 가격', '−90%', '행렬 계산과 오차'], verify)
    # Verify temporal and selection invariants.
    assert all(np.all(np.diff(v) >= 40) for v in eventsets.values())
    assert all(all(t+41 < s.T for t in v) for v in eventsets.values())
    assert set(groups['동반']).isdisjoint(groups['단독'])
    assert set(groups['동반']) | set(groups['단독']) == set(qts)
    after = fingerprint(DATA / 'ohlcv_10y.db')
    assert s.before == after, '주 DB 크기/수정 시각 변화'
    assert op_before == op_after, '운영 DB 조회 중 크기/수정 시각 변화'
    lines += ['검증: 사건 간격 ≥40, 미래 종료일 가용성, 코스닥 그룹의 중복 없음·전체 합 일치, 세 사건의 별도 SQL 직접 합산과 행렬 결과 일치를 확인했다. 이 검산은 처리 방침의 적절성이나 원자료의 경제적 진실성을 증명하지 않는다.', '',
              '주 DB 전후 식별값: `' + json.dumps(after) + '`. 운영 지수 조회 전후 식별값: `' + json.dumps(op_after) + '`. 모두 크기·수정 시각 동일. 연결은 읽기 전용이다.', '',
              '재현 명령: `python -B research/handoff/code_20261030_crash_depth_blind.py` (평일 금지 시간에는 중단; 사용자의 실제 배치 종료 확인이 있을 때만 `--batch-finished`). 이 스크립트는 지정 REPLY만 쓴다. 큰 중간 파일·캐시 파일을 만들지 않는다. §7이 이미 있으면 재계산 때 보존하므로, 입력이 바뀐 재실행에서는 §7 대조를 수동 갱신해야 한다.', '',
              '질문/확인 못 함: 당시 종목 시장명·영문 코드 누락의 반사실 결과·폐지 사유와 실제 회수액·유안타 원문 및 다섯 사건 날짜. 진행을 막는 질문은 아니므로 추가 조회 없이 한계로 남겼다. 운영 규칙·모델·점수·게이트·docs·worklog는 수정하지 않았다.']
    guard(args.batch_finished)
    content = '\n'.join(lines) + '\n'
    REPORT.write_text(content + comparison, encoding='utf-8')
    print('REPORT', REPORT)
    print('PRE_COMPARE_SHA256', hashlib.sha256(content.encode()).hexdigest())
    print('KOSPI10', stats(kp10), 'KOSPI20', stats(kp20))
    print('KOSDAQ_ALONE', stats(q_alone), 'TOGETHER', stats(q_together))
    print('EXTERNAL_R7_15_H20', stats(e7[1]))
    print('DEEP_OVERSOLD_DIFF', stats(lowdeep))


if __name__ == '__main__':
    main()
