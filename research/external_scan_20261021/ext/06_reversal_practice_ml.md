# 06 — 단기 반전 실무 구현 · ML 종목선택 냉정 평가 · 신호 결합 (웹 조사, 2026-10-21)

범례: **[실측 보고됨]** = 논문/보고서가 표·수치로 보고한 것(본문 미열람 시 '초록·2차 요약 기준' 병기). **[주장]** = 저자·블로그의 해석/권고. 로컬 저장소·DB는 건드리지 않았음.
접근 제한: SSRN·Alpha Architect·Wiley 는 403 → 초록·2차 요약(CXO, Quantpedia, Robeco 인사이트, 서브스택)으로 대체. "short-term reversal strategies made cheap"이라는 제목은 못 찾음 — 해당 내용은 de Groot–Huij–Zhou(2012)로 판단(추정). AQR 명의의 단기신호 논문도 못 찾음 — 단기신호 논문은 Robeco(Blitz 외) 것.

## A. 프로 퀀트의 단기 반전 구현 (논문 1건 = 1묶음)

### A1. 잔차 반전 — Blitz·Huij·Lansdorp·Verbeek (2013, JFM) "Short-Term Residual Reversal"
- 규칙(쉬운 말): 각 종목 월수익률을 36개월 롤링으로 시장·크기·가치 3팩터에 회귀 → 지난달 **잔차**(팩터로 설명 안 되는 부분)를 잔차 변동성으로 나눠 표준화 → 하위 10% 매수·상위 10% 매도, 월 리밸런스. 유니버스 = 미국, 주가 $1 초과·시총 NYSE 중위 이상.
- **[실측 보고됨, 2차 요약(CXO)]** 1926~2008 월평균 잔차 1.34% vs 일반 반전 0.97%, 연 샤프 1.28 vs 0.62. 기관 수준 비용 차감 후 연 8%+, 손익분기 왕복비용 ≈0.56%. 대형 500종목 한정 월 0.67%, 100종목 0.81%(순). 일반 월간 반전은 비용 후 수익 없음.
- **[주장]** 잔차화가 소형주 편중·팩터 노출 변동을 줄여 비용도 낮춤.
- URL: https://www.ssrn.com/abstract=1911449 · https://www.cxoadvisory.com/technical-trading/purified-short-term-stock-reversal/ · https://www.robeco.com/en/insights/2011/short-term-residual-reversal.html
- 스크리너 복사 1변수: 20일 수익률 대신 **'20일 수익률 − 동기간 시장(코스피/코스닥)·업종 수익률'**(sector_cache 활용) 또는 60일 롤링 베타로 뺀 잔차. 과매도 후보의 순위 변수 1개 교체.

### A2. 비용 통제 — de Groot·Huij·Zhou (2012, JBF) "Another Look at Trading Costs and Short-Term Reversal Profits"
- 규칙: 주간 반전을 **대형주로 한정** + '순위가 일정 구간을 벗어날 때만 교체'(buy/hold 밴드)로 회전율 억제.
- **[실측 보고됨, 초록·2차]** 비용 차감 후 주 30~50bp. 비용 잠식의 주범은 소형주 과잉 거래. 대형주 한정 + 밴드 구성으로 비용 더 감소.
- URL: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1605049 · https://repub.eur.nl/pub/25718
- 복사 1변수: 유동성 필터(20일 평균 거래대금 하위 X% 제외) 또는 **밴드 매도 규칙**(상위 10%로 진입, 상위 50% 밖으로 떨어질 때만 교체). 40일 보유는 이미 저회전이므로 유동성 필터가 더 직접적.

### A3. 단기신호 묶음 — Blitz·Hanauer·Honarvar·Huisman·van Vliet (2023, FAJ) "Beyond Fama-French Factors: Alpha from Short-Term Signals"
- 규칙: 5개 1개월 신호(반전·1개월 모멘텀(=업종 상대 반전 포함)·애널리스트 수정·단기 리스크·월 계절성)를 **합성 점수**로, MSCI World 대형·유동주, 밴드 매매(상위 10% 진입, 상위 50% 이탈 시 매도).
- **[실측 보고됨, 2차(서브스택·CFA 초록)]** 개별 신호 총알파 연 5~8%, **비용(0.25%) 후 ≈ −2%**. 합성 총알파 12%+, 단순 월 리밸런스면 2/3 이상 비용에 잠식, 밴드 규칙 적용 시 순알파 6%+. 1985~2021, 표본 외·발표 후·지역 간 유지, 롱온리·며칠 지연 집행에도 유지(초록 주장).
- URL: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4115411 · https://rpc.cfainstitute.org/research/financial-analysts-journal/2023/beyond-fama-french-factors-alpha-from-short-term-signals · https://tommijohnsen.substack.com/p/using-short-term-signals-to-generate
- 복사 1변수: **업종 상대 1개월 수익률**(종목 20일 − 업종 20일) 1개를 과매도 점수에 추가 관측(가중 0 → 검증).

### A4. 업종·팩터 모멘텀과의 충돌 제거 — Blitz·van der Grient·Honarvar (2023) "Reversing the Trend of Short-Term Reversal"
- **[주장, 초록]** 고전 반전은 대부분 지역에서 약화·소멸. 반전이 '업종·팩터의 단기 모멘텀'을 거슬러 사는 경향을 상쇄하면 위험조정 성과 2배 이상. 구체 수식·비용 수치는 초록에 없음(본문 미열람). 3rd-party 백테스트(paperswithbacktest, 1990~2026, 15L/15S)는 연 0.75%·샤프 0.16 — 논문 주장과 거리 큼(구현 차이 가능, 비용 미명시).
- URL: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4575689 · https://www.robeco.com/en-us/insights/2023/10/reversing-the-trend-of-short-term-reversal · https://paperswithbacktest.com/strategies/reversing-the-trend-of-short-term-reversal
- 복사 1변수: 종목 낙폭 중 **업종 전체 낙폭 비중**을 빼기(=A1·A3와 같은 변수). 업종이 통째로 빠진 종목은 반전 후보에서 감점.

### A5. 업종 내 반전 — Hameed·Mian (2015, JFQA) "Industries and Stock Return Reversals"
- **[실측 보고됨, 초록·WP 요약]** 24개 업종 내 전월 패자−승자(5분위, 동일가중) 월 1.46% vs 전체 표본 1.05%. 대형·유동주에도 존재, 시장 하락·변동성 큰 뒤 더 강함(유동성 공급 보상 해석 = 주장).
- URL: https://ideas.repec.org/a/cup/jfinqa/v50y2015i1-2p89-117_00.html · https://web2-bschool.nus.edu.sg/wp-content/uploads/media_rp/publications/BwXb81392625636.pdf
- 복사: A1~A4와 동일 변수. 한국 sector_cache 가 있으니 가장 싸게 시험 가능.

### A6. 뉴스 vs 비뉴스 분해 — Da·Liu·Schaumburg (2014, Mgmt Sci / NY Fed SR513)
- **[실측 보고됨, 초록]** 표준 반전을 '업종 간 모멘텀·업종 내 기대수익 차·현금흐름 뉴스 과소반응·잔차'로 분해 → **비뉴스(잔차) 성분만 유의**. 애널리스트 수정으로 뉴스를 걷어낸 강화 반전은 위험조정 수익 표준의 4배(초록 수치). 롱 쪽 수익 = 유동성 충격(강제 매도), 숏 쪽 = 심리.
- URL: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr513.pdf · https://ideas.repec.org/a/inm/ormnsc/v60y2014i3p658-674.html
- 복사 1변수(애널리스트 자료 없음 → 대리): **실적 공시(DART)·거래량 급증 동반 하락은 '뉴스 하락'으로 제외/감점**. 간단 대리 = 낙폭 중 거래량 z-score 상위 날의 기여 비중.

### A7. 실적 발표 주변 반전 — So·Wang (2014, JFE) "News-driven return reversals"
- **[실측 보고됨, 초록·Quantpedia]** 발표일 전후 3일 반전이 비발표 기간의 ≈6배(1.45% vs 0.22%, 1996~2011, 대형주 5분위 158bp/3일, 비용 미차감). Quantpedia 표본 외 추적은 소폭 음(−).
- URL: https://ideas.repec.org/a/eee/jfinec/v114y2014i1p20-35.html · https://quantpedia.com/strategies/reversal-during-earnings-announcements
- 복사: 40일 보유 체계와 안 맞음(3일 전략). 다만 "발표 직전 급락은 반전 후보에서 제외"라는 A6 대리 규칙의 근거로만 사용.

### A8. 회전율로 반전/모멘텀 갈림 — Medhat·Schmeling (2022, RFS) "Short-term Momentum"
- **[실측 보고됨, 초록·2차]** 전월 수익률×회전율 이중정렬: 회전율 하위 7분위에서 1개월 반전 유의, 최상위 분위는 **단기 모멘텀**(12개월 지속, 대형·유동주에서 가장 강함). 반전은 형성 후 3개월이면 0. 미국 1963~2018.
- **한국 재현 — 엄철준·박종원 (2023, 재무관리연구 40(4))**: **[실측 보고됨, 초록]** 한국은 전월 반전 유의, 단기 모멘텀은 고회전 그룹에서도 **없음**. 반전은 소형·저유동에서 더 강함, 외국인·기관이 승자 매수·패자 매도. 단, 반전 프리미엄 크기·유의성은 다른 팩터 대비 **매우 작음**. 중국 재현(Yue 외 2023)도 모멘텀 없음·반전만.
- URL: https://openaccess.city.ac.uk/id/eprint/31278/ · https://alphaarchitect.com/short-term-momentum/ · https://www.kci.go.kr/kciportal/landing/article.kci?arti_id=ART002987582 · https://ideas.repec.org/a/eee/pacfin/v77y2023ics0927538x22002153.html
- 복사 1변수: **20일 평균 회전율(거래량/유통주식 또는 거래대금/시총)** 을 관측 변수로 — 미국식 '고회전 = 모멘텀 → 반전 후보 제외'는 한국 논문이 부정하므로 가중 0 관측부터.

### A9. 한국 횡단면 증거(KRX 전종목)
- **[실측 보고됨, 본문 열람]** JDQS 29(3) 2021(모멘텀 논문, 1999.1~2021.2, 월평균 658종목, 500원 미만 제외): 전월 수익률 계수 −2.95%(t=−3.77); Nagel식 반전 포트 월 1.293%(t=3.32), 5팩터 알파 1.275%(t=3.22). Amihud 비유동성 계수는 **무의미**(미국과 다름). 소형·유동성 하위집단 분석 없음. 비용 미반영.
- **[실측 보고됨, 본문 열람]** 정우성·강민 (JDQS 29(3) 2021): KOSPI·KOSDAQ 개별주 일별, 2000년 이후에만 평균회귀; 회전율 변화를 걷어내면 평균회귀가 유의하게 줄어듦(VR 격차 10일 0.0017→100일 0.0100). 즉 한국 단기 반전의 상당 부분은 **거래량 변화에 딸려 있음**.
- URL: https://www.emerald.com/jdqs/article/29/3/174/206550/The-effect-of-short-term-return-reversals-on · https://www.emerald.com/insight/content/doi/10.1108/jdqs-01-2021-0003/full/html
- 한국 퀀트 블로그: 1개월 반전 KR 백테스트 수치가 있는 글은 못 찾음. TT Lab(2026-03)은 "한국 단기(1~3개월) 팩터 약함"이라고만 서술 **[주장]**. https://ttlab.hopto.org/blog/finance/2026-03-05-finance-quant-factor-investing-backtest-python

### A 요약 — 실무 공통 규칙
1) 대형·유동주로 한정(비용의 주범 = 소형주 회전) 2) 시장·업종·팩터 성분을 뺀 **잔차/업종 상대 반전** 3) 뉴스(실적·공시) 동반 하락 제외 4) 밴드 매매로 회전 억제 5) 단독 신호는 비용 후 음(−), **여러 1개월 신호 합성**에서만 순알파. 반전 단독 효과는 미국도 약화, 한국은 유의하나 '작다'.

## B. ML 횡단면 종목선택 — 냉정한 시각
- Gu·Kelly·Xiu (2020, RFS): **[실측]** NN 월 OOS R² 수준 미미(~0.4%), 동일가중 10분위 L/S에서 큼. 재현(Tidy Finance·GitHub)은 "동일가중이 훨씬 좋음 = 소형·고변동주에 신호 집중" 지적 **[실측 보고됨]**. https://www.nber.org/papers/w25398 · https://www.tidy-finance.org/blog/gu-kelly-xiu-replication/
- Avramov·Cheng·Metzker (2023, Mgmt Sci): **[실측 보고됨, 초록]** 마이크로캡·부실주·고변동 국면 제외하면 ML 수익 크게 감소, 고회전으로 비용 후 더 악화. 반론 Azevedo·Hoegner·Velikov(2023): 320 이상현상·9모델, 비용(실효 스프레드) 차감 시 수익 13~40% 감소하나 LSTM 순알파 월 1.20%(t 3.46) 유지, 편측 회전 60~70%; **비용 완화 기법은 2개월 보유 외 모두 순수익을 낮춤**. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3450322 · https://quantpedia.com/the-expected-returns-of-machine-learning-strategies/
- Chen·Hanauer·Kalsbach (2025/26) "Design choices": **[실측 보고됨]** 1,000개+ 모델에서 설계 선택만으로 월 L/S 0.13%~1.98%, 샤프 0.08~1.82. 설계 분산이 표준오차보다 59% 큼 → **연구자 자유도가 성과를 만든다**. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5031755
- Nagel (2025, NBER 34104) "Seemingly Virtuous Complexity": **[주장+시뮬]** 복잡 모델(ridgeless)은 사실상 변동성 타이밍된 모멘텀을 재현, 반전 데이터에선 실패. Buncic: 랜덤 가중 평균하면 복잡성 우위 사라짐. https://www.nber.org/system/files/working_papers/w34104/w34104.pdf
- 신흥국 — Hanauer·Kalsbach (2023, EMR): **[실측 보고됨, 2차]** 32개국 15,000종목, OOS 2002~2021, L/S 월 선형 0.8% / 트리 1.0% / NN·앙상블 1.2%(시총가중, 총수익). 상위 특징 = 52주고가 대비 가격·고유변동성·회전율; 단기 반전은 상위 15 안. 비용 후 수치는 정성적으로만("유의한 순초과"). 한국 단독 결과 없음. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4287550 · https://www.robeco.com/en-int/insights/2023/10/using-machine-learning-for-emerging-market-equity-returns
- 한국 — Noh·Jang·Yang (2023, APJFS 52:193-241): GBM이 선형보다 예측·포트 성과 우수(초록) **[실측 보고됨, 초록]**, 비용·OOS R² 수치 미확인. Choi 외 (2024, JKSS 53:248-280): LightGBM·GBRT 최선, **매년 최적 모델로 갈아타기는 단일 모델을 못 이김**, 검증지표를 OOS R²가 아닌 '상위10% 누적수익(CRP10)'으로 바꾸면 결과가 달라짐 **[실측 보고됨, 초록]** → 지표 선택이 결론을 바꾸는 전형. 비용 언급 없음. https://onlinelibrary.wiley.com/doi/10.1111/ajfs.12419 · https://link.springer.com/article/10.1007/s42952-023-00245-0
- Leung·Lohre 외 (2021, JFDS): **[실측 보고됨, 초록]** ML이 선형을 이기지만 "경제적 이득은 제한적이며 위험 감수·효율적 집행 능력에 결정적으로 의존". https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3546725
- Cakici 외 (2023, JEDC): 46개국, ML 예측력의 원천 = 모멘텀·반전·가치·크기 등 **이미 알려진 팩터**; 모델 결합이 특히 효과 **[초록]**. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4141663

## C. 순위 평균(소수 단순 신호 결합) vs 튜닝된 단일 신호
- DeMiguel·Garlappi·Uppal (2009, RFS): **[실측 보고됨]** 14개 최적화 모델 중 1/N 을 샤프·CEQ·회전율에서 일관되게 이기는 모델 없음; 25자산 기준 1/N을 이기려면 추정창 ≈3,000개월 필요. https://ideas.repec.org/a/oup/rfinst/v22y2009i5p1915-1953.html
- GSAM (2018) "How to Combine Investment Signals": **[실측 보고됨(시뮬)]** '점수 평균→순위'(Integrated) vs '순위→평균'(Mixed) 위험조정 성과 차이 경제적으로 미미, Mixed 의 전달계수 약간 높음. https://www.gsam.com/content/dam/gsam/pdfs/institutions/en/articles/2018/Combining_Investment_Signals_in_LongShort_Strategies.pdf
- A3(Robeco 단기신호): 개별 신호 비용 후 음(−) → 합성에서만 순알파(상관 낮거나 음). Alpha Architect 다팩터 요약 **[주장+2차]**: "특성별 동일가중은 표본 외에서 이기기 매우 어렵다". https://alphaarchitect.com/combining-factors-in-multifactor-portfolios/
- 결론: 3~5개 저상관 단순 신호의 **동일가중 순위 평균**이 튜닝 단일 신호보다 OOS 에서 안전하다는 쪽이 증거 우세(실측 2건 + 실무 2건). 다만 신호 수가 늘면 각 신호의 사전등록·분모 증가 문제는 그대로.

## D. 이 스크리너에 대한 함의 (실측/추정 구분)
- 자료 크기(추정): 2023-06~ ≈ 820거래일 × ~2,500종목, 월간 단위면 ≈ 40개월 — GKX류 ML은 월 30년×수천 종목에서도 OOS R² <1%였다. 40개월 횡단면으로 트리/NN을 "학습→OOS 40일 판정"하면 Chen 외가 보인 설계 분산(샤프 0.08~1.82)이 결과를 지배할 것(추정, 근거 = B의 실측).
- 즉시 시험 가치가 높은 1변수(관측 가중 0 → §11 판정): ① 업종 상대 20일 수익률(A1/A3/A5, sector_cache) ② 거래량 급증 동반 낙폭 비중 = 뉴스 하락 대리(A6/A7) ③ 20일 회전율(A8, 한국 방향성 미정) ④ 유동성 하한 필터(A2).
- 결합은 v30 점수식 교체가 아니라 **새 model_id**로 2~3개 순위 평균(C). "채택 안 함"이 기본값.
