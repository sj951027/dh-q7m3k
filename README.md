# KOSPI · KOSDAQ Oversold Screener (V2.6)

시장 레짐 + 펀더멘털 기반으로 **과매도 종목을 매일 발굴**하고, 섹터 쏠림을 막은
추천 리스트와 **점수 적중도(IC)**를 폰에서 볼 수 있게 만든 개인용 스크리너.

- 📱 대시보드: **https://sj951027.github.io/dh-q7m3k/**
- 실행 방식: **로컬 PC에서 수동 실행 → 결과만 GitHub에 올려 배포** (Actions로 스크리너를 돌리지 않음)

---

## 🚀 빠른 시작 (평소 루틴)

1. 바탕화면의 **`run_all_and_diversify.bat`** 바로가기 더블클릭
2. 자동 진행: **스크리너 → 섹터 분산 → 점수 적중도(IC) 계산 → GitHub 업로드**
3. 약 10초 뒤 폰에서 위 대시보드 주소를 열면 최신 결과 + IC 카드 확인

> 소요 시간: 스크리너 60~120분(PC가 계산). 업로드/배포는 별도로 ~10초(GitHub).

---

## 🔑 키 설정 (처음 한 번만)

스크리너와 섹터 분류(DART)에 API 키가 필요하다.

1. `.env.example` 을 복사해 **`.env`** 로 이름 변경
2. `.env` 를 열어 실제 키 입력: `DART_API_KEY=실제_DART_키`
3. 저장. (`.env` 는 `.gitignore`로 보호되어 GitHub에 올라가지 않음)

키 확인: https://opendart.fss.or.kr → 인증키 신청/관리 → 오픈API 이용현황

---

## 🧰 내가 직접 실행하는 것

| 파일 | 용도 | 언제 |
|---|---|---|
| `run_all_and_diversify.bat` | 스크리너+분산+IC+업로드 한 번에 | **평소 (매 거래일)** |
| `validate_scores.py` | 점수 예측력 상세 점검 (CSV 출력) | 가끔 (주1~월1) |

```
python validate_scores.py     # 상세 IC 리포트 + validation_summary.csv
```

나머지(`run_all_v2_6.py`, 각 stage, `diversify_picks.py`, `compute_ic.py`,
`build_dashboard.py`)는 위 bat이 알아서 부르는 부품이라 직접 실행할 일 없음.

---

## 📊 점수 적중도(IC) 카드 — 대시보드 맨 위

"스크리너 점수가 실제로 맞히고 있나?"를 매 실행마다 측정해 폰 카드로 보여준다.

- **큰 숫자 = 최종점수 IC**: `+0.05↑` 유효(초록) · `0 근처` 노이즈(회색) · `음수` 역작동(빨강)
- **상위↔하위 격차**: 점수 상위 1/3이 하위보다 잘 갔는지
- **요소별 칩**: 과매도·매집·수급·펀더멘털·현금흐름·모멘텀 각각의 IC → 어떤 요소가 신호이고 어떤 게 노이즈인지 한눈에
- 데이터가 적은 초반엔 "데이터 쌓는 중"으로 표시되고, 거래일마다 쌓일수록 정확해진다.

> IC 계산 로직은 `validate_scores.py`, 결과는 `docs/ic_summary.json`(카드용) +
> `docs/ic_history.json`(추세 누적).

---

## 🧪 파이프라인 단계

```
run_all_v2_6.py
├─ Stage 1  과매도 점수 (RSI·낙폭·볼린저·거래량) + 매집/추세/수급 + 시장 레짐
├─ Stage 2  DART 공시 리스크 필터 (관리종목·감사거절·거래정지·증자 등 제외)
└─ Stage 3  펀더멘털(영업이익 YoY 패턴) + 현금흐름 질(OCF) + 모멘텀
        ↓ history.db 누적 + docs/ 대시보드 생성
diversify_picks.py   섹터 쏠림 방지 (업종당 최대 N개) — DART 산업분류로 업종 자동 채움
compute_ic.py        점수 적중도(IC) 계산 → docs/ic_summary.json
```

---

## 🗂️ 데이터가 쌓이는 곳 (삭제 금지)

| 경로 | 내용 |
|---|---|
| `history.db` | 추천 종목·점수 누적 (IC 측정의 토대) |
| `snapshots/날짜/` | 단계별 결과 (parquet) |
| `archive/날짜/` | 일자별 CSV 보관 |
| `docs/` | 폰 대시보드 (index.html, data.json, ic_summary.json) |
| `sector_cache.json` | 업종 조회 캐시 (재사용) |

> 위 파일들은 자동 업로드(push)되어 GitHub에도 백업된다. **스크리너를 돌린 날만**
> 데이터가 쌓이므로, 거래일에 규칙적으로 돌리는 것이 IC 측정의 핵심.

지워도 되는 것: 날짜 붙은 옛 출력(`diversified_picks_*.csv`, `validation_*.csv`),
캐시(`price_cache/`, `dart_cache/`, `__pycache__/`). — `.gitignore`가 업로드는 막아둠.

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
python run_and_diversify.py --no-push                     # 업로드 없이 실행
python run_and_diversify.py --top 25 --max-per-sector 2   # 분산 개수 조정
python run_and_diversify.py --skip-screener               # 스크리너 건너뛰고 분산/IC만
python diversify_picks.py --demo                          # 분산 동작 예시
python validate_scores.py --self-test                     # 인터넷 없이 IC 계산 점검
```

---

## 📌 알아둘 점

- IC 첫 계산은 종목 시세를 받느라 몇 분 더 걸린다(캐시되어 이후 빨라짐). 최근 40일 ×
  시장별 상위 50개로 제한.
- 시장 레짐 점수(KOSPI/환율/외인)는 **그날 모든 종목에 동일하게 더해지므로 같은 날
  종목 간 순위에는 영향을 주지 않는다.** (기록·분석용. 일일 선택 필터로 쓰려면 별도 개선 필요.)
- 투자 판단 보조 도구이며 투자 권유가 아니다.
