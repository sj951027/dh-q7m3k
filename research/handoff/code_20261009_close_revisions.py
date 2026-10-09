"""Stored logs and read-only DB audit; no network or collector imports."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
from datetime import datetime,timedelta,timezone
import sqlite3
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding='utf-8')
def guard():
 t=datetime.now(timezone(timedelta(hours=9)))
 if t.weekday()<5 and '20:10'<=t.strftime('%H:%M')<'22:30':raise SystemExit('KST batch window')
 return t.isoformat(timespec='seconds')
def ro(p):return sqlite3.connect('file:'+str(p.resolve())+'?mode=ro',uri=True)
def table(h,rs):return '\n'.join(['| '+' | '.join(map(str,h))+' |','|'+'|'.join(['---']*len(h))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rs])
def main():
 started=guard();d=pd.read_csv(ROOT/'logs/close_revisions_detail.csv',dtype={'ticker':str,'target_date':str});s=pd.read_csv(ROOT/'logs/close_revisions.csv',dtype={'target_date':str})
 d['exact_pct']=(d.new_close/d.old_close-1)*100
 o=ro(ROOT.parent/'dh-q7m3k-data/ohlcv.db');h=ro(ROOT/'history.db')
 enrich=[]
 for r in d.itertuples():
  p=o.execute('SELECT market,close,high,low,shares,volume FROM daily_ohlcv WHERE ticker=? AND date=?',(r.ticker,r.target_date)).fetchone()
  ev=o.execute("SELECT rcept_dt,event_type,report_nm FROM dart_events WHERE ticker=? AND rcept_dt BETWEEN ? AND ? AND event_type IN ('paid_in','bonus','reduction','paid_bonus_mix') ORDER BY rcept_dt",(r.ticker,(datetime.strptime(r.target_date,'%Y%m%d')-timedelta(days=120)).strftime('%Y%m%d'),r.target_date)).fetchall()
  enrich.append(dict(market=p[0] if p else '',cap=p[1]*p[4]/1e8 if p and p[4] else np.nan,amount=p[1]*p[5]/1e8 if p else np.nan,px=p[1] if p else np.nan,inside=(p[3]<=r.old_close<=p[2]) if p else False,events=ev,same_day=any(e[0]==r.target_date for e in ev)))
 d=pd.concat([d,pd.DataFrame(enrich)],axis=1)
 rows=[]
 for date,g in s.groupby('target_date',sort=True):
  dd=d[d.target_date==date]
  rows.append([date,int(g.n_close_revised.sum()),len(dd),f'{dd.exact_pct.abs().median():.3f}' if len(dd) else '확인 못 함',f'{g.max_abs_pct.max():.2f}',int((dd.exact_pct>0).sum()),int((dd.exact_pct<0).sum())])
 repeat=[]
 for t,g in d.groupby('ticker'):
  if len(g)<2:continue
  repeat.append([t,len(g),g.market.iloc[-1],f'{g.cap.median():.1f}',f'{g.amount.median():.2f}',f'{g.px.median():.0f}',f'{g.exact_pct.mean():+.3f}'])
 large=d[d.exact_pct.abs()>.5]
 sam=d[d.ticker=='207940']
 assert len(sam)==4
 hypotheses=[['207940의 같은 비율 재조정',len(sam),int(sam.inside.sum()),int(sam.events.map(bool).sum()),'가격조정과 일치하는 패턴; 원인 확정 아님'],['나머지 상세 행',len(d)-len(sam),int(d[d.ticker!='207940'].inside.sum()),int(d[d.ticker!='207940'].events.map(bool).sum()),'임시/애프터마켓 값과 양립; 구분 불가'],['상세 없는 요약 행',int(s.n_close_revised.sum())-len(d),'확인 못 함','확인 못 함','종목·방향·가격범위 복원 불가']]
 # Isolate fixed-score, fixed-basket endpoint-return changes from the logged prices.
 px=pd.read_sql_query("SELECT date,ticker,close FROM daily_ohlcv WHERE date>='20260501'",o)
 close=px.pivot(index='date',columns='ticker',values='close').sort_index();dates=close.index.to_list();di={date:i for i,date in enumerate(dates)}
 early=close.copy();late=close.copy();current_mismatch=0
 for (date,t),g in d.sort_values('run_started_at').groupby(['target_date','ticker'],sort=False):
  if date in di and t in close:
   early.loc[date,t]=g.old_close.iloc[0];late.loc[date,t]=g.new_close.iloc[-1]
   current_mismatch+=int(close.loc[date,t]!=g.new_close.iloc[-1])
 effects=[];extremes=[]
 for model,tb,col,reg in [('v30','v3_scores','final_score_v3','20260606'),('lv_b','lowvol_scores','lowvol_score','20260625')]:
  scores=pd.read_sql_query(f'SELECT run_id,market,ticker,{col} score FROM {tb} WHERE model_id=? AND run_id>=?',h,params=(model,reg));scores.market=scores.market.str.lower()
  candidates={}
  for rid in sorted(scores.run_id.unique()):
   if rid in ['20260608','20260703']:continue
   t=int(np.searchsorted(dates,rid,side='right')-1)
   if t<0 or (rid not in di and (datetime.strptime(rid,'%Y%m%d')-datetime.strptime(dates[t],'%Y%m%d')).days>5):continue
   candidates.setdefault(t,[]).append(rid)
  for t,rids in sorted(candidates.items()):
   rid=dates[t] if dates[t] in rids else min(rids)
   if t+21>=len(dates):continue
   for market,g in scores[scores.run_id==rid].groupby('market'):
    picks=g.dropna(subset=['score']).nlargest(10,'score').ticker
    a=(early.iloc[t+21].reindex(picks)/early.iloc[t+1].reindex(picks)-1)*100
    b=(late.iloc[t+21].reindex(picks)/late.iloc[t+1].reindex(picks)-1)*100
    ok=a.notna()&b.notna();delta=b[ok]-a[ok]
    if not ok.any():continue
    effects.append(dict(model=model,market=market,date=dates[t],n=int(ok.sum()),delta=float(delta.mean()),max_stock=float(delta.abs().max())))
    for stock,value in delta[abs(delta)>1e-12].items():extremes.append([model,market,dates[t],dates[t+1],dates[t+21],stock,f'{value:+.6f}'])
 effects=pd.DataFrame(effects)
 impact=[]
 for (model,market),g in effects.groupby(['model','market']):
  impact.append([model,market,len(g),int(g.n.sum()),int((g.delta.abs()>1e-12).sum()),f'{g.delta.abs().max():.6f}',f'{g.delta.mean():+.6f}',f'{g.max_stock.max():.6f}'])
 eventrows=[[r.ticker,r.target_date,f'{r.exact_pct:+.4f}',r.same_day,','.join(sorted(set(x[1]+':'+x[0] for x in r.events))) or '없음',r.inside] for r in large.itertuples()]
 text=f'''# REPLY — 3. 종가 정정 원인과 수익 영향

검토 {started}. 저장 자료만 분석, 수집기·외부 조회 없음. 결론: 소폭 정정이 늘어난 추세는 확인되지 않으며, 대부분은 시간외 마지막 체결가/임시값 가설과 양립하지만 **원인은 확정 못 함**. 배치 시각을 늦추면 해결된다고 단정할 자료도 없다.

## (1) 9/14 이후 날짜별 전수

요약 n={len(s)}행·정정 이벤트 합 n={int(s.n_close_revised.sum())}; 상세 n={len(d)}행·n={d.ticker.nunique()}종목. 상세가 9/22부터라 9/14~21의 n={int(s.n_close_revised.sum())-len(d)}건에는 종목·old/new·중앙값이 없다. 정정 0일은 CSV에 행이 생기지 않으므로 표의 날짜만으로 모든 거래일 정정률을 추정하지 않는다. 중복 날짜는 서로 다른 관측 실행의 정정 이벤트 수를 합산했다.

'''+table(['대상 날짜','요약 정정 n','상세 n','상세 절대폭 중앙 %','요약 최대 %','상승 n','하락 n'],rows)+f'''

상세 기간의 방향: 상승 n={int((d.exact_pct>0).sum())}, 하락 n={int((d.exact_pct<0).sum())}, 절대폭 중앙 {d.exact_pct.abs().median():.4f}%. 소수 종목이 여러 번 나오므로 행을 독립 시행으로 간주한 이항 구간은 제시하지 않았다. 날짜별 중앙·건수 표는 기술통계이며 성과 CI가 아니다.

## (2) 반복 종목

시총·거래대금·종가는 **현재 저장된 해당 대상 날짜** 기준이며 당시 최초 수집값이 아니다. 시총의 과거 주식 수/수정가격 한계도 남는다.

'''+table(['종목','정정 n','시장','시총 중앙 억원','거래대금 중앙 억원','종가 중앙 원','변화율 평균 %'],repeat)+f'''

0.5% 초과 상세 n={len(large)}건, 그중 207940 n=4. 나머지 n={len(large)-4}건의 당일 old_close가 현재 고저 범위 안인 수={int(large[large.ticker!='207940'].inside.sum())}. 범위 안이라는 사실은 시간외 거래/장중 임시값/자료 공급자 정정 중 어느 하나를 확정하지 않는다.

요청 배경의 n=24는 CSV의 반올림 pct 절댓값≥0.5로 세면 재현된다. 반올림 pct>0.5는 n=22, old/new로 복원한 정확한 변화율>0.5는 n=23이다. 경계의060590(3030→3045)은 실제+0.49505%, 013700(1590→1598)은+0.50314%인데 둘 다CSV에는0.5로 저장됐다. 본 표는 정확한 변화율 기준이다.

## (3~5) 공시와 가격 범위에 따른 가설 대조

'''+table(['분류','정정 n','old가 현재 고저 안 n','직전120일 관련 공시 n','해석'],hypotheses)+'''

관련 공시는 유상·무상·유무상·감자에 한정했다. 같은 날 공시 여부와 직전 120일 공시를 따로 표시한다. 공시 접수일은 권리락/효력일이 아니므로 단순 일치로 가격 조정 원인을 확정할 수 없다. 207940의 4개 과거 날짜가 같은 실행에서 약 −0.77%씩 바뀐 패턴은 전체 과거가격 재조정과 맞고, 서로 다른 날의 마지막 체결가가 같은 비율로 어긋난 것보다 설명력이 있다. 다만 정확한 조정계수/원문 효력일이 없어 확인 못 함이다.

'''+table(['종목','대상일','정정 %','당일 관련 공시','직전120일 관련 공시 유형:접수일','old 고저 안'],eventrows)+f'''

주의: close_revisions()는 |new/old−1|≤ADJ_TOL인 정정만 상세에 남기며 큰 재조정은 제외한다. 따라서 이 CSV는 모든 수정주가 사건 목록이 아니다. 코드 주석의 '확정 공식 종가로 바뀐다'는 인과 단정은 이 로그만으로 검증되지 않는다. observed_at은 **새 값 재확인 시각**이고 최초 old 값 수집 시각은 행에 없으므로 '20:10 값이었다'는 것도 모든 행에 대해 직접 입증되지 않는다.

## (6) 상위10의 20일 수익 영향

고정된 동결점수로 시장별 상위10, 신호 다음 거래일 종가→그 뒤20거래일 종가를 비교했다. 두 게이트 run 20260608·20260703 제외, 비거래일은 직전5일 내 거래일로 매핑, 같은 앵커는 거래일 run 우선. n은 종료된 **바구니-날짜** 및 유효 종목자리 수다. 비교는 상세 CSV의 최초 old 가격으로 되돌린 상태와 마지막 new 가격 상태이며, 가격 결손 집합은 양쪽 공통으로 고정했다. 실제 종목 선택이나 점수 변화는 재계산하지 않았다.

'''+table(['모델','시장','완료 바구니 n','유효 자리 n','영향 바구니 n','최대 바구니 변화 절댓값 %p','평균 변화 %p','최대 단일 자리 변화 %p'],impact)+'''

'''+(table(['모델','시장','신호일','진입일','종료일','종목','변화 %p'],extremes) if extremes else '영향 있는 단일 자리 n=0.')+f'''

현재 DB 종가와 마지막 상세 new가 다른 셀 n={current_mismatch}. 이 경우 표는 로그에 기록된 변화만의 반사실 비교이며 최신 DB와 최초 스냅샷 전체 비교가 아니다. 상세 없는 n={int(s.n_close_revised.sum())-len(d)}건·ADJ_TOL 초과 변경·변경이 점수나 선택에 준 영향은 확인 못 함. 최신 20일 미완결 신호를 완료 수익에 섞지 않았다. 위 최대치와 전수 기술 평균에 표본 CI를 붙이지 않았다.

## 재현 방법 · 영향 · 고치는 안

- 재현: `python research/handoff/code_20261009_close_revisions.py`. 원자료 로그·DB 읽기 전용. n={len(d)} 상세 행의 가격/거래량/주식 수와 이벤트를 결합한다.
- 영향: 최초 저장값과 나중 값이 다를 수 있고, 작은 변동도 등급·순위 경계에서는 선택을 바꿀 수 있다. 이번 검토는 고정 선택의 가격 수익 영향만 측정했다.
- 고치는 안(의견): 검증 자료 없이 배치 시각부터 늦추기보다는 기존 다음 거래일 재확인과 최초/정정 관측 보관을 유지하고, 공급원별 당일 종가·시간외/확정 상태를 따로 비교하는 것이 원인을 가릴 수 있다. 다음날 재확인이 최종 확정이라는 보장도 없다. 최초 가격의 원 출처·조회시각·응답 원문과 공식 종가 대조가 있어야 시간 변경의 효과를 검증할 수 있다.
- 못 한 것: 시간외 실제 체결자료·공식 종가 원본·조정계수 없음으로 원인 확정 및 '다음날만으로 충분' 여부는 확인 못 함. 외부 조회·수집·운영 코드 변경은 하지 않았다. 새 큰 중간 파일 없음.

3번 완료. 다음 번호: 4번.
'''
 guard();Path(__file__).with_name('REPLY_20261009_close_revisions.md').write_text(text,encoding='utf-8')
 print('DONE',len(d),'large',len(large),'impact',impact)
if __name__=='__main__':main()
