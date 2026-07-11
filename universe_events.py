# -*- coding: utf-8 -*-
"""
universe_events.py — 상폐·거래정지 이벤트 전진 기록 → ohlcv.db `universe_events` (P3)
==============================================================================
왜: ohlcv 백필은 '현재 상장' 종목만 담아 생존편향이 있다(§26-5 P3). 과거는 못 고치지만
앞으로는 "언제 어떤 종목이 사라졌나/정지됐나"를 매일 기록해 편향을 전진 차단한다.
몇 달 쌓이면 백테스트에서 상폐 직전 종목의 실제 처리(0 수익 가정 등)가 가능해진다.

이벤트(직전 거래일 대비 diff, 점수·표시 미연결):
  DISAPPEARED : 직전 거래일엔 시세가 있었는데 오늘 없음(상폐/이전상장/수집실패 — 원인 미구분,
                해석은 분석 시. 수집실패였다면 다음날 REAPPEARED 로 자동 상쇄 확인 가능)
  REAPPEARED  : 사라졌던 종목의 시세 재등장
  SUSPENDED   : is_suspended 0→1 (거래정지 시작)
  RESUMED     : is_suspended 1→0 (거래재개)
  NEW         : 신규 등장(신규상장/재상장)

증분·idempotent: (date,ticker,event) PK. 같은 날 재실행 0행. 실패해도 비치명.
사용:
    python universe_events.py          # 최신 거래일 1일치 diff
    python universe_events.py --backfill   # DB 전체 기간 소급 기록(최초 1회)
"""
import argparse
import os
import sys
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
OHLCV_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))

DDL = """CREATE TABLE IF NOT EXISTS universe_events (
    date   TEXT NOT NULL,
    ticker TEXT NOT NULL,
    event  TEXT NOT NULL,
    market TEXT,
    PRIMARY KEY (date, ticker, event)
)"""


def diff_one(con, d_prev, d_now):
    q = "SELECT ticker, market, is_suspended FROM daily_ohlcv WHERE date=?"
    prev = {t: (m, s) for t, m, s in con.execute(q, (d_prev,))}
    now = {t: (m, s) for t, m, s in con.execute(q, (d_now,))}
    ev = []
    for t in prev.keys() - now.keys():
        ev.append((d_now, t, "DISAPPEARED", prev[t][0]))
    for t in now.keys() - prev.keys():
        # 과거 어디에도 없던 티커면 NEW, 있었으면 REAPPEARED
        seen = con.execute(
            "SELECT 1 FROM daily_ohlcv WHERE ticker=? AND date<? LIMIT 1",
            (t, d_prev)).fetchone()
        ev.append((d_now, t, "REAPPEARED" if seen else "NEW", now[t][0]))
    for t in prev.keys() & now.keys():
        s0, s1 = prev[t][1] or 0, now[t][1] or 0
        if s0 != s1:
            ev.append((d_now, t, "SUSPENDED" if s1 else "RESUMED", now[t][0]))
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", help="DB 전 기간 소급(최초 1회)")
    args = ap.parse_args()
    if not os.path.exists(OHLCV_DB):
        print(f"⚠️ ohlcv.db 없음({OHLCV_DB}) — 생략(비치명).")
        return
    con = sqlite3.connect(OHLCV_DB)
    con.execute(DDL)
    dates = [d for (d,) in con.execute(
        "SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
    if len(dates) < 2:
        print("거래일 2일 미만 — 비교 불가.")
        return
    pairs = list(zip(dates[:-1], dates[1:])) if args.backfill else [(dates[-2], dates[-1])]
    total = 0
    for d_prev, d_now in pairs:
        ev = diff_one(con, d_prev, d_now)
        if ev:
            cur = con.executemany(
                "INSERT OR IGNORE INTO universe_events VALUES (?,?,?,?)", ev)
            total += cur.rowcount
    con.commit()
    summ = con.execute(
        "SELECT event, COUNT(*) FROM universe_events GROUP BY event ORDER BY 2 DESC").fetchall()
    con.close()
    print(f"완료: 신규 {total}건. 누적: " + (" · ".join(f"{e} {c}" for e, c in summ) or "없음"))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 실패(비치명 — 파이프라인 계속): {e}")
        sys.exit(0)
