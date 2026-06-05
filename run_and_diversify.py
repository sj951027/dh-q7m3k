#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_and_diversify.py — 스크리너 + 분산 추천을 한 번에 실행
============================================================
하는 일 (순서대로):
  1) .env 파일에서 DART_API_KEY를 읽어 환경에 넣는다
     (이미 OS 환경변수로 설정돼 있으면 그걸 그대로 사용 — 덮어쓰지 않음)
  2) 키가 제대로 있는지 확인 (없거나 placeholder면 안내 후 중단)
  3) run_all_v2_6.py  실행 (KOSPI + KOSDAQ 스크리너 전체)
  4) 성공하면 이어서 diversify_picks.py 실행 (섹터 쏠림 방지 추천)
     → 스크리너가 실패하면 분산은 돌리지 않는다 (잘못된 데이터 방지)

키 넣는 법 (한 번만):
  1) 같은 폴더의 .env.example 을 복사해서 .env 로 이름 바꾸기
  2) .env 를 메모장으로 열어 다음 줄의 값을 실제 키로 교체:
        DART_API_KEY=여기에_실제_키_입력
  3) 저장. 끝. (.env 는 .gitignore에 있어 GitHub에 안 올라감)

실행:
  python run_and_diversify.py
  또는 run_all_and_diversify.bat 더블클릭 (Windows)

옵션:
  --skip-screener     스크리너는 건너뛰고 분산만 (이미 결과가 있을 때)
  --max-per-sector N  업종당 최대 개수 (기본 3)
  --top N             분산 추천 개수 (기본 20)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_dotenv(path=None):
    """.env 파일을 읽어 os.environ에 채운다. 이미 설정된 변수는 덮어쓰지 않음.
    의존성(python-dotenv) 없이 동작하는 간단 파서."""
    path = Path(path) if path else (HERE / ".env")
    if not path.exists():
        return False
    loaded = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:        # OS 환경변수 우선
                os.environ[key] = val
                loaded += 1
    except Exception as e:
        print(f"   ⚠️  .env 읽기 중 오류: {e}")
        return False
    if loaded:
        print(f"   🔑 .env 에서 {loaded}개 변수 로드")
    return True


def key_looks_valid(key):
    """stage2/stage3와 동일 기준: placeholder가 아니고 길이 30+ 면 유효로 간주."""
    if not key:
        return False
    if "여기에" in key:
        return False
    return len(key.strip()) >= 30


def check_dart_key():
    load_dotenv()
    key = os.environ.get("DART_API_KEY", "")
    if key_looks_valid(key):
        masked = key[:4] + "…" + key[-4:]
        print(f"   ✅ DART_API_KEY 확인됨 ({masked})")
        return True

    print("\n" + "=" * 64)
    print("  ❌ DART_API_KEY를 찾을 수 없습니다 (또는 아직 placeholder).")
    print("=" * 64)
    print("  해결 방법 (둘 중 하나):")
    print("   (A) .env 파일에 키 넣기  ← 권장, 한 번만")
    print("       1) .env.example 을 복사해 .env 로 이름 변경")
    print("       2) .env 를 열어  DART_API_KEY=실제키  로 수정 후 저장")
    print("   (B) 또는 OS 환경변수로 등록 (Windows):")
    print('       setx DART_API_KEY "실제키"   → 새 터미널에서 실행')
    print("\n  키 확인: https://opendart.fss.or.kr → 인증키 신청/관리 → 오픈API 이용현황")
    print("=" * 64 + "\n")
    return False


def run_script(args_list, label):
    print(f"\n{'━'*64}\n▶  {label}\n{'━'*64}")
    rc = subprocess.run([sys.executable] + args_list, env=os.environ.copy()).returncode
    if rc != 0:
        print(f"   ⚠️  {label} 종료 코드 {rc}")
    return rc


def _git(args):
    """git 명령 실행 → (returncode, 출력문자열). git 없으면 (None, '')."""
    try:
        r = subprocess.run(["git"] + args, cwd=str(HERE),
                           capture_output=True, text=True)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return None, ""


def git_push():
    """결과를 GitHub에 commit + push. 키 유출 방지 안전장치 포함."""
    print(f"\n{'━'*64}\n▶  3단계: GitHub 업로드 (push)\n{'━'*64}")

    # git 저장소인지 확인
    if not (HERE / ".git").exists():
        print("   ⏭  이 폴더는 GitHub와 연결돼 있지 않아 업로드를 건너뜁니다.")
        print("      (clone한 dh-q7m3k 폴더에서 실행해야 자동 업로드됩니다.)")
        return
    rc, _ = _git(["rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        print("   ⏭  git 저장소가 아니라 업로드를 건너뜁니다."); return

    # 🔒 안전장치: .env 가 git에 올라갈 위험이 있으면 즉시 중단
    if (HERE / ".env").exists():
        rc_ig, _ = _git(["check-ignore", ".env"])
        if rc_ig != 0:   # 0이면 무시됨(안전). 0이 아니면 추적될 수 있음!
            print("   🛑 중단: .env(키 파일)가 .gitignore로 보호되지 않습니다.")
            print("      키 유출을 막기 위해 업로드하지 않았습니다.")
            print("      → .gitignore 맨 위에 '.env' 한 줄이 있는지 확인 후 다시 실행.")
            return

    # 변경분 스테이징 (.gitignore가 .env/캐시를 알아서 제외)
    _git(["add", "-A"])
    rc_diff, _ = _git(["diff", "--cached", "--quiet"])
    if rc_diff == 0:
        print("   ℹ️  바뀐 내용이 없어 업로드할 게 없습니다 (정상)."); return

    # 한 번 더 방어: .env 가 실제로 스테이징됐으면 중단
    _, staged = _git(["diff", "--cached", "--name-only"])
    if any(line.strip() == ".env" for line in staged.splitlines()):
        print("   🛑 중단: .env 가 업로드 목록에 포함됨. 안전을 위해 취소합니다.")
        _git(["reset"]); return

    from datetime import datetime
    msg = f"Auto update {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    rc_c, out_c = _git(["commit", "-m", msg])
    if rc_c != 0:
        print(f"   ⚠️  commit 실패:\n      {out_c[:300]}"); return

    rc_p, out_p = _git(["push"])
    if rc_p == 0:
        print("   ✅ 업로드 완료 — 약 10초 뒤 폰에서 최신으로 보입니다.")
        print("      https://sj951027.github.io/dh-q7m3k/")
    else:
        print(f"   ⚠️  push 실패:\n      {out_p[:300]}")
        print("      대개 인증 문제입니다 → GitHub Desktop을 한 번 열어 로그인/푸시하면")
        print("      이후부터는 자동 push가 됩니다.")


def main():
    ap = argparse.ArgumentParser(description="스크리너 + 분산 추천 한 번에")
    ap.add_argument("--skip-screener", action="store_true")
    ap.add_argument("--max-per-sector", type=int, default=3)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--no-push", action="store_true",
                    help="결과를 GitHub에 자동 업로드하지 않음")
    args = ap.parse_args()

    print("=" * 64)
    print("  🚀 스크리너 + 섹터 분산 추천  통합 실행")
    print("=" * 64)

    if not check_dart_key():
        sys.exit(1)

    # 1) 스크리너
    if not args.skip_screener:
        if not (HERE / "run_all_v2_6.py").exists():
            print("❌ run_all_v2_6.py 를 찾을 수 없습니다 (같은 폴더에 있어야 함)."); sys.exit(1)
        rc = run_script(["run_all_v2_6.py"], "1단계: 스크리너 (KOSPI + KOSDAQ)")
        if rc != 0:
            print("\n❌ 스크리너가 실패해 분산 단계를 건너뜁니다. 위 로그를 확인하세요.")
            sys.exit(rc)
    else:
        print("\n⏭  스크리너 건너뜀 (--skip-screener) — 기존 결과로 분산만 진행")

    # 2.6) v3 점수/등급/버킷 생성 — diversify·대시보드보다 '먼저' 돌려야 함.
    #      그날 v3 가 만들어지고 latest_*_final.csv 에 병합된다.
    if (HERE / "v3_daily.py").exists():
        run_script(["v3_daily.py"], "2.6단계: v3 점수 생성·병합")

    # 2) 분산 추천 — v3 점수 기준(파일에 v3 있으면 자동 사용, 없으면 v2.6 폴백)
    if not (HERE / "diversify_picks.py").exists():
        print("❌ diversify_picks.py 를 찾을 수 없습니다."); sys.exit(1)
    run_script(["diversify_picks.py",
                "--max-per-sector", str(args.max_per_sector),
                "--top", str(args.top)],
               "2단계: 섹터 쏠림 방지 추천")

    # 2.7) 관측 팩터 배선 (가중치 0): stage3_final 에 smartmoney/ROE/내부자/소각 컬럼 채움.
    if (HERE / "catalyst_observe.py").exists():
        run_script(["catalyst_observe.py"], "2.7단계: 관측 팩터 배선 (점수 불변)")

    # 2.5) 점수 적중도(IC) 계산 → 폰 대시보드 카드용 (실패해도 무해)
    if (HERE / "compute_ic.py").exists():
        run_script(["compute_ic.py"], "2.5단계: 점수 적중도(IC) 계산")

    # 2.8) 대시보드 재생성 — '그날 v3' + IC 가 반영되도록 다시 빌드.
    #      (스크리너 1단계에서 만든 대시보드는 그날 v3 이전이라 최신이 아님)
    if (HERE / "build_dashboard.py").exists():
        run_script(["build_dashboard.py"], "2.8단계: 대시보드 재생성 (v3 반영)")

    # 3) GitHub 자동 업로드 (push) — 폰에서 보려면 필요
    if not args.no_push:
        git_push()

    # 4) 텔레그램 알림 (완료 + IC + TOP3 + 링크) — 토큰 없으면 조용히 건너뜀
    if (HERE / "notify_telegram.py").exists():
        try:
            import notify_telegram
            print(f"\n{'━'*64}\n▶  4단계: 텔레그램 알림\n{'━'*64}")
            notify_telegram.send()
        except Exception as e:
            print(f"   ⚠️  텔레그램 알림 단계 오류: {e}")

    print("\n" + "=" * 64)
    print("  ✅ 전체 완료")
    print("     • 스크리너 결과: latest_kospi_final.csv / latest_kosdaq_final.csv")
    print("     • 분산 추천:     diversified_picks_*.csv")
    print("=" * 64)


if __name__ == "__main__":
    main()
