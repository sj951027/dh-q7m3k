"""Independent, offline macro/regime reproduction. No old research imports.

python -X utf8 -B research/handoff/code_20261102_macro_regime_blind.py
Writes only out_20261102_macro_regime and the requested REPLY in handoff.
Forbidden comparison documents are never opened by this code.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import re
import sqlite3

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'dh-q7m3k-data'
OUT=ROOT/'research/handoff/out_20261102_macro_regime'
REPLY=ROOT/'research/handoff/REPLY_20261102_macro_regime_blind.md'
METRICS=['os_mean','all_mean','ks_f40','os_tail20','os_minus_all']
AXES={'FX20':('USDKRW',1,'percent'), 'US20':('SPX',0,'percent'),
      'RATE20':('US10Y',2,'difference'), 'IXIC20':('IXIC',0,'percent'),
      'OIL20':('WTI',2,'percent')}
EXCLUDE=re.compile('금융|은행|증권|보험|캐피탈|카드|손해보험|생명|화재|저축|여신|신탁|리츠|REIT|부동산투자|스팩|SPAC',re.I)
PROTOCOL={
 'request':'REQUEST_20261102_macro_regime_blind',
 'signal_window':['20150201','20260831'],
 'grid':'first common KOSPI/KOSDAQ date >=20150201, then every 5 common sessions; t+41 within price data',
 'entry':'t+1 close', 'exit':'t+41 close; delisted within holding interval uses last stored positive close if exact exit absent',
 'eligibility':'allowed current metadata market/name/code; t and t+1 positive close and volume; t and t+1 close>=1000; positive t-20 close',
 'rank':'linear 20th percentile on ex-ante eligible R20, inclusive <=; missing future outcomes excluded only after selection, never re-ranked',
 'regime':'KOSPI common-axis R20: A<=-5; BC (-5,5]; D>5',
 'events':'greedy first A grid day with common-calendar index at least 40 after prior selected event',
 'macro_cutoff':'subtract 1/0/2 CALENDAR days from signal date for FX/US/rate+oil; last available observation <= cutoff',
 'macro_reference':'last observation <= last_selected_observation_date minus 28 CALENDAR days',
 'oil_negative':'exclude if any nonpositive WTI observation inside [reference observation date,last observation date]',
 'median':'A-day available-value median for both A events and A days; equal values go lower (<=median), upper >median',
 'bad_group':'FX/RATE/OIL upper; US/IXIC lower; US+IXIC zero sensitivity uses <0 versus >=0',
 'reference_splits':'each regime own all-period median; halves reuse pooled regime thresholds; all-period terciles per own axis',
 'bootstrap':'whole event rows 4000 draws seed20261030; whole calendar-month blocks with all member grid rows 2000 draws seed7; percentile95; thresholds fixed',
 'event_minimum':'either group n<5 => n shortage only, no reported estimate or CI',
 'depth_match':'A-day KOSPI R20 5 quantile bins; within bin global A-axis split; common weights=min(nbad,ngood); fixed bins/labels, month bootstrap',
 'verdict':'os_mean primary. Closed has precedence: |event diff|<3 or sign flip across A/BC/D/ALL/A halves/ALL halves, or |A-day rho(axis,R20)|>=.5 and |depth-matched diff|<3. Open requires nonzero95CI, |event diff|>=3, same sign in all references and depth match. Otherwise consistent sign+CI contains0=hold; unassessable=hold. No causal claim.',
 'no_network':True, 'read_only_databases':['ohlcv_10y.db','macro_10y.db']}


def guard():
    now=datetime.now(ZoneInfo('Asia/Seoul'))
    if now.weekday()<5 and '20:10'<=now.strftime('%H:%M')<'22:30':
        raise RuntimeError('Weekday batch exclusion window')
    return now.isoformat(timespec='seconds')


def ro(path):
    guard()
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    c.execute('PRAGMA query_only=ON')
    assert c.execute('PRAGMA query_only').fetchone()[0]==1
    return c


def state(path):
    s=path.stat();return {'bytes':s.st_size,'mtime_ns':s.st_mtime_ns}


def dump(path,obj):
    guard();path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def baskets():
    c=ro(DATA/'ohlcv_10y.db')
    try:
        meta=pd.read_sql_query('SELECT ticker,name,market,listed,delisted,status FROM meta ORDER BY ticker',c)
        ix=pd.read_sql_query("SELECT series,date,close FROM index_daily WHERE series IN ('KOSPI','KOSDAQ') ORDER BY date",c)
        index=ix.pivot(index='date',columns='series',values='close').dropna().sort_index()
        calendar=index.index.to_numpy(str); D=len(calendar); lookup={d:i for i,d in enumerate(calendar)}
        last_price=c.execute('SELECT max(date) FROM prices').fetchone()[0]
        ok=meta.market.isin(['KOSPI','KOSDAQ','KOSDAQ GLOBAL']) & meta.ticker.str.endswith('0')
        ok &= ~meta.name.fillna('').str.contains(EXCLUDE) & ~meta.ticker.isin(['055550','001450'])
        uni=meta[ok].reset_index(drop=True);N=len(uni)
        close=np.full((D,N),np.nan);volume=np.full((D,N),np.nan)
        seen_rows=0
        for j,ticker in enumerate(uni.ticker):
            for d,p,v in c.execute('SELECT date,close,volume FROM prices WHERE ticker=? ORDER BY date',(ticker,)):
                k=lookup.get(d)
                if k is not None:
                    close[k,j]=np.nan if p is None else p
                    volume[k,j]=np.nan if v is None else v;seen_rows+=1
            if (j+1)%500==0:guard();print('read tickers',j+1,'/',N,flush=True)
        start=int(np.searchsorted(calendar,'20150201'))
        grid=np.array([i for i in range(start,D-41,5) if calendar[i]<='20260831' and calendar[i+41]<=last_price])
        ks=index.KOSPI.to_numpy(float)
        r20=100*(close[grid]/close[grid-20]-1)
        entry=close[grid+1]
        valid=(close[grid]>=1000)&(entry>=1000)&(volume[grid]>0)&(volume[grid+1]>0)&(close[grid-20]>0)&np.isfinite(r20)
        exit_price=close[grid+41].copy();fallback=np.zeros_like(valid)
        delisted=uni.delisted.fillna('').str.replace('-','',regex=False).to_numpy(str)
        for j,date in enumerate(delisted):
            if not date:continue
            selected=np.flatnonzero(valid[:,j] & (date>calendar[grid+1]) & (date<=calendar[grid+41]) & ~(exit_price[:,j]>0))
            for z in selected:
                candidates=np.flatnonzero((close[:grid[z]+42,j]>0)&(np.arange(grid[z]+42)>=grid[z]+1))
                if len(candidates):exit_price[z,j]=close[candidates[-1],j];fallback[z,j]=True
        with np.errstate(divide='ignore',invalid='ignore'):
            returns=100*(exit_price/entry-1)
        returns[~(valid & (exit_price>0) & np.isfinite(returns))]=np.nan
        records=[]
        for z,i in enumerate(grid):
            threshold=np.quantile(r20[z,valid[z]],.2,method='linear') if valid[z].any() else np.nan
            oversold=valid[z]&(r20[z]<=threshold)
            osr=returns[z,oversold];allr=returns[z,valid[z]]
            ks20=100*(ks[i]/ks[i-20]-1)
            records.append({'date':calendar[i],'calendar_i':int(i),'entry_date':calendar[i+1],'exit_date':calendar[i+41],
                'regime':'A' if ks20<=-5 else 'D' if ks20>5 else 'BC','ks_r20':ks20,
                'ks_f40':100*(ks[i+41]/ks[i+1]-1),'os_mean':float(np.nanmean(osr)),
                'all_mean':float(np.nanmean(allr)),'os_tail20':float(np.mean(osr[np.isfinite(osr)]<=-20)*100),
                'n_eligible':int(valid[z].sum()),'n_os_selected':int(oversold.sum()),
                'n_all_outcome':int(np.isfinite(allr).sum()),'n_os_outcome':int(np.isfinite(osr).sum()),
                'n_all_missing_outcome':int(np.isnan(allr).sum()),'n_os_missing_outcome':int(np.isnan(osr).sum()),
                'n_delist_fallback':int(fallback[z].sum()),'os_r20_threshold':float(threshold)})
        days=pd.DataFrame(records)
        days['os_minus_all']=days.os_mean-days.all_mean
        days['event']=False;last=-10000
        for row in days.itertuples():
            if row.regime=='A' and row.calendar_i-last>=40:
                days.loc[row.Index,'event']=True;last=row.calendar_i
        info={'universe_meta_rows':N,'price_rows_read':seen_rows,'common_calendar_rows':D,
              'calendar_first':calendar[0],'calendar_last':calendar[-1],'price_last':last_price,
              'grid_first':days.date.min(),'grid_last':days.date.max(),'grid_rows':len(days),
              'regime_counts':{k:int(v) for k,v in days.regime.value_counts().items()},
              'event_dates':days.loc[days.event,'date'].tolist(),'delist_fallback_total':int(fallback.sum()),
              'all_missing_outcome_total':int(days.n_all_missing_outcome.sum()),
              'os_missing_outcome_total':int(days.n_os_missing_outcome.sum())}
        # Small audit: recompute 3 days from selected vectors with scalar means.
        for z in [0,len(grid)//2,len(grid)-1]:
            selected=valid[z]&(r20[z]<=days.iloc[z].os_r20_threshold)
            vals=[float(returns[z,j]) for j in np.flatnonzero(selected) if np.isfinite(returns[z,j])]
            assert abs(sum(vals)/len(vals)-days.iloc[z].os_mean)<1e-10
        return days,info
    finally:c.close()


def macro_axes(days):
    c=ro(DATA/'macro_10y.db')
    try:raw=pd.read_sql_query('SELECT series,date,close FROM series_daily ORDER BY series,date',c)
    finally:c.close()
    info={}
    for axis,(series,lag,kind) in AXES.items():
        frame=raw[raw.series==series].copy(); ds=frame.date.to_numpy(str);vals=frame.close.to_numpy(float)
        dt=pd.to_datetime(ds)
        rows=[]
        for t in days.date:
            cutoff=(pd.Timestamp(str(t))-pd.Timedelta(days=lag)).strftime('%Y%m%d')
            k=np.searchsorted(ds,cutoff,side='right')-1
            row={'value':np.nan,'last_date':None,'reference_date':None,'last':np.nan,'reference':np.nan,'reason':''}
            if k<0:row['reason']='no_last'
            else:
                baseline=(dt[k]-pd.Timedelta(days=28)).strftime('%Y%m%d')
                b=np.searchsorted(ds,baseline,side='right')-1
                if b<0:row['reason']='no_reference'
                else:
                    row.update(last_date=ds[k],reference_date=ds[b],last=vals[k],reference=vals[b])
                    assert ds[k]<=cutoff and ds[b]<=baseline
                    if series=='WTI' and np.any(vals[b:k+1]<=0):row['reason']='nonpositive_in_window'
                    elif kind=='percent' and vals[b]<=0:row['reason']='nonpositive_denominator'
                    else:row['value']=float(vals[k]-vals[b] if kind=='difference' else 100*(vals[k]/vals[b]-1))
            rows.append(row)
        f=pd.DataFrame(rows)
        days[axis]=f.value
        for col in ['last_date','reference_date','last','reference','reason']:days[axis+'_'+col]=f[col]
        info[axis]={'series':series,'lag_calendar_days':lag,'missing_all':int(f.value.isna().sum()),
                    'missing_A':int(days.loc[days.regime=='A',axis].isna().sum()),
                    'missing_events':int(days.loc[days.event,axis].isna().sum()),
                    'reasons':{k:int(v) for k,v in f.reason.value_counts().items() if k},
                    'excluded_dates':days.loc[f.value.isna(),'date'].tolist()}
    return days,info


def weights(frame,unit):
    n=len(frame)
    if unit=='event':
        rng=np.random.default_rng(20261030);B=4000
        ids=np.arange(n);u=n
    else:
        rng=np.random.default_rng(7);B=2000
        _,ids=np.unique(frame.date.str[:6],return_inverse=True);u=int(ids.max()+1)
    samples=rng.integers(0,u,size=(B,u))
    w=np.zeros((B,u),dtype=np.int16)
    np.add.at(w,(np.repeat(np.arange(B),u),samples.ravel()),1)
    return w[:,ids].astype(float),u


def estimate(frame,bad,unit='month'):
    f=frame.reset_index(drop=True); bad=np.asarray(bad,bool)
    nb=int(bad.sum());ng=len(f)-nb
    result={'n_bad':nb,'n_good':ng,'unit':unit,'status':'ok','metrics':{}}
    if min(nb,ng)==0 or (unit=='event' and min(nb,ng)<5):
        result['status']='n 부족';return result
    w,blocks=weights(f,unit);result['n_blocks']=blocks
    wb=w*bad;wg=w*(~bad);db=wb.sum(axis=1);dg=wg.sum(axis=1)
    valid=(db>0)&(dg>0);result['valid_bootstraps']=int(valid.sum())
    for col in METRICS:
        y=f[col].to_numpy(float);assert np.isfinite(y).all()
        point=float(y[bad].mean()-y[~bad].mean())
        boot=(wb[valid]@y)/db[valid]-(wg[valid]@y)/dg[valid]
        lo,hi=np.quantile(boot,[.025,.975])
        result['metrics'][col]={'bad_mean':float(y[bad].mean()),'good_mean':float(y[~bad].mean()),
                                'diff':point,'lo':float(lo),'hi':float(hi)}
    return result


def bad_side(values,axis,threshold,mode='median'):
    if mode=='zero':return values<0
    return values<=threshold if axis in ('US20','IXIC20') else values>threshold


def corr(frame,a,b):
    f=frame[[a,b]].dropna();n=len(f)
    if n<3 or min(f[a].nunique(),f[b].nunique())<2:return {'n':n,'rho':None}
    return {'n':n,'rho':float(spearmanr(f[a],f[b]).statistic)}


def matched(frame,axis,threshold):
    f=frame[frame[axis].notna()].copy().reset_index(drop=True)
    # Cutpoints are from all A-day depths before axis-specific missing removal.
    edges=np.unique(np.quantile(frame.ks_r20,[0,.2,.4,.6,.8,1]))
    f['stratum']=pd.cut(f.ks_r20,edges,include_lowest=True,labels=False)
    bad=np.asarray(bad_side(f[axis],axis,threshold),bool)
    w,_=weights(f,'month'); B=len(w)
    total=0.;points=np.zeros(len(METRICS));boot_num=np.zeros((B,len(METRICS)));boot_den=np.zeros(B)
    strata=[];usable=0
    for label in sorted(f.stratum.dropna().unique()):
        select=f.stratum.to_numpy()==label;mb=select&bad;mg=select&~bad
        nb=int(mb.sum());ng=int(mg.sum());common=min(nb,ng)
        row={'bin':int(label),'n_bad':nb,'n_good':ng,'weight':common}
        if common:
            y=f[METRICS].to_numpy(float); delta=y[mb].mean(axis=0)-y[mg].mean(axis=0)
            points+=common*delta;total+=common;usable+=nb+ng
            row['diffs']={m:float(d) for m,d in zip(METRICS,delta)}
            db=w[:,mb].sum(axis=1);dg=w[:,mg].sum(axis=1);good=(db>0)&(dg>0)
            # Keep original matching weights, discard bootstrap draw if any support stratum disappears.
            boot=np.zeros((B,len(METRICS)))
            boot[good]=(w[good][:,mb]@y[mb])/db[good,None]-(w[good][:,mg]@y[mg])/dg[good,None]
            boot[~good]=np.nan;boot_num+=common*boot;boot_den+=common
        strata.append(row)
    result={'strata':strata,'n':len(f),'usable_rows':usable,'common_pair_weight':total,'metrics':{}}
    if total:
        boot=boot_num/boot_den[:,None];valid=np.isfinite(boot).all(axis=1)
        result['valid_bootstraps']=int(valid.sum())
        for j,m in enumerate(METRICS):
            lo,hi=np.quantile(boot[valid,j],[.025,.975])
            result['metrics'][m]={'diff':float(points[j]/total),'lo':float(lo),'hi':float(hi)}
    return result


def statistics(days):
    A=days[days.regime=='A'];events=days[days.event]
    result={'splits':{},'matched':{},'correlations':{},'axis_correlations':{},'terciles':{},'thresholds':{}}
    for axis in AXES:
        threshold=float(A[axis].median());result['thresholds'][axis]=threshold
        specs=[('median',threshold)]+([('zero',0.)] if axis in ('US20','IXIC20') else [])
        for mode,cut in specs:
            key=axis+':'+mode; out={}
            for label,frame,unit,th in [('A_events',events,'event',cut),('A_days',A,'month',cut)]:
                f=frame.dropna(subset=[axis]);out[label]=estimate(f,bad_side(f[axis],axis,th,mode),unit)
                out[label]['threshold']=th
            for regime in ['ALL','A','BC','D']:
                f=days if regime=='ALL' else days[days.regime==regime]
                th=0. if mode=='zero' else float(f[axis].median())
                for period in ['pooled','early','late']:
                    g=f if period=='pooled' else f[f.date<='20201231'] if period=='early' else f[f.date>='20210101']
                    g=g.dropna(subset=[axis]);label=regime+'_'+period
                    out[label]=estimate(g,bad_side(g[axis],axis,th,mode))
                    out[label]['threshold']=th
            result['splits'][key]=out
        result['matched'][axis]=matched(A,axis,threshold)
        for scope,frame in [('ALL',days),('A_days',A),('A_events',events)]:
            for y in ['os_mean','ks_f40','ks_r20']:
                result['correlations'][f'{axis}:{scope}:{y}']=corr(frame,axis,y)
        f=days.dropna(subset=[axis]).copy();edges=np.quantile(f[axis],[1/3,2/3])
        f['tercile']=np.searchsorted(edges,f[axis],side='left')
        groups=[]
        for g in range(3):
            sub=f[f.tercile==g];w,blocks=weights(sub,'month');den=w.sum(axis=1)
            row={'tercile':g+1,'n':len(sub),'months':blocks,'metrics':{}}
            for m in METRICS:
                y=sub[m].to_numpy();boot=(w@y)/den;lo,hi=np.quantile(boot,[.025,.975])
                row['metrics'][m]={'mean':float(y.mean()),'lo':float(lo),'hi':float(hi)}
            groups.append(row)
        result['terciles'][axis]={'cuts':[float(x) for x in edges],'groups':groups}
    for scope,frame in [('ALL',days),('A_days',A),('A_events',events)]:
        for a,b in [('FX20','US20'),('FX20','RATE20'),('US20','RATE20')]:
            result['axis_correlations'][f'{scope}:{a}:{b}']=corr(frame,a,b)
    result['verdicts']={}
    for axis in ['FX20','US20','RATE20']:
        s=result['splits'][axis+':median'];e=s['A_events'];reason=[]
        if e['status']!='ok':
            result['verdicts'][axis]={'label':'보류','reasons':['A 사건 n 부족']};continue
        point=e['metrics']['os_mean'];sign=np.sign(point['diff'])
        references=['A_days','ALL_pooled','BC_pooled','D_pooled','A_early','A_late','ALL_early','ALL_late']
        flips=[name for name in references if s[name]['status']=='ok' and np.sign(s[name]['metrics']['os_mean']['diff'])!=sign]
        d=result['matched'][axis]['metrics'].get('os_mean')
        rho=result['correlations'][f'{axis}:A_days:ks_r20']['rho']
        if abs(point['diff'])<3:reason.append('|A 사건 차이|<3%p')
        if flips:reason.append('부호 반전: '+','.join(flips))
        if d and rho is not None and abs(rho)>=.5 and abs(d['diff'])<3:reason.append('깊이 반복: |rho|>=0.5 및 짝 차이<3%p')
        if reason:label='닫음'
        elif d and np.sign(d['diff'])==sign and point['lo']*point['hi']>0 and all(s[x]['status']=='ok' for x in references):
            label='열림';reason=['사전 고정 조건 충족']
        else:
            label='보류';reason=['구간이 0 포함 또는 깊이/참고 조건 미충족']
        result['verdicts'][axis]={'label':label,'reasons':reason}
    return result


def f(x):return 'NA' if x is None or not np.isfinite(x) else f'{x:.3f}'
def interval(x):return f"{f(x['diff'])} [{f(x['lo'])}, {f(x['hi'])}]"


def report(days,info,macro,result,run):
    lines=['# REPLY — 거시 축으로 코스피 A 사건을 나누는 눈가림 계산','',
      '## 1. 독립 계산 범위·사전 고정','',
      f"실행 {run['started_at']}~{run['finished_at']}. 새 코드로 두 DB만 mode=ro/query_only로 읽었다. 네트워크·기존 연구 코드 import·운영 DB 쓰기 없음. 이전 대화에서 수급 연구의 요약 결론을 접한 이력은 있지만 이번 계산 전 금지 연구 본문·지도·계획서·worklog 본문은 열지 않았다. 아래 결과와 코드 해시를 먼저 고정한 뒤 §7 대조를 별도로 한다.",
      '요청서에는 §7 제목이 없지만 §5의 마지막 대조 지시를 §7로 해석했다. 기준이 수치로 정해지지 않은 부분은 protocol.json에 계산 전 고정했다.',
      '',
      '- 격자는 2015-02-02부터 5 공통 거래일 간격. R20은 공통 거래일 20칸 전. t·t+1 종가 모두 1,000원 이상, 양수 거래량. 순위는 미래 결과를 보기 전 대상에서 하위 20%(경계 포함), 미래 결과 누락 때문에 재선정하지 않음.',
      '- A 날 중앙값은 모든 A 격자일에서 구하고 사건에도 같은 문턱 적용. 동률은 아래(≤), 위는 >. 미국 축 나쁜 쪽은 낮은 값, 환율·금리·유가는 높은 값. 미국 축 0 기준은 <0 / ≥0.',
      '- t−1·t−2는 달력일 차감. 기준 관측은 마지막 관측 날짜의 28달력일 전 이하 마지막 값. 한국 달력에 채우지 않음. 유가는 비교 구간 안 비양수 관측이 하나라도 있으면 제외.',
      '- 사건 전체 행을 4,000회(seed 20261030), 월 전체 묶음을 2,000회(seed 7) 복원 추출. 분기 문턱은 고정, 95% 백분위 구간. 사건 그룹당 5개 미만은 차이·구간 미제시.',
      '- 깊이 짝은 A 날 R20 5분위. 같은 칸의 축 위/아래 평균 차이를 min(양쪽 n)으로 가중, 월 블록 구간. 일대일 가까운 날짜 짝이나 회귀 조정은 아님.',
      '- 판정은 os_mean 주지표. 닫음 조건이 보류보다 우선. 깊이 차이 소멸은 |짝 차이|<3%p로 고정. 부호 점검은 A 날·전체·BC·D·A 앞뒤반·전체 앞뒤반. 과매도−전체 차이와 보조 결과는 별도 표.',
      '', '## 2. 자료·시각·결측','',
      f"유니버스 메타 {info['universe_meta_rows']}종목, 읽은 가격 {info['price_rows_read']:,}행. 공통 달력 {info['common_calendar_rows']}일, 가격 마지막 {info['price_last']}. 격자 {info['grid_rows']}일({info['grid_first']}~{info['grid_last']}), 칸별 {info['regime_counts']}. A 사건 {len(info['event_dates'])}개.",
      f"상폐 마지막 저장가격 적용 {info['delist_fallback_total']} 종목×격자일. 미래 결과 누락: 전체 {info['all_missing_outcome_total']}, 과매도 {info['os_missing_outcome_total']} 종목×격자일. 각 날짜의 분모는 days.csv/events.csv에 있다.",
      '', '|축|전체 누락|A 날 누락|A 사건 누락|누락 사유|','|---|---:|---:|---:|---|']
    for axis,m in macro.items():lines.append(f"|{axis}|{m['missing_all']}|{m['missing_A']}|{m['missing_events']}|{m['reasons']}|")
    lines += ['', 'US20/IXIC20의 미국 D=t 종가는 한국 t+1 새벽이므로 한국 t 종가 시점에는 미공개다. 요청 표의 규칙을 그대로 적용했고, t+1 종가 진입 전에 알려진 값이라는 뜻으로만 해석한다. 환율 D≤t−1, 금리·유가 D≤t−2도 실제 과거 제공처 게시 시각을 입증하지 않는다. 금리·유가 공개 지연이 이보다 길었던 날의 시각 위반 가능성은 남는다. 값은 현재 제공처 역사 스냅샷이며 과거 수정 전 보관본이 아니다.',
      '모든 기간 중앙값·분위 문턱은 요청된 후향적 분류다. 당시 정해져 있던 실시간 매매 규칙으로 해석할 수 없다.',
      '', '## 3. 본문 — A 사건 차이','', '표는 나쁜 쪽−좋은 쪽 %p, 사건 부트스트랩 95% 구간. os_tail20은 종목 비율의 %p 차이. os_minus_all은 같은 사건·같은 추출에서 (과매도 차이−전체 차이)이며 독립 구간끼리 빼지 않았다.',
      '', '|축/기준|문턱|나쁨 n|좋음 n|os_mean|all_mean|ks_f40|os_tail20|os−all|','|---|---:|---:|---:|---|---|---|---|---|']
    for key,s in result['splits'].items():
        e=s['A_events']; cells=[interval(e['metrics'][m]) for m in METRICS] if e['status']=='ok' else ['n 부족']*5
        lines.append('|'+ '|'.join([key,f(e['threshold']),str(e['n_bad']),str(e['n_good'])]+cells)+'|')
    lines += ['', '사건 날짜: '+', '.join(info['event_dates']), '',
      '사건별 결과·축 값·선택 관측일·28일 전 기준 관측일·누락 사유는 events.csv에 전부 공개했다. IXIC는 감도, OIL은 참고이며 열림 후보 판정에는 쓰지 않았다.',
      '', '## 4. 겹치는 A 날·칸·기간·깊이 참고','',
      '아래는 os_mean 차이와 월 블록 95% 구간. 모든 결과값·그룹 평균·n·문턱·유효 추출 수는 results.json에 있다. 각 칸은 자체 전체기간 중앙값으로 분기하고 앞/뒤반에는 같은 문턱을 재사용했다.',
      '', '|축/기준|표본|나쁨 n|좋음 n|os_mean 차이 [95% 구간]|','|---|---|---:|---:|---|']
    for key,s in result['splits'].items():
        for name in ['A_days','ALL_pooled','BC_pooled','D_pooled','A_early','A_late','ALL_early','ALL_late']:
            e=s[name];v=interval(e['metrics']['os_mean']) if e['status']=='ok' else 'n 부족'
            lines.append(f"|{key}|{name}|{e['n_bad']}|{e['n_good']}|{v}|")
    lines += ['', '깊이 5분위 안 비교:', '', '|축|사용 A 날|짝 가중합|os_mean|all_mean|ks_f40|os_tail20|os−all|','|---|---:|---:|---|---|---|---|---|']
    for axis,m in result['matched'].items():
        lines.append('|'+ '|'.join([axis,str(m['usable_rows']),f(m['common_pair_weight'])]+[interval(m['metrics'][x]) if x in m['metrics'] else 'n 부족' for x in METRICS])+'|')
    lines += ['', '전체 기간 축 3분위의 과매도 평균(월 블록 95% 구간; 분위 1은 낮은 값):','',
      '|축|분위|날 n|os_mean 평균 [95% 구간]|','|---|---:|---:|---|']
    for axis,t in result['terciles'].items():
        for g in t['groups']:
            m=g['metrics']['os_mean'];lines.append(f"|{axis}|{g['tercile']}|{g['n']}|{f(m['mean'])} [{f(m['lo'])}, {f(m['hi'])}]|")
    lines += ['', '## 5. 순위상관','', '|축|표본|결과|n|Spearman rho|','|---|---|---|---:|---:|']
    for key,x in result['correlations'].items():
        axis,scope,y=key.split(':');lines.append(f"|{axis}|{scope}|{y}|{x['n']}|{f(x['rho'])}|")
    lines += ['', '|표본|축 쌍|n|Spearman rho|','|---|---|---:|---:|']
    for key,x in result['axis_correlations'].items():
        scope,a,b=key.split(':');lines.append(f"|{scope}|{a}↔{b}|{x['n']}|{f(x['rho'])}|")
    lines += ['', '상관은 기술 통계이며 원인·독립 효과를 입증하지 않는다. 축↔R20 상관과 깊이 짝 비교를 함께 본다.',
      '', '## 6. 사전 조건표 판정·한계·재현','']
    for axis,v in result['verdicts'].items():lines.append(f"- **{axis}: {v['label']}** — {'; '.join(v['reasons'])}.")
    lines += ['', '이는 이번 요청의 후속 연구 분류이며 모델 채택·점수 변경 판정이 아니다. 세 주축과 감도·참고 축의 다중비교를 보정한 구간은 아니다. 사건 수가 적고 월 블록은 40일 결과의 모든 겹침을 없애지 못한다. 현재 메타 이름/시장으로 유니버스를 거른 선택 편향, 수정주가, 거래정지 종가 청산 가능성, 상폐 마지막 가격의 낙관성, 비용 미반영이 남는다.',
      '', '`python -X utf8 -B research/handoff/code_20261102_macro_regime_blind.py`',
      '', f"코드 SHA256 `{run['code_sha256']}`. protocol.json은 계산 시작 전, blind_freeze.json은 대조 문서 열기 전에 생성했다. DB 전후 크기/mtime 불변(내용 전체 해시 검증 아님). 큰 중간 파일은 생성하지 않는다.",
      '', '## 7. 독립 결과 고정 후 수급 연구 대조','', '아직 대조 문서를 열지 않은 상태의 독립 결과다. 고정 후 이 절에만 대조 내용을 추가한다.','']
    return '\n'.join(lines)


def self_check():
    # Boundary/tie orientation, event spacing, relative versus rate difference.
    v=pd.Series([-1.,0.,1.]);assert bad_side(v,'US20',0).tolist()==[True,True,False]
    assert bad_side(v,'US20',0,'zero').tolist()==[True,False,False]
    assert bad_side(v,'RATE20',0).tolist()==[False,False,True]
    frame=pd.DataFrame({'date':[f'202001{i+1:02}' for i in range(10)]})
    for j,m in enumerate(METRICS):frame[m]=np.arange(10)+j
    e=estimate(frame,np.arange(10)<5,'event')
    assert abs(e['metrics']['os_mean']['diff']+5)<1e-10
    assert estimate(frame.iloc[:9],np.arange(9)<5,'event')['status']=='n 부족'
    print('self checks passed',flush=True)


def main():
    started=guard();self_check();OUT.mkdir(exist_ok=True)
    sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    dump(OUT/'protocol.json',{'frozen_at':started,'code_sha256':sha,**PROTOCOL})
    states={name:state(DATA/name) for name in PROTOCOL['read_only_databases']}
    days,info=baskets();print('baskets',info,flush=True)
    days,macro=macro_axes(days);print('axes ready',macro,flush=True)
    stats=statistics(days);print('statistics ready',stats['verdicts'],flush=True)
    assert states=={name:state(DATA/name) for name in states}
    run={'started_at':started,'finished_at':guard(),'code_sha256':sha,'db_states':states,
         'python_dependencies':{'numpy':np.__version__,'pandas':pd.__version__}}
    guard();days.to_csv(OUT/'days.csv',index=False,encoding='utf-8-sig')
    events=days[days.event].copy()
    for axis,cut in stats['thresholds'].items():events[axis+'_bad_median']=bad_side(events[axis],axis,cut).where(events[axis].notna())
    events.to_csv(OUT/'events.csv',index=False,encoding='utf-8-sig')
    dump(OUT/'results.json',{'run':run,'data':info,'macro':macro,**stats})
    REPLY.write_text(report(days,info,macro,stats,run),encoding='utf-8')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [OUT/'protocol.json',OUT/'events.csv',OUT/'days.csv',OUT/'results.json']}
    dump(OUT/'blind_freeze.json',{'frozen_at':guard(),'code_sha256':sha,'files':hashes,
                                  'blind_reply_sha256':hashlib.sha256(REPLY.read_bytes()).hexdigest()})
    print('FROZEN',OUT/'blind_freeze.json',flush=True)


if __name__=='__main__':main()
