# REPLY — 11/25 배포 수리·11/23 결손 처리 점검

점검일: 2026-11-26(KST), 배치 전. 대상: `8ad3fae` → `6950c80` → `6d1e6f0` 및 현재 DB.

## 범위·확인 순서

- 요청서의 배포·결손 처리·기록 정확성만 점검했다. 이 REPLY 외 파일을 만들거나 수정하지 않았다. DB는 모두 `sqlite3.connect(Path(...).resolve().as_uri() + '?mode=ro', uri=True)`로 열었다. `ohlcv.db` 접근은 정상이다. 포지션 트래커는 열지 않았다.
- 수집기·배치·배포·텔레그램 발송은 실행하지 않았다. `.env`·토큰 값을 읽지 않았다. 판정 도구도 실행하지 않고 소스를 확인했다. 특히 `large_verdict.py`는 실행하면 상태 파일을 쓰므로 실행하지 않았다(290~293행).
- 아래 §1~§2 결론을 파일에 먼저 작성하고, 그 뒤 11/25 worklog와 패치노트를 읽어 §3에 대조했다. 다만 필수 선행 문서인 `worklog/README.md`·`PITFALLS.md`·D48에 배포 성공 등 요약이 있어 이미 읽었다. **완전한 눈가림은 아니다.** 11/26 최신 worklog 본문도 대조 단계까지 미뤘다.
- 실측 = 직접 읽은 코드·DB·로그·공개 GitHub API 응답 또는 아래 모의 시험. 해석·권고와 미확인은 별도로 표시한다. GitHub 공식 문서와 upstream 이슈는 직접 열어 확인했지만, 이슈 작성자의 관측을 이 저장소에서 재현한 것으로 취급하지 않는다.

## 1. 배포 workflow

### 1-1. 알림 조건과 `job.status` — 이상 없음(공식 동작·코드 대조)

근거: `.github/workflows/deploy-pages.yml:69`, `:74`.

| 상황 | 식의 결과 | 알림 분기 |
|---|---|---|
| push, 앞 단계 정상 | 없는 `inputs.test_alert`는 빈 문자열, `'' == true`는 거짓 | 실행 안 함 |
| push/수동, 앞 단계 실패 | `failure()`가 참 | 실행, `KIND=failure` |
| 수동, 정상, 시험 체크 | boolean `true == true` | 시험 알림 |
| 수동, 실패, 시험 체크 | 참 | 실제 실패 알림 |

없는 속성은 빈 문자열이고, 서로 다른 자료형 비교 시 빈 문자열은 0·true는 1로 변환된다. `failure()`를 명시했으므로 기본 `success()` 조건 때문에 실패 뒤 알림이 건너뛰어지지 않는다. `job.status`는 진행 중에도 현재까지의 상태다. runner 구현도 일반 step의 `failure()`를 이 상태로 계산한다. [Contexts](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts), [Expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions), [runner FailureFunction](https://github.com/actions/runner/blob/main/src/Runner.Worker/Expressions/FailureFunction.cs).

한계: runner 자체 중단·작업 취소·워크플로 준비 실패까지 이 step의 발송을 보장하는 것은 아니다. 이 저장소에서 실제 실패/시험 발송을 실행한 검증은 아니다.

### 1-2. 알림 실패를 성공으로 처리 — 고칠 것(지금)

근거: workflow 78~79·98~100행.

- **secret 없음:** 경고를 쓰고 `exit 0`. 완전히 조용하지는 않지만, 정상 배포 후 `test_alert=true` 시험은 메시지가 전송되지 않아도 성공 표시가 된다.
- **텔레그램 HTTP 오류:** `curl -sS -o /dev/null -w ...`는 HTTP 400/401/403/429/500 등에 실패 종료하지 않는다. 응답 본문의 `ok`도 버린다. 실제 배포가 실패했다면 전체 job은 원래 실패 상태지만, 알림 step은 성공으로 보일 수 있다. 시험 실행에서는 전체가 성공으로 보일 수 있다.
- **실측 모의 시험:** 파일을 쓰지 않는 localhost HTTP 서버가 `400`·`{"ok":false}`를 돌려주도록 하고 같은 curl 옵션으로 호출했다. 결과 `http 400`, 종료 코드 **0**. `--fail`을 붙인 대조는 종료 코드 **22**. Telegram 서버·실제 secret은 사용하지 않았다. Windows curl 시험이며 GitHub Ubuntu의 실제 발송 시험은 아니다. 기본 동작은 [curl 공식 문서](https://curl.se/docs/manpage.html#--fail)와 같다.
- 권고: HTTP 실패와 JSON `ok != true`를 명시적으로 실패 처리하고, secret 없는 시험도 실패로 표시한다. 응답 원문 전체 대신 정리한 오류 코드만 남긴다. 연결·전체 전송 시간 제한도 둔다. Bot API는 응답의 `ok`로 성공 여부를 제공한다. [Telegram Bot API](https://core.telegram.org/bots/api#making-requests).

**토큰 로그 노출 — 이상 없음(현재 정적 경로), 실제 로그 검증은 모름.** 토큰은 secret→환경변수로 전달되고 토큰 출력·`set -x`·curl verbose가 없으며 응답 본문도 버린다. GitHub의 secret 마스킹도 적용된다. 현재 코드에서 평문 토큰을 명시적으로 출력하는 경로는 찾지 못했다. 다만 이것을 모든 오류·debug 설정에서의 절대 비노출 보장으로 쓰면 안 된다. [GitHub secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions).

### 1-3. 20초 대기 — 이상 없음(완화책), 영구 해결 여부는 모름

근거: workflow 53~60행, 공개 Actions API의 run·job·step 조회.

| 실행 | 커밋 | 직접 확인한 결과 |
|---|---|---|
| [45632145520](https://github.com/sj951027/dh-q7m3k/actions/runs/45632145520) | `0061df0` | upload 성공, deploy 실패 |
| [45632755460](https://github.com/sj951027/dh-q7m3k/actions/runs/45632755460) | `8ad3fae` | 네 도구 버전 올림 뒤에도 upload 성공, deploy 실패 |
| [45633166549](https://github.com/sj951027/dh-q7m3k/actions/runs/45633166549) | `6950c80` | upload 완료 23:21:46 → 대기 20초 → deploy 23:22:06~13 성공(KST) |

실측으로 확인한 것은 **20초 대기를 넣은 실행 1건의 성공**이다. 원인·충분한 대기 상한을 증명한 것은 아니다. 조회 시 최신 배포도 이 수동 실행이었고, `6d1e6f0`의 알림이 실행된 이력은 이 조회에서 확인되지 않았다.

**외부 근거:** upstream [deploy-pages #451](https://github.com/actions/deploy-pages/issues/451)에 같은 job에서 업로드 직후 artifact를 못 찾는 제보가 있다. 11/25 댓글의 공개 실험은 8회 중 4회 첫 조회 실패, 관측 지연 최대 약 6초였다. 다른 제보는 지연을 1.6~60초 사이로만 한정했다. 20초면 항상 충분하다는 근거는 아니다.

**더 믿을 만한 방법 — 고칠 것(언젠가: D48의 재발 조건 충족 시):** 단순히 전체 workflow를 다시 돌리기보다, 업로드를 유지한 채 지연을 둔 artifact 조회 재시도를 제한된 횟수/시간으로 수행하고 실제 가시성을 확인한다. 현재 deploy v5는 `@actions/artifact.listArtifacts()`의 **Twirp 목록**을 사용하며, 0개이면 즉시 예외를 낸다. REST의 run-artifacts 조회 성공만으로 이 목록에도 보인다고 판단하면 안 된다. 조회 경로를 맞추거나 deploy step을 지연 후 제한적으로 재시도해야 한다. [deploy v5 소스](https://github.com/actions/deploy-pages/blob/v5/src/internal/api-client.js).

upload v5는 `artifact_id`를 출력하지만 deploy v5의 공개 입력은 `artifact_name`이고 `artifact_id` 입력은 없다. 바로 연결하는 YAML만 제안하면 작동하지 않는다. 직접 ID 전달은 upstream 지원 또는 별도 구현 검토가 필요하다. 현재의 `timeout`·`error_count`는 이 0개 조회를 재시도하는 장치가 아니다. [deploy v5 입력](https://github.com/actions/deploy-pages/blob/v5/action.yml), [upload v5 출력](https://github.com/actions/upload-pages-artifact/blob/v5/action.yml).

D48④에 따라 지금 재시도 장치를 추가하지 않았다.

### 1-4. 네 도구 버전의 알려진 문제 — 확인 범위 내 아래와 같음

| 도구 | 분류·확인한 근거 |
|---|---|
| checkout v7 | **이상 없음(이 workflow와 관련된 문제 미확인).** self-hosted Windows의 v7.0.0 정리 오류 [#2528](https://github.com/actions/checkout/issues/2528)는 닫혔고 [v7.0.1 릴리스](https://github.com/actions/checkout/releases/tag/v7.0.1)에 수정이 있다. 여기서는 ubuntu-latest이며 checkout도 성공했다. 모든 v7 문제가 없다는 뜻은 아니다. |
| configure-pages v6 | **이상 없음(해당 실패 원인 아님).** 배포 초기 v6 major tag 누락 [#193](https://github.com/actions/configure-pages/issues/193)은 3/27 해결 처리. 이번 run에서 Setup Pages 성공. [v6 릴리스](https://github.com/actions/configure-pages/releases/tag/v6.0.0)는 Node 24 전환을 명시한다. |
| upload-pages-artifact v5 | **이상 없음(직접 업로드 성공), 이후 가시성은 별개.** [v5 릴리스](https://github.com/actions/upload-pages-artifact/releases/tag/v5.0.0)는 upload-artifact v7 및 숨김 파일 옵션 도입. 위 실패 run도 업로드는 성공했다. 이 버전만 원인이라고 확정할 근거는 찾지 못했다. |
| deploy-pages v5 | **고칠 것(언젠가: 재발 시 완화 보강).** 위 #451의 artifact 발견 실패가 관련된다. [v5 릴리스](https://github.com/actions/deploy-pages/releases/tag/v5.0.0)의 Node 24 전환 자체로 이 문제가 해결되지는 않는다. |

### 1-5. `docs/.nojekyll` 제외 — 이상 없음(이 배포 방식)

실측: docs의 점으로 시작하는 파일은 `.nojekyll` 1개였다. upload v5의 `include-hidden-files` 기본값은 false라 제외된다. 하지만 이 workflow는 Jekyll 빌드 없이 이미 생성된 `docs`를 tar로 업로드하고 Pages 배포 API로 배포한다. 따라서 브랜치 소스를 Jekyll로 빌드하지 말라는 표식이 없어도 이 경로에 Jekyll 단계가 생기지 않는다. `_large_obs.html`처럼 밑줄로 시작하는 파일은 해당 숨김 파일 규칙의 대상도 아니다. [upload 구현](https://github.com/actions/upload-pages-artifact/blob/v5/action.yml), [GitHub Pages custom workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

### 1-6. 실패 알림의 원인 단정 — 고칠 것(지금)

workflow 86행은 모든 앞 단계 실패에 대해 "자료는 저장소에 올라가 있고 배포만 안 된 상태"라고 보낸다. 하지만 69행은 checkout·Setup Pages·upload 실패도 잡고 수동 실행도 허용한다. 최신 배치 자료가 정상 게시됐음을 검사하지 않는다. **권고:** "페이지 갱신 작업이 실패했습니다. 아래 실행 기록을 확인해 주세요"처럼 관측한 범위만 쓰거나 실패 단계별로 구분한다. 11/25 사건 설명으로는 맞더라도 앞으로 모든 실패의 설명으로는 성립하지 않는다.

## 2. 11/23 결손 처리

### 2-1. v30·v32a 동결 — 이상 없음(현 상태), 변경 이력의 완전 증명은 모름

직접 조회:

```sql
SELECT model_id,market,COUNT(*),MIN(frozen_at),MAX(frozen_at)
FROM v3_scores WHERE run_id='20261123' GROUP BY model_id,market;
```

| 모델 | kospi | kosdaq | frozen_at(최소=최대) |
|---|---:|---:|---|
| v30 | 485 | 918 | 2026-11-23T20:36:13+09:00 |
| v32a | 485 | 918 | 2026-11-23T20:36:13+09:00 |

네 CSV(`v3_archive/v3_{kospi,kosdaq}_20261123.csv`, `v32a_archive/v32a_{kospi,kosdaq}_20261123.csv`)와 DB를 ticker별로 대조했다. 총 **2,806행의 점수(허용 오차 1e-9)·grade·bucket 차이 0건**, CSV의 `value_score`는 전부 0.0, `value_source`는 전부 `UNAVAILABLE_OFFLINE`이다.

당일 로그 2754~2755행의 v30 가치 소스도 같고 2772행은 신규 2,806행 동결이다. `freeze_scores.py:145~152`는 기존 키를 건너뛴다. 따라서 현재 저장값은 가치 점수 없이 채점한 보관값과 일치하며 **재계산 흔적을 발견하지 못했다**.

한계: 해당 CSV와 DB는 git에 추적되지 않아 수리 전 commit과 직접 비교할 수 없었다. 범위 내에서 수리 전 DB 백업을 확보하지 못했다. 타임스탬프와 현재 CSV만으로 과거 UPDATE가 한 번도 없었다고 증명하지 않는다.

### 2-2. `large_final` — 이상 없음(행 수·적재 시각), 다른 run 불변은 일부 확인·나머지 모름

```sql
SELECT run_id,COUNT(*),MIN(run_timestamp),MAX(run_timestamp)
FROM large_final GROUP BY run_id ORDER BY run_id;
```

- 총 **110 run·55,000행**, 모든 run이 500행.
- 20261123은 **500행**, `run_timestamp` 전부 **20261125_2300**. 사후 적재 표시와 맞는다.
- 11/19·20·24·25도 각각 500행. 11/24 로그 3753행, 11/25 로그 3795행의 당시 행 수도 각각 500으로 현재와 같다.
- 다른 모든 run의 수리 전후 행 수·내용 불변은 비교용 이전 DB 없이 확정할 수 없다. "현재 모두 500"을 "다른 run은 하나도 변하지 않음"으로 확대하지 않는다.

### 2-3. `valuation_daily` — 이상 없음(2,724행·단순 복사 아님), 날짜 정확성은 모름

```sql
SELECT date,market,COUNT(*) FROM valuation_daily
WHERE date IN ('20261120','20261123','20261124') GROUP BY date,market;
```

11/23은 kospi **908**, kosdaq **1,816**, 합계 **2,724행**이다. 앞뒤 날과 공통 ticker 2,724개를 비교했다(`IS`로 NULL끼리도 동일하게 셈).

| 11/23과 비교 | BPS 동일 | PBR 동일 | PER 동일 | PBR·PER·DIV·BPS·EPS 모두 동일 |
|---|---:|---:|---:|---:|
| 11/20 | 2,724 | 692 | 1,219 | 355 |
| 11/24 | 2,722 | 795 | 1,219 | 386 |

**실측 결론:** 전 종목의 앞날/뒷날 값을 통째로 복사한 자료는 아니다. PBR이 바뀌고 BPS 대부분이 유지되는 모습은 일별 가치 자료와 부합한다. 다만 그것만으로 날짜가 정확히 11/23이라고 확정할 수는 없다.

추가 교차 확인: `valuation_daily`와 `daily_ohlcv`를 ticker·date로 연결하고 `bps>0 AND close>0`인 행에서 `abs(pbr-close/bps)<=0.00501`(소수 둘째 자리 반올림 허용)을 셌다. 11/23은 **1,130/2,446행**만 부합했다. 앞뒤 날 자체도 11/20 **1,171/2,446**, 11/24 **1,027/2,446**으로 완전히 맞지 않았다. 따라서 이 불일치를 11/23 복구 오류로 단정하지도 않는다.

예: 삼성전자 11/23 `PBR=2.77`, `BPS=63,997`, 시세 DB 종가 `180,600`으로 `close/BPS≈2.8220`. 같은 종목 PBR은 11/20 2.86, 11/24 2.96이다. **당일 원자료 또는 가격 기준 차이를 설명하는 근거 없이 '그날 자료임을 확인'은 과한 표현**이다. 수집기 재호출은 하지 않았다.

### 2-4. D48을 판정 때 빠뜨릴 경로 — 고칠 것(판정 전)

**이상 없음:** `DECISIONS_LOG.md:111~118`에 포함 쪽으로 라벨을 정하고 제외값은 감도로만 둔다는 결정이 있고, `VERDICT_CHECKLIST.md:23`의 3-1행은 v30·v32a·ls_t1 요구를 담았다. 절차서를 그대로 붙여 확인하면 사람이 챙길 수 있다.

**실측한 누락 경로:**

1. **v32a 도구:** `research/verdict_v32a_20261116.py:222~245`는 동결 점수를 읽지만 11/23 제외 감도 인자가 없다. 442~445행의 자체 대조표 안내도 3번 다음 바로 4·8번으로 넘어가 **3-1이 없다**. `--asof`는 뒤 날짜를 모두 자르므로 하루 제외의 대체물이 아니다.
2. **ls_t1 도구:** `large_verdict.py:199~219`는 일반 게이트만 적용하며 D48 사후 적재 각주·11/23 제외 감도를 출력하지 않는다. 311~314행의 인자도 `--check`뿐이다. 기존 D44의 '정하기 전에 닫힌 앵커 제외'는 다른 감도다. 제외 감도를 구현할 때는 **원래 주간 앵커를 고른 뒤 11/23만 빼야** 해당 앵커의 영향을 잴 수 있다. 먼저 원자료에서 빼고 `weekly_subset()`을 다시 돌리면 11/24가 그 주 첫 앵커를 대신한다(81~89행). 대체 실험을 할 경우 별도 정의가 필요하다.
3. **약속 수집 절차:** 절차서 9행은 `DECISIONS.md`를 검색하지만 D48 본문은 `DECISIONS_LOG.md`에 있다. `PROMISES.md`의 P04·P05·P07에도 D48 연결이 없고, 두 판정 스크립트의 출력 안내는 각각 P04/P07만 가리킨다. 전체 세션 규칙대로 이력을 읽으면 발견하지만, 판정 도구 출력·약속 장부만으로 완결된 준비라고 보기 어렵다.

권고: 판정 전에 D48 각주와 해당 날짜 포함/제외 결과 위치를 도구 출력·대조표에 연결한다. 기본 결과는 포함한 채 유지하고, 제외 감도에서 주지표·n·CI·관련 짝 비교를 명시한다. ls_t1의 11/23 h60은 **12월 말에도 미완결**이므로 그때 완결 표본에 들지 않는다는 사실과 감도 차이 없음/계산 대상 없음의 이유를 구분해 적는다. 표기 약속은 향후 h60/h120 완결 시점에도 남겨 둬야 한다.

### 2-5. lv_e 2차 창에는 별도 범위 공백 — 고칠 것(판정 전), 적용 범위는 질문

D48①과 체크리스트 3-1은 v30·v32a의 가치 점수, ③은 ls_t1을 명시한다. **lv_e·lv_b의 ROE 결측 처리는 명시하지 않는다.** 따라서 D48이 lv_e의 각주·제외 감도까지 이미 확정했다고 해석하면 안 된다.

직접 조회:

```sql
SELECT run_id,market,COUNT(*),COUNT(roe_value)
FROM stage3_final WHERE run_id IN ('20261120','20261123','20261124')
GROUP BY run_id,market;
```

| run | kospi ROE 있음/전체 | kosdaq ROE 있음/전체 |
|---|---:|---:|
| 11/20 | 423/424 | 887/898 |
| 11/23 | **0/485** | **0/918** |
| 11/24 | 448/449 | 834/843 |

11/23 lowvol_scores는 lv_e·lv_b 각각 kospi 102·kosdaq 177행, 동결 시각 11/23 20:42:08이다. 두 모델 모두 ROE를 보조 팩터로 쓰고(`lowvol_score.py:83`, `:137`), 결측 순위는 0.5로 채운다(`:195~202`). **코드·DB로 판단하면 이날은 둘 다 ROE가 중립값인 점수다.** 실제 점수를 재계산하거나 변경하지 않았다.

lv_e 도구(`research/verdict_lv_e_w2_20261116.py:31~45`, `:346~349`)도 해당 날짜 각주·제외 감도·3-1 안내가 없다. 권고는 lv_e·lv_b를 함께 대상으로 ROE 결손 사실과 감도 표기 범위를 **결과 완결 전에 명시**하는 것이다. 기존 D48의 v3 가치 점수 0을 lowvol 점수 0으로 옮겨 적으면 틀린다. lowvol의 ROE 결측 처리는 0.5 중립이다.

## 3. worklog·패치노트 대조

대상: `worklog/2026-11-25_pages_deploy_krx_gap_check.md` · `patch_note/20261125_deploy_pages_action_versions.md`(2026.11.23). 11/26 최신 worklog도 이 단계에서 읽었다.

### 3-1. 수리 경과·미확인 표기 — 이상 없음 / 일부 모름

- **이상 없음:** 패치노트 4~6행의 "버전 올림만으로 실패 지속 → 20초 대기 뒤 성공 1건 → 원인은 추정·다음 자동 배포로 확인"은 공개 run/job API와 일치한다. 11행의 Telegram 실제 수신 미확인 표기도 적절하다. `.nojekyll` 제외 자체도 upstream 구현과 맞는다.
- **이상 없음:** worklog 8행의 모델별 1,403행 동결·가치 소스는 DB·CSV·당일 로그와 일치한다. 29행의 사후 적재 뒤 총 55,000행·110 run도 현재 DB와 일치한다.
- **모름:** 당시 공개 JSON의 응답 내용·Last-Modified, 로그의 0.4/0.8초 간격은 이번 점검에서 당시 응답/원격 로그 원문까지 확보하지 않았다. step API의 초 단위 시각은 확인했으나 이를 소수점 간격의 독립 재현으로 쓰지 않는다. 시장 수급·일반 배치 전체 건강은 요청의 "볼 것" 밖이므로 추가 검사하지 않았다.

### 3-2. 가치 자료 날짜를 확정한 문장 — 고칠 것(지금)

- worklog **28행**: "BPS 는 11/20·11/24 와 100% 같고 … → 11/23 자료가 맞음".
- D48 구현 상태 **118행**도 "BPS 는 앞뒤 날과 같고 PBR 은 달라 11/23 자료임을 확인".

§2-3처럼 **앞뒤 날과 다르다는 사실은 정확한 해당 날짜의 증명이 아니다**. 현재 DB의 BPS도 11/24와는 2건 다르다: `347770` 2,043→10,215, `417180` 8,876→6,835. 11/20과 100% 일치는 재현된다. PBR 23~36% 일치는 시장별로 계산하면 재현된다(11/20 대비 kosdaq 422/1,816·kospi 270/908, 11/24 대비 468/1,816·327/908).

권고 문장: "2,724행을 확인했고 앞뒤 날의 단순 복사본은 아니다. 대부분의 BPS는 유지되고 PBR은 달랐다. 날짜의 정확성은 원자료/가격 기준 추가 대조 전에는 미확인." 현재 DB와 당시 상태가 달랐다는 증거가 있다면 그 시점도 별도 표기한다. **DB를 고치라는 제안은 아니다.**

### 3-3. ls_t1 적재 시각 — 고칠 것(지금)

worklog **29행**의 "적재함(22:4x)"는 현재 `large_final` 500행의 **20261125_2300**과 맞지 않는다. `large_score.py:240~241`은 이 필드를 실제 적재 시각으로 설정한다. 현재 확인 가능한 표현은 "11/25 23:00 적재 시각이 기록된 500행"이다. 22:4x에 별도 적재한 뒤 23:00에 다시 적재했는지는 증거가 없어 **모름**이다.

### 3-4. 반복 실패를 영구 원인으로 해석 — 고칠 것(지금)

- worklog **33행** "일시 문제가 아님": 연속 실패만으로 일시적인 목록 반영 지연을 배제할 수 없다. "연속 재실행도 같은 증상으로 실패"로 좁히는 것이 정확하다.
- 패치노트 **25행** "옛 배포 도구가 못 찾는 것": 새 v5도 실패한 4행·27행과 어긋나는 옛 추정이 남아 있다. "업로드 성공 뒤 배포 단계의 목록 조회 실패"까지는 관측과 일치한다.
- 패치노트 **27행** "올린 버전은 해롭지 않아": 배포 성공 1회로 전체 무해를 증명하지 못한다. "현재 확인한 배포에서는 새 버전으로 성공했고 별도 문제는 발견하지 못함" 정도가 맞다.
- 패치노트 **9행** "자료는 올라가 있음"은 상시 알림의 보장으로 쓰기 어렵다(§1-6). **10행** "test_alert 체크 → '(시험)' 알림"도 배포가 실패하면 실제 실패 문구가 나온다. 11행에 미확인이라고 적은 것은 맞지만, 시험의 예상 분기는 §1-1처럼 구분해야 한다.

### 3-5. 세션 전체를 읽기 전용·0-diff로 표현 — 고칠 것(지금)

worklog 제목 **1행**은 "읽기만"인데 뒤에는 사용자 승인으로 가치 자료·large_final을 적재하고 workflow를 수정한 내용이 있다. **41행** "코드·docs 무변경. 판정·점수 0-diff(건드리지 않음)"도 세션 전체를 가리키면 범위가 모호하다.

권고: "처음은 읽기 점검, 이후 승인된 자료 보충·배포 설정 수정"으로 단계 구분. "점수식·라벨 기준과 기존 v30·v32a 동결값은 유지; large_final에는 500행 추가; workflow 수정; docs 직접 수정 없음"으로 명시한다. **ls_t1 입력 표본은 추가됐으므로 모든 판정 출력이 0-diff라는 뜻으로 쓰면 안 된다.** 패치노트 35행은 배포 설정 변경만의 영향 범위라면 DB 무변경이라는 표현이 성립한다. 두 범위를 섞지 않아야 한다.

### 3-6. 이미 결정된 일을 다시 남은 일로 기록 — 고칠 것(언젠가: 다음 기록 정리)

worklog **44행**의 "위 결정 1~4 … 결정되면 D48"은 같은 파일 25~38행의 승인·적재·수리 완료 뒤에도 초기 문구로 남아 있다. D48은 이미 존재한다. 남은 것은 **11/26 자동 배포 재확인, 실제 알림 수신 시험, D48 판정 감도·각주 연결 및 lv_e 범위 명시**다. 11/26 최신 worklog가 실제 알림을 미실행으로 적은 것은 현재 조회와 맞는다.

## 4. 재확인에 사용한 조회·한계

- 로컬 Git: `git --no-optional-locks status --short`, 대상 커밋의 workflow diff, 대상 파일 경로의 추적 여부 확인. 처음부터 있던 작업본 변경은 건드리지 않았다.
- 공개 GitHub API(인증 없이 GET): `/repos/sj951027/dh-q7m3k/actions/workflows/deploy-pages.yml/runs?per_page=12` 및 위 3개 run의 `/jobs`. Actions 실행·재실행 요청은 하지 않았다.
- CSV 대조: 모델·시장별 11/23 파일을 읽고 ticker로 DB의 `final_score_v3,grade,bucket`과 연결했다. 점수는 절대 오차 1e-9, 나머지는 문자열 일치 기준. 이전 파일 원본 부재 한계는 §2-1과 같다.
- 가치 자료 비교는 다음 SELECT를 실행했다(비교일은 20261120·20261124). 날짜 진위의 독립 원자료 검증을 대신하지 않는다.

```sql
SELECT COUNT(*), SUM(a.bps IS b.bps), SUM(a.pbr IS b.pbr),
       SUM(a.per IS b.per),
       SUM(a.pbr IS b.pbr AND a.per IS b.per AND a.div IS b.div
           AND a.bps IS b.bps AND a.eps IS b.eps)
FROM valuation_daily a JOIN valuation_daily b ON a.ticker=b.ticker
WHERE a.date='20261123' AND b.date=?;

SELECT COUNT(*), SUM(ABS(v.pbr-o.close/v.bps)<=0.00501)
FROM valuation_daily v JOIN daily_ohlcv o USING(ticker,date)
WHERE v.date=? AND v.bps>0 AND o.close>0;
```

이번 작업은 점수식 변경·모델 판정·통계 성과 재평가가 아니다. 보고서 외 코드를 추가하지 않았다.

## 질문

1. lv_e 2차 창에도 11/23 ROE 중립 대체 각주와 lv_e·lv_b 같은 앵커 제외 감도를 병기할 것인가? D48의 명시 범위 밖이므로 임의 확장하지 않았다.
2. 11/23 valuation 원응답 또는 날짜·가격 기준을 확인할 별도 근거가 보존돼 있는가? 현재 DB 비교로는 단순 복사 아님까지 확인했다.
3. 다른 run의 완전 보존을 증명할 수리 전 history.db 또는 그때의 행별 해시가 있는가? 현재 DB·당시 로그 외 증거는 이번 범위에서 확보하지 못했다.
