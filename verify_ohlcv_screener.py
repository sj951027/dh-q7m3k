#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_ohlcv_screener.py — Phase 2 사전 검증 (전환 전 0-diff 확인)

스크리너의 analyze_ticker 를 두 경로로 돌려 결과를 비교:
  (A) 원본: fdr.DataReader (네트워크)
  (B) ohlcv.db 에서 읽어 fdr 형식으로 변환

같은 종목에 대해 과매도 점수(oversold_score)와 핵심 지표가 byte 수준으로
같은지 확인. 같으면 → Phase 2 전환 안전. 다르면 → 원인(수정주가/최신일/반올림) 추적.

Claude 는 fdr 호출 불가 → 이 스크립트는 '사용자 PC'에서 실행해 0-diff 를 실측 보증.

사용:
  python verify_ohlcv_screener.py                 # 상위 30종목 비교
  python verify_ohlcv_screener.py --n 100         # 100종목
  python verify_ohlcv_screener.py --market KOSDAQ # 시장 지정
  python verify_ohlcv_screener.py --show-diff     # 불일치 상세 출력
"""
import sqlite3, argparse, sys
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# 스크리너 모듈 import (같은 폴더)
import screener_fdr_v2_6 as scr
import FinanceDataReader as fdr

OHLCV_DB = "../dh-q7m3k-data/ohlcv.db"


def load_from_ohlcv(ticker, from_date, to_date, con):
    """ohlcv.db 에서 읽어 fdr.DataReader 와 동일한 형식(DataFrame)으로 변환.
    fdr: 인덱스=날짜(Timestamp), 컬럼=Open/High/Low/Close/Volume (대문자).
    ohlcv: date(YYYYMMDD str), open/low/high/close/volume (소문자)."""
    fd = from_date.replace("-", "")
    td = to_date.replace("-", "")
    df = pd.read_sql(
        "SELECT date, open, high, low, close, volume FROM daily_ohlcv "
        "WHERE ticker=? AND date>=? AND date<=? AND is_suspended=0 ORDER BY date",
        con, params=(ticker, fd, td))
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df = df.set_index("date")
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                            "close": "Close", "volume": "Volume"})
    return df[["Open", "High", "Low", "Close", "Volume"]]


def analyze_from_df(df, ticker, name_map, sector_map):
    """analyze_ticker 의 df 받은 이후 로직을 그대로 재현(가격 소스만 df 로 주입).
    원본 analyze_ticker 는 내부에서 fdr 를 부르므로, 같은 계산을 여기서 수행."""
    if df is None or len(df) < 50:
        return None
    if df["Close"].iloc[-1] < 1000:
        return None
    if df["Volume"].tail(5).sum() == 0:
        return None
    df = df.copy()
    df["RSI"] = scr.calculate_rsi(df["Close"])
    df["BB_U"], df["BB_M"], df["BB_L"] = scr.calculate_bollinger_bands(df["Close"])
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["Vol_MA20"] = df["Volume"].rolling(20).mean()
    df["Stoch"] = scr.calculate_stochastic(df)
    latest = df.iloc[-1]
    price = latest["Close"]
    recent = df.tail(252) if len(df) >= 252 else df
    high_52w = recent["High"].max()
    low_52w = recent["Low"].min()

    def pct_change(n):
        if len(df) < n + 1:
            return np.nan
        return (price / df["Close"].iloc[-(n + 1)] - 1) * 100

    bb_range = latest["BB_U"] - latest["BB_L"]
    bb_pos = ((price - latest["BB_L"]) / bb_range * 100) if bb_range > 0 else 50
    accum = scr.calculate_accumulation_score(df)
    vol_metrics = scr.calculate_volume_metrics(df)
    trend = scr.calculate_trend_reversal(df)
    return {
        "ticker": ticker, "price": int(price),
        "RSI": round(latest["RSI"], 1) if pd.notna(latest["RSI"]) else None,
        "Stoch_K": round(latest["Stoch"], 1) if pd.notna(latest["Stoch"]) else None,
        "BB_pct": round(bb_pos, 1),
        "drawdown_52w_high_%": round((price - high_52w) / high_52w * 100, 1),
        "return_1w_%": round(pct_change(5), 1),
        "return_1m_%": round(pct_change(21), 1),
        "volume_vs_avg": round(latest["Volume"] / latest["Vol_MA20"], 2) if latest["Vol_MA20"] > 0 else None,
        **accum, **vol_metrics, **trend,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="비교할 종목 수")
    ap.add_argument("--market", default="KRX", help="fdr StockListing 시장")
    ap.add_argument("--ohlcv", default=OHLCV_DB)
    ap.add_argument("--show-diff", action="store_true")
    a = ap.parse_args()

    today = datetime.now()
    from_date = (today - timedelta(days=scr.LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")

    # 종목 목록 (ohlcv 에 있는 것 중 시총 상위 N)
    con = sqlite3.connect(a.ohlcv)
    latest = con.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()[0]
    tickers = [r[0] for r in con.execute(
        "SELECT ticker FROM daily_ohlcv WHERE date=? AND is_suspended=0 AND close IS NOT NULL "
        "ORDER BY close*COALESCE(shares,0) DESC LIMIT ?", (latest, a.n)).fetchall()]

    print("=" * 66)
    print(f"Phase 2 검증: fdr vs ohlcv (analyze_ticker 0-diff)")
    print(f"  종목 {len(tickers)}개 · 기간 {from_date}~{to_date} · ohlcv 최신 {latest}")
    print("=" * 66)

    # 비교할 핵심 키 (과매도 점수의 입력)
    keys = ["price", "RSI", "Stoch_K", "BB_pct", "drawdown_52w_high_%",
            "return_1w_%", "return_1m_%", "volume_vs_avg",
            "acc_score", "trend_score", "oversold_score"]

    n_match = n_diff = n_skip = 0
    diffs = []
    for tk in tickers:
        # (A) fdr 경로 — 원본 analyze_ticker
        try:
            ra = scr.analyze_ticker(tk, {}, None, from_date, to_date)
        except Exception:
            ra = None
        # (B) ohlcv 경로
        df_o = load_from_ohlcv(tk, from_date, to_date, con)
        rb = analyze_from_df(df_o, tk, {}, None)

        if ra is None or rb is None:
            n_skip += 1
            continue
        # 과매도 점수 부여(둘 다)
        ra["oversold_score"] = scr.calculate_oversold_score(ra)
        rb["oversold_score"] = scr.calculate_oversold_score(rb)

        # 키별 비교
        mism = []
        for k in keys:
            va, vb = ra.get(k), rb.get(k)
            if pd.isna(va) and pd.isna(vb):
                continue
            if va != vb:
                mism.append((k, va, vb))
        if mism:
            n_diff += 1
            diffs.append((tk, mism))
        else:
            n_match += 1

    con.close()
    print(f"\n결과: ✅일치 {n_match} · ⚠️불일치 {n_diff} · 건너뜀(데이터부족) {n_skip}")
    if n_diff == 0 and n_match > 0:
        print("\n🎉 0-DIFF 통과 — ohlcv 가격으로 계산해도 과매도 점수 동일.")
        print("   Phase 2 전환 안전. (단 매일 universe_ohlcv 가 스크리너보다 먼저 돌아야 — 최신일 정합)")
    elif n_diff > 0:
        print(f"\n⚠️  불일치 {n_diff}종목 — 전환 보류. 원인 분석 필요.")
        show = diffs if a.show_diff else diffs[:5]
        for tk, mism in show:
            print(f"\n  [{tk}]")
            for k, va, vb in mism:
                print(f"    {k}: fdr={va} vs ohlcv={vb}")
        if not a.show_diff and len(diffs) > 5:
            print(f"\n  ... 외 {len(diffs)-5}종목 (--show-diff 로 전체)")


if __name__ == "__main__":
    main()
