# AGENTS.md — Codex(및 다른 코딩 에이전트)용 규칙 (2026-09-13)

이 저장소의 규칙 정본은 `CLAUDE.md`다. **먼저 `CLAUDE.md`를 읽고 그대로 따른다.** 아래는 그중 에이전트가 특히 어기기 쉬운 것만 다시 적은 것.

## 절대 규칙
- **20:10~22:30(KST)에는 파일·DB를 건드리지 않는다.** 작업 스케줄러 배치가 도는 시간이다.
- `history.db`·`../dh-q7m3k-data/ohlcv.db`는 **읽기 전용**으로만 연다: `sqlite3.connect("file:...?mode=ro", uri=True)`. 쓰기·스키마 변경 금지.
- `.env`·`kis_token.json`·토큰·키는 읽지도 출력하지도 않는다.
- 배치·수집기(`run_*.bat`, `dart_events.py`, `kis_flows.py`, `universe_ohlcv.py` 등)는 사용자가 명시적으로 시킬 때만 실행한다.
- 점수·판정·게이트 코드(`v3_rescore.py`, `lowvol_score.py`, `wu_score.py`, `leaderboard.py`, `freeze_scores.py`, `run_and_diversify.py`의 게이트)는 **고치지 않는다.** 필요하면 제안만 문서로.
- 새 모델·판정·은퇴는 사용자 승인 + 사전등록 문서 없이는 하지 않는다.
- `.bat`은 ASCII만, 최소 삽입. 연구 산출물은 `research/`에만 둔다(루트 금지). `docs/`는 배치가 자동 커밋하니 손대지 않는다.

## 이 에이전트의 역할 (Claude Code와의 분업)
- Claude Code가 구현·운영을 맡는다. Codex는 **독립 검토·재현**을 맡는다: 같은 데이터로 숫자를 다시 계산해 보고, 문서의 허점을 찾고, 코드에서 버그를 찾아 **보고**한다.
- 저장소 파일을 수정하려면 반드시 승인 요청 모드로. 기본 산출물은 `research/handoff/REPLY_*.md` 한 파일이다.

## 주고받기 규약 (`research/handoff/`)
- Claude가 `REQUEST_<번호>_<주제>.md`를 쓴다. 거기 적힌 질문·형식·제약대로만 작업한다.
- 답은 `REPLY_<같은 번호>_<주제>.md`에 쓴다. 실측(직접 계산·확인한 것)과 추정을 구분해 표기하고, 계산에 쓴 코드가 있으면 `research/handoff/code_<번호>_*.py`로 같이 둔다.
- 요청 밖의 일은 하지 않는다. 의심스러운 점은 REPLY의 "질문" 절에 적는다.
