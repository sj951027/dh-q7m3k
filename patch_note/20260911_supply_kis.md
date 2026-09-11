# 2026-09-11 — 네이버 수급 크롤링 소멸 · 수급 소스 KIS daily_flows 교체 (2026.09.4 · 판정·점수 0-diff)

## 그래서 뭐가 바뀌나
- 스크리너의 외국인/기관 수급(5일·20일)이 네이버 크롤링 대신 **KIS 일별 투자자 수급(ohlcv.db `daily_flows`)**에서 나온다.
  값의 정의는 그대로(최근 5/20거래일 순매매량×종가 합, 억 단위 0.1 반올림)라 화면·CSV·점수 모두 전과 같은 숫자.
- 배치가 스크리너 **앞에서** KIS 수급을 한 번 더 받는다(2,520종목 · 약 4분). 뒤쪽 Large 구간의 KIS 호출은 공매도·신용·대차만(`--no-daily`).
- 텔레그램 🔔 줄에 "KIS 수급 정지" 신선도 경고 추가(수급 최신일 < 시세 최신일일 때만).

## 왜 바꿨나 (사건)
- 09-11 20:14 배치에서 네이버 수급 조회 **0/265 · 0/714**, 레짐 외인 proxy 0/10. 09-09까지는 100% 성공, 전 로그 통틀어 첫 0건.
- 원인(실측 22:0x): `finance.naver.com/item/frgn.naver?code=…` 가 `stock.naver.com/domestic/stock/{code}/investmentinfo` 로 **302** 되고,
  새 페이지는 HTML `<table>`이 없는 앱 페이지 → `pd.read_html` "No tables found" → 코드가 빈값 처리. 구 주소(`frgn.nhn`·`main.naver`)도 전부 리다이렉트.
  주소 교체로는 복구 불가(구조 변경).
- 영향(09-11 run): v30 `supply_score_v2`(가중 1.0, −10~+15) 전 종목 0 · 레짐 외인 점수 0(KIS로 재계산하면 −3) ·
  stage1 `supply_score` 0 → stage2 컷(composite ≥30) 통과 감소(stage3 175/364, 전일 192/416) → lv_b 유니버스 183(전일 209).
  즉 09-11 run은 v30 점수와 lv_b 유니버스가 함께 축소·왜곡된 상태(부분실행은 아니라 게이트엔 안 걸림).

## 어떻게
| 파일 | 변경 |
|---|---|
| `screener_fdr_v2_6.py` | `fetch_supply_data_naver()`(이름 유지, 호출부 무변경)가 `SUPPLY_SOURCE=kis`(기본)면 `_fetch_supply_kis()` — `_load_kis_flows()`가 ohlcv.db `daily_flows`를 읽기 전용으로 1회 로드해 종목별 5/20일 합을 캐시. 네이버 구 경로는 `_fetch_supply_naver_html()`로 보존(`SUPPLY_SOURCE=naver`). `SUPPLY_ASOF=YYYYMMDD`는 오프라인 재현용. KIS 경로는 sleep 없음. 수급 최신일<시세 최신일 또는 최신일 보유 종목 <90%면 경고 출력(표시 전용) |
| `kis_flows.py` | `--no-daily` 플래그(일별 수급 단계 스킵, 공매도 단계만) |
| `run_all_and_diversify.bat` | `universe_events.py` 다음·`run_and_diversify.py` 앞에 `kis_flows.py --universe all --sleep 0.1 --flows-db ..\dh-q7m3k-data\ohlcv.db --no-short` 삽입. Large 구간 기존 호출에 `--no-daily` 추가(ASCII·기존 줄바꿈 유지) |
| `notify_telegram.py` | `_freshness_warnings()`에 daily_flows 최신일 점검 추가 |

### 검증 (오프라인, 읽기 전용 — `SUPPLY_ASOF`로 그날까지만 사용)
새 경로로 계산한 값을 history.db `stage3_final`의 네이버 시절 값과 비교:

| run | stage3 종목 | KIS 커버 | 외인/기관 5일 동일 | v30 `supply_score_v2` 동일 | stage1 `supply_score` 동일 |
|---|---|---|---|---|---|
| 20260909 | 608 | 100% | 100% / 100% | 100% | 100% |
| 20260908 | 608 | 100% | 100% / 100% | 100% | 100% |
| 20260907 | 647 | 96.9% (KIS 전종목 확대 전) | 100% / 100% (커버분) | 98.3% | 98.3% |

- 20일 컬럼은 99.5~99.8% 동일(차이 ≤1.7억, 창 끝 결측일 차이) — 20일 값은 어떤 점수에도 쓰이지 않음(표시 전용).
- 레짐 외인 proxy(시총 상위 10) KIS 경로 동작 확인: 09-11 기준 외인이탈_강함 −3, 10/10 합산.
- `python tests/run_tests.py` 전체 통과(lowvol 17 · wu 10 · leaderboard 골든 15). py_compile 3파일 OK.
- 비교 스크립트는 세션 스크래치(`kis_vs_naver.py`·`kis_score_diff.py`·`replay_supply_kis.py`)에서 실행 — 산출물 없음.

## 영향범위
- **점수식·가중·임계값·판정·게이트 무변경.** 입력 공급처만 교체이며 겹치는 run에서 수급 성분 0-diff 실측.
  v30 W2b 창(PREREGISTER_v30_w2) 스펙 불변 — §4 등록 기록에 데이터 소스 교체 사실만 추가.
- 새 전제: 스크리너 앞에서 `kis_flows`가 성공해야 당일치 수급이 들어감. KIS는 당일 조회를 00:00~15:40 차단하므로
  20:10 배치는 무관. **20:14에 당일치가 KIS에 있는지는 미실측**(관측된 가장 이른 성공 20:27) — 09-14(월) 배치 로그의
  "수급 소스: KIS daily_flows … 최신 YYYYMMDD" 줄과 🔔 경고로 확인. 없으면 그날 창은 하루 밀린 5일(경고 표시).
- KIS 실패 시 수급 0(09-11과 동일 상태) — 이전보다 나빠지지 않음. 토큰 발급 횟수 불변(PTW 공유 토큰).
- 잠정치→확정치 재기록(KIS 30일 창)은 네이버 때와 같은 성질(동결 점수는 당일 잠정치).
- **미처리(별건)**: `fetch_consensus.py`도 `finance.naver.com/item/main.naver`를 크롤링 → 같은 리다이렉트로 다음 주간 실행(09-14 이후) 실패 예상. 관측 전용(점수 무관).
- 09-11 run: 수급 0 상태로 동결됨. 재실행 여부는 사용자 결정(주말 실행 시 run_id는 20260911로 자동, 사전 `research/clean_partial_run.py 20260911 --yes --force` 필요).
