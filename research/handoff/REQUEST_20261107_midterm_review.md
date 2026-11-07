# REQUEST — 중간점검(읽기 전용): 11/4~11/7 에 바뀐 것 전부를 한 번에 검토 — 판정 정본·관측 계약·모의 계좌 14장·운영 보강 .11.1~.11.3 (2026-11-07)

> 보내는 사람: 사용자(Claude 초안). 받는 사람: Codex. **코드·docs·DB 수정 없음**, DB 는 `mode=ro`, 배치·수집기 실행 금지, 평일 20:10~22:30 실행 금지. 답 하나: `research/handoff/REPLY_20261107_midterm_review.md`. 시간·토큰 넉넉히.
> 왜: 네 11/3 운영 검토(F1~F8)와 11/4 진화 검토 2차 뒤 Claude 가 나흘 동안 많이 바꿨다. 바꾼 것이 **네 지적을 제대로 고쳤는지, 새 구멍을 만들지 않았는지, 관측 계약이 모순 없이 적혔는지** 한 번에 보자. 좋다/나쁘다가 아니라 **허점·모순·누락**만, 파일:줄과 재현법으로.

## 0. 읽을 것(이 순서)
1. 정본 셋: `VERDICT_20261104_lv_e.md`(정본 '유의') · `research/OBSERVATION_CONTRACT_20261104.md`(11/7 승인) · `VERDICT_RULES.md` §8(새 절).
2. 패치노트 3건: `patch_note/20261107_paper_mix_account.md`(2026.11.1) · `20261107_health_flows_partial.md`(2026.11.2) · `20261107_calendar_window.md`(2026.11.3) — 그리고 그 코드: `paper_engine.py`(`mix_picks`·`restrict_to_calendar`) · `paper_account.py`(MIX_ID·load_prices·JSON 원자적 쓰기) · `market_flows_obs.py`(`refresh_status`·`summarize(calendar)`·`build_json`) · `data_health.py`(`parts_last`·`_asof_ts`·`flows_json`/`paper_json`·`state`) · `tests/test_paper_account_v2.py`([J][K]) · `tests/test_market_flows_obs.py`([D][E]) · `tests/test_data_health.py`([E]).
3. 네 답 2건과 Claude 의 합치기: `REPLY_20261103_ops_review_1043_1048.md` · `REPLY_20261104_evolution_round2.md` · `CLAUDE_20261104_evolution_round2_merge.md`.
4. 지도 `research/IDEA_MAP_20261030.md` §13·§13-1·§13-2 · `MODELS_LEDGER.md` 상단 메모와 lv_e·lv_b 행 · `worklog/2026-11-07_observation_contract_mix.md`.

## 1. 묻는 것 (각각 허점 → 파일:줄 → 재현/검증 한 줄 → 심각도 상/중/하)
1. **네 F1~F5 지적이 닫혔나**: 각 항목에 대해 "닫힘 / 부분 / 안 닫힘"과 근거. 특히 ① F1 — `refresh_status` 가 partial 일 때 `last_success_at` 미갱신 + 점검표 `parts_last` 로 한쪽 정지를 잡는 경로에 빈틈이 남나(예: 두 시장 모두 **같은 날** 멈추면?) ② F5 — `_asof_ts` 의 `:59` 초 처리·`date <= asof` 상한이 다른 되감기 갈래(earn_fetch 등)와 일관되나 ③ F3 — `flows_json`·`paper_json` 갈래가 **배치 순서**(수급 66행 → 모의 계좌 128행 → 점검표 129행)에서 실제로 같은 배치 산출을 보는지, 모의 계좌 단계가 실패해 JSON 이 전날 것이면 lag 가 뜨는지 ④ F2 — 본표 달력 고정이 **보충표만의 종목**(136)의 만기·청산에 부작용이 없나(본표에 없는 날짜의 보충표 가격을 버리면 그 종목의 마지막 가격·끊김 판정이 어떻게 바뀌나) ⑤ F4 — `build_json` 이 ohlcv.db 를 못 읽으면 조용히 행 기준으로 떨어지는데 그 사실이 JSON `calendar` 문구 외에 점검표에도 드러나야 하나.
2. **정적 반반 계좌 `mix_v30_lvb_5050`**: "두 목록을 이어 붙여 예산을 목록 길이로 나눈다 = 반반"이 맞나 — 두 목록 길이가 다를 때(한 시장만 10개, 중복 제거 뒤 19개 등) 실제 배분 비율은 얼마가 되나. 이것이 관측 계약 §3 "같은 투입액 통제"로 쓰기에 충분한지, 아니면 '목록별 예산 절반'을 엔진에 명시해야 하나(코드 변경 제안만, 적용은 Claude).
3. **관측 계약의 모순 찾기**: §1 "최대 3창"과 §3 lv_e 2차 창 시작 20261104 run · 결정 ≈12/30 이 리더보드 oos_days 셈법과 맞나(결손일 처리) · "승격 결정 규칙"의 돈 조건을 신규 후보에만 적용한다는 문장이 §13 2단계 ①·②와 어긋나는 곳 · E3 전향 시작 20261109 run 과 비교군 3개(v30·lv_b·mix)의 **같은 투입액** 주장이 실제 엔진에서 성립하는지(슬롯 40·NAV/40 규칙).
4. **lv_e 판정문 §4·각주 ④ 의 네 답 인용이 정확한가**(자리바꿈 통과율 조건 묶음·결손일 문구·656행 불일치 언급) — 틀린 인용이 있으면 파일:줄.
5. **놓친 것 한 가지**: 위 네 가지 밖에서 이번 나흘 변경이 만든 **가장 위험한 새 구멍** 하나와 고치는 법 한 줄.

## 2. 답 양식
- 표 하나(항목 · 상태(닫힘/부분/안 닫힘/새 구멍) · 파일:줄 · 재현 또는 검증 · 심각도 · 고치는 제안 한 줄) + 끝에 핵심 5줄. 재현 가능한 것은 합성 입력으로(실 DB 쓰기 금지). 패치는 만들지 마라 — Claude 가 0-diff 보이고 사용자 승인 뒤 적용한다.
