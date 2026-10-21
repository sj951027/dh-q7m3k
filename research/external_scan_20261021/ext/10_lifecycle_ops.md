# 10. 수명주기·운영 — 소규모 체계적 주식 전략을 혼자 수년간 안전히 돌리기 (웹 조사, 2026-10-21)

표기: **[실측 보고됨]** = 논문·공식 자료·집계 수치 / **[주장]** = 실무자 의견·블로그 규칙 / **[미확인]** = 검색으로 못 찾음.
출처 품질: 학술 논문·규제 문서 > 벤더·블로그(AlgoLab 등 개인 퀀트 블로그는 참고용).

## (1) 알파 소멸(alpha decay)
- McLean–Pontiff(JF 2016, 97개 예측변수): 표본 밖(out-of-sample) 수익 **−26%**, 발표 후 **−58%** → 차액 32%p 를 "발표 정보 거래" 효과로 해석. [실측 보고됨] https://www.gwern.net/doc/economics/2016-mclean.pdf
- Jacobs–Müller(2020, 39개국 138~241개 이상현상): 발표 후 유의한 감소는 **미국만**. 한국 포함 여부는 요약에서 미확인. [실측 보고됨] https://quantpedia.com/equity-anomalies-persist-in-international-markets/
- Chen–Lopez-Lira–Zimmermann: 이론 유무와 무관하게 발표 후 예측력 **약 50% 소멸**. [실측 보고됨] https://arxiv.org/pdf/2212.10317
- Linnainmaa–Roberts(RFS 2017): 발견 표본 밖에서 Sharpe/IR **60~77% 감소**(회계 기반 이상현상). [실측 보고됨] https://finance.wharton.upenn.edu/~mrrobert/resources/Publications/anomaliesRFS2017.pdf
- Falck–Rej–Thesmar(CFM): 발표 연도만으로 Sharpe 감소 분산의 30% 설명. [실측 보고됨] https://arxiv.org/pdf/2105.01380
- 한국 시장 발표-후 소멸을 직접 검증한 논문: **[미확인]**. 국내 모멘텀은 미·유럽보다 약함(Sonu–Choi 2011; Kang 등 2024는 개별종목 모멘텀 반전) [실측 보고됨] https://academicnewsletter.sufe.edu.cn/info/355719
- 시사점(추정): 백테스트 수익의 **절반**을 기본 할인으로 두고, 소멸은 "발표/확산" 사건 뒤 수년 단위 → 재검증 주기는 분기~반기, 단 판정은 거래일 수(≥40~60 거래일 OOS) 기준으로.

## (2) 워크포워드·사전등록·과적합 통제
- 다중검정 문턱: Harvey–Liu–Zhu(2016) 새 팩터 **t > 3.0**(FDR 1%면 3.39, 5%면 2.81). [실측 보고됨] https://www.nber.org/papers/w20592 · 반론 https://arxiv.org/pdf/2206.15365
- Harvey–Liu "Backtesting"(JPM 2015): 업계 관행 "Sharpe 50% 삭감"은 어림법일 뿐 — 다중검정 삭감은 비선형(높은 SR는 조금, 경계 SR는 크게 깎임). [실측 보고됨] https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF
- 최소 백테스트 길이(MinBTL, Bailey–Borwein–López de Prado–Zhu 2014): **5년 일별 자료면 45개 이상 변형을 시험하면** 우연히 IS Sharpe≥1(OOS 0) 전략이 거의 확실히 나옴. 기대 최대 Sharpe ≈ σ·[(1−γ)Φ⁻¹(1−1/N)+γΦ⁻¹(1−1/(Ne))]; N=1000 시 약 3.3. [실측 보고됨] https://www.davidhbailey.com/dhbpapers/overfit-tools-at.pdf · https://www.cxoadvisory.com/big-ideas/insidiousness-of-overfitting-investment-strategies-via-iterative-backtests · https://cxoadvisory.com/?p=25715
- DSR/PBO: Deflated Sharpe = 시도 횟수 N 의 기대최대 SR을 문턱으로 한 확률적 SR; PBO = CSCV 분할에서 IS 최우수가 OOS 하위 50%에 드는 비율. 정직한 N 집계가 전제(상관된 시도는 유효 N 축소). [실측 보고됨] https://papers.ssrn.com/abstract=2460551 · https://en.wikipedia.org/wiki/Deflated_Sharpe_ratio
- 워크포워드 관행: IS 2~5년 / OOS 3~12개월, 워크포워드 효율(WFE=OOS/IS 성과) **>0.5 양호, <0.3 경고**(Pardo 귀속). [주장] https://www.luxalgo.com/library/concept/walk-forward-analysis/ · https://tradingstrategy.ai/glossary/walk-forward-analysis
- 모의(paper) 운용 최소치: 종결 거래 **30~100건** + 변동성 큰 장세 수 회 포함, 달력으로 **1~3개월**이 하한(일봉 전략은 50건 모으는 데 2~3개월). 체결 가정이 낙관적이므로 최소 수량 실거래로 이행. [주장] https://www.luxalgo.com/library/concept/forward-paper-trading-confirmation.md · https://alpaca.markets/learn/paper-trading-vs-live-trading-a-data-backed-guide-on-when-to-start-trading-real-money
- 은퇴 기준(실무): OOS 기대값(비용 후) 음전환, 워크포워드 연속 실패, 비용이 엣지 상회, 원래 전제 소멸 → 은퇴; 애매하면 규모 축소. 작은 손실 뒤 재최적화 금지(최적화기에 잡음 맞출 기회 제공), 홀드아웃 본 뒤 재조정 금지. [주장] https://www.luxalgo.com/blog/edge-decay-reoptimize-or-throw-out-strategy/

## (3) 감시 — 국면 변화·모델 붕괴 조기 탐지
- CUSUM(Page 1954): 문턱 h 가 거짓경보/탐지지연 트레이드오프의 단일 손잡이. 평균런길이(ARL)로 설계; 문턱이 시간에 따라 변할 수 있고 σ 추정에 민감. 단독 매매신호가 아닌 "재검토 알람"으로 쓰는 게 정석. [주장+학술] https://www.luxalgo.com/library/concept/change-point-detection.md · https://publikationen.bibliothek.kit.edu/1000055429/3854114
- 실시간 감시용 검정: Chu–Stinchcombe–White(1996) — 새 자료마다 일회성 검정을 반복하면 거짓 단절을 확률 1로 신고하므로 감시 전용 경계(√(b_α+ln(t−n)), b_α=4.6≈5%) 사용. López de Prado AFML 17장이 이를 채택. 동분산 가정은 금융 시계열에서 약점. [실측 보고됨] https://econometricsociety.org/publications/econometrica/1996/09/01/monitoring-structural-change · https://nottingham-repository.worktribe.com/OutputFile/5396073
- 롤링 IC: Spearman 롤링 IC + 지수감쇠 반감기 + 블록 부트스트랩 CI + sup-Wald 단절검정(alphafade 패키지 구성). 고정 IC 문턱의 권위 있는 수치 **[미확인]**. [주장] https://pypi.org/project/alphafade/
- 드로다운 vs 기대: 사전에 백테스트 거래열을 몬테카를로/부트스트랩해 밴드 고정 → 실시간 DD 가 **과거 최대 DD 의 1.5~2배** 또는 고분위 밴드 초과 시 검토. 승률 10~15%p 하락이 연속 2개 창, PF 1.5~2.0→1.0 접근도 트리거. 거래 수 적을 땐 소멸과 불운이 오래 구분 불가 → 문턱은 **반드시 사전 고정**. [주장] https://www.luxalgo.com/blog/edge-decay-reoptimize-or-throw-out-strategy/ · https://strategyquant.com/forum/topic/5062-assessing-if-a-live-ea-needs-to-be-shutdown/
- 검토 주기(실무): 스윙·포지션 전략 = 월간 점검 + 분기 심층(또는 신규 30~50건마다). 한 달 부진만으로 사망 선고 금지. [주장] 같은 출처.

## (4) 한국 자료 함정
- 시점 정합(PIT): 기간말이 아니라 **접수일(rcept_dt) 다음 거래일**부터 사용. 분·반기 45일(연결 최초 2개 연도 60일), 사업보고서 90일 이내 제출(자본시장법 §159·§160). 12월 결산 3분기(9/30)는 11월 중순, 연간은 3월 말 공시가 전형. [실측 보고됨: 법령] https://korea.legal/wiki/자본시장과-금융투자업에-관한-법률-제160조/ · [주장] https://algolab.co.kr/blog/dart-opendart-financial-statement-api-lag-2026
- 정정공시: OpenDART `last_reprt_at=Y` 는 최종 정정본 → 백테스트는 **원공시 값·원접수일**을 보존하고 정정본은 정정 접수일부터 적용해야 함(블로그는 이 처리 미설명). 규모 참고: 2023년 상장사 95곳이 감사보고서 242회 정정(상장사 3.6%). [실측 보고됨: 금감원 보도] https://www.ajunews.com/view/20241226112640707
- 연결/별도: `fs_div=CFS` 가 status 013(연결 없음)이면 OFS 로 대체하고 `fs_div_used` 열 기록; 섞으면 같은 회사 비율이 크게 달라짐. 당기(thstrm_amount) vs 누적(thstrm_add_amount) 혼동 시 ROA 가 4배 점프. 비12월 결산 처리 자료 **[미확인]** — 결산월별 reprt_code/기간 매핑 직접 검증 필요. [주장] 같은 AlgoLab 글
- 생존편향: 2015-09-03 상장 주권 약 1,842 중 **266(14.4%)** 이 이후 폐지; 그중 정리매매 거친 건 약 61%, 합병·완전자회사화 약 20%(전액 손실 아님). 10년간 주권 폐지 575건(피흡수합병 61, 스팩소멸 53, 상폐기준 52, 관리종목 후 미제출 51, 감사의견거절 17 …). 6자리 코드는 시간상 비고유 → ISIN 병행. FDR `KRX-DELISTING` 실패 시 빈 DF 반환(assert 필요). [실측 보고됨: 저자 집계, 독립 검증 없음] https://algolab.co.kr/blog/survivorship-bias-backtest-delisted-krx-2026
- 상폐 수익률 처리: 일괄 −100% 금지. 정리매매(통상 7거래일, 가격제한폭 없음)는 마지막 거래일 종가+보수적 슬리피지, 합병은 공시 대가. 2017~18년 상폐 종목 정리매매 평균 등락률 **약 −94%**(성지건설 −92%). [실측 보고됨: 보도] https://www.newsis.com/view/NISX20210812_0001546652 · https://www.frism.io/dan-7il-gagyeog-jehan-eobsneun-dobagpan-sangjangpyeji-jeongrimaemae-dodaece-nuga-saneun-geolgga/
- 관리종목·거래정지: 관리종목 지정 시 1일 매매정지(14:30 이후 공시면 익일 9시까지)·신용거래 금지; 2026 개정으로 주가 1,000원 미만 30거래일 연속 → 관리종목. 유통주식 10만주 미만/비율 2%(코스피 1%) 미만 매매정지. 백테스트는 KIND 공시 기준 지정·정지·재개일로 "매매 불가 기간" 반영. [실측 보고됨: KRX 공시·보도] https://kind.krx.co.kr/external/2026/07/15/000716/20260715001881/68818.htm · https://www.etoday.co.kr/news/view/1306273 · https://wikidocs.net/blog/@goodhosup/28344/
- 수정주가: pykrx 수정주가는 1990년부터 제공되나 1990년 3월 삼성전자 −99% 같은 이상치 존재 → 검증 못 하면 1995년 이후 사용 권고; pykrx·FDR(NAVER) 모두 네이버 기반이나 제공 기간 상이, 액면분할 이후 그래프에 소스 간 차이. 무상증자 권리락일 시초가 인위 조정(착시) → 비수정 종가와 수정주가를 병행 보유하고 권리락·배당락일을 DART 와 대조. 라이브러리 간 조정식 차이의 공식 문서 **[미확인]**. [주장] https://wikidocs.net/228554 · https://wikidocs.net/376431

## (5) 자동매매 운영 안전장치
- 규제 기준선(SEC 15c3-5, 사전 통제): 신용·자본 한도 초과 주문 차단, **오류 주문 거부(가격·수량 한도, 단시간 연속 주문, 중복 주문)**, 체결 즉시 사후보고, 연 1회 통제 검토·문서화. [실측 보고됨: 규정] https://www.sec.gov/rules/final/2010/34-63241-secg.htm
- Knight Capital(2012-08-01, 45분에 400만 주문·4.6억$ 손실): SEC 지적 — 라우터 **출력 주문 vs 입력 주문 대조 통제 부재**, 총자본 한도 통제 미연결, 코드 배포·테스트 절차 부재, 사고 대응 절차 부재, **개장 전 자동 경고 메일 97통 미열람**(경고가 '알람'으로 설계되지 않음), 사후 근본원인 분석 부재. [실측 보고됨] https://www.sec.gov/news/press-release/2013-222
- FINRA 15-09(2015): 5영역(위험평가·코드개발·테스트/검증·거래시스템·컴플라이언스). 전문 목록은 PDF 미파싱 **[미확인 세부]**. https://www.finra.org/rules-guidance/notices/15-09
- 킬 스위치: 회사 수준+알고리즘 수준 2단, 정기 시험; 취소 트래픽을 신규 주문과 분리 우선; 킬 루틴이 "청산 주문 성공"을 가정하면 안 됨(거래소 거절 사례 — 독립 확인 필수). [주장] https://gravitee.io/corpus/gen-1134/electronic-trading/pre-trade-risk-controls-and-kill-switches-for-electronic-trading-apis.html · https://nexusfi.com/a/automation/automated-risk-controls
- 중복 주문 방지: 클라이언트 주문ID/멱등키/시퀀스 번호를 **전송 전 영구 저장**, 타임아웃 재시도 전 미체결 조회. 재시작·재접속 뒤 "포지션·미체결·체결 대조 완료" 신호 전까지 신규 주문 금지(브로커 API가 이 신호를 명시 제공하지 않는 경우 흔함). [주장] https://www.quantconnect.com/forum/discussion/21474/ibkr-on-qc-cloud-supported-reconciliation-barrier-after-reconnect-or-restart/
- 대조(reconciliation): 일일 ① 모든 거래 계상 ② 오류 식별·처리 ③ 잔고 일치, 다음 거래일 전 완료. [주장: 업계 관행 문서] https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7809632
- KIS 특이사항: 모의 `openapivts…:29443`/실전 `openapi…:9443`, tr_id 접두 V/T, 키·토큰·계좌 환경별 분리(같은 프로세스에서 토글 금지), 모의 미지원 TR(40580000)은 실전에서 처음 노출, 호출한도 EGW00201(블로그 기준 국내 실전 20/초·모의 2/초 — 공식 미확인), 토큰 24h·발급 호출도 별도 한도. 이행 순서: **1주 매수·매도 왕복 → 소액 며칠 → 정상 수량**. [주장] https://algolab.co.kr/blog/kis-api-paper-to-live-switch-2026 · https://algolab.co.kr/blog/kis-egw00201-rate-limit-fix-2026
- 혼자 운영자용 최소 체크리스트(종합·추정): 일일 주문 건수·금액 예산, 종목당 수량·가격 괄호(collar), 일일 손실 한도→자동 중단, 주문ID 멱등성+재시도 전 미체결 조회, 시작 시·장 마감 후 잔고 대조 실패 시 신규 주문 봉인, 모든 msg_cd/msg1 로그 보존, 경고는 "읽히는 채널"(텔레그램 등)로만, 킬 스위치 월 1회 모의 발동 시험, 배포 전 체크섬·롤백 경로.
