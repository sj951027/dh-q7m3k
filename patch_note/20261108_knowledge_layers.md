# 2026-11-08 — 지식 세 층 구조(KNOWLEDGE·DECISIONS·PITFALLS) + 연구 공통 틀 `research/lib` — 2026.11.11

## 뭐가
- 새 파일(루트): `KNOWLEDGE.md`(확정 결론 한 장, 자리별 44행 + 어긋남 7 + 열린 것 5, 19KB) · `DECISIONS.md`(사용자 결정 날짜순 36행 + 대기 12묶음, 13KB) · `PITFALLS.md`(당한 함정 18줄, 3KB).
- 새 모듈 `research/lib/tenyr.py`(+`__init__.py`): 11년 대리 틀(정리 유니버스·과매도 대리·5거래일 격자·40일·비용·월 블록 부트스트랩·6칸)을 세 스크립트가 복사해 쓰던 것을 한 곳으로. 기존 스크립트는 안 고침(결과 파일 보존).
- 새 테스트 `tests/test_tenyr_lib.py`(10년 DB, ~1분, run_tests 밖) · `tests/test_knowledge_sheets.py`(즉시, run_tests 에 추가: 세 장 존재·'마지막 정리'·크기 상한·정본 링크 실재·원장 모델 13개가 KNOWLEDGE 에 있는지).
- `CLAUDE.md`: 읽기 순서 0-1(세 장, 세 층 설명) · 불변 규칙에 lib import(복사 금지) · 마무리 7(지식 층 갱신) · 8(정리 주기, 크기 상한). 6.5KB → 7.9KB.
- `tests/README.md` 한 줄 · Codex 요청 `research/handoff/REQUEST_20261108_knowledge_layers.md`.
- Claude 메모리(저장소 밖): 시간순 프로젝트 상태 파일을 비우고 "저장소 세 층이 정본" 포인터로.

## 왜
사용자: "너가 계속 똑똑해지길 원하는데 최적의 방법은?" → 실측: 결론이 시간순 기록(worklog 28·patch_note 102·메모 117·지도 68KB·PROJECT_KNOWLEDGE 150KB)에 묻히고 같은 결론이 다섯 곳에 적혀 어긋남('국면' 정의 셋). 세션 사이 기억이 없는 Claude 에게는 "매번 전부 읽을 수 있는 크기의 확정 결론·결정·함정"이 있어야 같은 실험·같은 질문을 반복하지 않는다.

## 어떻게 + 검증
- 결론·결정은 보조 2개가 기록 층 전체(지도·VERDICT·메모 결론 절 / worklog 28편·§13)에서 추출, 숫자 4건 원문 대조(crash_depth 27.6 · fresh −0.20 [−0.51, +0.12] · E1 A 58일 +3.27 [+1.84, +4.75] · 11/7 "300만 기준으로 설계하지 말고") 일치.
- lib: `tests/test_tenyr_lib.py` → `research/out_signal_board/{tenyr_days,e1_cells}.csv` 와 **0-diff**(신호일 545 · E1 27행, 부트스트랩 CI 포함 atol 1e-9) 통과.
- `python tests/run_tests.py` 통과(test_knowledge_sheets 포함).

## 영향 범위
문서·테스트·연구 보조 모듈만. **점수·판정·게이트·배치·docs 무변경(0-diff)**. 기존 연구 스크립트와 출력 파일 그대로.
