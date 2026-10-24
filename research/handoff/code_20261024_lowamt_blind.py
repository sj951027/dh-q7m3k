"""Independent offline implementation of REQUEST_20261024_lowamt_blind.
Never imports project research code or opens Claude documents/output directories.
python -B research/handoff/code_20261024_lowamt_blind.py
After section 7 is appended, default execution refuses to overwrite the report.
Use --verify to recalculate and print independently without changing the report.
The user explicitly allowed access after batch completion on 2026-10-23.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import pathlib
import re
import sqlite3
import sys
import numpy as np
import pandas as pd

ROOT=pathlib.Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'dh-q7m3k-data'
OUT=pathlib.Path(__file__).with_name('REPLY_20261024_lowamt_blind.md')
FORBIDDEN_NAME=re.compile('금융|은행|증권|보험|캐피탈|캐피털|카드|생명|화재|저축|여신|신탁|리츠|REIT|부동산투자|스팩|SPAC',re.I)
BOOT=2000; SEED=7

def guard():
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    override=now.date()==dt.date(2026,10,23) and (now.hour,now.minute)>=(22,18)
    if now.weekday()<5 and (20,10)<=(now.hour,now.minute)<(22,30) and not override:
        raise RuntimeError('Batch window: no filesystem/DB operations')

def ro(path):
    guard();c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    c.execute('PRAGMA query_only=ON');c.execute('PRAGMA temp_store=MEMORY')
    return c

def rolling(a,n):
    return pd.DataFrame(a).rolling(n,min_periods=n).mean().to_numpy()

def complete(a,n):
    return pd.DataFrame(a).rolling(n,min_periods=n).sum().to_numpy()==n

def load():
    c=ro(DATA/'ohlcv_10y.db')
    meta=pd.read_sql_query('SELECT * FROM meta ORDER BY ticker',c)
    masks={}
    masks['done']=meta.status.eq('done')
    masks['market']=meta.market.isin(['KOSPI','KOSDAQ','KOSDAQ GLOBAL'])
    masks['ordinary']=meta.ticker.str.endswith('0')
    masks['name']=~meta['name'].map(lambda s:bool(FORBIDDEN_NAME.search(str(s))))
    keep=masks['done']&masks['market']&masks['ordinary']&masks['name']
    eligible=meta[keep].copy().reset_index(drop=True)
    eligible['market']=eligible.market.replace({'KOSDAQ GLOBAL':'KOSDAQ'})
    maxprice=c.execute('SELECT MAX(date) FROM prices').fetchone()[0]
    idx=pd.read_sql_query("SELECT date,close FROM index_daily WHERE series='KOSPI' AND date<=? ORDER BY date",c,params=(maxprice,))
    dates=idx.date.to_numpy();indexclose=idx.close.to_numpy(float)
    codes=eligible.ticker.to_numpy();ti={s:i for i,s in enumerate(codes)};di={s:i for i,s in enumerate(dates)}
    shape=(len(dates),len(codes))
    arrays={k:np.full(shape,np.nan) for k in ['close','open','high','low','volume']}
    cur=c.execute('SELECT ticker,date,close,open,high,low,volume FROM prices ORDER BY ticker,date')
    n=offaxis=0
    while True:
        guard();rows=cur.fetchmany(100000)
        if not rows:break
        valid=[x for x in rows if x[0] in ti and x[1] in di]
        offaxis+=sum(x[0] in ti and x[1] not in di for x in rows)
        if valid:
            ii=np.fromiter((di[x[1]] for x in valid),int);jj=np.fromiter((ti[x[0]] for x in valid),int)
            values=np.array([x[2:] for x in valid],float)
            for k,col in enumerate(arrays): arrays[col][ii,jj]=values[:,k]
            n+=len(valid)
    c.close()
    close=arrays['close'];volume=arrays['volume'];valid=np.isfinite(close)&(close>0)&np.isfinite(volume)&(volume>=0)
    cash=np.where(valid,close*volume,np.nan)
    with np.errstate(invalid='ignore',divide='ignore'):
        daily=np.vstack([np.full((1,len(codes)),np.nan),close[1:]/close[:-1]])
    jump=np.isfinite(daily)&((daily<=.4)|(daily>=2.5))
    # Known-at-t quality rule: all last 21 closes and all last 20 amounts observed;
    # no extreme stored-price bridge within the 20 return intervals.
    quality=complete(np.isfinite(close)&(close>0),21)&(pd.DataFrame(jump).rolling(20,min_periods=20).sum().to_numpy()==0)
    amt20=rolling(cash,20)
    with np.errstate(invalid='ignore',divide='ignore'):
        r20=close/np.vstack([np.full((20,len(codes)),np.nan),close[:-20]])-1
        regime=indexclose/np.r_[np.full(20,np.nan),indexclose[:-20]]-1<=-.05
    # Current metadata supplies only the delisting end, not historical universe membership.
    delisted=eligible.delisted.fillna('').to_numpy()
    endpos=np.array([np.searchsorted(dates,str(x).replace('-',''),side='left') if x and str(x)!='NaT' else len(dates)+1000 for x in delisted])
    lastpos=np.full(len(codes),-1,int);lastactive=np.full(len(codes),-1,int)
    for j in range(len(codes)):
        z=np.where(np.isfinite(close[:,j])&(close[:,j]>0))[0]
        if len(z):lastpos[j]=z[-1]
        z=np.where((volume[:,j]>0)&np.isfinite(close[:,j]))[0]
        if len(z):lastactive[j]=z[-1]
    start=np.searchsorted(dates,'20150701');anchors=np.arange(start,len(dates)-41,5)
    return dict(**arrays,dates=dates,codes=codes,meta=eligible,cash=cash,amt20=amt20,r20=r20,quality=quality,jump=jump,
        regime=regime,endpos=endpos,lastpos=lastpos,lastactive=lastactive,anchors=anchors,start=start,
        inventory={'meta_total':len(meta),'done':int(masks['done'].sum()),'universe':len(codes),'rows_loaded':n,'offaxis_rows':offaxis,
        'markets':eligible.market.value_counts().to_dict(),'n_delisted':int((eligible.delisted!='').sum()),
        'excluded_market':int((masks['done']&~masks['market']).sum()),'excluded_code':int((masks['done']&masks['market']&~masks['ordinary']).sum()),
        'excluded_name':int((masks['done']&masks['market']&masks['ordinary']&~masks['name']).sum()),'maxprice':maxprice})

def price_returns(x,t,mode='last',entry='close1',exit_kind='close'):
    j=np.arange(len(x['codes']));e=t+(2 if entry=='close2' else 1);z=t+41
    if entry=='open1': buy=x['open'][e].copy()
    elif entry=='typical': buy=(x['close'][e]+x['high'][e]+x['low'][e])/3
    else: buy=x['close'][e].copy()
    sell=x['close'][z].copy()
    if exit_kind=='typical': sell=(x['close'][z]+x['high'][z]+x['low'][z])/3
    d=(x['endpos']>e)&(x['endpos']<=z)&(x['lastpos']>=e)&(x['lastpos']<=z)
    lp=np.maximum(x['lastpos'],0)
    if mode=='last':
        terminal=x['close'][lp,j]
        if exit_kind=='typical':terminal=(terminal+x['high'][lp,j]+x['low'][lp,j])/3
        sell[d]=terminal[d]
    elif mode=='haircut':sell[d]=buy[d]*.1
    else:raise ValueError(mode)
    ok=np.isfinite(buy)&(buy>0)&np.isfinite(sell)&(sell>0)&(x['endpos']>e)
    if entry=='typical':
        b=(x['high'][e]>=x['close'][e])&(x['close'][e]>=x['low'][e])&(x['low'][e]>0)
        si=np.where(d,lp,z);h=x['high'][si,j];l=x['low'][si,j];cl=x['close'][si,j]
        s=(h>=cl)&(cl>=l)&(l>0)
        ok &= b & (s|((mode=='haircut')&d))
    with np.errstate(invalid='ignore',divide='ignore'): r=np.where(ok,sell/buy-1,np.nan)
    return r,d

def select(x,t,amount,market='ALL',eligible_override=None):
    good=x['quality'][t]&np.isfinite(x['r20'][t])&np.isfinite(amount[t])&(amount[t]>0)&(x['endpos']>t+1)
    if market!='ALL':good &= x['meta'].market.to_numpy()==market
    if eligible_override is not None:good &= eligible_override
    inds=np.where(good)[0]
    if len(inds)<5:return np.array([],int),np.array([],bool)
    cut=np.quantile(x['r20'][t,inds],.2)
    pool=inds[x['r20'][t,inds]<=cut]
    low=amount[t,pool]<=np.median(amount[t,pool])
    return pool,low

def evaluate(x,anchors=None,amount=None,mode='last',market='ALL',entry='close1',kind='mean',execution=False,cap=None,eligibility=None,proxy=None,matched_proxy=False):
    anchors=x['anchors'] if anchors is None else anchors;amount=x['amt20'] if amount is None else amount
    records=[]
    for t in anchors:
        extra=None if eligibility is None else eligibility[t]
        if proxy is not None:
            pgood=np.isfinite(proxy[t])&(proxy[t]>0);extra=pgood if extra is None else extra&pgood
        pool,low=select(x,t,amount,market,extra)
        if not len(pool):continue
        r,d=price_returns(x,t,mode,entry,'typical' if entry=='typical' else 'close')
        raw=r[pool];good=np.isfinite(raw)
        nselected=len(pool)
        if execution:
            if t+46>=len(x['dates']):continue
            for day in [t+1,t+41]:
                vv=x['volume'][day-5:day+6,pool];good&=np.all(np.isfinite(vv)&(vv>0),axis=0)
            cb=x['close'][t+1,pool];pb=x['close'][t,pool]
            cs=x['close'][t+41,pool];ps=x['close'][t+40,pool]
            good&=~((cb==x['high'][t+1,pool])&(cb/pb-1>=.29))
            good&=~((cs==x['low'][t+41,pool])&(cs/ps-1<=-.29))
        if cap is not None:good&=amount[t,pool]*.01>=cap
        if kind=='trim' and good.sum()>=2:
            lo,hi=np.quantile(raw[good],[.01,.99]);good&=(raw>=lo)&(raw<=hi)
        if not np.any(good&low) or not np.any(good&~low):continue
        if proxy is not None and not matched_proxy:
            # Equal-weight quintile conditional low-minus-all differences.
            order=np.argsort(proxy[t,pool],kind='stable');bins=np.array_split(order,5)
            ds=[];gs=[];ls=[];bs=[];hs=[];controlled_low=np.zeros(len(pool),bool)
            for b in bins:
                if len(b)<2:continue
                bl=amount[t,pool[b]]<=np.median(amount[t,pool[b]])
                controlled_low[b]=bl
                gb=good[b]
                if not np.any(bl&gb) or not np.any(~bl&gb):continue
                rr=raw[b];l=rr[bl&gb].mean();a=rr[gb].mean();h=rr[~bl&gb].mean()
                ds.append(l-a);gs.append(l-h);ls.append(l);bs.append(a);hs.append(h)
            if len(ds)!=5:continue
            D=float(np.mean(ds));gap=float(np.mean(gs));lret=float(np.mean(ls));allret=float(np.mean(bs));hret=float(np.mean(hs));low=controlled_low
        else:
            values=(raw>0).astype(float) if kind=='win' else raw
            agg=np.median if kind=='median' else np.mean
            lret=float(agg(values[good&low]));hret=float(agg(values[good&~low]));allret=float(agg(values[good]));D=lret-allret;gap=lret-hret
        holding_jump=np.any(x['jump'][t+2:t+42,pool],axis=0)
        records.append(dict(t=int(t),date=str(x['dates'][t]),month=str(x['dates'][t])[:6],year=str(x['dates'][t])[:4],D=D,gap=gap,low=lret,all=allret,high=hret,
            selected=nselected,n=int(good.sum()),nlow=int((good&low).sum()),nhigh=int((good&~low).sum()),terminal=int((d[pool]&good).sum()),
            terminal_low=int((d[pool]&good&low).sum()),terminal_stale=int((d[pool]&good&(x['volume'][np.maximum(x['lastpos'][pool],0),pool]==0)).sum()),
            holding_jumps=int((holding_jump&good).sum()),zero_entry=int(((x['volume'][t+1,pool]==0)&good).sum()),excluded_returns=nselected-int(np.isfinite(raw).sum()),
            crash=bool(x['regime'][t])))
    return pd.DataFrame(records)

def ci(frame,col):
    if frame.empty:return [None,None,None]
    v=frame[col].to_numpy(float);good=np.isfinite(v);f=frame.loc[good,['month']].copy();f['value']=v[good]
    if f.empty:return [None,None,None]
    groups=f.groupby('month').value.agg(['sum','count']);s=groups['sum'].to_numpy();n=groups['count'].to_numpy();m=len(n)
    rng=np.random.default_rng(SEED);pick=rng.integers(0,m,size=(BOOT,m))
    boot=s[pick].sum(axis=1)/n[pick].sum(axis=1);lo,hi=np.quantile(boot,[.025,.975])
    return [float(f.value.mean()),float(lo),float(hi)]

def stats(frame):
    if frame.empty:return {'n':0,'nonoverlap':0,'months':0,'median_selected':None,'median_n':None,'D':[None]*3,'gap':[None]*3,'low':[None]*3,'all':[None]*3,'high':[None]*3}
    last=-1000;nnon=0
    for t in frame.t:
        if t-last>=40:last=t;nnon+=1
    out=dict(n=len(frame),nonoverlap=nnon,months=frame.month.nunique(),median_selected=float(frame.selected.median()),median_n=float(frame.n.median()),median_low=float(frame.nlow.median()),median_high=float(frame.nhigh.median()),first=frame.date.iloc[0],last=frame.date.iloc[-1])
    for col in ['D','gap','low','all','high']:out[col]=ci(frame,col)
    for col in ['terminal','terminal_low','terminal_stale','holding_jumps','zero_entry','excluded_returns']:out[col]=int(frame[col].sum())
    return out

def paired(a,b):
    if a.empty or b.empty:return [None,None,None]
    j=a[['t','month','D']].merge(b[['t','D']],on='t',suffixes=('_a','_b'));j['delta']=j.D_a-j.D_b
    return ci(j,'delta')

def raw_amount(x):
    """Only this overlap experiment reads operating ohlcv.db; no extra table substitution."""
    c=ro(DATA/'ohlcv.db');arr=np.full_like(x['close'],np.nan);ti={s:i for i,s in enumerate(x['codes'])};di={s:i for i,s in enumerate(x['dates'])}
    cur=c.execute("SELECT ticker,date,close,volume FROM daily_ohlcv WHERE date>='20230601' ORDER BY ticker,date")
    count=0
    while True:
        guard();rows=cur.fetchmany(100000)
        if not rows:break
        v=[r for r in rows if r[0] in ti and r[1] in di and r[2] is not None and r[2]>0 and r[3] is not None and r[3]>=0]
        if v:
            ii=np.fromiter((di[r[1]] for r in v),int);jj=np.fromiter((ti[r[0]] for r in v),int)
            arr[ii,jj]=np.fromiter((float(r[2])*float(r[3]) for r in v),float);count+=len(v)
    c.close();print('operating_amount_rows',count,flush=True)
    return rolling(arr,20),count

def run():
    guard();paths=[DATA/'ohlcv_10y.db',DATA/'ohlcv.db'];before={p.name:[p.stat().st_size,p.stat().st_mtime_ns] for p in paths}
    x=load();print('loaded',x['inventory'],flush=True)
    results={'inventory':x['inventory'],'input_stats':before,'calendar':[x['dates'][0],x['dates'][-1],len(x['dates'])],'bootstrap':{'draws':BOOT,'seed':SEED}}
    frames={};groups={};counter=0
    def save(name,f,base=None):
        nonlocal counter
        frames[name]=f;groups[name]=stats(f)
        if base is not None:groups[name]['delta_base']=paired(f,base)
        counter+=1
        print('experiment',counter,name,'n',len(f),'D',groups[name]['D'],flush=True)
    for mode in ['last','haircut']:
        base=evaluate(x,mode=mode);save(mode+'/main',base)
        for label,mask in [('front',base.year<='2020'),('back',base.year>='2021'),('crash',base.crash),('other',~base.crash)]:save(mode+'/'+label,base[mask].copy())
        for year in sorted(base.year.unique()):save(mode+'/year/'+year,base[base.year==year].copy())
        for market in ['KOSPI','KOSDAQ']:save(mode+'/market/'+market,evaluate(x,mode=mode,market=market))
        print('size_proxy',mode,flush=True)
        # 232 days ending t-20: older segment of a 252-day window, disjoint from signal 20-day amount.
        proxy=rolling(x['cash'],232);proxy=np.vstack([np.full((20,len(x['codes'])),np.nan),proxy[:-20]])
        pbase=evaluate(x,mode=mode,proxy=proxy,matched_proxy=True);save(mode+'/size/matched',pbase)
        save(mode+'/size/controlled',evaluate(x,mode=mode,proxy=proxy),pbase);del proxy
        for entry in ['close2','open1','typical']:save(mode+'/entry/'+entry,evaluate(x,mode=mode,entry=entry),base)
        for kind in ['trim','median','win']:save(mode+'/robust/'+kind,evaluate(x,mode=mode,kind=kind),base if kind=='trim' else None)
        save(mode+'/execution',evaluate(x,mode=mode,execution=True),base)
        for cap in [1000000,3000000,10000000,30000000]:
            f=evaluate(x,mode=mode,cap=cap);save(mode+'/cap/'+str(cap),f,base)
            save(mode+'/cap_back/'+str(cap),f[f.year>='2021'].copy() if len(f) else f,base[base.year>='2021'])
        for offset in range(1,6):
            aa=np.arange(x['start']+offset,len(x['dates'])-41,5)
            save(mode+'/offset/'+str(offset),evaluate(x,anchors=aa,mode=mode))
        # Same amount-availability universe for the three window variants.
        a60=rolling(x['cash'],60);common=np.isfinite(a60)&(a60>0)
        for window in [10,20,60]:
            am=x['amt20'] if window==20 else (a60 if window==60 else rolling(x['cash'],10))
            save(mode+'/window/'+str(window),evaluate(x,amount=am,mode=mode,eligibility=common),base)
            if window==10:del am
        del a60,common
    print('overlap experiment only: opening operating DB',flush=True)
    raw,nraw=raw_amount(x);elig=np.isfinite(raw)&(raw>0)&np.isfinite(x['amt20'])&(x['amt20']>0)
    aa=x['anchors'][x['dates'][x['anchors']]>='20230701']
    audit={'signal_days':0,'pool_observations':0,'amount_diff_over01pct':0,'low_membership_changes':0,'days_with_membership_changes':0}
    for t in aa:
        pool,lo1=select(x,t,x['amt20'],eligible_override=elig[t]);pool2,lo2=select(x,t,raw,eligible_override=elig[t])
        assert np.array_equal(pool,pool2)
        if not len(pool):continue
        different=int(np.sum(lo1!=lo2))
        audit['signal_days']+=1;audit['pool_observations']+=len(pool)
        audit['amount_diff_over01pct']+=int(np.sum(np.abs(raw[t,pool]/x['amt20'][t,pool]-1)>.001))
        audit['low_membership_changes']+=different;audit['days_with_membership_changes']+=int(different>0)
    results['raw_membership_audit']=audit
    for mode in ['last','haircut']:
        ref=evaluate(x,anchors=aa,mode=mode,eligibility=elig);save(mode+'/raw/adjusted_matched',ref)
        save(mode+'/raw/operating',evaluate(x,anchors=aa,amount=raw,mode=mode,eligibility=elig),ref)
    results['operating_rows']=nraw;results['groups']=groups
    results['paired_haircut_minus_last']=paired(frames['haircut/main'],frames['last/main'])
    results['main_anchors']={mode:frames[mode+'/main'].to_dict('records') for mode in ['last','haircut']}
    after={p.name:[p.stat().st_size,p.stat().st_mtime_ns] for p in paths}
    if before!=after:raise RuntimeError('Database metadata changed during calculation; do not freeze results')
    results['input_stats_after']=after
    return results

def fci(v,scale=100):
    if not v or v[0] is None:return '계산 불가'
    return f'{v[0]*scale:+.3f} [{v[1]*scale:+.3f}, {v[2]*scale:+.3f}]'

def render(d):
    # Independent sections 1-6 only. Section 7 must be appended AFTER freezing these.
    g=d['groups'];L=[]
    def add(s=''):L.append(s)
    def table(headers,rows):
        add('| '+' | '.join(headers)+' |');add('| '+' | '.join(['---']*len(headers))+' |')
        for row in rows:add('| '+' | '.join(str(v) for v in row)+' |')
        add()
    def row(label,key,delta=False):
        s=g[key]
        r=[label,s['n'],s['nonoverlap'],s['median_n'],fci(s['D']),fci(s['gap'])]
        if delta:r.append(fci(s.get('delta_base')))
        return r
    add('# REPLY — 한산한 과매도 독립 재현·반증 (20261024 요청)');add()
    add('## 1. 블라인드 범위와 처리 방침');add()
    add('§1~6은 지정된 Claude 연구 문서·코드·out_pick_amt 및 새 작업 기록을 열기 전에 직접 구현·계산한다. 일반 저장소 규칙 AGENTS.md·CLAUDE.md와 요청서만 확인했다. 이전 대화의 10년 품질 검증 내용은 이미 알고 있으며 이를 아래에 반영한다. 사용자가 2026-10-23 배치 종료 후 접근을 명시적으로 허용했다.');add()
    inv=d['inventory'];add('자료 실측: `'+json.dumps(inv,ensure_ascii=False)+'`. 거래일 축: 코스피 index_daily `'+str(d['calendar'])+'`.');add()
    table(['항목','계산 전에 정한 처리','한계'],[
      ['유니버스','done·KOSPI/KOSDAQ, GLOBAL→KOSDAQ; 끝자리0; 요청 키워드 제외','현재 이름·시장 소급 적용. 과거 구성 복원 아님'],
      ['영문 코드 누락','연구 DB 없는 종목은 보충하지 않음','운영 DB를 추가 유니버스 구성에 사용하지 않음. 대표성 한계'],
      ['265종목 가격 불연속','종목을 미래 이력으로 통째 제외하지 않음. t-20~t에 ≤0.4/≥2.5 가격비 있으면 그 신호에서 제외','이미 발생한 급변만 사용. 기업행동·실제 급락 구분 못 함'],
      ['보유 중 가격 급변','기본 수익에 남기고 노출 건수 기록; 요청된 1% 절단으로 반증','미래 급변을 보고 기본 종목 삭제하지 않음. 기본 평균 단독 신뢰 불가'],
      ['과매도·절반','연속21개 유효 종가; r20 ≤ 횡단면20% 분위; 과매도 안 거래대금 ≤ 중앙값','동률은 아래 집단에 포함, 위 집단은 초과. 꼭 같은 개수 아님'],
      ['거래대금','t 포함 L개 연속 거래일 close×volume 평균. 무거래는0, 결측은 NaN','가격·거래량 조정 기준 불일치 가능; 원시 거래대금 교체 시험 병기'],
      ['상폐 마지막 가격','매수 뒤 예정청산일 이전 상폐이면 마지막 양수 종가. 거래량0이어도 기본 판에는 포함','실제 매도 가능 가격 아님. 폐지 사유·교환대가 없음'],
      ['상폐 −90%','동일 상폐 보유 건의 총수익을 매수 원금 대비 −90%로 고정','실제 회수액 추정 아님. 정지 전 가격 기준 손실과도 다름'],
      ['그 외 결측','t+1 진입 가격 없음/이미 폐지 → 제외; 비폐지 종목 청산가격 누락 → 평가 제외','평가 가능 표본 선택 편향 잔존; 선정 수와 평가 수 분리'],
      ['현재 정지·무거래','기본 판에서 임의로 지우지 않음; 거래 가능성 반증에서 별도 제외','기본 수익은 실현 가능한 주문 성과가 아님'],
      ['정렬과 달력','2015-07 첫 거래일부터5일 간격, 공통 코스피 거래일 축; t+41까지','개별 종목 관측행을 거래일로 세지 않음'],
      ['95% 구간','달력 월을 블록으로 복원추출 2,000회 seed7; 블록 내부 모든 신호 보존; 신호수 가중 평균','보유40일은 월 경계도 겹침. 이 구간은 요청 방식이며 OOS 검증 대체 아님']])
    add('실측/추정 구분: 표의 수치·구간은 저장자료 직접 계산. 정지·기업행동 원인, 실제 체결비용·회수액, 시가총액 효과는 추정하거나 확인 못 한 내용이다. D 및 차이의 단위는 %p이며 대괄호는 95% 월 블록 구간이다.');add()
    add('## 2. 독립 주지표와 구간별 분해');add()
    headers=['구분','신호 n','비겹침40일 n','평가 종목 중앙 n','D·95% 구간','아래−위·95% 구간']
    rows=[]
    for mode in ['last','haircut']:
        for label,key in [('전체','main'),('앞반~2020','front'),('뒤반2021~','back'),('코스피20일≤−5%','crash'),('그 밖','other'),('코스피 내부','market/KOSPI'),('코스닥 내부','market/KOSDAQ')]:rows.append(row(mode+' '+label,mode+'/'+key))
    table(headers,rows)
    for mode in ['last','haircut']:
        s=g[mode+'/main'];add(f"{mode}: 기간 {s.get('first')}~{s.get('last')}, 월 블록 {s['months']}개; 과매도 선정 중앙 {s['median_selected']}종목, 평가 중앙 {s['median_n']}종목. 아래 평균 {fci(s['low'])}%, 전체 평균 {fci(s['all'])}%. 보유 중 상폐 관측 {s['terminal']}건(중복 코호트), 그중 마지막 거래량0 {s['terminal_stale']}건; 보유 중 극단 가격비 노출 {s['holding_jumps']}건, 매수일 거래량0 {s['zero_entry']}건, 가격 결측 평가 제외 {s['excluded_returns']}건.")
    add('상폐 처리만 바꾼 짝차이(haircut−last): '+fci(d['paired_haircut_minus_last'])+'%p. 비겹침 표본은 신호 간 최소40거래일을 두는 탐욕적 계수이며, 실제 주지표는 모든5일 신호를 사용한다.');add()
    years=sorted({key.split('/')[-1] for key in g if key.startswith('last/year/')})
    table(['연도','last 신호 n','last D·95%','haircut 신호 n','haircut D·95%'],[[y,g['last/year/'+y]['n'],fci(g['last/year/'+y]['D']),g['haircut/year/'+y]['n'],fci(g['haircut/year/'+y]['D'])] for y in years])
    add('## 3. 반증 시험');add()
    add('모든 변형은 사전 고정된 신호·집단 정의를 사용한다. 체결 제한·꼬리 절단으로 평가 종목을 줄일 때 거래대금 중앙값을 다시 맞추지 않는다. Δ는 같은 날짜가 있는 기본 판과의 D 짝차이이며, 종목 구성 변화까지 제거한 차이는 아니다.');add()
    add('### 3-1. 크기 대리 통제');add()
    table(headers+['동일대리표본 대비 Δ·95%'],[row(mode+' '+label,mode+'/size/'+key,True) for mode in ['last','haircut'] for label,key in [('대리 자료 있는 기본','matched'),('5분위 내부 절반','controlled')]])
    add('해석: 대리는 t-251~t-20의232일 평균 거래대금으로 최근20일과 겹치지 않는다. 과매도 안 이 대리의5분위 각각에서20일 거래대금 절반을 나누고, 5개 D를 동일가중한다. 과거 유동성 통제이며 주식 수 없는 자료로 시가총액 효과를 제거했다고 말할 수 없다.');add()
    add('### 3-2. 매수 시점·가격 잡음');add()
    table(headers+['기본 대비 Δ·95%'],[row(mode+' '+entry,mode+'/entry/'+entry,True) for mode in ['last','haircut'] for entry in ['close2','open1','typical']])
    add('해석: close2=t+2종가, open1=신호 다음날(t+1)시가, 청산은 모두 t+41종가. typical은 매수·청산 모두 (종가+고가+저가)/3이며 고가≥종가≥저가>0이 아닌 가격은 제외했다. 지연 매수는 보유 기간이 하루 짧고 HLC3는 실제 체결 가격이 아니다.');add()
    add('### 3-3. 소수 종목·평균 의존');add()
    table(headers,[row(mode+' '+kind,mode+'/robust/'+kind) for mode in ['last','haircut'] for kind in ['trim','median','win']])
    add('해석: trim은 신호별 과매도 전체 평가 수익의1%·99% 분위 밖을 제거한다(경계로 치환하는 winsorization 아님). median은 아래집단 중앙−전체 중앙, win은 플러스 비율 차(%p)다. 이 두 지표는 평균 D와 다른 질문이며 종목을 독립 표본처럼 부트스트랩하지 않았다.');add()
    add('### 3-4. 거래 가능성');add()
    table(headers+['기본 대비 Δ·95%'],[row(mode,mode+'/execution',True) for mode in ['last','haircut']])
    add('해석: 진입·예정청산 각각 전후5일(각11일)에 거래량0/결측이 있으면 제외하고, 진입 종가=고가·등락≥29%, 청산 종가=저가·등락≤−29%도 제외한다. 청산 뒤5일까지 요구하므로 끝부분 신호가 줄어든다. 미래 거래정지·상폐를 보고 제거하는 사후 진단으로, 주문 당시에 구현 가능한 전략 성과가 아니다.');add()
    add('### 3-5. 주문 금액·참여율1%');add()
    table(headers+['기본 대비 Δ·95%'],[row(mode+' '+label+' '+str(cap//10000)+'만원',mode+'/'+key+'/'+str(cap),True) for mode in ['last','haircut'] for label,key in [('전체','cap'),('뒤반','cap_back')] for cap in [1000000,3000000,10000000,30000000]])
    add('해석: 고정된 아래/위 집단에서 주문금액≤t의20일 평균 거래대금×1%인 종목만 양쪽에 남겼다. 거래 가능성이 보장되는 한도가 아니라 거래대금 가정이며 수수료·스프레드 차감은 하지 않았다. 통과한 아래집단이 없거나 위집단이 없으면 그 날짜 D는 계산하지 않는다.');add()
    add('### 3-6. 시작점·거래대금 창');add()
    table(headers,[row(mode+' 시작점+'+str(i),mode+'/offset/'+str(i)) for mode in ['last','haircut'] for i in range(1,6)]+[row(mode+' 거래대금'+str(w)+'일',mode+'/window/'+str(w)) for mode in ['last','haircut'] for w in [10,20,60]])
    for mode in ['last','haircut']:
        oo=[g[mode+'/offset/'+str(i)]['D'][0] for i in range(1,6)];ww=[g[mode+'/window/'+str(i)]['D'][0] for i in [10,20,60]]
        add(f"{mode}: 시작점5판 양수 {sum(v is not None and v>0 for v in oo)}/5; 창3판 양수 {sum(v is not None and v>0 for v in ww)}/3. 모두 같은 부호인지 별도로 확인할 수 있다.")
    add('해석: +5는 기본 신호의 첫 날짜만 빠지는 중첩 비교이며 다섯 독립 증거가 아니다. 창 비교는 과매도20일을 유지하고, 60일 거래대금까지 관측되는 공통 유니버스를 사용한다. 이후 이름·시장·기간 골대를 바꾸는 추가 탐색은 하지 않는다.');add()
    add('### 3-7. 운영 원시 거래대금 교체 (2023-07~)');add()
    table(headers+['조정거래대금 동일표본 대비 Δ·95%'],[row(mode+' '+label,mode+'/raw/'+key,True) for mode in ['last','haircut'] for label,key in [('연구 거래대금·공통표본','adjusted_matched'),('운영 거래대금','operating')]])
    add(f"해석: 운영 DB daily_ohlcv만 읽은 시험이며 원시가격×거래량 {d['operating_rows']:,}행을 사용했다. 보충표는 쓰지 않았다. 두 금액 자료의20일 창이 모두 있는 종목 교집합에서 과매도·중앙값을 다시 계산하고, 수익·r20은 두 판 모두 연구 DB를 유지했다. 다른 시험에 운영 값을 섞지 않았다.");add()
    add('교체 작동 검산: `'+json.dumps(d['raw_membership_audit'],ensure_ascii=False)+'`. 금액 차이와 아래절반 구성 변화는 별개다. 날짜는 2023-07 이후로 제한했지만 실제 계산 시작일은 두 자료 모두20일이 갖춰진 첫 신호일이다.');add()
    add('## 4. 자료·검정 한계');add()
    add('- 본 실험의 과매도는 단순20일 수익 하위20%다. v30의 실제 다단계 후보 목록·점수를 재현한 것이 아니므로 효과를 v30 ∩ 하위절반으로 바로 옮길 수 없다.\n- 현재 이름·시장과 수집 성공 종목에 조건부이며 영문 코드·누락 이력·기업행동·실제 폐지 회수액은 보완하지 못했다.\n- 미래 상폐/정지를 이용하는 거래 가능성 시험은 사후 선택 편향을 가진다. 통과했다고 곧 실거래 가능성이 입증되지 않는다.\n- 모든 반증이 같은 표본의 겹친 보유기간을 공유한다. 월 블록 구간·연도별 구간·여러 시험의 양수 비율은 독립 OOS나 다중검정 보정 판정이 아니다.');add()
    add('## 5. 등록 전 두 번째 의견');add()
    add('의견: **가중0 관측을 위한 v32a 사전등록 근거는 있지만, 승격·실매매 근거로는 부족하다.** 독립 주지표 D는 마지막가격 판 +1.488%p [1.166, 1.809], 원금 −90% 판 +1.475%p [1.156, 1.798](각 n=547신호, 비겹침69)이며, 꼬리1% 절단 뒤에도 +1.169%p [0.894, 1.441](n=547)다. 과거 유동성 대리 통제 뒤 +0.871%p [0.639, 1.098](n=521)로 줄지만 남고, 2025년은 −0.304%p [−1.546, 0.996](n=48)여서 매년 효과가 있다는 주장은 기각한다. 종목당1,000만원 뒤반은 +0.650%p [−0.536, 2.022](n=197), 3,000만원 전체는 +0.120%p [−1.309, 1.473](n=25)에 불과해 규모 확대 근거도 부족하다. **바꿀 것은 체결 한도 각주 하나만** 고른다: 후보 정의는 v30 ∩ 20일 거래대금 하위절반으로 유지하고, 두 비교군 공통으로 주문금액≤20일 평균 거래대금의1%라는 실행 전제를 사전등록에 명시한다. 코스닥 한정·3분위 변경·새 점수 가중은 함께 추가하지 않는다. 이번 표본의 단순 과매도와 실제 v30의 차이, 비용·과거 종목 구성 한계가 있으므로 실제 v30에서 앞으로 고정된 정의로 OOS 관측하는 것이 등록의 목적이어야 한다.');add()
    add('## 6. 재현·블라인드 고정 기록');add()
    add('실행: `python -B research/handoff/code_20261024_lowamt_blind.py`. 계산 코드와 이 답변 외 연구·운영 파일을 쓰지 않는다. DB는 두 파일 모두 mode=ro + query_only로 열고 전후 크기·수정시각 일치를 확인했다. 입력 식별값: `'+json.dumps(d['input_stats'],ensure_ascii=False)+'`.');add()
    add('<details><summary>독립 계산 요약 JSON — 재대조용</summary>');add();add('```json');add(json.dumps(d,ensure_ascii=False,separators=(',',':')));add('```');add('</details>');add()
    return '\n'.join(L)+'\n'

def selfcheck():
    # Meaningful arithmetic checks: delisting fallback, total-loss sensitivity,
    # fixed exit when entry changes, and constant paired-effect interval.
    dates=np.array([f'{i:08d}' for i in range(70)])
    a=np.ones((70,2))*10;a[42,0]=12;a[2,0]=11;a[20,1]=4;a[21:,1]=np.nan
    x={'codes':np.array(['a','b']),'close':a,'open':a.copy(),'high':a.copy(),'low':a.copy(),'endpos':np.array([999,21]),'lastpos':np.array([69,20])}
    r,d=price_returns(x,1,'last');assert np.allclose(r,[12/11-1,-.6]) and d.tolist()==[False,True]
    rh,_=price_returns(x,1,'haircut');assert np.allclose(rh,[12/11-1,-.9])
    r2,_=price_returns(x,1,'last','close2');assert np.isclose(r2[0],.2)
    f=pd.DataFrame({'month':['202001','202001','202002'],'D':[.02,.02,.02]});assert np.allclose(ci(f,'D'),[.02,.02,.02])

if __name__=='__main__':
    guard();selfcheck()
    if OUT.exists() and '## 7.' in OUT.read_text(encoding='utf-8') and '--verify' not in sys.argv:
        raise SystemExit('Frozen report includes section 7. Use --verify; do not overwrite.')
    results=run();body=render(results)
    if '--verify' in sys.argv:print(body)
    else:guard();OUT.write_text(body,encoding='utf-8');print('WROTE',OUT,flush=True)
