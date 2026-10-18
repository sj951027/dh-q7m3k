from pathlib import Path
import sqlite3, ast, datetime as dt
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).with_name('REPLY_20261018_short_horizon.md')
MODELS={'v30':('v3_scores','final_score_v3','20260606'),'le_a':('wu_scores','wu_score','20260715'),'lv_b':('lowvol_scores','lowvol_score','20260625'),'lv_e':('lowvol_scores','lowvol_score','20260901')}
def ro(p):
 c=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True); c.execute('pragma query_only=ON'); return c
# Only pure gate helpers, no operational imports or network.
tree=ast.parse((ROOT/'leaderboard.py').read_text(encoding='utf-8'))
ns={}; exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('anchor','dedupe_by_anchor')],type_ignores=[]),'gate_helpers','exec'),ns)
def stats(values,dates):
 a=np.asarray(values,float); mask=np.isfinite(a); a=a[mask]; ds=np.asarray(dates)[mask]
 if len(a)==0:return 'n=0; 확인 못 함'
 rng=np.random.default_rng(7); b=a[rng.integers(len(a),size=(4000,len(a)))].mean(1)
 weeks=pd.to_datetime(ds).to_period('W-SUN'); groups=[a[weeks==w] for w in sorted(set(weeks))]
 ix=np.random.default_rng(7).integers(len(groups),size=(4000,len(groups)))
 sums=np.array([g.sum() for g in groups]); counts=np.array([len(g) for g in groups]); wb=sums[ix].sum(1)/counts[ix].sum(1)
 ci=np.percentile(b,[2.5,97.5]); wc=np.percentile(wb,[2.5,97.5]); bc=np.percentile(b,[2.5/12,100-2.5/12])
 return f'{a.mean():+.4f}; n={len(a)}; 날짜[{ci[0]:+.4f},{ci[1]:+.4f}]; 주[{wc[0]:+.4f},{wc[1]:+.4f}]({len(groups)}주); /12[{bc[0]:+.4f},{bc[1]:+.4f}]'
def main():
 h=ro(ROOT/'history.db'); p=ro(ROOT.parent/'dh-q7m3k-data/ohlcv.db')
 px=pd.read_sql("select ticker,date,open,close,market from daily_ohlcv where date>='20260601'",p)
 dates=sorted(px.date.unique()); didx={d:i for i,d in enumerate(dates)}
 close=px.pivot(index='date',columns='ticker',values='close').reindex(dates).astype(float)
 op=px.pivot(index='date',columns='ticker',values='open').reindex_like(close).astype(float)
 close=close.where(close>0); op=op.where(op>0)
 mk=px.pivot(index='date',columns='ticker',values='market').reindex_like(close)
 lines=['# REPLY — 단기 보유 독립 조사 (2026-10-18)','', '## 범위·정의', '', '실측: DB mode=ro + query_only, 외부 호출·운영 파일 수정 없음. 금지된 Claude 코드·보고서·출력 폴더는 읽지 않았다. 필수 worklog에 Claude의 요약 결론이 있어 완전한 눈가림은 아니다.', '', 'A=t+1 시가→종가, B=t+1 종가→t+2 종가, C=t+1 시가→t+2 종가, G=t 종가→t+1 시가. 수정 여부는 DB 메타만으로 독립 확인 못 함; 요청대로 저장 open/close 사용. 부분 20260608·이중 20260703 제외. 등록 필터 후 leaderboard의 순수 anchor/dedupe 함수를 AST로 추출해 사용.', '', '시장별 점수 내림차순, 동점은 ticker 오름차순. 상위10·10분위는 수익 결측 제거 전에 점수로 고정(미래 시세 유무로 대체 종목을 뽑지 않음). 10분위 개수=ceil(해당 시장 목록 수×0.1). 시세 없는 선택 종목은 평균에서 제외하며 현금 수익으로 대체하지 않음. 시장 비교군은 해당 지평 필요 시세가 있고 점프컷을 통과한 daily_ohlcv 전 종목. 시장 구분은 앵커 당일 값을 사용.', '', '모든 지평에 t+1·t+2 close/전일 close의 절대 변화 >32% 제외를 공통 적용. 필요한 세 종가가 없어 점프컷 검증 불가하면 제외. A도 t+2까지 확인된 앵커만 사용(요청의 공통 점프컷). 주 블록은 월~일을 복원추출하고 뽑힌 날짜를 합쳐 평균. n=앵커 수; 수익·초과·비율 단위는 % 또는 %p, IC는 무단위. 날짜/주 4,000회 seed 7, /12는 날짜 구간의 Bonferroni 감도.', '', f'시세 마지막 날: {dates[-1]}.', '', '## 1. 모델 4 × 지평 3 (실측)', '', '|모델·지평|지표|평균; n; 날짜 95%; 주 95%; /12 감도|','|---|---|---|']
 audits=[]; candidates={}; totals={}
 for model,(table,col,reg) in MODELS.items():
  s=pd.read_sql(f"select run_id,market,ticker,frozen_at,{col} score from {table} where model_id=? and run_id>=?",h,params=(model,reg)); s.market=s.market.str.lower()
  keep=ns['dedupe_by_anchor'](s,didx,{'20260608','20260703'},reg)
  rec=[]; timely=set(); counts=dict(rows=0,missing=0,jump=0,unverified=0,not_mature=0,missing_score=0)
  cand=[]
  for rid,g in s[s.run_id.isin(keep)].groupby('run_id'):
   t=ns['anchor'](rid,didx)
   if t+2>=len(dates): counts['not_mature']+=1;continue
   deadline=pd.Timestamp(dates[t+1]+' 09:00',tz='Asia/Seoul')
   frozen=pd.to_datetime(g.frozen_at,format='mixed',utc=True,errors='coerce')
   if frozen.notna().all() and (frozen<deadline).all():timely.add(dates[t])
   c0,c1,c2=close.iloc[t],close.iloc[t+1],close.iloc[t+2]; o1=op.iloc[t+1]
   available=c0.notna()&c1.notna()&c2.notna(); jump=((c1/c0-1).abs()>.32)|((c2/c1-1).abs()>.32)
   ret={'A':100*(c1/o1-1),'B':100*(c2/c1-1),'C':100*(c2/o1-1),'G':100*(o1/c0-1)}
   assert np.allclose((1+ret['A']/100)*(1+ret['B']/100)-1,ret['C']/100,equal_nan=True)
   market=mk.iloc[t].astype(str).str.lower()
   counts['rows']+=len(g)
   counts['missing']+=int((~(available&o1.notna()).reindex(g.ticker,fill_value=False)).sum())
   counts['unverified']+=int((~available.reindex(g.ticker,fill_value=False)).sum())
   counts['jump']+=int(jump.reindex(g.ticker,fill_value=False).sum())
   counts['missing_score']+=int(g.score.isna().sum())
   marketvals={z:[] for z in ret}; cgroups=[]
   for m,gm in g.groupby('market'):
    gm=gm.dropna(subset=['score']).sort_values(['score','ticker'],ascending=[False,True]); ids=gm.ticker.to_numpy(); scores=gm.score.to_numpy(); n=len(ids); k=max(1,int(np.ceil(n*.1)))
    for z,r in ret.items():
     r=r.where(available&~jump); a=r.reindex(ids).to_numpy(); valid=np.isfinite(a)
     ic=pd.Series(scores[valid]).corr(pd.Series(a[valid]),method='spearman') if valid.sum()>=8 and len(set(scores[valid]))>=3 and len(set(a[valid]))>=3 else np.nan
     bench=r[market==m].mean()
     def avg(v):return np.nanmean(v) if np.isfinite(v).any() else np.nan
     top=avg(a[:10]); win=100*np.mean(a[:10][np.isfinite(a[:10])]>0) if np.isfinite(a[:10]).any() else np.nan
     marketvals[z].append([ic,top-bench,win,avg(a[:k])-avg(a[-k:]),top,bench])
     if z=='C' and model!='lv_e':
      sel=(np.arange(n)<5)&valid
      if sel.sum()>0 and (valid&~sel).sum()>0:cgroups.append((a[valid],sel[valid],bench))
   for z,vals in marketvals.items():
    if vals:
     arr=np.array(vals); den=np.isfinite(arr).sum(0); v=np.divide(np.nansum(arr,axis=0),den,out=np.full(arr.shape[1],np.nan),where=den>0); rec.append((dates[t],z,*v))
   if cgroups:cand.append((dates[t],cgroups))
  df=pd.DataFrame(rec,columns=['date','h','IC','초과','양 비율','10분위 차','상위10 수익','시장 수익'])
  totals[model]=(df,timely); candidates[model]=cand; audits.append((model,len(keep),counts,int((s.run_id=='20261014').sum())))
  for z in 'ABC':
   q=df[df.h==z]
   for metric in ['IC','초과','양 비율','10분위 차','상위10 수익','시장 수익']:
    lines.append(f'|{model} {z}|{metric}|{stats(q[metric],q.date)}|')
   for cost in [.35,.5]:
    lines.append(f'|{model} {z}|초과−{cost}%|{stats(q["초과"]-cost,q.date)}|')
    lines.append(f'|{model} {z}|절대수익−{cost}%|{stats(q["상위10 수익"]-cost,q.date)}|')
  q=df[df.h=='G']; lines.append(f'|{model} G|상위10 갭(참고)|{stats(q["상위10 수익"],q.date)}|')
  print(model, 'completed', flush=True)
 lines+=['','## 2. 조건 가설 세 개 (실측·의견 분리)','', '성과 조회 전에 후보를 고정: v30·le_a·lv_b 각각 시장별 점수 상위5. C 이틀 수익만 조건검정에 사용. 조건 정의 1개×모델3개=총3회 시도, 문턱·방향·지평을 바꾼 추가 탐색 없음. 앞 floor(2n/3) 앵커를 탐색 구간, 뒤를 확인 구간으로 분리. 본 분석은 앞 구간 결과로 문턱을 최적화하지 않는 더 제한적인 시험이다. 경계에서 앞 구간 t+2가 뒤 첫 앵커일보다 빠른 경우만 학습에 남긴다.', '', '조건의 개선=상위5 평균−나머지 목록 평균. 시장별 평균 후 앵커 동일가중. 자리바꿈은 각 앵커·시장 안에서 같은 수의 종목에 선택 표식을 무작위 부착(1,000회, seed 20261018), p=(1+무작위 개선≥실제 개선 횟수)/1001. 각 날짜를 독립적으로 섞어 종목의 날짜 간 지속성을 보존하지 못하므로 p는 탐색 참고값이다. 3조건 보정 p=min(1,3p), 후보 채택 근거로 사용하지 않는다.', '', '|후보·구간|선택−나머지 (95% 구간 포함)|선택 시장초과−0.35%|선택 시장초과−0.5%|자리바꿈 p / 3보정|','|---|---|---|---|---|']
 for model in ['v30','le_a','lv_b']:
  data=candidates[model]; cut=len(data)*2//3; boundary=didx[data[cut][0]]
  train=[x for x in data[:cut] if didx[x[0]]+2<boundary]
  for label,part in [('전체',data),('앞2/3(경계 제거)',train),('뒤1/3',data[cut:])]:
   ds=[]; actual=[]; exc=[]; null=np.zeros(1000); rng=np.random.default_rng(20261018)
   for d,groups in part:
    ds.append(d); diffs=[]; excess=[]; daynull=np.zeros(1000)
    for a,sel,bench in groups:
     k=int(sel.sum()); diffs.append(a[sel].mean()-a[~sel].mean()); excess.append(a[sel].mean()-bench)
     for b in range(1000):
      picked=rng.choice(len(a),k,replace=False); sm=a[picked].sum(); daynull[b]+=(sm/k-(a.sum()-sm)/(len(a)-k))/len(groups)
    actual.append(np.mean(diffs)); exc.append(np.mean(excess)); null+=daynull/len(part)
   hits=np.count_nonzero(null>=np.mean(actual)); pv=(1+hits)/1001
   ph=hits/1000; zz=1.95996398454; center=(ph+zz*zz/2000)/(1+zz*zz/1000); half=zz*np.sqrt(ph*(1-ph)/1000+zz*zz/(4*1000**2))/(1+zz*zz/1000)
   lines.append(f'|{model} 상위5 {label}|{stats(actual,ds)}|{stats(np.array(exc)-.35,ds)}|{stats(np.array(exc)-.5,ds)}|{pv:.4f} / {min(1,3*pv):.4f}; 1,000회 꼬리확률 95%[{center-half:.4f},{center+half:.4f}]|')
 lines+=['','## 3. 제외·한계 (실측)','', '|모델|중복제거 후 앵커|행수/제외|10/14 저장행|','|---|---|---|---|']
 for m,n,c,r in audits:lines.append(f'|{m}|{n}|{c}|{r}|')
 lines+=['', 'rows=완결 앵커의 점수행, missing=세 종가 또는 t+1 시가 부족 행, unverified=점프컷 검증 불가(세 종가 부족; missing의 부분집합), jump=32% 초과 행(결측과 중복 가능), not_mature=t+2 미완결 앵커, missing_score=점수 결측. B는 시가 불필요하므로 missing 전부가 B 탈락은 아니다. 네 모델 간 행 중복은 합산하지 않는다.', '', '20261014 runs는 0행이지만 le_a는 1,047행(코스닥605·코스피442)이 존재한다. frozen_at=2026-10-15 20:55:13+0900으로 t+1 장 종료 뒤 저장됐다. 요청의 run 기준 본표에는 포함하되 당시 매수 가능 목록이었다고 해석할 수 없다. 이 연구가 새 점수행을 만들지는 않았다. le_a는 wu 전체 유니버스이므로 다른 모델과 IC 절대값으로 우열을 정하지 않는다. 시장 초과에서 비용을 뺀 값과 절대 수익은 다르다. 양 비율은 비용 전이며 실제 체결·거래정지·가격제한·슬리피지는 별도 검증하지 못했다. 비용 일정 차감은 체결 가능성 보장이 아니다.', '', '## 4. 결론', '', '의견: 상위10의 12조합 모두 비용 후 시장초과 평균이 음수여서 하루~이틀 매매의 추가 이익 근거를 찾지 못했다. 이는 절대수익이 반드시 음수라는 뜻은 아니다(절대수익 비용차감 행 참조). 상위5 후보 세 개도 뒤1/3에서 비용 후 초과 평균이 모두 음수이고 날짜 구간이 0을 걸친다. 확인된 선택 조건은 없다. 가능한 모든 조건이 없다는 증명은 아니며, 채택·모델 변경은 하지 않는다.', '', '검증: A·B의 복리 연결이 C와 같은지 모든 앵커·종목 배열에서 assert 통과. DB는 query_only, 운영 모듈 import 없이 게이트 순수함수 두 개만 사용. 자리바꿈 꼬리확률 구간은 1,000회에 대한 Wilson 구간(시장 표본 불확실성과 별개).', '', '재현: `python research/handoff/code_20261018_short_horizon.py`. 결과물은 이 보고서와 코드 두 파일뿐이며 큰 중간 파일은 만들지 않는다. 운영·점수·판정·docs/ 변경 없음.']
 lines+=['','## 5. 저장 시점 감도와 대조 시 확인할 점','', '실측: frozen_at이 t+1 09:00 KST보다 늦거나 결측인 행이 하나라도 있는 앵커를 통째로 제외한 감도. 과거 재저장일 수 있으므로 당시 신호가 없었다는 확정은 아니나, 현재 DB만으로 장전 공개를 증명하지 못한다. 본표를 바꾸지 않고 별도 제시한다. 조건 가설 표도 본표와 같은 저장시점 한계를 가진다.', '', '|모델·지평|장전 저장 확인 앵커의 초과−0.35%|','|---|---|']
 for m,(df,timely) in totals.items():
  for z in 'ABC':
   q=df[(df.h==z)&df.date.isin(timely)]; lines.append(f'|{m} {z}|{stats(q["초과"]-.35,q.date)}|')
 lines+=['', 'Claude 보고서를 열지 않았으므로 수치 일치 여부는 확인 못 함. 대조 때 확인할 정의: 결측 제거 전 상위10 고정 여부, 공통 t+2 점프컷으로 A 마지막 날도 제외했는지, 시장 비교군의 결측·점프컷, 동점 처리, 10/14 le_a 행과 저장 시점. 시세 누락 행을 제거한 뒤 상위10을 다시 채우면 다른 표가 된다.']
 OUT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
 h.close();p.close()
if __name__=='__main__':main()
