# 2026-09-24 — lead 트랙 신설 · ld_a 월간 관측 적재 등록 (2026.09.24 · 판정·점수 0-diff · 표시 없음)

## 그래서 뭐가 바뀌나
- 새 트랙 **lead(주도주)** 의 관측 모델 **ld_a**(고베타×최근 신고가, 통합 top20, 그룹당 4 상한)가 **매월 첫 거래일** 배치에서 `history.db.lead_picks` 에 동결 저장된다(대조군 `ld_ctl_amt` = 거래대금 상위 20 도 같이). 첫 앵커 **2026-10-01**.
- 화면·텔레그램·리더보드·점수·판정·게이트는 **아무것도 안 바뀐다**(가중 0·표시 없음·기존 테이블 무접촉). 배치 로그에 `[lead_observe]` 한 줄만 는다(첫 거래일이 아니면 "건너뜀").

## 왜 바꿨나
- 9/24 연구(RESEARCH_bigwinners·angles, Codex 교차검토 2회)에서 "시장을 크게 이긴 종목"의 선행조건으로 **고베타×최근 신고가** 조합만 시총지수를 이겼다(h120 +10.4 [+2.6, +19.5], in-sample·기움). 검증하려면 새 데이터에 스펙을 동결해 두어야 하고(사전등록), 기존 트랙 잣대(h20 IC·40일)는 이 후보와 맞지 않아 **새 트랙으로 분리**해 10월 판정 분모를 건드리지 않았다(사용자 결정 9/24 밤).

## 어떻게
| 파일 | 변경 |
|---|---|
| `lead_observe.py` (신규) | 가드(§22-2)·beta60·days_since_high·순위합·상관 클러스터 상한·월초 게이트·동결 적재. `--dry-run/--anchor/--force(dry-run 전용)` |
| `lead_eval.py` (신규, 읽기 전용) | PREREGISTER §3 잣대(120일·픽비중 지수/EW/대조군·6개월 블록 CI·비겹침 창) 출력. 자동 라벨 없음 |
| `run_all_and_diversify.bat` | build_scoreboard 뒤 `python lead_observe.py` 1단계(ASCII rem, CRLF 유지, 비치명 FAILED 집계) |
| `tests/test_lead_observe_rules.py` (신규) + `tests/run_tests.py` | spec_hash 골든(ld_a 4f01c8fcfb95 · ctl ea086b02aa03)·순위합·게이트·상한·클러스터 결정성 14체크 |
| `PREREGISTER_ld_a.md` (신규) · `MODELS_LEDGER.md` · `docs/models_registry.json`(`observe` 키) · `checkup.py REG_DATE` | 등록 기록. registry 소비자(telegram/weekly/scoreboard)는 특정 키만 읽어 무영향 |

- **검증(실측)**: ① 연구 코드 전체 패널 vs 프로덕션 330일 룩백 선정 대조 5앵커 19~20/20 일치 ② 게이트: 9/23 앵커 "첫 거래일 아님 → 건너뜀"(exit 0) ③ 사본 history.db 에 20260303 적재 → 재실행 "이미 적재 → 건너뜀" → 같은 달 다른 날 건너뜀 → `lead_eval` h120 계산 정상 ④ `python tests/run_tests.py` 전체 통과 ⑤ 실 DB·docs 무접촉(첫 실제 적재는 10/1 배치).
- 실행 조건: 앵커일 종목 수 <2000 이면 적재 안 함(부분 수집 방어, exit 1 → FAILED 경고). 클러스터 실패 시 상한 없이 선정하고 cap_applied=0 기록.

## 영향 범위
- 판정·점수·게이트·표시 **0-diff**. 새 테이블 1개(월 40행). 배치 시간 +수 초(월초만 +~20초). 10월 판정(px_a·lv_e·v30 W2b) 분모 불변.
- 되돌리기: bat 의 3줄 제거 + `lead_picks` 는 남겨도 무해(읽는 곳 없음).

## §2. 같은 날 밤 보강 — 관측 페이지 `docs/lead.html` (표시 전용)
- **뭐가 바뀌나**: `docs/lead.html` 신설 — 앵커별 픽 20(코드·이름·베타·신고가 후 일수·동행그룹·거래대금·현재까지/120일 수익·같은 시장 지수 대비), ① 픽 시장비중 지수 ② 앵커 유니버스 동일가중 ③ 대조군 3중 비교 KPI, 창 마감 앵커 누적(6개월 블록 CI는 n≥3 부터), 비겹침 창 부호. 앵커가 없으면 "첫 앵커 2026-10-01 대기" 문구. `docs/leaderboard.html` 하단 링크 1줄("별도 잣대라 위 표엔 없음"). **성적표(40일 보유) 표에는 넣지 않음** — 규칙(월 1회·통합 20·120일)이 달라 같은 잣대로 재면 사전등록과 다른 것을 재게 됨(사용자 질문 9/24 밤).
- **어떻게**: `build_lead_page.py`(신규, 읽기 전용) · `lead_observe.py` 에 `lead_universe`(앵커일 가드 유니버스 ticker·market, 월 ~1,100행) 저장 추가(② 재현용, spec_hash 무관) · bat 에 `python build_lead_page.py` 1단계(lead_observe 직후, 비치명) · PREREGISTER_ld_a "표시 없음" → "표시 전용 페이지" 갱신.
- **검증(실측)**: 실 DB(픽 없음) → 대기 문구 페이지 생성 · 사본 DB 에 2026-03-03(마감)·2026-09-01(진행 16일) 적재 → 두 상태 렌더 확인(브라우저) · run_tests 통과. docs/lead.html 은 다음 배치가 push(9/28 월).
