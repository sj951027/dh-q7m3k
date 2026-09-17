# 2026-09-17 — 날짜 탭 확장: sv_a · ls_t1 · mom_b(기록용 페이지) (2026.09.15 · 판정·점수 0-diff)

## 그래서 뭐가 바뀌나
- `docs/sv.html`(sv_a)·`docs/_large_test.html`(ls_t1)에도 **오늘 | 어제 | 그제 | 더 보기(7일)** 날짜 탭. 과거 탭 = 그날 동결 점수 기준 시장별 상위 50: 그날 순위 · 시장 · 종목 · 코드 · 점수 · 그날 종가 · 오늘 종가 · **이후 등락%** · 오늘 순위. sv 는 전체/KOSPI/KOSDAQ 시장 탭이 과거 탭에서도 동작, ls_t1 은 필터 바·본 표를 숨기고 별도 표. 오늘 탭 복귀 시 원래 표·필터 복원.
- **`docs/mom_b.html` 신규(기록용)**: 9/17 판정으로 은퇴한 mom_b(모멘텀+눌림)의 마지막 10거래일 리스트만 보여준다. 상단 배너 "판정 완료: 역작동(유의) → 은퇴(9/17 정본) · 기록용 · 매수신호 아님". 첫 탭 이름은 '오늘'이 아니라 **'마지막 적재(9/17)'** — 적재가 멈춰 새 날짜는 안 늘어난다. 리더보드 `MODEL_PAGES` 에 mom_b 링크 추가.
- 데이터: `build_daily_lists.py` MODELS 에 `mom_b`(lowvol_scores 동결 점수)·`ls_t1` 추가. ls_t1 은 점수 테이블이 없어 `large_final` 에서 리더보드와 같은 정의(1/PER·1/PBR·RIM·배당 백분위 평균, 결측 제외·최소 2개)로 그날 랭크를 다시 계산 → `docs/hist/{ls_t1,mom_b}.json`.

## 왜
- 사용자 요청(9/17 밤): "sv_a랑 ls_t1 그리고 모멘텀+눌림 mom_b쪽도 html 표시하고 싶어". mom_b 는 표시 페이지가 없었고(mom.html 은 mom_a) 은퇴 모델이라 매수 유도가 안 되게 기록용으로만.

## 어떻게
| 파일 | 변경 |
|---|---|
| `build_daily_lists.py` | MODELS += mom_b, ls_t1(`load_ls_t1`) · 종목명 우선순위 large_final.name → stage3_final → listing_cache |
| `docs/sv.html` | `.dtabs` CSS · `#dtabs/#dnote` · `renderDtabs/renderHist`(hist/sv_a.json) · `load()` 가 과거 모드 해제 · 시장 탭 과거 모드 재렌더 |
| `build_large_test.py` | 템플릿에 탭 바·`#histPanel`·스크립트(hist/ls_t1.json) → `docs/_large_test.html` 재생성 |
| `docs/mom_b.html`(신규) | lowvol 톤 다크 테마 · 배너 · KOSPI/KOSDAQ · 날짜 탭(hist/mom_b.json) |
| `docs/leaderboard.html` | `MODEL_PAGES['mom_b']='mom_b.html'` (표시 링크만) |

## 검증(실측, 로컬 http.server)
- sv: 9/16 탭 100행(전체) → KOSDAQ 50행, 휴온스글로벌 sv점수 0.999→표시 1 · 22,100→22,550 +2.0% 가 history.db·ohlcv.db 와 일치. 오늘 탭 복귀 시 필터·587행 복원.
- ls_t1: 9/15 탭 100행(서희건설 94.6 …), 오늘 복귀 시 필터 바·본 표 복원. 생성 HTML 에 미치환 `{{` 0.
- mom_b: 마지막 적재(9/17) KOSPI 50행(대성산업 3.42 = lowvol_scores 3.4159), 9/16 KOSDAQ 50행. 콘솔 오류 없음.
- 점수·판정·게이트 코드 미접촉. `python tests/run_tests.py` 통과.

## 영향 범위 / 남은 것
- 표시 전용. 배치는 이미 `build_daily_lists.py` 를 돌리므로 9/18부터 6개 JSON 자동 갱신(mom_b 는 새 행 없음 → 같은 10일 유지).
- px.html 탭은 아직(요청 시). 리더보드 개편·운용 채택 관찰 표시는 별건 대기.
