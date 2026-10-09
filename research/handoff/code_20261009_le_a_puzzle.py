"""Offline independent le_a diagnostics; only the paired REPLY is written."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import sys,sqlite3,json
import numpy as np,pandas as pd
from scipy.stats import spearmanr
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[2]
def guard():
 t=datetime.now(timezone(timedelta(hours=9)))
 if t.weekday()<5 and '20:10'<=t.strftime('%H:%M')<'22:30':raise SystemExit('KST batch window')
 return t.isoformat(timespec='seconds')
def ro(p):return sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
def table(h,rs):return '\n'.join(['| '+' | '.join(h)+' |','|'+'|'.join(['---']*len(h))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rs])
def ci(a):
 a=np.asarray(a,float);rng=np.random.default_rng(7)
 return '['+', '.join(f'{v:+.3f}' for v in np.quantile(a[rng.integers(len(a),size=(4000,len(a)))].mean(axis=1),[.025,.975]))+']'
def main():
 started=guard();h=ro(ROOT/'history.db');o=ro(ROOT.parent/'dh-q7m3k-data/ohlcv.db')
 px=pd.read_sql_query('SELECT date,ticker,close,market FROM daily_ohlcv',o)
 close=px.pivot(index='date',columns='ticker',values='close').sort_index();dates=list(close.index);di={d:i for i,d in enumerate(dates)}
 mk=px.groupby('ticker').market.last().str.lower();chg=close.pct_change(fill_method=None).abs()
 counts=pd.read_sql_query('SELECT run_id,COUNT(*) n FROM stage1_oversold GROUP BY run_id',h)
 partial=set(counts.loc[counts.n<counts.n.median()*.3,'run_id']);double=set()
 for tb in ['v3_scores','lowvol_scores','wu_scores']:
  fa=pd.read_sql_query(f'SELECT run_id,model_id,frozen_at FROM {tb}',h);fa['ts']=pd.to_datetime(fa.frozen_at,utc=True,errors='coerce')
  sp=fa.groupby(['run_id','model_id']).ts.agg(['min','max']);double.update(sp.loc[(sp['max']-sp['min']).dt.total_seconds()>=3600].index.get_level_values(0))
 excluded=partial|double
 def anch(rid):
  for k in range(6):
   d=(datetime.strptime(rid,'%Y%m%d')-timedelta(days=k)).strftime('%Y%m%d')
   if d in di:return di[d]
 def keep(s,reg):
  cand={}
  for rid in sorted(s.run_id.unique()):
   if rid<reg or rid in excluded:continue
   t=anch(rid)
   if t is not None:cand.setdefault(t,[]).append(rid)
  return {t:dates[t] if dates[t] in rs else min(rs) for t,rs in cand.items()}
 specs=[('le_a','wu_scores','wu_score','20260715'),('v30','v3_scores','final_score_v3','20260606'),('mom_a','lowvol_scores','lowvol_score','20260627')]
 scores={};kept={}
 for mid,tb,col,reg in specs:
  s=pd.read_sql_query(f'SELECT run_id,market,ticker,{col} score FROM {tb} WHERE model_id=?',h,params=(mid,));s.market=s.market.str.lower();scores[mid]=s;kept[mid]=keep(s,reg)
 mature=[t for t in kept['le_a'] if t+41<len(dates)];records=[];bins=[];icrows=[];later=[];comp=[]
 for mid in scores:
  s=scores[mid]
  for t,rid in sorted(kept[mid].items()):
   guard()
   rr=close.iloc[min(t+41,len(dates)-1)]/close.iloc[t+1]-1 if t+1<len(dates) else None
   if rr is None:continue
   for market,g in s[s.run_id==rid].dropna(subset=['score']).groupby('market'):
    top=g.nlargest(10,'score').ticker.to_list();a=rr.reindex(top).dropna()*100;b=rr.reindex(mk.index[mk==market]).dropna()*100
    if len(a)<5:continue
    if t in mature:
     comp.append(dict(model=mid,t=t,market=market,ret=a.mean(),bench=b.mean(),ex=a.mean()-b.mean(),n=len(a)))
     if mid=='le_a':
      for ticker,r in a.items():records.append(dict(t=t,date=dates[t],market=market,ticker=ticker,ret=r,bench=b.mean(),weight=1/len(a)/2))
    if mid=='le_a' and t>max(mature):
     later.append([dates[t],dates[t+1],len(dates)-t-2,market,len(a),f'{a.mean():+.3f}',f'{b.mean():+.3f}',f'{a.mean()-b.mean():+.3f}'])
    if mid=='le_a':
     ranked=g.copy();ranked['bin']=np.minimum(20,np.floor((ranked.score.rank(method='first')-1)/len(ranked)*20).astype(int)+1)
     for horizon in [20,40]:
      if t+1+horizon>=len(dates):continue
      ret=(close.iloc[t+1+horizon]/close.iloc[t+1]-1)*100
      x=ranked.copy();x['ret']=ret.reindex(x.ticker).to_numpy();x=x.dropna(subset=['ret'])
      if t in mature:
       for bn,gg in x.groupby('bin'):bins.append(dict(t=t,market=market,h=horizon,bin=bn,ret=gg.ret.mean(),n=len(gg)))
      if horizon==20:
       jump=chg.iloc[t+2:t+2+horizon].max();valid=x[jump.reindex(x.ticker).to_numpy()<=.32]
       if len(valid)>=8:icrows.append(dict(t=t,market=market,ic=spearmanr(valid.score,valid.ret).statistic,n=len(valid)))
 rec=pd.DataFrame(records);cp=pd.DataFrame(comp);bn=pd.DataFrame(bins);ics=pd.DataFrame(icrows)
 daily=cp[cp.model=='le_a'].groupby('t')[['ret','bench','ex']].mean()
 snap=json.loads((ROOT/'docs/scoreboard.json').read_text(encoding='utf-8'));orig=next(m for m in snap['models'] if m['model']=='le_a')['fix']
 diffs={k:float(daily[c].mean()-orig[k]) for k,c in [('ret_mean','ret'),('bench_mean','bench'),('exc_mean','ex')]}
 assert max(map(abs,diffs.values()))<1e-9,diffs
 contribution=rec.assign(contribution=rec.ret*rec.weight/len(mature)).groupby('ticker').agg(contribution=('contribution','sum'),slots=('ret','size'),mean=('ret','mean')).sort_values('contribution',ascending=False)
 top3=contribution.head(3).index;removed=rec[~rec.ticker.isin(top3)].groupby(['t','market']).agg(ret=('ret','mean'),bench=('bench','first')).groupby('t').mean();removed['ex']=removed.ret-removed.bench
 bestdays=daily.ex.nlargest(3).index;dropdays=daily.drop(bestdays)
 attr=[['전체',len(daily),len(rec),f'{daily.ret.mean():+.3f}',f'{daily.ex.mean():+.3f}',ci(daily.ex)],['기여 상위3종목 제거 후 재동일가중',len(removed),len(rec[~rec.ticker.isin(top3)]),f'{removed.ret.mean():+.3f}',f'{removed.ex.mean():+.3f}',ci(removed.ex)],['초과 상위3신호일 제거',len(dropdays),len(rec[~rec.t.isin(bestdays)]),f'{dropdays.ret.mean():+.3f}',f'{dropdays.ex.mean():+.3f}',ci(dropdays.ex)]]
 markets=[]
 for market,g in cp[cp.model=='le_a'].groupby('market'):
  cc=rec[rec.market==market].assign(c=lambda x:x.ret/10/len(mature)).groupby('ticker').c.sum().nlargest(3).index
  rem=rec[(rec.market==market)&~rec.ticker.isin(cc)].groupby('t').agg(ret=('ret','mean'),bench=('bench','first'))
  markets.append([market,len(g),int(g.n.sum()),f'{g.ret.mean():+.3f}',f'{g.bench.mean():+.3f}',f'{g.ex.mean():+.3f}',ci(g.ex),','.join(cc),f'{(rem.ret-rem.bench).mean():+.3f}',f'{g.sort_values("ex").iloc[:-3].ex.mean():+.3f}'])
 # Conditional randomisation: one random ordering per simulation, shared across dates.
 # This preserves repeated stocks and overlapping windows. Future missing prices are dropped.
 randomrows=[];rng=np.random.default_rng(7)
 for pool in ['same_market_all','le_a_scored']:
  sims=np.zeros((1000,len(mature),2));sims[:]=np.nan
  for j,market in enumerate(['kospi','kosdaq']):
   universe=mk.index[mk==market].to_list();cols={ticker:i for i,ticker in enumerate(universe)};keys=rng.random((1000,len(universe)))
   for k,t in enumerate(sorted(mature)):
    cand=universe if pool=='same_market_all' else None
    if pool=='le_a_scored':cand=scores['le_a'].loc[(scores['le_a'].run_id==kept['le_a'][t])&(scores['le_a'].market==market)&scores['le_a'].score.notna(),'ticker'].to_list()
    cand=[x for x in cand if x in cols and pd.notna(close.iloc[t+1].get(x)) and close.iloc[t+1][x]>0]
    ids=np.array([cols[x] for x in cand]);pick=np.argpartition(keys[:,ids],9,axis=1)[:,:10]
    r=((close.iloc[t+41]/close.iloc[t+1]-1)*100).reindex(cand).to_numpy();vals=r[pick]
    sims[:,k,j]=np.nanmean(vals,axis=1)-cp[(cp.model=='le_a')&(cp.t==t)&(cp.market==market)].bench.iloc[0]
  draws=np.nanmean(sims,axis=(1,2));q=np.quantile(draws,[.025,.975])
  randomrows.append([pool,1000,len(mature),f'{draws.mean():+.3f}',f'[{q[0]:+.3f}, {q[1]:+.3f}]',int((draws>=daily.ex.mean()).sum()),f'{(draws>=daily.ex.mean()).mean():.3f}'])
 comparisons=[]
 for mid,g in cp.groupby('model'):
  dg=g.groupby('t')[['ret','bench','ex']].mean();paired=dg.ex-daily.ex.reindex(dg.index)
  comparisons.append([mid,len(dg),int(g.n.sum()),f'{dg.ret.mean():+.3f}',f'{dg.bench.mean():+.3f}',f'{dg.ex.mean():+.3f}',ci(dg.ex),f'{paired.mean():+.3f}',ci(paired)])
 btable=[];charts=[]
 for market in ['kospi','kosdaq']:
  chart={}
  for horizon in [20,40]:
   gr=bn[(bn.market==market)&(bn.h==horizon)];means=gr.groupby('bin').ret.mean();chart[horizon]=means
   for bi,g in gr.groupby('bin'):btable.append([market,horizon,bi,len(g),int(g.n.sum()),f'{g.ret.mean():+.3f}',ci(g.ret)])
  charts.append('```mermaid\nxychart-beta\n title "'+market+' 점수순위20칸: 선1=h20, 선2=h40"\n x-axis "낮은 점수 → 높은 점수" 1 --> 20\n y-axis "수익 %"\n'+''.join(' line ['+', '.join(f'{v:.3f}' for v in chart[hh].reindex(range(1,21)))+']\n' for hh in [20,40])+'```')
  print('BINS',market,[(hh,round(spearmanr(list(range(1,21)),chart[hh]).statistic,4),round(chart[hh].iloc[-1],3)) for hh in [20,40]])
 independent=[];last=-9999
 for t in sorted(mature):
  if t+1>=last:independent.append(t);last=t+41
 icday=ics.groupby('t').ic.mean();cohortic=icday.reindex(mature).dropna()
 text=f'''# REPLY — 4. le_a 순위 상관과 상위10 성과

검토 {started}, 가격 마지막 {dates[-1]}. 운영 코드·DB·docs 변경 없음. 기존 scoreboard의 완료 n={len(mature)}개를 독립 재계산했고 평균 수익·시장·초과의 최대 차이 {max(map(abs,diffs.values())):.12f}%p로 일치했다.

## 먼저 구분할 수치

요청의 +0.011은 **현재 h20 관측값**이다. 9/13 정본은 le_a h20 **−0.0145, 95% [−0.0436,+0.0152], n=20**, 가격 기준9/11이다. 이번 같은 가격에서 점프컷0.32를 적용한 h20 IC는 n={len(icday)}일 평균 {icday.mean():+.6f}, 날짜 iid95% {ci(icday)}; 완료40일의 같은 n={len(cohortic)}일에서는 {cohortic.mean():+.6f}, {ci(cohortic)}. 전종목 순위의 h20과 꼬리10종목의 h40은 대상·기간·이상치 규칙이 다르다. scoreboard에는 점프컷·희석 제외·과거시점 유니버스 보정이 없다.

이하 수익은 신호 다음 거래일 종가→40거래일 후 종가, 무비용·시장별 동일가중 후 두 시장 평균. 날짜는 **매수 체결일이 아닌 신호 앵커일**이다. h20/40 20칸은 같은 완료 n={len(mature)}일만 사용해 기간 차이를 고정했다. 순위를 시장×신호일 내 낮은 점수1칸~높은20칸으로 나누고 칸 수익을 날짜 동일가중했다. 동점은 DB행 순서로 분할(전체 IC는 평균순위).

## (1) 20칸 수익 그림과 수치

'''+ '\n\n'.join(charts)+'\n\n'+table(['시장','보유일','칸','날짜 n','유효 자리 n','평균 %','날짜 iid95% 참고'],btable)+'''

그림과 아래 구간은 이미 본 자료의 설명이다. 날짜 iid95%는 겹친 보유기간을 독립으로 취급한 **참고값**이며 일반화의 신뢰구간이 아니다. 비겹침 40일 블록은 n=1이라 유효한 블록95% 구간은 확인 못 함.

## (2~3) 집중도와 시장 분해

종목 기여는 각 바구니의 유효 종목수로 나눈 수익을 두 시장·16일에 걸쳐 더한 값이다. 반복 등장한 자리도 포함한다. 제거 계산은 해당 종목을 모든 날짜에서 뺀 뒤 남은 종목을 재동일가중했다. 상위3일은 일평균 **초과수익** 순서이며 시장별 제거도 따로 계산했다.

'''+table(['종목','등장 자리 n','평균 종목 수익 %','전체 수익 기여 %p'],[[t,int(g.slots),f'{g["mean"]:+.3f}',f'{g.contribution:+.3f}'] for t,g in contribution.head(10).iterrows()])+'\n\n'+table(['대상','날짜 n','자리 n','수익 %','초과 %p','날짜 iid95% 참고'],attr)+'\n\n'+table(['시장','날짜 n','자리 n','수익 %','시장 %','초과 %p','iid95% 참고','기여 상위3종목','3종목 제외 초과','3일 제외 초과'],markets)+f'''

전체에서 제외한 상위3일: {', '.join(dates[t] for t in bestdays)}. 상위3종목: {', '.join(top3)}. 종목과 날짜는 결과를 보고 선정했으므로 제거 결과도 사후 민감도이다.

## (4) 같은 16신호일 비교

'''+table(['모델','공통 날짜 n','자리 n','수익 %','시장 %','초과 %p','iid95% 참고','모델−le_a %p','짝 iid95% 참고'],comparisons)+'''

무작위 n=1,000회, seed7. 각 회의 종목별 무작위 순서를 전체16일에 공통 적용해 반복 보유를 유지했다. 각 날짜 진입가가 있는 시장 종목/당일 le_a 점수후보에서 10개를 고르고 종료가 결손만 제외했다. 아래95%는 **해당 기간·가격을 고정한 무작위 바구니 분포**이며 미래 성과의 CI도 모델 다중탐색을 보정한 p값도 아니다. 현재 시장 분류와 생존자료 한계가 있다.

'''+table(['무작위 후보군','모의 n','날짜 n','평균 초과 %p','조건부95% 범위','le_a 이상 횟수 n','비율'],randomrows)+f'''

## (5) 비겹침 표본

완료 신호일 n={len(mature)}, {dates[min(mature)]}~{dates[max(mature)]}. 진입→종료의 40거래일 구간을 겹치지 않게 최대한 고르면 **n={len(independent)}**, 선택 앵커 {', '.join(dates[t] for t in independent)}. 16/40=0.4는 표시용 비율이며 독립 표본수가 0.4개라는 뜻은 아니다. n=1은 통계적 독립까지 보장하지 않는다.

## (6) 이후 미완결 목록의 현재 평가

다음 표는 {dates[max(mature)]} 이후, 진입 완료·40일 미완결 신호 n={len(later)//2}개(시장별 행 n={len(later)})의 마지막 종가 평가. 보유기간이 다르므로 완료40일과 직접 비교할 수 없다. 수익은 체결 시뮬레이션이 아닌 고정 바구니 평가이며 최신 신호의 진입가가 없으면 제외한다.

'''+table(['신호일','진입일','현재 보유거래일','시장','유효 n','평가 수익 %','시장 %','초과 %p'],later)+'''

## 결론

20칸은 단조 증가하지 않고 최고점수 칸도 최고수익 칸이 아니다(코스피40일 최상위칸 +8.869%보다 최하위칸 +20.931%가 높음, 각 n=16; 코스닥은18칸 +25.766%가20칸 +22.299%보다 높음). 따라서 '맨 위 칸만 맞춘다'는 단순 설명은 지지되지 않는다. 극상위10은 같은 기간 v30·mom_a보다 좋았고, 반복된 상위3종목 n=37자리의 전체 수익 기여는 +7.171%p였다. 이들을 빼도 초과 +6.335%p(n=16)가 남아 단3종목만의 결과도 아니다. 다만 같은 후보군 무작위의 95% 범위 안에 le_a가 들어가고 비겹침40일 구간은 n=1이다. **한 구간에서 꼬리 선택이 잘된 관측**으로 설명할 수 있으나, 지속적 꼬리 예측능력과 우연의 구분은 확인 못 함. 이미 본 자료의 사후 분석이므로 다른 국면의 비겹침 완결 구간에서 꼬리 수익·집중도가 반복되는지가 필요하다.

## 재현 방법 · 영향 · 고치는 안

- 재현: `python research/handoff/code_20261009_le_a_puzzle.py`. 저장된 DB는 mode=ro, 외부 호출·운영 스크립트 실행 없음. 게이트는 stage1 중앙값30% 및 모델내 frozen_at60분 간격, 앵커 중복제거를 독립 구현했다.
- 영향: 전체 순위 IC가 0근처여도 극상위 일부와 더 긴 보유기간의 수익은 높을 수 있다. 서로 다른 지표를 모순으로 읽거나, 겹친16일을 독립16회로 읽으면 증거를 과대평가한다. 9/13 판정값과 현재 관측값을 섞어 적은 요청 배경도 구분해야 한다.
- 고치는 안(표시 의견): 참고95%의 날짜 iid 가정과 비겹침 n=1을 나란히 표시하고, 정본 판정·가격 기준일·현재 관측을 구분한다. 새 모델·등록·채택 제안 없음.
- 못 한 것: n=1의 독립40일 블록 CI와 새로운 국면의 확정 성과는 확인 못 함. 현재가격의 과거조정, 유니버스 생존편향, 거래비용은 보정하지 않았다. 이미 본 자료의 분석이며 맨 위 몇 종목을 지속해서 맞추는 능력과 한 구간의 우연을 확정적으로 가르지 못한다. 다른 기간의 비겹침 완결 표본에서 같은 꼬리 형태와 집중도 유지 여부가 추가 증거가 된다.

4번 완료. 다음 번호: 5번.
'''
 guard();Path(__file__).with_name('REPLY_20261009_le_a_puzzle.md').write_text(text,encoding='utf-8')
 print('DONE',diffs,'ATTR',attr,'RANDOM',randomrows,'IC',len(icday),icday.mean(),'MARKET',markets)
if __name__=='__main__':main()
