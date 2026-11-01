# REQUEST — 구현: 목록 페이지 '정기보고서 접수 후 N거래일' 표시(관측·가중 0 · 점수 무접촉) (2026-11-02)

> 보내는 사람: 사용자(Claude 초안). 받는 사람: Codex. **코드 수정 있음**(운영 파일) — 그러나 점수·순위·게이트는 한 글자도 바뀌면 안 된다. 커밋 금지(사용자가 GitHub Desktop 으로). 평일 20:10~22:30 실행·수정 금지(배치). `.bat`·`docs/*.json`·`docs/*.md`·DB 는 손대지 않는다. 시간·토큰 넉넉히.
> 왜: `research/RESEARCH_earnings_oversold_3y_20261031.md`(네 11/1 재현 포함): 직전 20거래일 안에 분기 보고서가 접수된 과매도는 40일 −2.8%p [−4.7, −0.9]. 사용자 결정(10/31) "**실적만 넣자**" = 표시만, 점수 반영 없음, 자사주 표시는 안 함. 라벨은 네 교정대로 '정기보고서 접수 후 N거래일'.

## 0. 먼저 읽을 것(순서)
1. `research/PLAN_earnings_recent_badge_20261031.md` — 구현 계획 전부(함수 이름·열 이름·소비처 4곳·테스트·검증). **이 계획대로**, 계획과 다르게 하고 싶으면 답 §4 에 이유만 적고 계획대로 한다.
2. `earnings_flag.py`(기존 배지 `earn_drop_60d` 의 `load`/`attach` — 같은 모양으로 `load_recent`/`attach_recent` 추가) · `tests/test_earnings_flag.py`(기존 테스트 양식).
3. 소비처: `diversify_picks.py`(≈353행) · `build_lowvol_filter.py`(≈242) · `build_wu_filter.py`(≈290) · `build_mom_filter.py`(≈255) — 기존 `attach` 호출 바로 아래 한 줄, 같은 비치명 try 안에.
4. 페이지 열 정의: `docs/filter.html`(≈612행 `earn_drop_60d` 항목, 688·703행 열 목록) · `docs/lowvol.html` · `docs/lva.html` · `docs/le.html` · `docs/sv.html` · `docs/qs.html` · `docs/px.html` · `docs/mom.html` — 각 파일에서 `earn_drop_60d` 가 쓰인 자리 **바로 옆**에 `earn_recent_20d` 를 같은 양식(type 'earnflag' 류, 회색 배지)으로. PTW(`../Position-Tracker-Web`)는 손대지 않는다.

## 1. 고정 사양
- 상수 `RECENT_LOOKBACK = 20`(거래일, 연구와 같은 창) 하나. 거래일 축은 기존 `load` 가 쓰는 `cal_db`(ohlcv.db) 경로 그대로.
- `load_recent(asof=None, lookback=RECENT_LOOKBACK, db=EARN_DB, cal_db=OHLCV_DB)` → `{ticker(6자리): (rcept_dt, days_ago, sue_sign)}`. 대상 = `earnings_q` 에서 asof 기준 직전 lookback 거래일 안 `rcept_dt` 의 **최신 1건**(접수일 순 마지막). `sue IS NULL` 도 포함(부호 없음 → 화살표 없이). `sue_sign` = '↓' if sue ≤ 기존 `DROP` 상수, '↑' if sue ≥ +|DROP|, 그 외 '' (기존 배지와 같은 문턱을 쓴다 — 새 매직넘버 금지). `days_ago` = asof 까지의 거래일 수(접수일 = 0).
- `attach_recent(df, asof=None, ticker_col="ticker", col="earn_recent_20d")` → 값 `"접수 3일(↓)"` / `"접수 12일"` / `""`. 열 하나 추가 외에 df 의 다른 열·행 순서 무변경.
- 정정 보고서는 `earnings_q` 에 PK(ticker,year,reprt) 로 한 행만 있으므로 별도 처리 불필요 — 단 답에 "원본/정정 구분은 `earnings_q` 적재 단계 규칙을 따른다" 고 적어라(네가 `earnings_incr.py` 를 읽고 그 규칙이 무엇인지 한 줄).

## 2. 검증(답에 그대로 붙일 것)
- `python -X utf8 tests/run_tests.py` 전부 통과(새 테스트 3개 포함: 창 안/밖 · 최신 1건 · 부호 라벨).
- **점수 0-diff 증명**: 소비처는 배치가 돌리므로 직접 돌리지 말고, 각 소비처에서 네가 넣은 줄이 **`final_score`·순위·게이트·CSV 행 순서에 닿지 않음**을 diff 로 보여라(`git diff` 전문을 답에). 추가 열은 CSV·JSON 끝에 붙는 열 하나뿐.
- `earnings_flag.load_recent("20261030")` 결과 개수와, 그 중 `history.db v3_scores`(`model_id='v30'`, run_id 20261030) 20종목에 해당하는 수 — 연구의 "v30 목록 27%" 와 자릿수가 맞는지.
- 줄바꿈: 각 파일의 기존 줄바꿈(CRLF/LF)을 유지. `git diff --stat` 에 줄바꿈만 바뀐 파일이 없어야 한다.

## 3. 답
- `research/handoff/REPLY_20261102_earnings_badge_impl.md`: 바뀐 파일 목록 · diff 전문 · 테스트 출력 · 검증 숫자 · 계획과 다르게 한 점(있으면) · 패치노트 초안 3줄(뭐가/왜/어떻게 — Claude 가 `patch_note/20261102_earnings_recent_badge.md` 2026.10.49 로 정리). 작업 트리에 변경을 남겨 두고(커밋 X) 끝.
