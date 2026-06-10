# -*- coding: utf-8 -*-
"""
make_handoff.py — Claude 핸드오프 패키지 생성 (동작/성능 분리)
=============================================================
작업 종류에 따라 넘길 zip을 분리한다:

  [동작]  코드·파이프라인·속도·파일IO 작업      → handoff_code_*.zip   (코드+설정만, 수 MB)
  [성능]  IC·챌린저 판정·백테스트·관측팩터 분석  → handoff_perf_*.zip   (history.db + v3_archive + docs/*.json)
  [점수·출력을 바꾸는 변경]                      → 둘 다 (0 diff 검증에 DB가 필요)

사용:
  python make_handoff.py --code        # 동작용만
  python make_handoff.py --perf        # 성능용만
  python make_handoff.py               # 둘 다
옵션:
  --with-model-archives   v31a~d_archive 포함 (보통 불필요 — compare_models가 DB로 재계산)
  --with-price-cache      price_cache 포함 (IC를 오프라인 재계산시킬 때만)
  --with-docs-csv         docs/latest_*.csv 포함 (보통 불필요 — 매 실행 재생성물)
출력: handoff/handoff_code_YYYYMMDD_HHMM.zip / handoff_perf_YYYYMMDD_HHMM.zip
"""
import argparse
import datetime as dt
import re
import subprocess
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "handoff"

# code zip에서 항상 제외 (git 추적 여부와 무관하게 — 데이터는 perf 쪽 담당)
CODE_EXCLUDE = [
    r"^history\.db$", r"^archive/", r"^snapshots/", r"^dart_cache/", r"^price_cache/",
    r"^_trash/", r"^backup/", r"^handoff/", r"^v3_archive/", r"^v31[a-z]_archive/",
    r"^diversified_picks_.*\.csv$", r"^validation_.*\.csv$",
    r"^latest_(kospi|kosdaq)_final\.csv$",
    r"^v3_(kospi|kosdaq)_final_.*\.csv$",
    r"^valuation_.*\.csv$", r"^catalyst_.*\.csv$",
    r"\.pyc$", r"^__pycache__/", r"\.bak$",
]
CODE_EXCLUDE_DOCS_CSV = r"^docs/.*\.csv$"

# git이 없을 때 폴백으로 담을 것들
FALLBACK_GLOBS = ["*.py", "*.bat", "*.md", "*.txt", "requirements.txt",
                  ".gitignore", "sector_cache.json", "docs/**/*", ".github/**/*"]


def _excluded(rel, patterns):
    rel = rel.replace("\\", "/")
    return any(re.search(p, rel) for p in patterns)


def list_code_files(with_docs_csv=False):
    patterns = list(CODE_EXCLUDE)
    if not with_docs_csv:
        patterns.append(CODE_EXCLUDE_DOCS_CSV)
    files = []
    try:
        # 추적 파일 + (gitignore를 존중하는) 미추적 파일 → 새로 만든 .py도 자동 포함
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(HERE), capture_output=True, text=True, check=True)
        rels = [l.strip() for l in out.stdout.splitlines() if l.strip()]
    except Exception:
        print("   ⚠️  git을 못 써서 폴백 수집(코드 확장자 기준)으로 진행합니다.")
        rels = set()
        for g in FALLBACK_GLOBS:
            for p in HERE.glob(g):
                if p.is_file():
                    rels.add(str(p.relative_to(HERE)))
        rels = sorted(rels)
    for rel in rels:
        p = HERE / rel
        if p.is_file() and not _excluded(rel, patterns):
            files.append(p)
    return files


def list_perf_files(with_models=False, with_price=False):
    files = []
    db = HERE / "history.db"
    if db.exists():
        files.append(db)
    else:
        print("   ⚠️  history.db 가 없습니다 — perf zip의 핵심이 빠집니다.")
    v3 = HERE / "v3_archive"
    if v3.exists():
        files += sorted(v3.glob("*.csv"))
    docs = HERE / "docs"
    if docs.exists():
        files += sorted(docs.glob("*.json"))
    if with_models:
        for d in sorted(HERE.glob("v31?_archive")):
            files += sorted(d.glob("*.csv"))
    if with_price:
        pc = HERE / "price_cache"
        if pc.exists():
            files += sorted(pc.glob("*.parquet"))
    return files


def write_zip(name, files):
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"{name}_{dt.datetime.now():%Y%m%d_%H%M}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for p in files:
            z.write(p, p.relative_to(HERE))
    mb = out.stat().st_size / 1048576
    print(f"   ✅ {out.relative_to(HERE)}  ({len(files)}개 파일, {mb:.1f} MB)")
    return out


def main():
    ap = argparse.ArgumentParser(description="Claude 핸드오프 패키지 생성")
    ap.add_argument("--code", action="store_true", help="동작 작업용(코드+설정)")
    ap.add_argument("--perf", action="store_true", help="성능 작업용(DB+결과)")
    ap.add_argument("--with-model-archives", action="store_true")
    ap.add_argument("--with-price-cache", action="store_true")
    ap.add_argument("--with-docs-csv", action="store_true")
    args = ap.parse_args()
    do_code = args.code or not (args.code or args.perf)
    do_perf = args.perf or not (args.code or args.perf)

    print("📦 핸드오프 패키지 생성")
    if do_code:
        files = list_code_files(args.with_docs_csv)
        print(f"— [동작] code zip: 코드·설정 {len(files)}개")
        write_zip("handoff_code", files)
    if do_perf:
        files = list_perf_files(args.with_model_archives, args.with_price_cache)
        print(f"— [성능] perf zip: history.db + v3_archive + docs/*.json 등 {len(files)}개")
        write_zip("handoff_perf", files)
    print("\n규칙: 동작 작업=code / 성능·판정=perf / 점수·출력을 바꾸는 변경=둘 다(0 diff 검증용)")


if __name__ == "__main__":
    main()
