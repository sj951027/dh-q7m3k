# 2026-11-07 — 운영 검토 F1·F5·F3 보강: 수급 한쪽만 갱신 감지 · 점검표 되감기 시각 형식 · 산출물 상태 갈래 — **2026.11.2**

## 뭐가
- **F1** `market_flows_obs.py`: `refresh_status(markets)` 순수 함수 — 두 시장 모두 저장했을 때만 `ok`, 한쪽만 `partial`, 없으면 `failed`(종전 `any(ok)` → ok). 자식은 전역 `last_success_at` 을 **두 시장 모두 성공일 때만** 쓰고, 시장별 `last_success_<MK>` 를 따로 남김. `data_health.py`: 시장 수급 갈래에 **시장별 마지막 날짜(parts_last)** 를 모아, 한쪽만 멈추면 `lag`("일부만 갱신 — KOSDAQ 마지막 …").
- **F5** `data_health.py`: 되감기 인자 `YYYYMMDD_HHMM` 을 `fetched_at` 형식(`YYYY-MM-DD HH:MM:59`)으로 바꿔 비교(`_asof_ts`) + `date <= asof` 상한. 종전엔 형식이 달라 **미래 적재분이 과거 조회에 섞였다**(10/30 시점 조회에 11/2 적재분 — 실 DB 재현 테스트 추가).
- **F3** `data_health.py`: 갈래 2개 추가(17→**19**) — `flows_json`(docs/market_flows_obs.json 의 시장별 `data_as_of` + `refresh_status` 가 ok/skipped 아니면 ⚠️ 산출 상태) · `paper_json`(docs/paper_account.json 의 `end`). 새 상태 `state`(⚠️ 산출 상태 줄). `paper_account.py` JSON 쓰기를 임시 파일 → `os.replace` 로(반쪽 JSON 방지).

## 왜
- Codex 운영 검토(`research/handoff/REPLY_20261103_ops_review_1043_1048.md`) 중 5건 가운데 실 DB·합성으로 재현된 F1·F5 와, 입력이 최신이어도 산출 실패를 못 잡던 F3. 적용 순서도 Codex 제안(F1·F5 → F3 → F2·F4) 그대로.

## 어떻게 + 검증
- 테스트: `tests/test_data_health.py` [E] 6체크(시장별 부분 갱신 lag · 둘 다 최신 ok · 시각 변환 · state 경고 · 갈래 19 · **실 DB 되감기 10/30 ≤ 20261030**) · `tests/test_market_flows_obs.py` [D] 3체크. `python -X utf8 tests/run_tests.py` 전체 통과.
- **0-diff(실측)**: 현재 자료로 점검표 재실행 — 기존 17갈래 상태·마지막 날짜 전부 동일(경고 0), 새 2갈래 ok. `market_flows_obs.py --no-fetch` 사본 JSON 의 `markets` 가 11/6 배치 산출과 동일.
- 판정·점수·게이트 무접촉.

## 영향 범위
- 배치: 월요일부터 수급 갱신 줄에 `partial` 이 나올 수 있고, 점검표 19갈래. 텔레그램 ⚠️ 줄에 "산출 상태" 유형 추가. `docs/data_health.json/.md` 갈래 2개 증가.
- 남은 운영 검토: **F2**(보충표에만 있는 날짜가 모의 계좌 달력에 들어옴 — 본표 달력 고정) · **F4**(수급 20일 창에 하루 통째 결손) · 하 3건(F6~F8).
