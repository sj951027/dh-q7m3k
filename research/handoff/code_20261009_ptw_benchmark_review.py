"""PTW source-only audit. No PTW package imports, DB, data/, backup/, or network."""
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
import sys,ast,bisect
import numpy as np
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[2];PTW=ROOT.parent/'Position-Tracker-Web'
def guard():
 t=datetime.now(timezone(timedelta(hours=9)))
 if t.weekday()<5 and '20:10'<=t.strftime('%H:%M')<'22:30':raise SystemExit('KST batch window')
 return t.isoformat(timespec='seconds')
def table(h,rs):return '\n'.join(['| '+' | '.join(h)+' |','|'+'|'.join(['---']*len(h))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rs])
def main():
 started=guard();src=(PTW/'app/benchmark.py').read_text(encoding='utf-8-sig');tree=ast.parse(src)
 names=['_ymd','_avg','_r','_chain','build_benchmark'];ns=dict(bisect=bisect,date=date,datetime=datetime,BENCH_KEYS=('half','ks','kq'),MIN_DAYS_SIDE=10,MONTHS_SHOWN=12,BASIS='original definition')
 for node in tree.body:
  if isinstance(node,ast.FunctionDef) and node.name in names:exec(compile(ast.Module(body=[node],type_ignores=[]),'pure_ptw_functions','exec'),ns)
 fn=ns['build_benchmark'];S=lambda d,e,p,r:dict(date=d,total_eval=e,total_pnl=p,realized_total=r);B=lambda d,q,p:dict(side='buy',qty=q,price=p,traded_at=d)
 ds=['2026-09-28','2026-09-29','2026-09-30','2026-10-01'];idx={d:100+i for i,d in enumerate(ds)};rows=[]
 def case(label,snaps,buys,comparison,notes,indices=None):
  indices=indices or idx;out=fn(snaps,buys,indices,indices,today=date(2026,10,1));ps=[p for p in out['points'] if p['span'] is not None]
  rows.append([label,len(snaps),len(buys),str([p['r_me'] for p in ps]),comparison,notes]);return out
 a=case('同日2회 왕복', [S(ds[0],0,0,0),S(ds[1],0,0,200)],[B(ds[1],1,1000),B(ds[1],1,1000)],'자금1000→1200: +20%','이익100씩 2회, 총매수2000; 코드+10%')
 assert a['points'][1]['r_me']==10
 b=case('전량매도 다음날 재매수',[S(ds[0],1000,0,0),S(ds[1],0,0,100),S(ds[2],1210,110,100)],[B(ds[2],1,1100)],'각 +10%, 복리+21%','이 예는 일치; 전날 현금1100 재투자')
 assert [p['r_me'] for p in b['points'][1:]]==[10,10]
 c=case('부분매도 뒤 잔액만 상승',[S(ds[0],1000,0,0),S(ds[1],120,20,0),S(ds[2],132,32,0)],[],'현금900 포함 1000→1032: +3.2%','코드 +2%, +10%를 복리하면 +12.2%')
 assert [p['r_me'] for p in c['points'][1:]]==[2,10]
 d=case('과거거래 정정만 반영',[S(ds[0],1000,0,0),S(ds[1],1000,0,200)],[],'시세·경제적 손익 변화0%','장부정정+200을 오늘수익+20%로 분류')
 assert d['points'][1]['r_me']==20
 e=case('전량매도 후 현금대기',[S(ds[0],1000,0,0),S(ds[1],0,0,100),S(ds[2],0,0,100),S(ds[3],1210,110,100)],[B(ds[3],1,1100)],'현금대기일 계좌수익0%','코드는 가운데날None, 지수는 계속 계산')
 assert e['points'][2]['r_me'] is None
 f=case('누적실현값 없는 중간기록',[S(ds[0],1000,0,0),S(ds[1],1010,10,None),S(ds[2],1020,20,0),S(ds[3],1030,30,0)],[],'첫20원 변화 복원돼야 함','None인 날도 prev갱신: 두 간격 누락, 다음날만계산')
 assert [p['r_me'] for p in f['points'][1:3]]==[None,None]
 # Nontrading-day restatement assigned to a later index-up day.
 wkidx={'2026-09-25':100,'2026-09-28':101};w=fn([S('2026-09-25',1000,0,0),S('2026-09-26',1000,0,100),S('2026-09-28',1000,0,100)],[],wkidx,wkidx)
 assert w['points'][-1]['r_me']==10 and w['updown']['half']['up']['me_avg']==10
 # Intersection of index calendars hides one missing trading day.
 k1={ds[0]:100,ds[1]:101,ds[2]:102};k2={ds[0]:100,ds[2]:102}
 miss=fn([S(ds[0],1000,0,0),S(ds[1],1010,10,0),S(ds[2],1020,20,0)],[],k1,k2)
 assert miss['points'][-1]['span']==1 and miss['updown']['half']['up']['n']==1
 # Cross-month missing snapshot puts the whole interval in the endpoint month.
 mi={'2026-09-30':100,'2026-10-01':101,'2026-10-02':102};mo=fn([S('2026-09-30',1000,0,0),S('2026-10-02',1020,20,0)],[],mi,mi)
 assert mo['months'][0]['key']=='2026-10' and mo['months'][0]['n']==1 and mo['points'][-1]['span']==2
 # Repeat 5 same-capital round trips: 10% gross-turnover yield vs 50% account return.
 repeat=fn([S(ds[0],0,0,0),S(ds[1],0,0,500)],[B(ds[1],1,1000) for _ in range(5)],idx,idx)
 assert repeat['points'][1]['r_me']==10
 toy_n=10
 # Conditional on n up (or down) days; parameter choices are illustrations, not observed PTW facts.
 rng=np.random.default_rng(7);sim=[]
 for n in [5,10,20,60]:
  for scale,rho in [(1.0,0),(.15,0),(1.0,.5)]:
   index=np.abs(rng.normal(0,scale,(10000,n)));eps=rng.normal(0,1.5,(10000,n))
   if rho:
    for j in range(1,n):eps[:,j]=rho*eps[:,j-1]+np.sqrt(1-rho*rho)*eps[:,j]
   ratio=.8+eps.mean(axis=1)/index.mean(axis=1);q=np.quantile(ratio,[.025,.975]);sd=np.std(ratio)
   sim.append([10000,n,scale,rho,.8,f'[{q[0]:+.3f}, {q[1]:+.3f}]',f'{q[1]-q[0]:.3f}',f'{sd:.3f}',f'{(ratio<0).mean():.3f}'])
 # Existing test definitions reviewed statically; do not import app/main/db or run the full test.
 tests=(PTW/'test_benchmark.py').read_text(encoding='utf-8-sig');count=sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='check' for n in ast.walk(ast.parse(tests)))
 txt=f'''# REPLY — 6. PTW 시장 비교 계산 정의 검토

검토 {started}. **PTW는 소스·규칙만 읽음. data/·backup/·운영DB·개인 매매자료를 열지 않았다.** 해당 저장소 파일도 수정하지 않았다. 아래 원 단위 숫자는 모두 가짜 자료다. 결론: 정의대로 구현되어 있지만, 이 수익률을 시간가중 투자성과 또는 계좌 전체 수익률로 해석하면 안 된다. 반복매매·자금노출 변화·장부정정에 민감하고, 오른/내린 날 비율은 n=20에서도 크게 흔들릴 수 있다.

## 검토 범위와 기존 테스트

app/benchmark.py·test_benchmark.py·PATCH_NOTES_v5.37~39·CLAUDE.md·핸드북§5·9·12 및 화면/호출부의 관련 줄만 읽었다. 기존 테스트의 check호출 정의 n={count}개는 요청의 분모·주말이월 규칙을 확인한다. 전체 테스트는 app.main·app.db를 import하므로 실행하지 않았다(설정·초기화와 운영경로 접촉 회피). 본 시험은 AST로 추출한 **순수 계산 함수5개**만 가짜 dict/list와 지수에 적용했다. 부팅·DB·FDR·KIS·네트워크 실행 없음. 가짜 시나리오 n={toy_n}, assertion 전부 통과.

## (1) 매매 패턴 시험

'''+table(['가짜 시나리오','저녁기록 n','매수건 n','코드 일수익 %','비교 기준','설명'],rows).replace('同日','같은 날')+'''

같은 날5회 왕복(매번1000 매수·1100 매도, 최초자금1000)은 코드 +10%지만 계좌자금1000→1500은 +50%(매매 n=5, 기록 n=2). 매번 같은 현금을 쓰는데 총매수액5000을 분모로 삼기 때문이다. 이는 매수금액당 이익률로는 정의와 맞으나 자본 수익률로는 다르다. 수익률의 양수·음수 모두 축소하므로 항상 '보수적'이라는 표현도 적절하지 않다.

전량매도 다음날 재매수 자체는 오류가 아니다. 현금1100 전액 재투자한 위 예는 두 날 모두10%로 맞았다. 다만 현금 대기일은 내수익None인데 지수수익은 누적돼 현금으로 피한 하락·포기한 상승이 일관된 계좌 기준에 반영되지 않는다. 부분매도도 첫날의 총손익 변화는 맞지만, 이후 분모가 남은 주식만으로 급감해 같은 곡선을 계좌지수처럼 이어 곱하기 어렵다.

장부가 일관되면 Δ합계손익=오늘주식평가액−전날주식평가액−매수대금+매도대금이다. 현재 분모는 매수를 하루처음부터 보유한 것으로 놓고 매도는 같은 방식으로 시간조정하지 않는다. 현금흐름 시각을 모르면 정확한 시간가중 수익률은 복원 못 한다. 과거 거래 삭제/재입력으로 누적실현손익이 바뀌면 경제적 새 수익이 없는 날도 수익으로 기록된다. 분모0인 정정 또는 중간 totals=None은 아예 누락되고 다음 간격으로 자동복원되지 않는다.

## (2) 오른 날/내린 날 평균 비율의 모의 범위

가정: 지수=정규분포 절댓값(오른 날), 내수익=0.8×지수+독립잔차(표준편차1.5%p). 내린 날은 지수 부호만 반대로 놓아 같은 대칭 분포를 얻는다. true ratio=0.8. 각 조건 모의 n=10,000회·seed7. n은 **한쪽 날 수**여서 전체20거래일이면 양쪽 n≈10이지20이 아니다. rho는 잔차의 날짜상관. 아래는 가정 하 모의95% 범위이며 운영자료의 CI가 아니다.

'''+table(['모의 n','한쪽날 n','지수σ %','잔차rho','참 비율','모의95%','폭','표준편차','음수 비율'],sim)+'''

지수가 크게 움직인 날보다 0근처 움직임이 많으면 평균 지수라는 분모가 작아져 비율이 특히 불안정하다. **10일 미만 참고만**은 자료부족 경고로는 이해되지만10일 이상이면 신뢰할 만하다는 통계근거는 이 정의에 없다. n=20도 잔차상관·지수폭에 따라95%폭이 크게 달라진다. 화면은 양쪽 n≥10·내상승평균>0·내하락평균<0일 때만 문장을 보여주지만, 이 부호조건은 불확실성을 제거하지 않는다. 현재 반환값은 평균·비율뿐이며95% 구간을 계산하지 않는다.

## (3) 주말·휴일·누락 이월

가짜 시험 n=3:

| 재현 | 코드 결과 | 영향 |
|---|---|---|
| 금요일 합계손익0→토요일 과거거래정정+100→월요일그대로, 평가액1000, 지수월+1% | 월요일 내+10%, span1·상승일 표에 포함 | 주말 장부정정을 월요일 시장성과로 오인 |
| 코스피는 월·화 모두, 코스닥은 월 값만 누락, 금·월·화 저녁기록 존재 | 두 지수 날짜의 교집합에서 금→화 span1, 상승일 n=1 | 실제2거래일 변화가 '하루' 분류됨. 교집합달력으로는 휴장과자료누락 구분 못 함 |
| 9/30기록 뒤10/1없고10/2기록, 지수는모두존재 | span2 전체를10월복리로 산입, 상승/하락표에서는 제외 | 실제 간격은 알지만 날짜별·월별 손익을 나눌 수 없음 |

주말을 건너뛴 것 자체보다 **건너뛴 사이 변화의 원인**을 모르는 것이 문제다. 손익 정정·뒤늦은 거래입력·일봉결손을 수익으로 합친다. 한쪽 지수 자료가 없으면 교집합 기준 span도 작아져 누락 경고를 놓친다. 마지막 지수 뒤 평일은 모두pending으로 세므로 공휴일도 거래일 대기처럼 표시될 수 있다(실제 휴장달력 검증 없음). None 수익을 곡선에서 건너뛰면서 지수는 같은 기간 포함하므로 비교기간의 유효범위도 다를 수 있다.

## (4) 더 나은 정의와 장단점 — 문서 의견

| 목적/정의 | 장점 | 한계·필요자료 |
|---|---|---|
| 현금포함 계좌NAV의 시간가중수익: 각 외부입출금 전후 평가를 연결 | 매매는 내부교환이라 반복매수·부분매도가 분모를 중복 부풀리지 않음. 지수와 동일기간 비교가능 | 현금잔고·입출금·평가시점·비용 필요. 현재저녁기록만으로 과거전부 복원불가 |
| 현금제외 주식부분의 시간가중수익 | 종목선택/보유성과와 현금대기를 분리 | 매수·매도를 주식부분의 외부흐름으로 다뤄 시각별 평가 필요. 잔여보유0인 구간 정의 필요 |
| Modified Dietz: 이익/(초기자산+시간가중 순외부흐름) | 일중평가 없이 흐름시각으로 근사, 주식부분은 매수 유입·매도 유출을 대칭처리 | 큰 흐름·급변·분모0근처에 불안정. 체결시각/평가가 없어 정확한 역사복원은 못 함 |
| 금액손익 Δ, 매수금액당 이익률을 그대로 별도표시 | 현재자료로 재현가능, 산식이명료 | 투자자본의 시간가중성과로 지수와 직결못 함. 정정분은 분리해야 함 |
| 상승/하락일 내평균−지수평균(%p), 비율과 병기 | 지수평균0근처 분모폭발을 피함, 의미가명료 | 여전히작은n·상관·현금노출에 민감. 날짜블록95%와 유효n 표시필요 |

어떤 정의를 고를지는 '계좌의 돈이 얼마나 늘었나'와 '주식에 노출된 때 선택이 어땠나' 중 표시목적에 달려 있다. 현재자료로 정확한TWR을 만들었다고 이름만 바꾸면 안 된다. 실제금액·거래를 확인하지 않았으므로 운영오차 크기는 확인 못 함.

## 재현 방법 · 영향 · 고치는 안

- 재현: `python research/handoff/code_20261009_ptw_benchmark_review.py`. PTW의5개순수함수만 추출·가짜자료 실행, 모의 seed7. 생성물은 스크리너 REPLY와 본 코드뿐이다.
- 영향: 반복 매수는 같은자금을 중복분모로 세고, 부분청산은 다음날부터 분모가줄며, 과거정정은 오늘성과로 튄다. 비율n=10문턱은 정밀도보장이 아니고 지수자료누락을 휴장으로 취급할 여지가 있다.
- 고치는 안: 화면의 수익률 이름에 실제분모를 유지하고 계좌수익률·TWR과 구분, 정정표식·실제거래일달력·지수결손상태·같은유효기간을 표시한다. 목적에 맞는 현금흐름 정의와95%구간은 위장단점을 검토할 수 있다. 구현·DB·운영자료는 수정하지 않았다.
- 못 한 것: 운영자료로 빈도·오차·현재화면값 검증, 실제지수조회, 전체통합테스트는 확인 못 함. 가짜자료와 가정하모의 결과이며 실제사용자의 성과·매매분포를 뜻하지 않는다. 이미 본 정의·문서의 사후검토라는 한계가 있다.

6번 완료. 다음 번호: 7번.
'''
 guard();Path(__file__).with_name('REPLY_20261009_ptw_benchmark_review.md').write_text(txt,encoding='utf-8')
 print('DONE toy',toy_n,'existing_checks',count,'SIM',sim)
if __name__=='__main__':main()
