# -*- coding: utf-8 -*-
"""10년 일봉(폐지 종목 포함) 수집기 — 연구용 별도 DB. 운영 ohlcv.db 는 건드리지 않는다. (2026-10-21 작성 · 같은 날 Codex 검토 4건 반영)

출처(무료·스크래핑 — 약관·차단 위험 있음, 종목당 쉬어 가며 받는다). 설치된 FinanceDataReader 0.9.202 는 `exchange=` 인자를 무시하고
**종목 문자열 접두어**로 소스를 고른다(Codex 실측) → 반드시 접두어로 지정한다:
  - 상장 종목: DataReader('NAVER:005930', start, end)        → NAVER 일별(fdr_naver). 'KRX:' 경로는 2년 제한(400)이라 못 씀(실측)
  - 폐지 종목: DataReader('NAVER:005930', start, 폐지일) → NAVER 일별(fdr_naver_delisted). KRX-DELISTING 경로는 2026-10-21 실측 전부 400.
저장: ../dh-q7m3k-data/ohlcv_10y.db
  prices(ticker, date, open, high, low, close, volume, change_pct(소수, 운영 DB 와 같음), source)   PRIMARY KEY(ticker, date)
  meta(ticker, name, market, listed, delisted, status, rows, fetched_at, note)   note = "start=YYYY-MM-DD;end=…;src=…"
이어받기: meta.status='done' 이고 note 의 start 가 요청 start 이하(그리고 end 가 요청 end 이상)인 종목만 건너뛴다(Codex 4).
유효 가격 0행이면 'empty'(완료 아님, 다음 실행 때 재시도) (Codex 3).
수정주가: 소스별 처리가 다를 수 있어 **수집 뒤 검증 단계**(pykrx adjusted 와 대조)에서 다룬다. 이 파일은 받기만 한다.
실행 예: python research/fetch_10y_prices.py --smoke 5
         python research/fetch_10y_prices.py --start 2015-01-01 --sleep 0.5    (전체, 2시간 안팎)
         python research/fetch_10y_prices.py --only-delisted                    (폐지 종목만)
"""
import argparse, sqlite3, sys, time
from datetime import datetime, date
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


def col(df, *names):
    for n in names:
        if n in df.columns:
            return n
    return None


def listings(fdr):
    cur = fdr.StockListing("KRX")
    try:
        dl = fdr.StockListing("KRX-DELISTING")
    except Exception as e:
        log(f"폐지 목록 실패(상장 종목만 진행): {e}"); dl = None
    return cur, dl


def to_rows(df, ticker, source):
    out = []
    o, h, l, c, v, ch = (col(df, "Open"), col(df, "High"), col(df, "Low"), col(df, "Close"), col(df, "Volume"), col(df, "Change"))
    if c is None:
        return out
    for idx, r in df.iterrows():
        d = idx.strftime("%Y%m%d") if hasattr(idx, "strftime") else str(idx)[:10].replace("-", "")
        try:
            close = float(r[c])
        except Exception:
            continue
        if close != close or close <= 0:
            continue
        def f(k):
            try:
                x = float(r[k]); return x if x == x else None
            except Exception:
                return None
        out.append((ticker, d, f(o) if o else None, f(h) if h else None, f(l) if l else None, close, f(v) if v else None,
                    (f(ch) if ch else None), source))      # 소수(0.29 = +29%) — 운영 ohlcv.db.change_pct 와 같은 단위(검토 지적: ×100 섞이면 100배 함정)
    return out


def fetch_one(fdr, code, start, end, delisted, delisted_date=""):
    """접두어로 소스 지정(0.9.202 실측). 상장 = KRX 일별, 폐지 = NAVER(KRX-DELISTING 경로는 2026-10-21 실측 전부 400 → 폐지 코드도 NAVER 가
    상장일~폐지일 이력을 그대로 준다). 폐지 종목은 end 를 폐지일로 잘라 넘긴다."""
    if delisted:
        e = min(end, delisted_date) if delisted_date else end
        return fdr.DataReader(f"NAVER:{code}", start, e)
    return fdr.DataReader(f"NAVER:{code}", start, end)      # KRX: 경로는 "Period is up to 2 years" 400(2026-10-21 실측) → 상장 종목도 NAVER


def parse_note(note):
    out = {}
    for part in str(note or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1); out[k.strip()] = v.strip()
    return out


def covered(note, start, end):
    """이미 받은 범위가 요청 범위를 덮나(Codex 4). note 에 범위가 없으면(옛 행) 덮지 않은 것으로."""
    n = parse_note(note)
    if "start" not in n:
        return False
    if n["start"] > start:
        return False
    if end and n.get("end", "") and n["end"] < end:
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01"); ap.add_argument("--end", default=None)
    ap.add_argument("--sleep", type=float, default=0.5); ap.add_argument("--smoke", type=int, default=0)
    ap.add_argument("--retries", type=int, default=3); ap.add_argument("--only-delisted", action="store_true")
    a = ap.parse_args()
    end = a.end or date.today().isoformat()
    import FinanceDataReader as fdr
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB); ensure(con)
    cur, dl = listings(fdr)
    plan = []
    cc, cn, cm = col(cur, "Code", "Symbol"), col(cur, "Name"), col(cur, "Market")
    if not a.only_delisted:
        for _, r in cur.iterrows():
            plan.append((str(r[cc]).zfill(6), str(r[cn]), str(r[cm]) if cm else "", "", "", False))
    if dl is not None:
        dc, dn, dm, dd, dli = col(dl, "Symbol", "Code"), col(dl, "Name"), col(dl, "Market"), col(dl, "DelistingDate"), col(dl, "ListingDate")
        sg = col(dl, "SecuGroup")
        for _, r in dl.iterrows():
            ddate = str(r[dd])[:10] if dd else ""
            if ddate and ddate < a.start:                      # 수집 시작일 전에 폐지된 종목은 받을 자료가 없다(1961년 폐지 등 → 400)
                continue
            if sg and str(r[sg]) not in ("주권", "외국주권"):   # ETF·ETN·수익증권·신주인수권 등은 제외
                continue
            plan.append((str(r[dc]).zfill(6), str(r[dn]), str(r[dm]) if dm else "", str(r[dli])[:10] if dli else "", ddate, True))
    done = {t: note for (t, note) in con.execute("SELECT ticker, note FROM meta WHERE status='done'")}
    todo = [p for p in plan if p[0].isdigit() and not (p[0] in done and covered(done[p[0]], a.start, a.end))]   # --end 를 안 주면 끝날짜는 안 본다(다음날 재실행 때 전부 다시 받던 것 방지)
    skipped = len(plan) - len(todo)
    if a.smoke:
        todo = todo[:a.smoke]
    n_dl = sum(1 for p in plan if p[5])
    log(f"대상 {len(plan)}(상장 {len(plan)-n_dl} · 폐지(시작일 이후·주권) {n_dl}) · 범위 덮인 완료 {skipped} · 이번 {len(todo)} · {a.start}~{end}")
    ok = err = empty = 0; t0 = time.time()
    for i, (code, name, market, listed, delisted, is_dl) in enumerate(todo, 1):
        df = None; note = ""; src = "fdr_naver_delisted" if is_dl else "fdr_naver"
        for k in range(a.retries):
            try:
                df = fetch_one(fdr, code, a.start, end, is_dl, delisted); break
            except Exception as e:
                note = str(e)[:120]; time.sleep(a.sleep * (2 ** k) + 1.0)
        rows = to_rows(df, code, src) if df is not None else []
        now = datetime.now().isoformat(timespec="seconds")
        if df is None:
            con.execute("INSERT OR REPLACE INTO meta VALUES (?,?,?,?,?,?,?,?,?)", (code, name, market, listed, delisted, "error", 0, now, note)); err += 1
        elif not rows:                                  # Codex 3: 유효 가격 0행은 완료가 아니다
            con.execute("INSERT OR REPLACE INTO meta VALUES (?,?,?,?,?,?,?,?,?)", (code, name, market, listed, delisted, "empty", 0, now, f"start={a.start};end={end};src={src};raw_rows={len(df)}")); empty += 1
        else:
            con.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?,?,?)", rows)
            con.execute("INSERT OR REPLACE INTO meta VALUES (?,?,?,?,?,?,?,?,?)", (code, name, market, listed, delisted, "done", len(rows), now, f"start={a.start};end={end};src={src}")); ok += 1
        con.commit()
        if i % 50 == 0 or i == len(todo):
            log(f"  {i}/{len(todo)} · 성공 {ok} · 빈 {empty} · 실패 {err} · {time.time()-t0:.0f}s")
        time.sleep(a.sleep)
    n = con.execute("SELECT COUNT(*), MIN(date), MAX(date), COUNT(DISTINCT ticker) FROM prices").fetchone()
    s = con.execute("SELECT source, COUNT(DISTINCT ticker) FROM prices GROUP BY source").fetchall()
    log(f"끝. prices {n[0]:,}행 · {n[1]}~{n[2]} · 종목 {n[3]} · 소스별 {s} · DB {DB.stat().st_size/1048576:.0f}MB")
    con.close()


if __name__ == "__main__":
    main()
