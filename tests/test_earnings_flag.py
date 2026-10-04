# -*- coding: utf-8 -*-
"""실적 악화 60거래일 배지(2026-10-04) — 합성 DB 만, 네트워크·운영 DB 미접촉.

계약:
  A. 직전 60거래일 안에 접수된 '가장 최근' 보고서의 (이번 분기 − 전년 같은 분기) ÷ 시총 이 −1% 이하면 배지. 경계값(−1.0%) 포함.
  B. 더 최근 보고서가 악화가 아니면 배지 없음(최신 보고서 하나만 본다). 60거래일보다 오래된 보고서는 안 본다.
  C. asof 이후에 접수된 보고서는 쓰지 않는다(그날 알 수 없던 정보).
  D. attach 는 행·기존 열을 바꾸지 않고 열 하나만 더한다. 표시 = '영업이익↓ MM/DD'. 종목코드는 6자리로 맞춘다.
  E. DB 가 없거나 깨져도 예외 없이 빈 배지(비치명).
  F. 분기 3개월 값: 분기·반기는 당기 3개월, 사업보고서는 연간 − 3분기 누적. 전년 동기는 저장값 → 올해 보고서들의 누적 차분 → 전년 보고서 순.
     다른 보고서와 섞을 때는 연결/별도 기준이 같아야 한다. 3개월 칸에 누적을 적은 보고서는 누적 차분으로.
  G. [2026.10.16] 자료 만들기: 접수일은 접수번호로 찾은 공시의 '원본' 날짜 · 12월 결산이 아니면 제외 · 극단값·오래된 시세 제외 ·
     접수 뒤 주식수가 크게 바뀌면 큰 시총으로 · asof 형식 정리 · 자료가 낡으면 경고.
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
check("3분기: 올해 보고서들의 전년 누적 차분 우선 (5, 24−14=10) — 전년 보고서 값(7)보다 먼저", ef.quarter_values(rep, "A", 2025, "Q3") == (5, 10))
check("반기: 앞 보고서(Q1)도 전년 보고서도 없으면 못 구함", ef.quarter_values(rep, "A", 2025, "H1") == (None, None))
rep2 = {("D", 2026, "Q3"): dict(fs="CFS", th=5, th_add=30, fr=nan, fr_q=nan, fr_add=24), ("D", 2026, "H1"): dict(fs="OFS", th=12, th_add=25, fr=nan, fr_q=nan, fr_add=14),
        ("D", 2025, "Q3"): dict(fs="OFS", th=7, th_add=22, fr=nan, fr_q=nan, fr_add=nan), ("E", 2025, "Q3"): dict(fs="CFS", th=9, th_add=nan, fr=nan, fr_q=nan, fr_add=nan),
        ("E", 2026, "Q3"): dict(fs="CFS", th=6, th_add=nan, fr=nan, fr_q=nan, fr_add=nan),
        ("G", 2026, "H1"): dict(fs="CFS", th=30, th_add=30, fr=nan, fr_q=8, fr_add=nan), ("G", 2026, "Q1"): dict(fs="CFS", th=18, th_add=18, fr=nan, fr_q=nan, fr_add=5)}
check("연결/별도가 다른 보고서와는 섞지 않는다 → 못 구함", ef.quarter_values(rep2, "D", 2026, "Q3") == (None, None))
check("누적 차분을 못 쓰면 전년 같은 보고서(같은 기준) (6, 9)", ef.quarter_values(rep2, "E", 2026, "Q3") == (6, 9))
check("3개월 칸에 누적을 적은 반기 → 누적 차분 (30−18, 8)", ef.quarter_values(rep2, "G", 2026, "H1") == (12, 8))
check("1분기: 전년 누적 = 전년 3개월 (3, 8)", ef.quarter_values(rep, "B", 2026, "Q1") == (3, 8))
check("저장된 전년 동기 3개월 값이 있으면 그것 (4, 6)", ef.quarter_values(rep, "C", 2026, "H1") == (4, 6))
check("없는 보고서 → (None, None)", ef.quarter_values(rep, "Z", 2026, "Q1") == (None, None))
check("상수: −1% · 60거래일 · 열 이름", (ef.DROP, ef.LOOKBACK, ef.COL) == (-0.01, 60, "earn_drop_60d"))

print("[G] 자료 만들기·형식·경고")
import io, json, contextlib
src = os.path.join(td, "src.db"); odb = os.path.join(td, "ohlcv.db"); out = os.path.join(td, "out.db")
it = lambda th, th_add=None, fr_add=None, fr_q=None, fr=None: json.dumps([dict(account_id="dart_OperatingIncomeLoss", sj_div="IS", thstrm_amount=th, thstrm_add_amount=th_add,
                                                                           frmtrm_add_amount=fr_add, frmtrm_q_amount=fr_q, frmtrm_amount=fr)])
c = sqlite3.connect(src)
c.execute("CREATE TABLE reports(stock_code TEXT, year INTEGER, reprt TEXT, api TEXT, fs TEXT, status TEXT, kept INTEGER, rcept_no TEXT, items TEXT)")
c.execute("CREATE TABLE filings(rcept_no TEXT PRIMARY KEY, kind TEXT, stock_code TEXT, report_nm TEXT, rcept_dt TEXT)")
R = [  # stock, year, reprt, fs, rcept_no, items
    ("AAA001", 2025, "Q1", "CFS", "R0", it(20, 20, 15)), ("AAA001", 2025, "H1", "CFS", "R1b", it(10, 30, 50)),      # 반기: 10 vs (50−15)=35 → −25
    ("BBB002", 2025, "Q1", "CFS", "R2", it(5, 5, 50)),                                                               # 6월 결산(제목 2025.09)
    ("CCC003", 2025, "Q1", "CFS", "R3", it(0, 0, 1000)),                                                             # 극단값
    ("DDD004", 2025, "Q1", "CFS", "R4", it(0, 0, 50)),                                                               # 시세가 오래됨
    ("EEE005", 2025, "Q1", "OFS", "R5", it(20, 20, 15)), ("EEE005", 2025, "H1", "CFS", "R6", it(10, 30, 50)),        # 반기만 연결 → 못 구함
    ("FFF006", 2025, "Q1", "CFS", "R7", it(0, 0, 50)),                                                               # 접수 뒤 주식 병합
    ("GGG007", 2025, "Q1", "CFS", "RX", it(0, 0, 50)),                                                               # 공시 목록에 없는 접수번호
]
c.executemany("INSERT INTO reports VALUES(?,?,?,'ALL',?,'000',1,?,?)", R)
F = [("R0", "A003", "AAA001", "분기보고서 (2025.03)", "20250515"), ("R1", "A002", "AAA001", "반기보고서 (2025.06)", "20250814"),
     ("R1b", "A002", "AAA001", "[기재정정]반기보고서 (2025.06)", "20250901"), ("R2", "A003", "BBB002", "분기보고서 (2025.09)", "20251114"),
     ("R3", "A003", "CCC003", "분기보고서 (2025.03)", "20250515"), ("R4", "A003", "DDD004", "분기보고서 (2025.03)", "20250515"),
     ("R5", "A003", "EEE005", "분기보고서 (2025.03)", "20250515"), ("R6", "A002", "EEE005", "반기보고서 (2025.06)", "20250814"),
     ("R7", "A003", "FFF006", "분기보고서 (2025.03)", "20250515")]
c.executemany("INSERT INTO filings VALUES(?,?,?,?,?)", F); c.commit(); c.close()
c = sqlite3.connect(odb); c.execute("CREATE TABLE daily_ohlcv(ticker TEXT, date TEXT, close REAL, shares REAL)")
P = [("AAA001", "20250514", 10, 125), ("AAA001", "20250813", 10, 125), ("AAA001", "20250829", 10, 125), ("CCC003", "20250514", 10, 100),
     ("DDD004", "20250401", 10, 100), ("EEE005", "20250514", 10, 125), ("EEE005", "20250813", 10, 125),
     ("FFF006", "20250514", 10, 1000), ("FFF006", "20250901", 10, 100), ("BBB002", "20251113", 10, 100), ("GGG007", "20250514", 10, 100)]
c.executemany("INSERT INTO daily_ohlcv VALUES(?,?,?,?)", P); c.commit(); c.close()
n, sk = ef.rebuild_from_research(src=src, out=out, ohlcv=odb)
got = {(t, y, r_): (d, round(sue, 4), s_) for t, y, r_, d, sue, s_ in sqlite3.connect(out).execute("SELECT ticker, year, reprt, rcept_dt, sue, source FROM earnings_q")}
check("정정본 접수번호여도 접수일은 원본 날짜(20250814) · 값 −25/1250 = −2%", got.get(("AAA001", 2025, "H1"), ("", 0, ""))[:2] == ("20250814", -0.02))
check("1분기 행도 정상(+5/1250)", got.get(("AAA001", 2025, "Q1"), ("", 0, ""))[:2] == ("20250515", 0.004))
check("12월 결산 아님 → 제외", ("BBB002", 2025, "Q1") not in got and sk["non_dec"] == 1)
check("극단값(|감소분÷시총| > 0.5) → 제외", ("CCC003", 2025, "Q1") not in got and sk["extreme"] == 1)
check("접수 전 10일 안 시세 없음 → 제외", ("DDD004", 2025, "Q1") not in got and sk["no_price"] == 1)
check("연결/별도가 섞여 못 구함 → 반기 제외(1분기는 남음)", ("EEE005", 2025, "H1") not in got and ("EEE005", 2025, "Q1") in got and sk["no_values"] == 1)
check("접수 뒤 주식 병합 → 큰 시총 기준(−50/10000 = −0.5%, 배지 아님) · 표시 남김", got.get(("FFF006", 2025, "Q1")) == ("20250515", -0.005, "research_backfill|shares_jump"))
check("공시 목록에 없는 접수번호 → 제외", ("GGG007", 2025, "Q1") not in got and sk["no_date"] == 1)
check("저장 행 수 = 4", n == 4 and len(got) == 4)
check("asof 에 '-' 가 섞여도 같은 결과", ef.load(asof[:4] + "-" + asof[4:6] + "-" + asof[6:], db=edb, cal_db=cal) == ef.load(asof, db=edb, cal_db=cal))
cal2 = os.path.join(td, "cal2.db"); c = sqlite3.connect(cal2); c.execute("CREATE TABLE market_daily(series TEXT, date TEXT, close REAL)")
days2 = days + [f"2027{m:02d}{d:02d}" for m in range(1, 5) for d in range(1, 29)]
c.executemany("INSERT INTO market_daily VALUES('KOSPI',?,1)", [(d,) for d in days2]); c.commit(); c.close()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    r1 = ef.load(days2[-1], db=edb, cal_db=cal2); r2 = ef.load(days[-1][:6] + "28", db=edb, cal_db=cal); r3 = ef.load(days2[len(days) + 20], db=edb, cal_db=cal2)
lines = buf.getvalue().strip().splitlines()
check("자료가 60거래일 창 밖이면 빈 배지 + 경고", r1 == {} and any("전부 비었음" in x for x in lines))
check("자료가 싱싱하면 경고 없음 · 조금 낡으면(45거래일 초과) '반영 안 됨' 경고", len(r2) == 4 and sum("반영 안 됨" in x for x in lines) == 1 and len(lines) == 2)

print("\n" + ("❌ 실패 %d건" % fails if fails else "✅ test_earnings_flag 통과"))
sys.exit(1 if fails else 0)
