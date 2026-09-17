# TASK — 모델 페이지에 '지난 날짜 리스트' 탭 (2026-09-17 사용자 결정, 다음 세션 착수)

## 요구
- 모델 페이지(먼저 `docs/lowvol.html` = lv_b, 다음 `docs/filter.html` = v30 코스피/코스닥, 그 뒤 sv·px)에 날짜 탭.
- 오늘 탭 = 지금 그대로(CSV·필터·정렬). 과거 탭 = 단순 표: 그날 순위 · 종목 · 코드 · 점수 · 등급/버킷 · **그날 종가→오늘 종가 등락%** · 오늘 순위(있으면).
- 데이터 **10거래일**(사용자 확정), 화면은 기본 탭 3개(오늘·어제·그제) + "더 보기"로 나머지 7일.
- 과거 탭은 **당시 동결 점수**(history.db)로만 만든다 — 사후 정정과 무관한 '그날 화면' 기록.

## 데이터 (읽기 전용 → docs JSON)
- 새 스크립트 `build_daily_lists.py`(루트, 관측·표시 전용, 점수/판정 코드 미접촉):
  - 입력: history.db `v3_scores`(v30: final_score_v3·grade·bucket) · `lowvol_scores`(lv_b) · `wu_scores`(sv_a·px_a); 종목명·시장은 같은 run 의 `stage3_final`(9/17 실측 lv_b 235종목 이름 누락 0), 없으면 `../dh-q7m3k-data/listing_cache.json`.
  - 가격: ohlcv.db `daily_ohlcv.close` — 그날(run_id 거래일) 종가와 최신 종가 → 등락%.
  - run_id → 거래일 매핑은 leaderboard.py `anchor`/`dedupe_by_anchor` 규약(비거래일 run 은 직전 거래일, 게이트 run 제외).
  - 출력: `docs/hist/{model}.json` = {"model","asof","days":[{"run_id","date","rows":[{"rank","ticker","name","market","score","grade","bucket","px_then","px_now","chg_pct","rank_today"}...]}]} · 시장별 상위 50 · 최근 10거래일. 모델당 ~50KB.
- 배치: `run_all_and_diversify.bat` 에서 동결(`freeze`)·리더보드 뒤, 첫 push 앞에 `python build_daily_lists.py` 한 줄(ASCII·최소 삽입·CRLF 유지). 실패해도 비치명.

## 화면
- 표 위 탭 바: `오늘(9/17) | 9/16 | 9/15 | 더 보기 ▾`. 과거 탭 클릭 시 필터 영역은 접고 단순 표 렌더, 상단에 "당시 동결 점수 기준 · 등락은 그날 종가→오늘 종가" 한 줄. 오늘 탭으로 돌아오면 원래 표.
- 외부 자원 0, fetch 는 `hist/{model}.json?t=` 하나 추가. 휴대폰에서 탭이 줄바꿈되게.
- 유도 금지 원칙: 과거 탭에 "좋았다/나빴다" 색 강조 없음(등락 부호 색만).

## 완료 조건
- lowvol.html 로컬 실측(데스크톱·375px), JSON 숫자 3종목을 history.db·ohlcv.db 로 손대조, filter.html 동일.
- patch_note 1건(2026.09.14) + README 버전. `python tests/run_tests.py`. 커밋은 사용자(또는 요청 시).

## 참고
- 리더보드 개편(설계 문서 → 목업 1개)은 별건으로 대기 중(원칙: 첫 화면은 사용자 매매 방식(상위10·40일)으로 잰 숫자만 · 판정/관측 구분 · 규칙 없는 배지 제거 · 3층 구조).
- 운용 채택 관찰(9/17~) 표시: 주간 리캡 한 줄 + 리더보드 접힘 패널(코호트 n/4·국면·E)도 대기 중.
