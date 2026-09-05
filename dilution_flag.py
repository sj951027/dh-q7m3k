#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dilution_flag.py — 희석 공시 60거래일 플래그 (표시 전용 · 점수·순위·유니버스 무반영)
====================================================================================
[2026-09-05 신설] 3년·PIT 이벤트 스터디(research/RESEARCH_fullscan_20260903.md §3):
  유상증자·CB·BW·EB(·유무상혼합) '결정' 공시 뒤 60거래일은 같은 유니버스 대비 −1.4~−6.6%p/60일(전부 CI<0).
  걸리는 비율 3~9%. 자동 컷(lv_e_x 등)은 판정 시즌 뒤 사전등록으로만 — 지금은 배지만 달아 사람이 판단.

  데이터: ohlcv.db dart_events(dart_events.py 가 매일 적재) · 거래일 달력 = market_daily KOSPI.
  정정(report_nm '정정' 포함)은 제외. 같은 종목 여러 건이면 최신 건 표시.
  실패 시 빈 플래그(컬럼은 빈 문자열) — 비치명.
"""
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
OHLCV_DB = os.environ.get("OHLCV_DB", os.path.join(HERE, "..", "dh-q7m3k-data", "ohlcv.db"))
LOOKBACK = 60          # 거래일. 근거: 결정 공시 → 신주 상장 1~2개월(§3) — 유일한 상수
TYPES = {"paid_in": "유상증자", "cb": "CB", "bw": "BW", "eb": "EB", "paid_bonus_mix": "유무상혼합"}
COL = "dilution_60d"


def load(asof=None, lookback=LOOKBACK, db=OHLCV_DB):
    """→ {ticker(6자리): (라벨, rcept_dt)} — asof(YYYYMMDD) 기준 직전 lookback 거래일 내 최신 건."""
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        dates = [d for (d,) in con.execute(
            "SELECT DISTINCT date FROM market_daily WHERE series='KOSPI' ORDER BY date")]
        if asof:
            dates = [d for d in dates if d <= str(asof)]
        if not dates:
            con.close(); return {}
        start, end = dates[max(0, len(dates) - lookback)], dates[-1]
        q = ("SELECT ticker, event_type, rcept_dt FROM dart_events WHERE rcept_dt>=? AND rcept_dt<=? "
             "AND event_type IN (%s) AND (report_nm IS NULL OR report_nm NOT LIKE '%%정정%%') "
             "ORDER BY rcept_dt" % ",".join("?" * len(TYPES)))
        out = {}
        for t, e, d in con.execute(q, (start, end, *TYPES.keys())):
            out[str(t).zfill(6)] = (TYPES.get(e, e), str(d))
        con.close()
        return out
    except Exception as e:
        print(f"   ⚠️ dilution_flag: 로드 실패(비치명, 플래그 없음): {e}")
        return {}


def attach(df, asof=None, ticker_col="ticker", col=COL):
    """df 에 col 추가: '유상증자 08/21' 또는 ''. 반환 (df, 걸린 종목 수)."""
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


if __name__ == "__main__":
    import sys
    f = load(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"희석 60거래일 플래그 {len(f)}종목")
    for t, (lab, d) in sorted(f.items(), key=lambda kv: kv[1][1], reverse=True)[:10]:
        print(f"  {t} {lab} {d}")
