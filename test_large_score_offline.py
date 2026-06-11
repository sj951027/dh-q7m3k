# -*- coding: utf-8 -*-
"""
test_large_score_offline.py — large_score.py v1.2 오프라인 검증
================================================================
실제 history.db '사본' + 합성 valuation/catalyst CSV로, 네트워크 없이 검증:
  [1] 팩터 규칙: RIM(log형·NaN·캡·사분면·순위동치), KRX 0 처리, 무제외
  [2] 업종 오버레이(실데이터): 금융 통합·KSIC64 지주 보정·우선주 상속·리츠, 원본 보존
  [3] PIT: stage3 운반값 미래 run 누출 0
  [4] buyback 우선순위: catalyst_large > v3 catalyst, 미확인=NaN
  [5] 통합 적재 + 구스키마 자동 마이그레이션(sector_raw ALTER) + 멱등
  [6] v3 4개 테이블 전 행 해시 0 diff
사용: python test_large_score_offline.py [history.db경로] [sector_cache.json경로]
"""
import hashlib
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import large_score as ls

DB_SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "history.db").resolve()
SC_SRC = Path(sys.argv[2] if len(sys.argv) > 2 else "sector_cache.json").resolve()
RUN = "20260610"


def table_hash(db, table):
    con = sqlite3.connect(db)
    try:
        df = pd.read_sql(f"SELECT * FROM {table} ORDER BY rowid", con)
    finally:
        con.close()                      # Windows: 핸들을 닫아야 임시 폴더 삭제 가능
    return hashlib.md5(df.to_csv(index=False).encode()).hexdigest(), len(df)


def make_synthetic_valuation(workdir, uni):
    t = list(uni['ticker'])
    cases = {  # ticker → (PBR, PER, DIV, BPS, EPS)
        t[0]: (0.8, 7.0, 2.5, 10000, 1200),    # ROE12%, 사분면 해당
        t[1]: (1.5, 0.0, 0.0, 10000, 0),       # KRX 적자표기 EPS=0 → roe NaN
        t[2]: (1.2, 9.0, 1.0, 0, 500),         # BPS=0
        t[3]: (0.0, 8.0, 1.0, 10000, 900),     # PBR=0
        t[4]: (2.0, 5.0, 1.0, 10000, 10000),   # ROE100% → 캡 10
        t[5]: (0.9, 30.0, 0.0, 10000, 50),     # ROE0.5%≤g → fair NaN, DIV=0 유효
    }
    rows = []
    for _, r in uni.iterrows():
        pbr, per, div, bps, eps = cases.get(r['ticker'], (1.2, 10.0, 1.5, 10000, 800))
        rows.append((r['ticker'], r['market'], pbr, per, div, bps, eps))
    v = pd.DataFrame(rows, columns=['ticker', 'market', 'PBR', 'PER', 'DIV', 'BPS', 'EPS'])
    drop = set(t[-3:])
    v = v[~v['ticker'].isin(drop)]
    for mkt in ('kospi', 'kosdaq'):
        v[v['market'] == mkt].drop(columns='market').to_csv(
            workdir / f"valuation_{mkt}_{RUN}.csv", index=False, encoding='utf-8-sig')
    return t, drop


def main():
    work = Path("_t_large").resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    db = work / "history.db"
    shutil.copy(DB_SRC, db)
    if SC_SRC.exists():
        shutil.copy(SC_SRC, work / 'sector_cache.json')
    v3_tabs = ('stage1_oversold', 'stage2_filtered', 'stage3_final', 'runs')
    before = {tb: table_hash(db, tb) for tb in v3_tabs}
    con = sqlite3.connect(db)
    try:
        uni_raw = pd.read_sql("SELECT * FROM large_universe WHERE run_id=? ORDER BY marcap_rank",
                              con, params=(RUN,))
        n_uni_total = con.execute("SELECT COUNT(*) FROM large_universe").fetchone()[0]
    finally:
        con.close()
    t, dropped = make_synthetic_valuation(work, uni_raw)
    os.chdir(work)

    # ---- [2] 업종 오버레이 (실데이터) ----
    uni = ls.apply_sector_overlay(uni_raw, ls.load_sector_map())
    r = uni.set_index('ticker')
    assert (uni['sector_raw'] == uni_raw['sector']).all(), "원본 라벨 보존 실패"
    assert r.loc['105560', 'sector'] == '금융', "KB금융 → 금융 실패"      # 미분류였던 진짜 금융
    for tk in ('001040', '003550'):                                      # CJ, LG (KSIC64 오라벨)
        if tk in r.index:
            assert r.loc[tk, 'sector'] == '지주', f"{tk} 지주 보정 실패"
    if '005935' in r.index:                                              # 삼성전자우 상속
        assert r.loc['005935', 'sector'] == '반도체·전자부품', "우선주 상속 실패"
    u300 = uni[uni['marcap_rank'] <= 300]
    n_mi = int((u300['sector'] == '미분류').sum())
    assert n_mi <= 2, f"top300 미분류 잔여 {n_mi}개(기대 ≤2)"
    assert (u300['sector'] == '금융').sum() >= 25 and (u300['sector'] == '지주').sum() >= 20
    print(f"✅ [2] 오버레이: 금융 {(u300['sector']=='금융').sum()} · 지주 {(u300['sector']=='지주').sum()} · "
          f"리츠 {(u300['sector']=='리츠').sum()} · 미분류 잔여 {n_mi} · sector_raw 보존 OK")

    # ---- 통합 흐름 (main 과 동일 순서) ----
    val = ls.load_valuation(RUN)
    df = uni.merge(val, on='ticker', how='left')
    s3 = ls.load_stage3_latest(df['ticker'], RUN, db)
    df = df.merge(s3, on='ticker', how='left')

    # ---- [4] buyback 우선순위 ----
    pd.DataFrame({'ticker': [t[0], t[6]], 'buyback_cancel_flag': [1, 0]}).to_csv(
        f"catalyst_kospi_{RUN}.csv", index=False, encoding='utf-8-sig')
    bb, mode = ls.load_buyback(RUN)
    assert mode == 'v3' and len(bb) == 2 and set(bb['buyback_src']) == {'catalyst'}
    pd.DataFrame({'ticker': t[:4], 'buyback_cancel_flag': [1, 0, np.nan, 0],
                  'buyback_src': ['dart', 'v3공유', '미등록', 'dart']}).to_csv(
        f"catalyst_large_{RUN}.csv", index=False, encoding='utf-8-sig')
    bb, mode = ls.load_buyback(RUN)
    assert mode == 'large' and len(bb) == 4, "전수 스캔 파일 우선순위 실패"
    df = df.merge(bb, on='ticker', how='left')
    df['buyback_src'] = df.get('buyback_src', pd.Series(index=df.index, dtype=object)).fillna('미수집')
    r2 = df.set_index('ticker')
    assert r2.loc[t[0], 'buyback_cancel_flag'] == 1 and r2.loc[t[0], 'buyback_src'] == 'dart'
    assert np.isnan(r2.loc[t[2], 'buyback_cancel_flag']) and r2.loc[t[2], 'buyback_src'] == '미등록'
    assert df.loc[df['buyback_src'] == '미수집', 'buyback_cancel_flag'].isna().all()
    print("✅ [4] buyback: catalyst_large 우선 · src 전달 · 미확인 NaN OK")

    df = ls.compute_factors(df)

    # ---- [1] 팩터 규칙 (log형) ----
    assert len(df) == len(uni_raw) == 500, "행 제외 발생"
    rr = df.set_index('ticker')
    a = rr.loc[t[0]]
    assert abs(a['roe_value'] - 12.0) < 1e-9 and abs(a['rim_fair_pbr'] - 1.375) < 1e-9
    assert abs(a['rim_spread'] - np.log(1.375 / 0.8)) < 1e-9 and a['rim_quadrant'] == 1.0
    assert np.isnan(rr.loc[t[1], 'roe_value']) and np.isnan(rr.loc[t[3], 'rim_spread'])
    assert rr.loc[t[4], 'rim_fair_pbr'] == 10.0
    assert abs(rr.loc[t[4], 'rim_spread'] - np.log(10.0 / 2.0)) < 1e-9
    assert np.isnan(rr.loc[t[5], 'rim_fair_pbr']) and rr.loc[t[5], 'div_yield'] == 0.0
    s = df.dropna(subset=['rim_spread'])
    old_form = 1.0 - s['pbr'] / s['rim_fair_pbr']
    assert (old_form.rank() == s['rim_spread'].rank()).all(), "log형 순위 동치 깨짐"
    for d in dropped:
        assert np.isnan(rr.loc[d, 'pbr'])
    print("✅ [1] 팩터 규칙(log형 RIM·캡·사분면·순위동치·KRX 0 처리·무제외) OK")

    # ---- [3] PIT ----
    old = ls.load_stage3_latest(df['ticker'], '20260601', db)
    assert (old['stage3_src_run'].astype(str) <= '20260601').all()
    assert (s3['stage3_src_run'].astype(str) <= RUN).all()
    print("✅ [3] PIT: 미래 run 누출 0")

    # ---- [5] 적재 + 구스키마 마이그레이션 + 멱등 ----
    con = sqlite3.connect(db)
    pre = {x[1] for x in con.execute("PRAGMA table_info(large_final)")}
    con.close()
    if 'sector_raw' in pre:
        print("   (참고: 이 DB는 이미 마이그레이션됨 — ALTER 발생 없이 적재만 검증)")
    ls.report(df, RUN)
    n1 = ls.save_db(df, RUN, db)
    n2 = ls.save_db(df, RUN, db)
    assert n1 == n2 == 500
    con = sqlite3.connect(db)
    post = {x[1] for x in con.execute("PRAGMA table_info(large_final)")}
    assert 'sector_raw' in post, "ALTER 마이그레이션 실패"
    assert con.execute("PRAGMA quick_check").fetchone()[0] == 'ok'
    nuni = con.execute("SELECT COUNT(*) FROM large_universe").fetchone()[0]
    con.close()
    assert nuni == n_uni_total, "large_universe 변형됨"
    print("✅ [5] 적재·sector_raw ALTER·멱등·무결성 OK")

    # ---- [6] v3 0 diff ----
    for tb, hv in before.items():
        assert table_hash(db, tb) == hv, f"v3 테이블 {tb} 변경됨!"
    print("✅ [6] v3 4개 테이블 전 행 해시 0 diff")

    os.chdir('..')
    import gc
    gc.collect()                          # 남은 sqlite 핸들 정리(Windows)
    try:
        shutil.rmtree(work)
    except OSError:
        print(f"⚠️  임시 폴더 삭제 실패 — 수동 삭제 요망: {work} (검증 결과와는 무관)")
    print("\n🎉 v1.2 오프라인 검증 전부 통과")


if __name__ == "__main__":
    main()
