# REQUEST — J05: 모의 계좌에서 **못 사는 종목(정지·상한가·거래량 0·시세 없음)을 다음 순위로 바꿔 사면** 현금으로 두는 지금과 얼마나 다른가 (기존 엔진 재사용 · 연구 전용, 2026-11-02)

> 보내는 사람: 사용자(Claude 초안). 받는 사람: Codex. 읽기 전용: `history.db`(v3_scores·lowvol_scores) · `../dh-q7m3k-data/ohlcv.db`(daily_ohlcv·daily_ohlcv_extra). **쓰기는 `research/handoff/out_20261102_j05/` 안에만** — `../dh-q7m3k-data/paper_account.db`·`docs/` 절대 쓰지 않는다(운영 장부). 평일 20:10~22:30 실행 금지.
> 왜: 지도 §12 다 갈래 ④. 모의 계좌는 t+1 에 못 사는 종목을 **현금**으로 둔다(10/23 실측 0.5%, E5 대리 0.3%). 바꿔 사면 수익이 달라지나, 달라진다면 비교 공정성(13장 모두 같은 규칙)에 영향이 있나를 숫자로. 작아서 '후순위' 로 닫히는 것도 정당한 결론.
> 열지 말 것(§5 전): `research/RESEARCH_*`, `research/IDEA_MAP_20261030.md`, worklog 본문.

## 0. 엔진은 **그대로 가져다 쓴다**(복사·수정 금지)
- `paper_engine.simulate(dates, close, picks, *, slots=40, hold=40, cost=0.005, tradable=..., settle_days=0)` 와 `paper_engine.tradable_mask(susp, chg, limit_up)` — 서명·뜻은 `paper_engine.py` 독스트링. `paper_account.py` 의 `load_prices()`(본표+보충표 병합)·`model_picks(...)`·`v30_picks(...)`·상수(`START_DEFAULT`·`LIMIT_UP`·`HOLD`)를 **import 해서** 쓴다(`PAPER_USE_EXTRA` 기본 1). `run()` 은 부르지 않는다(장부를 쓴다).
- 되감기 구간·비용·슬롯·진입 지연은 운영과 같게(상수 import). 모델 3개: **v30**(v3_scores 상위 10/시장) · **lv_b**(lowvol_scores) · **v32a**(v3_scores model_id='v32a', 5일뿐 — 참고). 희석 제외 규칙은 `paper_account.py` 가 하는 그대로(`_dil_flags`).

## 1. 비교할 규칙 (변수 1개)
- **지금(기준)**: 추천일 t 상위 10/시장 → t+1 에 `tradable` False 면 그 몫은 현금(엔진 기본).
- **대체 A**: t+1 에 못 사는 종목을 같은 시장 **11위, 12위, …** 로 미리 바꿔 넣은 picks 를 엔진에 준다(대체 종목도 못 사면 다음 순위, 최대 15위까지; 그래도 없으면 현금). 바꾸기 판단에 쓰는 정보는 **t+1 의 tradable 뿐**(t+1 종가 매수이므로 그날 정지·상한가 여부는 주문 시점에 앎 — 거래량 0 은 장 끝에야 알므로 각주).
- **대체 B(참고)**: 못 사는 종목을 **그 다음 거래일 이후 처음 살 수 있는 날**(≤ t+5)에 사는 '지연 진입' — 엔진이 지원 안 하면 생략하고 "엔진 밖" 이라 적는다.
- 공정성 보조: 대체가 들어간 날 수·종목 수(모델별), 대체로 들어온 종목의 40일 수익 vs 원래 종목이 살 수 있었다면의 수익(t+1 종가 기준, 참고) vs 현금 0.

## 2. 보고
- 모델별 `total_ret`(되감기 전체)·`max_dd`·`cash_share` — 기준 vs 대체 A(차이 %p). 대체가 **한 번도 안 일어난 모델은 "발생 0"** 한 줄.
- 발생 목록(날짜·시장·원래 종목·이유(정지/상한가/거래량0/시세없음)·대체 종목·대체 종목 40일 수익).
- 결론 한 줄(사전 고정): 전체 수익 차이 |Δ| < 0.3%p 이고 발생 ≤ 1%/슬롯 → **"후순위 닫음(규칙 유지 = 현금)"**; |Δ| ≥ 0.3%p 면 "검토" — 그래도 13장 모두 같은 규칙이어야 하므로 채택은 Claude·사용자가.

## 3. 답
- `research/handoff/REPLY_20261102_j05_replace_vs_cash.md` + `code_20261102_j05_replace_vs_cash.py` + `out_20261102_j05/`(csv). 실측/추정 구분. 엔진 상수·되감기 시작일·시세 공급원(본표+보충표)을 답 머리에 적어라.
- §5 에서만 `research/RESEARCH_ops_realism_20261101.md`·`research/paper_slot_gaps_20261031.py` 를 열고 J10(정지일 예정 청산)·J06(목록 부족)과 이 결과가 같은 자릿수인지 한 절.
