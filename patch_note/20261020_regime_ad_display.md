# 2026.10.31 — A~D 진입 국면 표시(텔레그램 · data.json · 성적표 · PTW) — 표시 전용 (2026-10-20)

## 뭐가
- 새 모듈 `regime_ad.py`: 코스피·코스닥 각각 **20거래일 수익(R20)** → 칸(A 급락 뒤 ≤−5% · B 약세 −5~0 · C 강세 0~+5 · D 급등 뒤 >+5%)과 **며칠째**(같은 칸 연속 일수, 들어온 날 = 1). `market_daily` 읽기 전용(mode=ro).
- `build_dashboard.py`: `docs/data.json` 최상위 `regime_ad` 키 추가(`{"kospi": {date, r20_pct, cell, label, days}, "kosdaq": …}`) — PTW·텔레그램이 읽는다. 실패하면 키 없음(비치명).
- `notify_telegram.py`: 성적표 블록 뒤 `🧭 시장국면: 코스피 -13.0% 급락 뒤 7일째 · 코스닥 -0.4% 약세 2일째` 한 줄. data.json → 없으면 ohlcv.db(ro) → 둘 다 실패면 줄 생략.
- `build_scoreboard.py`: 모델별 `regime_ad_money`(코스피·코스닥 칸별 40일 시장 대비 %p·일수·양수 비율, 4일 미만 칸 비움) + `regime_ad_now`·`regime_ad_cells`. 종전 '상승/약세'(코스닥 20일선) 기록은 그대로 두고 **병기**.
- `docs/leaderboard.html` '국면별 · 지금 형세': 머리글에 지금 A~D 두 지수 값, 표에 '코스피 A~D에 산 날' 열(네 칸), 각주에 정의·근거 링크.
- PTW v5.45(별도 저장소): 상단 시장국면 칩에 ` · -13.0% 급락 뒤 7일째` 병기(data.json `regime_ad`, 없으면 종전 칩).

## 왜
- 3년 전 종목 조사(`research/RESEARCH_entry_regime_deep_20261020.md`) + Codex 독립 재현(`research/handoff/REPLY_20261020_entry_regime_blind.md`, 핵심 수치 일치): 코스피 급락 뒤 40일은 9사건 전부 플러스·위험 절반, 급등 뒤가 가장 나빴다. 종전 '코스닥 20일선 위/아래'보다 **낙폭 크기**가 더 갈랐다. 사용자 결정(10/20 오전): A~D 표시 승인.
- 관측 표시이지 매수 신호가 아니다(독립 사건 9개·사후 탐색). 규칙은 `PREREGISTER_regime_gate.md`(초안 2차) 가설로만.

## 어떻게 / 검증
- 순수 함수 테스트 `tests/test_regime_ad.py`(경계값 · 며칠째 · 한 줄 말 · 텔레그램 줄) → `tests/run_tests.py` 등록. **전체 17파일 통과**(실측).
- 실측: 10/19 기준 코스피 R20 −13.0%(A, 10/08 진입 **7일째**) · 코스닥 −0.4%(B, 2일째). `build_scoreboard.py` 재생성 OK(v30 코스피 A 26일 +1.5%p · D 11일 +8.2%p 등 — 2026 한 사이클, 참고만). `notify_telegram.build_message()` 로컬 생성 OK(전송 없음).
- 오전 기록의 "8일째"는 하루 많게 적힌 것 — 코드 실측(10/08·10/12·10/13·10/14·10/15·10/16·10/19 = 7일)으로 교정.

## 영향범위
- **점수·판정·게이트 0-diff**(점수식·판정 코드 미접촉). docs 산출물(data.json·scoreboard.json)에 키 추가만 — 종전 키 불변. 텔레그램 한 줄 추가. 첫 줄(✅/⚠️) 판정 무관.
