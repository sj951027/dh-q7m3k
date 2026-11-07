# 2026-11-07 — 모의 계좌 14장째: 정적 반반 `mix_v30_lvb_5050`(E3 비교군) + 판정 스크립트 돈 관측표 — **2026.11.1**

## 뭐가
- `paper_engine.mix_picks(dates, picks_a, picks_b)`(순수 함수): 날마다 v30·lv_b 목록을 이어 붙임(중복 1회) → `simulate` 가 그날 예산(NAV/40)을 목록 길이로 나누므로 둘 다 있는 날은 각 목록이 예산 절반. 한쪽만 있는 날은 그 목록 전부, 둘 다 없으면 현금. info = days_both/only_a/only_b/missing.
- `paper_account.py`: `MIX_ID = "mix_v30_lvb_5050"`, NAMES·defs·summary(days_*)·print·DB meta(`mix`)·JSON `mix` 메타.
- `tests/test_paper_account_v2.py` [J] 5체크(이어 붙임·결손일·중복·현금·예산 반반 1/80).
- `research/verdict_lv_e_20261104.py` ⑩ 돈 관측표(관측 계약 §2 정의: 시장별 상위10·t+1·40일·동일가중·희석 제외·비용 0.5/0.35·같은 시장 전종목 대비·40일 코호트 블록 부트스트랩) — 라벨 무접촉, 연구 스크립트.

## 왜
- 관측 계약(2026-11-07 승인, `research/OBSERVATION_CONTRACT_20261104.md` §3): E3 스위치 전향 관측의 비교군에 **같은 투입액 정적 혼합**이 필요(Codex 2차 진화 검토 지적 — 스위치 vs 단독 둘만으로는 '고르는 효과'와 '섞는 효과'를 못 가름). 변수 = '그날 어느 목록' 하나.

## 어떻게 + 검증
- **기존 13장 0-diff(실측)**: `--out` 사본과 11/6 배치 산출 `docs/paper_account.json` 대조 — 13계좌 NAV 배열·요약 키 전부 동일(위반 0). 새 계좌 1장만 추가.
- 되감기(8/10~11/6, 탐색값·라벨 아님): mix −8.3%(낙폭 −10.0) vs 스위치 −8.1% · v30 −9.6% · lv_b −6.8%. 둘 다 있는 날 56 · 목록 없음 4.
- `python -X utf8 tests/run_tests.py` 전체 통과. 토요일 수동 재생성(`paper_account.py`, 배치 없음)으로 `../dh-q7m3k-data/paper_account.db`·`docs/paper_account.json` 14장(generated 2026-11-07 11:18). 월요일 배치부터 자동.
- 판정·점수·게이트 0-diff(모의 계좌는 관측 전용, 판정과 무관).

## 영향 범위
- `docs/paper_account.json` 에 계좌 1장 추가(페이지는 accounts 를 순회하므로 자동 표시 — 확인은 월요일 배치 뒤). 패치노트 버전은 CalVer 규칙대로 11월 첫 변경 = **2026.11.1**(11/1~11/3 노트 3건이 2026.10.47~.49 로 적힌 것은 월 표기 오기 — 번호는 그대로 둠).
