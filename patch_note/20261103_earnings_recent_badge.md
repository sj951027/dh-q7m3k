# 2026-11-03 — 목록 페이지 '정기보고서 접수' 표시(관측·가중 0) — **2026.10.49**

## 뭐가
- `earnings_flag.py` 에 `load_recent(asof, lookback=RECENT_LOOKBACK=20)` · `attach_recent(df, asof, col="earn_recent_20d")` 추가. 값 예 `"접수 3일(↓)"` / `"접수 12일"` / `""` — asof 기준 직전 20거래일 안 **최신 정기보고서 1건**(sue 결측도 포함, 부호 ↓/↑ 는 기존 `DROP` 문턱 ±1% 그대로, 새 매직넘버 없음).
- 소비처 4곳(`diversify_picks.py` · `build_lowvol_filter.py` · `build_wu_filter.py` · `build_mom_filter.py`) 의 기존 `attach` 바로 아래 한 줄씩 — 같은 비치명 try 안. CSV·JSON 에 열 하나 추가.
- 페이지 8곳(`docs/filter.html` · lowvol · lva · le · sv · qs · px · mom) 열 정의에 `earn_recent_20d`(회색 '접수' 배지, 기존 📉 옆). filter.html 은 저장된 열 선택에 1회 자동 추가.
- 테스트 `tests/test_earnings_flag.py` [H] 3체크(창 안/밖·당일 0·미래 제외 / 최신 1건·결측 포함 / 부호 라벨·행·열 순서 0-diff).

## 왜
- `research/RESEARCH_earnings_oversold_3y_20261031.md`: 접수 20거래일 안 과매도의 40일 수익 −2.8%p [−4.7, −0.9](Codex 재현 일치, 3.2년 대리). 사용자 결정(10/31) "실적만 넣자" = 표시만, 점수 반영 없음. 라벨은 Codex 교정 '정기보고서 접수 후 N거래일'(접수일 기준, 앞으로 남은 발표가 아님).

## 어떻게 + 검증
- 구현: Codex(11/2, `research/handoff/REQUEST_20261102_earnings_badge_impl.md` → 작업 트리). Claude 확인(11/3): diff 전문 검토 — 소비처는 각 1줄 추가뿐, `earnings_flag` 기존 함수 무변경(Codex AST 대조 PASS, `research/handoff/out_20261102_earnings_badge/verification.json`).
- **판정·점수 0-diff**: 점수·순위·게이트 코드 무접촉. 동결 v30 행 1,483 × 기존 열 전부 동일(Codex `csv_without_new_column_identical: true`). 10/30 기준 표시 6종목, v30 상위 20 중 0(연구의 27% 는 3.2년 평균 — 시즌 아닌 날은 0 도 정상).
- `python -X utf8 tests/run_tests.py` 전체 통과(Claude 11/3 19:05 실측, 23파일).
- 줄바꿈: 바뀐 파일 전부 기존 LF/CRLF 유지(diff 에 CR 변경 0).

## 영향 범위
- 배치: 11/3 밤부터 열 하나 추가. 실패해도 비치명(빈 열). PTW 무관(독립 원칙 — 그쪽에서 원하면 그쪽 저장소에서).
- 모의 계좌·리더보드·판정 무관. 재측정 2027-01(지도 §12 나 갈래).
