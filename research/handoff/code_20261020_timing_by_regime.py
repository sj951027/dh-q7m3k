"""Offline paired timing exploration. Only writes the companion REPLY.
Run from repo root: python -B research/handoff/code_20261020_timing_by_regime.py
Uses the prior independent audit's pure helpers; never runs its main.
No network, production edits, DB writes, extra OHLCV, or result-dependent grid.
"""
from pathlib import Path
import ast
import hashlib
import warnings
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from code_20261020_entry_regime_blind import (
    ROOT, guard, ro, extract, classify, greedy, count_separate, MonthBoot,
    nanmean, f, iv, valci, tab, B, SEED,
)

OUT=Path(__file__).with_name('REPLY_20261020_timing_by_regime.md')
START='20230626'


def bounds(x):
    x=np.asarray(x);x=x[np.isfinite(x)]
    return np.quantile(x,[.025,.975]) if len(x)>1 else np.array([np.nan,np.nan])


def run():
    guard()
    dbs=[ROOT.parent/'dh-q7m3k-data/ohlcv.db',ROOT/'history.db']
    before=[(p.stat().st_size,p.stat().st_mtime_ns) for p in dbs]
    with ro(dbs[0]) as con:
        p=pd.read_sql_query('SELECT date,ticker,close,market,is_suspended FROM daily_ohlcv WHERE date>=? ORDER BY date,ticker',con,params=(START,))
        ix=pd.read_sql_query("SELECT date,series,close FROM market_daily WHERE series IN ('KOSPI','KOSDAQ') ORDER BY date,series",con)
    dates=pd.Index(sorted(p.date.unique()));ticks=pd.Index(sorted(p.ticker.unique()))
    T,N=len(dates),len(ticks);end=dates[-1]
    assert not p.duplicated(['date','ticker']).any()
    C=p.pivot(index='date',columns='ticker',values='close').reindex(index=dates,columns=ticks)
    raw=C.to_numpy(float);live=np.isfinite(raw)&(raw>0)
    mark=C.where(C>0).ffill().to_numpy(float)
    indices=ix.pivot(index='date',columns='series',values='close').sort_index().loc[:end]
    assert set(dates)==set(indices.index[indices.index>=START])
    indexclose=indices.reindex(dates)
    r20={k:indices[k].pct_change(20,fill_method=None).reindex(dates).to_numpy() for k in indices}
    cats={k:classify(r20[k]) for k in indices}
    cross={}
    for k in indices:
        full=classify(indices[k].pct_change(20,fill_method=None).to_numpy())
        for cat in ['A','D']:
            ds=set(indices.index[(full==cat)&np.r_[False,full[:-1]!=cat]])
            cross[k,cat]=np.array([d in ds for d in dates])
    events={k:greedy(np.flatnonzero(cross[k,'A']),40) for k in indices}
    # Read only pure classification function: check equality without importing module.
    op=extract('regime_ad.py',['cell_of'],{'TH_DOWN':-.05,'TH_UP':.05})['cell_of']
    for k in cats:
        assert all((op(v) or '?')==c for v,c in zip(r20[k],cats[k]))
    boot=MonthBoot(dates);audit={};flags=[];output=[]
    print('DATA',T,N,end,'A events', {k:[dates[t] for t in v] for k,v in events.items()},flush=True)

    def note(name,base,kept):
        v=audit.setdefault(name,[0,0,0])
        v[0]+=1;v[1]+=base;v[2]+=base-kept

    def get_ids(t,selection=None):
        ids=np.flatnonzero(live[t]) if selection is None else np.asarray(selection,dtype=int)
        return ids[live[t,ids]]

    def shared(t,required,selection,name):
        ids=get_ids(t,selection);n=len(ids)
        ids=ids[np.all(live[np.asarray(sorted(set(required)))[:,None],ids],axis=0)]
        note(name,n,len(ids))
        return ids

    def path_one(entry,exit_,ids):
        path=nanmean(mark[entry:exit_+1,ids]/raw[entry,ids],axis=1)-1
        assert abs(path[0])<1e-12
        ret=float(nanmean(raw[exit_,ids]/raw[entry,ids]-1)*100)
        assert np.isclose(path[-1]*100,ret,atol=1e-9)
        return ret,float(path.min()*100)

    def paired_records(t,selection=None,k='KOSPI',tag='전종목'):
        """Three entries, own 40-day holding periods, same endpoint-complete basket."""
        e=t+1
        ups=np.flatnonzero(indexclose[k].to_numpy()[t+1:]>indexclose[k].to_numpy()[t:-1])
        if not len(ups):return []
        up=t+1+int(ups[0]);entries=[e,up+1,e+5]
        assert indexclose[k].iloc[up]>indexclose[k].iloc[up-1]
        assert not np.any(indexclose[k].to_numpy()[t+1:up]>indexclose[k].to_numpy()[t:up-1])
        if max(entries)+40>=T:return []
        ids=shared(t,entries+[a+40 for a in entries],selection,tag+'/1 공통')
        if not len(ids):return []
        vals=[path_one(a,a+40,ids) for a in entries]
        return [dict(t=t,rule=rule,k=k,ret=v[0],low=v[1],base=vals[0][0],blow=vals[0][1],
                     hold=40,bhold=40,n=len(ids),entry=a,exit=a+40,
                     wait=a-e) for rule,a,v in zip(['즉시','상승확인','5일대기'],entries,vals)]

    def split_records(t,selection=None,tag='전종목'):
        e=t+1;x=e+40
        if x>=T:return []
        ids=shared(t,list(range(e,e+5))+[x],selection,tag+'/2 공통')
        if not len(ids):return []
        result=[]
        for days in [1,3,5]:
            curve=np.ones(41)
            # Each tranche owns 1/days capital; unspent tranches stay as cash.
            for offset in range(days):
                curve[offset:]+=(nanmean(mark[e+offset:x+1,ids]/raw[e+offset,ids],axis=1)-1)/days
            ret=(curve[-1]-1)*100;low=(curve.min()-1)*100
            if days==1:
                br,bl=path_one(e,x,ids)
                assert np.isclose(ret,br) and np.isclose(low,bl)
                ret,low=br,bl  # identical rule: avoid floating-point phantom differences
            direct=np.mean([nanmean(raw[x,ids]/raw[e+j,ids]-1) for j in range(days)])*100
            assert np.isclose(ret,direct,atol=1e-9)
            result.append(dict(t=t,rule=f'{days}일',ret=ret,low=low,base=br,blow=bl,
                               hold=40,bhold=40,n=len(ids),entry=e,exit=x))
        return result

    def regime_records(t,selection=None,tag='전종목'):
        e=t+1;base=e+40
        if base>=T or cats['KOSPI'][t]=='?':return []
        scan=np.arange(e+1,base+1)  # holding starts AFTER entry close
        d=scan[cross['KOSPI','D'][scan]]
        a=scan[cross['KOSPI','A'][scan]]
        gain=scan[r20['KOSPI'][scan]>=r20['KOSPI'][e]+.10]
        exits=[int(d[0]) if len(d) else base,base+20 if len(a) else base,
               int(gain[0]) if len(gain) else base]
        if max(exits)>=T:return []
        ids=shared(t,[e,base]+exits,selection,tag+'/3 공통')
        if not len(ids):return []
        br,bl=path_one(e,base,ids);out=[]
        for rule,x in zip(['D전환청산','A전환20일연장','R20+10%p청산'],exits):
            ret,low=path_one(e,x,ids)
            out.append(dict(t=t,rule=rule,ret=ret,low=low,base=br,blow=bl,hold=x-e,bhold=40,
                            n=len(ids),entry=e,exit=x,changed=int(x!=base)))
        return out

    def stop_records(t,selection=None,tag='전종목'):
        e=t+1;base=e+40
        if base>=T or cats['KOSPI'][t]=='?':return []
        ids=get_ids(t,selection)
        ids=ids[live[e,ids]&live[base,ids]];initial=len(get_ids(t,selection))
        if not len(ids):return []
        exits=[];hits=[]
        # A close breach at age 1..39 executes at the next close, never beyond fixed exit.
        rel=raw[e+1:base,ids]/raw[e,ids]
        for threshold in [.10,.15]:
            hit=(rel<=1-threshold)&np.isfinite(rel)
            anyhit=hit.any(axis=0);exit_=np.where(anyhit,e+2+hit.argmax(axis=0),base)
            assert np.all(exit_<=base) and np.all(exit_>=e+1)
            exits.append(exit_);hits.append(anyhit)
        ok=np.ones(len(ids),bool)
        for ex in exits:ok &= live[ex,ids]
        ids=ids[ok];exits=[x[ok] for x in exits];hits=[x[ok] for x in hits]
        note(tag+'/4 공통',initial,len(ids))
        if not len(ids):return []
        br=float(nanmean(raw[base,ids]/raw[e,ids]-1)*100);out=[]
        for rule,ex,hit in zip(['손절-10%','손절-15%'],exits,hits):
            rr=(raw[ex,ids]/raw[e,ids]-1)*100
            if t in [100,300,600] and selection is None:
                threshold=.10 if rule=='손절-10%' else .15
                check=[]
                for sid in ids:
                    outday=base
                    for day in range(e+1,base):
                        if np.isfinite(raw[day,sid]) and raw[day,sid]<=raw[e,sid]*(1-threshold):
                            outday=day+1
                            break
                    check.append((raw[outday,sid]/raw[e,sid]-1)*100)
                assert np.allclose(rr,check,atol=1e-9)
            out.append(dict(t=t,rule=rule,ret=float(rr.mean()),base=br,n=len(ids),
                            hold=float((ex-e).mean()),bhold=40,trigger=int(hit.sum()),entry=e,exit=base))
        return out

    def vec(records,key,mask=None):
        a=np.full(T,np.nan)
        for z in records:
            if mask is None or mask(z):a[z['t']]=z[key]
        return a

    def mean_ci(x):return valci(nanmean(x),boot.means(x))

    def paired(records,section,label,h=40):
        if not records:return ['0 (0/0)','확인 못 함','확인 못 함','확인 못 함','0/0']
        b=vec(records,'base');v=vec(records,'ret');delta=v-b
        bs=boot.means(delta);ci=bounds(bs);pos=np.flatnonzero(np.isfinite(delta))
        if np.all(np.isfinite(ci)) and ci[0]*ci[1]>0:
            flags.append([section,label,'수익 차이',len(pos),count_separate(pos,h),valci(nanmean(delta),bs)])
        nm=len(set(boot.labels[pos]))
        return [f'{len(pos)} ({count_separate(pos,40)}/{count_separate(pos,60)})',
                mean_ci(b),mean_ci(v),valci(nanmean(delta),bs),f'{nm}/{np.isfinite(bs).sum()}']

    def other_difference(records,key,bkey,section,label,metric,h=40):
        if not records:return '확인 못 함'
        d=vec(records,key)-vec(records,bkey);bs=boot.means(d);ci=bounds(bs)
        pos=np.flatnonzero(np.isfinite(d))
        if np.all(np.isfinite(ci)) and ci[0]*ci[1]>0:
            flags.append([section,label,metric,len(pos),count_separate(pos,h),valci(nanmean(d),bs)])
        return valci(nanmean(d),bs)

    def observation(records):
        if not records:return '완결 짝표본이 없어 차이를 확인 못 함.'
        d=vec(records,'ret')-vec(records,'base')
        pos=np.flatnonzero(np.isfinite(d))
        return f"n={len(pos)}(40일 비겹침 {count_separate(pos,40)}), 수익 짝차이 {mean_ci(d)}%p"

    sec=['# REPLY — 시장 상황별 매매 시점 독립 탐색 (2026-10-20)',
         '## 0. 범위·정의·눈가림',
         '- **사후 탐색이며 규칙 채택·판정이 아니다.** 이번에 금지된 Claude 연구·코드·out_entry_regime·게이트 초안·모의계좌 설계·PTW 코드를 열지 않았다. 다만 이전 요청 때 게이트 초안을 이미 읽었고, 필수 최신 worklog에는 게이트 방향과 이전 조사 요약이 노출됐다. 완전히 방향을 모르는 눈가림이라고 할 수 없다. 이번의 문턱·기간·규칙은 요청서에 고정된 것만 썼다.',
         f'- 실측 입력: daily_ohlcv {len(p):,}행 / {N:,}종목 / {T}개 로컬 거래일, {START}~{end}(실행 때 최신). daily_ohlcv_extra 미사용. 지수 R20은 그 이전 로컬 지수도 사용한다. regime_ad.py의 순수 cell_of와 모든 날짜 분류가 일치함을 확인했다. 외부 날짜 달력·수정주가·실거래 체결 가능성은 확인 못 함.',
         '- 전 종목은 신호일 t에 가격이 있는 로컬 종목이며, 한 비교 묶음의 모든 매수·청산가격이 있는 **동일 종목 교집합**을 사용했다. 한 사건 안에서는 모든 규칙의 종목과 최초 배분금액이 같다. 종목을 시점마다 새로 고르지 않는다. 날짜/사건별 바스켓 수익을 동일가중한다. 비교 간 교집합이 달라 이전 REPLY의 무조건부 평균과 직접 같을 필요는 없다. 미래 가격 존재 여부를 요구하는 생존편향은 남으며, 탈락 수를 마지막 표에 적었다.',
         '- 짝차이는 규칙−즉시/40일 기준(%p). §1~4·6은 비용 전, §5 모의만 왕복 비용 0.5%. 경로 최저는 투자원금 1 대비 종가 평가자산의 최저수익(시작 0% 포함), 고점 대비 최대낙폭과 다르다. 중간 누락가격은 마지막 종가로 평가하고, 실제 매수/청산 가격 누락은 교집합에서 제외한다. 정지·점프 필터는 쓰지 않는다.',
         '- [ ]는 월 블록 4,000회 seed 7의 95% 구간. 같은 달을 모든 규칙에 함께 복원추출해 짝차이를 계산한다. n은 신호일/사건 수, 괄호는 시간순 **40일/60일** 간격으로 고른 수다. §1의 지연창은 서로 겹칠 수 있고 §3의 60일 보유도 있어 60일 간격을 함께 보인다. 이 수가 경제적으로 독립인 하락·회복 수를 보장하지 않는다. 달을 넘는 창의 상관 및 여러 비교를 보정하지 않았다.',
         '- 단일 사건의 실측에는 신뢰구간을 붙일 수 없어 날짜별 행은 값만 적고 집계 행에 구간을 붙인다. 관측월 1개의 재표집은 구간 폭이 0일 수 있으며 미래 불확실성을 측정하지 못한다. 미완결은 그 비교 묶음 전체에서 제외한다. 빈 칸은 “확인 못 함”이다.']

    # 1. Delay: actual A transitions spaced 40, both index definitions.
    delay={};rows=[]
    for k in ['KOSPI','KOSDAQ']:
        zz=[r for t in events[k] for r in paired_records(t,k=k)]
        delay[k]=zz
        for rule in ['즉시','상승확인','5일대기']:
            rr=[r for r in zz if r['rule']==rule]
            pp=paired(rr,'1',k+'/'+rule)
            rows.append([k,'집계',rule,*pp[:4],mean_ci(vec(rr,'blow')),mean_ci(vec(rr,'low')),
                         other_difference(rr,'low','blow','1',k+'/'+rule,'최저경로 차이'),
                         mean_ci(vec(rr,'wait')),pp[4]])
        for z in zz:
            rows.append([k,dates[z['t']],z['rule'],'1 (1/1)',f(z['base']),f(z['ret']),f(z['ret']-z['base']),
                         f(z['blow']),f(z['low']),f(z['low']-z['blow']),
                         f"{z['wait']}일; {dates[z['entry']]}→{dates[z['exit']]}",
                         f"종목 {z['n']}"])
    sec+=['## 1. 사는 날을 미루면',
          '- 즉시=t+1. 상승확인은 t 이후(t+1부터) 해당 지수 종가가 전일보다 처음 오른 날을 확인하고 그 다음날 종가 매수한다. 5일대기는 즉시보다 5거래일 늦은 t+6 매수. 각각 실제 매수일부터 40거래일 보유한다. 상승일까지 대기기간에는 수익·이자가 없으며 최저경로는 실제 매수 후부터다. 세 방식 모두 완결된 동일 사건·종목만 비교한다.',
          tab(['지수','사건/집계','규칙','n(40/60 비겹침)','즉시 수익','규칙 수익','짝차이 [95%]','즉시 최저','규칙 최저','최저 짝차이 [95%]','대기일 [95%]/매수→매도','관측월/유효재표집 또는 종목 n'],rows),
          '- 실측 1: 코스피 상승확인 — '+observation([z for z in delay['KOSPI'] if z['rule']=='상승확인'])+'.',
          '- 실측 2: 코스닥 상승확인 — '+observation([z for z in delay['KOSDAQ'] if z['rule']=='상승확인'])+'; 날짜 경과 규칙이 가격 확인으로 개선됐는지는 이 짝차이로 읽는다.']
    print('DELAY DONE',flush=True)

    # 2. Capital path, paired distribution change using exact repeated-month sample.
    split=[r for t in events['KOSPI'] for r in split_records(t)]
    rows=[]
    for rule in ['1일','3일','5일']:
        rr=[r for r in split if r['rule']==rule];pp=paired(rr,'2',rule)
        vals=vec(rr,'ret');base=vec(rr,'base');pos=np.flatnonzero(np.isfinite(vals))
        x=vals[pos];y=base[pos];weights=boot.w[:,boot.mi[pos]]
        sd=[];worst=[];ds=[];dw=[]
        for w in weights:
            a=np.repeat(x,w);b=np.repeat(y,w)
            sd.append(np.std(a,ddof=1) if len(a)>1 else np.nan)
            ds.append(np.std(a,ddof=1)-np.std(b,ddof=1) if len(a)>1 else np.nan)
            worst.append(a.min() if len(a) else np.nan)
            dw.append(a.min()-b.min() if len(a) else np.nan)
        if len(x):
            stdval=np.std(x,ddof=1);sdiff=stdval-np.std(y,ddof=1);wdiff=x.min()-y.min()
            for metric,value,bs in [('표준편차 차이',sdiff,ds),('최악사건 차이',wdiff,dw)]:
                ci=bounds(bs)
                if ci[0]*ci[1]>0:flags.append(['2',rule,metric,len(pos),count_separate(pos,40),valci(value,bs)])
            dist=[valci(stdval,sd),valci(sdiff,ds),
                  f"{dates[pos[np.argmin(x)]]}: {valci(x.min(),worst)}",valci(wdiff,dw)]
        else:dist=['확인 못 함']*4
        rows.append([rule,*pp[:4],mean_ci(vec(rr,'low')),
                     other_difference(rr,'low','blow','2',rule,'최저경로 차이'),*dist,pp[4]])
    sec+=['## 2. 나눠 사면',
          '- 코스피 A 첫 진입 사건만, 총자금 1을 최초 바스켓에 1·3·5일 균등 분할한다. 매수일까지 미집행 자금은 현금(이자 0), 이미 산 주식 수는 유지한다. 마지막 분할일과 무관하게 첫 매수일+40에 전부 청산한다. 최저경로에는 이 현금도 포함한다. 사건 간 표준편차는 ddof=1. 최악 사건은 각 규칙의 최솟값이며, 최악값 차이 구간도 같은 월 표본을 함께 재추출했다.',
          tab(['분할','n(40/60 비겹침)','한번 매수 수익','분할 수익','수익 짝차이 [95%]','최저경로 평균 [95%]','최저경로 짝차이 [95%]','사건 표준편차 [95%]','표준편차 차이 [95%]','최악 사건/수익 [95%]','최악값 차이 [95%]','관측월/유효재표집'],rows),
          '- 실측 1: 3일 분할 — '+observation([z for z in split if z['rule']=='3일'])+'.',
          '- 실측 2: 5일 분할 — '+observation([z for z in split if z['rule']=='5일'])+'; 최악 사건과 표준편차는 위 표에서 별도로 비교했다.']

    # 3. Same-close market exits, literal requested convention.
    regimes=[r for t in range(T) for r in regime_records(t)]
    rows=[]
    for rule in ['D전환청산','A전환20일연장','R20+10%p청산']:
        rr=[r for r in regimes if r['rule']==rule]
        for z in rr:z['daily']=z['ret']/z['hold'];z['bdaily']=z['base']/40
        pp=paired(rr,'3',rule,60)
        rows.append([rule,*pp[:4],mean_ci(vec(rr,'hold')),mean_ci(vec(rr,'bdaily')),mean_ci(vec(rr,'daily')),
                     other_difference(rr,'daily','bdaily','3',rule,'하루당 수익 차이',60),
                     f"{sum(z['changed'] for z in rr)}/{len(rr)}",pp[4]])
    sec+=['## 3. 보유 중 장이 바뀌면',
          '- 모든 유효 신호일, 진입 후 다음 거래일(t+2)부터 기준 청산일(t+41)까지 살핀다. D전환은 비D→D의 첫 전환, A연장은 비A→A가 한 번이라도 있으면 20일만 연장(총60일); 이미 D/A에서 시작했다는 이유만으로 즉시 실행하지 않는다. +10%p 청산은 실제 매수일 t+1의 코스피 R20보다 10%p 이상 높아진 첫날이다. 조건 없으면 40일.',
          '- **요청대로 변화가 확인되는 당일 종가 청산을 계산했다.** 최종 지수 종가를 알아야 확정되는 신호와 같은 종가 체결을 동시에 가정하므로 실시간으로 보장할 수 없는 이상적 체결이다. 다른 다음날 청산 규칙으로 바꿔 계산하지 않았다. 연장 필요 여부와 최장 청산일까지 세 규칙 모두 완결된 공통 표본이다.',
          '- 하루당 수익은 각 사건 단순수익/실제 보유 거래일의 평균(%p/일), 연환산 아님. 조기청산 후 원래 40일까지 현금 이자는 0이며 다른 종목에 재투자하지 않는다. 하루당 비율이 높아도 남은 현금의 기회비용을 해결하지 않는다.',
          tab(['청산 규칙','n(40/60 비겹침)','40일 수익','규칙 수익','수익 짝차이 [95%]','평균 보유일 [95%]','기준 하루당','규칙 하루당','하루당 짝차이 [95%]','청산일 변경 n/전체','관측월/유효재표집'],rows),
          '- 실측 1: D전환 청산 — '+observation([z for z in regimes if z['rule']=='D전환청산'])+'.',
          '- 실측 2: A전환 연장 — '+observation([z for z in regimes if z['rule']=='A전환20일연장'])+'.']
    print('REGIME DONE',flush=True)

    # 4. Stock-level stop, next-day execution, aggregate into matched baskets.
    stops=[r for t in range(T) for r in stop_records(t)]
    rows=[];interactions={}
    for rule in ['손절-10%','손절-15%']:
        for grp in ['A','비A']:
            rr=[z for z in stops if z['rule']==rule and ((cats['KOSPI'][z['t']]=='A')==(grp=='A'))]
            pp=paired(rr,'4',rule+'/'+grp)
            rows.append([rule,grp,*pp[:4],mean_ci(vec(rr,'hold')),
                         f"{sum(z['trigger'] for z in rr):,}/{sum(z['n'] for z in rr):,}",pp[4]])
        zz=[z for z in stops if z['rule']==rule]
        delta=vec(zz,'ret')-vec(zz,'base')
        a=np.where(cats['KOSPI']=='A',delta,np.nan);b=np.where(np.isin(cats['KOSPI'],['B','C','D']),delta,np.nan)
        bs=boot.means(a)-boot.means(b);d=nanmean(a)-nanmean(b)
        interactions[rule]=(d,bounds(bs),valci(d,bs))
        n=np.isfinite(a).sum()+np.isfinite(b).sum()
        rows.append([rule,'차의 차 A−비A',f"{np.isfinite(a).sum()} / {np.isfinite(b).sum()}",
                     'A 손절−기준','비A 손절−기준',valci(d,bs),'해당 없음','해당 없음',int(np.isfinite(bs).sum())])
        ci=bounds(bs)
        if ci[0]*ci[1]>0:flags.append(['4',rule+'/A−비A','손절효과 차이',n,count_separate(np.flatnonzero(np.isfinite(delta)),40),valci(d,bs)])
    sec+=['## 4. 종목별 손절',
          '- 최초 매수가 대비 종가가 −10%/−15% 이하가 된 첫날의 **다음 거래일 종가**로 해당 종목만 청산하고 그 돈은 원래 40일 종료일까지 현금 보유한다. 최초 가격 기준 고정 손절이며 고점 추적 손절이 아니다. 보유 39일째까지 신호를 살펴 다음날 청산이 40일을 넘지 않게 한다. 기준 청산일의 하락은 이미 종료하므로 새 신호로 세지 않는다. 중간 누락 종가에는 새 손절 신호를 만들지 않는다.',
          '- 손절 신호가 있어도 갭으로 실제 손실이 −10%/−15%보다 커질 수 있다. 표의 손절 건수는 종목×매수일 수이며 독립 사건 수가 아니다. 두 손절 방식과 기준 모두 실제 청산가격이 있는 같은 바스켓으로 비교한다. “차의 차”가 음수이면 A에서 더 불리한 방향이다.',
          tab(['손절','진입칸','n(40/60 비겹침), 차의 차는 A/비A n','기준 수익','손절 수익','짝차이 [95%]','평균 종목보유일 [95%]','신호 종목×날/전체','관측월/유효재표집'],rows),
          '- 실측 1: −10% 손절 효과의 A−비A 차이는 '+interactions['손절-10%'][2]+'%p.',
          '- 실측 2: −15% 손절 효과의 A−비A 차이는 '+interactions['손절-15%'][2]+'%p. 각 칸의 단독 부호와 “A에서 특히”라는 차의 차는 다른 주장이다.']
    print('STOP DONE',flush=True)

    # 5. Match the average NEW-slot fraction literally, not tuned average exposure.
    first=int(np.flatnonzero(cats['KOSPI']!='?')[0])
    last_signal=T-42
    signals=np.arange(first,last_signal+1)
    assert last_signal+1+40==T-1
    q=float(np.mean(cats['KOSPI'][signals]!='D'))
    cpaths=np.full((T,41),np.nan);nsim=np.zeros(T,int);sim_missing=0;sim_pairs=0
    for t in signals:
        e=t+1;ids=np.flatnonzero(live[t]&live[e]);nsim[t]=len(ids)
        if not len(ids):continue
        cpaths[t]=nanmean(mark[e:e+41,ids]/raw[e,ids],axis=1)
        sim_pairs+=len(ids);sim_missing+=int((~live[e+40,ids]).sum())
    sd=dates[first+1:];sb=MonthBoot(sd);D=len(sd)
    def simulate(kind):
        cash=1.;active=[];curve=[];cf=[];principal=np.zeros(D);profit=np.zeros(D);caps=0;entered=0
        for d in range(first+1,T):
            keep=[]
            for t,a in active:
                age=d-t-1;value=a*cpaths[t,age]
                if age==40:
                    cash+=value;principal[d-first-1]+=a;profit[d-first-1]+=value-a-a*.005
                else:keep.append((t,a))
            active=keep;risk=sum(a*cpaths[t,d-t-1] for t,a in active)
            nav=cash+risk;t=d-1
            if t<=last_signal:
                frac=float(cats['KOSPI'][t]!='D') if kind=='D면0' else q
                desired=nav/40*frac
                amount=min(desired,max(cash,0)/1.005) if nsim[t] else 0.
                caps+=int(amount+1e-12<desired)
                if amount:
                    cash-=amount*1.005;risk+=amount;active.append((t,amount));entered+=1
            nav=cash+risk
            assert cash>=-1e-12 and len(active)<=40 and nav>0
            curve.append(nav);cf.append(max(cash,0)/nav)
        assert not active
        curve=np.array(curve);cf=np.array(cf);rr=curve/np.r_[1.,curve[:-1]]-1
        mdd=float((curve/np.maximum.accumulate(np.r_[1.,curve])[1:]-1).min()*100)
        return dict(curve=curve,r=rr,cash=cf,principal=principal,profit=profit,
                    weighted=profit.sum()/principal.sum()*100,mdd=mdd,entered=entered,caps=caps)
    sims={s:simulate(s) for s in ['D면0','상시축소']}
    draws=np.random.default_rng(SEED).integers(0,len(sb.months),(B,len(sb.months)))
    groups=[np.flatnonzero(sb.labels==m) for m in sb.months]
    sims_boot={}
    for name,v in sims.items():
        out=np.full((B,4),np.nan)
        for i,draw in enumerate(draws):
            take=np.concatenate([groups[j] for j in draw])
            wealth=np.cumprod(1+v['r'][take]);peak=np.maximum.accumulate(np.r_[1.,wealth])[1:]
            den=v['principal'][take].sum()
            out[i]=[v['profit'][take].sum()/den*100 if den else np.nan,
                    (wealth/peak-1).min()*100,v['cash'][take].mean()*100,(wealth[-1]-1)*100]
        sims_boot[name]=out
    rows=[]
    for name,v in sims.items():
        observed=[v['weighted'],v['mdd'],v['cash'].mean()*100,(v['curve'][-1]-1)*100]
        rows.append([name,f'{len(signals)} ({count_separate(signals,40)})',
                     v['entered'],*[valci(x,sims_boot[name][:,j]) for j,x in enumerate(observed)],v['caps']])
    ds=sims_boot['D면0']-sims_boot['상시축소']
    a=sims['D면0'];b=sims['상시축소']
    diffs=[a['weighted']-b['weighted'],a['mdd']-b['mdd'],
           (a['cash'].mean()-b['cash'].mean())*100,(a['curve'][-1]-b['curve'][-1])*100]
    rows.append(['D면0−상시축소',f'{len(signals)} ({count_separate(signals,40)})','위 두 계좌',
                 *[valci(x,ds[:,j]) for j,x in enumerate(diffs)],'해당 없음'])
    for j,metric in enumerate(['집행금 가중 순수익 차이','최대낙폭 차이']):
        ci=bounds(ds[:,j])
        if ci[0]*ci[1]>0:flags.append(['5','D면0−상시축소',metric,len(signals),count_separate(signals,40),valci(diffs[j],ds[:,j])])
    sec+=['## 5. 현금 효과를 걷어내는 대조',
          f'- 코스피 D 신규 0/나머지 1의 **신규 슬롯 비율 평균 q={q:.8f}**를 전체 완결 가능 신호일 {dates[first]}~{dates[last_signal]}에서 한 번 계산하고, 상시축소는 모든 날 q를 사용한다. 최적화/탐색으로 q를 고르지 않았다. 전체 미래기간으로 q를 맞춘 사후 대조라 이 q를 당시 미리 알 수 있었던 운영규칙으로 해석하면 안 된다.',
          f'- 공통 최초 체결 {sd[0]}, 최종 평가 {end}, 평가일 {D}(40일 비겹침 {count_separate(np.arange(D),40)}). 매일 신규 직전 자산/40×비율, 현금 한도, 기존 주식 수 고정, 40일 보유. 왕복 원금 0.5%를 진입 때 현금 차감. 요청의 미완결 제외에 따라 마지막 40일에는 신규를 중단하고 모든 슬롯을 만기까지 평가했다. 따라서 끝의 미완결 보유를 포함했던 이전 §7 총수익과 직접 같지 않다.',
          f'- 미래 가격 존재 여부로 종목을 고르지 않고 t와 t+1에 가격이 있는 종목으로 시작한다. 보유 중 및 만기 누락은 직전가 평가/가상 현금화. 완결 종목×슬롯 {sim_pairs:,}쌍 중 만기 실제 종가 누락 {sim_missing:,}쌍; 실청산 가능성 확인 못 함. 중간 미집행 현금은 이자 0.',
          '- 집행금 가중 순수익=완결 슬롯 순손익 합/투입 원금 합. 최대낙폭은 일별 계좌 자산의 직전 최고점 대비 하락(음수, 차이가 양수면 낙폭 감소). 같은 달을 두 계좌에 함께 재표집하며 순손익/원금 비율과 일별 경로 최대낙폭을 재계산했다. 이는 관측된 계좌 일수익의 월 재표집이며 재표집된 시장에서 규칙을 재실행한 것이 아니다. q도 재추정하지 않은 조건부 구간이다.',
          '- **평균 신규 비율을 맞췄어도 실제 투자 평가액 비중이 정확히 같지는 않다.** 주가 변화·현금제약·진입 시점이 달라 평균현금 차이를 함께 보인다. 이 한 대조만으로 국면 신호의 인과적 가치를 완전히 분리했다고 주장할 수 없다.',
          tab(['규칙','신규 가능일 n(40일 비겹침)','완결 슬롯 n','집행금 가중 순수익 [95%]','최대낙폭 [95%]','평균현금 [95%]','총수익 [95%]','현금제약 일수'],rows),
          '- 실측 1: D면0−상시축소 집행금 가중 순수익 차이 '+valci(diffs[0],ds[:,0])+'%p.',
          '- 실측 2: 같은 두 계좌의 최대낙폭 차이 '+valci(diffs[1],ds[:,1])+'%p; 평균현금 차이 '+valci(diffs[2],ds[:,2])+'%p.']
    print('SIM DONE',q,diffs,flush=True)

    # 6. v30 only; preserve prior post-registration all-anchor method.
    didx={d:i for i,d in enumerate(dates)};ti={t:i for i,t in enumerate(ticks)}
    env=extract('leaderboard.py',['anchor','dedupe_by_anchor'],dict(np=np,pd=pd))
    tr=ast.parse((ROOT/'checkup.py').read_text(encoding='utf-8-sig'))
    reg=next(ast.literal_eval(x.value) for x in tr.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REG_DATE' for t in x.targets))['v30']
    with ro(dbs[1]) as con:
        sc=pd.read_sql_query('SELECT run_id,market,ticker,final_score_v3 score FROM v3_scores WHERE model_id=? AND run_id BETWEEN ? AND ? ORDER BY run_id,market,ticker',con,params=('v30',reg,end))
    keep=env['dedupe_by_anchor'](sc,didx,set(),reg=reg);sc.market=sc.market.str.upper()
    modelrows=[];modelmeta=[]
    for market in ['KOSPI','KOSDAQ']:
        picks={}
        for rid,g in sc[sc.market==market].groupby('run_id'):
            if rid not in keep:continue
            t=env['anchor'](rid,didx)
            chosen=g.dropna(subset=['score']).sort_values(['score','ticker'],ascending=[False,True]).head(10).ticker.tolist()
            picks[t]=[ti[x] for x in chosen if x in ti]
        modelmeta.append(f'{market} 등록후 앵커 {len(picks)}, A 첫 진입 앵커 KOSPI={sum(t in picks for t in events["KOSPI"])}/KOSDAQ={sum(t in picks for t in events["KOSDAQ"])}')
        for k in ['KOSPI','KOSDAQ']:
            zz=[r for t in events[k] if t in picks for r in paired_records(t,picks[t],k,'v30/'+market)]
            for rule in ['상승확인','5일대기']:
                rr=[z for z in zz if z['rule']==rule];pp=paired(rr,'6',market+'/1/'+k+'/'+rule)
                modelrows.append([market,'1/진입지수 '+k,rule,*pp[:4],mean_ci(vec(rr,'low')),
                                  other_difference(rr,'low','blow','6',market+'/'+rule,'최저경로 차이'),pp[4]])
        zz=[r for t,ids in picks.items() for r in regime_records(t,ids,'v30/'+market)]
        for rule in ['D전환청산','A전환20일연장','R20+10%p청산']:
            rr=[z for z in zz if z['rule']==rule];pp=paired(rr,'6',market+'/3/'+rule,60)
            for z in rr:z['daily']=z['ret']/z['hold'];z['bdaily']=z['base']/40
            modelrows.append([market,'3/전체 앵커',rule,*pp[:4],
                              '보유일 '+mean_ci(vec(rr,'hold'))+'; 일할 기준 '+mean_ci(vec(rr,'bdaily'))+' → 규칙 '+mean_ci(vec(rr,'daily')),
                              '일할 차이 '+other_difference(rr,'daily','bdaily','6',market+'/'+rule,'하루당 수익 차이',60),pp[4]])
        zz=[r for t,ids in picks.items() for r in stop_records(t,ids,'v30/'+market)]
        for rule in ['손절-10%','손절-15%']:
            for grp in ['A','비A']:
                rr=[z for z in zz if z['rule']==rule and ((cats['KOSPI'][z['t']]=='A')==(grp=='A'))]
                pp=paired(rr,'6',market+'/4/'+rule+'/'+grp)
                modelrows.append([market,'4/'+grp,rule,*pp[:4],mean_ci(vec(rr,'hold')),'평균 종목보유일',pp[4]])
    sec+=['## 6. v30 참고 — 2026 한 사이클',
          f'- 등록일 {reg} 이후 v3_scores의 v30, 시장별 점수 상위10 동일가중. 전 REPLY §6처럼 부분/이중실행 게이트를 추가 적용하지 않고 등록일과 비거래일 앵커 중복 제거만 적용했다. 같은 점수는 ticker순; 가격 누락을 다음 순위로 채우지 않는다. 시장은 바스켓 시장, 진입지수는 국면 지수다. §1은 **실제 A 첫 진입 사건과 등록후 앵커의 교집합**만 사용하고 인접일 점수로 대신하지 않는다.',
          '- '+ '; '.join(modelmeta)+'. 종료 미완결과 필요한 교집합 누락은 아래 유효 n에서 빠진다. 실제 보유 종목은 원 top10 이하여서 전종목과 표본 성격이 다르다.',
          tab(['종목시장','적용 항목/표본','규칙','앵커 n(40/60 비겹침)','기준 수익','규칙 수익','짝차이 [95%]','최저경로/보유일/하루당 [95%]','보조 짝차이 [95%]/설명','관측월/유효재표집'],modelrows),
          '- 실측 1: A 첫 진입과 v30 앵커가 겹치는 사건 자체가 드물며, 위의 유효 n·관측월 수가 재현 범위를 정한다. 구간이 0폭이면 같은 관측월만 반복된 결과다.',
          '- 실측 2: 모든 모델 행은 2026 등록 이후의 짧은 한 사이클이다. 표본이 겹치므로 독립 검증으로 세거나 모델 판정·채택 근거로 쓰지 않았다.']
    print('MODEL DONE',flush=True)

    # 7. Enumerate all nonzero paired intervals, without selecting a winning grid.
    relevant=[r for r in flags if r[0] in ['1','2','3','4','5']]
    relevant_text=tab(['항목','규칙/분류','차이 지표','n','비겹침 수(§3=60, 나머지40)','짝차이 [95%]'],relevant) if relevant else '해당하는 짝비교 구간은 없다.'
    # Direction of wider versus tighter fixed stop within A, separate from no-stop.
    a10=[z for z in stops if z['rule']=='손절-10%' and cats['KOSPI'][z['t']]=='A']
    a15=[z for z in stops if z['rule']=='손절-15%' and cats['KOSPI'][z['t']]=='A']
    wide=vec(a15,'ret')-vec(a10,'ret');wmean=nanmean(wide);wci=bounds(boot.means(wide))
    direction='같은 방향' if wmean>0 else ('반대 방향' if wmean<0 else '차이 없음')
    sec+=['## 7. 해석 — 실측과 검토 의견',
          '### (a) 0을 걸치지 않은 짝비교 구간: 실측',
          relevant_text,
          '- 위 표는 §1~5에서 수익·최저경로·분포·하루당 수익·손절효과 차이·집행금 수익·낙폭의 짝차이 중 95% 구간이 0을 제외한 항목을 빠짐없이 모았다. 같은 비교의 여러 지표가 독립적인 증거는 아니다. 보정 전 탐색 구간이며 수익 자체가 양수인지와도 다른 질문이다.',
          '### (b) 가장 큰 사후 낙관: 검토 의견',
          '- 사건 9개 안팎 및 길게 겹치는 매수일을 여러 독립 검증처럼 읽는 것이 가장 큰 문제다. 월 블록은 40~60일에 걸친 공통 회복과 연속 거래 신호를 완전히 분리하지 못한다. 기다리는 매수는 청산일도 늦어져 다른 기간의 수익을 비교하고, 하루당 수익은 현금의 기회비용을 제거하지 않는다.',
          '- 고정된 여러 규칙·두 지수·여러 지표·전종목/v30를 같은 기간에 확인했다. 0을 제외한 구간만 추리는 선택 자체가 낙관을 만든다. 최소/최악 사건의 부트스트랩은 관측하지 않은 더 큰 손실을 생성하지 못한다. 한 관측월의 0폭 구간도 정밀한 추정이 아니다.',
          '- 미래 청산가격이 있는 종목만 남기는 짝비교와 모의의 누락가격 가상 현금화는 실제 상장폐지·정지 손실을 숨길 수 있다. 당일 종가 청산은 신호와 체결의 시간 충돌이 있고, 매수 지연·분할은 체결능력과 비용 차이를 반영하지 않았다. 동일 신규 비율 대조도 실제 평균 노출의 완전 일치는 아니다.',
          '### (c) 사전등록 후보 하나: 제안·미등록',
          f'- **변수 하나:** 코스피 A에서 종목별 고정 손절 문턱을 −10%에서 −15%로 넓히면 동일 바스켓의 40일 순수익이 높아진다는 가설. 두 문턱 모두 요청에 있던 값이며 새로운 문턱은 탐색하지 않았다. 이번 A 일별 짝차이는 {mean_ci(wide)}%p(n={np.isfinite(wide).sum()}, 40일 비겹침 {count_separate(np.flatnonzero(np.isfinite(wide)),40)})다. **이 후보를 고른 것은 결과를 본 뒤의 사후 선택**이다. 손절 자체가 무손절보다 좋다는 가설도, PTW 조건을 검증했다는 주장도 아니다.',
          '- 앞으로 승인·정의 동결 이후의 새 코스피 비A→A 첫 진입 사건만, 사건 간 40거래일 이상, 완결된 짝사건 최소 12개 및 2개 이상의 달력연도, 마지막 사건까지 관찰 후 한 번 평가를 제안한다. 현재 83개 A 날짜의 결과를 새로운 첫 진입 사건으로 재검증하는 설계이며 둘을 같은 표본이라고 취급하지 않는다. t+1 매수, 다음날 손절 체결, 미청산은 40일 종료, 같은 초기 바스켓·왕복 0.5%·청산결측 처리도 사전에 고정한다. 12개/2년은 이번 자료가 증명한 충분한 검정력이 아니라 최소 관측량 제안이다.',
          '- 가설은 “−15% 손절의 40일 순수익−−10% 손절이 양수” 한 개. 고정 월 블록 95% 구간 상단≤0이면 반증, 0을 포함하면 보류. 하단>0이어도 사건 하나 제외로 부호가 뒤집히면 견고한 우위로 보지 않는다. 최소 표본 미달이면 자료 부족이다. 사전등록 파일·운영 규칙은 만들지 않았다.',
          '### (d) PTW 손절 완화와 방향',
          f'- 실측상 코스피 A에서 −15% 완화−−10% 손절 수익은 {mean_ci(wide)}%p(n={np.isfinite(wide).sum()}, 40일 비겹침 {count_separate(np.flatnonzero(np.isfinite(wide)),40)})로 점추정은 PTW 완화와 **{direction}**이다. 다만 PTW는 코스닥 20일선 아래라는 다른 조건이므로 PTW 규칙 자체의 지지/반박은 확인 못 함(코드 미열람).',
          '- 요청 밖의 추가 격자·운영 반영은 하지 않았다.']

    jumps=np.isfinite(raw[1:]/raw[:-1])&(np.abs(raw[1:]/raw[:-1]-1)>.32)
    quality=[[name,*counts] for name,counts in sorted(audit.items())]
    sec+=['## 8. 결측·점프·재현 검증',
          f'- 로컬 close 일간 절대변화>32%는 {int(jumps.sum()):,}쌍; is_suspended=1은 {int(p.is_suspended.eq(1).sum()):,}행. 점프컷·정지 제외 없이 유지했다. 누락 칸은 상장 전/후도 포함해 원 행이 없는 종목×날 {int((~live).sum()):,}칸; 그 전부가 수집오류라는 뜻은 아니다.',
          tab(['비교 묶음','가격 점검 신호/사건 n','신호일 후보 종목×사건 n','필요가격 누락 탈락 n'],quality),
          f'- A 첫 진입 후보는 코스피 {len(events["KOSPI"])}개 / 코스닥 {len(events["KOSDAQ"])}개. §1은 대기 후 40일 끝값까지 공통 완결 요구, §2는 첫 매수+40, §3은 실제 연장이 필요한 날에만 +60까지 요구, §4는 기준+40까지 요구한다. 보고서의 n 차이는 이 조건에서 생긴다. 기본 신호일 R20 결측은 {sum(cats["KOSPI"]=="?")}개.',
          '- 자동 검증: 중복 종목·날짜 없음, 지수/시세 로컬 날짜 집합 일치, 운영 cell_of와 전 날짜 A~D 일치, 첫 상승일 전에 상승 신호 없음, 경로 시작 0 및 끝값 직접 수익 일치, 분할1일=한번 매수 및 각 분할의 직접 청산수익 일치, 손절의 다음날 청산 및 40일 상한. 로컬 날짜 위치 100/300/600의 전 종목·두 문턱에 대해 별도 종목별 반복 계산으로 손절 결과를 대조했다. 모의 현금≥0·동시 슬롯≤40·종료 열린 슬롯0. 아래 합성 예제로도 날짜와 현금 처리를 확인한다.',
          '- 재현: `python -B research/handoff/code_20261020_timing_by_regime.py`. numpy/pandas/threadpoolctl 및 같은 폴더의 전 독립 코드 `code_20261020_entry_regime_blind.py` 순수 도우미를 사용한다(전 main 실행 안 함). 새 파일은 이 코드와 REPLY 두 개뿐. 큰 중간 파일 없음. 원자료 최신값이 늘거나 과거값이 바뀌면 재현값도 달라진다.',
          f'- 이번 날짜 축 SHA256 `{hashlib.sha256("|".join(dates).encode()).hexdigest()}`; 마지막 날짜 `{end}`. DB는 mode=ro/query_only로만 열었으며 외부 호출·수집기·배치·점수/판정/게이트/docs/PTW 변경 없음.']

    # Meaningful synthetic indexing checks independent of observed return signs.
    # Three-day tranches at prices 100, 80, 120 -> 40d exit120: mean(20,50,0)=23.333%.
    prices=np.r_[100.,80.,120.,np.full(38,120.)]
    curve=np.ones(41)
    for j in range(3):curve[j:]+=(prices[j:]/prices[j]-1)/3
    assert np.isclose((curve[-1]-1)*100,(20+50+0)/3)
    assert np.isclose(curve[1],1-.2/3)  # unspent capital remains cash
    prices=np.array([100.,89.,70.,120.])
    hit=np.flatnonzero(prices[1:-1]<=90)[0]+1
    assert hit==1 and hit+1==2 and np.isclose(prices[hit+1]/prices[0]-1,-.3)
    assert count_separate([1,39,41,80,81],40)==3
    sec+=['- 합성검증 실측: 100→80→120 분할 매수의 동일 총금액 청산수익 23.3333% 및 대기 현금 평가 일치; 100→89 손절 신호 뒤 다음날 70 청산으로 −30%(−10%에 체결했다고 계산하지 않음); 40일 비겹침 경계 일치.']
    assert before==[(p.stat().st_size,p.stat().st_mtime_ns) for p in dbs], 'Input DB changed during run'
    sec+=['- 두 DB의 실행 전후 크기·수정시각 동일(전체 내용 해시는 아님).',
          '## 결론 한 줄',
          '**같은 하락에서도 매수·청산 시점에 따른 짝차이는 있지만, 적은 사건·겹친 창·당일 종가 체결·결측 처리 때문에 “언제 사고팔아야 한다”는 운영 규칙으로 확정할 수 없다.**']
    guard();OUT.write_text('\n\n'.join(sec)+'\n',encoding='utf-8')
    print('NONZERO',relevant,flush=True)
    print('PTW',direction,mean_ci(wide),flush=True)
    print('WROTE',OUT,OUT.stat().st_size,flush=True)


if __name__=='__main__':
    with threadpool_limits(limits=2):
        run()
