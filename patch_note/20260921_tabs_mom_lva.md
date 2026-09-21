# 2026-09-21 — 날짜 탭 확장: mom_a(mom.html) · lv_a(lva.html) (2026.09.20 · 판정·점수 0-diff)

## 그래서 뭐가 바뀌나
- 리더보드에서 들어가는 `docs/mom.html`(모멘텀 mom_a)·`docs/lva.html`(저변동+반전 lv_a)에도 **오늘 | 어제 | 그제 | 더 보기(7일)** 날짜 탭.
  과거 탭 = 그날 동결 점수 기준 시장별 상위 50: 그날 순위 · 종목 · 코드 · 점수 · 그날 종가 · 오늘 종가 · 이후 등락% · 오늘 순위. KOSPI/KOSDAQ 탭은 과거 탭에서도 동작, 오늘 탭 복귀 시 필터·원래 표 복원.
- 이제 날짜 탭이 있는 페이지: v30(filter) · lv_b(lowvol) · sv_a(sv) · ls_t1(_large_test) · mom_b(기록용) · **mom_a · lv_a**. 없는 페이지: px·qs·wu.
- `build_daily_lists.py` MODELS 에 `mom_a`·`lv_a` 추가 → `docs/hist/{mom_a,lv_a}.json`(10거래일 × 시장별 50). 배치는 이미 이 스크립트를 돌리므로 9/22부터 자동 갱신.

## 왜
- 사용자 요청(9/21): "mom_a랑 lv_a 도 v30·lv_b 처럼 10일 치". 두 모델은 §11 '차이 없음(노이즈, 8/29)' 확정이라 과거 탭 안내문에 그 사실을 적었다(색 강조 없음).

## 어떻게
| 파일 | 변경 |
|---|---|
| `build_daily_lists.py` | MODELS += mom_a(등록 20260627)·lv_a(20260625) — lowvol_scores 동결 점수 |
| `docs/mom.html` · `docs/lva.html` | lowvol.html 과 같은 틀: `.dtabs` CSS · `#dtabs/#dnote` · `renderDtabs/renderHist` · `load()` 가 과거 모드 해제 · 시장 탭 과거 모드 재렌더 |

## 검증(실측, 로컬 http.server)
- mom.html: 콘솔 오류 0 · 9/18 탭 KOSPI 50행(KB발해인프라 2.71 · 10,330→10,300 −0.3% — history.db 2.71·ohlcv.db 종가와 일치) · KOSDAQ 전환 50행 · 오늘 복귀 시 필터·122행 복원(시장 선택 유지).
- lva.html: 더 보기로 10일 전부 펼침(탭 11개) · 9/15 탭 50행(미스토홀딩스 2.5 · 39,200→38,850 −0.9%, 오늘 순위 19 — DB 일치) · 오늘 복귀 정상.
- 점수·판정·게이트 코드 미접촉. `python tests/run_tests.py` 통과.
