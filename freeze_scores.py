# -*- coding: utf-8 -*-
"""
freeze_scores.py — v3/챌린저 점수를 history.db 에 **append-only 동결 저장** (감사 권고 #5)
==============================================================================
문제(감사): v3 점수는 v3_archive/*.csv(gitignore)에만 있고 DB엔 없다. compare_models 는
과거 점수를 **현재 코드로 재계산**한다 → 입력(예: valuation)이 드리프트하면 재계산 ≠ 그날 값
→ OOS 비교가 오염될 수 있다.

해결: 그날 얼린 archive CSV(= 실제 표시/판정된 값)를 **그대로** DB 테이블 `v3_scores` 에
append-only 로 적재한다. 재계산이 아니라 **원본 동결값 보존**이라 드리프트에 면역.
키 = (run_id, market, ticker, model_id). 이미 있으면 **건드리지 않음**(최초 동결값이 진실).
spec_hash 를 같이 저장 → "어떤 spec 이 이 점수를 만들었나" 감사추적 + spec 드리프트 탐지.

순수 가산: stage1/2/3·runs·점수 로직 일절 안 건드림. 새 테이블 하나만 추가.

사용:
    python freeze_scores.py --backfill          # v3_archive + 모든 {model}_archive 1회 적재
    python freeze_scores.py --run-id 20260623   # 그날 run 만(파이프라인이 매일 호출)
    python freeze_scores.py --verify            # 적재 현황 요약(읽기 전용)
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "history.db"

# {model_id: (archive_dir, 파일 prefix)}.  챔피언 v30 = v3_archive/v3_*.csv,
# 챌린저 = {model}_archive/ 안의 CSV. 파일명 패턴은 prefix 로 매칭.
ARCHIVE_MAP = {
    "v30":  ("v3_archive",   "v3"),
    "v31a": ("v31a_archive", None),
    "v31b": ("v31b_archive", None),
    "v31c": ("v31c_archive", None),
    "v31d": ("v31d_archive", None),
    "v31f": ("v31f_archive", None),
    "v31g": ("v31g_archive", None),
}


def spec_hash(model_id):
    """MODELS[model_id] 스펙의 canonical 해시(12자). 스펙 모르면 'unknown'."""
    try:
        import v3_rescore as v3
        spec = v3.MODELS.get(model_id)
        if spec is None:
            return "unknown"
        blob = json.dumps(spec, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]
    except Exception:
        return "unknown"


def ensure_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS v3_scores (
            run_id          TEXT NOT NULL,
            market          TEXT NOT NULL,
            ticker          TEXT NOT NULL,
            model_id        TEXT NOT NULL,
            spec_hash       TEXT,
            final_score_v3  REAL,
            grade           TEXT,
            bucket          TEXT,
            frozen_at       TEXT,
            PRIMARY KEY (run_id, market, ticker, model_id)
        )
    """)
    con.commit()


def _iter_archive_files(root, model_id, run_id=None):
    adir, prefix = ARCHIVE_MAP[model_id]
    base = Path(root) / adir
    if not base.exists():
        return
    # 패턴: <something>_{market}_{run_id}.csv  (예: v3_kospi_20260622.csv)
    for p in sorted(base.glob("*.csv")):
        stem = p.stem
        parts = stem.split("_")
        if len(parts) < 3:
            continue
        rid = parts[-1]
        mkt = parts[-2].lower()
        if run_id and rid != str(run_id):
            continue
        if mkt not in ("kospi", "kosdaq"):
            continue
        if prefix and parts[0] != prefix:
            continue
        yield p, rid, mkt


def _latest_run(root, models):
    """등록된 archive 들에서 가장 큰 run_id 문자열을 찾는다(없으면 None)."""
    best = None
    for mid in models:
        if mid not in ARCHIVE_MAP:
            continue
        for _p, rid, _m in _iter_archive_files(root, mid, None):
            if best is None or rid > best:
                best = rid
    return best


def ingest(con, root, model_id, run_id=None):
    sh = spec_hash(model_id)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    ins = skip = drift = 0
    cur = con.cursor()
    for path, rid, mkt in _iter_archive_files(root, model_id, run_id):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
        except Exception as e:
            print(f"   ⚠️ {path.name} 읽기 실패: {e}")
            continue
        for r in rows:
            tk = (r.get("ticker") or "").strip()
            if not tk:
                continue
            fs = r.get("final_score_v3")
            try:
                fs = float(fs) if fs not in (None, "", "nan") else None
            except (TypeError, ValueError):
                fs = None
            key = (str(rid), mkt, tk, model_id)
            existing = cur.execute(
                "SELECT spec_hash FROM v3_scores WHERE run_id=? AND market=? AND ticker=? AND model_id=?",
                key).fetchone()
            if existing is not None:
                skip += 1
                if existing[0] and sh != "unknown" and existing[0] != sh:
                    drift += 1   # 같은 키인데 spec_hash 다름 = 동결 스펙 변경 신호(경고만)
                continue
            cur.execute(
                "INSERT INTO v3_scores (run_id,market,ticker,model_id,spec_hash,"
                "final_score_v3,grade,bucket,frozen_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (str(rid), mkt, tk, model_id, sh, fs,
                 (r.get("grade") or None), (r.get("bucket") or None), now))
            ins += 1
    con.commit()
    return ins, skip, drift


def verify(con):
    print("=== v3_scores 적재 현황 ===")
    try:
        tot = con.execute("SELECT COUNT(*) FROM v3_scores").fetchone()[0]
    except sqlite3.OperationalError:
        print("  (테이블 없음 — --backfill 먼저)")
        return
    print(f"  총 {tot}행")
    for mid, n, runs, hashes in con.execute(
        "SELECT model_id, COUNT(*), COUNT(DISTINCT run_id), COUNT(DISTINCT spec_hash) "
        "FROM v3_scores GROUP BY model_id ORDER BY model_id"):
        flag = "  ⚠️ spec_hash 2개+(동결 스펙 변경?)" if hashes > 1 else ""
        print(f"  {mid:6s}: {n:6d}행 · {runs:2d} run · spec_hash {hashes}종{flag}")
    rng = con.execute("SELECT MIN(run_id), MAX(run_id) FROM v3_scores").fetchone()
    print(f"  run 범위: {rng[0]} ~ {rng[1]}")


def main():
    ap = argparse.ArgumentParser(description="v3 점수 동결 저장(append-only)")
    ap.add_argument("--root", default=str(HERE), help="프로젝트 루트(archive 폴더 위치)")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--run-id", default=None, help="이 run 만 적재")
    ap.add_argument("--latest", action="store_true", help="archive 중 최신 run만 적재(매일 파이프라인용·빠름)")
    ap.add_argument("--backfill", action="store_true", help="모든 archive 1회 적재")
    ap.add_argument("--verify", action="store_true", help="현황만 출력(읽기 전용)")
    ap.add_argument("--models", default=None, help="쉼표구분 모델 한정(기본=전부)")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    try:
        if args.verify:
            verify(con)
            return
        ensure_table(con)
        # [2026-08-09] 기각 모델(v3_rescore.RETIRED)은 기본 동결 대상에서 제외(기존 행 보존).
        models = (args.models.split(",") if args.models
                  else [m for m in ARCHIVE_MAP if m not in getattr(v3, "RETIRED", set())])
        run_id = None
        if args.backfill:
            run_id = None
        elif args.latest:
            run_id = _latest_run(args.root, models)
            if not run_id:
                print("   ⚠️ archive 에서 run 을 찾지 못했습니다(아직 생성 전?)."); return
        elif args.run_id:
            run_id = str(args.run_id)
        else:
            print("   ⚠️ --backfill / --latest / --run-id 중 하나가 필요합니다.")
            return
        scope = "백필(전체)" if args.backfill else f"run {run_id}"
        print(f"▶ 점수 동결 저장 — {scope} · 모델 {len(models)}개")
        tot_i = tot_s = tot_d = 0
        for mid in models:
            if mid not in ARCHIVE_MAP:
                print(f"   ⏭ {mid}: 미등록 모델, 건너뜀"); continue
            i, s, d = ingest(con, args.root, mid, run_id)
            if i or s:
                msg = f"   {mid:6s}: +{i} 신규 · {s} 기존보존"
                if d:
                    msg += f" · ⚠️{d} spec_hash 불일치"
                print(msg)
            tot_i += i; tot_s += s; tot_d += d
        print(f"💾 완료 — 신규 {tot_i}행 동결 · {tot_s}행 기존 보존(append-only)"
              + (f" · ⚠️ {tot_d}행 spec 드리프트 의심" if tot_d else ""))
        if tot_d:
            print("   ⚠️ spec_hash 불일치 = 동결됐던 모델 스펙이 바뀌었을 수 있음. 새 model_id 권장(불변규칙 2).")
    finally:
        con.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
