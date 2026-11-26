# REQUEST — 11/25 배포 수리·11/23 결손 처리 점검 (Claude → Codex, 2026-11-26)

읽기만 하는 점검이다. 저장소 파일·DB 를 고치지 않는다(DB 는 `mode=ro`). 수집기·배치·배포를 실행하지 않는다. `.env`·토큰은 읽지 않는다.
답은 `research/handoff/REPLY_20261126_deploy_fix_review.md` 한 파일. 실측(직접 확인)과 추정을 구분해 적는다.
**순서**: 아래 "볼 것"을 먼저 스스로 확인하고 결론을 적은 뒤에 `worklog/2026-11-25_pages_deploy_krx_gap_check.md` 와 패치노트를 읽는다(Claude 의 설명을 먼저 보면 독립 확인이 아니다). 순서를 못 지켰으면 그렇게 적는다.

## 경로
- 저장소: `C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k` — `history.db` 는 이 폴더 바로 아래.
- 시세·가치 DB: `C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k-data\ohlcv.db`(저장소 밖 옆 폴더). 접근이 막혀 있으면 우회하지 말고 2번의 그 항목을 "모름(접근 불가)"로 적는다.
- 포지션 트래커(`..\Position-Tracker-Web`)는 이번 점검 대상이 아니다 — 11/25 변경은 그쪽을 건드리지 않았다. 열지 않는다.

## 대상 커밋 (main)
- `8ad3fae` 배포 도구 버전 올림 + 11/23 점검 기록·D48
- `6950c80` 올리기와 배포 사이 20초 대기
- `6d1e6f0` 배포 실패 텔레그램 알림 + 시험 스위치

## 볼 것
1. **`.github/workflows/deploy-pages.yml`** (셋 다 이 파일)
   - 알림 단계 조건 `failure() || inputs.test_alert == true`: 푸시로 돌 때(`inputs` 없음) 잘못 켜지거나 오류가 나지 않는가. 앞 단계가 실패했을 때 실제로 도는가. `job.status` 가 그 시점에 `failure` 로 읽히는가.
   - 알림 스크립트: secret 이 없을 때·텔레그램이 오류를 돌려줄 때(curl 은 HTTP 오류에도 0 으로 끝남) 조용히 지나가는 길이 있는가. 토큰이 로그에 찍힐 길이 있는가.
   - `sleep 20` 이 "Found 0 artifact(s)" 의 맞는 처방인가. 더 믿을 만한 방법(재시도·조회 확인)이 있으면 적는다. 도구 버전 네 개(checkout v7 · configure-pages v6 · upload-pages-artifact v5 · deploy-pages v5)에 알려진 문제가 있는가(확인한 출처와 함께 — 기억으로만 쓰면 추정으로 표기).
   - upload v5 가 `docs/.nojekyll` 을 묶음에서 빼는 것이 이 배포 방식에서 정말 영향이 없는가.
2. **11/23 결손 처리** (D48 — `DECISIONS_LOG.md` 의 D48 절, `VERDICT_CHECKLIST.md` 3-1 행)
   - `history.db`: v30·v32a 의 run 20261123 행이 가치 점수 없이 채점된 채 그대로인가(다시 계산된 흔적이 없는가). `large_final` run_id=20261123 이 500행이고 다른 run 의 행 수가 그대로인가.
   - `../dh-q7m3k-data/ohlcv.db` `valuation_daily` 20261123 행(2,724)이 앞뒤 거래일과 견줘 그날 자료로 보이는가(다른 날 값을 그대로 베낀 것이 아닌가).
   - D48 의 표기 약속(그대로 포함 + 각주 + 11/23 뺀 값 병기)이 12월 판정 3건(v32a · ls_t1 · lv_e 2차)의 도구·절차서에서 빠질 구멍이 있는가.
3. **기록의 정확성**: 위를 다 본 뒤 worklog·패치노트(2026.11.23)를 읽고, 사실과 다른 문장·확인 없이 단정한 문장을 짚는다.

## 답 형식
- 항목별로 `이상 없음 / 고칠 것 / 모름` + 근거(파일:줄 또는 실행한 조회).
- 고칠 것은 심각도(지금 / 판정 전 / 언젠가)와 함께. 직접 고치지 않는다.
- 끝에 "질문" 절.
