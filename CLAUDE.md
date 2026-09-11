# CLAUDE.md — dh-q7m3k (한국주식 스크리너)

당신은 이 스크리너의 신중한 협업자다. 항상 한국어, 간결·사실 위주, 실측과 추정을 구분 표기.
쉬운 말을 우선한다("회귀 신호를 놓쳤다" 대신 "느려졌는데 그냥 통과시켰다").

## 먼저 읽을 것 (순서)
1. `MODELS_LEDGER.md` — 전 모델 현황·골대·판정 예정(원장). 원장과 정본(PREREGISTER_*/VERDICT_*)이 어긋나면 정본이 이긴다.
2. 요청이 어느 트랙인지 분간한 뒤 그 설계 문서만: v3·lowvol·wu → `PROJECT_KNOWLEDGE.md`(크다 — 필요한 절만 grep), lowvol → `LOWVOL_TRACK_DESIGN.md`, 대형 → `LARGE_SCORE_DESIGN.md`.
3. 운영 권고 `OPS_GUIDE.md`(강제 아님) · 최근 이력 `patch_note/`(최신 3~4건) · 연구 `research/`.
- 자매 프로젝트 `../Position-Tracker-Web`(실거래 소비자)는 그쪽 `CLAUDE.md`·`PTW_PROJECT_HANDBOOK.md` 기준. us-screener·div-tracker는 별개 — 여기서 다루지 않는다.

## 트랙
- (A) v3 과매도: 챔피언 **v30**(§11 유의, VERDICT_20260809). 2차 창 W2b 재판정 사전등록(PREREGISTER_v30_w2, ~10/07).
  파생 lowvol(**lv_b** 표시 기준, 기움 — VERDICT_20260829_lowvol) · wu(sv_a·le_a·qs_a·px_a 관측 중).
- (B) 대형 가치: 별도 유니버스·`large_final`, ls_t1은 테스트(h60~120). v3와 절대 섞지 않는다.
- 트랙 간·프로젝트 간 점수/유니버스/IC 절대값 비교 금지.

## 불변 규칙
- 판정은 §11 그대로(40거래일 OOS · h=20d 주지표 · 부트스트랩 CI + 주블록 감도 각주③ · 주별 일관 · Bonferroni 분모 = distinct model_id, 행 보존이라 은퇴로 줄지 않음). 40거래일 미만은 '노이즈'가 기본값. 경계값은 '채택'이 아니라 '기움'.
- 관측 팩터는 점수식에 넣지 않는다. 새 모델 = 새 model_id + PREREGISTER. 챌린저는 변수 1개, 시작하면 spec 동결. 판정 직전 신규 등록 회피(분모 증가).
- §11 기각·은퇴 모델은 `RETIRED` 집합(v3_rescore/lowvol_score/wu_score)으로 적재 중지, 기존 행 보존. 부활은 새 model_id로만.
- 내부자 elestock OFF · 매직넘버 금지 · 관측 우선(가중 0 적재 → 검증 → 승격) · 완전성 게이트는 stage1 기준(stage3 크기는 장세 함수).
- 점수/판정/게이트 코드를 만지면: history.db로 **결과 0-diff**를 먼저 보이고 사용자 승인 후 적용. 세션 끝에 `python tests/run_tests.py`(골든이 깨지면 골든이 아니라 코드를 의심).
- IC·수익은 항상 n과 CI와 함께. "채택 안 함"도 정당한 결론.
- `.bat` 수정은 ASCII만·최소 삽입(CRLF 유지). 연구 산출물은 `research/`에(루트 금지).

## 실행 주의 (Claude Code는 네트워크가 된다 — 그래서 더 조심)
- **20:10~22:30(KST)엔 파일·DB를 건드리지 않는다** — 작업 스케줄러 배치(`run_auto_logged.bat`) 실행 중. 로그는 `logs/auto_run_YYYYMMDD_2010.log`.
- 전체 배치·DART/KRX/KIS 수집기(`run_manual_logged.bat`, `dart_events.py`, `kis_flows.py` 등)는 **사용자가 명시적으로 시킬 때만** 실행. 재실행은 09:00 이전이면 run_id가 전 거래일로 자동 잡힘(09:00~19:59 재실행 금지 — 장중 가격 오염).
- 부분실행 run 정리: `python research/clean_partial_run.py YYYYMMDD [--yes] [--force]`(백업 자동). 같은 날 재실행 전 필수(이중실행 게이트).
- 읽기는 자유: `history.db`·`../dh-q7m3k-data/ohlcv.db`는 `mode=ro`로 열기.
- FDR 상장목록이 404면 `listing_cache.py`(예비 캐시)가 자동 대체 — 텔레그램 🔔 줄의 신선도 경고로 확인.

## 세션 마무리 체크리스트
1. 코드·표시·파이프라인·운영이 바뀌었으면 `patch_note/YYYYMMDD_주제.md` 1건(뭐가/왜/어떻게+검증/영향범위, "판정·점수 0-diff" 명시) + `patch_note/README.md` 버전(CalVer 연도.월.차수).
2. 모델 등록/판정/은퇴가 있으면 같은 세션에서 `MODELS_LEDGER.md` + `docs/models_registry.json`(리더보드·텔레그램·주간 리캡의 표시 단일 소스) 갱신.
3. 점수·판정·게이트를 만졌으면 `python tests/run_tests.py`.
4. 커밋은 사용자가(GitHub Desktop). `docs/`는 배치가 스스로 push하니 코드 파일만 골라 커밋하도록 안내. 줄바꿈만 바뀐 파일은 커밋하지 않는다.
5. 보고 끝에 '도전 카드' 0~2개(기대 이득 + 검증 경로; 검증 기준 완화는 도전이 아님).

## 하드 경계 (승인이 있어도 안 함 — 사용자가 직접)
로그인/인증 클릭, 계정 생성, 비밀번호 입력, 권한 부여·변경, 실거래 주문. `.env`·토큰은 읽거나 출력하지 않는다.
