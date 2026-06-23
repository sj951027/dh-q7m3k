#!/usr/bin/env python3
"""
[V2.6] 누적 적재 v2 — 코스피 + 코스닥 통합
==============================================
파이프라인 산출물(CSV)을 SQLite + Parquet으로 누적 보관.
market 컬럼으로 코스피/코스닥 구분.

저장 구조:
  history.db
    ├ runs                     # 실행 메타 (market 컬럼 포함)
    ├ stage1_oversold          # 1단계 결과 (market 컬럼 포함)
    ├ stage2_filtered          # 2단계 결과 (market 컬럼 포함)
    └ stage3_final             # 3단계 결과 (market 컬럼 포함)

  snapshots/YYYYMMDD/
    ├ kospi_stage1.parquet
    ├ kospi_stage3.parquet
    ├ kosdaq_stage1.parquet
    └ kosdaq_stage3.parquet

[사용법]
    python accumulate_history.py                  # 모든 시장 자동
    python accumulate_history.py --market kospi   # 코스피만
    python accumulate_history.py --market kosdaq  # 코스닥만
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_PATH = Path("history.db")
SNAPSHOT_DIR = Path("snapshots")
ARCHIVE_DIR = Path("archive")

# 시장별 파일 패턴 정의
MARKETS = {
    "kospi": [
        {"name": "stage1", "pattern": "v2_kospi_oversold_*.csv", "table": "stage1_oversold"},
        {"name": "stage2", "pattern": "v2_kospi_filtered_safe_*.csv", "table": "stage2_filtered"},
        {"name": "stage3", "pattern": "v2_kospi_final_*.csv", "table": "stage3_final"},
    ],
    "kosdaq": [
        {"name": "stage1", "pattern": "v2_kosdaq_oversold_*.csv", "table": "stage1_oversold"},
        {"name": "stage2", "pattern": "v2_kosdaq_filtered_safe_*.csv", "table": "stage2_filtered"},
        {"name": "stage3", "pattern": "v2_kosdaq_final_*.csv", "table": "stage3_final"},
    ],
}


def find_latest_csv(pattern, date_str=None):
    candidates = list(Path(".").glob(pattern))
    if date_str:
        candidates = [p for p in candidates if date_str in p.name]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def extract_timestamp_from_filename(filename):
    parts = Path(filename).stem.split("_")
    if len(parts) >= 2:
        return f"{parts[-2]}_{parts[-1]}"
    return datetime.now().strftime("%Y%m%d_%H%M")


def make_run_id(timestamp):
    return timestamp.split("_")[0]


def load_csv_with_meta(csv_path, run_id, run_ts, market):
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.insert(0, "market", market)
    df.insert(1, "run_id", run_id)
    df.insert(2, "run_timestamp", run_ts)
    return df


def write_to_sqlite(df, table_name, conn, market):
    """동일 (market, run_id) 조합이 있으면 먼저 삭제 후 append → 재실행 안전."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    )
    if cursor.fetchone():
        # 스키마 드리프트 방어: CSV엔 있는데 테이블에 없는 컬럼을 TEXT로 자동 추가
        # (예: stage2/3 CSV가 dart_status 컬럼을 새로 얻은 경우). 기존 행은 NULL.
        existing = {r[1] for r in cursor.execute(f"PRAGMA table_info({table_name})")}
        for col in df.columns:
            if col not in existing:
                cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN "{col}" TEXT')
                print(f"     ↪ [스키마] {table_name} 에 컬럼 자동추가: {col}")
        run_ids = df["run_id"].unique().tolist()
        placeholders = ",".join("?" * len(run_ids))
        cursor.execute(
            f"DELETE FROM {table_name} WHERE market=? AND run_id IN ({placeholders})",
            [market] + run_ids,
        )
        conn.commit()
    df.to_sql(table_name, conn, if_exists="append", index=False)


def write_parquet_snapshot(df, stage_name, run_id, market):
    day_dir = SNAPSHOT_DIR / run_id
    day_dir.mkdir(parents=True, exist_ok=True)
    out_path = day_dir / f"{market}_{stage_name}.parquet"
    df.to_parquet(out_path, index=False, compression="snappy")
    return out_path


def upsert_runs_meta(conn, run_id, run_ts, df_stage1, market):
    """실행 메타정보. (market, run_id)가 PK처럼 작동."""
    meta_cols = [
        "market_regime", "regime_score",
        "regime_kospi_score", "regime_fx_score", "regime_flow_score",
        "usdkrw", "usdkrw_vs_sma20_%", "foreign_kospi_5d_억",
    ]
    if df_stage1.empty:
        meta = {c: None for c in meta_cols}
    else:
        first = df_stage1.iloc[0]
        meta = {c: (first[c] if c in df_stage1.columns else None) for c in meta_cols}

    meta["market"] = market
    meta["run_id"] = run_id
    meta["run_timestamp"] = run_ts
    meta["stage1_count"] = len(df_stage1)

    df_meta = pd.DataFrame([meta])
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runs'")
    if cursor.fetchone():
        cursor.execute("DELETE FROM runs WHERE market=? AND run_id=?", (market, run_id))
        conn.commit()
    df_meta.to_sql("runs", conn, if_exists="append", index=False)


def accumulate_market(market, date_str, conn, archive=False):
    """한 시장의 모든 단계 CSV 적재. 적재된 게 있으면 True.
    archive=True면 적재 후 raw CSV를 archive/로 이동 (final은 루트에도 latest 사본 유지)."""
    stages = MARKETS[market]
    csvs = {}
    for stage in stages:
        csv = find_latest_csv(stage["pattern"], date_str)
        if csv is None:
            continue
        csvs[stage["name"]] = (csv, stage["table"])

    if not csvs:
        print(f"  [{market}] 매칭되는 CSV 없음 — 스킵")
        return False

    ref_csv = csvs.get("stage1", next(iter(csvs.values())))[0]
    run_ts = extract_timestamp_from_filename(ref_csv.name)
    run_id = make_run_id(run_ts)
    print(f"  [{market}] run_id={run_id}, timestamp={run_ts}")

    df_stage1_for_meta = pd.DataFrame()
    final_csv_path = None
    for stage_name, (csv_path, table) in csvs.items():
        df = load_csv_with_meta(csv_path, run_id, run_ts, market)
        write_to_sqlite(df, table, conn, market)
        if os.environ.get("SCREENER_NO_SNAPSHOTS", "0") in ("1", "true", "True", "yes"):
            print(f"     ↪ {stage_name}: {len(df):>4}행 → SQLite[{table}] (snapshot 생략)")
        else:
            parquet_path = write_parquet_snapshot(df, stage_name, run_id, market)
            print(f"     ↪ {stage_name}: {len(df):>4}행 → SQLite[{table}] + {parquet_path.name}")
        if stage_name == "stage1":
            df_stage1_for_meta = df
        if stage_name == "stage3":
            final_csv_path = csv_path

    if not df_stage1_for_meta.empty:
        upsert_runs_meta(conn, run_id, run_ts, df_stage1_for_meta, market)

    # 아카이빙 — CSV를 archive/YYYYMMDD/market/로 이동
    if archive:
        archive_csvs(market, run_id, csvs, final_csv_path)

    return True


def archive_csvs(market, run_id, csvs, final_csv_path):
    """raw CSV들을 archive/로 이동 + latest_<market>_final.csv는 루트에 유지."""
    target_dir = ARCHIVE_DIR / run_id / market
    target_dir.mkdir(parents=True, exist_ok=True)

    moved = 0
    # 모든 CSV 이동 (모든 v2_{market}_*_TIMESTAMP.csv 패턴)
    # find_latest_csv가 찾은 것 외에 stage2의 _filtered_all 도 같이 처리
    extra_patterns = [
        f"v2_{market}_oversold_*.csv",
        f"v2_{market}_filtered_safe_*.csv",
        f"v2_{market}_filtered_all_*.csv",
        f"v2_{market}_final_*.csv",
    ]
    today_id = run_id
    for pattern in extra_patterns:
        for csv in Path(".").glob(pattern):
            # 다른 날짜 CSV는 건드리지 않음
            if today_id not in csv.name:
                continue
            target = target_dir / csv.name
            if target.exists():
                target.unlink()
            csv.rename(target)
            moved += 1

    # 본인이 자주 보는 final CSV는 루트에 'latest' 사본으로 유지 (덮어쓰기)
    if final_csv_path is not None:
        archived_final = target_dir / final_csv_path.name
        if archived_final.exists():
            latest_path = Path(f"latest_{market}_final.csv")
            # 복사 (이동 아님)
            latest_path.write_bytes(archived_final.read_bytes())
            print(f"     📌 latest_{market}_final.csv (루트에 최신본 유지)")

    print(f"     🗂  {moved}개 CSV → {target_dir}/")


def main():
    parser = argparse.ArgumentParser(description="V2.6 결과 누적 적재 (코스피+코스닥)")
    parser.add_argument("--date", help="특정 날짜만 (YYYYMMDD)")
    parser.add_argument(
        "--market", choices=["kospi", "kosdaq", "all"], default="all",
        help="적재할 시장 (기본: all)"
    )
    parser.add_argument(
        "--archive", action="store_true",
        help="적재 후 raw CSV를 archive/로 이동. final은 latest_<market>_final.csv로 루트에 유지"
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"📦 V2.6 결과 누적 적재 (코스피+코스닥 통합)")
    print(f"{'='*60}")

    targets = ["kospi", "kosdaq"] if args.market == "all" else [args.market]

    conn = sqlite3.connect(DB_PATH)
    any_loaded = False
    for market in targets:
        any_loaded = accumulate_market(market, args.date, conn, archive=args.archive) or any_loaded
    conn.commit()
    conn.close()

    if not any_loaded:
        print("\n❌ 적재할 CSV가 하나도 없었습니다.")
        sys.exit(1)

    print(f"\n✅ 적재 완료 → {DB_PATH.resolve()}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
