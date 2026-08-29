# -*- coding: utf-8 -*-
"""회귀 테스트 일괄 실행 — python tests/run_tests.py
빠른 것(합성)부터 → DB 골든 순. 하나라도 실패하면 종료코드 1(파이프라인 훅으로 쓸 수 있게)."""
import subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
FILES = ["test_lowvol_score_rules.py", "test_leaderboard_frozen.py"]
fail = 0
for f in FILES:
    print(f"━━ {f}")
    r = subprocess.run([sys.executable, str(HERE / f)])
    if r.returncode != 0:
        fail += 1
print("\n" + ("❌ 실패 있음 — 골든을 고치지 말고 원인부터" if fail else "✅ 전체 테스트 통과"))
sys.exit(1 if fail else 0)
