"""Render the requested reply from completed, saved calculations only."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from code_20261110_first_week_compute import OUT, ROOT, guard, metadata

guard()
HERE = OUT.parent
a = pd.read_csv(OUT/'A_comparison.csv')
b = pd.read_csv(OUT/'B_summary.csv')
d = pd.read_csv(OUT/'D_actual_frozen_summary.csv')
rebuilt = pd.read_csv(OUT/'D_actual_summary.csv')
dp = pd.read_csv(OUT/'D_proxy_summary.csv')
bd = pd.read_csv(OUT/'B_days.csv',dtype={'date':str})
dd = pd.read_csv(OUT/'D_proxy_days.csv',dtype={'date':str})
meta = json.loads((OUT/'D_actual_frozen_meta.json').read_text(encoding='utf-8'))
audit = json.loads((OUT/'sample_audit_meta.json').read_text(encoding='utf-8'))
lm = json.loads((OUT/'long_meta.json').read_text(encoding='utf-8'))


def number(x, digits=3, sign=True):
    if pd.isna(x): return '—'
    return f'{x:+.{digits}f}' if sign else f'{x:.{digits}f}'


def ci(row, mean='mean', lo='lo', hi='hi', digits=3, sign=True):
    if pd.isna(row.get(mean,np.nan)): return '—'
    return f'{number(row[mean],digits,sign)} [{number(row[lo],digits,sign)}, {number(row[hi],digits,sign)}]'


def rng(row, lo='bonf_lo',hi='bonf_hi',digits=3):
    return f'[{number(row[lo],digits)}, {number(row[hi],digits)}]'


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+
                     ['| '+' | '.join(str(v) for v in row)+' |' for row in rows])


def yn(x): return '통과' if bool(x) else '미통과'


lines=['''# REPLY — 첫 주 우상향 2차 A·B·D 독립 계산 (2026-11-10)

**실측 결론:** A의 26개 모델은 기존 표와 표본 수·평균값이 일치한다. B의 고정 8변수는 **후보 없음**이다. D는 **사후 목표**로, 경로5와 관련된 통계적 신호는 있으나 곧바로 첫 주 고르기 후보나 운영 변경 근거가 되지 않는다. 끝의 두 번째 의견은 **(가), 사전에 남겨 둔 C 사건 연구만 아직 열림**이다.

## 0. 수행 범위와 재현 한계

- 요청서의 A·B·D만 계산했다. 기존 코드·docs·DB·지식 문서는 수정하지 않았고 배치·수집기·네트워크는 실행하지 않았다. DB는 모두 `file:...?mode=ro`와 `query_only=ON`으로 읽었다. 새 코드·작은 산출물·이 답변만 `research/handoff/`에 두었다.
- 계산 시작은 11/10 19:28 KST, 모두 금지 시간 전이다. 연구 코드는 평일 **20:09~22:31 자동 종료** 장치를 둬 20:10~22:30을 피한다. 실행은 `-B`로 했으며 기존 모듈의 캐시 파일을 만들지 않았다.
- **눈가림 절차 한계:** 요청서를 한 번에 읽으며 §2의 A 숫자가 계산 전에 노출됐다. 따라서 A를 완전한 눈가림 재현이라고 부르지 않는다. 기존 A 계산 코드는 독립 계산을 저장한 뒤에만 읽었다. A의 결과를 맞추기 위한 표본·변수·기준 조정은 하지 않았다. B·D의 상대방 결과는 제공되지 않았고 열지 않았다.
- B는 `research/lib/tenyr.py`의 가격판·정리 유니버스·상수를 **import**했다. D는 요청대로 1차의 변수 구성 코드를 읽어 재사용하고 path5와 통계 집계를 별도 코드로 작성했다. 운영 모듈 전체 실행 대신 리더보드의 지정 함수 네 개만 구문 트리에서 추출했다.
- **판정 기준 불변:** 상승 비율 개선 하단 > +5%p, n≥40 또는 장기 대리 신호일≥200, 앞/뒤 부호, 다중비교 보정, 40일 대가 확인. A의 iid 구간은 요청된 관측표이며 모델 채택 검정이 아니다. D의 ‘통계 통과’는 1차의 경로 목표 검정 통과라는 뜻이며 §1의 up5 후보와 구분한다.

## A. 전 모델 첫 주 — Codex 값 | 기존 값 | 차이·원인

가격 범위는 2023-06-26~2026-11-09. 등록일은 `checkup.REG_DATE`, 부분 실행 20260608·이중 실행 20260703 제외, 등록일 필터 후 앵커 중복 제거. t+1 종가 진입 후 t+6 종가로 up5를 잰다. 시장명을 대문자로 맞추고 시장별 점수 상위 10을 뽑아 두 시장을 같은 비중으로 평균했다. 유효 가격·점수 그룹은 MIN_GROUP=8, 보유 중 하루 절대 등락 >0.32 제외. 점수 동률은 리더보드의 점수 단독 정렬을 그대로 따른다.

상승은 **비용 전** 수익>0, 경로5는 t+2~t+6 다섯 종가 모두 진입가 이상이다. 초과는 상위10 평균 5일 수익−같은 시장 점수 있는 유니버스의 중앙값이며 비용 차감 전이다. 아래 up5·기준율·path5는 %, 차·초과는 %p. 대괄호는 95% iid CI, 앵커 2,000회·seed 7. †는 은퇴 모델로, 기간이 다른 모델끼리 이 표로 우열을 정하지 않는다.
''']

arows=[]
for _,r in a.sort_values(['retired','track_ours','model']).iterrows():
    arows.append([r['model']+('†' if r.retired else ''),int(r.n_ours),
                  ci(r,'up5_ours','up5_lo','up5_hi',2,False),
                  ci(r,'baseline','baseline_lo','baseline_hi',2,False),
                  ci(r,'diff','diff_lo','diff_hi',2),
                  ci(r,'excess','excess_lo','excess_hi',2),
                  ci(r,'path5','path5_lo','path5_hi',2,False),
                  ci(r,'차','차하한','차상한',2),'평균·n 동일'])
lines.append(table(['모델','n','Codex up5 [CI]','기준율 [CI]','차 [CI]','초과 [CI]','path5 [CI]','기존 차 [CI]','대조'],arows))
lines.append('''
**대조 실측:** 26개 전부 n·up5·기준율·차·초과·path5 평균의 최대 오차는 2.85×10⁻¹⁴%p 이하. CI 차이는 게이트·앵커·시장·점프컷 때문이 아니다. Codex는 통계별로 seed 7을 초기화했고 기존 코드는 모델 안에서 up5→차→초과→path5 순서로 같은 난수기를 계속 썼다. 독립 일별 결과에 그 순서를 적용하면 **CI 최대 오차도 1.43×10⁻¹⁴%p 이하**다. 위 표에는 독립 계산의 원래 CI를 남겼다. `A_rng_audit.csv`에 순서를 맞춘 결과가 있다.

동률 처리 점검: 종목코드로 동률을 깨는 대안을 쓰면 54개 모델×날짜×시장 그룹의 선정 종목이 달라진다. 본표는 그 대안으로 바꾸지 않았다. 또 리더보드의 점수/수익 고유값 3개 조건을 Codex는 유지했고 기존 A 코드는 생략했지만 이 자료에서는 결과 차이가 없었다.

**해석:** 현재 적재 중인 모델의 평균 up5 최고는 lv_b 47.42%이고, lv_e의 차는 +5.49%p지만 하단 +0.99%p·n=38이다. A에서 §1의 개선 하단 >+5%p를 넘는 모델은 없다. 은퇴 모델 일부가 50%를 넘는다는 사실은 별개 기간의 기준율도 높았다는 관측이지 부활 근거가 아니다. 절대 상승 비율이 50% 미만이라는 이유만으로 예측 불가능이라고 결론 내리지 않는다.

## B. 과매도 조건 없는 8변수 — 후보 없음

정리 유니버스 2,763종목, 원 시세 2015-01-02~2026-10-21. 신호일 **545일(2015-07-13~2026-08-13)**, 앞반 269일(<2021-01-01)·뒤반 276일. tenyr의 시작 인덱스 130·5거래일 격자·유효 종목≥300·40일 가격 가용 조건을 유지했다. 거래량 0·1,000원 미만·금융/스팩/리츠 제외와 상폐 마지막 가격 유지도 같은 틀이다.

정의: nh252=종가/252일 최고 **종가**−1(운영 wu 정의대로 min_periods=120), r20·r5=종가 수익, up_streak=**종가>시가인 양봉** 연속 일수, vol_ratio=당일 거래량/당일 포함 20일 평균, brk20=당일 종가≥당일 포함 20일 최고 종가, sma20_above=종가>20일 평균, hl_range=(고가−저가)/종가. 양봉을 전일 대비 상승으로 바꾼 변형이나 다른 돌파 문턱은 시험하지 않았다.

T1·T4=각각 5일·40일 종목 수익−동일 날짜 유효 전 종목 동일가중 수익. 왕복 비용 0.35%를 종목·기준에 똑같이 차감하므로 초과의 상수 비용은 상쇄된다. up5는 A와 같은 비용 전 0/1이며 비용 뒤 수익률과 혼동하지 않는다. 날짜별 스피어만→날짜 같은 비중 평균, 월 전체 재표집 4,000회 seed 7. 표본 2,000회가 기본인 공통 틀에서 보정 꼬리를 위해 1차 장기 스캔과 같은 4,000회를 썼다. 양측 α=0.05/16, 보정 CI=99.6875%.

### B-1. 두 주목표의 IC·보정·앞/뒤
''')
rows=[]
for v in lm['B_vars']:
    r=b[(b['var']==v)&(b.target=='T1')].iloc[0]
    u=b[(b['var']==v)&(b.target=='up5')].iloc[0]
    rows.append([v,int(r.n),ci(r),rng(r)+' '+yn(r.bonf_pass),
                 number(r.front)+' / '+number(r.back),ci(u),rng(u)+' '+yn(u.bonf_pass),
                 number(u.front)+' / '+number(u.back)])
lines.append(table(['변수','n','T1 IC [95%]','T1 보정 CI·통과','T1 앞/뒤','up5 IC [95%]','up5 보정 CI·통과','up5 앞/뒤'],rows))
lines.append('''
### B-2. 상위20%−하위20% 상승 비율 차이와 40일 대가

차이는 높은 변수값 집단−낮은 집단이다. 음수는 강한 쪽을 사는 방향에 불리하다. 동률을 임의 종목코드로 쪼개지 않고 20/80분위 경계의 동률을 모두 포함한다. 따라서 이산 변수는 정확히 20%가 아니며, 두 분위 경계가 같아 집단이 겹치는 날은 Q 차이를 결측 처리한다. 특히 brk20의 Q 통계는 **38일뿐**으로 545일짜리 연속 변수와 같은 범위의 비교가 아니다. IC는 545일 전체의 이진 순위상관으로 유지한다.
''')
rows=[]
for v in lm['B_vars']:
    u=b[(b['var']==v)&(b.target=='up5')].iloc[0]
    r4=b[(b['var']==v)&(b.target=='T4')].iloc[0]
    rows.append([v,int(u.q_n),ci(u,'q_mean','q_lo','q_hi',2),
                 number(u.q_front,2)+' / '+number(u.q_back,2),int(r4.n),ci(r4),
                 '없음'])
lines.append(table(['변수','Q 유효일 n','상−하 up5 차 %p [95%]','차 앞/뒤 %p','T4 n','T4 IC [95%]','후보'],rows))
lines.append('''
**한 줄 판정: 후보 없음.** 양의 차이가 가장 큰 nh252도 +0.60 [−0.45,+1.68]%p로 +5%p 하단 기준과 거리가 있고 앞/뒤 부호가 바뀐다. 반대 방향을 참고로 읽어도 가장 큰 hl_range의 낮은 쪽−높은 쪽은 +3.80 [+2.72,+4.91]%p여서 기준에 못 미친다. 최근 수익·양봉·20일 돌파·20일선 위는 높은 쪽의 T1/up5가 오히려 음이다. 이 결과는 전 종목의 이번 8변수에 한정한다.

요청서에는 B의 잣대를 ‘상위−하위’로, 계획 §1에는 ‘선택 집단−같은 날 전체 기준율’로 적어 **대조군이 서로 다르다**. 둘을 같은 값으로 부르지 않았다. 보조 `topbase_*`도 저장했으며, 같은 높은 쪽−전체의 95% 하단을 넘는 후보 역시 없다. brk20처럼 동률로 상위 경계가 0이면 보조 집단이 전체가 될 수 있어 그 0 근처 값을 선별 효과로 읽지 않는다. 본문 B 판정은 요청서의 상−하 잣대를 기준으로 한다.

## D. 사후 — path5로 1차 변수 목록 재스캔

**사후 추가 목표다.** 진입 t+1 뒤 다섯 종가(t+2~t+6)가 모두 진입가 이상이면 1이다. 매일 전날보다 오르는 ‘단조 상승’이나 장중에 한 번도 진입가 아래로 내려가지 않는 조건은 아니다. 비용을 빼지 않는 경로 조건이며, up5>0와도 다르다(0%로 끝난 경로는 path5=1일 수 있음).

실제 표본: 2026-06-02~11-06의 100앵커, stage3 **89,972행**·v30 상위10 **2,000행**. path5 완결 행은 각각 82,328/1,880, T4 완결 행은 54,430/1,220. 전종목 표본은 시장별 n≥20에서 IC를 낸 뒤 시장 평균, 상위10 표본은 1차와 동일하게 **두 시장을 합친 날짜별 n≥12**다. 경로값이 전부 0/1인 날은 IC가 정의되지 않아 n이 94보다 줄 수 있고, Q 차이의 n은 별도다. 시장 혼합의 한계는 그대로 남긴다.

92변수 각각 path5/T4를 계산했다. 1차처럼 20관측일 원형 블록 2,000회 seed 7, 보정 α=0.05/(2×92), 앞/뒤=변수별 유효 날짜 중앙값, 뒤반 단독 95%가 0을 제외할 때만 ‘형식 통과’다. 목표를 하나로 줄였다고 보정 분모를 92로 줄이지 않았다. 부트스트랩은 통계별 seed를 고정하므로 1차의 연속 난수 호출 순서와는 다르다.

**자료 갱신 차이를 따로 공개한다.** 현재 DB로 1차 패널을 다시 만들면 종목×run 행 키는 89,972행 전부 같고 t/j 인덱스도 같지만, 원 패널과 일부 변수 값·T4가 달라진다. 아래 실제 표본의 주표는 남아 있는 11/8 `panel.pkl`의 **92변수·상위10 표식·T4를 고정**한 결과다. path5만 현재 DB 시세로 새로 계산했다. 최초 시세 스냅샷이 없으므로 그 부분까지 ‘완전히 같은 원자료’라고 주장할 수 없다. 현재 DB 재구성 표도 삭제하지 않고 함께 남겼다.
''')
lines.append(table(['원 패널 대비 달라진 열','행 수'],[[k,v] for k,v in audit['differences'].items()]))

lines.append('''
### D-1. 실제 표본 — 형식 통과 요약

아래 수치는 원 패널 고정본이다. 전체 92×2 표는 뒤의 D-3에 빠짐없이 싣는다. T4의 ‘대가’는 **선택 방향을 맞춘 뒤** 읽어야 한다. path IC<0이면 낮은 값을 고르는 방향이므로 원시 T4 IC도 음일 때 같은 방향이다.
''')
rows=[]
for _,r in d[d.stat_candidate].iterrows():
    rows.append([r['sample'],r['var'],int(r.n),ci(r),rng(r),number(r.front)+' / '+number(r.back),
                 f"{ci(r,'T4_mean','T4_lo','T4_hi')} (n={int(r.T4_n)})",
                 f"{ci(r,'q_mean','q_lo','q_hi',2)} (n={int(r.q_n)})"])
lines.append(table(['표본','변수','n','path5 IC [95%]','보정 CI','앞/뒤','T4 IC [95%]','상−하 path5 %p [95%]'],rows))

ins=d[(d['sample']=='v30_top10')&(d['var']=='insu_5d_share')].iloc[0]
lines.append(f'''
- v30 상위10의 보험 순매수 비중은 path5 IC {ci(ins)} (n={int(ins.n)}), 상−하 경로 비율 차 {ci(ins,'q_mean','q_lo','q_hi',2)}%p (Q n={int(ins.q_n)})다. **경로 비율 차의 하단도 +5%p를 못 넘고**, Q 유효일은 40 미만이다. 더구나 이것은 up5 개선 검정이 아니며 두 시장 혼합·짧은 기간·사후 목표다. 바로 새 챌린저 근거로 쓰지 않는다.
- `annual_prev_억`는 낮은 값이 path5에 유리한 반면 원시 T4 평균은 양이라 선택 방향이 반대다. T4 구간은 0을 포함하므로 ‘40일을 확실히 깎는다’까지 단정할 수 없고 **대가를 못 가름**이다.
- `smartmoney_trigger`·`credit_bal_rate`처럼 유효일이 짧은 열은 신뢰구간 모양부터 주의해야 한다. 원형 블록 길이 20보다 짧은 뒤반에서는 재표집이 같은 관측을 한 바퀴씩 돌아 **CI가 점 하나로 퇴화**할 수 있다. 요청한 1차 계산법은 그대로 보존했지만 이런 ‘형식 통과’를 유효한 확인으로 읽지 않는다. 신용잔고는 T4 표본도 없다.
- ‘40일도 같은 방향으로 예측한다’는 사실만으로 첫 주 효과가 없다고 판정하는 것은 §1의 조건이 아니다. 이번에는 크기·표본·대가·사후 목표를 따로 보고 보수적으로 결론을 제한한다.
''')

merged=d.merge(rebuilt,on=['sample','var'],suffixes=('_frozen','_rebuilt'))
changes=merged[merged.stat_candidate_frozen!=merged.stat_candidate_rebuilt]
lines.append('원 패널 고정본과 현재 DB 재구성본의 **형식 통과 여부가 달라진 열**:')
if len(changes):
    lines.append(table(['표본','변수','고정본','현재 재구성'],[[r['sample'],r['var'],yn(r.stat_candidate_frozen),yn(r.stat_candidate_rebuilt)] for _,r in changes.iterrows()]))
else:
    lines.append('없음. 값 차이는 각 CSV에 보존했다.')

lines.append('''
### D-2. 11년 과매도 대리 20변수 — 사후

1차와 같은 시작 인덱스 260·5거래일 격자, **519신호일(2016-01-20~2026-08-13)**, 20일 수익 하위20%. 앞/뒤=2021-01-01, 월 블록 4,000회 seed 7, 보정 α=0.05/40(99.875% CI). 원 변수 공식(250일 고저점·RSI 단순평균·r5−r20/4 가속 포함)을 유지했다. path5는 상폐 종목만 마지막 가격 유지한 판으로 계산했다. T4는 같은 날짜 전체 동일가중 대비다. n=516인 이진 열은 일부 날짜에 변수가 상수여서 IC가 없다.
''')
rows=[]
for v in lm['D_vars']:
    r=dp[(dp['var']==v)&(dp.target=='path5')].iloc[0]
    r4=dp[(dp['var']==v)&(dp.target=='T4')].iloc[0]
    rows.append([v,int(r.n),ci(r),rng(r)+' '+yn(r.bonf_pass),
                 number(r.front)+' / '+number(r.back),ci(r,'back','back_lo','back_hi'),
                 ci(r4)+f' (n={int(r4.n)})',ci(r,'q_mean','q_lo','q_hi',2),yn(r.stat_candidate)])
lines.append(table(['변수','n','path5 IC [95%]','보정 CI·통과','앞/뒤','뒤반 [95%]','T4 IC [95%]','상−하 경로 차 %p [95%]','형식 통과'],rows))
numproxy=int(dp[(dp.target=='path5')&dp.stat_candidate].shape[0])
lines.append(f'''
형식 통과는 **{numproxy}/20개**다. 이 통과 변수들은 원시 T4와 path5의 방향이 같아, 낮은 값을 선택하는 경우까지 방향을 맞추면 40일 평균도 같은 방향이다. 전부 첫 주에만 작동하는 신호라는 뜻은 아니다. 경로 차이는 거래대금·변동성 등 기존 축에 몰리며, 가장 큰 낮은 거래대금 쪽−높은 쪽 차이도 약 +4.26 [+3.29,+5.25]%p로 **하단 +5%p 미달**이다. 닫힌 저변동·거래대금 연구를 새 모델로 다시 열지 않는다.

### D-3. 실제 표본 전체 변수표 — 사후, 원 패널 고정본

‘보정’은 보정 CI가 0을 제외하는지, ‘형식’은 보정+앞/뒤 같은 부호+뒤반 95%가 0을 제외하는지다. n=0이면 상수·결측 등으로 계산 불가. 신용·smartmoney의 짧은 표본 문제는 D-1의 제한을 우선한다. 앞/뒤 평균은 부호 확인용이며 각 구간의 n·95% CI와 모든 Q 통계는 `D_actual_frozen_summary.csv`에 함께 남겼다.
''')
for sample in ['stage3','v30_top10']:
    lines.append('#### '+('stage3 전체' if sample=='stage3' else 'v30 시장별 상위10 (IC는 두 시장 혼합)'))
    rows=[]
    for _,r in d[d['sample']==sample].iterrows():
        rows.append([r['var'],int(r.n),ci(r),rng(r)+' '+yn(r.bonf_pass),
                     number(r.front)+' / '+number(r.back),ci(r,'back','back_lo','back_hi'),
                     ci(r,'T4_mean','T4_lo','T4_hi')+f' (n={int(r.T4_n)})',yn(r.stat_candidate)])
    lines.append(table(['변수','n','path5 IC [95%]','보정 CI·통과','앞/뒤','뒤반 [95%]','T4 IC [95%]','형식'],rows))

size=sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())
lines.append(f'''
## 재현·검증·보관

- `code_20261110_first_week_compute.py`: A/B/D 계산, `code_20261110_first_week_compare.py`: A 사후 대조, `code_20261110_first_week_audit.py`: 표본·수치 범위·기존 패널 대조, `code_20261110_first_week_report.py`: 이 답변 생성.
- 실행 순서(저장소 루트, 금지 시간 밖): 아래 명령. A 대조는 A 독립 계산을 저장한 다음에만 실행한다. B·D 결과를 읽어 변수를 추가하거나 문턱을 고르는 단계는 없다.

```powershell
python -B -X utf8 research/handoff/code_20261110_first_week_compute.py a
python -B -X utf8 research/handoff/code_20261110_first_week_compare.py
python -B -X utf8 research/handoff/code_20261110_first_week_compute.py long
python -B -X utf8 research/handoff/code_20261110_first_week_compute.py dactual
python -B -X utf8 research/handoff/code_20261110_first_week_audit.py
python -B -X utf8 research/handoff/code_20261110_first_week_compute.py dfrozen
python -B -X utf8 research/handoff/code_20261110_first_week_report.py
```

- A 26모델, B 8변수×3목표, D 실제 92변수×2표본·장기 20변수×2목표의 수·비율 범위·차 계산을 확인했다. 원 패널과 재구성본의 행 키·앵커·종목 위치는 일치한다. 변수 값 차이는 위에 모두 공개했다. 운영 전체 테스트·배치는 돌리지 않았다.
- 작업 중 git 상태에는 다른 운영 파일·docs의 추가 변경도 관찰됐다. 이 계산 코드의 쓰기 대상은 handoff의 지정 산출물뿐이며, 그 외 변경은 이 작업에서 수정하거나 되돌리지 않았다. 따라서 저장소 전체가 시작 때와 같다는 주장은 하지 않는다.
- 신뢰구간은 요청한 재표집 기준이다. A의 겹치는 5일 창은 iid가 충분히 반영하지 못하며, D의 92변수 보정 꼬리는 2,000회에서 한 번 미만의 극단 추출에 해당해 경계 결과가 안정적이지 않다. 표를 임의 완화하거나 이런 구간으로 운영 채택을 선언하지 않았다.
- 11년 유니버스의 현재 분류·수정주가·상폐 마지막 가격 유지·미래 가격 가용성 조건 등 공통 틀의 한계가 있다. 과매도 대리를 v30 실제 목록의 증거로 옮기지 않는다. 실제 표본의 업종은 당시 분류 스냅샷이 아닌 1차 패널의 분류다.
- 새 산출물 폴더는 **약 {size/1024/1024:.2f} MiB**이며 큰 가격판·pickle을 새로 저장하지 않았다. 기존 `research/out_early_rise_scan/panel.pkl`은 사용자의 기존 파일이라 삭제하지 않았다. 고정본 재현에는 이 원 패널이 필요하다. 없는 환경에서는 `dactual`로 현재 DB를 재구성할 수 있지만, 원 패널과 완전히 같은 값이라고 부르면 안 된다.

## 두 번째 의견

**(가) 더 볼 각도는 계획 §2의 C(공시·지수 편입 사건 뒤 첫 주) 하나가 남아 있다.** 이번 A·B는 고정된 개선 하단 +5%p를 넘지 못했고, D는 사후 경로 목표에서 일부 연관을 보였지만 짧은 표본·기존 축·40일 대가·목표 차이 때문에 곧바로 §1 후보가 되지 않는다. 따라서 B의 8변수와 이번 D를 이유로 ML·조합·문턱 탐색을 늘릴 근거는 없다. 다만 아직 계산하지 않은 C까지 포함해 ‘종목 고르기는 언제나 기준율 +5%p 안’이라고 일반화하는 것도 증거보다 강하다. C를 이미 고정한 사건 목록·§1 기준으로 한 번만 확인하고, 거기서도 못 넘으면 **이번 사전 목록 범위에서 닫는 것**이 맞다. ‘40일도 잘 맞힌다’ 또는 ‘절대 상승 비율이 반 미만이다’만으로 첫 주 효과를 부정하지 말고, 같은 날 기준율 대비 개선과 그 불확실성으로 판단해야 한다.
''')
guard()
target=HERE/'REPLY_20261110_first_week_round2.md'
target.write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
metadata('report_meta',dict(reply=str(target),bytes=target.stat().st_size,
                          frozen_stat_pass={s:int(g.stat_candidate.sum()) for s,g in d.groupby('sample')},
                          changed_flags=len(changes),output_bytes=size))
print(target, target.stat().st_size, 'bytes')
print('Frozen pass:',d[d.stat_candidate][['sample','var','n','mean','q_n','q_mean','q_lo','q_hi']].to_string(index=False))
