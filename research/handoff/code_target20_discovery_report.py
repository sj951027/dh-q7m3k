"""Summarize data-driven discovery without selecting a winner on held predictions."""
from pathlib import Path
import json
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'research/target20_discovery_20261004'
S=pd.read_csv(P/'summary.csv');D=pd.read_csv(P/'daily_results.csv');names={'learn_hit':'20% 수익 학습','learn_first':'첫날 상승 학습','learn_joint':'공동 목표 학습','learn_ret':'수익 크기 학습','learn_balanced':'세 확률 순위 평균','cluster_shape':'가격·거래량 모양 군집','control_amount':'거래대금 상위10','control_fundamental':'재무 순위 상위10','control_rsi':'RSI 낮은10'}
def table(df):
 def fmt(x):
  if pd.isna(x):return '—'
  return f'{x:.2f}' if isinstance(x,(float,np.floating)) else str(x)
 return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(map(fmt,row))+' |' for row in df.itertuples(index=False,name=None))
all=S[S.period=='all'].copy();all.method=all.method.map(names)
cols={'market':'시장','method':'선정 방식','n_dates':'평가 날짜','ret':'20일 평균 %','hit':'20% 비율 %','first':'첫날 상승 %','joint':'공동 목표 %','mae':'최저 수익 평균 %'}
overview=all[list(cols)].rename(columns=cols)
main=S[(S.period=='all')&(S.method=='learn_joint')];lines=[]
for r in main.itertuples():
 lines.append(f'- **{r.market.upper()} 공동 목표 학습**: 20일 평균 {r.ret:+.2f}% [{r.ret_lo:+.2f}, {r.ret_hi:+.2f}], 20% 도달 비율 {r.hit:.2f}%, 첫날 상승 {r.first:.2f}%, 공동 목표 {r.joint:.2f}%. 거래대금 대조 대비 수익 차이 {r.vs_amount_ret:+.2f}%p [{r.vs_amount_ret_lo:+.2f}, {r.vs_amount_ret_hi:+.2f}], 공동 목표 차이 {r.vs_amount_joint:+.2f}%p [{r.vs_amount_joint_lo:+.2f}, {r.vs_amount_joint_hi:+.2f}].')
year=S[(S.period.isin(['2025','2026']))&S.method.isin(['learn_joint','learn_hit','learn_first','cluster_shape','control_amount','control_fundamental'])].copy();year.method=year.method.map(names)
yt=year[['market','method','period','ret','hit','first','joint']].rename(columns={'market':'시장','method':'방식','period':'연도','ret':'수익 %','hit':'20% 비율','first':'첫날 상승','joint':'공동 목표'})
audit=pd.concat([pd.read_csv(P/f'fold_audit_{m}.csv') for m in ['kospi','kosdaq']]);cal=pd.concat([pd.read_csv(P/f'calibration_{m}.csv') for m in ['kospi','kosdaq']]);imp=pd.concat([pd.read_csv(P/f'training_importance_{m}.csv') for m in ['kospi','kosdaq']]);verify=json.loads((P/'verification.json').read_text())
ig=imp[(imp.target=='joint')&(imp.fold=='2026Q3')].sort_values(['market','gain'],ascending=[True,False]).groupby('market').head(6);ig=ig[['market','feature','share']].copy();ig['share']*=100;ig.columns=['시장','변수','학습 분할 이득 비중 %']
calt=cal.groupby(['market','target']).agg(folds=('fold','size'),mean_auc=('auc','mean'),mean_brier=('brier','mean'),mean_baseline_brier=('baseline_brier','mean')).reset_index()
methods=['control_amount','control_fundamental','learn_hit','learn_first','learn_joint','learn_balanced','cluster_shape'];labels=['Liquidity control','Fundamental control','Learn +20%','Learn first day','Learn joint goal','Mean probability ranks','Path clusters'];fig,axes=plt.subplots(1,4,figsize=(16,5),constrained_layout=True)
for k,m in enumerate(['kospi','kosdaq']):
 data=S[(S.market==m)&(S.period=='all')].set_index('method').loc[methods]
 for offset,metric in enumerate(['joint','first']):
  ax=axes[k*2+offset];y=np.arange(len(methods));ax.hlines(y,data[metric+'_lo'],data[metric+'_hi'],color='#8aaac0',lw=2);ax.scatter(data[metric],y,color='#25587a',s=24);ax.set_yticks(y,labels if offset==0 else ['']*len(labels));ax.invert_yaxis();ax.set_title(m.upper()+(' joint goal' if metric=='joint' else ' first-day gain'));ax.set_xlabel('Percent');ax.grid(axis='x',alpha=.2)
  if metric=='first':ax.axvline(50,color='gray',ls=':',lw=1)
fig.suptitle('Quarterly past-only learning: 2025 to 2026\nDaily top10 means; exploratory 95% day-block intervals; not an account return',fontsize=11);fig.savefig(P/'learned_methods.png',dpi=160);plt.close(fig)
report=f'''# 데이터가 직접 관계를 학습하도록 바꾼 연구

2026-10-04 / Codex. 운영 모델 등록·점수·판정·DB 변경 없음.

## 1. 사용자의 지적에 대한 답

맞는 지적이었다. 앞선 전수 탐색은 지표와 숫자 구간을 사람이 정하고 조합한 연구였다. 이번에는 **연속 원자료에서 비선형 관계를 학습하는 방법**과 **과거 가격·거래량 모양을 자동으로 묶는 방법**을 실제로 실행했다. 더 좋은 결과를 만들기 위해 평가 후 기준을 바꾸지는 않았다.

전체 자료는 기존과 같지만 종목을 고르는 함수는 달라졌다. 사람이 RSI<30 같은 조건을 지정하지 않아도, 학습기가 과거 결과를 보고 어느 변수의 어떤 경계를 다른 변수와 함께 사용할지 결정한다. 군집 방법은 손으로 만든 지표 조합 대신 과거 20일의 가격·거래량 경로 자체를 입력한다.

## 2. 주목표의 실제 결과

주목표는 결과를 본 뒤 승자를 고르지 않도록 **공동 목표 학습**으로 먼저 정했다. 공동 목표는 20일 순수익≥20%, 첫날 시가→종가 상승, 보유 중 최저 종가 수익≥−10%, 보유 종가 80% 이상이 진입가 위인 사건이다. 이는 사용자의 희망을 연구용으로 표현한 것이고 기존 §11 채택 기준을 바꾼 것이 아니다.

{chr(10).join(lines)}

수익과 확률을 함께 봐야 한다. 20% 적중 비율이 높아도 평균 수익이 음수이거나 중간 손실이 크면 ‘편안한 상승’을 찾았다고 말할 수 없다. 위 구간은 여러 방법을 비교한 횟수에 대한 통합 보정 전이다.

## 3. 무엇을 새로 했나

| 방법 | 데이터에서 배우는 것 |
|---|---|
| 20% 수익 학습 | 20일 후 순수익이 20%를 넘었던 사례의 공통 관계 |
| 첫날 상승 학습 | 다음 날 시가보다 종가가 높았던 사례의 관계 |
| 공동 목표 학습 | 급등·첫날 상승·작은 중간 손실·진입가 위 유지가 함께 일어난 관계 |
| 수익 크기 학습 | 확률이 아니라 20일 수익 자체 |
| 세 확률 순위 평균 | 앞선 세 분류 점수의 당일 순위를 동일 비중으로 결합. 가중치 최적화 없음 |
| 가격·거래량 군집 | 과거 20일 가격·거래량의 비슷한 모양 32개. 과거 공동 목표 비율로 평가 기간 군집을 채점 |

149개 원자료 중 첫 학습 기간에 60% 이상 관측되고 변동이 있던 **78개 연속 지표**를 사용했다. 기존 5분위 값만 학습한 것이 아니다. 2026년에만 쌓인 수급·모델 점수를 과거에 채워 넣지 않았다. 시장별로 따로 학습했고 종목 코드는 입력하지 않았다.

가격 모양은 목록일 종가 대비 과거 20일 종가의 로그 비율, 거래량 모양은 과거 20일 평균 대비 일별 로그 비율이다. 표준화와 군집 중심은 각 분기의 과거 학습 자료에서만 만들었다. 군집의 성과는 표본이 작을 때 전체 과거 비율 쪽으로 완화했다.

## 4. 미래를 섞지 않은 평가 방법

- 2025Q1부터 2026Q3까지 7개 평가 분기 × 2시장 = 14개 구간.
- 각 분기 직전에 20일 결과까지 끝난 행만 학습. **학습 목록일+20거래일 < 평가 첫 목록일**을 모든 구간에서 검사했다.
- 예: 2025Q1 평가 첫 목록일은 2025-01-02, 학습의 마지막 결과일은 2024-12-30이다.
- 4개 지도 학습 × 14구간 = 56회 학습, 경로 군집도 14회 학습했다. 트리 80회·최대 잎15·최소 잎200·학습률0.06으로 고정하고 설정 탐색을 하지 않았다.
- 자동 조기 종료의 무작위 검증 분할을 끄고, 날짜마다 학습 가중치 합계가 같도록 했다.
- 평가 분기에서는 재학습하지 않고 같은 학습기를 썼다. 다음 분기에만 과거 자료를 늘려 다시 학습했다.
- 매일 시장별 상위10을 고른다. 동점은 이미 알려진 거래대금과 종목 코드로 결정한다.

**중요한 범위:** 시간 순서를 지킨 예측이지만 2026년 자료는 이미 앞선 연구에서 본 자료다. 세상에 처음 공개되는 미래 성과나 완전히 독립된 최종 검증 표본으로 부르지 않는다. 운영 모델을 새로 등록한 것도 아니다.

## 5. 모든 방식의 결과

2025~2026 평가 기간을 합쳤다. 목록 다음 거래일 시가 매수, 20번째 거래일 종가 평가, 왕복 비용 0.5%p 차감. ‘최저 수익’은 진입가 대비 최저 종가 수익이다. 날짜별 상위10 평균을 다시 날짜마다 동일 비중으로 평균했다. **실제 자본 제한 계좌의 수익이 아니다.**

{table(overview)}

대조군의 재무 순위는 연간 ROE와 영업이익 증가의 당일 분위 순위를 평균한 값이다. 앞선 ‘두 값 모두 상위20%’ 계좌와 동일한 규칙은 아니다. 기존 v30·lv_b 등의 운영 목록과도 직접 순위 비교하지 않았다.

## 6. 연도를 나눴을 때

{table(yt)}

분기별 결과는 `summary.csv`에 전부 있다. 통합 평균만 보고 모든 시기에 통했다고 판단하지 않는다. 각 분기에서는 그때까지 완료된 과거만 사용했으므로, 성과의 변화에는 시장 변화와 학습 자료 증가가 함께 포함된다.

## 7. 학습기가 무엇을 사용했나

마지막 평가 구간용 공동 목표 학습기의 주요 변수는 아래와 같다. 비중은 학습 트리의 분할 이득 합계 비중이다. **인과 효과도, 평가 기간에서 독립 검증한 중요도도 아니다.** 서로 비슷한 지표끼리는 비중을 나눠 가질 수 있다.

{table(ig)}

`surrogate_kospi.txt`, `surrogate_kosdaq.txt`에는 과거 학습 자료에서 학습기의 예측을 흉내 낸 깊이3 설명용 나무를 남겼다. 이 나무는 원래 예측기의 일부 행동을 요약하며, 그 조건을 새로운 검증된 매수 규칙으로 제시한 것은 아니다.

군집별 과거 성과는 `clusters_*.csv`, 예측 확률 구간별 실제 빈도는 `probability_reliability.csv`에 있다. 이름이 ‘확률’인 출력도 실제 빈도와 다를 수 있어, 숫자 0.3을 곧바로 실제 성공확률 30%로 읽으면 안 된다.

분기 평균의 분류 진단:

{table(calt)}

AUC는 성공 사례의 점수가 실패 사례보다 높은 정도(0.5는 구분 못 함), Brier는 예측 확률과 실제 0/1 결과의 제곱 차이(작을수록 좋음)다. 대조 Brier는 그때의 학습 기간 성공률을 모두에게 동일하게 준 결과다. 분기 평균은 종목 수로 가중하지 않은 평균이다.

![학습 방법별 비교](../target20_discovery_20261004/learned_methods.png)

## 8. 추가 반증과 검산

- 같은 날짜 거래대금 상위10과 짝지어 수익·첫날 상승·급등·공동 목표 차이를 계산했다. 단순히 상승장이었던 효과를 성과로 부풀리지 않기 위해서다.
- 같은 날짜·같은 시총 분위의 평균 대비 수익을 별도로 계산했다.
- 가장 많이 고른 종목의 비중, 고유 종목 수, 수익 기여가 가장 큰 종목을 제외한 평균을 남겼다.
- 40일 수익도 확인했다. 최근 목록은 40일 결과가 아직 없어 표본이 줄며 `n_dates40`으로 표시했다.
- 14개 학습/평가 경계를 검사했고, 일별 최대10개 선정 {verify['selected_day_checks']:,}건을 확인했다.
- 무작위 선택 가격 경로 {verify['raw_price_checks']}개를 원시 시가·종가로 다시 계산했다. 최대 수익 차이는 {verify['max_price_error']:.3g}%p였다.
- 상세 구간은 연속20일 날짜 묶음 2,000회 재표집이다. 종목×날짜를 모두 독립 표본으로 취급하지 않았다. 장기간 반복되는 종목의 모든 상관을 완전히 제거한 것은 아니다.

## 9. 여전히 남는 데이터 한계

학습 방식이 새로워도 원자료의 한계는 사라지지 않는다. 상장폐지를 포함한 당시 전체 투자 가능 목록, 역사적 주식 수와 수정주가 일치, 모든 재무의 최초 공시 시각, 거래정지 시 실제 매도 가능성은 완전히 재구축하지 못했다. 연간 재무는 공시 접수일 이후부터 썼지만 실제 당시 12개월 PER과 같지 않다.

이 연구는 이전 분석에서 다음 날 시가 진입 가능·20일 결과 확인 조건을 통과한 행을 이어받았다. 따라서 평가 대상의 사후 선택 가능성을 제거한 완전한 실거래 시뮬레이션이 아니다. 학습의 시간 경계를 지킨 것과 원자료 전체가 당시 정보로 완벽하다는 것은 다른 문제다.

최근 수급·공매도·기존 모델 점수를 이용하는 별도 학습은 충분한 과거 기록이 없어 이번 장기 평가에 넣지 않았다. 인터넷 뉴스·공시 문장·분봉·업종 당시 구성·실적 예상치 기반 학습도 수행하지 않았다.

## 10. 코드·자료

원자료와 평가 정의: `research/target20_discovery_20261004/PLAN.md`.

재현 순서:

```powershell
python research/handoff/code_target20_conditions_build.py --output research/target20_discovery_20261004 --raw
python research/handoff/code_target20_discovery_fit.py kospi
python research/handoff/code_target20_discovery_fit.py kosdaq
python research/handoff/code_target20_discovery_evaluate.py
python research/handoff/code_target20_discovery_report.py
```

학습 구현은 [HistGradientBoosting 공식 문서](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html), 시간순 평가 원칙은 [TimeSeriesSplit 공식 문서](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)를 참고했다. 실제 분할은 종목 행 수가 아니라 거래일과 결과 완료일을 기준으로 직접 구현했다.

보존 자료: `summary.csv`, `daily_results.csv`, `selected_predictions.csv.gz`, `fold_audit_*.csv`, `learned_inputs_*.csv`, `calibration_*.csv`, `training_importance_*.csv`, `clusters_*.csv`, `probability_reliability.csv`, `verification.json`, 설명용 나무·비교 그림. 큰 원자료·학습 입력·전체 종목 예측 Parquet는 결과와 검산을 남긴 뒤 용량 규칙에 따라 정리한다. 보관 목록·해시는 `artifact_manifest.csv`에 기록한다.
'''
(ROOT/'research/handoff/REPLY_20261004_data_discovery.md').write_text(report,encoding='utf-8')
print('REPORT_READY',flush=True)
