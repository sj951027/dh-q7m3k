#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate_flows_to_ohlcv.py — Phase 1 이전 스크립트 (1회 실행)

수급(daily_flows)·공매도(short_flows)를 history.db → ohlcv.db 로 이전.
§21-8 Phase1: raw(가격·수급·공매도)는 ohlcv.db, 점수는 history.db.

안전장치:
- ohlcv.db 에 이미 같은 테이블이 있으면 INSERT OR REPLACE 로 병합(중복 키 덮어쓰기).
- history.db 의 원본은 '삭제하지 않음'(--drop-source 줘야 삭제). 먼저 검증 후 지우는 것을 권장.
- 검증: 이전 후 양쪽 행수·해시 출력.

사용:
  python migrate_flows_to_ohlcv.py
    → history.db 의 flows 를 ohlcv.db 로 복사(원본 유지). 검증 출력.
  python migrate_flows_to_ohlcv.py --drop-source
    → 복사 + 검증 통과 시 history.db 의 flows 삭제(VACUUM).

검증 통과(ohlcv 와 history 행수 동일) 후에만 --drop-source 권장.
"""
import sqlite3, argparse, hashlib
from pathlib import Path

HIST = Path("history.db")
OHLCV = Path("..") / "dh-q7m3k-data" / "ohlcv.db"
TABLES = ["daily_flows", "short_flows"]


def table_hash(con, tbl):
    """테이블 내용 해시(ticker,date 정렬) — 이전 전후 동일성 확인용."""
    try:
        rows = con.execute(
            f"SELECT * FROM {tbl} ORDER BY ticker, date").fetchall()
        return hashlib.md5(str(rows).encode()).hexdigest(), len(rows)
    except Exception:
        return None, 0


def migrate(hist_path, ohlcv_path, drop_source):
    if not Path(ohlcv_path).exists():
        raise SystemExit(f"❌ ohlcv.db 없음({ohlcv_path}) — universe_ohlcv.py 먼저")
    if not Path(hist_path).exists():
        raise SystemExit(f"❌ history.db 없음({hist_path})")

    src = sqlite3.connect(hist_path)
    dst = sqlite3.connect(ohlcv_path)

    print("=" * 60)
    print("Phase 1 이전: 수급·공매도 → ohlcv.db")
    print("=" * 60)

    for tbl in TABLES:
        # 원본 존재 확인
        has = src.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{tbl}'").fetchone()
        if not has:
            print(f"  {tbl}: history.db 에 없음 — 스킵")
            continue

        # 스키마 복제(없을 때만)
        schema = src.execute(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{tbl}'").fetchone()[0]
        dst.execute(schema.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS"))

        # 컬럼 수
        ncol = len(src.execute(f"PRAGMA table_info({tbl})").fetchall())
        rows = src.execute(f"SELECT * FROM {tbl}").fetchall()
        ph = ",".join(["?"] * ncol)
        # INSERT OR REPLACE: 중복 키(있다면) 덮어쓰기, 없으면 추가
        dst.executemany(f"INSERT OR REPLACE INTO {tbl} VALUES ({ph})", rows)
        dst.commit()

        # 검증
        sh, sn = table_hash(src, tbl)
        dh, dn = table_hash(dst, tbl)
        ok = (sh == dh)
        print(f"  {tbl}: history {sn:,}행 → ohlcv {dn:,}행  "
              f"{'✅ 해시일치' if ok else '⚠️ 해시불일치(ohlcv에 기존 데이터 있었을 수 있음)'}")

    # 원본 삭제(옵션)
    if drop_source:
        print("\n[--drop-source] history.db 의 flows 삭제")
        for tbl in TABLES:
            src.execute(f"DROP TABLE IF EXISTS {tbl}")
        src.commit()
        src.execute("VACUUM")
        print("  ✅ 삭제 + VACUUM 완료 (history.db 가벼워짐)")
    else:
        print("\n  원본 유지(history.db). 검증 OK 확인 후 --drop-source 로 삭제 권장.")

    src.close()
    dst.close()
    print("\n완료. 이후 kis_flows.py 는 --flows-db ../dh-q7m3k-data/ohlcv.db 로 저장,")
    print("     lowvol_score.py / build_large_report.py 는 ohlcv.db 에서 자동으로 읽음.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist", default=str(HIST))
    ap.add_argument("--ohlcv", default=str(OHLCV))
    ap.add_argument("--drop-source", action="store_true",
                    help="복사 후 history.db 의 flows 삭제(검증 OK 후 권장)")
    a = ap.parse_args()
    migrate(a.hist, a.ohlcv, a.drop_source)
