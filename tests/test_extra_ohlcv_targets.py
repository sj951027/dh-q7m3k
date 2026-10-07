# -*- coding: utf-8 -*-
"""대형 보충표(daily_ohlcv_extra) 대상 선정 회귀(2026-10-07) — 임시 DB·가짜 상장목록만, 네트워크·운영 DB 미접촉.

사건: 상장목록 캐시 출처가 FDR 로 바뀌자 코스닥 글로벌·영문코드 136종목이 목록에서 빠져 보충 대상이 0 이 됐고,
      보충표가 10/02 에서 조용히 멈췄다(10/06·10/07 배치 '보충 대상 0종목').
계약:
  A. 상장목록에 있고 본 표에 없는 종목은 종전대로 대상(0-diff).
  B. 보충표에 이미 있는 종목은 상장목록에서 사라져도 계속 대상 — 시장·주식수는 표의 마지막 행에서.
  C. 본 표(daily_ohlcv)에 생긴 종목은 둘 중 어디에 있어도 빠진다(읽는 쪽 본 표 우선).
  D. 중복 없음 · 상장목록 캐시가 비어도 보충표 종목이 있으면 진행, 둘 다 없으면 종전처럼 멈춤.
실행: python tests/test_extra_ohlcv_targets.py
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


import extra_ohlcv as X  # noqa: E402

LISTING = [{"code": "005930", "market": "KOSPI", "shares": 10, "name": "A"},    # 본 표에 있음 → 대상 아님
           {"code": "0126Z0", "market": "KOSDAQ", "shares": 20, "name": "B"},   # 본 표에 없음 → 대상(①)
           {"code": "999999", "market": "KONEX", "shares": 1, "name": "C"}]     # 시장 밖 → 대상 아님
FAKE = {"rows": LISTING, "at": "2026-10-07 20:10"}
sys.modules["listing_cache"] = types.SimpleNamespace(load=lambda market="KRX": (FAKE["rows"], FAKE["at"]))

tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "ohlcv.db")
con = sqlite3.connect(db)
con.executescript("CREATE TABLE daily_ohlcv (ticker TEXT, date TEXT, close INTEGER);")
con.executescript(X.SCHEMA)
con.executemany("INSERT INTO daily_ohlcv VALUES (?,?,?)", [("005930", "20261007", 1), ("000660", "20261007", 1)])
# 보충표 기존 종목: 196170(코스닥 글로벌, 목록에 없음) · 000660(본 표에 생김) · 0126Z0(목록에도 있음)
con.executemany(f"INSERT INTO {X.TABLE} (ticker,date,close,shares,market) VALUES (?,?,?,?,?)",
                [("196170", "20261001", 5, 111, "KOSDAQ"), ("196170", "20261002", 6, 222, "KOSDAQ"),
                 ("000660", "20261002", 7, 333, "KOSPI"), ("0126Z0", "20261002", 8, 444, "KOSDAQ")])
con.commit()


def targets():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out, at = X.target_tickers(con)
    return out, at, buf.getvalue()


print("[A·B·C·D] 대상 선정")
out, at, log = targets()
codes = [r["code"] for r in out]
check("A. 목록에 있고 본 표에 없는 0126Z0 은 종전대로 대상(목록 행 그대로: 주식수 20)", "0126Z0" in codes and next(r for r in out if r["code"] == "0126Z0")["shares"] == 20)
check("B. 목록에서 빠진 보충표 종목 196170 도 대상 — 시장·주식수는 표의 마지막 행(KOSDAQ·222)",
      next((r for r in out if r["code"] == "196170"), None) == {"code": "196170", "market": "KOSDAQ", "shares": 222, "name": ""}, str(out))
check("C. 본 표에 생긴 000660(보충표에 있어도)·005930(목록에 있어도)은 빠진다", "000660" not in codes and "005930" not in codes)
check("시장 밖(KONEX)은 종전대로 제외 · 중복 없음 · 캐시 시각 전달", "999999" not in codes and len(codes) == len(set(codes)) == 2 and at == FAKE["at"])
check("구성 로그 한 줄(목록 1 + 기존 1)", "상장목록 기준 1종목 + 보충표 기존 1종목" in log, log)

print("[D] 목록이 비었을 때")
FAKE["rows"] = None
out, at, log = targets()
check("상장목록 캐시가 비어도 보충표 종목으로 진행(196170·0126Z0)", sorted(r["code"] for r in out) == ["0126Z0", "196170"])
con.execute(f"DELETE FROM {X.TABLE}"); con.commit()
try:
    with contextlib.redirect_stdout(io.StringIO()):
        X.target_tickers(con)
    stopped = False
except SystemExit:
    stopped = True
check("둘 다 없으면 종전처럼 멈춤(SystemExit)", stopped)
FAKE["rows"] = LISTING

print("[배선] 배치")
bat = open(REPO / "run_all_and_diversify.bat", encoding="utf-8", errors="replace").read()
check("배치가 extra_ohlcv.py 를 부른다", "python extra_ohlcv.py" in bat)
con.close()
print(f"\n{P}개 통과")
