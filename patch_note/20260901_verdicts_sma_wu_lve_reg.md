# 2026-09-01 — 3차 판정(sm_a·wu_a·wu_b) 확정 + lv_e 등록

## 뭐가
1. **§11 판정 정본 2건**: VERDICT_20260901_sm_a.md(sm_a '노이즈'),
   VERDICT_20260901_wu.md(wu_a·wu_b '역작동(유의)' 기각 — 셋 다 적재 유지·가중 0).
   계산: research/verdict_lowvol_20260829.py(재실행) + research/verdict_wu_20260901.py(신규,
   lowvol 판정 규약 이식 + 분모 사전등록 11/실측 6 병기 + 주블록 감도). 사용자 승인으로 확정.
2. **lv_e 등록**: research/lv_e_wiring_20260829.patch 적용(lowvol_score.py FACTORS to20 +
   MODELS lv_e), checkup.py REG_DATE "lv_e": "20260901"(첫 적재 예정 — 미실행 시 실제 run_id로
   정정), PREREGISTER_lv_e.md 상태 초안→등록. lowvol 분모 10→11.
3. docs/wu.html 경고 배너를 '기각' 라벨로 갱신(표시 조항 — 판정 기준 아님).
4. MODELS_LEDGER.md 3차 판정 섹션 + 현역 표 갱신.
5. 예약 작업 이관: 폴더 미연결로 실패하던 9/11 새 세션 예약 삭제 → 같은 시각(9/11 08:30 KST)
   본 세션 알림으로 대체(sv_a 판정→sv_b 배선은 그 시점).

## 검증
- lv_e spec_hash **1774127f89ef = 사전등록값 일치**. 기존 10모델 0-diff는 8/29 사전검증
  (173,656행 점수 불일치 0) + 오늘 tests/run_tests.py **전체 통과**(동결창·spec_hash 골든 32체크).
- 판정 수치는 docs/leaderboard.json(08-31 파이프라인)의 자동 라벨과 방향 일치 확인.
- **판정·점수 0-diff**: 기존 모델 전부 무변(lv_e는 신규 행만 추가 예정, 다음 파이프라인부터 적재).

## 영향범위
- 다음 파이프라인 실행부터 lv_e 적재 시작(그날이 REG_DATE 실효). lv_e 판정은 40거래일 후(~10월 말).
- lowvol 이후 판정의 Bonferroni 분모 11. wu 트랙 남은 판정: sv_a(~9/10)·le_a·qs_a(~9월 말)·px_a(~10월 초).

## 추가 (같은 날 저녁) — wu 트랙 spec_hash 골든 테스트
- tests/test_wu_score_rules.py 신규(10체크): 6모델 spec_hash 골든(라이브==DB 저장값==
  PREREGISTER 문서값 3중 일치 확인 후 동결), svr5/nh252/mom12 방향 골든(8/29 방향 혼동
  사건 재발 방지), 등록 모델 보존 체크. run_tests.py 등록 → 전체 42체크.
- 목적: 9/11 sv_b 배선 패치(wu_score.py 수정)의 안전망 — 기존 6모델 스펙 불변을 기계 증명.
- 판정·점수 0-diff(테스트 추가만). 전체 테스트 통과 확인.
