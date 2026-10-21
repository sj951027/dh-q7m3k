# 04. 실행 비용·자동화 제약 (KIS OpenAPI, 한국 중소형주, 다음날 종가 매수 → ~40거래일 보유)

조사일 2026-10-21. 웹 조사만. 표기: [실측 보고됨] = 공식 페이지·논문·보도에 수치가 있음 / [주장] = 블로그·커뮤니티·2차 자료 / [추정] = 본 문서의 계산.
KIS Developers 포털(apiportal)은 FAQ·공지 본문이 비로그인 상태에서 비어 있어 공식 수치 확인 실패 → KIS 항목은 대부분 [주장].

## 1. 거래비용
### 1-1 위탁수수료 (KIS 공식, 기준 2025.10.27) [실측 보고됨]
- 뱅키스(은행/비대면 온라인) 계좌 HTS/MTS: **0.0140527%** · 영업점 계좌 0.147% · 유관기관수수료 KRX **0.0036396%**, NXT 0.0031833% (별도 부과).
  https://securities.koreainvestment.com/main/customer/guide/_static/TF04ae010000.jsp
- API 이용료 없음, 수수료는 HTS와 동일 [주장] https://algolab.co.kr/blog/broker-api-fees-cost-guide-2026
- 타사 이벤트(평생 0.0036396%만 등)는 수시로 바뀜 [주장] https://wikidocs.net/blog/@niceguy/2102/
### 1-2 증권거래세·농특세 (매도 시만) [실측 보고됨: 2025·2026 / 2024는 미확인]
- 2026-01-01 매도분부터: 코스피 거래세 0.05% + 농특세 0.15% = **0.20%**, 코스닥 0.20%(농특세 없음), K-OTC 0.20%. 금투세 폐지로 2023년 수준 환원. 코스피 0%/코스닥 0.15% 인하 계획은 철회.
  https://www.taxtimes.co.kr/news/article.html?no=272624 · https://studygov.kr/blog/0337-2026-stock-transaction-tax/
- 2025년: 코스피 0%+농특세 0.15% = 0.15%, 코스닥 0.15%. (2024년 0.18%는 검색으로 미확인 — [추정] 기억 기반, 백테스트 비용 모델에 넣을 땐 연도별 표 재확인 필요.)
### 1-3 호가가격단위 (2023-01-25 개편, 3시장 통일) [실측 보고됨]
- <2,000원 1원 / 2천~5천 5원 / 5천~2만 10원 / 2만~5만 50원 / 5만~20만 100원 / 20만~50만 500원 / ≥50만 1,000원. 매매수량단위 1주.
  https://www.hanwhawm.com/main/center/info/CS181_3p.cmd · https://news.mtn.co.kr/news-detail/2022110114103274390
- [추정] 최소 1틱 상대폭: 2,000원 주식 0.05%(1원), 5,000원 0.1%(5원), 20,000원 0.25%(50원), 50,000원 0.2%(100원). 저가 소형주는 틱보다 호가 공백이 비용의 본체.
### 1-4 호가스프레드·시장충격 실측 (한국)
- 한국금융학회지(e-kjfs #935), 2019.1~10 일별, 코스피 896·코스닥 1,288종목, 유동성 4분위 [실측 보고됨]:
  코스피 호가스프레드(%) 저유동성 1분위 0.63 / 2분위 0.41 / 3분위 0.30 / 고유동성 4분위 0.19~0.22. 코스닥 1분위 0.55 / 2분위 0.38~0.41 / 3분위 0.30~0.35 / 4분위 0.21~0.26. H-L 스프레드 코스닥 1분위 1.4~1.5%.
  거래대금 코스닥 1분위 일평균 2~9억원, 2분위 9~15억원. https://www.e-kjfs.org/journal/view.php?viewtype=pubreader&number=935
  → [추정] 소형주 반스프레드(즉시 체결 비용) 편도 0.25~0.3%, 왕복 0.5~0.6%; 시가총액 하위·거래대금 10억 미만이면 그 이상.
- 우민철·김지현(2013) 재무관리연구 30(3) '국내 주식시장의 시장충격비용 및 결정요인' — PDF 본문 추출 실패(수치 미확인). 소개문: 강종만(1999) 한국 시장충격비용이 유럽 거래소의 약 2배 [주장]. https://www.smallake.kr/wp-content/uploads/2015/01/30-3-07.pdf
- 시총 중간값 ≈1,100억원(2026-01 보도) — 유니버스 절반이 초소형 [실측 보고됨] https://m.news.nate.com/view/20260123n33091
- 일반 참여율 모델: 충격 ≈ σ_daily × √(주문/ADV) × c(≈1). 예: 변동성 2%·참여율 1% → ~20bp, 0.1% → ~6bp [주장] https://www.tradermath.org/courses/research-validation-and-backtesting/impact-capacity-and-turnover

## 2. 종가 매수를 위협하는 미시구조
- 종가 단일가 15:20~15:30, 접수 호가: 지정가·시장가·스톱지정가(조건부지정가 불가). 가격우선→시간우선, 동일가격 비례배분 없음(블로그) . **랜덤엔드: 15:30부터 30초 이내 임의 종료** → "15:29:59 주문" 전략은 못 쓴다 [실측 보고됨: 삼성증권·다올 안내]
  https://www.samsungpop.com/ux/kor/customer/guide/workproductguide/domesticStockTab2.do · https://www.daolsecurities.com/customer/guide/stockBuy.jsp
- 예상체결가는 추정치 — 마감 직전 대량 주문으로 급변 [주장] https://bullstory.io/blog/동시호가-뜻-시간-총정리-장-시작마감-각각-다르다
- **NXT 종가매매 15:30~16:00(호가접수 15:00~): KRX 당일 종가로 체결** — 종가 확정 후 그 가격에 사는 두 번째 기회. 단, NXT 선정 종목만(소형주 다수 미포함 가능), 증권사별 참여 상이(다올은 메인마켓 미참여) [실측 보고됨] https://www.daolsecurities.com/customer/task/BizNxtInfo.jsp
- VI: 동적 — 코스피200 ±3%(마감 동시호가 ±2%), 코스피 일반·코스닥 ±6%(**15:20~15:30엔 ±4%**); 정적 — 전일종가 ±10%; 발동 시 2분 단일가(+랜덤엔드). 신규상장 첫날·정리매매·단기과열·코스닥 관리종목은 예외 [실측 보고됨] https://kbthink.com/stock/vi.html · https://download.kiwoom.com/kiwoom_easy_help_new/5110.htm
- 가격제한폭 ±30%(코넥스 ±15%). 상한가 종가면 매수 미체결(매도 공급 부족) — 과매도 반등 스크린에서 흔함 [추정].
- 관리종목: 30분 주기 단일가매매(연속매매 아님) [실측 보고됨, 시행연도 미확인] https://www.kcmi.re.kr/kcmifile/webzine_content/weekly_jedo/4092/webzinepdf_4092.PDF · 코스닥 저유동성종목 10분 단일가는 별개 제도(같은 문서). 정리매매는 VI 예외·가격제한폭 없음(일반 지식, 미검증).
- 2026-07-01 상장폐지 요건 강화(시총·동전주·공시위반; 관리종목 지정 후 90거래일 내 45거래일 연속 기준 상회 못 하면 상폐) → 소형주 유니버스에서 상폐·정리매매 노출 증가 [실측 보고됨] https://news.mtn.co.kr/news-detail/2026100219101115998 (2026-10-02 법원이 시총 상폐 규정 무효 가처분 — 유동적)
- 2026-09-14 KRX 시간외단일가 → 접속매매로 변경, 20:00까지 거래 [실측 보고됨, 세부 미확인] https://www.fnnews.com/news/202609120801422727
- **종가에 실제로 다 채워지나?** 소형주 종가 체결 비율을 측정한 공개 자료는 못 찾음. 레버리지 ETF 리밸런싱으로 대형주 마감 동시호가 거래량 +43% 보도(2026-06) — 대형주는 종가 유동성 증가, 소형주는 해당 없음 [실측 보고됨] https://www.fnnews.com/news/202606291837087716
  [추정] 소형주 종가 단일가는 거래대금 2~9억원/일 종목이면 10분간 모이는 물량이 수천만 원 수준. 10~20종목 × 종목당 수백만 원이면 참여율 5~10%를 넘기 쉬움 → 지정가(종가 예상가 +1~2틱)로 미체결 위험 vs 시장가로 가격 밀림 중 택일.

## 3. KIS OpenAPI 실무
- 공식 포털 FAQ/공지는 비로그인 노출 0건 → 아래는 공식 GitHub README + 블로그·커뮤니티.
- 토큰: 유효 1일(응답 `access_token_token_expired` 기준), **발급 1분 1회**(공식 README), 6시간 내 재요청 시 같은 토큰 반환, 발급마다 알림 발송. 웹소켓은 별도 `approval_key`(/oauth2/Approval, 필드명 `secretkey`). [실측 보고됨: README / 나머지 주장]
  https://github.com/koreainvestment/open-trading-api · https://algolab.co.kr/blog/kis-api-access-token-expiry-refresh-2026
- 초당 호출: 실전 20건/초, **모의 2건/초** (EGW00201 '초당 거래건수 초과') [주장; README는 "모의가 더 낮다"만 명시] https://algolab.co.kr/platforms/kis · https://www.inflearn.com/community/questions/1825942
- 웹소켓 등록: 체결(H0STCNT0)+호가(H0STASP0) 합 20건(튜토리얼; 41건 설은 미확인) + 체결통보 1건 [주장] https://wikidocs.net/170517
- 모의 vs 실전: 도메인 openapivts(:29443) vs openapi(:9443), tr_id 접두 V/T(현금매수 VTTC0802U/TTTC0802U), appkey 별도, 캐시 파일 분리 필수. 모의계좌 비활성/만료 사례. 모의 체결 로직·NXT 지원 여부는 공개 문서 미확인 [주장]
  https://algolab.co.kr/blog/kis-api-paper-to-live-switch-2026 · https://www.inflearn.com/community/questions/1771250/모의투자-주문이-불가한-계좌입니다
- 주문 응답: HTTP 200이라도 `rt_cd`≠'0'이면 실패 — "에러 없이 돌아가는데 주문이 안 나감" 사례 [주장] https://algolab.co.kr/blog/chatgpt-algotrading-code-broker-api-gotchas-2026
- 거래소 구분(KRX/NXT/SOR) 파라미터 변경 공지 "[중요] API 변경에 따른 안내 2026.08.27" 제목만 확인, 본문 미확인 → 주문 API 필드 재검토 필요 [실측 보고됨: 제목만]
- 장애: 한투 2026 1Q 전산장애 배상 8.3억원(13사 합계의 60%↑), 2026-01 MTS 접속지연, 2025-10 호가조회 오류, 금감원 과태료 1억 [실측 보고됨, Open API 특정 장애는 미확인] https://www.etoday.co.kr/news/view/2595447 · https://news.tf.co.kr/read/economy/2335460.htm
- 자동매매 약관·허가 문서: 공개 검색으로 못 찾음. README 면책("샘플 코드로 발생한 손해 책임 없음")만 확인.

## 4. 시스템 전략 슬리피지 증거 (한국)
- 젠포트(뉴지스탁) 사용자 1건: 2007~2021 백테스트 +2500% 알고리즘, 실전 첫날 평균 -2%(개별 -6%); 댓글 "14년 슬리피지 34%" [주장, 2021 블라인드] https://www.teamblind.com/kr/post/젠포트-자동매매-어렵네-FiVMaH3j
- 퀀트킹·젠포트의 체계적 실전 vs 백테스트 괴리 통계는 공개 자료 없음(네이버 카페 내부 추정).
- 일반론(블로그): 종가/시가 정확 체결 가정·거래세 누락·룩어헤드·생존편향이 주 원인 [주장] https://algolab.co.kr/blog/backtest-vs-live-trading-gap
- 유동성 필터 경험칙: 주문 ≤ ADV의 1%(보수)~5%(일반)~10%(장기 트렌드) [주장] https://elitetrader.com/et/threads/how-much-size-is-too-much.206531/ · https://www.thechartist.com.au/?p=5995
  [추정] 종가 단일가에만 집중 매수하면 "하루 거래대금"이 아니라 "종가 단일가 거래대금"(통상 일중의 5~15%, 미측정)이 분모 → 종목당 금액 ≤ 20일 ADV의 0.5~1%가 안전선.

## 5. 세금 한 줄
- 소액주주 장내 매매차익 비과세, 매도 시 거래세만. 대주주(2026 양도분): 종목당 시총 **50억원** 이상 또는 지분 코스피 1%/코스닥 2%/코넥스 4%, 전년말 기준 판정; 10억 하향설은 자료 엇갈림 [실측 보고됨(50억)/엇갈림] https://glasswallet.com/calculate/stock-capital-gains/major-shareholder · https://www.heumtax.com/contents/posts/major-shareholder-stock-transfer-tax

## 6. 왕복 비용 합계 [추정]
| 구분 | 수수료 왕복 | 유관기관 왕복 | 거래세(매도) | 반스프레드 왕복 | 충격(참여율 1~5%) | 합계 |
|---|---|---|---|---|---|---|
| (a) 코스피 대·중형(유동성 상위 2분위) | 0.028% | 0.007% | 0.20% | 0.2~0.4% | 0.05~0.15% | **0.5~0.8%** |
| (b) 코스닥 소형·저회전(하위 1~2분위, ADV<15억) | 0.028% | 0.007% | 0.20% | 0.5~0.7% | 0.3~1.0%+ | **1.0~1.9%**, 미체결·상한가 미매수 별도 |
- 40거래일 보유 기준 연 ~6회전 → (a) 3~5%/년, (b) 6~11%/년 비용. 백테스트 알파가 이보다 작으면 실전 0.
