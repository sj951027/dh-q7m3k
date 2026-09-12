# 2026-09-12 — 텔레그램을 배치 맨 끝으로 · DART 재무 백필 · 저장소/백업 정리 (2026.09.5 · 판정·점수 0-diff)

## 그래서 뭐가 바뀌나
- 텔레그램 알림이 배치 **맨 끝**(대형 push 다음)에 온다. 평일 기준 21:25 → **21:45쯤**으로 약 20분 늦어진다.
  대신 메시지 안의 모든 링크가 발송 시점에 이미 올라가 있다.
- **배포 보류(게이트 실패) 알림은 지금처럼 즉시** 온다 — 뒤 단계가 안 돌 수도 있으므로 미루지 않는다.
- GitHub Desktop 변경 목록에서 `latest_sv.csv`·`sector_cache.json` 두 줄이 사라진다(파일은 그대로 남는다).

## 왜 바꿨나
### ① 텔레그램이 화면보다 먼저 왔다 (사용자 관찰 → 실측 확인)
09-12 재실행 로그 실측: 주요 데이터 push 11:55 → 텔레그램 11:55 → **대형 페이지 push 12:13**(18분 뒤).
09-11 자동 배치도 같은 간격(21:25 발송 / 21:44 push). 메시지 본문의 `_large_obs.html`·`_large_test.html` 링크는
발송 시점에 아직 전날 것이었고, `ls_t1` 종목 수도 `large_final` 최신 run = 전일 값을 읽고 있었다.

곁가지 확인(문제 아님): GitHub Pages 배포 자체는 정상이다. 09-12 12:40 기준 `_large_obs.html`·`latest_sv.csv`·
`leaderboard.json`·`data.json`·`latest_kospi_lowvol.csv` 5개를 라이브와 커밋본(LF 기준)으로 대조 → **전부 일치**.
페이지의 데이터 fetch는 전부 `?ts=`/`?t=` 캐시버스터를 붙이고 있어 CDN 캐시(`max-age=600`)에 걸리지 않는다.
남는 지연은 push→Pages 빌드 시간뿐(미실측).

### ② 커밋 목록에 매번 뜨던 루트 파일 2개
- `latest_sv.csv`: 루트 사본인데 추적 중이었다. 형제(`latest_wu/qs/px/…`)는 전부 `.gitignore`에 있는데 sv만 누락.
  페이지가 읽는 건 `docs/latest_sv.csv`이고 그건 배치가 매일 커밋한다.
- `sector_cache.json`: 업종 라벨 캐시. 매 실행 갱신되고 `rebuild_sectors.py`로 재생성 가능.
  수동 교정은 `sector_overrides.csv`가 담당하므로 이 파일은 순수 캐시 → `dart_cache/`·`price_cache/`와 같은 취급.

## 어떻게
| 파일 | 변경 |
|---|---|
| `run_and_diversify.py` | `--defer-telegram` 플래그 신설. 정상(`deploy_ok`) + 플래그면 4단계에서 발송하지 않고 "미룸" 한 줄만 출력. 게이트 실패 시 '보류' 알림은 종전대로 즉시 발송 |
| `run_all_and_diversify.bat` | `run_and_diversify.py --defer-telegram` 으로 호출 · 대형 push 다음·cleanup 앞에 `python notify_telegram.py` 추가(ASCII·기존 줄바꿈 유지) |
| `run_and_diversify.py` | (보강) 미룸일 때만 `telegram_pending.flag` 생성, 그 외엔 항상 삭제 |
| `run_all_and_diversify.bat` | (보강) 끝 단계는 `if exist telegram_pending.flag` 일 때만 발송하고 플래그 삭제 |
| `.gitignore` | `/latest_sv.csv` · `/sector_cache.json` · `/telegram_pending.flag` 추가(루트 앵커라 `docs/` 사본은 계속 추적) |
| (1회) | `git rm --cached latest_sv.csv sector_cache.json` — 추적만 해제, 파일은 디스크에 그대로 |

### 보강 — 게이트 보류일 때 중복 알림 방지 (같은 세션 후속 점검에서 발견)
첫 구현은 배치 끝에서 무조건 `notify_telegram.py` 를 불렀다. 그런데 완전성 게이트 보류는 **종료코드 0**이라
배치가 그대로 계속 진행된다 → '보류' 알림 직후 '✅ 완료' 알림이 겹쳐 나갈 수 있었다(실제 발생 전 발견).
→ `telegram_pending.flag`(정상일 때만 생성)로 잠갔다. 드라이 실행 2가지 실측: 플래그 없음 → `[Notify] skipped` 만 출력,
플래그 있음 → 발송 후 플래그 삭제.

검증: `.bat` 드라이 파싱(모든 `python` 줄을 echo 로 치환해 실행)으로 순서 확인 — 대형 push → **Notify 텔레그램** → Cleanup.
`run_and_diversify.py --help` 에 플래그 노출 확인. `notify_telegram.build_message()` 단독 호출로 본문 정상 생성 확인(발송 없음).
`git check-ignore -v` 로 두 파일이 `.gitignore` 81·84줄에 걸리는 것 확인. `docs/latest_sv.csv` 는 추적 유지.

## 영향범위
- **점수·판정·게이트·파이프라인 산출물 무변경.** 알림 시각과 git 추적 목록만 바뀐다.
- 배치 소요 시간 불변(알림 위치만 이동).
- 알림이 20분 늦는 것이 불편하면 되돌리기는 `.bat`에서 `--defer-telegram` 제거 + 끝의 `notify_telegram.py` 줄 삭제 2곳이면 된다.
- 새 PC로 옮길 때 `sector_cache.json`이 없으면 업종 라벨을 한 번 다시 만들어야 한다(`rebuild_sectors.py`).
  단 `ohlcv.db`가 저장소 밖이라 어차피 새 PC에서 배치를 바로 돌릴 수는 없다.

## 추가 — DART 재무 결손 백필 (`dart_backfill.py` 신설)

### 증상 (실측)
`stage3_final.ocf_pattern='데이터없음'` 종목 수: **09-07 5 · 09-08 4 · 09-09 47 · 09-11 98**(541 중 18%).
로그의 DART 2차 시도 복구율: 09-07 91/91 → 09-09 0/43 → 09-11 0/96 → 09-12 0/98.
이 종목들은 `quality_score` 에서 '데이터없음'(−2)으로 처리되므로 **v30 점수에 영향**이 있다.

### 원인 (실측 + 추정)
- 실측: 배치와 무관한 시각에 같은 키·같은 엔드포인트로 순차 호출(list.json·fnlttSinglAcnt.json 각 6회, 0.3s 간격)
  → **12/12 전부 status 000**. 결손 98종목 순차 재호출 → **복구 94 · 자료없음(정상) 4 · 연결실패 0**(120초).
- 추정: DART가 배치의 대량 호출 중·직후 연결을 끊고(RemoteDisconnected) 얼마간 막으며, 시간이 지나면 풀린다.
  stage3 의 2차 시도는 실패 직후(0.3s 간격)라 같은 차단 창에 걸린다. 동시 스레드는 이미 2로 낮다.

### 수정
- `dart_backfill.py`(신설): 최신 run 의 결손 종목만 골라 stage3 의 fetch 함수를 **그대로** 순차 재호출 →
  성공분이 `dart_cache/fin`(정상응답 TTL 14일)에 들어가 **다음 실행이 캐시로 읽는다**.
  history.db 는 읽기 전용으로만 열고, **동결된 점수·stage3_final 행은 고치지 않는다**(소급 수정 없음).
- `run_all_and_diversify.bat`: 맨 끝(텔레그램 뒤·cleanup 앞)에 `python dart_backfill.py` 추가.
  stage3 로부터 1시간 이상 떨어뜨리는 것이 목적.
- 09-12 수동 실행으로 이미 94종목 캐시 확보 → **09-14(월) 배치부터 '데이터없음'이 한 자릿수로 줄어야 정상**.
  안 줄면 차단 창이 더 길다는 뜻이므로 백필 위치를 새벽 별도 작업으로 옮기는 것이 다음 수.

### 저장소·디스크 정리
- `research/clean_partial_run.py`: 백업 자동 회전 추가(최근 2개만 유지). 압축 없는 300MB+ 백업이 4개 1.25GB 쌓여 있었다.
- 그 중 오래된 3개 수동 삭제(09-08 ×2, 09-11 ×1) → `backup/` 1.7GB → 753MB. 직전 상태 1개는 남겨 둠.
- 7월 스냅샷 `v2_*.csv` 16개 추적 해제(`.gitignore` `/v2_*.csv` 는 이미 있었고 해제만 남아 있던 건). 파일은 디스크에 그대로.

검증: `dart_backfill.py --dry-run` 대상 98종목 확인 → 10종목 시험(복구 9) → 전량 실행(복구 94/연결실패 0).
`.bat` 드라이 파싱으로 순서 확인(대형 push → 텔레그램 → **Heal 백필** → Cleanup). `clean_partial_run.py` 드라이런 정상(보호 가드 동작).
