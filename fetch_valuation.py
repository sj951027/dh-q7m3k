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

KRX 로그인:
    같은 폴더의 .env 파일에 아래 두 줄을 넣어두면 자동으로 읽어 로그인한다.
        KRX_ID=본인아이디
        KRX_PW=본인비밀번호
    (= 양옆 공백/따옴표 없이. 이미 들어있는 DART_API_KEY 등은 그대로 둬도 됨)

실행:
    python fetch_valuation.py                 # 가장 최근 영업일 기준
    python fetch_valuation.py --date 20260602 # 특정 날짜(run_id와 동일 형식)

날짜에 데이터가 없으면(주말/휴장/미게시) 가장 가까운 과거 영업일로 자동으로
물러나 받는다. 단, 저장 파일명은 요청한 날짜(run_id)로 유지한다.
"""
import argparse
import datetime as dt
import os
from pathlib import Path

import pandas as pd


# ----------------------------------------------------------------- .env 로딩
def load_env(env_path=None):
    """.env 파일을 읽어 환경변수로 올린다(이미 설정된 값은 덮어쓰지 않음)."""
    p = Path(env_path) if env_path else (Path(__file__).resolve().parent / ".env")
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, val)


# .env 를 pykrx import 보다 먼저 올려야 로그인에 반영된다
load_env()

try:
    from pykrx import stock
except ImportError:
    raise SystemExit("pykrx가 필요합니다.  pip install pykrx")


def _try_one(date_str, market):
    """해당 날짜·시장의 펀더멘털. 데이터 없으면 None."""
    try:
        df = stock.get_market_fundamental(date_str, market=market)
    except Exception:
        return None
    if df is None or len(df) == 0:
        return None
    return df


def fetch_one(req_date, market, lookback=10):
    """요청일부터 과거로 최대 lookback일 물러나며 데이터가 있는 영업일을 찾는다."""
    base = dt.datetime.strptime(req_date, "%Y%m%d")
    for i in range(lookback):
        ds = (base - dt.timedelta(days=i)).strftime("%Y%m%d")
        f = _try_one(ds, market)
        if f is not None:
            f = f.reset_index()
            # 첫 컬럼이 종목코드 (pykrx 버전 따라 '티커'/'index' 등)
            f = f.rename(columns={f.columns[0]: "ticker"})
            f["ticker"] = f["ticker"].astype(str).str.zfill(6)
            keep = [c for c in ["ticker", "PBR", "PER", "DIV", "BPS", "EPS"]
                    if c in f.columns]
            return f[keep], ds
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None,
                    help="YYYYMMDD (기본: 오늘). run_id와 같은 형식")
    args = ap.parse_args()
    req_date = args.date or dt.date.today().strftime("%Y%m%d")

    # 로그인 정보 안내(없어도 진행은 함)
    if not os.environ.get("KRX_ID") or not os.environ.get("KRX_PW"):
        print("[안내] .env 에 KRX_ID / KRX_PW 가 없습니다. "
              "로그인이 필요한 환경이면 데이터가 비어올 수 있습니다.")

    any_ok = False
    for mkt_key, mkt_api in [("kospi", "KOSPI"), ("kosdaq", "KOSDAQ")]:
        df, used = fetch_one(req_date, mkt_api)
        if df is None:
            print(f"[건너뜀] {mkt_api}: 최근 {req_date} 부근에 데이터 없음 "
                  f"(휴장/주말/미게시 또는 로그인 필요). value 없이 진행.")
            continue
        out = f"valuation_{mkt_key}_{req_date}.csv"   # 파일명은 run_id 기준 유지
        df.to_csv(out, index=False, encoding="utf-8-sig")
        med = pd.to_numeric(df["PBR"], errors="coerce").replace(0, pd.NA).median()
        note = "" if used == req_date else f"  (실데이터일: {used})"
        print(f"[OK] {out}  ({len(df)} 종목)  PBR 중앙값={med:.2f}{note}")
        any_ok = True

    if not any_ok:
        print("두 시장 모두 데이터를 받지 못했습니다. .env 의 KRX_ID/KRX_PW 를 "
              "확인하거나 날짜를 바꿔 다시 시도해 보세요.")


if __name__ == "__main__":
    main()