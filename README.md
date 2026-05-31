# KOSPI · KOSDAQ Oversold Screener (V2.6)

시장 레짐 + 펀더멘털 기반으로 **과매도 종목을 매일 발굴**하고, 섹터 쏠림을 막아
필터/정렬로 보고, **점수 적중도(IC)**까지 폰에서 확인하는 개인용 스크리너.

- 📱 대시보드: **https://sj951027.github.io/dh-q7m3k/**
- 🔍 필터·정렬: **https://sj951027.github.io/dh-q7m3k/filter.html**
- 실행 방식: **로컬 PC에서 수동 실행 → 결과만 GitHub에 올려 배포** (Actions로 스크리너를 돌리지 않음)

---

## 🚀 빠른 시작 (평소 루틴)

1. 바탕화면의 **`run_all_and_diversify.bat`** 바로가기 더블클릭
2. 자동 진행: **스크리너 → 섹터 분산 → 점수 적중도(IC) → GitHub 업로드 → 텔레그램 알림**
3. 끝나면 텔레그램으로 "완료 + IC + TOP3 + 링크"가 오고, 링크를 누르면 폰/PC 어디서든 웹으로 확인

> 소요 시간: 스크리너 60~120분(PC가 계산). 업로드/배포는 별도로 ~10초(GitHub).

---

## 🔑 키 설정 (처음 한 번만)

`.env.example` 을 복사해 **`.env`** 로 이름을 바꾸고, 아래 키를 입력한다.
(`.env` 는 `.gitignore`로 보호되어 GitHub에 올라가지 않음)

```
DART_API_KEY=실제_DART_키            # 스크리너 + 섹터 분류에 필요
TELEGRAM_BOT_TOKEN=봇_토큰           # 완료 알림 (선택)
TELEGRAM_CHAT_ID=챗_아이디           # 완료 알림 (선택)
```

- DART 키: https://opendart.fss.or.kr → 인증키 신청/관리 → 오픈API 이용현황
- 텔레그램: @BotFather 로 봇 생성 → 토큰 / 봇에 메시지 후 `getUpdates`로 chat id
  (텔레그램 키가 없으면 알림 단계는 조용히 건너뛴다)

---

## 🧰 내가 직접 실행하는 것

| 파일 | 용도 | 언제 |
|---|---|---|
| `run_all_and_diversify.bat` | 스크리너+분산+IC+업로드+알림 한 번에 | **평소 (매 거래일)** |
| `validate_scores.py` | 점수 예측력 상세 점검 (CSV 출력) | 가끔 (주1~월1) |

```
python validate_scores.py     # 상세 IC 리포트 + validation_summary.csv
```

나머지(`run_all_v2_6.py`, 각 stage, `diversify_picks.py`, `compute_ic.py`,
`build_dashboard.py`, `notify_telegram.py`)는 bat이 알아서 부르는 부품.

---

## 🔍 필터 페이지 — 켰다 껐다 보기

`filter.html` 은 최신 결과를 **필터/정렬/검색**으로 보는 화면.

- 상단 **KOSPI / KOSDAQ** 토글로 시장 전환 (최신 데이터 자동 로드)
- 실적패턴·OCF·위험등급·점수범위·수급·종목검색 필터를 자유롭게 on/off
- **🧭 섹터 분산** 토글: 켜면 업종당 최대 N개만(점수순) → 쏠림 제거된 뷰, 끄면 전체
  - 업종은 `diversify_picks.py`가 DART로 채운 `docs/latest_{시장}_enriched.csv`에서 읽음
- 메인 대시보드의 "🔍 필터·정렬·검색으로 자세히 보기" 버튼으로 진입

---

## 📊 점수 적중도(IC) 카드 — 대시보드 맨 위

"스크리너 점수가 실제로 맞히고 있나"를 매 실행마다 측정해 카드로 표시.

- **큰 숫자 = 최종점수 IC**: `+0.05↑` 유효(초록) · `0 근처` 노이즈(회색) · `음수` 역작동(빨강)
- **상위↔하위 격차**: 점수 상위 1/3이 하위보다 잘 갔는지
- **요소별 칩**: 과매도·매집·수급·펀더멘털·현금흐름·모멘텀 각각의 IC → 어떤 게 신호이고 어떤 게 노이즈인지
- 데이터가 적은 초반엔 "데이터 쌓는 중"으로 표시되고, 거래일마다 쌓일수록 정확해진다.

> IC 로직은 `validate_scores.py`, 결과는 `docs/ic_summary.json` + `docs/ic_history.json`(추세).

---

## 🧪 파이프라인 단계

```
run_all_v2_6.py
├─ Stage 1  과매도 점수 (RSI·낙폭·볼린저·거래량) + 매집/추세/수급 + 시장 레짐
├─ Stage 2  DART 공시 리스크 필터 (관리종목·감사거절·거래정지·증자 등 제외)
└─ Stage 3  펀더멘털(영업이익 YoY 패턴) + 현금흐름 질(OCF) + 모멘텀
        ↓ history.db 누적 + docs/ 대시보드 생성 + latest_*.csv 를 docs/로 복사
diversify_picks.py   섹터 쏠림 방지 + docs/latest_*_enriched.csv (업종 채운 전체)
compute_ic.py        점수 적중도(IC) → docs/ic_summary.json
notify_telegram.py   완료 + IC + TOP3 + 링크 알림
```

---

## 🗂️ 데이터가 쌓이는 곳 (삭제 금지)

| 경로 | 내용 |
|---|---|
| `history.db` | 추천 종목·점수 누적 (IC 측정의 토대) |
| `snapshots/`, `archive/` | 단계별 결과 / 일자별 CSV 보관 |
| `docs/` | 폰 대시보드·필터·IC·CSV (배포되는 폴더) |
| `sector_cache.json` | 업종 조회 캐시 (재사용) |

> 자동 push되어 GitHub에도 백업된다. **스크리너를 돌린 날만** 데이터가 쌓이므로,
> 거래일에 규칙적으로 돌리는 것이 IC 측정의 핵심.

---

## 🧹 파일 정리 (선택)

지워도 되는 것 (생성물·임시·옛버전 — `.gitignore`가 재업로드는 막음):

- `diversified_picks_*.csv`, `validation_*.csv`, `v2_kospi_*.csv`, `v2_kosdaq_*.csv` — 날짜별 임시 출력
- `__pycache__/`, `dart_cache/`, `price_cache/` — 캐시 (재생성)
- `README_AUTOMATION.md`, `SETUP_GUIDE.md`, `SETUP_LOCAL.md` — 옛 GitHub Actions 자동화 문서 (현재 방식과 불일치)
- `csv_filter2_v26.html` — 원본 필터 (이제 `docs/filter.html`이 대체)
- `gitignore`(점 없는 파일이 따로 있으면) — 진짜는 `.gitignore`. 점 없는 건 삭제

남기는 것: 모든 `.py`, `run_all_and_diversify.bat`, `.env`, `.gitignore`,
`.github/workflows/deploy-pages.yml`, `requirements.txt`, `README.md`, 그리고 위 "삭제 금지" 데이터.

---

## ☁️ 배포 구조 (GitHub Pages)

- 스크리너는 **로컬에서 실행** → Actions 시간 거의 0
- `docs/` 가 push되면 **`deploy-pages.yml`** 가 ~10초 만에 Pages 배포 (스크리너 재실행 안 함)
- 자동 push는 `run_and_diversify.py`에 내장. `.env`가 `.gitignore`로 보호되지 않으면
  키 유출 방지를 위해 **push를 스스로 중단**한다.

> 첫 push에서 인증 오류가 나면 GitHub Desktop을 한 번 열어 로그인하면 이후 자동화됨.

---

## ⚙️ 옵션

```
python run_and_diversify.py --no-push                     # 업로드/알림 없이 실행
python run_and_diversify.py --top 25 --max-per-sector 2   # 분산 개수 조정
python run_and_diversify.py --skip-screener               # 스크리너 건너뛰고 분산/IC만
python diversify_picks.py --demo                          # 분산 동작 예시
python validate_scores.py --self-test                     # 인터넷 없이 IC 계산 점검
python notify_telegram.py                                 # 텔레그램 알림만 테스트
```

---

## 📌 알아둘 점

- IC 첫 계산은 종목 시세를 받느라 몇 분 더 걸린다(캐시되어 이후 빨라짐). 최근 40일 × 시장별 상위 50개로 제한.
- **시장 레짐 점수(KOSPI/환율/외인)는 그날 모든 종목에 동일하게 더해져, 같은 날 종목 간 순위에는 영향을 주지 않는다.** 현재는 기록·표시용. (선택에 반영하려면 별도 개선 필요 — 차후 과제.)
- 투자 판단 보조 도구이며 투자 권유가 아니다.
