# 2026-09-13 — 게이트 보류 후 push 차단 · 배치 실패 수집 · 페이지/알림 문구 정정 · 백필 시간 상한 (2026.09.6 · 판정·점수 0-diff)

## 그래서 뭐가 바뀌나
- 완전성 게이트에 걸린 날은 배치 뒷부분(대형 트랙)도 **push 하지 않는다**. 종전엔 보류 알림을 보내 놓고 뒤에서 조용히 올라갔다.
- 파이썬 단계 12개 중 하나라도 0이 아닌 코드로 끝나면 배치 끝에 **[WARN] 요약**이 찍히고, 텔레그램 🔔 줄에 "배치 단계 실패: 이름"이 붙는다. 그날 첫 줄은 "✅ 이상 없음" 대신 **"⚠️ 확인 필요"**.
- 저변동 페이지가 스스로를 "테스트·관측 / 실제 추천은 v3 / 검증 전"이라 부르던 것을 **운용 기준(§11 판정: 기움)** 으로 바로잡았다.
  lv_a·mom_a 페이지는 "판정 전"에서 **"판정 완료: 노이즈"** 로. 대문의 v30 "역방향" 배지 옆에 모집단(추천종목·5일)을 명시.
- 주간 리캡 링크를 일간과 같게(저변동 + 리더보드). qs_a 단독 링크 제거.
- 같은 날 재실행해서 동결이 안 바뀌면 동결 단계가 그 사실과 절차를 로그에 적는다.
- DART 재무 백필에 시간 상한(600초·연속 8실패)을 넣었다.

## 왜
09-12~13 전수 점검(세 갈래: 문서 모순·화면/알림·운영 위험)에서 나온 것 중 위험 없는 것 8건 + 제 코드 결함 1건.

| # | 문제 | 근거(실측) |
|---|---|---|
| 1 | 게이트 보류가 무력화됨 | `logs/auto_run_20260908_2010.log:1439` "push 건너뜀" → `:1606` "업로드 완료" |
| 2 | 저변동 페이지 문구가 사실과 다름 | `docs/lowvol.html:102` "실제 추천 기준은 여전히 v3", `:118` "검증 전(40거래일 미달)" ↔ OOS 50·8/29 판정 완료·OPS_GUIDE "운용 중인 건 lv_b" |
| 3 | 경고 있는 날도 첫 줄 "이상 없음" | `notify_telegram.py` 머리말 하드코딩 |
| 4 | 배치가 실패를 안 봄 | `.bat` 파이썬 12줄 전부 종료코드 미확인 · 09-08 첫 단계 Traceback 뒤 "[OK] Done." |
| 5 | 재실행이 동결을 안 바꾸는데 안내 없음 | `freeze_scores.py` append-only(같은 키 skip) · 절차는 `clean_partial_run.py` 주석에만 |
| 6 | 판정 끝난 모델 페이지가 "판정 전" | `docs/lva.html:98~101`, `docs/mom.html:97,100` ↔ registry 노이즈(8/29) |
| 7 | 대문 헤드라인이 리더보드와 반대로 읽힘 | `docs/ic_summary.json` headline h5 −0.035 "역방향" ↔ leaderboard v30 h20 +0.032 |
| 8 | 주간 리캡이 qs_a 를 권하는 모양새 | `notify_weekly.py:179~182` |
| 9 | 백필이 DART 차단 시 몇 시간 붙잡을 수 있음 | `dart_backfill.py` 상한 없음 · stage3 `_request_json` 재시도 3회·타임아웃 15s |

## 어떻게
| 파일 | 변경 |
|---|---|
| `run_and_diversify.py` | push 성공 시 `deploy_ok.flag` 생성(시작 시 잔재 제거) |
| `run_all_and_diversify.bat` | `set "FAILED="` 초기화 · 파이썬 12줄 뒤 `if errorlevel 1 set "FAILED=%FAILED% name"` · 대형 push 를 `if exist deploy_ok.flag` 로 감쌈 · 텔레그램 전에 `batch_failed.flag` 기록/삭제 · 끝에 `[WARN]/[OK]` 요약 · 플래그 정리. ASCII·LF 유지 |
| `notify_telegram.py` | 본문에 ⚠️ 있으면 첫 줄 "확인 필요" · `batch_failed.flag` → 🔔 이벤트 |
| `notify_weekly.py` | 링크 2개(저변동·리더보드) |
| `freeze_scores.py` | 신규 0·보존 >0 이면 재실행 안내 2줄 |
| `dart_backfill.py` | `--max-sec 600` · `--max-streak 8` · 중단 사유 출력 |
| `docs/lowvol.html` | 제목·h1·경고문·각주 — "운용 기준(§11: 기움)", 반전 항 각주 삭제(lv_a 잔재), 운영 권고 한 줄 |
| `docs/lva.html` `docs/mom.html` | "판정 완료(8/29 정본): 노이즈 — 운용·추천 기준 아님" |
| `docs/index.html` | 헤드라인 verdict 옆 "(추천종목·5일 관측치 — 판정 정본은 리더보드 h20)" |
| `.gitignore` | `/deploy_ok.flag` `/batch_failed.flag` |

## 검증
- `.bat` 드라이 실행(파이썬 줄을 echo 로 치환, 플래그를 배치 중간에 생성) 2케이스:
  A 게이트 통과·실패 없음 → 대형 push 실행 · 텔레그램 발송 · `[OK] all python steps exited 0` · 플래그 잔재 없음.
  B 게이트 보류·`large_score` 종료코드 1 → push skipped · 텔레그램 skipped · `batch_failed.flag=" large_score"` · `[WARN] … large_score`.
- `notify_telegram.build_message()` 발송 없이 렌더: 평상시 첫 줄 "✅ … 이상 없음", `batch_failed.flag` 가 있으면 "⚠️ … 확인 필요" + 🔔 "배치 단계 실패: …" 확인.
- `notify_weekly.build_message()` 링크 줄 확인. py_compile 5파일. `python tests/run_tests.py` 통과.
- `dart_backfill.py --dry-run` 정상, `--help` 에 새 옵션 노출.

## 추가 — history.db 종목코드 앞자리 0 교정 (같은 날, 사용자 승인 후 실행)

### 무엇이 잘못돼 있었나 (실측)
2026-06-08~08-27 사이 19개 run 의 점수·stage 행에서 종목코드가 int 로 읽혀 앞자리 0이 빠진 채 저장돼 있었다
(`accumulate_history.py` 09-09 수정 이전 잔재). 리더보드·공통잣대·알파베타·요즘폼·판정 스크립트 6개 등
**읽는 쪽 10곳이 전부 zfill 없이** 시세와 맞추므로 그 종목들이 조용히 계산에서 빠졌다. 0으로 시작하는 코드는
대형주에 몰려 있어 무작위 결손이 아니다. 영향 모델 11/23(v30 +0.0324→+0.0466 등), **판정 라벨 변동 0**.

| 테이블 | 교정 행 |
|---|---|
| v3_scores | 9,634 |
| lowvol_scores | 3,968 |
| stage3_final | 1,930 |
| stage2_filtered | 184 |
| stage1_oversold | 68 |
| **합계** | **15,784** |

### 어떻게
- 백업 `backup/history_before_zfill_20260913_182115.db`(318MB) → 트랜잭션 1회 `UPDATE … SET ticker=substr('000000'||ticker,-6,6) WHERE LENGTH(ticker)<6 AND 숫자만`.
  사전 검사: 영문 섞인 코드 0건, 채운 뒤 기존 키와 충돌 0건(5개 테이블). 사후: 비정상 0건, `PRAGMA quick_check` ok.
- **점수 값·행 수·frozen_at 은 그대로**(라벨만 채움). 읽는 쪽 코드는 손대지 않았다(원인 제거로 전부 정상화).
- 골든 재동결: `tests/frozen_fwd_h20.csv` 재생성(51,536→52,487행 — 빠졌던 종목의 forward 수익이 들어옴),
  `tests/test_leaderboard_frozen.py` GOLDEN v30 +0.0573→**+0.0513** · lv_c −0.0962→**−0.0929** · lv_b 불변. 전체 테스트 통과.
  ("골든이 깨지면 코드를 의심" 규칙의 예외 — 이번엔 코드가 아니라 데이터 라벨이 틀렸던 경우. 사유를 GOLDEN 주석에 남김.)
- 판정문 각주: `VERDICT_20260809.md`·`VERDICT_20260829_lowvol.md` 에 "각주 ④ 교정 후 재계산" 추가 — 본문 수치는 소급 수정하지 않고
  같은 창 재계산값을 병기(v30 8/09 창 +0.1315→+0.1235, CI 하단 +0.088 → 유의 유지 / lowvol 8/29 창 mom_a·lv_d·lv_c 소폭 이동, 라벨 전부 유지).
- 리더보드 JSON 은 다음 배치가 재생성(교정 후 값으로 자연 갱신). 자동 라벨 변동 알림은 없을 것(라벨 불변).

## 영향범위
- **점수·판정·게이트 판정식 무변경.** 바뀐 건 push 조건, 로그·알림 문구, 페이지 문구, 그리고 DB 종목코드 라벨.
- 게이트 보류일엔 이제 대형 관측 페이지도 안 올라간다(보류 취지). 필요하면 `.bat` 의 `if exist deploy_ok.flag` 만 풀면 된다.
- `--no-push` 로 돌리면 `deploy_ok.flag` 가 안 생겨 뒤쪽 push 도 자연히 건너뛴다(의도와 일치).
- 미처리(결정 필요): DB 종목코드 앞자리 0 교정(15,532행) · 게이트 커버리지 지표 · sv_a/le_a 판정 · 운용 채택 기준 등록 · 지식 문서 갱신.
