"""Independent offline exploration; no Claude result files/imports/network.
Run: python -B research/handoff/code_20261020_entry_regime_blind.py
Writes only REPLY_20261020_entry_regime_blind.md. Definitions fixed before results:
- daily equal-initial-weight basket -> distribution across signal days;
  stock-level outcome rates are separately reported, never conflated.
- all local-calendar days, next close entry; no jump or suspension filter;
  endpoint-complete forward pairs, missing counts disclosed.
- calendar-month blocks, 4000 draws, seed 7. Paired regime differences use
  the SAME month draws. Quantile bootstrap preserves repeated months exactly.
- A-entry events: crossing from not-A, greedy >=40 calendar-trading positions.
- simulation: current pre-entry NAV/40, capped cash, 40 days buy-and-hold,
  0.5% of principal paid at entry, cash interest 0. Missing marks carried forward;
  no future-endpoint selection for simulation. Rule signal is preceding day.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import ast
import hashlib
import sqlite3
import warnings
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).with_name('REPLY_20261020_entry_regime_blind.md')
START,END='20230626','20261019'
B,SEED=4000,7


def guard():
    now=datetime.now(timezone(timedelta(hours=9)))
    if now.weekday()<5 and (20,10)<=(now.hour,now.minute)<=(22,30):
        raise SystemExit('평일 배치 제한 시간: 실행 중단')


def ro(path):
    guard();c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    c.execute('PRAGMA query_only=ON');return c


def extract(path,names,env=None):
    tr=ast.parse((ROOT/path).read_text(encoding='utf-8-sig'))
    nodes=[n for n in tr.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(nodes)==len(names)
    e=dict(env or {});exec(compile(ast.Module(body=nodes,type_ignores=[]),path+':pure','exec'),e)
    return e


def tab(head,rows):
    def s(x):return str(x).replace('|','/').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(head)+' |','|'+'|'.join(['---']*len(head))+'|']+
                     ['| '+' | '.join(s(x) for x in r)+' |' for r in rows])


def f(v,d=2):
    return '확인 못 함' if not np.isfinite(v) else f'{v:+.{d}f}'


def iv(a):
    a=np.asarray(a);a=a[np.isfinite(a)]
    return '[확인 못 함]' if len(a)<2 else '['+', '.join(f(x) for x in np.quantile(a,[.025,.975]))+']'


def valci(v,a):return f'{f(v)} {iv(a)}'


def count_separate(pos,h):
    last=-10**9;n=0
    for p in sorted(set(pos)):
        if p-last>=h:n+=1;last=p
    return n


def greedy(pos,h):
    out=[]
    for p in pos:
        if not out or p-out[-1]>=h:out.append(int(p))
    return out


def nanmean(x,axis=None):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning)
        return np.nanmean(x,axis=axis)


class MonthBoot:
    def __init__(self,dates):
        self.dates=pd.Index(dates)
        self.labels=np.array([str(x)[:6] for x in dates])
        self.months=sorted(set(self.labels))
        self.mi=np.array([self.months.index(x) for x in self.labels])
        m=len(self.months);rng=np.random.default_rng(SEED)
        draw=rng.integers(0,m,(B,m))
        self.w=np.zeros((B,m),dtype=np.int16)
        np.add.at(self.w,(np.arange(B)[:,None],draw),1)

    def means(self,x,mask=None):
        x=np.asarray(x,float);ok=np.isfinite(x)
        if mask is not None:ok &= np.asarray(mask,bool)
        n=np.bincount(self.mi[ok],minlength=len(self.months))
        sums=np.bincount(self.mi[ok],weights=x[ok],minlength=len(self.months))
        den=self.w@n
        return np.divide(self.w@sums,den,out=np.full(B,np.nan),where=den>0)

    def stats(self,x,mask,h):
        x=np.asarray(x,float);ok=np.asarray(mask,bool)&np.isfinite(x);pos=np.flatnonzero(ok)
        if not len(pos):return dict(n=0,ne=0,row=['0 (0)']+['확인 못 함']*4,mean=np.nan,boots=np.full(B,np.nan))
        a=x[ok];order=np.argsort(a);a=a[order];labs=self.mi[ok][order]
        weights=self.w[:,labs];cum=np.cumsum(weights,axis=1);total=cum[:,-1]
        def quant(q):
            ranks=(total-1)*q;lo=np.floor(ranks);hi=np.ceil(ranks)
            i=(cum<=lo[:,None]).sum(axis=1).clip(0,len(a)-1)
            j=(cum<=hi[:,None]).sum(axis=1).clip(0,len(a)-1)
            out=a[i]+(ranks-lo)*(a[j]-a[i]);out[total==0]=np.nan
            return out
        bm=self.means(x,ok)
        bw=self.means((x>0).astype(float)*100,ok)
        return dict(n=len(pos),ne=count_separate(pos,h),mean=float(a.mean()),boots=bm,
            row=[f'{len(pos)} ({count_separate(pos,h)})',valci(a.mean(),bm),
                 valci(np.median(a),quant(.5)),valci(np.mean(a>0)*100,bw),valci(np.quantile(a,.1),quant(.1))])

    def diff(self,x,a,b,h):
        x=np.asarray(x,float);a=np.asarray(a,bool)&np.isfinite(x);b=np.asarray(b,bool)&np.isfinite(x)
        ma=nanmean(x[a]) if a.any() else np.nan;mb=nanmean(x[b]) if b.any() else np.nan
        ba,bb=self.means(x,a),self.means(x,b)
        boots=ba-bb
        return [f'{a.sum()} ({count_separate(np.flatnonzero(a),h)})',f'{b.sum()} ({count_separate(np.flatnonzero(b),h)})',
                valci(ma,ba),valci(mb,bb),valci(ma-mb,boots),int(np.isfinite(boots).sum())]


def classify(r):
    r=np.asarray(r);out=np.full(len(r),'?',dtype='<U1')
    out[np.isfinite(r)&(r<=-.05)]='A'
    out[np.isfinite(r)&(r>-.05)&(r<=0)]='B'
    out[np.isfinite(r)&(r>0)&(r<=.05)]='C'
    out[np.isfinite(r)&(r>.05)]='D'
    return out


def streaks(mask):
    out=np.zeros(len(mask),dtype=int)
    for i,on in enumerate(mask):out[i]=(out[i-1]+1 if i else 1) if on else 0
    return out


def main():
    guard();paths=[ROOT/'history.db',ROOT.parent/'dh-q7m3k-data/ohlcv.db']
    before=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]
    with ro(paths[1]) as c:
        p=pd.read_sql_query('SELECT ticker,date,close,shares,market,is_suspended FROM daily_ohlcv WHERE date BETWEEN ? AND ? ORDER BY date,ticker',c,params=(START,END))
        ix=pd.read_sql_query("SELECT series,date,close FROM market_daily WHERE series IN ('KOSPI','KOSDAQ') AND date<=? ORDER BY date,series",c,params=(END,))
    indices=ix.pivot(index='date',columns='series',values='close').sort_index()
    dates=pd.Index(sorted(p.date.unique()));ticks=pd.Index(sorted(p.ticker.unique()));T=len(dates)
    assert set(dates)==set(indices.index[indices.index>=START])
    assert not p.duplicated(['date','ticker']).any()
    C=p.pivot(index='date',columns='ticker',values='close').reindex(index=dates,columns=ticks).astype(float)
    S=p.pivot(index='date',columns='ticker',values='shares').reindex(index=dates,columns=ticks).astype(float)
    M=p.pivot(index='date',columns='ticker',values='market').reindex(index=dates,columns=ticks)
    c=C.to_numpy();shares=S.to_numpy();mark=C.ffill().to_numpy();present=np.isfinite(c)&(c>0)
    market_masks={k:(M.to_numpy()==k) for k in ['KOSPI','KOSDAQ']}
    lb={k:{w:indices[k].pct_change(w,fill_method=None).reindex(dates).to_numpy() for w in [10,20,40]} for k in ['KOSPI','KOSDAQ']}
    cats={k:classify(lb[k][20]) for k in lb}
    boot=MonthBoot(dates)
    rets={};daily={};counts={};stockwin={};stockp10={};by_market={};candidate={}
    for h in [20,40,60]:
        R=np.full_like(c,np.nan)
        raw=c[1+h:]/c[1:T-h]-1
        ok=present[:T-h-1]&present[1:T-h]&present[1+h:]
        R[:T-h-1]=np.where(ok,raw,np.nan)
        rets[h]=R*100;counts[h]=np.isfinite(R).sum(axis=1)
        candidate[h]=present.sum(axis=1)
        daily[h]=nanmean(R,axis=1)*100
        stockwin[h]=np.divide(np.sum(R>0,axis=1)*100,counts[h],out=np.full(T,np.nan),where=counts[h]>0)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning)
            stockp10[h]=np.nanquantile(R,.1,axis=1)*100
        by_market[h]={mk:nanmean(np.where(mask,R,np.nan),axis=1)*100 for mk,mask in market_masks.items()}
    print('DATA',T,len(ticks),'full months',len(boot.months),'first R20',[(k,next(dates[i] for i in range(T) if cats[k][i]!='?')) for k in cats],flush=True)
    # Independent random cell checks: exact entry and exit indexing, no jump filtering.
    rng=np.random.default_rng(20261020)
    checked=0
    for h in [20,40,60]:
        tt,ss=np.where(np.isfinite(rets[h]))
        for j in rng.choice(len(tt),min(25,len(tt)),replace=False):
            t,s=tt[j],ss[j]
            assert np.isclose(rets[h][t,s],(C.iloc[t+1+h,s]/C.iloc[t+1,s]-1)*100,atol=1e-10)
            checked+=1
    # Bootstrap rank interpolation validated against literal month duplication.
    toy=np.arange(T,dtype=float);sel=np.arange(T)%3==0
    st=boot.stats(toy,sel,20)
    assert st['n']==sel.sum()
    for b in range(3):
        vals=np.repeat(toy[sel],boot.w[b,boot.mi[sel]])
        assert np.isclose(boot.means(toy,sel)[b],vals.mean())

    sec=['# REPLY — 어떤 장에서 샀을 때 좋았나: 독립 탐색 (2026-10-20)',
        '## 0. 범위·눈가림·고정한 계산 정의',
        '- **탐색이며 규칙 채택·모델 판정이 아니다.** 금지된 Claude 보고서·entry_regime 코드·out_entry_regime 파일은 열거나 실행하지 않았다. 다만 시작 시 필수 `worklog/README.md` 목록에 같은 연구의 방향 요약이 이미 노출되었다. 따라서 완전한 눈가림은 아니다. 그 요약의 숫자를 계산 입력·검증 정답·규칙 선택에 사용하지 않았고, 이 코드의 입력은 지정된 두 DB와 등록일/앵커 순수 함수뿐이다. 기존에 읽은 작업 기록의 새 연구 결과 부분을 추가로 열지 않았다.',
        f'- 로컬 입력: daily_ohlcv {len(p):,}행, {len(ticks):,}종목, {T} 날짜({dates.min()}~{dates.max()}); 시장별 코드의 합집합. daily_ohlcv_extra는 사용하지 않는다. 지수는 market_daily KOSPI/KOSDAQ. 분석 신호기간 {START}~{END}, 지수 되돌아보기에는 DB에 있는 그 이전 지수를 사용했다.',
        '- **주표의 단위:** 신호일 t에 종가가 있는 종목 중 t+1과 t+1+h 종가가 있는 종목의 수익을 동일가중하여 하루 바스켓 수익을 만든다. 그 바스켓 수익을 날짜 동일가중해 평균·중앙값·승률·하위10%를 계산한다. 승률은 “그날 전 종목에 나눠 샀을 때 플러스인 신호일 비율”이다. “개별 종목이 오를 확률”은 별도 표에 분리한다. 종목 수가 많은 날에 가중치를 더 주는 전체 행 합산 통계와 다르다.',
        '- R20=지수(t)/지수(t−20)−1. A≤−5%, B −5%<R20≤0%, C 0%<R20≤+5%, D>+5%. 지수 두 가지 모두 같은 전 종목 바스켓을 분류한다. 모든 신호는 t까지의 값만 쓰고 t+1 종가 진입, t+1+h 종가 청산. 기본·군별·모델 표는 비용 전, 모의 운용만 왕복 0.5% 반영. 점프컷·거래정지 필터 없음.',
        '- 괄호 안 수는 시간순으로 직전 선택 신호와 h개의 로컬 거래일 이상 떨어진 것만 센 수다. 이는 독립적인 경제 사건 수를 보장하지 않는다. 신호 자체가 오래 이어지면 서로 다른 표본도 같은 경기 국면을 공유한다. 단일 사건의 수익/날짜/종목 수에는 표본 신뢰구간이 없으며 사건 평균에는 별도 구간을 낸다.',
        f'- 구간은 달 블록 복원추출 {B:,}회, seed {SEED}, 95%. {len(boot.months)}개 달을 한 묶음씩 재표집하여 같은 달의 모든 날짜를 함께 옮긴다. A−나머지 등 차이는 동일 달 추출을 공유한다. 평균·승률·분위수마다 재계산한다. 드문 집합이 빠진 재표집은 NaN으로 제외하며 격자표에 유효 재표집 수도 쓴다. 달 사이에 걸친 h40 수익 겹침과 사후 탐색 수를 보정한 구간은 아니다.',
        '- 끝부분 미완결 h20/40/60은 표에서 제외한다. 끝값 없는 종목도 빠지므로 상장폐지·수집누락에 따른 낙관이 남을 수 있다. 시세가 있는 현재 종목만 고른 목록을 사용하지는 않았지만 원 DB의 과거 수집대상 편향은 이 자료만으로 확인 못 함. 가격은 수정주가 여부를 추가 확인하지 않고 요청한 close 그대로 썼다.',
        '## 1. 기본 표 — 날짜별 전 종목 바스켓',
        '- 수익·구간·승률 단위는 %. 모든 칸의 평균/중앙값/승률/하위10% 옆 [ ]가 월 블록 95% 구간이다. “아무 날”도 해당 지수 R20이 계산되는 동일 기간을 쓴다.']
    basic=[];base_results={}
    for k in cats:
        for h in [20,40]:
            for cat in ['전체','A','B','C','D']:
                mask=(cats[k]!='?') if cat=='전체' else cats[k]==cat
                st=boot.stats(daily[h],mask,h);base_results[k,h,cat]=st
                nstock=counts[h][mask&np.isfinite(daily[h])]
                basic.append([k,h,cat,*st['row'],f'{nstock.min()}~{nstock.max()}' if len(nstock) else '0'])
    sec += [tab(['지수','h','칸','날 수(비겹침)','평균 [95%]','중앙값 [95%]','바스켓 승률 [95%]','하위10% [95%]','날별 종목 n'],basic)]
    stockrows=[]
    for k in cats:
        for h in [20,40]:
            for cat in ['전체','A','B','C','D']:
                m=(cats[k]!='?') if cat=='전체' else cats[k]==cat
                valid=m&np.isfinite(daily[h])
                stockrows.append([k,h,cat,f'{valid.sum()} ({count_separate(np.flatnonzero(valid),h)})',
                    valci(nanmean(stockwin[h][valid]),boot.means(stockwin[h],valid)),
                    valci(nanmean(stockp10[h][valid]),boot.means(stockp10[h],valid)),int(counts[h][valid].sum())])
    sec += ['### 개별 종목 승률·하위 꼬리(별도 정의)',
            '- 매일 종목별 플러스 비율 및 종목 수익 하위10%를 구한 뒤 날짜 동일가중 평균했다. 위의 바스켓 승률·날짜 하위10%와 혼용하지 않는다.',
            tab(['지수','h','칸','날 수(비겹침)','종목 승률의 날짜평균 [95%]','종목 하위10%의 날짜평균 [95%]','종목×날 n'],stockrows)]
    print('BASIC DONE',[(k,h,base_results[k,h,'A']['mean']) for k in cats for h in [20,40]],flush=True)

    sec += ['## 2. A 진입 사건별 — 40일 이상 간격',
            '- R20이 전날 A가 아니었다가 A가 된 날만 후보로 하고, 먼저 고른 사건 이후 40거래일 이상 지난 후보만 남겼다. A가 계속되는 동안 40일마다 새 사건을 만들지 않는다. 40일 종가 경로 최저점은 진입 직후 0%를 포함한 바스켓 평가수익 최저값(고점 대비 최대낙폭과 다른 수치)이다. 40일 종료가격까지 있는 같은 종목을 유지하고 중간 누락만 직전 종가로 평가한다.']
    event_positions={};event_summary=[];event_count_return={}
    for k in cats:
        fullcat=classify(indices[k].pct_change(20,fill_method=None).to_numpy())
        cross=(fullcat=='A')&np.r_[True,fullcat[:-1]!='A']
        transition=set(indices.index[cross]);candidate_events=[i for i,d in enumerate(dates) if d in transition]
        events=greedy(candidate_events,40);event_positions[k]=events
        erows=[]
        for t in events:
            worst=np.nan
            if t+41<T:
                m=np.isfinite(rets[40][t]);path=nanmean(mark[t+1:t+42,m]/c[t+1,m],axis=1)-1
                assert np.isclose(path[-1]*100,daily[40][t],atol=1e-9)
                worst=float(np.min(path)*100)
            erows.append([dates[t],f(lb[k][20][t]*100),*[f(daily[h][t]) for h in [20,40,60]],f(worst),
                          '/'.join(str(counts[h][t]) for h in [20,40,60])])
        sec += [f'### {k}',tab(['A 첫 진입일','R20 %','h20 %','h40 %','h60 %','40일 종가경로 최저 %','종목 n(20/40/60)'],erows)]
        for h in [20,40,60]:
            m=np.zeros(T,bool);m[events]=True
            st=boot.stats(daily[h],m,h);event_summary.append([k,h,*st['row']])
            valid=[t for t in events if np.isfinite(daily[h][t])]
            event_count_return[k,h]=(len(valid),sum(daily[h][t]>0 for t in valid))
        # Leave-one-event-out, not leave one highly-overlapping signal day out.
        loo=[]
        for t in events:
            mm=np.zeros(T,bool);mm[[p for p in events if p!=t]]=True
            rr=[]
            for h in [20,40]:
                st=boot.stats(daily[h],mm,h)
                rr.extend([st['row'][0],st['row'][1]])
            loo.append([dates[t],*rr])
        sec += ['한 사건씩 제외한 나머지 사건 평균(조건부 일별 A 평균과 다른 집계):',tab(['뺀 사건','h20 n(비겹침)','h20 평균 [95%]','h40 n(비겹침)','h40 평균 [95%]'],loo)]
        v40=[t for t in events if np.isfinite(daily[40][t])]
        if len(v40)>1:
            biggest=max(v40,key=lambda t:daily[40][t])
            selected=next(row for row in loo if row[0]==dates[biggest])
            sec += [f'- 실측: 가장 큰 h40 사건({dates[biggest]})을 뺀 나머지 평균은 {selected[4]}%, 사건 n(비겹침)={selected[3]}. 개별 최대 사건의 영향과 나머지 사건의 부호를 이 표로 구분한다.']
    sec += ['### 사건 평균과 분포',tab(['지수','h','사건 n(비겹침)','평균 [95%]','중앙값 [95%]','양수 비율 [95%]','하위10% [95%]'],event_summary)]
    sec += ['- 양수 사건만 있는 집합의 월 재표집 승률 구간은 [100,100]으로 퇴화한다. 이는 다음 사건 성공확률이 100%라는 뜻이 아니라, 관측된 실패가 없어 이 재표집법으로 실패 가능성을 추정할 수 없다는 한계다.']

    sec += ['## 3. 문턱·되돌아보기 격자와 연도별 차이',
            '- 각 셀에서 A는 지수 과거 w일 수익≤문턱, 나머지는 같은 w가 계산되는 나머지 모든 날. 표의 차이 단위는 %p. 되돌아보기 40일은 초기 지수 자료 부족으로 일부 날이 빠진다. 좋은 셀을 선택해 채택하지 않는다.']
    grid=[];grid_sign={}
    for k in cats:
        for w in [10,20,40]:
            for th in [-3,-5,-8,-10]:
                a=np.isfinite(lb[k][w])&(lb[k][w]<=th/100);other=np.isfinite(lb[k][w])&~a
                for h in [20,40]:
                    ds=boot.diff(daily[h],a,other,h)
                    grid.append([k,w,th,h,*ds]);grid_sign[k,w,th,h]=nanmean(daily[h][a])-nanmean(daily[h][other])
    sec += [tab(['지수','과거 w','문턱 %','보유 h','A 날(비겹침)','나머지 날(비겹침)','A 평균','나머지 평균','차이 [95%]','유효 재표집'],grid)]
    yr=[]
    for k in cats:
        for h in [20,40]:
            for y in ['2023','2024','2025','2026']:
                m=np.array([d.startswith(y) for d in dates]);a=m&(cats[k]=='A');b=m&np.isin(cats[k],['B','C','D'])
                yr.append([k,h,y,*boot.diff(daily[h],a,b,h)])
    sec += [tab(['지수','h','신호연도','A 날(비겹침)','나머지 날(비겹침)','A 평균','나머지 평균','차이 [95%]','유효 재표집'],yr)]
    print('GRID DONE',flush=True)

    sec += ['## 4. A 안에서 — 연속일 수와 하락 깊이',
            '- 연속일 수는 A 진입일부터 실제 연속 A 날짜 수다. 중간에 A를 벗어나면 다음 A에서 1로 초기화한다. 깊이는 −10%≤R20≤−5%, −15%≤R20<−10%, R20<−15%로 겹치지 않게 나눴다.']
    inside=[];early_rows=[]
    for k in cats:
        full=indices[k].pct_change(20,fill_method=None).to_numpy();stfull=streaks(classify(full)=='A')
        age=pd.Series(stfull,index=indices.index).reindex(dates).to_numpy()
        masks={'1~3일':(age>=1)&(age<=3),'4~10일':(age>=4)&(age<=10),'11일+':age>=11,
               '−5~−10%':(cats[k]=='A')&(lb[k][20]>=-.10),'−10~−15%':(lb[k][20]<-.10)&(lb[k][20]>=-.15),'<−15%':lb[k][20]<-.15}
        for h in [20,40]:
            for label,m in masks.items():inside.append([k,h,label,*boot.stats(daily[h],m,h)['row']])
            early_rows.append([k,h,*boot.diff(daily[h],masks['1~3일'],age>=4,h)])
    sec += [tab(['지수','h','A 안의 구분','날 수(비겹침)','평균 [95%]','중앙값 [95%]','승률 [95%]','하위10% [95%]'],inside),
            '초반 1~3일 − 이후 4일 이상(같은 달을 함께 재표집):',
            tab(['지수','h','초반 날(비겹침)','이후 날(비겹침)','초반 평균','이후 평균','차이 [95%]','유효 재표집'],early_rows)]
    ke=next(row for row in early_rows if row[0]=='KOSDAQ' and row[1]==40)
    sec += [f'- 실측 답: 코스닥 A 초반 1~3일의 h40 평균 {ke[4]}%(n/비겹침 {ke[2]}), 이후 {ke[5]}%(n/비겹침 {ke[3]}), 차이 {ke[6]}%p. 점추정상 초반이 낮지만 차이의 95% 구간에는 0이 포함된다.']

    sec += ['## 5. 코스피 A에서 종목군별 h40',
            '- 종목군은 그날의 전체 종목 횡단면에서 선정한다(거래소를 KOSPI로 제한하는 뜻이 아님). 과거20일 종목 수익, 과거60개의 일간 수익 표준편차(ddof=1, 60개 모두 필요), 당시 close×shares를 사용한다. 하위20%=순위≤20%, 상위20%=순위>80%. 동률은 ticker순, 미래 수익을 보고 종목군을 정하지 않는다. 각 군의 같은 정의로 A 아닌 날과 비교한다. 초기 60일 자료가 없는 변동성군은 늦게 시작하므로 전체군과 기간이 다를 수 있다.']
    r20=C.pct_change(20,fill_method=None)
    vol=C.pct_change(fill_method=None).rolling(60,min_periods=60).std(ddof=1)
    mcap=(C*S).where((C*S)>0)
    masks={'전 종목':present}
    for key,frame in [('20일 수익',r20),('60일 변동성',vol),('시총',mcap)]:
        rk=frame.rank(axis=1,method='first',pct=True)
        masks[key+' 하위20%']=(rk<=.2).to_numpy()&present
        masks[key+' 상위20%']=(rk>.8).to_numpy()&present
    grow=[]
    for label,m in masks.items():
        rr=np.where(m,rets[40],np.nan);v=nanmean(rr,axis=1)
        a=cats['KOSPI']=='A';other=np.isin(cats['KOSPI'],['B','C','D'])
        n=np.isfinite(rr).sum(axis=1);live=(a|other)&np.isfinite(v)
        grow.append([label,*boot.diff(v,a,other,40),f'{n[live].min()}~{n[live].max()}'])
    sec += [tab(['종목군','A 날(비겹침)','나머지 날(비겹침)','A 평균','나머지 평균','차이 [95%]','유효 재표집','날별 종목 n'],grow)]

    sec += ['## 6. 2026 동결 모델 — 시장별 상위10',
            '- 요청의 “등록 후 앵커 전부”를 우선하여 부분실행/이중실행 게이트로 추가 제외하지 않았다. 비거래일 run은 직전 거래일로 대응하고 중복 앵커는 거래일 run 우선, 없으면 가장 이른 run 1개로 대표한다(leaderboard 순수 함수). 아래는 판정용 §11 표본과 다를 수 있다. 등록 전 점수는 제외, 점프컷 없음. 같은 점수면 ticker순. 상위10 선정 후 가격 없는 종목을 다음 순위로 대체하지 않는다.',
            '- 절대수익은 해당 시장 top10의 유효 종목 동일가중, 초과는 같은 t의 같은 시장 전 종목 동일가중 수익을 뺀 값. 지수 기준을 KOSPI/KOSDAQ으로 각각 적용하여 같은 시장 기준과 교차 시장 기준을 모두 보인다. 짧은 2026 표본은 같은 상승·하락 사이클을 공유하므로 독립적인 재현이 아니다.']
    env=extract('leaderboard.py',['anchor','dedupe_by_anchor','build_gates'],dict(np=np,pd=pd,GATE_FRAC=.30,
            TRACKS={'v3':('v3_scores','final_score_v3',None),'lv':('lowvol_scores','lowvol_score',None),'wu':('wu_scores','wu_score',None)}))
    tr=ast.parse((ROOT/'checkup.py').read_text(encoding='utf-8-sig'))
    reg=next(ast.literal_eval(x.value) for x in tr.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REG_DATE' for t in x.targets))
    didx={d:i for i,d in enumerate(dates)};ti={t:i for i,t in enumerate(ticks)}
    modelrows=[];modelmeta=[];score_missing=[]
    with ro(paths[0]) as hcon:
        partial,double,_=env['build_gates'](hcon,list(dates))
        for mid,tb,col in [('v30','v3_scores','final_score_v3'),('lv_b','lowvol_scores','lowvol_score'),('le_a','wu_scores','wu_score')]:
            sc=pd.read_sql_query(f'SELECT run_id,market,ticker,{col} score FROM {tb} WHERE model_id=? AND run_id BETWEEN ? AND ? ORDER BY run_id,market,ticker',hcon,params=(mid,reg[mid],END))
            sc.market=sc.market.str.upper();keep=env['dedupe_by_anchor'](sc,didx,set(),reg=reg[mid])
            modelmeta.append([mid,reg[mid],sc.run_id.nunique(),len(keep),','.join(sorted(keep&(partial|double))) or '없음',int(sc.run_id.eq('20261014').sum())])
            for mk in ['KOSPI','KOSDAQ']:
                top=[]
                for rid,g in sc[sc.market==mk].groupby('run_id'):
                    if rid not in keep:continue
                    t=env['anchor'](rid,didx)
                    ts=g.dropna(subset=['score']).sort_values(['score','ticker'],ascending=[False,True]).head(10).ticker.tolist()
                    top.append((t,ts))
                for hor in [20,40]:
                    vals=np.full(T,np.nan);nn=np.zeros(T,int);picked=0;miss=0
                    for t,ts in top:
                        if t+1+hor>=T:continue
                        rr=np.array([rets[hor][t,ti[x]] if x in ti else np.nan for x in ts]);picked+=len(rr);miss+=int((~np.isfinite(rr)).sum())
                        vals[t]=nanmean(rr);nn[t]=np.isfinite(rr).sum()
                    excess=vals-by_market[hor][mk];score_missing.append([mid,mk,hor,picked,miss])
                    for ik in cats:
                        for cat in ['전체','A','B','C','D']:
                            mask=cats[ik]!='?' if cat=='전체' else cats[ik]==cat
                            v=mask&np.isfinite(vals)&np.isfinite(excess);pos=np.flatnonzero(v)
                            bm,be=boot.means(vals,v),boot.means(excess,v)
                            nmonth=len(set(boot.labels[v]));nb=int(np.isfinite(bm).sum())
                            modelrows.append([mid,mk,ik,hor,cat,f'{v.sum()} ({count_separate(pos,hor)})',
                                valci(nanmean(vals[v]),bm),valci(nanmean(excess[v]),be),
                                f'{nn[v].min()}~{nn[v].max()}' if v.any() else '0',f'{nmonth}/{nb}'])
    sec += [tab(['모델','등록일','등록 후 run 수','중복제거 앵커 수','정본 게이트라면 제외될 run','10/14 기존 점수행 n'],modelmeta),
            '- 관측월이 1개뿐인 칸은 같은 달을 반복해 구간 폭이 0이 될 수 있다. 그런 칸의 미래 성과 불확실성은 이 구간으로 확인 못 함. v30/lv_b의 없는 10/14 run은 만들지 않았고 le_a의 DB 기존 행은 포함했다.',
            tab(['모델','종목시장','진입지수','h','칸','앵커 n(비겹침)','절대수익 [95%]','동일시장 초과 [95%]','실제 보유종목 n','관측월/유효재표집'],modelrows),
            tab(['모델','시장','h','완결 앵커에서 선정한 종목×날 n','가격 대조 불가 n'],score_missing)]
    print('MODELS DONE',flush=True)

    # Cohort mark-to-market paths chosen using only t and entry t+1 availability.
    # Zero is entry; existing shares are held unchanged until 40 trading days.
    paths40=np.full((T,41),np.nan);entryn=np.zeros(T,int);missing_exit=0;complete_entry_n=0;forced_zero=0
    for t in range(T-1):
        m=present[t]&present[t+1];entryn[t]=m.sum()
        if not m.any():continue
        last=min(t+41,T-1);path=nanmean(mark[t+1:last+1,m]/c[t+1,m],axis=1)
        paths40[t,:len(path)]=path
        assert np.isclose(path[0],1)
        if t+41<T:
            missing_exit+=int((~present[t+41,m]).sum());complete_entry_n+=int(m.sum())
    common=np.flatnonzero((cats['KOSPI']!='?')&(cats['KOSDAQ']!='?')&(entryn>0))
    first=int(common[0]);simdates=dates[first+1:];D=len(simdates)
    sb=MonthBoot(simdates)
    # Actual elapsed calendar days also resampled with the monthly return blocks.
    prevdates=pd.to_datetime(dates[first:T-1]);currdates=pd.to_datetime(simdates)
    daygaps=(currdates-prevdates).days.to_numpy(float)
    RULES=['항상1','A만1','D면0','D면0.5','B·D면0.5']
    def fraction(rule,cat):
        if rule=='항상1':return 1.
        if rule=='A만1':return float(cat=='A')
        if rule=='D면0':return float(cat!='D')
        if rule=='D면0.5':return .5 if cat=='D' else 1.
        return .5 if cat in ['B','D'] else 1.
    def simulate(k,rule):
        cash=1.;active=[];curve=[];cashfrac=[];caps=0;invested=0.;finished_principal=0.;finished_profit=0.;cohorts=0;finished=0
        exit_principal=np.zeros(D);exit_profit=np.zeros(D)
        for d in range(first+1,T):
            # Active tuple: signal position, principal. No daily rebalance within a cohort.
            still=[]
            for t,a in active:
                age=d-(t+1);v=a*paths40[t,age]
                if age==40:
                    cash+=v;finished_principal+=a;finished_profit+=v-a-a*.005;finished+=1
                    exit_principal[d-first-1]+=a;exit_profit[d-first-1]+=v-a-a*.005
                else:still.append((t,a))
            active=still
            risk=sum(a*paths40[t,d-(t+1)] for t,a in active)
            nav=cash+risk;t=d-1
            frac=fraction(rule,cats[k][t]) if cats[k][t]!='?' else 0.
            desired=nav/40*frac
            actual=min(desired,max(cash,0)/1.005) if entryn[t]>0 else 0.
            if actual+1e-12<desired:caps+=1
            if actual>0:
                cash-=actual*1.005;active.append((t,actual));invested+=actual;cohorts+=1;risk+=actual
            nav=cash+risk
            assert nav>0 and cash>=-1e-12 and len(active)<=40
            curve.append(nav);cashfrac.append(max(cash,0)/nav)
        curve=np.array(curve);cashfrac=np.array(cashfrac)
        r=curve/np.r_[1.,curve[:-1]]-1
        dd=curve/np.maximum.accumulate(np.r_[1.,curve])[1:]-1
        total=(curve[-1]-1)*100;ann=(curve[-1]**(365.25/daygaps.sum())-1)*100
        invested_ret=finished_profit/finished_principal*100 if finished_principal else np.nan
        return dict(curve=curve,r=r,cash=cashfrac,total=total,ann=ann,mdd=dd.min()*100,
                    avgcash=cashfrac.mean()*100,weighted=invested_ret,cohorts=cohorts,finished=finished,caps=caps,
                    invested=invested,finished_principal=finished_principal,profit=finished_profit,
                    exit_principal=exit_principal,exit_profit=exit_profit)
    def sim_ci(v):
        # Resample whole observed months; recompute path drawdown, not monthly endpoint drawdown.
        groups=[np.flatnonzero(sb.labels==m) for m in sb.months];rng=np.random.default_rng(SEED)
        vals=np.empty((B,4))
        for b in range(B):
            pick=np.concatenate([groups[j] for j in rng.integers(0,len(groups),len(groups))])
            wealth=np.cumprod(1+v['r'][pick]);peak=np.maximum.accumulate(np.r_[1.,wealth])[1:]
            vals[b]=[(wealth[-1]-1)*100,(wealth[-1]**(365.25/daygaps[pick].sum())-1)*100,
                     (wealth/peak-1).min()*100,v['cash'][pick].mean()*100]
        return [iv(vals[:,i]) for i in range(4)]
    sims={};simrows=[]
    for k in cats:
        for rule in RULES:
            v=simulate(k,rule);sims[k,rule]=v;ci=sim_ci(v)
            num=np.bincount(sb.mi,weights=v['exit_profit'],minlength=len(sb.months))
            den=np.bincount(sb.mi,weights=v['exit_principal'],minlength=len(sb.months))
            bden=sb.w@den
            bweighted=np.divide(sb.w@num,bden,out=np.full(B,np.nan),where=bden>0)*100
            simrows.append([k,rule,f"{D} ({count_separate(np.arange(first+1,T),40)})",
                *[f'{f(v[key])} {ci[j]}' for j,key in enumerate(['total','ann','mdd','avgcash'])],
                f"{v['cohorts']}/{v['finished']}",valci(v['weighted'],bweighted),v['caps']])
    assert np.allclose(sims['KOSPI','항상1']['curve'],sims['KOSDAQ','항상1']['curve'])
    sec += ['## 7. 단순 규칙 모의 — 전부 사후 탐색',
        f'- 공동 신호 시작 {dates[first]}, 최초 체결 {simdates[0]}, 평가 종료 {END}. 날짜별 시작 전 자산의 1/40×해당 비율을 새 슬롯에 배정하고 현금이 모자라면 현금 범위로 줄인다. 40거래일 보유 후 종가 청산, 만기 자금은 같은 날 새 슬롯에 쓸 수 있다. 현금 이자 0. 기존 보유는 규칙 변경으로 팔지 않는다. 현금 100%에서 시작하는 초기 40일 진입 증가 구간과 끝의 미완결 보유를 포함한다.',
        '- 왕복 비용은 투자 원금의 0.5%를 진입 때 한 번 현금 차감한다(완결 슬롯의 원금 대비 순수익은 총수익−0.5%p). 자산 매입과 비용까지 현금으로 충당한다. 종목 선정은 신호일과 진입일 시세만 보며 미래 청산값 존재 여부로 고르지 않는다. 개별 보유주식 수는 고정한다. 배당·이자·시장충격·실거래 체결가능성은 반영하지 않았다.',
        f'- 보유 중 가격 누락은 직전 가격으로 평가하고 만기에도 그 평가액을 현금화한 것으로 처리했다. 완결 슬롯의 종목×진입 {complete_entry_n:,}쌍 중 만기 실제 가격 누락 {missing_exit:,}쌍. 실제 청산 가능 가격은 확인 못 함. 따라서 이 모의는 실현 가능한 수익의 보장이 아니며, 끝값 결측을 버리는 기본 표와 표본 처리도 다르다. 거래정지 종목도 요청 정의상 포함된다.',
        '- 총수익=최종자산/초기자산−1, 연환산은 실제 달력 경과일 365.25일 기준, 최대낙폭은 일별 평가자산의 이전 최고점 대비 하락, 평균현금은 일별 현금/자산 평균. 모의 구간은 관측된 일별 순수익을 월째 이어 붙여 계산한 참고 95%이며, 재표집 경로에서 규칙을 새로 재실행한 것이 아니다.',
        '- 추가 지표: **집행금 가중 완결 슬롯 순수익**=완결 슬롯 순손익 합/그 슬롯 투자원금 합. 쉬고 있던 현금을 분모에서 빼므로 “투자를 적게 해서 덜 잃음”과 “집행한 돈의 수익률 개선”을 구분하는 보조 수치다. 재투자되는 원금을 반복 합산하는 40일 단위 지표라 계좌 총수익·연환산과 같지 않다. 아직 열린 슬롯은 이 지표에서 제외한다. 구간은 청산월별 순손익과 투자원금을 함께 재표집한 95%이다.',
        tab(['지수','규칙','평가일 n(40일 비겹침)','총수익 [95%]','연환산 [95%]','최대낙폭 [95%]','평균현금 [95%]','진입/완결 슬롯 n','집행금 가중 순수익 [95%]','현금제약 일수'],simrows)]
    print('SIM DONE',[(k,r,round(v['total'],3)) for (k,r),v in sims.items()],flush=True)

    # One observable explanation: same/different signals and contemporaneous future market returns.
    diag=[]
    for k in cats:
        for mk in by_market[40]:
            a=cats[k]=='A';other=np.isin(cats[k],['B','C','D'])
            diag.append([k,mk,*boot.diff(by_market[40][mk],a,other,40)])
    co=[];valid=(cats['KOSPI']!='?')&(cats['KOSDAQ']!='?')
    for name,m in [('둘 다 A',(cats['KOSPI']=='A')&(cats['KOSDAQ']=='A')),
                   ('코스피만 A',(cats['KOSPI']=='A')&(cats['KOSDAQ']!='A')),
                   ('코스닥만 A',(cats['KOSDAQ']=='A')&(cats['KOSPI']!='A'))]:
        co.append([name,*boot.stats(daily[40],m&valid,40)['row']])
    sec += ['## 8. 해석과 사후 탐색의 낙관 — 실측과 의견 분리',
        '### (c) 두 지수 기준이 다를 때 자료로 볼 수 있는 것',
        '- 실측: 같은 전 종목 바스켓이라도 두 지수가 A로 분류하는 날짜가 다르다. 아래 겹침/비겹침 표와 종목시장별 h40 차이를 보면 “같은 날 종목시장이 다른 효과”와 “신호 날짜 선택이 다른 효과”를 구분할 단서를 얻을 수 있다. 산업구성·해외 변수 등이 원인이라고 이 표만으로 단정하지 않는다.',
        tab(['A 날짜 조합','날 수(비겹침)','평균 [95%]','중앙값 [95%]','승률 [95%]','하위10% [95%]'],co),
        f'- 실측: 둘 다 A인 날은 n(비겹침)={co[0][1]}, h40 {co[0][2]}%; 코스닥만 A인 날은 n(비겹침)={co[2][1]}, h40 {co[2][2]}%. 코스닥 A에는 공통 급락 외의 낮은 사후수익 날짜가 추가로 포함되는 구성이 관측된다. 이것은 날짜 구성의 분해이며 경제적 원인을 증명하지 않는다.',
        tab(['신호 지수','보유 종목시장','A 날(비겹침)','나머지 날(비겹침)','A 평균','나머지 평균','차이 [95%]','유효 재표집'],diag),
        '### (a) 가장 큰 낙관이 숨는 곳 — 검토 의견',
        '- 가장 큰 문제는 많은 겹친 매수일을 독립 반복으로 읽는 것이다. 위의 비겹침 수조차 같은 폭락·회복 사이클을 공유할 수 있다. 월 블록 구간도 h40/60의 달 사이 겹침을 모두 제거하지 못한다. 사건 한 건씩 뺀 표와 연도별 차이가 전체 평균보다 먼저 확인할 근거다.',
        '- 문턱 4×되돌아보기 3×지수 2×보유 2만으로 48개 셀이고, 지속일·깊이·종목군·3모델·5규칙·여러 성과지표를 더 봤다. 각 95% 구간은 이 선택 수를 보정하지 않는다. 같은 3년에서 발견·설명·규칙 모의까지 하면 그럴듯한 셀을 고르기 쉽다. 기본 −5%/20일 정의도 이미 탐색을 거쳐 제시됐을 수 있다.',
        '- “전 종목”은 로컬 DB에 있는 종목이다. 초기 수집대상·상장폐지 누락·거래정지 체결불가·수정주가 미확인·끝값 결측 탈락/직전가 평가가 실제 손실을 숨길 수 있다. 점프컷은 요청대로 하지 않았다. 아래 가격 점프 수와 결측률을 함께 봐야 한다.',
        '- 초반/깊이/종목군 분할은 시장 하락의 원인과 무관한 인과효과가 아니다. A가 켜질 때까지 이미 떨어진 가격에 들어간 것과 침체가 지속될 가능성이 함께 있다. 조건부 평균이 양수여도 개별 투자자의 손실 확률이나 다음 사건 반등을 보장하지 않는다.',
        '- 규칙의 낮은 낙폭 중 얼마가 국면 신호이고 얼마가 높은 현금 비중 때문인지는 동일 평균 노출의 상시 투자 대조 없이 분리하지 못했다. 집행금 기준 수익은 보조 지표이지 이 문제를 해결하는 인과 검증이 아니다.',
        '### (b) 사전등록할 가치가 있는 가설 하나 — 제안, 미등록',
        '- **가설:** 코스피 R20≤−5% 이후 다음날 전 종목 바스켓의 40일 순수익이, 앞으로 새로 쌓일 A 아닌 날의 동일 바스켓보다 높다. 이 요청의 기본 정의 1개만 후보로 남기며 더 좋아 보인 격자로 문턱을 바꾸지 않는다. 코스피를 후보로 고른 것 자체는 이번 결과를 보고 한 사후 선택이다. 매수 축소 규칙 채택으로 연결하지 않는다.',
        '- 검증 설계 제안: 승인·동결 다음 거래일부터 수집한 자료만 사용. A 진입은 전날 비A→A, 사건 간 40거래일 이상; A 사건 8개 이상, 비교 사건 8개 이상, 2개 이상의 달력연도에 걸친 표본을 확보한 뒤 1회 평가. 8개/2년은 이번 데이터가 증명한 최적값이 아니라 사전에 정할 최소 관측량 제안이다. 0.5% 비용과 당시 존재한 종목/청산결측 처리도 먼저 고정한다.',
        '- **반증 기준:** A−나머지 40일 순수익 차이의 사전 고정 블록 95% 구간 상단≤0이면 양의 우위 가설을 기각. 구간이 0을 포함하면 결론 보류, 하단>0이어도 한 사건 제외 시 부호가 뒤집히면 견고한 우위로 채택하지 않는다. 최소 관측량을 채우기 전이나 정한 종료시점에 미달이면 “자료 부족”이다. 실제 사전등록·운영 반영은 하지 않았다.']

    # Explicit data caveats and optional scalar interpretation, not selected winner.
    actual_change=C.pct_change(fill_method=None).abs().to_numpy()
    jumps=np.isfinite(actual_change)&(actual_change>.32)
    deficit=[]
    for hor in [20,40,60]:
        live=np.arange(T)+1+hor<T
        numerator=int(counts[hor][live].sum());denominator=int(candidate[hor][live].sum())
        deficit.append([hor,int(live.sum()),int(count_separate(np.flatnonzero(live),hor)),numerator,denominator-numerator,
                        f'{100*(denominator-numerator)/denominator:.3f}'])
    sec += ['## 9. 자료 한계·재현 검증',
        tab(['h','완결 가능한 신호일 n','비겹침 수','유효 종목×날','진입/청산값 결측 쌍','결측률 %'],deficit),
        f'- 로컬 close로 직접 계산한 일간 절대변화>32%는 {int(jumps.sum()):,}건(유효 일간 쌍 {int(np.isfinite(actual_change).sum()):,}); 모두 유지했다. DB is_suspended=1인 행은 {int(p.is_suspended.eq(1).sum()):,}건. 따라서 이 결과는 거래 가능한 정제 바스켓의 성과가 아니다.',
        f'- 지수 R20 계산 못 한 초기 날짜: {[(k,dates[cats[k]=="?"].tolist()) for k in cats]}. 각 지수/시세의 로컬 날짜 집합은 일치하지만 공통으로 빠진 실제 거래일이 없는지는 외부 달력 없이 확인 못 함. 날짜 축은 로컬 데이터 기준이다. 20261014 모델 run 결손 등은 추가 생성하지 않았다.',
        '- 비율/결측 수는 관측 자료의 전수 집계이고 표본 불확실성 구간을 붙여도 수집누락 자체의 불확실성을 설명하지 못한다. 성과·승률·집행금 추가지표의 구간은 각 표의 월 블록 구간을 참조한다.',
        f'- 검증: 종목/날 중복 없음; 지수·시세 날짜 집합 일치; 임의 셀 {checked}개의 t+1/t+1+h 직접 계산 일치; 월 블록 평균을 실제 반복표본과 대조; 사건 경로 끝값과 h40 수익 일치; 모의 현금≥0·동시 보유≤40·시작값 1·항상1의 지수 간 완전 일치. 금지 파일 내용과 대조하지 않았다.',
        '- 재현: `python -B research/handoff/code_20261020_entry_regime_blind.py`. numpy·pandas·threadpoolctl 필요. 지수·시세 종료일 20261019 고정, DB mode=ro/query_only. 제어 코드/등록일은 AST로 필요한 부분만 추출하여 운영 모듈을 import하지 않았다. 외부 호출·배치·수집·운영 DB 쓰기 없음. 이 코드와 REPLY만 생성하며 큰 중간 파일 없음.',
        f'- 신호 날짜 축 SHA256 `{hashlib.sha256("|".join(dates).encode()).hexdigest()}`. 과거 DB 값이 수정되면 같은 종료일로도 결과가 달라질 수 있다.']
    # State direct observations without choosing the best rule after seeing them.
    arows=[]
    for k in cats:
        st=base_results[k,40,'A'];nn,positive=event_count_return[k,40]
        arows.append(f"{k} A h40 평균 {st['row'][1]}%, 날 n={st['n']}(비겹침 {st['ne']}), 첫 진입 사건 양수 {positive}/{nn}")
    sec += ['## 결론 한 줄',
            '**하락 뒤 매수의 결과는 지수·사건·시기에 조건부다: '+ '; '.join(arows)+ ' — 과거 평균으로 다음 하락의 반등을 보장할 수 없으며 규칙은 미채택.**']
    assert before==[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths], 'Input DB changed'
    sec += ['- 읽은 두 DB의 실행 전후 크기·수정시각 동일(전체 내용 해시 확인은 아님). 운영·점수·판정·docs 파일은 이 감사에서 변경하지 않았다.']
    guard();OUT.write_text('\n\n'.join(sec)+'\n',encoding='utf-8')
    print('CONCLUSION',arows,flush=True);print('WROTE',OUT,OUT.stat().st_size,flush=True)


if __name__=='__main__':
    with threadpool_limits(limits=2):
        main()
