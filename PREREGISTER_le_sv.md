# PREREGISTER — le_a(저점탈출) · sv_a(공매도비중) 관측 모델 (2026-07-14 동결)

> wu 트랙(전체종목, wu_scores 테이블)에 추가되는 **가중치 0 관측 모델 2종**.
> 발견은 전부 post-hoc(in-sample) → **REG_DATE 2026-07-15부터의 forward 데이터만 §11 판정에 사용.**
> 표시·추천·텔레그램 사용 금지(판정 전). 이 문서 이후 spec 변경 금지 — 바꾸려면 새 model_id.

## 1. 출처 (발견 경위 — 판정에는 사용 불가한 in-sample 근거)

- `research/RESEARCH_tail_anatomy_20260714.md`: 저점탈출 결합(dlow52↑&obv63↓&amt20↑) 급등(E50) lift 3.06,
  mean fw20 +5.6%, P(−30%) 3.0%.
- 익일시가 진입 재계산(2026-07-14, nextday 스캔): 동일 결합 top10/일 **+0.92%/5d** (CI +0.40~+1.46,
  462일) — 6개 후보 점수 중 유일하게 익일 진입에서 생존. KOSDAQ>SMA20 국면에선 +1.42%/5d.
- `research/RESEARCH_winners_20260714.md`: svr5(공매도비중 5d)는 폭락장 표본(5/22~7/14)에서
  유일하게 국면독립(반등일 +0.16/하락일 +0.18, 31일 중 30일 양수), 시총 3분위 통제 후 생존.
  ⚠ svr5 는 폭락장 단일 국면 표본 — 상승장 검증이 OOS의 핵심 관전 포인트.

## 2. 동결 스펙 (wu_score.py MODELS/FACTORS와 1:1)

공통: wu 트랙 유니버스·가드 그대로(전체 상장, rv21≥0.003 · flat63≤0.5 · jump21≤0.30 ·
amt20≥5억 · 미정지 · 종가 존재). 순위합 = cross-sectional pct rank, 핵심(첫 팩터) 실측필수(NaN=제외),
보조 NaN=0.5. 저장: history.db `wu_scores` (model_id='le_a'/'sv_a').

| model_id | 팩터(순서=핵심 먼저) | 방향 | spec_hash |
|---|---|---|---|
| **le_a** | dlow52 = close/rolling_min(close,252)−1 | ↑ (저점서 이미 오름) | `29cb040142b0` |
| | obv63 = Σ(sign(Δ)·vol,63)/Σ(vol,63) | ↓ (미매집 우대) | |
| | amt20f = mean(close·vol,20)/1e8 | ↑ (유동성 우대) | |
| **sv_a** | svr5 = mean(short_vol_ratio,5, min 3) | ↑ (공매도비중 상위) | `e38efdfc260d` |

- sv_a 데이터 주의(스펙의 일부): 배치 순서상 wu_score 는 kis_flows 이전 실행 → 당일 short_flows
  미적재 가능. svr5 rolling(5, min 3)이 자동으로 직전 적재분을 사용(1일 지연 허용, 동결).
- 신규 모델은 기존 run_id(≤20260714)에 소급 적재하지 않음 — 20260715 이후 신규 run부터 자연 시작.

## 3. 판정 규칙 (§11 그대로)

- **h=20d IC 주지표, h=5d 보조**(le_a 는 발견이 h5 구조였으므로 h5 를 '보조 관전 1순위'로 명시하되
  판정 승격은 h20 기준 유지). OOS ≥ 40거래일 전까지 무조건 '노이즈'.
- 부트스트랩 CI(2,000) > 0 · 주간 방향일관성 ≥ 60% · 다중검정(wu 트랙 모델 수 기준 Bonferroni).
- 관전 포인트(사전 서약): ① le_a — 익일 진입 구조에서 발견된 h5 우위가 h20 IC로도 남는가,
  KOSDAQ<SMA20 국면에서 소멸하는 패턴이 재현되는가 ② sv_a — 상승장 도래 시 IC 부호 유지 여부.
- 판정 예상 시점: 2026-09 초순(거래일 기준).

## 4. 불변 확인 (2026-07-14 오프라인 검증 완료)

- wu_a `6c146134b5a1` / wu_b `f09894fd2fcf` spec_hash 변경 없음.
- 실 history.db 사본에 신코드 실행 → "[증분] 신규 적재 대상 없음" (기존 행 0-diff, count/기간 동일).
- 빈 DB 스모크: 4모델 정상 적재(유니버스 1,181 · le_a 1,172행 · sv_a 1,181행 · 점수범위 정상).
- build_wu_filter.py 는 MODEL="wu_a" 하드코딩 — le_a/sv_a 는 docs/텔레그램 어디에도 노출 안 됨.
- checkup.py REG_DATE 등재: wu_a/wu_b 20260702(원장 정식화, leaderboard setdefault와 동일값) ·
  le_a/sv_a 20260715.
