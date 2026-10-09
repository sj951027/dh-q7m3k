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
print("[G] 2026-10-09 보강 — 실패 건 재시도 · 완료 표지 · 예산 · 접수번호 · 읽기 전용 상태")
td2 = tempfile.mkdtemp(); odb2 = os.path.join(td2, "ohlcv.db"); edb2 = os.path.join(td2, "earn.db")
oc2 = sqlite3.connect(odb2)
oc2.executescript("CREATE TABLE daily_ohlcv(ticker TEXT, date TEXT, close INTEGER, shares INTEGER); CREATE TABLE daily_ohlcv_extra(ticker TEXT, date TEXT, close INTEGER, shares INTEGER);")
oc2.commit()
c2 = X.open_db(edb2)
FIN.clear(); CALLS.clear(); LIMIT["on"] = False
npend = lambda: c2.execute("SELECT COUNT(*) FROM earnings_pending").fetchone()[0]
nq = lambda t: c2.execute("SELECT COUNT(*) FROM earnings_q WHERE ticker=?", (t,)).fetchone()[0]
# G1 시세 없음 → 나중에 시세가 생기면 다음 실행이 다시 넣는다(목록에 없어도)
FIN[("C1", "2026", "11014", "CFS")] = op(1200, 3000, fr_q=1000, fr_add=2500)
f1 = X.parse_filing(row(stock_code="111111", corp_code="C1", rcept_no="20261114100001"))
c = X.process(c2, oc2, [f1], "k", fetch=fake, now=now)
check("시세 없음: 저장 안 함 · 재시도 큐에 남음 · 원자료 상태 no_price", c["no_price"] == 1 and nq("111111") == 0 and npend() == 1
      and c2.execute("SELECT state FROM earnings_raw WHERE ticker='111111'").fetchone()[0] == "no_price")
check("전년 3개월 값이 보고서 안에 있으면 의존 보고서를 받지 않는다(호출 1회)", c["calls"] == 1, str(c["calls"]))
oc2.execute("INSERT INTO daily_ohlcv VALUES('111111','20261113',100,1000)"); oc2.commit()
CALLS.clear()
c = X.process(c2, oc2, [], "k", fetch=fake, now=now)          # 목록이 비어도 큐에서 다시 본다
check("시세가 생긴 뒤 다음 실행: 큐에서 꺼내 저장 · 재무는 다시 안 받음 · 큐 비움", c["retry"] == 1 and c["new"] == 1 and nq("111111") == 1 and npend() == 0 and not CALLS, str(c))
c = X.process(c2, oc2, [f1], "k", fetch=fake, now=now)
check("저장까지 끝난 접수번호만 '이미 처리'", c["done"] == 1 and c["calls"] == 0)
# G2 사업보고서: 3분기 원자료가 없어 값 못 구함 → 나중에 생기면 회복
FIN[("C2", "2025", "11011", "CFS")] = op(5000, fr=4000)
fy = X.parse_filing(row(stock_code="222222", corp_code="C2", report_nm="사업보고서 (2025.12)", rcept_no="20260310100001", rcept_dt="20260310"))
oc2.execute("INSERT INTO daily_ohlcv VALUES('222222','20260309',100,100000)"); oc2.commit()
c = X.process(c2, oc2, [fy], "k", fetch=fake, now=datetime(2026, 3, 10, 20, 15))
check("사업보고서: 3분기 누적이 없으면 값 없음(0 으로 채우지 않음) · 큐에 남음", c["no_values"] == 1 and nq("222222") == 0 and npend() == 1, str(c))
FIN[("C2", "2025", "11014", "CFS")] = op(1500, 3500, fr_q=1100, fr_add=3000)
c = X.process(c2, oc2, [], "k", fetch=fake, now=datetime(2026, 3, 11, 20, 15))
r2 = c2.execute("SELECT q_op, q_op_prev, rcept_dt FROM earnings_q WHERE ticker='222222'").fetchone()
check("3분기 원자료가 생기면 4분기 = 연간 − 3분기 누적(5000−3500, 전년 4000−3000) · 접수일은 원래 날", c["new"] == 1 and r2 == (1500.0, 1000.0, "20260310") and npend() == 0, str(r2))
# G3 예산: 호출 상한을 넘으면 남은 보고서는 큐로 미루고 다음 실행이 이어받는다
fs3 = []
for i, (t, cc) in enumerate((("333331", "D1"), ("333332", "D2"), ("333333", "D3"))):
    FIN[(cc, "2026", "11014", "CFS")] = op(100 + i, 300, fr_q=90, fr_add=250)
    oc2.execute("INSERT INTO daily_ohlcv VALUES(?,?,?,?)", (t, "20261113", 100, 1000))
    fs3.append(X.parse_filing(row(stock_code=t, corp_code=cc, rcept_no=f"2026111420000{i}")))
oc2.commit()
c = X.process(c2, oc2, fs3, "k", fetch=fake, now=now, max_calls=1)
check("호출 상한 1: 1건만 처리 · 2건은 미룸(큐, 횟수 0)", c["new"] == 1 and c["deferred"] == 2 and npend() == 2
      and c2.execute("SELECT MAX(tries) FROM earnings_pending").fetchone()[0] == 0, str(c))
c = X.process(c2, oc2, [], "k", fetch=fake, now=now)
check("다음 실행이 미룬 2건을 이어서 처리", c["retry"] == 2 and c["new"] == 2 and npend() == 0)
c = X.process(c2, oc2, fs3, "k", fetch=fake, now=now, max_seconds=0)
check("시간 상한을 넘겨도 이미 끝난 것은 '이미 처리'로만 센다(큐에 다시 안 넣음)", c["done"] == 3 and c["deferred"] == 0 and npend() == 0)
# G4 재무 응답의 실제 접수번호: 원본을 처리하는 사이 정정본 값이 왔으면 그 번호로 적고, 정정본이 목록에 떠도 다시 받지 않는다
it = op(700, 900, fr_q=600, fr_add=800); it[0]["rcept_no"] = "20261120300009"
FIN[("E1", "2026", "11014", "CFS")] = it
oc2.execute("INSERT INTO daily_ohlcv VALUES('444444','20261113',100,1000)"); oc2.commit()
f4 = X.parse_filing(row(stock_code="444444", corp_code="E1", rcept_no="20261114300001"))
c = X.process(c2, oc2, [f4], "k", fetch=fake, now=now)
check("원자료에 응답의 접수번호를 적는다", c["new"] == 1 and c2.execute("SELECT rcept_no FROM earnings_raw WHERE ticker='444444'").fetchone()[0] == "20261120300009")
CALLS.clear()
f4a = X.parse_filing(row(stock_code="444444", corp_code="E1", report_nm="[기재정정]분기보고서 (2026.09)", rcept_no="20261120300009", rcept_dt="20261120"))
c = X.process(c2, oc2, [f4, f4a], "k", fetch=fake, now=now)
check("원본·정정본 모두 '이미 처리'(재호출 없음)", c["done"] == 2 and not CALLS)
# G5 큐 기한
c2.execute("INSERT INTO earnings_pending VALUES('20260101999999', ?, 'no_price', '20260101_2015', 3, '20260102_2015')", (__import__("json").dumps(f1),)); c2.commit()
lst, dropped = X.load_pending(c2, now)
check(f"큐에 {X.PENDING_MAX_DAYS}일 넘게 있던 것은 버린다", dropped == 1 and npend() == 0)
# G6 시총: 두 표에 다 있으면 더 최근 날짜
oc2.execute("INSERT INTO daily_ohlcv VALUES('555555','20261110',100,10)"); oc2.execute("INSERT INTO daily_ohlcv_extra VALUES('555555','20261113',200,10)"); oc2.commit()
check("본 표(11/10)보다 보충표(11/13)가 최근이면 보충표 값", X.mcap_at(oc2, "555555", "20261114") == (2000.0, 10.0, "20261113"))
c2.close(); oc2.close()
# G7 옛 구조에서 올리기: state 열이 없던 표 → 이미 배지 자료에 들어간 것만 ok
edb3 = os.path.join(td2, "old.db"); w3 = sqlite3.connect(edb3)
w3.executescript("""CREATE TABLE earnings_raw(ticker TEXT, year INTEGER, reprt TEXT, fs TEXT, rcept_no TEXT, th REAL, th_add REAL, fr REAL, fr_q REAL, fr_add REAL, fetched_at TEXT, PRIMARY KEY(ticker, year, reprt));
CREATE TABLE earnings_q(ticker TEXT, year INTEGER, reprt TEXT, reprt_ord INTEGER, rcept_dt TEXT, q_op REAL, q_op_prev REAL, mcap_prev REAL, sue REAL, source TEXT, PRIMARY KEY(ticker, year, reprt));
INSERT INTO earnings_raw VALUES('000001',2026,'H1','CFS','r1',1,1,1,1,1,'x');
INSERT INTO earnings_raw VALUES('000002',2026,'H1','CFS','r2',1,1,1,1,1,'x');
INSERT INTO earnings_q VALUES('000001',2026,'H1',2,'20260814',1,1,1,0.0,'incr|was:research_backfill');""")
w3.commit(); w3.close()
c3 = X.open_db(edb3)
check("옛 표에 state 열 추가 · 저장까지 된 것만 ok(나머지는 다시 볼 수 있게 빈 값)",
      dict(c3.execute("SELECT ticker, state FROM earnings_raw").fetchall()) == {"000001": "ok", "000002": None})
c3.close()
# G8 상태 확인은 읽기 전용(표가 없어도 죽지 않고, 파일을 바꾸지 않는다)
edb4 = os.path.join(td2, "ro.db"); w4 = sqlite3.connect(edb4)
w4.execute("CREATE TABLE earnings_q(ticker TEXT, year INTEGER, reprt TEXT, reprt_ord INTEGER, rcept_dt TEXT, q_op REAL, q_op_prev REAL, mcap_prev REAL, sue REAL, source TEXT)"); w4.commit(); w4.close()
import io as _io, contextlib as _ctx   # noqa: E402
_argv = sys.argv; sys.argv = ["earnings_incr.py", "--status", "--db", edb4]
with _ctx.redirect_stdout(_io.StringIO()) as _buf:
    rc = X.main()
sys.argv = _argv
r4 = sqlite3.connect(edb4); tabs = [x[0] for x in r4.execute("SELECT name FROM sqlite_master WHERE type='table'")]; r4.close()
check("--status: 종료코드 0 · 표를 새로 만들지 않는다", rc == 0 and tabs == ["earnings_q"] and "earnings_q" in _buf.getvalue(), str(tabs))

print(f"\n{P}개 통과")
