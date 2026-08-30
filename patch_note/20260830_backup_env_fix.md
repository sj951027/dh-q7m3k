# 2026-08-30 — 백업 오프사이트 경로(.env BACKUP_DIR) 실동작 수정

## 뭐가
cleanup.py 의 backup_db() 앞에 `_load_dotenv_backup_keys()` 추가:
.env 의 BACKUP_DIR / BACKUP_OHLCV / OHLCV_DB 를 os.environ 에 반영(실제 환경변수가
이미 있으면 그것이 우선, 실패는 비치명 → 로컬 backup/ 폴백).

## 왜
.env 에 `BACKUP_DIR=C:\Users\SAMSUNG\OneDrive\screener` 가 지정돼 있었지만,
cleanup.py 는 .bat 에서 단독 프로세스로 실행돼 .env 를 읽지 않았음(실측: 백업이
계속 로컬 backup/ 에만 쌓임 — history_20260807~0828.db.gz). 로컬 백업은 원본과
같은 디스크라 디스크 장애 시 함께 소실 — 오프사이트(OneDrive 동기화)가 원래 의도.

## 어떻게 + 검증
- VM 오프라인 테스트(임시 폴더, 가짜 history.db + .env): ① BACKUP_DIR 지정 시
  해당 폴더에 gzip 생성 ② 7일 가드 정상(재호출 skip) ③ .env 없으면 로컬 backup/
  폴백 ④ gzip 해제 후 sqlite 정상 오픈(행 보존) — ALL PASS.
- ast 구문 검사 통과. 점수·판정·게이트 코드 무접촉 → **판정·점수 0-diff (해당 없음)**,
  tests/run_tests.py 대상 아님.

## 영향범위
- 다음 .bat 실행부터 백업이 OneDrive\screener 로 감(빈 폴더라 가드 없이 즉시 1회 생성).
  용량: history gz(~수십MB)×4 + ohlcv_full gz(~150MB)×2 ≈ 수백MB 수준.
- 기존 로컬 backup/ 6개 파일은 그대로 남음(회전 대상 아님) — 이중 사본으로 두거나
  수동 삭제 가능.
