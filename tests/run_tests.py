# -*- coding: utf-8 -*-
"""회귀 테스트 일괄 실행 — python tests/run_tests.py
빠른 것(합성)부터 → DB 골든 순. 하나라도 실패하면 종료코드 1(파이프라인 훅으로 쓸 수 있게)."""
import os, subprocess, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 부모 프로세스의 ✅/━━ 출력도 cp949 콘솔에서 안 깨지게
except Exception:
    pass
from pathlib import Path
HERE = Path(__file__).resolve().parent
FILES = ["test_index_source.py", "test_extra_ohlcv_targets.py", "test_kis_flows_targets.py","test_earnings_incr.py", "test_close_revision_detail.py", "test_fin_gap_warning.py", "test_missed_run_warning.py", "test_data_health.py","test_earnings_flag.py", "test_telegram_scoreboard.py", "test_regime_ad.py", "test_buy_context.py", "test_paper_engine.py", "test_cross_sim_hold.py", "test_shadow_ops_rules.py", "test_lowvol_score_rules.py", "test_wu_score_rules.py", "test_lead_observe_rules.py", "test_v3_models_rules.py", "test_v32a_page_rules.py", "test_notify_verdict_rules.py", "test_leaderboard_frozen.py"]
fail = 0
for f in FILES:
    print(f"━━ {f}")
    r = subprocess.run([sys.executable, str(HERE / f)], env={**os.environ, "PYTHONIOENCODING": "utf-8"})   # cp949 콘솔에서 ✓ 출력이 깨져 전 테스트가 실패하던 것 방지
    if r.returncode != 0:
        fail += 1
print("\n" + ("❌ 실패 있음 — 골든을 고치지 말고 원인부터" if fail else "✅ 전체 테스트 통과"))
sys.exit(1 if fail else 0)
