# -*- coding: utf-8 -*-
"""실적 악화 배지용 정기보고서 증분 수집(2026-10-07) — 가짜 DART 응답·임시 DB 만, 네트워크·운영 DB 미접촉.

계약:
  A. 공시목록 거르기: 상장사(Y/K)·종목코드 6자리·'사업/반기/분기보고서 (YYYY.MM)' 만. 12월 결산이 아니면 제외. 정정 표시 구분.
  B. 재무 응답 → 영업이익 행(연결 우선, 없으면 별도). 분기값은 earnings_flag.quarter_values 그대로(3분기 = 3개월 값 · 전년 동기).
  C. 시총 = 접수일 직전 거래일 종가 × 그날 주식수(본 표 → 보충표). 접수 전 10일 안 시세가 없으면 None.
  D. 저장: 새 보고서는 신규(source=incr, 주식수·시세 날짜 저장) · 같은 접수번호는 다시 처리 안 함 ·
     정정본은 값만 갱신하고 접수일·시총은 원본 것 유지(연구 수집본 행도) · 원본 없는 정정본은 건너뜀 ·
     결산 종료 뒤 130일 밖 접수는 제외 · 극단값(|차÷시총|>0.5) 제외 · 전년 동기가 없으면 전년 보고서를 받아서 채움.
  E. dry-run 은 재무 호출·저장 없음. DART 일일 한도(020)는 RuntimeError 로 올려 호출부가 멈춘다.
  F. 배선: 배치에 extra_ohlcv 다음·run_and_diversify 앞. 기존 earnings_q 열 유지 + 열 2개 추가.
실행: python tests/test_earnings_incr.py
"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO)); os.chdir(REPO)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
P = 0


def check(name, cond, info=""):
    global P
    if not cond:
        print(f"  FAIL  {name}  {info}"); sys.exit(1)
    P += 1; print(f"  ok    {name}")


import earnings_incr as X  # noqa: E402

print("[A] 공시목록 거르기")
row = lambda **k: dict({"corp_cls": "Y", "stock_code": "005930", "corp_code": "00126380", "report_nm": "분기보고서 (2026.09)", "rcept_no": "20261114000001", "rcept_dt": "20261114"}, **k)
f = X.parse_filing(row())
check("3분기 분기보고서 → Q3 2026 · 정정 아님", f and (f["reprt"], f["year"], f["ym"], f["amend"]) == ("Q3", 2026, "202609", False), str(f))
check("반기(06)→H1 · 1분기(03)→Q1 · 사업(12)→Y", [X.parse_filing(row(report_nm=n))["reprt"] for n in ("반기보고서 (2026.06)", "분기보고서 (2026.03)", "사업보고서 (2025.12)")] == ["H1", "Q1", "Y"])
check("정정 표시", X.parse_filing(row(report_nm="[기재정정]분기보고서 (2026.09)"))["amend"] is True)
check("12월 결산 아님(사업보고서 2026.06 · 분기 2026.12) → 제외", X.parse_filing(row(report_nm="사업보고서 (2026.06)")) is None and X.parse_filing(row(report_nm="분기보고서 (2026.12)")) is None)
check("비상장(E)·종목코드 없음·다른 공시 → 제외", X.parse_filing(row(corp_cls="E")) is None and X.parse_filing(row(stock_code="")) is None and X.parse_filing(row(report_nm="주요사항보고서(유상증자결정)")) is None)
check("접수 창: 9월 결산 종료 뒤 130일 안만", X.in_filing_window("202609", "20261114") and not X.in_filing_window("202609", "20260930") and not X.in_filing_window("202609", "20270301"))

print("[B] 재무 응답 → 원자료")
items = [{"account_id": "ifrs-full_Revenue", "sj_div": "IS", "account_nm": "매출액", "thstrm_amount": "9"},
         {"account_id": "dart_OperatingIncomeLoss", "sj_div": "IS", "account_nm": "영업이익", "thstrm_amount": "1,200", "thstrm_add_amount": "3,000",
          "frmtrm_amount": "9,999", "frmtrm_q_amount": "1,000", "frmtrm_add_amount": "2,500"}]
raw = X.raw_from_items(items, "CFS", "r1")
check("영업이익 행에서 당기 3개월·누적·전년 3개월·전년 누적", (raw["th"], raw["th_add"], raw["fr_q"], raw["fr_add"], raw["fs"]) == (1200.0, 3000.0, 1000.0, 2500.0, "CFS"))
check("영업이익 행이 없으면 None", X.raw_from_items([items[0]], "CFS", "r1") is None)

# ---- 가짜 DART ----
FIN = {}      # (corp, year, reprt_code, fs) → items 또는 None(013)
LIST = {}     # (bgn, end, cls) → rows
CALLS = []
LIMIT = {"on": False}


def fake(url, params, api_key):
    CALLS.append((url.rsplit("/", 1)[-1], dict(params)))
    if LIMIT["on"]:
        return {"status": "020", "message": "limit"}
    if url == X.LIST_URL:
        rows = LIST.get((params["bgn_de"], params["end_de"], params["corp_cls"]), [])
        return {"status": "000", "list": rows, "total_page": 1} if rows else {"status": "013", "message": "no data"}
    it = FIN.get((params["corp_code"], params["bsns_year"], params["reprt_code"], params["fs_div"]))
    return {"status": "000", "list": it} if it else {"status": "013", "message": "no data"}


def op(th, th_add=None, fr_q=None, fr_add=None, fr=None):
    return [{"account_id": "dart_OperatingIncomeLoss", "sj_div": "IS", "account_nm": "영업이익", "thstrm_amount": str(th),
             "thstrm_add_amount": "" if th_add is None else str(th_add), "frmtrm_q_amount": "" if fr_q is None else str(fr_q),
             "frmtrm_add_amount": "" if fr_add is None else str(fr_add), "frmtrm_amount": "" if fr is None else str(fr)}]


td = tempfile.mkdtemp()
odb = os.path.join(td, "ohlcv.db"); edb = os.path.join(td, "earn.db")
oc = sqlite3.connect(odb)
oc.executescript("CREATE TABLE daily_ohlcv(ticker TEXT, date TEXT, close INTEGER, shares INTEGER); CREATE TABLE daily_ohlcv_extra(ticker TEXT, date TEXT, close INTEGER, shares INTEGER);")
oc.executemany("INSERT INTO daily_ohlcv VALUES(?,?,?,?)", [("005930", "20261112", 100, 1000), ("005930", "20261113", 110, 1000), ("005930", "20261117", 200, 2000),
                                                           ("000660", "20261001", 50, 100)])
oc.executemany("INSERT INTO daily_ohlcv_extra VALUES(?,?,?,?)", [("196170", "20261113", 10, 500)])
oc.commit()

print("[C] 시총")
check("접수 직전 거래일(11/13) 종가 110 × 주식수 1000 — 접수 뒤 주식수 변화는 무시(고정)", X.mcap_at(oc, "005930", "20261114") == (110000.0, 1000.0, "20261113"))
check("본 표에 없으면 보충표", X.mcap_at(oc, "196170", "20261114") == (5000.0, 500.0, "20261113"))
check("접수 전 10일 안 시세 없음 → None", X.mcap_at(oc, "000660", "20261114") == (None, None, None))

print("[D] 처리·저장")
con = X.open_db(edb)
cols = {r[1] for r in con.execute("PRAGMA table_info(earnings_q)")}
check("earnings_q 에 기존 10열 + shares_at·px_dt", {"ticker", "year", "reprt", "reprt_ord", "rcept_dt", "q_op", "q_op_prev", "mcap_prev", "sue", "source", "shares_at", "px_dt"} <= cols)
# 연구 수집본 행(2026 H1) 하나 미리
con.execute("INSERT INTO earnings_q(ticker,year,reprt,reprt_ord,rcept_dt,q_op,q_op_prev,mcap_prev,sue,source) VALUES('005930',2026,'H1',2,'20260814',500,400,90000,0.00111,'research_backfill')")
con.commit()
# 3분기 보고서(원본): 당기 3개월 1200 · 전년 3개월 1000 → 차 +200 ÷ 시총 110000
FIN[("00126380", "2026", "11014", "CFS")] = op(1200, 3000, fr_q=1000, fr_add=2500)
now = datetime(2026, 11, 14, 20, 15)
f_q3 = X.parse_filing(row())
c = X.process(con, oc, [f_q3], "k", fetch=fake, now=now)
r = con.execute("SELECT rcept_dt, q_op, q_op_prev, mcap_prev, shares_at, px_dt, source, sue FROM earnings_q WHERE ticker='005930' AND year=2026 AND reprt='Q3'").fetchone()
check("신규 저장: 접수일·3개월 값·전년 동기·시총 고정(110000, 주식수 1000, 11/13)·source incr", r is not None and r[:7] == ("20261114", 1200.0, 1000.0, 110000.0, 1000.0, "20261113", "incr") and abs(r[7] - 200 / 110000) < 1e-9, str(r))
check("호출: 3분기 CFS 1회 + 전년 동기 의존 보고서(H1 2026 · Q3 2025) 시도 — 재무 API 만", c["new"] == 1 and c["calls"] >= 1 and all(u == "fnlttSinglAcntAll.json" for u, _ in CALLS), str(c))
n_calls = len(CALLS)
c = X.process(con, oc, [f_q3], "k", fetch=fake, now=now)
check("같은 접수번호는 다시 처리하지 않는다(호출 0)", c["done"] == 1 and len(CALLS) == n_calls)
# 정정본: 값 1300 으로 → 값 갱신, 접수일·시총 유지
FIN[("00126380", "2026", "11014", "CFS")] = op(1300, 3100, fr_q=1000, fr_add=2500)
f_am = X.parse_filing(row(report_nm="[기재정정]분기보고서 (2026.09)", rcept_no="20261120000009", rcept_dt="20261120"))
c = X.process(con, oc, [f_am], "k", fetch=fake, now=now)
r = con.execute("SELECT rcept_dt, q_op, mcap_prev, shares_at, source FROM earnings_q WHERE ticker='005930' AND year=2026 AND reprt='Q3'").fetchone()
check("정정본: 값만 1300 으로 갱신 · 접수일 11/14 · 시총 110000 그대로", c["updated"] == 1 and r == ("20261114", 1300.0, 110000.0, 1000.0, "incr"), str(r))
# 연구 수집본 행의 정정본: 접수일·시총 유지, source 표시
FIN[("00126380", "2026", "11012", "CFS")] = op(600, 1100, fr_q=400, fr_add=900)
f_h1 = X.parse_filing(row(report_nm="[기재정정]반기보고서 (2026.06)", rcept_no="20261001000005", rcept_dt="20261001"))
c = X.process(con, oc, [f_h1], "k", fetch=fake, now=now)
r = con.execute("SELECT rcept_dt, q_op, q_op_prev, mcap_prev, source FROM earnings_q WHERE ticker='005930' AND year=2026 AND reprt='H1'").fetchone()
check("연구 수집본 행의 정정본: 값 갱신 · 접수일 8/14 · 시총 90000 유지 · 출처 표시", r == ("20260814", 600.0, 400.0, 90000.0, "incr|was:research_backfill"), str(r))
# 원본 없는 정정본 → 건너뜀
f_x = X.parse_filing(row(stock_code="000660", corp_code="00164779", report_nm="[기재정정]분기보고서 (2026.03)", rcept_no="20260701000007", rcept_dt="20260701"))
c = X.process(con, oc, [f_x], "k", fetch=fake, now=now)
check("원본을 모르는 정정본은 건너뜀(호출 없음)", c["amend_no_orig"] == 1 and c["calls"] == 0)
# 창 밖 · 시세 없음 · 극단값
f_old = X.parse_filing(row(report_nm="분기보고서 (2025.09)", rcept_no="20261114000002", rcept_dt="20261114"))
c = X.process(con, oc, [f_old], "k", fetch=fake, now=now)
check("결산 뒤 130일 넘은 접수는 제외", c["window"] == 1)
FIN[("00164779", "2026", "11014", "CFS")] = op(1, fr_q=0)
f_np = X.parse_filing(row(stock_code="000660", corp_code="00164779", rcept_no="20261114000003"))
c = X.process(con, oc, [f_np], "k", fetch=fake, now=now)
check("접수 전 시세가 없으면 저장 안 함", c["no_price"] == 1 and con.execute("SELECT COUNT(*) FROM earnings_q WHERE ticker='000660'").fetchone()[0] == 0)
oc.execute("INSERT INTO daily_ohlcv VALUES('000660','20261113',1,1)"); oc.commit()      # 시총 1
FIN[("00164779", "2026", "11014", "CFS")] = op(5, fr_q=0)                                 # 차 5 ÷ 시총 1 = 5 > 0.5
c = X.process(con, oc, [X.parse_filing(row(stock_code="000660", corp_code="00164779", rcept_no="20261114000004"))], "k", fetch=fake, now=now)
check("극단값(|차÷시총| > 0.5) 제외", c["extreme"] == 1)
# 전년 동기가 보고서 안에 없으면 전년 보고서를 받아서 채운다
FIN[("00000001", "2026", "11014", "CFS")] = None
FIN[("00000001", "2026", "11014", "OFS")] = op(300, 700)                                   # 별도 기준 · 전년 3개월 칸 비어 있음
FIN[("00000001", "2025", "11014", "OFS")] = op(250, 600)                                   # 전년 Q3 당기 3개월 = 250
oc.execute("INSERT INTO daily_ohlcv VALUES('196170','20261113',100,100)"); oc.commit()
c = X.process(con, oc, [X.parse_filing(row(stock_code="196170", corp_code="00000001", rcept_no="20261114000005"))], "k", fetch=fake, now=now)
r = con.execute("SELECT q_op, q_op_prev FROM earnings_q WHERE ticker='196170' AND year=2026 AND reprt='Q3'").fetchone()
check("연결 없음 → 별도 · 전년 동기는 전년 보고서(같은 기준)에서 250", c["new"] == 1 and r == (300.0, 250.0), str((c, r)))
check("원자료 표에 보고서·의존 보고서가 남는다", con.execute("SELECT COUNT(*) FROM earnings_raw WHERE ticker='196170'").fetchone()[0] == 2)

print("[E] dry-run · 한도")
CALLS.clear()
c = X.process(con, oc, [X.parse_filing(row(stock_code="000990", corp_code="00000002", rcept_no="20261114000006"))], "k", fetch=fake, dry=True, now=now)
check("dry-run: 재무 호출·저장 없음", c["dry"] == 1 and not CALLS and con.execute("SELECT COUNT(*) FROM earnings_q WHERE ticker='000990'").fetchone()[0] == 0)
LIMIT["on"] = True
try:
    X.process(con, oc, [X.parse_filing(row(stock_code="000990", corp_code="00000002", rcept_no="20261114000006"))], "k", fetch=fake, now=now)
    hit = False
except RuntimeError as e:
    hit = "DART_DAILY_LIMIT" in str(e)
check("일일 한도(020) → RuntimeError 로 호출부가 멈춘다", hit)
LIMIT["on"] = False
LIST[("20261114", "20261114", "Y")] = [row(), row(report_nm="주요사항보고서"), row(corp_cls="Y", report_nm="사업보고서 (2026.06)")]
fl, calls = X.fetch_filings("k", "20261114", "20261114", fetch=fake)
check("공시목록: Y·K 두 번 조회 · 대상만 남김(1건)", calls == 2 and len(fl) == 1 and fl[0]["reprt"] == "Q3")
check("메타: 마지막 조회일 저장·읽기", (X.meta_set(con, "last_end", "20261114"), X.meta_get(con, "last_end"))[1] == "20261114")
con.commit(); con.close(); oc.close()

print("[F] 배선")
bat = open(REPO / "run_all_and_diversify.bat", encoding="utf-8", errors="replace").read()
check("배치: extra_ohlcv 다음 · run_and_diversify 앞", bat.index("python extra_ohlcv.py") < bat.index("python earnings_incr.py") < bat.index("python run_and_diversify.py"))
src = open(REPO / "earnings_incr.py", encoding="utf-8").read()
check("실패는 비치명(종료코드 0) · 분당 상한 공유 · 분기값은 earnings_flag 그대로", "sys.exit(0)" in src and "_drate.wait()" in src and "EF.quarter_values(" in src)
print(f"\n{P}개 통과")
