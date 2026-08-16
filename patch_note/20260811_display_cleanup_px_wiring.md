# [2026.08.1] 2026-08-11 — 표시 정리 · px_a 관측 페이지 · lowvol 신고가 필터

## 그래서 뭐가 바뀌나
- 텔레그램: 대시보드·테스트 링크 4종(ls_t1·wu_a·mom_a·qs_a) 제거, '모델 관측 현황' 헤더 제거,
  리더보드 링크를 제목 바로 아래로. 필터 링크에 "(챔피언 v30 기준)" 명시.
- filter.html 제목·부제에 챔피언 v30 명시(모델 v30 ↔ 엔진 V3.0 구분).
- leaderboard.html 모델 칸이 각 모델 페이지 링크로(페이지 실존 모델만).
- px_a 관측 페이지 신설: docs/px.html + 파이프라인 2.89c(build_wu_filter --model px_a).
- lowvol.html에 "신고가 근접 ⅓" 토글 필터(그날 분포 상위 1/3 — 고정 임계값 없음).

## 왜 바꿨나
- 사용자 결정(링크 정리·v30 명시). px_a는 등록(8/10) 직후 열람 수단 부재.
- 신고가 근접은 같은 날 lv_b 조건부 요인 탐색(research/RESEARCH_lvb_conditional_20260811.md)에서
  A·B 표본 모두 방향 일관된 유일 기움(nh252)이라 참고 필터로만 노출(검증 전 가설 명시).

## 어떻게
- notify_telegram.py(주석 보존 방식 비활성화), docs/filter.html(3줄), docs/leaderboard.html
  (MODEL_PAGES+mlink), docs/px.html(qs.html 기반, PREREGISTER_px_a 수치로 배너 재작성),
  run_and_diversify.py(2.89c), .gitignore(/latest_px.csv), docs/lowvol.html(nh3rd 필터).
- 검증: py_compile, 메시지 실렌더(태그 짝·길이), JS node --check, px_a CSV 실생성(1,072종목),
  필터 컷 실데이터 확인(KOSPI 139→47).

## 영향 범위
- 판정·점수 0-diff — 전부 표시·관측 전용. px_a 표시 배선은 PREREGISTER의 "표시 없음" 기술과
  어긋나지만 표시는 판정 기준이 아님(§ 불변 규칙).
