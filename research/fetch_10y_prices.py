# -*- coding: utf-8 -*-
"""10년 일봉(폐지 종목 포함) 수집기 — 연구용 별도 DB. 운영 ohlcv.db 는 건드리지 않는다. (2026-10-21 작성 · 실행은 사용자 승인 뒤, 배치 밖 시간에)

출처(무료·KRX 스크래핑 — 약관·차단 위험 있음, 종목당 쉬어 가며 받는다):
  - 상장 종목: FinanceDataReader.StockListing('KRX')  →  DataReader(code, start, end)
  - 폐지 종목: FinanceDataReader.StockListing('KRX-DELISTING') → DataReader(code, exchange='KRX-DELISTING')
저장: ../dh-q7m3k-data/ohlcv_10y.db
  prices(ticker, date, open, high, low, close, volume, change_pct, source)   PRIMARY KEY(ticker, date)
  meta(ticker, name, market, listed, delisted, status, rows, fetched_at, note)
이어받기: meta.status='done' 인 종목은 건너뛴다. 실패는 status='error' 로 남기고 다음으로.
수정주가: FDR 'KRX' 는 KRX 원시 종가에 가깝고 폐지 종목은 소스 설명이 없다 → 액면분할·무상증자 보정은 **수집 뒤 검증 단계**(pykrx adjusted 와 대조)에서 다룬다. 이 파일은 받기만 한다.
실행 예: python research/fetch_10y_prices.py --smoke 5          (종목 5개만)
         python research/fetch_10y_prices.py --start 2015-01-01 --sleep 0.7   (전체, 1~2시간)
"""
import argparse, sqlite3, sys, time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
DB = REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"
LOG = HERE / "out_fetch_10y.log"


def log(msg):
    line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line)
    try:
        LOG.open("a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass


def ensure(con):
    con.execute("CREATE TABLE IF NOT EXISTS prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, change_pct REAL, source TEXT, PRIMARY KEY(ticker, date))")
    con.execute("CREATE TABLE IF NOT EXISTS meta (ticker TEXT PRIMARY KEY, name TEXT, market TEXT, listed TEXT, delisted TEXT, status TEXT, rows INTEGER, fetched_at TEXT, note TEXT)")
    con.commit()


def listings(fdr):
    """(상장 목록, 폐지 목록) — 각 DataFrame 에 Code/Name/Market(/ListingDate/DelistingDate). 열 이름은 FDR 버전에 따라 다를 수 있어 느슨하게 고른다."""
    cur = fdr.StockListing("KRX")
    try:
        dl = fdr.StockListing("KRX-DELISTING")
    except Exception as e:
        log(f"폐지 목록 실패(상장 종목만 진행): {e}"); dl = None
    return cur, dl


def col(df, *names):
    for n in names:
        if n in df.columns:
            return n
    return None


def to_rows(df, ticker, source):
    out = []
    o, h, l, c, v, ch = (col(df, "Open"), col(df, "High"), col(df, "Low"), col(df, "Close"), col(df, "Volume"), col(df, "Change"))
    for idx, r in df.iterrows():
        d = idx.strftime("%Y%m%d") if hasattr(idx, "strftime") else str(idx)[:10].replace("-", "")
        try:
            close = float(r[c])
        except Exception:
            continue
        if close != close or close <= 0:
            continue
        out.append((ticker, d, float(r[o]) if o else None, float(r[h]) if h else None, float(r[l]) if l else None, close,
                    float(r[v]) if v and r[v] == r[v] else None, float(r[ch]) * 100 if ch and r[ch] == r[ch] else None, source))
    return out


def fetch_one(fdr, code, start, end, delisted):
    if delisted:
        return fdr.DataReader(code, exchange="KRX-DELISTING")
    return fdr.DataReader(code, start, end)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01"); ap.add_argument("--end", default=None)
    ap.add_argument("--sleep", type=float, default=0.7); ap.add_argument("--smoke", type=int, default=0)
    ap.add_argument("--retries", type=int, default=3)
    a = ap.parse_args()
    import FinanceDataReader as fdr
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB); ensure(con)
    cur, dl = listings(fdr)
    plan = []
    cc, cn, cm = col(cur, "Code", "Symbol"), col(cur, "Name"), col(cur, "Market")
    for _, r in cur.iterrows():
        plan.append((str(r[cc]).zfill(6), str(r[cn]), str(r[cm]) if cm else "", "", "", False))
    if dl is not None:
        dc, dn, dm, dd, dli = col(dl, "Symbol", "Code"), col(dl, "Name"), col(dl, "Market"), col(dl, "DelistingDate"), col(dl, "ListingDate")
        for _, r in dl.iterrows():
            plan.append((str(r[dc]).zfill(6), str(r[dn]), str(r[dm]) if dm else "", str(r[dli])[:10] if dli else "", str(r[dd])[:10] if dd else "", True))
    done = {t for (t,) in con.execute("SELECT ticker FROM meta WHERE status='done'")}
    todo = [p for p in plan if p[0] not in done and p[0].isdigit()]
    if a.smoke:
        todo = todo[:a.smoke]
    log(f"대상 {len(plan)}(상장 {len(cur)} · 폐지 {0 if dl is None else len(dl)}) · 이미 받음 {len(done)} · 이번 {len(todo)}")
    ok = err = 0; t0 = time.time()
    for i, (code, name, market, listed, delisted, is_dl) in enumerate(todo, 1):
        df = None; note = ""
        for k in range(a.retries):
            try:
                df = fetch_one(fdr, code, a.start, a.end, is_dl); break
            except Exception as e:
                note = str(e)[:120]; time.sleep(a.sleep * (2 ** k) + 1.0)
        if df is None or len(df) == 0:
            con.execute("INSERT OR REPLACE INTO meta VALUES (?,?,?,?,?,?,?,?,?)", (code, name, market, listed, delisted, "error" if df is None else "empty", 0, datetime.now().isoformat(timespec="seconds"), note))
            con.commit(); err += 1
        else:
            rows = to_rows(df, code, "fdr_delisting" if is_dl else "fdr_krx")
            con.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?,?,?)", rows)
            con.execute("INSERT OR REPLACE INTO meta VALUES (?,?,?,?,?,?,?,?,?)", (code, name, market, listed, delisted, "done", len(rows), datetime.now().isoformat(timespec="seconds"), ""))
            con.commit(); ok += 1
        if i % 50 == 0 or i == len(todo):
            log(f"  {i}/{len(todo)} · 성공 {ok} · 실패 {err} · {time.time()-t0:.0f}s")
        time.sleep(a.sleep)
    n = con.execute("SELECT COUNT(*), MIN(date), MAX(date), COUNT(DISTINCT ticker) FROM prices").fetchone()
    log(f"끝. prices {n[0]:,}행 · {n[1]}~{n[2]} · 종목 {n[3]} · DB {DB.stat().st_size/1048576:.0f}MB")
    con.close()


if __name__ == "__main__":
    main()
