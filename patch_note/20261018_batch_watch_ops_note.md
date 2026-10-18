# 2026-10-18 — 배치 밖 미실행 감지(GitHub Actions) · 운용 채택 비용 표기 해석 각주 · v30 2차 창 판정문 초안 **[2026.10.25]**

판정·점수·게이트 **0-diff**(점수·적재 코드 무변경 · `tests/run_tests.py` 대상 코드 안 건드림). 배치(.bat) 무변경.

## 1. 그래서 뭐가 바뀌나
- **평일 23:10(KST)에 GitHub 가 "오늘 자료 push 가 있었나"를 보고, 없으면 텔레그램 ⚠️ 한 줄**을 보낸다 — PC 가 꺼졌거나 재시작 뒤 로그인이 안 된 날(10/14 같은 날)을 **그날 밤** 안다. 지금까지의 '빠진 날 알림'(2026.10.24)은 다음 배치가 돌아야 왔다.
- 운용 채택 사전등록(`PREREGISTER_ops_adoption.md`)에 **비용 표기 해석 각주** 1개 — 라벨 판정은 보수적인 0.5% 차감본, 0.35% 는 표기만(본문·동결 코드 불변).
- `VERDICT_20261018_v30_w2.md` **초안**(사용자 확정 전) — v30 2차 창 §11 기본값 '노이즈'. 레지스트리·원장은 확정 뒤 갱신.

## 2. 왜
- 2026-10-18 진화 검토 세 의견(Claude·Codex Sol·Astra)이 모두 "자료 고장이 사고 뒤에 한 갈래씩 보강되고, 배치 밖 감지가 없다"를 꼽음(`research/handoff/CLAUDE_20261018_evolution_synthesis.md` 추천 1번). 사용자 결정(10/18): GitHub Actions 경로.
- 비용 표기: 3·35행("0.35 정본")과 46행("판정 CI = 0.5 차감본")이 충돌(Codex Sol S12). 첫 코호트 결과를 보기 전에 정해 둬야 사후 해석이 안 됨 → 사용자 결정 보수적 해석.
- v30 2차 창: 가격 날짜 차 44 ≥ 40 도달. Astra 독립 계산(`REPLY_20261018_v30_w2_blind.md`)과 내 도구(`research/verdict_v30_w2_px_a_20261009.py`)가 소수 넷째 자리까지 일치.

## 3. 어떻게
### 3-1. `.github/workflows/batch_watch.yml` (새 파일)
- `schedule: '10 14 * * 1-5'`(월~금 14:10 UTC = 23:10 KST) + 수동 실행. `permissions: contents: read`.
- 판단: KST 오늘 날짜 · 토·일이면 건너뜀 · `skip_dates.txt` 에 있는 날이면 건너뜀 · `git log -1 -- docs/` 의 커밋 날짜(KST)가 오늘이 아니면 **MISSED**. 배치가 성공할 때마다 `run_and_diversify.git_push()` 로 docs/ 를 push 하므로("Auto update …" 커밋) 그 push 가 완료 표식 — **배치 코드 변경 없음**.
- 알림: MISSED 일 때만 `curl` 로 텔레그램 sendMessage(토큰·chat id 는 Actions Secrets `TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID` — 로그에 가려짐). Secrets 가 없으면 경고만 찍고 끝(실패로 안 만듦).
- 한계(적어 둠): GitHub 예약은 몇 분~수십 분 늦을 수 있고 드물게 건너뛴다 → **알림 없음 ≠ 정상**. 배치가 돌았는데 push 만 실패한 날(게이트 보류 등)도 MISSED 로 나온다 — 그건 '확인하라'는 뜻이라 그대로 둠.
- 검증: YAML 파싱 OK(파이썬 yaml) · `TZ=Asia/Seoul git log -1 --format=%ad --date=format-local:'%Y%m%d %H:%M' -- docs/` → `20261016 21:13`(10/16 배치 push 와 일치). **실행 검증은 사용자가 Secrets 등록 뒤 Actions 탭 'Run workflow'**(일요일이라 '건너뜀'만 찍힘 — 평일 첫 실행 로그로 확인).

### 3-2. `PREREGISTER_ops_adoption.md` §2 머리에 인용 각주 1개
- 본문·§1·§2 논리식·동결 commit hash·관찰기간 **불변**(v6 재등록 아님). 각주만: "§2 라벨 판정 CI·E = 0.5% 차감본, 0.35% 는 표기 · 크기 조건 E ≥ +1.5%p".

### 3-3. `VERDICT_20261018_v30_w2.md` (초안)
- h20 −0.0052 n=21 · iid [−0.0347,+0.0238] · 주블록 [−0.0520,+0.0531] · /7 [−0.0444,+0.0339] · 주별 양 60%(3/5) · h10 +0.0281 [+0.0071,+0.0504](주블록 걸침) · lv_b−v30 −0.1037 [−0.1646,−0.0441].
- 해석표 빈칸(IC<0 · CI 0 걸침) → 새 규칙 없이 §11 기본값 **노이즈** · 챔피언 유지 · 라벨 "유의(8/09)·2차 노이즈(10/18)" 병기 · lv_b 짝비교 재검토 안건 없음(lv_b 가 뒤짐). 각주 ④(겹치지 않는 앵커 2 · 지속성 0.914/81.5% · 자리바꿈 43.8 백분위 · 가짜 유의 16.4%/11.1%).
- 확정 시 할 일: 상태 '정본' · `MODELS_LEDGER.md` 행 · `docs/models_registry.json` sealed.v30.t.

## 4. 영향 범위
- 점수·판정·게이트·적재·배치: 무변경. docs/ 산출물 무변경. 새 워크플로는 저장소를 읽기만 한다.
- 비용 각주는 2027-06 판정 때 라벨 계산에 쓰는 비용 열을 정한다(0.5).

## 5. 바뀐 파일
`.github/workflows/batch_watch.yml`(새) · `PREREGISTER_ops_adoption.md`(각주) · `VERDICT_20261018_v30_w2.md`(새·초안) · `research/handoff/CLAUDE_20261018_plan_3month.md`(새·계획안) · `patch_note/README.md` · 이 파일.
