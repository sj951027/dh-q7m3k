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
LABEL = "영업이익↓"


def load(asof=None, lookback=LOOKBACK, db=EARN_DB, cal_db=OHLCV_DB):
    """→ {ticker(6자리): (라벨, rcept_dt)} — asof(YYYYMMDD) 기준 직전 lookback 거래일 안에 접수된 최신 보고서가 '악화'인 종목."""
    try:
        con = sqlite3.connect(f"file:{cal_db}?mode=ro", uri=True)
        dates = [d for (d,) in con.execute("SELECT DISTINCT date FROM market_daily WHERE series='KOSPI' ORDER BY date")]
        con.close()
        if asof:
            dates = [d for d in dates if d <= str(asof)]
        if not dates:
            return {}
        start, end = dates[max(0, len(dates) - lookback)], dates[-1]
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
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
_END = {"Q1": "0331", "H1": "0630", "Q3": "0930", "Y": "1231"}
_PREV = {"H1": "Q1", "Q3": "H1", "Y": "Q3"}


def quarter_values(rep, stock, year, reprt):
    """(이번 분기 3개월 영업이익, 전년 같은 분기) — 못 구하면 (None, None). rep[(stock, year, reprt)] = dict(th, th_add, fr, fr_q, fr_add)."""
    import math
    ok = lambda v: v is not None and not (isinstance(v, float) and math.isnan(v))
    x = rep.get((stock, year, reprt))
    if not x:
        return None, None
    if reprt == "Y":
        q3 = rep.get((stock, year, "Q3"))
        if not q3 or not all(ok(v) for v in (x["th"], q3["th_add"], x["fr"], q3["fr_add"])):
            return None, None
        return x["th"] - q3["th_add"], x["fr"] - q3["fr_add"]
    q_this, q_prev = x["th"], x["fr_q"]
    if not ok(q_prev):
        py = rep.get((stock, year - 1, reprt)); q_prev = py["th"] if py else None
    if not ok(q_prev):
        if reprt == "Q1":
            q_prev = x["fr_add"]
        else:
            pr = rep.get((stock, year, _PREV[reprt]))
            q_prev = (x["fr_add"] - pr["fr_add"]) if pr and ok(x["fr_add"]) and ok(pr["fr_add"]) else None
    return (q_this, q_prev) if ok(q_this) and ok(q_prev) else (None, None)


def rebuild_from_research(src=None, out=EARN_DB, ohlcv=OHLCV_DB):
    """연구 수집본(dart_hist.db 의 reports·filings)으로 earnings_q 를 새로 만든다. 운영 DB(ohlcv.db·history.db)는 읽기만."""
    import json, re
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
    for stock, year, reprt, fs, items in con.execute("SELECT stock_code, year, reprt, fs, items FROM reports WHERE status='000' AND kept>0 AND api='ALL'"):
        key = (stock, int(year), reprt)
        if key in rep and rep[key]["fs"] == "CFS":
            continue
        it = op_item(json.loads(items))
        if it is None:
            continue
        rep[key] = dict(fs=fs, th=num(it.get("thstrm_amount")), th_add=num(it.get("thstrm_add_amount")), fr=num(it.get("frmtrm_amount")),
                        fr_q=num(it.get("frmtrm_q_amount")), fr_add=num(it.get("frmtrm_add_amount")))
    # 정기보고서 원본 접수일: 제목의 (YYYY.MM) → (연도, 종류). 정정 아닌 것 중 가장 이른 날, 없으면 가장 이른 정정본.
    orig = {}
    kind_ok = {"A001": {"Y"}, "A002": {"H1"}, "A003": {"Q1", "Q3"}}
    for kind, stock, nm, dt_ in con.execute("SELECT kind, stock_code, report_nm, rcept_dt FROM filings WHERE kind IN ('A001','A002','A003') ORDER BY rcept_dt"):
        m = re.search(r"\((\d{4})\.(\d{2})\)", nm or "")
        if not m:
            continue
        reprt = {"03": "Q1", "06": "H1", "09": "Q3", "12": "Y"}.get(m.group(2))
        if reprt not in kind_ok[kind]:
            continue
        key = (stock, int(m.group(1)), reprt); amend = "정정" in (nm or "")
        if key not in orig or (orig[key][1] and not amend):
            orig[key] = (dt_, amend)
    con.close()
    oc = sqlite3.connect(f"file:{ohlcv}?mode=ro", uri=True)
    has_extra = oc.execute("SELECT 1 FROM sqlite_master WHERE name='daily_ohlcv_extra'").fetchone() is not None

    def mcap_before(ticker, d8):
        for tab in ("daily_ohlcv",) + (("daily_ohlcv_extra",) if has_extra else ()):
            r = oc.execute(f"SELECT close, shares FROM {tab} WHERE ticker=? AND date<? AND close>0 AND shares>0 ORDER BY date DESC LIMIT 1", (ticker, d8)).fetchone()
            if r:
                return float(r[0]) * float(r[1])
        return None

    rows = []; skipped = dict(no_date=0, no_values=0, window=0, no_mcap=0)
    for (stock, year, reprt) in rep:
        if (stock, year, reprt) not in orig:
            skipped["no_date"] += 1; continue
        q_this, q_prev = quarter_values(rep, stock, year, reprt)
        if q_this is None:
            skipped["no_values"] += 1; continue
        d8 = orig[(stock, year, reprt)][0]; end = f"{year}{_END[reprt]}"
        if not (end < d8 <= (datetime.strptime(end, "%Y%m%d") + timedelta(days=130)).strftime("%Y%m%d")):
            skipped["window"] += 1; continue
        mc = mcap_before(stock, d8)
        if not mc:
            skipped["no_mcap"] += 1; continue
        rows.append((stock, year, reprt, _ORD[reprt], d8, q_this, q_prev, mc, (q_this - q_prev) / mc, "research_backfill"))
    oc.close()
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
