# 조기 매도 후 현금 유지·재투자 독립 검토

- 작성: 2026-11-08, Codex.
- 사용자 후속 요청: “그리고 남은 것도 봐줄래? 조기에 파는거였나”.
- 범위: v30의 고정 20·25거래일 매도를 40거래일 보유와 비교. 운영 변경·새 모델 판정 없음.
- 이 문서의 수치는 아래 독립 계산으로 직접 확인한 **실측**이다. 해석·후속 제안은 따로 표시했다.
- Claude의 당일 조기 매도 연구 문서·스크립트·출력은 열지 않았다. 앞선 Codex 답변과 운영 순수 엔진·원자료만 사용했다.

## 1. 답

**20~25일에 일찍 팔아 다음 추천 종목으로 더 빨리 갈아타면 성과가 좋아진다는 근거는 이번 표본에서 확인되지 않았다.**

- **실측:** 6/5~11/6 연구 계좌에서 40일 보유는 −3.62%, 20일 매도 후 신규 배분 확대는 −5.45%, 25일 매도 후 확대는 −5.67%였다.
- **실측:** 매도만 앞당기고 매일 신규 배분을 종전 1/40으로 유지하면, 20일 계좌는 −2.58%, 최대낙폭 −5.83%로 완화됐다. 그러나 평균 주식 비중도 73.13%에서 41.19%로 줄었다.
- **해석:** 현금 비중 증가와 조기 매도 시점의 효과가 함께 들어 있다. 이를 “더 좋은 매도 시점 발견”으로 해석할 수 없다. 40일을 유지하며 신규 배분만 줄인 비교군도 비슷한 낙폭 완화를 보였다.
- **실측:** 시작을 8/10으로 바꾸면 적극 재투자의 수익 차이는 소폭 양수로 바뀌었다. 일별 차이의 신뢰구간은 0을 포함한다.
- **결론:** 보유 기간을 바로 바꿀 정도의 일관된 우위는 없다. 그렇다고 40일이 항상 최적이라는 검증도 아니다.

앞서 사용자가 우선순위로 고른 **“매수 후 일주일 안에 오르기 시작할 종목 찾기”**와 별개의 질문이다. 조기 상승 검토는 `REPLY_20261108_early_rise_review.md`에 남겼다.

## 2. 비교 조건

### 자료·목록

- `history.db`, `../dh-q7m3k-data/ohlcv.db`를 모두 `mode=ro` + `PRAGMA query_only=ON`으로 열었다.
- 시세는 `daily_ohlcv` 본표에서 2026-05-01~11-06을 조회: 실제 5/4~11/6, 332,312행, 2,664종목. 보충표는 합치지 않았다.
- 동결된 `v3_scores.model_id='v30'`에서 등록일 20260606 이후 기록을 사용했다. 부분 실행 20260608과 이중 실행 20260703은 제외했다.
- 비거래일 run은 직전 본표 거래일에 연결하되 5달력일 초과는 제외했다. 같은 거래일이면 그날 run 우선, 없으면 가장 이른 run을 선택했다.
- 총 98개 추천 기준일, 1,960개 종목-추천일. 마지막 11/6 추천은 다음 거래일 가격이 없어 아직 진입하지 않는다.
- 주 비교는 **성적표 방식 시장별 상위 10**, 점수 내림차순·동점 종목코드 오름차순. 같은 목록으로 모든 보유 기간을 비교했다.
- 화면 권고10의 재무 위험 조건을 적용한 목록도 감도로 계산했다. 당시 `stage3_final`의 주의·위험 및 이중적자·밸류트랩의심을 제외한 뒤 시장별 상위 10을 다시 골랐다. 동점은 종목코드 순이다.
- **운영 모의 계좌 잔액을 그대로 재현한 것이 아니다.** 운영 계좌의 희석 배지 제외·보충 시세·시작일을 모두 복제하지 않았다. 이 연구의 주 목록과 화면 감도 목록을 구분해서 봐야 한다.

### 돈의 흐름

- 6/5에 초기 자금 1, 전액 현금. 첫 진입 6/8, 마지막 평가 11/6.
- 날짜별 자산 평가 105개, 초기 상태를 제외한 일수익률 104개.
- 추천 다음 거래일 **종가**에 진입, 진입일 + H거래일 종가에 매도한다. 달력일이 아니다.
- 매일 신규 예산 = 전날 총자산 ÷ 배분 분모. 실제 현금 한도 내에서 해당일 목록에 동일 금액 배분.
- **20일 / 1/40, 25일 / 1/40:** 매도일만 앞당긴다. 늘어난 현금에서 종전 속도로 새 추천에 계속 배분한다. 매도금을 영구히 따로 보관하는 규칙은 아니다.
- **20일 / 1/20, 25일 / 1/25:** 매도일과 신규 배분 규모를 함께 바꿔 재투자를 늘린다. 전액을 즉시 한 번에 재투자하는 규칙은 아니다.
- 기본 비용 왕복 0.5%를 매수·매도 각각 절반 차감한다. 이는 이전 매매별 표의 “총수익에서 0.5%p 차감”과 소폭 다르다.
- 진입 종가 없음·거래정지·등락률 29% 이상이면 그 종목 몫은 현금. 다음 순위로 교체하거나 나머지 종목에 재배분하지 않는다.
- 주 비교에서 진입 예정 1,940건 중 17건을 건너뛰어 실제 1,923건 진입. 40일 계좌는 종료 시점 1,164건 청산·759건 보유, 20일은 1,544건 청산·379건 보유, 25일은 1,444건 청산·479건 보유.
- 현금 이자 0, 소수점 주식 허용, 매도대금 당일 사용이 기본. T+2 대기는 별도 감도.
- 만기 시 가격이 없으면 마지막 유효 종가로 평가·청산하는 기존 엔진 가정을 따른다. 주 비교에서 만기 종가 누락 청산은 0건이었다. 이것이 실제 매도 체결 가능성까지 보장하지는 않는다.
- 마지막 날 남은 주식은 시가 평가하고 강제 청산하지 않는다. 미청산분의 미래 매도 비용은 포함하지 않는다.

## 3. 주 비교 실측

n = 104 일수익률, 동일 97개 진입 기준일의 목록. 비용 차감 후 초기 자금 대비 총수익이다. 연환산하지 않았다.

| 보유 기간 / 매일 신규 배분 | 총수익 | 최대낙폭 | 평균 주식 비중 | 실제 차감 비용 / 초기 자금 |
|---|---:|---:|---:|---:|
| 40일 / 1⁄40 | -3.62% | -11.65% | 73.13% | 0.99% |
| 20일 / 1⁄40 | -2.58% | -5.83% | 41.19% | 1.09% |
| 25일 / 1⁄40 | -3.42% | -7.40% | 50.14% | 1.06% |
| 20일 / 1⁄20 | -5.45% | -11.47% | 82.39% | 2.18% |
| 25일 / 1⁄25 | -5.67% | -11.70% | 80.22% | 1.70% |

총수익·최대낙폭은 한 개의 실제 역사 경로 값이다. 아래 신뢰구간은 **각 대안의 일수익률 − 40일/1⁄40 일수익률의 평균**에 대한 값이며, 총수익 차이의 신뢰구간으로 읽으면 안 된다. 단위 1bp = 0.01%p.

| 대안 | 평균 일수익 차이 bp [95% 구간], 40일 블록 | 20일 블록 감도 |
|---|---:|---:|
| 20일 / 1⁄40 | 0.53 [-11.47, 12.19] | 0.53 [-11.76, 12.49] |
| 25일 / 1⁄40 | -0.18 [-9.49, 8.99] | -0.18 [-9.47, 9.03] |
| 20일 / 1⁄20 | -1.47 [-4.71, 1.12] | -1.47 [-5.23, 2.06] |
| 25일 / 1⁄25 | -1.77 [-3.65, 0.02] | -1.77 [-4.23, 0.75] |

- 같은 날짜끼리 차이를 낸 후, 원형 연속 블록 재표집 4,000회, seed 20261108, 백분위 95% 구간.
- 104일에 40일 블록이므로 독립적인 구간이 충분하지 않다. 이 구간은 불확실성 표시이며 §11 판정이나 새 운용 규칙의 채택 근거가 아니다.
- 총수익과 평균 일수익의 순서가 일부 다른 것은 복리 경로와 변동성이 다르기 때문이다. 예를 들어 25일/1⁄40의 총수익 차이는 양수지만 평균 일수익 차이는 소폭 음수다.
- 재투자를 늘리면 신규 매수 누계가 초기 자금의 2.46배에서 20일 4.84배·25일 3.88배로 커졌다. 차감 비용 누계도 약 0.99%에서 2.18%·1.70%로 늘었다. 비용만으로 성과 차이 전부를 설명했다는 뜻은 아니다.

### 현금 증가만으로도 낙폭이 줄어드는가

| 비교군 | 총수익 | 최대낙폭 | 평균 주식 비중 |
|---|---:|---:|---:|
| 40일 보유, 매일 1/80 배분 | −1.64% | −5.91% | 36.74% |
| 40일 보유, 매일 1/64 배분 | −2.10% | −7.36% | 45.87% |

40일/1⁄40 대비 평균 일수익 차이의 40일 블록 95% 구간은 각각 +1.35bp [−10.52, +13.00], +1.01bp [−7.91, +9.77]로 둘 다 0을 포함한다.

**해석:** 더 일찍 팔지 않고 보유 비중만 줄여도 비슷한 낙폭 완화를 관찰했다. 다만 이 두 계좌와 조기 매도 계좌는 평균 비중·보유 종목의 나이가 정확히 같지 않다. 조기 매도 효과가 전혀 없다는 인과 증명은 아니다.

## 4. 조건을 바꿔도 같은가

아래는 각 조건에서 다시 현금부터 시작하거나 비용·목록·결제만 바꾼 총수익이다. 8/10 시작은 60개 평가일·59개 일수익률, 나머지는 105개 평가일·104개 일수익률이다.

| 조건 | 40일/1⁄40 | 20일/1⁄40 | 25일/1⁄40 | 20일/1⁄20 | 25일/1⁄25 |
|---|---:|---:|---:|---:|---:|
| 화면 권고10 필터 | -2.83% | -2.27% | -3.13% | -4.85% | -5.22% |
| 8/10 현금부터 시작 | -9.71% | -4.59% | -5.75% | -9.14% | -9.17% |
| 매도대금 T+2 대기 | -3.62% | -2.58% | -3.42% | -5.02% | -5.43% |
| 왕복비용 0.35% | -3.34% | -2.26% | -3.12% | -4.84% | -5.20% |
| 왕복비용 1.00% | -4.55% | -3.62% | -4.43% | -7.47% | -7.25% |

- **화면 목록 감도:** 적극 재투자 두 계좌가 모두 40일 기준보다 낮았다. 20일/1⁄20의 평균 일수익 차이는 −1.64bp, 40일 블록 구간 [−4.76,+0.94]. 25일/1⁄25는 −2.09bp [−3.89,−0.27]이나 20일 블록에서는 [−4.58,+0.56]으로 0을 포함한다. 한 구간만 골라 열등 판정하지 않는다.
- **8/10 시작 감도:** 적극 재투자 차이가 소폭 양수로 바뀐다. 20일/1⁄20 +1.13bp [−0.49,+2.74], 25일/1⁄25 +1.07bp [−0.35,+2.50]. 두 구간 모두 0을 포함한다. 현금 비중이 크게 늘어나는 대안도 블록 길이 20일에서는 0을 포함해, 짧은 구간의 확정적 우위로 읽기 어렵다.
- **T+2 감도:** 1/40 배분 계좌는 현금이 충분해 수익 경로가 같았다. 적극 재투자는 결제 대기로 투입이 줄면서 손실도 다소 줄었다. 여전히 기준보다 낮고 일평균 차이 구간은 각각 [−4.57,+1.78]bp, [−3.62,+0.56]bp다.
- **왕복 0.35%:** 적극 재투자 평균 일수익 차이 구간은 [−4.37,+1.48]bp, [−3.45,+0.22]bp로 0을 포함한다.
- **왕복 1.00%:** 적극 재투자 평균 일수익 차이 구간은 [−5.83,−0.01]bp, [−4.36,−0.63]bp이나 20일 블록에서는 각각 [−6.40,+0.87], [−4.96,+0.06]으로 0을 포함한다. 비용 증가가 짧은 교체 주기에 더 불리한 점은 관찰되지만 공식 판정은 하지 않는다.

## 5. 이전 매매별 계산과의 관계·한계

앞선 답변의 공통 59개 추천일·1,169개 종목-추천일 표에서는 비용 차감 후 매매별 평균이 20일 +1.57%, 25일 +1.78%, 40일 +3.08%였다. 그때 계산한 40일 대비 차이는 20일 −1.50%p [−5.17,+2.25], 25일 −1.30%p [−4.51,+1.96]였다. 방법과 누락 처리는 앞선 답변에 있다.

**그 양수 수익과 이번 계좌의 음수 수익은 모순이 아니다.** 앞선 표는 모든 기간의 만기가 지난 6/5~9/4 추천만 공통으로 비교했다. 이번 계좌는 더 최근 추천에도 실제 자금을 배분하고 11/6의 미청산 손익까지 평가한다. 비교 대상·시점·자금 가중치가 다르다.

이번에 확인한 것은 **고정 20·25일 매도**뿐이다. “5일 안에 상승하지 않으면 매도”, “수익이 날 때만 매도”, “고점에서 일정 폭 밀리면 매도”는 시험하지 않았다. 그런 조건에는 신호를 확인한 시점 이후의 체결 가격을 쓰는 별도 계산이 필요하다. 사후에 잘 오른 종목만 골라 조기 매도의 근거로 삼지 않았다.

추가 한계:

- 최근 약 5개월, 동일 종목 반복 진입·겹치는 보유 구간이다. 종목-추천일 수를 독립 표본 수로 취급하지 않았다.
- 40일/1⁄40도 초기 40일 동안 서서히 투자된다. 20일/1⁄20은 더 빨리 투자되고 평균 보유 비중도 더 높아, 두 적극 투자 계좌의 노출이 완전히 같지는 않다.
- 현금 이자·정수 주수·호가 간격·거래대금 한도·실제 주문 체결은 모델링하지 않았다. 비용은 정해진 비율 가정이다.
- 미래 결과를 보고 20일·25일 중 좋은 기간을 채택하거나, 8/10 시작 구간만 선택해서 결론 내리지 않는다.
- 이번 비교는 10년 v30 재현이 아니다. 과거 다른 과매도 대리 목록의 결과를 v30의 10년 성과로 대신하지 않았다.

## 6. 제안·질문

**제안:** 현재 결과만으로 운영 보유 기간을 줄이지 않는다. 사용자가 우선순위로 고른 “매수 후 5거래일 안에 상승할 후보 찾기”를 다음 연구의 목표로 두는 편이 요청에 더 가깝다. 이것은 새 조건의 성과를 확인했다는 뜻이 아니다.

추가 비교가 필요하다면, 먼저 “기다림을 줄이는 편의”와 “같은 자본의 수익 증가” 중 목표를 고정해야 한다. 다음 한 건은 사전 고정한 단일 조기 매도 규칙에 대해 **동일한 보유 비중의 40일 비교군·실제 재투자·비용·시간 순서가 맞는 체결**을 함께 검증하는 방식이 적절하다. 이 문서는 그 규칙을 등록하거나 실행하지 않았다. 진행을 막는 질문은 없다.

## 7. 검증·재현·변경 범위

- 계산은 새로 작성한 메모리상의 Python 코드로 수행했다. 아래 코드가 그 재현본이다. 별도 .py·중간 DB·CSV를 만들지 않았다.
- 계산 후 기존 순수 `paper_engine.simulate`와 7개 운용 × 6개 조건의 모든 일별 자산을 대조했다. 최대 절대 차이 2.89×10⁻¹⁵. 이것은 엔진 규칙의 계산 일치를 확인한 것이며 현실 체결 가정의 검증은 아니다.
- 입력 DB의 크기·수정시각은 전후 같았다.
  - history.db: 503,844,864 bytes, mtime_ns 1793965716376118300.
  - ohlcv.db: 438,329,344 bytes, mtime_ns 1793966684871711000.
- 확인 당시 HEAD: `2538a898a52aa088d833a749d920f58bd9bfdfe1`.
- `paper_engine.py` SHA256: `D29BA36E1BCF9B40992D460A603E0776E20A2E021F1C1D94CAB0DC8071C79F91`.
- 이번 작업의 저장 산출물은 이 REPLY 한 파일이다. 운영 코드·docs·DB·연구 지도·worklog를 수정하지 않았다. 배치·수집·네트워크·커밋·푸시 없음.
- 아래 Python을 저장소 루트에서 `python -B -`의 표준입력으로 실행하면 같은 표를 출력한다. DB가 이후 적재되거나 과거 run이 바뀌면 게이트 모집단이 달라질 수 있으므로 위 입력 상태를 함께 비교해야 한다. 평일 배치 시간에는 재현하지 않는다.

### 재현 코드

```python
import sys,json,sqlite3,hashlib
from pathlib import Path
import numpy as np,pandas as pd
sys.stdout.reconfigure(encoding='utf-8')
root=Path.cwd()
def ro(p):
 c=sqlite3.connect(Path(p).resolve().as_uri()+'?mode=ro',uri=True);c.execute('PRAGMA query_only=ON');return c

h=ro('history.db');o=ro('../dh-q7m3k-data/ohlcv.db')
P=pd.read_sql_query("SELECT ticker,date,close,market,is_suspended,change_pct FROM daily_ohlcv WHERE date>='20260501' AND date<='20261106' ORDER BY date,ticker",o)
print('PRICE',len(P),P.ticker.nunique(),P.date.min(),P.date.max())
C=P.pivot(index='date',columns='ticker',values='close').astype(float);C=C.where(C>0)
dates=list(C.index);di={d:i for i,d in enumerate(dates)}
mk=P.drop_duplicates('ticker',keep='last').set_index('ticker').market.str.lower()
R=C.pct_change(fill_method=None)
S=pd.read_sql_query("SELECT run_id,market,ticker,final_score_v3 AS score,frozen_at FROM v3_scores WHERE model_id='v30' ORDER BY run_id,market,ticker",h)
S.ticker=S.ticker.str.zfill(6)
cnt=pd.read_sql_query("SELECT run_id,COUNT(*) n FROM stage1_oversold GROUP BY run_id",h)
partial=set(cnt.loc[cnt.n<cnt.n.median()*.3,'run_id'])
double=set()
for tab in ['v3_scores','lowvol_scores','wu_scores','large_scores']:
 if not h.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(tab,)).fetchone():continue
 cols=[x[1] for x in h.execute('PRAGMA table_info('+tab+')')]
 if 'frozen_at' not in cols or 'model_id' not in cols:continue
 q=pd.read_sql_query('SELECT run_id,model_id,MIN(frozen_at) lo,MAX(frozen_at) hi FROM '+tab+' GROUP BY run_id,model_id',h)
 gap=(pd.to_datetime(q.hi,utc=True)-pd.to_datetime(q.lo,utc=True)).dt.total_seconds()
 double.update(q.loc[gap>=3600,'run_id'])
excl=partial|double
cand={}
for rid in sorted(S.run_id.unique()):
 if rid in excl or rid<'20260606':continue
 t=int(np.searchsorted(dates,rid,side='right')-1)
 if t<0 or (pd.Timestamp(rid)-pd.Timestamp(dates[t])).days>5:continue
 cand.setdefault(t,[]).append(rid)
keep={t:next((r for r in rs if r==dates[t]),min(rs)) for t,rs in cand.items()}
S=S[S.run_id.isin(keep.values())].copy()

import paper_engine
meta_before={str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in [Path('history.db'),Path('../dh-q7m3k-data/ohlcv.db')]}
rank=S.dropna(subset=['score']).sort_values(['run_id','market','score','ticker'],ascending=[True,True,False,True])
raw={dates[t]:list(rank[rank.run_id==rid].groupby('market',sort=True).head(10).ticker) for t,rid in keep.items()}
F=pd.read_sql_query("SELECT run_id,ticker,risk_level,ocf_pattern FROM stage3_final",h)
F.ticker=F.ticker.str.zfill(6)
assert not F.duplicated(['run_id','ticker']).any()
Q=rank.merge(F,on=['run_id','ticker'],how='left',validate='many_to_one')
Q=Q[~Q.risk_level.isin(['\uc8fc\uc758','\uc704\ud5d8'])&~Q.ocf_pattern.isin(['\uc774\uc911\uc801\uc790','\ubc38\ub958\ud2b8\ub7a9\uc758\uc2ec'])]
ui={dates[t]:list(Q[Q.run_id==rid].groupby('market',sort=True).head(10).ticker) for t,rid in keep.items()}
T=(~((P.is_suspended.fillna(0)>0)|(P.change_pct>=.29)))
T=pd.DataFrame({'date':P.date,'ticker':P.ticker,'ok':T}).pivot(index='date',columns='ticker',values='ok').reindex(index=C.index,columns=C.columns).fillna(True).astype(bool)
A=C.to_numpy(); FF=C.ffill().to_numpy(); TT=T.to_numpy(); cols={x:i for i,x in enumerate(C.columns)}
def calc(picks,start,hold,slots,cost=.005,settle=0,end=None):
 first=di[start]; last=len(dates)-1 if end is None else di[end]
 schedule={di[d]+1:ls for d,ls in picks.items() if di[d]>=first and di[d]+1<=last}
 cash=1.; previous=1.; positions=[]; pending={}; rows=[]; skipped=0; stale=0; ledger=[]
 for i in range(first,last+1):
  sale=buy=fees=0.; out=[]; nout=nin=0
  for j,q,e,spent in positions:
   if i==e+hold:
    gross=q*FF[i,j]; fee=gross*cost/2
    pending[i+settle]=pending.get(i+settle,0.)+gross-fee
    sale+=gross; fees+=fee; nout+=1; stale+=int(not np.isfinite(A[i,j]))
    ledger.append((spent,gross-fee,e,i))
   else:out.append((j,q,e,spent))
  positions=out
  cash+=pending.pop(i,0.)
  ls=schedule.get(i,[])
  if ls:
   budget=max(0.,min(cash,previous/slots)); per=budget/len(ls)
   for ticker in ls:
    j=cols.get(ticker)
    if j is None or not np.isfinite(A[i,j]) or not TT[i,j]:
     skipped+=1;continue
    if per<=0:continue
    q=per*(1-cost/2)/A[i,j]; positions.append((j,q,i,per))
    buy+=per;fees+=per*cost/2;cash-=per;nin+=1
  value=sum(q*FF[i,j] for j,q,e,spent in positions); unsettled=sum(pending.values())
  nav=cash+value+unsettled
  assert cash>=-1e-12 and np.isfinite(nav) and nav>0
  rows.append(dict(date=dates[i],nav=nav,cash=cash,invested=value,pending=unsettled,ret=nav/previous-1,buy=buy,sale=sale,fees=fees,entries=nin,exits=nout,n_pos=len(positions)))
  previous=nav
 df=pd.DataFrame(rows)
 return df,dict(skipped=skipped,stale_exits=stale,closed=len(ledger),open=len(positions))
def ci_diff(a,b,block=40):
 x=(a.ret-b.ret).iloc[1:].to_numpy()
 rg=np.random.default_rng(20261108); n=len(x)
 ix=(rg.integers(n,size=(4000,int(np.ceil(n/block))))[:,:,None]+np.arange(block))%n
 samples=x[ix.reshape(4000,-1)[:,:n]].mean(axis=1)*10000
 return [float(x.mean()*10000),*map(float,np.quantile(samples,[.025,.975]))]
def summary(df,info,ref):
 v=df.nav.to_numpy(); peak=np.maximum.accumulate(np.r_[1.,v])[1:]
 return dict(days=len(df),first=df.date.iloc[0],last=df.date.iloc[-1],ret=float((v[-1]-1)*100),mdd=float((v/peak-1).min()*100),
  exposure=float((df.invested/df.nav).mean()*100),cash=float((df.cash/df.nav).mean()*100),
  buy=float(df.buy.sum()),sell=float(df.sale.sum()),fees=float(df.fees.sum()*100),
  daily_diff_bp_ci40=ci_diff(df,ref),daily_diff_bp_ci20=ci_diff(df,ref,20),**info)
configs=[(40,40),(20,40),(25,40),(20,20),(25,25),(40,80),(40,64)]
print('SELECTION',json.dumps(dict(anchors=len(raw),selected=sum(map(len,raw.values())),ui_selected=sum(map(len,ui.values())),first=min(raw),last=max(raw),partial=sorted(partial),double=sorted(double)),ensure_ascii=False))
result={}
for label,picks,start,cost,settle in [
 ('raw_main',raw,min(raw),.005,0),('ui_main',ui,min(ui),.005,0),
 ('raw_aug10',raw,'20260810',.005,0),('raw_t2',raw,min(raw),.005,2),
 ('raw_cost035',raw,min(raw),.0035,0),('raw_cost1',raw,min(raw),.01,0)]:
 curves={}; results={}
 for hold,slots in configs:
  df,info=calc(picks,start,hold,slots,cost,settle)
  curves[(hold,slots)]=df
  results[str((hold,slots))]=summary(df,info,curves[(40,40)])
 # independent simulator vs operational pure engine, every config and every daily nav
 maxdiff=0.
 for hold,slots in configs:
  subdates=[d for d in dates if d>=start]
  oracle,_=paper_engine.simulate(subdates,C,{d:ls for d,ls in picks.items() if d>=start},hold=hold,slots=slots,cost=cost,settle_days=settle,tradable=T)
  diff=np.max(np.abs(oracle.nav.to_numpy()-curves[(hold,slots)].nav.to_numpy()))
  maxdiff=max(maxdiff,float(diff))
 assert maxdiff<1e-10
 result[label]=results
 print('RESULT',label,json.dumps({k:{a:v[a] for a in ['ret','mdd','exposure','fees','daily_diff_bp_ci40','daily_diff_bp_ci20']} for k,v in results.items()}))
 print('VALIDATION',label,'max_nav_diff',maxdiff)
# completed common cohort actual conditional entry restrictions, same sample for all horizons
coh=[]
for d,ls in raw.items():
 e=di[d]+1
 if e+40>=len(dates):continue
 for tk in ls:
  j=cols.get(tk)
  if j is None or not np.isfinite(A[e,j]) or not TT[e,j]:continue
  if not all(np.isfinite(A[e+h,j]) for h in [20,25,40]):continue
  coh.append([d,tk,*[(A[e+h,j]/A[e,j]*(1-.005/2)**2-1)*100 for h in [20,25,40]]])
coh=pd.DataFrame(coh,columns=['date','ticker','h20','h25','h40'])
print('COMMON',len(coh),coh.date.nunique(),coh.groupby('date')[['h20','h25','h40']].mean().mean().to_dict())
print('UNCHANGED',meta_before=={str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in [Path('history.db'),Path('../dh-q7m3k-data/ohlcv.db')]})
h.close();o.close()
```

