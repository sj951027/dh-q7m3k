# 2026-08-17 휴장일 1회성 스킵 장치 (skip_once.flag)

## 뭐가
- `run_auto_logged.bat`에 skip_once 블록 추가(ASCII만, 6줄 삽입 + 주석 2줄):
  `skip_once.flag` 파일이 있으면 `logs\auto_run_*_SKIPPED.log` 마커만 남기고
  플래그를 지운 뒤 exit 0. 없으면 기존과 완전 동일 동작.
- 루트에 `skip_once.flag` 생성 → **오늘(8/17 광복절 대체휴일) 밤 자동 실행 1회만 스킵**.

## 왜
- 8/17은 휴장일. run_id 보정에 공휴일 캘린더가 없어(§24 한계) 그대로 돌면
  run_id=20260817 유령 거래일이 적재됨(6/3 선거일 전례: stage1 2,272행).
  안전장치(정적 run 제외·비거래일 앵커 게이트)로 판정은 안 깨지지만,
  60~120분 낭비 실행 + 8/14와 동일 내용 알림이 나감 → 스킵이 깔끔.

## 어떻게 + 검증
- 스킵 조건은 스케줄러 경로(run_auto_logged.bat)에만 존재 — 수동 실행
  (run_manual_logged.bat, run_all_and_diversify.bat 직접 실행)은 영향 없음.
- 플래그는 소비형(1회 후 자삭) → 내일부터 자동 정상. 앞으로 휴장일마다
  루트에 `skip_once.flag` 빈 파일 하나만 만들면 재사용 가능.
- batch 함정 회피: `echo ... %TIME%> file`은 TIME 끝 숫자가 스트림 리다이렉트
  (`5>`)로 오파싱될 수 있어 **리다이렉트 선행형** `>file echo ...`로 작성.
- ASCII-only·CRLF 검증 완료(2026-08-07 인코딩 사건 규칙 준수).
- 오프라인 실행 검증은 불가(Windows cmd 없음) — 로직 단순(if exist/del/exit).
  실측 확인 포인트: 오늘 밤 `logs\auto_run_*_SKIPPED.log` 생성 + flag 소멸 +
  history.db에 run_id=20260817 미적재.

## 영향범위
- **판정·점수 0-diff**: 점수식·적재 로직·판정 도구 무변경. 실행 여부만 제어.
- 8/17은 비거래일이라 관측일 손실도 없음(돌렸어도 정적 run으로 제외됐을 날).
- lv 계열 40거래일 도달: 8/17 휴장 반영 시 ~8/26 저녁 추정(notify_verdict_ready가
  도달 시점 자동 알림 — 별도 조치 불요).
