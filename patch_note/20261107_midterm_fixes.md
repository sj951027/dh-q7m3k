# 2026-11-07 — Codex 중간점검 반영: 반반 계좌 가중치 · 수급 상태 날짜 일치·창 합산 · 점검표 산출 상태 · 돈 관측표 결손 처리 — **2026.11.4**

## 뭐가
- **M1** `paper_engine.mix_picks` → `{date: {ticker: 가중치}}`(목록별 예산 절반 고정: 0.5/nA + 0.5/nB, 중복 합산). `simulate` 가 dict 목록이면 `budget × 가중치`, list 면 **종전 `budget / len` 그대로**(곱셈으로 바꾸면 부동소수점 끝자리가 달라져 0-diff 가 깨짐 — 실측 뒤 되돌림). 테스트 J 8체크(20:10 반례·중복·3:1·list 0-diff).
- **F1 잔여** `market_flows_obs.refresh_status`: 두 시장 ok **이고 마지막 날짜가 같을 때만** ok, 다르면 partial(테스트 2).
- **F4 잔여** `summarize(calendar, required_cols)`: 달력 날짜 **행만** 합산(달력 밖 행 배제) · 필수 투자자 열 누락이면 None + 열 이름. `build_json` 은 `required_cols=DETAIL`. `data_health` 는 JSON `calendar` 가 "달력 없음"이면 `state`.
- **F3 잔여** `data_health` paper_json 갈래: 계좌 0장 · 생성일 < 기준일 → `state`(테스트).
- **N1** `research/verdict_lv_e_20261104.py` ⑩ 돈 관측표: 만기 가격 없는 종목은 **마지막 유효 종가**로 청산(dropna 로 손실 종목이 사라지던 것) — Codex 합성 사례 −21.33%p 재현 일치. 진입일 가격 없는 종목만 제외.

## 왜
- `research/handoff/REPLY_20261107_midterm_review.md`(Codex, HEAD 3268d9b 검토): 새 구멍 상 3(M1·C4·N1) + F1~F4 잔여. 처리 기록 `handoff/CLAUDE_20261107_midterm_review_note.md`.

## 어떻게 + 검증
- 테스트: 3파일 +12체크 · `python -X utf8 tests/run_tests.py` 전체 통과.
- **0-diff(실측)**: `paper_account.py --out` 사본 vs 11/7 11:18 산출 — 기존 **13장 NAV·요약 전부 동일**, `mix_v30_lvb_5050` 만 설계대로 변함(−8.31 → −8.2%). 수급 JSON `markets` 는 달력에 결손·누락 열이 없어 동일. 실제 산출물 재생성(12:26, 14장).
- 판정·점수·게이트 무접촉(판정 스크립트 ⑩ 은 라벨 아님).

## 영향 범위
- 문서 교정 같이: 관측 계약(C1~C6·M2·C4) · VERDICT_RULES §8 · `VERDICT_20261104_lv_e.md`(V1~V3) · 원장(lv_e 11/11 승격 재질문 삭제). 남은 것: 점검표 '시장당 12행' 검사 · 본표 결손일 때 모의 계좌 단계 보류 게이트(로드맵) · 배치 ID 대조(돈 장부 설계) · 656행 원인 감사.
