# CLEANUP_NOTES — 산출물 보존정책 & 핸드오프 분리 (2026-06-10)

> run_id 20260609 시점 repo 실측 기반. 적용 파일: cleanup.py(교체), accumulate_history.py(교체),
> .gitignore(교체), make_handoff.py(신규).

## 1. 진단 (왜 커지는가)

| 항목 | 실측 | 성격 |
|---|---|---|
| dart_cache/fin | 287MB / 4,339개 | 재현 가능 캐시. 만료돼도 파일을 안 지워 무한 누적 |
| .git | 150MB | history.db(49MB)·archive·snapshots를 **매일 commit+push** → 팩 비대 |
| archive/날짜 | 91MB | history.db와 **완전 중복**(20260605 표본 578행 전 컬럼 일치 검증) |
| history.db | 49MB | **원본. 영구 보존** |
| snapshots/날짜 | 17MB | DB와 같은 행의 parquet 사본. **읽는 코드 없음**(전 스크립트 grep 확인) |
| v3_archive | 11MB | **v3 점수의 유일한 영구 기록**(DB에 v3 점수 없음). compute_ic·대시보드·텔레그램이 읽음 |
| v31a~d_archive | 16MB | 챌린저 '그날 얼린' OOS 기록 — 실험 감사용, 유지 |
| 루트 CSV들 | 수십 MB | 단계 간 전달용. 적재 후엔 중복 |

근본 원인 둘: ① git이 데이터까지 매일 push ② 캐시/중복 사본에 보존기한이 없음.

## 2. 보존 정책 (cleanup.py가 집행)

- 영구: history.db · v3_archive/ · v31*_archive/ · docs/ · latest_*_final.csv · price_cache/ · sector_cache.json
- 회전(_trash 이동): 루트 valuation/v3_final/diversified 7일 · catalyst 30일(observe --full 재백필 여지) ·
  archive/날짜 14일(**DB에 run 존재 확인 후에만**) · snapshots/날짜 7일
- 직접 삭제: dart_cache/fin 중 mtime 30일 초과(활성 키는 TTL 갱신 때 mtime이 리셋되므로 안전) + tmp 잔재

## 3. 1회 작업 — git 다이어트 (push 비대의 주범 제거)

```bat
:: ① 새 .gitignore로 교체 후
git rm -r --cached history.db archive snapshots
git rm --cached diversified_picks_*.csv validation_picks.csv validation_summary.csv
git rm --cached latest_kospi_final.csv latest_kosdaq_final.csv v3_kospi_final_20260602.csv v3_kosdaq_final_20260602.csv
git commit -m "데이터 산출물 git 추적 제외 (원본=history.db, 웹=docs/)"
git push
```

- 파일은 디스크에 그대로 남고 GitHub에서만 빠진다. Pages는 docs/만 쓰므로 **대시보드 무영향**.
- ⚠️ 이후 GitHub는 더 이상 history.db의 백업이 아님 → 주 1회 `cleanup.py --backup-db`
  (backup/history_날짜.db.gz, 최근 4개 유지) + 가끔 그 gz를 클라우드/외장에 복사 권장.
- 과거 커밋에 든 150MB는 그대로 둬도 무방(증가만 멈춤). 줄이려면 filter-repo인데
  force-push가 필요한 별도 작업이라 원할 때 따로 상의.

## 4. 일상 운영

```bat
:: 주 1회 (또는 .bat 끝에 추가해도 무해 — 보관일 안 지난 건 안 건드림)
python cleanup.py --yes --backup-db
```

- snapshots를 아예 안 만들려면(소비처 0 확인됨): 교체된 accumulate_history.py 상태에서
  .bat 상단에 `set SCREENER_NO_SNAPSHOTS=1` 한 줄. **기본값은 기존과 동일하게 생성**(끄는 건 선택).
  DB 적재 경로는 패치와 무관함을 오프라인 0 diff로 검증(아래 §6).

## 5. 핸드오프 분리 — [동작] vs [성능]

```bat
python make_handoff.py --code   :: [동작] 코드·파이프라인·속도·파일IO 작업 → 0.2MB
python make_handoff.py --perf   :: [성능] IC·챌린저 판정·관측팩터 분석 → ~12MB (db+v3_archive+docs/*.json)
python make_handoff.py          :: 둘 다
```

| 작업 종류 | 넘길 것 | 비고 |
|---|---|---|
| [동작] 리팩터·속도·IO·로그 | handoff_code_*.zip | 코드만으로 충분 |
| [성능] IC·리더보드·§11 판정 | handoff_perf_*.zip | 코드 없이 DB+JSON으로 분석 가능 |
| 점수·출력에 닿는 변경 | **둘 다** | "결과 0 diff" 증명에 DB가 반드시 필요 |

옵션: --with-price-cache(IC 오프라인 재계산시), --with-model-archives(보통 불필요 — compare_models는 DB 재계산).

## 6. 검증 내역 (오프라인, 이 repo의 history.db 기준)

- archive ↔ DB 중복성: 20260605 kospi final 578행, 공통 전 컬럼 **완전 일치** → 회전 안전.
- accumulate 패치(0 diff): 20260609 양 시장 CSV를 패치본으로 재적재 → 원본 DB 대비
  stage1(62컬럼)/stage2(79)/stage3(CSV 유래 116)/runs(12) **전부 일치**.
  (stage3의 smartmoney_trigger·catalyst_score 차이는 2.7단계 관측 채움분 — CSV에 없는 컬럼, 패치 무관.)
- cleanup 실적용 리허설: 18건 이동·보존 대상 전부 무사·DB run 수 불변(15)·--backup-db 정상.
- handoff 생성: code 42파일 0.2MB(데이터 유입 0) / perf 19파일 12.4MB(db+v3_archive 14csv+json).
- 미검증(사용자 1회 확인 필요): 실제 일일 실행에서 cleanup·핸드오프가 Windows 경로에서도 동일 동작하는지,
  dart_cache 프루닝 실측(이쪽 샌드박스는 파일 mtime이 추출 시각이라 0건이 정상).
