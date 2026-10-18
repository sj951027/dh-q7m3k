# 2026-10-18(밤) — history.db 인덱스 3개 · history.db 매일 백업 · 점검표 업종 갈래 **[2026.10.27]**

판정·점수·게이트 **0-diff**(인덱스는 결과를 바꾸지 않음 — `tests/run_tests.py` 골든 포함 전부 통과 · 점수·판정 코드 무변경).

## 1. 그래서 뭐가 바뀌나
- `history.db` 에 인덱스 3개(`v3_scores`·`lowvol_scores`·`wu_scores` 의 `(model_id, run_id)`). **실측 이득은 작다**: 판정 스크립트의 전체 행 읽기 0.12→0.10초, 리더보드 23만 행 읽기 0.24→0.22초 — DB 가 이미 페이지 캐시로 빨랐다. 무해하고(생성 1초, 크기 변화 없음) 사본이 있어 유지. 되돌리려면 `DROP INDEX idx_v3_scores_mr` 등 3줄.
- **history.db 백업이 주 1회 → 매일**(`cleanup.py --backup-gap 1 --backup-keep 10`, 보존 10개 ≈ 2주). ohlcv 전체 사본은 **주 1회 그대로**(`ohlcv_gap_days=7` 가드 추가 — 수백 MB 라 매일은 과함, 시세는 다시 받을 수 있음). 최대 손실 7일 → 1일.
- 자료 건강 점검표에 **업종 분류 갈래**(15번째): `sector_cache.json` 날짜(허용 30거래일 — 새 종목 때만 바뀜) + **최신 run 종목 중 업종 있는 비율 < 90% 면 ⚠️**. 현재 2,349종목 분류·커버 ok.

## 2. 왜
- 진화 검토 2차(`research/handoff/CLAUDE_20261018_evolution_review2.md` §2) 의 작은 과제 C·E·D 일부 — 결과 0-diff 인 것만 일요일 밤에.
- 업종 자료가 '없다'는 1차 전제가 틀렸음을 확인(실측 2,358종목·49업종) → 조용히 비는 것만 감시.

## 3. 어떻게 · 검증
- 인덱스: 생성 전 `history_20261018_preindex.db.gz`(OneDrive, 86.5MB, sqlite backup API 로 정합 복제) → `CREATE INDEX IF NOT EXISTS` 3개 → `pragma quick_check` ok → 같은 조회 3회 최소 시간 전후 비교(위 숫자).
- `cleanup.py`: `backup_db(keep, min_gap_days, ohlcv_gap_days=7)` + CLI `--backup-gap`·`--backup-keep`. `.bat` 1줄 변경(ASCII·CRLF 유지, 비ASCII 0바이트 확인).
- `data_health.py`: `BRANCHES` 에 `sector`, 수집에 커버 비율(`cover`), 판정에 `COVER_MIN=0.9` 규칙. `tests/test_data_health.py` +3 체크(커버 85% → ⚠️, 99.6% → ok, 갈래 15).

## 4. 영향 범위
- 배치 소요 +수 초(백업 gzip 매일 ~12초). OneDrive 용량 +86MB/일 × 10개.
- 점수·판정·docs 산출 불변.

## 5. 바뀐 파일
`cleanup.py` · `run_all_and_diversify.bat`(1줄+echo) · `data_health.py` · `tests/test_data_health.py` · `history.db`(인덱스 — git 밖) · `patch_note/README.md` · 이 파일.
