# REQUEST — 변경 검토: 업종 낙폭 사실 배지 · 업종 캐시 날짜별 스냅샷 · 세 목록 이름 (커밋 3659218, 2026.11.7) — 2026-11-08

> 보내는 사람: 사용자(Claude 초안). 받는 사람: Codex. **코드·docs·DB 수정 없음**, DB 는 `mode=ro`, 배치·수집기 실행 금지, 평일 20:10~22:30 실행 금지.
> 답 하나: `research/handoff/REPLY_20261108_sector_badge_review.md`. 이번 건은 "위험한 변경 검토" 몫(표시 전용이라고 주장하는 변경이 정말 0-diff 인지). 양보다 **틀린 곳 찾기**. 없으면 "없음".

## 0. 무엇이 바뀌었나 (읽을 것, 이 순서)
1. `patch_note/20261108_sector_badge_lists.md` — 뭐가/왜/어떻게. 근거는 네가 11/8 에 답한 `REPLY_20261108_full_review_sector_drawdown.md` §2(경고 불허·세 목록 차이 81/1,960행) 와 Claude `research/SECTOR_DRAWDOWN_20261108.md` §1 정의.
2. `build_sector_dd.py`(새, 약 90줄) · `run_and_diversify.py` 2.75단계(5줄 삽입) · `docs/filter.html`(`renderListsNote` · `sectorDDBadge` · 권고 상자 `listsNote` · `case 'name'`/`'string'`) · `docs/lowvol.html`(`sectorDDBadge` · COLS sector) · `docs/leaderboard.html`(도움말 한 문장). `git show 3659218 --stat` 으로 범위 확인.
3. 산출물: `docs/sector_dd.json`(36개 업종) · `../dh-q7m3k-data/sector_snapshots/sector_cache_20261106.json`.

## 1. 확인해 달라는 것 (각각 맞음 / 틀림+어디 / 못 가름)
1. **0-diff 주장**: 커밋이 점수식·`paper_engine`·`leaderboard`·`build_scoreboard`·게이트·선정(권고10 집합 자체)을 건드리지 않았나. `run_and_diversify.py` 삽입 위치(2.74 뒤·완전성 게이트 앞)가 배포 게이트·`deploy_ok` 에 영향 없는지. 스크립트가 예외를 삼키고 exit 0 이라 "조용한 실패" 가 배치 로그에 보이는지(⚠️ 줄).
2. **정의 일치**: `build_sector_dd.sector_drawdowns` 가 연구 §1 과 같은가 — 동일가중 일수익(`change_pct`) 누적, 종목 ≥ 10 인 날만, dd20 = 당일 ÷ 직전 20거래일(당일 포함) 최고 − 1, 시장 구분 없음. 가능하면 **업종 2~3개를 독립 재계산**(네 11/8 방법으로)해 `docs/sector_dd.json` 과 대조. 특히: 최근 90거래일만 읽는데(`LOAD_DAYS`) 지수 시작점을 바꿔도 dd 가 불변인지 · 종목 < 10 인 날을 빼면 그 날이 '없는 날' 이 되어 20일 창이 달력상 늘어나는 문제 · `change_pct` NULL 처리 · 보충표 `daily_ohlcv_extra` 미포함(의도: 연구와 같게) 이 맞는지.
3. **세 목록 차이 수**(`filter.html renderListsNote`): 성적표 상위10 = `final_score_v3` 내림차순, 동점은 ticker 오름차순 — `paper_engine.picks_from_scores` 와 같은가(네가 81행 차이를 셀 때 쓴 규칙과도). 모의 계좌 = CSV 의 `dilution_60d` 비어있지 않음 제외 — `paper_account.py` 의 `dilution_flag` 제외와 **같은 집합인가**(다르면 화면 문구 "이 화면 자료 기준" 이 충분한지). 화면 권고10 제외 조건(ocf_pattern 이중적자·밸류트랩의심, risk_level 주의·위험)이 `notify_telegram` 폴백과 아직 같은가.
4. **문구**: 배지·툴팁·배지 뜻·권고 상자·성적표 도움말이 "경고·위험 아님 · 향후 수익 미확인" 을 지키는가, 사용자가 '사라/팔아라' 로 읽을 표현이 있는가. "2026-06~09 실측: 나쁘지 않았음(차이 구간이 0 을 걸침)" 이 네 숫자(+3.53 [−2.71, +5.76])와 어긋나지 않는가.
5. **스냅샷**: 날짜 = `daily_ohlcv` 최대 날짜 — 배치 순서(universe_ohlcv 가 먼저)에서 그날이 맞는지, 09:00 이전 재실행·주말 수동 실행 때 어느 날짜로 저장되는지(이중 저장·덮어씀이 해가 되는 경우). `cleanup.py` 회전·`.gitignore` 에 걸리지 않는지. 2027 연구에서 이 스냅샷으로 "당시 분류" 를 쓰려면 더 남겨야 할 게 있는지(예: 분류 바뀐 종목 목록).
6. **화면 안전**: `sector_dd.json` 이 없거나 늦게 올 때(fetch 경쟁) 화면이 깨지지 않는지 · 업종 열 숨김/표시 전환 때 배지 중복 · 375px.

## 2. 답 양식
항목 6개 표(맞음/틀림+어디/못 가름 · 한 줄 근거) + 독립 재계산 결과(했으면 업종·dd20·dd60·차이) + **고쳐야 할 것 순서대로 ≤ 5줄**(없으면 "없음"). 코드 수정 제안은 "제안" 으로만.
