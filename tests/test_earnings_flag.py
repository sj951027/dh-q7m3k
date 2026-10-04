# -*- coding: utf-8 -*-
"""실적 악화 60거래일 배지(2026-10-04) — 합성 DB 만, 네트워크·운영 DB 미접촉.

계약:
  A. 직전 60거래일 안에 접수된 '가장 최근' 보고서의 (이번 분기 − 전년 같은 분기) ÷ 시총 이 −1% 이하면 배지. 경계값(−1.0%) 포함.
  B. 더 최근 보고서가 악화가 아니면 배지 없음(최신 보고서 하나만 본다). 60거래일보다 오래된 보고서는 안 본다.
  C. asof 이후에 접수된 보고서는 쓰지 않는다(그날 알 수 없던 정보).
  D. attach 는 행·기존 열을 바꾸지 않고 열 하나만 더한다. 표시 = '영업이익↓ MM/DD'. 종목코드는 6자리로 맞춘다.
  E. DB 가 없거나 깨져도 예외 없이 빈 배지(비치명).
  F. 분기 3개월 값: 분기·반기는 당기 3개월, 사업보고서는 연간 − 3분기 누적. 전년 동기는 저장값 → 전년 보고서 → 누적 차분 순.
실행: python tests/test_earnings_flag.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import pandas as pd
import earnings_flag as ef

fails = 0


def check(name, cond):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        fails += 1


td = tempfile.mkdtemp(); cal = os.path.join(td, "cal.db"); edb = os.path.join(td, "earn.db")
days = [f"2026{m:02d}{d:02d}" for m in range(1, 11) for d in range(1, 29)]          # 달력 280일(가짜 거래일)
c = sqlite3.connect(cal); c.execute("CREATE TABLE market_daily(series TEXT, date TEXT, close REAL)")
c.executemany("INSERT INTO market_daily VALUES('KOSPI',?,1)", [(d,) for d in days]); c.commit(); c.close()
asof = days[-1]; in60 = days[-30]; old = days[-100]; edge = days[-60]; out = days[-61]
rows = [  # ticker, year, reprt, ord, rcept_dt, q_op, q_prev, mcap, sue
    ("000001", 2026, "H1", 2, in60, 0, 20, 1000, -0.02),          # 악화
    ("000002", 2026, "H1", 2, in60, 0, 10, 1000, -0.01),          # 경계값 −1.0% → 배지
    ("000003", 2026, "H1", 2, in60, 0, 9, 1000, -0.009),          # 기준 미달
    ("000004", 2026, "Q1", 1, days[-50], 0, 50, 1000, -0.05),     # 옛 보고서는 악화였지만
    ("000004", 2026, "H1", 2, in60, 30, 10, 1000, 0.02),          #   더 최근 보고서가 개선 → 배지 없음
    ("000005", 2026, "Q1", 1, old, 0, 50, 1000, -0.05),           # 60거래일보다 오래됨
    ("000006", 2026, "H1", 2, edge, 0, 50, 1000, -0.05),          # 창의 첫날(포함)
    ("000007", 2026, "H1", 2, out, 0, 50, 1000, -0.05),           # 창 바로 밖
    ("000008", 2026, "Q1", 1, days[-50], 30, 10, 1000, 0.02),     # 옛 보고서는 개선이었지만
    ("000008", 2026, "H1", 2, in60, 0, 50, 1000, -0.05),          #   최근 보고서가 악화 → 배지
]
w = sqlite3.connect(edb)
w.execute("CREATE TABLE earnings_q(ticker TEXT, year INTEGER, reprt TEXT, reprt_ord INTEGER, rcept_dt TEXT, q_op REAL, q_op_prev REAL, mcap_prev REAL, sue REAL, source TEXT, PRIMARY KEY(ticker, year, reprt))")
w.executemany("INSERT INTO earnings_q VALUES(?,?,?,?,?,?,?,?,?,'t')", rows); w.commit(); w.close()

print("[A·B] 배지 대상")
f = ef.load(asof, db=edb, cal_db=cal)
check("악화·경계값·창 첫날·최근 악화만 배지", sorted(f) == ["000001", "000002", "000006", "000008"])
check("라벨과 접수일", f["000001"] == ("영업이익↓", in60))
print("[C] 그날 알 수 없던 보고서는 안 쓴다")
f2 = ef.load(days[-31], db=edb, cal_db=cal)
check("접수일 전날 기준이면 000001 배지 없음", "000001" not in f2)
check("그날 기준 최신(1분기 악화)이면 000004 는 배지", "000004" in f2 and "000008" not in f2)
print("[D] attach")
_load = ef.load
ef.load = lambda asof=None, **k: _load(asof, db=edb, cal_db=cal)
df = pd.DataFrame({"ticker": ["1", "000003", "000008", 6], "score": [1.0, 2.0, 3.0, 4.0]})
g, n = ef.attach(df, asof=asof)
check("행·기존 열 불변 + 열 하나", list(g.columns) == ["ticker", "score", "earn_drop_60d"] and g[["ticker", "score"]].equals(df) and len(g) == 4)
check("표시 문구·6자리 맞춤·건수", list(g.earn_drop_60d) == [f"영업이익↓ {in60[4:6]}/{in60[6:]}", "", f"영업이익↓ {in60[4:6]}/{in60[6:]}", f"영업이익↓ {edge[4:6]}/{edge[6:]}"] and n == 3)
check("원본 df 는 안 바뀐다", "earn_drop_60d" not in df.columns)
ef.load = _load
print("[E] 실패해도 조용히 빈 배지")
check("DB 없음 → {}", ef.load(asof, db=os.path.join(td, "none.db"), cal_db=cal) == {})
check("달력 DB 없음 → {}", ef.load(asof, db=edb, cal_db=os.path.join(td, "none2.db")) == {})
print("[F] 분기 3개월 값 유도")
nan = float("nan")
rep = {("A", 2025, "Q3"): dict(th=5, th_add=30, fr=nan, fr_q=nan, fr_add=24), ("A", 2025, "H1"): dict(th=12, th_add=25, fr=nan, fr_q=nan, fr_add=14),
       ("A", 2025, "Y"): dict(th=42, th_add=nan, fr=40, fr_q=nan, fr_add=nan), ("A", 2024, "Q3"): dict(th=7, th_add=22, fr=nan, fr_q=nan, fr_add=nan),
       ("B", 2026, "Q1"): dict(th=3, th_add=3, fr=nan, fr_q=nan, fr_add=8), ("C", 2026, "H1"): dict(th=4, th_add=9, fr=nan, fr_q=6, fr_add=nan)}
check("사업보고서: 연간 − 3분기 누적 (42−30, 40−24)", ef.quarter_values(rep, "A", 2025, "Y") == (12, 16))
check("3분기: 전년 같은 보고서의 3개월 값 우선 (5, 7)", ef.quarter_values(rep, "A", 2025, "Q3") == (5, 7))
check("반기: 전년 보고서 없으면 누적 차분 — 앞 보고서(Q1)가 없으면 못 구함", ef.quarter_values(rep, "A", 2025, "H1") == (None, None))
check("1분기: 전년 누적 = 전년 3개월 (3, 8)", ef.quarter_values(rep, "B", 2026, "Q1") == (3, 8))
check("저장된 전년 동기 3개월 값이 있으면 그것 (4, 6)", ef.quarter_values(rep, "C", 2026, "H1") == (4, 6))
check("없는 보고서 → (None, None)", ef.quarter_values(rep, "Z", 2026, "Q1") == (None, None))
check("상수: −1% · 60거래일 · 열 이름", (ef.DROP, ef.LOOKBACK, ef.COL) == (-0.01, 60, "earn_drop_60d"))

print("\n" + ("❌ 실패 %d건" % fails if fails else "✅ test_earnings_flag 통과"))
sys.exit(1 if fails else 0)
