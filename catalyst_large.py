# -*- coding: utf-8 -*-
"""
catalyst_large.py — 대형 가치주 트랙: 자사주 '소각' 전수 스캔 (DART 네트워크 필요)
====================================================================================
large_universe(시총 상위, 기본 500)의 전 종목에 대해 자사주 소각 공시 여부를 수집한다.

설계 원칙:
  - v3 파이프라인 무접촉: catalyst_{mkt}_{run_id}.csv 는 '읽기만'(같은 날 v3 후보와
    겹치는 종목은 그 결과를 복사해 DART 재호출 0회). 산출은 별도 파일.
  - 내부자(elestock) 경로는 이 스크립트에 존재하지 않음 — §4-A 결정(자사주 소각만).
  - 점수화/판단 없음: 플래그 수집만. large_score.py 가 관측 컬럼으로 조인한다.
  - DART 예절: catalyst_insider 와 동일(병렬 2스레드, 건당 sleep 0.05). 검증된
    catalyst_insider.score_buyback_cancel / stage2 배관(get_corp_code_mapping,
    fetch_disclosures)을 그대로 재사용한다(소각 탐지 로직 복제 금지).

산출: catalyst_large_{run_id}.csv
  컬럼: ticker, name, market, buyback_cancel_flag, buyback_cancel_dt, buyback_src
  buyback_src: 'dart'(신규 스캔) | 'v3공유'(v3 catalyst 복사) | '미등록'(DART 매핑
  없음, flag=NaN) | '실패'(개별 호출 실패, flag=NaN — 에러값 저장 안 함, 다음 날 재시도)

실행 (.bat 끝에서 large_universe.py 다음, large_score.py 이전):
    python catalyst_large.py                # run_id = large_universe 최신 run
    python catalyst_large.py --days 90
"""
import argparse
import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

# 검증된 로직 재사용 (네트워크 없이 import 가능)
from catalyst_insider import load_env, score_buyback_cancel, DEFAULT_DAYS, MAX_WORKERS

DB_PATH = Path("history.db")


# ============================================================
# 로드 / 분할 (순수 — 오프라인 검증 대상)
# ============================================================
def latest_universe_run(db_path=DB_PATH):
    with sqlite3.connect(db_path) as con:
        rid = con.execute("SELECT MAX(run_id) FROM large_universe").fetchone()[0]
    if not rid:
        raise RuntimeError("large_universe 가 비어 있음 — 먼저 python large_universe.py 실행")
    return str(rid)


def load_large_tickers(run_id, db_path=DB_PATH):
    with sqlite3.connect(db_path) as con:
        df = pd.read_sql(
            "SELECT ticker, name, market FROM large_universe WHERE run_id=? ORDER BY marcap_rank",
            con, params=(str(run_id),))
    if df.empty:
        raise RuntimeError(f"large_universe 에 run_id={run_id} 없음")
    df['ticker'] = df['ticker'].astype(str).str.zfill(6)
    return df


def load_v3_catalyst(run_id):
    """같은 날 v3 catalyst CSV(있으면)에서 소각 결과를 읽는다 — 읽기 전용."""
    frames = []
    for mkt in ('kospi', 'kosdaq'):
        p = Path(f"catalyst_{mkt}_{run_id}.csv")
        if p.exists():
            c = pd.read_csv(p, encoding='utf-8-sig', dtype={'ticker': str})
            c['ticker'] = c['ticker'].str.zfill(6)
            keep = [x for x in ('ticker', 'buyback_cancel_flag', 'buyback_cancel_dt') if x in c.columns]
            frames.append(c[keep])
    if not frames:
        return pd.DataFrame(columns=['ticker', 'buyback_cancel_flag', 'buyback_cancel_dt'])
    return pd.concat(frames, ignore_index=True).drop_duplicates('ticker')


def split_reuse(uni, v3df):
    """v3 결과가 있는 종목은 복사(src='v3공유'), 나머지만 신규 스캔 대상으로 분리."""
    if v3df.empty:
        todo = uni.copy()
        reused = pd.DataFrame(columns=list(uni.columns) +
                              ['buyback_cancel_flag', 'buyback_cancel_dt', 'buyback_src'])
        return reused, todo
    hit = uni['ticker'].isin(set(v3df['ticker']))
    reused = uni[hit].merge(v3df, on='ticker', how='left')
    reused['buyback_src'] = 'v3공유'
    todo = uni[~hit].copy()
    return reused, todo


# ============================================================
# DART 스캔 (네트워크 — 사용자 PC 전용)
# ============================================================
def scan_dart(todo, api_key, days, workers):
    """catalyst_insider.run_market 의 자사주 경로만 미러링(내부자 경로 없음)."""
    import importlib
    stage2 = importlib.import_module("stage2_risk_filter_v2_6")   # 기업코드/공시목록 재사용

    corp = stage2.get_corp_code_mapping(api_key)
    corp['stock_code'] = corp['stock_code'].str.zfill(6)
    todo = todo.merge(corp[['stock_code', 'corp_code']],
                      left_on='ticker', right_on='stock_code', how='left')
    unreg = todo[todo['corp_code'].isna()].copy()
    if len(unreg):
        print(f"   ⚠️  DART 미등록 {len(unreg)}개 (flag=NaN, src='미등록')")
        unreg['buyback_cancel_flag'] = np.nan
        unreg['buyback_cancel_dt'] = ''
        unreg['buyback_src'] = '미등록'
    work = todo.dropna(subset=['corp_code']).to_dict('records')
    total = len(work)
    print(f"   {total}개 신규 스캔 (병렬 {workers}스레드, 윈도 {days}일, 종목당 DART 1회)")

    results, done = [], 0
    lock = threading.Lock()
    t0 = time.time()

    def one(r):
        time.sleep(0.05)
        discs, _dart = stage2.fetch_disclosures(r['corp_code'], api_key, days_back=days)  # (목록, fetch_status) 2-튜플 언팩
        buy = score_buyback_cancel(discs, days=days)
        return {'ticker': r['ticker'], 'name': r['name'], 'market': r['market'],
                'buyback_cancel_flag': float(buy['buyback_cancel_flag']),
                'buyback_cancel_dt': buy['buyback_cancel_dt'], 'buyback_src': 'dart'}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(one, r): r for r in work}
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"   ⚠️  {r.get('name', r['ticker'])} 실패: {e}")
                results.append({'ticker': r['ticker'], 'name': r['name'], 'market': r['market'],
                                'buyback_cancel_flag': np.nan, 'buyback_cancel_dt': '',
                                'buyback_src': '실패'})
            with lock:
                done += 1
                if done % 50 == 0 or done == total:
                    el = time.time() - t0
                    eta = (el / done) * (total - done) if done else 0
                    print(f"   [{done}/{total}] {el:.0f}s, 남은 ~{eta:.0f}s")

    scanned = pd.DataFrame(results) if results else pd.DataFrame(
        columns=['ticker', 'name', 'market', 'buyback_cancel_flag', 'buyback_cancel_dt', 'buyback_src'])
    cols = ['ticker', 'name', 'market', 'buyback_cancel_flag', 'buyback_cancel_dt', 'buyback_src']
    return pd.concat([scanned[cols], unreg[cols]] if len(unreg) else [scanned[cols]],
                     ignore_index=True)


# ============================================================
def save_csv(reused, scanned, uni, run_id):
    cols = ['ticker', 'name', 'market', 'buyback_cancel_flag', 'buyback_cancel_dt', 'buyback_src']
    out = pd.concat([reused[cols]] + ([scanned[cols]] if len(scanned) else []), ignore_index=True)
    out = out.drop_duplicates('ticker')
    # 유니버스 순서 보존(시총순) + 누락 0 확인
    out = uni[['ticker']].merge(out, on='ticker', how='left')
    miss = out['buyback_src'].isna().sum()
    if miss:
        print(f"   ⚠️  산출 누락 {miss}개 — src='실패' 처리")
        out['buyback_src'] = out['buyback_src'].fillna('실패')
    fn = f"catalyst_large_{run_id}.csv"
    out.to_csv(fn, index=False, encoding='utf-8-sig')
    n_flag = int((out['buyback_cancel_flag'] == 1).sum())
    n_re = int((out['buyback_src'] == 'v3공유').sum())
    n_new = int((out['buyback_src'] == 'dart').sum())
    print(f"💾 {fn}  소각 {n_flag} · v3공유 {n_re} · 신규스캔 {n_new} · "
          f"미등록/실패 {len(out) - n_re - n_new}")
    return fn


def main():
    ap = argparse.ArgumentParser(description="대형 유니버스 자사주 소각 전수 스캔(플래그 수집만)")
    ap.add_argument("--run-id", default=None, help="기본: large_universe 최신 run")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()

    load_env()
    api_key = os.environ.get("DART_API_KEY", "").strip()
    if len(api_key) < 30:
        raise SystemExit("❌ .env 의 DART_API_KEY 확인")

    run_id = args.run_id or latest_universe_run(Path(args.db))
    print("=" * 64)
    print(f"🏛️  대형 자사주 소각 전수 스캔 — run {run_id}")
    print("=" * 64)
    uni = load_large_tickers(run_id, Path(args.db))
    v3 = load_v3_catalyst(run_id)
    reused, todo = split_reuse(uni, v3)
    print(f"   유니버스 {len(uni)} = v3공유 {len(reused)} + 신규 스캔 {len(todo)}")
    scanned = scan_dart(todo, api_key, args.days, args.workers) if len(todo) else \
        pd.DataFrame(columns=['ticker', 'name', 'market',
                              'buyback_cancel_flag', 'buyback_cancel_dt', 'buyback_src'])
    save_csv(reused, scanned, uni, run_id)
    print("\n✅ 완료. 다음: python large_score.py (이 파일을 자동으로 읽어 적재)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
