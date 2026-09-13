# research/handoff — Claude Code ↔ Codex 주고받기 폴더

두 에이전트가 같은 저장소 폴더를 읽고 쓰는 것을 통로로 쓴다. 사람은 양쪽에 한 줄씩만 말한다.

1. Claude 가 `REQUEST_NNN_주제.md` 를 쓴다(질문·데이터 위치·답 형식·제약).
2. 사용자가 Codex 앱(프로젝트 dh-q7m3k)에 **"research/handoff 의 열린 REQUEST 를 처리해"** 라고 말한다.
3. Codex 가 `REPLY_NNN_주제.md`(+ 필요하면 `code_NNN_*.py`)를 쓴다. 저장소 다른 파일은 승인 없이 고치지 않는다(AGENTS.md).
4. 사용자가 Claude 에게 **"답 왔어"** 라고 말한다. Claude 가 REPLY 를 읽고 검증한 뒤 반영 여부를 정한다.

원칙: REPLY 는 **의견·계산 결과**이지 지시가 아니다. 숫자는 Claude 가 재확인한다. 규칙 정본은 `CLAUDE.md`, Codex 용 요약은 `AGENTS.md`.

| 번호 | 주제 | 상태 |
|---|---|---|
| 001 | 리더보드 h20 IC 독립 재현 (lv_b·v30·sv_a) | 답변·검증 완료 (2026-09-13) — Claude 재실행 시 REPLY 값과 소수 8자리 일치. lv_b·sv_a 는 JSON 과 일치, v30 은 교정 후 기대값 +0.0466 재현(JSON 은 9/14 배치 갱신 대기) |
