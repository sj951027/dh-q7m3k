# 2026-10-30(2부) — E3 국면 스위치 계좌 `switch_v30_lvb` 를 모의 계좌 2판 틀에 추가 — 2026.10.42

> 보조 세션(모의 계좌 2판을 만든 세션)이 원래 세션의 요청(사용자 승인 19:30)으로 이어서 작업. 같은 폴더, 커밋 없음, `research/`·두 README 는 건드리지 않음.

## 요약
- 계좌 1장 추가(13장): 앵커일 코스피 칸이 A(R20 ≤ −5%)면 v30 상위 10, 그 밖이면 lv_b 상위 10. 나머지 규칙은 'v30 기본'과 같음. 칸은 `v30_gateD0` 와 같은 함수·날짜. 고른 목록이 없는 날은 현금(`days_missing`).
- 기존 12계좌 0-diff · 전체 테스트 통과(새 합성 8체크) · 저장소 실행으로 JSON 13장 확인(19:39, 배치 전).
- 실측 한 줄: 스위치 −5.7%(낙폭 −7.4, 현금 48.8%) vs v30 −5.8%(−8.5) · lv_b −5.5%(−7.4). 앵커 A 16·그 밖 34·없음 4. 급락 창이라 A 칸 날이 많아 아직 둘 사이 — **창 하나, 결론 아님**.

## 시간순 흐름
1. 19:36 요청 수신 → `EXPERIMENT_PLAN_20261030.md` E3 · `RESEARCH_regime_switch_proxy_10y_20261030.md` §4 · `regime_ad.py` 칸 정의 확인.
2. 스크래치에서 엔진 순수 함수 `switch_picks` + 배선 → `--out` 산출로 12계좌 0-diff → 합성 테스트 G절 → 19:39 저장소 반영·전체 테스트·`python paper_account.py` 1회.
3. 기록(이 파일·패치노트 2026.10.42).

## 사용자 결정
- (19:30, 원래 세션) E3 2단계 = 모의 계좌 1장 추가 승인.
- 보조 세션 가정(확인 대상): 칸 기준 = **앵커일 칸**(gateD0 와 동일, 요청 문구대로). E3 문서 '경계' 줄의 "전 거래일 종가" 와 다름 — 바꾸려면 `cells.reindex(dates).shift(1)` 한 줄이지만 변수가 늘어 사용자 결정.

## 바뀐 것(커밋은 사용자 — 코드 파일만)
- `paper_engine.py`(`switch_picks`) · `paper_account.py`(`SWITCH_ID`·계좌 1장·요약 키·메타) · `tests/test_paper_account_v2.py`(G절).
- `patch_note/20261030_paper_switch_e3.md`(새) · 이 worklog.
- 산출물(배치가 다시 만듦, 커밋 대상 아님): `docs/paper_account.json`(13장) · `../dh-q7m3k-data/paper_account.db`.

## 검증
- 0-diff: 기존 12계좌 summary 기존 키·nav 54일 소수 여섯째 자리까지 일치, 추가 키 없음(대조 스크립트·결과는 공유 메모 폴더 `paper_v2_compare_zero_diff.py`·`paper_e3_zero_diff_result.txt`).
- `python tests/run_tests.py` 전체 통과. 실행 23초.
- 10/30 배치 로그에서 `스위치 앵커 A …` 줄과 `✓ paper_account.db · paper_account.json` 확인은 다음 세션.

## 남은 일
1. 10/30 배치 뒤 JSON 13장 확인 · 두 README 한 줄(원래 세션).
2. 칸 기준(앵커일 vs 전 거래일) 사용자 확인. E4(급락 가속 계좌)를 붙인다면 같은 틀(`defs` 에 한 줄 + `new_ratio` 2배는 엔진의 budget 식 확인 필요 — 현재는 `min(cash, prev_nav/slots × ratio)` 라 ratio 2 로 바로 됨).
3. 지표 '40일 블록 NAV 차(스위치 − v30 · 스위치 − lv_b)' 는 JSON nav 에서 계산 가능 — 표시(돈 기준 탭) 때 함께.

## 다음 세션 시작점
- 배치 로그 → JSON `accounts.switch_v30_lvb.summary` 확인 → 칸 기준 결정 → E4 여부 → 돈 기준 탭.

## 작업 요령
- 이 Bash 도구의 heredoc 은 `\n` 같은 역슬래시를 먹는다 — 파이썬으로 파일을 고칠 땐 Edit/Write 도구가 안전(이번에도 한 번 걸림).
