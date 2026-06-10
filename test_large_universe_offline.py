# -*- coding: utf-8 -*-
"""
test_large_universe_offline.py — large_universe.py 오프라인 검증
================================================================
네트워크 없이 검증 가능한 부분만 검증한다(fetch_listing 자체는 사용자 PC 실행으로 확인).
  [1] build_universe: 랭킹·플래그·정제(중복/무효시총)·'제외 없음' 원칙
  [2] save_db: 실제 history.db '사본'에 적재 → v3 4개 테이블 0 diff + 재실행 멱등
  [3] default_run_id: 최신 stage3 run 반환
사용: python test_large_universe_offline.py [history.db경로]
"""
import shutil
import sqlite3
import sys
from pathlib import Path

import pandas as pd

import large_universe as lu

DB_SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "history.db")


def t1_build():
    listing = pd.DataFrame([
        # ticker, name, close, marcap, stocks, market
        ('005930', '삼성전자',      60000, 3.6e14, 5.9e9, 'kospi'),
        ('005935', '삼성전자우',    50000, 4.0e13, 8.0e8, 'kospi'),   # 우선주(끝자리 5)
        ('105560', 'KB금융',        80000, 3.2e13, 4.0e8, 'kospi'),   # 금융(키워드)
        ('055550', '신한지주',      50000, 2.5e13, 5.0e8, 'kospi'),   # 금융(known)+지주
        ('003550', 'LG',            80000, 1.2e13, 1.5e8, 'kospi'),   # 비금융 지주 아님(이름상)
        ('088980', '맥쿼리인프라',   12000, 5.0e12, 4.0e8, 'kospi'),
        ('330590', '롯데리츠',       3500,  9.0e11, 2.5e8, 'kospi'),   # 리츠
        ('900001', '대신밸런스스팩', 2000,  1.0e11, 5.0e7, 'kosdaq'),  # 스팩
        ('035720', '카카오',        40000, 1.8e13, 4.4e8, 'kospi'),
        ('035720', '카카오중복',    40000, 1.8e13, 4.4e8, 'kospi'),   # 중복 → 1개만
        ('123456', '무효시총',      1000,  float('nan'), 1.0e7, 'kosdaq'),  # 탈락 대상
    ], columns=['ticker', 'name', 'close', 'marcap', 'stocks', 'market'])

    df = lu.build_universe(listing, sector_map={'005930': '반도체·전자부품'})

    assert len(df) == 9, f"중복1+무효1 제외 후 9개여야 함: {len(df)}"
    assert df.iloc[0]['ticker'] == '005930' and df.iloc[0]['marcap_rank'] == 1
    assert list(df['marcap_rank']) == sorted(df['marcap_rank']), "랭크 정렬 불량"
    assert (df['marcap'].diff().dropna() <= 0).all(), "시총 내림차순 아님"
    row = df.set_index('ticker')
    assert row.loc['005935', 'is_pref'] == 1 and row.loc['005930', 'is_pref'] == 0
    assert row.loc['105560', 'is_financial'] == 1, "키워드 금융 플래그 실패"
    assert row.loc['055550', 'is_financial'] == 1, "known 금융 플래그 실패"
    assert row.loc['055550', 'is_holding'] == 1 and row.loc['003550', 'is_holding'] == 0
    assert row.loc['330590', 'is_reit'] == 1 and row.loc['900001', 'is_spac'] == 1
    # '제외 없음' 원칙: 금융/리츠/스팩/우선주 전부 잔류
    for t in ('005935', '105560', '055550', '330590', '900001'):
        assert t in row.index, f"{t} 가 제외됨 — 설계 위반"
    assert row.loc['005930', 'sector'] == '반도체·전자부품'
    assert row.loc['105560', 'sector'] == '미분류'
    print("✅ [1] build_universe: 랭킹·플래그·정제·무제외 OK")
    lu.report_distribution(df, n_candidates=(3, 5))   # 출력 경로 스모크
    return df


def _table_counts(db):
    with sqlite3.connect(db) as con:
        tabs = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tabs}


def t2_db(df):
    work = Path("_test_history.db")
    shutil.copy(DB_SRC, work)
    before = _table_counts(work)
    v3_tabs = {'stage1_oversold', 'stage2_filtered', 'stage3_final', 'runs'}
    assert v3_tabs <= set(before), f"원본 DB에 v3 테이블 없음: {before.keys()}"

    n1 = lu.save_db(df, run_id='99999999', db_path=work, store_top=5)
    n2 = lu.save_db(df, run_id='99999999', db_path=work, store_top=5)  # 재실행
    assert n1 == n2 == 5, f"store_top=5 적재/멱등 실패: {n1}, {n2}"

    after = _table_counts(work)
    for t in v3_tabs:
        assert before[t] == after[t], f"v3 테이블 {t} 변경됨! {before[t]} → {after[t]}"
    assert after['large_universe'] == 5, "중복 적재 발생(멱등 깨짐)"
    with sqlite3.connect(work) as con:
        cols = [r[1] for r in con.execute("PRAGMA table_info(large_universe)")]
        for c in ('run_id', 'ticker', 'marcap', 'stocks', 'marcap_rank',
                  'is_pref', 'is_financial', 'is_holding', 'sector'):
            assert c in cols, f"컬럼 누락: {c}"
        idx = [r[1] for r in con.execute("PRAGMA index_list(large_universe)")]
        assert 'idx_large_universe_rt' in idx, "인덱스 미생성"
        ok = con.execute("PRAGMA quick_check").fetchone()[0]
        assert ok == 'ok', f"DB 무결성: {ok}"
    work.unlink()
    print("✅ [2] save_db: v3 4테이블 0 diff · 멱등 재실행 · 스키마/인덱스/무결성 OK")


def t3_runid():
    rid = lu.default_run_id(DB_SRC)
    with sqlite3.connect(DB_SRC) as con:
        expect = str(con.execute("SELECT MAX(run_id) FROM stage3_final").fetchone()[0])
    assert rid == expect, f"run_id 불일치: {rid} ≠ {expect}"
    print(f"✅ [3] default_run_id = {rid} (최신 stage3 run과 일치)")


if __name__ == "__main__":
    df = t1_build()
    t2_db(df)
    t3_runid()
    print("\n🎉 오프라인 검증 전부 통과 (fetch_listing은 사용자 PC에서 실행으로 확인)")
