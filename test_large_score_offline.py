# -*- coding: utf-8 -*-
"""
test_large_score_offline.py — large_score.py 오프라인 검증
==========================================================
실제 history.db '사본' + 합성 valuation/catalyst CSV로, 네트워크 없이 검증 가능한 전부를 검증:
  [1] 팩터 규칙: RIM(NaN 규칙·클램프·사분면), KRX 0 처리(DIV=0은 유효), 행 무제외
  [2] PIT: stage3 운반값이 대상 run 이하만 사용(미래 run 누출 0)
  [3] 통합: 유니버스→조인→계산→리포트→적재 전 구간 + 멱등 재실행
  [4] v3 4개 테이블 전 행 해시 0 diff
사용: python test_large_score_offline.py [history.db경로]
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
RUN = "20260609"


def table_hash(db, table):
    with sqlite3.connect(db) as con:
        df = pd.read_sql(f"SELECT * FROM {table} ORDER BY rowid", con)
    return hashlib.md5(df.to_csv(index=False).encode()).hexdigest(), len(df)


def make_synthetic_inputs(workdir, db):
    """실제 유니버스 티커에 결정적 합성 valuation/catalyst를 만든다(엣지 케이스 포함)."""
    with sqlite3.connect(db) as con:
        uni = pd.read_sql(
            "SELECT ticker, market, marcap_rank FROM large_universe WHERE run_id=? ORDER BY marcap_rank",
            con, params=(RUN,))
    t = list(uni['ticker'])
    cases = {  # ticker → (PBR, PER, DIV, BPS, EPS)
        t[0]: (0.8, 7.0, 2.5, 10000, 1200),    # 정상 가치주: ROE12%, 사분면 해당
        t[1]: (1.5, 0.0, 0.0, 10000, 0),       # KRX 적자표기 EPS=0 → roe NaN
        t[2]: (1.2, 9.0, 1.0, 0, 500),         # BPS=0 → roe NaN
        t[3]: (0.0, 8.0, 1.0, 10000, 900),     # PBR=0 → pbr NaN → spread NaN (roe는 9%)
        t[4]: (2.0, 5.0, 1.0, 10000, 10000),   # ROE100% → fair 12.4 → cap 10
        t[5]: (0.9, 30.0, 0.0, 10000, 50),     # ROE0.5% ≤ g → fair NaN, DIV=0 유효
    }
    rows = []
    for i, r in uni.iterrows():
        tk = r['ticker']
        pbr, per, div, bps, eps = cases.get(tk, (1.2, 10.0, 1.5, 10000, 800))  # 기본 ROE8%
        rows.append((tk, r['market'], pbr, per, div, bps, eps))
    v = pd.DataFrame(rows, columns=['ticker', 'market', 'PBR', 'PER', 'DIV', 'BPS', 'EPS'])
    drop = set(t[-3:])                          # 마지막 3개는 valuation 자체 누락 케이스
    v = v[~v['ticker'].isin(drop)]
    for mkt in ('kospi', 'kosdaq'):
        v[v['market'] == mkt].drop(columns='market').to_csv(
            workdir / f"valuation_{mkt}_{RUN}.csv", index=False, encoding='utf-8-sig')
    # catalyst: 유니버스 2종목만 수집된 상황
    pd.DataFrame({'ticker': [t[0], t[6]], 'buyback_cancel_flag': [1, 0]}).to_csv(
        workdir / f"catalyst_kospi_{RUN}.csv", index=False, encoding='utf-8-sig')
    return t, drop


def main():
    work = Path("_t_large").resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    db = work / "history.db"
    shutil.copy(DB_SRC, db)
    before = {tb: table_hash(db, tb) for tb in
              ('stage1_oversold', 'stage2_filtered', 'stage3_final', 'runs')}
    t, dropped = make_synthetic_inputs(work, db)
    os.chdir(work)

    # ---- 통합 흐름 (main()과 동일 순서) ----
    uni = ls.load_universe(RUN, db)
    val = ls.load_valuation(RUN)
    df = uni.merge(val, on='ticker', how='left')
    s3 = ls.load_stage3_latest(df['ticker'], RUN, db)
    df = df.merge(s3, on='ticker', how='left')
    bb = ls.load_buyback(RUN)
    df = df.merge(bb, on='ticker', how='left')
    df['buyback_src'] = np.where(df['ticker'].isin(bb['ticker']), 'catalyst', '미수집')
    df = ls.compute_factors(df)

    # [1] 팩터 규칙
    assert len(df) == len(uni) == 500, "행 제외 발생 — 무제외 원칙 위반"
    r = df.set_index('ticker')
    a = r.loc[t[0]]
    assert abs(a['roe_value'] - 12.0) < 1e-9 and abs(a['rim_fair_pbr'] - 1.375) < 1e-9
    assert abs(a['rim_spread'] - np.log(1.375 / 0.8)) < 1e-9 and a['rim_quadrant'] == 1.0
    assert abs(r.loc[t[4], 'rim_spread'] - np.log(10.0 / 2.0)) < 1e-9, "캡 적용 후 log 스프레드"
    # log형 ↔ 구식(1−PBR/fair) 순위 동치(단조변환) 확인
    s = df.dropna(subset=['rim_spread'])
    old_form = 1.0 - s['pbr'] / s['rim_fair_pbr']
    assert (old_form.rank() == s['rim_spread'].rank()).all(), "스프레드 정의 교체로 순위 변동"
    assert np.isnan(r.loc[t[1], 'roe_value']) and np.isnan(r.loc[t[1], 'rim_spread'])
    assert np.isnan(r.loc[t[2], 'roe_value'])
    assert np.isnan(r.loc[t[3], 'pbr']) and np.isnan(r.loc[t[3], 'rim_spread']) \
        and abs(r.loc[t[3], 'roe_value'] - 9.0) < 1e-9
    assert r.loc[t[4], 'rim_fair_pbr'] == 10.0, "정당PBR 캡 미작동"
    assert np.isnan(r.loc[t[5], 'rim_fair_pbr']) and r.loc[t[5], 'div_yield'] == 0.0
    assert r.loc[t[5], 'rim_quadrant'] == 0.0
    for d in dropped:
        assert np.isnan(r.loc[d, 'pbr']), "valuation 누락 종목이 NaN으로 보존되지 않음"
    assert r.loc[t[0], 'buyback_cancel_flag'] == 1 and r.loc[t[6], 'buyback_cancel_flag'] == 0
    assert (df['buyback_src'] == 'catalyst').sum() == 2
    assert df.loc[df['buyback_src'] == '미수집', 'buyback_cancel_flag'].isna().all(), \
        "미수집이 0으로 오염됨('확인 안 함'≠'없음')"
    assert set(df.loc[df['sector'] == '화학', 'is_cyclical']) <= {1}
    print("✅ [1] 팩터 규칙(RIM NaN·캡·사분면, KRX 0 처리, DIV=0 유효, 무제외, 자사주 NaN 구분) OK")

    # [2] PIT — 과거 시점으로 재계산해도 미래 run 누출 0
    old = ls.load_stage3_latest(df['ticker'], '20260601', db)
    assert (old['stage3_src_run'].astype(str) <= '20260601').all(), "PIT 위반"
    assert (s3['stage3_src_run'].astype(str) <= RUN).all()
    moved = (old.set_index('ticker')['stage3_src_run'].astype(str)
             != s3.set_index('ticker')['stage3_src_run'].astype(str).reindex(old.set_index('ticker').index)).sum()
    print(f"✅ [2] PIT: target 20260601 → src 전부 ≤ 20260601 (target {RUN} 대비 src 변동 {moved}종목)")

    # [3] 리포트 스모크 + 적재 멱등
    ls.report(df, RUN)
    n1 = ls.save_db(df, RUN, db)
    n2 = ls.save_db(df, RUN, db)
    assert n1 == n2 == 500, f"멱등 실패: {n1}, {n2}"
    with sqlite3.connect(db) as con:
        idx = [x[1] for x in con.execute("PRAGMA index_list(large_final)")]
        assert 'idx_large_final_rt' in idx
        assert con.execute("PRAGMA quick_check").fetchone()[0] == 'ok'
        cov = con.execute(
            "SELECT COUNT(*), SUM(stage3_src_run IS NOT NULL), SUM(rim_spread IS NOT NULL) "
            "FROM large_final WHERE run_id=?", (RUN,)).fetchone()
    print(f"✅ [3] 통합 적재·멱등·인덱스·무결성 OK (행 {cov[0]}, stage3 운반 {cov[1]}, rim_spread {cov[2]})")

    # [4] v3 0 diff
    for tb, (h, n) in before.items():
        h2, n2 = table_hash(db, tb)
        assert (h, n) == (h2, n2), f"v3 테이블 {tb} 변경됨!"
    print("✅ [4] v3 4개 테이블 전 행 해시 0 diff")

    os.chdir('..')
    shutil.rmtree(work)
    print("\n🎉 오프라인 검증 전부 통과 — 실데이터 검증은 오늘 .bat 후 실행분으로")


if __name__ == "__main__":
    main()
