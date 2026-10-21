# 2026-10-21(수 저녁) — Codex 요청 재안내 · **PTW '샀을 때 시장'**(선행 조사 → 스크리너 2026.10.34 + PTW v5.46)

## 요약
- 사용자 질문 둘: ① Codex 남은 요청이 무엇이었나 → `REQUEST_20261021_kosdaq_only_a.md` 한 줄로 재안내(전송은 사용자, 배치 시간 피해서). ② PTW 매수 기록에 그날 시장 점수·상황을 찍고, 기준이 바뀌어도 과거가 같이 바뀌는 확장 형태인가 → "점수는 저장값이 아니라 원자료에서 매일 재계산" 구조라 가능하다고 답하고, **선행 조사 뒤 구현**(사용자 "둘 다 진행, 연구 먼저").
- **선행 조사** `research/RESEARCH_ptw_market_context_20261021.md`: 매수일 칸이 바구니 40일 수익 분산의 11% 설명 · **한 종목 수익의 시장 몫은 7%** · 칸별 개별 종목 플러스 확률 **59%→35% 단조** · 전날 종가 칸 ≠ 당일 종가 칸인 날 26% → 붙이는 시점은 **매수 전 거래일 종가**로 고정 · 두 겹(재계산 조회 + 당시 본 값 스냅샷) 설계.
- **스크리너 2026.10.34**: `regime_ad.history()` + `build_dashboard.py` 가 `docs/market_context.json`(803일·150KB, 그날까지 자료만) 매일 생성. 테스트 E 절(임시 DB). 20:10 전 완료(19:49).
- **PTW v5.46**: `screener.market_context_asof`(전 거래일 행, ok/no_day/unavailable) · `trades.entry_mkt_json` 스냅샷 · 거래 응답 `mkt_asof`·`mkt_snap` · 매수 행 📍 한 줄 + 툴팁. `test_market_context.py` 17체크 통과, 전체 회귀 50파일 통과.

## 사용자 결정
- 두 겹(재계산 조회 + 스냅샷) 모두 진행. 통계 탭 '매수 때 시장 칸별 성적' 표는 다음 판(v5.47).

## 바뀐 것 (미커밋)
- 스크리너: `regime_ad.py`(history) · `build_dashboard.py` · `tests/test_regime_ad.py` · `patch_note/20261021_market_context.md` · `patch_note/README.md`(2026.10.34) · `research/RESEARCH_ptw_market_context_20261021.md` · 이 기록 · `worklog/README.md`. (`docs/market_context.json`·`docs/data.json`·`docs/index.html` 은 배치 산출물.)
- PTW: `app/screener.py` · `app/db.py` · `app/main.py` · `app/static/index.html` · `test_market_context.py`(새) · `PATCH_NOTES_v5.46.md`(새) · `PTW_PROJECT_HANDBOOK.md`.

## 검증
- 스크리너 `test_regime_ad.py` 통과(history 임시 DB). PTW `test_market_context.py` 17/17. 전체 회귀 `run_all_tests.py` **50파일 통과**(98초, 19:52 실측).
- 확인 못 한 것: PTW 화면 실렌더(배포 뒤 매수 행 📍) · 오늘 밤 21:20 텔레그램 3줄 모양(어제 배선분 첫 실전).

## 남은 일 · ★ 다음 세션 시작점
1. 커밋(사용자): 위 목록. 오늘 밤 텔레그램 3줄·성적표 상단 카드·PTW 📍 줄 확인.
2. PTW v5.47: 통계 탭 '매수 때 시장 칸별 성적'(n 병기, 4건 미만 비움) · CSV 내보내기에 시장 열.
3. 모의 계좌 배치 한 줄(`python paper_account.py`, 사용자 확인 뒤) → 2판(다른 모델 계좌·자리바꿈).
4. 과제 F 체결가 vs 가정가(PTW 거래 CSV 필요) · Codex 요청서 전송 시점(사용자) · 10년 시세 승인.

## 작업 요령
- 저장된 점수가 아니라 "원자료 + 그날까지만 보는 함수"로 이력을 만들면 기준 변경이 과거 전부에 자동 적용된다. 대신 "그때 본 값"은 따로 저장해야 남는다.
