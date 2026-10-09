"""Offline ls_t1 audit. Never executes large_verdict.run/main or collectors."""
import sys,sqlite3,json,subprocess,ast
from pathlib import Path
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import numpy as np,pandas as pd
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[2]
def guard():
 t=datetime.now(timezone(timedelta(hours=9)))
 if t.weekday()<5 and '20:10'<=t.strftime('%H:%M')<'22:30':raise SystemExit('KST batch window')
 return t.isoformat(timespec='seconds')
def ro(p):return sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
def table(h,rs):return '\n'.join(['| '+' | '.join(h)+' |','|'+'|'.join(['---']*len(h))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rs])
def stat(v):
 a=np.asarray(v,float)
 if not len(a):return dict(ic=None,n=0,ci=[None,None],pos=None)
 rng=np.random.default_rng(7);bo=np.array([rng.choice(a,len(a)).mean() for _ in range(2000)])
 return dict(ic=round(float(a.mean()),4),n=len(a),ci=[round(float(x),4) for x in np.quantile(bo,[.025,.975])],pos=round(float((a>0).mean()),3))
def main():
 started=guard();hc=ro(ROOT/'history.db');oc=ro(ROOT.parent/'dh-q7m3k-data/ohlcv.db')
 px=pd.read_sql_query('SELECT date,ticker,close FROM daily_ohlcv',oc);ex=pd.read_sql_query('SELECT date,ticker,close FROM daily_ohlcv_extra',oc)
 base=px.pivot(index='date',columns='ticker',values='close').sort_index();ex=ex[~ex.ticker.isin(base.columns)];extra=ex.pivot(index='date',columns='ticker',values='close').reindex(base.index)
 close=base.join(extra);dates=list(close.index);di={d:i for i,d in enumerate(dates)}
 lg=pd.read_sql_query('SELECT run_id,market,ticker,per,pbr,rim_spread,div_yield FROM large_final',hc)
 factors=pd.DataFrame({'ep':1/lg.per.where(lg.per>0),'bp':1/lg.pbr.where(lg.pbr>0),'rim':lg.rim_spread,'dv':lg.div_yield})
 rk=factors.groupby(lg.run_id).rank(pct=True);lg['score']=rk.mean(axis=1).where(rk.notna().sum(axis=1)>=2);s=lg.dropna(subset=['score'])
 cnt=pd.read_sql_query('SELECT run_id,COUNT(*) n FROM stage1_oversold GROUP BY run_id',hc);partial=set(cnt.loc[cnt.n<cnt.n.median()*.3,'run_id']);dbl=set();gaterows=[]
 for tb in ['v3_scores','lowvol_scores','wu_scores']:
  fa=pd.read_sql_query(f'SELECT run_id,model_id,frozen_at FROM {tb}',hc);fa['ts']=pd.to_datetime(fa.frozen_at,utc=True,errors='coerce');sp=fa.groupby(['run_id','model_id']).ts.agg(['min','max']);sp['gap']=(sp['max']-sp['min']).dt.total_seconds()/60
  for (rid,mid),rr in sp[sp.gap>=60].iterrows():dbl.add(rid);gaterows.append([rid,mid,tb,str(rr['min']),str(rr['max']),f'{rr.gap:.2f}'])
 excluded=partial|dbl
 def anchor(rid):
  for k in range(6):
   d=(datetime.strptime(rid,'%Y%m%d')-timedelta(days=k)).strftime('%Y%m%d')
   if d in di:return di[d]
 def select():
  cand={}
  for rid in sorted(s.run_id.unique()):
   if rid<'20260806' or rid in excluded:continue
   t=anchor(rid)
   if t is not None:cand.setdefault(t,[]).append(rid)
  return {t:dates[t] if dates[t] in rs else min(rs) for t,rs in cand.items()}
 kept=select();weeks={}
 for t,rid in sorted(kept.items()):weeks.setdefault(datetime.strptime(dates[t],'%Y%m%d').isocalendar()[:2],(t,rid))
 weekly=dict(weeks.values())
 def measure(frame,keeps,horizon):
  jumps=frame.pct_change(fill_method=None).abs();out=[];detail=[]
  for t,rid in sorted(keeps.items()):
   if t+1+horizon>=len(frame):continue
   ret=frame.iloc[t+1+horizon]/frame.iloc[t+1]-1;ret=ret.where(jumps.iloc[t+2:t+2+horizon].max()<=.32);day=[];e=[]
   for mk,g in s[s.run_id==rid].groupby('market'):
    z=g.set_index('ticker').score;rr=ret.reindex(z.index);ok=z.notna()&rr.notna()
    if ok.sum()<8 or z[ok].nunique()<3 or rr[ok].nunique()<3:continue
    day.append(np.corrcoef(z[ok].rank(),rr[ok].rank())[0,1]);e.append((rr[ok].reindex(z[ok].sort_values(ascending=False).head(20).index).mean()-rr[ok].median())*100)
    detail.append([dates[t],mk,int(ok.sum()),float(rr[ok].median()*100),float(rr[ok].mean()*100)])
   if day:out.append((t,float(np.mean(day)),float(np.mean(e))))
  return stat([v for t,v,e in out]),out,detail
 rows=[];stats={};nonovs={}
 for horizon in [20,60,120]:
  for label,ks in [('일간',kept),('주간',weekly)]:
   st,out,dd=measure(close,ks,horizon);stats[(label,horizon)]=st
   rows.append([horizon,label,len(ks),sum(t+1+horizon<len(close) for t in ks),st['n'],st['ic'],st['ci'],st['pos']])
  if horizon>=60:
   no={};last=None
   for t,rid in sorted(weekly.items()):
    if last is None or t-last>=horizon:no[t]=rid;last=t
   nonovs[horizon]=no
 # Execute only extracted pure functions, with synthetic pandas frames. No project imports.
 namespace=dict(np=np,pd=pd,ENTRY_LAG=1,HORIZONS=[60,120],MIN_GROUP=8,TOP_EXC=20,JUMP_CAP=.32,BOOT=2000)
 tree=ast.parse((ROOT/'leaderboard.py').read_text(encoding='utf-8-sig'))
 for node in tree.body:
  if isinstance(node,ast.FunctionDef) and node.name in ['anchor','dedupe_by_anchor','model_ic']:exec(compile(ast.Module(body=[node],type_ignores=[]),'pure_lb_functions','exec'),namespace)
 toy_dates=pd.bdate_range('2026-01-01',periods=182).strftime('%Y%m%d').to_list();tdi={d:i for i,d in enumerate(toy_dates)};tick=[str(i) for i in range(12)]
 toy=pd.DataFrame({t:100*np.exp(np.arange(182)*(.0001+i*.00001)) for i,t in enumerate(tick)},index=toy_dates)
 ts=pd.DataFrame(dict(run_id=[toy_dates[0]]*12,market=['kospi']*12,ticker=tick,score=np.arange(12)))
 fun=namespace['model_ic'];ref=fun(ts,toy,len(toy),tdi,set(),reg=toy_dates[0]);changed=toy.copy();changed.iloc[122:]*=np.arange(1,13)
 assert fun(ts,changed,len(toy),tdi,set(),reg=toy_dates[0])==ref
 assert fun(ts,toy.iloc[:61],61,{d:i for i,d in enumerate(toy_dates[:61])},set(),reg=toy_dates[0])[60]['n']==0
 assert fun(ts,toy.iloc[:62],62,{d:i for i,d in enumerate(toy_dates[:62])},set(),reg=toy_dates[0])[60]['n']==1
 toytests=3
 # Historical committed JSON is evidence of what was displayed; recomputed masked prices isolate the known gap only.
 history=[]
 for rev in ['233c875','6ef266e','384feac','1aa32b8','dc8e623','03c0d5f']:
  guard();r=subprocess.run(['git','show',rev+':docs/leaderboard.json'],cwd=ROOT,capture_output=True)
  if r.returncode:continue
  doc=json.loads(r.stdout);m=next(x for x in doc['models'] if x['model']=='ls_t1')
  committed=subprocess.check_output(['git','show','-s','--format=%ad','--date=iso',rev],cwd=ROOT,text=True).strip()
  history.append([rev,committed,m['h20']['n'],m['h20']['ic'],m['h20']['ci'],m.get('exc20')])
 sensitivity=[]
 for cutoff in ['20261002','20261006','20261007','20261008']:
  now=close.loc[:cutoff].copy();gap=now.copy();gap.loc[gap.index>'20261002',extra.columns]=np.nan
  full,_,d1=measure(now,kept,20);masked,_,d0=measure(gap,kept,20)
  sensitivity.append([cutoff,full['n'],full['ic'],full['ci'],masked['ic'],masked['ci'],sum(x[2] for x in d1),sum(x[2] for x in d0)])
 current=json.loads((ROOT/'docs/leaderboard.json').read_text(encoding='utf-8'));current=next(x for x in current['models'] if x['model']=='ls_t1')
 assert stats[('일간',20)]==current['h20'],(stats,current)
 weeklyrows=[[w[0],w[1],dates[t],rid,dates[t+1] if t+1<len(dates) else '미진입'] for w,(t,rid) in sorted(weeks.items())]
 future=[]
 for horizon in [60,120]:future.append([horizon,len(nonovs[horizon]),sum(t+1+horizon<len(close) for t in nonovs[horizon]),min(kept)+1+horizon-len(close)+1])
 countrows=[[rid,int(cnt.loc[cnt.run_id==rid,'n'].iloc[0]),f'{cnt.n.median():.1f}',f'{cnt.n.median()*.3:.1f}'] for rid in sorted(partial)]
 detail=measure(close,kept,20)[2]
 txt=f'''# REPLY — 5. ls_t1 판정 스크립트 사전 점검

검토 {started}, 가격 마지막 {dates[-1]}. 결론: h60·h120 계산의 미래 가격 사용은 재현하지 못했고, 현재 완결 n=0으로 대기다. 그러나 **최소8·주 첫 앵커·비겹침 라벨 규칙은 사전등록 원문과 동일한 규칙이 아니며**, 정본의 전 유니버스 IC와 구현의 시장별 IC 평균도 다르다. 이미 h20·현재 평가·선택 규칙 메모가 화면에 공개돼 있어 판정일 최초 열람 구조가 아니다.

`large_verdict.py`를 CLI로 실행하지 않았다. 기본과 --check 모두 research 상태 파일을 덮어쓰고 --check는 leaderboard.main도 부른다. 본 계산은 별도 코드·mode=ro로 수행했다. 미래 경계는 소스에서 추출한 순수 model_ic 함수만 가짜 자료로 시험 n={toytests}, 모두 통과했다.

## (1) 문서와 구현의 규칙 대조

| 항목 | 사전등록/설계 | 구현·판정 |
|---|---|---|
| 호라이즌 | §9 h60·h120 | 동일, 둘을 별도 라벨; 종합 판정 조합 규칙은 없음 |
| 리밸런스 | §9 주간/월간, prereg 주간 | ISO주 첫 유효 앵커1개로 구체화; 주중 결손이면 다음 유효일 |
| 최소 표본 | 작으면 보수적; 숫자 미명시 | 날짜상 닫힌 수와 실제 IC n 둘 다8이상 |
| 비겹침 | 원문에 세부 없음 | 이전 앵커와 h거래일 이상 간격. '유의' 유지에는 실제 계산 n≥2와CI하단>0 필요 |
| IC | §9 '전 유니버스 Spearman' | 시장별 Spearman→시장 동일가중 평균, 최소8종목·3순위; 시장간 순위쌍은 버림 |
| 이상치 | §9 구체 규칙 미명시 | leaderboard의 일수익 절댓값32% 초과 종목 제거 |
| 방향 일관성 | §9 세부 미명시, §11 '주별≥60%' | stat.pos=선택 앵커 IC 양수 비율. 주간 정본은 주당1개라 주별과 같지만 일간 줄은 날짜 비율 |

스크립트 머리말도 주간·8개·비겹침을 10/3 구현자 결정으로 적었다. 이 기록은 원문 규칙 자체를 바꾸지 않는다. n=8의 겹친 주간 표본은 h60 약12주·h120 약24주 구간을 공유한다. '비겹침 n≥2'는 안전장치지만 n=2 자체를 넓은 일반화 근거로 삼을 수 없다. 첫 창 종료는 판정일이 아니다.

주간 앵커 실측:

'''+table(['ISO연도','주','앵커일','run','진입일'],weeklyrows)+'\n\n'+table(['h','기준','선택 n','날짜상 종료 n','IC계산 n','IC','날짜iid95%','양수비율'],rows)+'\n\n'+table(['h','비겹침 선택 n','완료 n','첫 창까지 남은 거래일'],future)+f'''

현재 일간 선택 n={len(kept)}·주간 n={len(weekly)}. 보관된 status의 일간39와 leaderboard의OOS {current['oos_days']}는 다르다. 현재 leaderboard 소스는 선택 앵커수를 OOS로 쓰므로 현재 DB로 다시 계산하면39다. 이 저장 JSON의 OOS 38이 만들어진 당시 입력·실행시점은 확인 못 함(JSON 자체에 기준일·생성시각 필드가 없다). h20 실제 계산 n={stats[('일간',20)]['n']}·IC·95%·양수비율은 현재 leaderboard.json과 전부 일치했다. h60·120의 유효95%는 완료 n=0이라 확인 못 함.

## (2) 미래정보와 경계

선행수익 = close[t+1+h]/close[t+1]−1, t+1+h<N일 때만 계산. 마지막 h수익에 t+h를 쓰지 않는다. 장난감 n=12종목·182거래일에서 (a) t+122 이후 가격을 바꿔도 h60/120 불변, (b)61행에는 h60 n=0, (c)62행에는h60 n=1을 확인했다. 점프컷은 진입 다음날~종료일만 사용한다. 미래수익으로 종목을 제외하는 규칙은 실시간 거래선택이 아닌 성과측정의 이상치 필터다. 현재 저장가격의 사후 수정과 재무 원자료의 당시 알려진 시점은 이 시험으로 검증하지 못한다.

## (3) 10/3~7 보충표 공백의 흔적

Git에 실제 남은 당시 leaderboard(JSON) n={len(history)}건:

'''+table(['commit','커밋시각(KST)','h20 n','IC','95%','exc20'],history)+'''

현재 가격을 각 기준일에서 잘라 보충표의10/2 이후 가격만 없앴을 때의 민감도(당시DB 원본이 없어 완전복원은 아님):

'''+table(['기준일','h20 n','현재보충 IC','95%','공백가정 IC','95%','현재유효 자리 n','공백유효 자리 n'],sensitivity)+'''

10/6 저장 IC +0.0449와10/7 저장 +0.0364는 현재가격의 공백가정 재계산과 소수4자리·95%까지 일치했다(각 n=17·18). 같은 기준일의 보충 후 재계산은 +0.0423·+0.0326이다. 따라서 **공백 중 생성한 h20 참고값에 누락의 흔적이 남았다**. 10/8 저장값은 현재보충 계산과 일치한다. 10/3은 주말이어서 그 날짜 가격행이 없어도 누락이 아니다. 해당기간 실제 거래일은10/6·10/7이다. 현재 보충표 최근행 fetched_at은10/8 재조회로 덮여 있어 최초 채운 시각은 이 열로 확인 못 함. 당시 저장 JSON은 실제 표시된 값의 증거지만 지금 DB와의 차이 전부를 공백 탓으로 돌릴 수 없다(가격 정정·시세연장·모델 실행·코드 변화 포함). h60/120은 당시도 지금도 완료 n=0이므로 이 호라이즌의 과거 판정숫자가 오염됐다는 증거는 없다.

## (4) 두 게이트 run

'''+table(['부분실행 run','stage1 n','전체 중앙 n','30% 경계'],countrows)+'\n\n'+table(['이중 run','모델','표','최초','최후','간격분'],gaterows)+f'''

실측 제외 run n={len(excluded)}: {', '.join(sorted(excluded))}. 부분실행은 중앙30% 미달, 이중실행은 **같은 모델내**60분 이상 간격을 만족한다. 단순 시각 distinct수나 모델간 백필 차이를 사용하지 않아 규칙과 맞는다. 둘 다8/6 등록 전이므로 이번 ls_t1 OOS 제외에 직접 영향 n=0. '맞다'는 저장된 게이트 규칙 재현 의미이며 최초 수집 실패의 모든 원인은 로그 없이는 확인 못 함.

## (5) 대조군 중앙값

large_verdict 정본 IC에는 대조군 수익을 빼지 않는다. leaderboard.model_ic의 exc20 관측은 같은 run×시장 **점수가 있고 양끝가격·점프컷을 통과한 large_final 후보**의 중앙값이며 전체 상장종목 중앙값이 아니다. top20도 이 유효집합에서 다시 뽑으므로 처음 점수상위20과 다를 수 있다. 현재 h20 대조 계산 자리 n={sum(x[2] for x in detail)}. 예시:

'''+table(['앵커','시장','유효 n','후보 중앙 수익 %','후보 평균 수익 %'],[[a,b,n,f'{m:+.4f}',f'{av:+.4f}'] for a,b,n,m,av in detail[:6]])+'''

반면 build_scoreboard의 ls_t1 시장비교는 후보 **평균**이고, build_large_test.insample_ic는 전 run 백필을 포함한 시장을 합친 IC이며 점프컷·게이트가 다르다. 같은 '대형 성적'이라도 정본과 같지 않다. §9/prereg에는 후보 중앙 대조 수익의 별도 정의가 없어 '정본의 중앙값 정의와 일치'는 확인 못 함; 현재 코드끼리는 위처럼 차이가 명시된다.

## (6) 판정 전 공개 여부

- docs/leaderboard.json: ls_t1 등록 후 h1/3/5/10/20 IC와 exc20 관측이 이미 저장됨.
- docs/scoreboard.json: ls_t1 완료40일/현재평가를 표시하는 구조. 이번 기준에서는 오래 보유한 현재 평가가 있어 방향을 미리 관찰할 수 있다.
- docs/_large_test.html: 과거 목록→현재 종가 등락과 9/14 '어떤 걸 고르는 게 좋았나' 메모(백필 포함, 필터 조합 성적)가 보임. 판정과 별개라는 각주는 있지만 수익 관측 자체는 공개됐다. '비공개 미링크'라는 prereg 설명과 현재 파일의 '목록에 연결돼 있고 주소로 열린다'도 다르다.
- research/large_verdict_status.md: h60·h120 숫자는 현재n=0으로 없음. **정본 h60/120의 값이 미리 새었다는 증거는 없으나, 전체 성과를 판정일 처음 본다는 구조는 아니다.**

## 재현 방법 · 영향 · 고치는 안

- 재현: `python research/handoff/code_20261009_large_verdict_precheck.py`. 생산main·수집기를 부르지 않고 DB읽기 전용 및 Git 저장본을 비교한다.
- 영향: 구현의8개·시장평균IC·비겹침보수화를 원문 그대로라 설명하면 판정 기준의 출처를 오인한다. h20·40·현재평가·백필 메모는 이미 본 자료라 나중판정의 완전한 눈가림 근거가 될 수 없다.
- 고치는 안(문서에만): 실제 고정된 규칙과 원문에 없는 구현결정을 명확히 기록하고, 전유니버스IC/시장별평균 중 정본 정의와 h60·h120종합 처리의 불일치를 해소할 필요가 있다. 비겹침 표본수·관측 공개범위·기준일·유효후보수를 결과 옆에 표시한다. 코드나 기존 문서를 수정하지 않았다. 등록·채택 제안 없음.
- 못 한 것: 당시DB원본·최초관측가격·재무공시시점검증과 미래 완결60/120일 성과는 확인 못 함. n이 작은 iid구간은 참고이며 비겹침유효CI는 지금 확인 못 함. 이미 본 자료에 대한 사후 점검이라는 한계가 있다.

5번 완료. 다음 번호: 6번.
'''
 guard();Path(__file__).with_name('REPLY_202610xx_large_verdict_precheck.md').write_text(txt.replace('不明','확인 못 함'),encoding='utf-8')
 print('DONE',rows,'KEPT',len(kept),'SENSITIVITY',sensitivity,'HISTORY',history)
if __name__=='__main__':main()
