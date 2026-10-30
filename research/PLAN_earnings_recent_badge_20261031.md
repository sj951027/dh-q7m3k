# 준비 메모 — '실적 발표 N일 전' 표시(관측·가중 0) 구현 계획 (2026-10-31 06:20, 사용자 승인 "실적만 넣자" · 구현은 다음 세션)

## 근거
- `RESEARCH_earnings_oversold_3y_20261031.md`: 직전 20거래일 안에 분기 실적이 접수된 과매도는 40일 −2.9%p [−4.7, −1.1](3.2년 대리, 과매도의 31%·v30 목록의 27% 적용, 악화/개선 안 갈림). 실제 목록은 앵커 8 로 못 가림 → **표시만**, 2027-01 말 재측정, 그때 챌린저 후보.

## 지금 구조(10/31 확인)
- 이미 있는 실적 배지 `earnings_flag.py`: **영업이익↓ 60거래일**(sue ≤ −1%) 하나를 `load(asof)` → `attach(df)` 로 열 `earn_drop_60d` 에 붙인다. 소비처 4곳: `diversify_picks.py:353`(v3/v30 목록) · `build_lowvol_filter.py:242` · `build_wu_filter.py:290` · `build_mom_filter.py:255`. 자료 `../dh-q7m3k-data/earnings.db` `earnings_q`(배치 `earnings_incr.py` 가 매일 증분, 2023-08~).
- 새 표시는 **부호와 무관하게 '발표 자체'**(연구 결과) — 기존 배지와 뜻이 다르므로 열을 따로 둔다.

## 가장 작은 구현(변수 1개 · 점수 무접촉)
1. `earnings_flag.py` 에 함수 추가: `load_recent(asof, lookback=20)` → `{ticker: (rcept_dt, days_ago, sue_sign)}` — 직전 20거래일 안 **원본 정기보고서** 접수(정정 제외, `earnings_q.rcept_dt` 그대로) 중 최신 1건. `attach_recent(df, asof, col="earn_recent_20d")` → 값 예: `"실적 3일전(↓)"` / `""`. 상수는 `RECENT_LOOKBACK = 20` 하나(연구와 같은 창).
2. 소비처 4곳의 기존 `attach` 바로 아래에 `attach_recent` 한 줄씩(비치명 try 그대로). CSV·JSON 에 열이 하나 늘 뿐 순위·점수 무변경.
3. 페이지: `docs/filter*.html`·저변동·wu 페이지의 열 정의에 `earn_recent_20d` 추가(기존 `earn_drop_60d` 옆, 회색 배지). PTW 는 손대지 않음(독립 원칙 — PTW 쪽에서 원하면 그쪽 저장소에서).
4. 테스트: `tests/test_earnings_flag.py` 에 합성 3체크(창 안/밖 · 정정 제외 · 최신 1건).
5. 검증: `python diversify_picks.py` 류를 돌리지 않고(배치가 함) `earnings_flag.load_recent("20261030")` 결과 수와 `RESEARCH_earnings_oversold` 의 "v30 목록 27%" 가 맞는지 눈으로 · `tests/run_tests.py`.
6. 패치노트(2026.10.47) · 지도 §0 '관측 중' 칸 갱신 · 2027-01 재측정 일정은 지도 §12 나 갈래에 이미 있음.

## 하지 않을 것
- 자사주 취득 공시 표시(사용자 결정: 안 넣음) · 점수·게이트 반영 · 모의 계좌 변형 계좌(재측정 뒤).

## 미확인(표시 전에 한 번 보기 — Codex 제안)
- `earnings_q.rcept_dt` 가 장 마감 뒤 접수인지(DART 접수 시각은 저장 안 됨) — 표시 용도엔 영향 없음(t+1 매수 가정), 문구에 "접수일 기준" 만 적는다.
