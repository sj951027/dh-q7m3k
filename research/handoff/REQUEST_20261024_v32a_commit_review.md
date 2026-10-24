# REQUEST — 커밋 142077b 전체 점검 (v32a 등록·배선 + 10/23 연구) (Codex · 2026-10-24 작성 · 평일 20:10~22:30 밖에서만 실행)

> 이 파일 하나가 요청 전부다. 답: `research/handoff/REPLY_20261024_v32a_commit_review.md` + 필요하면 `code_20261024_v32a_commit_review.py`. 끝나면 멈추고 핵심 5줄로 보고.
> 대상: `git show 142077b`(50파일 — 코드 8 · 테스트 2 · 문서 · docs 3 · 연구 다수). 정본: `PREREGISTER_v32a.md` · `VERDICT_RULES.md` · `patch_note/20261024_v32a_register.md` · `worklog/2026-10-24_v32a_register.md`.

## 규칙
- AGENTS.md·CLAUDE.md 를 따른다. **고치지 말고 찾기만**(코드·docs·DB 수정 금지). DB 는 전부 `mode=ro`. 배치·수집기·`leaderboard.py`·`build_*.py` 를 docs 에 쓰는 방식으로 실행 금지(필요하면 출력 경로를 임시 폴더로 돌리거나 쓰기를 막고 실행).
- 찾은 것마다 **P1(점수·판정·적재가 틀어짐) / P2(표시·기록이 틀어지거나 월요일 배치에서 깨질 수 있음) / P3(문서·주석 불일치)** 와 파일:줄 · 재현 방법 · 고칠 방향 한 줄. 실측과 추정 구분. 없으면 "없음"도 결론.
- 묻지 말고 이어서 한다.

## 점검할 것
1. **v30 0-diff 재현**: 커밋 전(`142077b~1`) `v3_rescore.py` 와 현재 것으로 history.db `stage3_final` 전 run 을 v30 스펙으로 재점수해 완전 일치하는지(Claude 결과: 325셀·159,250행 다른 칸 0, `research/v32a_zero_diff_20261024.txt`). v30·v31a~g spec_hash 가 그대로인지.
2. **v32a 규칙이 사전등록과 같은지**: `PREREGISTER_v32a.md` §1(셀 = run×market 의 stage3_final 전체 행 · `amt_avg_1m_억` 중앙값 초과 또는 결측 → main_candidate=False + `final_score_v3`·`entry_score` −999 · 같음은 남김) ↔ `v3_rescore.rescore()` 실제 동작. 하드 제외·E4·E5(섹터 중립화)·정렬과 겹칠 때 순서 문제, 인덱스 정렬(merge 뒤), dtype, grade/bucket 에 생기는 부작용.
3. **월요일 배치 경로**: `shadow_run.py`(v32a 만 순회) → `v32a_archive/v32a_{mkt}_{run}.csv` → `freeze_scores.py --latest`(ARCHIVE_MAP·`_latest_run`·spec_hash 기록) → `v3_scores`. 등록 전 run 이 백필로 들어갈 길이 있는지. `leaderboard.py`·`build_scoreboard.py`·`build_cross_sim.py`·`notify_telegram.py`·`notify_verdict_ready.py`·`model_race.py`·`checkup.py` 가 v32a 행이 생겼을 때 깨지거나 v3 분모·표시가 의도와 다르게 바뀌는 곳.
4. **등록일 일관성**: 20261026 이 적힌 곳(checkup.REG_DATE · build_cross_sim · docs/models_registry.json · PREREGISTER §2 · MODELS_LEDGER)과 빠진 곳.
5. **관측 페이지 `build_v32a_page.py`**: D20 계산이 PREREGISTER §2 주지표 정의(상위 10 = 점수 내림차순·동점 종목코드 · ENTRY_LAG=1 · h20 · 본표 가격 · 보유 중 정지·상폐 = 마지막 가격 · 두 시장 평균 · 게이트·앵커 중복 제거)와 같은지. 특히 `close.ffill()` 이 진입 가격에 쓰이지 않는지, 앵커 t 가 비거래일 run 일 때, h20 미완결 처리, 표본 5 미만 구간. 행이 없을 때·한 시장만 있을 때·stage3 가 비었을 때 비치명으로 끝나는지. 페이지 문구가 사실과 맞는지(쉬운 말·'매수 추천 아님').
6. **bat·기타**: `run_all_and_diversify.bat` 추가 3줄이 ASCII·CRLF·실패 시 FAILED 기록 관례와 맞는지 · `.gitignore` · `docs/leaderboard.html` 링크 · `docs/models_registry.json` JSON 형식·소비자 영향 · 새 테스트 `tests/test_v3_models_rules.py` 가 실제로 지켜야 할 것을 지키는지(빠진 검사).
7. **연구 문서 숫자 대조**(표본만): `research/RESEARCH_pick_amt_recheck_20261023.md` §1·§3 · `RESEARCH_etf_sleeve_10y_20261023.md` §1 · `handoff/CLAUDE_20261023_lowamt_blind_crosscheck.md` §1 의 숫자가 각 스크립트 출력(`out_pick_amt/summary.csv`·`out_etf_sleeve/summary.csv`·`reconcile_codex_lowamt_20261023.py` 실행)과 맞는지. 다른 곳 목록.
8. **사전등록 자체의 허점**: 결과를 본 뒤 바꿀 여지가 남은 곳(정의가 모호한 단어), 해석표 6칸이 빠짐없이 갈리는지, 분모 8 이 VERDICT_RULES 와 맞는지, 체결 한도 각주(§4-1)가 라벨에 새어 들어갈 길.

## 하지 않는 것
코드·문서·DB 수정 · 새 모델 제안 · 전략 수익 탐색 · 점검 항목 밖 격자.
