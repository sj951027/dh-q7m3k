#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
earnings_incr.py — 실적 악화 배지용 정기보고서 **증분 수집** (2026-10-07 신설 · 수집 전용 · 점수·순위·판정 0-diff)
========================================================================================================
왜: earnings_flag.py 의 자료(earnings.db earnings_q)는 연구 수집본을 한 번 옮긴 것이라 2026 반기보고서(8월 접수)까지다.
    60거래일 창이라 11월 중순이면 배지가 전부 사라진다. 3분기 보고서(11/14 마감)부터는 배치가 새 접수분을 스스로 받아야 한다.
무엇: 매일 ① DART 공시목록(list.json)에서 최근 접수된 정기보고서(사업·반기·분기, 상장사, 12월 결산)를 찾고
      ② 보고서마다 재무 API(fnlttSinglAcntAll, 연결 → 별도)를 불러 3개월 영업이익·전년 같은 분기를 뽑아
      ③ 접수일 직전 거래일의 종가 × 그날 주식수로 시총을 **한 번 계산해 고정 저장**(병합·분할 문제가 새 자료부터 사라짐)
      ④ earnings_q 에 넣는다(source='incr'). 같은 (종목·연도·보고서)가 이미 있으면 값만 갱신하고 **접수일·시총은 원본 것을 유지**.
      분기값 계산식은 earnings_flag.quarter_values 그대로(원자료는 earnings_raw 표에 보관 — 누적 차분·전년 동기에 필요).
안전: DART 호출 속도 상한 dart_rate 공유 · 실패는 경고만(배치 계속, 종료코드 0) · DART_API_KEY 없으면 건너뜀 ·
      운영 캐시(dart_cache)·history.db·ohlcv.db 는 읽기만 · 마지막 조회일을 기록해 다음 실행이 이어받는다(겹침 3일).
사용:
  python earnings_incr.py                      # 증분(마지막 조회일 −3일 ~ 오늘). 배치: extra_ohlcv 다음·run_and_diversify 앞
  python earnings_incr.py --dry-run            # 받을 목록만 보고 저장 안 함(재무 API 도 안 부름)
  python earnings_incr.py --start 20260901     # 조회 시작일 지정(첫 실행)
  python earnings_incr.py --verify 20          # 이미 있는 2026 반기 행 N개를 다시 받아 값 대조(저장 안 함)
  python earnings_incr.py --status
"""
import argparse
import calendar
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import earnings_flag as EF          # noqa: E402  quarter_values · 상수(PRICE_MAX_AGE·SUE_CAP) · DB 경로
import dart_rate as _drate          # noqa: E402  분당 상한(배치의 다른 DART 단계와 같은 규칙)

LIST_URL = "https://opendart.fss.or.kr/api/list.json"
FIN_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
REPRT_CODE = {"Y": "11011", "Q1": "11013", "H1": "11012", "Q3": "11014"}
KIND_OF_NAME = (("사업보고서", "A001"), ("반기보고서", "A002"), ("분기보고서", "A003"))
REPRT_OF = {("A001", "12"): "Y", ("A002", "06"): "H1", ("A003", "03"): "Q1", ("A003", "09"): "Q3"}
DEPS = {"Y": (("Q3", 0),), "Q3": (("H1", 0), ("Q3", -1)), "H1": (("Q1", 0), ("H1", -1)), "Q1": (("Q1", -1),)}   # (보고서, 연도 차) — 전년 동기·누적 차분용
OVERLAP_DAYS = 3                 # 다음 실행이 다시 보는 날수(늦게 올라오는 목록·정정 대비)
DEFAULT_START = "20260901"       # 연구 수집본의 마지막 접수일 다음 달 — 첫 실행 기준
FILING_WINDOW_DAYS = 130         # 결산 종료일 뒤 이 날수 안의 접수만(연구와 같음)
PAGE = 100
SOURCE = "incr"

RAW_SCHEMA = """
CREATE TABLE IF NOT EXISTS earnings_raw(ticker TEXT, year INTEGER, reprt TEXT, fs TEXT, rcept_no TEXT,
    th REAL, th_add REAL, fr REAL, fr_q REAL, fr_add REAL, fetched_at TEXT, PRIMARY KEY(ticker, year, reprt));
CREATE TABLE IF NOT EXISTS earnings_meta(key TEXT PRIMARY KEY, value TEXT);
"""


# ----------------------------------------------------------------------------- 순수 함수
def num(v):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "", "-") else None
    except ValueError:
        return None


def parse_filing(row):
    """공시목록 한 행 → 정기보고서 정보 dict, 대상이 아니면 None.
    대상: 상장사(Y/K) · 종목코드 있음 · 제목 '사업/반기/분기보고서 (YYYY.MM)' · 12월 결산(사업 12 · 반기 06 · 분기 03/09)."""
    if (row.get("corp_cls") or "") not in ("Y", "K"):
        return None
    stock = str(row.get("stock_code") or "").strip()
    if not stock.isdigit() or len(stock) != 6:
        return None
    nm = row.get("report_nm") or ""
    kind = next((k for word, k in KIND_OF_NAME if word in nm), None)
    m = re.search(r"\((\d{4})\.(\d{2})\)", nm)
    if not kind or not m:
        return None
    reprt = REPRT_OF.get((kind, m.group(2)))
    if not reprt:
        return None                     # 12월 결산이 아닌 회사(결산월이 다름) — 분기 맞추기가 어긋나 제외(배지 규칙과 같음)
    return {"ticker": stock, "corp_code": str(row.get("corp_code") or ""), "kind": kind, "reprt": reprt, "year": int(m.group(1)),
            "ym": m.group(1) + m.group(2), "amend": "정정" in nm, "rcept_no": str(row.get("rcept_no") or ""),
            "rcept_dt": str(row.get("rcept_dt") or "")}


def op_item(items):
    """재무 응답에서 영업이익 행(손익계산서/포괄손익계산서) — earnings_flag.rebuild_from_research 와 같은 규칙."""
    for it in items:
        if it.get("account_id") == "dart_OperatingIncomeLoss" and it.get("sj_div") in ("IS", "CIS"):
            return it
    for it in items:
        if it.get("sj_div") in ("IS", "CIS") and (it.get("account_nm") or "").replace(" ", "") in ("영업이익", "영업이익(손실)", "영업손익", "영업손실"):
            return it
    return None


def raw_from_items(items, fs, rcept_no):
    it = op_item(items or [])
    if it is None:
        return None
    return dict(fs=fs, rcept_no=rcept_no, th=num(it.get("thstrm_amount")), th_add=num(it.get("thstrm_add_amount")), fr=num(it.get("frmtrm_amount")),
                fr_q=num(it.get("frmtrm_q_amount")), fr_add=num(it.get("frmtrm_add_amount")))


def in_filing_window(ym, rcept_dt):
    """결산 종료일 < 접수일 ≤ 종료일 + 130일 (연구와 같은 규칙)."""
    end = f"{ym}{calendar.monthrange(int(ym[:4]), int(ym[4:]))[1]:02d}"
    return end < rcept_dt <= (datetime.strptime(end, "%Y%m%d") + timedelta(days=FILING_WINDOW_DAYS)).strftime("%Y%m%d")


def mcap_at(ocon, ticker, d8, max_age=EF.PRICE_MAX_AGE):
    """접수일 직전 거래일(접수 전 max_age 일 안)의 종가 × 그날 주식수 → (시총, 주식수, 시세 날짜). 본 표 → 보충표 순. 없으면 (None, None, None)."""
    lo = (datetime.strptime(d8, "%Y%m%d") - timedelta(days=max_age)).strftime("%Y%m%d")
    tabs = ["daily_ohlcv"]
    if ocon.execute("SELECT 1 FROM sqlite_master WHERE name='daily_ohlcv_extra'").fetchone():
        tabs.append("daily_ohlcv_extra")
    for tab in tabs:
        r = ocon.execute(f"SELECT close, shares, date FROM {tab} WHERE ticker=? AND date<? AND date>=? AND close>0 AND shares>0 ORDER BY date DESC LIMIT 1",
                         (ticker, d8, lo)).fetchone()
        if r:
            return float(r[0]) * float(r[1]), float(r[1]), str(r[2])
    return None, None, None


# ----------------------------------------------------------------------------- DART 호출
def fetch_json(url, params, api_key):
    """실호출(테스트에서 바꿔 끼움). 반환 dict(status, message, list). 재시도·속도 상한은 연구 수집기와 같다."""
    import requests
    last = None
    for attempt in range(3):
        try:
            _drate.wait()
            r = requests.get(url, params=dict(params, crtfc_key=api_key), timeout=20)
            d = r.json()
            st = str(d.get("status", ""))
            if st in ("1020", "900", "901", "902") and attempt < 2:
                time.sleep(3 ** attempt); continue
            return d
        except Exception as e:          # 연결·타임아웃·JSON 오류
            last = e
            if attempt < 2:
                time.sleep(3 ** attempt); continue
    return {"status": "REQUEST_ERROR", "message": str(last)[:120], "list": []}


def fetch_filings(api_key, bgn, end, fetch=fetch_json, counts=None):
    """기간 안 정기보고서(pblntf_ty=A) 목록 — 상장사 Y·K 각각, 페이지 전부. 반환 (parse_filing 통과 행 목록, 호출 수)."""
    out, calls = [], 0
    for cls in ("Y", "K"):
        page = 1
        while True:
            d = fetch(LIST_URL, {"bgn_de": bgn, "end_de": end, "corp_cls": cls, "pblntf_ty": "A", "page_no": page, "page_count": PAGE}, api_key); calls += 1
            st = str(d.get("status", ""))
            if st == "013":            # 데이터 없음
                break
            if st != "000":
                if counts is not None:
                    counts["list_error"] = counts.get("list_error", 0) + 1
                print(f"  ⚠ 공시목록 조회 실패({cls} p{page}): {st} {str(d.get('message', ''))[:60]}")
                break
            rows = d.get("list") or []
            out.extend(f for f in (parse_filing(r) for r in rows) if f)
            if counts is not None:
                counts["list_rows"] = counts.get("list_rows", 0) + len(rows)
            total = int(d.get("total_page") or 1)
            if page >= total or not rows:
                break
            page += 1
    out.sort(key=lambda f: (f["rcept_dt"], f["rcept_no"]))
    return out, calls


def fetch_report(api_key, corp_code, year, reprt, rcept_no, fetch=fetch_json):
    """재무 API: 연결(CFS) → 별도(OFS). 영업이익 행이 있으면 raw dict, 없으면 None. 반환 (raw|None, 호출 수, 마지막 status)."""
    calls, st = 0, ""
    for fs in ("CFS", "OFS"):
        d = fetch(FIN_URL, {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": REPRT_CODE[reprt], "fs_div": fs}, api_key); calls += 1
        st = str(d.get("status", ""))
        if st == "020":
            raise RuntimeError("DART_DAILY_LIMIT")
        if st != "000":
            continue
        raw = raw_from_items(d.get("list") or [], fs, rcept_no)
        if raw:
            return raw, calls, st
    return None, calls, st


# ----------------------------------------------------------------------------- 저장소
def open_db(path=EF.EARN_DB):
    con = sqlite3.connect(path)
    con.executescript(RAW_SCHEMA)
    con.execute("""CREATE TABLE IF NOT EXISTS earnings_q(ticker TEXT, year INTEGER, reprt TEXT, reprt_ord INTEGER, rcept_dt TEXT,
                   q_op REAL, q_op_prev REAL, mcap_prev REAL, sue REAL, source TEXT, PRIMARY KEY(ticker, year, reprt))""")
    cols = {r[1] for r in con.execute("PRAGMA table_info(earnings_q)")}
    for col, typ in (("shares_at", "REAL"), ("px_dt", "TEXT")):      # [2026-10-07] 시총 고정 저장의 근거(주식수·시세 날짜) — 기존 행은 NULL
        if col not in cols:
            con.execute(f"ALTER TABLE earnings_q ADD COLUMN {col} {typ}")
    con.commit()
    return con


def meta_get(con, key, default=None):
    r = con.execute("SELECT value FROM earnings_meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def meta_set(con, key, value):
    con.execute("INSERT OR REPLACE INTO earnings_meta(key, value) VALUES(?,?)", (key, str(value)))


def load_rep(con, ticker):
    """earnings_raw → quarter_values 가 읽는 모양 {(ticker, year, reprt): dict}."""
    rep = {}
    for y, r, fs, rc, th, th_add, fr, fr_q, fr_add in con.execute(
            "SELECT year, reprt, fs, rcept_no, th, th_add, fr, fr_q, fr_add FROM earnings_raw WHERE ticker=?", (ticker,)):
        rep[(ticker, int(y), r)] = dict(fs=fs, rcept_no=rc, th=th, th_add=th_add, fr=fr, fr_q=fr_q, fr_add=fr_add)
    return rep


def save_raw(con, ticker, year, reprt, raw, fetched_at):
    con.execute("INSERT OR REPLACE INTO earnings_raw VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ticker, year, reprt, raw["fs"], raw["rcept_no"], raw["th"], raw["th_add"], raw["fr"], raw["fr_q"], raw["fr_add"], fetched_at))


def ensure_raw(con, api_key, f, year, reprt, fetch, counts, fetched_at, force=False):
    """(ticker, year, reprt) 원자료를 raw 표에서 읽거나 받아 둔다. force 면 다시 받는다(정정). 반환 raw|None."""
    cur = con.execute("SELECT fs, rcept_no, th, th_add, fr, fr_q, fr_add FROM earnings_raw WHERE ticker=? AND year=? AND reprt=?", (f["ticker"], year, reprt)).fetchone()
    if cur and not force:
        return dict(fs=cur[0], rcept_no=cur[1], th=cur[2], th_add=cur[3], fr=cur[4], fr_q=cur[5], fr_add=cur[6])
    raw, calls, st = fetch_report(api_key, f["corp_code"], year, reprt, f["rcept_no"] if (year, reprt) == (f["year"], f["reprt"]) else "", fetch)
    counts["calls"] += calls
    if raw is None:
        counts["no_values"] += 1
        return None
    save_raw(con, f["ticker"], year, reprt, raw, fetched_at)
    return raw


def process(con, ocon, filings, api_key, fetch=fetch_json, dry=False, now=None):
    """공시 목록(parse_filing 결과들)을 차례로 처리. 반환 counts dict. dry=True 면 DART 재무 호출·저장 없이 분류만."""
    now = now or datetime.now()
    fetched_at = now.strftime("%Y%m%d_%H%M")
    counts = dict(filings=len(filings), new=0, updated=0, done=0, amend_no_orig=0, window=0, no_values=0, no_price=0, extreme=0, calls=0, dry=0)
    for f in filings:
        t, y, r = f["ticker"], f["year"], f["reprt"]
        if not in_filing_window(f["ym"], f["rcept_dt"]):
            counts["window"] += 1; continue
        exist = con.execute("SELECT rcept_dt, mcap_prev, shares_at, px_dt, source FROM earnings_q WHERE ticker=? AND year=? AND reprt=?", (t, y, r)).fetchone()
        raw_rc = con.execute("SELECT rcept_no FROM earnings_raw WHERE ticker=? AND year=? AND reprt=?", (t, y, r)).fetchone()
        if raw_rc and raw_rc[0] == f["rcept_no"]:
            counts["done"] += 1; continue                 # 이 접수번호는 이미 처리함
        if f["amend"] and not exist:
            counts["amend_no_orig"] += 1; continue         # 원본을 모르는 정정본 — 접수일을 정할 수 없어 건너뜀(원본은 보통 이미 표에 있다)
        if dry:
            counts["dry"] += 1; continue
        raw = ensure_raw(con, api_key, f, y, r, fetch, counts, fetched_at, force=True)
        if raw is None:
            continue
        for dep_r, dy in DEPS[r]:                          # 전년 동기·누적 차분에 필요한 보고서(없을 때만 받는다)
            ensure_raw(con, api_key, f, y + dy, dep_r, fetch, counts, fetched_at)
        q_this, q_prev = EF.quarter_values(load_rep(con, t), t, y, r)
        if q_this is None:
            counts["no_values"] += 1; con.commit(); continue
        if exist:                                          # 접수일·시총은 원본 것을 유지(배지 시작일이 밀리지 않게 · 시총 고정)
            rcept_dt, mcap, shares, px_dt, source = exist[0], exist[1], exist[2], exist[3], (exist[4] or "")
            if not mcap:
                mcap, shares, px_dt = mcap_at(ocon, t, rcept_dt)
            source = source if source.startswith(SOURCE) else f"{SOURCE}|was:{source}"
        else:
            rcept_dt = f["rcept_dt"]
            mcap, shares, px_dt = mcap_at(ocon, t, rcept_dt)
            source = SOURCE
        if not mcap:
            counts["no_price"] += 1; con.commit(); continue
        sue = (q_this - q_prev) / mcap
        if abs(sue) > EF.SUE_CAP:
            counts["extreme"] += 1; con.commit(); continue
        con.execute("INSERT OR REPLACE INTO earnings_q(ticker, year, reprt, reprt_ord, rcept_dt, q_op, q_op_prev, mcap_prev, sue, source, shares_at, px_dt) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (t, y, r, EF._ORD[r], rcept_dt, q_this, q_prev, mcap, sue, source, shares, px_dt))
        counts["updated" if exist else "new"] += 1
        con.commit()
    return counts


def verify(con, ocon, api_key, n, fetch=fetch_json, year=2026, reprt="H1"):
    """이미 있는 연구 수집본 행 n개를 다시 받아 영업이익 값을 대조(저장 안 함). 시총은 주식수가 바뀐 종목에서만 달라야 한다."""
    rows = con.execute("SELECT ticker, q_op, q_op_prev, mcap_prev, rcept_dt FROM earnings_q WHERE year=? AND reprt=? AND source LIKE 'research%' ORDER BY RANDOM() LIMIT ?",
                       (year, reprt, n)).fetchall()
    ok = diff = nomatch = 0; calls = 0; mcap_diff = []
    for t, q_op, q_prev, mc, d8 in rows:
        # 접수일 당일 공시목록으로 corp_code·접수번호를 찾는다(회사 지정 없이 하루치 — 호출 1~2회)
        fl, c = fetch_filings(api_key, d8, d8, fetch); calls += c
        f = next((x for x in fl if x["ticker"] == t and x["year"] == year and x["reprt"] == reprt and not x["amend"]), None)
        if not f:
            nomatch += 1; print(f"  ? {t} {d8}: 그날 목록에서 원본 보고서를 못 찾음"); continue
        tmp = sqlite3.connect(":memory:"); tmp.executescript(RAW_SCHEMA)
        counts = dict(calls=0, no_values=0)
        raw = ensure_raw(tmp, api_key, f, year, reprt, fetch, counts, "verify", force=True)
        for dep_r, dy in DEPS[reprt]:
            ensure_raw(tmp, api_key, f, year + dy, dep_r, fetch, counts, "verify")
        calls += counts["calls"]
        a, b = EF.quarter_values(load_rep(tmp, t), t, year, reprt)
        mc2, sh2, px2 = mcap_at(ocon, t, d8)
        same = a is not None and b is not None and abs(a - q_op) < 1 and abs(b - q_prev) < 1
        ok += same; diff += (not same)
        if mc and mc2:
            mcap_diff.append(mc2 / mc - 1)
        print(f"  {'=' if same else '≠'} {t} {d8}: 영업이익 {q_op:,.0f}/{(a if a is not None else float('nan')):,.0f} · 전년 {q_prev:,.0f}/{(b if b is not None else float('nan')):,.0f}"
              f" · 시총 비 {((mc2 / mc) if (mc and mc2) else float('nan')):.3f}")
    print(f"• 대조 {len(rows)}건: 값 일치 {ok} · 불일치 {diff} · 목록에서 못 찾음 {nomatch} · DART 호출 {calls}")
    if mcap_diff:
        big = sum(1 for x in mcap_diff if abs(x) > 0.01)
        print(f"  시총: 1% 넘게 다른 종목 {big}/{len(mcap_diff)} (주식수가 바뀐 종목이면 정상 — 새 자료는 접수 시점 값을 고정 저장)")
    return ok, diff, nomatch


def status(con):
    r = con.execute("SELECT source, COUNT(*), MAX(rcept_dt) FROM earnings_q GROUP BY source").fetchall()
    print("• earnings_q:", ", ".join(f"{s or '-'} {n}건(~{d})" for s, n, d in r))
    print("• earnings_raw:", con.execute("SELECT COUNT(*) FROM earnings_raw").fetchone()[0], "행 · 마지막 조회일", meta_get(con, "last_end", "-"))


def main():
    ap = argparse.ArgumentParser(description="실적 악화 배지용 정기보고서 증분 수집")
    ap.add_argument("--start"); ap.add_argument("--end"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", type=int, default=0); ap.add_argument("--status", action="store_true"); ap.add_argument("--db", default=None)
    a = ap.parse_args()
    con = open_db(a.db or EF.EARN_DB)
    if a.status:
        status(con); return 0
    try:
        from run_and_diversify import load_dotenv
        load_dotenv()
    except Exception:
        pass
    api_key = os.environ.get("DART_API_KEY", "").strip()
    if not api_key:
        print("⚠ DART_API_KEY 없음 — 실적 증분 수집 생략(비치명)"); return 0
    ocon = sqlite3.connect(f"file:{EF.OHLCV_DB}?mode=ro", uri=True)
    try:
        if a.verify:
            verify(con, ocon, api_key, a.verify); return 0
        today = datetime.now().strftime("%Y%m%d")
        last_end = meta_get(con, "last_end")
        start = a.start or ((datetime.strptime(last_end, "%Y%m%d") - timedelta(days=OVERLAP_DAYS)).strftime("%Y%m%d") if last_end else DEFAULT_START)
        end = a.end or today
        counts = {}
        filings, calls = fetch_filings(api_key, start, end, counts=counts)
        t0 = time.time()
        c = process(con, ocon, filings, api_key, dry=a.dry_run)
        c["calls"] += calls
        print(f"• 실적 증분 {start}~{end}: 목록 {counts.get('list_rows', 0)}행 → 정기보고서(12월 결산) {c['filings']}건 · "
              f"신규 {c['new']} · 갱신(정정) {c['updated']} · 이미 처리 {c['done']} · 건너뜀(창 밖 {c['window']} · 원본 없는 정정 {c['amend_no_orig']} · "
              f"값 없음 {c['no_values']} · 시세 없음 {c['no_price']} · 극단값 {c['extreme']}) · DART 호출 {c['calls']} · {time.time() - t0:.0f}s"
              + (f" · dry-run(처리 예정 {c['dry']}건)" if a.dry_run else ""))
        if not a.dry_run and not counts.get("list_error"):
            meta_set(con, "last_end", end); con.commit()
        status(con)
    except RuntimeError as e:
        if "DART_DAILY_LIMIT" in str(e):
            print("⚠ DART 일일 한도(020) — 오늘은 여기까지, 다음 배치에서 이어서 받는다(마지막 조회일은 안 올림)"); return 0
        raise
    finally:
        ocon.close(); con.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:          # 비치명 — 배치는 계속, 로그에만
        print(f"⚠ 실적 증분 수집 실패(비치명): {type(e).__name__}: {str(e)[:160]}")
        sys.exit(0)
