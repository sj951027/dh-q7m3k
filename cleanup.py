# -*- coding: utf-8 -*-
"""
cleanup.py — 산출물 보존정책 정리 v2
====================================================
원칙: "백테스트/비교에 필요한 원본"은 영구 보존, "재현 가능한 중간 산출물"만 회전.
영구 삭제가 아니라 _trash/{정리일자}/ 로 '이동'한다(DART 캐시만 예외 — 100% 재현 가능 캐시라 직접 삭제).

영구 보존 (절대 건드리지 않음):
    history.db            ← 모든 점수·관측팩터의 원본 (백테스트의 근간)
    v3_archive/           ← v3 점수의 유일한 영구 기록 (compute_ic·대시보드·텔레그램이 읽음)
    v31a~d_archive/       ← 챌린저의 '그날 얼린' OOS 기록 (실험 감사용)
    docs/                 ← GitHub Pages 대시보드 (filter.html이 docs/latest_*_*.csv를 fetch)
    latest_*_final.csv    ← 루트 최신본 (텔레그램·catalyst가 읽음)
    price_cache/ · sector_cache.json · .env · 코드 일체

회전 (보관일 지난 것만 _trash/ 이동 — 값은 전부 history.db에 이미 적재됨):
    valuation_* / v3_*_final_* / diversified_picks_*   기본 7일   (--days)
    catalyst_*                                         기본 30일  (--catalyst-days)
                                                       └ catalyst_observe --full 재백필 여지 때문에 길게
    archive/YYYYMMDD/  (해당 run이 DB에 있는 날짜만)    기본 14일  (--archive-days)
    snapshots/YYYYMMDD/                                기본 7일   (--snap-days)

직접 삭제 (재현 가능한 캐시 — 필요해지면 자동 재수집됨):
    dart_cache/fin/*.json 중 mtime이 오래된 것          기본 30일  (--dart-days, --no-dart로 끔)
    dart_cache/**/*.tmp.* 잔재                          즉시

부가:
    --backup-db        history.db → backup/history_YYYYMMDD.db.gz (최근 4개 유지)

사용:
    python cleanup.py                # 미리보기 → y/n 확인 후 실행
    python cleanup.py --yes          # 확인 없이 바로
    python cleanup.py --dry-run      # 미리보기만
    python cleanup.py --yes --backup-db    # 정리 + DB 백업 (주 1회 권장)
    python cleanup.py --empty-trash  # _trash/ 통째로 영구 삭제
"""
import argparse
import datetime as dt
import glob
import gzip
import re
import shutil
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRASH = HERE / "_trash"
DATE_RE = re.compile(r"(\d{8})")

# 루트 회전 대상: (glob 패턴, 보관일 키)
ROOT_PATTERNS = [
    ("valuation_kospi_*.csv", "days"),
    ("valuation_kosdaq_*.csv", "days"),
    ("v3_kospi_final_*.csv", "days"),
    ("v3_kosdaq_final_*.csv", "days"),
    ("diversified_picks_*.csv", "days"),
    ("large_universe_*.csv", "days"),              # 대형 트랙 1단계 산출 (DB 적재됨 → 7일)
    ("catalyst_kospi_*.csv", "catalyst_days"),
    ("catalyst_kosdaq_*.csv", "catalyst_days"),
    ("catalyst_large_*.csv", "catalyst_days"),     # 대형 자사주 스캔 (large_final 반영 → 30일)
]

# 이중 안전장치: 어떤 경우에도 건드리면 안 되는 이름/디렉터리
PROTECT_NAMES = {
    "latest_kospi_final.csv", "latest_kosdaq_final.csv",
    "history.db", "sector_cache.json", ".env",
}
PROTECT_DIR_PARTS = {"v3_archive", "docs", "price_cache", "_trash", "backup",
                     "v31a_archive", "v31b_archive", "v31c_archive", "v31d_archive"}


def _file_date(name):
    m = DATE_RE.search(name)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _size_mb(paths):
    total = 0
    for p in paths:
        if p.is_dir():
            total += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        elif p.is_file():
            total += p.stat().st_size
    return total / 1048576


def db_run_ids():
    """history.db의 stage3_final에 존재하는 run_id 집합. DB 없으면 빈 집합."""
    db = HERE / "history.db"
    if not db.exists():
        return set()
    try:
        con = sqlite3.connect(db)
        rows = con.execute("SELECT DISTINCT run_id FROM stage3_final").fetchall()
        con.close()
        return {str(r[0]) for r in rows}
    except Exception:
        return set()


def collect_root(args):
    """루트 CSV 회전 대상 (path, date) 리스트."""
    targets = []
    for pat, key in ROOT_PATTERNS:
        keep = getattr(args, key)
        cutoff = dt.date.today() - dt.timedelta(days=keep)
        for p in glob.glob(str(HERE / pat)):
            path = Path(p)
            if path.name in PROTECT_NAMES:
                continue
            if PROTECT_DIR_PARTS & set(path.parts):
                continue
            d = _file_date(path.name)
            if d is None or d >= cutoff:
                continue
            targets.append((path, d))
    return sorted(targets, key=lambda x: x[1])


def collect_date_dirs(base_name, keep_days, require_db=False, runs=None):
    """archive/ 또는 snapshots/ 의 날짜 폴더 회전 대상."""
    base = HERE / base_name
    if not base.exists():
        return [], []
    cutoff = dt.date.today() - dt.timedelta(days=keep_days)
    targets, held = [], []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        d = _file_date(child.name)
        if d is None or d >= cutoff:
            continue
        if require_db and runs is not None and child.name not in runs:
            held.append(child)          # DB에 없는 run → 유일본일 수 있어 보류
            continue
        targets.append((child, d))
    return targets, held


def collect_dart(args):
    """dart_cache/fin 의 오래된 캐시 + tmp 잔재."""
    base = HERE / "dart_cache"
    old, tmps = [], []
    if args.no_dart or not base.exists():
        return old, tmps
    cutoff = dt.datetime.now().timestamp() - args.dart_days * 86400
    fin = base / "fin"
    if fin.exists():
        for p in fin.glob("*.json"):
            try:
                if p.stat().st_mtime < cutoff:
                    old.append(p)
            except OSError:
                pass
    for p in base.rglob("*.tmp.*"):
        tmps.append(p)
    return old, tmps


def backup_db(keep=4):
    src = HERE / "history.db"
    if not src.exists():
        print("   ⚠️  history.db 없음 — 백업 생략")
        return
    bdir = HERE / "backup"
    bdir.mkdir(exist_ok=True)
    out = bdir / f"history_{dt.date.today():%Y%m%d}.db.gz"
    with open(src, "rb") as f_in, gzip.open(out, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)
    print(f"   💾 DB 백업: {out.name} ({out.stat().st_size/1048576:.1f} MB)")
    olds = sorted(bdir.glob("history_*.db.gz"))
    for p in olds[:-keep]:
        p.unlink()
        print(f"   🗑  오래된 백업 삭제: {p.name}")


def empty_trash():
    if not TRASH.exists():
        print("_trash/ 가 없습니다. 비울 것 없음.")
        return
    n = sum(1 for _ in TRASH.rglob("*") if _.is_file())
    shutil.rmtree(TRASH)
    print(f"_trash/ 영구 삭제 완료 (파일 {n}개).")


def move_to_trash(path, sub=""):
    dest_dir = TRASH / dt.date.today().strftime("%Y%m%d") / sub
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / path.name
    if target.exists():
        target = dest_dir / f"{path.stem}_{dt.datetime.now():%H%M%S}{path.suffix}"
    shutil.move(str(path), str(target))


def main():
    ap = argparse.ArgumentParser(description="산출물 보존정책 정리 v2")
    ap.add_argument("--days", type=int, default=7, help="루트 CSV 보관일 (기본 7)")
    ap.add_argument("--catalyst-days", type=int, default=30, help="catalyst CSV 보관일 (기본 30)")
    ap.add_argument("--archive-days", type=int, default=14, help="archive/날짜 보관일 (기본 14)")
    ap.add_argument("--snap-days", type=int, default=7, help="snapshots/날짜 보관일 (기본 7)")
    ap.add_argument("--dart-days", type=int, default=30, help="DART fin 캐시 보관일 (기본 30)")
    ap.add_argument("--no-dart", action="store_true", help="DART 캐시 정리 건너뜀")
    ap.add_argument("--backup-db", action="store_true", help="history.db gzip 백업 (최근 4개 유지)")
    ap.add_argument("--yes", action="store_true", help="확인 없이 바로 실행")
    ap.add_argument("--dry-run", action="store_true", help="미리보기만")
    ap.add_argument("--empty-trash", action="store_true", help="_trash/ 영구 삭제")
    args = ap.parse_args()

    if args.empty_trash:
        empty_trash()
        return

    if args.backup_db and not args.dry_run:
        backup_db()

    runs = db_run_ids()
    root_t = collect_root(args)
    arch_t, arch_held = collect_date_dirs("archive", args.archive_days,
                                          require_db=True, runs=runs)
    snap_t, _ = collect_date_dirs("snapshots", args.snap_days)
    dart_old, dart_tmp = collect_dart(args)

    print("\n보존 정책: history.db / v3_archive / v31*_archive / docs / latest_* / price_cache = 영구")
    print(f"회전 기준: 루트CSV {args.days}일 · catalyst {args.catalyst_days}일 · "
          f"archive {args.archive_days}일 · snapshots {args.snap_days}일 · DART캐시 {args.dart_days}일\n")

    if arch_held:
        print(f"⏸  보류(이동 안 함): DB(stage3_final)에 run_id가 없는 archive 날짜 "
              f"{[d.name for d in arch_held]} — 유일본일 수 있음\n")

    groups = [
        ("루트 CSV", [p for p, _ in root_t], "root"),
        ("archive/날짜 폴더", [p for p, _ in arch_t], "archive"),
        ("snapshots/날짜 폴더", [p for p, _ in snap_t], "snapshots"),
    ]
    any_work = False
    for label, items, _ in groups:
        if items:
            any_work = True
            print(f"이동 대상 — {label}: {len(items)}개 ({_size_mb(items):.1f} MB)")
            for p in items[:8]:
                print(f"   {p.relative_to(HERE)}")
            if len(items) > 8:
                print(f"   … 외 {len(items)-8}개")
    if dart_old or dart_tmp:
        any_work = True
        print(f"직접 삭제 — DART 캐시: 오래된 {len(dart_old)}개 ({_size_mb(dart_old):.1f} MB)"
              f" + tmp 잔재 {len(dart_tmp)}개")

    if not any_work:
        print("정리할 것이 없습니다. 깨끗합니다.")
        return

    if args.dry_run:
        print("\n[dry-run] 실제로는 아무것도 옮기지/지우지 않았습니다.")
        return

    if not args.yes:
        ans = input("\n위 항목을 정리할까요? (y/n) ").strip().lower()
        if ans != "y":
            print("취소했습니다.")
            return

    for p, _ in root_t:
        move_to_trash(p)
    for p, _ in arch_t:
        move_to_trash(p, sub="archive")
    for p, _ in snap_t:
        move_to_trash(p, sub="snapshots")
    deleted = 0
    for p in dart_old + dart_tmp:
        try:
            p.unlink()
            deleted += 1
        except OSError:
            pass

    print(f"\n완료: _trash/ 이동 {len(root_t)+len(arch_t)+len(snap_t)}건, "
          f"DART 캐시 삭제 {deleted}건.")
    print("되돌리기: _trash/ 에서 도로 꺼내면 됨. 완전 비우기: python cleanup.py --empty-trash")


if __name__ == "__main__":
    main()
