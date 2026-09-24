"""Rebuild the research note from saved calculations; no external services."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from code_20260924_pattern_scan import block_ci, allowed

allowed()
HERE=Path(__file__).resolve().parent
OUT=HERE/'pattern_scan_20260924'
R=pd.read_csv(OUT/'cohorts.csv',dtype={'date':str,'exit_date':str})
V=pd.read_csv(OUT/'validation_selected.csv',dtype={'period':str})
P=pd.read_csv(OUT/'portfolios.csv')
M=json.loads((OUT/'metadata.json').read_text(encoding='utf-8'))
checks=json.loads((OUT/'verification.json').read_text(encoding='utf-8'))
recipes=json.loads((OUT/'recipes.json').read_text(encoding='utf-8'))
Q=R[(R.year>=2025)&(R.h==40)]
pooled=Q.groupby(['date','name']).mean(numeric_only=True)

def ci(x,block=8):
    a,l,h,n=block_ci(x,block)
    return f'{a*100:+.2f} [{l*100:+.2f}, {h*100:+.2f}]'

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])

def vals(name):return pooled.xs(name,level='name')

L=[
'# REPLY — 가격·거래량 패턴 탐색 (2026-09-24)',
'',
'사용자 직접 요청: 공시를 제외하고, 가격·거래량에서 변화의 순서와 조합을 폭넓게 탐색. 과거 주식수 근사치는 허용하되 비교 검증. 이 문서는 모델 등록·운용 채택·추천 종목 목록이 아니다.',
'',
'## 1. 직접 계산한 결론',
'',
'- 첫 탐색 42개 규칙 + 결과를 보고 추가한 원인 분리용 대조군 4개 = 총 46개. 보유기간 20·40·60일을 계산했다. 42개에는 기준선 4개가 포함된다.',
'- **2025~2026년 40일 보유, 코스피·코스닥 50:50 평균에서 지수를 넘은 규칙은 0/46개.** 다른 시장·기간·개별 사례에서 수익이 없다는 뜻은 아니다.',
'- 저변동 종목 안에서 꾸준한 상승·고점 근접으로 다시 고르면 단순 저변동보다 개선됐다. 평균 차이의 명목 95% 신뢰구간은 0 위지만, 많은 시도 및 기존 연구에서 이미 본 데이터라는 제약 때문에 확정 신호로 판단하지 않는다.',
'- 시가총액 근사치를 넣는 것도 도움이 됐다. 그러나 큰 종목만 고르는 대조군보다 평균 수익이 낮아, 개선을 새로운 패턴의 독립 효과로 설명할 근거는 부족하다.',
'- 단기 강세 전환·거래량 재증가·눌림 뒤 반등 조건은 이번 구현에서 강하지 않았다. 다른 정의까지 모두 실패했다고 일반화할 수 없다.',
'',
'## 2. 데이터와 계산 규칙',
'',
f'- daily_ohlcv: {M["first"]}~{M["last"]}, {M["dates"]}거래일, {M["tickers"]:,}종목, {M["rows"]:,}행. SQLite `mode=ro` + `PRAGMA query_only=ON`. 수집기 실행 없음.',
'- 최소 120거래일 가격 이력, 직전 60일 중 거래량 0인 날 ≤5일, 직전 20일 평균 종가×거래량 ≥5억원, 신호일 거래량·종가 양수. 당시 행의 시장 구분으로 코스피·코스닥을 별도 정렬했다.',
'- 특성은 신호일 t까지의 값만 쓴다. 각 시장 내 백분위 순위를 동일가중 평균한다. t+1 종가 진입, t+1+h 종가 평가. 신호일에 정한 종목이 다음날 거래 불가능하면 교체하지 않고 해당 몫을 현금으로 둔다.',
'- 시장별 상위20개 동일가중, 두 시장을 합칠 때 50:50. 기간별 바스켓 수익은 5거래일 간격으로 측정. 과매도 v30 또는 대형 가치 ls_t1의 기존 유니버스·점수와 섞지 않은 전체 가격자료 탐색이다.',
'- 비용은 왕복 0.35% 가정. 현재 실제 세금·수수료라는 주장이 아니다. 주식·지수 모두 배당 미포함 가격수익. 지수 비교는 시장별 KOSPI/KOSDAQ 가격지수, 보조 비교는 같은 진입 가능 모집단 동일가중(같은 비용)이다.',
'- 2024년 진입 중 40일 결과가 2024년 안에 확정된 자료만으로 8개 가족별 1위를 선택했다. 2025년과 2026년을 이후 확인 구간으로 분리했다. 2024년에는 신호 이전 이력 120일을 확보하므로 2023년 일부 가격을 쓴다.',
'- **이 기간은 기존 연구에서 이미 탐색했다.** 시간 순서 검증은 했지만 완전히 손대지 않은 OOS라고 주장하지 않는다. 후속 대조군 4개는 결과를 보고 추가했으며 가족별 후보 선정에서 제외했다.',
'- 신뢰구간: 날짜별 두 시장 평균을 먼저 구한 다음, 20·40·60일 보유에 각각 4·8·12개 신호일 블록을 사용하는 원형 블록 부트스트랩 3,000회. 아래 구간은 다중비교 미보정 95%. 76개 신호일은 보유기간이 겹치므로 독립 투자 76회가 아니다.',
'',
'## 3. 핵심 후보: 2025~2026, 40일 보유',
'',
'수익은 %, 차이는 %p. 각 셀은 평균 [95% 구간]. 모든 행 n=76개 신호일, 시장별20개씩 최대40개. 아래 3개는 연 수익률 또는 누적 수익률이 아니다.',
'',
table(['조건','비용 후 수익','지수 대비','단순 저변동 대비'],[
    [label,ci(vals(n).net),ci(vals(n).excess_index),ci(vals(n).delta_quiet)]
    for n,label in [('base_quiet','단순 저변동'),('quiet_gate_steady','저변동 안에서 꾸준함·고점 근접'),('quiet_strength_with_size','저변동·최근 상대강세·근사 시총')]
]),
'',
'정확한 정의:',
'',
'- 단순 저변동: 직전 60일 일수익 표준편차가 낮은 순.',
'- 저변동 안에서 꾸준함·고점 근접: 변동성 낮은 상위20%에서, 직전60일 상승일 비율과 현재종가/직전120일 최고종가의 시장 내 백분위를 평균해 상위20개.',
'- 저변동·상대강세·근사 시총: 낮은 60일 변동성, 직전20일 자기 시장 지수 대비 수익, 종가×주식수의 백분위를 동일가중. 세 조건을 모두 넘는 교집합 필터는 아니다.',
'',
'## 4. 근사치가 실제로 도움이 됐나',
'',
'근사치를 버리지 않고 사용했다. 같은 신호일·같은 보유기간의 짝차이를 측정했다(n=76).',
'',
table(['비교: 저변동·상대강세·시총 − 대조군','40일 수익 차이 %p [95% 구간]'],[
    [label,ci(vals('quiet_strength_with_size').net-vals(n).net)] for n,label in [
        ('quiet_strength_no_shares','시총을 뺀 저변동·상대강세'),('control_size','시총만 사용'),
        ('control_quiet_size','저변동·시총'),('control_rs20_size','상대강세·시총')]
]),
'',
'[해석] 근사 시총은 탐색에서 유용했다. 다만 큰 종목 선호만으로도 결과가 달라지므로, 근사치를 쓴 패턴이 새로운 예측 정보를 찾았다고 할 수는 없다. 과거 정확한 주식수 자료가 없는 상태에서 이 효과가 당시에도 동일했을지는 검증하지 못했다.',
'',
'## 5. 시장을 분리하면',
'',
table(['조건','시장','비용 후 수익 % [95% 구간]','지수 대비 %p [95% 구간]'],[
    [name,m,ci(g.net),ci(g.excess_index)]
    for name in ['quiet_gate_steady','quiet_strength_with_size'] for m in ['KOSPI','KOSDAQ']
    for g in [Q[(Q.name==name)&(Q.market==m)]]
]),
'',
'각 행 n=76. 코스닥 평균 초과는 양수지만 신뢰구간이 0을 포함한다. 코스피에서는 지수 대비 음수다. 시장을 합쳐 성공으로 포장하거나 코스닥만 사후 선택해 확정 전략으로 제시하지 않는다.',
'',
'## 6. 연도 및 보유기간',
'',
table(['조건','연도','n','40일 수익 % [95% 구간]','지수 대비 %p [95% 구간]'],[
    [name,year,len(g),ci(g.net),ci(g.excess_index)]
    for name in ['quiet_gate_steady','quiet_strength_with_size'] for year in [2025,2026]
    for g in [pooled.xs(name,level='name').query('year == @year')]
]),
'',
table(['조건','보유일','n','수익 % [95% 구간]','단순 저변동 대비 %p [95% 구간]'],[
    [r['name'],r['h'],r['n_anchors'],f"{r['net']*100:+.2f} [{r['net_lo']*100:+.2f}, {r['net_hi']*100:+.2f}]",
     f"{r['delta_quiet']*100:+.2f} [{r['delta_quiet_lo']*100:+.2f}, {r['delta_quiet_hi']*100:+.2f}]"]
    for r in V[(V.period=='2025_2026')&V.name.isin(['quiet_gate_steady','quiet_strength_with_size'])].to_dict('records')
]),
'',
'2026년 두 후보 모두 평균 절대수익이 음수다. 기간을 합쳤을 때의 양수만으로 항상 돈을 버는 방법이라고 해석할 수 없다.',
'',
'## 7. 실행 가능한 형태에 가까운 계좌 경로',
'',
'40일 보유 후 다음 바스켓으로 전액 교체, 보유 중 비중 재조정 없음. 시작을 0·10·20·30거래일 옮긴 4개 경로를 계산했다. 경로당 9~10회 교체 구간이며 서로 상당히 겹친다. 이것들은 독립 표본이 아니다. 아래는 관측 경로 요약으로 통계적 신뢰구간은 산출하지 않았고, 수익 불확실성은 위 블록 구간을 함께 본다.',
'',
table(['조건','4경로 연환산 평균 %','연환산 최저~최고 %','최대낙폭 평균 %'],[
    [n,f'{g.cagr.mean()*100:.2f}',f'{g.cagr.min()*100:.2f} ~ {g.cagr.max()*100:.2f}',f'{g.mdd.mean()*100:.2f}']
    for n in ['base_quiet','quiet_gate_steady','quiet_strength_with_size'] for g in [P[P.name==n]]
]),
'',
f'같은 시작·종료 구간에서 코스피·코스닥 지수를 반반 매수해 보유한 비교값의 연환산 평균은 {P.index_cagr.mean()*100:.2f}%였다. 같은 모집단 동일가중 40일 교체 계좌 평균은 {P.ew_cagr.mean()*100:.2f}%였다. 지수와 평균 종목의 차이가 크므로 비교 기준을 반드시 병기한다.',
'',
'## 8. 민감도와 재현',
'',
'- 시장별10·20·40개, 최소 거래대금20억원, 과거60일 중 일변동 절댓값35% 초과 종목 제외를 확인했다. 두 핵심 후보 모두 이 변형들에서도 두 시장 평균의 지수 초과는 음수였다. 자세한 구간은 sensitivities.csv.',
'- 비용을 왕복1%로 가정하면 완전히 채워진 바스켓의 수익은 0.65%p 더 낮아진다. 지수 미달 결론이 뒤집히지 않는다. 이는 비용 가정의 산술 민감도이며 호가·시장충격 모형은 아니다.',
'- 매도 예정일 자료가 없으면 마지막 관측 가격으로 평가했고 해당 사례를 별도 집계했다. 누락된 매도 가격에 −100% 손실을 적용한 스트레스도 계산했다. 거래정지 종목의 실제 매도 가능 시점을 완전히 재현한 것은 아니다.',
'',
table(['조건','주 계산 %','누락 출구 전손 처리 %'],[
    [n,f'{vals(n).net.mean()*100:.3f}',f'{vals(n).stress_missing_net.mean()*100:.3f}']
    for n in ['quiet_gate_steady','quiet_strength_with_size']
]),
'',
f'- 별도 구현이 신호일 이전 데이터만 다시 읽어 2025-01-03·2026-03-04 × 2개 시장의 선정 종목 20개를 전부 재현했다. 해당 40일 수익 최대 절대 오차 {max(x["abs_error"] for x in checks):.3g}. 주 스캔 함수를 불러 계산한 검사가 아니라 종목별 pandas 계산으로 재구성했다.',
'- 생산 점수·판정·게이트·docs·DB는 변경하지 않았다. 신규 파일만 research/handoff 아래에 만들었다. 전체 운영 테스트는 생산 코드 변경이 없어 실행하지 않았다.',
'',
'## 9. 범위와 아직 남은 질문',
'',
'- 상장폐지 종목이 과거 전체 모집단에서 얼마나 빠졌는지 확인하지 못했다. 현재 남아 있는/백필 가능한 종목 위주일 수 있다.',
'- 수정주가의 사후 정정, 근사 주식수 및 수정주가×원거래량의 기준 차이가 있다. 당시 저장본 전체를 복원한 연구는 아니다.',
'- 날짜별 종가 매수가 모두 체결된다는 근사다. 상한가 매수 실패·충격비용·정지 후 청산 지연은 완전하게 모델링하지 못했다.',
'- 다수 조건·보유기간·후속 비교를 시도했다. 기존 연구에서 같은 기간을 본 영향도 있으므로 신뢰구간 0 제외만으로 채택하지 않는다.',
'- 조사한 것은 평균 순위 조합과 일부 필터다. 패턴의 모든 길이·임계값·순서를 시험한 것이 아니며, 이번 실패로 일반 가격 데이터의 예측 가능성이 없다고 단정할 수 없다.',
'',
'도전 카드: **저변동 안의 꾸준함이 독립 정보인지 확인**. 다음 실험은 크기·거래대금이 비슷한 종목끼리 꾸준함 유무를 맞춰 비교하고, 이후 새 데이터에 동일한 규칙을 고정한다. 기대 이득은 큰 종목 선호 효과와 패턴 효과를 분리하는 것. 이번에는 새 모델 등록이나 배포를 하지 않았다.',
'',
'## 10. 전체 46개 결과와 레시피',
'',
'2025~2026년 40일 보유, n=76개 신호일씩. 아래 순서는 사후 성적순이며 이 순서로 후보를 선택한 것이 아니다. 비용 후 수익 %, 지수 차이 %p. 2024 선택 열은 가족별 선발 여부. 식의 항들은 시장 내 백분위 동일가중이다. exact gate는 코드 참조.',
'',
table(['이름','2024 선택','조합','수익 % [95% 구간]','지수 대비 %p [95% 구간]'],[
    [n,'예' if n in M['winners'].values() else '후속 대조' if n.startswith('control_') else '아니오',
     '+'.join(next(s['keys'] for s in recipes if s['name']==n)),ci(vals(n).net),ci(vals(n).excess_index)]
    for n in Q.groupby('name').net.mean().sort_values(ascending=False).index
]),
'',
'## 산출물',
'',
'- `code_20260924_pattern_scan.py`: 가격 패널·46개 레시피·시간 분리·비용·시장별 결과·계좌경로.',
'- `code_20260924_verify_patterns.py`: 독립 4개 바스켓 재현.',
'- `code_20260924_pattern_report.py`: 이 보고서 재생성.',
'- `pattern_scan_20260924/cohorts.csv`: 개별 신호일·시장·보유기간별 결과.',
'- `summary_all.csv`, `validation_selected.csv`, `sensitivities.csv`, `portfolios.csv`, `contributions.csv`, `recipes.json`, `metadata.json`, `verification.json`: 같은 산출물 폴더.',
]
report=HERE/'REPLY_20260924_price_volume_patterns.md'
report.write_text('\n'.join(L)+'\n',encoding='utf-8')
print(report)
