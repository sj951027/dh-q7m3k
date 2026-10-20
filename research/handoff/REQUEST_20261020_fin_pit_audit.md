# REQUEST — 재무 자료 '그날 알던 값' 감사 (Codex · 2026-10-20 작성)

> 이 파일 하나가 요청 전부다. 답: `research/handoff/REPLY_20261020_fin_pit_audit.md` + `code_20261020_fin_pit_audit.py`. 끝나면 멈추고 핵심 5줄로 보고.
> 질문: 점수에 들어가는 분기 재무(stage3 의 영업이익·영업현금흐름·ROE)가 **그 run 날에 이미 공시돼 있던 값**인가, 아니면 나중 공시가 과거 run 에 섞였나(미래 참조). 결과가 나쁘면 재무 성분이 든 모델 판정에 각주가 붙는다(판정·점수·코드는 바꾸지 않는다).

## 규칙
- AGENTS.md 와 CLAUDE.md 를 따른다. DB 읽기 전용(mode=ro). 수집기·배치 실행 금지, **DART·KIS·KRX 등 외부 호출 금지**(필요한 접수일은 아래 DB 에 있다). 점수·판정·게이트 코드와 docs/ 수정 금지.
- 평일 20:10~22:30 에는 아무것도 실행하지 않는다.
- 숫자에는 n 과 95% 구간, 실측과 추정 구분, 모르면 '확인 못 함'. 묻지 말고 이어서 한다.

## 자료 (전부 로컬 DB)
- `history.db` `stage3_final`(run_id × ticker): 재무 열 `q_period`(분기 키) · `q_prev_key` · `q_prev_억` · `quarterly_yoy_%` · `ocf_latest_억` · `ocf_prev_억` · `annual_prev_억` · `roe_value` · `dart_ocf_status` · `ocf_pattern`('데이터없음' 포함). run 99개(~20261019).
- `../dh-q7m3k-data/earnings.db` `earnings_q`(ticker, year, reprt, reprt_ord, rcept_dt, q_op, q_op_prev, …): 분기 보고서의 **접수일 rcept_dt** — 이것이 "그날 알 수 있었나"의 기준. `earnings_raw`(rcept_no, fetched_at) 보조.
- `../dh-q7m3k-data/ohlcv.db` `dart_events`(rcept_dt, event_type) 는 사건 공시(cb·유상증자 등)라 재무와 무관 — 쓰지 않는다.

## 할 일
1. **대응 규칙부터**: stage3 의 `q_period`/`q_prev_key` 가 earnings_q 의 (year, reprt) 와 어떻게 대응하는지 코드(`stage3_fundamental_momentum_v2_6.py` 의 분기 선택 로직)로 확인해 적어라. 대응이 안 되는 형식이 있으면 그 수와 예.
2. **전수 대조(가능하면)**: run 마다 stage3 재무가 가리키는 분기의 접수일 `rcept_dt` 를 찾아 `run_id < rcept_dt`(= 아직 공시 안 된 값을 썼다) 인 행의 비율을 **run 별·월별**로. earnings_q 에 접수일이 없는 종목·분기는 '확인 못 함'으로 따로 센다(비율에 섞지 않는다).
3. **표본 20 정밀 대조**: 시총 5분위 × 결산월(12월/비12월) × 정정공시 유무가 섞이게 20 (run, ticker) 를 뽑아(seed 20261020, 뽑는 규칙을 먼저 적고 뽑아라), 각 행에 대해 ① stage3 값 ② 그 값이 나오는 보고서와 접수일 ③ run 날짜와의 차이(일) ④ 그날 가장 최근 공시로 볼 때 썼어야 할 값(다르면) 을 표로.
4. **영향 추정(관측만)**: 미래 참조 행이 있으면, 그 행을 제외했을 때 v30 h20 IC 가 얼마나 바뀌는지 — 등록일 이후 run 만, §11 규약(`leaderboard` 순수 함수 추출, 10/18 `code_20261018_v30_w2_blind.py` 참고). **판정 숫자를 바꾸는 것이 아니라 각주용**임을 명시.
5. 각주: 20261014 run 없음 · stage3 '데이터없음' 비율 · earnings_q 의 커버리지(상장 종목 대비).
6. 결론 한 줄: "재무는 그날 알던 값인가(비율) · 아니면 어느 모델 판정에 각주가 필요한가".

## 하지 않을 것
점수·판정 코드 수정, 새 모델, DART 호출, 운영 DB 쓰기.
