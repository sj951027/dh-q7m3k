# 2026.10.42 — 모의 계좌에 E3 '국면 스위치 계좌' 1장(`switch_v30_lvb`: 급락 뒤 v30, 그 밖 lv_b) (2026-10-30)

## 그래서 뭐가 바뀌나
- `docs/paper_account.json`·`paper_account.db` 에 계좌 1장 추가(12 → 13): **`switch_v30_lvb` "스위치 · 급락 뒤 v30, 그 밖 lv_b"**. 규칙은 'v30 기본'과 전부 같고(슬롯 40 · t+1 종가 진입 · 40거래일 뒤 청산 · 왕복 0.5% · 시장별 상위 10 동일가중 · 희석 제외 · 되감기 20260810 · 라벨 '사후'), **그날 어느 목록을 쓰나만** 다르다: 앵커일 코스피 칸이 A(R20 ≤ −5%)면 v30 상위 10, 그 밖(B·C·D·칸 없음)이면 lv_b 상위 10. 고른 목록이 그날 없으면 신규 0(현금).
- 요약 키 추가: `days_A`·`days_other`(그 목록을 쓴 앵커 수) · `days_missing`(목록 없어 신규 0 인 날) · `slots_from_v30`·`slots_from_lvb`(체결 슬롯 수) + 2판 감도 3개(`total_ret_cost035`·`total_ret_delist90`·`slots_gone`) 동일. JSON 상단 `switch` 블록에 정의 메모.
- 표시(리더보드)·텔레그램 무변경.

## 왜 바꿨나
- 실험 계획 `research/EXPERIMENT_PLAN_20261030.md` E3 · 11년 대리 되감기 `research/RESEARCH_regime_switch_proxy_10y_20261030.md` §4: A 칸 과매도 − 저변동 +5.55%p, D 칸 −2.15 → "급락 뒤엔 과매도, 그 밖엔 저변동" 스위치가 둘 각각보다 나은지 **실제 목록으로 돈 기준 관측**(2단계). 사용자 승인 19:30. 변수는 '목록 선택' 하나.

## 어떻게
- `paper_engine.py`: 순수 함수 `switch_picks(dates, cells, picks_a, picks_other, a_cells=("A",))` → (합친 목록, info{days_A·days_other·days_missing·source}). 칸이 a_cells 면 picks_a[그날], 그 밖(NaN 포함)은 picks_other[그날]; 고른 쪽이 없으면 그날 없음(대체 안 함). `simulate` 무변경.
- `paper_account.py`: `SWITCH_ID`·`SWITCH_A_CELLS`, `cells.reindex(dates)`(= `v30_gateD0` 가 쓰는 **같은 Series·같은 날짜 기준** — 새 칸 기준 없음)로 v30 목록(`picks`)과 lv_b 목록(`mpicks["lv_b"]`)을 합쳐 계좌 1장 추가, 요약에 위 키, `paper_meta.switch`.
- `tests/test_paper_account_v2.py` G절(합성 8체크): A 날 v30 · B 날 lv_b · 결손 날 현금(대체 안 함) · 칸 없음 = 그 밖 · 날마다 한 목록만 · 진입 순서 · 슬롯 출처 셈 · 두 목록 동시 진입 없음.
- 검증: ① **기존 12계좌 0-diff** — `--out` 스크래치 산출 ↔ `docs/paper_account.json`(19:00 산출, 같은 자료 20261029) 대조: summary 기존 키 전부 · nav 54일 전부 소수 여섯째 자리까지 일치, 추가된 키 없음(새 계좌만 추가). ② `python tests/run_tests.py` 전체 통과. ③ 저장소 `python paper_account.py` 1회(23초) → JSON 13장·`switch_v30_lvb` 요약 확인(10/30 배치가 다시 만든다).
- 실측(20260810~20261029, 사후): 스위치 **−5.7%**(최대 낙폭 −7.4 · 평균 현금 48.8%) vs v30 기본 −5.8%(−8.5) · lv_b 기본 −5.5%(−7.4). 앵커 A 16 · 그 밖 34 · 목록 없음 4(v30·lv_b 둘 다 run 결손인 날 — 게이트·공휴일). 체결 슬롯 v30 298 · lv_b 593. 감도: 0.35% −5.6% · 상폐 −90% 차이 0. 창 하나(급락 창 자체가 A 칸 위주라 lv_b 와 비슷) — 결론 아님.

## 영향 범위
- **판정·점수 0-diff**(history.db 읽기만). 기존 12계좌 0-diff(위). 배치 시간 +1초 안팎(23~26초).
- 각주: E3 문서 '경계' 줄은 "칸은 신호일 **전 거래일** 종가"라 적혀 있으나, 요청대로 `v30_gateD0` 와 같은 **앵커일 칸**을 썼다(새 기준을 만들지 않기 위해). 두 기준을 같이 쓰려면 변수가 하나 더 늘므로 사용자 결정 사항으로 남김.
