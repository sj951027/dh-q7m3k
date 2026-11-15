# REQUEST — 11/15 에 적용한 것 점검: 잘 들어갔나, 문제 될 곳은 없나 (2026-11-15)

답은 `research/handoff/REPLY_20261115_applied_review.md` **한 파일**로. 다른 파일은 만들거나 고치지 말 것(읽기만 — 코드·docs·DB·hook 수정 금지, 배치·수집기 실행 금지). 규칙은 `AGENTS.md`.
분량: 결론 5줄 먼저, 전체 A4 2쪽 안쪽. **결함은 파일·줄·재현 방법·심각도(높음/중간/낮음)** 로.

## 무엇을 점검하나
11/15 의 커밋 둘(`git log -2` — `906f05f` 와 그 다음 커밋)에 들어간 것. 설계 근거는 `research/DESIGN_20261115_knowledge_scale.md` §7, 당신의 앞 답 두 건(`REPLY_20261115_structure_review.md`·`REPLY_20261115_knowledge_scale.md`)과 그 대조(`CHECK_20261115_*.md`).

## 부탁 (우선순위 순 — 한도가 모자라면 위에서부터, 못 한 것은 '안 함'으로)
1. **기억 없는 시험(가장 중요)**: `research/RECALL_TESTSET_20261115.md` 의 Q1~Q10 을, **`AGENTS.md` 와 `WHERE.md` 가 가리키는 길만 따라가서** 답해 볼 것. 질문마다 '꼭 나와야 하는 것'을 실제로 찾았는지(찾은 경로 한 줄) · 못 찾은 것 · 표에는 없지만 꼭 있어야 했던 근거 · `WHERE.md` 에 보탤 낱말. 묶음 자체가 틀렸으면(꼭 나와야 하는 것이 잘못 적힘) 그것도.
2. **감시 장치** `tests/knowledge_guard.py`(읽기만, 실행은 `python tests/test_knowledge_guard.py` 정도는 가능 — 임시 폴더만 쓴다):
   - `batch_done`·`run_mode`: 끝 줄(`Done.  End:`)로 배치 종료를 판단하는 것이 틀릴 경우 — 로그 이름이 `_2010` 이 아닌 날, 수동 실행 로그(`manual_run_*`), 배치가 실패로 끝난 날(끝 줄이 찍히나 — `run_all_and_diversify.bat` 꼬리 확인), 재실행한 날(로그 2개), 자정 넘김, 로그 인코딩.
   - 읽기 전용 경로가 정말 쓰기·git 을 안 하나(`start(readonly=True)` 가 부르는 것 전부).
   - `parse_promises`·`promise_lines`: 표 형식이 조금 어긋났을 때(칸 수·`|` 가 든 글·`≈` 날짜·날짜 2개) 조용히 빠지는 행이 있나. 실제 `PROMISES.md` 가 전부 읽히나.
   - 세 자리 번호·카드 인식(`CARD_DIR`): 카드가 0장인 지금과 K42 가 생긴 뒤 둘 다 맞게 도나. 카드와 `KNOWLEDGE.md` 색인 줄이 어긋나는 것(카드만 있고 색인 없음, 번호 중복)을 잡는 검사가 **없다** — 넣어야 하나, 어디에.
3. **문서끼리 어긋남**: `PROMISES.md` 의 각 행이 '나온 곳'의 원문과 맞나(특히 P04 v32a ≈12/18 셈, P05·P06 ls_t1, P07 lv_e 2차 창) · `VERDICT_CHECKLIST.md` 대조표 15줄이 `VERDICT_RULES.md`·각 PREREGISTER 와 어긋나거나 빠뜨린 의무가 있나 · `WHERE.md` 의 번호가 실제 그 내용의 행을 가리키나(잘못 가리킨 번호 목록) · `CLAUDE.md`·`AGENTS.md` 의 바뀐 배치 시간 문장이 서로 같은 뜻인가.
4. **`research/PRINCIPLES_20261115.md`**: 설명 후보 E1~E5 와 질문 A1~A6 에서 **근거 번호가 그 말을 실제로 뒷받침하지 않는 곳**, 지나친 일반화, '같은 표본' 표시가 빠진 곳. 질문 가운데 이미 답이 있는데 모르고 적은 것.
5. **sv_b 판정문 추기**(`VERDICT_20261113_sv_b.md` 맨 아래, 계산 `research/verdict_sv_b_addendum_20261115.py`, 산출 `research/out_verdict_sv_b/addendum_20261115.txt`): 자료를 판정 당시로 자르는 방식(가격·run 을 20261112 까지)에 구멍이 있나(잘리지 않는 표, `leaderboard` 가 따로 읽는 것). 한도가 남으면 10/14 제외 값·자리바꿈 값을 독립으로 다시 계산해 한 줄로 — 자료는 저장소 `history.db` 와 `C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k-data\ohlcv.db`, 둘 다 `mode=ro`. 판정 스크립트를 그대로 실행하지 말고 계산은 `handoff/code_20261115_*.py` 로 따로.
6. **놓친 것**: 오늘 변경이 만든 새 위험 최대 3개(예: 새 파일 5개가 또 낡는 길, 읽을 것이 늘어난 것, 세 장이 여전히 상한 — DECISIONS 15,000/15,000B).

## 답 형식
- 맨 위 결론 5줄(가장 심각한 것부터). 그 아래 부탁 번호대로.
- 문장마다 **실측**(파일·줄·실행 결과)과 **제안**(판단)을 구분. 고칠 것은 "어느 파일 어느 줄을 무엇으로"까지 적되 직접 고치지 않는다.
- 판정 규칙·0-diff·배치 시간·하드 경계를 느슨하게 하는 것은 제안이 아니다. 모르는 것·확인 못 한 것은 그렇게 적을 것.
