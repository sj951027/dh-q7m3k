# [2026.08.2] 2026-08-12 — [사건] lowvol 게이트 오탐·freeze 침묵 실패 수정 + 6일 유실 복구

## 그래서 뭐가 바뀌나
- lowvol_scores 적재가 8/03에서 멈춰 있던 것(6 run 유실: 7/23, 8/04~8/10)이 복구되고,
  v3_scores의 8/10 공백도 채워짐. lv_b 판정 시계 정상화.
- 텔레그램 관측 현황에 uni(유니버스 크기) 병기 — 표본 마름을 실시간 인지.
- 수동/자동 실행용 로그 래퍼 신설: run_manual_logged.bat / run_auto_logged.bat
  (날짜별 logs\*.log, stderr 포함 — 창을 닫아도 로그 보존).

## 왜 바꿨나 (원인 분석)
1. **lowvol_score.py 완전성 게이트 오탐**: "stage3 행수 < 전체 중앙값 50%면 부분실행 의심 제외"
   규칙이, 약세장으로 stage3가 실제 축소(중앙값 1,226 → 100대)되자 정상 run을 연속 제외.
   리더보드가 8/09 §28-2에서 고친 것과 동일 유형의 버그가 이 스크립트에 남아 있었음.
2. **freeze_scores.py NameError 즉사**: 8/09 RETIRED 제외 패치가 `v3.RETIRED`를 참조하는데
   `import v3_rescore as v3` 누락. 에러가 stderr로 가서 auto_run.log(stdout만)에 안 남아
   "종료 코드 1, 0초, 무출력"의 침묵 실패가 됨.

## 어떻게
- lowvol_score.py: 게이트를 stage1 행수 기준으로 교정(파이프라인 완주 여부는 stage1이 판정).
  진짜 부분실행(20260608)은 계속 제외됨을 전/후 비교로 확인 후 사용자 승인, 적용.
- freeze_scores.py: import 추가(+부재 시 RETIRED=set() 폴백).
- 검증: 사본 DB에서 백필 → 기존 157,027행 완전 0-diff + 복구 6 run만 추가 확인 → 실DB 백업
  (sqlite backup API) 후 반영 → PRAGMA quick_check ok. 다음날(8/12 저녁) 실운영 로그로 재확인.
- notify_telegram.py: uni 병기(모델별 최신 run 행수, 이중 try/except 비치명).

## 영향 범위
- **판정 재료 복구** — lv 계열 OOS가 실제 이력대로 복원(조작 아님·append-only).
  점수식 무변경. 게이트 교정은 §28-2와 동일 원리의 버그 수정.
- 교훈: 비치명 단계의 침묵 실패는 로그에 stderr까지 남겨야 잡힌다. 이후 스케줄러 명령에
  2>&1이 이미 있었음을 확인(8/14) — 래퍼는 날짜별 이력 보존용으로 유지.
