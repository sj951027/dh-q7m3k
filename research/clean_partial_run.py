# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행. 사용자 PC 전용(history.db 수정).
"""clean_partial_run.py — 부분실행(유니버스 붕괴) run 의 행을 지워 '깨끗한 재실행'이 가능하게 한다.

배경: 2026-09-08 FDR StockListing 404 → stage1 75/20행·v3_scores 22행만 동결됨. 이 상태로 같은 날 다시 돌리면
  frozen_at 간격 > 60분이라 leaderboard 이중실행 게이트가 그날을 통째로 제외한다(측정 복구 불가).
  → 재실행 전에 그 run_id 의 행을 지우면 재실행이 '그날의 유일한 실행'이 되어 앵커로 산다.

안전장치: --yes 없으면 삭제 대상 건수만 보여 준다(드라이런). 실행 전 history.db 를 backup/ 에 복사한다.
대상 테이블: stage1_oversold · stage2_filtered · stage3_final · runs · v3_scores · lowvol_scores · wu_scores · large_universe · large_final
  (있는 테이블만, run_id 컬럼 기준). 다른 run_id 행은 절대 건드리지 않는다.
사용:  python research/clean_partial_run.py 20260908          # 드라이런
       python research/clean_partial_run.py 20260908 --yes    # 실제 삭제(백업 후)
       python research/clean_partial_run.py 20260908 --yes --force   # 정상 규모지만 내용이 깨진 run(예: ticker 앞자리 0 유실)
"""
import shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DB = REPO / "history.db"
TABLES = ["stage1_oversold", "stage2_filtered", "stage3_final", "runs", "v3_scores",
          "lowvol_scores", "wu_scores", "large_universe", "large_final"]


def main():
    if len(sys.argv) < 2 or not sys.argv[1].isdigit() or len(sys.argv[1]) != 8:
        print("사용: python research/clean_partial_run.py YYYYMMDD [--yes]"); return 1
    rid = sys.argv[1]; do = "--yes" in sys.argv
    con = sqlite3.connect(str(DB))
    have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    plan = []
    for t in TABLES:
        if t not in have:
            continue
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({t})")]
        if "run_id" not in cols:
            continue
        n = con.execute(f"SELECT COUNT(*) FROM {t} WHERE run_id=?", (rid,)).fetchone()[0]
        plan.append((t, n))
    total = sum(n for _, n in plan)
    print(f"run_id {rid} 삭제 대상:")
    for t, n in plan:
        print(f"   {t:18s} {n:6d}행")
    print(f"   합계 {total}행")
    # 정상 run 을 실수로 지우는 것 방지 — stage1 이 최근 중앙값의 50% 이상이면 '부분실행'이 아니다
    med = con.execute("SELECT COUNT(*) n FROM stage1_oversold GROUP BY run_id ORDER BY run_id DESC LIMIT 20").fetchall()
    med = sorted(x[0] for x in med)[len(med) // 2] if med else 0
    s1 = dict(plan).get("stage1_oversold", 0)
    if med and s1 >= 0.5 * med and "--force" not in sys.argv:
        print(f"   🛑 중단: stage1 {s1}행은 최근 중앙값 {med}의 50% 이상 — 부분실행이 아니라 정상 run 으로 보임. 삭제하지 않음."
              f" (데이터가 깨진 정상 규모 run 을 지우려면 --force)")
        con.close(); return 2
    if not do:
        print("   (드라이런 — 실제 삭제는 --yes)"); con.close(); return 0
    if total == 0:
        print("   지울 행 없음."); con.close(); return 0
    bdir = REPO / "backup"; bdir.mkdir(exist_ok=True)
    bk = bdir / f"history_before_clean_{rid}_{datetime.now():%Y%m%d_%H%M%S}.db"
    con.close(); shutil.copy2(DB, bk); print(f"   💾 백업: {bk.name}")
    con = sqlite3.connect(str(DB))
    for t, n in plan:
        if n:
            con.execute(f"DELETE FROM {t} WHERE run_id=?", (rid,))
    con.commit(); con.close()
    print(f"   ✅ run_id {rid} {total}행 삭제 완료. 이제 배치를 다시 돌리면 그날의 유일한 실행이 된다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
