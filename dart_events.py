# -*- coding: utf-8 -*-
"""dart_events.py — DART 주요사항보고 공시 이벤트 수집 (2026-08-30, 관측 전용)

근거: research/RESEARCH_feasibility_sector_dart_20260830.md — 희석 이벤트(주식수 증가)가
과매도 유니버스 진입 종목의 87%에 걸리며 ex_h20 −9%p대(CI 0 제외). 유형 구분(유상/무상/
CB·BW/감자/자사주)과 정확한 공시일·예고 공시는 DART 만 제공해 수집을 시작함.

설계 원칙:
  * 순수 축적 — 점수·판정·표시 어디에도 미연결(판정·점수 0-diff by construction).
    활용(플래그 관측 적재·검증)은 판정 시즌 후 별도 결정.
  * 저장: ohlcv.db `dart_events` (rcept_no PK, INSERT OR IGNORE → 재실행·중복 안전)
  * 기본 실행: 마지막 적재일 3일 전 ~ 오늘 증분. `--backfill YYYYMMDD` 로 소급 수집.
  * 소스: opendart list.json, pblntf_ty='B'(주요사항보고)·corp_cls Y/K 만 — 호출량 작음.
    rate limit 보수적(호출 간 0.25s, 일 20,000건 한도 대비 수백 건 수준).
  * 실패는 비치명 — run_and_diversify 의 run_script 가 경고만 남기고 계속 진행.

사용:
  python dart_events.py                  # 증분
  python dart_events.py --backfill 20230601   # 소급(ohlcv 가격 이력 시작점에 맞춤)
"""
import argparse
import datetime as dt
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

from catalyst_insider import load_env   # .env 로더 재사용 (DART_API_KEY)

HERE = Path(__file__).resolve().parent
OHLCV_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))
API_URL = "https://opendart.fss.or.kr/api/list.json"
PAGE_COUNT = 100
CHUNK_DAYS = 60          # 날짜창 분할(페이지 폭주 방지)
SLEEP_SEC = 0.25

# report_nm → 유형. 순서 중요('유무상' → '유상' → '무상').
EVENT_PATTERNS = [
    ("유무상증자", "paid_bonus_mix"),
    ("유상증자",   "paid_in"),        # 희석(실측 음(-)의 주 대상)
    ("무상증자",   "bonus"),
    ("전환사채",   "cb"),
    ("신주인수권부사채", "bw"),
    ("교환사채",   "eb"),
    ("감자",       "reduction"),
    ("주식소각",   "retire"),
    ("자기주식.{0,6}취득", "buyback"),
    ("자기주식.{0,6}처분", "buyback_sell"),
]


def classify(report_nm):
    for pat, typ in EVENT_PATTERNS:
        if re.search(pat, report_nm or ""):
            return typ
    return None


def fetch_json(params):
    """실호출 분리(테스트에서 monkeypatch). '000' 정상 / '013' 데이터 없음."""
    import requests
    r = requests.get(API_URL, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def ensure_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS dart_events(
        rcept_no  TEXT PRIMARY KEY,
        rcept_dt  TEXT NOT NULL,
        ticker    TEXT NOT NULL,
        corp_name TEXT,
        market    TEXT,
        event_type TEXT NOT NULL,
        report_nm TEXT,
        fetched_at TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_dart_events_td ON dart_events(ticker, rcept_dt)")


def collect(con, key, bgn, end, fetch=fetch_json, sleep=True):
    """[bgn, end] 구간의 Y/K 주요사항보고를 적재. 신규 삽입 행수 반환."""
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ins = 0
    d0 = dt.datetime.strptime(bgn, "%Y%m%d").date()
    d1 = dt.datetime.strptime(end, "%Y%m%d").date()
    while d0 <= d1:
        d_hi = min(d0 + dt.timedelta(days=CHUNK_DAYS - 1), d1)
        for cls in ("Y", "K"):
            page = 1
            while True:
                js = fetch({"crtfc_key": key, "bgn_de": f"{d0:%Y%m%d}",
                            "end_de": f"{d_hi:%Y%m%d}", "corp_cls": cls,
                            "pblntf_ty": "B", "page_no": page,
                            "page_count": PAGE_COUNT})
                st = js.get("status")
                if st == "013":          # 데이터 없음
                    break
                if st != "000":
                    raise RuntimeError(f"DART status {st}: {js.get('message')}")
                for row in js.get("list", []):
                    tic = (row.get("stock_code") or "").strip()
                    if not tic:          # 비상장 제외
                        continue
                    typ = classify(row.get("report_nm"))
                    if typ is None:      # 관심 유형 외 스킵
                        continue
                    cur = con.execute(
                        "INSERT OR IGNORE INTO dart_events"
                        "(rcept_no,rcept_dt,ticker,corp_name,market,event_type,report_nm,fetched_at)"
                        " VALUES(?,?,?,?,?,?,?,?)",
                        (row.get("rcept_no"), row.get("rcept_dt"), tic.zfill(6),
                         row.get("corp_name"), cls, typ, row.get("report_nm"), now))
                    ins += cur.rowcount
                total = int(js.get("total_page") or 1)
                if page >= total:
                    break
                page += 1
                if sleep:
                    time.sleep(SLEEP_SEC)
            if sleep:
                time.sleep(SLEEP_SEC)
        d0 = d_hi + dt.timedelta(days=1)
    con.commit()
    return ins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", help="YYYYMMDD 부터 소급 수집(기본: 증분)")
    ap.add_argument("--end", help="YYYYMMDD 까지(기본: 오늘)")
    ap.add_argument("--db", default=OHLCV_DB)
    args = ap.parse_args()

    load_env()
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        print("⚠️ .env 의 DART_API_KEY 없음 — 수집 생략(비치명).")
        return 0
    if not os.path.exists(args.db):
        print(f"⚠️ ohlcv.db 없음({args.db}) — 수집 생략(비치명).")
        return 0

    con = sqlite3.connect(args.db)
    ensure_table(con)
    end = args.end or dt.date.today().strftime("%Y%m%d")
    if args.backfill:
        bgn = args.backfill
    else:
        last = con.execute("SELECT MAX(rcept_dt) FROM dart_events").fetchone()[0]
        if last:                          # 3일 겹침(PK 중복 무해) — 지연 공시 보강
            bgn = (dt.datetime.strptime(last, "%Y%m%d") - dt.timedelta(days=3)).strftime("%Y%m%d")
        else:
            bgn = (dt.date.today() - dt.timedelta(days=30)).strftime("%Y%m%d")
            print(f"   첫 실행 — 최근 30일({bgn}~)부터. 소급은 --backfill 사용.")
    print(f"   수집 구간 {bgn} ~ {end}")
    ins = collect(con, key, bgn, end)
    n = con.execute("SELECT COUNT(*) FROM dart_events").fetchone()[0]
    print(f"   💾 dart_events: 신규 {ins}건 적재 (누적 {n}건)")
    con.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:              # 비치명 — 파이프라인 계속
        print(f"   ⚠️ dart_events 실패(비치명): {e}")
        sys.exit(1)
