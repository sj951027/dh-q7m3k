# 운영 가이드 — dh-q7m3k 한 장 요약 (2026-06-10)

## 매일
- `run_all_and_diversify.bat` 더블클릭. 끝까지 자동(스크리너→v3→추천→촉매→IC→대시보드→push→텔레그램).
- 결과 보는 곳: 텔레그램 요약 + https://sj951027.github.io/dh-q7m3k/ (필터 페이지 포함).
- 파일을 직접 열어볼 필요 없음 — 필요한 건 전부 DB와 웹에 쌓인다.

## 주 1회
```bat
python cleanup.py --yes --backup-db    :: 오래된 산출물 회전 + DB 압축 백업(backup/, 최근 4개)
python compare_models.py               :: 챌린저 추세 확인 (판정은 40거래일 §11 기준, 그 전엔 노이즈)
```
- 월 1회쯤 `backup\history_*.db.gz` 하나를 클라우드/외장에 복사.
  **GitHub는 이제 history.db의 백업이 아니다** — 이 백업이 유일한 보험.

## Claude에게 작업 맡길 때 (핸드오프)
| 작업 종류 | 만들기 | 올릴 것 |
|---|---|---|
| [동작] 코드 수정·버그·속도·파일IO | `python make_handoff.py --code` | handoff_code_*.zip (0.2MB) + **에러로그 복사** |
| [성능] IC·챌린저 판정·N일 점검·관측팩터 | `python make_handoff.py --perf` | handoff_perf_*.zip (~12MB) |
| 점수·출력을 바꾸는 변경 | `python make_handoff.py` | **둘 다** (0 diff 검증에 DB 필요) |
| 설계·아이디어 논의 | — | 파일 없이 그냥 질문 |

- zip은 `handoff\`에 생김 → 채팅창에 드래그. 메시지 첫머리에 **[동작]/[성능]** 붙이기.
- perf zip은 **그날 bat 실행이 끝난 뒤** 만들 것(최신 run 포함되게).
- 옛 zip은 쌓이면 그냥 삭제(gitignore라 GitHub엔 안 올라감). 헷갈리면 zip 없이 먼저 물어봐도 됨.

## 무엇이 남고 무엇이 지워지나
- **영구 보존**: history.db(원본) · v3_archive(v3 점수의 유일한 기록) · v31*_archive(챌린저 OOS) ·
  docs(웹) · latest_*_final.csv · price_cache · sector_cache.json
- **자동 회전**(cleanup이 _trash/로 이동): 루트 CSV 7일 · catalyst 30일 · archive 14일 · snapshots 7일
- **직접 삭제**: DART 캐시 30일 초과분
- _trash는 며칠 두고 이상 없으면 `python cleanup.py --empty-trash`로 비움.

## 문제 생겼을 때
- 잘못 지워진 듯 → `_trash\날짜\`에서 도로 꺼내면 끝.
- DB가 깨짐 → `backup\history_*.db.gz`를 압축 프로그램(반디집 등)으로 풀어 history.db로 교체.
- push 실패 → GitHub Desktop 한 번 열어 로그인 후 재시도.
- 디스크 급함 → `dart_cache` 폴더 통째 삭제 OK(다음 stage3 1회만 2~3분 느려짐).
- snapshots 안 만들기(선택) → bat에서 `python run_and_diversify.py` 윗줄에 `set SCREENER_NO_SNAPSHOTS=1`.

## 가끔 쓰는 명령
```bat
python catalyst_insider.py             :: 촉매(자사주 소각) 단독 재수집
python catalyst_observe.py --full      :: 과거 run 관측팩터 강제 덮어쓰기
python cleanup.py --dry-run            :: 정리 미리보기(아무것도 안 옮김)
```
