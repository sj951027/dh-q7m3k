# 2026-09-17 — §11 판정: mom_b 역작동(유의)·은퇴 · qs_a 노이즈 (2026.09.13 · 판정 정본 VERDICT_20260917_mom_b_qs_a.md · 다른 모델 점수 0-diff)

## 그래서 뭐가 바뀌나
- mom_b: 리더보드 "역작동(유의)·은퇴(9/17 정본)" 배지, 은퇴 목록으로 이동. **내일 배치부터 mom_b 새 행 적재 중지**(`lowvol_score.py RETIRED`), 기존 행·분모(11) 보존.
- qs_a: "노이즈(9/17 정본)" 배지. 적재 유지·가중 0. `docs/qs.html` 제목 "판정 완료: 노이즈(9/17 정본)".
- 텔레그램 SEALED 맵도 동일(누락돼 있던 sv_a·le_a 9/13 판정도 함께 추가).

## 왜 (실측)
- mom_b h20 IC −0.092, iid·Bonferroni(/11)·주블록 CI 전부 음수, 주별 양 0%, 상승·하락 국면 모두 음수. qs_a −0.056, CI 0 걸침, in-sample 우위 미재현, 상위10 초과 −1.0%p.
- 확정 전 점검: Codex 독립 구현으로 IC 재계산 → 차이 0. 돈 관점(상위 10% vs 하위 10% 20일): mom_b −5.2%p, qs_a −7.5%p, 둘 다 CI 음수.

## 어떻게 / 검증
- 갱신 파일: VERDICT 정본 · MODELS_LEDGER(본표 2행·은퇴표 1행) · docs/models_registry.json(sealed 2·retired 1) · docs/leaderboard.html 인라인 맵 · notify_telegram.py SEALED_V2/RETIRED_FALLBACK_V2 · docs/qs.html · lowvol_score.py RETIRED.
- `python tests/run_tests.py` 전체 통과(골든 불변 = 다른 모델 0-diff). 재현: `python research/verdict_mom_b_qs_a_prep_20260917.py`.
