# 2026-11-15(일) — Codex 두 번째 의견 대조 → 약속 장부·판정 절차서·저녁 알림 + 배치 시간 규칙 변경 + sv_b 판정문 추기

## 요약
11/13 근본 점검(`research/REVIEW_20261113_structure.md`)의 구조 제안을 Codex 에 물었고(답 `handoff/REPLY_20261115_structure_review.md`), 답의 사실 주장을 대조한 뒤(`handoff/CHECK_20261115_structure_review.md`) 순서를 바꿔 적용했다: **판정 전 약속 대조가 먼저**. 새 파일 `PROMISES.md`(약속 장부)·`VERDICT_CHECKLIST.md`(판정 절차서), 감시 장치의 저녁 알림·약속 기한 알림, 배치 시간 규칙 변경(D39), sv_b 판정문 추기 ①. 판정·점수 0-diff. 이어서 사용자가 "장기적으로 용량을 크게 확보하고 계속 똑똑해지는 구조"를 물어 설계 메모와 Codex 요청서를 썼다(답 대기).

## 시간순 흐름
- 사용자 "상한이면 줄이는 방법뿐인가" → "이게 최선인가" → REVIEW §6 에 고친 안 → "Codex 에 적절한지 물어보게" → 요청서 `handoff/REQUEST_20261115_structure_review.md`(눈가림 순서).
- **Codex 답 대조**(CHECK §1): 주장 9건 중 8건 맞음 — 시작 알림이 상태 파일 삭제·git 읽기도 한다 · 끝 검사는 '무언가 적었다'만 본다 · **판정 도래 알림이 판정 기록 있는 모델·대형·주도주를 빼서 12월 말 3건 중 2건(lv_e 2차 창·ls_t1)이 안 뜬다** · **sv_b 판정문이 자리바꿈 검정을 "노이즈라" 생략**(규약 각주 ④·D16 위반에 가까움 — 판정 스크립트 `--perm` 기본값 0) · K11·K37 은 닫힌 축이 아님(내 14행 분류가 거칠었다) · 눈가림이 worklog 요약으로 깨졌다. 1건 재현 안 됨(`build_large_report.py` L407 문구 — 없다).
- 사용자 "그렇게 진행" + **"배치 종료 뒤엔 가능으로 바꿔 줘"**(D39).
- 적용(patch_note `20261115_promises_checklist_guard.md`, 2026.11.17):
  - `PROMISES.md` 15건(P01 바깥 축 재현은 기한 지남으로 뜬다 · P04 v32a ≈12/18 · P05 ls_t1 h60 ≈12/28 · P07 lv_e 2차 창 ≈12/30 · P06 ls_t1 순위 상관 정의는 "첫 창이 이미 닫혔는데 지금 정해도 되나"부터 사용자 확인).
  - `VERDICT_CHECKLIST.md`: 쓰기 전 약속 모으기 → 대조표 15줄(결과 위치 또는 해당 없음(사유) — "생략" 없음) → 쓴 뒤 갱신 목록.
  - `tests/knowledge_guard.py`: `run_mode`(off/readonly/full) · 배치 도는 중엔 읽기 전용 알림 · 약속 기한 알림 · `> 닫음(` 줄. 새 테스트 `tests/test_knowledge_guard.py` 26체크.
  - `CLAUDE.md`(실행 주의·읽을 것 0-2) · `AGENTS.md` · `build_large_report.py` L406 문구(+ 산출물) · 10/31 Codex 요청서에 닫음 줄.
- **sv_b 보충 계산** `research/verdict_sv_b_addendum_20261115.py`(판정 스크립트 무수정, 자료를 20261112 까지로 잘라 실행 → 주지표 n=19·+0.0025 재현 확인): 10/14 앵커 제외 n=18 **−0.0009 [−0.0231, +0.0207]** · 짝 **−0.0928 [−0.1215, −0.0645]** → 판정문 추기 ①. 자리바꿈 2,000회(같은 날 끝남): sv_b 실제 +0.0025 는 뒤섞은 분포의 **54.9 백분위**, 짝 −0.0891 은 **0.0 백분위**(짝 열위는 잡음 밖), 'CI>0 ∧ 주별 ≥60%' 묶음이 뒤섞은 점수에 통과를 준 비율 34.8% → 추기 ②, P16 완료.
  - 처음엔 자르지 않고 돌렸다가(11/13 배치분이 섞여 표본이 하루 늘어남) 멈추고 다시 띄웠다 — 그 프로세스만 PID 로 종료.
- 세 장: D39 추가 · 함정 2줄 추가. **상한 때문에 다섯 줄을 줄였다**(D37·D38 · heredoc/taskkill 두 줄을 한 줄로 · `.codex/hooks.json` 줄 삭제 — D36 이 같은 내용 · §B 문구 3곳) — 원문은 `KNOWLEDGE_ARCHIVE.md`. 최종 KNOWLEDGE 23,774 · DECISIONS 14,980 · PITFALLS 4,923.
- 사용자 새 질문 "용량을 획기적으로 확보하고 이전 결과에서 더 좋은 아이디어가 나오는 구조는? Codex 에도 물어보게" → 설계 메모 `research/DESIGN_20261115_knowledge_scale.md` + 요청서 `handoff/REQUEST_20261115_knowledge_scale.md`. 메모 내용은 Codex 답이 올 때까지 여기 적지 않았다(눈가림). **답이 온 뒤 요약**: 내 안 = 색인(매번)·카드(그때그때)·기록·원리 네 층. Codex 가 고친 것 = 전 결론 색인도 300행이면 다시 찬다 → 매번 읽는 것은 분야 안내, 결론 목록은 분야별 · 원리는 설명 후보이지 자리 확보 수단이 아님 · 불러오기는 손으로 여는 것부터, 공통 접근을 앱 전용 장치에 두지 않음 · 판정 3건에 걸린 것은 12월 뒤에 옮김 · 넓히는 조건은 시험 묶음 누락 0. 사실 주장 5건 맞음(검사 장치가 두 자리 번호만 읽음 등). Claude Code 기능은 문서 기준으로 확인(메모 §5).

## 사용자 결정
- D39: 배치 종료를 확인한 뒤에는 평일 20:10~22:30 에도 작업 가능 · 구조 보완은 Codex 대조 뒤 순서로.

## 바뀐 것
- 새 파일: `PROMISES.md` · `VERDICT_CHECKLIST.md` · `tests/test_knowledge_guard.py` · `research/verdict_sv_b_addendum_20261115.py` · `research/out_verdict_sv_b/addendum_20261115.txt` · `research/REVIEW_20261113_structure.md` · `research/DESIGN_20261115_knowledge_scale.md` · `research/handoff/REQUEST_·REPLY_·CHECK_20261115_structure_review.md` · `research/handoff/REQUEST_20261115_knowledge_scale.md` · `patch_note/20261115_promises_checklist_guard.md` · 이 기록.
- 고친 파일: `tests/knowledge_guard.py` · `tests/run_tests.py` · `CLAUDE.md` · `AGENTS.md` · `DECISIONS.md` · `PITFALLS.md` · `KNOWLEDGE_ARCHIVE.md` · `VERDICT_20261113_sv_b.md`(추기만) · `build_large_report.py` · `docs/_large_obs.html` · `research/handoff/REQUEST_20261031_review_flows_and_map.md` · `patch_note/README.md` · `worklog/README.md` · `worklog/2026-11-13_audit_followup.md`.
- 커밋: 아직 안 함.

## 검증
- `python tests/run_tests.py` 전체 통과(새 테스트 포함). 시작 알림을 직접 불러 약속 줄 확인.
- 확인 못 한 것: 실제 평일 배치 시간대의 읽기 전용 알림(합성 로그로만) · 고친 생성 코드의 실제 재생성(11/16 배치 뒤 — P02) .

## 남은 일
1. (끝) 자리바꿈 추기 ② — 시총 5분위 감도만 미실시.
2. 장기 구조: Codex 답 대조 끝(`handoff/CHECK_20261115_knowledge_scale.md`) → 설계 메모 §7 에 고친 안 — **사용자 결정 대기**(지금 할 8가지: 분야 안내 표 · 과거 질문 시험 묶음 · 검사 장치 세 자리 번호·카드 인식 · 새 결론부터 카드 · 실험 끝 세 줄 · 원리 비교 메모 · '열린 것' 절 중복 제거 · 기대 기록 묶음 표시 / 판정 뒤: 옛 행 카드화).
3. P06: ls_t1 순위 상관 정의 — 원장은 "첫 창이 닫힌 뒤엔 바꾸지 않는다"인데 첫 창이 이미 닫혔다. 지금 정해도 되는지부터 사용자에게.
4. P04: v32a 유효 앵커 40 은 셈으로 ≈12/18(원장 문구는 "12월 말~2027-01") — 판정 준비를 12월 둘째 주로 당긴다.
5. 미룬 구조 항목: 차단 hook · 페이지↔등록 표 대조 테스트 · 근거 번호 경고 · 복사한 11년 틀 2개 교체.
6. 종전: DECISIONS §B 14묶음 · AUDIT §3 다의 화면 4건(텔레그램 쉬운 말 표 등).

## 다음 세션 시작점
- 시작 알림의 "약속 기한 지남·임박" 줄부터 본다(P02 11/16 배치 뒤 문구 확인). 그다음 Codex 답 대조.

## 작업 요령
- 판정 뒤 보충 계산은 자료를 판정 당시로 자르고 주지표가 재현되는지부터(`VERDICT_CHECKLIST.md` §4).
- 눈가림 요청을 보낼 때는 worklog 에 내 안을 적기 전에 보낸다 — worklog 는 Codex 도 먼저 읽는다.
- 표를 낱말로 기계 분류한 결과는 어림이지 분류가 아니다(K11·K37).

지식 반영: D39 · PITFALLS 2줄(의무 항목 생략 · 낱말 기계 분류).

## 장기 구조 '지금 할 8가지' 진행표 (사용자 승인 11/15 오후 — 멈추면 여기서 이어서, 정본 DESIGN_20261115_knowledge_scale §7)
- [x] 7 `KNOWLEDGE.md` '열린 것' 절 중복 제거(원문 보관소)
- [x] 3 검사 장치: 세 자리 번호 · 카드 폴더 인식
- [x] 1 분야 안내 표 `WHERE.md` + CLAUDE.md·AGENTS.md 에서 가리킴
- [x] 4 카드 양식 `knowledge/README.md`(새 결론 K42~ 부터 — 아직 카드 0장)
- [x] 2 과거 질문 시험 묶음 `research/RECALL_TESTSET_20261115.md`
- [x] 5 실험 끝 세 줄 규칙(CLAUDE.md 마무리 9)
- [x] 6 원리 비교 메모 첫 판 `research/PRINCIPLES_20261115.md`
- [x] 8 기대 기록 묶음 표시(11/15 낮 FORECASTS 주석으로 끝)
- [x] 마무리: 테스트 전체 통과 · patch_note 2026.11.18 — 커밋은 아직(사용자 요청 시). 남은 것: 다음 새 세션에서 시험 묶음 Q1~Q10 을 기억 없는 상태로 한 번 · DECISIONS 가 상한 15,000B 에 딱 닿음(다음 결정 전에 정리 필요) · K42 첫 카드는 새 결론이 생길 때
