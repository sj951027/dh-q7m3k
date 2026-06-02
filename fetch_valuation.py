# -*- coding: utf-8 -*-
"""
fetch_valuation.py  (댁의 PC에서 실행 — 네트워크 필요)
=====================================================
pykrx로 KOSPI/KOSDAQ 전종목의 PBR/PER/배당수익률을 받아
v3_rescore.py 가 자동으로 읽는 파일을 만든다:

    valuation_kospi_{run_id}.csv
    valuation_kosdaq_{run_id}.csv

컬럼: ticker, PBR, PER, DIV, BPS, EPS

설치(한 번만):
    pip install pykrx

실행:
    python fetch_valuation.py                # 가장 최근 영업일 기준
    python fetch_valuation.py --date 20260601 # 특정 날짜(run_id와 동일 형식)

이 파일을 만든 뒤 v3_rescore.py / v3_backtest.py 를 다시 돌리면
value_source 가 'PYKRX' 로 바뀌고 value_score(업종 내 PBR/PER percentile)가 켜진다.
"""
import argparse
import datetime as dt
import pandas as pd

try:
    from pykrx import stock
except ImportError:
    raise SystemExit("pykrx가 필요합니다.  pip install pykrx")


def fetch_one(date_str, market):
    """market: 'KOSPI' or 'KOSDAQ'. ticker 인덱스 + BPS/PER/PBR/EPS/DIV/DPS."""
    f = stock.get_market_fundamental(date_str, market=market)
    f = f.reset_index().rename(columns={"티커": "ticker", "index": "ticker"})
    # pykrx 버전에 따라 인덱스명이 다를 수 있어 방어적으로 처리
    if "ticker" not in f.columns:
        f = f.rename(columns={f.columns[0]: "ticker"})
    f["ticker"] = f["ticker"].astype(str).str.zfill(6)
    keep = ["ticker", "PBR", "PER", "DIV", "BPS", "EPS"]
    keep = [c for c in keep if c in f.columns]
    return f[keep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None,
                    help="YYYYMMDD (기본: 오늘). run_id와 같은 형식")
    args = ap.parse_args()
    date_str = args.date or dt.date.today().strftime("%Y%m%d")

    for mkt_key, mkt_api in [("kospi", "KOSPI"), ("kosdaq", "KOSDAQ")]:
        df = fetch_one(date_str, mkt_api)
        out = f"valuation_{mkt_key}_{date_str}.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[OK] {out}  ({len(df)} 종목)  "
              f"PBR 중앙값={df['PBR'].replace(0, pd.NA).median():.2f}")


if __name__ == "__main__":
    main()
