# AGENTS.md — Codex(및 다른 코딩 에이전트)용 규칙 (2026-09-13)

이 저장소의 규칙 정본은 `CLAUDE.md`다. **먼저 `CLAUDE.md`를 읽고 그대로 따른다.** 아래는 그중 에이전트가 특히 어기기 쉬운 것만 다시 적은 것.

## 지난 작업 이어받기 (`worklog/`, 2026-10-03 도입)
- 작업을 시작하기 전에 `worklog/README.md` 를 열고 **목록 맨 위(가장 최근) 기록 1건**을 읽는다. 지난 세션에 무엇을 왜 어떻게 했는지, 사용자가 무엇을 정했는지, 무엇이 남았는지가 적혀 있다.
- 기록과 실제(코드·git 이력)가 다르면 실제가 맞다.
- 이 에이전트의 기본 산출물은 `research/handoff/REPLY_*.md` 다. 사용자 승인으로 저장소 파일을 직접 고친 세션이었다면, 끝날 때 `worklog/README.md` 의 양식대로 기록 1건을 쓰고 목록에 한 줄 추가한다(검토·재현만 했다면 REPLY 로 충분하다).

## 절대 규칙
- **평일(월~금) 20:10~22:30(KST)에는 파일·DB를 건드리지 않는다.** 작업 스케줄러 배치가 도는 시간이다(월~금만 등록). 토·일은 배치가 없으므로 이 제한이 없다. 애매하면 `logs/auto_run_YYYYMMDD_2010.log`가 그날 생겼는지로 판단한다. (2026-11-15 사용자 결정) 그날 로그(자동 `auto_run_*`·수동 `manual_run_*` 모두)의 **마지막 실행**에 끝 줄 `[OK] Done.  End:` 가 찍히고 배치의 python 프로세스가 없음을 확인한 뒤에는 이 시간대에도 작업해도 된다 — 끝 줄이 없거나 애매하면 도는 중으로 보고 22:30 까지 읽기만.
- (2026-11-15) 무엇을 먼저 읽을지는 `WHERE.md`(분야 안내 — 일의 종류 → K·D·P 번호와 정본, 같이 볼 한계). 날짜·조건이 붙은 약속은 `PROMISES.md`, 판정 전 대조는 `VERDICT_CHECKLIST.md`. 검색 0건은 '결론 없음'이 아니라 '미확인'으로 적는다.
- (2026-11-15, D40) 사용자 결정의 원문은 `DECISIONS_LOG.md`(번호로 찾아봄 — 덧붙이기만), `DECISIONS.md` 에는 짧은 한 줄. D01~D39 는 아직 `DECISIONS.md`·`KNOWLEDGE_ARCHIVE.md` 가 원문. `python tests/test_knowledge_sheets.py` 가 번호 어긋남(FAIL)·자리 부족(WARN)을 알린다 — 보이면 사용자에게 알린다.
- `history.db`·`../dh-q7m3k-data/ohlcv.db`는 **읽기 전용**으로만 연다: `sqlite3.connect("file:...?mode=ro", uri=True)`. 쓰기·스키마 변경 금지.
- `.env`·`kis_token.json`·토큰·키는 읽지도 출력하지도 않는다.
- 배치·수집기(`run_*.bat`, `dart_events.py`, `kis_flows.py`, `universe_ohlcv.py` 등)는 사용자가 명시적으로 시킬 때만 실행한다.
- 점수·판정·게이트 코드(`v3_rescore.py`, `lowvol_score.py`, `wu_score.py`, `leaderboard.py`, `freeze_scores.py`, `run_and_diversify.py`의 게이트)는 **고치지 않는다.** 필요하면 제안만 문서로.
- 새 모델·판정·은퇴는 사용자 승인 + 사전등록 문서 없이는 하지 않는다.
- `.bat`은 ASCII만, 최소 삽입. 연구 산출물은 `research/`에만 둔다(루트 금지). `docs/`는 배치가 자동 커밋하니 손대지 않는다.
- **용량 규칙(2026-10-04)**: 연구 중간 파일(npz·parquet·db·10MB 넘는 csv)은 커밋 대상이 아니다(`.gitignore` 의 `research/**` 규칙). 계산이 끝나 보고서에 숫자를 옮겼으면 **큰 중간 파일은 지우고** 다시 만드는 명령만 보고서에 남긴다. 한 연구 폴더가 50MB 를 넘으면 보고서 끝에 크기와 지워도 되는 파일을 적는다.

## 이 에이전트의 역할 (Claude Code와의 분업)
- Claude Code가 구현·운영을 맡는다. Codex는 **독립 검토·재현**을 맡는다: 같은 데이터로 숫자를 다시 계산해 보고, 문서의 허점을 찾고, 코드에서 버그를 찾아 **보고**한다.
- 저장소 파일을 수정하려면 반드시 승인 요청 모드로. 기본 산출물은 `research/handoff/REPLY_*.md` 한 파일이다.

## 주고받기 규약 (`research/handoff/`)
- Claude가 `REQUEST_<번호>_<주제>.md`를 쓴다. 거기 적힌 질문·형식·제약대로만 작업한다.
- 답은 `REPLY_<같은 번호>_<주제>.md`에 쓴다. 실측(직접 계산·확인한 것)과 추정을 구분해 표기하고, 계산에 쓴 코드가 있으면 `research/handoff/code_<번호>_*.py`로 같이 둔다.
- 요청 밖의 일은 하지 않는다. 의심스러운 점은 REPLY의 "질문" 절에 적는다.
