# bigwinners_20260924 — 재현 방법 (읽기 전용)
1. `python research/fullscan_20260903/step0_panel.py research/bigwinners_20260924/panel.npz` (ohlcv.db ro → 패널 캐시, ~12초, git 제외 대상)
2. `python research/bigwinners_20260924/bigwin.py` → out_bw/base_rates·single_lifts·decile_ev·combos·persistence·anatomy_h120
3. `python research/bigwinners_20260924/bigwin2.py` → rule_deciles·monthly_topN(_summary)·combos_cold·winner_episodes_h120
4. `python research/bigwinners_20260924/bigwin3.py` → r1_ablation·r1_nonoverlap_h*·r1_monthly_h120·r1_current_top20·summary3.txt
- names.csv 는 history.db stage1 의 ticker→name 스냅샷(2026-09-24). 보고서: ../RESEARCH_bigwinners_20260924.md
5. bigwin4_causal.py → out_bw/r1_causal_recheck.csv (정오표 ①⑤⑥ 정본 — 미래 필터 없음)
6. angles.py → out_bw/angles_*.csv, angles_log.txt (관점 7종, RESEARCH_angles_20260924.md)
