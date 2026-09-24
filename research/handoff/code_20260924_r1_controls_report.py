"""Render R1 follow-up note and static account chart from saved outputs."""
from pathlib import Path
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
H=Path(__file__).resolve().parent;O=H/'r1_controls_20260924'
S=pd.read_csv(O/'summary.csv');P=pd.read_csv(O/'paired.csv');A=pd.read_csv(O/'accounts.csv');D=pd.read_csv(O/'account_paths.csv')
M=json.loads((O/'metadata.json').read_text(encoding='utf-8'));V=json.loads((O/'verification.json').read_text(encoding='utf-8'))
names={'R1':'R1: 장기 모멘텀+고베타+최근 신고가','R1_amount':'R1+거래대금','beta_near':'고베타+최근 신고가',
       'size_only':'시가총액만','amount_only':'거래대금만','beta_only':'고베타만','momentum_only':'장기 모멘텀만','near_only':'최근 신고가만'}
def tab(head,rows):return '\n'.join(['| '+' | '.join(head)+' |','|'+'|'.join(['---']*len(head))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def ci(row,key):return f'{row[key]*100:+.2f} [{row[key+"_lo"]*100:+.2f}, {row[key+"_hi"]*100:+.2f}]'
plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
fig,ax=plt.subplots(figsize=(11,5.5),layout='constrained')
for name,matched,label,color in [('R1_amount',False,'R1+거래대금','#1d7a68'),('beta_near',False,'고베타+최근 신고가','#397ac4'),
                               ('amount_only',False,'거래대금만','#da8a32'),('R1_amount',True,'R1+거래대금과 같은 시장비중의 지수','#777777')]:
    g=D[(D.name==name)&(D.matched==matched)]
    ax.plot(pd.to_datetime(g.date.astype(str)),g.nav*100,label=label,color=color,lw=2,ls='--' if matched else '-')
ax.set(title='같은 자금 100으로 시작한 분할 투자 모의계좌',ylabel='현금+주식 평가액 (시작=100)')
ax.grid(alpha=.2);ax.legend(loc='upper left');fig.suptitle('매월 계좌의 1/6 목표 · 120거래일 보유 · 편도 비용 0.25% · 과거 탐색 결과',fontsize=10,color='#555555')
fig.savefig(O/'accounts.png',dpi=160);plt.close(fig)
out=[
'# REPLY — R1 단순 대조군·분할 투자 계좌 확인 (2026-09-24)',
'',
'사용자가 계속 진행하도록 승인한 후 수행했다. 오늘 배치가 이미 스킵됐다는 사용자 확인에 따라 2026-09-24에 한해 시간 제한 예외를 적용했다. DB·운영 코드·Claude 원본은 수정하지 않았다.',
'',
'## 직접 계산한 결론',
'',
'- 수정 R1의 지수 초과 +10.55%p를 다시 재현했다. 같은20개월·같은120일 보유·같은비용으로 비교해 R1+거래대금과 고베타+최근신고가 조합을 추가 검토 후보로 남긴다.',
'- **고베타만으로는 같은 성과가 나오지 않았다.** 최근 신고가와 결합하면 고베타 단독 대비 개선이 관측된다. “핵심은 베타 하나”라는 결론은 성급하다.',
'- **모멘텀 불필요가 확정된 것도 아니다.** 모멘텀 제거형과 R1의 차이를 명확히 확인하지 못했다. 동등성 검증이나 새 기간 검증은 하지 않았다. 더 단순한 비교 후보로 둘 수는 있다.',
'- “거래대금 큰 종목만”보다 조합이 추가로 우월한지는 불확실하다. 이 대조군이 다음 검증의 핵심이다.',
'- 현금 제약이 있는 분할 계좌에서도 후보들의 우위는 남았으나, 이는 이미 탐색한 한 기간의 결과다. 미래 기대수익·운용 채택을 의미하지 않는다.',
'',
'## 1. 맞춘 비교 조건',
'',
f'- 신호일: {M["selection_start"]}~{M["selection_end"]}, 원본 R1이 계산 가능한 동일20개월. 모든 대조군도 이 날짜만 사용했다.',
'- 동일 가격 패널·동일 신호일 가드·통합 상위20개·t+1 종가 진입·120거래일 보유. 미래수익·향후 가격존재 여부로 후보를 거르지 않음. +500% 초과 수익 보존.',
'- 연구 질문은 R1과 단순 대조군 비교이며, 기존 v30/ls_t1 점수나 공식 판정과 섞지 않았다.',
'- 베타는60일 시장민감도, 최근 신고가는252일 롤링 최고가(최소120관측)를 마지막으로 갱신한 이후 경과일. 단순한 고점과의 가격거리와 다르다.',
'- 모멘텀은 원본식(252일 수익−21일 수익), 시총은 원본 근사 주식수×가격. 원본과 일치시키기 위해 최근 관측 시장구분을 사용했으며 과거 시장이전은 별도 검증하지 않았다.',
'- 진입 시점별 수익은 왕복0.5% 차감. 선정 종목의 코스피·코스닥 비중과 동일한 지수를 비교했다. 배당 제외.',
'- 아래 구간은6개월 원형 블록·3,000회·명목95%. 20개 진입은 독립20회가 아니며 많은 시도에 대한 보정은 없다.',
'',
'## 2. 같은20개월의 120일 보유 결과',
'',
tab(['조건','비용 후 평균 수익 % [95% 구간]','같은 시장비중 지수 초과 %p [95% 구간]'],[
    [names[r['name']],ci(r,'net'),ci(r,'excess')] for r in S.to_dict('records')]),
'',
'모든 행 n=20개월. 이것은120일 보유 바스켓의 평균이며 연환산 수익률이 아니다. 큰 종목만 선정하면 코스피 비중도 커지므로 규칙마다 비교지수 수익이 다르다. 실제 수익의 차이와 시장배분을 맞춘 초과수익 차이를 아래에 함께 제시한다.',
'',
'## 3. 같은 날짜의 직접 차이',
'',
tab(['비교','비용 후 수익 차이 %p [95% 구간]','지수 초과의 차이 %p [95% 구간]'],[
    [names[a]+' − '+names[b],
     f'{gn.difference*100:+.2f} [{gn.lo*100:+.2f}, {gn.hi*100:+.2f}]',
     f'{ge.difference*100:+.2f} [{ge.lo*100:+.2f}, {ge.hi*100:+.2f}]']
    for a,b in [('beta_near','R1'),('beta_near','beta_only'),('R1_amount','R1'),('R1_amount','amount_only'),('R1_amount','size_only')]
    for gn in [P[(P.a==a)&(P.b==b)&(P.metric=='net')].iloc[0]]
    for ge in [P[(P.a==a)&(P.b==b)&(P.metric=='excess')].iloc[0]]]),
'',
'각 행 n=20개월. 모멘텀 제거형과 R1의 수익 차이 구간이0을 포함한다는 사실은 “둘이 같다”는 증거가 아니다. 거래대금을 추가한 개선도 실제수익 차이에서는 양수지만 시장배분을 맞춘 초과차이에서는0을 포함한다. 가설을 단순하게 가져갈 이유와 성분이 불필요하다는 통계적 확정은 구분한다.',
'',
'## 4. 한 계좌에서 매월 나눠 투자하면',
'',
f'계좌 기간: {M["account_start"]}~{M["account_end"]}. 시작 자금1, 외부입금 없음. 매월 계좌 평가액의1/6을 목표로 새 바스켓을 매수하고120거래일 후 매도한다. 잔여현금보다 많이 사지 않으며 매수·매도 금액의0.25%씩 비용을 낸다. 일별 비중 재조정 없음, 현금이자0.',
'',
'120거래일은 달력6개월과 정확히 같지 않고 계좌 평가액도 바뀌므로 현금이 부족한 월에는 덜 산다. R1+거래대금은20회 중7회 목표보다 적게 샀다. 처음에는 현금이 많고 마지막 신규진입 후에는 잔여 보유분이 순차 청산된다. 완결된20개 진입을 비교하기 위한 닫힌 연구 구간이며 이후 매월 계속 투자한 계좌는 아니다.',
'',
tab(['조건','누적 %','연환산 %','최대낙폭 %','동일 방식 지수의 연환산 %'],[
    [names[name],f'{g.total*100:+.2f}',f'{g.cagr*100:+.2f}',f'{g.mdd*100:.2f}',f'{b.cagr*100:+.2f}']
    for name in ['R1','R1_amount','beta_near','amount_only','size_only','beta_only']
    for g in [A[(A.name==name)&~A.matched].iloc[0]] for b in [A[(A.name==name)&A.matched].iloc[0]]]),
'',
'각 행은 동일 역사기간의 계좌경로1개, 신규진입20회다. 계좌의 연환산·최대낙폭에 신뢰구간은 계산하지 않았으며 미래 기대값으로 제시하지 않는다. 통계적 불확실성은 위 월간 바스켓 블록 구간을 함께 봐야 한다.',
'',
f'참고로 시작일부터 끝까지 코스피·코스닥 지수를50:50으로 전액 보유하면 같은 비용 가정에서 연환산 {M["benchmark_buyhold_50_50"]["cagr"]*100:.2f}%, 최대낙폭 {M["benchmark_buyhold_50_50"]["mdd"]*100:.2f}%였다. 후보 계좌의 평균 주식 노출은 약72%이므로 낙폭이 작은 이유에 현금 보유 효과가 포함된다. 위 표의 “동일 방식 지수”가 노출 차이를 더 잘 맞춘 비교다.',
'',
f'![분할 투자 계좌]({(O/"accounts.png").as_posix()})',
'',
'## 5. 불확실성·검증',
'',
'- 상장폐지·백필 모집단, 수정주가 사후정정, 근사 주식수, 시장이전 미검증의 한계가 유지된다. 신호일 선정에 미래 가격을 사용하지 않았다는 것과 당시 정보 전체를 완벽히 복원했다는 것은 다르다.',
'- 일별 종가 체결 가정이다. 상한가 매수 실패·시장충격은 완전하게 재현하지 못했다. 진입 거래량0이면 해당 몫은 현금으로 두고 다음 순위로 교체하지 않았다.',
'- 계좌는120일째 거래정지이면 매도를 미루고 마지막 관측 가격으로 평가한다. R1+거래대금은 종료일에1개 포지션이 남아 평가액0.00613(시작자금1)이 포함된다. 이를 전손 처리해도 종료자금은2.43052→2.42439다.',
'- 수익 기여는 일부 종목에 집중된다. R1+거래대금의 SK스퀘어·원익홀딩스 두 종목이 평균120일 총수익에 합계7.14%p 기여했다(400개 종목×진입 슬롯, 동일 종목 재등장 포함). 이 기여도는 계좌 누적수익 기여와 다르며 사후 선정 통계다.',
f'- 수정 R1 바스켓 수익은 직전 독립감사와 최대오차 {M["reproduction_max_error"]:.3g}. 별도 주식수·현금 장부로 R1+거래대금의 {V["days"]}거래일 계좌를 재구성했고 현금/평가액 최대오차 {V["max_nav_cash_error"]:.3g}, 매수예산 최대오차 {V["max_budget_error"]:.3g}. 차입 없음·20개 진입·예산 상한을 확인했다.',
'- 검증용 코드와 산출물만 추가했다. 생산 코드·DB·기존 보고서 수정 및 신규 모델 등록은 없다.',
'',
'## 다음 연구의 기준',
'',
'**후보: 고베타+최근 신고가, R1+거래대금. 필수 대조군: 거래대금만, 고베타만, 같은 시장비중 지수.** 새 조건을 더 찾기보다 이 소수 규칙을 고정해 새 기간에서 비교하는 것이 우선이다. 특히 거래대금 단독보다 추가로 좋은지를 통과해야 복잡한 조합을 쓸 이유가 생긴다. 등록·공식 판정은 별도 결정이다.',
'',
'## 산출물',
'',
'- code_20260924_r1_controls.py (오늘 배치 예외는 `--batch-skipped-date 20260924`로 명시)',
'- code_20260924_r1_accounts_verify.py / code_20260924_r1_controls_report.py',
'- r1_controls_20260924/: cohorts·summary·paired·holdings·accounts·account_paths·orders·ticker_contributions CSV, metadata·verification JSON, accounts.png',
]
target=H/'REPLY_20260924_r1_controls_and_accounts.md';target.write_text('\n'.join(out)+'\n',encoding='utf-8');print(target)
