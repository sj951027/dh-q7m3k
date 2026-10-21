# 03 시장 타이밍·국면 오버레이 — 외부 근거 정리 (2026-10-21, 웹 조사만)

표기: **[실측 보고됨]** = 출처가 표본·수치를 제시 / **[주장]** = 수치 없는 의견·실무 통념 / **[비동료심사]** = 개인 블로그·깃허브·증권사 코멘트(원자료 미확인).
우리 자체 결과(코스피 20일 ≤−5% 다음날 매수 +6.8%·9/9, 코스닥 단독 급락 반등 없음, 확인 대기·분할 비용 0.7~2.5%p, 손절 역효과, MA 필터 < 낙폭 깊이)는 각 절 끝 "대조"에서만 비교.

## 1. 추세추종 / 이동평균 타이밍 (Faber 10개월 SMA 등)

- Faber(2007/2013 갱신) S&P500 1901~2012: SMA10 CAGR 10.2% vs 매수보유 9.3%, 변동성 12.0% vs 17.9%, 최대낙폭 −50.3% vs −83.5%. 5자산 EW 1973~2012: 10.5% vs 9.9%, MDD −9.5% vs −46.0%. **거래비용·세금 미반영.** 발표 후 2006~2012 7년 중 타이밍이 이긴 해 3개(4개 해는 뒤짐). EAFE 단독 수치는 없음(EM 미포함). [실측 보고됨] https://www.cxoadvisory.com/?p=1115
- CXO, S&P 1871~2012(1,704개월): SMA10 즉시 실행 월 0.75% vs 매수보유 0.79%(수익은 **낮음**), 변동성 2.73% vs 4.10%, 주식 보유 기간 61.9%. **1개월 지연 실행 시 0.61%로 급감.** 10년 단위 15구간 중 수익률은 SMA가 6승·매수보유 9승, 위험조정은 SMA 11승. 거래비용 손익분기 약 1%(편도). [실측 보고됨] https://www.cxoadvisory.com/technical-trading/10-month-sma-timing-signals-over-the-long-run/
- Zakamulin(1860~2009 S&P, 6개 MA 규칙, 0.25% 비용): 타이밍 규칙은 평균수익 **낮고** 샤프만 높음, 현금 보유 약 1/3, 5·10년 구간에서 이길 확률 ≈ 50%. 초과성과는 1870s·1900s·1930s·1970s·2000s 약세장에 집중, 수십 년 뒤처지는 구간 존재. [실측 보고됨] https://www.cxoadvisory.com/technical-trading/market-timing-with-moving-averages-over-the-very-long-run/
- Zakamulin 2014(JAM) "실전 성과": OOS+비용 반영 시 "타이밍 성과는 크게 과장돼 있다". 2018(IRF): Glabadanidis의 강한 결과는 look-ahead 편향, MA는 매수보유와 "통계적으로 구별 불가". [실측 보고됨, 수치는 유료 본문] https://ideas.repec.org/a/pal/assmgt/v15y2014i4d10.1057_jam.2014.25.html · https://onlinelibrary.wiley.com/doi/abs/10.1111/irfi.12132
- Swedroe 요약(Zakamulin 2013): "매도" 신호 기간에 T-bill이 주식을 이긴 비율은 약 20% → 신호 실패율 ≈ 80%. [실측 보고됨, 2차 인용] https://www.etf.com/sections/index-investor-corner/swedroe-beware-lure-market-timing
- Sullivan–Timmermann–White 1999(JF): 다우 100년, 7,846개 기술규칙 Reality Check. 1987~96 OOS에서 p=0.70 → 최우수 규칙도 유의성 없음. [실측 보고됨] https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf
- Bessembinder–Chan 1995(PBFJ): 아시아 6국 중 MA·돌파 규칙은 말레이시아·태국·대만에서 유효, **한국·홍콩·일본은 약함**, 비동시거래·비용 반영 시 더 감소. [실측 보고됨, 2차 요약] https://weblib.cpce-polyu.edu.hk/apps/wps/assets/pdf/w20160505.pdf
- 한국 직접 백테스트(개인 깃허브, 비동료심사): KOSPI 2016-09~2026-09 무비용 — MA240 돌파 CAGR 10.4%/MDD −38.6% vs 매수보유 13.3%/−43.9%; MA20/60 교차 9.7%/−34.8%. 0.1% 비용·2015~2025: KOSPI 교차 −0.58% vs B&H +2.33%, KOSDAQ −3.91% vs +0.29%. 2023~2026 강세장: KOSPI 교차 20.9% vs B&H 34.1%(13%p 뒤짐). [비동료심사] https://github.com/tpwns1903/quant-strategy-backtests
- 코스피 200일선 학술 백테스트(KCI·DBpia)는 검색에서 확인 못 함(없다는 뜻은 아님). 2026-10-13 코스피 200일선(6,385) 첫 이탈 보도. https://www.fnnews.com/news/202610170802085816
- Newfound: 12개월 MA 국가별 적용 시 이탈리아는 **낙폭이 매수보유보다 더 깊어짐**(단일 국가 역효과 사례). [실측 보고됨] https://blog.thinknewfound.com/2019/11/global-growth-trend-timing/
- **대조**: 외부 근거는 "MA 타이밍 = 수익은 비슷하거나 낮고 낙폭만 줄임, 강세장 뒤처짐, 지연 실행 시 급감"으로 우리 "MA 필터 < 낙폭 깊이" 및 "확인 대기 비용" 결과와 방향 일치. 한국은 B&C에서도 약한 시장.

## 2. 급락 후 매수 / 변동성 관리 / VKOSPI

### 2-a 지수 급락 후 반등 (한국)
- 유안타(2026-10): 코스피 7거래일 −10% 이상 12회 → 1주 뒤 상승 83%(10/12). 낙폭 −15% 초과 5회 → **1개월 뒤 상승 20%(1/5)**. [실측 보고됨, 증권사·n 매우 작음] https://www.imaeil.com/page/view/2026101609001546709
- 키움(2026-06): 역대 코스피 일간 하락률 상위 10회 → 5거래일 +6.9%, 20거래일 +7.8%, 60거래일 +24.6% 평균(2008 류 시스템 위기 제외 대부분 반등). [실측 보고됨, 증권사·n=10·CI 없음] https://core.asiae.co.kr/article/2026062408442970147
- 골드만(BigGo 인용): 2000년 이후 서킷브레이커 12회 중 다음날 상승 9회(75%), 5일 평균 +4.5%. [실측 보고됨, 2차] https://finance.biggo.com/news/810f395c-fc9a-41eb-9b4c-d0e5dc518d9b
- 2026년 일간 −5.5% 이상 16회 중 다음날 반등 10회(62.5%); 7/28 −10.8% 다음날 −6% 추가 하락 사례. [실측 보고됨] https://www.fnnews.com/news/202610141720386931
- 미국 "buy the dip" 종합: 매년 −10% 조정을 기다린 투자자 6.6% vs 연초 즉시 투자 12.1%(S&P 1990~2024, 현금 대기 비용 포함). QQQ 442개 변형 중 −10% 딥 규칙 6.6%/년 vs B&H 20.1%(2013~). [실측 보고됨, 비동료심사] https://www.couttscrowndependencies.com/insights/cio-update/cio-update-should-you-buy-the-dip.html · https://marketnull.substack.com/p/i-backtested-442-ways-to-buy-the
- 국제 장기 평균회귀: 18개국 1900~2009 반감기 ~18.5년(1970~96 패널은 ~3.5년) — 월·분기 단위 반등 근거로는 부적합. [실측 보고됨] https://www.sciencedirect.com/science/article/abs/pii/S0261560611001616
- **대조**: 한국 증권사 통계는 우리 "+6.8%·9/9"와 방향 일치하나 모두 n≤16·CI 없음. 유안타의 "−15% 초과 시 1개월 승률 20%"는 **낙폭이 너무 깊으면 20일 반등이 안 된다**는 반증 후보 → 우리 규칙의 하한(−5% ~ −15%)을 로컬에서 확인할 가치.

### 2-b 변동성 관리(Moreira–Muir 식)
- Moreira–Muir 2017(JF): 변동성 역비례 비중이 시장·모멘텀 등에서 알파·샤프 개선, 부록에서 OECD 20개국에도 성립 주장(국가별 표는 미확인). [실측 보고됨] https://www.nber.org/papers/w22208.pdf
- Cederburg 외 2020(JFE): 103개 전략에서 **실시간 구현 시 샤프·확실성등가 대체로 하락**, 스패닝 회귀 알파는 OOS에서 재현 안 됨(구조 불안정). [실측 보고됨] https://www.sciencedirect.com/science/article/abs/pii/S0304405X2030132X
- DeMiguel 외 2024(JF), Barroso–Detzel 2021: 비용·OOS 반영 시 효과 축소. 45개국 연구(2024, JBF 계열)는 국가 간 차이 큼. [실측 보고됨, 수치 유료] https://www.sciencedirect.com/science/article/pii/S092753982400094X
- 한국 전용 변동성 관리 연구는 검색에서 미확인.
- **대조**: 변동성 관리는 "고변동 때 비중 축소" = 급락 직후 매수와 **정반대 방향**. 우리 급락 매수 결과가 맞다면 한국 소형주에서 vol-targeting은 반등을 놓칠 위험. 함정 후보.

### 2-c VKOSPI
- 금융정보연구 2024: VKOSPI 상승 동반 대규모 하락 → 반전 효과, VKOSPI 하락 동반 급등 → 지속 효과; 통제 후에도 유의(개별종목 수준, 수치 초록 미기재). [실측 보고됨] https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003055121
- Lee–Ryu: VKOSPI 상승 다음날 대형>소형, 성장>가치 — **소형주에 불리한 국면 신호**. [실측 보고됨] https://pure.skku.edu/en/publications/the-volatility-index-and-style-rotation-evidence-from-the-korean-/
- 월간 그랜저 인과(2003~2016) 수익률↔VKOSPI p=0.18~0.49 불유의. [실측 보고됨] http://www.korfin.org/korfin_file/forum/2017co-conf7-1.pdf
- 2026년 VKOSPI: 7/29 87.79, 10/15 55.38(뉴스). 급등 뒤 지수 수익률 백테스트는 미확인.
- **대조**: "VKOSPI 급등 + 지수 급락 → 반전"은 우리 규칙을 뒷받침하되, 소형주는 반등 초기에 대형주에 뒤질 수 있음(스타일 회전) → 바스켓 40일 수익이 지수 반등보다 작은지 확인 가치.

## 3. 시장 폭(breadth)·투매 지표
- Zaremba 외(2021~): 64개국 1973~2018 등락종목 차이가 미래 수익 예측(패널·IS). [실측 보고됨, OOS 설계 미확인] https://www.researchgate.net/publication/340699814_Herding_for_profits_Market_breadth_and_the_cross-section_of_global_equity_returns
- 인도 ADR 지표: 예측력 없음(단일국가, 부정 결과). [실측 보고됨] https://www.researchgate.net/publication/324706089_An_Analysis_of_the_Advance-Decline_Indicator_in_the_Indian_Stock_Market
- 200일선 상회 비율·Zweig thrust·90% 상승거래량 등은 실무 통념(20%/80% 임계) 수준, 엄밀한 OOS 검증 자료 미발견; 집계 방식이 벤더마다 달라 수치 불일치. [주장] https://chartschool.stockcharts.com/table-of-contents/market-indicators/percent-above-moving-average
- 한국: ADR 70% 이하 과매도 통념, 2023~25 코스피 ADR 저점 60~75%대(제공 사이트 간 79% vs 61% 불일치). 10/13 52주 신저가 200종목. KCI 실증 미확인. [주장] https://www.kadr.co.kr/ · https://www.fnnews.com/news/202610151815584946
- **대조**: 폭 지표는 지수 낙폭과 상관 높아 독립 정보가 적을 가능성. 추가하려면 "낙폭 통제 후 증분"으로만 평가.

## 4. 야간 vs 장중 수익률 (한국)
- 코스닥 전종목(재무관리연구 2016): 야간수익률 유의 양(+), 주간 유의 음(−), 둘 사이 유의 음의 상관(반전). 전일 개인 순매수 비중 높을수록 반전 확대. [실측 보고됨, 수치 초록 미기재] https://www.kci.go.kr/kciportal/landing/article.kci?arti_id=ART002182863
- KOSPI 종목(MDPI 2019): 높은 야간수익률 → 2~3일 단기 상승, 장기 하락. [실측 보고됨] https://www.mdpi.com/2071-1050/11/13/3718
- KOSPI 일수익 분산의 40.7%가 야간 성분(Emerald JDQS). [실측 보고됨] https://www.emerald.com/jdqs/article/28/4/209/197675/CAPM-verification-using-overnight-and-daytime
- Lou–Polk–Skouras 2019(JFE, 미국): 모멘텀 이익은 야간, 반전·가치는 장중에 발생. [실측 보고됨] https://personal.lse.ac.uk/polk/research/TugOfWar.pdf
- **대조·함의**: 한국 소형주는 "종가 매수 → 시가 매도"가 평균적으로 유리하고 "시가 매수"는 개인 추격매수 프리미엄을 지불하는 셈. 우리 "급락 다음날 매수"가 **시가**라면 전일 종가 매수 대비 비용이 숨어 있을 수 있음 → 체결 시점별 재계산 가치(실측 가능).

## 5. 몇 번 맞아야 믿을 수 있나 (다중검정·과최적화)
- Harvey–Liu–Zhu 2016(RFS): 316개 팩터 다중검정 → 신규 팩터 **t ≥ 3.0**(기존 2.0은 무의미). [실측 보고됨] https://www.nber.org/papers/w20592
- Harvey–Liu 2015(JPM) "Backtesting": 샤프 haircut — 50% 일괄 할인은 틀림, 한계적 샤프는 거의 전부 깎임. [실측 보고됨] https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF
- Bailey–Borwein–López de Prado–Zhu 2014: **5년 표본에 45개 이상 설정을 시험하면 IS 샤프 ≈1.0이 거의 보장되고 OOS 기대 샤프 = 0**. MinBTL은 시험 횟수 N의 로그에 비례해 늘어남. [실측 보고됨] https://www.cxoadvisory.com/big-ideas/insidiousness-of-overfitting-investment-strategies-via-iterative-backtests · https://papers.ssrn.com/abstract=2326253
- Bailey–López de Prado 2014 DSR: N회 시험 중 최대 샤프 기대치를 허들로; N을 정직하게 세는 것이 전부. [실측 보고됨] https://papers.ssrn.com/abstract=2460551
- 실무 환산(추정): 이항 승률만으로 "9/9"는 p=0.002(단측, 무작위 50%) — 그러나 규칙 변형을 k개 시험했다면 Bonferroni로 k배. 사건 수 n≈9~12는 **방향 확인용**, 효과 크기 CI는 넓어 수익률 수치 신뢰엔 n≥30 사건 또는 t≥3 필요(위 문헌 기준). 겹치는 40일 창은 독립 사건 수를 더 줄임.
- **대조**: 우리 9/9는 유안타 10/12·골드만 9/12와 같은 급의 표본. "채택"이 아니라 "기움"이 정직한 라벨.

## 결론(1줄씩)
- 근거 가장 강함: 급락 후 매수(한국 다수 소표본 일치) — 단 깊은 낙폭(−15%↑)·시스템 위기는 예외; 야간 프리미엄(체결 시점 설계).
- 함정 후보: MA 추세필터(강세장 뒤처짐·지연 비용), 변동성 관리(급락 직후 비중 축소로 반등 놓침), 폭 지표(낙폭과 중복), 확인 대기.
- 최소 표본 규칙: t≥3 / 5년·45시험 한계 / 사건 n<30이면 방향만.
