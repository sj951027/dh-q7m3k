# 2026-09-17 — 모델 페이지 '지난 날짜 리스트' 탭 (lv_b·v30) (2026.09.14 · 판정·점수 0-diff)

## 그래서 뭐가 바뀌나
- `docs/lowvol.html`(lv_b)·`docs/filter.html`(v30)에 날짜 탭: **오늘(날짜) | 어제 | 그제 | 더 보기(7일)**. 과거 탭은 그날 **동결 점수** 기준 시장별 상위 50을 단순 표로: 그날 순위 · 종목 · 코드 · 점수(v30 은 등급·버킷도) · 그날 종가 · 오늘 종가 · **이후 등락%** · 오늘 순위(오늘 상위 50 밖이면 —). 시장 탭(코스피/코스닥)은 과거 탭에서도 동작. 오늘 탭으로 돌아오면 원래 표·필터 복원.
- 데이터: 새 스크립트 `build_daily_lists.py` → `docs/hist/{lv_b,v30,sv_a,px_a}.json`(10거래일 × 시장별 50, 약 200KB/모델). sv_a·px_a 페이지 탭은 다음에.

## 왜
- 사용자 요청(9/17): "오늘 리스트는 그대로, 탭으로 어제자 리스트". 10거래일로 확정(용량 무시 수준). 어제 뽑힌 종목이 그 뒤 어떻게 됐는지 바로 보이게 '이후 등락'을 넣음. 외부 검토의 "당시 무엇을 보여줬는지 기록" 원칙과 부합(동결 점수 기반이라 사후 정정과 무관).

## 어떻게
| 파일 | 변경 |
|---|---|
| `build_daily_lists.py`(신규) | history.db 동결 점수 + 같은 run 의 stage3_final 종목명(없으면 listing_cache) + ohlcv 종가. run_id→거래일·게이트는 leaderboard.py 규약. 읽기 전용·비치명 |
| `run_all_and_diversify.bat` | `build_large_test.py` 뒤·Large push 앞에 `python build_daily_lists.py` + FAILED 수집 한 줄(ASCII, 기존 줄 무변경) |
| `docs/lowvol.html` | `.dtabs` 탭 바 + hist 모드 렌더(기존 표 재사용) |
| `docs/filter.html` | 탭 바 + 별도 `#histPanel`(기존 필터 표는 숨김) · `autoLoad` 가 hist 모드면 시장만 바꿔 재렌더 |

## 검증(실측)
- 로컬: lv_b 9/16 탭 50행 렌더, 시프트업·현대엘리베이터·HD현대중공업 점수/종가/오늘 순위를 history.db·ohlcv.db 와 손대조 일치. 오늘 탭 복귀 시 필터·표 복원. v30 9/16 KOSPI 50행, 등급·버킷 표시, 콘솔 오류 0.
- 점수·판정·게이트 코드 미접촉. `python tests/run_tests.py` 통과.
