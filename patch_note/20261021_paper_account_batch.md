# 2026.10.35 — 모의 계좌를 배치에 연결 (`python paper_account.py`, 비치명) (2026-10-21)

## 뭐가
- `run_all_and_diversify.bat`: `build_scoreboard.py` 다음·`data_health.py` 앞에 `python paper_account.py` 한 줄(ASCII·CRLF 유지). 실패해도 배치를 막지 않는다(스크립트가 종료코드 0 으로 끝남, FAILED 표식 없음).
- 매일 되감기 전체를 다시 계산해 `../dh-q7m3k-data/paper_account.db` 와 `docs/paper_account.json` 을 갱신(약 25초, 무작위 100벌). 라벨은 **'사후'** — 등록(동결)은 2판(상폐 −90% 처리·코스닥 소형 비용 감도) 뒤 사용자 승인으로.

## 왜
- 사용자 결정(10/21): "붙이자, 등록은 2판 뒤". 매일 돌아야 '돈 기준' 숫자가 최신이고 자료 문제가 일찍 드러난다. 되감기라 매일 안 돌려도 자료는 안 잃는다.

## 검증
- 10/20 밤 수동 실행 OK(계좌 7장, 24초). 첫 배치 실행은 10/22 20:10 — 로그에 `✓ paper_account.db · docs/paper_account.json` 줄 확인. 점수·판정 0-diff.
