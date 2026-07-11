# -*- coding: utf-8 -*-
"""
market_series.py — 시장 레벨 시계열(지수·환율) 수집 → ohlcv.db `market_daily` (P2)
==============================================================================
왜: §17 결론(절대수익 병목=시장 베타/노출)을 다루려면 시장 레벨 데이터가 필요한데,
ohlcv.db 엔 개별종목뿐 시장 시계열이 없었다(§26-5 P2). 지수·환율 일별 종가를 쌓아
노출/레짐 분석의 기반을 만든다. 점수·표시 미연결(순수 축적).

시리즈(FDR 코드): KS11(KOSPI) · KQ11(KOSDAQ) · USD/KRW(환율).
  - 최초 실행: 2023-06-01 부터 백필(개별종목 ohlcv 백필 기점과 정렬).
  - 이후: DB에 없는 날짜만 증분(idempotent). 실패해도 비치명(exit 0).

사용:
    python market_series.py           # 증분(최초엔 자동 백필)
파이프라인: run_all_and_diversify.bat 에서 universe_ohlcv 다음에 호출.
⚠️ 네트워크(FDR) 사용 — 오프라인 환경에선 자동 생략.
"""
import os
import sys
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
OHLCV_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))
BACKFILL_START = "2023-06-01"

SERIES = {  # 이름: FDR 코드
    "KOSPI": "KS11",
    "KOSDAQ": "KQ11",
    "USDKRW": "USD/KRW",
}

DDL = """CREATE TABLE IF NOT EXISTS market_daily (
    series TEXT NOT NULL,
    date   TEXT NOT NULL,
    close  REAL,
    PRIMARY KEY (series, date)
)"""


def main():
    if not os.path.exists(OHLCV_DB):
        print(f"⚠️ ohlcv.db 없음({OHLCV_DB}) — 생략(비치명).")
        return
    try:
        import FinanceDataReader as fdr
    except ImportError:
        print("⚠️ FinanceDataReader 없음 — 생략(비치명). pip install finance-datareader")
        return
    con = sqlite3.connect(OHLCV_DB)
    con.execute(DDL)
    total = 0
    for name, code in SERIES.items():
        last = con.execute(
            "SELECT MAX(date) FROM market_daily WHERE series=?", (name,)).fetchone()[0]
        start = BACKFILL_START if last is None else \
            f"{last[:4]}-{last[4:6]}-{last[6:]}"  # 마지막 날짜부터(중복은 IGNORE)
        try:
            df = fdr.DataReader(code, start)
        except Exception as e:
            print(f"  ⚠️ {name}({code}) 조회 실패 건너뜀: {e}")
            continue
        if df is None or df.empty or "Close" not in df.columns:
            print(f"  ⚠️ {name}({code}) 데이터 없음/형식 상이 — 건너뜀")
            continue
        rows = [(name, idx.strftime("%Y%m%d"), float(v))
                for idx, v in df["Close"].dropna().items()]
        cur = con.executemany(
            "INSERT OR IGNORE INTO market_daily VALUES (?,?,?)", rows)
        con.commit()
        total += cur.rowcount
        print(f"  ✓ {name}: 신규 {cur.rowcount}행 (마지막 {rows[-1][1] if rows else '-'})")
    n = con.execute("SELECT series, COUNT(*), MAX(date) FROM market_daily GROUP BY series").fetchall()
    con.close()
    print(f"완료: 신규 {total}행. 누적: " + " · ".join(f"{s} {c}행(~{d})" for s, c, d in n))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 실패(비치명 — 파이프라인 계속): {e}")
        sys.exit(0)
