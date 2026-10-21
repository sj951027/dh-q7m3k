# 07 포트폴리오 구성·위험 통제 — 외부 증거 스카우트 (2026-10-21, 웹만)

대상: 롱온리·동일가중·10~20종목·40거래일 보유·한국 중소형·1인 운용(모의 계좌: 슬롯 40, 다음날 종가 진입, 40일 청산, 왕복 0.5%).
표기: [실측] = 논문/보고서가 데이터로 보임(2차 요약 포함) · [주장] = 이론·실무자 의견·검증 없음 · (추정) = 내 해석.
주의: 상당수 출처는 검색 요약·초록 수준으로 확인(원문 전체 미열람). 숫자는 재확인 전까지 참고치.

## 1. 손절 vs 무손절 vs 시간 청산
- Kaminski–Lo(JFM 2014) [실측+이론]: 수익이 랜덤워크면 손절은 기대수익을 깎음, 모멘텀(자기상관 +)이면 "stopping premium" 양수(지속성에 비례), **평균회귀면 손절이 해침**(하락 뒤 팔고 반등을 놓침). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968338 · PDF https://www.smallake.kr/wp-content/uploads/2017/02/When_Do_Stop-Loss_Rules_Stop_Losses.pdf
- Han–Zhou–Zhu "Taming Momentum Crashes"(1926~2013) [실측]: 월초가 대비 −10% 종목별 손절→T-bill. EW 모멘텀 최악월 −49.8%→−11.4%, 샤프 2배+. 단 이는 **롱숏 모멘텀**(크래시는 숏 레그에서 발생). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2407199
- Alpha Architect 재현 [실측]: 롱온리 winner 포트폴리오에서는 효과가 작고 5% 손절이 가장 나음 — 롱온리 적용 근거 약함. https://alphaarchitect.com/2016/08/taming-the-momentum-roller-coaster-fact-or-fiction/
- Robeco: 모멘텀 크래시 대책으로 손절이 아닌 **정의 변경**(잔차 모멘텀 등) 제시. 손절 전용 Robeco 논문은 못 찾음. https://www.robeco.com/de-de/einblicke/2023/02/quant-chart-taming-momentum-crashes
- 실무자 [주장]: "평균회귀 전략에서 손절은 거의 모든 백테스트에서 해롭다"(Quantified Strategies). https://www.quantifiedstrategies.com/mean-reversion-trading-strategy/
- → 채택 후보: **종목 손절 없음 + 시간 청산(40일) 유지**가 문헌과 일치. 테스트: 모의 계좌에 −10%/−15%/−20% 종목 손절 변형을 병행 적재(가중 0 관측) → 40거래일 뒤 h=20d 평균·CI·최악 주 비교. 손절 변형은 왕복 0.5%가 추가 발생함을 반드시 반영.

## 2. 포지션 크기: 동일가중 vs 변동성 역가중 vs 순위가중
- EDHEC(Plyakha–Uppal–Vilkov) [실측]: 월 리밸런스 EW 가 VW·PW 보다 총수익·4팩터 알파·샤프 우위, 50bp 비용 뒤에도 유지. 단 변동성·첨도 높음, 알파 일부는 역추세 리밸런싱 효과. https://www.venn-capital.com/pdf/edhec_working_paper_equal-weighted_portfolio.pdf
- EW 가 여전히 어려운 벤치마크(50bp 비용 뒤) [실측]. https://www.sciencedirect.com/science/article/pii/S2110701724000489
- ReSolve [실측]: 산업/팩터 묶음에서 역변동성 샤프 0.51~0.54 vs EW 0.49~0.51 — 차이 0.01~0.03로 미미. https://investresolve.com/portfolio-optimization-simple-optimal-methods/
- 변동성 관리(포트폴리오 레벨) Moreira–Muir 효과는 Cederburg 외(JFE 2020) 103전략 OOS 에서 **체계적 초과 없음**, 비용 뒤 소멸(Barroso–Detzel). https://alphaarchitect.com/does-portfolio-timing-based-on-volatility-signals-outperform-buy-and-hold/
- 순위가중 vs EW 비용 뒤 직접 비교 증거: 못 찾음.
- → 채택: EW 유지(단순·증거 충분). 역변동성은 소형주에서 저변동=저유동 쪽으로 기울 위험(추정). 테스트: 같은 신호로 EW vs 1/σ20일 가중 두 계좌를 병행, 차이의 CI 가 0을 포함하면 EW 유지.

## 3. 종목 수·업종 집중 한도
- CLMX(2001) [실측]: 미국 개별주 고유변동성 상승으로 분산에 필요한 종목 수 증가(약 50). 소형주 전용 수치는 없음. https://www.nber.org/system/files/working_papers/w7590/w7590.pdf · 2022 후속 https://www.nber.org/system/files/working_papers/w29916/w29916.pdf
- 한국: KOSPI200 무작위 조합 논문 [실측] — 비체계적 위험은 약 10종목에서 대부분 제거(기간별 차이). https://scienceon.kisti.re.kr/srch/selectPORSrchArticle.do?cn=DIKO0011851895 · 20종목=분산가능위험 90.9% 제거(금융정보연구 2016). https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART002280807
- 업종 중립 [실측, 혼재]: 롱숏에서는 업종 조정이 유리(78% vs 20%), **롱온리에선 샤프 거의 같음**(Alpha Architect 종합). https://alphaarchitect.com/is-sector-neutrality-in-factor-investing-a-mistake/ · S&P DJI 는 업종중립이 더 효율적이라 주장. https://www.spglobal.com/spdji/en/documents/research/research-exploring-techniques-in-multi-factor-index-construction.pdf
- → 채택: 종목 20~40 은 한국 대형주 기준으로 충분; 중소형은 고유위험이 커서 더 필요할 가능성(추정). 업종 캡은 롱온리 수익 개선 증거 약함 → **최대 손실 통제 목적**으로만 소프트 캡(예: 한 업종 ≤30%). 테스트: 과거 적재 기록에서 업종 캡 적용/미적용 두 시뮬 → h=20d 평균 차이·최악 주 비교(0-diff 가 기본 가설).

## 4. 계좌 드로다운 뒤 노출 축소
- Strahle(SSRN 2026, SPY 2000~2025) [실측]: 드로다운 기반 노출 축소 3종 모두 변동성·MDD 감소했지만 CAGR 8.03%→5.27~7.41%. 원인은 **반등 구간 저노출**과 얕은 드로다운에서의 왕복. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7542498
- Macrosynergy [실측, 암호자산]: 변동성 통제로 같은 MDD 를 맞추려면 노출을 크게 줄여야 해 수익 손상. https://macrosynergy.com/research/drawdown-control/
- 역추세 전략 + 드로다운 통제 직접 연구: 못 찾음. (추정) 과매도 전략은 급락 직후 수익이 집중되므로(연구 "코스피 급락 뒤 9/9 플러스" 내부 발견과 일치) 드로다운 트리거는 Kaminski–Lo 논리상 해로울 가능성이 큼.
- → 채택 후보: 계좌 DD 트리거 **도입 안 함**. 대신 자본 보존은 슬롯 수(40) 자체로. 테스트: 모의 계좌 로그에 "−10% DD 이후 신규 진입 절반" 가상 규칙을 오버레이해 h=20d·주별 일관 비교 — 해로우면 폐기.

## 5. 일별 분할 진입(1/N) vs 일괄 진입
- Jegadeesh–Titman(1993) [실측]: 중첩 포트폴리오(매월 1/K 교체)는 검정력 목적; 2차 요약은 "비중첩과 수익 차이 없음 + 분산 효과". https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf
- Newfound "Rebalance Timing Luck" [실측]: 리밸런스 날짜만 달라도 100종목 스마트베타에서 연 100~400bp 차이; N개 하위 포트폴리오 동일가중이 타이밍 운을 **1/N 로 축소**(저자 주장, 도출은 미확인). 집중·빠른 신호일수록 효과 큼. https://www.thinknewfound.com/rebalance-timing-luck · https://blog.thinknewfound.com/2019/11/the-dumb-timing-luck-of-smart-beta/
- → 현 설계(매일 1/40 진입·40일 보유)는 문헌이 권하는 트랜칭 그 자체. 채택: 유지. 테스트: 같은 기간을 "매 40일 일괄 진입" 40가지 시작일로 시뮬 → 결과 분산 vs 일별 분할 1개 결과. 분산 축소 폭이 1/N 근처인지 확인.

## 6. 리밸런싱·회전율·재진입 금지 K일
- Novy-Marx–Velikov(RFS 2016) [실측]: 비용 완화에 가장 효과적인 단일 도구 = **매수/보유 스프레드**(진입 기준보다 완화된 보유 기준). 월 편도 회전 50% 이하 전략만 비용 뒤 유의. https://www.nber.org/system/files/working_papers/w20721/w20721.pdf
- Chen–Velikov [실측]: 공표 후 비용 완화 이상현상 수익 평균 월 13bp, 취약. https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2019/09/Accounting-for-the-Anomaly-Zoo.pdf
- 한국 단기 반전 [실측]: 1개월 반전 계수 −2.95%/월(t=−3.77), 미국보다 강함; 비용 반영 시 축소 예상. https://www.emerald.com/jdqs/article/29/3/174/206550/The-effect-of-short-term-return-reversals-on · 소형주 과다 거래가 비용의 주범(de Groot–Huij–Zhou, 미국). https://www.efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2011-Braga/papers/0259.pdf
- Robeco 단기반전 개선 [주장+실측 요약]: 업종·팩터 모멘텀과 결합해 위험조정수익 2배. https://www.robeco.com/en-int/insights/2023/10/reversing-the-trend-of-short-term-reversal
- "같은 종목 K일 내 재진입 금지" 직접 연구: 못 찾음. (추정) 40일 보유 뒤 즉시 재진입은 왕복 0.5% 추가에 신호 중복이라 매수/보유 스프레드 논리상 손해.
- → 채택 후보: 청산 후 재진입 쿨다운 K=20거래일(h 와 동일) 또는 "청산 시점에 신호가 여전히 상위면 보유 연장"(buy/hold spread). 테스트: 모의 계좌에서 재진입 건만 분리해 h=20d 평균 vs 신규 진입 평균 비교(n·CI 명시).

## 7. 한국 특수: 관리종목·거래정지·상하한가·상장폐지
- 제도 [사실]: 상폐 사유 발생 시 매매정지; 정리매매 최대 7거래일, 가격제한폭 없음, 30분 단일가. https://www.stockplus.com/m/investing_strategies/articles/5661?scope=all · https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1701&ccfNo=1&cciNo=2&cnpClsNo=2
- 정리매매 손실 [실측, 표본 작음]: 15개사 정리매매 직전 종가→종료일 평균 −92.8%(대부분 −90% 이상). https://www.sedaily.com/article/14113356 · KCMI: 상폐 전 1년 대비 정리매매 가격 약 1/8(52종목). https://www.kcmi.re.kr/kcmifile/report_data/1197/reportpdf_1197.pdf
- 미국 기준 [실측]: Shumway–Warther 나스닥 누락 상폐 수익률 −55% 가정, NYSE/AMEX −30%(Shumway 1997). https://ideas.repec.org/a/bla/jfinan/v54y1999i6p2361-2379.html
- 2026 변동 [사실]: 시총 미달 상폐가 법원 결정으로 유예, 거래정지는 유지 — 이벤트 날짜 고정 어려움. https://www.mediapen.com/news/view/1129268
- 가격제한폭 [실측, 중국]: 상한가 다음날 지속이 반전보다 흔함, 하한가 뒤 지속 더 강함 → 상한가 종가 매수 가정은 상향 편향. https://arxiv.org/pdf/1503.03548 · https://www.princeton.edu/~wxiong/papers/PriceLimit.pdf
- → 채택 후보: (a) 상폐·정리매매 진입 종목은 **정지 전 종가의 −90%**(미국 −55%보다 보수적, 한국 실측에 맞춤) 또는 정리매매 실제 종가 중 작은 쪽; (b) 진입일 종가가 상한가 마감이면 진입 불가(다음날 재시도 1회 뒤 포기), 청산일 하한가 마감이면 다음 거래 가능일 종가로 청산; (c) 거래정지 중 청산 예정이면 해제일 종가(지연일수 기록); (d) 관리종목 지정 종목은 진입 제외(게이트). 테스트: 과거 적재에서 (a)~(c) 적용 전후 h=20d 평균·최악 종목 차이 보고(영향 0 이면 각주만).

## 모의 계좌 가정 중 가장 틀릴 법한 것
- "다음날 종가에 항상 체결·청산 가능" — 상한가 마감·거래정지·관리종목 전환을 무시하면 과매도 소형주에서 상향 편향. 둘째는 상폐 손실 처리(마지막 가격 유지 시 과소 손실).
