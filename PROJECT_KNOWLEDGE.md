# PROJECT_KNOWLEDGE — dh-q7m3k (한국주식 과매도 스크리너)

> **용도**: 새 Claude Project의 "프로젝트 지식(파일)"으로 올려, 매번 맥락을 다시 설명하지 않고
> 작업을 이어가기 위한 핸드오프 문서. 코드 작업 시엔 **이 문서 + 최신 repo zip**을 함께 올린다
> (문서=무엇을/왜, zip=실제 현재 코드). 행동 규칙은 별도 "프로젝트 지침"에 둔다(PROJECT_INSTRUCTIONS).
>
> **최종 갱신 기준**: run_id 20260606. 반영 = 3.0(v3 표시), 3.1(챔피언/챌린저 섀도우), D2-②(DART
> 재무 캐시), catalyst_observe(인덱스+증분), A(촉매 수집 자동화 — 현재 **자사주 소각만**), B(섹터
> 전량 분류), 내부자(elestock) 비활성 결정, **§11 실험 판정 기준(40거래일) 사전등록**.
>
> **추가 갱신(2026-06-22)**: F1 챌린저 v31f(macd 이격도), F2 챌린저 v31g(거래량팽창), 관측팩터 2종
> (vol_1w_vs_1m_ratio·realized_vol), 파이프라인 2.72단계(observe_vol), 성숙도 팩터 보류, compare_models
> `--since`+h=20d. 골대는 별도 **PREREGISTER_v31f_maturity.md**. 점수 변경분 전부 챔피언 0-diff 검증.
>
> **추가 갱신(2026-06-23, 외부 코드·퀀트 감사 대응)**: 견고성 5종(점수·유니버스 불변=정상일 0-diff, 또는 가산). ① **git push allowlist**(`git add -- docs`). ④ **OOS 점수 동결저장**(`freeze_scores.py`+테이블 `v3_scores`, append-only·spec_hash; compare_models 동결값 읽기→드리프트 면역). **stage2 DART UNKNOWN**(에러/예외를 '위험없음'과 구분→추천 배제, fail-open 차단). **완전성 게이트**(행수 비정상↓이면 공개배포 보류). **종료코드 전파**(치명 단계/스테이지 실패 시 배포 보류). 상세 **§12**.
>
> **추가 갱신(2026-06-23 저녁, §12-2 후속 핫픽스 + 첫 §12 가동)**: §12 첫 프로덕션 런에서 §12-2 의
> `fetch_disclosures` **2-튜플 반환**(`list`→`(list, fetch_status)`) 변경이 두 곳의 미갱신을 드러냄 → 둘 다 수정.
> ① **accumulate 스키마 자가치유**: `stage2_filtered`·`stage3_final` 에 `dart_status` 컬럼이 없어 append
> 크래시 → `write_to_sqlite` 가 "CSV엔 있고 테이블엔 없는 컬럼"을 자동 `ADD COLUMN`(TEXT). **0-diff 검증**
> (수동 ALTER와 4테이블 바이트 동일·기존 run 불변), **수동 DB 작업 불필요**. ② **catalyst 튜플 언팩**:
> `catalyst_insider`·`catalyst_large` 가 튜플을 리스트로 받아 전 종목 실패(`'list'…get'`) → `discs,_=fetch_disclosures(...)`
> (자사주 소각=관측·비차단, **라이브 DART 미검증**). 부수: 게이트(§12-3)가 이 크래시의 부분적재(kosdaq stage1=0)를
> 잡아 push 보류 = 설계대로. 상세 **§12-6**.
>
> **추가 갱신(2026-06-25, 저변동 트랙 신설)**: v3·large 와 분리된 **제3 트랙 lowvol** 1단계 배포.
> 18일 진단서 발견한 신호(저변동·단기반전·ROE)를 순위합 5모델(lv_a~d·lv_a3)로 **관측 적재**(테이블
> `lowvol_scores`, 가중치 0). 견고성 1위 **lv_a** 만 v31g처럼 **테스트 텔레그램+전용 HTML(`docs/lowvol.html`)**
> 노출, 나머지 shadow. 전부 검증 전 섀도우(post-hoc→forward-only, 판정 OOS 40거래일). 파이프라인
> 2.86(적재)·2.87(CSV)·4b(텔레) 추가, **전부 비치명**. v3·large 산출물 **0-diff 불변** 검증. lv점수는
> "오른다"가 아니라 "시장 방향대로 증폭"(상승장 더 오름·하락장 덜 빠짐). 상세 **§13** + LOWVOL_TRACK_DESIGN.md.
>
> **추가 갱신(2026-06-25, 탐색/배포 분리)**: 도전적 가설 탐색이 검증 게이트에 막혀 죽지 않도록
> **research(게이트 면제·`research/` 산출물 한정·docs/·텔레·점수테이블 유출 금지) vs production(관측→40거래일
> OOS→CI/Bonferroni→0-diff) 분리** 원칙 명문화(§14). 탐색 백로그(우선순위): ①거래비용·세금 현실점검
> ②알파/베타 분해 ③베타 오버레이 ④트랙 앙상블 ⑤호라이즌 분리. **핵심 인식 = 병목은 종목선택이 아니라
> 시장 베타.** 점수·코드 0 건드림(지식 문서 추가, 0-diff).

---

## 0. 한 줄 요약
KOSPI/KOSDAQ에서 **과매도+턴어라운드 후보**를 매일 자동 발굴해 점수화·등급화하고, GitHub
Pages 대시보드 + 텔레그램으로 보는 개인 파이프라인. 점수는 **v2.6(원본)** 위에 **v3(등급/버킷)**
를 얹은 2층 구조이고, 그 위에 **챔피언/챌린저 섀도우 실험틀**과 **가중치 0 관측 팩터**(나중에
데이터로 승격 판단)가 붙어 있다.

---

## 1. 환경 / 실행

- **repo**: `dh-q7m3k` · GitHub `github.com/sj951027/dh-q7m3k` · Pages `https://sj951027.github.io/dh-q7m3k/` (필터 `docs/filter.html`)
- **실행 주체**: 사용자 Windows PC. 매일 `run_all_and_diversify.bat`(= `python run_and_diversify.py`).
- **언어**: 모든 대화/주석/로그 한국어.
- **run_id 규칙**: 날짜 `YYYYMMDD`(예: 20260606). 누적 테이블·아카이브 폴더 키.
- **텔레그램**: 그룹 "screener", chat_id `-1004202649026`, bot `@sjk_screener_bot`.
- **소요(20260606 실측)**: 스크리너 ~14분 + v3 7초 + 섀도우 1초 + diversify 3초 + 촉매(2.68)
  ~5분(내부자 포함 시) + catalyst_observe 1초 + IC 2.4분 + 대시보드/푸시/텔레그램.
  → **자사주 전용이면 2.68이 ~절반(~2.5분)**.

### Claude(나)의 협업 제약 — 중요
- **나는 네트워크가 없다.** DART/KRX/네이버 호출 스크립트(stage1~3, fetch_valuation, v3_daily,
  compute_ic, catalyst_insider)는 실행 못 한다. 결과가 필요하면 사용자에게 '실행 + 로그·zip'을 요청한다.
- **오프라인 검증 가능**: history.db만 있으면 되는 것 — build_dashboard, diversify(캐시 히트 시),
  v3_backtest, v3_rescore(재계산 동일성), compare_models, catalyst_observe, 점수/IC 로직 단위검증.
- **zip 주의**: 이 repo zip은 **zip64**라 리눅스 `unzip`이 실패한다. **항상 Python `zipfile`로 추출**
  (`.git/`까지 풀면 `git ls-files`로 추적상태 확인 가능). history.db ≈ 46MB.

---

## 2. 파이프라인 (단계 순서 = run_and_diversify.py)

1. **1단계** `run_all_v2_6.py` — 스크리너 3스테이지(코스피+코스닥) → 누적(accumulate_history) → 1차 대시보드.
   - stage1 `screener_fdr_v2_6`: 과매도+레짐+환율+외인+수급(네이버) → `stage1_oversold`
   - stage2 `stage2_risk_filter_v2_6`: DART 공시 위험필터(가짜악재 방어) → `stage2_filtered` + `v2_{mkt}_filtered_safe_*.csv`
   - stage3 `stage3_fundamental_momentum_v2_6`: 분기 YoY + OCF + v2.6 `final_score` → `stage3_final` (**stage2 SAFE 생존분만**)
2. **2.6단계** `v3_daily.py` → `fetch_valuation.py` → `v3_rescore.py`(final_score_v3/grade/bucket) → `v3_merge.py`
3. **2.65단계** `shadow_run.py` — 챌린저(v31a~d·**f·g**) 섀도우 누적(조용, ~0 네트워크). MODELS 자동 순회라 새 챌린저 자동 포함.
3b. **2.66단계** `freeze_scores.py --latest` — 방금 만든 archive(챔피언+챌린저)의 **그날 얼린 점수를 DB `v3_scores`에 append-only 적재**(드리프트 면역 OOS). 점수·로직 불변(가산). *(2026-06-23)*
4. **2단계** `diversify_picks.py` — 섹터 쏠림 방지 추천(업종당 최대 N, top개)
5. **2.68단계** `catalyst_insider.py` — **촉매 수집(현재 자사주 소각만)** → `catalyst_{mkt}_{run_id}.csv` *(A에서 추가)*
6. **2.7단계** `catalyst_observe.py` — 관측 팩터를 stage3_final에 배선(가중치 0, 점수 불변)
6b. **2.72단계** `observe_vol.py` — `realized_vol` 관측 컬럼 채움(가중치 0, 점수 불변, 증분). *(2026-06-22 추가)*
7. **2.5단계** `compute_ic.py` — 점수 적중도(IC) 계산
8. **2.8단계** `build_dashboard.py` — v3 반영 대시보드 재생성
9. **3단계** git push  →  **4단계** `notify_telegram.py`. **단, push 직전 배포 게이트**(§12): 완전성(행수)+치명단계 rc 점검 → degraded/실패면 push·평소텔레 **보류** + '보류' 알림(DB 기록은 남김). *(2026-06-23)*

### 누적 DB (history.db, SQLite)
- 테이블: `stage1_oversold`, `stage2_filtered`, `stage3_final`, `runs`. 아카이브 CSV는 `archive/날짜/`.
- **인덱스**: `idx_stage3_mrt ON stage3_final(market, run_id, ticker)` — catalyst_observe가 1회 생성. UPDATE 풀스캔 방지. **observe_vol도 이 인덱스를 쓴다**(키 (market,run_id,ticker) — market 빠지면 풀스캔이라 주의).

---

## 3. 점수 체계

### v2.6 `final_score` (원본 엔진 — 절대 삭제 금지)
과매도+매집+추세+수급+펀더+모멘텀+OCF+레짐. **v3가 이것을 입력으로 계산**하므로 지우면 안 됨.

### v3 (현재 사용자 노출 기준)
`final_score_v3` + `grade`(A+/A/B/C/WATCH/EXCLUDE) + `bucket`(BUY/WAIT/OBSERVE/WATCH/EXCLUDE).
- **사용자 표시는 모두 v3**(텔레그램/대시보드/필터). v2.6 final_score는 보존(필터 '옛최종' 오염 방지)하되 표시는 v3.
- **regime_score는 (run,market)마다 상수** → 같은 날 종목 간 랭킹 영향 없음 → v3는 제외.
- 텔레그램 정렬 = 의도된 2키(bucket BUY→WAIT, 그다음 final_score_v3 내림차순).

### 관측 팩터 (가중치 0 — 점수식에 안 들어감)
`catalyst_observe.py`가 stage3_final에 채움. **final_score_v3 계산에 절대 미사용**(v3_rescore/v3_merge
참조 0회, 검증됨). 대시보드/텔레그램 미표시 → 사용자 오해 없음. IC가 좋으면 **v32 승격** 후보.
- `smartmoney_score`(0~15): 과매도+거래대금폭발+양봉+수급. stage3 컬럼만으로 계산 → 전 run 채움.
- `roe_value`(%)=EPS/BPS×100(자본잠식 BPS≤0=NaN). `roe_gate`=PBR<1 & ROE≥8%. valuation_*.csv 있는 run만.
- `insider_score`/`insider_source`: **현재 비활성(OFF)** — §4-A 참고.
- `buyback_cancel_flag`(0/1): 자사주 **소각** 공시. catalyst_*.csv 있는 run만.
- `vol_1w_vs_1m_ratio`(거래량 팽창 = 5일/21일 평균거래량): **기존 stage3 컬럼**, FACTOR_COLUMNS 등록만(채움 불필요). 가설: 팽창→+IC(거래량 동반 반등). **발견=낚시(post-hoc)** → PREREGISTER E-1. *(2026-06-22)*
- `realized_vol`(trailing 21 활성런 종가수익률 std): `observe_vol.py`(2.72)가 채움. low-vol 가설 검정(부호는 데이터에 맡김). 커버리지 ~43%(가격이 과매도 패널에만 → 최근 윈도우 머문 종목; 신규 pending). *(2026-06-22)*
- validate_scores의 `FACTOR_COLUMNS`에 위 6개 등록 → IC 하니스 자동 측정.

### IC 현실 인식 (기대치 조정)
- v2.6 final_score 단기 IC는 음(–)에 가까웠고, v3는 ≈0~약간+. v3는 "방향이 거꾸로였던 것"을
  바로잡았지만 **절대 엣지는 ≈0**(나쁜 종목 걸러내기엔 좋고, 버킷 내 미세 랭킹 예측력은 약함).
- 13일치로는 **표본 부족** → IC 카드 "데이터 쌓는 중". **판정은 §11(40거래일) 기준.**

---

## 4. 주요 모듈 & 의사결정

### 4-A. `catalyst_insider.py` — **현재 '자사주 소각'만 (내부자 매수 비활성)**
- 산출 `catalyst_{mkt}_{run_id}.csv`. catalyst_observe(2.7)가 읽어 insider/buyback 컬럼 채움(병합 로직 존재).
- run_id 기본값 = **최신 stage3 run**(누적/자정경계 정합). 종목당 DART: 자사주만 1회(공시목록),
  `--with-insider` 켜면 2회(+elestock). 병렬 2스레드, sleep 0.05.

**왜 내부자 매수를 끄는가 (institutional knowledge — 되살리지 말 것):**
- elestock(임원·주요주주 소유보고) 요약은 **소유수 '증감'만** 줄 뿐 *사유*를 구분 못 한다:
  장내매수(호재) / **무상증자·주식배당(중립)** / 상속·증여 / 스톡옵션행사 / 분할이 전부 "증가"로 찍힘.
- 무상증자는 최대주주 포함 전원의 보유수를 늘려 "내부자 매집"으로 **오판**된다(흔해서 오염 큼).
- 비율(%)로 거르면 무상증자는 빠지지만, **대형주의 진짜 장내매수는 반올림 0.00**으로 같이 사라진다.
- → elestock 요약만으로는 호재성 매수를 깨끗이 정제 불가. **사용자가 이전에 같은 이유로 뺐던 판단이
  옳다.** 그래서 기본 비활성, 해석 여지 없는 '자사주 소각'만 사용.
- (과거 "전 종목 insider 0"의 직접 원인은 **별개의 날짜 파싱 버그**: elestock `rcept_dt`가
  `YYYY-MM-DD`(하이픈)인데 코드가 `YYYYMMDD`로 가정해 `[:8]` → 파싱 실패로 전부 스킵. **수정 완료**,
  `--with-insider` 경로 정상. 단 위 정제불가 한계로 **기본은 여전히 OFF**.)
- 자사주 소각 탐지는 검증됨(20260606 실측 100건). `buyback_cancel_flag`는 유지 가치 큼.

### 4-B. `catalyst_observe.py` — 인덱스 + 증분 (성능)
- 과거 8분55초 원인: stage3_final 인덱스 없음 → UPDATE 풀스캔 + 매번 전 run 재백필(O(n²)).
- 수정(결과 불변, 검증): ① `idx_stage3_mrt` 인덱스(1회) ② **이미 채워진 run은 건너뛰기**. 매일 새 run
  1개만 처리 → **~0.7~1초**.
- 채움 판정: smartmoney(전부 채워짐=완료), roe(roe_gate 1개라도 있으면 완료), catalyst(insider_source
  1개라도 non-null이면 완료). **함정**: insider_source가 "NONE"/"OFF"여도 non-null → "채워짐"으로 봄.
  과거 run의 catalyst를 **덮어쓰려면 `python catalyst_observe.py --full`** 필요.

### 4-C. `diversify_picks.py` — 섹터 전량 분류 (B)
- 과거 "미분류 1493개"는 버그 아님 = **의도된 절약**(점수 상위 `max(top*6,60)`개만 FDR/DART 조회).
- B 변경: override/`sector_cache.json`에 **있으면 전 종목 공짜로 채우고**(네트워크 0), 남은 미분류 상위만 네트워크.
- 효과(검증): 미분류 1493→~4, **top-20 추천 불변**, 필터 섹터 토글 ~14%→~100%.
- `sector_cache.json`은 현재 universe 100% 커버. `sector_overrides.csv`(수동)는 없어도 됨.

### 4-D. `dart_cache_util.py` — DART 재무 캐시 (D2-②)
- stage3 `_request_json` 래핑. **키 = url + (crtfc_key 제외) 정렬 params**(연도/보고서코드 포함).
- '000' 길게(`DART_FIN_TTL_DAYS` 기본 14일), '013' 짧게(`DART_NODATA_TTL_HOURS` 기본 12h),
  **에러는 캐시 안 함**. 미스 경로는 캐시 이전과 100% 동일. 실측: 같은 날 재실행 stage3 172s→51s.
- 환경변수: `DART_NO_CACHE=1`(끄기), `DART_CACHE_DIR`. `dart_cache/`는 gitignore.

### 캐시 안전성 요약 (질문 재발 방지)
- **재무 캐시**: 키에 보고서 기간 포함 → **제출 보고서는 불변** → 14일 캐시해도 정확. 미제출은 12h마다
  재확인 → 새 보고서 곧 반영. **안전.**
- **corp_code 매핑 캐시**(`dart_cache/corp_code.csv`): **30일 미만 재사용**(로그 "기업코드 매핑 사용 (N일 전)").
  거의 안 변함 → 6~7일 캐시 **OK**. 유일 영향 = 최근 며칠 신규상장 누락(IPO 직후는 과매도 후보 아님,
  30일 내 자동 갱신). 강제 갱신 = `dart_cache/corp_code.csv` 삭제.
- **sector_cache.json**: TTL 없음(영구), 현재 universe 100% 커버.

### 4-E. `observe_vol.py` — realized_vol 관측 컬럼 (2026-06-22)
- 가격패널(stage1_oversold) trailing 21 **활성런**(v3_backtest와 동일 정의) 종가수익률 std → `realized_vol`. 점수 미사용(가중치 0).
- ALTER 1회 + `(market,run_id,ticker)` 키 UPDATE(idx_stage3_mrt 사용) + `executemany`. idempotent(미채움 run만 증분, `--full` 전체).
- 동결값 WINDOW=21·MIN_OBS=8. PIT 안전(run R 시점까지만). 커버리지 ~43%(과매도 패널 한정 — 신규 편입 pending).
- **초기 버그(수정됨)**: UPDATE WHERE 에 market 누락 → §4-B와 같은 풀스캔으로 멈춤. 3키 WHERE로 인덱스 사용 → ~3초.

---

## 5. 챔피언 / 챌린저 섀도우 실험틀 (3.1)

목적: 점수 모델 변경을 **실거래/실표시 영향 없이** 그림자로 누적해, 충분한 표본 뒤 IC/수익으로 채택 판단.

- **v3_rescore.py**: spec 주도. `SPEC_V30`=현재 챔피언 상수. `MODELS` 레지스트리. `rescore(df, run_id,
  market, spec=None, ...)` — spec=None이면 SPEC_V30 → v3_daily/v3_merge/v3_backtest는 **현 챔피언과 동일**.
- **챌린저(각각 v30 + 변수 1개)**:
  - `v31a` E2 반전확인 진입게이트(BUY는 실제 반전 플래그 충족 시만)
  - `v31b` E3 수급가중↑(w.supply 1.0→1.6)
  - `v31c` E4 유동성하한(LIQ_FLOOR=5.0억)
  - `v31d` E5 섹터중립화(섹터 내 demean) — **B 덕에 섹터 전량 채워져 공정 평가됨**
  - `v31f` **F1 macd 이격도 가산**(vs_SMA20−vs_SMA50 셀내 z(±3)×`MACD_TILT_W=6.0`) — 발견=영상룰 번역, post-hoc *(2026-06-22)*
  - `v31g` **F2 거래량팽창 가산**(vol_1w_vs_1m_ratio 셀내 z(±3)×`VOLEXP_TILT_W=7.0`) — 발견=관측팩터 낚시, post-hoc *(2026-06-22)*
- **shadow_run.py**: v3_daily 직후 최신 run을 챌린저별 재점수 → `{model}_archive/` (v30 제외, ~0 네트워크).
- **compare_models.py**: history.db 전체 재계산, 3개 표 + `docs/model_compare.json`. **`--since YYYYMMDD`**(OOS 판정용)·**h=20d 컬럼** 지원(2026-06-22). **(2026-06-23) 점수 동결값(`v3_scores`) 우선 읽기**(없으면 재계산 폴백·`--recompute` 강제·출처 표기) → 재계산이 입력 드리프트(value_score=0 등)에 오염되던 문제 해소.
  1. 전 종목 IC(final_score_v3) — E3/E5 / 2. BUY-only 시장초과수익+n — E2 / 3. BUY+WAIT 수익+n — E4
- **검증 사실**: 리팩터 v30 == 원본 **0 diff**(전 run). v31f·v31g 추가도 v30·v31a~d **0 diff**(32,373행). 단기치는 **순수 노이즈** → **§11(40거래일)으로 판정**. 챌린저 **6개**(v31a~d·f·g) → 다중검정 Bonferroni 분모 6. **v31f/g·거래량팽창은 post-hoc라 forward-only·소급 금지**(PREREGISTER 참조).

---

## 6. 불변 규칙 (작업 시 반드시 지킬 것)

1. **v2.6 엔진 절대 삭제 금지**(v3가 그 위에서 계산).
2. **챌린저 spec은 시작하면 동결**(과거 가중치 변경 = look-ahead → 새 모델 id로).
3. **챌린저 1개 = 변수 1개만**.
4. **캐시 미스 경로는 캐시 이전과 100% 동일**(가속만, 에러 캐시 금지).
5. **사용자 표시는 v3 유지**.
6. **관측 팩터는 점수식에 절대 투입 금지**(승격은 데이터로만, 새 모델 id).
7. **출력 동일성 우선**: 성능/리팩터 변경은 "결과 0 diff" 오프라인 증명 후 적용.
8. **post-hoc(낚시)로 찾은 팩터/챌린저는 forward-only·소급 금지** — in-sample 수치는 가설이지 OOS 증거 아님(같은 표본 재사용 금지). *(2026-06-22)*
9. **단, 관측 컬럼 백필(--full)은 허용**(점수 불변·판정은 forward만). 이는 챌린저 archive의 '소급 금지'(archive를 OOS로 *세는* 문제)와 차원이 다름. *(2026-06-22)*

---

## 7. .gitignore (비대화 방지)
- 데이터 CSV는 history.db에 값이 들어가므로 ignore: `valuation_*.csv`, `catalyst_*.csv`(추가됨) 등.
- 챌린저 아카이브 `v31a_archive/`~`v31d_archive/` + **`v31f_archive/`·`v31g_archive/`**(2026-06-22)도 ignore. 이미 추적된 건 `git rm -r --cached`로 1회 정리 완료.
  **새 챌린저(v32a 등) 추가 시 같은 식으로 한 줄 추가.**
- **(2026-06-23) git push allowlist**: `run_and_diversify.py` git_push 가 `git add -A` 대신 **`git add -- docs`**(PUSH_ALLOWLIST). docs/만 커밋 → 작업중 코드·잡파일 자동커밋 방지. **코드 변경은 `git add <파일>` 명시 커밋 필요.**
- `dart_cache/`도 ignore.

---

## 8. 향후 작업 (우선순위)

| 우선 | 항목 | 게이트/메모 |
|---|---|---|
| ★ 주력 | **E1 관측 팩터 IC 수확** | **§11 기준(40거래일)** 충족 시, `smartmoney_score`/`roe_value`/`buyback_cancel_flag`/`vol_1w_vs_1m_ratio`/`realized_vol` 중 일관 양(+)인 팩터를 IC비례 가중으로 **v32 승격**. (insider는 OFF라 제외.) FACTOR_COLUMNS 등록 완료. **다음 메인 마일스톤.** |
| ★ | **챌린저 판정(E2~E5·F1·F2)** | 주 1회 `compare_models.py`로 추세만, **§11 기준(40거래일)**에서 채택/폐기. F1/F2(v31f·v31g)는 **post-hoc → `--since` 로 OOS만** 봐야 정직. |
| 중 | E6 단기반등 vs 중기턴어라운드 이중 모델 | 더 큰 작업. E1로 어떤 팩터가 먹히는지 안 뒤에. |
| 중 | E7 내부자/자사주 이벤트 스터디 | 자사주 소각 누적 후 가능. 내부자는 OFF라 데이터 미축적 — 하려면 `--with-insider`로 켜야 하나 §4-A 한계로 비권장. |
| 낮 | sector_overrides.csv 수동 보정 | B로 대부분 해결. 상위 후보 중 미분류 보일 때만. |
| 낮 | D2 동시성 튜닝 | 네트워크라 내가 검증 불가, 캐시로 일상 빨라 우선순위 낮음. feature-flag + 직렬 폴백 + before/after 0 diff. |
| 운영 | 일일 `.bat` / 주간 `compare_models.py` | 챔피언 v30 운영, 챌린저·관측 자동 누적. |

---

## 9. 운영 치트시트

```bash
# 매일 (Windows)
run_all_and_diversify.bat            # = python run_and_diversify.py
# 주 1회 — 챌린저 비교(추세만, 판정은 §11/40거래일)
python compare_models.py
python compare_models.py --since 20260622   # §11 OOS 판정용(등록 이후만; h=20d 포함)
# 실현변동성 관측 컬럼 최초 백필(이후는 .bat 2.72가 증분 자동)
python observe_vol.py --full
# 촉매(자사주 소각만) 단독 재수집
python catalyst_insider.py                 # 기본: 자사주 소각만, 최신 run
python catalyst_insider.py --with-insider  # (비권장) 내부자 평가도 켜기
# 과거 run catalyst 강제 덮어쓰기
python catalyst_observe.py --full
# 캐시 강제 갱신
del dart_cache\corp_code.csv          # 기업코드 매핑 새로 받기
set DART_NO_CACHE=1                    # 재무 캐시 임시 끄기
```

---

## 10. 변경 이력
- **3.0** 사용자 표시 v2.6 → v3 전환 + 버그픽스.
- **3.1** 챔피언/챌린저 섀도우 틀(v3_rescore spec화, shadow_run, compare_models). v30 == 원본 0 diff.
- **D2-②** DART 재무 캐시 — stage3 가속, 결과 불변.
- **catalyst_observe** 인덱스 + 증분 — 8분55초 → ~1초, 0 diff.
- **A** 촉매 수집 자동화(2.68). 현재 **자사주 소각만**(§4-A 근거). run_id=최신 stage3.
- **B** diversify 섹터 전량 분류 — 미분류 1493→~4, top-20 불변.
- **버그픽스** elestock 날짜 파싱(하이픈) — `--with-insider` 정상화(기본 OFF 유지).
- **§11 사전등록** 실험 판정 기준 = **40거래일** 고정.
- **F1/v31f**(2026-06-22) macd 이격도 챌린저(섀도우, 0-diff). **F2/v31g** 거래량팽창 챌린저(섀도우, 0-diff).
- **관측팩터 2종**(2026-06-22) vol_1w_vs_1m_ratio·realized_vol + `observe_vol.py`/2.72단계. (observe_vol 초기 풀스캔 버그 → 3키 WHERE로 수정.)
- **성숙도(maturity) 보류**(2026-06-22): maturity proxy vs_SMA200 IC −0.06(평균회귀 레짐 부호 반대) → 추세장 전환 시 재검토(새 id·새 사전등록).
- **compare_models `--since`+h=20d**(2026-06-22). **PREREGISTER_v31f_maturity.md** 신설(골대 고정).
- **견고성 5종 (2026-06-23, 외부 감사 대응)** — §12:
  - **#1 git push allowlist**(`git add -- docs`).
  - **#4 OOS 동결저장**: `freeze_scores.py` + 테이블 `v3_scores`(append-only·spec_hash) + 파이프라인 2.66 + compare_models 동결읽기. 백필 완료(7모델 86,457행).
  - **stage2 DART UNKNOWN**: dart_status(SAFE/RISK/UNKNOWN)·UNKNOWN 추천배제·커버리지 게이트. fail-open 2종(에러응답·검사예외) 차단. 정상일 0-diff.
  - **완전성 게이트**: stage1/stage3 행수 < 최근 중앙값×0.5면 공개배포 보류(6/8형 차단). 정상일 무영향.
  - **종료코드 전파**: run_all `sys.exit(0 if all_success else 1)` + 치명 단계(v3_daily·diversify·build_dashboard) rc→배포보류. 비치명은 로그+계속.
- **§12-2 후속 핫픽스 (2026-06-23 저녁, 첫 §12 가동일 발견·수정)** — §12-6:
  - **accumulate 스키마 자가치유**: `write_to_sqlite` 가 CSV 신규 컬럼을 자동 `ADD COLUMN`(TEXT) → `dart_status` 누락 append 크래시 해소. **0-diff**(수동 ALTER와 stage1/2/3/runs 4테이블 바이트 동일·기존 run 불변), 수동 DB 작업 불필요·동종 컬럼 추가 영구 흡수.
  - **catalyst 2-튜플 언팩**: `catalyst_insider`·`catalyst_large` 가 `discs,_=fetch_disclosures(...)` 로 언팩 → `'list'…get'` 전 종목 실패 해소(관측·비차단, 라이브 DART 미검증).
  - **첫 §12 가동 검증**: 완전성 게이트가 부분적재(kosdaq stage1=0) 공개배포 정상 차단 → §12-3·§12-4 라이브 1회 확인분 충족.

---

## 11. 실험 판정 기준 (사전등록 — 골대 고정용)

> 나중에 결과 보고 기준을 바꾸지 않으려 **미리** 못 박는다. **40거래일은 '가장 이른 판정 시점'**이지
> 유의성 보장이 아니다 — 경계값은 '채택'이 아니라 '기움(lean)'으로만 본다.

- **판정 시점**: 챔피언 도입(20260606) 이후 **OOS 40거래일**(약 2개월) 누적 후 1차 판정. 그 전엔 노이즈로 간주.
- **주력 지표**: 전 종목 Spearman IC. **사전 고정 호라이즌 = h=20d**(보조로 h=5d 같이 본다). 데이터가
  가장 많아 검정력이 있음.
  - 보조(부호 일치 확인용): BUY+WAIT 평균 시장초과수익(h=20d).
- **채택 조건(챌린저별, 모두 충족)**:
  1. 40거래일 OOS에서 `평균(IC_챌린저 − IC_챔피언)`의 **부트스트랩 95% CI(날짜 리샘플)가 전부 0 초과**(h=20d).
  2. 주별 방향 일관성 **≥ 60%**.
  3. 보조 지표(BUY+WAIT 수익) 부호가 주력과 **상충하지 않음**.
- **다중검정(챌린저 6개: v31a~d·f·g)**: 위 CI를 **≈99%(=0.05/6, Bonferroni)**로 올리거나, **별도 보유기간에서 재현**될
  때만 **최종 채택**. 둘 다 못 넘으면 '기움'까지만 표기. *(v31f·v31g 추가로 4→6 갱신, 2026-06-22)*
- **BUY 희소성**: 20260606 BUY=1개 → **E2(v31a)는 BUY-only 수익으로 수개월간 판정 불가**. E2는
  'BUY+WAIT 집합 개선' + 정성검토로만 보고, BUY-only 숫자에 의존하지 않는다.
- **무판정도 결론**: 40거래일(필요시 연장)에 아무도 기준을 못 넘으면 **챔피언 v30 유지** — 정상적이고
  바람직한 결과(과적합 방지).
- **채택 절차**: 기준 충족 시에도 즉시 교체하지 않고, 그 챌린저를 **새 챔피언 후보로 1주 관전** 후 반영.
  반영 시 변경분은 불변 규칙 2(spec 동결)를 따른다.

### 11-A. post-hoc(낚시) 챌린저 정직성 + compare_models 주의 (2026-06-22)
> v31f·v31g·거래량팽창은 **사후 발견**(여러 후보 훑어 고름)이라 일반 챌린저보다 엄격히 다룬다.
> 상세 골대는 **PREREGISTER_v31f_maturity.md**(A·E·F절).

- **forward-only·소급 금지**: 발견 표본(≈~0619까지)의 in-sample IC는 **증거가 아니라 가설**. OOS 판정엔 등록일(≈20260622) 이후만 쓴다.
- ⚠️ **compare_models 해석**: 이 스크립트는 IC를 **전체 history(발견 기간 포함)** 로 계산한다 → 리더보드에서 v31f/v31g가 챔피언보다 높아 보이는 건 **부분적으로 발견표본 때문**(판정 아님). **반드시 `python compare_models.py --since 20260622`** 로 OOS 구간만 보고 판정한다. (실측: --since 로 발견기간 빼면 v31f/g 우위가 사라짐.)
- **h=20d 주력 미성숙**: 현재 h=20d 계산 가능 셀 **0개**. 그 전 모든 숫자(h≤5d)는 보조이고 노이즈로 간주.
- **낚시 출신 추가 기준**: Bonferroni 0.05/6 + **별도 호라이즌(h=10d) 재현**까지 봐야 '유의'.

---

## 12. 견고성 레이어 (2026-06-23 외부 코드·퀀트 감사 대응)

> 외부 감사 지적 중 **타당하고 적용 가능한 것**만 반영. 전부 **점수·유니버스 불변**(정상일 0-diff)이거나 **가산**(새 테이블/컬럼)이라 챔피언 spec 동결을 안 깬다.
> (감사의 "팩터 중복 가중" 지적은 v3엔 오진 — v3 실제 6컴포넌트 상호상관 최대 0.33, reversal↔oversold −0.46으로 직교. 높은 상관은 v3컴포넌트↔그 v2.6 원시입력 간이며 최종점수에 중복 합산 안 함.)

### 12-1. OOS 점수 동결저장 (감사 #5 — 가장 강한 지적)
- **문제**: v3 점수가 archive CSV(gitignore)에만 있고, compare_models 가 과거를 **현재 코드로 재계산** → 입력(valuation 등) 드리프트 시 재계산 ≠ 그날 값 → OOS 판정 오염.
- **해결**: `freeze_scores.py` 가 그날 archive 원본(=실제 표시·판정값)을 DB 테이블 **`v3_scores`**(키 run_id·market·ticker·model_id, **append-only**, spec_hash 동반)에 적재. 재계산이 아니라 **원본 보존 → 드리프트 면역**.
  - 이미 있으면 안 건드림(최초 동결값=진실). spec_hash 불일치 시 경고(동결 스펙 변경 탐지).
  - 플래그: `--backfill`(전체 1회)·`--latest`(매일 2.66)·`--verify`. **백필 완료**: v30 22,133 / v31a~d 각 15,430 / v31f·g 각 1,302 = **86,457행**, 전 모델 spec_hash 1종.
- **compare_models 페이로프**: 점수 **동결값 우선 읽기**(없으면 재계산 폴백·`--recompute` 강제·출처 표기) → §11 판정이 드리프트 면역. (단 §11-A 의 `--since`(발견/OOS 분리)는 여전히 필요 — 동결읽기는 *드리프트*를, --since 는 *발견기간 제외*를 담당.)

### 12-2. stage2 DART UNKNOWN (fail-open 차단 — 안전)
- **문제**: `fetch_disclosures` 가 DART 에러(010/020/800/900)·네트워크 예외 시 **빈 목록 → "위험 없음" → SAFE 통과**. "위험 없음"과 "확인 불가"가 안 구분됨.
- **해결**: fetch 가 `(disclosures, fetch_status)` 반환(000/013=ok, 그 외/예외=unknown). `dart_status`=SAFE/RISK/**UNKNOWN**. **UNKNOWN 은 추천 유니버스(safe_with_caution)에서 배제** — 검사 예외로 merge 에서 빠진(NaN) 종목까지 포함(2종 fail-open 차단). 정상 응답일엔 UNKNOWN 0 → **기존과 0-diff**.
- **커버리지 게이트**: UNKNOWN 비율 > `UNKNOWN_GATE_FRAC`(0.10)면 "DART 불안정 — 재실행 권장" 경고. 개수 매 run 로그 → stage2 실패율 자동 측정(과거는 기록 없어 측정 불가, 프록시 stage3 재무 99.7% ok → 드묾).

### 12-3. 완전성 게이트 (degraded 배포 보류 — 안전)
- **문제**: 6/8 처럼 stage1 이 75/20행(평소 720/1550)인데 **종료코드 0(degraded 성공)** 으로 저장·배포됨. 종료코드만으론 못 잡음.
- **해결**: `run_and_diversify.check_completeness()` 가 push 직전 stage1·stage3 행수를 **시장별 최근 중앙값과 비교**, `floor_frac`(0.5) 미만이면 degraded → push·평소텔레 **보류** + '보류' 알림(침묵 금지), **DB 기록은 남김**(어제 대시보드 유지). 점검 자체 에러는 통과(게이트 버그가 정상 run 안 막게). **정상일 무영향**(검증: 6/8 보류·0622 통과).

### 12-4. 종료코드 전파 (하드 크래시 — 완전성 게이트 보완)
- **문제**: run_all 이 `all_success` 추적만 하고 `sys.exit` 안 함 → 스테이지 하드 실패해도 0 반환 → run_and_diversify 1단계 검사 무력.
- **해결**: run_all `return 0 if all_success else 1` + `sys.exit(main())`(조기 실패도 `return 1`). run_and_diversify 는 **치명 단계**(run_all 하드중단 / v3_daily·diversify·build_dashboard rc→`deploy_ok=False`)만 배포 보류, **비치명**(shadow·freeze·catalyst·observe·compute_ic·v3_backtest·build_v31g)은 **로그+계속**(챌린저 버그로 챔피언 배포 안 멈춤). 배포 게이트 = `치명실패 OR degraded`.
- **남은 1회 확인(사용자)**: 실제 종료코드 전파(실패한 날 push 보류)는 라이브 1회 확인 — 정상일엔 전부 0 → 기존과 동일.

### 12-5. 보류/미적용 (낮은 우선순위)
- **#2 결측→플래그**: valuation 결측 → value_score=0 은 "결측"과 "중립"을 섞음. **챔피언 점수 변경**이라 챌린저/관측으로만. 라이브 결측률 측정 먼저(매일 valuation 받으니 작을 듯) → 십중팔구 `value_source` 플래그 노출로 충분(Bonferroni 낭비 방지). **미적용.**
- **stage3 재무 REQUEST_ERROR 전파**: 영구 에러→`not_found` 로 뭉개짐(약한 fail-open). 단 재시도(1→3→9초)로 완화 + 결과가 *점수 중립*(안전 우회 아님) + 99.7% ok → **급하지 않음**(선택).
- **kis_flows(대형 트랙)**: 에러 미저장·다음날 재시도·토큰실패 raise = **fail-safe 모범**. 손댈 것 없음.

### 12-6. §12-2 후속 핫픽스 (2026-06-23 저녁 — 첫 §12 가동일 발견·수정)
> §12 첫 프로덕션 런에서 §12-2 의 `fetch_disclosures` 반환 시그니처 변경(`list` → `(list, fetch_status)` 2-튜플)이
> **두 곳의 미갱신**을 드러냄. 둘 다 수정. **교훈: 반환형을 바꾼 함수는 모든 호출부 + 적재 DB 스키마를 함께 본다.**

- **증상 A (차단)**: `accumulate_history.py` 가 stage2 append 에서 크래시 — `table stage2_filtered has no column named dart_status`. §12-2 가 stage2/3 산출 CSV 에 `dart_status` 컬럼을 추가했는데 history.db 의 `stage2_filtered`·`stage3_final` 테이블엔 그 컬럼이 없었음(스키마 미마이그레이션). stage3 CSV 도 stage2 SAFE 출력을 이어받아 `dart_status` 를 들고 옴 → **stage2 만 ALTER 하면 stage3 에서 2차 크래시**(오프라인 시뮬레이션으로 확인).
  - **해결(스키마 자가치유)**: `write_to_sqlite` 가 적재 직전 **CSV 엔 있고 테이블엔 없는 컬럼을 `ALTER TABLE … ADD COLUMN "<col>" TEXT` 로 자동 추가**(기존 행 NULL). dart_status 뿐 아니라 **앞으로의 동종 컬럼 추가도 자동 흡수** → 이 부류 크래시 영구 차단, **수동 ALTER 불필요**.
  - **검증(0-diff, 오프라인)**: 패치본(자동 ADD) 적재 결과 == 수동 ALTER 2개 후 적재 결과, `stage1/stage2/stage3/runs` **4테이블 바이트 동일**, 기존 run 총행수 불변. 정상일(컬럼 누락 0)엔 ALTER 미발생 → 기존과 동일. (TEXT 어피니티 — 현재 추가 컬럼 dart_status 는 문자열이라 적합. 향후 수치 컬럼이면 affinity 만 유의, SQLite 동적타입이라 적재는 정상.)
- **증상 B (비차단·관측)**: `catalyst_insider.py`(404)·`catalyst_large.py`(122) 가 `discs = stage2.fetch_disclosures(...)` 로 튜플을 리스트처럼 받음 → `score_buyback_cancel` 이 튜플을 순회하다 첫 원소(리스트)에 `.get` → **`'list' object has no attribute 'get'` 전 종목 실패**(0623 자사주 소각 0건; 0606 표본은 100건). stage2 자기 호출부(라인 312)는 이미 올바르게 `disclosures, dart_fetch = …` 로 언팩돼 있었음.
  - **해결**: 두 파일 모두 `discs, _dart = stage2.fetch_disclosures(...)` 로 언팩. **자사주 소각=관측(가중치 0)** 이라 v3 점수 무관(관측 컬럼 백필은 §6-9 허용). ⚠️ **라이브 DART 미검증**(네트워크 없음) — 재실행 로그에서 `'list'…` 소거 + 소각 재검출 확인 필요.
- **부수 확인 (게이트 정상 동작)**: 0623 부분적재(stage1 kospi 715 만 적재) 상태에서 **완전성 게이트(§12-3)가 stage1 kosdaq=0(DB)** 을 잡아 push·평소텔레 보류, 어제 대시보드 유지, '보류' 알림(침묵 없음). **데이터 손상의 공개 배포를 정상 차단** → §12-3·§12-4 의 "라이브 1회 확인"분이 사실상 충족(실제 degraded 일을 게이트가 막음). 게이트가 운 이유는 stage1 MAX(run_id)=0623·kosdaq 0 단 하나(stage3 는 MAX run_id 가 아직 0622라 통과). **복구**: 패치본 적용 후 디스크의 0623 CSV 로 `python accumulate_history.py --date 20260623`(재스크리닝 불필요) 또는 `.bat` 재실행 → 클린 적재 시 게이트 4항목(stage1 715/1519·stage3 530/1080) 전부 통과(오프라인 검증).

---

## 13. 저변동 트랙 (lowvol) — 제3 트랙 (2026-06-25 신설)

> 상세 설계·검증은 **LOWVOL_TRACK_DESIGN.md**, 골대는 **PREREGISTER_lowvol.md**.

**정체성**: v3=중소형 과매도 반등, large=대형 가치, **lowvol=적당히 빠진 우량 저변동주**.
세 트랙은 데이터/인프라(stage3_final·history.db·대시보드·텔레그램·git)만 공유, 유니버스·점수·표시 분리.

**발견 경로**: 18거래일(0602~0624) 오프라인 분석에서 v3 단기 칼날(BUY 5일 −4.7%, 단 시장초과는
+2.4%p로 방향은 옳음)을 추적하다, 절대수익과 단조관계인 신호 3종 발견:
- realized_vol IC −0.23(저변동 선호), return_1w IC −0.21(단기반전), roe_value IC +0.12(우량).
- **반전은 h=5d만 유효**(h=20d서 부호 반전 +0.09 = 모멘텀). 호라이즌 주의.
- 학술 일치: 단기반전(Jegadeesh 1990), 단 유동성 프리미엄(Nagel)이라 **유동성 하한 필수**.

**모델(테이블 `lowvol_scores`, 가중치 0 관측, PIT 안전)**:
- 순위합 = run 내 cross-sectional 백분위 합. 핵심팩터 실측 필수(NaN 제외), 보조 NaN=0.5.
- lv_a 저변동+ROE+반전 / lv_b 저변동+ROE / lv_c 낙폭+ROE+반전 / lv_d 낙폭+ROE / lv_a3=lv_a(상한60).
- 유니버스: 과매도 30~70(극단 제외=반전 살림) + 유동성 ≥5억(분포 근거). 일평균 ~439종목.

**검증(전부 18일 in-sample=가설, §11 노이즈 구간)**:
- IC(h5 시장초과): lv_a 0.226, lv_a3 0.234, lv_b 0.191, lv_c 0.142, lv_d 0.158.
- lv_a 견고성 1위: 시장분리(코스피 0.251/코스닥 0.211)·시간분할(전반 0.242/후반 0.226)·5분위
  단조(−1.02→+2.13 무결점)·유니버스민감도(0.2~0.25) 전부 최상위.
- **상승장/하락장 양방향 작동**(시장 방향대로 증폭): 상승장 5일 Q5 1일 +2.0%(상승확률 73%),
  하락장 Q5 −1.6%(Q1 −2.6%). 단 이 기간 23일 중 18일 하락 → 전체 평균은 마이너스(장 탓). 상승장 표본 5일=유보.
- **realized_vol 커버리지 43% → lv_a/b의 h=20d(장기)는 표본 0, 현재 미검증.** forward 필요.
- 결합 교훈: 저변동·반전 **AND 금지(모순집합=추가하락), 순위합으로 가산.** 낙폭·OCF·모멘텀
  추가는 가산가치 0(중복) → 3팩터가 스위트스폿.
- v3·large 산출물 0-diff 불변 / lv_a3 추가 시 원본 lv_a~d 0-diff(최대차 4e-16) 검증.

**배포(v31g 패턴)**:
- `lowvol_score.py`(적재) → `build_lowvol_filter.py`(lv_a CSV → docs/latest_*_lowvol.csv) →
  `docs/lowvol.html`(전용 페이지, fetch, 점수해석·수급·양방향 설명 포함). `notify_lowvol_test.py`(테스트 텔레, 경고 도배+수급).
- 파이프라인: 2.86 적재(증분) · 2.87 CSV · 4b 텔레(정상 배포일만). **전부 비치명**.
- 노출은 lv_a만(테스트·관측·매수신호 아님 명시). lv_b~d·lv_a3는 shadow(점수만 누적).
- HTML 표시: lv점수·실현변동성·외인/기관 수급(5d·20d)·v3 bucket 비교. 섹터는 sector_cache.json에서 채움(stage3 sector 100% 빈칸).

**불변 규칙(상속)**: 관측 팩터 점수 미투입(검증 전), v3·large 불변, 매직넘버 금지(유동성/컷=분포),
PIT 엄수, post-hoc forward-only(판정 OOS 40거래일), 출력 0-diff 오프라인 검증 우선.

**운영 주의**:
- 최초 1회: `python lowvol_score.py --full`(36178행) + `python build_lowvol_filter.py`.
- 코드는 PUSH_ALLOWLIST(docs)에 안 걸림 → **수동 `git add` 커밋 필요**. docs/것만 자동 push.
- 판정: 등록일(0625) 이후 OOS 40거래일. 그 전 노이즈. Bonferroni 분모 5(모델 5개).
- **점수 해석(중요)**: lv점수↑ = "오른다"가 아니라 "시장 방향대로 증폭"(상승장 더 오름·하락장 덜 빠짐). 매수신호 아님.

**다음**: forward 누적 → 40거래일 후 lv_a vs lv_a3 vs 나머지 OOS 비교(발견기간 제외). 그때
검증 통과 모델만 가중 판단.

---

## 14. 탐색(research)과 배포(production)의 분리 — 규율은 유지, 사고는 확장 (2026-06-25)

> **왜 이 절을 추가하나**: 지금까지의 불변 규칙(관측 우선·40거래일·post-hoc forward-only·
> 0-diff·Bonferroni)은 **과적합 방지를 위한 흉터**이고 유효하다. 단 이 규칙이
> "검증 안 된 건 *점수에* 넣지 마"를 넘어 "검증 안 된 건 *시도조차* 마"로 읽히면 탐색이 죽는다.
> 둘은 다르다. 이 절은 그 경계를 명문화해, 도전적 시도를 과적합 누출 없이 허용한다.

### 14-1. 두 모드
- **탐색 모드 (`research/` 산출물 한정)**: **게이트 면제.** 어떤 가설·조합·ML·이상한 팩터든
  history.db로 자유롭게 굴린다. ML(트리/부스팅), 비선형 결합, 팩터 상호작용, 레짐 분기,
  대체 라벨(h별·국면별) 등 전부 허용. **단 산출물은 `research/`(또는 노트북)에만** — 절대
  `docs/`·텔레그램·점수 테이블(v3_scores·lowvol_scores·large_final)로 나가지 않는다.
- **배포 모드 (사용자 노출·가중)**: **기존 모든 게이트 적용.** 탐색에서 유망한 게 나오면
  → 새 model_id로 **관측 적재(가중치 0)** → **OOS 40거래일**(가치 트랙은 60~120일)
  → **부트스트랩 CI·Bonferroni** 통과 → **0-diff 검증** → 그때만 가중/노출.

### 14-2. 다리(승격 규칙) — 이게 있어야 탐색이 화려해도 안 샌다
- 탐색의 **in-sample 수치는 영원히 "가설"**. 발견 기간 IC가 아무리 좋아도 증거가 아니다.
- 배포 승격은 **등록일 이후 OOS 통과로만**. (PROJECT §11·§11-A·불변규칙 8 그대로 상속.)
- ML·복합모델일수록 자유도가 커 과적합 위험↑ → **OOS 문턱을 더 높이고**(예: 별도 호라이즌
  재현 필수), 해석가능성 낮으면 **관측 기간을 더 길게** 둔다.
- 탐색→배포 전환 시 반드시 **PREREGISTER 문서 신설**(골대 고정), 발견 기간 명시.

### 14-3. 지침(PROJECT_INSTRUCTIONS)에 추가할 문구
> "**새 가설 탐색은 게이트 면제로 자유롭게 제안·실험한다**(research/ 산출물 한정, docs/·텔레·점수
> 테이블 유출 금지). **배포·가중·사용자 노출만** 기존 검증 게이트(관측→40거래일 OOS→CI/Bonferroni
> →0-diff)를 반드시 통과시킨다. '검증 전이라 점수에 못 넣음'과 '검증 전이라 시도도 못 함'은 다르다
> — **후자는 금지가 아니다.** 데이터 갭이 있으면 상상 팩터를 만들지 말고 갭을 명시하되, 갭이
> 없는 조합·방법론 탐색은 적극 제안한다."

### 14-4. 열린 탐색 백로그 (research 모드 — 전부 가설, 배포 전 게이트 필요, 우선순위순)

> 핵심 인식: **현 시스템의 병목은 종목 선택이 아니다.** 랭킹 방향은 맞는데(시장초과 +) 절대수익이
> 마이너스인 건 **시장 베타 탓**(메모 일치). 그런데 세 트랙 전부 "오늘 *어떤* 종목"(cross-sectional)만
> 다루고 "*언제·얼마나* 노출"은 없다. 가장 큰 레버는 여기다.

1. **거래비용·세금 현실 점검** [1순위·전제]: 한국 거래세(매도 ~0.18~0.23%)+슬리피지+호가단위를
   백테스트에 넣어 기존 IC/수익이 **비용 후에도 남는지**. 저유동 반전 엣지는 비용에 먹히기 쉬움
   (Nagel 유동성 프리미엄). **이게 음성이면 아래 다수가 신기루** → 반드시 먼저. (db만으로 가능.)
2. **알파/베타 분해** [측정 인프라]: BUY+WAIT 손익을 시장(equal-weight proxy 또는 지수) 대비
   **베타 × 시장수익 + 잔차알파**로 분해. "절대 마이너스=베타 탓"을 정량 확인. **회전율·MDD·
   국면별(상승/하락 레짐) 성과**를 IC와 함께 상시 측정 패널로. (db만으로 가능.)
3. **베타 오버레이** [최대 레버 후보]: 레짐 하락 구간에서 **노출 축소 또는 인버스/선물 헤지**로
   베타를 죽이고 알파만 잔존. cross-sectional이 아닌 **직교 축**이라 기존 트랙 **0-diff 유지하며
   위에 얹음**. (백테스트는 db, 실집행은 사용자 — 단 이 트랙도 "발굴·관찰", 자동매매 금지.)
4. **트랙 앙상블** [국면 배분]: v3(반등)·large(가치/방어)·lowvol(저변동)은 서로 다른 국면에서
   켜진다 → **레짐별 동적 가중 메타모델**을 관측. "섞지 마"는 *점수 오염* 금지일 뿐, 트랙 위
   **메타 배분**은 별개 축(점수 테이블 안 건드림).
5. **호라이즌 분리 포트폴리오** [구조]: 반전=5d·가치=60d를 이미 아는데 한 화면에 섞고 있음.
   **보유기간 다른 두 바스켓**으로 나누는 것 자체가 구조 개선(LOWVOL §4 호라이즌 표 활용).

### 14-5. 불변(탐색해도 안 건드리는 것)
- v2.6 엔진·v3 점수·large_final·lowvol_scores **테이블/표시 0-diff**.
- 탐색 산출물의 **docs/·텔레그램·점수 테이블 유출 금지**(14-1).
- KIS/실집행은 **조회·관찰 전용, 자동매매·주문 금지**(트랙 불문).
- post-hoc forward-only·매직넘버 금지·PIT 엄수(전 트랙 상속).

---

**다음 실증(예고)**: 위 백로그 1·2번(거래비용 점검 + 알파/베타 분해)을 perf 핸드오프의
history.db(115MB)로 **오프라인 착수**. v3_scores·lowvol_scores의 BUY+WAIT 수익에 한국 거래비용을
반영하고, equal-weight 시장 proxy 대비 베타/알파로 분해한다. 이는 `research/` 분석이며 점수·docs/
**0-diff**(읽기 전용 분석, 산출은 research/ 리포트만).
