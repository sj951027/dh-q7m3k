"""REQUEST_005: independent holdings implementation. No production module imports."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import sys,sqlite3,json,bisect,platform
import numpy as np,pandas as pd
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[2]
SPECS=[('v30','v3_scores','final_score_v3','20260606'),('lv_b','lowvol_scores','lowvol_score','20260625'),('lv_a','lowvol_scores','lowvol_score','20260625'),('mom_a','lowvol_scores','lowvol_score','20260627'),('mom_b','lowvol_scores','lowvol_score','20260717'),('lv_e','lowvol_scores','lowvol_score','20260901'),('sm_a','lowvol_scores','lowvol_score','20260627'),('sv_a','wu_scores','wu_score','20260715'),('le_a','wu_scores','wu_score','20260715'),('qs_a','wu_scores','wu_score','20260723'),('px_a','wu_scores','wu_score','20260810'),('sv_b','wu_scores','wu_score','20260914'),('ls_t1','large_final',None,'20260806')]
def guard():
 t=datetime.now(timezone(timedelta(hours=9)))
 if t.weekday()<5 and '20:10'<=t.strftime('%H:%M')<'22:30':raise SystemExit('KST batch window')
 return t.isoformat(timespec='seconds')
def ro(p):return sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
def table(h,rs):return '\n'.join(['| '+' | '.join(h)+' |','|'+'|'.join(['---']*len(h))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rs])
def simulate_independent(signals,prices,start,end):
 """Vector quantities, explicit close-of-day trade schedule; no copied return series."""
 dates=list(prices.index);idate={d:i for i,d in enumerate(dates)};ic={c:i for i,c in enumerate(prices.columns)}
 valid=prices.where(np.isfinite(prices)&(prices>0));marks=valid.ffill().fillna(0).to_numpy(float);spot=valid.to_numpy(float)
 trades={idate[d]+1:list(sel) for d,sel in signals.items() if start<=d<=end and sel and d in idate and idate[d]+1<len(dates)}
 q=np.zeros(len(ic));cash=1.;nav=1.;first_trade=None;returns={};trac=[]
 for i,d in enumerate(dates):
  if d<start:continue
  if d>end:break
  v=cash+float(q@marks[i])
  if first_trade is not None and i>first_trade:returns[d]=v/nav-1 if nav>0 else 0
  nav=v
  if i in trades:
   pick=trades[i];q[:]=0;cash=0;budget=v/len(pick);miss=0
   for t in pick:
    j=ic.get(t);p=spot[i,j] if j is not None else np.nan
    if np.isfinite(p):q[j]+=budget/p
    else:cash+=budget;miss+=1
   if first_trade is None:first_trade=i
   trac.append([d,len(pick),miss,float(cash),float(nav)])
 return pd.Series(returns,dtype=float),trac
def metrics(s):
 if not len(s):return {}
 nav=(1+s).cumprod();nav0=np.r_[1.,nav.to_numpy()]
 tail=lambda k:round(float(np.prod(1+s.iloc[-k:])-1)*100,1) if len(s)>=k else None
 return dict(r1=tail(1),r5=tail(5),r20=tail(20),rall=round(float(nav.iloc[-1]-1)*100,1),mdd=round(float((nav/nav.cummax()-1).min())*100,1),mdd_initial=round(float((nav0/np.maximum.accumulate(nav0)-1).min())*100,1),n=len(s),since=str(s.index[0]))
def main():
 started=guard();h=ro(ROOT/'history.db');o=ro(ROOT.parent/'dh-q7m3k-data/ohlcv.db')
 # Main-only prices are the current production cross_sim scope. Full earlier history is used only for a benchmark sensitivity.
 px=pd.read_sql_query("SELECT date,ticker,close,volume FROM daily_ohlcv WHERE date>='20260501'",o)
 allc=px.pivot(index='date',columns='ticker',values='close').sort_index();allv=px.pivot(index='date',columns='ticker',values='volume').reindex_like(allc)
 c=allc.loc['20260601':].copy();v=allv.reindex_like(c);dates=list(c.index);universe=set(c.columns);end=dates[-1]
 extra=pd.read_sql_query('SELECT date,ticker,close FROM daily_ohlcv_extra WHERE date>=?',o,params=('20260601',));extra=extra[~extra.ticker.isin(universe)];ec=extra.pivot(index='date',columns='ticker',values='close').reindex(c.index);ce=c.join(ec)
 scores={};regs={m:r for m,tb,col,r in SPECS}
 for mid,tb,col,reg in SPECS:
  if col:
   scores[mid]=pd.read_sql_query(f'SELECT run_id,ticker,{col} s FROM {tb} WHERE model_id=? AND run_id>=?',h,params=(mid,reg))
  else:
   g=pd.read_sql_query('SELECT run_id,ticker,per,pbr,rim_spread,div_yield FROM large_final WHERE run_id>=?',h,params=(reg,));f=pd.DataFrame(dict(ep=1/g.per.where(g.per>0),bp=1/g.pbr.where(g.pbr>0),rim=g.rim_spread,dv=g.div_yield));r=f.groupby(g.run_id).rank(pct=True);g['s']=r.mean(axis=1).where(r.notna().sum(axis=1)>=2);scores[mid]=g.dropna(subset=['s'])[['run_id','ticker','s']]
  scores[mid].ticker=scores[mid].ticker.astype(str).str.zfill(6)
 def picks(mid,gate=False,prefilter=False,extra_scope=False):
  s=scores[mid];allowed=set(ce.columns) if extra_scope else universe;candidates={}
  for rid in sorted(s.run_id.unique()):
   if gate and rid in ['20260608','20260703']:continue
   i=bisect.bisect_right(dates,rid)-1
   if i>=0:candidates.setdefault(dates[i],[]).append(rid)
  out={}
  for d,rids in candidates.items():
   rid=d if d in rids else min(rids);g=s[s.run_id==rid]
   if prefilter:g=g[g.ticker.isin(allowed)]
   out[d]=[t for t in g.nlargest(20,'s').ticker if t in allowed]
  return out
 baseline={};gated={};pref={};both={};traces={}
 for mid in scores:
  guard();baseline[mid],traces[mid]=simulate_independent(picks(mid),c,regs[mid],end)
  gated[mid],_=simulate_independent(picks(mid,gate=True),c,regs[mid],end)
  pref[mid],_=simulate_independent(picks(mid,prefilter=True),c,regs[mid],end)
  both[mid],_=simulate_independent(picks(mid,gate=True,prefilter=True),c,regs[mid],end)
 doc=json.loads((ROOT/'docs/cross_sim.json').read_text(encoding='utf-8'));assert doc['trailing']['asof']==end
 out=[];full=[];mddrows=[];maxdiff=0;big=[]
 for target in doc['trailing']['rows']:
  mid=target['model'];mine=metrics(baseline[mid]);delta=[]
  for k in ['r1','r5','r20','rall','mdd']:
   a,b=mine[k],target[k];diff=None if a is None or b is None else a-b
   out.append([mid,k,mine['n'],a,b,'—' if diff is None else f'{diff:+.3f}'])
   if diff is not None:maxdiff=max(maxdiff,abs(diff))
   if diff is not None and abs(diff)>.100001:big.append((mid,k,diff))
  assert mine['n']==target['n'],(mid,mine,target)
  full.append([mid,mine['n'],mine['since'],mine['r1'],mine['r5'],mine['r20'],mine['rall'],mine['mdd']])
  if mine['mdd_initial']!=mine['mdd']:mddrows.append([mid,mine['n'],mine['mdd'],mine['mdd_initial'],round(mine['mdd_initial']-mine['mdd'],3)])
 amt=(c*v).rolling(20,min_periods=10).mean()/1e8
 bsignals={d:amt.loc[d][amt.loc[d]>=5].index.to_list() for d in dates};bs,_=simulate_independent(bsignals,c,'20260601',end);bm=metrics(bs)
 benchrows=[[k,len(bs),bm[k],doc['trailing']['bench'][k],f'{bm[k]-doc["trailing"]["bench"][k]:+.3f}'] for k in ['r1','r5','r20']]
 prior=(allc*allv).rolling(20,min_periods=20).mean().shift(1).reindex(c.index)/1e8
 lagged={d:prior.loc[d][prior.loc[d]>=5].index.to_list() for d in dates};bl,_=simulate_independent(lagged,c,'20260601',end);blm=metrics(bl)
 panels=[];panelgate=[];panelbench=[]
 for panel in doc['panels']:
  start=panel['start'];b,_=simulate_independent(bsignals,c,start,end);bb,_=simulate_independent(lagged,c,start,end)
  panelbench.append([start,len(b),metrics(b)['rall'],panel['bench_cum'],metrics(bb)['rall']])
  for target in panel['rows']:
   mid=target['model'];x,_=simulate_independent(picks(mid),c,start,end);y,_=simulate_independent(picks(mid,gate=True),c,start,end);ms=metrics(x);ys=metrics(y)
   panels.append([start,mid,len(x),ms['rall'],target['cum'],f'{ms["rall"]-target["cum"]:+.3f}',ms['mdd'],target['mdd']]);panelgate.append([start,mid,len(y),ys['rall'],f'{ys["rall"]-ms["rall"]:+.3f}'])
 # Attribute effects of specified gates and universe-order ambiguity to first affected signals/returns.
 sens=[];divergences=[];pickdiff=[]
 for mid in scores:
  b,g,p,z=map(metrics,[baseline[mid],gated[mid],pref[mid],both[mid]])
  sens.append([mid,b['n'],g['n'],b['rall'],g['rall'],f'{g["rall"]-b["rall"]:+.3f}',p['rall'],f'{p["rall"]-b["rall"]:+.3f}',z['rall']])
  maps=[('gate',picks(mid),picks(mid,gate=True),baseline[mid],gated[mid]),('prefilter',picks(mid),picks(mid,prefilter=True),baseline[mid],pref[mid])]
  for label,p0,p1,s0,s1 in maps:
   sig=[d for d in sorted(set(p0)|set(p1)) if p0.get(d)!=p1.get(d) and d>=regs[mid]]
   if not sig:continue
   common=s0.index.intersection(s1.index);dd=(s1.reindex(common)-s0.reindex(common)).abs();first=dd[dd>1e-12].index.min() if (dd>1e-12).any() else None
   divergences.append([mid,label,len(sig),sig[0],dates[bisect.bisect_right(dates,sig[0])] if bisect.bisect_right(dates,sig[0])<len(dates) else '없음',first,metrics(s0)['rall'],metrics(s1)['rall']])
   if label=='prefilter':
    for d in sig[:2]:pickdiff.append([mid,d,len(p0.get(d,[])),len(p1.get(d,[])),','.join(sorted(set(p1.get(d,[]))-set(p0.get(d,[]))))])
 # Supplemental prices intentionally separate, since cross_sim does not currently load them.
 lex,_=simulate_independent(picks('ls_t1',extra_scope=True),ce,regs['ls_t1'],end);lem=metrics(lex)
 # Five requested categories, including two missing-price subcases, plus fixed-quantity control.
 D=['d0','d1','d2','d3','d4','d5'];toy=[]
 def check(label,cols,sig,exp):
  frame=pd.DataFrame(cols,index=D,dtype=float);got,_=simulate_independent(sig,frame,'d0','d5');assert list(got.index)==list(exp) and np.allclose(got.values,list(exp.values()),rtol=0,atol=1e-12),(label,got,exp);toy.append([label,len(got),str({d:round(r*100,6) for d,r in got.items()}),'일치'])
 check('1 첫 매수 전날 상승 제외',dict(A=[100,110,121,121,121,121]),{'d0':['A']},{'d2':.1,'d3':0,'d4':0,'d5':0})
 check('2 교체일 기존 보유 귀속',dict(A=[100,100,100,120,120,120],B=[50,50,50,50,60,60]),{'d0':['A'],'d2':['B']},{'d2':0,'d3':.2,'d4':.2,'d5':0})
 check('3 신호 없는 날 수익 복사 없음',dict(A=[100,100,110,110,121,121]),{'d0':['A']},{'d2':.1,'d3':0,'d4':.1,'d5':0})
 check('4a 미매수 몫 현금',dict(A=[100,100,110,110,110,110],B=[50,np.nan,50,50,50,50]),{'d0':['A','B']},{'d2':.05,'d3':0,'d4':0,'d5':0})
 check('4b 보유 결측과 재개',dict(A=[100,100,100,100,100,100],B=[50,50,50,np.nan,60,60]),{'d0':['A','B']},{'d2':0,'d3':0,'d4':.1,'d5':0})
 check('5 마지막 예약 이익 제외·기존평가 포함',dict(A=[100,100,100,100,100,110],B=[50,50,50,50,50,50]),{'d0':['A'],'d4':['B'],'d5':['A']},{'d2':0,'d3':0,'d4':0,'d5':.1})
 check('수량고정 추가',dict(A=[100,100,200,100,100,100],B=[50,50,50,50,50,50]),{'d0':['A','B']},{'d2':.5,'d3':-1/3,'d4':0,'d5':0})
 # Drawdown counterexample: initial capital must count as a high-water point.
 drawtoy=metrics(pd.Series([-.1,0],index=['d2','d3']));assert drawtoy['mdd']==0 and drawtoy['mdd_initial']==-10
 txt=f'''# REPLY_005 — cross_sim 정정본 독립 재현 (SOL 7번)

검토 {started}. 환경: Python {platform.python_version()}, pandas {pd.__version__}, numpy {np.__version__}, Windows. DB mode=ro. **build_cross_sim.py 및 운영모듈 import/실행 없음**. 독립 구현의 현재코드 조건 계산은 JSON 생성 {doc['generated']}·가격 기준 {end}와 대조했다. 9/16 고정본을 지금 DB로 동일하게 복원했다고 주장하지 않는다.

결론: 보유 상태의 진입지연·교체귀속·결측처리는 손계산과 일치한다. 하지만 **현재 운영코드는 요청서의 게이트 run n=2개 제외를 구현하지 않았다.** 또한 상위20을 고른 뒤 가격종목으로 거르는 순서, 벤치마크의 전일 의미, 초기NAV를 빠뜨린MDD, 마지막 '미실현 제외'의 의미는 별도로 명시해야 한다. 현재 JSON수치의 재현과 요청서 규약의 일치는 별개다.

## 1. 현재 구현 조건으로 독립 재현

두 구현이 같은 버그를 공유하지 않도록 일별 보유수량 벡터와 명시적인 다음날 체결일정으로 처음부터 계산했다. 가격결손 평가에는 유효양수가격을 전일에서만 이어 사용하고, 매수는 해당일 원가격이 있는 경우만 허용한다. 신호가 없으면 수량을 유지한다. 현재운영 조건을 맞추기 위해 **게이트미제외·상위20후가격표필터·본시세만·신호일20일평균(최소10행)**을 먼저 사용했다.

| 비교 범위 | 표본 n | 결과 |
|---|---|---|
| trailing 모델 | {len(full)}모델 | 1/5/20일·등록후누적·MDD를 아래에 전수대조 |
| 공통창 | {len(doc['panels'])}창·{len(panels)}모델행 | 누적·MDD·일수대조 |
| 고정 손계산 | 요청5범주·세부{len(toy)}건 | 전부일치 |

전수 값(반올림은JSON과동일):

'''+table(['모델','수익일 n','첫 수익일','r1 %','r5 %','r20 %','누적 %','MDD %'],full)+'\n\n'+table(['모델','항목','수익일 n','내 값','JSON 값','차이 %p'],out)+f'''

trailing 비교 최대차이 {maxdiff:.3f}%p, 0.1%p 초과 n={len(big)}개. None은 유효20수익일 미달이며0%가 아니다. 결정론적 재현오차이므로95%CI를 붙이지 않았다.

'''+table(['창 시작','모델','수익일 n','내 누적 %','JSON 누적 %','차이 %p','내MDD %','JSON MDD %'],panels)+'\n\n'+table(['벤치 항목','수익일 n','내 값 %','JSON 값 %','차이 %p'],benchrows)+'\n\n'+table(['창 시작','수익일 n','내벤치누적 %','JSON %','신호일이전20일해석 %'],panelbench)+'''

## 2. 요청 규약과 운영 구현이 다른 지점의 영향

아래는 JSON과의 단순 오차가 아니라 조건을 하나씩 바꾼 비교다. 게이트 제외 후에도 신호없는 날의 기존보유는 유지한다. '가격표 안에서 먼저 상위20'은 요청문구의 다른 해석이며 운영은 상위20후필터다. 둘을 섞어 재현실패로 쓰지 않았다.

'''+table(['모델','현재수익일 n','게이트후 n','현재누적 %','게이트제외 %','차이 %p','가격필터먼저 %','차이 %p','둘다 %'],sens)+'\n\n'+table(['모델','바꾼조건','달라진신호 n','첫신호앵커','교체일','첫공통수익차이일','현재누적 %','변경누적 %'],divergences)+'''

게이트 차이는20260608·20260703 앵커에서 시작한다. 6/8 제외는v30의 첫진입과 첫수익일도 바꾼다. 7/3 제외는 그다음거래일 교체를 취소하므로 당일수익까지 즉시 바뀌는 것이 아니라 이후 보유수익이 갈린다. 공통창별 영향:

'''+table(['창 시작','모델','게이트후수익일 n','게이트후누적 %','현재대비 %p'],panelgate)+'''

상위20후필터 때문에 줄어든 바구니 예시(영향 있는 각 모델의 첫2신호):

'''+table(['모델','신호일','현재바구니 n','가격필터먼저 n','추가종목'],pickdiff)+f'''

보충표 n={len(ec.columns)}종목은 현재 build_cross_sim.py에 연결돼 있지 않다. 본시세 우선으로 ls_t1에만 보충을 넣고 기존 '상위20후필터'를 유지하면 수익일 n={lem['n']}, 등록후누적 {lem['rall']:+.1f}%, r20 {lem['r20']:+.1f}%, MDD {lem['mdd']:+.1f}%다(현재누적 {metrics(baseline['ls_t1'])['rall']:+.1f}%). 이번 ls_t1 바구니에는 보충에 따른 값 변화가 없었다. 이는 현재JSON의 오류재현이 아니라 **시세범위를바꾼민감도**다. 다른트랙이나벤치에는보충표를넣지않았다. 10/3 보충시세변경이 모든페이지에적용됐다고읽으면안된다.

## 3. MDD 초기자산 누락

운영 MDD는 첫 수익후NAV부터 cummax를 시작한다. 최초진입자산1을 최고점에포함하지않아 첫날손실을낙폭에반영하지못할수있다. 가짜 수익[-10%,0%], n=2에서 운영식MDD0%, 초기자산포함식−10%를재현했다. 현재실자료의 차이 있는 모델:

'''+(table(['모델','수익일 n','운영 MDD %','초기자산포함 %','차이 %p'],mddrows) if mddrows else '현재 trailing에서 반올림0.1%p수준 차이 있는 모델 n=0. 이 자료에서 영향이 없어도 가짜반례는남는다.')+f'''

## 4. 고정 사례 손계산

'''+table(['사례','수익행 n','독립 계산 일수익 %','손계산대조'],toy)+'''

범주1: d0 A100→d1 110→d2 121에서110에산후+10%만포함. 범주2: d3교체일에는기존A100→120의+20%, 다음d4에는새B50→60의+20%. 범주3:가격이멈춘날0%여서이전+10%복사안함. 범주4:처음못산B몫은현금, 보유중B결측은50평가뒤60재개시반영. 범주5:d4신호의d5진입과d5신호의기간밖진입에는수익을만들지않고, 기존A의d5종가평가+10%는포함한다.

## 5. 모호한 규약 및 현재 변경점

- '마지막 종가까지 실현분만/미실현 제외': 현재코드와고정테스트는 **마지막날까지 보유한 미매도 평가손익을 포함**하고 기간밖 미래수익·마지막예약바구니수익만제외한다. 매도해 확정한실현손익만뜻한다면현재코드와다르다.
- '상위20, 시세DB에있는종목만': 먼저가격표종목으로제한한뒤20개인지, 전체점수20에서가격표밖을빼는지불명확. 현재는후자라20미만바구니이며 남은종목에재동일가중, 빠진종목몫은현금이아니다. 현금처리는 **선정됐지만교체일가격만없을때** 적용한다.
- '전일20일평균': t+1체결의전일=t이면현재 amt20[t]는그때알수있는값이다. 신호t의전일=t−1까지를뜻하면shift(1)이필요하다. 위별도벤치열은후자·완전20관측으로계산했다. 현재 trailing은 {bm['r1']:+.1f}/{bm['r5']:+.1f}/{bm['r20']:+.1f}%이고 후자해석은 {blm['r1']:+.1f}/{blm['r5']:+.1f}/{blm['r20']:+.1f}% (각 r1/r5/r20, 수익일 n={len(bs)}/{len(bl)})다. 최소10관측허용과6/1가격절단도요청서에는없던구현세부다.
- 비거래일run은등록일필터후직전거래일로매핑하지만그앵커가시뮬레이션시작보다앞이면버린다. 예:v30 6/6등록run→6/5앵커는시작6/6밖이라진입예약에쓰이지않는다. 등록일첫바구니를포함할지규약에명시가필요하다.
- 게이트: 요청서는두run제외,현재생성기는미제외. 이번코드는현재조건재현후제외효과를따로계산했다. 생산게이트를바꾸지않았다.
- 동점: nlargest는원SQL반환순서에따라동점을고른다. ticker정렬등추가규칙은없다. 현재DB순서를보존했고, 다른환경/DB재작성에도동점선정이완전히같다는보장은확인못함.
- 빈선택은보유유지,매수0종목신호를전량현금화로해석하지않는다. 비용0·주식분할조정가격·배당총수익별도미반영·결손평가시실제로정지종목을팔수있는지는검증안함.
- 현재모델n=13: 요청11개에10/3 le_a·sm_a가추가됨. 공통창의모델그룹은여전히기존목록이라두모델은trailing만추가. px_a는7/24창보다등록이늦어그창에서대기,8/10창에는포함. 보충표는다른대형표와달리cross_sim에서는미사용.

## 재현 방법 · 영향 · 고치는 안

- 재현: `python research/handoff/code_005_cross_sim.py`. DB읽기전용·현재JSON읽기, 본REPLY만쓴다. 수익경로를숫자배열로복사하지않고수량과현금으로계산했다.
- 영향:게이트미제외·바구니필터순서·초기MDD·벤치신호시점해석에따라누적과낙폭이다르다. 현재JSON과맞는다는것만으로요청규약을만족했다고말하면안된다.
- 고치는 안(답파일에만):게이트처리와바구니필터·최초신호/최후평가·MDD초기기준·벤치평균창의정의를명확히하고,교체일과첫수익일을테스트에고정한다. 코드·DB·docs는수정하지않았다. 등록·채택제안없음.
- 못 한 것:9/16당시DB스냅샷과가격정정전값이없어9/16JSON의완전한당시입력복원은확인못함. 실거래가능성·수수료/세금·운영배포는미검증. 이는이미본자료의사후재현이며미래수익의증거가아니다. 결정론적재현·고정사례에는표본95%CI를붙이지않았다. 큰중간파일없음.

7번 완료. 이번 요청2~7번 종료.
'''
 guard();Path(__file__).with_name('REPLY_005_cross_sim_replication.md').write_text(txt,encoding='utf-8')
 print('DONE maxdiff',maxdiff,'big',big,'SENSITIVITY',sens,'MDD',mddrows,'EXTRA',lem)
if __name__=='__main__':main()
