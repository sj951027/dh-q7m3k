#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
earnings_flag.py — 실적 악화 60거래일 배지 (표시 전용 · 점수·순위·유니버스 무반영)
====================================================================================
[2026-10-04 신설] 근거(research/RESEARCH_target20_wide_20261004.md §E4d·§6-3):
  최근 분기 영업이익이 전년 같은 분기보다 '시총의 1% 이상' 줄어든 종목은 그 뒤 20거래일에 같은 날·같은 시장·
  같은 시총 구간 대비 −1.0%p [−1.5, −0.5](세 연도 모두 음), 실제 모델 목록 상위 10 안에서도 −3.2%p [−4.7, −1.1]
  (2026-06~09, 넉 달 — 단서). 자동 제외가 아니라 배지만 달아 사람이 판단한다(희석 배지와 같은 원칙).

  정의(유일한 상수 2개): 감소분 ÷ 시총 ≤ −1% (DROP) · 보고서 접수일부터 60거래일 (LOOKBACK).
    분기 3개월 영업이익 = 분기·반기 보고서의 당기 3개월 값, 사업보고서는 연간 − 3분기 누적.
    시총 = 접수일 직전 거래일 종가 × 상장주식수. 접수일 = 정기보고서 원본(정정 아님) 접수일.
    같은 종목은 60거래일 안의 '가장 최근 보고서' 하나만 본다(그 보고서가 악화가 아니면 배지 없음).
  [2026.10.16 보강 — 독립 검토 반영] 12월 결산 회사만(보고서 제목의 결산월로 확인) · 접수일은 보고서 접수번호로 직접 찾음 ·
    전년 동기는 '올해 보고서 안의 값'을 먼저 쓰고 연결/별도 기준이 같을 때만 비교 · 감소분÷시총 크기가 0.5 를 넘거나
    접수 전 10일 안 시세가 없으면 제외 · 접수 뒤 주식수가 1.5배 넘게 바뀐 종목(병합·분할)은 두 기준 중 큰 시총으로(배지가 덜 붙는 쪽).
  데이터: ../dh-q7m3k-data/earnings.db 의 earnings_q 표(이 파일의 --rebuild-from-research 가 만든다).
    지금은 연구용 수집본(research/dart_history/dart_hist.db, 2026 반기보고서까지)에서 한 번 옮긴 것 —
    3분기 보고서(11/14 마감)부터는 배치에 증분 수집을 붙여야 한다(미구현, patch_note 참조).
  실패 시 빈 플래그(컬럼은 빈 문자열) — 비치명. 거래일 달력 = ohlcv.db market_daily KOSPI(희석 배지와 같음).
"""
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
OHLCV_DB = os.environ.get("OHLCV_DB", os.path.join(HERE, "..", "dh-q7m3k-data", "ohlcv.db"))
EARN_DB = os.environ.get("EARNINGS_DB", os.path.join(HERE, "..", "dh-q7m3k-data", "earnings.db"))
LOOKBACK = 60          # 거래일
DROP = -0.01           # (이번 분기 영업이익 − 전년 같은 분기) ÷ 시총
COL = "earn_drop_60d"
STALE_DAYS = 45        # 자료의 마지막 접수일이 이만큼(거래일) 지나면 로그에 경고
SUE_CAP = 0.5          # |감소분÷시총| 이 이보다 크면 단위 오류·정리매매 시총으로 보고 제외
PRICE_MAX_AGE = 10     # 접수 전 이 날수(달력일) 안의 시세가 있어야 시총을 쓴다
SHARES_JUMP = 1.5      # 접수 뒤 주식수가 이 배수 넘게 바뀌면 병합·분할로 본다
LABEL = "영업이익↓"


def load(asof=None, lookback=LOOKBACK, db=EARN_DB, cal_db=OHLCV_DB):
    """→ {ticker(6자리): (라벨, rcept_dt)} — asof(YYYYMMDD) 기준 직전 lookback 거래일 안에 접수된 최신 보고서가 '악화'인 종목."""
    try:
        con = sqlite3.connect(f"file:{cal_db}?mode=ro", uri=True)
        dates = [d for (d,) in con.execute("SELECT DISTINCT date FROM market_daily WHERE series='KOSPI' ORDER BY date")]
        con.close()
        if asof:
            asof = "".join(ch for ch in str(asof) if ch.isdigit())[:8]      # '2026-10-02' 같은 형식도 받는다
            dates = [d for d in dates if d <= asof]
        if not dates:
            return {}
        start, end = dates[max(0, len(dates) - lookback)], dates[-1]
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        mx = con.execute("SELECT MAX(rcept_dt) FROM earnings_q").fetchone()[0]
        if mx and str(mx) < start:
            print(f"   ⚠️ earnings_flag: 실적 자료가 {mx} 접수분까지뿐 — 60거래일 창 밖이라 배지가 전부 비었음(자료 갱신 필요)")
        elif mx and sum(1 for d in dates if d > str(mx)) > STALE_DAYS:
            print(f"   ⚠️ earnings_flag: 실적 자료 기준일 {mx} — 그 뒤 접수된 분기 보고서는 배지에 반영 안 됨(자료 갱신 필요)")
        rows = con.execute("SELECT ticker, rcept_dt, sue FROM earnings_q WHERE rcept_dt>=? AND rcept_dt<=? AND sue IS NOT NULL "
                           "ORDER BY rcept_dt, year, reprt_ord", (start, end)).fetchall()
        con.close()
        latest = {}
        for t, d, sue in rows:                      # 접수일 순 → 마지막 것이 최신 보고서
            latest[str(t).zfill(6)] = (str(d), sue)
        return {t: (LABEL, d) for t, (d, sue) in latest.items() if sue <= DROP}
    except Exception as e:
        print(f"   ⚠️ earnings_flag: 로드 실패(비치명, 플래그 없음): {e}")
        return {}


def attach(df, asof=None, ticker_col="ticker", col=COL):
    """df 에 col 추가: '영업이익↓ 08/14' 또는 ''. 반환 (df, 걸린 종목 수)."""
    flags = load(asof)
    vals, n = [], 0
    for x in df[ticker_col]:
        t = str(x).zfill(6)
        if t in flags:
            lab, d = flags[t]; vals.append(f"{lab} {d[4:6]}/{d[6:]}"); n += 1
        else:
            vals.append("")
    df = df.copy(); df[col] = vals
    return df, n


# ---------------------------------------------------------------- 데이터 만들기(연구 수집본 → earnings.db)
_ORD = {"Q1": 1, "H1": 2, "Q3": 3, "Y": 4}
_PREV = {"H1": "Q1", "Q3": "H1", "Y": "Q3"}


def quarter_values(rep, stock, year, reprt):
    """(이번 분기 3개월 영업이익, 전년 같은 분기) — 못 구하면 (None, None).
    rep[(stock, year, reprt)] = dict(th, th_add, fr, fr_q, fr_add[, fs]). 다른 보고서와 섞을 때는 연결/별도(fs)가 같아야 한다.
    전년 동기 순서: 저장된 3개월 값 → 올해 보고서들의 전년 누적 차분 → 전년 같은 보고서의 당기 3개월."""
    import math
    ok = lambda v: v is not None and not (isinstance(v, float) and math.isnan(v))
    x = rep.get((stock, year, reprt))
    if not x:
        return None, None
    same = lambda y: bool(y) and y.get("fs") == x.get("fs")
    if reprt == "Y":
        q3 = rep.get((stock, year, "Q3"))
        if not same(q3) or not all(ok(v) for v in (x["th"], q3["th_add"], x["fr"], q3["fr_add"])):
            return None, None
        return x["th"] - q3["th_add"], x["fr"] - q3["fr_add"]
    pr = rep.get((stock, year, _PREV[reprt])) if reprt != "Q1" else None
    q_this = x["th"]
    if reprt != "Q1" and ok(x["th"]) and ok(x.get("th_add")) and x["th"] == x["th_add"] and same(pr) and ok(pr.get("th_add")):
        q_this = x["th_add"] - pr["th_add"]            # 3개월 칸에 누적을 적은 보고서 → 누적 차분
    q_prev = x["fr_q"]
    if not ok(q_prev):
        if reprt == "Q1":
            q_prev = x["fr_add"]
        elif same(pr) and ok(x["fr_add"]) and ok(pr["fr_add"]):
            q_prev = x["fr_add"] - pr["fr_add"]
    if not ok(q_prev):
        py = rep.get((stock, year - 1, reprt)); q_prev = py["th"] if same(py) else None
    return (q_this, q_prev) if ok(q_this) and ok(q_prev) else (None, None)


def rebuild_from_research(src=None, out=EARN_DB, ohlcv=OHLCV_DB):
    """연구 수집본(dart_hist.db 의 reports·filings)으로 earnings_q 를 새로 만든다. 운영 DB(ohlcv.db·history.db)는 읽기만."""
    import calendar, json, re
    from datetime import datetime, timedelta
    src = src or os.path.join(HERE, "research", "dart_history", "dart_hist.db")

    def num(v):
        try:
            return float(str(v).replace(",", "")) if v not in (None, "", "-") else None
        except ValueError:
            return None

    def op_item(items):
        for it in items:
            if it.get("account_id") == "dart_OperatingIncomeLoss" and it.get("sj_div") in ("IS", "CIS"):
                return it
        for it in items:
            if it.get("sj_div") in ("IS", "CIS") and (it.get("account_nm") or "").replace(" ", "") in ("영업이익", "영업이익(손실)", "영업손익", "영업손실"):
                return it
        return None

    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True); rep = {}
    for stock, year, reprt, fs, rc, items in con.execute("SELECT stock_code, year, reprt, fs, rcept_no, items FROM reports WHERE status='000' AND kept>0 AND api='ALL'"):
        key = (stock, int(year), reprt)
        if key in rep and rep[key]["fs"] == "CFS":
            continue
        it = op_item(json.loads(items))
        if it is None:
            continue
        rep[key] = dict(fs=fs, rcept_no=rc or "", th=num(it.get("thstrm_amount")), th_add=num(it.get("thstrm_add_amount")), fr=num(it.get("frmtrm_amount")),
                        fr_q=num(it.get("frmtrm_q_amount")), fr_add=num(it.get("frmtrm_add_amount")))
    # 공시 목록: 접수번호 → (종류, 종목, 제목의 결산 연월). 같은 (종목, 종류, 연월) 가운데 정정 아닌 가장 이른 날 = 원본 접수일.
    by_no, orig = {}, {}
    for rc, kind, stock, nm, dt_ in con.execute("SELECT rcept_no, kind, stock_code, report_nm, rcept_dt FROM filings WHERE kind IN ('A001','A002','A003') ORDER BY rcept_dt"):
        m = re.search(r"\((\d{4})\.(\d{2})\)", nm or "")
        if not m:
            continue
        ym = m.group(1) + m.group(2); by_no[rc] = (kind, stock, ym)
        key = (stock, kind, ym); amend = "정정" in (nm or "")
        if key not in orig or (orig[key][1] and not amend):
            orig[key] = (dt_, amend)
    con.close()
    oc = sqlite3.connect(f"file:{ohlcv}?mode=ro", uri=True)
    has_extra = oc.execute("SELECT 1 FROM sqlite_master WHERE name='daily_ohlcv_extra'").fetchone() is not None
    tabs = ("daily_ohlcv",) + (("daily_ohlcv_extra",) if has_extra else ())

    def mcap_before(ticker, d8):
        """접수 전 PRICE_MAX_AGE 일 안의 마지막 시세로 시총. 접수 뒤 주식수가 크게 바뀌었으면(병합·분할) 두 기준 중 큰 값."""
        lo = (datetime.strptime(d8, "%Y%m%d") - timedelta(days=PRICE_MAX_AGE)).strftime("%Y%m%d")
        for tab in tabs:
            r = oc.execute(f"SELECT close, shares FROM {tab} WHERE ticker=? AND date<? AND date>=? AND close>0 AND shares>0 ORDER BY date DESC LIMIT 1", (ticker, d8, lo)).fetchone()
            if r:
                close, sh = float(r[0]), float(r[1])
                last = oc.execute(f"SELECT shares FROM {tab} WHERE ticker=? AND shares>0 ORDER BY date DESC LIMIT 1", (ticker,)).fetchone()
                sh_now = float(last[0]) if last else sh
                jump = sh_now / sh > SHARES_JUMP or sh / sh_now > SHARES_JUMP
                return close * (max(sh, sh_now) if jump else sh), jump
        return None, False

    want_mm = {"Q1": "03", "H1": "06", "Q3": "09", "Y": "12"}; kind_of = {"Y": "A001", "H1": "A002", "Q1": "A003", "Q3": "A003"}
    rows = []; skipped = dict(no_date=0, non_dec=0, no_values=0, window=0, no_price=0, extreme=0); jumps = 0
    for (stock, year, reprt), x in rep.items():
        f = by_no.get(x["rcept_no"])
        if not f or f[1] != stock or f[0] != kind_of[reprt]:
            skipped["no_date"] += 1; continue
        ym = f[2]
        if ym[4:] != want_mm[reprt] or int(ym[:4]) != year:
            skipped["non_dec"] += 1; continue          # 12월 결산이 아니거나 결산월이 바뀐 회사 — 분기 맞추기가 어긋나므로 제외
        q_this, q_prev = quarter_values(rep, stock, year, reprt)
        if q_this is None:
            skipped["no_values"] += 1; continue
        d8 = orig[(stock, f[0], ym)][0]
        end = f"{ym}{calendar.monthrange(int(ym[:4]), int(ym[4:]))[1]:02d}"
        if not (end < d8 <= (datetime.strptime(end, "%Y%m%d") + timedelta(days=130)).strftime("%Y%m%d")):
            skipped["window"] += 1; continue
        mc, jump = mcap_before(stock, d8)
        if not mc:
            skipped["no_price"] += 1; continue
        sue = (q_this - q_prev) / mc
        if abs(sue) > SUE_CAP:
            skipped["extreme"] += 1; continue
        jumps += jump
        rows.append((stock, year, reprt, _ORD[reprt], d8, q_this, q_prev, mc, sue, "research_backfill" + ("|shares_jump" if jump else "")))
    oc.close()
    skipped["shares_jump_kept"] = jumps
    tmp = out + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    w = sqlite3.connect(tmp)
    w.execute("""CREATE TABLE earnings_q(ticker TEXT, year INTEGER, reprt TEXT, reprt_ord INTEGER, rcept_dt TEXT,
                 q_op REAL, q_op_prev REAL, mcap_prev REAL, sue REAL, source TEXT, PRIMARY KEY(ticker, year, reprt))""")
    w.execute("CREATE INDEX ix_earn_dt ON earnings_q(rcept_dt)")
    w.executemany("INSERT OR REPLACE INTO earnings_q VALUES(?,?,?,?,?,?,?,?,?,?)", rows); w.commit(); w.close()
    os.replace(tmp, out)
    return len(rows), skipped


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--rebuild-from-research":
        n, sk = rebuild_from_research()
        print(f"earnings_q {n}행 저장 → {os.path.abspath(EARN_DB)} · 건너뜀 {sk}")
        sys.exit(0)
    f = load(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"실적 악화 60거래일 플래그 {len(f)}종목")
    for t, (lab, d) in sorted(f.items(), key=lambda kv: kv[1][1], reverse=True)[:10]:
        print(f"  {t} {lab} {d}")
