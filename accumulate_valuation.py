# -*- coding: utf-8 -*-
"""
accumulate_valuation.py — 전종목 밸류 스냅샷을 ohlcv.db 에 적재 (관측 데이터 축적)
==============================================================================
왜: fetch_valuation 이 매일 만드는 valuation_{kospi,kosdaq}_{date}.csv 는 전종목
(약 2,700개) PBR/PER/DIV/BPS/EPS 스냅샷인데, cleanup 7일 회전으로 버려지고 있었다
(2026-07-11 발견). 이 스크립트는 루트에 있는 모든 valuation CSV 를 ohlcv.db 의
`valuation_daily` 테이블에 증분 적재해 포인트-인-타임 펀더멘털 히스토리를 쌓는다.

몇 달 쌓이면 열리는 것: 전체종목 가치(E/P·B/P·DIV)·품질(ROE=EPS/BPS) 팩터의
룩어헤드 없는 백테스트 (RESEARCH_wholeuniverse §6 의 '가치 데이터 갭' 해소).

원칙:
  * 증분·idempotent: (ticker,date) PK — 이미 있는 날짜는 건너뜀. 재실행 0행.
  * CSV 는 건드리지 않음(cleanup 회전은 그대로) — 적재 후엔 버려져도 DB에 남음.
  * ohlcv.db 는 B트랙 raw 저장소(universe_ohlcv·kis_flows 와 동일한 쓰기 대상).
    기존 테이블(daily_ohlcv·daily_flows·short_flows)은 일절 안 건드림.
  * 점수·표시 어디에도 연결 안 함(순수 축적). 팩터 승격은 §11 절차로만.

사용:
    python accumulate_valuation.py           # 루트의 모든 valuation_*.csv 적재
파이프라인: run_and_diversify 2.895단계(비치명)가 매일 호출.
"""
import glob
import os
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
OHLCV_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))

DDL = """CREATE TABLE IF NOT EXISTS valuation_daily (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,
    market TEXT,
    pbr REAL, per REAL, div REAL, bps REAL, eps REAL,
    PRIMARY KEY (ticker, date)
)"""


def main():
    files = sorted(glob.glob(str(HERE / "valuation_*_*.csv")))
    if not files:
        print("적재할 valuation_*.csv 없음 — 종료(비치명).")
        return
    if not os.path.exists(OHLCV_DB):
        print(f"⚠️ ohlcv.db 없음({OHLCV_DB}) — 적재 생략(비치명).")
        return
    con = sqlite3.connect(OHLCV_DB)
    con.execute(DDL)
    have = {d for (d,) in con.execute("SELECT DISTINCT date FROM valuation_daily")}
    total = 0
    for p in files:
        m = re.match(r"valuation_(kospi|kosdaq)_(\d{8})\.csv", os.path.basename(p))
        if not m:
            continue
        mkt, date = m.group(1), m.group(2)
        # 같은 날짜는 시장별로 함께 들어가므로 (date,market) 단위로 스킵 판단
        n_exist = con.execute(
            "SELECT COUNT(*) FROM valuation_daily WHERE date=? AND market=?",
            (date, mkt)).fetchone()[0]
        if n_exist > 0:
            continue
        try:
            v = pd.read_csv(p, dtype={"ticker": str}, encoding="utf-8-sig")
        except Exception as e:
            print(f"  ⚠️ {os.path.basename(p)} 파싱 실패 건너뜀: {e}")
            continue
        need = {"ticker", "PBR", "PER", "DIV", "BPS", "EPS"}
        if not need.issubset(v.columns):
            print(f"  ⚠️ {os.path.basename(p)} 컬럼 불일치 건너뜀: {list(v.columns)}")
            continue
        for c in ("PBR", "PER", "DIV", "BPS", "EPS"):
            v[c] = pd.to_numeric(v[c], errors="coerce")
        rows = [(str(t), date, mkt, pbr, per, dv, bps, eps)
                for t, pbr, per, dv, bps, eps in
                v[["ticker", "PBR", "PER", "DIV", "BPS", "EPS"]].itertuples(index=False)]
        cur = con.executemany(
            "INSERT OR IGNORE INTO valuation_daily VALUES (?,?,?,?,?,?,?,?)", rows)
        con.commit()
        total += cur.rowcount  # OR IGNORE 로 걸러진 중복 제외한 실제 삽입 수
        print(f"  ✓ {date} {mkt}: {cur.rowcount}행 적재")
    n_dates = con.execute("SELECT COUNT(DISTINCT date) FROM valuation_daily").fetchone()[0]
    n_rows = con.execute("SELECT COUNT(*) FROM valuation_daily").fetchone()[0]
    con.close()
    print(f"완료: 신규 {total}행. 누적 {n_dates}일 · {n_rows}행 (valuation_daily).")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 실패(비치명 — 파이프라인 계속): {e}")
        sys.exit(0)
