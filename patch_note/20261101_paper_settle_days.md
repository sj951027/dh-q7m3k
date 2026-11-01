# 2026.10.48 — 모의 계좌: 매도대금 T+2 결제 감도 `total_ret_settle2` (J11, 사용자 승인 11/1) (2026-11-01)

## 그래서 뭐가 바뀌나
- `paper_engine.simulate(..., settle_days=0)` 인자 추가: 청산 대금이 `settle_days` 거래일 뒤에 현금이 된다(그 전엔 '결제 대기' — NAV 엔 포함, 신규 매수엔 못 씀). **기본 0 = 종전과 완전 동일**(테스트로 확인).
- `paper_account`: 모든 계좌 요약에 **`total_ret_settle2`**(settle_days = `pe.SETTLE_DAYS` = 2) 추가, 출력 줄 `T+2:` , JSON `sens.settle_days`·note. 주 계좌 규칙 무변경.
- 실측(8/10~10/30): v30 −7.59 → −7.59 · lv_b −7.68 → −7.68 · 스위치 −7.95 → −7.95(현금 충분) · **le_a −20.10 → −19.23 · sv_a −11.86 → −11.41**(현금 바닥 계좌는 결제 전 돈으로 못 사 덜 투자 → 이번 창에선 덜 잃음) · 시장 B0 −10.18 → −9.76 · 무작위 B3 −10.36 → −9.96.

## 왜
- `research/RESEARCH_ops_realism_20261101.md` §2: le_a·sv_a 는 10/13 부터 진입의 64~68% 가 결제 전 돈이었다. 판정 대상 모델의 돈 기준 비교에 각주가 필요 → 숫자로 병기.

## 검증
- 기존 키·NAV **0-diff**(스크래치 산출 ↔ docs, 최대 차 2e-14) · `tests/test_paper_account_v2.py` I절 5체크(settle 0 = 기본, T+2 땐 결제 대기 중 매수 불가·NAV 보존) · `tests/run_tests.py` 전체 통과 · `docs/paper_account.json` 재생성.
- **판정·점수·게이트 0-diff**(history.db 읽기만). 표시 무변경(리더보드는 이 키를 아직 안 읽음).
