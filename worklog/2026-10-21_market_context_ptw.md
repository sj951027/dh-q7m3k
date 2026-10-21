# 2026-10-21(수 저녁) — Codex 요청 재안내 · **PTW '샀을 때 시장'**(선행 조사 → 스크리너 2026.10.34 + PTW v5.46)

## 요약
- 사용자 질문 둘: ① Codex 남은 요청이 무엇이었나 → `REQUEST_20261021_kosdaq_only_a.md` 한 줄로 재안내(전송은 사용자, 배치 시간 피해서). ② PTW 매수 기록에 그날 시장 점수·상황을 찍고, 기준이 바뀌어도 과거가 같이 바뀌는 확장 형태인가 → "점수는 저장값이 아니라 원자료에서 매일 재계산" 구조라 가능하다고 답하고, **선행 조사 뒤 구현**(사용자 "둘 다 진행, 연구 먼저").
- **선행 조사** `research/RESEARCH_ptw_market_context_20261021.md`: 매수일 칸이 바구니 40일 수익 분산의 11% 설명 · **한 종목 수익의 시장 몫은 7%** · 칸별 개별 종목 플러스 확률 **59%→35% 단조** · 전날 종가 칸 ≠ 당일 종가 칸인 날 26% → 붙이는 시점은 **매수 전 거래일 종가**로 고정 · 두 겹(재계산 조회 + 당시 본 값 스냅샷) 설계.
- **스크리너 2026.10.34**: `regime_ad.history()` + `build_dashboard.py` 가 `docs/market_context.json`(803일·150KB, 그날까지 자료만) 매일 생성. 테스트 E 절(임시 DB). 20:10 전 완료(19:49).
- **PTW v5.46**: `screener.market_context_asof`(전 거래일 행, ok/no_day/unavailable) · `trades.entry_mkt_json` 스냅샷 · 거래 응답 `mkt_asof`·`mkt_snap` · 매수 행 📍 한 줄 + 툴팁. `test_market_context.py` 17체크 통과, 전체 회귀 50파일 통과.

- **Codex 3차 답 대조**(`REPLY_20261021_kosdaq_only_a.md`, 19:41~19:52): Q만 −0.63% 재현 · 평균을 낮춘 건 큰 코스닥 종목(구간 0 포함) · 갈라진 것은 **코스피 R20 부호 하나**(코스피 ≥ 0 인 Q만 날 −7.3%, 사건 4) · **시장 폭 85% 는 못 가름** → "급락 안에서 더 좋은 날을 고르는 기준"은 지수·종목 자료 모두에서 없음. 연구 deep §7. 등록 없음.

- **Codex PTW v5.46 검토 반영**(`REVIEW_v5.46.md` F1~F5: 비유한 값 500 · 가짜 날짜/빈 결과가 정상 캐시 지움 · 미래 거래일 KST 기준 · 스냅샷 pos10 누락 · 실패 재시도) → 전부 수정, `test_market_context.py` 23체크 · 전체 50파일 통과.
- **외부 조사(배치 중, 웹만)**: 서브에이전트 11건(한국 팩터 근거 · 자료 소스/GitHub · 타이밍 문헌 · 체결 비용/KIS · 공시·대체자료 · 실무 반전·ML · 포트폴리오 위험 · 대형 가치 · 업종·달력·공매도 레짐 · 모델 수명·운영 안전 · ETF 슬리브) → **적립 카드 28장** `research/external_scan_20261021/EXTERNAL_SCAN_20261021.md`(원본 `ext/01~11`). 가장 값어치: 현실 왕복 비용(코스닥 소형 1~2%, 0.5% 는 코스피 대·중형만) · 상·하한가/급등 후 과매도 제외 필터(가중 0 관측 즉시 가능) · 10년 생존편향 없는 시세 무료 경로(FDR KRX-DELISTING + pykrx) · 업종 상대 20일 수익 챌린저 · ML 안 함 · 상폐는 −90% 처리 · ETF 슬리브.
- **10/21 배치 정상**(21:18): 전 단계 0 · 경고 0 · `market_context.json` 804일 · 텔레그램 🧭 3줄 첫 실전 발송("코스피 9.7/10 · -14.6% …"), 로그상 들여쓰기 공백 유지(폰 표시는 사용자 확인).

- (밤) 사용자 결정: **모의 계좌 배치 연결**(2026.10.35, .bat 한 줄, 등록은 2판 뒤) · 10년 시세 수집기 `research/fetch_10y_prices.py` 작성(FDR 상장+폐지 목록, 별도 `ohlcv_10y.db`, 이어받기·쉬어 가기) — **실행은 "10년이 의미 있나" 답 뒤 사용자 확인**. 과제 F 용 PTW 거래 CSV 내려받는 법 안내.

- **과제 F 완료**(사용자가 PTW 원장 CSV 제공, 개인 자료라 임시 읽기·집계만): `research/RESEARCH_fill_vs_close_20261021.md` — 매수 체결가 − 그날 종가 **+0.06%p [−0.39, +0.53]**(n=115), 매도 +0.10 · 참여율 중앙 0.001%(최대 0.05%) → "다음날 종가 매수" 가정은 이 계좌 크기에서 맞고, 작은·한산한 종목 추가 비용 없음(구간 0 포함) → 10/20 유동성 효과(−1.9%p)는 이 규모에선 체결로 안 녹음. 0.5% 비용은 보수적(실제 ≈0.25~0.3%).
- **10년 시세 수집 시작**(사용자 "응 그래"): `fetch_10y_prices.py --smoke 5` OK(2015-01-02~) → 전체 7,077종목(상장 2,867·폐지 4,210) 백그라운드 22:01~(약 2시간, `../dh-q7m3k-data/ohlcv_10y.db`, 로그 `research/out_fetch_10y_run.log`). 끝나면 폐지 종목 수정주가 검증이 다음 일.

## 사용자 결정
- 두 겹(재계산 조회 + 스냅샷) 모두 진행. 통계 탭 '매수 때 시장 칸별 성적' 표는 다음 판(v5.47).

## 바뀐 것 (미커밋)
- 스크리너: `regime_ad.py`(history) · `build_dashboard.py` · `tests/test_regime_ad.py` · `patch_note/20261021_market_context.md` · `patch_note/README.md`(2026.10.34) · `research/RESEARCH_ptw_market_context_20261021.md` · 이 기록 · `worklog/README.md`. (`docs/market_context.json`·`docs/data.json`·`docs/index.html` 은 배치 산출물.)
- PTW: `app/screener.py` · `app/db.py` · `app/main.py` · `app/static/index.html` · `test_market_context.py`(새) · `PATCH_NOTES_v5.46.md`(새) · `PTW_PROJECT_HANDBOOK.md`.

## 검증
- 스크리너 `test_regime_ad.py` 통과(history 임시 DB). PTW `test_market_context.py` 17/17. 전체 회귀 `run_all_tests.py` **50파일 통과**(98초, 19:52 실측).
- 확인 못 한 것: PTW 화면 실렌더(배포 뒤 매수 행 📍) · 오늘 밤 21:20 텔레그램 3줄 모양(어제 배선분 첫 실전).

## 남은 일 · ★ 다음 세션 시작점
0. 적립 카드 §I 순서대로: **가중 0 관측 넷**(상·하한가 도달 제외 · 급등 후 과매도 제외 · 유상/무상증자 공시 제외 · 업종 상대 20일 수익)을 v30 목록 안 사후로 먼저 → 하나만 챌린저(새 model_id).
1. 커밋(사용자): 위 목록 + `research/external_scan_20261021/`(12파일) + `run_all_and_diversify.bat` + `patch_note/20261021_paper_account_batch.md`·README + `research/fetch_10y_prices.py` + PTW `REVIEW_v5.46.md`.
1-a. 10년 수집 결과 확인(`research/out_fetch_10y_run.log` 마지막 줄 · meta status 분포) → 폐지 종목 수정주가 검증(액면분할 보정, pykrx adjusted 대조) → 그 뒤 급락 사건 수십 개로 '언제 사나' 재검증.
1-b. 10/22 배치 로그에서 `paper_account.db · docs/paper_account.json` 줄 확인. 10년 시세 수집은 승인되면 **주말 낮**에 `python research/fetch_10y_prices.py --smoke 5` → 전체(1~2시간, 배치 밖). 오늘 밤 텔레그램 3줄·성적표 상단 카드·PTW 📍 줄 확인.
2. PTW v5.47: 통계 탭 '매수 때 시장 칸별 성적'(n 병기, 4건 미만 비움) · CSV 내보내기에 시장 열.
3. 모의 계좌 배치 한 줄(`python paper_account.py`, 사용자 확인 뒤) → 2판(다른 모델 계좌·자리바꿈).
4. 과제 F 체결가 vs 가정가(PTW 거래 CSV 필요) · Codex 요청서 전송 시점(사용자) · 10년 시세 승인.

## 작업 요령
- 저장된 점수가 아니라 "원자료 + 그날까지만 보는 함수"로 이력을 만들면 기준 변경이 과거 전부에 자동 적용된다. 대신 "그때 본 값"은 따로 저장해야 남는다.
