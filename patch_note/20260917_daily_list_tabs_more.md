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

## 전체 점검 (같은 밤 2차 · 사용자 요청 "문제 없는지 꼼꼼하게")
점검 항목과 결과(실측):
| 항목 | 결과 |
|---|---|
| 콘솔 오류 | sv·ls_t1·mom_b 세 페이지 모두 0 (로컬 http.server) |
| 더 보기 | sv 에서 10일 전부 펼침·접기 동작(9/17~9/4) |
| 휴대폰 폭 | mom_b 375px 에뮬: 가로 스크롤 없음, 탭 2줄로 줄바꿈 |
| JSON 6개 | 모두 10일 · 시장별 50행 · 종목명 누락 0 · 시장값 kospi/kosdaq 소문자 통일 |
| large_final | run 당 (run_id, ticker) 중복 0 · 시장 kospi 326/kosdaq 174 |
| 배치 배선 | `.bat` 113~114행에 build_daily_lists 호출·FAILED 수집 있음. push 는 `run_and_diversify.git_push()` 가 `docs/` 통째로 add → hist/*.json·mom_b.html 자동 포함 |
| 생성 HTML | `_large_test.html` 미치환 `{{` 0 |

고친 것(2차):
- `docs/mom_b.html` 의 `../VERDICT_…md` 링크 제거 → 파일명만 표기. GitHub Pages 루트가 `docs/` 라 저장소 루트 문서는 404 가 났을 것(다른 페이지도 전부 파일명만 적는 관례).
- `docs/sv.html` 과거 탭에서 상위 10 강조(top50row) 제거 — 과거 탭 50행은 전부 top50 바스켓이라 강조가 의미 없고, 유도 금지 원칙(색 강조 없음)에도 어긋남.
- 과거 탭 안내문 5곳(lowvol·filter·sv·ls_t1·mom_b)에 **'—' = 가격 자료 없음** 범례 추가. ls_t1 은 "품질게이트·플래그 필터 미적용"도 명시(오늘 표는 필터 적용, 과거 표는 원 랭크).

발견했지만 **안 고친 것**(사용자 결정 필요 · 수집기/유니버스 변경이라 이 세션 범위 밖):
- 과거 탭에서 그날 종가·등락이 '—' 인 행이 있다: lv_b 9/17 100행 중 10, mom_b 8, **ls_t1 24**, v30 1~2, sv_a·px_a 0. 원인은 `universe_ohlcv.py get_universe()` 가 FDR Market 이 정확히 KOSPI/KOSDAQ 인 **숫자 6자리 코드만** 담아서, 코스닥 글로벌(Market='KOSDAQ GLOBAL' — 에코프로·에코프로비엠·JYP Ent.·SOOP·클래시스·HK이노엔·솔브레인홀딩스·하림지주·피엔티 등 약 50종목)과 영문 섞인 신규 코드(0088M0 메쥬 등 약 81종목)가 ohlcv.db `daily_ohlcv` 에 **한 행도 없다**. 이미 9/11 `kis_flows.py` 주석에 같은 사실이 적혀 있고, 그때 "시세 유니버스는 별건(lowvol/wu 모델 유니버스가 바뀜)"으로 미룬 상태.
- 규모(9/17 실측): stage3_final 713 중 21종목(3%), large_final 500 중 51종목(10%) 이 ohlcv 에 없음. **lv_b KOSDAQ 오늘 상위 10 중 3종목(JYP Ent.·SOOP·클래시스)** 이 여기 해당 → 리더보드 IC·따라사기·운용 채택 관찰(shadow_ops)에서도 이 종목들은 가격이 없어 조용히 빠진다(표시 문제가 아니라 데이터 커버리지 문제).
- 선택지: (a) `universe_ohlcv.py` 에 KOSDAQ GLOBAL·영문코드 포함 + 백필(수집기 실행은 사용자) — 단 lowvol/wu 유니버스가 넓어지므로 판정 중 모델에 미치는 영향을 먼저 재고 0-diff 여부 확인 필요. (b) 리더보드·shadow_ops 는 그대로 두고 표시만 stage3_final.price 로 보충(등락은 여전히 계산 불가). 결정 전까지는 '—' 범례로 둔다.
