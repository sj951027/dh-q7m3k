# 2026-10-20(화 저녁) — Codex 국면 답 대조(일치) · **A~D 진입 국면 표시 구현**(2026.10.31 · PTW v5.45) · 게이트 초안 2차 · Codex 다음 요청서(매매 시점)

## 요약
- **Codex 국면 조사 답 대조 완료**(`research/handoff/REPLY_20261020_entry_regime_blind.md` ↔ 내 두 문서): 핵심 수치 **전부 일치**(코스피 A 뒤 40일 +6.78%·83일·독립 9·승률 89%, 9사건 수익 소수 둘째 자리까지 같음, D −1.35%, 코스닥 A +2.40%, 종목군·깊이·며칠째·규칙 모의 순서). 작은 어긋남 4건(코스닥 사건 수 11 vs 9 — 간격 규칙 차이, B·C 날 수 10~20일, 모의 총수익 1~2%p, '며칠째' 내 기록이 하루 많았음). Codex 가 더한 핵심: **'코스닥만 A'인 날은 −0.63%(코스닥 효과는 코스피와 겹치는 날에서 옴)** · **규칙 모의의 낙폭 개선은 상당 부분 현금 효과**(집행금 가중 순수익 +0.72 [−1.26, +2.82], 0 걸침) · 사전등록 후보는 '살 때'(코스피 A 우위) 쪽. → `RESEARCH_entry_regime_deep_20261020.md` §5 로 추가.
- **① A~D 표시 구현(승인 건) 완료**: 새 `regime_ad.py`(코스피·코스닥 20거래일 수익 → 칸·며칠째) → `docs/data.json` `regime_ad` · 텔레그램 `🧭 시장국면: 코스피 -13.0% 급락 뒤 7일째 · 코스닥 -0.4% 약세 2일째` · `scoreboard.json` 모델별 `regime_ad_money`(코스피·코스닥 칸별) + `leaderboard.html` '국면별' 표에 '코스피 A~D에 산 날' 열·머리글 · PTW v5.45 상단 칩 병기. 점수·판정 0-diff. 테스트 `tests/test_regime_ad.py` 추가 → `run_tests.py` **17파일 통과** · PTW `run_all_tests.py` **49파일 통과**(실측).
- **② 국면 게이트 초안 2차**(`PREREGISTER_regime_gate.md` 전면 개정): 가설 = "코스피 R20 > +5% 면 신규 매수 0(정본)·절반(보조)". Codex 지적 반영 — 대조군 **'상시 비중 축소'**(평균 노출 맞춤) · 주지표 **집행금 가중 순수익** · 라벨에 '현금 효과' 추가. 미등록(모의 계좌 가동 뒤).
- 사용자 추가 요청 "매매 시점 연구를 Codex 에": `research/handoff/REQUEST_20261020_timing_by_regime_blind.md` 작성(사는 날 미루기·나눠 사기·보유 중 장 바뀌면 팔기·손절·현금 효과 대조·v30 참고·PTW 손절 완화 방향). **보내는 날은 사용자가** — Codex 한도 메모(주 1~2건)상 이번 주 이미 2건 보냈으니 다음 주 권고.

## 시간순 흐름
1. worklog 10/20 오전 기록 '★ 시작점' 확인 → Codex REPLY 있음 → 전문 읽고 내 두 문서 §2·S1~S9 와 수치 대조.
2. 코드 위치 파악: 텔레그램엔 '시장국면 줄'이 **없었음**(새로 추가) · data.json 은 `regime_history`/`latest.meta` 만 · 성적표는 `load_regime`(코스닥 20일선) · PTW 는 `latest.meta.market_regime` 칩.
3. `regime_ad.py` 작성 → 실측: 코스피 10/08 부터 A, 10/19 = **7일째**(오전 기록 '8일째'는 하루 많음 → 연구 1차·패치노트에 교정 표기).
4. 네 소비자 수정 → 테스트 작성 → `build_scoreboard.py` 재생성(57초) · `notify_telegram.build_message()` 로컬 생성(전송 없음) · PTW 파싱 합성 검증(가짜 requests.get) → 두 저장소 회귀 전체 통과.
5. 문서: 연구 §5 대조 · 게이트 초안 2차 · 패치노트 2026.10.31 · PTW v5.45 패치노트+핸드북 한 줄 · Codex 요청서.

## 사용자 결정
- 오전 결정(①②④ 승인) 그대로 실행. 새 결정 요청 없음. **Codex 요청서는 작성만** — 보낼지·언제 보낼지는 사용자.

## 바뀐 것 (미커밋 — 사용자가 GitHub Desktop)
- 스크리너: `regime_ad.py`(새) · `build_dashboard.py` · `notify_telegram.py` · `build_scoreboard.py` · `docs/leaderboard.html` · `tests/test_regime_ad.py`(새) · `tests/run_tests.py` · `PREREGISTER_regime_gate.md` · `research/RESEARCH_entry_regime_20261020.md`(한 줄 교정) · `research/RESEARCH_entry_regime_deep_20261020.md`(§5) · `research/handoff/REQUEST_20261020_timing_by_regime_blind.md`(새) · `patch_note/20261020_regime_ad_display.md`(새) · `patch_note/README.md`(2026.10.31) · 이 기록 · `worklog/README.md`. (`docs/scoreboard.json` 은 산출물 — 배치가 덮어씀, 커밋 제외.)
- PTW: `app/screener.py` · `app/static/index.html` · `PATCH_NOTES_v5.45.md`(새) · `PTW_PROJECT_HANDBOOK.md`(헤더 한 줄).

## 검증
- `python tests/run_tests.py` 17파일 ✅ · PTW `python run_all_tests.py` 49파일 ≈1049체크 ✅(93초).
- 실측 값: `regime_ad.now()` → 코스피 −13.0% A 7일째 · 코스닥 −0.4% B 2일째(10/19 기준). data.json 페이로드·텔레그램 본문·scoreboard.json 키 확인.
- `leaderboard.html` 새 열 **실제 렌더 확인**(로컬 정적 서버 + 브라우저 패널: 머리글 'A~D: 코스피 -13.0% 급락 뒤 7일째 · 코스닥 -0.4% 약세 2일째', 표 7열, v30 행 `+1.5%p(26) · +4.1%p(4) · +4.7%p(5) · +8.2%p(11)`, 콘솔 오류 0). 확인 못 한 것: PTW 화면 실렌더(Render 배포 뒤).

## 남은 일
- [ ] **커밋·푸시(사용자)** — 위 목록(스크리너는 `docs/scoreboard.json` 제외, PTW 4개).
- [ ] 내일(10/21) 배치 뒤: 텔레그램에 🧭 줄 · `leaderboard.html` '국면별' 새 열 · PTW 칩 ` · -x.x% … n일째` 확인. 깨지면 표시 전용이라 되돌리기 쉬움(`regime_ad` 키 없으면 전부 종전대로).
- [ ] **④ 모의 계좌 코드(B, 1주)**: `PAPER_ACCOUNT_DESIGN_20261018.md` §2~§5·§8 → `paper_account.py` + `../dh-q7m3k-data/paper_account.db` + 배치 1줄 + 되감기(20260810~) + **게이트 적용 계좌 + 상시 비중 축소 계좌**(게이트 초안 2차 §1 대조군). `shadow_ops_portfolio.py` 동결.
- [ ] Codex 요청서(매매 시점) 전송 시점 결정(사용자) → 답 오면 대조 → 가설 1개를 모의 계좌 설계에 반영할지.
- [ ] 오늘 밤 23:27 Actions 로그(`auto push within 14h - OK`) · lv_e 판정 ≈10/30~11/03(11거래일 뒤) · sv_b 18거래일 뒤 · ls_t1 17거래일 뒤.
- [ ] 뒤로 미룬 것: stage3 rcept_no 저장 · 과제 C~H · Codex 11월 요청 초안.

## ★ 다음 세션 시작점
0. 이 기록 + `PAPER_ACCOUNT_DESIGN_20261018.md` §2~§5·§8 + `PREREGISTER_regime_gate.md`(초안 2차 §1 대조군 정의).
1. 10/21 배치 결과에서 🧭 줄·새 열·PTW 칩 확인(위 '남은 일' 2번째).
2. **④ 모의 계좌 코드** 시작 — 계좌 3장(기본 · 게이트 적용 · 상시 비중 축소)이 같은 날부터 쌓이게.
3. 결정 대기: Codex 요청서 전송 시점만.

## 작업 요령
- 셸 heredoc 여러 개를 한 호출에 넣으면 한글·따옴표에서 파싱이 깨져 **하나도 안 써진다** — 문서는 Write 로 임시 폴더에 만든 뒤 `cat >>`/`cp` 로 옮기는 게 안전.
- '며칠째' 같은 수치는 기록보다 **코드 실측**을 믿는다(오전 기록 8일 → 실측 7일).
- 표시 기능은 "키 없으면 종전대로"로 만들어 두면 내일 배치가 깨져도 되돌릴 일이 없다.
