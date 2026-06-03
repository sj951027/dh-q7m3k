# -*- coding: utf-8 -*-
"""
fetch_valuation.py  (댁의 PC에서 실행 — 네트워크 + KRX 로그인 필요)
==================================================================
pykrx로 KOSPI/KOSDAQ 전종목의 PBR/PER/배당수익률을 받아
v3_rescore.py 가 자동으로 읽는 파일을 만든다:

    valuation_kospi_{run_id}.csv
    valuation_kosdaq_{run_id}.csv

컬럼: ticker, PBR, PER, DIV, BPS, EPS

설치(한 번만):
    pip install pykrx

KRX 로그인 (.env 에 두 줄):
    KRX_ID=본인아이디
    KRX_PW=본인비밀번호
  이 스크립트는 import 직후 pykrx 의 login_krx(id, pw) 를 '명시적으로' 호출해
  로그인한다. (환경변수 자동 로그인이 실패해도 강제로 재로그인)
  로그인이 안 되면 최근 날짜는 0으로 채워진 빈 표가 오는데, 그런 0짜리 데이터는
  '무효'로 보고 저장하지 않는다(점수 오염 방지).

실행:
    python fetch_valuation.py
    python fetch_valuation.py --date 20260603
"""
import argparse
import datetime as dt
import os
from pathlib import Path

import pandas as pd


# ----------------------------------------------------------------- .env 로딩
def load_env(env_path=None):
    """.env 를 읽어 환경변수로 올린다. (키는 덮어쓰기)"""
    p = Path(env_path) if env_path else (Path(__file__).resolve().parent / ".env")
    if not p.exists():
        print(f"[env] .env 파일을 찾지 못함: {p}")
        return
    n = 0
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            os.environ[key] = val
            n += 1
    print(f"[env] .env 에서 {n}개 키 로드")


load_env()

_KID = os.environ.get("KRX_ID", "").strip()
_KPW = os.environ.get("KRX_PW", "").strip()

try:
    from pykrx import stock
    import pykrx.website.comm as _comm
except ImportError:
    raise SystemExit("pykrx가 필요합니다.  pip install pykrx")


def krx_login():
    """pykrx login_krx(id, pw) 명시적 호출. 성공 시 True."""
    if not _KID or not _KPW:
        print("[로그인] ⚠️  .env 의 KRX_ID/KRX_PW 가 비어 있음 → 로그인 불가")
        return False
    try:
        ok = _comm.login_krx(_KID, _KPW)
        if ok:
            print(f"[로그인] ✅ KRX 로그인 성공 (ID: {_KID[:3]}***)")
        else:
            print(f"[로그인] ❌ KRX 로그인 실패 (ID/PW 확인: {_KID[:3]}***)")
        return bool(ok)
    except Exception as e:
        print(f"[로그인] ❌ 로그인 중 오류: {type(e).__name__}: {e}")
        return False


def _valid(df):
    """받은 펀더멘털이 '실데이터'인지. 전부 0/NaN 이면 무효."""
    if df is None or len(df) == 0 or "PBR" not in df.columns:
        return False
    pbr = pd.to_numeric(df["PBR"], errors="coerce").fillna(0)
    return (pbr > 0).sum() >= max(5, int(len(df) * 0.1))


def _try_one(date_str, market):
    try:
        df = stock.get_market_fundamental(date_str, market=market)
    except Exception:
        return None
    return df if _valid(df) else None


def fetch_one(req_date, market, lookback=10):
    base = dt.datetime.strptime(req_date, "%Y%m%d")
    for i in range(lookback):
        ds = (base - dt.timedelta(days=i)).strftime("%Y%m%d")
        f = _try_one(ds, market)
        if f is not None:
            f = f.reset_index()
            f = f.rename(columns={f.columns[0]: "ticker"})
            f["ticker"] = f["ticker"].astype(str).str.zfill(6)
            keep = [c for c in ["ticker", "PBR", "PER", "DIV", "BPS", "EPS"]
                    if c in f.columns]
            return f[keep], ds
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYYMMDD (기본: 오늘)")
    args = ap.parse_args()
    req_date = args.date or dt.date.today().strftime("%Y%m%d")

    krx_login()   # 명시적 로그인 (실패해도 아래 _valid 가 0짜리를 거름)

    any_ok = False
    for mkt_key, mkt_api in [("kospi", "KOSPI"), ("kosdaq", "KOSDAQ")]:
        df, used = fetch_one(req_date, mkt_api)
        if df is None:
            print(f"[건너뜀] {mkt_api}: {req_date} 부근에서 유효 데이터를 못 받음 "
                  f"(휴장/미게시 또는 로그인 실패). value 없이 진행.")
            continue
        out = f"valuation_{mkt_key}_{req_date}.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        med = pd.to_numeric(df["PBR"], errors="coerce").replace(0, pd.NA).median()
        note = "" if used == req_date else f"  (실데이터일: {used})"
        print(f"[OK] {out}  ({len(df)} 종목)  PBR 중앙값={med:.2f}{note}")
        any_ok = True

    if not any_ok:
        print("두 시장 모두 유효 데이터를 못 받았습니다. 위 [로그인] 줄을 확인하세요.")


if __name__ == "__main__":
    main()
