# -*- coding: utf-8 -*-
"""
v3_daily.py — 자동 실행용 (조용한 데이터 누적 전용)
====================================================
기존 스크리너(run_all_v2_6.py + diversify_picks.py)가 끝난 뒤 호출한다.
하는 일:
  1) 최신 run_id 를 history.db 에서 읽는다
  2) fetch_valuation.py 로 그날 PBR/PER/배당을 받는다 (네트워크, 실패해도 계속)
  3) v3_rescore.py --quiet 로 재점수화 → v3_archive/ 에 run_id별로 영구 저장

의도적으로 하지 않는 것:
  * BUY/WAIT 리스트를 화면/대시보드에 노출하지 않음 (검증 전 과신 방지)
  * docs/ 에 쓰지 않음 (--docs 안 줌)
  * 백테스트를 매일 돌리지 않음 (v3_backtest.py 는 주 1회 수동 권장)

이 스크립트의 목적은 '오늘의 추천'이 아니라
'검증에 필요한 히스토리를 매일 빠짐없이 쌓는 것'이다.

연결 방법:
  run_and_diversify.py 의 diversify 호출 직후에 한 줄:
      subprocess.run([sys.executable, "v3_daily.py"], cwd=HERE)
  또는 run_all_and_diversify.bat 의 python 실행 줄 아래에:
      python v3_daily.py
"""
import os
import sys
import sqlite3
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "history.db"


def latest_run_id():
    con = sqlite3.connect(DB)
    try:
        rid = con.execute(
            "SELECT MAX(run_id) FROM stage3_final").fetchone()[0]
    finally:
        con.close()
    return str(rid)


def run(cmd, **kw):
    """서브프로세스 실행. 실패해도 예외로 죽지 않고 returncode만 반환."""
    print(">>", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(HERE), **kw).returncode


def main():
    if not DB.exists():
        print("[v3_daily] history.db 없음 — 스크리너를 먼저 실행하세요.")
        return 1
    run_id = latest_run_id()
    print(f"[v3_daily] 대상 run_id = {run_id}")

    # 1) 밸류에이션 (네트워크). pykrx 미설치/네트워크 실패해도 계속 진행.
    rc = run([sys.executable, "fetch_valuation.py", "--date", run_id])
    if rc != 0:
        print("[v3_daily] 밸류에이션 수집 실패/건너뜀 — value_score 없이 진행")

    # 2) 조용한 재점수화 + 보관 폴더 누적 (대시보드 노출 안 함)
    rc = run([sys.executable, "v3_rescore.py",
              "--run_id", run_id, "--quiet"])
    if rc != 0:
        print("[v3_daily] 재점수화 실패")
        return rc

    print(f"[v3_daily] 완료. 결과는 v3_archive/ 에 누적됨 (화면/대시보드 노출 없음).")
    print("           검증은 주 1회 정도  python v3_backtest.py  로 직접 확인.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
