# KOSPI · KOSDAQ Oversold Screener

시장 레짐 + 펀더멘털로 **과매도·턴어라운드 후보를 매일 발굴**하고, **v3 등급/버킷**으로 정리해
섹터 쏠림을 막아 보여주며, **점수 적중도(IC)**와 **챔피언/챌린저 모델 비교**까지 폰에서 확인하는
개인용 스크리너.

- 📱 대시보드: **https://sj951027.github.io/dh-q7m3k/**
- 🔍 필터·정렬: **https://sj951027.github.io/dh-q7m3k/filter.html**
- 실행 방식: **로컬 PC에서 수동 실행 → 결과만 GitHub에 올려 배포** (Actions로 스크리너를 돌리지 않음)

> ⚠️ 투자 판단 보조 도구이며 **투자 권유가 아닙니다.**

---

## 📚 Claude/협업자용 — 먼저 읽을 지식 문서 (handoff 시 맥락)

> zip(handoff)만 받았다면 코드 전에 이 문서들을 읽어야 "무엇을/왜"가 잡힌다. 트랙이 **3개**다.

| 문서 | 내용 | 트랙 |
|---|---|---|
| `PROJECT_KNOWLEDGE.md` | **메인 핸드오프.** 파이프라인·점수체계·모듈·불변규칙·실험판정(§11)·견고성(§12)·lowvol(§13) | v3(주) |
| `LARGE_SCORE_DESIGN.md` | 대형 가치주 트랙 설계(시총 상위·금융 포함·과매도 게이트 없음) | large |
| `LOWVOL_TRACK_DESIGN.md` | 저변동·우량·반전 트랙 설계·검증(lv_a~d·lv_a3) | lowvol |
| `PREREGISTER_v31f_maturity.md` | v31f/g 챌린저 골대(post-hoc forward-only) | v3 |
| `PREREGISTER_lowvol.md` | lowvol 골대(OOS 40거래일·Bonferroni 5) | lowvol |
| `CLEANUP_NOTES.md` | 산출물 보존정책·git 다이어트·handoff 분리 | 운영 |

**3트랙 한눈에**: v3=중소형 과매도 반등(메인, 표시 기준) · large=대형 가치(설계/구축 중) ·
lowvol=적당히 빠진 우량 저변동(1단계 관측 배포, lv_a 테스트 노출). **셋의 점수·유니버스·표시는 분리**,
데이터·인프라(history.db·대시보드·텔레그램·git)만 공유.

---

## 🧠 점수 체계 (2층 구조)

- **v2.6 엔진 (`final_score`)** — 과매도 + 매집 + 추세 + 수급 + 펀더멘털(영업이익 YoY) + 모멘텀 + OCF(현금흐름 질) + 시장 레짐. *원본 점수 엔진.*
- **v3 (현재 표시 기준)** — v2.6을 입력으로 재점수화해 사람이 읽기 쉬운 형태로:
  - `grade` : **A+ / A / B / C / WATCH / EXCLUDE**
  - `bucket` : **BUY / WAIT / OBSERVE / WATCH / EXCLUDE**
  - 대시보드·필터·텔레그램은 모두 v3 기준으로 표시·정렬한다.
- **관측 팩터 (가중치 0)** — `smartmoney`·`ROE`·`자사주 소각` 등을 점수에 넣지 않고 **따로 쌓아두어**,
  나중에 예측력(IC)이 검증되면 다음 모델로 승격한다. *지금 점수에는 영향 없음.*

---

## 🚀 빠른 시작 (평소 루틴)

1. **`run_all_and_diversify.bat`** 더블클릭
2. 자동 진행: **스크리너 → v3 점수 → 챌린저 섀도우 → 섹터 분산 → 촉매(자사주) → 관측팩터 배선 → IC → 대시보드 → GitHub 업로드 → 텔레그램**
3. 끝나면 텔레그램으로 "완료 + TOP + 링크"가 오고, 링크로 폰/PC 어디서든 확인

> 소요: 보통 **~20–30분**(PC가 계산). DART 재무는 캐시되어 **같은 날 재실행은 훨씬 빠르다**. 업로드/배포는 ~10초.

---

## 🔑 키 설정 (처음 한 번만)

루트에 **`.env`** 파일을 만들고 아래 키를 채운다. (`.env`는 `.gitignore`로 보호되어 GitHub에 올라가지 않음 — **절대 커밋 금지**)

```
DART_API_KEY=...          # DART 오픈API 인증키 (스크리너 + 섹터 분류)
KRX_ID=...                # KRX 데이터 계정 (밸류에이션 PBR/PER/BPS/EPS 조회)
KRX_PW=...                # KRX 비밀번호
TELEGRAM_BOT_TOKEN=...    # 완료 알림 (선택)
TELEGRAM_CHAT_ID=...      # 완료 알림 (선택)
```

- DART 키: https://opendart.fss.or.kr → 인증키 신청/관리
- 텔레그램이 없으면 알림 단계는 **조용히 건너뛴다**.

---

## 🧪 파이프라인 단계 (`run_and_diversify.py`)

```
run_all_v2_6.py                 # 1단계: 스크리너 (KOSPI + KOSDAQ)
├─ Stage 1  과매도 점수(RSI·낙폭·볼린저·거래량) + 매집/추세/수급 + 시장 레짐
├─ Stage 2  DART 공시 리스크 필터(관리종목·감사·거래정지·증자 등 / 가짜악재 방어)
└─ Stage 3  펀더멘털(영업이익 YoY) + 현금흐름 질(OCF) + 모멘텀 → final_score
        ↓ history.db 누적 + 1차 대시보드
v3_daily.py        # 2.6: 밸류에이션(fetch_valuation) → v3 재점수(grade/bucket) → docs 병합
shadow_run.py      # 2.65: 챔피언 대비 챌린저(v31a~d)를 그림자로 누적 (표시·점수 영향 0)
diversify_picks.py # 2: 섹터 쏠림 방지 + docs/latest_*_enriched.csv (업종 채운 전체)
catalyst_insider.py# 2.68: 촉매 수집 — 현재 '자사주 소각'만 (내부자 매수는 기본 OFF, 아래 참고)
catalyst_observe.py# 2.7: 관측 팩터(smartmoney/ROE/자사주)를 history.db에 배선 (가중치 0)
compute_ic.py      # 2.5: 점수 적중도(IC) → docs/ic_summary.json
build_dashboard.py # 2.8: v3 반영 대시보드 재생성
                   # 3: git push  →  4: 텔레그램 알림
```

---

## 🔁 챔피언 / 챌린저 (모델 실험)

점수 모델 변경을 **실제 표시·추천에 영향 없이** 그림자로만 매일 누적해, 충분한 표본 뒤 데이터로 채택을 판단한다.

- 챔피언 = 현재 v3. 챌린저 = v3에서 **변수 하나만** 바꾼 후보들(진입게이트·수급가중·유동성하한·섹터중립화).
- `python compare_models.py` → 모델별 IC / 수익 비교 + `docs/model_compare.json`.
- **판정은 충분한 표본(약 40거래일) 이후** — 며칠치 결과는 노이즈로 본다. 아무도 못 이기면 챔피언 유지(정상).

---

## 🔍 필터 페이지 — 켰다 껐다 보기

`filter.html`은 최신 결과를 **필터/정렬/검색**으로 보는 화면.

- 상단 **KOSPI / KOSDAQ** 토글로 시장 전환
- 실적패턴·OCF·등급·점수범위·수급·종목검색 필터 on/off
- **🧭 섹터 분산** 토글: 켜면 업종당 최대 N개(점수순) → 쏠림 제거 뷰
  - 업종은 `diversify_picks.py`가 캐시/ DART로 채운 `docs/latest_{시장}_enriched.csv`에서 읽음 (현재 거의 전 종목 분류)

---

## 📊 점수 적중도(IC) 카드 — 대시보드 맨 위

"점수가 실제로 맞히고 있나"를 매 실행마다 측정해 카드로 표시.

- **큰 숫자 = IC**: `+`(초록, 유효) · `0 근처`(회색, 노이즈) · `–`(빨강, 역작동)
- **상위↔하위 격차**, **요소별 칩**(과매도·매집·수급·펀더·현금흐름·모멘텀 + 관측팩터)
- 데이터가 적은 초반엔 "데이터 쌓는 중"으로 표시되고, 거래일마다 쌓일수록 정확해진다.

> IC 로직 `validate_scores.py` / `compute_ic.py`, 결과 `docs/ic_summary.json`(+ `ic_history.json` 추세).

---

## 🗂️ 데이터가 쌓이는 곳 (삭제 금지)

| 경로 | 내용 |
|---|---|
| `history.db` | 추천 종목·점수·관측팩터 누적 (IC·모델비교의 토대) |
| `archive/` | 일자별 CSV 보관 |
| `docs/` | 폰 대시보드·필터·IC·모델비교·CSV (배포 폴더) |
| `sector_cache.json` | 업종 조회 캐시 (재사용) |
| `dart_cache/` | DART 재무 응답·기업코드 캐시 (재실행 가속, gitignore) |

> 자동 push되어 GitHub에도 백업된다. **돌린 날만** 데이터가 쌓이므로, 거래일에 규칙적으로 돌리는 것이 IC의 핵심.

---

## ⚙️ 옵션

```
python run_and_diversify.py --no-push                     # 업로드/알림 없이 실행
python run_and_diversify.py --top 25 --max-per-sector 2   # 분산 개수 조정
python run_and_diversify.py --skip-screener               # 스크리너 건너뛰고 이후 단계만
python compare_models.py                                  # 챔피언/챌린저 비교 (주 1회 권장)
python catalyst_observe.py --full                         # 관측 컬럼 강제 전체 재백필
python catalyst_insider.py --with-insider                 # (비권장) 내부자 매수까지 수집
python diversify_picks.py --demo                          # 분산 동작 예시
python validate_scores.py --self-test                     # 인터넷 없이 IC 계산 점검
```

---

## 📌 알아둘 점

- IC는 **최근 40거래일 × 시장별 상위 50종목**으로 측정(속도 + 실제 관심권). 첫 계산은 시세를 받느라 몇 분 더 걸리고 이후 캐시로 빨라진다.
- **시장 레짐 점수(KOSPI/환율/외인)는 그날 모든 종목에 동일하게 더해져, 같은 날 종목 간 순위에 영향이 없다** → v3는 같은 날 랭킹에서 이를 제외한다.
- **내부자 매수(elestock)는 기본 비활성.** DART 소유보고 요약은 *증감 사유*(장내매수 vs 무상증자·상속·스톡옵션 등)를 구분하지 못해 신호가 오염된다. 해석 여지가 없는 **자사주 소각만** 촉매로 사용한다. (`--with-insider`로 켤 수는 있으나 위 한계로 권장하지 않음.)
- DART 재무 캐시: 제출된 보고서는 불변이라 길게(기본 14일) 캐시하고, 미제출은 짧게(12h) 재확인 → 정확성 유지하며 재실행을 가속.
- 다시 강조 — **투자 권유가 아니며**, 모든 판단과 책임은 사용자에게 있다.
