# 2026-09-16 — 모의계좌(cross_sim) 계산 오류 확인 → 돈 표·텔레그램 💰 줄 보류 (2026.09.11 · 판정·점수 0-diff)

## 그래서 뭐가 바뀌나
- 텔레그램 💰 줄이 숫자 대신 "계산 오류 확인 — 정정 전까지 표시 보류" 한 줄로 나간다(`notify_telegram.py` `MONEY_HOLD=True`).
- 리더보드 ① 돈 표 위에 빨간 경고 배너("매수 전 하루 수익 포함 — 참고 금지").
- 수치 자체(cross_sim.json)는 아직 그대로 — 정정은 별도 패치.

## 왜 (외부 검토 → 코드·재계산 실측)
- `build_cross_sim.py daily_series` 가 신호일 t 의 상위20에 **t+1 일간수익**을 적용(문서상 진입은 t+1 종가 → 첫 수익은 t+2). 결측일엔 수익률을 ffill. `model_race.py` 동일.
- 크기(읽기 전용 재계산, research/RESEARCH_cross_sim_entry_lag_20260916.md): lv_b 7/02~ +17.5→+6.9%, mom_a 8/10~ +12.0→−7.1%, 최근 20일 전 모델 하락. §11 IC·exc20(leaderboard.py, ENTRY_LAG=1 → close[t+1] 진입)은 무관.

## 정정 범위(합의, 다음 패치)
보유 상태 기준 시뮬레이션(t+1 종가 교체·t→t+1 수익은 기존 보유 귀속·신호 없는 날 보유 유지·결측 규칙 명시·미실현 구간 제외) · 재현 테스트 5건 · 전후 표 3단계(기존→지연만→결측까지) · model_race.py · 관련 서술 정정.

## 검증
- `build_message()` 미발송 프리뷰: 💰 숫자 없음, 보류 줄 표시. py_compile OK. 점수·판정·DB 무변경.

## 같은 날 추가 (19:3x, 배치 전)
- `notify_weekly.py`: 주간 리캡 "이번 주 성적" 줄도 같은 보류(`MONEY_HOLD`). `--dry-run` 확인.
- `fetch_consensus.py`: 수집 실패 감지 — 커버리지 20% 미만 또는 0행이면 저장하지 않고 종료 코드 1(배치 [WARN]). 평소 커버리지 ~86%.
- `ohlcv.db consensus_daily` 20260912 스냅샷(2,520행 전부 None) 삭제 — 백업 `research/consensus_20260912_failed_snapshot.csv`. 실패 스냅샷이 '무커버리지'로 분석되는 것 방지.
- `PREREGISTER_ops_adoption.md`(미등록 초안): 관찰 시작일 "20260915" → "등록·동결 완료일 다음 거래일"(소급 금지).
