# 2026-09-30 — 오늘 변경분 전수 점검 후 수정 (2026.09.29 · 판정·점수 0-diff)

## 그래서 뭐가 바뀌나
- **텔레그램 운용 모델 규칙 정리**
  - registry의 `live`(운용 모델)가 있으면 **항상 첫 줄**에 둔다. `show`는 나머지 순서만 정한다.
  - `show`가 리스트가 아니면 무시하고, 은퇴 모델은 뺀다.
  - registry를 못 읽을 때의 폴백을 `live=""`, `show=[v30, lv_b]`로 바꿨다(전에는 lv_b '운용 중' 폴백).
  - 운용·표시 설정을 따로 읽어, 다른 키에서 예외가 나도 적용되게 했다.
  - 오래된 주석("lv_b(운용) → v30(참고)")을 정정했다.
- **v30 페이지 3개월 컬럼**: 저장된 컬럼 설정이 없던 사용자가 3개월 컬럼을 끄면 다음 로드에 다시 켜지던 문제를 고쳤다.
- **le 지난 탭 3개월 순위**
  - 오늘 탭(JS)과 **같은 값·같은 반올림·같은 동점 순서**로 계산하게 맞췄다.
    - le점수: 소수 3자리
    - 3개월 수익률: 소수 1자리
    - le+3개월 점수: 소수 3자리
    - 동점 순서: CSV 순서
  - 9/30 기준 169종목에서 3개월↓순위·le+3개월순위 **불일치 0**(전에는 37건·27건, 최대 4계단 차이).
- **배치 관측 단계 실패 처리**
  - `build_daily_lists.py`의 본 단계가 실패해도 `v30_obs_formulas`·`le_obs_3m`은 따로 실행한다.
  - 관측 단계가 실패하면 **종료코드 1**을 낸다. .bat의 FAILED → 텔레그램 🔔에 잡히고, `build_daily_lists`는 OBS_ONLY라 알림 첫 줄은 그대로다. 9/21 "조용히 낡는 것 방지" 원칙에 맞춘 것이다.
- **`docs/lowvol.html`**: 제목·머리말·경고·바닥글의 "운용 기준"을 "표시 기준"으로 바꿨다. 경고 문구에는 "2026-09-30부터 사용자 운용 안 함"을 추가했다.

## 왜
- 사용자 요청(9/30): 오늘 변경분 전수 검사.
- 코드 리뷰 에이전트와 직접 실행 점검에서 **치명 문제 0**, 중간 1·경미 여러 건이 나왔다. 그중 표시·알림에 영향이 있는 것을 고쳤다.

## 점검 범위와 결과 (실측)
- **Python**: 루트·research·tests `py_compile` 전부 통과. `python tests/run_tests.py` 통과.
- **JSON**: docs의 JSON 34개 모두 정상.
- **HTML 19개 전부** 로컬 렌더(http.server): 콘솔 오류 0, 네트워크 요청 전부 200(404 없음).
  - 대상: index·filter·filter_v31g·guide·le·lead·leaderboard·leaderboard_full·lowvol·lva·mom·mom_b·px·qs·scoreboard·sv·wu·_large_obs·_large_test
- **소비자 영향 없음**
  - PTW는 `latest_{mkt}_lowvol.csv`와 `hist/{v30,ls_t1,le_a,ld_a}.json`만 읽는다. 스키마 불변.
  - notify_weekly·build_scoreboard·leaderboard 페이지는 registry의 `live`/`show`를 읽지 않는다.
- **텔레그램**(발송 없이 미리보기): registry 조합 6가지를 검증했다.
  - live 빈값 / live=lv_b / live가 show 밖 / show 없음 / show 문자열 / show에 은퇴모델 → 모두 의도대로 동작.
  - 현재 메시지는 직전과 같다(v30 먼저, 운용 표시 없음).
- **알고 두는 것(수정 안 함)**
  - `v30_obs_formulas`는 게이트(부분실행·이중실행)를 적용하지 않는다. 지금은 화면에 쓰는 곳이 없고 run_id로 맞추니 무해하다. 나중에 화면에 붙일 때 적용한다.
  - v30 3개월↓순위 범위는 희석 공시 종목을 포함한다(BUY·WAIT·OBSERVE). 설명 상자 문구와는 일치한다.
  - px.html 오늘 탭 KOSDAQ + top50은 0행이다. top50이 두 시장을 합친 순위라서 생기는 기존 동작이다.

## 어떻게
| 파일 | 변경 |
|---|---|
| `notify_telegram.py` | `_apply_show()` 신설(live 첫 줄 + show 나머지 · 형식 검사 · 은퇴 제외), 폴백 상수, 별도 try, 주석 정정 |
| `docs/filter.html` | 기본값 분기에서도 `csv_filter_r3m_cols_20260930` 기록 |
| `le_obs_3m.py` | r63 round(1) · le점수 round(3)로 백분위 · le3m round(3) · 점수 내림차순 안정 정렬 후 순위 |
| `build_daily_lists.py` | `__main__`: 본 단계·관측 2단계를 독립 실행하고 실패 시 rc=1 |
| `docs/lowvol.html` | "운용 기준" → "표시 기준" 4곳 |

## 파일 정리 (사용자 승인 · 같은 날)
- `research/INDEX.md` 신설: 보고서 62개 한 줄 목록(날짜·제목·관련 폴더). 파일 이동 없음 — 보고서끼리 경로로 참조하므로 옮기지 않았다.
- `Screener/` 삭제: 제목 한 줄뿐인 `AGENTS.md`(9/13, 외부 도구 import 흔적으로 추정)와 빈 `experiments/`. 참조 없음.
- `_trash/` 날짜 폴더 43개(7/11~9/15) 영구 삭제: 283MB → 47MB. cleanup이 옮겨 둔 회전 파일이고 값은 history.db에 있다. git과 무관한 로컬 정리다. 최근 14일(9/16~)과 날짜가 아닌 개별 파일 10개는 남겼다.
- `__pycache__` 12개 삭제(git 제외 임시 파일).
- 하지 않은 것: research의 큰 중간 CSV git 추적 제외는 사용자가 원하지 않아 보류했다. `%TEMP%\dh_v30_formula_20260930`(약 180MB, 저장소 밖)은 10월 F1~F4 채점 뒤 지운다.

## 영향 범위
- 표시·알림만 바뀌었다 → **판정·점수 0-diff**.
