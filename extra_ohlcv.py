# -*- coding: utf-8 -*-
"""
extra_ohlcv.py — 시세 보충 표 `daily_ohlcv_extra` (대형 트랙 판정 전용)

왜: 본 시세 수집(universe_ohlcv.py)은 FDR 상장목록에서 Market 이 정확히 KOSPI/KOSDAQ 이고 숫자 6자리 코드인
   종목만 담는다 → 코스닥 글로벌 세그먼트(알테오젠·에코프로 …)·영문 섞인 신규 코드(0126Z0 …)가 시세 DB에 없다.
   대형 트랙(ls_t1)은 그 종목에도 점수가 있어 선행수익을 못 구하면 판정 표본에서 조용히 빠진다
   (코스닥 쪽 시총 40% — research/RESEARCH_ohlcv_gap_large_20261003.md).
어떻게: 본 표(daily_ohlcv)는 건드리지 않는다(lowvol·wu 유니버스 불변 — 현역 모델 spec 동결).
   상장목록 캐시(listing_cache)에 있지만 daily_ohlcv 에 없는 종목만 **별도 표** daily_ohlcv_extra 에 담는다.
   읽는 쪽(leaderboard.py ls_t1 블록·build_large_test.py)은 본 표를 우선하고, 본 표에 없는 종목만 이 표로 채운다.
   사용자 결정 2026-10-03 (a)안.

사용:
  python extra_ohlcv.py                     # 일상 증분(최근 7일 재확인) — run_all_and_diversify.bat 에서 universe_ohlcv 다음
  python extra_ohlcv.py --backfill --years 3
  python extra_ohlcv.py --status
"""
import argparse
import sqlite3
import sys
import os
from datetime import datetime, timedelta

import universe_ohlcv as U          # fetch_ohlcv / _safe_int / DB_PATH 재사용 (본 표에는 쓰지 않음)

TABLE = "daily_ohlcv_extra"
INCREMENTAL_WINDOW = 7

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    ticker        TEXT NOT NULL,
    date          TEXT NOT NULL,
    open          INTEGER, high INTEGER, low INTEGER, close INTEGER,
    volume        INTEGER,
    change_pct    REAL,
    shares        INTEGER,
    is_suspended  INTEGER DEFAULT 0,
    market        TEXT,
    fetched_at    TEXT,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_ohlcv_extra_date ON {TABLE}(date);
"""


def _connect(path=None):
    p = path or U.DB_PATH
    if not os.path.exists(p):
        raise SystemExit(f"ohlcv.db 없음: {p} — 본 시세 표가 먼저 있어야 한다")
    con = sqlite3.connect(p)
    con.executescript(SCHEMA)
    return con


def target_tickers(con):
    """보충 대상 = ① 상장목록 캐시(KOSPI/KOSDAQ)에 있고 daily_ohlcv 에 한 번도 없는 종목
                 + ② 이미 이 표에 있는 종목(본 표에 아직 없는 것). 반환 (list of dict, 캐시 시각).
    [2026-10-07] ②를 더했다 — 상장목록 캐시의 출처가 FDR 로 바뀌면서 코스닥 글로벌·영문코드 136종목이 목록에서
    빠져 ①이 0 이 됐고, 그 결과 이 표가 10/02 에서 조용히 멈춰 있었다(10/06·10/07 배치 로그 '보충 대상 0종목').
    이 표에 한 번 들어온 종목은 목록 출처와 무관하게 계속 받는다. 본 표에 생기면 그때 빠진다(읽는 쪽은 본 표 우선)."""
    import listing_cache
    rows, at = listing_cache.load("KRX")
    have = {r[0] for r in con.execute("SELECT DISTINCT ticker FROM daily_ohlcv")}
    out = [r for r in (rows or []) if r.get("market") in ("KOSPI", "KOSDAQ") and r.get("code") and r["code"] not in have]
    seen = {r["code"] for r in out}
    n_list = len(out)
    for code, market, shares in con.execute(
            f"SELECT t.ticker, t.market, t.shares FROM {TABLE} t "
            f"WHERE t.date = (SELECT MAX(date) FROM {TABLE} WHERE ticker = t.ticker) ORDER BY t.ticker"):
        if code in have or code in seen:
            continue
        out.append({"code": code, "market": market or "", "shares": shares, "name": ""})
        seen.add(code)
    if not out and not rows:
        raise SystemExit("listing_cache 비어 있음 — 배치가 한 번 돌아 캐시가 있어야 한다")
    print(f"  대상 구성: 상장목록 기준 {n_list}종목 + 보충표 기존 {len(out) - n_list}종목")
    return out, at


def latest_date(con, ticker):
    r = con.execute(f"SELECT MAX(date) FROM {TABLE} WHERE ticker=?", (ticker,)).fetchone()
    return r[0] if r else None


def upsert(con, code, market, shares, df, fetched_at):
    rows = []
    for idx, r in df.iterrows():
        d = idx.strftime("%Y%m%d") if hasattr(idx, "strftime") else str(idx).replace("-", "")[:8]
        vol = U._safe_int(r.get("Volume"))
        rows.append((code, d, U._safe_int(r.get("Open")), U._safe_int(r.get("High")), U._safe_int(r.get("Low")),
                     U._safe_int(r.get("Close")), vol,
                     float(r["Change"]) if "Change" in r and r["Change"] == r["Change"] else None,
                     shares, 1 if (vol is None or vol == 0) else 0, market, fetched_at))
    if rows:
        con.executemany(f"INSERT OR REPLACE INTO {TABLE} (ticker,date,open,high,low,close,volume,change_pct,"
                        f"shares,is_suspended,market,fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def collect(backfill=False, years=3, window=INCREMENTAL_WINDOW, db=None):
    con = _connect(db)
    targets, at = target_tickers(con)
    today = datetime.now()
    end = today.strftime("%Y-%m-%d")
    fetched_at = today.strftime("%Y%m%d_%H%M")
    global_start = (today - timedelta(days=365 * years)).strftime("%Y-%m-%d")
    print(f"• 보충 대상 {len(targets)}종목 (상장목록 캐시 {at}, daily_ohlcv 에 없는 종목 + 보충표 기존 종목) · "
          f"{'백필 ' + global_start + '~' if backfill else '증분 최근 ' + str(window) + '일'}")
    n_ok = n_skip = n_rows = 0
    for i, t in enumerate(targets, 1):
        code, mkt = t["code"], t["market"]
        if backfill:
            start = global_start
        else:
            last = latest_date(con, code)
            if last:
                start = (datetime.strptime(last, "%Y%m%d") - timedelta(days=window)).strftime("%Y-%m-%d")
            else:
                start = global_start          # 새로 생긴 대상(신규 상장 등)은 처음 한 번 전 기간
        df = U.fetch_ohlcv(code, start, end)
        if df is None or isinstance(df, tuple):
            n_skip += 1
            con.execute("INSERT INTO ohlcv_skips(ticker,reason,at_date,fetched_at) VALUES (?,?,?,?)",
                        (code, "extra:" + (df[1] if isinstance(df, tuple) else "empty"), end.replace("-", ""), fetched_at))
            continue
        n_rows += upsert(con, code, mkt, t.get("shares"), df, fetched_at)
        n_ok += 1
        if i % 50 == 0 or i == len(targets):
            con.commit()
            print(f"  [{i}/{len(targets)}] ok={n_ok} skip={n_skip} rows={n_rows:,}")
    con.commit()
    status(con)
    con.close()
    return n_skip, len(targets)


def status(con=None, db=None):
    own = con is None
    if own:   # [2026-10-03] --status 는 읽기 전용(표를 만들지 않는다)
        p = db or U.DB_PATH
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        if not con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone():
            print(f"• {TABLE}: 아직 없음(백필 전)"); con.close(); return
    n, nt, d0, d1 = con.execute(f"SELECT COUNT(*), COUNT(DISTINCT ticker), MIN(date), MAX(date) FROM {TABLE}").fetchone()
    dup = con.execute(f"SELECT COUNT(DISTINCT e.ticker) FROM {TABLE} e WHERE e.ticker IN (SELECT DISTINCT ticker FROM daily_ohlcv)").fetchone()[0]
    print(f"• {TABLE}: {nt}종목 {n:,}행 {d0}~{d1} · 본 표와 겹치는 종목 {dup}(겹치면 읽는 쪽이 본 표 우선)")
    if own:
        con.close()


def load_extra_close(db=None, exclude=()):
    """읽기 전용: date×ticker 종가표. exclude(본 표 종목)에 있는 종목은 뺀다 — 본 표 우선.
    표가 없으면 빈 DataFrame. leaderboard.py(ls_t1 블록)·build_large_test.py 가 쓴다."""
    import pandas as pd
    p = db or U.DB_PATH
    if not os.path.exists(p):
        return pd.DataFrame()
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        if not con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone():
            return pd.DataFrame()
        px = pd.read_sql(f"SELECT ticker, date, close FROM {TABLE}", con)
    finally:
        con.close()
    if px.empty:
        return pd.DataFrame()
    px["ticker"] = px["ticker"].astype(str)
    px = px[~px["ticker"].isin(set(exclude))]
    return px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()


def main():
    ap = argparse.ArgumentParser(description="대형 트랙용 시세 보충 표(daily_ohlcv_extra) 수집")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--db", default=None)
    a = ap.parse_args()
    if a.status:
        status(db=a.db); return 0
    n_skip, n_targets = collect(backfill=a.backfill, years=a.years, db=a.db)
    if n_targets and n_skip >= n_targets:   # [2026-10-03] 전부 실패 → 배치 FAILED 에 잡히게. 일부 실패는 로그만(한 종목 때문에 전체를 세우지 않음)
        print(f"❌ 보충 수집 전부 실패({n_skip}/{n_targets})"); return 2
    if n_skip: print(f"⚠ 보충 수집 일부 실패 {n_skip}/{n_targets} — 다음 증분에서 재시도")
    return 0


if __name__ == "__main__":
    sys.exit(main())
