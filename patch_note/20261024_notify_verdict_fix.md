# 2026.10.39 — 판정 도달 알림: 셈을 판정 기준(유효 앵커)과 같게 · 전송 성공 때만 '완료' 기록 (2026-10-24)

## 그래서 뭐가 바뀌나
- '판정 가능 도달' 텔레그램 알림이 **판정과 같은 날**에 온다(전엔 전 모델이 하루 늦게 셌음). lv_e 는 현재 유효 앵커 33 → **11/3(화) 배치에서 40** 도달 예정.
- 텔레그램 전송이 실패하면 다음 배치에서 **다시 시도**한다(전엔 실패해도 '알림 완료'로 적어 다시 안 보냄).

## 왜 바꿨나
- Codex 재점검(`research/handoff/REPLY_20261024_v32a_review_fixes.md`): R1 알림은 `run_id > 등록일`·고정 GATES 로 세어 leaderboard 의 유효 앵커(등록일 포함·게이트 매일 계산·주말 중복 제거)보다 하루 적음(실측 lv_e 32↔33, sv_b 25↔26, px_a 49↔50, qs_a 61↔62) · R2 `send_telegram()` 반환값을 안 보고 상태 기록. 둘 다 Claude 재현.

## 어떻게
- `notify_verdict_ready.py`: `gate_ctx()` 가 `leaderboard.load_ohlcv`·`build_gates` 로 (거래일 인덱스, 제외 run) 을 만들고 `oos_days(con, m, ctx)` 가 `leaderboard.dedupe_by_anchor(…, reg=등록일)` 로 센다. 준비 실패 시 옛 셈(이제 `>=` 로 등록일 포함). 전송 결과가 False 면 상태 파일을 안 쓰고 경고 한 줄.
- 새 테스트 `tests/test_notify_verdict_rules.py`(합성 7개: 등록일 포함·등록 전 제외·주말 중복 제거·게이트 제외 · 옛 셈 등록일 포함 · 등록 대상·트랙 · 전송 실패면 상태 안 씀 · 성공이면 씀 · 이미 알린 모델 재전송 없음) → `run_tests.py`.
- **검증**: 실DB 대조 lv_e 33 · sv_b 26 · px_a 50 · qs_a 62 · v30 88 = leaderboard 유효 앵커 · `--dry-run` 신규 알림 없음 · 실제 `verdict_notified.json` 미변경(10/12 그대로) · `python tests/run_tests.py` 전체 통과.

## 영향 범위
- 알림 시점·재시도만. **점수·판정·게이트·표시 0-diff**(leaderboard 함수는 읽기만).
