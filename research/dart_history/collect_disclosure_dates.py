# -*- coding: utf-8 -*-
"""collect_disclosure_dates.py — DART 공시목록(list.json)에서 '언제 처음 알려졌나' 날짜만 모은다 (연구용, 2026-10-04)

왜: 실적 시험(research/target20_wide_20261004/e4_events.py)은 정기보고서 접수일을 썼다. 대형주는 그보다 몇 주 앞서
    잠정실적(공정공시)을 내고, 정정본이 있으면 저장된 접수번호가 정정본 것이라 원본 접수일을 모른다.
무엇: 기간을 한 달씩 잘라 종목 구분 없이 조회(회사 지정 없이 조회하면 3개월 제한) → 상장사 행만 저장.
    A001 사업보고서 · A002 반기보고서 · A003 분기보고서(원본·정정 모두, last_reprt_at=N)
    I002 공정공시(잠정실적 포함) · I001 수시공시 중 제목에 '손익구조' 가 든 것(매출액또는손익구조 30% 변동)
저장: dart_hist.db 의 filings 표(운영 DB·캐시 안 건드림). 숫자는 안 받는다 — 날짜·제목뿐.
안전: dart_rate(분당 600) · 평일 19:55~22:40 쉼 · 한도 초과(020)면 멈춤 · 다시 돌리면 끝난 (종류, 달)은 건너뜀.
사용: python research/dart_history/collect_disclosure_dates.py [--probe] [--status] [--kinds A001,A002,A003,I002,I001]
"""
import argparse, os, sqlite3, sys, time
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
from collect_dart_history import call, log, in_batch_window, DB      # noqa: E402  같은 재시도·속도 상한·기록
from run_and_diversify import load_dotenv                            # noqa: E402

URL = "https://opendart.fss.or.kr/api/list.json"
START = date(2023, 4, 1)
KEEP = {"I001": ("손익구조",)}     # 이 종류는 제목에 이 말이 든 행만 저장


def ensure(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS filings(rcept_no TEXT PRIMARY KEY, kind TEXT, corp_code TEXT, stock_code TEXT, corp_cls TEXT,
        report_nm TEXT, rcept_dt TEXT, flr_nm TEXT, rm TEXT);
    CREATE TABLE IF NOT EXISTS filings_done(kind TEXT, bgn TEXT, end TEXT, total INTEGER, kept INTEGER, fetched_at TEXT, PRIMARY KEY(kind, bgn));
    CREATE INDEX IF NOT EXISTS idx_fil_stock ON filings(stock_code, rcept_dt);
    """)


def months(today):
    y, m = START.year, START.month
    while (y, m) <= (today.year, today.month):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        end = min(date(ny, nm, 1).toordinal() - 1, today.toordinal())
        yield date(y, m, 1).strftime("%Y%m%d"), date.fromordinal(end).strftime("%Y%m%d"), (y, m) == (today.year, today.month)
        y, m = ny, nm


def fetch_page(api_key, kind, bgn, end, page):
    import requests
    from collect_dart_history import _drate
    for attempt in range(3):
        try:
            _drate.wait()
            d = requests.get(URL, params=dict(crtfc_key=api_key, bgn_de=bgn, end_de=end, pblntf_detail_ty=kind, last_reprt_at="N",
                                              page_no=page, page_count=100, sort="date", sort_mth="asc"), timeout=20).json()
            st = str(d.get("status", ""))
            if st in ("000", "013"): return d, st
            if st in ("1020", "900", "901", "902") and attempt < 2: time.sleep(3 ** attempt); continue
            return d, st
        except Exception as e:
            if attempt < 2: time.sleep(3 ** attempt); continue
            return {"message": str(e)[:120]}, "REQUEST_ERROR"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--probe", action="store_true"); ap.add_argument("--status", action="store_true")
    ap.add_argument("--kinds", default="A001,A002,A003,I002,I001"); a = ap.parse_args()
    con = sqlite3.connect(DB); ensure(con)
    if a.status:
        for r in con.execute("SELECT kind, COUNT(*), MIN(rcept_dt), MAX(rcept_dt) FROM filings GROUP BY kind"): print(r)
        print("끝난 (종류, 달):", con.execute("SELECT COUNT(*) FROM filings_done").fetchone()[0]); return 0
    load_dotenv(str(REPO / ".env")); api_key = os.environ.get("DART_API_KEY", "")
    if len(api_key) < 30: log("DART_API_KEY 없음(.env)"); return 1
    if a.probe:
        for kind in a.kinds.split(","):
            d, st = fetch_page(api_key, kind, "20260801", "20260831", 1)
            print(kind, "status", st, d.get("message"), "total_count", d.get("total_count"), "total_page", d.get("total_page"), "| 첫 행:", {k: (d.get("list") or [{}])[0].get(k) for k in ("corp_name", "stock_code", "report_nm", "rcept_dt")})
        return 0
    calls = 0; today = date.today()
    for kind in a.kinds.split(","):
        for bgn, end, current in months(today):
            if con.execute("SELECT 1 FROM filings_done WHERE kind=? AND bgn=?", (kind, bgn)).fetchone(): continue
            while in_batch_window(): log("배치 시간(평일 19:55~22:40) — 쉼"); time.sleep(600)
            page, total, kept, tp = 1, 0, 0, 1
            while page <= tp:
                d, st = fetch_page(api_key, kind, bgn, end, page); calls += 1
                if st == "020": log(f"DART 일일 한도(020) — 멈춤 (호출 {calls}). 내일 같은 명령으로 이어서."); con.commit(); return 2
                if st == "013": break
                if st != "000": log(f"{kind} {bgn} p{page} 실패 {st} {d.get('message')}"); con.rollback(); return 3
                tp = int(d.get("total_page") or 1); total = int(d.get("total_count") or 0)
                for r in d.get("list") or []:
                    sc = (r.get("stock_code") or "").strip()
                    if not sc: continue
                    if kind in KEEP and not any(w in (r.get("report_nm") or "") for w in KEEP[kind]): continue
                    con.execute("INSERT OR REPLACE INTO filings VALUES(?,?,?,?,?,?,?,?,?)", (r.get("rcept_no"), kind, r.get("corp_code"), sc, r.get("corp_cls"), (r.get("report_nm") or "").strip(), r.get("rcept_dt"), r.get("flr_nm"), r.get("rm")))
                    kept += 1
                page += 1
            if not current:   # 이번 달은 아직 안 끝났으니 '끝남' 표시를 안 한다
                con.execute("INSERT OR REPLACE INTO filings_done VALUES(?,?,?,?,?,?)", (kind, bgn, end, total, kept, datetime.now().strftime("%Y%m%d_%H%M%S")))
            con.commit(); log(f"{kind} {bgn[:6]}: 전체 {total} · 저장 {kept} · 누적 호출 {calls}")
    log(f"끝 — 호출 {calls}"); return 0


if __name__ == "__main__":
    sys.exit(main())
