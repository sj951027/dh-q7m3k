# 2026-11-07 — 운영 검토 F2·F4 보강: 모의 계좌 달력을 본표로 고정 · 수급 창을 거래일 달력으로 검사 — **2026.11.3**

## 뭐가
- **F2** `paper_engine.restrict_to_calendar(df, calendar)`(순수 함수) + `paper_account.load_prices`: 보충표(daily_ohlcv_extra) 행 중 **본표 거래일에 없는 날짜**는 버리고 로그 한 줄(`⚠ 보충표 행 n개가 본표 거래일 밖 날짜라 제외`). 종가 표의 날짜축 = 본표 달력.
- **F4** `market_flows_obs.summarize(net, T, calendar=None)`: 달력이 주어지면 창 = 마지막 날짜 이하 **달력의 마지막 w 거래일**, 하나라도 없으면 `w{w}=None` + `w{w}_missing`(빠진 날짜 최대 5). `build_json` 은 시세 본표(ohlcv.db) 거래일을 달력으로 읽어 넘기고(못 읽으면 종전 행 기준·그 사실을 JSON `calendar` 에 적음).

## 왜
- Codex 운영 검토 F2(합성 재현: 본표 10/30·보충표 토요일 10/31 → 달력에 10/31 이 들어가 본표 종목이 '끊김'으로 잡히고 모든 계좌의 거래일이 바뀜) · F4(합성 재현: 20기준일 중 하루 통째 삭제 → 결측 셀이 없어 19일 합을 w20 으로 반환).

## 어떻게 + 검증
- 테스트: `tests/test_paper_account_v2.py` [K] 2체크 · `tests/test_market_flows_obs.py` [E] 4체크(달력 전부 있으면 같은 값 · 창 안 하루 결손 → None+기록 · 달력 없이 호환 · 창 밖 결손 무영향). 전체 테스트 통과.
- **0-diff(실측)**: `paper_account.py --out` 사본 vs 11/7 재생성본 — 14계좌 NAV·요약 전부 동일(현재 보충표에 본표 밖 날짜 0행 — Codex 실측과 일치). `market_flows_obs.py --no-fetch` 사본 JSON 의 `markets` 가 기존과 동일(현재 창에 결손일 없음).
- 판정·점수·게이트 무접촉.

## 영향 범위
- 앞으로 보충표에 주말·본표 밖 날짜가 들어와도 모의 계좌 달력이 흔들리지 않음. 수급 JSON 은 창 안 결손일이 생기면 null(+빠진 날짜)로 나와 점검표 `수급 산출(JSON)`·표시에서 드러남.
- 남은 운영 검토: 하 3건(F6 수량·금액 날짜 불일치 · F7 수량 정정 이력 · F8 T+2 구버전 대조) — 다음 Codex 중간점검 뒤.
