# -*- coding: utf-8 -*-
"""종가 정정 감시 상세 기록(2026-09-22) — 합성 입력만, 네트워크·운영 DB 미접촉.

계약:
  A. close_revisions 는 (date, old, new, code) 를 돌려주고, 수정주가 재조정(ADJ_TOL 초과)·오늘 행·값 같음은 제외.
  B. summarize_revisions 는 4-튜플을 그대로 받아 종전과 같은 요약을 만든다(요약 CSV 형식 0-diff).
  C. log_revision_details 는 상세 CSV 를 누적하고 요약 건수와 같다(같은 제외 규칙). 열: run_started_at(수집 시작)·observed_at(종목별 조회 직후).
  D. 상세 기록이 실패해도 예외가 밖으로 나가지 않는다(수집·적재 격리) — 반환 -1.
실행: python tests/test_close_revision_detail.py
"""
import io, os, sys, sqlite3, tempfile, contextlib
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import universe_ohlcv as U

fails = 0
def check(name, cond):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        fails += 1

# --- 합성 DB: 종목 A 의 저장 종가
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE daily_ohlcv (ticker TEXT, date TEXT, close INTEGER)")
con.executemany("INSERT INTO daily_ohlcv VALUES (?,?,?)", [
    ("000001", "20260918", 1000), ("000001", "20260919", 1000), ("000001", "20260921", 1000), ("000001", "20260922", 1000)])
df = pd.DataFrame({"Close": [1000, 1020, 1200, 990]},
                  index=pd.to_datetime(["2026-09-18", "2026-09-19", "2026-09-21", "2026-09-22"]))
revs = U.close_revisions(con, "000001", df)
check("A. 값 같음(9/18) 제외 · 재조정 수준(9/21, +20%) 제외 → 9/19·9/22 두 건", sorted(r[0] for r in revs) == ["20260919", "20260922"])
check("A. 튜플에 종목코드 포함", all(len(r) == 4 and r[3] == "000001" for r in revs))

agg = U.summarize_revisions(revs, "20260922")
revs5 = [r + ("20:13:07",) for r in revs]   # collect() 가 붙이는 종목별 조회 직후 시각
check("B. 요약: 오늘(9/22) 제외 → 9/19 1종목 ±2.0%", list(agg) == ["20260919"] and agg["20260919"]["n"] == 1 and abs(agg["20260919"]["max_pct"] - 2.0) < 1e-9)

# --- C. 상세 기록 (임시 경로로 바꿔 끼움)
tmp = Path(tempfile.mkdtemp())
U.REV_DETAIL_CSV = tmp / "logs" / "close_revisions_detail.csv"
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    n = U.log_revision_details(revs5, "20260922", "2026-09-22 20:10:04", agg)
txt = U.REV_DETAIL_CSV.read_text(encoding="utf-8").splitlines()
check("C. 상세 1행 기록(오늘 행 제외) · 반환값 = 행 수", n == 1 and len(txt) == 2)
check("C. 헤더·내용", txt[0] == "run_started_at,observed_at,target_date,ticker,old_close,new_close,pct" and txt[1] == "2026-09-22 20:10:04,20:13:07,20260919,000001,1000,1020,2.00")
check("C. 요약 건수 대조 '일치' 출력", "일치" in buf.getvalue() and "불일치" not in buf.getvalue())
with contextlib.redirect_stdout(io.StringIO()):
    U.log_revision_details(revs, "20260922", "2026-09-23 20:10:04", agg)   # 4-튜플(시각 없음)도 받는다 → observed_at 빈칸
check("C. 누적(append) — 헤더 1번만", len(U.REV_DETAIL_CSV.read_text(encoding="utf-8").splitlines()) == 3)
with contextlib.redirect_stdout(io.StringIO()):
    check("C. 기록할 게 없으면 0 · 파일 그대로", U.log_revision_details([], "20260922", "x", {}) == 0)

# --- D. 실패 격리: 부모가 '파일'인 경로 → mkdir/open 실패 → 예외 없이 -1
blocker = tmp / "blocker"; blocker.write_text("x")
U.REV_DETAIL_CSV = blocker / "sub" / "detail.csv"
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        r = U.log_revision_details(revs5, "20260922", "t", agg)
        raised = False
    except Exception:
        r, raised = None, True
check("D. 기록 실패 시 예외 전파 없음 · 반환 -1 · 경고 1줄", (not raised) and r == -1 and "실패" in buf.getvalue())

print("\n" + ("❌ 실패 %d" % fails if fails else "✅ test_close_revision_detail 통과"))
sys.exit(1 if fails else 0)
