# 2026-09-13 — 재실행 시 latest CSV 미갱신 버그(수급 0 표시) · v30 페이지 운영 권고 상자·권고10 배지 (2026.09.8 · 판정·점수 0-diff)

## 그래서 뭐가 바뀌나
- v30 페이지(`docs/filter.html`)에 **"어떻게 사나" 상자**가 생겼다(다음 거래일 매수 · 시장별 상위 10 · 희석 배지 회피 · 4트랜치 · 40거래일 보유 · 손절 없음 — OPS_GUIDE §0 요약, 강제 아님).
- 표의 # 옆에 **권고10** 배지: 텔레그램 폴백과 같은 안전필터(이중적자·밸류트랩의심·주의·위험 제외) 후 V3점수 상위 10.
- 자정 넘김·주말 **재실행** 뒤에도 `latest_*_final.csv`(→ docs CSV·필터 페이지)가 그 재실행 결과로 갱신된다.

## 왜 (사건, 실측)
- 사용자 지적: v30 페이지에 수급이 안 보인다. 확인 결과 `docs/latest_kospi_enriched.csv` 외인·기관 5/20일 열 175종목 전부 빈값, `supply_fetched` 전부 False. history.db `stage3_final` 20260911 은 541/541 채워져 있음.
- 원인: 09-12 10:46 재실행(run_id 20260911 로 보정)에서 3단계 출력 파일명이 실행 시각 `v2_kospi_final_20260912_1052.csv`. `accumulate_history.archive_csvs` 는 파일명에 run_id(20260911)가 든 것만 옮기고 그때만 latest 를 갱신 → 로그 "🗂 0개 CSV → archive\20260911\kospi/" · latest 는 **09-11 20:15 첫 실행본(네이버 크롤링 실패로 수급 0)** 그대로. 그 위에 `v3_merge` 가 v30 열만 재실행 값으로 병합.
- 영향: 필터 페이지의 V3점수·등급·버킷은 정상, 수급·RSI·수익률·패턴·위험 등 나머지 열은 첫 실행 값. history.db·텔레그램·index.html(data.json 은 history 기반)은 정상. 09-11 23:54 2차 재실행도 같은 로그(0개 CSV).
- 정규 20:10 배치는 실행일=run_id 라 해당 없음. 자정 넘김·주말 재실행에서만 발생.

## 어떻게
| 파일 | 변경 |
|---|---|
| `accumulate_history.py` | `archive_csvs(..., run_ts=None)`: 파일명에 run_id **또는 실행일(run_ts 날짜부)** 이 든 CSV 를 옮김. 호출부에서 run_ts 전달. py_compile OK |
| `docs/filter.html` | 운영 권고 상자(CSS `.howto-box`) · `computeReco10()` + 행 배지 `.reco`. 표시 전용 |
| 데이터 복구(스크립트, 사용자 실행) | 재실행 원본(`v2_{mkt}_final_20260912_*.csv`, 루트 잔존)을 latest/docs final 로 복사, enriched 는 원본 + market·dilution_60d·sector(기존 enriched 에서 ticker 매핑), 원본은 `archive/20260911/{mkt}/` 로 이동, 이후 `python v3_merge.py --run_id 20260911` |

## 검증
- 필터 페이지 로컬 실측: 상자 표시, 권고10 배지 1~10위, 콘솔 오류 0. `python tests/run_tests.py` 전체 통과(점수·판정 코드 미접촉 → 0-diff).
- 데이터 복구는 Claude 세션의 자동 권한이 파일 덮어쓰기를 막아 **사용자가 직접 실행**(아래 명령). 실행 후 확인: enriched `foreign_5d_억` 175/365 채움, `supply_fetched` True, v3 열 존재.

## 영향 범위
- 점수식·판정·게이트·DB 무변경. 공개 페이지는 09-14 배치 push 때 반영(또는 docs 수동 push).
- 남은 것: 재실행 원본 파일명이 실행일이라 헷갈리는 구조 자체는 그대로(보관 단계에서만 흡수). 3단계가 run_id 로 파일명을 찍게 하는 것은 별도 검토.
