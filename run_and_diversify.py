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
import time
import sqlite3
import statistics
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
    _t0 = time.time()
    rc = subprocess.run([sys.executable] + args_list, env=os.environ.copy()).returncode
    _el = time.time() - _t0
    _m, _s = divmod(int(_el), 60)
    _ts = f"{_m}분 {_s}초" if _m else f"{_s}초"
    if rc != 0:
        print(f"   ⚠️  {label} 종료 코드 {rc}  (소요 {_ts})")
    else:
        print(f"   ⏱  {label} 소요 {_ts}")
    return rc


def _git(args):
    """git 명령 실행 → (returncode, 출력문자열). git 없으면 (None, '')."""
    try:
        r = subprocess.run(["git"] + args, cwd=str(HERE),
                           capture_output=True, text=True)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return None, ""


def check_completeness(db_path, run_id=None, floor_frac=0.5, recent_n=10):
    """degraded(부분수집) 데이터의 공개 배포를 막는 게이트.
    게이트 판정은 stage1(수집 완전성의 직접 지표)만 사용한다. stage3 는 '과매도 40점 이상'
    종목 수라 반등장에서 정상적으로 급감할 수 있어(시장 의존) 게이트에서 제외하고
    참고(details)로만 남긴다.
    2026-08-04 변경: 반등장 오탐으로 배포 보류(kospi 117/중앙값 311, stage1·stage2 정상).
    전체 53개 run PIT 재현으로 검증 — 진짜 수집 실패(20260608, stage1 75/20행)는 stage1
    게이트 단독으로도 동일하게 검출, 시장 요인 2건(20260617·20260804)만 보류 해제됨.
    반환=(ok, issues, details)."""
    issues, details = [], []
    con = sqlite3.connect(str(db_path))
    try:
        for table, label, gates in (("stage1_oversold", "stage1", True),
                                    ("stage3_final", "stage3", False)):
            try:
                rid = run_id or con.execute(f"SELECT MAX(run_id) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                continue
            if rid is None:
                continue
            for mkt in ("kospi", "kosdaq"):
                cur = con.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE CAST(run_id AS TEXT)=? AND LOWER(market)=?",
                    (str(rid), mkt)).fetchone()[0]
                hist = [r[0] for r in con.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE LOWER(market)=? AND CAST(run_id AS TEXT)<>? "
                    f"GROUP BY run_id ORDER BY run_id DESC LIMIT ?", (mkt, str(rid), recent_n))]
                if len(hist) < 3:
                    continue
                med = statistics.median(hist)
                details.append(f"{label}·{mkt} {cur}")
                if med > 0 and cur < med * floor_frac:
                    msg = f"{label} {mkt}: {cur}행 (최근 중앙값 {int(med)}의 {cur/med:.0%}, 기준 {floor_frac:.0%} 미만)"
                    if gates:
                        issues.append(msg)
                    else:
                        # 시장 의존 지표 — 게이트 아님, 로그로만 남김
                        print(f"   ℹ️  {msg} — 시장 요인 가능(게이트 제외)")
        return (len(issues) == 0), issues, details
    finally:
        con.close()


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

    # 변경분 스테이징 — 배포 산출물(docs/)만 allowlist. **git add -A 금지**:
    #   작업 중인 코드·임시 파일이 자동 커밋되는 것을 막는다(감사 권고). docs/ = Pages 배포면.
    PUSH_ALLOWLIST = ["docs"]   # 배포 대상이 늘면 여기에 추가(현재는 전부 docs/ 아래)
    _git(["add", "--"] + PUSH_ALLOWLIST)
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

    # 배포 게이트 상태 — 치명 단계 실패 또는 degraded 데이터면 공개 배포(push·평소 텔레) 보류.
    deploy_ok = True
    critical_fail = []   # 치명 단계(점수/추천/대시보드) 실패 라벨

    # 2.6) v3 점수/등급/버킷 생성 — diversify·대시보드보다 '먼저' 돌려야 함.
    #      그날 v3 가 만들어지고 latest_*_final.csv 에 병합된다.
    if (HERE / "v3_daily.py").exists():
        rc = run_script(["v3_daily.py"], "2.6단계: v3 점수 생성·병합")
        if rc != 0:
            deploy_ok = False; critical_fail.append("v3 점수 생성(2.6)")

    # 2.65) 챌린저(v31a~) 섀도우 누적 — 조용히 {model}_archive 에만 저장(추가 네트워크 0).
    #       챔피언/대시보드/텔레그램엔 노출 안 함. 비교는 주 1회 compare_models.py.
    if (HERE / "shadow_run.py").exists():
        run_script(["shadow_run.py"], "2.65단계: 챌린저 섀도우 누적(조용)")

    # 2.66) 점수 동결 저장 — 방금 만들어진 archive(챔피언 v3_archive + 챌린저 {model}_archive)를
    #       DB v3_scores 에 append-only 적재(감사 #5). 재계산이 아닌 '그날 얼린 원본' 보존 →
    #       입력 드리프트에 면역. 점수·로직 불변, 새 테이블만 추가. 최신 run 만(빠름).
    if (HERE / "freeze_scores.py").exists():
        run_script(["freeze_scores.py", "--latest"], "2.66단계: 점수 동결 저장(append-only, drift 면역)")

    # 2) 분산 추천 — v3 점수 기준(파일에 v3 있으면 자동 사용, 없으면 v2.6 폴백)
    if not (HERE / "diversify_picks.py").exists():
        print("❌ diversify_picks.py 를 찾을 수 없습니다."); sys.exit(1)
    rc = run_script(["diversify_picks.py",
                "--max-per-sector", str(args.max_per_sector),
                "--top", str(args.top)],
               "2단계: 섹터 쏠림 방지 추천")
    if rc != 0:
        deploy_ok = False; critical_fail.append("분산 추천(2)")

    # 2.68) 촉매(내부자매수+자사주소각) 수집 — DART. catalyst_{market}_{run_id}.csv 생성.
    #        이게 '먼저' 있어야 다음 단계(catalyst_observe)가 insider/buyback 컬럼을 채운다.
    #        없어도 파이프라인은 계속(그 경우 insider/buyback 은 NULL 유지).
    if (HERE / "catalyst_insider.py").exists():
        run_script(["catalyst_insider.py"], "2.68단계: 촉매 수집(내부자/자사주, DART)")

    # 2.7) 관측 팩터 배선 (가중치 0): stage3_final 에 smartmoney/ROE/내부자/소각 컬럼 채움.
    if (HERE / "catalyst_observe.py").exists():
        run_script(["catalyst_observe.py"], "2.7단계: 관측 팩터 배선 (점수 불변)")

    # 2.72) 실현변동성 관측 컬럼(realized_vol) 채움 — 가중치 0, 점수 불변. 증분(미채움 run만).
    #        trailing 21 활성런 종가수익률 std. validate_scores 가 IC 측정(low-vol 가설 검정).
    if (HERE / "observe_vol.py").exists():
        run_script(["observe_vol.py"], "2.72단계: 실현변동성 관측 컬럼 (점수 불변)")

    # 2.73) 과매도 재출현/신선도 관측 컬럼(os_count_20d·os_streak·os_is_new20) — 가중치 0, 점수 불변. 증분.
    #        직전 20활성런 중 stage3 재등장 수/연속/신규. validate_scores 가 IC 측정. post-hoc → forward-only 판정.
    if (HERE / "observe_recurrence.py").exists():
        run_script(["observe_recurrence.py"], "2.73단계: 과매도 재출현 관측 컬럼 (점수 불변)")

    # 2.74) 급락 급성도 관측 컬럼(drop_acuteness) — 가중치 0, 점수 불변. 증분.
    #        월 낙폭 중 최근 1주 비율(return_1w_%/return_1m_%). validate_scores 가 IC 측정. post-hoc → forward-only.
    if (HERE / "observe_acuteness.py").exists():
        run_script(["observe_acuteness.py"], "2.74단계: 급락 급성도 관측 컬럼 (점수 불변)")

    # 2.5) 점수 적중도(IC) 계산 → 폰 대시보드 카드용 (실패해도 무해)
    if (HERE / "compute_ic.py").exists():
        run_script(["compute_ic.py"], "2.5단계: 점수 적중도(IC) 계산")

    # 2.55) v3 백테스트 — docs/v3_ic_summary.json 갱신(텔레그램 '검증 IC' 한 줄의 출처).
    #        compute_ic 와 독립: 이쪽은 v3_ic_summary.json 만, compute_ic 는 ic_summary.json 만
    #        쓴다(오프라인 0diff 확인). 텔레그램(4)·push(3) 전에 둬야 당일 반영. history.db만 사용.
    if (HERE / "v3_backtest.py").exists():
        run_script(["v3_backtest.py"], "2.55단계: v3 백테스트(검증 IC 요약 갱신)")

    # 2.8) 대시보드 재생성 — '그날 v3' + IC 가 반영되도록 다시 빌드.
    #      (스크리너 1단계에서 만든 대시보드는 그날 v3 이전이라 최신이 아님)
    if (HERE / "build_dashboard.py").exists():
        rc = run_script(["build_dashboard.py"], "2.8단계: 대시보드 재생성 (v3 반영)")
        if rc != 0:
            deploy_ok = False; critical_fail.append("대시보드(2.8)")

    # 2.85) v31g 챌린저 관측 CSV 생성 — filter_v31g.html 이 fetch할 docs/latest_*_v31g.csv 갱신.
    #        push(3) 전에 두어야 당일 반영. 점수 미투입·섬도우(검증 전). history.db만 사용.
    # [2026-08-09] 2.85단계(v31g 관측 CSV) 중지 — §11 첫 판정에서 v31g 기각(VERDICT_20260809.md).
    #   build_v31g_filter.py·docs/filter_v31g.html 파일은 보존(수동 실행 가능), 자동 갱신·링크만 제거.

    # 2.86) 저변동 트랙(lowvol) 관측 — lv_a~d·lv_a3 점수 적재(가중치 0) + lv_a 관측 CSV.
    #        v3·large 와 완전 분리(별도 테이블 lowvol_scores·전용 lowvol.html). 검증 전 섀도우.
    #        history.db(stage3)만 읽어 신규 API 0. 실패해도 챔피언 배포 안 막음(비치명).
    if (HERE / "lowvol_score.py").exists():
        run_script(["lowvol_score.py"], "2.86단계: 저변동 트랙 점수 적재 (관측, 점수 불변)")
    if (HERE / "build_lowvol_filter.py").exists():
        run_script(["build_lowvol_filter.py"], "2.87단계: 저변동 트랙 lv_a 관측 CSV (섀도우)")

    # 2.87b) 모멘텀 대조 모델(mom_a) 관측 CSV — mom.html 이 fetch할 docs/latest_*_mom.csv 갱신.
    #        점수 적재는 2.86(lowvol_score)이 이미 처리(mom_a 는 lowvol_scores 공유, §15).
    #        표시 전용 신규 파일만 생성 — v3·large·lv_a 산출물 0-diff. 실패해도 비치명.
    if (HERE / "build_mom_filter.py").exists():
        run_script(["build_mom_filter.py"], "2.87b단계: 모멘텀 mom_a 관측 CSV (섀도우)")

    # 2.88) 전체종목 트랙(wu) 관측 — wu_a·wu_b 점수 적재(가중치 0, 새 테이블 wu_scores) + wu_a 관측 CSV.
    #        v3·large·lowvol 과 완전 분리(전용 wu.html). 검증 전 섀도우(OOS 40거래일 전 노이즈).
    #        ohlcv.db(가격)만 읽어 신규 API 0. 실패해도 챔피언 배포 안 막음(비치명).
    if (HERE / "wu_score.py").exists():
        run_script(["wu_score.py"], "2.88단계: 전체종목 트랙 점수 적재 (관측, 점수 불변)")
    if (HERE / "build_wu_filter.py").exists():
        run_script(["build_wu_filter.py"], "2.89단계: 전체종목 트랙 wu_a 관측 CSV (섀도우)")

    # 2.89b) 조용한 강자(qs_a) 관측 CSV — qs.html 이 fetch할 docs/latest_qs.csv 갱신.
    #        점수 적재는 2.88(wu_score)이 이미 처리(qs_a 는 wu_scores 공유, PREREGISTER_qs.md).
    #        2026-07-29 노출 개정(§6) — 표시 전용, wu_a 산출물 0-diff. 실패해도 비치명.
    if (HERE / "build_wu_filter.py").exists():
        run_script(["build_wu_filter.py", "--model", "qs_a", "--out", "latest_qs.csv"],
                   "2.89b단계: 조용한 강자 qs_a 관측 CSV (섀도우)")

    # 2.89c) 가격 4팩터(px_a) 관측 CSV — px.html 이 fetch할 docs/latest_px.csv 갱신.
    #        점수 적재는 2.88(wu_score)이 이미 처리(px_a 는 wu_scores 공유, PREREGISTER_px_a.md).
    #        2026-08-11 사용자 결정: 테스트 열람용 표시 배선 — 표시 전용(판정·점수 0-diff), 실패해도 비치명.
    if (HERE / "build_wu_filter.py").exists():
        run_script(["build_wu_filter.py", "--model", "px_a", "--out", "latest_px.csv"],
                   "2.89c단계: 가격 4팩터 px_a 관측 CSV (섀도우)")

    # 2.895) 전종목 밸류 스냅샷 적재 — fetch_valuation 의 당일 valuation_*.csv(전종목
    #        PBR/PER/DIV/BPS/EPS)를 ohlcv.db `valuation_daily` 에 증분 적재.
    #        7일 회전으로 버려지던 포인트-인-타임 펀더멘털의 보존(2026-07-11, §26-5).
    #        순수 축적 — 점수·표시 미연결. 실패해도 비치명.
    if (HERE / "accumulate_valuation.py").exists():
        run_script(["accumulate_valuation.py"], "2.895단계: 밸류 스냅샷 적재 (관측 축적)")

    # 2.9) 판정일 도달 알림 — 모델별 OOS 40거래일 첫 도달 시 텔레그램 1회 알림(§11 시즌
    #      안전장치, 2026-07-11). history.db 직접 계산(leaderboard.json 신선도 무의존).
    #      판정 자체는 안 함(leaderboard.py 몫). 상태는 verdict_notified.json(로컬). 비치명.
    if (HERE / "notify_verdict_ready.py").exists():
        run_script(["notify_verdict_ready.py"], "2.9단계: 판정일 도달 알림 (1회성)")

    # 2.91) 전 트랙 리더보드 갱신 — 텔레그램 '모델 관측 현황'(notify_telegram)의 데이터 소스.
    #      2026-07-17: 텔레 본문이 종목 top3 → 모델 현황으로 바뀌면서 매일 신선도 필요해짐.
    #      leaderboard.py 는 읽기전용(history/ohlcv)·비치명(실패 시 pending 기록) 설계.
    if (HERE / "leaderboard.py").exists():
        run_script(["leaderboard.py"], "2.91단계: 전 트랙 리더보드 갱신 (leaderboard.json)")

    # 2.915) 공통 잣대 모의계좌 JSON — leaderboard.html 하단 관측 섹션용 (2026-08-14).
    #        판정(leaderboard.py)과 완전 분리 · 표시 전용 · 실패해도 비치명.
    if (HERE / "build_cross_sim.py").exists():
        run_script(["build_cross_sim.py"], "2.915단계: 공통 잣대 모의계좌 (관측, 판정 무관)")

    # 완전성 게이트: degraded(행수 비정상↓) 데이터는 공개 배포(push + 평소 텔레)를 보류.
    #   DB 기록은 남기고(감사·재현), 어제 대시보드 유지. degraded면 '보류' 알림만 보냄(침묵 금지).
    gate_issues, gate_details = [], []
    try:
        comp_ok, gate_issues, gate_details = check_completeness(str(HERE / "history.db"))
        deploy_ok = deploy_ok and comp_ok   # 치명 단계 실패와 결합(둘 중 하나라도 나쁘면 보류)
    except Exception as e:
        print(f"\n   ⚠️ 완전성 점검 실패 — 게이트 건너뛰고 계속: {e}")
    if gate_details:
        print(f"\n   🔎 완전성 점검: {' · '.join(gate_details)}")
    if not deploy_ok:
        print("\n   " + "🛑"*16)
        print("   배포 게이트: 공개 배포(push·평소 텔레) 보류")
        for cf in critical_fail:
            print(f"      • 단계 실패: {cf}")
        for it in gate_issues:
            print(f"      • {it}")
        print("   (DB 기록은 남김 · 어제 대시보드 유지 · 원인 확인 후 재실행 권장)")

    # 3) GitHub 자동 업로드 (push) — 완전하고 --no-push 아닐 때만
    if deploy_ok and not args.no_push:
        git_push()
    elif not deploy_ok:
        print("\n   ⏸  push 건너뜀(완전성 게이트).")

    # 4) 텔레그램 — 완전하면 평소 알림, degraded면 '보류' 알림(토큰 없으면 조용히 건너뜀)
    if (HERE / "notify_telegram.py").exists():
        try:
            import notify_telegram
            print(f"\n{'━'*64}\n▶  4단계: 텔레그램 알림\n{'━'*64}")
            if deploy_ok:
                notify_telegram.send()
            else:
                _reasons = ([f"• 단계 실패: {cf}" for cf in critical_fail]
                            + [f"• {it}" for it in gate_issues])
                alert = ("⚠️ 스크리너 — 배포 보류(데이터 불완전/단계 실패)\n\n"
                         + "\n".join(_reasons)
                         + "\n\n대시보드는 직전 정상 회차 유지. 원인 확인 후 재실행 권장.")
                notify_telegram.send(message=alert)
        except Exception as e:
            print(f"   ⚠️  텔레그램 알림 단계 오류: {e}")

    # 4b) 저변동 트랙 알림은 별도 메시지로 안 보냄 — v3 메시지 하단 링크로 대체(2026-06-25).
    #      점수 적재(2.86)·CSV(2.87)·HTML·lowvol_scores 는 그대로 유지. notify_lowvol_test.py 는 수동 미리보기용으로 남김.

    print("\n" + "=" * 64)
    print("  ✅ 전체 완료")
    print("     • 스크리너 결과: latest_kospi_final.csv / latest_kosdaq_final.csv")
    print("     • 분산 추천:     diversified_picks_*.csv")
    print("=" * 64)


if __name__ == "__main__":
    main()
