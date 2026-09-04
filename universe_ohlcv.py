# -*- coding: utf-8 -*-
"""
universe_ohlcv.py — 전체 KOSPI/KOSDAQ 일별 OHLCV 수집 (B 트랙 토대)

설계: PROJECT_KNOWLEDGE.md §21
  - 과매도 게이트 *없이* 전체 종목 일봉 적재 (모멘텀/매집/장기백테스트 공통 raw)
  - 별도 파일 ohlcv.db (history.db 와 분리 — 용량·격리·성격 분리)
  - 원재료(OHLCV) 저장, 완성품(RSI/이동평균) 미저장 → 분석 시 계산
  - FDR(FinanceDataReader) 사용. 수정주가 기본 제공(2018 삼성 분할 실측 확인).

사용:
  python universe_ohlcv.py --backfill --years 3      # 최초 3년 백필 (전체 종목, 무거움)
  python universe_ohlcv.py                            # 일상 증분 (최근 N일만, .bat 용)
  python universe_ohlcv.py --backfill --limit 100     # 시험: 100종목만
  python universe_ohlcv.py --status                   # 적재 현황만 출력

실무 함정 대책(§21):
  ① 생존편향: 상폐/거래정지 종목도 받아지는 만큼 적재(빼지 않음). 못 받으면 스킵 기록.
  ② 시계열 구멍: FDR 이 거래일만 주므로 자연히 영업일 기준. run 과 무관하게 매일 증분.
  ③ 거래정지: Volume=0 행도 저장하되 is_suspended=1 로 표시(분석서 제외 판단).
  ④ 포인트-인-타임 시총: 그날 close × 그날 shares. shares 는 마스터 현재값을 매 적재일에 기록
     (상장주식수는 자주 안 변하므로 근사. 분할일 전후만 주의 — 수정주가라 가격은 이미 조정됨).
"""
import argparse
import sqlite3
import time
import sys
import os
from datetime import datetime, timedelta

DB_DIR = os.path.join("..", "dh-q7m3k-data")  # ★ 레포 바깥(git·핸드오프 범위 밖). raw 데이터 격리.
DB_PATH = os.path.join(DB_DIR, "ohlcv.db")
INCREMENTAL_WINDOW = 7        # 일상 증분 시 최근 며칠 재확인(공백/정정 흡수)
ADJ_TOL = 0.05                # [2026-09-04] 재확인 창에서 기존 종가와 새 종가가 이만큼 어긋나면 '수정주가 재조정'(감자·분할)으로
                              #   보고 그 종목의 전 기간을 다시 받는다. 7일 창만 덮어쓰면 과거는 옛 배수로 남아 가짜 급등이 생김
                              #   (실측 2026-08-21~25 감자 재상장 15종목: +400~+1,577% 단절 — patch_note/20260904_ops_fixes.md)
SLEEP = 0.0                   # FDR 은 rate limit 부담 적음. 필요시 0.1~0.3 으로.

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_ohlcv (
    ticker        TEXT NOT NULL,
    date          TEXT NOT NULL,        -- YYYYMMDD
    open          INTEGER,
    high          INTEGER,
    low           INTEGER,
    close         INTEGER,              -- 수정종가(FDR 기본)
    volume        INTEGER,
    change_pct    REAL,                 -- FDR Change(등락률), 보너스
    shares        INTEGER,              -- 적재 시점 상장주식수(마스터). 시총=close*shares
    is_suspended  INTEGER DEFAULT 0,    -- 1=거래정지 의심(volume 0)
    market        TEXT,                 -- KOSPI/KOSDAQ
    fetched_at    TEXT,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_ohlcv_date   ON daily_ohlcv(date);
CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker ON daily_ohlcv(ticker);

-- 수집 실패/스킵 종목 기록 (생존편향 추적용 — 왜 빠졌는지 남김)
CREATE TABLE IF NOT EXISTS ohlcv_skips (
    ticker     TEXT,
    reason     TEXT,
    at_date    TEXT,
    fetched_at TEXT
);
"""


def _connect():
    """DB 폴더(레포 바깥)가 없으면 만들고 연결."""
    os.makedirs(DB_DIR, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def ensure_schema(con):
    con.executescript(SCHEMA)
    con.commit()


def get_universe():
    """FDR 종목마스터에서 전체 KOSPI/KOSDAQ 리스트 + 시총/주식수.
    반환: list of dict(code, name, market, shares, marcap)."""
    import FinanceDataReader as fdr
    print("• 종목 유니버스 로드 (FDR StockListing 'KRX')")
    krx = fdr.StockListing("KRX")
    # 컬럼: Code, Name, Market, Stocks, Marcap, ... (실측 확인됨)
    out = []
    for _, r in krx.iterrows():
        code = str(r.get("Code", "")).strip()
        mkt = str(r.get("Market", "")).strip()
        # 우선주/리츠/스팩 등도 일단 포함(필터는 분석 단계). 단 코드 6자리만.
        if len(code) != 6 or not code.isdigit():
            continue
        if mkt not in ("KOSPI", "KOSDAQ"):
            continue
        out.append({
            "code": code,
            "name": str(r.get("Name", "")).strip(),
            "market": mkt,
            "shares": _safe_int(r.get("Stocks")),
            "marcap": _safe_int(r.get("Marcap")),
        })
    print(f"  → {len(out)}종목 (KOSPI/KOSDAQ)")
    return out


def _safe_int(v):
    try:
        if v is None:
            return None
        return int(float(v))
    except (ValueError, TypeError):
        return None


def latest_date_in_db(con, ticker):
    row = con.execute(
        "SELECT MAX(date) FROM daily_ohlcv WHERE ticker=?", (ticker,)
    ).fetchone()
    return row[0] if row and row[0] else None


def fetch_ohlcv(code, start, end):
    """FDR 일봉. 반환 DataFrame(index=Date, cols=Open/High/Low/Close/Volume/Change)
    또는 빈 경우 None."""
    import FinanceDataReader as fdr
    try:
        df = fdr.DataReader(code, start, end)
        if df is None or len(df) == 0:
            return None
        return df
    except Exception as e:
        return ("ERR", str(e)[:120])


def upsert_ohlcv(con, code, market, shares, df, fetched_at, shares_by_date=None):
    """INSERT OR REPLACE. 반환 적재 행수. 빈 df 면 0(에러 미저장).
    shares_by_date: {YYYYMMDD: shares} — 전 기간 재적재 시 기존 행의 주식수(PIT)를 보존하기 위해 사용."""
    rows = []
    for idx, r in df.iterrows():
        d = idx.strftime("%Y%m%d") if hasattr(idx, "strftime") else str(idx).replace("-", "")[:8]
        vol = _safe_int(r.get("Volume"))
        suspended = 1 if (vol is None or vol == 0) else 0
        rows.append((
            code, d,
            _safe_int(r.get("Open")), _safe_int(r.get("High")),
            _safe_int(r.get("Low")), _safe_int(r.get("Close")),
            vol,
            float(r["Change"]) if "Change" in r and r["Change"] == r["Change"] else None,
            (shares_by_date.get(d, shares) if shares_by_date else shares), suspended, market, fetched_at,
        ))
    if not rows:
        return 0
    con.executemany(
        """INSERT OR REPLACE INTO daily_ohlcv
           (ticker,date,open,high,low,close,volume,change_pct,shares,is_suspended,market,fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    return len(rows)


def adjustment_detected(con, code, df, tol=ADJ_TOL):
    """재확인 창의 겹치는 날짜에서 DB 종가와 새 종가가 tol 이상 어긋나면 True(수정주가 재조정)."""
    try:
        dates = [idx.strftime("%Y%m%d") if hasattr(idx, "strftime") else str(idx).replace("-", "")[:8] for idx in df.index]
        if not dates:
            return False
        q = "SELECT date, close FROM daily_ohlcv WHERE ticker=? AND date BETWEEN ? AND ?"
        old = dict(con.execute(q, (code, min(dates), max(dates))).fetchall())
        for idx, r in df.iterrows():
            d = idx.strftime("%Y%m%d") if hasattr(idx, "strftime") else str(idx).replace("-", "")[:8]
            c_old = old.get(d); c_new = _safe_int(r.get("Close"))
            if c_old and c_new and abs(c_new / c_old - 1.0) > tol:
                return True
    except Exception:
        return False
    return False


def earliest_date_in_db(con, code):
    row = con.execute("SELECT MIN(date) FROM daily_ohlcv WHERE ticker=?", (code,)).fetchone()
    return row[0] if row and row[0] else None


def full_start_for(con, code, global_start):
    """전 기간 재적재 시작일: DB 에 있는 가장 오래된 날짜와 백필 기준일 중 더 이른 쪽(옛 배수 행이 남지 않게)."""
    first = earliest_date_in_db(con, code)
    if first:
        f = f"{first[:4]}-{first[4:6]}-{first[6:]}"
        return min(f, global_start)
    return global_start


def shares_map(con, code):
    return dict(con.execute("SELECT date, shares FROM daily_ohlcv WHERE ticker=?", (code,)).fetchall())


def record_skip(con, code, reason, at_date, fetched_at):
    con.execute(
        "INSERT INTO ohlcv_skips (ticker,reason,at_date,fetched_at) VALUES (?,?,?,?)",
        (code, reason, at_date, fetched_at),
    )


def collect(backfill=False, years=3, limit=None, incremental_window=INCREMENTAL_WINDOW, tickers=None):
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now()
    con = _connect()
    ensure_schema(con)

    universe = get_universe()
    if tickers:
        want = {t.strip() for t in tickers.split(",") if t.strip()}
        universe = [u for u in universe if u["code"] in want]
        print(f"  [지정 종목 전 기간 재적재] {len(universe)}종목: {sorted(want)}")
    if limit:
        universe = universe[:limit]
        print(f"  [시험모드] 앞 {limit}종목만")

    global_start = (today - timedelta(days=int(years * 365.25) + 5)).strftime("%Y-%m-%d")
    if backfill:
        print(f"• 백필 모드: {global_start} ~ 오늘, {len(universe)}종목")
    else:
        print(f"• 증분 모드: 종목별 최신일 이후만(최근 {incremental_window}일 재확인), {len(universe)}종목")

    end = today.strftime("%Y-%m-%d")
    n_ok = n_skip = n_rows = n_readj = 0
    t0 = time.time()

    for i, item in enumerate(universe, 1):
        code, mkt, shares = item["code"], item["market"], item["shares"]

        if backfill:
            start = global_start
        elif tickers:
            start = full_start_for(con, code, global_start)
        else:
            last = latest_date_in_db(con, code)
            if last:
                # 최신일에서 window 만큼 뒤로 물러나 재확인(정정·공백 흡수)
                ld = datetime.strptime(last, "%Y%m%d")
                start = (ld - timedelta(days=incremental_window)).strftime("%Y-%m-%d")
            else:
                # DB 에 없는 신규 종목 → 증분에서도 짧게 백필(1년)
                start = (today - timedelta(days=370)).strftime("%Y-%m-%d")

        res = fetch_ohlcv(code, start, end)
        if isinstance(res, tuple) and res[0] == "ERR":
            record_skip(con, code, f"fetch_error:{res[1]}", end, fetched_at)
            n_skip += 1
        elif res is None:
            # 데이터 없음(상폐/신규/거래없음) — 생존편향 추적용 기록
            record_skip(con, code, "no_data", end, fetched_at)
            n_skip += 1
        else:
            smap = None
            if tickers:
                smap = shares_map(con, code)                       # 지정 재적재: 기존 주식수(PIT) 보존
            elif not backfill and adjustment_detected(con, code, res):
                # 수정주가 재조정 감지 → 전 기간 다시 받아 옛 배수 행을 전부 교체(주식수는 기존 PIT 보존)
                full = fetch_ohlcv(code, full_start_for(con, code, global_start), end)
                if isinstance(full, tuple) or full is None:
                    print(f"  ⚠️  {code} 수정주가 재조정 감지했으나 전 기간 재수집 실패 — 이번엔 창만 적재(다음 실행 재시도)")
                else:
                    res = full; smap = shares_map(con, code); n_readj += 1
                    print(f"  ♻️  {code} 수정주가 재조정 감지(재확인 창 종가 불일치 >{ADJ_TOL:.0%}) → 전 기간 {len(res)}행 재적재")
            added = upsert_ohlcv(con, code, mkt, shares, res, fetched_at, shares_by_date=smap)
            n_rows += added
            n_ok += 1

        if SLEEP:
            time.sleep(SLEEP)

        if i % 100 == 0 or i == len(universe):
            el = time.time() - t0
            rate = i / el if el > 0 else 0
            eta = (len(universe) - i) / rate if rate > 0 else 0
            con.commit()
            print(f"  [{i}/{len(universe)}] ok={n_ok} skip={n_skip} rows={n_rows:,} "
                  f"| {el:.0f}s, ETA {eta:.0f}s")

    con.commit()
    con.close()
    print(f"\n[완료] 성공 {n_ok}종목 / 스킵 {n_skip} / 총 {n_rows:,}행 적재 / 수정주가 재조정 재적재 {n_readj}종목")
    print(f"       소요 {time.time()-t0:.0f}초. DB: {DB_PATH}")


def status():
    con = _connect()
    ensure_schema(con)
    c = con.cursor()
    n = c.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0]
    nt = c.execute("SELECT COUNT(DISTINCT ticker) FROM daily_ohlcv").fetchone()[0]
    nd = c.execute("SELECT COUNT(DISTINCT date) FROM daily_ohlcv").fetchone()[0]
    rng = c.execute("SELECT MIN(date), MAX(date) FROM daily_ohlcv").fetchone()
    nsus = c.execute("SELECT COUNT(*) FROM daily_ohlcv WHERE is_suspended=1").fetchone()[0]
    nskip = c.execute("SELECT COUNT(*) FROM ohlcv_skips").fetchone()[0]
    import os
    sz = os.path.getsize(DB_PATH) / 1e6 if os.path.exists(DB_PATH) else 0
    print(f"=== {DB_PATH} 현황 ===")
    print(f"  총 {n:,}행 · {nt}종목 · {nd}거래일 ({rng[0]}~{rng[1]})")
    print(f"  거래정지 의심행(volume=0): {nsus:,}")
    print(f"  스킵 기록(상폐/오류): {nskip}")
    print(f"  파일 크기: {sz:.0f}MB")
    con.close()


def main():
    ap = argparse.ArgumentParser(description="전체 종목 일별 OHLCV 수집 (ohlcv.db)")
    ap.add_argument("--backfill", action="store_true", help="과거 백필 모드")
    ap.add_argument("--years", type=float, default=3, help="백필 연수(기본 3)")
    ap.add_argument("--limit", type=int, default=None, help="앞 N종목만(시험용)")
    ap.add_argument("--window", type=int, default=INCREMENTAL_WINDOW,
                    help="증분 재확인 윈도(일)")
    ap.add_argument("--status", action="store_true", help="현황만 출력")
    ap.add_argument("--tickers", type=str, default=None,
                    help="지정 종목만 전 기간 재적재(쉼표 구분). 감자·분할 후 옛 배수 행 교정용")
    args = ap.parse_args()

    if args.status:
        status()
        return
    collect(backfill=args.backfill, years=args.years,
            limit=args.limit, incremental_window=args.window, tickers=args.tickers)


if __name__ == "__main__":
    main()
