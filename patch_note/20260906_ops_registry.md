# 2026-09-06 — 운영 권고(OPS_GUIDE) · 유니버스 고갈 칩 · 판정 레지스트리 단일화 · v30 W2b 사전등록 (2026.09.1 · 표시·문서 전용 · 판정·점수 0-diff)

## 뭐가 (사용자 눈에 보이는 것)
- `OPS_GUIDE.md`(루트) 신설 — **운영 권고**(시장별 상위 10·다음날 매수·4트랜치·40거래일·중간 신호 무시·희석 배지 회피). 같은 날 사용자 결정으로
  '규약(강제·무효 조건)' → '권고(막지 않음, 화면은 "괜찮으세요?"만)'로 격하 — 초안 OPS_GUIDE.md 는 _trash/ 로. §2에 '코드가 실제로 막는 것'을 이유와 함께 별도 명시.
- `PREREGISTER_v30_w2.md` 신설(**사용자 승인·등록**) — v30 2차 창 W2b(20260810~40거래일, ≈10/07) 재판정 사전등록. 등록 시점 h20 완결 앵커 0개. 스펙·분모 불변.
- lowvol/lva/mom 페이지: 시장별 **10종목 미만이면 '⚠️ 유니버스 고갈' 칩**(8 미만이면 'IC 앵커 없음' 붉은색). 현재 102/220 이라 안 뜸.
- `docs/models_registry.json` 신설 — 정본 판정(sealed)·은퇴(retired)·돈 대표(money)의 **표시 단일 소스**. leaderboard.html·notify_telegram·
  notify_weekly 가 읽고 없으면 인라인 폴백. 판정/은퇴 때 갱신 위치가 4곳 → **registry + MODELS_LEDGER**.

## 왜
- 9/05 연구 결론(40일 보유·상위 10·희석 회피)을 문서로 남기되, 강제하면 실제 실험·확장이 막힌다(사용자) → 권고 문서.
- 유니버스 고갈은 장세 함수라 정상이지만, 상위 10 규약을 못 채우는 날을 화면이 알려줘야 한다(억지로 채우는 사고 방지).
- sv_a·le_a 판정(~9/11)·sv_b 배선을 앞두고 SEALED 4곳 수동 갱신은 어긋남 위험(2026-09-04 사용자 피드백: 결정은 정본으로 읽는다).

## 어떻게 + 검증
| 파일 | 변경 | 검증 |
|---|---|---|
| `OPS_GUIDE.md` (구 OPS_GUIDE → _trash) · `PREREGISTER_v30_w2.md` | 신설 | 문서 |
| `docs/lowvol.html`·`lva.html`·`mom.html` | meta 칩 뒤 고갈 경고(try/catch, rows.length 기준) | JS 파서 통과 · 5행 CSV 로 headless 렌더 확인(칩 표시) |
| `docs/models_registry.json` | 신설(sealed 18·retired 13·money 2) | — |
| `docs/leaderboard.html` | SEALED/RETIRED_FALLBACK/RET_WHY/RET_DATE `const→let`, `applyRegistry()` + registry fetch(Promise.all 3번째) | registry 있음/없음 headless 렌더 **innerText·innerHTML 완전 동일** |
| `notify_telegram.py` | `_apply_registry()` (import 시 1회, 비치명) | `build_message()` 전/후 **0-diff** |
| `notify_weekly.py` | `_ret_fb` registry 대체(비치명) | `--dry-run` 전/후 **0-diff** |
| `MODELS_LEDGER.md` | registry 메커니즘 1항 | 문서 |
| `research/shadow_ops_portfolio.py` | 그림자 포트 산출(앵커·트랜치, 중앙값 대비/지수 대비 병기) | 실행 — 6~8월 h40 v30 +7.2·lv_b +9.4%p(중앙값 대비); **지수 대비 +20%p 는 대형주 급락 착시** → 규약 잣대를 중앙값으로 명시 |
| `research/verdict_sv_le_prep_20260906.py`·`SV_LE_PREP_20260906.md`·`sv_le_decile_20260906.py`·`svr_extreme_20260906.py` | sv_a·le_a 판정 준비 + IC≠돈 십분위 해부(판정 아님) | 실행(읽기 전용) |
| `research/ops_overlap_20260906.py` | v30·lv_b 상위10 겹침·상관(§5-1) → out_shadow/ops_overlap.csv | 실행 — 겹침 1.2종목, 상관 −0.1, 합집합 편차 축소 |
| `research/fullscan_20260903/step26_tranche.py` | 트랜치 효과(1/2/4회 × 시작일 오프셋) → out/tranche_grid.csv | 실행 — 평균 불변, 시작일 분산 축소 |
| `research/verdict_v30_window2_prep_20260906.py`·`V30_WINDOW2_PREP_20260906.md` | v30 2차 창(W2b 8/10~) 준비·사전등록 제안 | 실행(읽기 전용) |
| `research/DESIGN_dart_extension_20260906.md` | DART A/I 그룹 확장 설계(코드 미적용) | 문서 |

`python tests/run_tests.py` 통과(점수·판정 코드 무변경). 9/07 첫 배치에서 확인할 것: wu_a/wu_b·lv_c 등 미적재, leaderboard.json `retired` 키, 텔레그램 v2 형식.

## 영향범위
- 점수·유니버스·판정·leaderboard.json: **0-diff**. 표시·알림 문구도 오늘 기준 0-diff(registry 내용 = 종전 인라인).
- 이후 판정 시: registry 의 sealed/retired 를 고치면 세 소비자에 동시에 반영. 인라인 폴백은 그대로 두되 갱신 의무 없음(registry 가 이김).
