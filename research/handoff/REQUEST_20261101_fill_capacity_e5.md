# REQUEST — E5 체결 한도 실측: v30·v32a·lv_b 목록 종목에 **실제로 얼마까지 살 수 있나** (거래대금 대비 참여율 기준, 계산 있음, 2026-11-01)

> 보내는 사람: 사용자(Claude 초안). 받는 사람: Codex. 운영 DB·history.db 읽기만. 코드는 새로. 시간·토큰 넉넉히.
> 왜: 지도 §12 다 갈래 ③(E5). v32a(한산한 과매도, 10/24 관측 등록)는 **채택돼도 살 수 있는 금액**이 작을 수 있다는 각주가 달려 있다(10/23 Codex 블라인드 답 "체결 한도 각주"). v30·lv_b 도 종목당 금액 상한이 운용 채택 잣대(2027-06)에 들어간다. 지금 숫자로 박아 두자.

## 0. 경로·규칙
- `C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k-data\ohlcv.db`: `daily_ohlcv` + `daily_ohlcv_extra`(합쳐서; ticker·date·close·volume·is_suspended·market). 거래대금 = close × volume(근사 — 실제 거래대금 열은 없음, 그렇다고 적어라). `C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k\history.db`: `v3_scores`(run_id·market·ticker·final_score_v3 — v30 = 시장별 상위 10), v32a 점수 표(이름은 `PRAGMA`/`sqlite_master` 로 찾아라; `v32a` 가 들어간 표 또는 `model_id='v32a'` 열), `lowvol_scores`(lv_b: lowvol_score 상위 10/시장). 희석·게이트 제외는 생략(차이는 §6 에 적어라). 모두 `mode=ro`. 평일 20:10~22:30 실행 금지.
- 열지 말 것(§6 전): `research/RESEARCH_pick_exec_hold_10y_20261030.md`, `research/handoff/*lowamt*`, `research/EXPERIMENT_PLAN_20261030.md` E5 절, `research/IDEA_MAP_20261030.md`, worklog 본문.

## 1. 정의 (고정)
- 앵커(run_id)마다 모델별 상위 10/시장(=20종목). 종목 i 의 **ADV20** = 앵커 전 20거래일 평균 거래대금(원). **참여율 p** ∈ {0.5%, 1%, 2%, 5%}(외부 카드 C3 경험칙 0.5~1%).
- 종목 한도 L_i(p) = ADV20_i × p. 목록 한도 L(p) = Σ_i L_i(p)(20종목). 슬롯 40 규칙에선 날마다 NAV/40 을 20종목에 나누니 종목당 NAV/800 — 그래서 **계좌 NAV 상한** = min_i(L_i(p)) × 800(가장 한산한 종목이 묶는 경우) 과, 중앙값 기준 = median_i(L_i(p)) × 800 을 둘 다.
- 보고: 모델(v30·v32a·lv_b)별 · 시장별 · 기간(2026-06~ 월별)별로 L_i 분포(10/25/50/75/90 분위, 원) · 목록 한도 L(p) · 계좌 NAV 상한(최소·중앙) · "하루 1,000만원 / 1억원 / 10억원 을 20종목에 균등 투입할 때 참여율이 p 를 넘는 종목 수".
- 체결 가능성 보조: 앵커 다음날(t+1) 거래량 0·정지·상한가(change_pct ≥ 0.29) 비율 — 10/23 모의 계좌 실측 '정지/상한가로 못 삼 ≈ 0.5%' 와 맞는지.
- v32a 와 v30 의 겹침(같은 날 두 목록 교집합 비율)도 — 겹치면 같은 종목에 두 배 돈이 간다.

## 2. 묻는 것
1. v30·lv_b·v32a 각각, **종목당 금액 상한의 중앙값(p=1%)** 과 하위 10%. 억 단위로.
2. v32a 는 v30 보다 얼마나 한산한가(ADV20 중앙값 비, 참여율 1% 한도 비).
3. 한 사람이 하루 X 원(100만·1,000만·1억)으로 따라 하면 몇 종목에서 참여율 1% 를 넘나 — 모델별.
4. 결론 한 줄: "v32a 가 채택돼도 계좌 NAV 가 얼마를 넘으면 목록 그대로 못 산다"(최소 기준·중앙 기준 둘 다).

## 3. 답
- `research/handoff/REPLY_20261101_fill_capacity_e5.md` + `code_20261101_fill_capacity_e5.py`. 실측/추정 구분, 거래대금 근사(close×volume)의 한계 명시. §6 에서 `RESEARCH_pick_exec_hold` 와 `*lowamt*` 를 열고 "거래대금 하위 +1.26%p 생존" 결론이 이 한도와 어떻게 맞물리는지 한 절.
