# -*- coding: utf-8 -*-
"""배치가 안 돈 거래일 알림(2026-10-15) — 메모리 DB만, 네트워크·운영 DB 미접촉.

사건: 10/14 새벽 Windows 업데이트 재시작 뒤 로그인이 안 된 채라 20:10 배치가 통째로 건너뛰어졌는데 알림이 없었다.
계약:
  A. 직전 run 과 이번 run 사이의 거래일(시세·코스피 지수 날짜)을 빠진 날로 돌려준다.
  B. 정상(연속 거래일 run)·주말·휴장은 빈 목록. 주말 run 이 섞여도 오탐 없음.
  C. skip_dates 에 적은 날은 뺀다. 시세에는 없고 지수에만 있는 날도 잡는다.
  D. run 이 하나뿐이거나 market_daily 표가 없어도 예외 없음.
  E. 텔레그램 경고 줄은 ⚠️ 로 시작한다(첫 줄 '확인 필요').
실행: python tests/test_missed_run_warning.py
"""
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import notify_telegram as nt  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        fails += 1


def dbs(runs, px_days, idx_days=None, with_market=True):
    h = sqlite3.connect(":memory:"); h.execute("CREATE TABLE runs(run_id TEXT)")
    h.executemany("INSERT INTO runs VALUES(?)", [(r,) for r in runs])
    o = sqlite3.connect(":memory:"); o.execute("CREATE TABLE daily_ohlcv(ticker TEXT, date TEXT)")
    o.executemany("INSERT INTO daily_ohlcv VALUES('005930',?)", [(d,) for d in px_days])
    if with_market:
        o.execute("CREATE TABLE market_daily(series TEXT, date TEXT, close REAL)")
        o.executemany("INSERT INTO market_daily VALUES('KOSPI',?,1)", [(d,) for d in (idx_days if idx_days is not None else px_days)])
    return h, o


F = nt._missed_run_days
print("A. 10/14 사례")
h, o = dbs(["20261012", "20261013", "20261015"], ["20261012", "20261013", "20261014", "20261015"])
check("10/13 → 10/15 사이 10/14 를 잡는다", F(h, o) == ["20261014"])
print("B. 정상")
h, o = dbs(["20261012", "20261013"], ["20261012", "20261013"])
check("연속 거래일 → 없음", F(h, o) == [])
h, o = dbs(["20261008", "20261012"], ["20261008", "20261012"])
check("휴장(10/9)·주말 건너 → 없음", F(h, o) == [])
h, o = dbs(["20260626", "20260627", "20260629"], ["20260626", "20260629"])
check("토요일 run(6/27)이 섞여도 오탐 없음", F(h, o) == [])
print("C. 빼기·지수만 있는 날")
h, o = dbs(["20261013", "20261015"], ["20261013", "20261014", "20261015"])
check("skip_dates 의 날은 뺀다", F(h, o, {"20261014"}) == [])
h, o = dbs(["20261013", "20261016"], ["20261013", "20261016"], ["20261013", "20261014", "20261015", "20261016"])
check("시세엔 없고 지수에만 있는 날(14·15)도 잡는다", F(h, o) == ["20261014", "20261015"])
print("D. 가드")
h, o = dbs(["20261013"], ["20261013", "20261014"])
check("run 하나뿐 → 없음", F(h, o) == [])
h, o = dbs(["20261013", "20261015"], ["20261013", "20261014", "20261015"], with_market=False)
check("market_daily 표 없음 → 시세 날짜로만", F(h, o) == ["20261014"])
print("E. 경고 줄")
src = (REPO / "notify_telegram.py").read_text(encoding="utf-8")
check("경고 줄이 ⚠️ 로 시작하고 _freshness_warnings 에 연결", 'out.append(f"⚠️ 배치가 안 돈 거래일:' in src and "_missed_run_days(hc, oc, _skip_dates())" in src)
print(("\n❌ 실패 %d건" % fails) if fails else "\n✅ test_missed_run_warning 통과")
sys.exit(1 if fails else 0)
