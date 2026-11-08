# 2026-11-08 (저녁 3) — 지식 세 층 자동 감시 hook — 2026.11.13

## 뭐가
- `.claude/settings.json`(새, 저장소에 커밋): Claude Code hook 두 개 → `tests/knowledge_guard.py`.
  - **SessionStart** `--start`: 세 장 검사(`test_knowledge_sheets`) + 마지막 정리 뒤 며칠·worklog 몇 건·세 장이 안 가리키는 새 연구/판정 파일 목록을 세션 첫 문맥에 넣는다. 30일 또는 worklog 10건 넘으면 "이번 세션 첫 일로 세 장 정리 제안" 지시가 붙는다. 막지 않는다.
  - **Stop** `--stop`: 기록 층(worklog/·research/*.md·handoff/CHECK_*·VERDICT_*·PREREGISTER_*·patch_note/)이 바뀌었는데 세 장(KNOWLEDGE·DECISIONS·PITFALLS)이 하나도 안 바뀌었고, 바뀐 worklog 에 `지식 층: 변경 없음` 선언도 없으면 끝내기를 **한 번** 막고 이유를 돌려준다.
- `.gitignore` 에 stamp 파일 · CLAUDE.md 마무리 7 에 "장치가 지킨다" 한 줄.

## 왜
사용자: 세션마다 세 장 갱신·월 1회 정리라는 두 조건을 사람이 기억하지 않고 자동으로, 복잡하거나 오래 걸리는 부작용 없이. 지침(CLAUDE.md)만으로는 빠뜨릴 수 있어 hook 으로 강제.

## 부작용을 막은 설계(실측)
- **빠름**: 시작 0.34초·끝 0.31초(git status + 파일 3개 읽기, DB·네트워크 없음). timeout 30초.
- **조용함**: 질문만 한 세션·코드만 고친 세션은 기록 층이 안 바뀌므로 아무 일도 없다. 세 장을 고쳤으면 통과. 같은 상태로는 한 번만 막는다(stamp). Claude 가 이미 막힘에 응답 중(`stop_hook_active`)이면 안 막는다.
- **빠져나가는 길**: 정말 결론·결정·함정이 없던 세션은 worklog 에 `지식 층: 변경 없음(이유)` 한 줄이면 통과 — 선언을 남기게 해서 "안 적음"과 "없음"을 구별.
- **안전**: 읽기 전용(git 작업본), 예외가 나면 통과(감시가 작업을 세우지 않음).
- 시나리오 6개 시험: 기록만 바뀜 → 막음 / 같은 상태 두 번째 → 통과 / 세 장도 바뀜 → 통과 / 기록 층 아닌 파일 → 통과 / stop_hook_active → 통과 / 변경 없음 → 통과.

## 확인 남은 것
- ~~이 세션은 `.claude/` 가 없던 채 시작해 hook 이 실리지 않았다 → 새 세션에서 확인~~ → **22:07 같은 세션 resume 에서 SessionStart 실림(실측)**: 첫 문맥에 "[지식 세 층 감시 · 세션 시작]" + 세 장 OK · 후보 0, `.claude/guard/<session>.json` 생성. Stop 은 그 뒤 첫 끝내기부터 실험. 안 실리면 settings 경로·`CLAUDE_PROJECT_DIR` 부터.

## 영향 범위
Claude Code 작업 환경만. 점수·판정·게이트·배치·docs 무변경.

## 후속 (같은 날 저녁, Codex 검토 `REPLY_20261108_knowledge_guard.md` → `CHECK_20261108_knowledge_guard.md`, 지적 전부 맞음)
- **구멍 메움**: 설명문 속 `지식 층: 변경 없음` 문자열이 면제로 잡히던 것(실제 worklog 에 있어 전부 면제되던 상태) → 독립된 한 줄 + 비어 있지 않은 이유만 · 이전부터 미커밋인 세 장이 전부 통과시키던 것 → **세션 시작 해시**(`.claude/guard/<session_id>.json`, resume/compact 땐 처음 값 유지)와 끝에서 비교, 시작 해시 없으면 git 기준 · stamp 키를 파일명+HEAD → 세션별 + 기록 내용 해시.
- **부작용 차단**: 평일 20:10~22:30 엔 아무것도 안 함 · `-B`(캐시 안 씀) · git 10초 제한 · `research/large_verdict_status.md`(배치 산출물) 제외 · `age >= 30` · **끄는 법** = `KNOWLEDGE_GUARD_OFF=1` 로 Claude Code 를 시작하거나 `.claude/settings.json` 의 두 command 항목 삭제.
- **문구**: "누락 후보 알림이지 반영 보증 아님" · 정리 지시는 Codex 제안문(허용된 요청·배치 밖에서만, 완료/남김 기록, 전체 끝났을 때만 날짜 갱신, 새 결정·판정·등록 안 함) · worklog 에 `지식 반영: K##/D##` 로 잇기.
- **실측**: 시작 0.41초·끝 0.32초. 시나리오: 선언 정규식 5건(백틱·문장 속·빈 이유·자리표시 → 면제 아님, 독립 줄 → 면제) · 배치 창(월 20:30 off, 일 20:30 on, OFF env) · 세션 흐름(start → resume 때 처음 해시 유지 → 기록 dirty·세 장 그대로 → 막음 → 같은 내용 두 번째 → 조용 → 세 장 바뀜 → 통과 → 시작 상태 없는 세션은 git 기준 → 통과 → stop_hook_active → 통과). `run_tests.py` 통과.
- 나중(12월 초 첫 정리 때): 마지막 검토 HEAD+기록 해시 기준 후보 · worklog 절 ↔ D## 연결 · 정리 진행 상태(완료/남김). 상한 규칙 한 줄은 CLAUDE.md 마무리 8.

