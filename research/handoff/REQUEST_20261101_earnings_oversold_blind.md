# REQUEST — 독립 계산(눈가림): "직전 20거래일 안에 분기 실적이 접수된 과매도는 다른가" 재현 + 확장 두 가지(발표 예정 종목 · 유상증자/관리종목 공시 뒤 과매도) (2026-11-01)

> 보내는 사람: 사용자(Claude 초안). 받는 사람: Codex. **계산 있음**(운영 DB·실적 DB·DART 표 읽기, 10년 DB 아님). 코드는 새로 쓴다(저장소 연구 코드 가져오지 않기). 시간·토큰 넉넉히 써도 된다(사용자 뜻).
> 왜: 10/31 Claude 연구가 3.2년 대리에서 **발표 20일 안 과매도 −2.9%p [−4.7, −1.1]**(과매도의 31% 적용, 악화/개선 안 갈림)를 냈고, 사용자가 이를 **목록 페이지 표시(관측·가중 0)**로 올리기로 했다. 표시 전에 독립 재현과, 같은 자료로 할 수 있는 확장 둘을 부탁한다. 진짜면 2027-01 실제 목록 재측정 뒤 v30 변수 1개 챌린저("발표 20일 안 제외") 사전등록 후보가 된다.

## 0. 경로·규칙 (읽기 전용)
- 저장소 `C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k`(`AGENTS.md`·`CLAUDE.md`, 먼저 읽을 것 4번 지도 포함). 평일 20:10~22:30 실행 금지(월 11/2 저녁 주의 — 그 전이나 뒤에).
- 운영 시세 `C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k-data\ohlcv.db`: `daily_ohlcv`(2023-06-26~, ticker·date·close·volume·change_pct·shares·is_suspended·market) + **`daily_ohlcv_extra`**(136종목, 같은 열, 본표와 겹침 0 — 합쳐서 써라) · `market_daily`(series KOSPI/KOSDAQ, date, close) · `dart_events`(rcept_no·rcept_dt·ticker·event_type·report_nm; event_type ∈ cb·paid_in·buyback·buyback_sell·reduction·eb·bw·bonus·paid_bonus_mix, 2023-06~).
- 실적 `C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k-data\earnings.db` `earnings_q`(ticker·year·reprt·reprt_ord·rcept_dt·q_op·q_op_prev·mcap_prev·sue·source, 2023-08~2026-10, 30,754행·2,577종목). `sue` = (분기 영업이익 − 전년 동기) ÷ 시총(저장소 `earnings_flag.py` 머리말 참고 — 코드 가져오지 말고 정의만).
- 실제 v30 목록: `C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k\history.db` `v3_scores`(run_id·market·ticker·final_score_v3, 2026-06~) — 시장별 상위 10. 희석·게이트 제외는 무시해도 됨(그 차이는 §7 에서 Claude 가 설명).
- 모두 `mode=ro` + `PRAGMA query_only=ON`. 네트워크·수집·DB 쓰기·커밋 없음.
- **눈가림**: `research/RESEARCH_earnings_oversold_3y_20261031.md`·`research/out_earnings_oversold/`·`research/earnings_oversold_3y_20261031.py`·`research/earnings_v30_list_check_20261031.py`·`research/PLAN_earnings_recent_badge_20261031.md`·`research/IDEA_MAP_20261030.md` §10 끝부분·`worklog/` 본문은 **§7 전엔 열지 않는다**(worklog/README 는 제목 줄만).

## 1. 틀 (고정)
- 신호일 t: 운영 시세 공통 거래일 5거래일 격자(2023-07-31 부터 40일 완결까지). 조건 통과 = t·t+1 양수 종가·거래량 > 0, 종가 ≥ 1,000원, `is_suspended = 0`, R20(t) 유효. **과매도 = 조건 통과 중 R20 하위 20%**(선형보간 분위, 경계 포함).
- 결과 = t+1 종가 → t+41 종가(%), 비용 없음. 상폐·결측은 제외하고 수를 보고(10년 DB 가 아니라 '마지막 가격' 규칙 불필요).
- 칸 = 코스피 R20(t) A ≤ −5 / B·C / D > +5. 날 단위 동일가중(양쪽 다 있는 날) · 월 블록 부트스트랩 2,000(seed 7). 그룹 **차이**에 구간.

## 2. 재현 — 발표 20일 안 과매도
- E(t, 종목) = 직전 20거래일(t 포함) 안에 `earnings_q.rcept_dt` 접수가 있음(원본 정기보고서; 같은 분기 정정이 따로 행으로 있으면 최초 접수만). 비교: 과매도∧E vs 과매도∧¬E — 40일 수익 · −20% 이하 비율 · 양수 비율 · R20 깊이(두 집단 같은지).
- 2차: 과매도∧E 안에서 sue < 0(악화) vs ≥ 0(개선). 맥락: 과매도 아닌 종목에서 E vs ¬E, 악화 vs 개선.
- 감도: 창 10일 · 20일 · 40일 · 칸별 · 2023-08~2024 / 2025~ · 접수일 = t 인 경우를 E 에서 빼는 판(장 마감 뒤 접수면 t+1 에만 반영되는 문제).
- **실제 v30 목록**(2026-06~): 앵커(run_id)마다 상위 20 의 E 비율과 E/¬E 40일 수익, **둘 다 있는 앵커만 짝 비교**(앵커 단위 월 블록). 발표 슬롯이 8월 시즌에 몰려 시기와 섞이는 문제를 어떻게 다룰지 네 방법을 적어 달라(예: 같은 앵커 안 비교만, 또는 시즌 더미).

## 3. 확장 ① — 발표 **예정** 과매도(외부 카드 A6 의 앞부분)
- 예정일 자료가 없다. 대리: 같은 종목의 **전년 같은 분기 접수일 + 365일**(또는 직전 분기 접수일 + 91일) 을 예정일로 보고, 신호일 t 가 예정일 앞 0~10거래일 안이면 P(발표 임박). 두 대리의 적중률(실제 접수일과 ±5일 안)을 먼저 보고 쓸 만한지 판단.
- 비교: 과매도∧P vs 과매도∧¬P∧¬E(발표 뒤도 아님). 가설(Claude): 임박 과매도는 '발표를 기다리는' 종목이라 40일 안에 발표가 끼어 분산이 큼 — 평균보다 **꼬리**(−20% 비율)를 봐 달라.

## 4. 확장 ② — 공시 뒤 n일 과매도(유상증자·감자·CB/BW·관리/정지)
- `dart_events` 의 `paid_in`(유상증자)·`reduction`(감자)·`cb`/`bw`/`eb` 를 각각: 직전 20거래일 안 공시 있는 과매도 vs 없음. 저장소는 유상증자를 '희석 플래그'로 목록에서 이미 빼고 있다(10/20 모의 계좌·`dilution_flag.py`)— 그 **제외가 맞는지**(공시 뒤 과매도가 정말 나쁜지)를 독립으로 확인해 달라. 다중비교 5개를 세어 적고, 사건 수 적은 것은 '판단 불가'로.

## 5. 결과값·보고
- 표: 범위(전체/칸/기간/시즌 달) × 비교 × (n일 · 두 집단 평균 · 차이 [95%] · 꼬리 차 · 양수 비율 차 · R20 깊이). 시험 수 합계. 실측/추정 구분.
- 운용 번역: "발표 20일 안 과매도를 **빼면**" 전체 과매도 평균이 얼마나 오르나(= 차이 × E 비중, 날마다 곱해 평균).

## 6. 답 파일
- `research/handoff/REPLY_20261101_earnings_oversold_blind.md` + `research/handoff/code_20261101_earnings_oversold_blind.py`(재현 명령·셀프체크). 큰 중간 파일 없음.

## 7. 마지막에만 — 대조
그제야 Claude 문서(`RESEARCH_earnings_oversold_3y_20261031.md`)를 열고: 숫자 방향·크기·구간이 맞는지, 다르면 왜(유니버스·정정 처리·접수일 = t 처리·분위 방식), Claude 가 과장한 문장, 표시로 올릴 만한지 네 의견, 챌린저 사전등록 때 **정의를 무엇으로 고정**해야 하는지(창·정정·접수 시각) 한 절. Claude 는 네 답을 받은 뒤 자기 계산을 다시 맞춘다.
