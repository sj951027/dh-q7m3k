# 2026.10.47 — 자료 점검표에 '시장 수급(KRX)' 갈래 추가 (J14 운영 상태 기록) (2026-11-01)

## 그래서 뭐가 바뀌나
- `data_health.py` 갈래 16 → **17**: `mkt_flows` "시장 수급(KRX)" — `../dh-q7m3k-data/market_flows_10y.db` `investor_daily` 날짜별 행 수(정상 24). 허용 지연 0 · 건수 검사. `docs/data_health.json`·`.md`·텔레그램 ⚠️ 줄에 자동 반영.
- 왜: 10/31 보강한 수급 일일 갱신(`market_flows_obs.py`)은 비치명이라 조용히 멈출 수 있다 → 점검표가 매일 잡는다(지도 J14 '운영 상태 기록'). 표시·점수·판정 무관.
- 검증: `tests/test_data_health.py` 3체크 추가·통과 · `python data_health.py` 실측 17갈래 경고 0(시장 수급 20261030 24/24 ok) · 전체 테스트 통과. markdown 행 수 검사는 `len(BRANCHES)` 기준이라 자동.
