# -*- coding: utf-8 -*-
"""수급 수집 대상(kis_flows.load_all_tickers) 회귀(2026-10-11) — 임시 DB·가짜 상장목록만, 네트워크·운영 DB 미접촉.

사건: 배치에서 universe_ohlcv 가 '걸러낸 목록'을 상장목록 캐시에 덮어쓴 직후 수급 수집이 돌아서, 캐시로 보충하던
      코스닥 글로벌·영문코드 136종목이 대상에서 빠졌고 daily_flows 가 9/11 에서 조용히 멈췄다(10/09 Codex 감사로 발견).
계약:
  A. 본 표의 활발 종목(거래정지 아님·종가 있음)은 종전대로 시총 순(0-diff).
  B. 상장목록 캐시에 있고 활발 본 표에 없는 종목은 종전대로 보충(0-diff).
  C. 시세 보충표(daily_ohlcv_extra) 최신일의 활발 종목은 캐시에서 빠져 있어도 대상.
  D. 중복 없음 · 보충표의 거래정지·옛 날짜 종목은 넣지 않는다.
  E. 공매도 전용 호출(include_extras=False)은 종전 그대로(본 표 활발 종목만 — sv_a 입력 불변).
  F. 보충표가 없는 DB·캐시 실패에도 멈추지 않는다.
실행: python tests/test_kis_flows_targets.py
"""
import contextlib
import io
import os
import sqlite3
import sys
import tempfile
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO)); os.chdir(REPO)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
P = 0


def check(name, cond, info=""):
    global P
    if not cond:
        print(f"  FAIL  {name}  {info}"); sys.exit(1)
    P += 1; print(f"  ok    {name}")


import kis_flows as K  # noqa: E402

# 배치 시점의 캐시 = universe_ohlcv 가 걸러낸 목록(본 표 종목뿐). 196170·0126Z0 은 없다.
FILTERED = [{"code": "005930", "name": "A"}, {"code": "000660", "name": "B"}, {"code": "111111", "name": "정지"}]
FAKE = {"rows": FILTERED, "fail": False}


def _load(market="KRX"):
    if FAKE["fail"]:
        raise RuntimeError("cache broken")
    return FAKE["rows"], "2026-10-08 20:10"


sys.modules["listing_cache"] = types.SimpleNamespace(load=_load)

tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "ohlcv.db")
con = sqlite3.connect(db)
con.executescript("""CREATE TABLE daily_ohlcv (ticker TEXT, date TEXT, close INTEGER, shares INTEGER, is_suspended INTEGER);
CREATE TABLE daily_ohlcv_extra (ticker TEXT, date TEXT, close INTEGER, shares INTEGER, is_suspended INTEGER);""")
con.executemany("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?)",
                [("005930", "20261008", 100, 10, 0), ("000660", "20261008", 300, 10, 0), ("111111", "20261008", 5, 1, 1)])
con.executemany("INSERT INTO daily_ohlcv_extra VALUES (?,?,?,?,?)",
                [("196170", "20261008", 50, 10, 0), ("0126Z0", "20261008", 90, 10, 0),
                 ("222222", "20261008", 7, 1, 1),        # 보충표 안의 거래정지 → 제외
                 ("333333", "20261002", 7, 1, 0),        # 옛 날짜에만 있음 → 제외
                 ("005930", "20261008", 100, 10, 0)])    # 본 표와 겹침 → 한 번만
con.commit(); con.close()


def targets(include_extras=True):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rid, tk = K.load_all_tickers(db, include_extras=include_extras)
    return rid, [t for t, _ in tk], buf.getvalue()


print("[A~D] 일별 수급 대상")
rid, codes, log = targets()
check("A. 본 표 활발 종목이 시총 순으로 맨 앞(000660 → 005930)", codes[:2] == ["000660", "005930"] and rid == "all_ohlcv_20261008", str(codes))
check("B. 캐시에 있고 활발 본 표에 없는 111111 은 종전대로 보충", codes[2] == "111111" and "상장목록 보충 1종목" in log, log)
check("C. 캐시에서 빠진 보충표 종목 0126Z0·196170 도 대상(시총 순)", codes[3:] == ["0126Z0", "196170"] and "시세 보충표 2종목" in log, str(codes))
check("D. 중복 없음 · 보충표의 거래정지(222222)·옛 날짜(333333)는 제외", len(codes) == len(set(codes)) == 5 and "222222" not in codes and "333333" not in codes)

print("[B'] 캐시가 온전할 때(스크리너가 되돌린 뒤) — 같은 종목을 두 번 넣지 않는다")
FAKE["rows"] = FILTERED + [{"code": "196170", "name": "C"}, {"code": "0126Z0", "name": "D"}]
rid, codes2, log = targets()
check("집합은 같고 보충표 줄은 안 찍힌다", sorted(codes2) == sorted(codes) and "시세 보충표" not in log, log)
FAKE["rows"] = FILTERED

print("[E] 공매도 전용 호출")
rid, codes, log = targets(include_extras=False)
check("E. 본 표 활발 종목만(종전 그대로)", codes == ["000660", "005930"] and "보충" not in log, str(codes))

print("[F] 실패에 견딤")
FAKE["fail"] = True
rid, codes, log = targets()
check("캐시가 깨져도 보충표 종목은 받는다", codes == ["000660", "005930", "0126Z0", "196170"] and "상장목록 보충 실패" in log, str(codes))
FAKE["fail"] = False
c = sqlite3.connect(db); c.execute("DROP TABLE daily_ohlcv_extra"); c.commit(); c.close()
rid, codes, log = targets()
check("보충표가 없는 DB 에서도 종전 결과", codes == ["000660", "005930", "111111"], str(codes))

print("[배선] 배치 순서")
bat = open(REPO / "run_all_and_diversify.bat", encoding="utf-8", errors="replace").read()
check("extra_ohlcv 가 수급 수집보다 먼저 돈다(보충표 최신일 = 그날)",
      0 < bat.find("python extra_ohlcv.py") < bat.find("python kis_flows.py --universe all"))
print(f"\n{P}개 통과")
