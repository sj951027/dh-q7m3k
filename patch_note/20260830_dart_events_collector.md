# 2026-08-30 — DART 공시 이벤트 수집기 신설 (관측 축적)

## 뭐가
- `dart_events.py` 신규: opendart list.json(주요사항보고 B, 유가/코스닥)에서
  유상증자·유무상혼합·무상증자·CB/BW/EB·감자·주식소각·자사주 취득/처분 공시를
  ohlcv.db `dart_events`(rcept_no PK) 에 증분 적재. `--backfill YYYYMMDD` 소급 지원.
- `run_and_diversify.py` 2.896단계 추가(2.895 밸류 적재 다음): 비치명, 스크립트 없으면 생략.

## 왜
research/RESEARCH_feasibility_sector_dart_20260830.md 실측 — 희석 이벤트(주식수 증가)가
과매도 유니버스 진입 종목의 87%에 걸리고 ex_h20 −9~−17%p(CI 0 제외). 유형 구분·정확한
공시일·예고 공시(결정→상장 수 주 선행)는 DART 만 제공. 사용자 승인 2026-08-30.

## 어떻게 + 검증
- 순수 축적: 점수·판정·표시 어디에도 미연결 → **판정·점수 0-diff (by construction)**.
  활용(유형별 플래그 가중치 0 관측 적재·h20/h60 검증)은 판정 시즌 후 별도 결정.
- 오프라인 테스트(가짜 응답, 네트워크 0): 유형 분류(유무상 우선순위 포함)·비상장 제외·
  관심 외 스킵·ticker zfill(6)·페이징(Y 2p+K 013)·재실행 중복 0건·이상 status 예외 — ALL PASS.
- ast 구문 검사 2파일 통과. tests/run_tests.py 통과(동결 골든 무변).
- rate: 호출 간 0.25s, pblntf_ty=B 한정이라 증분 하루 수십 건 수준(일 한도 20,000 대비 미미).

## 영향범위
- 다음 .bat 실행부터 dart_events 테이블 생성·증분 적재(첫 실행은 최근 30일).
- 소급은 수동 1회: `python dart_events.py --backfill 20230601` (ohlcv 가격 이력 시작점).
- 백업: ohlcv.db 소속이라 주간 full 백업에 자동 포함(core 모드 목록엔 미추가 —
  DART 소급 조회로 재생성 가능한 데이터라 '재생성 불가' 기준에 해당 안 함).
