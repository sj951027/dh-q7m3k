# -*- coding: utf-8 -*-
"""
cleanup.py — 매 실행마다 쌓이는 중복 CSV 안전 정리
====================================================
재생성 가능한 날짜별 중복 파일만 정리한다. 영구 삭제가 아니라
_trash/{정리일자}/ 로 '이동'하므로, 잘못 옮겨도 도로 꺼내면 된다.

정리 대상 (최근 KEEP_DAYS 일치는 남기고, 그보다 오래된 것만 이동):
    valuation_kospi_*.csv / valuation_kosdaq_*.csv
    v3_kospi_final_*.csv  / v3_kosdaq_final_*.csv
    diversified_picks_*.csv

절대 건드리지 않는 것 (보호):
    v3_archive/         ← 검증 히스토리 (백테스트의 핵심)
    latest_*_final.csv  ← 대시보드/텔레그램이 읽는 최신본
    docs/               ← 웹 대시보드
    history.db, sector_cache.json, .env, *.py, *.html, *.json, *.bat

사용:
    python cleanup.py                 # 미리보기 → y/n 확인 후 이동
    python cleanup.py --days 14       # 최근 14일 보관 (기본 7)
    python cleanup.py --yes           # 확인 없이 바로 이동
    python cleanup.py --dry-run       # 미리보기만 (이동 안 함)
    python cleanup.py --empty-trash   # _trash/ 통째로 영구 삭제
"""
import argparse
import datetime as dt
import glob
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRASH = HERE / "_trash"
KEEP_DAYS = 7

# 정리 대상 패턴 (날짜 YYYYMMDD 가 파일명에 들어가는 것들)
PATTERNS = [
    "valuation_kospi_*.csv",
    "valuation_kosdaq_*.csv",
    "v3_kospi_final_*.csv",
    "v3_kosdaq_final_*.csv",
    "diversified_picks_*.csv",
]

# 혹시라도 매칭되면 안 되는 보호 파일 (이중 안전장치)
PROTECT_NAMES = {
    "latest_kospi_final.csv", "latest_kosdaq_final.csv",
    "history.db", "sector_cache.json", ".env",
}
DATE_RE = re.compile(r"(\d{8})")


def _file_date(name):
    """파일명에서 YYYYMMDD 추출 → date. 없으면 None."""
    m = DATE_RE.search(name)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def collect(days):
    """이동 대상 파일 목록. 최근 days 일치와 보호파일은 제외."""
    cutoff = dt.date.today() - dt.timedelta(days=days)
    targets = []
    for pat in PATTERNS:
        for p in glob.glob(str(HERE / pat)):
            path = Path(p)
            if path.name in PROTECT_NAMES:
                continue
            # v3_archive 안은 glob 범위에 안 들어오지만 이중 확인
            if "v3_archive" in path.parts or "docs" in path.parts:
                continue
            d = _file_date(path.name)
            if d is None:
                continue          # 날짜 없는 파일은 안전하게 건너뜀
            if d < cutoff:
                targets.append((path, d))
    return sorted(targets, key=lambda x: x[1])


def empty_trash():
    if not TRASH.exists():
        print("_trash/ 가 없습니다. 비울 것 없음.")
        return
    n = sum(1 for _ in TRASH.rglob("*") if _.is_file())
    shutil.rmtree(TRASH)
    print(f"_trash/ 영구 삭제 완료 (파일 {n}개).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=KEEP_DAYS,
                    help=f"최근 N일 보관 (기본 {KEEP_DAYS})")
    ap.add_argument("--yes", action="store_true", help="확인 없이 바로 이동")
    ap.add_argument("--dry-run", action="store_true", help="미리보기만")
    ap.add_argument("--empty-trash", action="store_true",
                    help="_trash/ 통째로 영구 삭제")
    args = ap.parse_args()

    if args.empty_trash:
        empty_trash()
        return

    targets = collect(args.days)
    cutoff = dt.date.today() - dt.timedelta(days=args.days)
    print(f"기준: {cutoff} 이전 파일만 정리 (최근 {args.days}일은 보관)")
    print("보호: v3_archive/ · latest_*_final.csv · docs/ · history.db · .env\n")

    if not targets:
        print("정리할 오래된 중복 파일이 없습니다. 깨끗합니다.")
        return

    total = sum(p.stat().st_size for p, _ in targets)
    print(f"이동 대상 {len(targets)}개 ({total/1024:.0f} KB):")
    for p, d in targets:
        print(f"  {d}  {p.name}")

    if args.dry_run:
        print("\n[dry-run] 실제로는 아무것도 옮기지 않았습니다.")
        return

    if not args.yes:
        ans = input(f"\n위 {len(targets)}개를 _trash/ 로 옮길까요? (y/n) ").strip().lower()
        if ans != "y":
            print("취소했습니다.")
            return

    dest = TRASH / dt.date.today().strftime("%Y%m%d")
    dest.mkdir(parents=True, exist_ok=True)
    for p, _ in targets:
        target = dest / p.name
        if target.exists():           # 같은 이름이 이미 있으면 덮어쓰기 방지
            target = dest / f"{p.stem}_{dt.datetime.now():%H%M%S}{p.suffix}"
        shutil.move(str(p), str(target))
    print(f"\n완료: {len(targets)}개를 {dest} 로 이동.")
    print("되돌리려면 그 폴더에서 파일을 도로 꺼내세요. "
          "완전히 비우려면:  python cleanup.py --empty-trash")


if __name__ == "__main__":
    main()
