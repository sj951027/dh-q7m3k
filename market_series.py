# -*- coding: utf-8 -*-
"""
market_series.py — 시장 레벨 시계열(지수·환율) 수집 → ohlcv.db `market_daily` (P2)
==============================================================================
왜: §17 결론(절대수익 병목=시장 베타/노출)을 다루려면 시장 레벨 데이터가 필요한데,
ohlcv.db 엔 개별종목뿐 시장 시계열이 없었다(§26-5 P2). 지수·환율 일별 종가를 쌓아
노출/레짐 분석의 기반을 만든다. 점수·표시 미연결(순수 축적).

시리즈(FDR 코드): KS11(KOSPI) · KQ11(KOSDAQ) · USD/KRW(환율).
  - 최초 실행: 2023-06-01 부터 백필(개별종목 ohlcv 백필 기점과 정렬).
  - 이후: DB에 없는 날짜만 증분(idempotent). 실패해도 비치명(exit 0).

사용:
    python market_series.py           # 증분(최초엔 자동 백필)
파이프라인: run_all_and_diversify.bat 에서 universe_ohlcv 다음에 호출.
⚠️ 네트워크(FDR) 사용 — 오프라인 환경에선 자동 생략.
"""
import os
import sys
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
OHLCV_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))
BACKFILL_START = "2023-06-01"

SERIES = {  # 이름: FDR 코드
    "KOSPI": "KS11",
    "KOSDAQ": "KQ11",
    "USDKRW": "USD/KRW",
}

DDL = """CREATE TABLE IF NOT EXISTS market_daily (
    series TEXT NOT NULL,
    date   TEXT NOT NULL,
    close  REAL,
    PRIMARY KEY (series, date)
)"""


KRX_INDEX = {"KOSPI": "1001", "KOSDAQ": "2001"}   # pykrx 지수 코드


def _load_dotenv():
    """[2026-09-20] .env 를 os.environ 에 로드(이미 있으면 안 덮음 · 값은 출력하지 않음).
    9/18 실측: FDR 지수가 9/17에서 멈춰 pykrx 예비가 처음 발동했는데, 이 스크립트만 .env 를 안 읽어
    KRX_ID/KRX_PW 가 비어 'KRX 로그인 실패(환경 변수 미설정)'로 떨어졌다. notify_telegram._load_dotenv 와 같은 동작."""
    p = HERE / ".env"
    if not p.exists():
        return
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def repair(start):
    """[2026-09-20] 지수 정정: start(YYYYMMDD)부터 시세 마지막 날까지 KOSPI/KOSDAQ 를 pykrx(KRX) 값으로 덮어쓴다(REPLACE).
    용도: FDR 지수 소스가 장중에 멈춰 확정 전 값이 저장된 날 정정. 사용: python market_series.py --repair-from 20260917"""
    _load_dotenv()
    con = sqlite3.connect(OHLCV_DB)
    px_last = con.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()[0]
    from pykrx import stock as _krx
    for name, kcode in KRX_INDEX.items():
        kdf = _krx.get_index_ohlcv_by_date(start, px_last, kcode)
        if kdf is None or kdf.empty:
            print(f"  ⚠️ {name}: pykrx 데이터 없음 — 정정 안 함"); continue
        ccol = "종가" if "종가" in kdf.columns else kdf.columns[3]
        for idx, v in kdf[ccol].dropna().items():
            d = idx.strftime("%Y%m%d")
            old = con.execute("SELECT close FROM market_daily WHERE series=? AND date=?", (name, d)).fetchone()
            con.execute("INSERT OR REPLACE INTO market_daily VALUES (?,?,?)", (name, d, float(v)))
            print(f"  ✓ {name} {d}: {old[0] if old else '없음'} → {float(v)}")
    con.commit(); con.close()


def main():
    _load_dotenv()
    if not os.path.exists(OHLCV_DB):
        print(f"⚠️ ohlcv.db 없음({OHLCV_DB}) — 생략(비치명).")
        return
    try:
        import FinanceDataReader as fdr
    except ImportError:
        print("⚠️ FinanceDataReader 없음 — 생략(비치명). pip install finance-datareader")
        return
    con = sqlite3.connect(OHLCV_DB)
    con.execute(DDL)
    total = 0
    for name, code in SERIES.items():
        last = con.execute(
            "SELECT MAX(date) FROM market_daily WHERE series=?", (name,)).fetchone()[0]
        start = BACKFILL_START if last is None else \
            f"{last[:4]}-{last[4:6]}-{last[6:]}"  # 마지막 날짜부터(중복은 IGNORE)
        try:
            df = fdr.DataReader(code, start)
        except Exception as e:
            print(f"  ⚠️ {name}({code}) 조회 실패 건너뜀: {e}")
            continue
        if df is None or df.empty or "Close" not in df.columns:
            print(f"  ⚠️ {name}({code}) 데이터 없음/형식 상이 — 건너뜀")
            continue
        rows = [(name, idx.strftime("%Y%m%d"), float(v))
                for idx, v in df["Close"].dropna().items()]
        cur = con.executemany(
            "INSERT OR IGNORE INTO market_daily VALUES (?,?,?)", rows)
        con.commit()
        total += cur.rowcount
        print(f"  ✓ {name}: 신규 {cur.rowcount}행 (마지막 {rows[-1][1] if rows else '-'})")
    # [2026-09-09] 예비 소스 — FDR 지수(KS11/KQ11)가 시세(daily_ohlcv)보다 뒤처지면 pykrx(KRX 지수 1001/2001)로 보충.
    #   9/08~09 실측: FDR 상장목록 404 와 함께 지수도 9/07에서 멈춤(시세·환율은 정상). 판정엔 안 쓰이지만
    #   리더보드 '돈' 표의 코스피 참고선이 ffill 로 조용히 낡는 것을 막는다. 둘 다 실패하면 경고만.
    try:
        px_last = con.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()[0]
    except Exception:
        px_last = None
    for name, kcode in KRX_INDEX.items():
        last = con.execute("SELECT MAX(date) FROM market_daily WHERE series=?", (name,)).fetchone()[0]
        if not px_last or not last or last >= px_last:
            continue
        try:
            from pykrx import stock as _krx
            from datetime import datetime as _dt, timedelta as _td
            s = (_dt.strptime(last, "%Y%m%d") + _td(days=1)).strftime("%Y%m%d")
            kdf = _krx.get_index_ohlcv_by_date(s, px_last, kcode)
            if kdf is None or kdf.empty:
                print(f"  ⚠️ {name} 예비(pykrx {kcode}): 데이터 없음 — 지수 {last}에서 정지 중(시세 {px_last})")
                continue
            ccol = "종가" if "종가" in kdf.columns else kdf.columns[3]
            rows = [(name, idx.strftime("%Y%m%d"), float(v)) for idx, v in kdf[ccol].dropna().items()]
            cur = con.executemany("INSERT OR IGNORE INTO market_daily VALUES (?,?,?)", rows)
            con.commit(); total += cur.rowcount
            print(f"  ✓ {name}: [예비 pykrx] 신규 {cur.rowcount}행 (마지막 {rows[-1][1] if rows else '-'})")
        except Exception as e:
            print(f"  ⚠️ {name} 예비(pykrx) 실패: {str(e)[:80]} — 지수 {last}에서 정지 중(시세 {px_last})")
    n = con.execute("SELECT series, COUNT(*), MAX(date) FROM market_daily GROUP BY series").fetchall()
    con.close()
    print(f"완료: 신규 {total}행. 누적: " + " · ".join(f"{s} {c}행(~{d})" for s, c, d in n))


if __name__ == "__main__":
    try:
        if len(sys.argv) >= 3 and sys.argv[1] == "--repair-from":
            repair(sys.argv[2])
        else:
            main()
    except Exception as e:
        print(f"❌ 실패(비치명 — 파이프라인 계속): {e}")
        sys.exit(0)
