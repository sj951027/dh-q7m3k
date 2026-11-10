# patch_note/ — 변경 이력 (2026-08-16 도입)

**현재 버전: 2026.11.14** (버전 = 최신 패치노트의 버전)

> **역할 분담**: 지식 문서(PROJECT_KNOWLEDGE 등)는 "현재 상태·설계 결정"의 정본,
> `patch_note/`는 "무엇이 언제 왜 어떻게 바뀌었나"의 이력. 연구 산출물은 research/ (별개).
> 프로그램 파악 시 지식 문서 + 최근 패치노트를 함께 읽는다.

## 작성 규칙

- **버전 체계(CalVer)**: `연도.월.차수` (예: 2026.08.1 → 08.2 → …, 9월 첫 변경은 2026.09.1).
  ⚠ v숫자 형식 금지 — v2.6(엔진)·v3(트랙)·v30(모델)·PTW v5.x와 이름공간 충돌.
  버전은 노트 제목(H1)에 병기하고, 이 README의 '현재 버전'을 함께 갱신한다.
  모델 스펙은 model_id가, 엔진은 v2.6이 각자 버전 관리 — 이 버전은 운영·표시·파이프라인의 시점만 담당.
- **파일명**: `YYYYMMDD_주제.md` (예: `20260812_lowvol_gate_stage1.md`). 같은 날 여러 건이면
  주제로 분리하거나 한 파일에 절로 묶기 — 세션 단위 1파일이 기본.
- **작성 시점**: 코드·표시·파이프라인·운영 설정이 바뀌는 세션의 마지막에 1건.
  연구만 한 세션(research/만 생성)은 생략 가능 — RESEARCH_*.md가 그 역할.
- **필수 항목** (PTW 템플릿 차용):
  1. **그래서 뭐가 바뀌나** — 사용자 눈에 보이는 변화 한두 줄
  2. **왜 바꿨나** — 문제·근거 (사건이면 원인 분석 포함)
  3. **어떻게** — 바뀐 파일 목록 + 핵심 구현 + 검증 방법(0-diff·py_compile·실렌더 등)
  4. **영향 범위** — 점수·판정에 영향 있는지 (없으면 "판정·점수 0-diff" 명시)
- 소급 작성은 하지 않는다(2026-08-11 이전 이력은 코드 주석·VERDICT·git이 담당).
  단 도입 주간(08-11~15)은 시작 사료로 백필돼 있음.

- [20261110_lve_page.md](20261110_lve_page.md) — **2026.11.14** lv_e 관측 페이지 `docs/lve.html` 신설(lowvol.html 틀 · 날짜 탭 `hist/lv_e.json` · 배치 2.87d · 성적표 링크) — 운용 목록은 lv_b 그대로, 표시 전용 0-diff
- [20261108_scoreboard_pending.md](20261108_scoreboard_pending.md) — **2026.11.8** 성적표 기록 칸 확정/쌓인/보유 중 구분(끝 날짜 9/4 혼동) · 회색 숫자 옆 "표본 부족, 색 없음" · 기록 칸 잘림 수정 — `pending` 키 추가뿐, 판정·점수 0-diff
- [20261108_knowledge_guard.md](20261108_knowledge_guard.md) — **2026.11.13** 지식 세 층 자동 감시 hook(`.claude/settings.json` SessionStart·Stop → `tests/knowledge_guard.py`): 시작 때 세 장 검사·정리 주기·정리할 거리, 끝날 때 기록 층만 바뀌면 한 번 막음(`지식 층: 변경 없음` 선언으로 통과) — 0.3초·읽기 전용·오류는 통과
- [20261108_signal_board_codex.md](20261108_signal_board_codex.md) — **2026.11.12** 🚦 카드 문구·표시 오류 개정(Codex 검토 9건 반영: 조합 아님 명시·모델 다섯 상태·업종 자료 없음·게이트 등호 제거·코스닥 병기, 375px 420px) + 지식 세 장 정정(lv_e 돈 조건 범위·스냅샷 완료·국면 용어 표·ID) + 검사 보강(원장 읽기 → 빠진 모델 5개 보강) — 표시 전용 0-diff
- [20261108_knowledge_layers.md](20261108_knowledge_layers.md) — **2026.11.11** 지식 세 층 구조: `KNOWLEDGE.md`(확정 결론)·`DECISIONS.md`(사용자 결정)·`PITFALLS.md`(함정) + `research/lib/tenyr.py`(11년 대리 공통 틀, 기존 결과 0-diff) + 테스트 2건 + CLAUDE.md 읽기 순서·마무리 7·8 — 문서·테스트만, 점수·판정·배치 무변경
- [20261108_signal_board.md](20261108_signal_board.md) — **2026.11.10** 🚦 오늘 한 줄 카드(모델×장세×업종 세 등불, 조합 문장, 모의 계좌 각주) 성적표·v30 목록 상단 — `docs/signal_board.js` 표시 전용, 규칙은 결과 전 고정(SIGNAL_BOARD_20261108), 11년 칸별 근거 · 변동성 축 닫음 · 판정·점수 0-diff
- [20261108_scoreboard_readability.md](20261108_scoreboard_readability.md) — **2026.11.9** Codex 사용성 검토 2차 반영: 자료 적음 배지 · 평가 완료/평가 대기 · 추천일 · 휴대폰 세로 배치(표시 전용, 0-diff)
- [20261108_sector_badge_lists.md](20261108_sector_badge_lists.md) — **2026.11.7** 업종 낙폭 사실 배지(v30·lv_b 목록, '20일↓ −21.7%' · 경고 아님 · `build_sector_dd.py` → `docs/sector_dd.json`, 배치 2.75단계) · 업종 캐시 날짜별 스냅샷(`../dh-q7m3k-data/sector_snapshots/`) · 세 목록 이름(화면 권고10 · 성적표 상위10 · 모의 계좌)과 오늘 차이 수(권고 상자·성적표 도움말) — 표시·자료 전용, 판정·점수 0-diff
- [20261107_usability_codex_batch.md](20261107_usability_codex_batch.md) — **2026.11.6** Codex 사용성 검토 반영 17건(표시·문구 전용): 작은 표본 비율 숨김을 작은 표 전부에 · 참고 구간 최저/최고 부호색 · v30 2차 창 판정 병기(성적표 상세+공통 상태 줄) · 상세 줄 나눔(40일 완료/참고 기록/보유분 평균) · 판정 쉬운 말 통일 · 안전필터 → '재무 위험 조건 제외' · 375px 버튼 2열 · 배지 뜻 · 알림 문구 3줄(현황 실패 ⚠️·표본 대기·모의 수익)
- [20261107_scoreboard_readability.md](20261107_scoreboard_readability.md) — **2026.11.5** 성적표 읽기 혼동 4건(표시 전용): 시장 수익 병기+'덜 잃음/더 벌음' · 목록 10개 미만/겹치지 않는 창 1 미만은 비율 회색 '참고 불가' · lv_e 아래 표시 기준 안내 · '이긴 비율'→'시장보다 나은 목록 비율'. 판정·점수 0-diff.
- [20261107_midterm_fixes.md](20261107_midterm_fixes.md) — **2026.11.4** Codex 중간점검 반영: 반반 계좌 목록별 예산 절반(가중치 dict, list 경로 0-diff) · 수급 상태 날짜 일치·창 달력 행 합산·열 누락 None · 점검표 산출 상태(계좌 0장·생성일) · 돈 관측표 만기 결손 = 마지막 유효가. 13장 0-diff·테스트 통과. 판정·점수 0-diff.
- [20261107_calendar_window.md](20261107_calendar_window.md) — **2026.11.3** 운영 검토 F2·F4: 모의 계좌 달력을 본표 거래일로 고정(보충표의 본표 밖 날짜 제외) · 수급 20·60일 창을 거래일 달력으로 검사(결손일 있으면 null+기록). 14계좌·수급 JSON 0-diff·테스트 통과. 판정·점수 0-diff.
- [20261107_health_flows_partial.md](20261107_health_flows_partial.md) — **2026.11.2** 운영 검토 F1·F5·F3: 수급 한쪽만 갱신 → partial·점검표 시장별 lag · 되감기 시각 형식 통일(미래 적재 혼입 차단) · 산출물 상태 갈래 2개(19갈래)·모의 계좌 JSON 원자적 쓰기. 기존 17갈래 0-diff·테스트 통과. 판정·점수 0-diff.
- [20261107_paper_mix_account.md](20261107_paper_mix_account.md) — **2026.11.1** 모의 계좌 14장째 정적 반반 `mix_v30_lvb_5050`(E3 비교군, 관측 계약 §3; 기존 13장 0-diff) + 판정 스크립트 돈 관측표 ⑩. 판정·점수 0-diff.
- [20261103_earnings_recent_badge.md](20261103_earnings_recent_badge.md) — **2026.10.49** 목록 페이지 '정기보고서 접수 N일' 표시(관측·가중 0, 열 `earn_recent_20d`; Codex 구현·Claude 검증, 테스트 통과). 판정·점수 0-diff.
- [20261101_paper_settle_days.md](20261101_paper_settle_days.md) — **2026.10.48** 모의 계좌 매도대금 T+2 결제 감도 키 `total_ret_settle2`(기본 경로 0-diff; le_a −20.1→−19.2 · sv_a −11.9→−11.4 병기). 판정·점수 0-diff.
- [20261101_data_health_market_flows.md](20261101_data_health_market_flows.md) — **2026.10.47** 자료 점검표 17번째 갈래 '시장 수급(KRX)'(J14). 표시·점수 무관.
- [20261031_market_flows_obs_hardening.md](20261031_market_flows_obs_hardening.md) — **2026.10.46** 수급 일일 갱신 단계 보강(자식 프로세스 300s 제한·저장 전 보존식 검사·수량 NULL 보존·revision·로그인 ID 출력 차단·창 완전성·원자적 JSON) + 모의 계좌 보충표 병합 (종목,날짜) 우선·실패 시 raise. Codex 검토 반영. 표시·점수 0-diff.
- [20261031_paper_cost100_extra_prices.md](20261031_paper_cost100_extra_prices.md) — **2026.10.45** 모의 계좌 비용 1.0% 감도 키(기존 키 0-diff) + 보충 시세표 daily_ohlcv_extra 합치기(lv_b 뽑힘 9% 가 현금이 되던 것 정정, lv_b −6.8 → −7.7 · 스위치 −7.0 → −8.0, 11/2 배치부터). 판정·점수 0-diff.
- [20261031_market_flows_obs.md](20261031_market_flows_obs.md) — **2026.10.44** 시장 수급(KRX 투자자별 11구분) 11년 수집(`market_flows_10y.db`) + 배치 일일 갱신·`docs/market_flows_obs.json`(관측·가중 0, 표시 미반영). 연구: 외국인 추종 닫음·연기금 보류. 판정·점수 0-diff.
- [20261030_paper_tradable_newlisting_fix.md](20261030_paper_tradable_newlisting_fix.md) — **2026.10.43** 모의 계좌: 상장 첫날 종목(등락률 NULL)이 있으면 진입 가능 표가 bool 이 못 되어 배치 단계가 비치명 실패하던 것 수정(`paper_engine.tradable_mask`, 열 합집합). 옛 식과 2,660열 전부 같음 · 판정·점수 0-diff.
- [20261030_paper_switch_e3.md](20261030_paper_switch_e3.md) — **2026.10.42** 모의 계좌 E3 '국면 스위치 계좌' 1장(`switch_v30_lvb`: 앵커일 코스피 A 칸이면 v30 상위 10, 그 밖 lv_b 상위 10 — `paper_engine.switch_picks`). 기존 12계좌 0-diff · 판정·점수 0-diff · 표시 무변경.
- [20261030_paper_account_v2.md](20261030_paper_account_v2.md) — **2026.10.41** 모의 계좌 2판: 모델 계좌 5장(lv_b·le_a·lv_e·sv_a·sv_b) + 전 계좌 상폐 −90%·비용 0.35% 감도(`paper_engine.simulate(gone=…)`·`paper_account.model_picks`). 기존 7계좌 0-diff · 판정·점수 0-diff. 자리바꿈·돈 기준 탭은 다음.
- [20261024_notify_verdict_skip_on_fallback.md](20261024_notify_verdict_skip_on_fallback.md) — **2026.10.40** 판정 도달 알림: 정확한 유효 앵커 셈을 못 한 날은 알림·완료 기록 건너뜀(옛 셈이 많게 세 일찍 알릴 수 있던 것). 0-diff.
- [20261024_notify_verdict_fix.md](20261024_notify_verdict_fix.md) — **2026.10.39** 판정 도달 알림: 셈을 leaderboard 유효 앵커와 같게(전 모델 하루 늦던 것) · 전송 성공 때만 '완료' 기록. 점수·판정 0-diff.
- [20261024_v32a_review_fixes.md](20261024_v32a_review_fixes.md) — **2026.10.38** Codex 커밋 점검 반영: v32a 페이지 첫 적재 실패 수정 · 바구니(−999 제외)·결측·시장 쌍 규칙 고정 · 판정 알림에 lv_e·sv_b·v32a. 점수·판정 0-diff.
- [20261024_v32a_register.md](20261024_v32a_register.md) — **2026.10.37** v3 챌린저 v32a(한산한 과매도) 등록·배선(관측, v3 분모 7→8) + 관측 페이지 `docs/v32a.html`. v30 0-diff(325셀).
- [20261023_buy_context_10y.md](20261023_buy_context_10y.md) — **2026.10.36** 🧭 통계를 10년 DB 기준으로(폐지 포함·수정주가 + 운영 DB 이어 붙임, 지수 10년 이력). 표시 전용, 0-diff.
- [20261021_paper_account_batch.md](20261021_paper_account_batch.md) — **2026.10.35** 모의 계좌 배치 연결(비치명, 사후 라벨). 0-diff.
- [20261021_market_context.md](20261021_market_context.md) — **2026.10.34** 거래일별 시장 상황 이력 `docs/market_context.json`(regime_ad.history, PTW 조회용). 0-diff.
- [20261020_paper_account_v1.md](20261020_paper_account_v1.md) — **2026.10.33** 모의 계좌 1판 `paper_account.py`(계좌 7장 되감기 적재 · 배치 미연결 · 사후 라벨). 0-diff.
- [20261020_buy_context_telegram.md](20261020_buy_context_telegram.md) — **2026.10.32** 🧭 '이만큼 빠졌던 때 과거엔 어땠나' 3줄(시장 전체 기준, buy_context.py) · 텔레그램 매일 알림 짧게(성적표 블록 off·판정 일정 임박만) · 성적표 페이지 여섯 칸 표 · 모의 계좌 엔진 뼈대 paper_engine.py. 표시 전용, 0-diff.
- [20261020_regime_ad_display.md](20261020_regime_ad_display.md) — **2026.10.31** A~D 진입 국면 표시(regime_ad.py · data.json `regime_ad` · 텔레그램 🧭 줄 · 성적표 A~D 병기 · PTW v5.45). 표시 전용, 0-diff.
- [20261020_batch_watch_delay.md](20261020_batch_watch_delay.md) — **2026.10.30** 배치 밖 감시 가짜 ⚠️ 수정(GitHub 예약 5h43m 지연 → '14시간 안 자동 push' 규칙, 배치일 = 지금−6h, 예약 23:27). 0-diff.
- [20261018_review2.md](20261018_review2.md) — **2026.10.29** 2차 검토 반영: 점검표 갈래별 격리(표 하나 없어도 그 갈래만) · ohlcv core 백업 주 1회 가드. 0-diff.
- [20261018_codex_review_fixes.md](20261018_codex_review_fixes.md) — **2026.10.28** Codex 커밋 점검 반영: 배치 감시는 'Auto update' 커밋만 인정 · 점검표 보충표 종목 수급 갈래(10/10 되감기 ⚠️ 재현) · 운용 채택 비용 각주 문구 교정. 0-diff.
- [20261018_index_backup_sector.md](20261018_index_backup_sector.md) — **2026.10.27** history.db 인덱스 3개(이득 작음, 무해) · history.db 매일 백업(ohlcv 주 1회) · 점검표 업종 갈래(커버 90% 기준). 0-diff.
- [20261018_data_health.md](20261018_data_health.md) — **2026.10.26** 자료 건강 점검표 `data_health.py`(14갈래 뒤처짐·건수 급감 → 텔레그램 ⚠️ + `docs/data_health.md`, 과거 사고 되감기 시험 통과). 배치 1줄. 점수·판정 0-diff.
- [20261018_batch_watch_ops_note.md](20261018_batch_watch_ops_note.md) — **2026.10.25** 배치 밖 미실행 감지(GitHub Actions `batch_watch.yml`, 평일 23:10 KST · docs/ push 날짜로 판단 · Secrets 는 사용자 등록) · 운용 채택 사전등록 비용 표기 해석 각주(판정 = 0.5% 차감본) · v30 2차 창 판정문 초안(노이즈 · 확정 전). 점수·판정 0-diff.
- [20261004_earnings_badge_review_fixes.md](20261004_earnings_badge_review_fixes.md) — **2026.10.16** 실적 악화 배지 독립 검토 반영(접수일을 접수번호로·12월 결산만·같은 연결/별도 기준·극단값/오래된 시세 제외·낡은 자료 경고) + 용량 정리(은퇴 모델 보관 폴더 압축 이동).
- [20261004_earnings_drop_badge.md](20261004_earnings_drop_badge.md) — **2026.10.15** 실적 악화 60거래일 배지 📉(표시 전용, 화면 8개 · `earnings_flag.py` · `earnings.db`). 배치 DART 호출 추가 없음. 11월 중순 전 증분 수집 필요(미구현).
