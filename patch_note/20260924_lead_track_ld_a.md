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

## §3. 같은 날 밤 보강 2 — lead 페이지 '오늘 기준 순위' 탭 + le_a 열람 페이지 (표시 전용)
- **lead.html 일별 참고 탭**: 같은 규칙을 매일 돌린 상위 20을 `docs/hist/lead_daily.json` 에 최근 10거래일 누적(배치마다 오늘치 1회 계산, ~6초)하고 페이지 하단에 날짜 탭으로 표시(그날 종가→오늘 등락). **"참고 · 동결 아님 · 판정에 안 씀"** 배지 — 판정은 월 첫 거래일 동결분(lead_picks)만. 첫 10일치는 9/10~9/23 로 백필(표시용).
- **le.html 신설**(사용자 요청 — 성적표 참고 수익 +4.2%p 가 눈에 띄어서): sv.html 을 본떠 le_a 목록·날짜 탭. **§11 정본은 노이즈(9/13)** 이므로 lva/mom 페이지처럼 '판정 완료 노이즈 · 기록·관찰용' 경고를 앞세움. 성적표 수치는 매수일 8일(40일 묶음 0.2개)짜리 참고치임을 페이지에 명시.
- **어떻게**: `build_lead_page.py` update_daily/daily_html · `docs/le.html`(신규) · `build_wu_filter.py --model le_a --out latest_le.csv`(run_and_diversify 2.89c3 단계, 비치명) → `docs/latest_le.csv`·`le_meta.json` · `build_daily_lists.py` MODELS 에 le_a → `docs/hist/le_a.json` · leaderboard.html·leaderboard_full.html MODEL_PAGES 에 le_a→le.html(성적표 모델 이름이 링크가 됨).
- **검증(실측)**: lead.html 10일 탭 렌더 · le.html 로컬 렌더(1,037종목, 희석 배지 74) · py_compile · run_tests 통과. 점수·판정·게이트 0-diff.

## §4. 같은 날 밤 — 신규 코드 전수 점검(사용자 요청) 결과와 수정
점검 범위: lead_observe.py · lead_eval.py · build_lead_page.py · docs/lead.html·le.html · build_daily_lists.py · run_and_diversify.py · run_all_and_diversify.bat · tests · checkup.REG_DATE · models_registry.json · .gitignore. 방법: 소비자 역추적(grep)·정독·사본 DB 시나리오 실행·전체 테스트.

| # | 발견 | 심각도 | 조치 |
|---|---|---|---|
| 1 | `lead_observe` 가 "오늘 = 그 달 첫 거래일"일 때만 적재 → 10/1 배치 미실행·부분 수집(<2000행)이면 **그 달 앵커 영구 누락** | 높음 | 자동 앵커 = 최신 달의 첫 거래일(`month_anchor`), 같은 달 안에서 따라잡기. 팩터는 앵커일까지 정보만 쓰므로 스펙 동일. 등록일(20261001) 이전 달은 건너뜀. 테스트 4개 추가 |
| 2 | beta60 = cov/var 에서 var=0 이면 inf → 순위 1위 가능 | 낮음(실제 발생 어려움) | 비유한값 → NaN(핵심 팩터라 제외) |
| 3 | lead.html 의 사전등록 링크 `../PREREGISTER_ld_a.md` 가 GitHub Pages 에서 404 | 낮음 | 저장소 blob URL 로 교체 |
| 4 | `month_anchor` 기본 인자가 정의 시점 상수에 묶여 테스트 오버라이드 무효 | 낮음(테스트만) | 호출 시 `REG_DATE` 명시 |
| — | 확인·이상 없음: Bonferroni 분모는 점수 테이블(v3/lowvol/wu) 실측이라 `lead_picks`·REG_DATE 추가 무영향 · checkup 은 점수 있는 모델만 대상 · registry `observe` 키는 어떤 소비자도 안 읽음 · bat 3줄 ASCII·CRLF·비치명 · INSERT 컬럼 17개 = 테이블 17개 · JSON 직렬화 타입 · 첫 거래일 당일은 페이지에 미표시(t+1 종가 전) · 루트 latest_le.csv gitignore | | |
| — | 알려진 제약(수정 안 함): build_lead_page 의 '마지막 관측가' 조회가 앵커마다 전체 테이블 GROUP BY(앵커 36개 시 ~1분 추정) · 한 달을 통째로 놓친 뒤 다음 달이 되면 그 달은 소급 안 됨(소급 적재 금지 원칙) · 앵커일 market_daily 결측 시 그날 지수수익 0 으로 베타 계산 | | |

검증(실측): 실 DB `python lead_observe.py` → "최신 달(202609) 첫 거래일이 등록일 이전 → 건너뜀"(exit 0) · 사본 DB 에 등록일을 9/1 로 가정해 자동 앵커 적재 → 재실행 동결 · 전체 테스트 통과(lead 테스트 18체크) · py_compile.
- 별건: le_a 보유기간 연구 `research/RESEARCH_le_hold_20260924.md`(정점 없음·시장평균 대비 선형 누적·지수 대비 0).
