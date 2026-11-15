# WHERE.md — 분야 안내: 무슨 일이면 무엇을 먼저 보나 (2026-11-15 시작 · Claude·Codex 공통 · 짧게 유지)

**지위**: 결론을 담지 않는다 — **가리키기만** 한다. 번호(K·D·P)의 내용은 `KNOWLEDGE.md`·`DECISIONS.md`·`PROMISES.md`(K42 부터는 `knowledge/K##.md` 카드)가 정본이다.
**찾는 법**: ① 아래 표에서 일의 종류를 찾아 '먼저 볼 것'과 '꼭 같이 볼 한계'를 연다. ② 표에 없거나 모자라면 낱말로 저장소를 검색한다(세 장 → `KNOWLEDGE_ARCHIVE.md` → 지도 §10·§12 → `research/` 파일 이름·본문 → `worklog/`). ③ **검색 0건은 '결론 없음'이 아니라 '미확인'**이다 — 다른 낱말·옛 이름으로 한 번 더 찾고, 그래도 없으면 "찾지 못했다"고 적는다. ④ 놓쳤던 낱말은 이 표의 '낱말' 칸에 보탠다.

| 일의 종류 | 먼저 볼 것 | 꼭 같이 볼 한계 | 낱말(별칭) |
|---|---|---|---|
| 모델 판정(§11)·후속 창 | `VERDICT_CHECKLIST.md` → `VERDICT_RULES.md` → 그 모델 `PREREGISTER_*` → `PROMISES.md` 의 그 모델 행 · K23 · K36 | K40(wu 트랙 사후 적재) · K38(재무 자료 시점) · 어긋남 5(40일 셈법) | 판정, 유의, 기움, 노이즈, 역작동, 자리바꿈, 분모, 앵커 |
| v30·과매도 점수·챌린저 | K15 · K16 · K17 · K37 · D19 / v32a 는 K25 · P04 · `PREREGISTER_v32a` | K02(이기는 자리는 급락 뒤뿐) · 어긋남 2(대리 ≠ v30 목록) | v30, 챔피언, v31a~g, v32a, 한산한, 공식, 깔때기 |
| 저변동 목록·lv_e 교체 | K18 · K19 · D31 · D36 · P07 · `research/OBSERVATION_CONTRACT_20261104.md` | 어긋남 6(순위 라벨 vs 돈) · 어긋남 7(승격 문구) | lv_b, lv_e, lowvol, 저변동, 표시 기준, 승격, 2차 창 |
| wu 트랙 | K20 · K19 · D37 | K40 · 한 창뿐 | sv_a, sv_b, le_a, qs_a, px_a, 신용잔고 |
| 대형 가치 | K24 · `PREREGISTER_ls_t1` · P05 · P06 · P10 · D05 · D08 · `research/large_verdict_status.md` | v3 와 섞지 않는다 · 보충표 136종목 | ls_t1, large, 대형, h60, 주간 앵커 |
| 언제 사나(시장·급락·수급·바깥 축) | K01~K14 · K35 · 지도 §2 ① | 어긋남 1('국면' 정의 다섯) · 어긋남 3 · K39(자료 범위) · P01(바깥 축 재현 전) | 국면, 칸 A~D, 급락, 깊이, 게이트, 외국인, 연기금, 환율, 업종 |
| 무엇을 사나(필터·사건·첫 주) | K25~K30 · K41 · 지도 §2 ③ | K39(종목 수급·공매도는 2026년뿐) · PITFALLS `dart_events` | 필터, 제외, 첫 주, 신탁, 자사주, 실적 접수, 수급 부호, 거래대금 |
| 진입·보유·청산 | K31 · K32 | PITFALLS '재투자 근사' | 40일, 익절, 손절, 조기 매도, t+1 종가 |
| 돈·계좌·비용·자동화 | K33 · K34 · K35 · D29 · D32 · D33 · `research/AUTOMATION_BACKLOG.md` | 비용 감도는 한 창 · 계좌 상한은 추정 | 모의 계좌, 비용, 체결 한도, 자본 사다리, T+2, 주문, KIS |
| 11년 대리 연구를 새로 할 때 | `research/lib/tenyr.py` · K39 · K40 · 지도 §6(하지 않을 것) · `research/FORECASTS.md` | 대리 결론을 v30 목록에 그대로 옮기지 않는다 · 업종은 현재 분류뿐 | 대리, 11년, 월 블록, 부트스트랩, 정리 유니버스 |
| 공개 화면·텔레그램 | `docs/models_registry.json` · D01 · D22 · D35 · D36 · 최근 `patch_note/` | PITFALLS '배치가 다시 만드는 페이지' · `leaderboard.py` 는 docs 를 덮어쓴다 | 페이지, 성적표, 리더보드, 🚦, 🧭, 알림 |
| PTW | `../Position-Tracker-Web/CLAUDE.md`·핸드북 · D09 · D36 · P15 | 스크리너와 독립 · 로그인은 하드 경계 | PTW, 출처, 전략 태그, 매수 폼 |
| 지식 구조·기록 정리 | `CLAUDE.md` 마무리 7~9 · `research/DESIGN_20261115_knowledge_scale.md` §7 · `research/RECALL_TESTSET_20261115.md` | 판정에 걸린 행은 12월 판정 뒤에 옮긴다 | 세 장, 보관소, 카드, 약속 장부, 정리 주기 |
