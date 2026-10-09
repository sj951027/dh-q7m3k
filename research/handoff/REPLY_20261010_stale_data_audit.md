## 범위와 방법

실행 2026-10-09T23:19:01+09:00. 기준일 20261008, 가장 최근 거래일 20261008, 10/09 휴장. calendar=market_daily의 KOSPI/KOSDAQ 합집합. 최근 n=60일 20260710~20261008, 최근 n=20일 20260908~20261008, 최근 n=10일 20260922~20261008. 거래일의 정확성은 DB 기록을 기준으로 했고 외부 달력과 별도 대조하지 않았다. 세 DB의 모든 물리 표(sqlite_master type=table)를 mode=ro로 읽었다. 수집기·배치·프로젝트 모듈 실행·DART·KIS·외부 호출 n=0. 성과 계산 n=0. 운영 코드·DB·docs 변경 없음. 날짜 뒤처짐은 실측, 오류 원인·영향 해석은 코드와 갱신 주기에 근거해 구분한다.

## 1. 모든 표의 재고와 마지막 날짜

날짜·조회/저장 시각·보고기간을 구분했다. 뒤처짐은 해당 날짜 뒤부터 기준일 20261008까지의 DB 거래일 수다. 최신 fetched_at이 과거 date의 최신성을 보장하지 않는다. rcept_no는 접수 식별자이며 날짜 열로 세지 않았다. 표 이름을 운영 Python 코드에서 찾아 소비/저장 파일 최대 n=3개를 적었다.

| 표 | 행 수 | 날짜 열 전부: 마지막 값 / 지연 / 비NULL 수 | 사용 파일(줄) |
|---|---|---|---|
| history.large_final | n=39,000 | run_id: 20261008 / 뒤처짐 0거래일 / 유효 n=39000; run_timestamp: 20261008_2043 / 뒤처짐 0거래일 / 유효 n=39000; stage3_src_run: 20261008 / 뒤처짐 0거래일 / 유효 n=31831 | large_verdict.py:48, build_cross_sim.py:48, build_daily_lists.py:25 |
| history.large_universe | n=39,500 | run_id: 20261008 / 뒤처짐 0거래일 / 유효 n=39500; run_timestamp: 20261008_2042 / 뒤처짐 0거래일 / 유효 n=39500 | build_large_report.py:97, build_lowvol_filter.py:50, build_mom_filter.py:46 |
| history.lead_picks | n=40 | run_id: 20261001 / 뒤처짐 4거래일 / 유효 n=40; frozen_at: 2026-10-01T21:57:19 / 뒤처짐 4거래일 / 유효 n=40 | build_lead_page.py:4, lead_eval.py:2, lead_observe.py:5 |
| history.lead_universe | n=1,069 | run_id: 20261001 / 뒤처짐 4거래일 / 유효 n=1069 | build_lead_page.py:4, lead_observe.py:187 |
| history.lowvol_scores | n=227,199 | run_id: 20261008 / 뒤처짐 0거래일 / 유효 n=227199; frozen_at: 2026-10-08T20:38:12.896258+09:00 / 뒤처짐 0거래일 / 유효 n=227199 | build_alpha_beta.py:29, build_cross_sim.py:40, build_daily_lists.py:4 |
| history.runs | n=187 | run_id: 20261008 / 뒤처짐 0거래일 / 유효 n=187; run_timestamp: 20261008_2030 / 뒤처짐 0거래일 / 유효 n=187 | analyze_history.py:41, checkup.py:70, accumulate_history.py:10 |
| history.stage1_oversold | n=212,896 | run_id: 20261008 / 뒤처짐 0거래일 / 유효 n=212896; run_timestamp: 20261008_2030 / 뒤처짐 0거래일 / 유효 n=212896 | checkup.py:69, lead_observe.py:201, lowvol_score.py:284 |
| history.stage2_filtered | n=124,311 | run_id: 20261008 / 뒤처짐 0거래일 / 유효 n=124311; run_timestamp: 20261008_2030 / 뒤처짐 0거래일 / 유효 n=124311 | accumulate_history.py:12 |
| history.stage3_final | n=86,072 | run_id: 20261008 / 뒤처짐 0거래일 / 유효 n=86072; run_timestamp: 20261008_2030 / 뒤처짐 0거래일 / 유효 n=86072; annual_year: 2025.0 (연도·보고기간 문자열MAX; 거래일 지연과 구분); q_period: 2026 Q1 (연도·보고기간 문자열MAX; 거래일 지연과 구분) | analyze_history.py:52, build_dashboard.py:134, cleanup.py:100 |
| history.v3_scores | n=336,680 | run_id: 20261008 / 뒤처짐 0거래일 / 유효 n=336680; frozen_at: 2026-10-08T20:33:42+09:00 / 뒤처짐 0거래일 / 유효 n=336680 | build_mom_filter.py:200, build_wu_filter.py:227, build_alpha_beta.py:28 |
| history.wu_scores | n=339,332 | run_id: 20261008 / 뒤처짐 0거래일 / 유효 n=339332; frozen_at: 2026-10-08 20:38:38+0900 / 뒤처짐 0거래일 / 유효 n=339332 | build_alpha_beta.py:30, build_cross_sim.py:43, build_daily_lists.py:4 |
| ohlcv.consensus_daily | n=27,649 | date: 20261006 / 뒤처짐 2거래일 / 유효 n=27649; fetched_at: 20261006_2132 / 뒤처짐 2거래일 / 유효 n=27649 | notify_weekly.py:157, fetch_consensus.py:6 |
| ohlcv.daily_flows | n=269,773 | date: 20261008 / 뒤처짐 0거래일 / 유효 n=269773; fetched_at: 20261008_2015 / 뒤처짐 0거래일 / 유효 n=269773 | factor_scan.py:223, notify_weekly.py:151, wu_factor_scan.py:210 |
| ohlcv.daily_ohlcv | n=2,029,660 | date: 20261008 / 뒤처짐 0거래일 / 유효 n=2029660; fetched_at: 2026-10-08 20:10:03 / 뒤처짐 0거래일 / 유효 n=2029660 | build_alpha_beta.py:37, build_cross_sim.py:164, build_large_test.py:79 |
| ohlcv.daily_ohlcv_extra | n=63,495 | date: 20261008 / 뒤처짐 0거래일 / 유효 n=63495; fetched_at: 20261008_2015 / 뒤처짐 0거래일 / 유효 n=63495 | build_large_test.py:82, build_scoreboard.py:288, earnings_flag.py:161 |
| ohlcv.dart_events | n=16,043 | rcept_dt: 20261008 / 뒤처짐 0거래일 / 유효 n=16043; fetched_at: 2026-10-08 20:39:06 / 뒤처짐 0거래일 / 유효 n=16043 | dart_events.py:2, dilution_flag.py:10, notify_telegram.py:710 |
| ohlcv.market_daily | n=2,515 | date: 20261008 / 뒤처짐 0거래일 / 유효 n=2515 | build_cross_sim.py:171, build_lead_page.py:135, lead_eval.py:32 |
| ohlcv.ohlcv_skips | n=0 | at_date: NULL / 뒤처짐 확인 못 함거래일 / 유효 n=0; fetched_at: NULL / 뒤처짐 확인 못 함거래일 / 유효 n=0 | extra_ohlcv.py:124, universe_ohlcv.py:60 |
| ohlcv.short_flows | n=335,733 | date: 20261008 / 뒤처짐 0거래일 / 유효 n=335733; fetched_at: 20261008_2043 / 뒤처짐 0거래일 / 유효 n=335733 | factor_scan.py:186, notify_weekly.py:152, accumulate_valuation.py:17 |
| ohlcv.universe_events | n=2,362 | date: 20261008 / 뒤처짐 0거래일 / 유효 n=2362 | cleanup.py:260, universe_events.py:3 |
| ohlcv.valuation_daily | n=168,438 | date: 20261008 / 뒤처짐 0거래일 / 유효 n=168438 | notify_weekly.py:155, accumulate_valuation.py:8, cleanup.py:259 |
| earnings.earnings_q | n=30,749 | rcept_dt: 20261007 / 뒤처짐 1거래일 / 유효 n=30749; px_dt: 20261006 / 뒤처짐 2거래일 / 유효 n=1350; year: 2026 (연도·보고기간 문자열MAX; 거래일 지연과 구분) | earnings_flag.py:18, earnings_incr.py:6 |
| earnings.earnings_raw | n=465 | fetched_at: 20261008_2015 / 뒤처짐 0거래일 / 유효 n=465; year: 2026 (연도·보고기간 문자열MAX; 거래일 지연과 구분) | earnings_incr.py:12 |

### 날짜 열이 없는 표

| 표 | 행 수 | 상태 | 사용 파일(줄) |
|---|---|---|---|
| earnings.earnings_meta | n=1 | 날짜 없음; value(last_end)=20261008 | earnings_incr.py:67 |

## 2. 표 안 갈래별 마지막 날짜

개별 구분 열과 market×model_id / market×event_type 조합을 모두 확인했다. NULL 갈래도 포함. 공시·분기·주간·은퇴 모델은 마지막 날짜가 오래되어도 수집 정지로 바로 판정하지 않는다.

| 표 | 갈래 | 행 수 | 날짜 열별 마지막 값(지연은 거래일) |
|---|---|---|---|
| history.large_final | market=kosdaq | n=13,846 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2043 (뒤처짐 0); stage3_src_run=20261008 (뒤처짐 0) |
| history.large_final | market=kospi | n=25,154 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2043 (뒤처짐 0); stage3_src_run=20261008 (뒤처짐 0) |
| history.large_final | buyback_src=catalyst | n=282 | run_id=20260610 (뒤처짐 81); run_timestamp=20260610_2125 (뒤처짐 81); stage3_src_run=20260610 (뒤처짐 81) |
| history.large_final | buyback_src=dart | n=24,741 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2043 (뒤처짐 0); stage3_src_run=20261007 (뒤처짐 1) |
| history.large_final | buyback_src=v3공유 | n=12,452 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2043 (뒤처짐 0); stage3_src_run=20261008 (뒤처짐 0) |
| history.large_final | buyback_src=미등록 | n=1,040 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2043 (뒤처짐 0); stage3_src_run=None (뒤처짐 확인 못 함) |
| history.large_final | buyback_src=미수집 | n=218 | run_id=20260610 (뒤처짐 81); run_timestamp=20260610_2125 (뒤처짐 81); stage3_src_run=20260609 (뒤처짐 82) |
| history.large_final | buyback_src=실패 | n=267 | run_id=20260622 (뒤처짐 73); run_timestamp=20260623_2059 (뒤처짐 72); stage3_src_run=20260619 (뒤처짐 74) |
| history.large_universe | market=kosdaq | n=14,029 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2042 (뒤처짐 0) |
| history.large_universe | market=kospi | n=25,471 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2042 (뒤처짐 0) |
| history.lead_picks | model_id=ld_a | n=20 | run_id=20261001 (뒤처짐 4); frozen_at=2026-10-01T21:57:19 (뒤처짐 4) |
| history.lead_picks | model_id=ld_ctl_amt | n=20 | run_id=20261001 (뒤처짐 4); frozen_at=2026-10-01T21:57:19 (뒤처짐 4) |
| history.lead_picks | market=KOSDAQ | n=18 | run_id=20261001 (뒤처짐 4); frozen_at=2026-10-01T21:57:19 (뒤처짐 4) |
| history.lead_picks | market=KOSPI | n=22 | run_id=20261001 (뒤처짐 4); frozen_at=2026-10-01T21:57:19 (뒤처짐 4) |
| history.lead_picks | market=KOSDAQ, model_id=ld_a | n=15 | run_id=20261001 (뒤처짐 4); frozen_at=2026-10-01T21:57:19 (뒤처짐 4) |
| history.lead_picks | market=KOSDAQ, model_id=ld_ctl_amt | n=3 | run_id=20261001 (뒤처짐 4); frozen_at=2026-10-01T21:57:19 (뒤처짐 4) |
| history.lead_picks | market=KOSPI, model_id=ld_a | n=5 | run_id=20261001 (뒤처짐 4); frozen_at=2026-10-01T21:57:19 (뒤처짐 4) |
| history.lead_picks | market=KOSPI, model_id=ld_ctl_amt | n=17 | run_id=20261001 (뒤처짐 4); frozen_at=2026-10-01T21:57:19 (뒤처짐 4) |
| history.lead_universe | market=KOSDAQ | n=625 | run_id=20261001 (뒤처짐 4) |
| history.lead_universe | market=KOSPI | n=444 | run_id=20261001 (뒤처짐 4) |
| history.lowvol_scores | market=kosdaq | n=141,011 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | market=kospi | n=86,188 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | model_id=hv_a | n=17,709 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | model_id=lv_a | n=21,984 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | model_id=lv_a3 | n=11,062 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | model_id=lv_b | n=21,984 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | model_id=lv_c | n=23,871 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | model_id=lv_d | n=23,871 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | model_id=lv_e | n=21,984 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | model_id=lv_short | n=17,709 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | model_id=mom_a | n=28,169 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | model_id=mom_b | n=25,697 | run_id=20260917 (뒤처짐 12); frozen_at=2026-09-17T20:37:48.145132+09:00 (뒤처짐 12) |
| history.lowvol_scores | model_id=sm_a | n=13,159 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | market=kosdaq, model_id=hv_a | n=11,349 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | market=kosdaq, model_id=lv_a | n=13,514 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | market=kosdaq, model_id=lv_a3 | n=6,985 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | market=kosdaq, model_id=lv_b | n=13,514 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | market=kosdaq, model_id=lv_c | n=14,589 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | market=kosdaq, model_id=lv_d | n=14,589 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | market=kosdaq, model_id=lv_e | n=13,514 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | market=kosdaq, model_id=lv_short | n=11,349 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | market=kosdaq, model_id=mom_a | n=16,769 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | market=kosdaq, model_id=mom_b | n=15,682 | run_id=20260917 (뒤처짐 12); frozen_at=2026-09-17T20:37:48.145132+09:00 (뒤처짐 12) |
| history.lowvol_scores | market=kosdaq, model_id=sm_a | n=9,157 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | market=kospi, model_id=hv_a | n=6,360 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | market=kospi, model_id=lv_a | n=8,470 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | market=kospi, model_id=lv_a3 | n=4,077 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | market=kospi, model_id=lv_b | n=8,470 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | market=kospi, model_id=lv_c | n=9,282 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | market=kospi, model_id=lv_d | n=9,282 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | market=kospi, model_id=lv_e | n=8,470 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | market=kospi, model_id=lv_short | n=6,360 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04T21:28:23.794402+09:00 (뒤처짐 21) |
| history.lowvol_scores | market=kospi, model_id=mom_a | n=11,400 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.lowvol_scores | market=kospi, model_id=mom_b | n=10,015 | run_id=20260917 (뒤처짐 12); frozen_at=2026-09-17T20:37:48.145132+09:00 (뒤처짐 12) |
| history.lowvol_scores | market=kospi, model_id=sm_a | n=4,002 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:38:12.896258+09:00 (뒤처짐 0) |
| history.runs | market=kosdaq | n=94 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2030 (뒤처짐 0) |
| history.runs | market=kospi | n=93 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2027 (뒤처짐 0) |
| history.stage1_oversold | market=kosdaq | n=146,030 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2030 (뒤처짐 0) |
| history.stage1_oversold | market=kospi | n=66,866 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2027 (뒤처짐 0) |
| history.stage2_filtered | market=kosdaq | n=82,368 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2030 (뒤처짐 0) |
| history.stage2_filtered | market=kospi | n=41,943 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2027 (뒤처짐 0) |
| history.stage3_final | market=kosdaq | n=58,640 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2030 (뒤처짐 0) |
| history.stage3_final | market=kospi | n=27,432 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2027 (뒤처짐 0) |
| history.stage3_final | insider_source=NULL | n=20,175 | run_id=20260827 (뒤처짐 27); run_timestamp=20260827_2016 (뒤처짐 27) |
| history.stage3_final | insider_source=OFF | n=65,897 | run_id=20261008 (뒤처짐 0); run_timestamp=20261008_2030 (뒤처짐 0) |
| history.v3_scores | market=kosdaq | n=233,513 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:33:42+09:00 (뒤처짐 0) |
| history.v3_scores | market=kospi | n=103,167 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:33:42+09:00 (뒤처짐 0) |
| history.v3_scores | model_id=v30 | n=74,674 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:33:42+09:00 (뒤처짐 0) |
| history.v3_scores | model_id=v31a | n=48,377 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:20+09:00 (뒤처짐 40) |
| history.v3_scores | model_id=v31b | n=48,377 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:20+09:00 (뒤처짐 40) |
| history.v3_scores | model_id=v31c | n=48,377 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:20+09:00 (뒤처짐 40) |
| history.v3_scores | model_id=v31d | n=48,377 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:21+09:00 (뒤처짐 40) |
| history.v3_scores | model_id=v31f | n=34,249 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:21+09:00 (뒤처짐 40) |
| history.v3_scores | model_id=v31g | n=34,249 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:21+09:00 (뒤처짐 40) |
| history.v3_scores | market=kosdaq, model_id=v30 | n=50,619 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:33:42+09:00 (뒤처짐 0) |
| history.v3_scores | market=kosdaq, model_id=v31a | n=33,806 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:20+09:00 (뒤처짐 40) |
| history.v3_scores | market=kosdaq, model_id=v31b | n=33,806 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:20+09:00 (뒤처짐 40) |
| history.v3_scores | market=kosdaq, model_id=v31c | n=33,806 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:20+09:00 (뒤처짐 40) |
| history.v3_scores | market=kosdaq, model_id=v31d | n=33,806 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:21+09:00 (뒤처짐 40) |
| history.v3_scores | market=kosdaq, model_id=v31f | n=23,835 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:21+09:00 (뒤처짐 40) |
| history.v3_scores | market=kosdaq, model_id=v31g | n=23,835 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:21+09:00 (뒤처짐 40) |
| history.v3_scores | market=kospi, model_id=v30 | n=24,055 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08T20:33:42+09:00 (뒤처짐 0) |
| history.v3_scores | market=kospi, model_id=v31a | n=14,571 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:20+09:00 (뒤처짐 40) |
| history.v3_scores | market=kospi, model_id=v31b | n=14,571 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:20+09:00 (뒤처짐 40) |
| history.v3_scores | market=kospi, model_id=v31c | n=14,571 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:20+09:00 (뒤처짐 40) |
| history.v3_scores | market=kospi, model_id=v31d | n=14,571 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:21+09:00 (뒤처짐 40) |
| history.v3_scores | market=kospi, model_id=v31f | n=10,414 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:21+09:00 (뒤처짐 40) |
| history.v3_scores | market=kospi, model_id=v31g | n=10,414 | run_id=20260807 (뒤처짐 40); frozen_at=2026-08-07T21:13:21+09:00 (뒤처짐 40) |
| history.wu_scores | market=KOSDAQ | n=191,644 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | market=KOSPI | n=147,688 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | model_id=le_a | n=61,283 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | model_id=px_a | n=42,919 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | model_id=qs_a | n=55,958 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | model_id=sv_a | n=61,848 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | model_id=sv_b | n=16,752 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | model_id=wu_a | n=50,443 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04 21:28:40+0900 (뒤처짐 21) |
| history.wu_scores | model_id=wu_b | n=50,129 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04 21:28:40+0900 (뒤처짐 21) |
| history.wu_scores | market=KOSDAQ, model_id=le_a | n=34,452 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | market=KOSDAQ, model_id=px_a | n=24,324 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | market=KOSDAQ, model_id=qs_a | n=31,611 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | market=KOSDAQ, model_id=sv_a | n=34,990 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | market=KOSDAQ, model_id=sv_b | n=9,591 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | market=KOSDAQ, model_id=wu_a | n=28,476 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04 21:28:40+0900 (뒤처짐 21) |
| history.wu_scores | market=KOSDAQ, model_id=wu_b | n=28,200 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04 21:28:40+0900 (뒤처짐 21) |
| history.wu_scores | market=KOSPI, model_id=le_a | n=26,831 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | market=KOSPI, model_id=px_a | n=18,595 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | market=KOSPI, model_id=qs_a | n=24,347 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | market=KOSPI, model_id=sv_a | n=26,858 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | market=KOSPI, model_id=sv_b | n=7,161 | run_id=20261008 (뒤처짐 0); frozen_at=2026-10-08 20:38:38+0900 (뒤처짐 0) |
| history.wu_scores | market=KOSPI, model_id=wu_a | n=21,967 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04 21:28:40+0900 (뒤처짐 21) |
| history.wu_scores | market=KOSPI, model_id=wu_b | n=21,929 | run_id=20260904 (뒤처짐 21); frozen_at=2026-09-04 21:28:40+0900 (뒤처짐 21) |
| ohlcv.daily_ohlcv | market=KOSDAQ | n=1,301,243 | date=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:10:03 (뒤처짐 0) |
| ohlcv.daily_ohlcv | market=KOSPI | n=728,417 | date=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:10:03 (뒤처짐 0) |
| ohlcv.daily_ohlcv_extra | market=KOSDAQ | n=46,579 | date=20261008 (뒤처짐 0); fetched_at=20261008_2015 (뒤처짐 0) |
| ohlcv.daily_ohlcv_extra | market=KOSPI | n=16,916 | date=20261008 (뒤처짐 0); fetched_at=20261008_2015 (뒤처짐 0) |
| ohlcv.dart_events | market=K | n=11,938 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | market=Y | n=4,105 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | event_type=bonus | n=220 | rcept_dt=20261007 (뒤처짐 1); fetched_at=2026-10-07 20:39:53 (뒤처짐 1) |
| ohlcv.dart_events | event_type=buyback | n=2,917 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | event_type=buyback_sell | n=1,801 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | event_type=bw | n=274 | rcept_dt=20261006 (뒤처짐 2); fetched_at=2026-10-06 20:46:40 (뒤처짐 2) |
| ohlcv.dart_events | event_type=cb | n=4,927 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | event_type=eb | n=335 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | event_type=paid_bonus_mix | n=163 | rcept_dt=20260902 (뒤처짐 23); fetched_at=2026-09-02 21:30:59 (뒤처짐 23) |
| ohlcv.dart_events | event_type=paid_in | n=4,906 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | event_type=reduction | n=500 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | market=K, event_type=bonus | n=176 | rcept_dt=20261007 (뒤처짐 1); fetched_at=2026-10-07 20:39:53 (뒤처짐 1) |
| ohlcv.dart_events | market=K, event_type=buyback | n=1,663 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | market=K, event_type=buyback_sell | n=1,102 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | market=K, event_type=bw | n=221 | rcept_dt=20261006 (뒤처짐 2); fetched_at=2026-10-06 20:46:40 (뒤처짐 2) |
| ohlcv.dart_events | market=K, event_type=cb | n=4,150 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | market=K, event_type=eb | n=219 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | market=K, event_type=paid_bonus_mix | n=155 | rcept_dt=20260902 (뒤처짐 23); fetched_at=2026-09-02 21:30:59 (뒤처짐 23) |
| ohlcv.dart_events | market=K, event_type=paid_in | n=3,935 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | market=K, event_type=reduction | n=317 | rcept_dt=20261006 (뒤처짐 2); fetched_at=2026-10-06 20:46:40 (뒤처짐 2) |
| ohlcv.dart_events | market=Y, event_type=bonus | n=44 | rcept_dt=20261006 (뒤처짐 2); fetched_at=2026-10-06 20:46:40 (뒤처짐 2) |
| ohlcv.dart_events | market=Y, event_type=buyback | n=1,254 | rcept_dt=20261006 (뒤처짐 2); fetched_at=2026-10-06 20:46:40 (뒤처짐 2) |
| ohlcv.dart_events | market=Y, event_type=buyback_sell | n=699 | rcept_dt=20261007 (뒤처짐 1); fetched_at=2026-10-07 20:39:53 (뒤처짐 1) |
| ohlcv.dart_events | market=Y, event_type=bw | n=53 | rcept_dt=20260921 (뒤처짐 10); fetched_at=2026-09-21 20:39:41 (뒤처짐 10) |
| ohlcv.dart_events | market=Y, event_type=cb | n=777 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.dart_events | market=Y, event_type=eb | n=116 | rcept_dt=20260608 (뒤처짐 83); fetched_at=2026-08-30 18:40:28 (뒤처짐 26) |
| ohlcv.dart_events | market=Y, event_type=paid_bonus_mix | n=8 | rcept_dt=20240403 (뒤처짐 609); fetched_at=2026-08-30 18:40:28 (뒤처짐 26) |
| ohlcv.dart_events | market=Y, event_type=paid_in | n=971 | rcept_dt=20261007 (뒤처짐 1); fetched_at=2026-10-07 20:39:53 (뒤처짐 1) |
| ohlcv.dart_events | market=Y, event_type=reduction | n=183 | rcept_dt=20261008 (뒤처짐 0); fetched_at=2026-10-08 20:39:06 (뒤처짐 0) |
| ohlcv.market_daily | series=KOSDAQ | n=816 | date=20261008 (뒤처짐 0) |
| ohlcv.market_daily | series=KOSPI | n=816 | date=20261008 (뒤처짐 0) |
| ohlcv.market_daily | series=USDKRW | n=883 | date=20261008 (뒤처짐 0) |
| ohlcv.universe_events | event=DISAPPEARED | n=27 | date=20261007 (뒤처짐 1) |
| ohlcv.universe_events | event=NEW | n=301 | date=20261001 (뒤처짐 4) |
| ohlcv.universe_events | event=RESUMED | n=978 | date=20261008 (뒤처짐 0) |
| ohlcv.universe_events | event=SUSPENDED | n=1,056 | date=20261008 (뒤처짐 0) |
| ohlcv.universe_events | market=KOSDAQ | n=1,706 | date=20261008 (뒤처짐 0) |
| ohlcv.universe_events | market=KOSPI | n=656 | date=20261008 (뒤처짐 0) |
| ohlcv.valuation_daily | market=kosdaq | n=111,709 | date=20261008 (뒤처짐 0) |
| ohlcv.valuation_daily | market=kospi | n=56,729 | date=20261008 (뒤처짐 0) |
| earnings.earnings_q | reprt=H1 | n=9,414 | rcept_dt=20261007 (뒤처짐 1); px_dt=20261006 (뒤처짐 2) |
| earnings.earnings_q | reprt=Q1 | n=7,313 | rcept_dt=20260703 (뒤처짐 64); px_dt=20260529 (뒤처짐 88) |
| earnings.earnings_q | reprt=Q3 | n=7,019 | rcept_dt=20251222 (뒤처짐 192); px_dt=20251127 (뒤처짐 209) |
| earnings.earnings_q | reprt=Y | n=7,003 | rcept_dt=20260430 (뒤처짐 106); px_dt=20260326 (뒤처짐 131) |
| earnings.earnings_q | source=incr | n=1 | rcept_dt=20261007 (뒤처짐 1); px_dt=20261006 (뒤처짐 2) |
| earnings.earnings_q | source=incr/was:research_backfill | n=141 | rcept_dt=20260901 (뒤처짐 24); px_dt=None (뒤처짐 확인 못 함) |
| earnings.earnings_q | source=incr/was:research_backfill/mcap_refix | n=10 | rcept_dt=20260814 (뒤처짐 35); px_dt=20260813 (뒤처짐 36) |
| earnings.earnings_q | source=incr/was:research_backfill/shares_jump | n=3 | rcept_dt=20260814 (뒤처짐 35); px_dt=None (뒤처짐 확인 못 함) |
| earnings.earnings_q | source=research_backfill | n=28,881 | rcept_dt=20260831 (뒤처짐 25); px_dt=None (뒤처짐 확인 못 함) |
| earnings.earnings_q | source=research_backfill/mcap_refix | n=1,339 | rcept_dt=20260831 (뒤처짐 25); px_dt=20260828 (뒤처짐 26) |
| earnings.earnings_q | source=research_backfill/shares_jump | n=374 | rcept_dt=20260814 (뒤처짐 35); px_dt=None (뒤처짐 확인 못 함) |
| earnings.earnings_raw | reprt=H1 | n=310 | fetched_at=20261008_2015 (뒤처짐 0) |
| earnings.earnings_raw | reprt=Q1 | n=155 | fetched_at=20261008_2015 (뒤처짐 0) |
| earnings.earnings_raw | fs=CFS | n=356 | fetched_at=20261008_2015 (뒤처짐 0) |
| earnings.earnings_raw | fs=OFS | n=109 | fetched_at=20261008_2015 (뒤처짐 0) |

## 3. 최근 n=60거래일 날짜별 행·종목 수 급감

최근 n=80거래일을 읽어 각 날짜 직전 n=20일 중앙값을 만들었다. 현재 행 수 또는 종목 수가 중앙값의 70% 미만이면 아래에 적었다(0 포함). 집계는 날짜별 모든 run 합계이며 같은 날짜 재실행은 행 수에 중복될 수 있다. 종목 수는 시장 안에서 중복 제거. 종목이 없는 표에는 종목 수를 적용하지 않았다. 등록 전·월별·주간·공시 자료의 0은 정상일 수 있다.

| 표 | 기준 날짜 열 | 시장 | 비어 있지 않은 날 | 0인 날짜(연속 거래일 묶음) | 70% 미만 |
|---|---|---|---|---|---|
| history.large_final | run_id | kosdaq | n=56/60일 | 20260716, 20260813, 20260820, 20260910 | n=4일 |
| history.large_final | run_id | kospi | n=56/60일 | 20260716, 20260813, 20260820, 20260910 | n=4일 |
| history.large_final | run_id | 전체 | n=56/60일 | 20260716, 20260813, 20260820, 20260910 | n=4일 |
| history.large_universe | run_id | kosdaq | n=56/60일 | 20260716, 20260813, 20260820, 20260910 | n=4일 |
| history.large_universe | run_id | kospi | n=56/60일 | 20260716, 20260813, 20260820, 20260910 | n=4일 |
| history.large_universe | run_id | 전체 | n=56/60일 | 20260716, 20260813, 20260820, 20260910 | n=4일 |
| history.lead_picks | run_id | kosdaq | n=1/60일 | 20260710~20260930(n=55일), 20261002~20261008(n=4일) | n=0일 |
| history.lead_picks | run_id | kospi | n=1/60일 | 20260710~20260930(n=55일), 20261002~20261008(n=4일) | n=0일 |
| history.lead_picks | run_id | 전체 | n=1/60일 | 20260710~20260930(n=55일), 20261002~20261008(n=4일) | n=0일 |
| history.lead_universe | run_id | kosdaq | n=1/60일 | 20260710~20260930(n=55일), 20261002~20261008(n=4일) | n=0일 |
| history.lead_universe | run_id | kospi | n=1/60일 | 20260710~20260930(n=55일), 20261002~20261008(n=4일) | n=0일 |
| history.lead_universe | run_id | 전체 | n=1/60일 | 20260710~20260930(n=55일), 20261002~20261008(n=4일) | n=0일 |
| history.lowvol_scores | run_id | kosdaq | n=57/60일 | 20260813, 20260820, 20260910 | n=26일 |
| history.lowvol_scores | run_id | kospi | n=57/60일 | 20260813, 20260820, 20260910 | n=14일 |
| history.lowvol_scores | run_id | 전체 | n=57/60일 | 20260813, 20260820, 20260910 | n=13일 |
| history.runs | run_id | kosdaq | n=57/60일 | 20260813, 20260820, 20260910 | n=3일 |
| history.runs | run_id | kospi | n=57/60일 | 20260813, 20260820, 20260910 | n=3일 |
| history.runs | run_id | 전체 | n=57/60일 | 20260813, 20260820, 20260910 | n=3일 |
| history.stage1_oversold | run_id | kosdaq | n=57/60일 | 20260813, 20260820, 20260910 | n=3일 |
| history.stage1_oversold | run_id | kospi | n=57/60일 | 20260813, 20260820, 20260910 | n=3일 |
| history.stage1_oversold | run_id | 전체 | n=57/60일 | 20260813, 20260820, 20260910 | n=3일 |
| history.stage2_filtered | run_id | kosdaq | n=57/60일 | 20260813, 20260820, 20260910 | n=12일 |
| history.stage2_filtered | run_id | kospi | n=57/60일 | 20260813, 20260820, 20260910 | n=13일 |
| history.stage2_filtered | run_id | 전체 | n=57/60일 | 20260813, 20260820, 20260910 | n=13일 |
| history.stage3_final | run_id | kosdaq | n=57/60일 | 20260813, 20260820, 20260910 | n=18일 |
| history.stage3_final | run_id | kospi | n=57/60일 | 20260813, 20260820, 20260910 | n=18일 |
| history.stage3_final | run_id | 전체 | n=57/60일 | 20260813, 20260820, 20260910 | n=17일 |
| history.v3_scores | run_id | kosdaq | n=57/60일 | 20260813, 20260820, 20260910 | n=21일 |
| history.v3_scores | run_id | kospi | n=57/60일 | 20260813, 20260820, 20260910 | n=21일 |
| history.v3_scores | run_id | 전체 | n=57/60일 | 20260813, 20260820, 20260910 | n=20일 |
| history.wu_scores | run_id | kosdaq | n=60/60일 | 없음 | n=5일 |
| history.wu_scores | run_id | kospi | n=60/60일 | 없음 | n=5일 |
| history.wu_scores | run_id | 전체 | n=60/60일 | 없음 | n=5일 |
| ohlcv.consensus_daily | date | kosdaq | n=10/60일 | 20260710~20260724(n=10일), 20260728~20260731(n=4일), 20260804~20260807(n=4일), 20260811~20260821(n=8일), 20260825~20260828(n=4일), 20260901~20260904(n=4일), 20260908~20260916(n=7일), 20260918~20260921(n=2일), 20260923, 20260929~20261002(n=4일), 20261007~20261008(n=2일) | n=0일 |
| ohlcv.consensus_daily | date | kospi | n=10/60일 | 20260710~20260724(n=10일), 20260728~20260731(n=4일), 20260804~20260807(n=4일), 20260811~20260821(n=8일), 20260825~20260828(n=4일), 20260901~20260904(n=4일), 20260908~20260916(n=7일), 20260918~20260921(n=2일), 20260923, 20260929~20261002(n=4일), 20261007~20261008(n=2일) | n=0일 |
| ohlcv.consensus_daily | date | 전체 | n=10/60일 | 20260710~20260724(n=10일), 20260728~20260731(n=4일), 20260804~20260807(n=4일), 20260811~20260821(n=8일), 20260825~20260828(n=4일), 20260901~20260904(n=4일), 20260908~20260916(n=7일), 20260918~20260921(n=2일), 20260923, 20260929~20261002(n=4일), 20261007~20261008(n=2일) | n=0일 |
| ohlcv.consensus_daily | date | 확인 못 함 | n=9/60일 | 20260710~20260724(n=10일), 20260728~20260731(n=4일), 20260804~20260807(n=4일), 20260811~20260821(n=8일), 20260825~20260828(n=4일), 20260901~20260904(n=4일), 20260908~20260916(n=7일), 20260918~20260923(n=4일), 20260929~20261002(n=4일), 20261007~20261008(n=2일) | n=0일 |
| ohlcv.daily_flows | date | kosdaq | n=60/60일 | 없음 | n=0일 |
| ohlcv.daily_flows | date | kospi | n=60/60일 | 없음 | n=0일 |
| ohlcv.daily_flows | date | 전체 | n=60/60일 | 없음 | n=0일 |
| ohlcv.daily_flows | date | 확인 못 함 | n=58/60일 | 20261007~20261008(n=2일) | n=26일 |
| ohlcv.daily_ohlcv | date | kosdaq | n=60/60일 | 없음 | n=0일 |
| ohlcv.daily_ohlcv | date | kospi | n=60/60일 | 없음 | n=0일 |
| ohlcv.daily_ohlcv | date | 전체 | n=60/60일 | 없음 | n=0일 |
| ohlcv.daily_ohlcv_extra | date | kosdaq | n=60/60일 | 없음 | n=0일 |
| ohlcv.daily_ohlcv_extra | date | kospi | n=60/60일 | 없음 | n=0일 |
| ohlcv.daily_ohlcv_extra | date | 전체 | n=60/60일 | 없음 | n=0일 |
| ohlcv.dart_events | rcept_dt | k | n=60/60일 | 없음 | n=10일 |
| ohlcv.dart_events | rcept_dt | kosdaq | n=0/60일 | 20260710~20261008(n=60일) | n=0일 |
| ohlcv.dart_events | rcept_dt | kospi | n=0/60일 | 20260710~20261008(n=60일) | n=0일 |
| ohlcv.dart_events | rcept_dt | y | n=60/60일 | 없음 | n=18일 |
| ohlcv.dart_events | rcept_dt | 전체 | n=60/60일 | 없음 | n=8일 |
| ohlcv.market_daily | date | kosdaq | n=60/60일 | 없음 | n=0일 |
| ohlcv.market_daily | date | kospi | n=60/60일 | 없음 | n=0일 |
| ohlcv.market_daily | date | usdkrw | n=59/60일 | 20260710 | n=1일 |
| ohlcv.market_daily | date | 전체 | n=60/60일 | 없음 | n=1일 |
| ohlcv.ohlcv_skips | at_date | kosdaq | n=0/60일 | 20260710~20261008(n=60일) | n=0일 |
| ohlcv.ohlcv_skips | at_date | kospi | n=0/60일 | 20260710~20261008(n=60일) | n=0일 |
| ohlcv.ohlcv_skips | at_date | 전체 | n=0/60일 | 20260710~20261008(n=60일) | n=0일 |
| ohlcv.short_flows | date | kosdaq | n=60/60일 | 없음 | n=0일 |
| ohlcv.short_flows | date | kospi | n=60/60일 | 없음 | n=0일 |
| ohlcv.short_flows | date | 전체 | n=60/60일 | 없음 | n=0일 |
| ohlcv.short_flows | date | 확인 못 함 | n=58/60일 | 20261007~20261008(n=2일) | n=27일 |
| ohlcv.universe_events | date | kosdaq | n=56/60일 | 20260716, 20260813, 20260820, 20260910 | n=15일 |
| ohlcv.universe_events | date | kospi | n=45/60일 | 20260710~20260713(n=2일), 20260716, 20260723, 20260729, 20260803, 20260812~20260813(n=2일), 20260818~20260820(n=3일), 20260904, 20260910, 20260916, 20260930 | n=27일 |
| ohlcv.universe_events | date | 전체 | n=56/60일 | 20260716, 20260813, 20260820, 20260910 | n=12일 |
| ohlcv.valuation_daily | date | kosdaq | n=57/60일 | 20260813, 20260820, 20260910 | n=3일 |
| ohlcv.valuation_daily | date | kospi | n=57/60일 | 20260813, 20260820, 20260910 | n=3일 |
| ohlcv.valuation_daily | date | 전체 | n=57/60일 | 20260813, 20260820, 20260910 | n=3일 |
| earnings.earnings_q | rcept_dt | kosdaq | n=22/60일 | 20260710~20260730(n=14일), 20260824, 20260902~20261006(n=22일), 20261008 | n=12일 |
| earnings.earnings_q | rcept_dt | kospi | n=6/60일 | 20260710~20260806(n=19일), 20260810, 20260818~20260827(n=8일), 20260831~20261008(n=26일) | n=0일 |
| earnings.earnings_q | rcept_dt | 전체 | n=22/60일 | 20260710~20260730(n=14일), 20260824, 20260902~20261006(n=22일), 20261008 | n=12일 |
| earnings.earnings_q | rcept_dt | 확인 못 함 | n=2/60일 | 20260710~20260812(n=23일), 20260818~20261008(n=35일) | n=0일 |
| earnings.earnings_raw | fetched_at | kosdaq | n=2/60일 | 20260710~20261006(n=58일) | n=0일 |
| earnings.earnings_raw | fetched_at | kospi | n=2/60일 | 20260710~20261006(n=58일) | n=0일 |
| earnings.earnings_raw | fetched_at | 전체 | n=2/60일 | 20260710~20261006(n=58일) | n=0일 |

### 70% 미만 날짜 전부

| 표 | 시장 | 날짜 | 행 | 종목 | 직전20일 행 중앙값 | 종목 중앙값 | 해석 |
|---|---|---|---|---|---|---|---|
| history.large_final | kosdaq | 20260716 | n=0 | n=0 | 179 | 179 | 확인 필요 |
| history.large_final | kosdaq | 20260813 | n=0 | n=0 | 176 | 176 | 확인 필요 |
| history.large_final | kosdaq | 20260820 | n=0 | n=0 | 176.5 | 176.5 | 확인 필요 |
| history.large_final | kosdaq | 20260910 | n=0 | n=0 | 175 | 175 | 확인 필요 |
| history.large_final | kospi | 20260716 | n=0 | n=0 | 318.5 | 318.5 | 확인 필요 |
| history.large_final | kospi | 20260813 | n=0 | n=0 | 324 | 324 | 확인 필요 |
| history.large_final | kospi | 20260820 | n=0 | n=0 | 323 | 323 | 확인 필요 |
| history.large_final | kospi | 20260910 | n=0 | n=0 | 324.5 | 324.5 | 확인 필요 |
| history.large_final | 전체 | 20260716 | n=0 | n=0 | 500 | 500 | 확인 필요 |
| history.large_final | 전체 | 20260813 | n=0 | n=0 | 500 | 500 | 확인 필요 |
| history.large_final | 전체 | 20260820 | n=0 | n=0 | 500 | 500 | 확인 필요 |
| history.large_final | 전체 | 20260910 | n=0 | n=0 | 500 | 500 | 확인 필요 |
| history.large_universe | kosdaq | 20260716 | n=0 | n=0 | 179 | 179 | 확인 필요 |
| history.large_universe | kosdaq | 20260813 | n=0 | n=0 | 176 | 176 | 확인 필요 |
| history.large_universe | kosdaq | 20260820 | n=0 | n=0 | 176.5 | 176.5 | 확인 필요 |
| history.large_universe | kosdaq | 20260910 | n=0 | n=0 | 175 | 175 | 확인 필요 |
| history.large_universe | kospi | 20260716 | n=0 | n=0 | 318.5 | 318.5 | 확인 필요 |
| history.large_universe | kospi | 20260813 | n=0 | n=0 | 324 | 324 | 확인 필요 |
| history.large_universe | kospi | 20260820 | n=0 | n=0 | 323 | 323 | 확인 필요 |
| history.large_universe | kospi | 20260910 | n=0 | n=0 | 324.5 | 324.5 | 확인 필요 |
| history.large_universe | 전체 | 20260716 | n=0 | n=0 | 500 | 500 | 확인 필요 |
| history.large_universe | 전체 | 20260813 | n=0 | n=0 | 500 | 500 | 확인 필요 |
| history.large_universe | 전체 | 20260820 | n=0 | n=0 | 500 | 500 | 확인 필요 |
| history.large_universe | 전체 | 20260910 | n=0 | n=0 | 500 | 500 | 확인 필요 |
| history.lowvol_scores | kosdaq | 20260729 | n=1637 | n=292 | 2400 | 403 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260804 | n=1032 | n=141 | 2356.5 | 392 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260805 | n=867 | n=125 | 2356.5 | 387.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260806 | n=797 | n=111 | 2356.5 | 377 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260807 | n=436 | n=71 | 2356.5 | 377 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260810 | n=242 | n=40 | 2356.5 | 377 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260811 | n=199 | n=26 | 2254 | 360.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260812 | n=168 | n=28 | 2125 | 342 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260813 | n=0 | n=0 | 1933.5 | 330.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260814 | n=95 | n=21 | 1744 | 315.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260818 | n=159 | n=37 | 1655 | 297 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260819 | n=173 | n=39 | 1334.5 | 216.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260820 | n=0 | n=0 | 949.5 | 133 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260910 | n=0 | n=0 | 890.5 | 174.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260911 | n=601 | n=181 | 890.5 | 174.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260918 | n=546 | n=213 | 890.5 | 229.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260921 | n=598 | n=235 | 890.5 | 229.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260922 | n=497 | n=200 | 880.5 | 232.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260923 | n=488 | n=194 | 835 | 232.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260928 | n=474 | n=198 | 790 | 232.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260929 | n=508 | n=208 | 768 | 232.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20260930 | n=480 | n=192 | 751.5 | 232.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20261001 | n=421 | n=166 | 732 | 229.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20261002 | n=383 | n=155 | 662 | 224.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20261006 | n=297 | n=123 | 599.5 | 216.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kosdaq | 20261007 | n=326 | n=134 | 572 | 210.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260715 | n=764 | n=144 | 1463 | 210.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260804 | n=360 | n=70 | 1345 | 185.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260805 | n=313 | n=59 | 1320.5 | 182.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260806 | n=316 | n=59 | 1303 | 181 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260807 | n=178 | n=33 | 1294 | 176 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260810 | n=164 | n=28 | 1284.5 | 170.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260811 | n=171 | n=28 | 1281 | 170 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260812 | n=206 | n=32 | 1274.5 | 169 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260813 | n=0 | n=0 | 1250.5 | 167 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260814 | n=95 | n=18 | 1250.5 | 167 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260818 | n=158 | n=26 | 1136 | 150.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260819 | n=156 | n=29 | 701 | 101.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260820 | n=0 | n=0 | 338 | 64.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | kospi | 20260910 | n=0 | n=0 | 436 | 69.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260804 | n=1392 | n=211 | 3797.5 | 567 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260805 | n=1180 | n=184 | 3729 | 557.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260806 | n=1113 | n=170 | 3716 | 551.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260807 | n=614 | n=104 | 3716 | 551.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260810 | n=406 | n=68 | 3716 | 551.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260811 | n=370 | n=54 | 3561.5 | 541.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260812 | n=374 | n=60 | 3400 | 530.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260813 | n=0 | n=0 | 3220.5 | 520 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260814 | n=190 | n=39 | 3003.5 | 492 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260818 | n=317 | n=63 | 2912 | 468.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260819 | n=329 | n=68 | 2156.5 | 338 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260820 | n=0 | n=0 | 1286 | 197.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.lowvol_scores | 전체 | 20260910 | n=0 | n=0 | 1337.5 | 236 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.runs | kosdaq | 20260813 | n=0 | 종목 열 없음 | 1 | 해당 없음 | 확인 필요 |
| history.runs | kosdaq | 20260820 | n=0 | 종목 열 없음 | 1 | 해당 없음 | 확인 필요 |
| history.runs | kosdaq | 20260910 | n=0 | 종목 열 없음 | 1 | 해당 없음 | 확인 필요 |
| history.runs | kospi | 20260813 | n=0 | 종목 열 없음 | 1 | 해당 없음 | 확인 필요 |
| history.runs | kospi | 20260820 | n=0 | 종목 열 없음 | 1 | 해당 없음 | 확인 필요 |
| history.runs | kospi | 20260910 | n=0 | 종목 열 없음 | 1 | 해당 없음 | 확인 필요 |
| history.runs | 전체 | 20260813 | n=0 | 종목 열 없음 | 2 | 해당 없음 | 확인 필요 |
| history.runs | 전체 | 20260820 | n=0 | 종목 열 없음 | 2 | 해당 없음 | 확인 필요 |
| history.runs | 전체 | 20260910 | n=0 | 종목 열 없음 | 2 | 해당 없음 | 확인 필요 |
| history.stage1_oversold | kosdaq | 20260813 | n=0 | n=0 | 1551.5 | 1551.5 | 확인 필요 |
| history.stage1_oversold | kosdaq | 20260820 | n=0 | n=0 | 1558.5 | 1558.5 | 확인 필요 |
| history.stage1_oversold | kosdaq | 20260910 | n=0 | n=0 | 1591.5 | 1591.5 | 확인 필요 |
| history.stage1_oversold | kospi | 20260813 | n=0 | n=0 | 720.5 | 720.5 | 확인 필요 |
| history.stage1_oversold | kospi | 20260820 | n=0 | n=0 | 724.5 | 724.5 | 확인 필요 |
| history.stage1_oversold | kospi | 20260910 | n=0 | n=0 | 728.5 | 728.5 | 확인 필요 |
| history.stage1_oversold | 전체 | 20260813 | n=0 | n=0 | 2272 | 2272 | 확인 필요 |
| history.stage1_oversold | 전체 | 20260820 | n=0 | n=0 | 2282 | 2282 | 확인 필요 |
| history.stage1_oversold | 전체 | 20260910 | n=0 | n=0 | 2316 | 2316 | 확인 필요 |
| history.stage2_filtered | kosdaq | 20260807 | n=419 | n=419 | 904 | 904 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kosdaq | 20260810 | n=559 | n=559 | 881.5 | 881.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kosdaq | 20260811 | n=333 | n=333 | 881.5 | 881.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kosdaq | 20260812 | n=250 | n=250 | 869 | 869 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kosdaq | 20260813 | n=0 | n=0 | 845 | 845 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kosdaq | 20260814 | n=494 | n=494 | 845 | 845 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kosdaq | 20260818 | n=248 | n=248 | 845 | 845 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kosdaq | 20260819 | n=182 | n=182 | 812.5 | 812.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kosdaq | 20260820 | n=0 | n=0 | 762 | 762 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kosdaq | 20260821 | n=284 | n=284 | 695.5 | 695.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kosdaq | 20260824 | n=364 | n=364 | 606.5 | 606.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kosdaq | 20260910 | n=0 | n=0 | 656.5 | 656.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260710 | n=365 | n=365 | 547 | 547 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260807 | n=282 | n=282 | 459.5 | 459.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260811 | n=208 | n=208 | 445.5 | 445.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260812 | n=174 | n=174 | 445.5 | 445.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260813 | n=0 | n=0 | 445.5 | 445.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260814 | n=293 | n=293 | 445.5 | 445.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260818 | n=211 | n=211 | 445.5 | 445.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260819 | n=164 | n=164 | 441.5 | 441.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260820 | n=0 | n=0 | 439.5 | 439.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260821 | n=222 | n=222 | 428.5 | 428.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260824 | n=174 | n=174 | 374 | 374 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260825 | n=188 | n=188 | 311.5 | 311.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | kospi | 20260910 | n=0 | n=0 | 280.5 | 280.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260807 | n=701 | n=701 | 1359 | 1359 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260810 | n=889 | n=889 | 1330 | 1330 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260811 | n=541 | n=541 | 1330 | 1330 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260812 | n=424 | n=424 | 1330 | 1330 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260813 | n=0 | n=0 | 1307 | 1307 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260814 | n=787 | n=787 | 1307 | 1307 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260818 | n=459 | n=459 | 1307 | 1307 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260819 | n=346 | n=346 | 1279 | 1279 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260820 | n=0 | n=0 | 1227.5 | 1227.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260821 | n=506 | n=506 | 1162.5 | 1162.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260824 | n=538 | n=538 | 1014.5 | 1014.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260825 | n=585 | n=585 | 838 | 838 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage2_filtered | 전체 | 20260910 | n=0 | n=0 | 928.5 | 928.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260715 | n=503 | n=503 | 836 | 836 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260716 | n=510 | n=510 | 836 | 836 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260723 | n=446 | n=446 | 812 | 812 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260803 | n=526 | n=526 | 807.5 | 807.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260804 | n=218 | n=218 | 775.5 | 775.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260805 | n=186 | n=186 | 752.5 | 752.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260806 | n=175 | n=175 | 716 | 716 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260807 | n=117 | n=117 | 661 | 661 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260810 | n=76 | n=76 | 636.5 | 636.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260811 | n=60 | n=60 | 592 | 592 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260812 | n=57 | n=57 | 537 | 537 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260813 | n=0 | n=0 | 518 | 518 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260814 | n=56 | n=56 | 518 | 518 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260818 | n=77 | n=77 | 486 | 486 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260819 | n=71 | n=71 | 332 | 332 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260820 | n=0 | n=0 | 202 | 202 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20260910 | n=0 | n=0 | 247.5 | 247.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kosdaq | 20261006 | n=265 | n=265 | 418 | 418 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260710 | n=236 | n=236 | 353 | 353 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260715 | n=208 | n=208 | 341 | 341 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260716 | n=211 | n=211 | 341 | 341 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260723 | n=163 | n=163 | 339 | 339 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260727 | n=220 | n=220 | 319 | 319 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260804 | n=117 | n=117 | 319 | 319 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260805 | n=94 | n=94 | 296 | 296 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260806 | n=96 | n=96 | 272.5 | 272.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260807 | n=55 | n=55 | 249 | 249 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260810 | n=43 | n=43 | 238.5 | 238.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260811 | n=41 | n=41 | 238 | 238 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260812 | n=55 | n=55 | 227.5 | 227.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260813 | n=0 | n=0 | 215.5 | 215.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260814 | n=38 | n=38 | 215.5 | 215.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260818 | n=47 | n=47 | 191.5 | 191.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260819 | n=55 | n=55 | 140 | 140 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260820 | n=0 | n=0 | 106.5 | 106.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | kospi | 20260910 | n=0 | n=0 | 95.5 | 95.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260715 | n=711 | n=711 | 1186.5 | 1186.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260716 | n=721 | n=721 | 1186.5 | 1186.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260723 | n=609 | n=609 | 1167.5 | 1167.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260803 | n=767 | n=767 | 1154 | 1154 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260804 | n=335 | n=335 | 1094.5 | 1094.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260805 | n=280 | n=280 | 1048.5 | 1048.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260806 | n=271 | n=271 | 988.5 | 988.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260807 | n=172 | n=172 | 907.5 | 907.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260810 | n=119 | n=119 | 872 | 872 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260811 | n=101 | n=101 | 819.5 | 819.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260812 | n=112 | n=112 | 767.5 | 767.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260813 | n=0 | n=0 | 744 | 744 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260814 | n=94 | n=94 | 744 | 744 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260818 | n=124 | n=124 | 688 | 688 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260819 | n=126 | n=126 | 472 | 472 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260820 | n=0 | n=0 | 307.5 | 307.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.stage3_final | 전체 | 20260910 | n=0 | n=0 | 332 | 332 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260715 | n=3521 | n=503 | 5684 | 842 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260716 | n=3570 | n=510 | 5684 | 842 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260723 | n=3122 | n=446 | 5684 | 812 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260803 | n=3682 | n=526 | 5652.5 | 807.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260804 | n=1526 | n=218 | 5428.5 | 775.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260805 | n=1302 | n=186 | 5267.5 | 752.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260806 | n=1225 | n=175 | 5012 | 716 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260807 | n=819 | n=117 | 4627 | 661 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260810 | n=76 | n=76 | 4455.5 | 636.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260811 | n=60 | n=60 | 4144 | 592 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260812 | n=57 | n=57 | 3759 | 537 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260813 | n=0 | n=0 | 3626 | 518 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260814 | n=56 | n=56 | 3626 | 518 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260818 | n=77 | n=77 | 3402 | 486 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260819 | n=71 | n=71 | 2324 | 332 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260820 | n=0 | n=0 | 1414 | 202 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260821 | n=170 | n=170 | 1263.5 | 180.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260824 | n=207 | n=207 | 1022 | 172.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260825 | n=205 | n=205 | 513 | 172.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20260910 | n=0 | n=0 | 247.5 | 247.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kosdaq | 20261006 | n=265 | n=265 | 418 | 418 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260710 | n=1652 | n=236 | 2373 | 366.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260715 | n=1456 | n=208 | 2373 | 350 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260716 | n=1477 | n=211 | 2373 | 350 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260723 | n=1141 | n=163 | 2373 | 339 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260727 | n=1540 | n=220 | 2233 | 319 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260804 | n=819 | n=117 | 2233 | 319 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260805 | n=658 | n=94 | 2072 | 296 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260806 | n=672 | n=96 | 1907.5 | 272.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260807 | n=385 | n=55 | 1743 | 249 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260810 | n=43 | n=43 | 1669.5 | 238.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260811 | n=41 | n=41 | 1666 | 238 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260812 | n=55 | n=55 | 1592.5 | 227.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260813 | n=0 | n=0 | 1508.5 | 215.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260814 | n=38 | n=38 | 1508.5 | 215.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260818 | n=47 | n=47 | 1340.5 | 191.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260819 | n=55 | n=55 | 980 | 140 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260820 | n=0 | n=0 | 745.5 | 106.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260821 | n=97 | n=97 | 665 | 95 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260824 | n=77 | n=77 | 521.5 | 95 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260825 | n=79 | n=79 | 241 | 85.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | kospi | 20260910 | n=0 | n=0 | 95.5 | 95.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260715 | n=4977 | n=711 | 8179.5 | 1193 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260716 | n=5047 | n=721 | 8179.5 | 1193 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260723 | n=4263 | n=609 | 8172.5 | 1167.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260803 | n=5369 | n=767 | 8078 | 1154 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260804 | n=2345 | n=335 | 7661.5 | 1094.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260805 | n=1960 | n=280 | 7339.5 | 1048.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260806 | n=1897 | n=271 | 6919.5 | 988.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260807 | n=1204 | n=172 | 6352.5 | 907.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260810 | n=119 | n=119 | 6104 | 872 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260811 | n=101 | n=101 | 5736.5 | 819.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260812 | n=112 | n=112 | 5372.5 | 767.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260813 | n=0 | n=0 | 5208 | 744 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260814 | n=94 | n=94 | 5208 | 744 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260818 | n=124 | n=124 | 4816 | 688 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260819 | n=126 | n=126 | 3304 | 472 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260820 | n=0 | n=0 | 2152.5 | 307.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260821 | n=267 | n=267 | 1928.5 | 275.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260824 | n=284 | n=284 | 1550.5 | 269 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260825 | n=284 | n=284 | 744 | 269 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.v3_scores | 전체 | 20260910 | n=0 | n=0 | 332 | 332 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | kosdaq | 20260907 | n=2483 | n=626 | 3696 | 621 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | kosdaq | 20260908 | n=2455 | n=619 | 3696 | 621.5 | 알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요); 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | kosdaq | 20260909 | n=2403 | n=606 | 3696 | 621.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | kosdaq | 20260910 | n=2414 | n=609 | 3696 | 621.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | kosdaq | 20260911 | n=2400 | n=605 | 3696 | 621.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | kospi | 20260907 | n=1908 | n=477 | 2837 | 473.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | kospi | 20260908 | n=1892 | n=473 | 2837 | 474 | 알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요); 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | kospi | 20260909 | n=1907 | n=477 | 2837 | 474 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | kospi | 20260910 | n=1912 | n=478 | 2837 | 475.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | kospi | 20260911 | n=1872 | n=468 | 2837 | 476.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | 전체 | 20260907 | n=4391 | n=1103 | 6559.5 | 1098 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | 전체 | 20260908 | n=4347 | n=1092 | 6559.5 | 1100.5 | 알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요); 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | 전체 | 20260909 | n=4310 | n=1083 | 6559.5 | 1100.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | 전체 | 20260910 | n=4326 | n=1087 | 6559.5 | 1100.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| history.wu_scores | 전체 | 20260911 | n=4272 | n=1073 | 6559.5 | 1100.5 | 확인 필요; 후보 수·신규/은퇴 영향 구분 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260710 | n=7 | n=7 | 138 | 138 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260713 | n=8 | n=8 | 75.5 | 75.5 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260714 | n=8 | n=8 | 13 | 13 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260715 | n=8 | n=8 | 11.5 | 11.5 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260901 | n=4 | n=4 | 6 | 6 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260902 | n=4 | n=4 | 6 | 6 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260903 | n=3 | n=3 | 6 | 6 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260904 | n=3 | n=3 | 6 | 6 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260907 | n=3 | n=3 | 6 | 6 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260908 | n=3 | n=3 | 5.5 | 5.5 | 알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요) |
| ohlcv.daily_flows | 확인 못 함 | 20260909 | n=3 | n=3 | 5 | 5 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260910 | n=3 | n=3 | 5 | 5 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260911 | n=3 | n=3 | 5 | 5 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260914 | n=3 | n=3 | 5 | 5 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260915 | n=3 | n=3 | 4.5 | 4.5 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260921 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260922 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260923 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260928 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260929 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20260930 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20261001 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20261002 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20261006 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20261007 | n=0 | n=0 | 3 | 3 | 확인 필요 |
| ohlcv.daily_flows | 확인 못 함 | 20261008 | n=0 | n=0 | 2 | 2 | 확인 필요 |
| ohlcv.dart_events | k | 20260727 | n=7 | n=7 | 19 | 15.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | k | 20260803 | n=11 | n=9 | 18.5 | 14.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | k | 20260805 | n=11 | n=11 | 18.5 | 14.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | k | 20260810 | n=7 | n=7 | 18.5 | 15 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | k | 20260824 | n=18 | n=10 | 17.5 | 14.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | k | 20260825 | n=11 | n=9 | 18 | 14.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | k | 20260902 | n=12 | n=11 | 18 | 15.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | k | 20260907 | n=10 | n=10 | 18 | 15 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | k | 20260908 | n=11 | n=10 | 18 | 15 | 알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요); 비일별·사건/주기 자료 |
| ohlcv.dart_events | k | 20260916 | n=13 | n=11 | 19 | 14.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260720 | n=2 | n=2 | 6 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260722 | n=2 | n=2 | 5.5 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260804 | n=2 | n=2 | 5.5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260806 | n=2 | n=2 | 5.5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260811 | n=1 | n=1 | 5.5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260818 | n=1 | n=1 | 5 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260820 | n=2 | n=2 | 5 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260821 | n=3 | n=2 | 5 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260824 | n=3 | n=3 | 4.5 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260826 | n=2 | n=2 | 4 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260902 | n=1 | n=1 | 4 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260907 | n=2 | n=2 | 4 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260908 | n=2 | n=2 | 4 | 4 | 알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요); 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260915 | n=2 | n=2 | 3.5 | 3.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260916 | n=4 | n=2 | 3.5 | 3.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20260923 | n=1 | n=1 | 4 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20261002 | n=2 | n=2 | 4 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | y | 20261008 | n=3 | n=2 | 4 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | 전체 | 20260727 | n=12 | n=12 | 25 | 20.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | 전체 | 20260803 | n=16 | n=14 | 24.5 | 19.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | 전체 | 20260810 | n=14 | n=13 | 24 | 19.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | 전체 | 20260818 | n=15 | n=15 | 22.5 | 19.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | 전체 | 20260902 | n=13 | n=12 | 21.5 | 18 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | 전체 | 20260907 | n=12 | n=12 | 21.5 | 18.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.dart_events | 전체 | 20260908 | n=13 | n=12 | 21 | 18 | 알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요); 비일별·사건/주기 자료 |
| ohlcv.dart_events | 전체 | 20260923 | n=16 | n=13 | 23.5 | 19 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.market_daily | usdkrw | 20260710 | n=0 | 종목 열 없음 | 1 | 해당 없음 | 확인 필요 |
| ohlcv.market_daily | 전체 | 20260710 | n=2 | 종목 열 없음 | 3 | 해당 없음 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260710 | n=10 | n=10 | 16 | 16 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260713 | n=10 | n=10 | 16 | 16 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260714 | n=10 | n=10 | 16 | 16 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260715 | n=10 | n=10 | 14.5 | 14.5 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260810 | n=6 | n=6 | 9 | 9 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260901 | n=4 | n=4 | 6 | 6 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260902 | n=4 | n=4 | 6 | 6 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260903 | n=3 | n=3 | 6 | 6 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260904 | n=3 | n=3 | 6 | 6 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260907 | n=3 | n=3 | 6 | 6 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260908 | n=3 | n=3 | 5.5 | 5.5 | 알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요) |
| ohlcv.short_flows | 확인 못 함 | 20260909 | n=3 | n=3 | 5 | 5 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260910 | n=3 | n=3 | 5 | 5 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260911 | n=3 | n=3 | 5 | 5 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260914 | n=3 | n=3 | 5 | 5 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260915 | n=3 | n=3 | 4.5 | 4.5 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260921 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260922 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260923 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260928 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260929 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20260930 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20261001 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20261002 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20261006 | n=1 | n=1 | 3 | 3 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20261007 | n=0 | n=0 | 3 | 3 | 확인 필요 |
| ohlcv.short_flows | 확인 못 함 | 20261008 | n=0 | n=0 | 2 | 2 | 확인 필요 |
| ohlcv.universe_events | kosdaq | 20260715 | n=2 | n=2 | 4 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260716 | n=0 | n=0 | 4 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260803 | n=3 | n=3 | 5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260806 | n=3 | n=3 | 5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260811 | n=3 | n=3 | 5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260813 | n=0 | n=0 | 5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260819 | n=1 | n=1 | 5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260820 | n=0 | n=0 | 5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260824 | n=2 | n=2 | 5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260907 | n=3 | n=3 | 5.5 | 5.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260908 | n=2 | n=2 | 5 | 5 | 알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요); 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260910 | n=0 | n=0 | 5.5 | 5.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260916 | n=2 | n=2 | 5.5 | 5.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260922 | n=1 | n=1 | 5.5 | 5.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kosdaq | 20260930 | n=3 | n=3 | 5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260710 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260713 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260716 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260722 | n=1 | n=1 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260723 | n=0 | n=0 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260724 | n=1 | n=1 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260729 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260803 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260812 | n=0 | n=0 | 2 | 2 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260813 | n=0 | n=0 | 2 | 2 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260818 | n=0 | n=0 | 2 | 2 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260819 | n=0 | n=0 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260820 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260824 | n=1 | n=1 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260826 | n=1 | n=1 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260827 | n=1 | n=1 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260903 | n=2 | n=2 | 3 | 3 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260904 | n=0 | n=0 | 2.5 | 2.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260910 | n=0 | n=0 | 2 | 2 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260915 | n=1 | n=1 | 2.5 | 2.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260916 | n=0 | n=0 | 2.5 | 2.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260921 | n=2 | n=2 | 3 | 3 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260922 | n=2 | n=2 | 3 | 3 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260929 | n=2 | n=2 | 4 | 4 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20260930 | n=0 | n=0 | 3.5 | 3.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20261001 | n=2 | n=2 | 3 | 3 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | kospi | 20261007 | n=1 | n=1 | 2.5 | 2.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260716 | n=0 | n=0 | 5 | 5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260723 | n=3 | n=3 | 6 | 6 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260803 | n=3 | n=3 | 5.5 | 5.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260813 | n=0 | n=0 | 6.5 | 6.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260819 | n=1 | n=1 | 7 | 7 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260820 | n=0 | n=0 | 6.5 | 6.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260824 | n=3 | n=3 | 6.5 | 6.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260904 | n=5 | n=5 | 8 | 8 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260910 | n=0 | n=0 | 7.5 | 7.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260916 | n=2 | n=2 | 8 | 8 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260922 | n=3 | n=3 | 8.5 | 8.5 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.universe_events | 전체 | 20260930 | n=3 | n=3 | 9 | 9 | 확인 필요; 비일별·사건/주기 자료 |
| ohlcv.valuation_daily | kosdaq | 20260813 | n=0 | n=0 | 1802 | 1802 | 확인 필요 |
| ohlcv.valuation_daily | kosdaq | 20260820 | n=0 | n=0 | 1801 | 1801 | 확인 필요 |
| ohlcv.valuation_daily | kosdaq | 20260910 | n=0 | n=0 | 1802 | 1802 | 확인 필요 |
| ohlcv.valuation_daily | kospi | 20260813 | n=0 | n=0 | 915 | 915 | 확인 필요 |
| ohlcv.valuation_daily | kospi | 20260820 | n=0 | n=0 | 915 | 915 | 확인 필요 |
| ohlcv.valuation_daily | kospi | 20260910 | n=0 | n=0 | 915 | 915 | 확인 필요 |
| ohlcv.valuation_daily | 전체 | 20260813 | n=0 | n=0 | 2717 | 2717 | 확인 필요 |
| ohlcv.valuation_daily | 전체 | 20260820 | n=0 | n=0 | 2716 | 2716 | 확인 필요 |
| ohlcv.valuation_daily | 전체 | 20260910 | n=0 | n=0 | 2717 | 2717 | 확인 필요 |
| earnings.earnings_q | kosdaq | 20260824 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | kosdaq | 20260901 | n=1 | n=1 | 2 | 2 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | kosdaq | 20260902 | n=0 | n=0 | 2 | 2 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | kosdaq | 20260903 | n=0 | n=0 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | kosdaq | 20260904 | n=0 | n=0 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | kosdaq | 20260907 | n=0 | n=0 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | kosdaq | 20260908 | n=0 | n=0 | 1 | 1 | 알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요); 비일별·사건/주기 자료 |
| earnings.earnings_q | kosdaq | 20260909 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | kosdaq | 20260910 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | kosdaq | 20260911 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | kosdaq | 20260914 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | kosdaq | 20260915 | n=0 | n=0 | 0.5 | 0.5 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260824 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260901 | n=1 | n=1 | 2 | 2 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260902 | n=0 | n=0 | 2 | 2 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260903 | n=0 | n=0 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260904 | n=0 | n=0 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260907 | n=0 | n=0 | 1.5 | 1.5 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260908 | n=0 | n=0 | 1 | 1 | 알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요); 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260909 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260910 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260911 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260914 | n=0 | n=0 | 1 | 1 | 확인 필요; 비일별·사건/주기 자료 |
| earnings.earnings_q | 전체 | 20260915 | n=0 | n=0 | 0.5 | 0.5 | 확인 필요; 비일별·사건/주기 자료 |

## 4. 최근 n=10거래일 값이 안 바뀐 열·전부 0/NULL

10거래일 모두 등장한 종목(모델 표는 종목×model_id)만 불변 비율 분모에 넣었다. 같은 날짜 재실행 값이 서로 다르면 불변이 아니다. NULL만 있는 열, 비NULL 값이 모두 0인 열은 별도 표시한다(혼합 NULL 수도 유의). 최근10일 전체가 아니어도 기준일만 전부 NULL/0인 열을 추가했다. ticker가 없는 표는 series/market별 반복 관측도 확인했다. 이 조건만으로 복사를 확정하지 않는다. 주식수·보고기간·재무 스냅샷·불변 분류·가중 0 관측/비활성 필드는 정상일 수 있다. 점수·수익·순위 상관 등 성과 통계는 계산하지 않았으며 실제 값 대신 불변/결손 여부만 집계했다.

| 표 | 검사 표본 |
|---|---|
| history.large_final | n=5000행 / 관측일 n=10/10 / ticker n=525 |
| history.large_universe | n=5000행 / 관측일 n=10/10 / ticker n=525 |
| history.lead_picks | n=40행 / 관측일 n=1/10 / ticker n=35 |
| history.lead_universe | n=1069행 / 관측일 n=1/10 / ticker n=1069 |
| history.lowvol_scores | n=9665행 / 관측일 n=10/10 / ticker n=885 |
| history.runs | n=20행 / 관측일 n=10/10 / market n=2 |
| history.stage1_oversold | n=23541행 / 관측일 n=10/10 / ticker n=2377 |
| history.stage2_filtered | n=11961행 / 관측일 n=10/10 / ticker n=1843 |
| history.stage3_final | n=6496행 / 관측일 n=10/10 / ticker n=1225 |
| history.v3_scores | n=6496행 / 관측일 n=10/10 / ticker n=1225 |
| history.wu_scores | n=52325행 / 관측일 n=10/10 / ticker n=1160 |
| ohlcv.consensus_daily | n=7551행 / 관측일 n=3/10 / ticker n=2537 |
| ohlcv.daily_flows | n=26192행 / 관측일 n=10/10 / ticker n=2631 |
| ohlcv.daily_ohlcv | n=26291행 / 관측일 n=10/10 / ticker n=2631 |
| ohlcv.daily_ohlcv_extra | n=1356행 / 관측일 n=10/10 / ticker n=136 |
| ohlcv.dart_events | n=251행 / 관측일 n=10/10 / ticker n=151 |
| ohlcv.market_daily | n=30행 / 관측일 n=10/10 / series n=3 |
| ohlcv.ohlcv_skips | 관측 n=0; 10일 값 비교 불가 |
| ohlcv.short_flows | n=25299행 / 관측일 n=10/10 / ticker n=2541 |
| ohlcv.universe_events | n=72행 / 관측일 n=10/10 / ticker n=56 |
| ohlcv.valuation_daily | n=27167행 / 관측일 n=10/10 / ticker n=2719 |
| earnings.earnings_q | n=1행 / 관측일 n=1/10 / ticker n=1 |
| earnings.earnings_raw | n=465행 / 관측일 n=2/10 / ticker n=155 |

| 표 | 갈래 | 열 | 검출 | 행 수 | 불변/완전10일 종목 | 불변 비율 | 분류 |
|---|---|---|---|---|---|---|---|
| history.large_final | kosdaq | stocks | 10일 불변≥90% | n=1814행 | n=160/170 | 94.1% | 우선 확인 |
| history.large_final | kospi | stocks | 10일 불변≥90% | n=3186행 | n=306/312 | 98.1% | 우선 확인 |
| history.large_final | 전체 | stocks | 10일 불변≥90% | n=5000행 | n=466/482 | 96.7% | 우선 확인 |
| history.large_universe | kosdaq | stocks | 10일 불변≥90% | n=1814행 | n=160/170 | 94.1% | 우선 확인 |
| history.large_universe | kospi | stocks | 10일 불변≥90% | n=3186행 | n=306/312 | 98.1% | 우선 확인 |
| history.large_universe | 전체 | stocks | 10일 불변≥90% | n=5000행 | n=466/482 | 96.7% | 우선 확인 |
| history.stage1_oversold | kosdaq | foreign_proxy_coverage | 10일 불변≥90% | n=16172행 | n=1600/1600 | 100.0% | 우선 확인 |
| history.stage1_oversold | kosdaq | foreign_proxy_success | 10일 불변≥90% | n=16172행 | n=1600/1600 | 100.0% | 우선 확인 |
| history.stage1_oversold | kosdaq | foreign_proxy_total | 10일 불변≥90% | n=16172행 | n=1600/1600 | 100.0% | 우선 확인 |
| history.stage1_oversold | kospi | foreign_proxy_coverage | 10일 불변≥90% | n=7369행 | n=730/730 | 100.0% | 우선 확인 |
| history.stage1_oversold | kospi | foreign_proxy_success | 10일 불변≥90% | n=7369행 | n=730/730 | 100.0% | 우선 확인 |
| history.stage1_oversold | kospi | foreign_proxy_total | 10일 불변≥90% | n=7369행 | n=730/730 | 100.0% | 우선 확인 |
| history.stage1_oversold | 전체 | foreign_proxy_coverage | 10일 불변≥90% | n=23541행 | n=2330/2330 | 100.0% | 우선 확인 |
| history.stage1_oversold | 전체 | foreign_proxy_success | 10일 불변≥90% | n=23541행 | n=2330/2330 | 100.0% | 우선 확인 |
| history.stage1_oversold | 전체 | foreign_proxy_total | 10일 불변≥90% | n=23541행 | n=2330/2330 | 100.0% | 우선 확인 |
| history.stage2_filtered | kosdaq | foreign_proxy_coverage | 10일 불변≥90% | n=7286행 | n=239/239 | 100.0% | 우선 확인 |
| history.stage2_filtered | kosdaq | foreign_proxy_success | 10일 불변≥90% | n=7286행 | n=239/239 | 100.0% | 우선 확인 |
| history.stage2_filtered | kosdaq | foreign_proxy_total | 10일 불변≥90% | n=7286행 | n=239/239 | 100.0% | 우선 확인 |
| history.stage2_filtered | kospi | foreign_proxy_coverage | 10일 불변≥90% | n=4675행 | n=215/215 | 100.0% | 우선 확인 |
| history.stage2_filtered | kospi | foreign_proxy_success | 10일 불변≥90% | n=4675행 | n=215/215 | 100.0% | 우선 확인 |
| history.stage2_filtered | kospi | foreign_proxy_total | 10일 불변≥90% | n=4675행 | n=215/215 | 100.0% | 우선 확인 |
| history.stage2_filtered | 전체 | foreign_proxy_coverage | 10일 불변≥90% | n=11961행 | n=454/454 | 100.0% | 우선 확인 |
| history.stage2_filtered | 전체 | foreign_proxy_success | 10일 불변≥90% | n=11961행 | n=454/454 | 100.0% | 우선 확인 |
| history.stage2_filtered | 전체 | foreign_proxy_total | 10일 불변≥90% | n=11961행 | n=454/454 | 100.0% | 우선 확인 |
| history.stage3_final | kosdaq | foreign_proxy_coverage | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 우선 확인 |
| history.stage3_final | kosdaq | foreign_proxy_success | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 우선 확인 |
| history.stage3_final | kosdaq | foreign_proxy_total | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 우선 확인 |
| history.stage3_final | kosdaq | supply_fetched | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 우선 확인 |
| history.stage3_final | kospi | foreign_proxy_coverage | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 우선 확인 |
| history.stage3_final | kospi | foreign_proxy_success | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 우선 확인 |
| history.stage3_final | kospi | foreign_proxy_total | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 우선 확인 |
| history.stage3_final | kospi | supply_fetched | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 우선 확인 |
| history.stage3_final | 전체 | foreign_proxy_coverage | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 우선 확인 |
| history.stage3_final | 전체 | foreign_proxy_success | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 우선 확인 |
| history.stage3_final | 전체 | foreign_proxy_total | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 우선 확인 |
| history.stage3_final | 전체 | supply_fetched | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 우선 확인 |
| ohlcv.daily_flows | kosdaq | bank_net_qty | 10일 불변≥90% | n=17059행 | n=1574/1628 | 96.7% | 우선 확인 |
| ohlcv.daily_flows | kosdaq | bank_net_val | 10일 불변≥90% | n=17059행 | n=1576/1628 | 96.8% | 우선 확인 |
| ohlcv.daily_flows | 전체 | bank_net_val | 10일 불변≥90% | n=26192행 | n=2293/2518 | 91.1% | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | bank_net_qty | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | bank_net_val | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | inst_net_val | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | insu_net_qty | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | insu_net_val | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | pension_net_qty | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | pension_net_val | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | prveq_net_qty | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | prveq_net_val | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | secfirm_net_val | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | trust_net_qty | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_flows | 확인 못 함 | trust_net_val | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.daily_ohlcv | KOSDAQ | shares | 10일 불변≥90% | n=17141행 | n=1670/1711 | 97.6% | 우선 확인 |
| ohlcv.daily_ohlcv | KOSPI | shares | 10일 불변≥90% | n=9150행 | n=906/915 | 99.0% | 우선 확인 |
| ohlcv.daily_ohlcv | 전체 | shares | 10일 불변≥90% | n=26291행 | n=2576/2626 | 98.1% | 우선 확인 |
| ohlcv.daily_ohlcv_extra | KOSDAQ | shares | 10일 불변≥90% | n=1086행 | n=106/107 | 99.1% | 우선 확인 |
| ohlcv.daily_ohlcv_extra | KOSPI | shares | 10일 불변≥90% | n=270행 | n=27/27 | 100.0% | 우선 확인 |
| ohlcv.daily_ohlcv_extra | 전체 | shares | 10일 불변≥90% | n=1356행 | n=133/134 | 99.3% | 우선 확인 |
| ohlcv.short_flows | kosdaq | credit_bal_amt | 기준일 전부 NULL | n=1626행 | 당일 검사 | 해당 없음 | 우선 확인 |
| ohlcv.short_flows | kosdaq | credit_bal_qty | 기준일 전부 NULL | n=1626행 | 당일 검사 | 해당 없음 | 우선 확인 |
| ohlcv.short_flows | kosdaq | credit_bal_rate | 기준일 전부 NULL | n=1626행 | 당일 검사 | 해당 없음 | 우선 확인 |
| ohlcv.short_flows | kospi | credit_bal_amt | 기준일 전부 NULL | n=890행 | 당일 검사 | 해당 없음 | 우선 확인 |
| ohlcv.short_flows | kospi | credit_bal_qty | 기준일 전부 NULL | n=890행 | 당일 검사 | 해당 없음 | 우선 확인 |
| ohlcv.short_flows | kospi | credit_bal_rate | 기준일 전부 NULL | n=890행 | 당일 검사 | 해당 없음 | 우선 확인 |
| ohlcv.short_flows | 전체 | credit_bal_amt | 기준일 전부 NULL | n=2516행 | 당일 검사 | 해당 없음 | 우선 확인 |
| ohlcv.short_flows | 전체 | credit_bal_qty | 기준일 전부 NULL | n=2516행 | 당일 검사 | 해당 없음 | 우선 확인 |
| ohlcv.short_flows | 전체 | credit_bal_rate | 기준일 전부 NULL | n=2516행 | 당일 검사 | 해당 없음 | 우선 확인 |
| ohlcv.short_flows | 확인 못 함 | credit_bal_amt | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.short_flows | 확인 못 함 | credit_bal_qty | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.short_flows | 확인 못 함 | credit_bal_rate | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.short_flows | 확인 못 함 | short_qty | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.short_flows | 확인 못 함 | short_val | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| ohlcv.short_flows | 확인 못 함 | short_vol_ratio | 비NULL 값 전부 0 | n=8행 | n=0/0 | 완전10일 표본 없음 | 우선 확인 |
| earnings.earnings_raw | kosdaq | fr | 전부 NULL | n=360행 | n=0/0 | 완전10일 표본 없음 | 정상 상수/선택 필드 가능 |
| earnings.earnings_raw | kospi | fr | 전부 NULL | n=105행 | n=0/0 | 완전10일 표본 없음 | 정상 상수/선택 필드 가능 |
| earnings.earnings_raw | 전체 | fr | 전부 NULL | n=465행 | n=0/0 | 완전10일 표본 없음 | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | annual_yoy | 10일 불변≥90% | n=1814행 | n=167/170 | 98.2% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | bps | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | buyback_cancel_flag | 10일 불변≥90% | n=1814행 | n=168/170 | 98.8% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | eps | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | is_cyclical | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | is_financial | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | is_holding | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | is_pref | 비NULL 값 전부 0 | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | is_reit | 비NULL 값 전부 0 | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | is_spac | 비NULL 값 전부 0 | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | ocf_to_op_ratio | 10일 불변≥90% | n=1814행 | n=168/170 | 98.8% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | quality_gate | 10일 불변≥90% | n=1814행 | n=168/170 | 98.8% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | quarterly_yoy | 10일 불변≥90% | n=1814행 | n=159/170 | 93.5% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | rim_fair_pbr | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | rim_quadrant | 10일 불변≥90% | n=1814행 | n=169/170 | 99.4% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | roe_value | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | sector | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kosdaq | sector_raw | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | annual_yoy | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | bps | 10일 불변≥90% | n=3186행 | n=311/312 | 99.7% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | buyback_cancel_flag | 10일 불변≥90% | n=3186행 | n=306/312 | 98.1% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | eps | 10일 불변≥90% | n=3186행 | n=311/312 | 99.7% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | is_cyclical | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | is_financial | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | is_holding | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | is_pref | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | is_reit | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | is_spac | 비NULL 값 전부 0 | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | ocf_to_op_ratio | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | quality_gate | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | quarterly_yoy | 10일 불변≥90% | n=3186행 | n=282/312 | 90.4% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | rim_fair_pbr | 10일 불변≥90% | n=3186행 | n=311/312 | 99.7% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | rim_quadrant | 10일 불변≥90% | n=3186행 | n=309/312 | 99.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | roe_value | 10일 불변≥90% | n=3186행 | n=311/312 | 99.7% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | sector | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | kospi | sector_raw | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | annual_yoy | 10일 불변≥90% | n=5000행 | n=479/482 | 99.4% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | bps | 10일 불변≥90% | n=5000행 | n=481/482 | 99.8% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | buyback_cancel_flag | 10일 불변≥90% | n=5000행 | n=474/482 | 98.3% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | eps | 10일 불변≥90% | n=5000행 | n=481/482 | 99.8% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | is_cyclical | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | is_financial | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | is_holding | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | is_pref | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | is_reit | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | is_spac | 비NULL 값 전부 0 | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | ocf_to_op_ratio | 10일 불변≥90% | n=5000행 | n=480/482 | 99.6% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | quality_gate | 10일 불변≥90% | n=5000행 | n=480/482 | 99.6% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | quarterly_yoy | 10일 불변≥90% | n=5000행 | n=441/482 | 91.5% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | rim_fair_pbr | 10일 불변≥90% | n=5000행 | n=481/482 | 99.8% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | rim_quadrant | 10일 불변≥90% | n=5000행 | n=478/482 | 99.2% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | roe_value | 10일 불변≥90% | n=5000행 | n=481/482 | 99.8% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | sector | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_final | 전체 | sector_raw | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kosdaq | is_financial | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kosdaq | is_holding | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kosdaq | is_pref | 비NULL 값 전부 0 | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kosdaq | is_reit | 비NULL 값 전부 0 | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kosdaq | is_spac | 비NULL 값 전부 0 | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kosdaq | sector | 10일 불변≥90% | n=1814행 | n=170/170 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kospi | is_financial | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kospi | is_holding | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kospi | is_pref | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kospi | is_reit | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kospi | is_spac | 비NULL 값 전부 0 | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | kospi | sector | 10일 불변≥90% | n=3186행 | n=312/312 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | 전체 | is_financial | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | 전체 | is_holding | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | 전체 | is_pref | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | 전체 | is_reit | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | 전체 | is_spac | 비NULL 값 전부 0 | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.large_universe | 전체 | sector | 10일 불변≥90% | n=5000행 | n=482/482 | 100.0% | 정상 상수/선택 필드 가능 |
| history.lead_picks | model_id=ld_ctl_amt; market=KOSDAQ | cap_applied | 비NULL 값 전부 0 | n=3행 | n=0/0 | 완전10일 표본 없음 | 정상 상수/선택 필드 가능 |
| history.lead_picks | model_id=ld_ctl_amt; market=KOSPI | cap_applied | 비NULL 값 전부 0 | n=17행 | n=0/0 | 완전10일 표본 없음 | 정상 상수/선택 필드 가능 |
| history.runs | kosdaq | market_regime | 10일 불변≥90% | n=10행 | n=1/1 | 100.0% | 정상 상수/선택 필드 가능 |
| history.runs | kosdaq | regime_flow_score | 10일 불변≥90% | n=10행 | n=1/1 | 100.0% | 정상 상수/선택 필드 가능 |
| history.runs | kosdaq | regime_fx_score | 비NULL 값 전부 0 | n=10행 | n=1/1 | 100.0% | 정상 상수/선택 필드 가능 |
| history.runs | kosdaq | regime_kospi_score | 10일 불변≥90% | n=10행 | n=1/1 | 100.0% | 정상 상수/선택 필드 가능 |
| history.runs | kosdaq | regime_score | 10일 불변≥90% | n=10행 | n=1/1 | 100.0% | 정상 상수/선택 필드 가능 |
| history.runs | kosdaq | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=1행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.runs | kospi | regime_flow_score | 10일 불변≥90% | n=10행 | n=1/1 | 100.0% | 정상 상수/선택 필드 가능 |
| history.runs | kospi | regime_fx_score | 비NULL 값 전부 0 | n=10행 | n=1/1 | 100.0% | 정상 상수/선택 필드 가능 |
| history.runs | kospi | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=1행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.runs | 전체 | regime_flow_score | 10일 불변≥90% | n=20행 | n=2/2 | 100.0% | 정상 상수/선택 필드 가능 |
| history.runs | 전체 | regime_fx_score | 비NULL 값 전부 0 | n=20행 | n=2/2 | 100.0% | 정상 상수/선택 필드 가능 |
| history.runs | 전체 | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=2행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage1_oversold | kosdaq | 52w_low | 10일 불변≥90% | n=16172행 | n=1454/1600 | 90.9% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | kosdaq | falling_knife | 10일 불변≥90% | n=16172행 | n=1516/1600 | 94.8% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | kosdaq | market_regime | 10일 불변≥90% | n=16172행 | n=1600/1600 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | kosdaq | regime_flow_score | 10일 불변≥90% | n=16172행 | n=1600/1600 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | kosdaq | regime_fx_score | 비NULL 값 전부 0 | n=16172행 | n=1600/1600 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | kosdaq | regime_kospi_score | 10일 불변≥90% | n=16172행 | n=1600/1600 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | kosdaq | regime_score | 10일 불변≥90% | n=16172행 | n=1600/1600 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | kosdaq | sector | 전부 NULL | n=16172행 | n=1600/1600 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | kosdaq | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=1622행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage1_oversold | kospi | regime_flow_score | 10일 불변≥90% | n=7369행 | n=730/730 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | kospi | regime_fx_score | 비NULL 값 전부 0 | n=7369행 | n=730/730 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | kospi | sector | 전부 NULL | n=7369행 | n=730/730 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | kospi | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=736행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage1_oversold | 전체 | falling_knife | 10일 불변≥90% | n=23541행 | n=2137/2330 | 91.7% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | 전체 | regime_flow_score | 10일 불변≥90% | n=23541행 | n=2330/2330 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | 전체 | regime_fx_score | 비NULL 값 전부 0 | n=23541행 | n=2330/2330 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | 전체 | sector | 전부 NULL | n=23541행 | n=2330/2330 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage1_oversold | 전체 | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=2358행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage2_filtered | kosdaq | corp_code | 10일 불변≥90% | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | danger_count | 비NULL 값 전부 0 | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | danger_details | 전부 NULL | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | danger_rcept_nos | 전부 NULL | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | danger_urls | 전부 NULL | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | dart_status | 10일 불변≥90% | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | fp_avoided_count | 10일 불변≥90% | n=7286행 | n=238/239 | 99.6% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | fp_avoided_count | 기준일 비NULL 값 전부 0 | n=683행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage2_filtered | kosdaq | fp_avoided_details | 10일 불변≥90% | n=7286행 | n=238/239 | 99.6% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | fp_avoided_details | 기준일 전부 NULL | n=683행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage2_filtered | kosdaq | fp_avoided_urls | 10일 불변≥90% | n=7286행 | n=238/239 | 99.6% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | fp_avoided_urls | 기준일 전부 NULL | n=683행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage2_filtered | kosdaq | market_regime | 10일 불변≥90% | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | regime_flow_score | 10일 불변≥90% | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | regime_fx_score | 비NULL 값 전부 0 | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | regime_kospi_score | 10일 불변≥90% | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | regime_score | 10일 불변≥90% | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | risk_level | 10일 불변≥90% | n=7286행 | n=234/239 | 97.9% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | sector | 전부 NULL | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | soft_downgraded_count | 비NULL 값 전부 0 | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | soft_downgraded_details | 전부 NULL | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | soft_downgraded_urls | 전부 NULL | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | stock_code | 10일 불변≥90% | n=7286행 | n=239/239 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=683행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage2_filtered | kosdaq | warning_count | 10일 불변≥90% | n=7286행 | n=218/239 | 91.2% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | warning_details | 10일 불변≥90% | n=7286행 | n=224/239 | 93.7% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | warning_rcept_nos | 10일 불변≥90% | n=7286행 | n=224/239 | 93.7% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kosdaq | warning_urls | 10일 불변≥90% | n=7286행 | n=224/239 | 93.7% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | corp_code | 10일 불변≥90% | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | danger_count | 비NULL 값 전부 0 | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | danger_details | 전부 NULL | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | danger_rcept_nos | 전부 NULL | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | danger_urls | 전부 NULL | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | dart_status | 10일 불변≥90% | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | fp_avoided_count | 10일 불변≥90% | n=4675행 | n=213/215 | 99.1% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | fp_avoided_details | 10일 불변≥90% | n=4675행 | n=213/215 | 99.1% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | fp_avoided_urls | 10일 불변≥90% | n=4675행 | n=213/215 | 99.1% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | regime_flow_score | 10일 불변≥90% | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | regime_fx_score | 비NULL 값 전부 0 | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | risk_level | 10일 불변≥90% | n=4675행 | n=211/215 | 98.1% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | sector | 전부 NULL | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | soft_downgraded_count | 비NULL 값 전부 0 | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | soft_downgraded_details | 전부 NULL | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | soft_downgraded_urls | 전부 NULL | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | stock_code | 10일 불변≥90% | n=4675행 | n=215/215 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=439행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage2_filtered | kospi | warning_count | 10일 불변≥90% | n=4675행 | n=201/215 | 93.5% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | warning_details | 10일 불변≥90% | n=4675행 | n=203/215 | 94.4% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | warning_rcept_nos | 10일 불변≥90% | n=4675행 | n=203/215 | 94.4% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | kospi | warning_urls | 10일 불변≥90% | n=4675행 | n=203/215 | 94.4% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | corp_code | 10일 불변≥90% | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | danger_count | 비NULL 값 전부 0 | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | danger_details | 전부 NULL | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | danger_rcept_nos | 전부 NULL | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | danger_urls | 전부 NULL | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | dart_status | 10일 불변≥90% | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | fp_avoided_count | 10일 불변≥90% | n=11961행 | n=451/454 | 99.3% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | fp_avoided_details | 10일 불변≥90% | n=11961행 | n=451/454 | 99.3% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | fp_avoided_urls | 10일 불변≥90% | n=11961행 | n=451/454 | 99.3% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | regime_flow_score | 10일 불변≥90% | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | regime_fx_score | 비NULL 값 전부 0 | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | risk_level | 10일 불변≥90% | n=11961행 | n=445/454 | 98.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | sector | 전부 NULL | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | soft_downgraded_count | 비NULL 값 전부 0 | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | soft_downgraded_details | 전부 NULL | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | soft_downgraded_urls | 전부 NULL | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | stock_code | 10일 불변≥90% | n=11961행 | n=454/454 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=1122행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage2_filtered | 전체 | warning_count | 10일 불변≥90% | n=11961행 | n=419/454 | 92.3% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | warning_details | 10일 불변≥90% | n=11961행 | n=427/454 | 94.1% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | warning_rcept_nos | 10일 불변≥90% | n=11961행 | n=427/454 | 94.1% | 정상 상수/선택 필드 가능 |
| history.stage2_filtered | 전체 | warning_urls | 10일 불변≥90% | n=11961행 | n=427/454 | 94.1% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | annual_fs_div | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | annual_latest_억 | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | annual_op_account_id | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | annual_op_account_nm | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | annual_prev_억 | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | annual_year | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | annual_yoy_% | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | buyback_cancel_flag | 10일 불변≥90% | n=3480행 | n=83/85 | 97.6% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | catalyst_score | 10일 불변≥90% | n=3480행 | n=83/85 | 97.6% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | corp_code | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | danger_count | 비NULL 값 전부 0 | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | danger_details | 전부 NULL | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | danger_rcept_nos | 전부 NULL | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | danger_urls | 전부 NULL | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | dart_annual_message | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | dart_annual_status | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | dart_ocf_message | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | dart_ocf_status | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | dart_q_message | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | dart_q_status | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | dart_status | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | earnings_pattern | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | fp_avoided_count | 10일 불변≥90% | n=3480행 | n=84/85 | 98.8% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | fp_avoided_count | 기준일 비NULL 값 전부 0 | n=339행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage3_final | kosdaq | fp_avoided_details | 10일 불변≥90% | n=3480행 | n=84/85 | 98.8% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | fp_avoided_details | 기준일 전부 NULL | n=339행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage3_final | kosdaq | fp_avoided_urls | 10일 불변≥90% | n=3480행 | n=84/85 | 98.8% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | fp_avoided_urls | 기준일 전부 NULL | n=339행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage3_final | kosdaq | fundamental_score | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | insider_score | 비NULL 값 전부 0 | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | insider_source | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | market_regime | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | ocf_account_id | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | ocf_account_nm | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | ocf_latest_억 | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | ocf_pattern | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | ocf_prev_억 | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | ocf_score | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | ocf_threshold_group | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | ocf_to_op_ratio | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | os_is_new20 | 10일 불변≥90% | n=3480행 | n=82/85 | 96.5% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | q_basis | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | q_fs_div | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | q_latest_key | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | q_latest_억 | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | q_op_account_id | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | q_op_account_nm | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | q_period | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | q_prev_key | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | q_prev_억 | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | q_source_api | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | quarterly_yoy_% | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | regime_flow_score | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | regime_fx_score | 비NULL 값 전부 0 | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | regime_kospi_score | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | regime_score | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | risk_level | 10일 불변≥90% | n=3480행 | n=84/85 | 98.8% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | roe_gate | 10일 불변≥90% | n=3480행 | n=84/85 | 98.8% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | roe_value | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | sector | 전부 NULL | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | smartmoney_trigger | 10일 불변≥90% | n=3480행 | n=79/85 | 92.9% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | soft_downgraded_count | 비NULL 값 전부 0 | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | soft_downgraded_details | 전부 NULL | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | soft_downgraded_urls | 전부 NULL | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | stock_code | 10일 불변≥90% | n=3480행 | n=85/85 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=339행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage3_final | kosdaq | warning_count | 10일 불변≥90% | n=3480행 | n=80/85 | 94.1% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | warning_details | 10일 불변≥90% | n=3480행 | n=82/85 | 96.5% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | warning_rcept_nos | 10일 불변≥90% | n=3480행 | n=82/85 | 96.5% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kosdaq | warning_urls | 10일 불변≥90% | n=3480행 | n=82/85 | 96.5% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | annual_fs_div | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | annual_latest_억 | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | annual_op_account_id | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | annual_op_account_nm | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | annual_prev_억 | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | annual_year | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | annual_yoy_% | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | buyback_cancel_flag | 10일 불변≥90% | n=3016행 | n=86/88 | 97.7% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | catalyst_score | 10일 불변≥90% | n=3016행 | n=86/88 | 97.7% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | corp_code | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | danger_count | 비NULL 값 전부 0 | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | danger_details | 전부 NULL | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | danger_rcept_nos | 전부 NULL | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | danger_urls | 전부 NULL | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | dart_annual_message | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | dart_annual_status | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | dart_ocf_message | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | dart_ocf_status | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | dart_q_message | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | dart_q_status | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | dart_status | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | earnings_pattern | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | fp_avoided_count | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | fp_avoided_details | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | fp_avoided_urls | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | fundamental_score | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | insider_score | 비NULL 값 전부 0 | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | insider_source | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | ocf_account_id | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | ocf_account_nm | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | ocf_latest_억 | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | ocf_pattern | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | ocf_prev_억 | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | ocf_score | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | ocf_threshold_group | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | ocf_to_op_ratio | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | os_is_new20 | 10일 불변≥90% | n=3016행 | n=87/88 | 98.9% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | q_basis | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | q_fs_div | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | q_latest_key | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | q_latest_억 | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | q_op_account_id | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | q_op_account_nm | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | q_period | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | q_prev_key | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | q_prev_억 | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | q_source_api | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | quarterly_yoy_% | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | regime_flow_score | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | regime_fx_score | 비NULL 값 전부 0 | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | risk_level | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | roe_gate | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | roe_value | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | sector | 전부 NULL | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | smartmoney_trigger | 10일 불변≥90% | n=3016행 | n=87/88 | 98.9% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | soft_downgraded_count | 비NULL 값 전부 0 | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | soft_downgraded_details | 전부 NULL | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | soft_downgraded_urls | 전부 NULL | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | stock_code | 10일 불변≥90% | n=3016행 | n=88/88 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=312행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage3_final | kospi | warning_count | 10일 불변≥90% | n=3016행 | n=84/88 | 95.5% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | warning_details | 10일 불변≥90% | n=3016행 | n=86/88 | 97.7% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | warning_rcept_nos | 10일 불변≥90% | n=3016행 | n=86/88 | 97.7% | 정상 상수/선택 필드 가능 |
| history.stage3_final | kospi | warning_urls | 10일 불변≥90% | n=3016행 | n=86/88 | 97.7% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | annual_fs_div | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | annual_latest_억 | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | annual_op_account_id | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | annual_op_account_nm | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | annual_prev_억 | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | annual_year | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | annual_yoy_% | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | buyback_cancel_flag | 10일 불변≥90% | n=6496행 | n=169/173 | 97.7% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | catalyst_score | 10일 불변≥90% | n=6496행 | n=169/173 | 97.7% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | corp_code | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | danger_count | 비NULL 값 전부 0 | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | danger_details | 전부 NULL | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | danger_rcept_nos | 전부 NULL | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | danger_urls | 전부 NULL | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | dart_annual_message | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | dart_annual_status | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | dart_ocf_message | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | dart_ocf_status | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | dart_q_message | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | dart_q_status | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | dart_status | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | earnings_pattern | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | fp_avoided_count | 10일 불변≥90% | n=6496행 | n=172/173 | 99.4% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | fp_avoided_details | 10일 불변≥90% | n=6496행 | n=172/173 | 99.4% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | fp_avoided_urls | 10일 불변≥90% | n=6496행 | n=172/173 | 99.4% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | fundamental_score | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | insider_score | 비NULL 값 전부 0 | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | insider_source | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | ocf_account_id | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | ocf_account_nm | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | ocf_latest_억 | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | ocf_pattern | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | ocf_prev_억 | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | ocf_score | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | ocf_threshold_group | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | ocf_to_op_ratio | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | os_is_new20 | 10일 불변≥90% | n=6496행 | n=169/173 | 97.7% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | q_basis | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | q_fs_div | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | q_latest_key | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | q_latest_억 | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | q_op_account_id | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | q_op_account_nm | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | q_period | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | q_prev_key | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | q_prev_억 | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | q_source_api | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | quarterly_yoy_% | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | regime_flow_score | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | regime_fx_score | 비NULL 값 전부 0 | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | risk_level | 10일 불변≥90% | n=6496행 | n=172/173 | 99.4% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | roe_gate | 10일 불변≥90% | n=6496행 | n=172/173 | 99.4% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | roe_value | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | sector | 전부 NULL | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | smartmoney_trigger | 10일 불변≥90% | n=6496행 | n=166/173 | 96.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | soft_downgraded_count | 비NULL 값 전부 0 | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | soft_downgraded_details | 전부 NULL | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | soft_downgraded_urls | 전부 NULL | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | stock_code | 10일 불변≥90% | n=6496행 | n=173/173 | 100.0% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | usdkrw_vs_sma20_% | 기준일 전부 NULL | n=651행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| history.stage3_final | 전체 | warning_count | 10일 불변≥90% | n=6496행 | n=164/173 | 94.8% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | warning_details | 10일 불변≥90% | n=6496행 | n=168/173 | 97.1% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | warning_rcept_nos | 10일 불변≥90% | n=6496행 | n=168/173 | 97.1% | 정상 상수/선택 필드 가능 |
| history.stage3_final | 전체 | warning_urls | 10일 불변≥90% | n=6496행 | n=168/173 | 97.1% | 정상 상수/선택 필드 가능 |
| ohlcv.consensus_daily | 확인 못 함 | coverage | 비NULL 값 전부 0 | n=2행 | n=0/0 | 완전10일 표본 없음 | 정상 상수/선택 필드 가능 |
| ohlcv.consensus_daily | 확인 못 함 | opinion_label | 전부 NULL | n=2행 | n=0/0 | 완전10일 표본 없음 | 정상 상수/선택 필드 가능 |
| ohlcv.consensus_daily | 확인 못 함 | opinion_score | 전부 NULL | n=2행 | n=0/0 | 완전10일 표본 없음 | 정상 상수/선택 필드 가능 |
| ohlcv.consensus_daily | 확인 못 함 | target_price | 전부 NULL | n=2행 | n=0/0 | 완전10일 표본 없음 | 정상 상수/선택 필드 가능 |
| ohlcv.daily_ohlcv | KOSDAQ | is_suspended | 10일 불변≥90% | n=17141행 | n=1676/1711 | 98.0% | 정상 상수/선택 필드 가능 |
| ohlcv.daily_ohlcv | KOSPI | is_suspended | 10일 불변≥90% | n=9150행 | n=900/915 | 98.4% | 정상 상수/선택 필드 가능 |
| ohlcv.daily_ohlcv | 전체 | is_suspended | 10일 불변≥90% | n=26291행 | n=2576/2626 | 98.1% | 정상 상수/선택 필드 가능 |
| ohlcv.daily_ohlcv_extra | KOSDAQ | is_suspended | 10일 불변≥90% | n=1086행 | n=106/107 | 99.1% | 정상 상수/선택 필드 가능 |
| ohlcv.daily_ohlcv_extra | KOSDAQ | is_suspended | 기준일 비NULL 값 전부 0 | n=109행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| ohlcv.daily_ohlcv_extra | KOSPI | is_suspended | 비NULL 값 전부 0 | n=270행 | n=27/27 | 100.0% | 정상 상수/선택 필드 가능 |
| ohlcv.daily_ohlcv_extra | 전체 | is_suspended | 10일 불변≥90% | n=1356행 | n=133/134 | 99.3% | 정상 상수/선택 필드 가능 |
| ohlcv.daily_ohlcv_extra | 전체 | is_suspended | 기준일 비NULL 값 전부 0 | n=136행 | 당일 검사 | 해당 없음 | 선택 필드/상태 가능 |
| ohlcv.valuation_daily | kosdaq | bps | 10일 불변≥90% | n=18027행 | n=1786/1798 | 99.3% | 정상 상수/선택 필드 가능 |
| ohlcv.valuation_daily | kosdaq | eps | 10일 불변≥90% | n=18027행 | n=1795/1798 | 99.8% | 정상 상수/선택 필드 가능 |
| ohlcv.valuation_daily | kospi | bps | 10일 불변≥90% | n=9140행 | n=909/914 | 99.5% | 정상 상수/선택 필드 가능 |
| ohlcv.valuation_daily | kospi | eps | 10일 불변≥90% | n=9140행 | n=911/914 | 99.7% | 정상 상수/선택 필드 가능 |
| ohlcv.valuation_daily | 전체 | bps | 10일 불변≥90% | n=27167행 | n=2695/2712 | 99.4% | 정상 상수/선택 필드 가능 |
| ohlcv.valuation_daily | 전체 | eps | 10일 불변≥90% | n=27167행 | n=2706/2712 | 99.8% | 정상 상수/선택 필드 가능 |

## 5. 종목 단위 구멍과 반대 방향

최근 n=20거래일 합집합과 기준일 하루를 따로 비교했다. 시총은 기준일 DB 종가×주식수(본 표 우선·보충표 다음); 없는 종목은 확인 못 함이며 이름은 history.db에서만 가져왔다. 캐시 내용은 읽지 않았다. daily_flows/short_flows는 전 상장사가 아니라 대상 유니버스를 받으며, extra는 본 표 밖 종목의 보충표다. 따라서 단순 차집합 전체를 오류로 판정하지 않는다.

| 기간 | 비교 표 | 방향 | 종목 수 | 시장별 |
|---|---|---|---|---|
| 최근20일 합집합 | daily_flows | 본 표만 | n=0 | kospi n=0 / kosdaq n=0 / 확인 못 함 n=0 |
| 최근20일 합집합 | daily_flows | 비교 표만 | n=131 | kospi n=27 / kosdaq n=104 / 확인 못 함 n=0 |
| 최근20일 합집합 | short_flows | 본 표만 | n=77 | kospi n=19 / kosdaq n=58 / 확인 못 함 n=0 |
| 최근20일 합집합 | short_flows | 비교 표만 | n=0 | kospi n=0 / kosdaq n=0 / 확인 못 함 n=0 |
| 최근20일 합집합 | daily_ohlcv_extra | 본 표만 | n=2638 | kospi n=916 / kosdaq n=1719 / 확인 못 함 n=3 |
| 최근20일 합집합 | daily_ohlcv_extra | 비교 표만 | n=136 | kospi n=27 / kosdaq n=109 / 확인 못 함 n=0 |
| 최근20일 합집합 | valuation_daily | 본 표만 | n=47 | kospi n=27 / kosdaq n=20 / 확인 못 함 n=0 |
| 최근20일 합집합 | valuation_daily | 비교 표만 | n=135 | kospi n=26 / kosdaq n=109 / 확인 못 함 n=0 |
| 최근20일 합집합 | consensus_daily | 본 표만 | n=96 | kospi n=22 / kosdaq n=74 / 확인 못 함 n=0 |
| 최근20일 합집합 | consensus_daily | 비교 표만 | n=0 | kospi n=0 / kosdaq n=0 / 확인 못 함 n=0 |
| 20261008 | daily_flows | 본 표만 | n=111 | kospi n=25 / kosdaq n=86 / 확인 못 함 n=0 |
| 20261008 | daily_flows | 비교 표만 | n=0 | kospi n=0 / kosdaq n=0 / 확인 못 함 n=0 |
| 20261008 | short_flows | 본 표만 | n=113 | kospi n=25 / kosdaq n=88 / 확인 못 함 n=0 |
| 20261008 | short_flows | 비교 표만 | n=0 | kospi n=0 / kosdaq n=0 / 확인 못 함 n=0 |
| 20261008 | daily_ohlcv_extra | 본 표만 | n=2629 | kospi n=915 / kosdaq n=1714 / 확인 못 함 n=0 |
| 20261008 | daily_ohlcv_extra | 비교 표만 | n=136 | kospi n=27 / kosdaq n=109 / 확인 못 함 n=0 |
| 20261008 | valuation_daily | 본 표만 | n=47 | kospi n=27 / kosdaq n=20 / 확인 못 함 n=0 |
| 20261008 | valuation_daily | 비교 표만 | n=135 | kospi n=26 / kosdaq n=109 / 확인 못 함 n=0 |
| 20261008 | consensus_daily | 본 표만 | n=2629 | kospi n=915 / kosdaq n=1714 / 확인 못 함 n=0 |
| 20261008 | consensus_daily | 비교 표만 | n=0 | kospi n=0 / kosdaq n=0 / 확인 못 함 n=0 |

### 각 방향 시총 상위 최대 n=10종목

| 기간 | 표 | 방향 | 종목 | 이름 | 시장 | 시총 억원 |
|---|---|---|---|---|---|---|
| 최근20일 | daily_flows | 비교 표만 | 196170 | 알테오젠 | kosdaq | 167520.59 |
| 최근20일 | daily_flows | 비교 표만 | 086520 | 에코프로 | kosdaq | 123827.85 |
| 최근20일 | daily_flows | 비교 표만 | 247540 | 에코프로비엠 | kosdaq | 123755.50 |
| 최근20일 | daily_flows | 비교 표만 | 036930 | 주성엔지니어링 | kosdaq | 122477.75 |
| 최근20일 | daily_flows | 비교 표만 | 0126Z0 | 삼성에피스홀딩스 | kospi | 85348.86 |
| 최근20일 | daily_flows | 비교 표만 | 058470 | 리노공업 | kosdaq | 66914.00 |
| 최근20일 | daily_flows | 비교 표만 | 240810 | 원익IPS | kosdaq | 65870.60 |
| 최근20일 | daily_flows | 비교 표만 | 222800 | 심텍 | kosdaq | 65693.09 |
| 최근20일 | daily_flows | 비교 표만 | 403870 | HPSP | kosdaq | 52672.00 |
| 최근20일 | daily_flows | 비교 표만 | 064760 | 티씨케이 | kosdaq | 32755.69 |
| 최근20일 | short_flows | 본 표만 | 001570 | 금양 | kospi | 6332.75 |
| 최근20일 | short_flows | 본 표만 | 309710 | 아이티켐 | kosdaq | 2684.43 |
| 최근20일 | short_flows | 본 표만 | 182400 | 확인 못 함 | kosdaq | 2654.97 |
| 최근20일 | short_flows | 본 표만 | 121800 | 확인 못 함 | kosdaq | 2563.09 |
| 최근20일 | short_flows | 본 표만 | 377460 | 확인 못 함 | kosdaq | 2531.87 |
| 최근20일 | short_flows | 본 표만 | 348950 | 확인 못 함 | kospi | 2332.98 |
| 최근20일 | short_flows | 본 표만 | 001470 | 확인 못 함 | kospi | 2277.94 |
| 최근20일 | short_flows | 본 표만 | 380540 | 옵티코어 | kosdaq | 2066.58 |
| 최근20일 | short_flows | 본 표만 | 080720 | 확인 못 함 | kosdaq | 1924.42 |
| 최근20일 | short_flows | 본 표만 | 016790 | 확인 못 함 | kosdaq | 1873.41 |
| 최근20일 | daily_ohlcv_extra | 본 표만 | 005930 | 삼성전자 | kospi | 15375712.74 |
| 최근20일 | daily_ohlcv_extra | 본 표만 | 000660 | SK하이닉스 | kospi | 12316101.27 |
| 최근20일 | daily_ohlcv_extra | 본 표만 | 005935 | 삼성전자우 | kospi | 1560611.99 |
| 최근20일 | daily_ohlcv_extra | 본 표만 | 402340 | SK스퀘어 | kospi | 1397075.14 |
| 최근20일 | daily_ohlcv_extra | 본 표만 | 009150 | 삼성전기 | kospi | 1164474.72 |
| 최근20일 | daily_ohlcv_extra | 본 표만 | 373220 | LG에너지솔루션 | kospi | 943020.00 |
| 최근20일 | daily_ohlcv_extra | 본 표만 | 005380 | 현대차 | kospi | 660248.77 |
| 최근20일 | daily_ohlcv_extra | 본 표만 | 105560 | KB금융 | kospi | 579559.76 |
| 최근20일 | daily_ohlcv_extra | 본 표만 | 207940 | 삼성바이오로직스 | kospi | 564749.60 |
| 최근20일 | daily_ohlcv_extra | 본 표만 | 032830 | 삼성생명 | kospi | 540000.00 |
| 최근20일 | daily_ohlcv_extra | 비교 표만 | 196170 | 알테오젠 | kosdaq | 167520.59 |
| 최근20일 | daily_ohlcv_extra | 비교 표만 | 086520 | 에코프로 | kosdaq | 123827.85 |
| 최근20일 | daily_ohlcv_extra | 비교 표만 | 247540 | 에코프로비엠 | kosdaq | 123755.50 |
| 최근20일 | daily_ohlcv_extra | 비교 표만 | 036930 | 주성엔지니어링 | kosdaq | 122477.75 |
| 최근20일 | daily_ohlcv_extra | 비교 표만 | 0126Z0 | 삼성에피스홀딩스 | kospi | 85348.86 |
| 최근20일 | daily_ohlcv_extra | 비교 표만 | 058470 | 리노공업 | kosdaq | 66914.00 |
| 최근20일 | daily_ohlcv_extra | 비교 표만 | 240810 | 원익IPS | kosdaq | 65870.60 |
| 최근20일 | daily_ohlcv_extra | 비교 표만 | 222800 | 심텍 | kosdaq | 65693.09 |
| 최근20일 | daily_ohlcv_extra | 비교 표만 | 403870 | HPSP | kosdaq | 52672.00 |
| 최근20일 | daily_ohlcv_extra | 비교 표만 | 064760 | 티씨케이 | kosdaq | 32755.69 |
| 최근20일 | valuation_daily | 본 표만 | 088980 | 맥쿼리인프라 | kospi | 46742.79 |
| 최근20일 | valuation_daily | 본 표만 | 395400 | SK리츠 | kospi | 15893.73 |
| 최근20일 | valuation_daily | 본 표만 | 950160 | 코오롱티슈진 | kosdaq | 13756.67 |
| 최근20일 | valuation_daily | 본 표만 | 950260 | 인제니아테라퓨틱스(Reg.S) | kosdaq | 12509.49 |
| 최근20일 | valuation_daily | 본 표만 | 415640 | KB발해인프라 | kospi | 12217.79 |
| 최근20일 | valuation_daily | 본 표만 | 330590 | 롯데리츠 | kospi | 11948.86 |
| 최근20일 | valuation_daily | 본 표만 | 451800 | 한화리츠 | kospi | 9788.20 |
| 최근20일 | valuation_daily | 본 표만 | 365550 | ESR켄달스퀘어리츠 | kospi | 7641.06 |
| 최근20일 | valuation_daily | 본 표만 | 094800 | 맵스리얼티 | kospi | 6934.72 |
| 최근20일 | valuation_daily | 본 표만 | 293940 | 신한알파리츠 | kospi | 6675.89 |
| 최근20일 | valuation_daily | 비교 표만 | 196170 | 알테오젠 | kosdaq | 167520.59 |
| 최근20일 | valuation_daily | 비교 표만 | 086520 | 에코프로 | kosdaq | 123827.85 |
| 최근20일 | valuation_daily | 비교 표만 | 247540 | 에코프로비엠 | kosdaq | 123755.50 |
| 최근20일 | valuation_daily | 비교 표만 | 036930 | 주성엔지니어링 | kosdaq | 122477.75 |
| 최근20일 | valuation_daily | 비교 표만 | 0126Z0 | 삼성에피스홀딩스 | kospi | 85348.86 |
| 최근20일 | valuation_daily | 비교 표만 | 058470 | 리노공업 | kosdaq | 66914.00 |
| 최근20일 | valuation_daily | 비교 표만 | 240810 | 원익IPS | kosdaq | 65870.60 |
| 최근20일 | valuation_daily | 비교 표만 | 222800 | 심텍 | kosdaq | 65693.09 |
| 최근20일 | valuation_daily | 비교 표만 | 403870 | HPSP | kosdaq | 52672.00 |
| 최근20일 | valuation_daily | 비교 표만 | 064760 | 티씨케이 | kosdaq | 32755.69 |
| 최근20일 | consensus_daily | 본 표만 | 001570 | 금양 | kospi | 6332.75 |
| 최근20일 | consensus_daily | 본 표만 | 309710 | 아이티켐 | kosdaq | 2684.43 |
| 최근20일 | consensus_daily | 본 표만 | 182400 | 확인 못 함 | kosdaq | 2654.97 |
| 최근20일 | consensus_daily | 본 표만 | 121800 | 확인 못 함 | kosdaq | 2563.09 |
| 최근20일 | consensus_daily | 본 표만 | 377460 | 확인 못 함 | kosdaq | 2531.87 |
| 최근20일 | consensus_daily | 본 표만 | 348950 | 확인 못 함 | kospi | 2332.98 |
| 최근20일 | consensus_daily | 본 표만 | 001470 | 확인 못 함 | kospi | 2277.94 |
| 최근20일 | consensus_daily | 본 표만 | 380540 | 옵티코어 | kosdaq | 2066.58 |
| 최근20일 | consensus_daily | 본 표만 | 080720 | 확인 못 함 | kosdaq | 1924.42 |
| 최근20일 | consensus_daily | 본 표만 | 016790 | 확인 못 함 | kosdaq | 1873.41 |
| 20261008 | daily_flows | 본 표만 | 001570 | 금양 | kospi | 6332.75 |
| 20261008 | daily_flows | 본 표만 | 309710 | 아이티켐 | kosdaq | 2684.43 |
| 20261008 | daily_flows | 본 표만 | 182400 | 확인 못 함 | kosdaq | 2654.97 |
| 20261008 | daily_flows | 본 표만 | 121800 | 확인 못 함 | kosdaq | 2563.09 |
| 20261008 | daily_flows | 본 표만 | 377460 | 확인 못 함 | kosdaq | 2531.87 |
| 20261008 | daily_flows | 본 표만 | 348950 | 확인 못 함 | kospi | 2332.98 |
| 20261008 | daily_flows | 본 표만 | 001470 | 확인 못 함 | kospi | 2277.94 |
| 20261008 | daily_flows | 본 표만 | 380540 | 옵티코어 | kosdaq | 2066.58 |
| 20261008 | daily_flows | 본 표만 | 080720 | 확인 못 함 | kosdaq | 1924.42 |
| 20261008 | daily_flows | 본 표만 | 016790 | 확인 못 함 | kosdaq | 1873.41 |
| 20261008 | short_flows | 본 표만 | 077360 | 덕산하이메탈 | kosdaq | 6411.16 |
| 20261008 | short_flows | 본 표만 | 001570 | 금양 | kospi | 6332.75 |
| 20261008 | short_flows | 본 표만 | 309710 | 아이티켐 | kosdaq | 2684.43 |
| 20261008 | short_flows | 본 표만 | 182400 | 확인 못 함 | kosdaq | 2654.97 |
| 20261008 | short_flows | 본 표만 | 121800 | 확인 못 함 | kosdaq | 2563.09 |
| 20261008 | short_flows | 본 표만 | 377460 | 확인 못 함 | kosdaq | 2531.87 |
| 20261008 | short_flows | 본 표만 | 348950 | 확인 못 함 | kospi | 2332.98 |
| 20261008 | short_flows | 본 표만 | 001470 | 확인 못 함 | kospi | 2277.94 |
| 20261008 | short_flows | 본 표만 | 380540 | 옵티코어 | kosdaq | 2066.58 |
| 20261008 | short_flows | 본 표만 | 080720 | 확인 못 함 | kosdaq | 1924.42 |
| 20261008 | daily_ohlcv_extra | 본 표만 | 005930 | 삼성전자 | kospi | 15375712.74 |
| 20261008 | daily_ohlcv_extra | 본 표만 | 000660 | SK하이닉스 | kospi | 12316101.27 |
| 20261008 | daily_ohlcv_extra | 본 표만 | 005935 | 삼성전자우 | kospi | 1560611.99 |
| 20261008 | daily_ohlcv_extra | 본 표만 | 402340 | SK스퀘어 | kospi | 1397075.14 |
| 20261008 | daily_ohlcv_extra | 본 표만 | 009150 | 삼성전기 | kospi | 1164474.72 |
| 20261008 | daily_ohlcv_extra | 본 표만 | 373220 | LG에너지솔루션 | kospi | 943020.00 |
| 20261008 | daily_ohlcv_extra | 본 표만 | 005380 | 현대차 | kospi | 660248.77 |
| 20261008 | daily_ohlcv_extra | 본 표만 | 105560 | KB금융 | kospi | 579559.76 |
| 20261008 | daily_ohlcv_extra | 본 표만 | 207940 | 삼성바이오로직스 | kospi | 564749.60 |
| 20261008 | daily_ohlcv_extra | 본 표만 | 032830 | 삼성생명 | kospi | 540000.00 |
| 20261008 | daily_ohlcv_extra | 비교 표만 | 196170 | 알테오젠 | kosdaq | 167520.59 |
| 20261008 | daily_ohlcv_extra | 비교 표만 | 086520 | 에코프로 | kosdaq | 123827.85 |
| 20261008 | daily_ohlcv_extra | 비교 표만 | 247540 | 에코프로비엠 | kosdaq | 123755.50 |
| 20261008 | daily_ohlcv_extra | 비교 표만 | 036930 | 주성엔지니어링 | kosdaq | 122477.75 |
| 20261008 | daily_ohlcv_extra | 비교 표만 | 0126Z0 | 삼성에피스홀딩스 | kospi | 85348.86 |
| 20261008 | daily_ohlcv_extra | 비교 표만 | 058470 | 리노공업 | kosdaq | 66914.00 |
| 20261008 | daily_ohlcv_extra | 비교 표만 | 240810 | 원익IPS | kosdaq | 65870.60 |
| 20261008 | daily_ohlcv_extra | 비교 표만 | 222800 | 심텍 | kosdaq | 65693.09 |
| 20261008 | daily_ohlcv_extra | 비교 표만 | 403870 | HPSP | kosdaq | 52672.00 |
| 20261008 | daily_ohlcv_extra | 비교 표만 | 064760 | 티씨케이 | kosdaq | 32755.69 |
| 20261008 | valuation_daily | 본 표만 | 088980 | 맥쿼리인프라 | kospi | 46742.79 |
| 20261008 | valuation_daily | 본 표만 | 395400 | SK리츠 | kospi | 15893.73 |
| 20261008 | valuation_daily | 본 표만 | 950160 | 코오롱티슈진 | kosdaq | 13756.67 |
| 20261008 | valuation_daily | 본 표만 | 950260 | 인제니아테라퓨틱스(Reg.S) | kosdaq | 12509.49 |
| 20261008 | valuation_daily | 본 표만 | 415640 | KB발해인프라 | kospi | 12217.79 |
| 20261008 | valuation_daily | 본 표만 | 330590 | 롯데리츠 | kospi | 11948.86 |
| 20261008 | valuation_daily | 본 표만 | 451800 | 한화리츠 | kospi | 9788.20 |
| 20261008 | valuation_daily | 본 표만 | 365550 | ESR켄달스퀘어리츠 | kospi | 7641.06 |
| 20261008 | valuation_daily | 본 표만 | 094800 | 맵스리얼티 | kospi | 6934.72 |
| 20261008 | valuation_daily | 본 표만 | 293940 | 신한알파리츠 | kospi | 6675.89 |
| 20261008 | valuation_daily | 비교 표만 | 196170 | 알테오젠 | kosdaq | 167520.59 |
| 20261008 | valuation_daily | 비교 표만 | 086520 | 에코프로 | kosdaq | 123827.85 |
| 20261008 | valuation_daily | 비교 표만 | 247540 | 에코프로비엠 | kosdaq | 123755.50 |
| 20261008 | valuation_daily | 비교 표만 | 036930 | 주성엔지니어링 | kosdaq | 122477.75 |
| 20261008 | valuation_daily | 비교 표만 | 0126Z0 | 삼성에피스홀딩스 | kospi | 85348.86 |
| 20261008 | valuation_daily | 비교 표만 | 058470 | 리노공업 | kosdaq | 66914.00 |
| 20261008 | valuation_daily | 비교 표만 | 240810 | 원익IPS | kosdaq | 65870.60 |
| 20261008 | valuation_daily | 비교 표만 | 222800 | 심텍 | kosdaq | 65693.09 |
| 20261008 | valuation_daily | 비교 표만 | 403870 | HPSP | kosdaq | 52672.00 |
| 20261008 | valuation_daily | 비교 표만 | 064760 | 티씨케이 | kosdaq | 32755.69 |
| 20261008 | consensus_daily | 본 표만 | 005930 | 삼성전자 | kospi | 15375712.74 |
| 20261008 | consensus_daily | 본 표만 | 000660 | SK하이닉스 | kospi | 12316101.27 |
| 20261008 | consensus_daily | 본 표만 | 005935 | 삼성전자우 | kospi | 1560611.99 |
| 20261008 | consensus_daily | 본 표만 | 402340 | SK스퀘어 | kospi | 1397075.14 |
| 20261008 | consensus_daily | 본 표만 | 009150 | 삼성전기 | kospi | 1164474.72 |
| 20261008 | consensus_daily | 본 표만 | 373220 | LG에너지솔루션 | kospi | 943020.00 |
| 20261008 | consensus_daily | 본 표만 | 005380 | 현대차 | kospi | 660248.77 |
| 20261008 | consensus_daily | 본 표만 | 105560 | KB금융 | kospi | 579559.76 |
| 20261008 | consensus_daily | 본 표만 | 207940 | 삼성바이오로직스 | kospi | 564749.60 |
| 20261008 | consensus_daily | 본 표만 | 032830 | 삼성생명 | kospi | 540000.00 |

### 현재 large_universe 대비 기준일 누락

| 표 | 기대 유니버스 run | 대상 | 기준일 없음 | 상위10 코드 |
|---|---|---|---|---|
| daily_flows | 20261008 | n=500 | n=52 | 196170, 086520, 247540, 036930, 0126Z0, 058470, 240810, 222800, 403870, 064760 |
| short_flows | 20261008 | n=500 | n=53 | 196170, 086520, 247540, 036930, 0126Z0, 058470, 240810, 222800, 403870, 064760 |

## 6. 캐시·파일 수정 시각(내용 미열람)

파일 메타데이터만 읽었다. 오래됨은 최근 n=20거래일 시작 20260908보다 수정일이 이른 경우이며, 이 기준은 감사용 후보 추출이지 운영 실패 판정이 아니다. 캐시 파일 n=5,591, 오래된 파일 n=1,042. 비밀 이름 파일은 제외했다. pycache/venv/node_modules/.git은 데이터 캐시가 아니므로 제외. 역사 연구 캐시는 고정 보관이 정상일 수 있고, mtime만으로 원자료 기준일은 **확인 못 함**.

| 폴더 | 파일 수 |
|---|---|
| . | n=2 |
| dart_cache | n=1 |
| dart_cache\fin | n=3,562 |
| price_cache | n=2,026 |

### listing_cache 파일

| 이름 | 크기 | 수정 시각 KST |
|---|---|---|
| C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k-data\listing_cache.json | n=339,878 bytes | 2026-10-08T20:42:28+09:00 |

### 최근 수정 파일 최대 n=20개

| 이름 | 크기 | 수정 시각 KST |
|---|---|---|
| dart_cache\fin\d537cf28e743a421be34d2f8861ab20b.json | n=214 bytes | 2026-10-08T21:06:05+09:00 |
| dart_cache\fin\4da21d5683839c5baaebf8603621bc82.json | n=214 bytes | 2026-10-08T21:06:04+09:00 |
| dart_cache\fin\7fc5fd9dab61b6529096e2c18ff22143.json | n=214 bytes | 2026-10-08T21:06:04+09:00 |
| dart_cache\fin\8a5423c4c7a3d6fd835c5d36899a055c.json | n=214 bytes | 2026-10-08T21:06:03+09:00 |
| dart_cache\fin\1128cf8b839b8cdb7625c90c7268b2e3.json | n=214 bytes | 2026-10-08T21:06:00+09:00 |
| dart_cache\fin\acc70d8e09ebe6023d5d31e19921416a.json | n=213 bytes | 2026-10-08T21:05:58+09:00 |
| dart_cache\fin\ad7c2e9c2d39561f8a42ea6e880a3e7b.json | n=214 bytes | 2026-10-08T21:05:58+09:00 |
| dart_cache\fin\c92789ac940e9673e31196ef1f005796.json | n=214 bytes | 2026-10-08T21:05:58+09:00 |
| dart_cache\fin\6b8f4df9f3ced23d582f54ad41145ff8.json | n=214 bytes | 2026-10-08T21:05:56+09:00 |
| dart_cache\fin\01b803f072efb4d064268a752d1833a2.json | n=214 bytes | 2026-10-08T21:05:51+09:00 |
| dart_cache\fin\1cdeacf1ddf23d17c99537635b48a1f2.json | n=213 bytes | 2026-10-08T21:05:50+09:00 |
| dart_cache\fin\8c34fa9f4df1712338943562b30ce102.json | n=214 bytes | 2026-10-08T21:05:50+09:00 |
| dart_cache\fin\36f5e69c0d9e9149fffe6d954dcf0647.json | n=214 bytes | 2026-10-08T21:05:49+09:00 |
| dart_cache\fin\e5bf955b58ca1f7b05b2f51a5417b975.json | n=214 bytes | 2026-10-08T21:05:48+09:00 |
| dart_cache\fin\e671e63a5e05e58bc1fa694585dd9f23.json | n=214 bytes | 2026-10-08T21:05:45+09:00 |
| dart_cache\fin\947f0154b584152a3c75ed20df190b55.json | n=213 bytes | 2026-10-08T21:05:44+09:00 |
| dart_cache\fin\f7ec6165e7fb7c993039718e96e94e50.json | n=214 bytes | 2026-10-08T21:05:44+09:00 |
| dart_cache\fin\21751287ee93ee9ea96d4a1a8ab69aa5.json | n=214 bytes | 2026-10-08T21:05:43+09:00 |
| dart_cache\fin\6d57b37b1ed93e89b24e525bd014e027.json | n=213 bytes | 2026-10-08T21:05:41+09:00 |
| dart_cache\fin\4d884304d93320e42477c26fa6bbe35a.json | n=214 bytes | 2026-10-08T21:05:40+09:00 |

### 오래된 파일 전부(이름·크기·수정 시각만)

| 이름 | 크기 | 수정 시각 KST |
|---|---|---|
| sector_cache.json.bak | n=14,271 bytes | 2026-06-03T12:51:33+09:00 |
| price_cache\000080.parquet | n=2,201 bytes | 2026-06-03T16:47:39+09:00 |
| price_cache\000120.parquet | n=2,623 bytes | 2026-07-11T13:27:13+09:00 |
| price_cache\000140.parquet | n=2,238 bytes | 2026-06-03T16:55:35+09:00 |
| price_cache\000220.parquet | n=2,567 bytes | 2026-07-11T13:27:26+09:00 |
| price_cache\000270.parquet | n=2,200 bytes | 2026-06-15T20:25:13+09:00 |
| price_cache\000490.parquet | n=2,246 bytes | 2026-06-03T16:55:34+09:00 |
| price_cache\000640.parquet | n=3,012 bytes | 2026-09-03T21:31:00+09:00 |
| price_cache\000680.parquet | n=3,000 bytes | 2026-09-03T21:29:14+09:00 |
| price_cache\000700.parquet | n=2,560 bytes | 2026-07-11T13:27:29+09:00 |
| price_cache\000720.parquet | n=2,322 bytes | 2026-06-15T20:25:12+09:00 |
| price_cache\000910.parquet | n=2,606 bytes | 2026-07-11T13:27:13+09:00 |
| price_cache\000950.parquet | n=2,600 bytes | 2026-07-11T13:27:22+09:00 |
| price_cache\001000.parquet | n=2,240 bytes | 2026-06-03T16:56:17+09:00 |
| price_cache\001060.parquet | n=2,205 bytes | 2026-06-03T16:54:27+09:00 |
| price_cache\0010V0.parquet | n=2,668 bytes | 2026-07-21T20:48:01+09:00 |
| price_cache\001120.parquet | n=2,245 bytes | 2026-06-03T16:54:21+09:00 |
| price_cache\001130.parquet | n=2,238 bytes | 2026-06-03T16:54:21+09:00 |
| price_cache\0011A0.parquet | n=3,143 bytes | 2026-09-03T21:27:52+09:00 |
| price_cache\001230.parquet | n=2,270 bytes | 2026-06-15T20:25:07+09:00 |
| price_cache\001250.parquet | n=2,242 bytes | 2026-06-03T16:54:29+09:00 |
| price_cache\001260.parquet | n=2,242 bytes | 2026-06-03T16:55:19+09:00 |
| price_cache\001360.parquet | n=2,989 bytes | 2026-08-26T20:22:56+09:00 |
| price_cache\001390.parquet | n=2,242 bytes | 2026-06-03T16:54:55+09:00 |
| price_cache\001440.parquet | n=2,206 bytes | 2026-06-03T16:55:10+09:00 |
| price_cache\0015G0.parquet | n=2,250 bytes | 2026-06-03T16:56:44+09:00 |
| price_cache\001630.parquet | n=3,040 bytes | 2026-09-03T21:29:49+09:00 |
| price_cache\001680.parquet | n=2,314 bytes | 2026-06-15T20:25:11+09:00 |
| price_cache\001770.parquet | n=2,244 bytes | 2026-06-03T16:55:32+09:00 |
| price_cache\001780.parquet | n=2,242 bytes | 2026-06-03T16:54:22+09:00 |
| price_cache\001790.parquet | n=2,232 bytes | 2026-06-03T16:55:41+09:00 |
| price_cache\001810.parquet | n=2,234 bytes | 2026-06-03T16:57:52+09:00 |
| price_cache\001940.parquet | n=2,717 bytes | 2026-07-29T20:40:15+09:00 |
| price_cache\002100.parquet | n=2,238 bytes | 2026-06-03T16:55:33+09:00 |
| price_cache\002150.parquet | n=2,594 bytes | 2026-07-11T13:27:18+09:00 |
| price_cache\002170.parquet | n=2,247 bytes | 2026-06-03T16:55:43+09:00 |
| price_cache\002200.parquet | n=2,585 bytes | 2026-07-11T13:27:17+09:00 |
| price_cache\002230.parquet | n=2,244 bytes | 2026-06-03T16:57:05+09:00 |
| price_cache\002240.parquet | n=2,616 bytes | 2026-07-11T13:27:25+09:00 |
| price_cache\002290.parquet | n=2,234 bytes | 2026-06-03T16:57:42+09:00 |
| price_cache\002320.parquet | n=2,246 bytes | 2026-06-03T16:55:12+09:00 |
| price_cache\002460.parquet | n=2,246 bytes | 2026-06-03T16:55:12+09:00 |
| price_cache\002600.parquet | n=2,235 bytes | 2026-06-03T16:55:21+09:00 |
| price_cache\002620.parquet | n=2,200 bytes | 2026-06-03T16:55:32+09:00 |
| price_cache\002710.parquet | n=2,247 bytes | 2026-06-03T16:54:43+09:00 |
| price_cache\002720.parquet | n=2,690 bytes | 2026-07-27T20:29:24+09:00 |
| price_cache\002760.parquet | n=2,596 bytes | 2026-07-11T13:27:17+09:00 |
| price_cache\002800.parquet | n=2,241 bytes | 2026-06-03T16:56:38+09:00 |
| price_cache\002840.parquet | n=2,246 bytes | 2026-06-03T16:54:51+09:00 |
| price_cache\002920.parquet | n=2,194 bytes | 2026-06-03T16:55:30+09:00 |
| price_cache\003000.parquet | n=2,244 bytes | 2026-06-03T16:54:32+09:00 |
| price_cache\003080.parquet | n=2,225 bytes | 2026-06-03T16:55:18+09:00 |
| price_cache\003090.parquet | n=2,714 bytes | 2026-07-23T20:52:58+09:00 |
| price_cache\003100.parquet | n=2,205 bytes | 2026-06-03T16:56:45+09:00 |
| price_cache\003310.parquet | n=3,109 bytes | 2026-09-03T21:28:57+09:00 |
| price_cache\003350.parquet | n=2,961 bytes | 2026-09-03T21:30:21+09:00 |
| price_cache\003380.parquet | n=2,244 bytes | 2026-06-03T16:56:18+09:00 |
| price_cache\003480.parquet | n=2,191 bytes | 2026-06-03T16:54:42+09:00 |
| price_cache\003610.parquet | n=2,176 bytes | 2026-06-03T16:55:02+09:00 |
| price_cache\003670.parquet | n=2,199 bytes | 2026-06-03T16:55:07+09:00 |
| price_cache\003800.parquet | n=2,196 bytes | 2026-06-03T16:57:31+09:00 |
| price_cache\003830.parquet | n=2,252 bytes | 2026-06-03T16:55:37+09:00 |
| price_cache\003850.parquet | n=2,199 bytes | 2026-06-03T16:41:09+09:00 |
| price_cache\003960.parquet | n=2,991 bytes | 2026-08-26T20:22:39+09:00 |
| price_cache\004080.parquet | n=2,178 bytes | 2026-06-03T16:54:55+09:00 |
| price_cache\004100.parquet | n=2,190 bytes | 2026-06-03T16:47:49+09:00 |
| price_cache\004140.parquet | n=2,598 bytes | 2026-07-11T13:27:27+09:00 |
| price_cache\004310.parquet | n=2,776 bytes | 2026-07-31T20:39:05+09:00 |
| price_cache\004360.parquet | n=2,587 bytes | 2026-07-11T13:27:26+09:00 |
| price_cache\004410.parquet | n=3,075 bytes | 2026-09-03T21:29:20+09:00 |
| price_cache\004450.parquet | n=2,242 bytes | 2026-06-03T16:55:33+09:00 |
| price_cache\004490.parquet | n=2,242 bytes | 2026-06-03T16:54:56+09:00 |
| price_cache\004590.parquet | n=2,142 bytes | 2026-06-03T16:57:17+09:00 |
| price_cache\004650.parquet | n=2,242 bytes | 2026-06-03T16:57:04+09:00 |
| price_cache\004690.parquet | n=2,250 bytes | 2026-06-03T16:54:29+09:00 |
| price_cache\004700.parquet | n=2,548 bytes | 2026-07-11T13:27:31+09:00 |
| price_cache\004720.parquet | n=2,230 bytes | 2026-06-03T16:54:53+09:00 |
| price_cache\004770.parquet | n=2,238 bytes | 2026-06-03T16:47:20+09:00 |
| price_cache\004780.parquet | n=2,229 bytes | 2026-06-03T16:57:26+09:00 |
| price_cache\004830.parquet | n=2,240 bytes | 2026-06-03T16:55:34+09:00 |
| price_cache\004890.parquet | n=2,239 bytes | 2026-06-03T16:55:23+09:00 |
| price_cache\004910.parquet | n=2,587 bytes | 2026-07-11T13:27:18+09:00 |
| price_cache\004920.parquet | n=2,236 bytes | 2026-06-03T16:47:05+09:00 |
| price_cache\004970.parquet | n=2,231 bytes | 2026-06-03T16:47:08+09:00 |
| price_cache\005070.parquet | n=2,200 bytes | 2026-06-03T16:41:43+09:00 |
| price_cache\005160.parquet | n=2,242 bytes | 2026-06-03T16:58:13+09:00 |
| price_cache\005320.parquet | n=2,188 bytes | 2026-06-03T16:55:25+09:00 |
| price_cache\005610.parquet | n=2,246 bytes | 2026-06-03T16:55:26+09:00 |
| price_cache\005710.parquet | n=2,721 bytes | 2026-07-28T20:31:06+09:00 |
| price_cache\005720.parquet | n=2,195 bytes | 2026-06-03T16:55:32+09:00 |
| price_cache\005740.parquet | n=2,196 bytes | 2026-06-03T16:55:05+09:00 |
| price_cache\005800.parquet | n=2,192 bytes | 2026-06-03T16:55:37+09:00 |
| price_cache\005810.parquet | n=2,248 bytes | 2026-06-03T16:54:36+09:00 |
| price_cache\005820.parquet | n=2,605 bytes | 2026-07-11T13:27:14+09:00 |
| price_cache\005870.parquet | n=3,055 bytes | 2026-09-03T21:29:14+09:00 |
| price_cache\005960.parquet | n=2,605 bytes | 2026-07-11T13:27:31+09:00 |
| price_cache\006040.parquet | n=2,944 bytes | 2026-09-03T21:31:12+09:00 |
| price_cache\006050.parquet | n=2,240 bytes | 2026-06-03T16:25:31+09:00 |
| price_cache\006090.parquet | n=2,194 bytes | 2026-06-03T16:54:25+09:00 |
| price_cache\006140.parquet | n=2,201 bytes | 2026-06-03T16:56:26+09:00 |
| price_cache\006260.parquet | n=2,316 bytes | 2026-06-15T20:25:10+09:00 |
| price_cache\006340.parquet | n=3,077 bytes | 2026-09-03T21:29:09+09:00 |
| price_cache\006360.parquet | n=2,612 bytes | 2026-07-11T13:27:15+09:00 |
| price_cache\006620.parquet | n=2,199 bytes | 2026-06-03T16:57:44+09:00 |
| price_cache\006730.parquet | n=2,243 bytes | 2026-06-03T16:55:54+09:00 |
| price_cache\006910.parquet | n=3,082 bytes | 2026-09-03T21:28:25+09:00 |
| price_cache\006980.parquet | n=2,628 bytes | 2026-07-11T13:27:11+09:00 |
| price_cache\007110.parquet | n=2,605 bytes | 2026-07-11T13:27:18+09:00 |
| price_cache\007160.parquet | n=2,245 bytes | 2026-06-03T16:55:38+09:00 |
| price_cache\007280.parquet | n=2,589 bytes | 2026-07-11T13:27:11+09:00 |
| price_cache\007310.parquet | n=2,199 bytes | 2026-06-03T16:54:53+09:00 |
| price_cache\007340.parquet | n=2,205 bytes | 2026-06-03T16:55:00+09:00 |
| price_cache\007370.parquet | n=2,199 bytes | 2026-06-03T16:57:26+09:00 |
| price_cache\007460.parquet | n=2,799 bytes | 2026-09-03T21:31:08+09:00 |
| price_cache\007540.parquet | n=2,248 bytes | 2026-06-03T16:54:19+09:00 |
| price_cache\007570.parquet | n=2,593 bytes | 2026-07-11T13:27:23+09:00 |
| price_cache\007590.parquet | n=2,168 bytes | 2026-06-03T16:55:41+09:00 |
| price_cache\007690.parquet | n=2,245 bytes | 2026-06-03T16:55:44+09:00 |
| price_cache\007700.parquet | n=2,200 bytes | 2026-06-03T16:54:54+09:00 |
| price_cache\007820.parquet | n=2,201 bytes | 2026-06-03T16:57:45+09:00 |
| price_cache\007860.parquet | n=2,128 bytes | 2026-06-03T16:55:27+09:00 |
| price_cache\008260.parquet | n=2,588 bytes | 2026-07-11T13:27:15+09:00 |
| price_cache\0082N0.parquet | n=2,206 bytes | 2026-06-03T16:56:47+09:00 |
| price_cache\008350.parquet | n=2,603 bytes | 2026-07-11T13:27:16+09:00 |
| price_cache\008370.parquet | n=2,194 bytes | 2026-06-03T16:57:19+09:00 |
| price_cache\008470.parquet | n=2,236 bytes | 2026-06-03T16:58:16+09:00 |
| price_cache\008500.parquet | n=2,467 bytes | 2026-07-20T20:36:49+09:00 |
| price_cache\008700.parquet | n=2,240 bytes | 2026-06-03T16:46:54+09:00 |
| price_cache\009070.parquet | n=2,593 bytes | 2026-07-11T13:27:25+09:00 |
| price_cache\009180.parquet | n=2,196 bytes | 2026-06-03T16:55:30+09:00 |
| price_cache\009270.parquet | n=2,234 bytes | 2026-06-03T16:54:41+09:00 |
| price_cache\009290.parquet | n=2,243 bytes | 2026-06-03T16:54:17+09:00 |
| price_cache\009300.parquet | n=2,245 bytes | 2026-06-03T16:57:01+09:00 |
| price_cache\009320.parquet | n=2,240 bytes | 2026-06-03T16:24:57+09:00 |
| price_cache\009580.parquet | n=3,097 bytes | 2026-09-03T21:28:48+09:00 |
| price_cache\009770.parquet | n=2,240 bytes | 2026-06-03T16:55:06+09:00 |
| price_cache\009780.parquet | n=2,240 bytes | 2026-06-03T16:57:13+09:00 |
| price_cache\009900.parquet | n=2,247 bytes | 2026-06-03T16:54:26+09:00 |
| price_cache\010240.parquet | n=2,195 bytes | 2026-06-03T16:57:54+09:00 |
| price_cache\010470.parquet | n=2,992 bytes | 2026-08-31T21:23:02+09:00 |
| price_cache\010580.parquet | n=2,736 bytes | 2026-09-03T21:30:42+09:00 |
| price_cache\010640.parquet | n=2,236 bytes | 2026-06-03T16:54:47+09:00 |
| price_cache\010660.parquet | n=3,052 bytes | 2026-09-03T21:28:40+09:00 |
| price_cache\010690.parquet | n=2,191 bytes | 2026-06-03T16:55:09+09:00 |
| price_cache\010820.parquet | n=3,119 bytes | 2026-09-03T21:30:41+09:00 |
| price_cache\011040.parquet | n=2,236 bytes | 2026-06-03T16:56:33+09:00 |
| price_cache\011420.parquet | n=3,043 bytes | 2026-09-03T21:29:04+09:00 |
| price_cache\011700.parquet | n=2,652 bytes | 2026-07-20T20:36:54+09:00 |
| price_cache\011760.parquet | n=2,187 bytes | 2026-06-03T16:55:35+09:00 |
| price_cache\011780.parquet | n=2,312 bytes | 2026-06-15T20:25:12+09:00 |
| price_cache\011930.parquet | n=3,135 bytes | 2026-09-03T21:29:37+09:00 |
| price_cache\012170.parquet | n=2,611 bytes | 2026-07-11T13:27:10+09:00 |
| price_cache\012320.parquet | n=2,625 bytes | 2026-07-11T13:27:29+09:00 |
| price_cache\012620.parquet | n=2,245 bytes | 2026-06-03T16:57:27+09:00 |
| price_cache\0126Z0.parquet | n=2,247 bytes | 2026-06-03T16:55:13+09:00 |
| price_cache\012700.parquet | n=2,237 bytes | 2026-06-03T16:57:48+09:00 |
| price_cache\012750.parquet | n=2,611 bytes | 2026-07-11T13:27:25+09:00 |
| price_cache\012790.parquet | n=2,241 bytes | 2026-06-03T16:57:00+09:00 |
| price_cache\012800.parquet | n=2,973 bytes | 2026-09-03T21:30:40+09:00 |
| price_cache\012860.parquet | n=2,141 bytes | 2026-06-03T16:58:04+09:00 |
| price_cache\013000.parquet | n=2,125 bytes | 2026-06-03T16:55:14+09:00 |
| price_cache\013030.parquet | n=2,206 bytes | 2026-06-03T16:56:47+09:00 |
| price_cache\013310.parquet | n=2,199 bytes | 2026-06-03T16:57:01+09:00 |
| price_cache\013360.parquet | n=2,725 bytes | 2026-07-27T20:29:46+09:00 |
| price_cache\013520.parquet | n=2,242 bytes | 2026-06-03T16:55:04+09:00 |
| price_cache\013570.parquet | n=2,679 bytes | 2026-07-23T20:53:05+09:00 |
| price_cache\013700.parquet | n=2,183 bytes | 2026-06-03T16:55:32+09:00 |
| price_cache\013870.parquet | n=2,693 bytes | 2026-07-27T20:29:43+09:00 |
| price_cache\014130.parquet | n=3,025 bytes | 2026-09-03T21:31:06+09:00 |
| price_cache\014160.parquet | n=2,638 bytes | 2026-07-20T20:36:54+09:00 |
| price_cache\014440.parquet | n=2,198 bytes | 2026-06-03T16:55:21+09:00 |
| price_cache\014470.parquet | n=2,198 bytes | 2026-06-03T16:32:01+09:00 |
| price_cache\014530.parquet | n=2,227 bytes | 2026-06-03T16:54:31+09:00 |
| price_cache\014620.parquet | n=2,252 bytes | 2026-06-03T16:56:56+09:00 |
| price_cache\014710.parquet | n=2,200 bytes | 2026-06-03T16:47:48+09:00 |
| price_cache\014790.parquet | n=2,668 bytes | 2026-07-22T20:49:15+09:00 |
| price_cache\014820.parquet | n=2,606 bytes | 2026-07-11T13:27:18+09:00 |
| price_cache\014830.parquet | n=2,250 bytes | 2026-06-03T16:54:44+09:00 |
| price_cache\014950.parquet | n=2,245 bytes | 2026-06-03T16:56:38+09:00 |
| price_cache\014970.parquet | n=2,235 bytes | 2026-06-03T16:56:59+09:00 |
| price_cache\015230.parquet | n=2,199 bytes | 2026-06-03T16:54:29+09:00 |
| price_cache\015360.parquet | n=2,201 bytes | 2026-06-03T16:55:03+09:00 |
| price_cache\015710.parquet | n=2,236 bytes | 2026-06-03T16:57:35+09:00 |
| price_cache\015750.parquet | n=2,244 bytes | 2026-06-03T16:56:37+09:00 |
| price_cache\015860.parquet | n=3,041 bytes | 2026-09-04T21:25:46+09:00 |
| price_cache\015890.parquet | n=2,187 bytes | 2026-06-03T16:47:33+09:00 |
| price_cache\016100.parquet | n=2,236 bytes | 2026-06-03T16:57:08+09:00 |
| price_cache\016250.parquet | n=2,247 bytes | 2026-06-03T16:56:42+09:00 |
| price_cache\016380.parquet | n=2,200 bytes | 2026-06-03T16:55:08+09:00 |
| price_cache\016580.parquet | n=2,915 bytes | 2026-09-03T21:30:54+09:00 |
| price_cache\016710.parquet | n=2,244 bytes | 2026-06-03T16:54:42+09:00 |
| price_cache\016800.parquet | n=2,978 bytes | 2026-09-03T21:31:21+09:00 |
| price_cache\017000.parquet | n=2,242 bytes | 2026-06-03T16:56:17+09:00 |
| price_cache\017180.parquet | n=2,240 bytes | 2026-06-03T16:54:51+09:00 |
| price_cache\017250.parquet | n=2,198 bytes | 2026-06-03T16:57:30+09:00 |
| price_cache\017390.parquet | n=2,248 bytes | 2026-06-03T16:55:28+09:00 |
| price_cache\017510.parquet | n=2,247 bytes | 2026-06-03T16:56:07+09:00 |
| price_cache\017550.parquet | n=2,198 bytes | 2026-06-03T16:55:40+09:00 |
| price_cache\017650.parquet | n=2,190 bytes | 2026-06-03T16:58:04+09:00 |
| price_cache\017810.parquet | n=2,607 bytes | 2026-07-11T13:27:26+09:00 |
| price_cache\017890.parquet | n=2,236 bytes | 2026-06-03T16:56:23+09:00 |
| price_cache\017940.parquet | n=2,249 bytes | 2026-06-03T16:54:51+09:00 |
| price_cache\018120.parquet | n=2,232 bytes | 2026-06-03T16:58:11+09:00 |
| price_cache\018250.parquet | n=2,245 bytes | 2026-06-03T16:55:14+09:00 |
| price_cache\018290.parquet | n=2,247 bytes | 2026-06-03T16:56:47+09:00 |
| price_cache\018670.parquet | n=3,013 bytes | 2026-09-02T21:28:42+09:00 |
| price_cache\019680.parquet | n=2,601 bytes | 2026-07-11T13:27:17+09:00 |
| price_cache\019770.parquet | n=2,236 bytes | 2026-06-03T16:56:49+09:00 |
| price_cache\020120.parquet | n=2,883 bytes | 2026-09-03T21:31:11+09:00 |
| price_cache\020180.parquet | n=2,241 bytes | 2026-06-03T16:57:58+09:00 |
| price_cache\020710.parquet | n=2,645 bytes | 2026-07-20T20:36:02+09:00 |
| price_cache\021040.parquet | n=2,234 bytes | 2026-06-03T16:57:13+09:00 |
| price_cache\021050.parquet | n=2,837 bytes | 2026-09-03T21:30:41+09:00 |
| price_cache\021080.parquet | n=2,817 bytes | 2026-09-03T21:29:01+09:00 |
| price_cache\021320.parquet | n=2,245 bytes | 2026-06-03T16:57:14+09:00 |
| price_cache\021820.parquet | n=2,245 bytes | 2026-06-03T16:55:00+09:00 |
| price_cache\022100.parquet | n=2,199 bytes | 2026-06-03T16:34:20+09:00 |
| price_cache\023000.parquet | n=2,227 bytes | 2026-06-03T16:55:16+09:00 |
| price_cache\023150.parquet | n=2,590 bytes | 2026-07-11T13:27:26+09:00 |
| price_cache\023160.parquet | n=2,248 bytes | 2026-06-03T16:56:33+09:00 |
| price_cache\023410.parquet | n=2,231 bytes | 2026-06-03T16:57:00+09:00 |
| price_cache\023450.parquet | n=2,237 bytes | 2026-06-03T16:55:21+09:00 |
| price_cache\023590.parquet | n=2,206 bytes | 2026-06-03T16:54:52+09:00 |
| price_cache\023600.parquet | n=2,242 bytes | 2026-06-03T16:57:56+09:00 |
| price_cache\023800.parquet | n=3,023 bytes | 2026-09-03T21:31:22+09:00 |
| price_cache\023810.parquet | n=2,668 bytes | 2026-07-22T20:49:07+09:00 |
| price_cache\023900.parquet | n=2,246 bytes | 2026-06-03T16:57:43+09:00 |
| price_cache\023910.parquet | n=2,201 bytes | 2026-06-03T16:58:07+09:00 |
| price_cache\023960.parquet | n=2,238 bytes | 2026-06-03T16:41:05+09:00 |
| price_cache\024090.parquet | n=2,240 bytes | 2026-06-03T16:54:54+09:00 |
| price_cache\024120.parquet | n=2,236 bytes | 2026-06-03T16:56:28+09:00 |
| price_cache\024720.parquet | n=3,050 bytes | 2026-09-03T21:29:09+09:00 |
| price_cache\024830.parquet | n=2,199 bytes | 2026-06-03T16:58:13+09:00 |
| price_cache\024840.parquet | n=2,202 bytes | 2026-06-03T16:57:35+09:00 |
| price_cache\024880.parquet | n=2,200 bytes | 2026-06-03T16:57:25+09:00 |
| price_cache\025000.parquet | n=2,195 bytes | 2026-06-03T16:55:41+09:00 |
| price_cache\025320.parquet | n=2,242 bytes | 2026-06-03T16:57:53+09:00 |
| price_cache\025550.parquet | n=2,241 bytes | 2026-06-03T16:57:10+09:00 |
| price_cache\025770.parquet | n=3,057 bytes | 2026-09-03T21:27:48+09:00 |
| price_cache\025820.parquet | n=2,189 bytes | 2026-06-03T16:55:40+09:00 |
| price_cache\025860.parquet | n=2,720 bytes | 2026-07-27T20:29:53+09:00 |
| price_cache\025870.parquet | n=2,751 bytes | 2026-07-28T20:31:21+09:00 |
| price_cache\025890.parquet | n=2,196 bytes | 2026-06-03T16:55:36+09:00 |
| price_cache\025900.parquet | n=2,246 bytes | 2026-06-03T16:57:40+09:00 |
| price_cache\025980.parquet | n=2,243 bytes | 2026-06-03T16:56:50+09:00 |
| price_cache\026040.parquet | n=2,241 bytes | 2026-06-03T16:57:59+09:00 |
| price_cache\026890.parquet | n=2,244 bytes | 2026-06-03T16:54:21+09:00 |
| price_cache\026940.parquet | n=2,236 bytes | 2026-06-03T16:55:16+09:00 |
| price_cache\026960.parquet | n=2,138 bytes | 2026-06-03T16:47:33+09:00 |
| price_cache\027050.parquet | n=2,236 bytes | 2026-06-03T16:55:56+09:00 |
| price_cache\027360.parquet | n=2,206 bytes | 2026-06-03T16:56:52+09:00 |
| price_cache\027410.parquet | n=3,026 bytes | 2026-09-03T21:30:25+09:00 |
| price_cache\027710.parquet | n=2,240 bytes | 2026-06-03T16:57:49+09:00 |
| price_cache\027740.parquet | n=2,762 bytes | 2026-07-31T20:37:45+09:00 |
| price_cache\027830.parquet | n=2,236 bytes | 2026-06-03T16:57:54+09:00 |
| price_cache\028100.parquet | n=2,616 bytes | 2026-07-11T13:27:28+09:00 |
| price_cache\028670.parquet | n=2,199 bytes | 2026-06-03T16:55:41+09:00 |
| price_cache\029460.parquet | n=2,205 bytes | 2026-06-03T16:55:18+09:00 |
| price_cache\029530.parquet | n=2,607 bytes | 2026-07-11T13:27:15+09:00 |
| price_cache\030000.parquet | n=2,201 bytes | 2026-06-03T16:55:38+09:00 |
| price_cache\030520.parquet | n=2,202 bytes | 2026-06-03T16:36:06+09:00 |
| price_cache\030530.parquet | n=2,252 bytes | 2026-06-03T16:57:46+09:00 |
| price_cache\030960.parquet | n=2,243 bytes | 2026-06-03T16:56:38+09:00 |
| price_cache\031310.parquet | n=3,051 bytes | 2026-09-03T21:28:40+09:00 |
| price_cache\032190.parquet | n=2,193 bytes | 2026-06-03T16:57:18+09:00 |
| price_cache\032620.parquet | n=2,231 bytes | 2026-06-03T16:56:18+09:00 |
| price_cache\032750.parquet | n=2,232 bytes | 2026-06-03T16:56:55+09:00 |
| price_cache\032820.parquet | n=2,731 bytes | 2026-07-23T20:51:42+09:00 |
| price_cache\032940.parquet | n=2,247 bytes | 2026-06-03T16:56:49+09:00 |
| price_cache\032960.parquet | n=2,245 bytes | 2026-06-03T16:56:02+09:00 |
| price_cache\033100.parquet | n=2,210 bytes | 2026-06-03T16:57:33+09:00 |
| price_cache\033250.parquet | n=2,715 bytes | 2026-07-27T20:29:52+09:00 |
| price_cache\033270.parquet | n=2,201 bytes | 2026-06-03T16:54:44+09:00 |
| price_cache\033310.parquet | n=2,234 bytes | 2026-06-03T16:57:42+09:00 |
| price_cache\033320.parquet | n=2,238 bytes | 2026-06-03T16:56:29+09:00 |
| price_cache\033340.parquet | n=2,237 bytes | 2026-06-03T16:45:09+09:00 |
| price_cache\033530.parquet | n=3,026 bytes | 2026-09-03T21:29:49+09:00 |
| price_cache\033790.parquet | n=2,870 bytes | 2026-09-03T21:29:37+09:00 |
| price_cache\033920.parquet | n=2,239 bytes | 2026-06-03T16:54:53+09:00 |
| price_cache\034590.parquet | n=2,190 bytes | 2026-06-03T16:55:38+09:00 |
| price_cache\034810.parquet | n=2,242 bytes | 2026-06-03T16:57:57+09:00 |
| price_cache\034950.parquet | n=2,188 bytes | 2026-06-03T16:57:43+09:00 |
| price_cache\035200.parquet | n=2,237 bytes | 2026-06-03T16:57:20+09:00 |
| price_cache\035250.parquet | n=2,244 bytes | 2026-06-03T16:55:31+09:00 |
| price_cache\035420.parquet | n=2,746 bytes | 2026-09-04T21:25:48+09:00 |
| price_cache\035460.parquet | n=2,199 bytes | 2026-06-03T16:56:25+09:00 |
| price_cache\035600.parquet | n=2,241 bytes | 2026-06-03T16:57:32+09:00 |
| price_cache\035610.parquet | n=2,190 bytes | 2026-06-03T16:57:47+09:00 |
| price_cache\035810.parquet | n=3,018 bytes | 2026-09-03T21:28:22+09:00 |
| price_cache\036030.parquet | n=2,198 bytes | 2026-06-03T16:56:37+09:00 |
| price_cache\036170.parquet | n=2,249 bytes | 2026-06-03T16:56:46+09:00 |
| price_cache\036190.parquet | n=2,248 bytes | 2026-06-03T16:58:07+09:00 |
| price_cache\036200.parquet | n=2,191 bytes | 2026-06-03T16:57:57+09:00 |
| price_cache\036220.parquet | n=2,246 bytes | 2026-06-03T16:57:37+09:00 |
| price_cache\036420.parquet | n=2,202 bytes | 2026-06-03T16:55:23+09:00 |
| price_cache\036540.parquet | n=2,129 bytes | 2026-06-03T16:58:16+09:00 |
| price_cache\036560.parquet | n=2,239 bytes | 2026-06-03T16:57:21+09:00 |
| price_cache\036580.parquet | n=2,668 bytes | 2026-07-22T20:49:15+09:00 |
| price_cache\036640.parquet | n=2,225 bytes | 2026-06-03T16:57:11+09:00 |
| price_cache\036670.parquet | n=2,238 bytes | 2026-06-03T16:58:01+09:00 |
| price_cache\036800.parquet | n=2,207 bytes | 2026-06-03T16:57:35+09:00 |
| price_cache\036810.parquet | n=2,252 bytes | 2026-06-03T16:56:58+09:00 |
| price_cache\037030.parquet | n=2,128 bytes | 2026-06-03T16:58:07+09:00 |
| price_cache\037230.parquet | n=2,690 bytes | 2026-07-22T20:48:22+09:00 |
| price_cache\037330.parquet | n=2,240 bytes | 2026-06-03T16:57:27+09:00 |
| price_cache\037350.parquet | n=2,243 bytes | 2026-06-03T16:56:56+09:00 |
| price_cache\037370.parquet | n=2,234 bytes | 2026-06-03T16:56:04+09:00 |
| price_cache\037440.parquet | n=2,199 bytes | 2026-06-03T16:57:57+09:00 |
| price_cache\037560.parquet | n=2,192 bytes | 2026-06-03T16:33:51+09:00 |
| price_cache\038060.parquet | n=2,198 bytes | 2026-06-03T16:49:08+09:00 |
| price_cache\038070.parquet | n=2,976 bytes | 2026-09-04T21:25:31+09:00 |
| price_cache\038110.parquet | n=2,241 bytes | 2026-06-03T16:56:03+09:00 |
| price_cache\038390.parquet | n=2,242 bytes | 2026-06-03T16:57:09+09:00 |
| price_cache\038460.parquet | n=3,021 bytes | 2026-09-03T21:28:41+09:00 |
| price_cache\038540.parquet | n=2,177 bytes | 2026-06-03T16:57:52+09:00 |
| price_cache\038680.parquet | n=2,243 bytes | 2026-06-03T16:56:46+09:00 |
| price_cache\038950.parquet | n=2,191 bytes | 2026-06-03T16:57:11+09:00 |
| price_cache\039010.parquet | n=2,239 bytes | 2026-06-03T16:45:57+09:00 |
| price_cache\039130.parquet | n=2,840 bytes | 2026-09-03T21:31:17+09:00 |
| price_cache\039200.parquet | n=2,248 bytes | 2026-06-03T16:57:52+09:00 |
| price_cache\039240.parquet | n=2,227 bytes | 2026-06-03T16:57:50+09:00 |
| price_cache\039290.parquet | n=3,077 bytes | 2026-09-03T21:28:16+09:00 |
| price_cache\039310.parquet | n=3,092 bytes | 2026-09-03T21:28:23+09:00 |
| price_cache\039420.parquet | n=2,198 bytes | 2026-06-03T16:56:43+09:00 |
| price_cache\039440.parquet | n=2,249 bytes | 2026-06-03T16:57:44+09:00 |
| price_cache\039570.parquet | n=2,223 bytes | 2026-06-03T16:47:19+09:00 |
| price_cache\039610.parquet | n=2,244 bytes | 2026-06-03T16:56:58+09:00 |
| price_cache\039860.parquet | n=2,825 bytes | 2026-09-03T21:28:14+09:00 |
| price_cache\040160.parquet | n=2,247 bytes | 2026-06-03T16:57:29+09:00 |
| price_cache\040300.parquet | n=2,237 bytes | 2026-06-03T16:56:18+09:00 |
| price_cache\040420.parquet | n=2,225 bytes | 2026-06-03T16:58:16+09:00 |
| price_cache\040910.parquet | n=2,196 bytes | 2026-06-03T16:56:54+09:00 |
| price_cache\041020.parquet | n=3,083 bytes | 2026-09-03T21:28:58+09:00 |
| price_cache\041190.parquet | n=3,040 bytes | 2026-09-04T21:25:36+09:00 |
| price_cache\041440.parquet | n=2,200 bytes | 2026-06-03T16:57:34+09:00 |
| price_cache\041510.parquet | n=2,245 bytes | 2026-06-03T16:56:30+09:00 |
| price_cache\041520.parquet | n=2,206 bytes | 2026-06-03T16:56:33+09:00 |
| price_cache\041910.parquet | n=2,200 bytes | 2026-06-03T16:57:18+09:00 |
| price_cache\041930.parquet | n=2,129 bytes | 2026-06-03T16:58:06+09:00 |
| price_cache\041960.parquet | n=2,243 bytes | 2026-06-03T16:57:58+09:00 |
| price_cache\042110.parquet | n=2,240 bytes | 2026-06-03T16:57:41+09:00 |
| price_cache\042370.parquet | n=3,131 bytes | 2026-09-03T21:28:42+09:00 |
| price_cache\042510.parquet | n=2,246 bytes | 2026-06-03T16:56:15+09:00 |
| price_cache\042700.parquet | n=2,206 bytes | 2026-06-03T16:55:17+09:00 |
| price_cache\043150.parquet | n=2,247 bytes | 2026-06-03T16:56:53+09:00 |
| price_cache\043650.parquet | n=2,231 bytes | 2026-06-03T16:58:07+09:00 |
| price_cache\044380.parquet | n=3,089 bytes | 2026-09-03T21:28:19+09:00 |
| price_cache\044450.parquet | n=2,667 bytes | 2026-07-21T20:48:49+09:00 |
| price_cache\044780.parquet | n=2,240 bytes | 2026-06-03T16:57:47+09:00 |
| price_cache\044820.parquet | n=2,188 bytes | 2026-06-03T16:55:14+09:00 |
| price_cache\044960.parquet | n=2,241 bytes | 2026-06-03T16:57:39+09:00 |
| price_cache\045100.parquet | n=2,193 bytes | 2026-06-03T16:57:32+09:00 |
| price_cache\045300.parquet | n=2,189 bytes | 2026-06-03T16:57:42+09:00 |
| price_cache\045390.parquet | n=2,238 bytes | 2026-06-03T16:57:20+09:00 |
| price_cache\045510.parquet | n=2,236 bytes | 2026-06-03T16:45:02+09:00 |
| price_cache\045520.parquet | n=2,231 bytes | 2026-06-03T16:56:59+09:00 |
| price_cache\045970.parquet | n=2,243 bytes | 2026-06-03T16:57:40+09:00 |
| price_cache\046120.parquet | n=2,246 bytes | 2026-06-03T16:56:55+09:00 |
| price_cache\046210.parquet | n=2,241 bytes | 2026-06-03T16:57:37+09:00 |
| price_cache\046310.parquet | n=2,241 bytes | 2026-06-03T16:56:44+09:00 |
| price_cache\047050.parquet | n=2,208 bytes | 2026-06-03T16:54:19+09:00 |
| price_cache\047310.parquet | n=3,011 bytes | 2026-09-03T21:28:37+09:00 |
| price_cache\047400.parquet | n=2,729 bytes | 2026-07-27T20:29:25+09:00 |
| price_cache\047770.parquet | n=2,239 bytes | 2026-06-03T16:56:10+09:00 |
| price_cache\047810.parquet | n=2,246 bytes | 2026-06-15T20:25:09+09:00 |
| price_cache\047820.parquet | n=2,237 bytes | 2026-06-03T16:57:23+09:00 |
| price_cache\048430.parquet | n=2,243 bytes | 2026-06-03T16:57:06+09:00 |
| price_cache\048470.parquet | n=2,232 bytes | 2026-06-03T16:56:14+09:00 |
| price_cache\048530.parquet | n=2,241 bytes | 2026-06-03T16:57:18+09:00 |
| price_cache\048830.parquet | n=2,236 bytes | 2026-06-03T16:36:47+09:00 |
| price_cache\049080.parquet | n=2,241 bytes | 2026-06-03T16:57:19+09:00 |
| price_cache\049430.parquet | n=2,200 bytes | 2026-06-03T16:45:05+09:00 |
| price_cache\049480.parquet | n=2,236 bytes | 2026-06-03T16:56:41+09:00 |
| price_cache\049520.parquet | n=2,194 bytes | 2026-06-03T16:58:14+09:00 |
| price_cache\049550.parquet | n=2,194 bytes | 2026-06-03T16:57:40+09:00 |
| price_cache\049720.parquet | n=2,194 bytes | 2026-06-03T16:57:58+09:00 |
| price_cache\049800.parquet | n=2,232 bytes | 2026-06-03T16:55:04+09:00 |
| price_cache\049950.parquet | n=2,205 bytes | 2026-06-03T16:56:17+09:00 |
| price_cache\050890.parquet | n=2,202 bytes | 2026-06-03T16:57:52+09:00 |
| price_cache\050960.parquet | n=2,238 bytes | 2026-06-03T16:57:39+09:00 |
| price_cache\051360.parquet | n=2,143 bytes | 2026-06-03T16:58:09+09:00 |
| price_cache\051390.parquet | n=2,772 bytes | 2026-09-03T21:30:03+09:00 |
| price_cache\051490.parquet | n=2,237 bytes | 2026-06-03T16:58:13+09:00 |
| price_cache\051980.parquet | n=2,241 bytes | 2026-06-03T16:57:32+09:00 |
| price_cache\052020.parquet | n=2,243 bytes | 2026-06-03T16:57:20+09:00 |
| price_cache\052260.parquet | n=2,236 bytes | 2026-06-03T16:57:15+09:00 |
| price_cache\052600.parquet | n=2,237 bytes | 2026-06-03T16:56:17+09:00 |
| price_cache\052860.parquet | n=2,948 bytes | 2026-09-03T21:29:36+09:00 |
| price_cache\053030.parquet | n=2,235 bytes | 2026-06-03T16:57:25+09:00 |
| price_cache\053080.parquet | n=2,205 bytes | 2026-06-03T16:58:08+09:00 |
| price_cache\053160.parquet | n=2,234 bytes | 2026-06-03T16:50:05+09:00 |
| price_cache\053210.parquet | n=2,581 bytes | 2026-07-11T13:27:31+09:00 |
| price_cache\053260.parquet | n=2,658 bytes | 2026-07-20T20:35:46+09:00 |
| price_cache\053290.parquet | n=2,240 bytes | 2026-06-03T16:57:55+09:00 |
| price_cache\053300.parquet | n=2,234 bytes | 2026-06-03T16:56:23+09:00 |
| price_cache\053350.parquet | n=2,232 bytes | 2026-06-03T16:57:29+09:00 |
| price_cache\053450.parquet | n=2,237 bytes | 2026-06-03T16:58:01+09:00 |
| price_cache\053580.parquet | n=2,242 bytes | 2026-06-03T16:56:32+09:00 |
| price_cache\053610.parquet | n=2,187 bytes | 2026-06-03T16:57:53+09:00 |
| price_cache\053690.parquet | n=2,627 bytes | 2026-07-11T13:27:28+09:00 |
| price_cache\053700.parquet | n=2,244 bytes | 2026-06-03T16:57:35+09:00 |
| price_cache\053980.parquet | n=2,232 bytes | 2026-06-03T16:57:41+09:00 |
| price_cache\054050.parquet | n=2,238 bytes | 2026-06-03T16:58:04+09:00 |
| price_cache\054090.parquet | n=2,194 bytes | 2026-06-03T16:35:41+09:00 |
| price_cache\054450.parquet | n=2,143 bytes | 2026-06-03T16:57:34+09:00 |
| price_cache\054540.parquet | n=2,246 bytes | 2026-06-03T16:56:10+09:00 |
| price_cache\054670.parquet | n=2,232 bytes | 2026-06-03T16:57:31+09:00 |
| price_cache\054780.parquet | n=2,231 bytes | 2026-06-03T16:56:31+09:00 |
| price_cache\054800.parquet | n=2,191 bytes | 2026-06-03T16:57:34+09:00 |
| price_cache\054920.parquet | n=2,198 bytes | 2026-06-03T16:56:50+09:00 |
| price_cache\056080.parquet | n=2,252 bytes | 2026-06-03T16:57:37+09:00 |
| price_cache\056090.parquet | n=2,740 bytes | 2026-07-28T20:31:19+09:00 |
| price_cache\056190.parquet | n=2,206 bytes | 2026-06-03T16:58:15+09:00 |
| price_cache\056360.parquet | n=2,203 bytes | 2026-06-03T16:57:29+09:00 |
| price_cache\056700.parquet | n=2,238 bytes | 2026-06-03T16:57:56+09:00 |
| price_cache\057050.parquet | n=2,205 bytes | 2026-06-03T16:55:15+09:00 |
| price_cache\058630.parquet | n=2,198 bytes | 2026-06-03T16:57:51+09:00 |
| price_cache\058820.parquet | n=2,731 bytes | 2026-07-28T20:31:09+09:00 |
| price_cache\058850.parquet | n=2,199 bytes | 2026-06-03T16:54:39+09:00 |
| price_cache\058860.parquet | n=2,192 bytes | 2026-06-03T16:54:44+09:00 |
| price_cache\058970.parquet | n=2,248 bytes | 2026-06-03T16:58:04+09:00 |
| price_cache\059090.parquet | n=2,205 bytes | 2026-06-03T16:50:08+09:00 |
| price_cache\059210.parquet | n=2,198 bytes | 2026-06-03T16:57:55+09:00 |
| price_cache\060150.parquet | n=2,241 bytes | 2026-06-03T16:56:53+09:00 |
| price_cache\060280.parquet | n=2,246 bytes | 2026-06-03T16:57:22+09:00 |
| price_cache\060370.parquet | n=3,054 bytes | 2026-09-03T21:29:19+09:00 |
| price_cache\060380.parquet | n=2,240 bytes | 2026-06-03T16:57:55+09:00 |
| price_cache\060540.parquet | n=2,138 bytes | 2026-06-03T16:58:01+09:00 |
| price_cache\060590.parquet | n=2,198 bytes | 2026-06-03T16:56:31+09:00 |
| price_cache\060720.parquet | n=2,202 bytes | 2026-06-03T16:56:43+09:00 |
| price_cache\063080.parquet | n=2,245 bytes | 2026-06-03T16:58:15+09:00 |
| price_cache\063160.parquet | n=2,244 bytes | 2026-06-03T16:55:27+09:00 |
| price_cache\063170.parquet | n=3,102 bytes | 2026-09-03T21:27:47+09:00 |
| price_cache\063570.parquet | n=2,242 bytes | 2026-06-03T16:55:55+09:00 |
| price_cache\064240.parquet | n=2,232 bytes | 2026-06-03T16:57:50+09:00 |
| price_cache\064520.parquet | n=2,194 bytes | 2026-06-03T16:58:09+09:00 |
| price_cache\065440.parquet | n=2,244 bytes | 2026-06-03T16:57:33+09:00 |
| price_cache\065660.parquet | n=2,244 bytes | 2026-06-03T16:56:17+09:00 |
| price_cache\065690.parquet | n=2,187 bytes | 2026-06-03T16:56:53+09:00 |
| price_cache\065710.parquet | n=2,245 bytes | 2026-06-03T16:58:16+09:00 |
| price_cache\066130.parquet | n=2,236 bytes | 2026-06-03T16:57:48+09:00 |
| price_cache\066670.parquet | n=2,196 bytes | 2026-06-03T16:57:50+09:00 |
| price_cache\066700.parquet | n=2,234 bytes | 2026-06-03T16:57:36+09:00 |
| price_cache\067000.parquet | n=2,241 bytes | 2026-06-03T16:56:28+09:00 |
| price_cache\067010.parquet | n=2,225 bytes | 2026-06-03T16:57:55+09:00 |
| price_cache\067080.parquet | n=2,196 bytes | 2026-06-03T16:58:08+09:00 |
| price_cache\067170.parquet | n=2,141 bytes | 2026-06-03T16:58:11+09:00 |
| price_cache\067280.parquet | n=2,237 bytes | 2026-06-03T16:58:01+09:00 |
| price_cache\067570.parquet | n=2,231 bytes | 2026-06-03T16:57:51+09:00 |
| price_cache\067730.parquet | n=2,236 bytes | 2026-06-03T16:56:23+09:00 |
| price_cache\067770.parquet | n=2,194 bytes | 2026-06-03T16:56:30+09:00 |
| price_cache\067830.parquet | n=2,999 bytes | 2026-09-01T21:24:33+09:00 |
| price_cache\067900.parquet | n=2,242 bytes | 2026-06-03T16:57:22+09:00 |
| price_cache\067920.parquet | n=2,236 bytes | 2026-06-03T16:57:32+09:00 |
| price_cache\068100.parquet | n=2,183 bytes | 2026-06-03T16:58:05+09:00 |
| price_cache\068330.parquet | n=2,654 bytes | 2026-07-20T20:36:08+09:00 |
| price_cache\068930.parquet | n=2,185 bytes | 2026-06-03T16:57:07+09:00 |
| price_cache\069080.parquet | n=2,238 bytes | 2026-06-03T16:57:45+09:00 |
| price_cache\069140.parquet | n=2,241 bytes | 2026-06-03T16:57:14+09:00 |
| price_cache\069330.parquet | n=2,192 bytes | 2026-06-03T16:46:12+09:00 |
| price_cache\069410.parquet | n=2,199 bytes | 2026-06-03T16:57:56+09:00 |
| price_cache\069510.parquet | n=2,248 bytes | 2026-06-03T16:56:22+09:00 |
| price_cache\069540.parquet | n=2,192 bytes | 2026-06-03T16:57:34+09:00 |
| price_cache\069730.parquet | n=2,183 bytes | 2026-06-03T16:41:51+09:00 |
| price_cache\070590.parquet | n=2,198 bytes | 2026-06-03T16:45:57+09:00 |
| price_cache\070960.parquet | n=2,236 bytes | 2026-06-03T16:55:03+09:00 |
| price_cache\071090.parquet | n=3,049 bytes | 2026-09-03T21:29:17+09:00 |
| price_cache\071280.parquet | n=2,200 bytes | 2026-06-03T16:57:19+09:00 |
| price_cache\071320.parquet | n=2,248 bytes | 2026-06-03T16:54:27+09:00 |
| price_cache\071670.parquet | n=2,246 bytes | 2026-06-03T16:57:38+09:00 |
| price_cache\071840.parquet | n=2,237 bytes | 2026-06-03T16:55:32+09:00 |
| price_cache\072020.parquet | n=2,188 bytes | 2026-06-03T16:57:28+09:00 |
| price_cache\072130.parquet | n=2,586 bytes | 2026-07-11T13:27:20+09:00 |
| price_cache\072470.parquet | n=2,242 bytes | 2026-06-03T16:56:19+09:00 |
| price_cache\072870.parquet | n=2,189 bytes | 2026-06-03T16:46:19+09:00 |
| price_cache\073190.parquet | n=2,231 bytes | 2026-06-03T16:35:51+09:00 |
| price_cache\073240.parquet | n=2,591 bytes | 2026-07-11T13:27:23+09:00 |
| price_cache\073540.parquet | n=2,235 bytes | 2026-06-03T16:57:06+09:00 |
| price_cache\075130.parquet | n=2,240 bytes | 2026-06-03T16:57:30+09:00 |
| price_cache\075180.parquet | n=2,225 bytes | 2026-06-03T16:47:29+09:00 |
| price_cache\075970.parquet | n=2,236 bytes | 2026-06-03T16:56:01+09:00 |
| price_cache\078000.parquet | n=2,606 bytes | 2026-07-11T13:27:23+09:00 |
| price_cache\078160.parquet | n=2,248 bytes | 2026-06-03T16:57:06+09:00 |
| price_cache\078340.parquet | n=2,719 bytes | 2026-07-29T20:39:58+09:00 |
| price_cache\078890.parquet | n=2,191 bytes | 2026-06-03T16:57:25+09:00 |
| price_cache\078930.parquet | n=2,191 bytes | 2026-06-03T16:41:51+09:00 |
| price_cache\079000.parquet | n=2,235 bytes | 2026-06-03T16:57:53+09:00 |
| price_cache\079160.parquet | n=2,237 bytes | 2026-06-03T16:54:30+09:00 |
| price_cache\079170.parquet | n=2,237 bytes | 2026-06-03T16:56:55+09:00 |
| price_cache\079370.parquet | n=2,246 bytes | 2026-06-03T16:57:28+09:00 |
| price_cache\079430.parquet | n=2,242 bytes | 2026-06-03T16:55:31+09:00 |
| price_cache\079810.parquet | n=3,120 bytes | 2026-09-04T21:24:56+09:00 |
| price_cache\080010.parquet | n=2,190 bytes | 2026-06-03T16:57:11+09:00 |
| price_cache\080160.parquet | n=2,234 bytes | 2026-06-03T16:58:06+09:00 |
| price_cache\080470.parquet | n=2,241 bytes | 2026-06-03T16:56:33+09:00 |
| price_cache\080520.parquet | n=2,238 bytes | 2026-06-03T16:57:36+09:00 |
| price_cache\081180.parquet | n=2,699 bytes | 2026-07-22T20:47:48+09:00 |
| price_cache\082850.parquet | n=2,240 bytes | 2026-06-03T16:56:43+09:00 |
| price_cache\083310.parquet | n=2,203 bytes | 2026-06-03T16:58:08+09:00 |
| price_cache\083420.parquet | n=2,580 bytes | 2026-07-11T13:27:11+09:00 |
| price_cache\083450.parquet | n=2,143 bytes | 2026-06-03T16:57:23+09:00 |
| price_cache\083470.parquet | n=2,198 bytes | 2026-06-03T16:29:46+09:00 |
| price_cache\083550.parquet | n=2,188 bytes | 2026-06-03T16:56:17+09:00 |
| price_cache\083650.parquet | n=2,245 bytes | 2026-06-03T16:57:20+09:00 |
| price_cache\083790.parquet | n=2,238 bytes | 2026-06-03T16:46:20+09:00 |
| price_cache\083930.parquet | n=2,201 bytes | 2026-06-03T16:58:12+09:00 |
| price_cache\084010.parquet | n=2,733 bytes | 2026-07-27T20:30:00+09:00 |
| price_cache\084110.parquet | n=2,756 bytes | 2026-07-28T20:31:28+09:00 |
| price_cache\084180.parquet | n=2,237 bytes | 2026-06-03T16:26:10+09:00 |
| price_cache\084440.parquet | n=2,134 bytes | 2026-06-03T16:58:09+09:00 |
| price_cache\084650.parquet | n=2,197 bytes | 2026-06-03T16:35:38+09:00 |
| price_cache\084680.parquet | n=3,094 bytes | 2026-09-03T21:29:14+09:00 |
| price_cache\084690.parquet | n=2,147 bytes | 2026-07-03T01:20:46+09:00 |
| price_cache\084730.parquet | n=2,238 bytes | 2026-06-03T16:58:10+09:00 |
| price_cache\084870.parquet | n=2,596 bytes | 2026-07-11T13:27:25+09:00 |
| price_cache\086280.parquet | n=2,246 bytes | 2026-06-15T20:25:09+09:00 |
| price_cache\086450.parquet | n=2,243 bytes | 2026-06-03T16:57:22+09:00 |
| price_cache\086670.parquet | n=2,245 bytes | 2026-06-03T16:57:59+09:00 |
| price_cache\086710.parquet | n=2,247 bytes | 2026-06-03T16:57:07+09:00 |
| price_cache\086820.parquet | n=2,246 bytes | 2026-06-03T16:56:19+09:00 |
| price_cache\086890.parquet | n=2,718 bytes | 2026-07-28T20:31:04+09:00 |
| price_cache\087260.parquet | n=2,244 bytes | 2026-06-03T16:28:36+09:00 |
| price_cache\088130.parquet | n=3,094 bytes | 2026-09-03T21:28:00+09:00 |
| price_cache\088280.parquet | n=2,245 bytes | 2026-06-03T16:57:26+09:00 |
| price_cache\088390.parquet | n=2,245 bytes | 2026-06-03T16:56:34+09:00 |
| price_cache\088800.parquet | n=2,242 bytes | 2026-06-03T16:57:30+09:00 |
| price_cache\088910.parquet | n=2,231 bytes | 2026-06-03T16:56:24+09:00 |
| price_cache\089010.parquet | n=2,205 bytes | 2026-06-03T16:57:46+09:00 |
| price_cache\089150.parquet | n=3,103 bytes | 2026-09-03T21:28:21+09:00 |
| price_cache\089230.parquet | n=2,244 bytes | 2026-06-03T16:57:08+09:00 |
| price_cache\089470.parquet | n=2,592 bytes | 2026-07-11T13:27:10+09:00 |
| price_cache\089600.parquet | n=2,238 bytes | 2026-06-03T16:56:00+09:00 |
| price_cache\089790.parquet | n=2,202 bytes | 2026-06-03T16:57:12+09:00 |
| price_cache\089850.parquet | n=2,241 bytes | 2026-06-03T16:57:41+09:00 |
| price_cache\089860.parquet | n=2,184 bytes | 2026-06-03T16:55:30+09:00 |
| price_cache\089890.parquet | n=2,203 bytes | 2026-06-03T16:50:07+09:00 |
| price_cache\090370.parquet | n=3,032 bytes | 2026-09-03T21:28:59+09:00 |
| price_cache\090410.parquet | n=2,234 bytes | 2026-06-03T16:45:56+09:00 |
| price_cache\090430.parquet | n=2,759 bytes | 2026-07-27T20:29:22+09:00 |
| price_cache\090470.parquet | n=2,245 bytes | 2026-06-03T16:58:02+09:00 |
| price_cache\090710.parquet | n=2,247 bytes | 2026-06-03T16:57:51+09:00 |
| price_cache\091120.parquet | n=2,244 bytes | 2026-06-03T16:57:51+09:00 |
| price_cache\091340.parquet | n=2,140 bytes | 2026-06-03T16:57:13+09:00 |
| price_cache\091700.parquet | n=2,237 bytes | 2026-06-03T16:56:27+09:00 |
| price_cache\092130.parquet | n=2,242 bytes | 2026-06-03T16:49:24+09:00 |
| price_cache\092220.parquet | n=3,068 bytes | 2026-08-31T21:22:42+09:00 |
| price_cache\092230.parquet | n=2,193 bytes | 2026-06-03T16:55:02+09:00 |
| price_cache\092730.parquet | n=2,245 bytes | 2026-06-03T16:56:31+09:00 |
| price_cache\092780.parquet | n=2,817 bytes | 2026-09-03T21:31:21+09:00 |
| price_cache\092870.parquet | n=2,206 bytes | 2026-06-03T16:57:07+09:00 |
| price_cache\093050.parquet | n=2,197 bytes | 2026-06-03T16:55:11+09:00 |
| price_cache\093190.parquet | n=2,243 bytes | 2026-06-03T16:56:56+09:00 |
| price_cache\093520.parquet | n=2,205 bytes | 2026-06-03T16:56:51+09:00 |
| price_cache\093640.parquet | n=2,195 bytes | 2026-06-03T16:58:10+09:00 |
| price_cache\093920.parquet | n=2,198 bytes | 2026-06-03T16:57:46+09:00 |
| price_cache\094170.parquet | n=2,249 bytes | 2026-06-03T16:58:00+09:00 |
| price_cache\094280.parquet | n=2,232 bytes | 2026-06-03T16:41:44+09:00 |
| price_cache\094360.parquet | n=2,205 bytes | 2026-06-03T16:57:49+09:00 |
| price_cache\094480.parquet | n=2,244 bytes | 2026-06-03T16:56:52+09:00 |
| price_cache\094800.parquet | n=2,568 bytes | 2026-07-11T13:27:16+09:00 |
| price_cache\094840.parquet | n=2,198 bytes | 2026-06-03T16:57:27+09:00 |
| price_cache\094860.parquet | n=2,234 bytes | 2026-06-03T16:58:05+09:00 |
| price_cache\094970.parquet | n=2,196 bytes | 2026-06-03T16:56:09+09:00 |
| price_cache\095270.parquet | n=2,742 bytes | 2026-07-28T20:31:00+09:00 |
| price_cache\095500.parquet | n=2,245 bytes | 2026-06-03T16:56:45+09:00 |
| price_cache\095700.parquet | n=2,240 bytes | 2026-06-03T16:57:10+09:00 |
| price_cache\095720.parquet | n=3,098 bytes | 2026-09-03T21:27:44+09:00 |
| price_cache\095910.parquet | n=3,067 bytes | 2026-09-03T21:28:39+09:00 |
| price_cache\096240.parquet | n=2,246 bytes | 2026-06-03T16:56:59+09:00 |
| price_cache\096250.parquet | n=2,239 bytes | 2026-06-03T16:57:02+09:00 |
| price_cache\096760.parquet | n=2,231 bytes | 2026-06-03T16:54:26+09:00 |
| price_cache\096770.parquet | n=3,150 bytes | 2026-09-03T21:30:33+09:00 |
| price_cache\096870.parquet | n=2,717 bytes | 2026-07-28T20:31:23+09:00 |
| price_cache\097520.parquet | n=2,142 bytes | 2026-06-03T16:47:21+09:00 |
| price_cache\097870.parquet | n=2,237 bytes | 2026-06-03T16:57:37+09:00 |
| price_cache\098070.parquet | n=3,123 bytes | 2026-09-03T21:29:48+09:00 |
| price_cache\098120.parquet | n=2,192 bytes | 2026-06-03T16:56:37+09:00 |
| price_cache\098660.parquet | n=2,240 bytes | 2026-06-03T16:56:39+09:00 |
| price_cache\099220.parquet | n=2,229 bytes | 2026-06-03T16:44:42+09:00 |
| price_cache\099750.parquet | n=2,239 bytes | 2026-06-03T16:56:56+09:00 |
| price_cache\100030.parquet | n=2,196 bytes | 2026-06-03T16:58:02+09:00 |
| price_cache\100120.parquet | n=2,206 bytes | 2026-06-03T16:57:18+09:00 |
| price_cache\100220.parquet | n=3,022 bytes | 2026-09-03T21:29:03+09:00 |
| price_cache\100250.parquet | n=2,196 bytes | 2026-06-03T16:54:59+09:00 |
| price_cache\100590.parquet | n=2,871 bytes | 2026-09-03T21:30:49+09:00 |
| price_cache\100660.parquet | n=2,237 bytes | 2026-06-03T16:56:34+09:00 |
| price_cache\100700.parquet | n=2,236 bytes | 2026-06-03T16:56:36+09:00 |
| price_cache\101160.parquet | n=2,245 bytes | 2026-06-03T16:57:15+09:00 |
| price_cache\101170.parquet | n=2,195 bytes | 2026-06-03T16:56:39+09:00 |
| price_cache\101240.parquet | n=2,240 bytes | 2026-06-03T16:57:02+09:00 |
| price_cache\101330.parquet | n=3,022 bytes | 2026-09-03T21:27:43+09:00 |
| price_cache\101360.parquet | n=2,722 bytes | 2026-07-23T20:51:44+09:00 |
| price_cache\101530.parquet | n=2,195 bytes | 2026-06-03T16:55:28+09:00 |
| price_cache\101680.parquet | n=2,199 bytes | 2026-06-03T16:56:50+09:00 |
| price_cache\101970.parquet | n=2,245 bytes | 2026-06-03T16:56:55+09:00 |
| price_cache\102120.parquet | n=2,202 bytes | 2026-06-03T16:57:46+09:00 |
| price_cache\102260.parquet | n=2,198 bytes | 2026-06-03T16:55:04+09:00 |
| price_cache\102370.parquet | n=2,191 bytes | 2026-06-03T16:45:59+09:00 |
| price_cache\102460.parquet | n=2,192 bytes | 2026-06-03T16:55:29+09:00 |
| price_cache\103230.parquet | n=3,036 bytes | 2026-09-03T21:27:54+09:00 |
| price_cache\104480.parquet | n=2,240 bytes | 2026-06-03T16:56:11+09:00 |
| price_cache\104540.parquet | n=2,237 bytes | 2026-06-03T16:57:23+09:00 |
| price_cache\104700.parquet | n=2,244 bytes | 2026-06-03T16:55:16+09:00 |
| price_cache\105330.parquet | n=2,199 bytes | 2026-06-03T16:58:15+09:00 |
| price_cache\105740.parquet | n=2,247 bytes | 2026-06-03T16:58:00+09:00 |
| price_cache\105760.parquet | n=3,075 bytes | 2026-09-03T21:28:50+09:00 |
| price_cache\106240.parquet | n=2,198 bytes | 2026-06-03T16:57:01+09:00 |
| price_cache\108230.parquet | n=2,930 bytes | 2026-09-03T21:29:16+09:00 |
| price_cache\108380.parquet | n=3,134 bytes | 2026-09-03T21:28:48+09:00 |
| price_cache\109070.parquet | n=2,241 bytes | 2026-06-03T16:47:37+09:00 |
| price_cache\109080.parquet | n=2,248 bytes | 2026-06-03T16:57:31+09:00 |
| price_cache\109610.parquet | n=2,237 bytes | 2026-06-03T16:56:29+09:00 |
| price_cache\109670.parquet | n=2,238 bytes | 2026-06-03T16:56:29+09:00 |
| price_cache\109860.parquet | n=2,136 bytes | 2026-06-03T16:49:39+09:00 |
| price_cache\110790.parquet | n=2,227 bytes | 2026-06-03T16:57:45+09:00 |
| price_cache\110990.parquet | n=2,200 bytes | 2026-06-03T16:57:15+09:00 |
| price_cache\111380.parquet | n=2,127 bytes | 2026-06-03T16:55:27+09:00 |
| price_cache\112610.parquet | n=2,240 bytes | 2026-06-03T16:54:50+09:00 |
| price_cache\114810.parquet | n=2,203 bytes | 2026-06-03T16:57:10+09:00 |
| price_cache\114840.parquet | n=2,244 bytes | 2026-06-03T16:26:16+09:00 |
| price_cache\115180.parquet | n=2,246 bytes | 2026-06-03T16:58:10+09:00 |
| price_cache\115440.parquet | n=2,203 bytes | 2026-06-03T16:56:58+09:00 |
| price_cache\115450.parquet | n=2,241 bytes | 2026-06-03T16:57:49+09:00 |
| price_cache\115500.parquet | n=2,249 bytes | 2026-06-03T16:58:08+09:00 |
| price_cache\117580.parquet | n=2,694 bytes | 2026-07-23T20:53:02+09:00 |
| price_cache\117730.parquet | n=2,249 bytes | 2026-06-03T16:58:05+09:00 |
| price_cache\118990.parquet | n=2,197 bytes | 2026-06-03T16:57:27+09:00 |
| price_cache\119500.parquet | n=2,239 bytes | 2026-06-03T16:56:56+09:00 |
| price_cache\119610.parquet | n=2,129 bytes | 2026-06-03T16:57:54+09:00 |
| price_cache\119850.parquet | n=2,251 bytes | 2026-06-03T16:57:02+09:00 |
| price_cache\120030.parquet | n=2,240 bytes | 2026-06-03T16:55:13+09:00 |
| price_cache\121440.parquet | n=2,237 bytes | 2026-06-03T16:56:47+09:00 |
| price_cache\122870.parquet | n=2,248 bytes | 2026-06-03T16:56:41+09:00 |
| price_cache\122900.parquet | n=2,194 bytes | 2026-06-03T16:31:01+09:00 |
| price_cache\123010.parquet | n=2,738 bytes | 2026-09-03T21:30:00+09:00 |
| price_cache\123700.parquet | n=2,190 bytes | 2026-06-03T16:55:24+09:00 |
| price_cache\124560.parquet | n=2,237 bytes | 2026-06-03T16:58:05+09:00 |
| price_cache\125210.parquet | n=2,730 bytes | 2026-07-23T20:51:18+09:00 |
| price_cache\126340.parquet | n=2,206 bytes | 2026-06-03T16:57:07+09:00 |
| price_cache\126560.parquet | n=2,219 bytes | 2026-06-03T16:54:27+09:00 |
| price_cache\126600.parquet | n=2,241 bytes | 2026-06-03T16:57:31+09:00 |
| price_cache\126720.parquet | n=2,249 bytes | 2026-06-03T16:54:25+09:00 |
| price_cache\127710.parquet | n=2,241 bytes | 2026-06-03T16:44:24+09:00 |
| price_cache\128660.parquet | n=2,241 bytes | 2026-06-03T16:57:41+09:00 |
| price_cache\129260.parquet | n=2,592 bytes | 2026-07-11T13:27:27+09:00 |
| price_cache\129920.parquet | n=3,035 bytes | 2026-08-27T20:23:50+09:00 |
| price_cache\130500.parquet | n=2,236 bytes | 2026-06-03T16:57:01+09:00 |
| price_cache\131030.parquet | n=2,244 bytes | 2026-06-03T16:56:34+09:00 |
| price_cache\131090.parquet | n=2,236 bytes | 2026-06-03T16:57:26+09:00 |
| price_cache\131100.parquet | n=2,240 bytes | 2026-06-03T16:31:17+09:00 |
| price_cache\131370.parquet | n=2,240 bytes | 2026-06-03T16:56:18+09:00 |
| price_cache\131400.parquet | n=2,241 bytes | 2026-06-03T16:50:01+09:00 |
| price_cache\134060.parquet | n=2,234 bytes | 2026-06-03T16:56:22+09:00 |
| price_cache\134380.parquet | n=2,712 bytes | 2026-07-31T20:39:32+09:00 |
| price_cache\136150.parquet | n=2,246 bytes | 2026-06-03T16:57:38+09:00 |
| price_cache\136480.parquet | n=2,237 bytes | 2026-06-03T16:57:15+09:00 |
| price_cache\136490.parquet | n=2,197 bytes | 2026-06-03T16:47:09+09:00 |
| price_cache\136540.parquet | n=2,240 bytes | 2026-06-03T16:57:25+09:00 |
| price_cache\137080.parquet | n=2,239 bytes | 2026-06-03T16:56:27+09:00 |
| price_cache\137400.parquet | n=2,250 bytes | 2026-06-03T16:58:16+09:00 |
| price_cache\138080.parquet | n=2,843 bytes | 2026-09-03T21:30:49+09:00 |
| price_cache\139670.parquet | n=2,240 bytes | 2026-06-03T16:56:09+09:00 |
| price_cache\139990.parquet | n=3,022 bytes | 2026-09-03T21:27:59+09:00 |
| price_cache\140070.parquet | n=2,199 bytes | 2026-06-03T16:57:33+09:00 |
| price_cache\140410.parquet | n=2,243 bytes | 2026-06-03T16:57:01+09:00 |
| price_cache\140520.parquet | n=2,236 bytes | 2026-06-03T16:57:42+09:00 |
| price_cache\140670.parquet | n=2,205 bytes | 2026-06-03T16:56:40+09:00 |
| price_cache\140860.parquet | n=2,208 bytes | 2026-06-15T20:25:11+09:00 |
| price_cache\141000.parquet | n=2,200 bytes | 2026-06-03T16:57:57+09:00 |
| price_cache\143160.parquet | n=2,245 bytes | 2026-06-03T16:57:58+09:00 |
| price_cache\143240.parquet | n=2,236 bytes | 2026-06-03T16:56:00+09:00 |
| price_cache\143540.parquet | n=2,189 bytes | 2026-06-03T16:57:31+09:00 |
| price_cache\144510.parquet | n=2,243 bytes | 2026-06-03T16:56:14+09:00 |
| price_cache\145990.parquet | n=2,227 bytes | 2026-06-03T16:41:45+09:00 |
| price_cache\146060.parquet | n=2,240 bytes | 2026-06-03T16:45:14+09:00 |
| price_cache\147830.parquet | n=3,053 bytes | 2026-09-03T21:27:53+09:00 |
| price_cache\153460.parquet | n=2,645 bytes | 2026-07-20T20:36:20+09:00 |
| price_cache\153710.parquet | n=2,198 bytes | 2026-06-03T16:57:28+09:00 |
| price_cache\154030.parquet | n=2,236 bytes | 2026-06-03T16:57:40+09:00 |
| price_cache\154040.parquet | n=2,240 bytes | 2026-06-03T16:26:02+09:00 |
| price_cache\155650.parquet | n=2,976 bytes | 2026-09-03T21:29:53+09:00 |
| price_cache\155660.parquet | n=2,187 bytes | 2026-06-03T16:47:21+09:00 |
| price_cache\158430.parquet | n=2,244 bytes | 2026-06-03T16:57:29+09:00 |
| price_cache\160190.parquet | n=2,252 bytes | 2026-06-03T16:57:03+09:00 |
| price_cache\161580.parquet | n=2,206 bytes | 2026-06-03T16:58:04+09:00 |
| price_cache\161890.parquet | n=2,181 bytes | 2026-06-03T16:54:53+09:00 |
| price_cache\163560.parquet | n=2,196 bytes | 2026-06-03T16:55:25+09:00 |
| price_cache\163730.parquet | n=2,205 bytes | 2026-06-03T16:56:46+09:00 |
| price_cache\166480.parquet | n=2,141 bytes | 2026-06-03T16:57:51+09:00 |
| price_cache\168330.parquet | n=2,141 bytes | 2026-06-03T16:58:17+09:00 |
| price_cache\170030.parquet | n=2,199 bytes | 2026-06-03T16:57:47+09:00 |
| price_cache\170790.parquet | n=2,235 bytes | 2026-06-03T16:56:38+09:00 |
| price_cache\171010.parquet | n=2,188 bytes | 2026-06-03T16:57:12+09:00 |
| price_cache\172670.parquet | n=2,206 bytes | 2026-06-03T16:57:37+09:00 |
| price_cache\173940.parquet | n=2,812 bytes | 2026-09-03T21:30:51+09:00 |
| price_cache\178920.parquet | n=2,844 bytes | 2026-09-04T21:25:40+09:00 |
| price_cache\182360.parquet | n=2,245 bytes | 2026-06-03T16:56:32+09:00 |
| price_cache\185750.parquet | n=3,042 bytes | 2026-09-03T21:29:22+09:00 |
| price_cache\187270.parquet | n=2,231 bytes | 2026-06-03T16:46:10+09:00 |
| price_cache\187790.parquet | n=2,141 bytes | 2026-06-03T16:58:17+09:00 |
| price_cache\188040.parquet | n=3,008 bytes | 2026-09-01T21:23:37+09:00 |
| price_cache\189690.parquet | n=2,238 bytes | 2026-06-03T16:57:19+09:00 |
| price_cache\189860.parquet | n=2,202 bytes | 2026-06-03T16:56:12+09:00 |
| price_cache\189980.parquet | n=2,240 bytes | 2026-06-03T16:56:41+09:00 |
| price_cache\190510.parquet | n=2,191 bytes | 2026-06-03T16:45:13+09:00 |
| price_cache\191410.parquet | n=2,742 bytes | 2026-07-28T20:31:23+09:00 |
| price_cache\191420.parquet | n=2,246 bytes | 2026-06-03T16:56:29+09:00 |
| price_cache\192250.parquet | n=2,936 bytes | 2026-09-03T21:29:06+09:00 |
| price_cache\192390.parquet | n=2,242 bytes | 2026-06-03T16:56:50+09:00 |
| price_cache\192400.parquet | n=2,246 bytes | 2026-06-03T16:54:57+09:00 |
| price_cache\192650.parquet | n=2,730 bytes | 2026-07-27T20:30:03+09:00 |
| price_cache\192820.parquet | n=2,250 bytes | 2026-06-03T16:54:19+09:00 |
| price_cache\194370.parquet | n=2,247 bytes | 2026-06-03T16:54:13+09:00 |
| price_cache\195500.parquet | n=2,241 bytes | 2026-06-03T16:55:52+09:00 |
| price_cache\196300.parquet | n=2,244 bytes | 2026-06-03T16:57:09+09:00 |
| price_cache\196450.parquet | n=2,141 bytes | 2026-06-03T16:49:56+09:00 |
| price_cache\196700.parquet | n=3,105 bytes | 2026-09-03T21:29:25+09:00 |
| price_cache\197140.parquet | n=2,194 bytes | 2026-06-03T16:57:14+09:00 |
| price_cache\199430.parquet | n=2,244 bytes | 2026-06-03T16:56:46+09:00 |
| price_cache\199730.parquet | n=2,241 bytes | 2026-06-03T16:56:57+09:00 |
| price_cache\199800.parquet | n=2,254 bytes | 2026-06-03T16:57:23+09:00 |
| price_cache\199820.parquet | n=2,244 bytes | 2026-06-03T16:56:38+09:00 |
| price_cache\200350.parquet | n=3,032 bytes | 2026-09-03T21:31:01+09:00 |
| price_cache\200670.parquet | n=2,238 bytes | 2026-06-03T16:56:49+09:00 |
| price_cache\200710.parquet | n=2,249 bytes | 2026-06-03T16:57:23+09:00 |
| price_cache\201490.parquet | n=2,980 bytes | 2026-09-03T21:29:17+09:00 |
| price_cache\204610.parquet | n=2,242 bytes | 2026-06-03T16:56:11+09:00 |
| price_cache\204620.parquet | n=2,753 bytes | 2026-07-31T20:37:34+09:00 |
| price_cache\205500.parquet | n=2,242 bytes | 2026-06-03T16:26:35+09:00 |
| price_cache\206560.parquet | n=2,242 bytes | 2026-06-03T16:56:30+09:00 |
| price_cache\206650.parquet | n=2,754 bytes | 2026-07-28T20:31:30+09:00 |
| price_cache\208140.parquet | n=2,229 bytes | 2026-06-03T16:56:13+09:00 |
| price_cache\208860.parquet | n=2,240 bytes | 2026-06-03T16:36:06+09:00 |
| price_cache\210120.parquet | n=2,240 bytes | 2026-06-03T16:57:35+09:00 |
| price_cache\210540.parquet | n=3,040 bytes | 2026-09-03T21:30:41+09:00 |
| price_cache\211270.parquet | n=2,186 bytes | 2026-06-03T16:58:11+09:00 |
| price_cache\213500.parquet | n=2,600 bytes | 2026-07-11T13:27:12+09:00 |
| price_cache\214180.parquet | n=2,246 bytes | 2026-06-03T16:56:27+09:00 |
| price_cache\214260.parquet | n=2,244 bytes | 2026-06-03T16:56:10+09:00 |
| price_cache\214270.parquet | n=2,240 bytes | 2026-06-03T16:57:23+09:00 |
| price_cache\214390.parquet | n=3,010 bytes | 2026-09-03T21:29:41+09:00 |
| price_cache\214680.parquet | n=2,903 bytes | 2026-09-03T21:30:11+09:00 |
| price_cache\215100.parquet | n=2,245 bytes | 2026-06-03T16:57:58+09:00 |
| price_cache\215360.parquet | n=2,242 bytes | 2026-06-03T16:56:33+09:00 |
| price_cache\215480.parquet | n=2,128 bytes | 2026-06-03T16:57:52+09:00 |
| price_cache\215600.parquet | n=2,194 bytes | 2026-06-03T16:57:11+09:00 |
| price_cache\215790.parquet | n=2,142 bytes | 2026-06-03T16:56:43+09:00 |
| price_cache\217270.parquet | n=2,241 bytes | 2026-06-03T16:57:02+09:00 |
| price_cache\217330.parquet | n=2,243 bytes | 2026-06-03T16:56:44+09:00 |
| price_cache\217730.parquet | n=2,241 bytes | 2026-06-03T16:56:50+09:00 |
| price_cache\217820.parquet | n=2,243 bytes | 2026-06-03T16:57:32+09:00 |
| price_cache\220100.parquet | n=2,199 bytes | 2026-06-03T16:36:17+09:00 |
| price_cache\220180.parquet | n=2,236 bytes | 2026-06-03T16:56:28+09:00 |
| price_cache\221840.parquet | n=2,240 bytes | 2026-06-03T16:57:27+09:00 |
| price_cache\221980.parquet | n=2,231 bytes | 2026-06-03T16:57:51+09:00 |
| price_cache\222420.parquet | n=2,240 bytes | 2026-06-03T16:56:50+09:00 |
| price_cache\223250.parquet | n=2,202 bytes | 2026-06-03T16:56:54+09:00 |
| price_cache\224110.parquet | n=2,232 bytes | 2026-06-03T16:57:59+09:00 |
| price_cache\225190.parquet | n=3,116 bytes | 2026-09-03T21:27:44+09:00 |
| price_cache\225220.parquet | n=3,058 bytes | 2026-09-03T21:29:44+09:00 |
| price_cache\225530.parquet | n=2,993 bytes | 2026-08-26T20:21:32+09:00 |
| price_cache\226320.parquet | n=2,194 bytes | 2026-06-03T16:55:03+09:00 |
| price_cache\226330.parquet | n=2,237 bytes | 2026-06-03T16:57:15+09:00 |
| price_cache\226590.parquet | n=2,250 bytes | 2026-06-03T16:56:19+09:00 |
| price_cache\226950.parquet | n=2,129 bytes | 2026-06-03T16:58:06+09:00 |
| price_cache\227840.parquet | n=2,986 bytes | 2026-09-03T21:31:17+09:00 |
| price_cache\228670.parquet | n=2,246 bytes | 2026-06-03T16:57:39+09:00 |
| price_cache\234030.parquet | n=2,244 bytes | 2026-06-03T16:57:09+09:00 |
| price_cache\234300.parquet | n=2,241 bytes | 2026-06-03T16:57:10+09:00 |
| price_cache\234690.parquet | n=2,657 bytes | 2026-07-20T20:35:41+09:00 |
| price_cache\236810.parquet | n=3,096 bytes | 2026-09-03T21:29:37+09:00 |
| price_cache\237880.parquet | n=3,099 bytes | 2026-09-03T21:28:07+09:00 |
| price_cache\238200.parquet | n=2,134 bytes | 2026-06-03T16:58:14+09:00 |
| price_cache\239340.parquet | n=2,236 bytes | 2026-06-03T16:48:52+09:00 |
| price_cache\239610.parquet | n=3,001 bytes | 2026-09-03T21:28:23+09:00 |
| price_cache\239890.parquet | n=2,678 bytes | 2026-07-22T20:48:25+09:00 |
| price_cache\240600.parquet | n=2,242 bytes | 2026-06-03T16:56:09+09:00 |
| price_cache\241520.parquet | n=2,242 bytes | 2026-06-03T16:56:56+09:00 |
| price_cache\241790.parquet | n=2,201 bytes | 2026-06-03T16:57:38+09:00 |
| price_cache\241840.parquet | n=2,243 bytes | 2026-06-03T16:56:57+09:00 |
| price_cache\246690.parquet | n=2,241 bytes | 2026-06-03T16:45:22+09:00 |
| price_cache\247660.parquet | n=2,864 bytes | 2026-09-03T21:29:29+09:00 |
| price_cache\248170.parquet | n=3,018 bytes | 2026-09-03T21:29:54+09:00 |
| price_cache\250000.parquet | n=2,196 bytes | 2026-06-03T16:57:56+09:00 |
| price_cache\250060.parquet | n=2,725 bytes | 2026-07-28T20:31:25+09:00 |
| price_cache\251630.parquet | n=2,202 bytes | 2026-06-03T16:57:52+09:00 |
| price_cache\251970.parquet | n=2,248 bytes | 2026-06-03T16:56:25+09:00 |
| price_cache\253590.parquet | n=2,203 bytes | 2026-06-03T16:57:41+09:00 |
| price_cache\253840.parquet | n=2,192 bytes | 2026-06-03T16:57:30+09:00 |
| price_cache\254120.parquet | n=2,241 bytes | 2026-06-03T16:57:41+09:00 |
| price_cache\254490.parquet | n=2,193 bytes | 2026-06-03T16:58:02+09:00 |
| price_cache\255220.parquet | n=2,240 bytes | 2026-06-03T16:57:54+09:00 |
| price_cache\256150.parquet | n=2,231 bytes | 2026-06-03T16:57:24+09:00 |
| price_cache\256840.parquet | n=2,241 bytes | 2026-06-03T16:56:47+09:00 |
| price_cache\256940.parquet | n=2,242 bytes | 2026-06-03T16:58:17+09:00 |
| price_cache\257370.parquet | n=2,238 bytes | 2026-06-03T16:57:22+09:00 |
| price_cache\257720.parquet | n=2,249 bytes | 2026-06-03T16:57:04+09:00 |
| price_cache\258610.parquet | n=2,238 bytes | 2026-06-03T16:57:20+09:00 |
| price_cache\260660.parquet | n=2,241 bytes | 2026-06-03T16:57:02+09:00 |
| price_cache\260970.parquet | n=2,801 bytes | 2026-09-03T21:30:52+09:00 |
| price_cache\261520.parquet | n=2,245 bytes | 2026-06-03T16:57:05+09:00 |
| price_cache\262260.parquet | n=2,202 bytes | 2026-06-03T16:57:05+09:00 |
| price_cache\263020.parquet | n=2,199 bytes | 2026-06-03T16:56:02+09:00 |
| price_cache\263690.parquet | n=2,199 bytes | 2026-06-03T16:57:38+09:00 |
| price_cache\263700.parquet | n=2,240 bytes | 2026-06-03T16:57:25+09:00 |
| price_cache\263770.parquet | n=3,079 bytes | 2026-09-03T21:29:11+09:00 |
| price_cache\263800.parquet | n=2,237 bytes | 2026-06-03T16:37:02+09:00 |
| price_cache\263810.parquet | n=2,240 bytes | 2026-06-03T16:58:12+09:00 |
| price_cache\263860.parquet | n=2,747 bytes | 2026-09-03T21:29:42+09:00 |
| price_cache\264450.parquet | n=2,988 bytes | 2026-09-03T21:29:02+09:00 |
| price_cache\264660.parquet | n=2,248 bytes | 2026-06-03T16:57:43+09:00 |
| price_cache\264900.parquet | n=2,228 bytes | 2026-06-03T16:55:36+09:00 |
| price_cache\267290.parquet | n=3,001 bytes | 2026-09-03T21:29:15+09:00 |
| price_cache\267790.parquet | n=2,240 bytes | 2026-06-03T16:56:58+09:00 |
| price_cache\268280.parquet | n=3,030 bytes | 2026-08-26T20:23:12+09:00 |
| price_cache\270660.parquet | n=3,104 bytes | 2026-09-01T21:24:25+09:00 |
| price_cache\271830.parquet | n=2,240 bytes | 2026-06-03T16:44:17+09:00 |
| price_cache\271940.parquet | n=3,100 bytes | 2026-09-03T21:29:34+09:00 |
| price_cache\271980.parquet | n=2,241 bytes | 2026-06-03T16:55:26+09:00 |
| price_cache\272450.parquet | n=2,195 bytes | 2026-06-03T16:55:30+09:00 |
| price_cache\273060.parquet | n=2,185 bytes | 2026-06-03T16:58:03+09:00 |
| price_cache\273640.parquet | n=2,248 bytes | 2026-06-03T16:56:56+09:00 |
| price_cache\274400.parquet | n=2,966 bytes | 2026-09-03T21:29:02+09:00 |
| price_cache\275630.parquet | n=2,196 bytes | 2026-06-03T16:57:43+09:00 |
| price_cache\277810.parquet | n=2,210 bytes | 2026-06-15T20:25:11+09:00 |
| price_cache\279600.parquet | n=2,241 bytes | 2026-06-03T16:58:12+09:00 |
| price_cache\282330.parquet | n=2,314 bytes | 2026-06-15T20:25:12+09:00 |
| price_cache\282720.parquet | n=3,122 bytes | 2026-09-03T21:29:01+09:00 |
| price_cache\284740.parquet | n=2,198 bytes | 2026-06-03T16:55:40+09:00 |
| price_cache\285130.parquet | n=2,696 bytes | 2026-07-22T20:49:16+09:00 |
| price_cache\285490.parquet | n=2,248 bytes | 2026-06-03T16:56:49+09:00 |
| price_cache\285800.parquet | n=3,050 bytes | 2026-09-03T21:28:00+09:00 |
| price_cache\286750.parquet | n=2,196 bytes | 2026-06-03T16:37:05+09:00 |
| price_cache\288620.parquet | n=2,190 bytes | 2026-06-03T16:58:07+09:00 |
| price_cache\288980.parquet | n=2,240 bytes | 2026-06-03T16:58:08+09:00 |
| price_cache\289010.parquet | n=3,000 bytes | 2026-09-03T21:28:19+09:00 |
| price_cache\289080.parquet | n=2,239 bytes | 2026-06-03T16:57:47+09:00 |
| price_cache\289930.parquet | n=2,687 bytes | 2026-07-20T20:36:19+09:00 |
| price_cache\290090.parquet | n=2,228 bytes | 2026-06-03T16:57:04+09:00 |
| price_cache\290270.parquet | n=2,237 bytes | 2026-06-03T16:57:24+09:00 |
| price_cache\291650.parquet | n=2,711 bytes | 2026-07-29T20:39:11+09:00 |
| price_cache\291810.parquet | n=2,784 bytes | 2026-07-31T20:36:06+09:00 |
| price_cache\293490.parquet | n=2,358 bytes | 2026-06-15T20:25:11+09:00 |
| price_cache\293580.parquet | n=2,241 bytes | 2026-06-03T16:57:21+09:00 |
| price_cache\293780.parquet | n=2,244 bytes | 2026-06-03T16:56:59+09:00 |
| price_cache\294570.parquet | n=3,157 bytes | 2026-09-04T21:25:37+09:00 |
| price_cache\294630.parquet | n=2,242 bytes | 2026-06-03T16:56:44+09:00 |
| price_cache\294870.parquet | n=2,203 bytes | 2026-06-03T16:54:54+09:00 |
| price_cache\296640.parquet | n=2,241 bytes | 2026-06-03T16:58:16+09:00 |
| price_cache\297090.parquet | n=2,244 bytes | 2026-06-03T16:56:21+09:00 |
| price_cache\297570.parquet | n=2,241 bytes | 2026-06-03T16:56:12+09:00 |
| price_cache\297890.parquet | n=2,199 bytes | 2026-06-03T16:57:36+09:00 |
| price_cache\298540.parquet | n=2,238 bytes | 2026-06-03T16:56:42+09:00 |
| price_cache\299170.parquet | n=2,241 bytes | 2026-06-03T16:56:12+09:00 |
| price_cache\302440.parquet | n=2,200 bytes | 2026-06-03T16:34:52+09:00 |
| price_cache\303530.parquet | n=2,243 bytes | 2026-06-03T16:56:49+09:00 |
| price_cache\304360.parquet | n=2,143 bytes | 2026-06-03T16:58:15+09:00 |
| price_cache\306200.parquet | n=2,206 bytes | 2026-06-03T16:55:17+09:00 |
| price_cache\307280.parquet | n=2,185 bytes | 2026-06-03T16:56:21+09:00 |
| price_cache\307930.parquet | n=2,197 bytes | 2026-06-03T16:49:51+09:00 |
| price_cache\310210.parquet | n=2,143 bytes | 2026-06-03T16:57:46+09:00 |
| price_cache\310870.parquet | n=2,127 bytes | 2026-06-03T16:58:05+09:00 |
| price_cache\312610.parquet | n=2,240 bytes | 2026-06-03T16:36:09+09:00 |
| price_cache\314130.parquet | n=2,241 bytes | 2026-06-03T16:57:00+09:00 |
| price_cache\314140.parquet | n=2,237 bytes | 2026-06-03T16:56:49+09:00 |
| price_cache\317120.parquet | n=2,198 bytes | 2026-06-03T16:57:56+09:00 |
| price_cache\317330.parquet | n=2,206 bytes | 2026-06-03T16:57:21+09:00 |
| price_cache\317400.parquet | n=2,793 bytes | 2026-07-31T20:39:38+09:00 |
| price_cache\317530.parquet | n=2,231 bytes | 2026-06-03T16:58:00+09:00 |
| price_cache\317690.parquet | n=2,241 bytes | 2026-06-03T16:57:24+09:00 |
| price_cache\317770.parquet | n=2,199 bytes | 2026-06-03T16:58:06+09:00 |
| price_cache\317850.parquet | n=2,243 bytes | 2026-06-03T16:56:29+09:00 |
| price_cache\318020.parquet | n=2,238 bytes | 2026-06-03T16:57:04+09:00 |
| price_cache\318060.parquet | n=3,115 bytes | 2026-09-03T21:28:52+09:00 |
| price_cache\318160.parquet | n=2,243 bytes | 2026-06-03T16:56:51+09:00 |
| price_cache\318410.parquet | n=2,229 bytes | 2026-06-03T16:56:55+09:00 |
| price_cache\321260.parquet | n=2,143 bytes | 2026-06-03T16:50:06+09:00 |
| price_cache\321550.parquet | n=2,246 bytes | 2026-06-03T16:56:15+09:00 |
| price_cache\322180.parquet | n=3,032 bytes | 2026-09-03T21:30:11+09:00 |
| price_cache\322510.parquet | n=2,236 bytes | 2026-06-03T16:57:13+09:00 |
| price_cache\323990.parquet | n=2,243 bytes | 2026-06-03T16:57:05+09:00 |
| price_cache\330730.parquet | n=2,142 bytes | 2026-06-03T16:49:48+09:00 |
| price_cache\331380.parquet | n=2,241 bytes | 2026-06-03T16:25:58+09:00 |
| price_cache\332290.parquet | n=2,236 bytes | 2026-06-03T16:36:14+09:00 |
| price_cache\332370.parquet | n=2,181 bytes | 2026-06-03T16:46:18+09:00 |
| price_cache\335870.parquet | n=2,237 bytes | 2026-06-03T16:56:33+09:00 |
| price_cache\336370.parquet | n=2,247 bytes | 2026-06-03T16:41:47+09:00 |
| price_cache\336570.parquet | n=2,142 bytes | 2026-06-03T16:50:15+09:00 |
| price_cache\336680.parquet | n=2,237 bytes | 2026-06-03T16:56:48+09:00 |
| price_cache\338840.parquet | n=2,244 bytes | 2026-06-03T16:56:34+09:00 |
| price_cache\339770.parquet | n=2,227 bytes | 2026-06-03T16:55:40+09:00 |
| price_cache\340360.parquet | n=2,865 bytes | 2026-09-03T21:29:20+09:00 |
| price_cache\340440.parquet | n=3,105 bytes | 2026-09-03T21:28:20+09:00 |
| price_cache\340450.parquet | n=3,088 bytes | 2026-09-03T21:27:48+09:00 |
| price_cache\340810.parquet | n=2,190 bytes | 2026-06-03T16:58:14+09:00 |
| price_cache\344820.parquet | n=2,238 bytes | 2026-06-03T16:55:44+09:00 |
| price_cache\344860.parquet | n=2,196 bytes | 2026-06-03T16:57:46+09:00 |
| price_cache\347770.parquet | n=3,093 bytes | 2026-09-03T21:27:42+09:00 |
| price_cache\347860.parquet | n=2,241 bytes | 2026-06-03T16:56:53+09:00 |
| price_cache\347890.parquet | n=2,232 bytes | 2026-06-03T16:58:12+09:00 |
| price_cache\348030.parquet | n=2,236 bytes | 2026-06-03T16:33:11+09:00 |
| price_cache\348210.parquet | n=2,129 bytes | 2026-06-03T16:58:11+09:00 |
| price_cache\351320.parquet | n=2,192 bytes | 2026-06-03T16:58:06+09:00 |
| price_cache\351330.parquet | n=2,247 bytes | 2026-06-03T16:57:47+09:00 |
| price_cache\351870.parquet | n=2,242 bytes | 2026-06-03T16:56:55+09:00 |
| price_cache\352090.parquet | n=2,138 bytes | 2026-06-03T16:57:57+09:00 |
| price_cache\352480.parquet | n=2,247 bytes | 2026-06-03T16:56:46+09:00 |
| price_cache\352700.parquet | n=2,240 bytes | 2026-06-03T16:56:59+09:00 |
| price_cache\352940.parquet | n=2,190 bytes | 2026-06-03T16:57:44+09:00 |
| price_cache\353590.parquet | n=2,237 bytes | 2026-06-03T16:57:59+09:00 |
| price_cache\353810.parquet | n=2,243 bytes | 2026-06-03T16:56:26+09:00 |
| price_cache\355690.parquet | n=2,237 bytes | 2026-06-03T16:56:43+09:00 |
| price_cache\356890.parquet | n=2,237 bytes | 2026-06-03T16:56:15+09:00 |
| price_cache\357230.parquet | n=2,187 bytes | 2026-06-03T16:57:42+09:00 |
| price_cache\361390.parquet | n=2,242 bytes | 2026-06-03T16:56:39+09:00 |
| price_cache\361570.parquet | n=2,236 bytes | 2026-06-03T16:58:14+09:00 |
| price_cache\361610.parquet | n=2,631 bytes | 2026-07-11T13:27:20+09:00 |
| price_cache\361670.parquet | n=2,994 bytes | 2026-09-03T21:28:42+09:00 |
| price_cache\362320.parquet | n=2,239 bytes | 2026-06-03T16:57:26+09:00 |
| price_cache\363260.parquet | n=2,714 bytes | 2026-07-23T20:51:18+09:00 |
| price_cache\363280.parquet | n=2,595 bytes | 2026-07-11T13:27:33+09:00 |
| price_cache\365330.parquet | n=2,242 bytes | 2026-06-03T16:57:19+09:00 |
| price_cache\366030.parquet | n=2,230 bytes | 2026-06-03T16:57:54+09:00 |
| price_cache\367000.parquet | n=2,232 bytes | 2026-06-03T16:56:19+09:00 |
| price_cache\372800.parquet | n=2,644 bytes | 2026-07-21T20:48:10+09:00 |
| price_cache\372910.parquet | n=2,711 bytes | 2026-07-23T20:52:51+09:00 |
| price_cache\373220.parquet | n=2,618 bytes | 2026-07-11T13:27:17+09:00 |
| price_cache\375500.parquet | n=2,616 bytes | 2026-07-11T13:27:21+09:00 |
| price_cache\376270.parquet | n=2,205 bytes | 2026-06-03T16:57:50+09:00 |
| price_cache\376290.parquet | n=2,236 bytes | 2026-06-03T16:57:31+09:00 |
| price_cache\376930.parquet | n=2,236 bytes | 2026-06-03T16:35:38+09:00 |
| price_cache\377220.parquet | n=2,241 bytes | 2026-06-03T16:28:58+09:00 |
| price_cache\377330.parquet | n=2,242 bytes | 2026-06-03T16:58:14+09:00 |
| price_cache\377450.parquet | n=3,112 bytes | 2026-09-03T21:27:42+09:00 |
| price_cache\377480.parquet | n=2,247 bytes | 2026-06-03T16:58:00+09:00 |
| price_cache\377740.parquet | n=2,125 bytes | 2026-06-03T16:55:28+09:00 |
| price_cache\378340.parquet | n=2,246 bytes | 2026-06-03T16:56:54+09:00 |
| price_cache\378800.parquet | n=2,241 bytes | 2026-06-03T16:57:21+09:00 |
| price_cache\380550.parquet | n=2,247 bytes | 2026-06-03T16:57:12+09:00 |
| price_cache\382150.parquet | n=2,244 bytes | 2026-06-03T16:57:11+09:00 |
| price_cache\382840.parquet | n=2,245 bytes | 2026-06-03T16:58:06+09:00 |
| price_cache\383800.parquet | n=2,146 bytes | 2026-06-03T16:47:43+09:00 |
| price_cache\384470.parquet | n=2,199 bytes | 2026-06-03T16:57:45+09:00 |
| price_cache\388720.parquet | n=2,206 bytes | 2026-06-03T16:46:01+09:00 |
| price_cache\388790.parquet | n=2,243 bytes | 2026-06-03T16:57:53+09:00 |
| price_cache\388870.parquet | n=2,236 bytes | 2026-06-03T16:56:23+09:00 |
| price_cache\389140.parquet | n=2,239 bytes | 2026-06-03T16:57:30+09:00 |
| price_cache\389500.parquet | n=2,129 bytes | 2026-06-03T16:57:52+09:00 |
| price_cache\396300.parquet | n=2,201 bytes | 2026-06-03T16:45:57+09:00 |
| price_cache\396470.parquet | n=2,200 bytes | 2026-06-03T16:57:21+09:00 |
| price_cache\397810.parquet | n=2,238 bytes | 2026-06-03T16:57:09+09:00 |
| price_cache\402030.parquet | n=2,242 bytes | 2026-06-03T16:49:47+09:00 |
| price_cache\403850.parquet | n=2,238 bytes | 2026-06-03T16:56:08+09:00 |
| price_cache\403870.parquet | n=2,193 bytes | 2026-06-03T16:58:06+09:00 |
| price_cache\405100.parquet | n=2,190 bytes | 2026-06-03T16:57:38+09:00 |
| price_cache\405920.parquet | n=2,990 bytes | 2026-09-03T21:30:08+09:00 |
| price_cache\407400.parquet | n=2,244 bytes | 2026-06-03T16:56:25+09:00 |
| price_cache\416180.parquet | n=2,248 bytes | 2026-06-03T16:58:00+09:00 |
| price_cache\417500.parquet | n=3,034 bytes | 2026-09-02T21:27:03+09:00 |
| price_cache\417790.parquet | n=2,234 bytes | 2026-06-03T16:57:10+09:00 |
| price_cache\417970.parquet | n=2,874 bytes | 2026-09-03T21:30:20+09:00 |
| price_cache\418420.parquet | n=2,187 bytes | 2026-06-03T16:58:02+09:00 |
| price_cache\418550.parquet | n=2,718 bytes | 2026-07-23T20:50:28+09:00 |
| price_cache\418620.parquet | n=2,198 bytes | 2026-06-03T16:57:54+09:00 |
| price_cache\419050.parquet | n=2,238 bytes | 2026-06-03T16:57:52+09:00 |
| price_cache\424870.parquet | n=2,240 bytes | 2026-06-03T16:58:12+09:00 |
| price_cache\424960.parquet | n=2,200 bytes | 2026-06-03T16:56:20+09:00 |
| price_cache\424980.parquet | n=2,202 bytes | 2026-06-03T16:56:20+09:00 |
| price_cache\425040.parquet | n=2,195 bytes | 2026-06-03T16:50:05+09:00 |
| price_cache\429270.parquet | n=2,191 bytes | 2026-06-03T16:57:25+09:00 |
| price_cache\430690.parquet | n=2,238 bytes | 2026-06-03T16:57:29+09:00 |
| price_cache\431190.parquet | n=3,086 bytes | 2026-09-03T21:28:32+09:00 |
| price_cache\432430.parquet | n=2,659 bytes | 2026-07-20T20:35:54+09:00 |
| price_cache\432470.parquet | n=3,119 bytes | 2026-09-03T21:28:12+09:00 |
| price_cache\432720.parquet | n=2,249 bytes | 2026-06-03T16:57:19+09:00 |
| price_cache\432980.parquet | n=2,238 bytes | 2026-06-03T16:57:14+09:00 |
| price_cache\434480.parquet | n=2,243 bytes | 2026-06-03T16:57:39+09:00 |
| price_cache\435570.parquet | n=2,238 bytes | 2026-06-03T16:56:48+09:00 |
| price_cache\438700.parquet | n=2,241 bytes | 2026-06-03T16:56:53+09:00 |
| price_cache\439090.parquet | n=2,712 bytes | 2026-07-29T20:39:58+09:00 |
| price_cache\441270.parquet | n=3,058 bytes | 2026-09-03T21:27:55+09:00 |
| price_cache\443670.parquet | n=2,244 bytes | 2026-06-03T16:56:19+09:00 |
| price_cache\444530.parquet | n=2,190 bytes | 2026-06-03T16:58:02+09:00 |
| price_cache\445680.parquet | n=2,245 bytes | 2026-06-03T16:49:32+09:00 |
| price_cache\446070.parquet | n=2,231 bytes | 2026-06-03T16:54:54+09:00 |
| price_cache\446540.parquet | n=2,740 bytes | 2026-09-04T21:25:31+09:00 |
| price_cache\446840.parquet | n=2,685 bytes | 2026-07-28T20:31:25+09:00 |
| price_cache\448280.parquet | n=2,196 bytes | 2026-06-03T16:58:17+09:00 |
| price_cache\450330.parquet | n=2,241 bytes | 2026-06-03T16:57:23+09:00 |
| price_cache\450950.parquet | n=2,755 bytes | 2026-07-28T20:31:20+09:00 |
| price_cache\452190.parquet | n=2,330 bytes | 2026-07-03T21:31:46+09:00 |
| price_cache\452200.parquet | n=2,141 bytes | 2026-06-03T16:57:35+09:00 |
| price_cache\452260.parquet | n=2,127 bytes | 2026-06-03T16:55:40+09:00 |
| price_cache\452280.parquet | n=2,856 bytes | 2026-09-03T21:30:43+09:00 |
| price_cache\453340.parquet | n=2,190 bytes | 2026-06-03T16:47:04+09:00 |
| price_cache\453450.parquet | n=2,246 bytes | 2026-06-03T16:57:29+09:00 |
| price_cache\455900.parquet | n=2,206 bytes | 2026-06-03T16:46:05+09:00 |
| price_cache\456070.parquet | n=2,769 bytes | 2026-07-28T20:30:51+09:00 |
| price_cache\457190.parquet | n=2,248 bytes | 2026-06-03T16:55:18+09:00 |
| price_cache\457550.parquet | n=2,244 bytes | 2026-06-03T16:56:37+09:00 |
| price_cache\459100.parquet | n=2,191 bytes | 2026-06-03T16:57:34+09:00 |
| price_cache\459510.parquet | n=2,196 bytes | 2026-06-03T16:58:07+09:00 |
| price_cache\459550.parquet | n=2,718 bytes | 2026-07-23T20:51:43+09:00 |
| price_cache\460470.parquet | n=2,189 bytes | 2026-06-03T16:58:15+09:00 |
| price_cache\460850.parquet | n=3,029 bytes | 2026-09-03T21:31:15+09:00 |
| price_cache\460870.parquet | n=2,227 bytes | 2026-06-03T16:57:31+09:00 |
| price_cache\462310.parquet | n=2,243 bytes | 2026-06-03T16:57:19+09:00 |
| price_cache\462860.parquet | n=3,100 bytes | 2026-09-04T21:25:31+09:00 |
| price_cache\462870.parquet | n=2,687 bytes | 2026-07-23T20:53:01+09:00 |
| price_cache\462980.parquet | n=3,062 bytes | 2026-08-31T21:22:40+09:00 |
| price_cache\463480.parquet | n=2,246 bytes | 2026-06-03T16:57:40+09:00 |
| price_cache\464080.parquet | n=2,246 bytes | 2026-06-03T16:57:48+09:00 |
| price_cache\464280.parquet | n=2,197 bytes | 2026-06-03T16:56:47+09:00 |
| price_cache\464490.parquet | n=2,757 bytes | 2026-07-28T20:30:40+09:00 |
| price_cache\464580.parquet | n=2,682 bytes | 2026-07-22T20:47:55+09:00 |
| price_cache\465480.parquet | n=2,188 bytes | 2026-06-03T16:57:44+09:00 |
| price_cache\468530.parquet | n=2,250 bytes | 2026-06-03T16:56:55+09:00 |
| price_cache\469750.parquet | n=2,192 bytes | 2026-06-03T16:49:17+09:00 |
| price_cache\471820.parquet | n=2,219 bytes | 2026-06-03T16:58:01+09:00 |
| price_cache\473980.parquet | n=2,770 bytes | 2026-07-28T20:31:13+09:00 |
| price_cache\474610.parquet | n=3,060 bytes | 2026-09-03T21:27:42+09:00 |
| price_cache\474650.parquet | n=2,772 bytes | 2026-07-28T20:31:17+09:00 |
| price_cache\475400.parquet | n=2,194 bytes | 2026-06-03T16:58:11+09:00 |
| price_cache\475460.parquet | n=3,039 bytes | 2026-09-03T21:30:20+09:00 |
| price_cache\475580.parquet | n=2,240 bytes | 2026-06-03T16:57:43+09:00 |
| price_cache\475660.parquet | n=2,242 bytes | 2026-06-03T16:57:35+09:00 |
| price_cache\476040.parquet | n=2,248 bytes | 2026-06-03T16:57:05+09:00 |
| price_cache\476830.parquet | n=2,253 bytes | 2026-06-03T16:57:09+09:00 |
| price_cache\478340.parquet | n=2,248 bytes | 2026-06-03T16:57:49+09:00 |
| price_cache\478560.parquet | n=2,241 bytes | 2026-06-03T16:57:13+09:00 |
| price_cache\480370.parquet | n=2,237 bytes | 2026-06-03T16:54:55+09:00 |
| price_cache\484590.parquet | n=2,692 bytes | 2026-07-21T20:47:24+09:00 |
| price_cache\486990.parquet | n=2,243 bytes | 2026-06-03T16:32:41+09:00 |
| price_cache\487570.parquet | n=2,250 bytes | 2026-06-03T16:54:45+09:00 |
| price_cache\488280.parquet | n=2,205 bytes | 2026-06-03T16:58:00+09:00 |
| price_cache\488900.parquet | n=2,248 bytes | 2026-06-03T16:57:22+09:00 |
| price_cache\489460.parquet | n=2,232 bytes | 2026-06-03T16:57:33+09:00 |
| price_cache\494120.parquet | n=3,142 bytes | 2026-09-03T21:27:57+09:00 |
| price_cache\900290.parquet | n=2,237 bytes | 2026-06-03T16:36:49+09:00 |
| price_cache\950140.parquet | n=2,969 bytes | 2026-09-03T21:29:46+09:00 |
| price_cache\950200.parquet | n=2,238 bytes | 2026-06-03T16:56:54+09:00 |
| price_cache\950250.parquet | n=2,244 bytes | 2026-06-03T16:56:48+09:00 |

## 2·3·5 추가. 본 표/보충표 갈래와 원자료 시각(핵심)

물리적인 market/source 열만으로 못 잡는 경우라 현재 시세 표의 종목 집합을 갈래로 추가했다. 최근 n=60일도 이 현재 집합으로 비교했으므로 과거 상장·편입 변화의 영향을 포함한다. 이 집계는 성과 검증이 아니다.

| 표 | 현재 종목 갈래 | 대상 | 종목별 마지막 날짜 분포 |
|---|---|---|---|
| daily_flows | 본 표 활발 | n=2518 | 20261008: n=2518 (뒤처짐 0) |
| daily_flows | 본 표 정지 | n=111 | 20261007: n=111 (뒤처짐 1) |
| daily_flows | 보충표 전체 | n=136 | 20260910: n=1 (뒤처짐 17); 20260911: n=130 (뒤처짐 16); 자료 없음: n=5 (뒤처짐 확인 못 함) |
| daily_flows | 보충표 활발 | n=136 | 20260910: n=1 (뒤처짐 17); 20260911: n=130 (뒤처짐 16); 자료 없음: n=5 (뒤처짐 확인 못 함) |
| short_flows | 본 표 활발 | n=2518 | 20261007: n=2 (뒤처짐 1); 20261008: n=2516 (뒤처짐 0) |
| short_flows | 본 표 정지 | n=111 | 20260629: n=1 (뒤처짐 68); 20260630: n=1 (뒤처짐 67); 20260720: n=1 (뒤처짐 54); 20260728: n=1 (뒤처짐 48); 20260731: n=1 (뒤처짐 45); 20260814: n=1 (뒤처짐 35); 20260819: n=1 (뒤처짐 33); 20260903: n=1 (뒤처짐 22); 20260909: n=2 (뒤처짐 18); 20260911: n=1 (뒤처짐 16); 20260914: n=5 (뒤처짐 15); 20260916: n=3 (뒤처짐 13); 20260917: n=1 (뒤처짐 12); 20260918: n=1 (뒤처짐 11); 20260922: n=3 (뒤처짐 9); 20260928: n=3 (뒤처짐 7); 20260930: n=2 (뒤처짐 5); 20261001: n=3 (뒤처짐 4); 20261002: n=5 (뒤처짐 3); 20261007: n=5 (뒤처짐 1); 자료 없음: n=69 (뒤처짐 확인 못 함) |
| short_flows | 보충표 전체 | n=136 | 20260626: n=2 (뒤처짐 69); 20260629: n=58 (뒤처짐 68); 자료 없음: n=76 (뒤처짐 확인 못 함) |
| short_flows | 보충표 활발 | n=136 | 20260626: n=2 (뒤처짐 69); 20260629: n=58 (뒤처짐 68); 자료 없음: n=76 (뒤처짐 확인 못 함) |

| 표 | 갈래 | 기준일 종목 수 | 최근60일 0인 날 | 70% 미만 날 |
|---|---|---|---|---|
| daily_flows | 본 표 활발 | n=2518 | n=0일: 없음 | n=0일 |
| daily_flows | 본 표 정지 | n=0 | n=1일: 20261008 | n=1일 |
| daily_flows | 보충표 전체 | n=0 | n=29일: 20260710~20260729(n=13일), 20260914~20261008(n=16일) | n=14일 |
| daily_flows | 보충표 활발 | n=0 | n=29일: 20260710~20260729(n=13일), 20260914~20261008(n=16일) | n=14일 |
| short_flows | 본 표 활발 | n=2516 | n=0일: 없음 | n=0일 |
| short_flows | 본 표 정지 | n=0 | n=1일: 20261008 | n=13일 |
| short_flows | 보충표 전체 | n=0 | n=60일: 20260710~20261008(n=60일) | n=3일 |
| short_flows | 보충표 활발 | n=0 | n=60일: 20260710~20261008(n=60일) | n=3일 |

| 표 | 갈래 | 70% 미만 날짜 | 종목 수 | 직전20일 중앙값 |
|---|---|---|---|---|
| daily_flows | 본 표 정지 | 20261008 | n=0 | 111 |
| daily_flows | 보충표 전체 | 20260710 | n=0 | 60 |
| daily_flows | 보충표 전체 | 20260713 | n=0 | 59 |
| daily_flows | 보충표 전체 | 20260714 | n=0 | 29 |
| daily_flows | 보충표 전체 | 20260914 | n=0 | 131 |
| daily_flows | 보충표 전체 | 20260915 | n=0 | 131 |
| daily_flows | 보충표 전체 | 20260916 | n=0 | 131 |
| daily_flows | 보충표 전체 | 20260917 | n=0 | 131 |
| daily_flows | 보충표 전체 | 20260918 | n=0 | 131 |
| daily_flows | 보충표 전체 | 20260921 | n=0 | 131 |
| daily_flows | 보충표 전체 | 20260922 | n=0 | 131 |
| daily_flows | 보충표 전체 | 20260923 | n=0 | 131 |
| daily_flows | 보충표 전체 | 20260928 | n=0 | 131 |
| daily_flows | 보충표 전체 | 20260929 | n=0 | 130.5 |
| daily_flows | 보충표 전체 | 20260930 | n=0 | 65 |
| daily_flows | 보충표 활발 | 20260710 | n=0 | 60 |
| daily_flows | 보충표 활발 | 20260713 | n=0 | 59 |
| daily_flows | 보충표 활발 | 20260714 | n=0 | 29 |
| daily_flows | 보충표 활발 | 20260914 | n=0 | 131 |
| daily_flows | 보충표 활발 | 20260915 | n=0 | 131 |
| daily_flows | 보충표 활발 | 20260916 | n=0 | 131 |
| daily_flows | 보충표 활발 | 20260917 | n=0 | 131 |
| daily_flows | 보충표 활발 | 20260918 | n=0 | 131 |
| daily_flows | 보충표 활발 | 20260921 | n=0 | 131 |
| daily_flows | 보충표 활발 | 20260922 | n=0 | 131 |
| daily_flows | 보충표 활발 | 20260923 | n=0 | 131 |
| daily_flows | 보충표 활발 | 20260928 | n=0 | 131 |
| daily_flows | 보충표 활발 | 20260929 | n=0 | 130.5 |
| daily_flows | 보충표 활발 | 20260930 | n=0 | 65 |
| short_flows | 본 표 정지 | 20260917 | n=23 | 35 |
| short_flows | 본 표 정지 | 20260918 | n=22 | 34.5 |
| short_flows | 본 표 정지 | 20260921 | n=21 | 34 |
| short_flows | 본 표 정지 | 20260922 | n=21 | 34 |
| short_flows | 본 표 정지 | 20260923 | n=18 | 34 |
| short_flows | 본 표 정지 | 20260928 | n=18 | 33 |
| short_flows | 본 표 정지 | 20260929 | n=15 | 32 |
| short_flows | 본 표 정지 | 20260930 | n=15 | 31.5 |
| short_flows | 본 표 정지 | 20261001 | n=13 | 28.5 |
| short_flows | 본 표 정지 | 20261002 | n=10 | 26 |
| short_flows | 본 표 정지 | 20261006 | n=5 | 24.5 |
| short_flows | 본 표 정지 | 20261007 | n=5 | 22.5 |
| short_flows | 본 표 정지 | 20261008 | n=0 | 21.5 |
| short_flows | 보충표 전체 | 20260710 | n=0 | 60 |
| short_flows | 보충표 전체 | 20260713 | n=0 | 59 |
| short_flows | 보충표 전체 | 20260714 | n=0 | 29 |
| short_flows | 보충표 활발 | 20260710 | n=0 | 60 |
| short_flows | 보충표 활발 | 20260713 | n=0 | 59 |
| short_flows | 보충표 활발 | 20260714 | n=0 | 29 |

### 보충표 종목 전부의 마지막 날짜

| 표 | 종목 | 이름 | 시장 | 마지막 원자료일 | 뒤처짐 거래일 | 마지막 수신 시각 |
|---|---|---|---|---|---|---|
| daily_flows | 0001A0 | 덕양에너젠 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0004V0 | 엔비알모션 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0004Y0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0007C0 | 아크릴 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0007J0 | 인벤테라 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 00088K | 한화3우B | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 0008Z0 | 에스엔시스 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0009K0 | 에임드바이오 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 00104K | CJ4우(전환) | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 0010F0 | 보원케미칼 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0010S0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| daily_flows | 0010V0 | 제이피아이헬스케어 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0011A0 | 액스비스 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0011T0 | 채비 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0013V0 | 삼진식품 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0015G0 | 그린광학 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0015N0 | 아로마티카 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0015S0 | 페스카로 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0017J0 | 세미티에스 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 00279K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 0030R0 | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 003380 | 하림지주 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0035S0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| daily_flows | 0037T0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0039P0 | 매드업 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0041B0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0041J0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0041L0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0044K0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 00499K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 0054V0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 006730 | 서부T&D | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 00680K | 미래에셋증권2우B | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 0068Y0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0071M0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0072Z0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 00781K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 00806K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 0082N0 | 카나프테라퓨틱스 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0088D0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0088M0 | 메쥬 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0091W0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0093G0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 009520 | 포스코엠텍 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0096B0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0096D0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0097F0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0098T0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0099W0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0099X0 | 확인 못 함 | kosdaq | 20260910 | 17 | 20260912_1038 |
| daily_flows | 0101C0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0105P0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0115H0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0117P0 | 피스피스스튜디오 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0120G0 | 삼양바이오팜 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 0126Z0 | 삼성에피스홀딩스 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 0129K0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0130D0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0130H0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0131D0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0132G0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0134X0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 014620 | 성광벤드 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0155E0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0156T0 | 에이치엘지노믹스 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0161M0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| daily_flows | 0164H0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0165X0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0197V0 | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0200G0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| daily_flows | 0209J0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| daily_flows | 0218L0 | 네오뷰 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 0220W0 | 한화머시너리앤서비스홀딩스 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 0220WL | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 023160 | 태광 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 02826K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 033100 | 제룡전기 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 03473K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 03481K | 확인 못 함 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 035760 | CJ ENM | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 035900 | JYP Ent. | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 036830 | 솔브레인홀딩스 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 036930 | 주성엔지니어링 | kosdaq | 20260911 | 16 | 20260912_1027 |
| daily_flows | 038500 | 삼표시멘트 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 041510 | 에스엠 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 046890 | 서울반도체 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 052400 | 코나아이 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 056190 | SFA | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 058470 | 리노공업 | kosdaq | 20260911 | 16 | 20260912_1027 |
| daily_flows | 064760 | 티씨케이 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 067160 | SOOP | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 069080 | 웹젠 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 078340 | 컴투스 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 082920 | 비츠로셀 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 086450 | 동국제약 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 086520 | 에코프로 | kosdaq | 20260911 | 16 | 20260912_1027 |
| daily_flows | 095610 | 테스 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 096530 | 씨젠 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 101490 | 에스앤에스텍 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 122870 | 와이지엔터테인먼트 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 131970 | 두산테스나 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 137400 | 피엔티 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 140860 | 파크시스템스 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 141080 | 리가켐바이오 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 18064K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 195940 | HK이노엔 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 196170 | 알테오젠 | kosdaq | 20260911 | 16 | 20260912_1027 |
| daily_flows | 200130 | 콜마비앤에이치 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 214150 | 클래시스 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 214450 | 파마리서치 | kosdaq | 20260911 | 16 | 20260912_1027 |
| daily_flows | 222080 | SFA넥셀 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 222800 | 심텍 | kosdaq | 20260911 | 16 | 20260912_1027 |
| daily_flows | 226950 | 올릭스 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 237690 | 에스티팜 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 240810 | 원익IPS | kosdaq | 20260911 | 16 | 20260912_1027 |
| daily_flows | 241710 | 코스메카코리아 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 247540 | 에코프로비엠 | kosdaq | 20260911 | 16 | 20260912_1027 |
| daily_flows | 251970 | 펌텍코리아 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 253450 | 스튜디오드래곤 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 26490K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 272290 | 이녹스첨단소재 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 28513K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 293490 | 카카오게임즈 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 298380 | 에이비엘바이오 | kosdaq | 20260911 | 16 | 20260912_1027 |
| daily_flows | 33626K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 33626L | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 33637K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 33637L | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 35320K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 357780 | 솔브레인 | kosdaq | 20260911 | 16 | 20260912_1038 |
| daily_flows | 36328K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 37550K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 37550L | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 38380K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| daily_flows | 403870 | HPSP | kosdaq | 20260911 | 16 | 20260912_1027 |
| daily_flows | 45226K | 확인 못 함 | kospi | 20260911 | 16 | 20260912_1027 |
| short_flows | 0001A0 | 덕양에너젠 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 0004V0 | 엔비알모션 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 0004Y0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0007C0 | 아크릴 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0007J0 | 인벤테라 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 00088K | 한화3우B | kospi | 20260629 | 68 | 20260629_2303 |
| short_flows | 0008Z0 | 에스엔시스 | kosdaq | 20260626 | 69 | 20260627_1902 |
| short_flows | 0009K0 | 에임드바이오 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 00104K | CJ4우(전환) | kospi | 20260629 | 68 | 20260629_2303 |
| short_flows | 0010F0 | 보원케미칼 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 0010S0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0010V0 | 제이피아이헬스케어 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0011A0 | 액스비스 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0011T0 | 채비 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0013V0 | 삼진식품 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0015G0 | 그린광학 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 0015N0 | 아로마티카 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0015S0 | 페스카로 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0017J0 | 세미티에스 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 00279K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 0030R0 | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 003380 | 하림지주 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 0035S0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0037T0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0039P0 | 매드업 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0041B0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0041J0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0041L0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0044K0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 00499K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 0054V0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 006730 | 서부T&D | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 00680K | 미래에셋증권2우B | kospi | 20260629 | 68 | 20260629_2303 |
| short_flows | 0068Y0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0071M0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0072Z0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 00781K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 00806K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 0082N0 | 카나프테라퓨틱스 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 0088D0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0088M0 | 메쥬 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0091W0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0093G0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 009520 | 포스코엠텍 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 0096B0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0096D0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0097F0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0098T0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0099W0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0099X0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0101C0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0105P0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0115H0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0117P0 | 피스피스스튜디오 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0120G0 | 삼양바이오팜 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 0126Z0 | 삼성에피스홀딩스 | kospi | 20260629 | 68 | 20260629_2303 |
| short_flows | 0129K0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0130D0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0130H0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0131D0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0132G0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0134X0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 014620 | 성광벤드 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 0155E0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0156T0 | 에이치엘지노믹스 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0161M0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0164H0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0165X0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0197V0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0200G0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0209J0 | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0218L0 | 네오뷰 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 0220W0 | 한화머시너리앤서비스홀딩스 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 0220WL | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 023160 | 태광 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 02826K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 033100 | 제룡전기 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 03473K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 03481K | 확인 못 함 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 035760 | CJ ENM | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 035900 | JYP Ent. | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 036830 | 솔브레인홀딩스 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 036930 | 주성엔지니어링 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 038500 | 삼표시멘트 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 041510 | 에스엠 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 046890 | 서울반도체 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 052400 | 코나아이 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 056190 | SFA | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 058470 | 리노공업 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 064760 | 티씨케이 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 067160 | SOOP | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 069080 | 웹젠 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 078340 | 컴투스 | kosdaq | 없음 | 확인 못 함 | 없음 |
| short_flows | 082920 | 비츠로셀 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 086450 | 동국제약 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 086520 | 에코프로 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 095610 | 테스 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 096530 | 씨젠 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 101490 | 에스앤에스텍 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 122870 | 와이지엔터테인먼트 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 131970 | 두산테스나 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 137400 | 피엔티 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 140860 | 파크시스템스 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 141080 | 리가켐바이오 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 18064K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 195940 | HK이노엔 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 196170 | 알테오젠 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 200130 | 콜마비앤에이치 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 214150 | 클래시스 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 214450 | 파마리서치 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 222080 | SFA넥셀 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 222800 | 심텍 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 226950 | 올릭스 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 237690 | 에스티팜 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 240810 | 원익IPS | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 241710 | 코스메카코리아 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 247540 | 에코프로비엠 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 251970 | 펌텍코리아 | kosdaq | 20260626 | 69 | 20260627_1902 |
| short_flows | 253450 | 스튜디오드래곤 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 26490K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 272290 | 이녹스첨단소재 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 28513K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 293490 | 카카오게임즈 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 298380 | 에이비엘바이오 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 33626K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 33626L | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 33637K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 33637L | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 35320K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 357780 | 솔브레인 | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 36328K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 37550K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 37550L | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 38380K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |
| short_flows | 403870 | HPSP | kosdaq | 20260629 | 68 | 20260629_2303 |
| short_flows | 45226K | 확인 못 함 | kospi | 없음 | 확인 못 함 | 없음 |

### 현재 대형 유니버스에서 자료가 빠진 시총 상위 n=10개씩

| 표 | 종목 | 이름 | 시장 | 시총 억원 | 마지막 원자료일 | 지연 거래일 | 소속 |
|---|---|---|---|---|---|---|---|
| daily_flows | 196170 | 알테오젠 | kosdaq | 167520.59 | 20260911 | 16 | 보충표 |
| daily_flows | 086520 | 에코프로 | kosdaq | 123827.85 | 20260911 | 16 | 보충표 |
| daily_flows | 247540 | 에코프로비엠 | kosdaq | 123755.50 | 20260911 | 16 | 보충표 |
| daily_flows | 036930 | 주성엔지니어링 | kosdaq | 122477.75 | 20260911 | 16 | 보충표 |
| daily_flows | 0126Z0 | 삼성에피스홀딩스 | kospi | 85348.86 | 20260911 | 16 | 보충표 |
| daily_flows | 058470 | 리노공업 | kosdaq | 66914.00 | 20260911 | 16 | 보충표 |
| daily_flows | 240810 | 원익IPS | kosdaq | 65870.60 | 20260911 | 16 | 보충표 |
| daily_flows | 222800 | 심텍 | kosdaq | 65693.09 | 20260911 | 16 | 보충표 |
| daily_flows | 403870 | HPSP | kosdaq | 52672.00 | 20260911 | 16 | 보충표 |
| daily_flows | 064760 | 티씨케이 | kosdaq | 32755.69 | 20260911 | 16 | 보충표 |
| short_flows | 196170 | 알테오젠 | kosdaq | 167520.59 | 20260629 | 68 | 보충표 |
| short_flows | 086520 | 에코프로 | kosdaq | 123827.85 | 20260629 | 68 | 보충표 |
| short_flows | 247540 | 에코프로비엠 | kosdaq | 123755.50 | 20260629 | 68 | 보충표 |
| short_flows | 036930 | 주성엔지니어링 | kosdaq | 122477.75 | 20260629 | 68 | 보충표 |
| short_flows | 0126Z0 | 삼성에피스홀딩스 | kospi | 85348.86 | 20260629 | 68 | 보충표 |
| short_flows | 058470 | 리노공업 | kosdaq | 66914.00 | 20260629 | 68 | 보충표 |
| short_flows | 240810 | 원익IPS | kosdaq | 65870.60 | 20260629 | 68 | 보충표 |
| short_flows | 222800 | 심텍 | kosdaq | 65693.09 | 20260629 | 68 | 보충표 |
| short_flows | 403870 | HPSP | kosdaq | 52672.00 | 20260629 | 68 | 보충표 |
| short_flows | 064760 | 티씨케이 | kosdaq | 32755.69 | 20260629 | 68 | 보충표 |

### 수급·공매도 개별 열의 마지막 비NULL 원자료일

| 표 | 열 | 비NULL 마지막 날짜 | 지연 거래일 |
|---|---|---|---|
| daily_flows | close | 20261008 | 0 |
| daily_flows | person_net_qty | 20261008 | 0 |
| daily_flows | foreign_net_qty | 20261008 | 0 |
| daily_flows | inst_net_qty | 20261008 | 0 |
| daily_flows | person_net_val | 20261008 | 0 |
| daily_flows | foreign_net_val | 20261008 | 0 |
| daily_flows | inst_net_val | 20261008 | 0 |
| daily_flows | pension_net_qty | 20261008 | 0 |
| daily_flows | pension_net_val | 20261008 | 0 |
| daily_flows | trust_net_qty | 20261008 | 0 |
| daily_flows | trust_net_val | 20261008 | 0 |
| daily_flows | secfirm_net_qty | 20261008 | 0 |
| daily_flows | secfirm_net_val | 20261008 | 0 |
| daily_flows | prveq_net_qty | 20261008 | 0 |
| daily_flows | prveq_net_val | 20261008 | 0 |
| daily_flows | insu_net_qty | 20261008 | 0 |
| daily_flows | insu_net_val | 20261008 | 0 |
| daily_flows | bank_net_qty | 20261008 | 0 |
| daily_flows | bank_net_val | 20261008 | 0 |
| short_flows | short_qty | 20261008 | 0 |
| short_flows | short_vol_ratio | 20261008 | 0 |
| short_flows | short_val | 20261008 | 0 |
| short_flows | credit_bal_qty | 20261002 | 3 |
| short_flows | credit_bal_amt | 20261002 | 3 |
| short_flows | credit_bal_rate | 20261002 | 3 |
| short_flows | loan_bal_qty | 20261008 | 0 |
| short_flows | loan_bal_amt | 20261008 | 0 |
| short_flows | loan_chg | 20261008 | 0 |

### market_daily 시계열별 최근60거래일 구멍

| series | 빈 거래일 수 | 빈 날짜 |
|---|---|---|
| KOSDAQ | n=0 | 없음 |
| KOSPI | n=0 | 없음 |
| USDKRW | n=1 | 20260710 |

환율은 원자료 시장 달력이 다를 수 있다. 여기서는 요청한 국내 거래일 대비 구멍만 확인했으며 누락 원인은 확인 못 함.

### 최근10거래일 신용 열의 비NULL 수

| 날짜 | 전체 행 수 | 신용 수량 비NULL | 신용 금액 비NULL | 신용 비율 비NULL |
|---|---|---|---|---|
| 20260922 | n=2538 | n=2441 | n=2441 | n=2441 |
| 20260923 | n=2535 | n=2439 | n=2439 | n=2439 |
| 20260928 | n=2535 | n=2437 | n=2437 | n=2437 |
| 20260929 | n=2533 | n=2436 | n=2436 | n=2436 |
| 20260930 | n=2534 | n=2431 | n=2431 | n=2431 |
| 20261001 | n=2532 | n=2430 | n=2430 | n=2430 |
| 20261002 | n=2529 | n=2423 | n=2423 | n=2423 |
| 20261006 | n=2524 | n=0 | n=0 | n=0 |
| 20261007 | n=2523 | n=0 | n=0 | n=0 |
| 20261008 | n=2516 | n=0 | n=0 | n=0 |

신용 비율 마지막 비NULL은 20261002, 기준일보다 n=3거래일 뒤처진다. kis_flows.py:459의 최근 1~2거래일 결손 설명보다 길지만, wu_score.py:166에는 3일 적재 지연 허용 설명도 있다. 휴장 전후 제공자 실제 게시 일정·응답은 **확인 못 함**이므로 비정상 정지 확정 대신 의심으로 분류한다.

### 최신 입력에 실제 포함된 보충표 종목

| 입력 표 | 보충표 종목 행 | 그중 supply_fetched=True |
|---|---|---|
| stage1_oversold | n=73 | n=32 |
| stage3_final | n=20 | n=20 |

| stage3 종목 | 이름 | supply_fetched | 실제 수급 마지막 날짜 | 최근20일 유효 날짜 |
|---|---|---|---|---|
| 214450 | 파마리서치 | 1 | 20260911 | n=4/20 |
| 0015N0 | 아로마티카 | 1 | 20260911 | n=4/20 |
| 241710 | 코스메카코리아 | 1 | 20260911 | n=4/20 |
| 214150 | 클래시스 | 1 | 20260911 | n=4/20 |
| 0156T0 | 에이치엘지노믹스 | 1 | 20260911 | n=4/20 |
| 0008Z0 | 에스엔시스 | 1 | 20260911 | n=4/20 |
| 141080 | 리가켐바이오 | 1 | 20260911 | n=4/20 |
| 298380 | 에이비엘바이오 | 1 | 20260911 | n=4/20 |
| 041510 | 에스엠 | 1 | 20260911 | n=4/20 |
| 253450 | 스튜디오드래곤 | 1 | 20260911 | n=4/20 |
| 0015S0 | 페스카로 | 1 | 20260911 | n=4/20 |
| 014620 | 성광벤드 | 1 | 20260911 | n=4/20 |
| 122870 | 와이지엔터테인먼트 | 1 | 20260911 | n=4/20 |
| 0011A0 | 액스비스 | 1 | 20260911 | n=4/20 |
| 035760 | CJ ENM | 1 | 20260911 | n=4/20 |
| 0082N0 | 카나프테라퓨틱스 | 1 | 20260911 | n=4/20 |
| 0011T0 | 채비 | 1 | 20260911 | n=4/20 |
| 0039P0 | 매드업 | 1 | 20260911 | n=4/20 |
| 0007C0 | 아크릴 | 1 | 20260911 | n=4/20 |
| 023160 | 태광 | 1 | 20260911 | n=4/20 |

입력 포함·확보 플래그와 원자료 날짜만 확인했다. 점수·순위·수익·성과 변화는 계산하지 않았다.

### 최신 large_final의 원자료 run 분포

최신 run 20261008: 당일 원자료 n=159, 과거 원자료 n=264, 원자료 없음 n=77; 최대 지연 n=79거래일.

| stage3_src_run | 현재 행 수 | 지연 거래일 |
|---|---|---|
| 20261008 | n=159 | 0 |
| 20261007 | n=4 | 1 |
| 20261006 | n=11 | 2 |
| 20261002 | n=11 | 3 |
| 20261001 | n=6 | 4 |
| 20260930 | n=18 | 5 |
| 20260929 | n=13 | 6 |
| 20260928 | n=5 | 7 |
| 20260923 | n=12 | 8 |
| 20260922 | n=8 | 9 |
| 20260921 | n=8 | 10 |
| 20260918 | n=9 | 11 |
| 20260917 | n=3 | 12 |
| 20260916 | n=16 | 13 |
| 20260915 | n=16 | 14 |
| 20260914 | n=10 | 15 |
| 20260911 | n=3 | 16 |
| 20260909 | n=5 | 18 |
| 20260908 | n=9 | 19 |
| 20260907 | n=4 | 20 |
| 20260904 | n=14 | 21 |
| 20260903 | n=11 | 22 |
| 20260902 | n=1 | 23 |
| 20260901 | n=1 | 24 |
| 20260831 | n=1 | 25 |
| 20260828 | n=1 | 26 |
| 20260827 | n=1 | 27 |
| 20260824 | n=1 | 30 |
| 20260812 | n=1 | 37 |
| 20260811 | n=2 | 38 |
| 20260810 | n=5 | 39 |
| 20260807 | n=5 | 40 |
| 20260806 | n=2 | 41 |
| 20260805 | n=2 | 42 |
| 20260804 | n=5 | 43 |
| 20260803 | n=12 | 44 |
| 20260731 | n=7 | 45 |
| 20260730 | n=7 | 46 |
| 20260729 | n=1 | 47 |
| 20260722 | n=2 | 52 |
| 20260709 | n=3 | 60 |
| 20260708 | n=1 | 61 |
| 20260706 | n=1 | 63 |
| 20260630 | n=2 | 67 |
| 20260629 | n=1 | 68 |
| 20260627 | n=1 | 69 |
| 20260624 | n=1 | 71 |
| 20260612 | n=1 | 79 |
| NULL | n=77 | 확인 못 함 |

### 알려진 20260911 사건 현재 기록 대조

| 시장 | stage3 행 | 수급 확보 행 | 최초 기록 시각 | 최종 기록 시각 |
|---|---|---|---|---|
| kosdaq | 365 | 365 | 20260912_1053 | 20260912_1053 |
| kospi | 176 | 176 | 20260912_1051 | 20260912_1051 |

| 모델 | 동결 행 | 최초 동결 시각 | 최종 동결 시각 |
|---|---|---|---|
| v30 | 541 | 2026-09-12T11:43:27+09:00 | 2026-09-12T11:43:27+09:00 |

현재 DB에서 09/11 stage3 수급은 모두 확보되어 있고 v30 동결도 09/12 시각이다. 과거 사고는 **알려짐**으로 표시하되 현재 DB가 여전히 수급 0이라는 주장은 하지 않았다. 동결 점수 성과·당시 원본과의 점수 차이는 계산하지 않았다.

## 7. 현재 감시가 있는가(코드 정적 확인)

감시 있음은 저장된 코드에 비교·경고/로그 경로가 있다는 뜻이다. 실제 발송·배포·스케줄러 실행은 확인 못 함. 단순 적재 건수·날짜 출력은 지연을 판단하는 경고와 구분했다. 모듈을 import하거나 경고 함수를 실행하지 않았다. PTW는 소스만 읽었으며 data/·운영 DB·API는 열지 않았다.

| 멈춤 유형 | 판정 | 근거 파일·줄 | 한계 |
|---|---|---|---|
| 지수 KOSPI/KOSDAQ가 본 표보다 뒤처짐 | 감시 있음 | notify_telegram.py:361~375; market_series.py:138~161 | 🔔 경고·예비 조회 코드 있음. 공통으로 같은 날 멈추거나 series 자체가 없으면 놓칠 수 있음 |
| daily_flows 전체 마지막 날짜 지연 | 감시 있음 | notify_telegram.py:379~386; screener_fdr_v2_6.py:984~989 | 전체 MAX(date)와 전체 최신 종목 비율 90% 문턱. 특정 갈래 0%를 보장하지 않음 |
| 보충표 종목만 수급 정지 | 감시 없음 | kis_flows.py:290~325; 위 전체 감시 | 본 표/보충표 갈래 기대 목록의 최신 커버리지 경고 없음 |
| short/credit/loan의 갈래·종목·열별 날짜 정지 | 감시 없음 | kis_flows.py:497~531; notify_weekly.py:150~162 | 개별 호출 실패는 로그에 있음. 표/열 최신일과 기대 대상의 지속 누락을 판단하는 정기 경고는 확인하지 못함 |
| 단일 short 조회 실패 | 감시 있음 | kis_flows.py:514~531 | 최초 실패 최대 n=5종목과 총 실패 수를 로그로 남김. 일부 실패에도 종료 0일 수 있어 배치 실패 알림과 다름 |
| daily_ohlcv_extra 날짜·종목별 멈춤 | 감시 없음 | extra_ohlcv.py:60~145; notify_telegram.py 신선도 함수 | 수집 대상 수·적재 범위는 로그로 출력. 본 표 대비 지연/빠진 기대 종목을 🔔로 알리는 비교 없음 |
| stage1 행 수 급감 | 감시 있음 | run_and_diversify.py:123~171 | 시장별 최근 n=10run 중앙값의 50% 미만이면 공개 배포 보류. 이 감사의 직전20일/70% 규칙과 다름 |
| 수급 확보·재무 결손 급변 | 감시 있음 | notify_telegram.py:636~674 | 수급 전일 대비 절반 미만·시장별 재무 결손 경고. 확보=True라도 원자료가 낡은 경우는 보장 안 됨 |
| 거래일인데 run 자체 없음 | 감시 있음 | notify_weekly.py:169~190 | 최근 n=7달력일의 KOSPI 달력과 stage3 run 차집합. 같은 날 배치가 전부 죽으면 당일 경고는 보장 안 됨 |
| 과거 데이터 중간 날짜 구멍 | 감시 없음 | 위 주간 감시 범위 밖 | 최근 n=7달력일을 벗어난 과거 구멍의 정기 전수 경고는 찾지 못함 |
| valuation 일별·시장별 정지 | 감시 없음 | accumulate_valuation.py; notify_weekly.py:155 | 누적 날짜 수 출력은 있음. 최신일/시장별 커버리지 경고는 찾지 못함 |
| consensus 수집 전체 무커버 오염 | 감시 있음 | fetch_consensus.py:168~175; run_all_and_diversify.bat:106~109 | 커버리지 20% 미만이면 저장 거부·종료 1. 독립적인 주간 최신일 초과 경고는 없음 |
| large_final의 옛 stage3 원자료 운반 | 감시 있음 | large_score.py:110~129,281~282 | 소스 run 저장·당일/과거 건수 로그 출력. 지연 문턱 경고·텔레그램/배포 차단은 없음 |
| earnings 자료의 장기 정지 | 감시 있음 | earnings_flag.py:40~65 | 최신 접수일이 45거래일 오래되면 로그 경고, 60거래일 창 밖도 경고. 큐 실패/종목별 지속 누락 전수 감시는 별개 |
| listing_cache의 기준일/예비 사용 | 감시 있음 | notify_telegram.py:389~400 | source/saved_at 기준 경고 코드 있음. 이번 감사는 캐시 내용을 읽지 않아 실제 내부 기준일은 확인 못 함 |
| 날짜만 진전·값 복사/전부0/NULL | 감시 없음 | 기존 행수·최신일·재무 결손 감시만 확인 | 주식수 등 정상 상수와 구분한 수급/신용/공매도/시총의 연속 값 감시 없음 |
| 모든 기준 자료가 함께 멈춤 | 감시 없음 | 지수·수급 경고가 daily_ohlcv를 상대 기준으로 삼음 | 외부 달력/예정 run 대비 모든 표의 절대 최신성을 보장하는 독립 감시 없음 |
| lowvol/wu 표시 목록 자체의 갱신 지연 | 감시 있음 | docs/lowvol.html:76~101; docs/wu.html:68~91 (읽기만 함) | 브라우저 현재일 대비 run이 주중 n=2일 이상 오래되면 경고 배지. 공휴일 예외는 문구만 있고, 배치 경고나 내부 원자료 freshness 검사는 아님 |
| PTW 지수 지연·지수 없음 | 감시 있음 | ../Position-Tracker-Web/app/market_data.py:269~290; app/main.py:190~193; app/compute.py:733~747 | 저녁 확인 index 실패·503와 요약 경고 코드 있음. 운영 배포·실제 알림 도달은 확인 못 함 |
| PTW 수급 지연·시장 대응표 결손 | 감시 없음 | ../Position-Tracker-Web/app/market_data.py:269~306; app/main.py:188~193 | 수급 behind/대응표 크기는 기록만 함. 저녁 실패 조건·요약 경고에는 미포함 |

## 결론: 발견별 재현 방법 · 영향 · 고치는 안

모든 물리 표 n=24개, 갈래 집계 n=170개를 확인했다. 현재 날짜 전체의 장기 정지는 발견 n=0이지만, **종목 갈래별 원자료 멈춤 n=2유형(F1/F2)**과 **과거 적재 공백 n=1유형(F4)**을 직접 확인했다. F2는 코드상 지원 범위 제외가 명시되어 있어 수집기 고장과 범위 부족을 구분해야 한다. 단기 개별 실패·과거 입력 운반·값 불변은 따로 의심으로 분류했다. 판정 눈가림을 위해 수익·IC·순위 상관·점수 차이 등 성과 숫자는 계산하지 않았다.

| 발견 | 분류 | 실측/근거 | 영향 받는 곳 | 감시 | 고치는 안 |
|---|---|---|---|---|---|
| F1 보충표 종목의 daily_flows | 멈춤 확정 | 기존 n=131종목 중 n=130는 09/11(n=16거래일 지연), n=1는 09/10; 처음부터 자료 없음 n=5. 최신 대형 n=500 중 수급 기준일 없음 n=52 | 점수 입력·대형 표시/관측, 해당 종목을 쓰는 후속 판정의 입력 | 감시 없음(갈래별) | 본 표+보충표의 활발 종목을 기대 목록으로 고정하고 갈래별 최신일·20일 유효일 수·누락 건수를 검사. 이번에는 수정 안 함 |
| F2 보충표 종목의 short_flows | 멈춤 확정 | 기존 n=60종목의 마지막 06/26 또는 06/29; 처음부터 없음 n=76. 코드가 --no-daily 때 보충 대상을 명시적으로 생략 | 공매도·신용·대차 관측; 현재 본 표 기반 wu 대상과 보충표의 관계는 구분 필요 | 감시 없음(갈래별) | 의도한 지원 범위를 문서/배치 기대 목록에 명시하고, 지원 대상이면 보충표도 포함. 제외가 의도라면 오래된 원자료를 현재 지원처럼 취급하지 않기 |
| F3 활발 종목의 당일 short 결손 | 의심(단기 결손은 확정) | n=2종목 077360, 217500; 10/08 로그에서 신용 조회의 초당 호출 초과로 실패 확인 | short 기반 점수/관측 입력·표시. 성과 영향은 미계산 | 감시 있음(호출 실패 로그), 지속 결손 감시 없음 | 성공한 공매도/대차와 실패한 신용을 부분별로 보관하고 실패 부분만 재시도. 종목별 최신일·상태를 경고 |
| F4 과거 중간 날짜 공백 | 멈춤 확정(적재 공백) | 최근60일 n=3거래일 20260813, 20260820, 20260910에 stage1/valuation과 여러 history 표가 0; 시세 표는 존재 | 점수·판정 앵커·표시 | 감시 있음(최근 주간 run 확인); 과거 구멍 감시 없음 | 당일 단계별 완료 표식과 기대 거래일별 저장 행 수를 보관. 원본 로그/아카이브로 원인 확인 후 처리안을 따로 결정 |
| F5 최신 large_final의 과거 stage3 운반 | 의심 | 당일 n=159, 과거 n=264, 없음 n=77; 최대 n=79거래일. 의도된 최신 과거 행 조인이나 동적 수급도 함께 운반 | 대형 재무/수급 표시·관측 입력, 품질 판별 | 감시 있음(정보 로그), 지연 문턱 경고 없음 | 재무의 보고기간과 수급의 실제 기준일을 분리. 동적 입력은 별도 최신 창에서 받고 소스 날짜를 함께 표시 |
| F6 날짜는 최신이나 신용 열만 NULL | 의심 | 신용 n=3열 마지막 비NULL 20261002; 최근 n=3거래일 전부 NULL, 10/08 short 표 n=2516행. 1~2일 결손 설명·3일 지연 허용 설명이 혼재 | 신용 관측·표시, credit_bal_rate를 읽는 sv_b 보조 입력. 5일 창 min_periods=1로 이전 값이 남을 수 있음 | 감시 없음(열별 신선도) | 휴장·제공자 게시 지연을 반영한 열별 기대 갱신일과 마지막 비NULL 날짜를 저장하고, 허용 지연 초과를 경고. 실제 게시 일정 확인 후 문턱 결정 |
| F7 환율 시계열의 과거 중간 구멍 | 의심(기준 달력 대비 구멍) | USDKRW는 07/10 n=1거래일 행 없음. KOSPI/KOSDAQ는 존재하며 환율 최신일 자체는 10/08 | 환율을 읽는 관측·시장 표시. 해당 날짜 사용처별 대체 동작은 확인 못 함 | 감시 없음(환율 누락) | 국내/원자료 시장의 기대 달력을 구분해 series별 구멍과 마지막 유효일을 경고. 제공자 휴장·적재 실패 여부부터 확인 |
| N1 본 표 종목의 당일 수급 없음 | 정상(거래정지) | 본 표만 n=111종목은 전부 is_suspended=1; 활발 본 표 수급 당일 누락 n=0 | 표시·입력 대상 범위 | 수집 대상에서 제외; 별도 정지 상태 있음 | 정지 종목의 기대 대상 제외를 감시 분모에 반영 |
| N2 월별 lead·은퇴 모델 갈래 | 정상(주기/은퇴) | lead 10/01은 월 첫 거래일 앵커. v31 계열·lv_c/lv_d/lv_a3/lv_short/hv_a/mom_b·wu_a/wu_b는 RETIRED에 있음 | 판정·표시 | 월 앵커·은퇴 분기 있음 | 활성/은퇴/월별 주기를 반영한 기대 갱신일로 비교 |
| N3 consensus·earnings의 비일별 접수 | 정상(주간/공시 주기) | consensus 10/06(주간 가드), earnings 접수 10/07·원자료 수신 10/08·last_end 10/08 | 표시·관측·실적 배지 | 일부 감시 있음 | 매일 새 보고서가 있어야 한다고 판정하지 말고 수집 커서/실패 상태와 갱신 주기를 별도로 감시 |
| N4 주식수·EPS/BPS·상태 필드 불변 | 정상(상수/공시 갱신) | 주식수는 본 표 n=2576/2626·보충표 n=133/134가 10일 불변. 주식수·분류·분기 재무 값은 매일 바뀌는 값이 아님 | 시총·점수 입력·표시 | 값 복사 자체 감시 없음 | 가격/거래량 변화·분할/증자 사건과 함께 보는 조건부 감시로 오탐 방지 |
| N5 bank_net_val 불변·선택 필드 0/NULL | 의심(희소 값일 수 있음) | bank_net_val n=2293/2518가 10일 불변. 전체 금융 수급 정지나 복사라는 증거는 아님. 선택 상태/비활성 필드 0/NULL은 원래 정상 가능 | 수급 관측·표시 | 필드별 연속값 감시 없음 | 비활성/선택 필드는 제외하고, 원자료 기준일과 금액/수량의 동시 변화·비NULL 커버리지를 감시. 실제 제공자 응답은 확인 못 함 |
| N6 오래된 캐시 파일 | 의심(mtime 후보, 고정 역사 캐시일 수 있음) | 메타데이터 n=5591파일 중 감사용 20거래일 기준보다 오래된 n=1042파일. listing_cache 파일 mtime은 10/08 | 재무·상장목록·분류 입력 | listing 일부 감시 있음; 개별 캐시 내부 기준일 확인 못 함 | mtime만으로 폐기하지 말고 원자료 기준일/만료 정책/사용처를 별도 기록. 이번에는 내용 미열람 |
| N7 지수·시세·현재 활성 모델 최신일 | 정상(기준일까지 존재) | KOSPI/KOSDAQ·본 표·보충표·밸류·활성 모델 표의 마지막 날짜는 10/08 | 점수·판정·표시 | 지수 일부·행수 일부 감시 있음 | 전체 최신일뿐 아니라 갈래별 최신일·기대 종목 커버리지를 함께 검사 |
| P1 PTW 뒤처짐 감시 | 정상(지수 감시 코드 확인, 운영 상태는 확인 못 함) | 지수 감시 코드 있음. 수급/시장 대응표는 정보용 기록. 운영 데이터·API·배포는 확인 안 함 | PTW | 지수 있음; 수급/대응표 경고 없음 | 기록된 수급 behind/시장 대응표 결손을 별도 경고로 올리는 안 검토. 여기서는 코드 수정/실행 안 함 |

### 핵심 재현 방법과 원인 범위

1. F1/F2: `daily_ohlcv_extra WHERE date=20261008`의 종목 집합을 만든 뒤 daily_flows/short_flows를 LEFT JOIN하고 종목별 MAX(date)를 센다. 일반 표/market별 MAX(date)는 모두 최신이라 이 갈래를 놓쳤다. `kis_flows.load_all_tickers`는 본 표 활발 종목+listing_cache를 쓰며 기존 보충표 종목 집합을 사용하지 않는다(kis_flows.py:290~325). 실제 캐시 내용은 요청에 따라 읽지 않았다. 10/08 로그는 시세 보충 대상 n=136, 일별 수급의 상장목록 보충 n=111, 공매도 대상 n=2518을 기록한다. **캐시에서 보충표 종목이 빠졌다는 직접 확인은 못 함**; 수집 대상 구성과 원자료의 집단 정지를 대조한 원인 추정이다. 공매도 보충 생략은 코드에서 직접 확인한 사실이다.
2. F1 영향 경로: screener_fdr_v2_6.py:955~989는 전 표의 최근20일 창 안에 보고된 행을 종목별 합산하고 supply_fetched=True로 둔다. 종목마다 당일 여부/유효20일을 필수로 요구하지 않는다. 10/08 로그의 최신일 보유는 91%, 경고 문턱은 90%라 전체 경고로는 누락 갈래를 잡지 못한다. 현재 stage1 보충표 종목 n=73 중 확보=True n=32, stage3 n=20 중 확보=True n=20를 직접 확인했다. stage3 상세 원자료 날짜·유효일 수는 위 표에 적었다. 점수/판정 수치가 얼마나 바뀌는지·성과 영향은 계산하지 않았다.
3. F3: 본 표 is_suspended=0이면서 10/08 short 행이 없는 종목을 구한다. 10/08 로그의 077360·217500 실패 사유는 신용 조회 초당 호출 초과다. collect_short는 신용 조회 실패 시 앞서 받은 공매도도 저장 단계로 넘기지 않는다(kis_flows.py:445~478). 해당 종목의 마지막 원자료는 아래 표에 적었다.

| 종목 | 이름 | 마지막 short 날짜 | 마지막 수신 시각 | 지연 거래일 |
|---|---|---|---|---|
| 077360 | 덕산하이메탈 | 20261007 | 20261007_2043 | 1 |
| 217500 | 러셀 | 20261007 | 20261007_2043 | 1 |

4. F4: market_daily의 거래일별 stage1/valuation 행 수를 0까지 채워 대조한다. 해당 날짜의 자동 배치 로그 파일은 현재 저장소에서 찾지 못했고 원인·사용자가 일부러 비운 것인지는 **확인 못 함**. 사후 복원이나 앵커 제외 여부를 여기서 정하지 않았다.
5. F5: 현재 large_final의 stage3_src_run별 행 수와 지연 거래일을 센다. load_stage3_latest는 target_run 이하 가장 최근 행을 종목마다 고르므로 오래된 값 운반 자체는 설계에 있다. 재무는 분기 갱신이 정상이나 동적 수급까지 같은 소스 시각으로 운반되는 점은 구분이 필요하다.

6. F6: short_flows를 date로 묶어 세 credit 열의 COUNT(열)과 MAX(CASE WHEN 열 IS NOT NULL THEN date END)를 대조한다. 10/06·10/07·10/08은 행이 있으나 세 열 모두 비NULL n=0이다. 공매도·대차는 비NULL 마지막 날짜 10/08로 신용만 뒤처졌다. wu_score는 신용을 5일 창·최소 유효1일 평균으로 읽는다(정적 확인); 이 감사에서는 점수를 실행하지 않았다. 제공자 게시 지연인지 실패인지 확인 못 함.

7. F7: 국내 거래일 집합과 market_daily의 series별 날짜 집합을 차집합으로 비교한다. 07/10 USDKRW n=0은 확인됐으나 원자료 달력이나 수집 실패 원인은 확인 못 함. notify_telegram의 지수 경고는 KOSPI/KOSDAQ만 검사하므로 환율은 빠진다.

### 해석 한계와 재현 명령

- 날짜·행 수·종목 집합·NULL/0/불변 비율은 직접 계산한 사실이다. 전부 같은 값이라는 조건만으로 제공자가 복사했다고 확정할 수 없다. 감시 코드는 정적으로 확인했으며 텔레그램 발송/운영 배포는 확인 못 함.
- 최근60일의 n=441개 70% 미만 행은 진단 후보이지 서로 독립적인 사고 n=441건이 아니다. 시장×표 중복, 주간·월별·공시 희소 자료, 은퇴와 등록, 후보 필터 변화가 함께 포함된다. stage1과 valuation의 공통 0 날짜·보충표 기대 목록의 연속 0은 별도로 확인했다.
- 실행: `python -B research/handoff/code_20261010_stale_data_audit.py`. 표/갈래/기간별 요약을 순서대로 답 파일에 저장한다. 캐시 파일은 이름·크기·mtime만 수집한다. 외부 호출·운영 코드 수정·DB 쓰기·성과 계산 n=0. 이미 본 저장 자료의 사후 감사이며 새로운 기간의 독립 성과 검증이 아니다.

### 감시가 없는 멈춤 유형

1. 전체 표는 최신인데 보충표·시장·모델·출처 등 일부 기대 갈래만 멈추거나 사라짐(활성/주기/정지 예외를 반영한 감시).
2. short_flows의 공매도·신용·대차 각각의 마지막 비NULL 날짜, 지속 누락 종목, 지원 범위 밖에 남은 오래된 자료.
3. daily_ohlcv_extra·valuation_daily의 기대 거래일/종목별 지연, 최근 주간 창을 벗어난 과거 적재 구멍.
4. 날짜만 진전하는 값 복사·전부0/NULL(정상 상수/선택 필드 제외), 기존 자료의 소스 날짜와 저장 날짜 분리 감시.
5. daily_ohlcv·market_daily·수급이 함께 멈춰 상대 날짜 비교를 통과하는 공통 정지의 배치 경고(일부 목록 화면에는 오래된 run 배지가 있음), USDKRW 등 시계열별 기대 달력 구멍.
6. 주간 consensus의 예정 갱신일 초과, 개별 캐시의 원자료 기준일/지원 범위 변화(파일 mtime 외).
7. PTW 수급 뒤처짐·시장 대응표 결손의 실패 경고(현재는 정보용 기록만 있음).

