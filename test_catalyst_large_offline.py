# -*- coding: utf-8 -*-
"""
test_catalyst_large_offline.py — catalyst_large.py 오프라인 검증
================================================================
네트워크 없는 부분만: 유니버스 로드 / v3 결과 재사용 분할 / 산출 CSV 스키마·정합.
(scan_dart 의 DART 호출은 사용자 첫 실행 로그로 확인 — 단 호출 로직은
 catalyst_insider.score_buyback_cancel + stage2 배관 '재사용'이라 신규 위험 최소.)
사용: python test_catalyst_large_offline.py [history.db경로]
"""
import os, shutil, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalyst_large as cl

DB_SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "history.db").resolve()
import sqlite3 as _sq
_c = _sq.connect(DB_SRC); RUN = str(_c.execute("SELECT MAX(run_id) FROM large_universe").fetchone()[0]); _c.close()

work = Path("_t_cat").resolve()
if work.exists():
    shutil.rmtree(work)
work.mkdir()
shutil.copy(DB_SRC, work / "history.db")
os.chdir(work)

# [1] 유니버스 로드 + 최신 run 판별
assert cl.latest_universe_run(Path("history.db")) == RUN
uni = cl.load_large_tickers(RUN, Path("history.db"))
assert len(uni) == 500 and uni['ticker'].str.len().eq(6).all()
print("✅ [1] 유니버스 로드(500, zfill) OK")

# [2] v3 catalyst 재사용 분할 — 합성 v3 CSV (유니버스 3종목 + 비유니버스 1종목)
t = list(uni['ticker'])
pd.DataFrame({'ticker': [t[0], t[2], t[7], '999999'],
              'buyback_cancel_flag': [1, 0, 1, 1],
              'buyback_cancel_dt': ['20260601', '', '20260520', '20260601']}).to_csv(
    f"catalyst_kospi_{RUN}.csv", index=False, encoding='utf-8-sig')
v3 = cl.load_v3_catalyst(RUN)
reused, todo = cl.split_reuse(uni, v3)
assert len(reused) == 3 and len(todo) == 497, f"분할 오류 {len(reused)}/{len(todo)}"
assert set(reused['buyback_src']) == {'v3공유'}
assert reused.set_index('ticker').loc[t[0], 'buyback_cancel_flag'] == 1
assert not set(reused['ticker']) & set(todo['ticker'])
print("✅ [2] v3공유 분할(교집합만 복사, 비유니버스 무시, 중복 0) OK")

# [3] v3 CSV 부재 시 전량 신규 스캔 대상
os.remove(f"catalyst_kospi_{RUN}.csv")
reused0, todo0 = cl.split_reuse(uni, cl.load_v3_catalyst(RUN))
assert len(reused0) == 0 and len(todo0) == 500
print("✅ [3] v3 부재 폴백(전량 todo) OK")

# [4] save_csv: 합성 스캔결과 결합 → 스키마/순서/누락 처리
scanned = todo.copy()
scanned['buyback_cancel_flag'] = 0.0
scanned.loc[scanned.index[:2], 'buyback_cancel_flag'] = 1.0
scanned['buyback_cancel_dt'] = ''
scanned['buyback_src'] = 'dart'
scanned = scanned.iloc[:-1]                       # 1개 누락 → '실패' 처리 확인
fn = cl.save_csv(reused, scanned, uni, RUN)
out = pd.read_csv(fn, encoding='utf-8-sig', dtype={'ticker': str})
assert list(out.columns) == ['ticker', 'name', 'market', 'buyback_cancel_flag', 'buyback_cancel_dt', 'buyback_src']
assert len(out) == 500 and (out['ticker'] == uni['ticker']).all(), "시총순 보존 실패"
assert (out['buyback_src'] == '실패').sum() == 1
assert out.loc[out['buyback_src'] == '실패', 'buyback_cancel_flag'].isna().all()
# large_score 가 이 파일을 그대로 읽는지 (우선순위 경로 연결 확인)
import large_score as ls
bb, mode = ls.load_buyback(RUN)
assert mode == 'large' and len(bb) == 500
print("✅ [4] 산출 스키마·순서·실패 NaN·large_score 연결 OK")

os.chdir('..')
shutil.rmtree(work)
print("\n🎉 catalyst_large 오프라인 검증 통과 (DART 호출부는 첫 실행 로그로 확인)")
