#!/usr/bin/env python3
"""
[V2.6] 전체 파이프라인 자동 실행 — 코스피 + 코스닥
==================================================
[필요 파일]
  • screener_fdr_v2_6.py              (코스피/코스닥 공용, V2_INPUT_MARKET로 시장 선택)
  • stage2_risk_filter_v2_6.py        (코스피/코스닥 공용, INPUT_CSV 자동 탐지)
  • stage3_fundamental_momentum_v2_6.py
  • accumulate_history.py

[실행]
    python run_all_v2_6.py                  # 코스피+코스닥 둘 다
    python run_all_v2_6.py --market kospi   # 코스피만
    python run_all_v2_6.py --market kosdaq  # 코스닥만
    python run_all_v2_6.py --no-accumulate  # 누적 적재 스킵
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime


def build_stages(market: str):
    """market에 따라 단계 정의 생성. stage2/3는 공용 스크립트지만 입력 파일 패턴이 다름."""
    return [
        {
            'script': 'screener_fdr_v2_6.py',
            'name': f'[V2.6 / {market.upper()}] 1단계: 과매도 스크리닝',
            'output_pattern': f'v2_{market}_oversold_*.csv',
            'desc': '레짐 + 환율 + 외인 통합 스크리닝',
            'env_extra': {'V2_INPUT_MARKET': market},
        },
        {
            'script': 'stage2_risk_filter_v2_6.py',
            'name': f'[V2.6 / {market.upper()}] 2단계: DART 리스크 필터',
            'output_pattern': f'v2_{market}_filtered_safe_*.csv',
            'desc': 'DART 공시 + 키워드 위험 진단',
            'env_extra': {'V2_INPUT_MARKET': market},
        },
        {
            'script': 'stage3_fundamental_momentum_v2_6.py',
            'name': f'[V2.6 / {market.upper()}] 3단계: 펀더멘털 + 모멘텀 + OCF',
            'output_pattern': f'v2_{market}_final_*.csv',
            'desc': '분기 YoY + OCF/영업이익 + final_score 산출',
            'env_extra': {'V2_INPUT_MARKET': market},
        },
    ]


def newest_new_file(before, pattern):
    after = set(Path('.').glob(pattern))
    new_files = list(after - before)
    if new_files:
        return sorted(new_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    candidates = sorted(after, key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    latest = candidates[0]
    age_sec = (datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)).total_seconds()
    return latest if age_sec < 300 else None


def run_stage(stage_info, stage_num, total):
    import os
    script = stage_info['script']
    name = stage_info['name']

    print(f"\n\n{'█' * 72}")
    print(f"█  [{stage_num}/{total}]  {name}")
    print(f"█  📝 {stage_info['desc']}")
    print(f"█  ⏰ 시작: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'█' * 72}\n")

    before = set(Path('.').glob(stage_info['output_pattern']))
    start = time.time()
    try:
        env = os.environ.copy()
        env.update(stage_info.get('env_extra') or {})
        result = subprocess.run([sys.executable, script], env=env)
        elapsed = time.time() - start

        if result.returncode != 0:
            print(f"\n❌ {name} 실패 (종료 코드: {result.returncode})")
            return False, elapsed, None

        latest = newest_new_file(before, stage_info['output_pattern'])
        if latest:
            size_kb = latest.stat().st_size / 1024
            print(f"\n✅ {name} 완료 ({elapsed:.0f}초)")
            print(f"   📂 생성: {latest.name} ({size_kb:.1f} KB)")
            return True, elapsed, latest

        print(f"\n⚠️  완료됐으나 출력 파일을 못 찾음")
        return False, elapsed, None

    except KeyboardInterrupt:
        print(f"\n\n⛔ 사용자 중단")
        return False, time.time() - start, None
    except Exception as e:
        print(f"\n❌ 예외 발생: {e}")
        return False, time.time() - start, None


def check_prerequisites(markets):
    needed = set()
    for m in markets:
        for s in build_stages(m):
            needed.add(s['script'])
    missing = [s for s in needed if not Path(s).exists()]
    if missing:
        print(f"\n❌ 다음 파일이 없습니다:")
        for f in missing:
            print(f"   • {f}")
        return False
    return True


def check_api_key():
    import os
    if not os.environ.get('DART_API_KEY'):
        print(f"\n⚠️  환경변수 DART_API_KEY가 없습니다.")
        print(f"   • 로컬: export DART_API_KEY='...' 후 재실행")
        print(f"   • GitHub: Secrets에 DART_API_KEY 등록")
        response = input(f"\n계속하시겠습니까? (y/N): ").strip().lower()
        return response == 'y'
    return True


def run_market(market: str):
    """한 시장(kospi/kosdaq)의 3단계 파이프라인 실행."""
    stages = build_stages(market)
    results = []
    for i, stage in enumerate(stages, 1):
        success, elapsed, output = run_stage(stage, i, len(stages))
        results.append({
            'name': stage['name'],
            'success': success,
            'elapsed': elapsed,
            'output': output.name if output else None,
        })
        if not success:
            print(f"\n\n⛔ [{market}] {stage['name']} 실패. 이 시장 중단합니다.")
            return results, False
    return results, True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--market', choices=['kospi', 'kosdaq', 'all'], default='all')
    parser.add_argument('--no-accumulate', action='store_true', help='SQLite 적재 생략')
    args = parser.parse_args()

    markets = ['kospi', 'kosdaq'] if args.market == 'all' else [args.market]

    print(f"\n{'='*72}")
    print(f"🚀  [V2.6] 과매도 종목 발굴 파이프라인 — {', '.join(markets).upper()}")
    print(f"{'='*72}")
    print(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    if not check_prerequisites(markets):
        return
    if not check_api_key():
        return

    total_start = time.time()
    all_results = {}
    all_success = True

    for i, market in enumerate(markets):
        # 두 번째 시장 시작 전 DART 서버 안정화 대기
        # (4스레드 → 2스레드로 줄였어도 누적 호출 부담 완화용)
        if i > 0:
            cooldown = 60
            print(f"\n\n⏸  DART 서버 안정화를 위해 {cooldown}초 대기 중...")
            time.sleep(cooldown)

        print(f"\n\n{'#'*72}")
        print(f"#  🏛  {market.upper()} 시장 시작")
        print(f"{'#'*72}")
        results, market_ok = run_market(market)
        all_results[market] = results
        if not market_ok:
            all_success = False
            # 한 시장 실패해도 다음 시장은 계속 시도

    total_elapsed = time.time() - total_start
    print(f"\n\n{'='*72}")
    print(f"📊  V2.6 파이프라인 실행 요약")
    print(f"{'='*72}")
    for market, results in all_results.items():
        print(f"\n  [{market.upper()}]")
        for r in results:
            status = '✅ 성공' if r['success'] else '❌ 실패'
            mins, secs = divmod(int(r['elapsed']), 60)
            out = f" → {r['output']}" if r['output'] else ''
            print(f"    {status}  {r['name'][:50]:<50} {mins:>2}분 {secs:>2}초{out}")

    # 누적 적재
    if not args.no_accumulate and Path('accumulate_history.py').exists():
        print(f"\n{'='*72}")
        print(f"📦  누적 적재 (SQLite + Parquet)")
        print(f"{'='*72}")
        try:
            rc = subprocess.run([sys.executable, 'accumulate_history.py', '--archive']).returncode
            if rc != 0:
                print(f"⚠️  적재 스크립트가 0이 아닌 코드로 종료: {rc}")
        except Exception as e:
            print(f"⚠️  적재 중 예외 발생: {e}")

    # 대시보드 자동 생성
    if Path('build_dashboard.py').exists():
        print(f"\n{'='*72}")
        print(f"📊  대시보드 생성")
        print(f"{'='*72}")
        try:
            subprocess.run([sys.executable, 'build_dashboard.py'])
        except Exception as e:
            print(f"⚠️  대시보드 생성 실패: {e}")

    # [V2.6 자동화] 총 소요시간을 맨 마지막에 한 줄로 크게 출력
    # 누적 적재/대시보드 생성까지 포함한 전체 시간
    grand_total = time.time() - total_start
    total_hours, rem = divmod(int(grand_total), 3600)
    total_mins, total_secs = divmod(rem, 60)
    if total_hours > 0:
        time_str = f"{total_hours}시간 {total_mins}분 {total_secs}초"
    else:
        time_str = f"{total_mins}분 {total_secs}초"

    print(f"\n{'='*72}")
    print(f"⏱️   총 소요시간: {time_str}   (시작: {datetime.fromtimestamp(total_start).strftime('%H:%M:%S')} → 종료: {datetime.now().strftime('%H:%M:%S')})")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    main()
