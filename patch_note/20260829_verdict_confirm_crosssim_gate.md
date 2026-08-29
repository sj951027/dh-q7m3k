# lowvol 판정 정본 확정 + 공통창 신모델 게이트 교정 (2026.08.6)

## 1. 그래서 뭐가 바뀌나

- `VERDICT_20260829_lowvol.md`가 **초안 → 정본**으로 확정됐다(사용자 승인).
  확정 전 점검에서 발견된 문구 결함 2건을 교정하고 **주블록 부트스트랩 감도(각주 ③)**를 추가했다.
- 리더보드 '공통 잣대 모의계좌'에서 **등록일이 창 시작보다 늦은 신모델(px_a)이 제외**된다.
  기존에는 미등록 기간이 수익 0%로 채워져 "px_a 시장에 뒤짐 -8.4%p" 같은 착시가 표시됐다.
- lv_e 등록 시점 결정: **sm_a 판정(다음 거래일 40일 도달) 완료 후 등록**(PREREGISTER_lv_e.md §2).

## 2. 왜 바꿨나

- **VERDICT 초안 결함(점검 실측)**: ① 각주 ①이 "주블록 부트스트랩"을 썼다고 기술했으나
  구현(leaderboard.py·verdict 스크립트)은 **iid 부트스트랩** — 오기. ② §3 "lv_b > lv_a 확정"은
  iid CI 기준 — 앵커 창 겹침을 반영한 주블록 감도에서는 CI가 0을 걸쳐(diff −0.0515,
  [−0.124, +0.014]) '확정'이 과함. 주블록 생존 우위는 mom_a·lv_d·lv_c 3건뿐.
  단독 판정은 전부 불변(lv_b '기움' 유지, lv_c '역작동(유의)' 생존).
- **공통창 착시(사용자 발견)**: px_a는 실점수가 20260810~(14 run)뿐인데 '전 모델 공통창(7/24~)'
  n=24일로 표시 — `daily_series`의 `fillna(0)`이 미등록 ~16거래일을 0%로 채우고, 그 사이
  시장평균이 +9.4% 올라 누적 비교가 왜곡. 각주의 "창이 찰 때까지 자동 대기" 의도와 구현
  (유효일 ≥ 10만 검사)이 어긋나 있었다.

## 3. 어떻게 (+ 검증)

| 파일 | 변경 |
|---|---|
| `VERDICT_20260829_lowvol.md` | 정본 승격 · 각주 ① iid로 정정 · §3 '확정'→'우위 기움' · 각주 ③(주블록 감도) · §7 확정 처분 |
| `build_cross_sim.py` | 패널별 `등록일 > 창 시작` 모델 제외 게이트 추가(기존 MIN_DAYS 게이트는 유지) |
| `docs/cross_sim.json` | 게이트 반영 재생성(전 모델 공통창에서 px_a 제외) |
| `docs/leaderboard.html` | 공통창 각주 문구·버전(2026.08.6) 갱신 |
| `research/verdict_blockboot_20260829.py` | 신규 — 주블록 감도 재현 스크립트(읽기 전용, seed 고정) |
| `PREREGISTER_lv_e.md` | 등록 시점 결정(sm_a 판정 후) 기록 |
| `research/lv_e_wiring_20260829.patch` | 주석의 등록일 하드코딩 제거(등록일=첫 적재일) — `git apply --check` 통과 재확인 |
| `MODELS_LEDGER.md` | 정본 확정·짝비교 문구 교정·확정 처분 반영(프로젝트 지식 동기 업로드) |

검증:
- **판정 수치 재현**: `verdict_lowvol_20260829.py` 재실행 — 문서 전 수치와 완전 일치(§1·§2·§3·각주).
- **주블록 감도**: `verdict_blockboot_20260829.py` — lv_b 기움 유지, lv_c 역작동(유의) 생존,
  짝비교 생존 mom_a·lv_d·lv_c / 소멸 lv_a·lv_a3·sm_a·lv_short·hv_a (블록 6개 — 거친 추정임을 문서에 명시).
- **cross_sim 0-diff**: 게이트 패치판을 임시 출력으로 실행 → 기존 `docs/cross_sim.json`과 비교,
  **px_a 행 제거 외 전 패널·전 모델·벤치·KOSPI 값 완전 동일** 확인 후 실제 재생성.
- `py_compile` 통과(build_cross_sim.py·verdict_blockboot_20260829.py).

### 추가 (같은 세션 후속 결정): 신모델 공통창 C 패널

- `build_cross_sim.py` PANELS에 **"신모델 공통창 (8/10~ · 매우 짧음 — 참고 최소한)"** 추가
  (px_a 등록일 시작, 편입은 B 패널과 동일 8모델). px_a가 창 전체를 커버하는 공정 비교 제공.
- 검증: 임시 출력 실행 → **기존 A·B 패널 완전 동일(0-diff)** + C 패널 신규 확인
  (n=13, px_a exc +1.2%p — 기존 착시 -8.4%p와 대비). HTML은 panels 배열을 동적 렌더라 무수정.
- **판정 시즌 후 공통창 전체 개편 예정**(창 시작 재설정 · wu_b/mom_b/sv_a/le_a 등 편입 정리 —
  "트랙 대표 + 직접 비교쌍" 8/14 기준 재적용). 그 전까지 C 패널은 참고 최소한으로만 읽는다.

### 추가 2 (같은 세션): lowvol 화면 '목록 신선도' 배지

- 배경: 20260804~10 게이트 오탐 사건 때 표시 CSV 가 8/03자 목록으로 일주일 동결돼 있었고,
  사용자가 그 화면으로 매수했음을 실측 확인(research/RESEARCH_ptw_live_20260829.md §2-c).
  미적재일에 옛 CSV 가 그대로 남는 구조는 지금도 동일 → 화면에서 알려주도록 함.
- `build_lowvol_filter.py`: `docs/lowvol_meta.json`(run_id·생성시각) 추가 기록(추가만, py_compile OK).
  초기 메타는 이번 세션에서 실측 run_id(20260828)로 생성 — 다음 실행부터 빌더가 자동 갱신.
- `docs/lowvol.html`: 메타의 run_id 로 '목록 기준일' 상시 표시 + **주중 기준 2일 이상 밀리면
  경고 배지**(공휴일 오탐 가능성 문구 포함). 메타 없으면 조용히 숨김(구버전 호환).
- 검증: 정상(8/28)·경고(8/03 가정) 두 상태 렌더 확인. 판정·점수 0-diff(표시 전용).
- (후속, 같은 날) **lva·mom·wu·qs·px 5개 관측 페이지에도 동일 배지 이식**:
  build_lowvol_filter(메타명 suffix 기반으로 교정 — lva 재사용 시 충돌 방지)·build_mom_filter·
  build_wu_filter(출력명에서 메타명 유도: wu/qs/px)가 각자 {이름}_meta.json 기록, 초기 메타
  5개는 세션에서 실측 run_id(전부 20260828)로 생성. py_compile 통과.
- (연계) PTW v5.18: 라운드트립 분리 + 매수 시점 lowvol 순위 스냅샷(lowvol_meta.json 소비) —
  상세는 PTW repo PATCH_NOTES_v5.18.md.

### 추가 3 (같은 세션): 회귀 테스트 하네스 tests/ 도입

- `tests/test_lowvol_score_rules.py`(합성 — NaN 규칙·순위합·spec_hash 골든 10종) ·
  `tests/test_leaderboard_frozen.py`(실 DB — 게이트·REG_DATE·동결창 h20 IC 골든 3종·상수) ·
  `run_tests.py`(일괄, 실패 시 exit 1). 전체 32체크 통과 확인. 규칙: 골든 깨지면 골든이 아니라
  코드를 의심(tests/README.md). 판정·점수 0-diff(테스트는 읽기 전용).

### 추가 4 (같은 세션): sv_b(공매도+신용잔고) 사전등록 초안 + 배선 준비

- 근거: research/RESEARCH_candidates_scan_20260829.md — sh_credit_rate 단독 강기움(직교·지연
  무해 실측) + sv_a 결합만 "양+양→추가 개선"(h10/h20 짝diff CI>0).
- 산출물: PREREGISTER_sv_b.md(초안·**미등록**), research/sv_b_wiring_20260829.patch
  (git apply --check 통과). 검증: 사본 DB 원본 vs 패치 재적재 — 기존 6모델 6,584행 0-diff,
  sv_b 1,102행 신규, sv_a↔sv_b 순위상관 +0.659. crb5 는 적재 3일 지연 대응 min_periods=1
  (min3 이면 전부 중립화되는 결함을 검증 중 발견·교정).
- **적용·등록은 sv_a §11 판정(~9월 중) 후** — wu 분모 6→7 회피(판정 직전 등록 회피 원칙).
- MODELS_LEDGER 에 초안 행 추가(프로젝트 지식 동기 업로드).

### 추가 5 (같은 세션): 알파/베타 상시 관측 패널 + 예약 작업

- `build_alpha_beta.py` 신규 — v30·lv_b·wu_a 상위20 EW 일수익을 전종목 EW 벤치에 회귀,
  최근 40유효일 β·일α·t·누적 분해(장 덕/선택 덕)를 `docs/alpha_beta.json` 으로 매일 산출
  (근거 research/RESEARCH_forward_levers_20260829.md B — §14-4 '측정 인프라').
- `run_and_diversify.py` 2.916단계 추가(비치명) · `docs/leaderboard.html` 에 "📐 알파/베타 관측"
  섹션(쉬운 설명 박스 포함) · `notify_telegram.py` 에 α/β 한 줄(파일 없으면 조용히 생략).
- 검증: 생성 실행(asof 20260828 — v30 β0.72 α+0.28%/일 t1.04 · lv_b β0.75 α+0.36 t1.84 ·
  wu_a β0.32), 텔레 메시지 빌드 확인, 렌더 미리보기 확인, py_compile 통과. 표시 전용 0-diff.
- 예약 작업 등록: "sv_b 점화" — 2026-09-11 08:30 KST 1회 실행(sv_a 40일 도달 예상 익일).
  내용: wu 계열 §11 판정 → 사용자 확정 → sv_b 패치 적용·REG_DATE 확정·원장 갱신.

## 4. 영향 범위

- **판정·점수 0-diff.** leaderboard.py·lowvol_score.py·DB 무변경. lv_e 배선은 여전히 **미적용**.
- 표시 변화는 공통창의 px_a 제외 1건뿐(§11 판정표는 무변경 — px_a는 원래 14/40 표기).
  px_a는 등록일이 창 시작 이전이 되는 새 공통창이 생기면 자동 등장.
