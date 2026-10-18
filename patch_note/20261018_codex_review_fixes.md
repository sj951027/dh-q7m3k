# 2026-10-18(밤) — Codex 커밋 점검 반영: 배치 감시는 자동 커밋만 · 보충표 종목 수급 갈래 · 비용 각주 문구 **[2026.10.28]**

판정·점수·게이트 **0-diff**. 근거: `research/handoff/REPLY_20261018_commit_review.md`(Codex, 8건) — 스크리너 몫 F5·F6·F7. PTW 몫(F1~F4·F8)은 PTW v5.43.

## 1. 그래서 뭐가 바뀌나
- **F5** `batch_watch.yml`: '오늘 docs/ 커밋이 있나' → '**오늘 배치 자동 커밋(메시지 `Auto update …`)이 있나**'. 낮에 사용자가 docs/ 를 손으로 커밋해도(레지스트리 갱신 등) 저녁 배치가 안 돌면 알림이 온다. `git log -1 --grep='^Auto update' -- docs/`.
- **F6** `data_health.py`: **수급(보충표 종목)** 갈래(16번째) — 보충표 136종목만의 수급 마지막 날짜·건수. 되감기 실측: **10/10 시점 전체 수급은 ok, 보충표 종목 수급은 마지막 8/25 → ⚠️**(9/14~10/08 사고가 이제 첫날 잡힘). 테스트 +2.
- **F7** `PREREGISTER_ops_adoption.md` 각주 문구: "E ≥ c+1.0 → E ≥ 1.5" 가 비용을 두 번 빼는 뜻으로 읽힐 수 있었다 → **비용 전 E_gross ≥ 1.5 = 비용 후 E_net ≥ 1.0, 동결 코드 `Ec = E − c ≥ 1.0` 과 같은 조건**으로 명시. 본문·코드·결정(판정 0.5) 불변.

## 2. 검증
- `tests/run_tests.py` 전부 통과(점검표 테스트 16갈래·되감기 3건). YAML 파싱 OK. 현재 표 16갈래 ✅.

## 3. 바뀐 파일
`.github/workflows/batch_watch.yml` · `data_health.py` · `tests/test_data_health.py` · `PREREGISTER_ops_adoption.md`(각주 문구) · `patch_note/README.md` · 이 파일.
