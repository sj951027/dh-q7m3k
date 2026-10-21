# 외부 도구·데이터 카탈로그 (한국주식 스크리너용) — 2026-10-21 웹 조사

범례: [실측] = 해당 페이지에서 직접 확인 · [2차] = 블로그/제3자 요약 · [미확인] = 찾지 못함.
스타 수는 2026-10-21 GitHub 페이지 표시값(스냅샷). 마지막 커밋 날짜는 GitHub 페이지에 안 보여 대부분 미확인.

## 1. 한국시장 가격 데이터 (최우선: 10년 생존편향 없는 일봉)

| 소스 | 형태 | 수정주가 | 상장폐지 종목 시세 | 한도/약관 | 비용 | 비고 |
|---|---|---|---|---|---|---|
| FinanceDataReader https://github.com/FinanceData/FinanceDataReader | pip, MIT, ★1.6k [실측] | 국내주식 "모두 수정가격" 명시(wiki, 2021) [실측] | `fdr.StockListing('KRX-DELISTING')` 목록 + `fdr.DataReader('코드', exchange='KRX-DELISTING')` 로 상장일~폐지일 OHLCV(+거래대금·상장주식수·액면가·거래정지·관리종목 플래그) [실측 wiki] | KRX bld 엔드포인트 스크래핑, 1회 2년치 제한 [2차 AlgoLab] | 무료 | **폐지종목 수정주가 여부는 명시 없음** → 액면분할 종목은 검증 필요. 목록 CSV 로딩 실패 시 빈 DF 조용히 반환 [2차] |
| pykrx https://github.com/sharebook-kr/pykrx | pip, ★1.1k, 라이선스 표시 없음 [실측] | 기본 adjusted=True(네이버), adjusted=False → KRX 원시가 | 네이버 소스는 폐지종목 없음, KRX 소스는 폐지종목 종가 있음(수정 안 됨). 2021-10 #89 이후 "부정확 폐지 데이터는 제공 안 함"으로 변경, 이슈 Open [실측] | README "무분별한 호출 자제", 예제 1초 sleep, 과다 호출 시 KRX 차단 [실측]; 티커 목록 프로세스당 1회 캐시 [2차] | 무료 | `get_market_ticker_list(날짜)` 로 과거 시점 유니버스 복원 가능 → 생존편향 제거의 핵심 함수. 시총·수급·펀더멘털(PER/PBR/DIV) 스냅샷 제공 |
| KRX 정보데이터시스템 data.krx.co.kr | 웹 CSV/Excel | 원시가(수정 아님) | 통계 메뉴에 폐지종목 포함 가능(OTP 2단계 요청) [2차] | 자동화 시 차단 위험, 2년치/회 | 무료 | FDR·pykrx가 실제로 쓰는 원천. 상업적 이용은 KRX Data Marketplace 유료 [실측 data.go.kr 문구] |
| KRX Open API openapi.krx.co.kr | REST, 인증키 | 미확인 | 미확인 | 서비스별(유가·코스닥·코넥스 일별매매정보·종목기본정보 6건) 개별 승인, 약 1일 [2차]; 호출 10,000건·2010년 이후·매일 08시 갱신 [2차 MCP 문서, 공식 미확인] | 무료로 알려짐 [미확인] | 공식 페이지는 본문 비어 있어 직접 가입해서 확인해야 함 |
| 공공데이터포털 금융위 주식시세정보 https://www.data.go.kr/data/15094808/openapi.do | REST | 원시가(시·고·저·종·거래량·거래대금) [실측] | 명시 없음 | 개발계정 10,000/일, 운영계정은 활용사례 등록 후 증설 [실측]; 영업일 다음날 13시 이후 갱신 | 무료, **공공누리 4유형(상업적 이용 금지·변경 금지)** [실측] | 자매 API 15094775 KRX상장종목정보(ISIN·법인번호) [실측]. 시작일 미표기 |
| KIS OpenAPI 일자별 시세 | REST(appkey) | FID_ORG_ADJ_PRC 로 수정/원시 선택(의미가 직관과 반대라는 지적) [2차] | 현재 상장 종목만(마스터 기본값) [2차] | 1회 최대 100건, 초당 한도(EGW00201) | 계좌 필요 | 대량 과거수집용 아님. 백테스트 값 대조·실거래용 |
| 네이버 금융 sise_day / fchart | 비공식 HTML/XML | 수정주가 | 폐지종목 일봉 **있음**(quant-airflow가 폐지분 백필에 사용, 거래대금은 근사) [실측 README] | 약관상 과도한 자동접근 금지, 429/IP 차단 사례 [2차] | 무료 | 공식 API 아님. pykrx #89는 "네이버는 폐지종목 없음"이라 했으나 2026 quant-airflow는 받는다고 함 → 직접 확인 필요 |
| OpenDART https://opendart.fss.or.kr | REST | — (재무·공시) | 폐지 법인 공시 보존 | 일 20,000건(응답코드 020) [2차], 분당 100회 이상 시 제한 [dart-fss 문서] | 무료 | 라이브러리 dart-fss(pip), opendart-client |
| FnGuide DataGuide https://dataguide.fnguide.com | 엑셀 애드인 | 예 | 예(기관용 DB, 자본금변동 포함) | 기관 대상 | 유료, 가격 비공개(영업기획팀 문의) [실측] | 개인 요금제 미확인. 대학 도서관 구독이 다수 |
| 코스콤 데이터몰 / 체크엑스퍼트 | — | — | — | — | [미확인] | 검색으로 가격·구성 확인 못 함 |
| 퀀터스(Quantus) | 앱/웹 | 내부 | 내부(미공개) | — | 이용권·마일리지 결제, 금액 미확인 [실측 앱스토어] | 데이터 내보내기 불가로 보임(미확인) |
| 퀀트킹 | Windows 프로그램(네이버 카페 배포) | 내부 | 미확인 | — | 연 17.5만원 [2차 영상 요약] | 백테스트 기능 추가됨(2025) [2차] |

### 생존편향 제거 실무 포인트 (AlgoLab 2026-09 글 요약 [2차] + 교차 확인)
- 폐지 규모: KRX 원본 상장폐지 전체 4,185행(주권 2,105). 최근 10년 주권 폐지 575(KOSDAQ 353·KONEX 115·KOSPI 107). 2015-09 유니버스 ~1,842 중 14.4% 소멸(추정).
- 합병·완전자회사화 계열 ≈20% → 일괄 −100% 처리 금지, 사유별 분기(FDR 목록 Reason·ToSymbol 컬럼).
- 6자리 코드 재사용 사례 있음 → ISIN 같이 저장(공공데이터 KRX상장종목정보 API 또는 pykrx).
- 정리매매 구간은 가격제한·유동성 달라 종가 청산 가정이 낙관적. 스팩 제외 여부 먼저 결정.
- 데이터 하한: KRX 통계는 2000-01-01 이후 [2차].
- **권장 절차**: ① FDR 'KRX-DELISTING' 목록 + 'KRX-DESC'(현재) 합집합 = 전 종목 마스터 ② pykrx `get_market_ticker_list(d)` 로 리밸런싱일별 유니버스 ③ 가격은 FDR(현재종목·폐지종목 모두) → KRX 원시가와 종가 대조로 수정주가 오류 탐지 ④ 폐지종목 수정주가는 액면변경 이력(KIND/DART) 으로 직접 보정 ⑤ 결과는 parquet/SQLite 캐시, 증분 수집.

## 2. 스크리너·퀀트 저장소 / 백테스트 프레임워크

| 저장소 | ★ | 라이선스 | 요지 | 재사용 가치 |
|---|---|---|---|---|
| younghwan91/quant-airflow https://github.com/younghwan91/quant-airflow | 2 | MIT | 키움 REST+DART+KRX+네이버 → TimescaleDB, **폐지종목 3단계 백필**(KRX 마스터→네이버 일봉→DART 상장주식수), 2016-09 이전 폐지분은 KIND+KRX 수동 1회. 커밋 260, 2026-10 활동 [실측] | 폐지종목 백필 설계도. Airflow/Postgres라 코드 이식보단 **방법론** 참고 |
| younghwan91/krx-quant-core https://github.com/younghwan91/krx-quant-core | 0 | Apache-2.0 | 호가단위·±30% 상하한(비대칭 주의)·시행일별 거래세·체결 시뮬·Deflated Sharpe·purged CV. v0.8, 테스트 950+, py3.11+ [실측] | **호가단위/상하한/세율 모듈**은 작아서 떼어 쓰기 좋음. 키움 의존 부분 제외 |
| yoonbae81/backtest (PyPI backtest) https://github.com/yoonbae81/backtest | 미확인 | 미확인 | 이벤트 기반 엔진, KOSPI·KOSDAQ 심볼 2,820 수집 절차 포함 [2차] | 참고용 |
| Ephimera621/bab-korea-replication | 0 | 미확인 | Frazzini-Pedersen BAB 한국 복제 [실측 topic] | 팩터 연구 템플릿 |
| are012/Finance-Agent | 0 | 미확인 | OHLCV 홀드아웃 분할 연구 프레임 [실측 topic] | 참고 |
| koreainvestment/open-trading-api `backtester/` | (1.7k 전체) | 미표기 | Docker 기반 QuantConnect Lean 백테스터 + strategy_builder(지표 80·프리셋 10) [실측] | 무겁다(Docker·Lean). 일봉 스크리너엔 과함 |
| vectorbt https://github.com/polakowo/vectorbt | 9.5k | Apache-2.0 + Commons Clause | pandas/NumPy 벡터화, 커뮤니티판(PRO 유료) [실측] | 일봉 신호→성과 집계에 적합. DataFrame 직접 입력, KR 어댑터 불필요 |
| bt https://github.com/pmorissette/bt | 3.0k | MIT | 트리 구조 리밸런싱 백테스트, 거래비용 모델 [실측] | 월별 리밸런싱 포트폴리오 검증에 적합 |
| backtrader https://github.com/mementum/backtrader | 23.5k | GPL-3.0 | 이벤트 기반, 2020 이후 개발 정체 [2차] | 안정적이지만 GPL·느림 |
| zipline-reloaded https://github.com/stefan-jansen/zipline-reloaded | 2.0k | Apache-2.0 | py3.11~3.14(차기), 커스텀 bundle 필요 [실측] | KR bundle 공개 저장소 못 찾음 → 직접 ingest 코드 필요. 비추 |
| microsoft/qlib | — | MIT | 지역 CN/US/TW만, KR 미지원. 토스 API→dump_bin 미들웨어 글만 있음 [2차] | 비추(일봉 소형주 스크리너엔 과함) |

- 토픽 페이지 https://github.com/topics/korean-stock-market , https://github.com/topics/korean-stock : KR 전용 저장소 대부분 ★0~5, 2026년 활동. 토스증권 OpenAPI·키움 REST·LS 래퍼가 2026 신규 다수. "KR 팩터 백테스트 + 생존편향 처리" 완성형 저장소는 없음 [실측].

## 3. KIS OpenAPI 자동화

| 저장소 | ★ | 라이선스 | 기능 | 주의 |
|---|---|---|---|---|
| koreainvestment/open-trading-api (공식 샘플) https://github.com/koreainvestment/open-trading-api | 1.7k | 미표기(참고용 면책) | REST+WS 전 카테고리 예제, kis_auth.py(토큰·실전/모의 전환), llms.txt, MCP. py3.11+, uv 권장 [실측] | 토큰 1분 1회 발급, EGW00201=초당 한도 초과, 모의계좌 REST 한도 낮음(최적화 반복은 실전계좌 권장), WS는 HTS ID 필요 [실측] |
| Soju06/python-kis https://github.com/Soju06/python-kis | 288 | MIT | 매수·매도·정정·취소·미체결, 잔고, WS 실시간(재접속 시 구독 복원), 모의투자(virtual), keep_token 캐시, 타입힌트. py3.11 [실측] | PyPI 최근 릴리스 2024-08 [2차]; 이벤트 티켓 GC 시 구독 소실, 멀티스레드 토큰 중복 발급 이력 등 changelog 확인 |
| sharebook-kr/mojito (pip mojito2) https://github.com/sharebook-kr/mojito | 92 | MIT | 현금주문(시장·지정가)·취소, fetch_balance, WS(체결·호가·잔고), 미국주식, 일봉 조회 [실측] | 모의투자 언급 없음, 커밋 92개, 유지보수 상태 미확인 |
| pjueon/pykis https://github.com/pjueon/pykis | 미확인 | Apache-2.0 | 비공식 래퍼, 상한가/하한가 조회 함수 예시, py3.7+ [2차] | README "아직 개발 단계" |
| unohee/kis-agent https://github.com/unohee/kis-agent | 52 | MIT | CLI+Python, **TWAP/VWAP 분할 집행**(지정가·정규장 가드·dry-run), 잔고, 실측 기반 rate limit 18 RPS/900 RPM, 캐시 [실측] | 토큰 처리 방식 미기술. 소규모 프로젝트 |

### KIS 공통 함정 (교차 확인)
- 호출 한도는 APP KEY 단위(프로세스 아님) [2차]. 실전 초당 20건으로 널리 알려짐, 모의투자는 자료마다 1~5건으로 엇갈림 → 상수로 박지 말고 설정값 [2차].
- 토큰 발급 1분 1회 [실측 공식 README] → 파일 캐시 필수(python-kis keep_token, 공식 kis_auth).
- 일자별 시세 1회 100건, 수정주가 플래그 의미 혼동 [2차].

## 4. 리스크·집행 보조 (소형주)
- 분할 집행: kis-agent TWAP/VWAP(위). 소형주는 스케줄 슬라이스보다 **호가 잔량 기반 상한** 필요 — 공개 KR 예제는 없음 [미확인].
- 가격제한폭·호가단위: krx-quant-core(상하한 비대칭 계산, ETF 호가단위, 시행일별 거래세) [실측]. 위키독스 호가단위 표는 구간이 오래됨 [2차] → KRX 현행 기준 재확인.
- 체결 가정: 정리매매·상하한 근접 구간은 종가 체결 가정이 낙관적(AlgoLab) → 백테스트에서 상한가 봉은 매수 불가 처리 권장(추정).
- 포트폴리오 통계: krx-quant-core 의 Deflated Sharpe·purged CV 함수(숫자만 반환, 판정 안 함) [실측].

## 5. 국내 퀀트 커뮤니티 성과 보고
- 퀀터스: 앱스토어 "기관급 전략 설계·검증" 홍보 [실측]. **아웃오브샘플 실전 성과 공개 자료 못 찾음** [미확인]. 요금 미확인.
- 퀀트킹: 연 17.5만원, 2025 백테스트 기능 탑재, 14년치 "10월말 매수·4월말 매도" 식 예시 [2차 영상 요약]. 폐지종목 포함 여부 미확인.
- 젠포트(뉴지스탁, 2016-07 정식 오픈, 팩터 ~120개) [실측 기사]. 2025 실전 괴리 독립 후기 못 찾음; 검색 결과 다수가 홍보성 [실측].
- AlgoLab 블로그 https://algolab.co.kr/blog/survivorship-bias-backtest-delisted-krx-2026 , https://algolab.co.kr/blog/stock-data-python-pykrx-fdr-kis-2026 : 수치·함정 정리가 구체적. 단 상업 블로그(플랫폼 홍보 포함) → 수치는 KRX 원본으로 재검증.
- 결론: 세 상용 도구 모두 "백테스트 ≠ 실전" 검증 자료가 공개 영역에 없음. 성과 주장은 채택 근거로 쓰지 않는다.

## 6. 미확인·사용자 직접 확인 필요
- KRX Open API 비용·호출한도·데이터 시작연도(가입 필요). KRX Data Marketplace 개인 구매 가격.
- FDR KRX-DELISTING 가격이 수정주가인지(액면분할 폐지종목 1~2개로 검증).
- 네이버 폐지종목 일봉 현재 제공 여부(quant-airflow 주장 vs pykrx #89).
- OpenDART 일 한도 공식 수치(FAQ '오픈API 이용한도').
- 퀀터스 요금·데이터 공급사, DataGuide 개인 요금.
