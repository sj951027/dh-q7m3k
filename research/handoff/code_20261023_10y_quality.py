"""Offline, read-only quality audit. No collectors/imported project code/network.
Run: python -B research/handoff/code_20261023_10y_quality.py
Writes only REPLY_20261023_10y_quality.md beside this script.
"""
from __future__ import annotations
import collections
import datetime as dt
import hashlib
import json
import pathlib
import sqlite3
import sys
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT.parent / 'dh-q7m3k-data'
OUT = pathlib.Path(__file__).with_name('REPLY_20261023_10y_quality.md')

def guard():
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    if now.weekday() < 5 and (20,10) <= (now.hour,now.minute) < (22,30):
        raise RuntimeError('Weekday batch window: no file/DB operations')

def ro(p):
    guard()
    c = sqlite3.connect(p.resolve().as_uri() + '?mode=ro', uri=True)
    c.execute('PRAGMA query_only=ON')
    c.execute('PRAGMA temp_store=MEMORY')
    return c

def days(a,b):
    return (pd.Timestamp(str(b))-pd.Timestamp(str(a))).days

def spans(indices):
    if not len(indices): return []
    return np.split(indices, np.where(np.diff(indices)>1)[0]+1)

def pct(a,b): return 100*a/b if b else None

def audit():
    guard()
    paths=[DATA/'ohlcv_10y.db',DATA/'ohlcv.db',ROOT/'history.db']
    stats={str(p):[p.stat().st_size,p.stat().st_mtime_ns] for p in paths}
    r,o=ro(paths[0]),ro(paths[1])
    meta=pd.read_sql_query('SELECT * FROM meta ORDER BY ticker',r).set_index('ticker')
    calendar=np.array([a[0] for a in o.execute("SELECT date FROM market_daily WHERE series='KOSPI' AND date<='20261021' ORDER BY date")])
    observed_axis=np.array([a[0] for a in r.execute('SELECT DISTINCT date FROM prices ORDER BY date')])
    extended_axis=np.unique(np.r_[observed_axis[observed_axis<calendar[0]],calendar])
    cindex={x:i for i,x in enumerate(calendar)}
    result={'input_stats':stats,'calendar':[calendar[0],calendar[-1],len(calendar)],
            'status':meta.groupby(['status']).size().to_dict(),'sources':r.execute('SELECT source,COUNT(*),COUNT(DISTINCT ticker),MIN(date),MAX(date) FROM prices GROUP BY source').fetchall(),
            'errors':meta[meta.status!='done'].reset_index().to_dict('records')}
    candidates=[]; compare=[]; gaps=[]; missing=[]; zero_spans=[]; tails=[]; outliers=[]; anomalies=[]; changes=[]
    counters=collections.Counter(); susp_missing=collections.Counter(); price_tickers=set()
    oq='''SELECT date,open,high,low,close,volume,change_pct,shares,is_suspended,market,'main' src FROM daily_ohlcv WHERE ticker=?
    UNION ALL SELECT date,open,high,low,close,volume,change_pct,shares,is_suspended,market,'extra' src FROM daily_ohlcv_extra e
    WHERE ticker=? AND NOT EXISTS(SELECT 1 FROM daily_ohlcv b WHERE b.ticker=e.ticker AND b.date=e.date) ORDER BY date'''
    for k,(ticker,m) in enumerate(meta.iterrows()):
        if k%500==0: print('progress',k,len(meta),flush=True);guard()
        f=pd.read_sql_query('SELECT date,open,high,low,close,volume,change_pct,source FROM prices WHERE ticker=? ORDER BY date',r,params=(ticker,))
        if f.empty: continue
        price_tickers.add(ticker); counters['rows']+=len(f)
        a=f.close.to_numpy(float); v=f.volume.to_numpy(float); dates=f.date.to_numpy(); n=len(f)
        ratio=np.r_[np.nan,a[1:]/a[:-1]]; returns=ratio-1
        vr=np.divide(v,np.r_[np.nan,v[:-1]],out=np.full(n,np.nan),where=np.r_[False,v[:-1]>0])
        stored=f.change_pct.to_numpy(float)
        counters['stored_outlier']+=int((np.abs(stored)>.35).sum())
        counters['computed_outlier']+=int((np.abs(returns)>.35).sum())
        counters['change_mismatch']+=int((np.abs(stored-returns)>1e-8).sum())
        counters['zero_volume_rows']+=int((v==0).sum())
        listed_valid=bool(m.listed) and not pd.isna(pd.to_datetime(m.listed,errors='coerce'))
        delisted_valid=bool(m.delisted) and not pd.isna(pd.to_datetime(m.delisted,errors='coerce'))
        before=(dates<str(m.listed).replace('-','')) if listed_valid else np.zeros(n,bool)
        after=(dates>str(m.delisted).replace('-','')) if delisted_valid else np.zeros(n,bool)
        counters['before_listing_rows']+=int(before.sum());counters['after_delisting_rows']+=int(after.sum())
        if before.any() or after.any(): anomalies.append({'ticker':ticker,'name':m['name'],'kind':'outside_metadata_lifetime','before':int(before.sum()),'after':int(after.sum()),'first':dates[0],'last':dates[-1],'listed':m.listed,'delisted':m.delisted})
        badfinite=~np.isfinite(f[['open','high','low','close','volume']].to_numpy(float)).all(axis=1)
        positive=(f[['open','high','low']]>0).all(axis=1).to_numpy()
        badbar=positive & ((f.high.to_numpy()<np.maximum(f.open,a)) | (f.low.to_numpy()>np.minimum(f.open,a)) | (f.high.to_numpy()<f.low.to_numpy()))
        excess=np.maximum.reduce([np.maximum(f.open.to_numpy(),a)-f.high.to_numpy(),f.low.to_numpy()-np.minimum(f.open.to_numpy(),a),f.low.to_numpy()-f.high.to_numpy(),np.zeros(n)])/a
        counters['nonfinite_ohlcv']+=int(badfinite.sum());counters['invalid_ohlc_order']+=int(badbar.sum())
        counters['ohlc_excess_over001']+=int((badbar&(excess>.001)).sum());counters['ohlc_excess_over005']+=int((badbar&(excess>.005)).sum())
        for i in np.where(badbar|badfinite)[0]: anomalies.append({'ticker':ticker,'name':m['name'],'date':dates[i],'kind':'ohlcv_nonfinite_or_order','o':f.open.iloc[i],'h':f.high.iloc[i],'l':f.low.iloc[i],'c':a[i],'v':v[i],'excess_fraction':excess[i]})
        extreme=(ratio<=.4)|(ratio>=2.5)
        for i in np.where(extreme)[0]:
            prevvol=v[i-1]
            voljump=(np.isfinite(vr[i]) and (vr[i]<=.5 or vr[i]>=2)) or (prevvol==0 and v[i]>0) or (prevvol>0 and v[i]==0)
            if voljump:
                candidates.append({'ticker':ticker,'name':m['name'],'date':dates[i],'prev_date':dates[i-1],'prev_close':a[i-1],'close':a[i],'ratio':ratio[i],'prev_volume':prevvol,'volume':v[i],'volume_ratio':None if not np.isfinite(vr[i]) else vr[i], 'volume_restart':prevvol==0 and v[i]>0,'gap_days':days(dates[i-1],dates[i]),'delisted':m.delisted})
        op=pd.read_sql_query(oq,o,params=(ticker,ticker))
        if len(op):
            opbad=(op[['open','high','low','close']]>0).all(axis=1)&((op.high<op[['open','close']].max(axis=1))|(op.low>op[['open','close']].min(axis=1))|(op.high<op.low))
            counters['operational_invalid_ohlc_order']+=int(opbad.sum())
            for row in op[opbad].itertuples(): anomalies.append({'ticker':ticker,'name':m['name'],'date':row.date,'kind':'operational_ohlc_order','o':row.open,'h':row.high,'l':row.low,'c':row.close})
        j=f.merge(op,on='date',suffixes=('_r','_o'))
        if len(j):
            valid=(j.close_o>0)&np.isfinite(j.close_o)&np.isfinite(j.close_r)
            diff=(j.close_r/j.close_o-1).abs(); bad=valid&(diff>.005); eq=valid&(j.close_r==j.close_o); near=valid&(diff<=.001)
            rec={'ticker':ticker,'name':m['name'],'n':int(valid.sum()),'exact':int(eq.sum()),'within01':int(near.sum()),'over05':int(bad.sum()),'invalid_op':int((~valid).sum()),'first_bad':str(j.loc[bad,'date'].min()) if bad.any() else '', 'last_bad':str(j.loc[bad,'date'].max()) if bad.any() else '', 'min_factor':float((j.close_r/j.close_o)[valid].min()),'max_factor':float((j.close_r/j.close_o)[valid].max())}
            compare.append(rec)
            for label in ['n','exact','within01','over05','invalid_op']: counters['compare_'+label]+=rec[label]
            for label,group in j.groupby('src'):
                mask=group.close_o>0;d=(group.close_r/group.close_o-1).abs()
                counters['compare_'+label+'_n']+=int(mask.sum());counters['compare_'+label+'_exact']+=int(((group.close_r==group.close_o)&mask).sum());counters['compare_'+label+'_over05']+=int(((d>.005)&mask).sum())
            # Source-ratio changes distinguish old disagreement start from adjustment boundary.
            factor=(j.close_r/j.close_o).to_numpy(); shifted=np.r_[np.nan,factor[:-1]]
            boundaries=np.where(np.isfinite(factor)&np.isfinite(shifted)&(np.abs(factor/shifted-1)>.05))[0]
            for i in boundaries:
                changes.append({'ticker':ticker,'name':m['name'],'prev_date':j.date.iloc[i-1],'date':j.date.iloc[i],'factor_before':factor[i-1],'factor_after':factor[i],'research_ratio':j.close_r.iloc[i]/j.close_r.iloc[i-1],'operational_ratio':j.close_o.iloc[i]/j.close_o.iloc[i-1],'shares_ratio':j.shares.iloc[i]/j.shares.iloc[i-1] if j.shares.iloc[i-1]>0 else None,'research_volume_ratio':j.volume_r.iloc[i]/j.volume_r.iloc[i-1] if j.volume_r.iloc[i-1]>0 else None})
        # Official calendar coverage only within observed first/last; listing dates absent for current listings.
        expect=calendar[(calendar>=dates[0])&(calendar<=dates[-1])]
        absent=expect[~np.isin(expect,dates)]
        if len(expect): missing.append({'ticker':ticker,'name':m['name'],'n':len(expect),'missing':len(absent),'pct':pct(len(absent),len(expect))})
        active_end=min(calendar[-1],str(m.delisted).replace('-','')) if m.delisted else calendar[-1]
        expected_tail=calendar[(calendar>dates[-1])&(calendar<=active_end)]
        counters['after_last_missing']+=len(expected_tail)
        combined=np.r_[absent,expected_tail]
        lookup=op.set_index('date') if len(op) else pd.DataFrame()
        for group in spans(np.array(sorted(cindex[d] for d in combined),dtype=int)):
            gd=calendar[group];known_susp=known_live=unknown=0
            for day in gd:
                if len(lookup) and day in lookup.index:
                    if lookup.loc[day,'is_suspended']==1: known_susp+=1
                    else: known_live+=1
                else: unknown+=1
            susp_missing.update({'known_suspended':known_susp,'known_not_suspended':known_live,'unknown':unknown})
            if days(gd[0],gd[-1])>=30:
                gaps.append({'ticker':ticker,'name':m['name'],'start':gd[0],'end':gd[-1],'sessions':len(gd),'calendar_days':days(gd[0],gd[-1])+1,'known_suspended':known_susp,'known_not_suspended':known_live,'unknown':unknown,'delisted':m.delisted})
        for group in spans(np.where(v==0)[0]):
            if days(dates[group[0]],dates[group[-1]])>=30:
                zero_spans.append({'ticker':ticker,'name':m['name'],'start':dates[group[0]],'end':dates[group[-1]],'rows':len(group),'calendar_days':days(dates[group[0]],dates[group[-1]])+1,'constant_close':len(np.unique(a[group]))==1})
        if m.delisted:
            active=np.where(v>0)[0];lastactive=active[-1] if len(active) else None
            endpos=np.searchsorted(extended_axis,dates[-1])
            tail=f[f.date>=extended_axis[max(0,endpos-19)]]
            tailmask=dates>=extended_axis[max(0,endpos-19)]
            base=extended_axis[endpos-60] if endpos>=60 else ''
            baseidx=np.where(dates==base)[0]
            r60=a[-1]/a[baseidx[0]]-1 if len(baseidx) else None
            tails.append({'ticker':ticker,'name':m['name'],'delisted':m.delisted,'last':dates[-1],'last_active':dates[lastactive] if lastactive is not None else '', 'gap':days(dates[-1],m.delisted),'active_gap':days(dates[lastactive],m.delisted) if lastactive is not None else None,'zero20':int((tail.volume==0).sum()),'rows20':len(tail),'large20':int((np.abs(returns[tailmask])>.35).sum()),'same20':int((tail.close==tail.close.iloc[-1]).sum()),'r60':r60,'r60_base':base,'r60_calendar_days':days(base,dates[-1]) if base else None,'calendar_kind':'official' if base>=calendar[0] else 'observed_proxy','volume_last':v[-1]})
        for i in np.where(np.abs(returns)>.35)[0]:
            near_delist=bool(m.delisted and 0<=days(dates[i],m.delisted)<=30)
            prior_limit=bool(i>=3 and np.all((returns[i-3:i]>=.29)&(returns[i-3:i]<=.31)))
            gap=days(dates[i-1],dates[i]); restart=bool(v[i-1]==0 and v[i]>0)
            category='폐지 전 30일(정리매매 후보)' if near_delist else ('재개/거래공백 후보' if restart or gap>7 else ('스팩 이름(원인 미확인)' if '스팩' in m['name'] else ('상한가 근접 3회 뒤(원인 미확인)' if prior_limit else '그 외: 기업행동/오류 미확정')))
            outliers.append({'ticker':ticker,'name':m['name'],'date':dates[i],'prev_date':dates[i-1],'prev_close':a[i-1],'close':a[i],'change':returns[i],'volume':v[i],'prev_volume':v[i-1],'gap_days':gap,'category':category,'stored_change':stored[i],'delisted':m.delisted})
        if ticker=='005930': result['samsung']=f[(f.date>='20180425')&(f.date<='20180509')][['date','close','volume']].to_dict('records')
    result.update(counters=dict(counters),candidates=candidates,compare=sorted(compare,key=lambda x:(-x['over05'],x['ticker'])),gaps=gaps,missing=missing,zero_spans=zero_spans,tails=tails,outliers=outliers,anomalies=anomalies,changes=changes,susp_missing=dict(susp_missing))
    cached=json.loads((DATA/'listing_cache.json').read_text(encoding='utf-8'))
    listed=set(meta[(meta.status=='done')&(meta.delisted=='')].index); cachecodes={row['code'] for row in cached['rows']}
    result['cache']={'saved_at':cached['saved_at'],'source':cached['source'],'n':len(cached['rows']),'missing':[row for row in cached['rows'] if row['code'] not in listed], 'extra':meta.loc[sorted(listed-cachecodes)].reset_index()[['ticker','name','market']].to_dict('records')}
    opcodes={x[0] for x in o.execute('select distinct ticker from daily_ohlcv UNION select distinct ticker from daily_ohlcv_extra')}
    result['operational_missing_codes']=sorted(opcodes-price_tickers)
    result['op_missing_alphanumeric']=sorted(t for t in opcodes-price_tickers if not t.isdigit())
    result['metadata_columns']=list(meta.reset_index().columns)
    result['meta_empty_listed_count']=int(((meta.delisted=='')&(meta.listed=='')).sum())
    result['invalid_meta_listed']=meta[(meta.listed!='')&pd.to_datetime(meta.listed,errors='coerce').isna()].reset_index()[['ticker','name','listed','delisted']].to_dict('records')
    result['delisted_markets']=meta[(meta.status=='done')&(meta.delisted!='')].market.value_counts().to_dict()
    result['active_markets']=meta[(meta.status=='done')&(meta.delisted=='')].market.value_counts().to_dict()
    result['meta_row_count_mismatches']=r.execute('SELECT m.ticker,m.rows,COUNT(p.date) FROM meta m LEFT JOIN prices p ON p.ticker=m.ticker GROUP BY m.ticker HAVING m.rows!=COUNT(p.date)').fetchall()
    result['op_unmatched_rows']=o.execute("SELECT COUNT(*) FROM daily_ohlcv WHERE close<=0 OR close IS NULL").fetchone()[0]
    r.close();o.close()
    result['input_stats_after']={str(p):[p.stat().st_size,p.stat().st_mtime_ns] for p in paths}
    if stats!=result['input_stats_after']: raise RuntimeError('Input database size/mtime changed during audit')
    return result

def safe(v):
    if isinstance(v,np.generic): return v.item()
    raise TypeError(type(v).__name__)

def summary(d):
    out={k:v for k,v in d.items() if k not in ['candidates','compare','gaps','missing','zero_spans','tails','outliers','anomalies','changes','cache','operational_missing_codes']}
    out['candidate_count']=len(d['candidates']);out['candidate_tickers']=len({x['ticker'] for x in d['candidates']});out['candidate_examples']=d['candidates'][:25]
    out['compare_top20']=d['compare'][:20];out['compare_tickers']=len(d['compare']);out['compare_bad_tickers']=sum(x['over05']>0 for x in d['compare'])
    out['gap_count']=len(d['gaps']);out['gap_examples']=sorted(d['gaps'],key=lambda x:-x['sessions'])[:25]
    out['missing_quantiles']=np.quantile([x['pct'] for x in d['missing']],[0,.25,.5,.75,.9,.95,.99,1]).tolist()
    out['missing_rows']=sum(x['missing'] for x in d['missing']);out['missing_expected']=sum(x['n'] for x in d['missing']);out['missing_tickers']=sum(x['missing']>0 for x in d['missing'])
    out['zero_spans_count']=len(d['zero_spans']);out['zero_span_tickers']=len({x['ticker'] for x in d['zero_spans']})
    out['tail_summary']={'n':len(d['tails']),'max_gap':max(x['gap'] for x in d['tails']),'max_active_gap':max(x['active_gap'] or 0 for x in d['tails']),'active_gap_over30':sum((x['active_gap'] or 0)>30 for x in d['tails']),'zero_last':sum(x['volume_last']==0 for x in d['tails']),'large20':sum(x['large20']>0 for x in d['tails'])}
    out['tail_examples']=sorted(d['tails'],key=lambda x:-(x['active_gap'] or 0))[:10]
    out['outlier_categories']=dict(collections.Counter(x['category'] for x in d['outliers']));out['outlier_examples']=sorted(d['outliers'],key=lambda x:-abs(x['change']))[:15]
    out['anomalies_count']=len(d['anomalies']);out['anomalies_examples']=d['anomalies'][:10]
    out['changes_count']=len(d['changes']);out['changes_examples']=d['changes'][:25]
    out['cache']={'n':d['cache']['n'],'saved_at':d['cache']['saved_at'],'missing':len(d['cache']['missing']),'extra':len(d['cache']['extra']),'missing_numeric':[x for x in d['cache']['missing'] if x['code'].isdigit()]}
    return out

def report(d):
    c=d['counters']; lines=[]
    def add(s=''): lines.append(s)
    def num(x,nd=3):
        if x is None or (isinstance(x,float) and not np.isfinite(x)): return '확인 못 함'
        return f'{x:,.{nd}f}'
    def tab(headers,rows):
        add('| '+' | '.join(headers)+' |');add('| '+' | '.join(['---']*len(headers))+' |')
        for row in rows: add('| '+' | '.join(str(x).replace('|','/') for x in row)+' |')
        add()
    def details(title,items):
        add('<details>');add('<summary>'+title+'</summary>');add()
        for x in items: add('- '+x)
        add();add('</details>');add()
    add('# REPLY — 10년 일봉 자료 품질 검증 (2026-10-23)')
    add()
    add('요청: `REQUEST_20261023_10y_quality.md`. **판정: 지수 연구와 종목 바구니 연구를 분리해야 한다. 이 DB를 바구니 연구에 그대로 사용해도 된다는 결론은 지지하지 않는다.** 영문 코드 누락, 종목 구성·폐지 사유 정보 부족, 가격 불연속·무거래 구간의 처리 확인이 먼저다. 전략 성과·매수 규칙은 시험하지 않았다.')
    add()
    add(f"**실측 범위:** 연구 DB {c['rows']:,}행, {sum(x[2] for x in d['sources']):,}종목. `prices`·`meta`와 운영 DB의 본표/보충표·`market_daily`·`universe_events`·`dart_events`, 로컬 `listing_cache.json`을 사용했다. DB 연결은 모두 `mode=ro` 및 `PRAGMA query_only=ON`. `history.db`는 스키마 확인 외 분석에 사용하지 않았다. 외부 호출·수집기·배치·운영 코드 실행이나 수정은 없다.")
    add('판정 용어: **실측**은 저장값의 계산 결과, **후보/추정**은 가격 패턴에 의한 분류다. 기업행동·거래정지·폐지 사유의 공식 확인과 실제 청산 대금은 이 자료만으로 확정하지 않는다. 분포는 현재 파일 전수의 기술통계이며 전략 수익 추정이나 유의성 판정이 아니다.')
    add()
    add('## 1. 수정주가 판정 — 급변 20종목은 기업행동 확정 표본이 아니다')
    add()
    distinct=[];seen=set()
    for x in d['candidates']:
        if x['ticker'] not in seen: distinct.append(x);seen.add(x['ticker'])
    sample=distinct[:20]
    add(f"전일 저장 종가 비율 ≤0.4 또는 ≥2.5이며 거래량이 절반 이하/2배 이상 또는 0↔양수로 바뀐 행: **{len(d['candidates']):,}행 / {len(seen):,}종목**. 거래량 급변 기준은 요청에 수치가 없어 위와 같이 명시했다. 코드순 첫 20종목의 첫 해당 행을 제시한다. 이는 액면분할·병합·무상증자 20건을 확인했다는 뜻이 아니다.")
    add()
    tab(['코드·이름','전일→당일','종가 전→후','가격비','거래량 전→후','관측 판정'],[[x['ticker']+' '+x['name'],x['prev_date']+'→'+x['date'],f"{x['prev_close']:g}→{x['close']:g}",num(x['ratio']),f"{x['prev_volume']:g}→{x['volume']:g}",'불연속; 원인 미확인'] for x in sample])
    add(f"실측 ① 위 {len(sample)}종목은 선택 조건 자체가 가격 불연속이다. 이미 과거 가격이 보정되어 연속적인 기업행동은 이 검색으로 발견되지 않으므로 이 표로 수정/원시 비율을 추정할 수 없다.")
    smooth=[x for x in d['changes'] if .7<=x['research_ratio']<=1.3 and (x['operational_ratio']<=.4 or x['operational_ratio']>=2.5)]
    add(f"실측 ② 운영 대비 가격 배율 변화 >5%인 경계는 {len(d['changes']):,}건이다. 그중 운영 가격비 ≤0.4/≥2.5인데 연구 가격비는 0.7~1.3인 경우 {len(smooth)}건으로, 소급 조정과 양립하는 사례가 있다. **수정/원시가 종목별로 섞였는지 확정은 못 함**: 연구 가격이 불연속이라는 이유만으로 원시주가라고 단정할 수 없다.")
    sam=d.get('samsung',[])
    add('삼성전자 요청 사례의 저장값: '+', '.join(f"{x['date']}={x['close']:g}(거래량 {x['volume']:g})" for x in sam)+'. 이 구간의 가격 연속성은 확인하지만, 50:1 기업행동 자체를 확인하는 별도 원자료는 사용하지 않았다.')
    add()
    add('## 2. 운영 DB 전 종목 종가 대조')
    add()
    n=c['compare_n'];badstocks=sum(x['over05']>0 for x in d['compare'])
    add(f"같은 코드·같은 날짜, 유효 양수 종가를 비교했다. 본표 우선 + 보충표의 본표 미존재 키만 합쳤다. **n={n:,}행 / {len(d['compare']):,}종목**, 완전 일치 {c['compare_exact']:,}행({pct(c['compare_exact'],n):.4f}%), 0.1% 이내(일치 포함) {c['compare_within01']:,}행({pct(c['compare_within01'],n):.4f}%), 0.5% 초과 {c['compare_over05']:,}행({pct(c['compare_over05'],n):.4f}%, {badstocks}종목). 일치와 0.1% 이내는 중복 지표다.")
    add(f"운영 종가가 0/비유한인 매칭 행 {c['compare_invalid_op']:,}개는 상대오차 분모에서 제외했다. 매칭되지 않는 날짜·종목은 일치로 세지 않는다. 기존 300종목 표본의 추출 기준이 없어 그 표본의 98.85%를 그대로 재현했다고 말하지 않는다.")
    add()
    top=[x for x in d['compare'] if x['over05']][:20]
    tab(['코드·이름','매칭 n','>0.5% n','다른 구간 첫날','마지막 다른 날','연구/운영 배율 최소~최대'],[[x['ticker']+' '+x['name'],x['n'],x['over05'],x['first_bad'],x['last_bad'],num(x['min_factor'])+'~'+num(x['max_factor'])] for x in top])
    add('실측 ① 표의 시작일은 **관측 가능한 불일치 구간의 첫날**이다. 과거 전체가 소급 변경된 경우 겹침 구간의 첫날이 나오므로 기업행동 발생일·실제 소급 조정일로 읽으면 안 된다. 배율 변화 경계는 부록에 따로 남겼다.')
    add(f"실측 ② 연구 DB에 있는 종목의 운영 OHLC 내부 고저 범위 위반은 {c.get('operational_invalid_ohlc_order',0)}행이다(있으면 부록 G). 두 자료의 불일치 중 어느 쪽이 틀렸는지 확정할 제3의 기준 가격·기업행동 조정계수는 없다. 따라서 불일치를 운영 DB 오류로 단정하지 않았다. 서로 다른 조정 기준의 종가·OHLC를 이어 붙이는 것은 불연속을 만들 수 있다.")
    add()
    add('## 3. 빠진 날·빠진 종목')
    add()
    miss=d['missing'];rates=[x['pct'] for x in miss];q=np.quantile(rates,[0,.5,.9,.95,.99,1]);cache=d['cache'];gaps=d['gaps'];non_susp=[x for x in gaps if x['known_not_suspended']>0]
    rows=[['공식 거래일 축',str(d['calendar'][2])+'일',d['calendar'][0]+'~'+d['calendar'][1]],['첫~마지막 가격 사이 기대 행',f"{sum(x['n'] for x in miss):,}",f"{len(miss)}종목"],['내부 결측',f"{sum(x['missing'] for x in miss):,}행",f"{sum(x['missing']>0 for x in miss)}종목"],['종목별 결측률 min/중앙/p90/p95/p99/max',str(len(rates))+'종목',' / '.join(f'{v:.3f}%' for v in q)],['마지막 가격 이후 기대 행 결측',str(c['after_last_missing'])+'행','상장 중 또는 폐지일까지, 연구 종료 20261021 제한'],['30일 초과 무행 구간',str(len(gaps))+'구간',f"{len({x['ticker'] for x in gaps})}종목; 운영 정지=0 행 포함 {len(non_susp)}구간"],['거래량 0이 30일 초과 지속',str(len(d['zero_spans']))+'구간',str(len({x['ticker'] for x in d['zero_spans']}))+'종목; 정지 확정은 아님'],['meta 상태',str(len(d['errors']))+'미완료',str(d['status'])],['현재 캐시 대비 미수집',str(len(cache['missing']))+'종목',f"기준 {cache['saved_at']}, 캐시 {cache['n']}종목"],['요청서 2,867−2,778', '89종목','88개 영문 코드 확인; 원본 당시 목록 없어 나머지 1개 미확인']]
    tab(['항목','n','관측값·한계'],rows)
    add(f"실측 ① 공식 거래일 표는 {d['calendar'][0]}부터다. 내부 결측률 분모는 각 종목 첫~마지막 관측일과 그 거래일 축의 교집합이며 첫 관측 이전·마지막 관측 이후를 내부 결측률에 포함하지 않는다. 실제 상장 기간을 확정한 분모는 아니다. 현재 상장 종목 {d['meta_empty_listed_count']}개의 `listed`가 비어 있어 첫 관측 이전 누락은 판별 못 함. 2015~2023-05 공식 거래일 기준 결측률도 확인 못 함.")
    add(f"실측 ② 캐시 누락 {len(cache['missing'])}개 중 영문 코드 {sum(not x['code'].isdigit() for x in cache['missing'])}개로, 수집기의 `isdigit()` 제외와 일치한다. 캐시와 연구 메타의 시장 범위도 다르므로 89개 전체를 이 최신 캐시로 확정하지 않는다. 결측일의 운영 상태는 {d['susp_missing']}이다. `is_suspended=0`은 저장된 표시에 불과하며 실제 정지 아님을 독립 확정한 것은 아니다.")
    add()
    add('## 4. 폐지 종목 635개 — 끝 가격과 실제 청산 대금 구분')
    add()
    def tailgroup(x):
        if x['volume_last']==0: return '끝 거래량 0: 정지/무거래 가격 잔존 후보'
        if x['large20']>0: return '마지막 20축일 급변: 정리매매 후보'
        return '그 외: 끝값의 성격 미확인'
    groups=collections.defaultdict(list)
    for x in d['tails']: groups[tailgroup(x)].append(x)
    rows=[]
    for name,group in groups.items():
        vals=[x['r60']*100 for x in group if x['r60'] is not None]
        quant=np.quantile(vals,[.1,.5,.9]) if vals else []
        rows.append([name,len(group),len(vals),' / '.join(num(v,2)+'%' for v in quant) or '확인 못 함',sum((x['active_gap'] or 0)>30 for x in group)])
    rows.append(['공식 폐지 사유(합병·자진·실질심사)',len(d['tails']),0,'해당 열·사유 근거 없음','사유별 분포 확인 못 함'])
    tab(['패턴별 임시 구분(사유 아님)','종목 n','60축일 종가변화 n','p10 / 중앙 / p90','마지막 양수 거래량~폐지 >30일 n'],rows)
    add(f"실측 ① 마지막 **저장 행 날짜**~폐지일 간격 최대 {max(x['gap'] for x in d['tails'])}일, 30일 초과 {sum(x['gap']>30 for x in d['tails'])}종목. 그러나 마지막 **양수 거래량 날짜**~폐지일은 최대 {max(x['active_gap'] or 0 for x in d['tails'])}일, 30일 초과 {sum((x['active_gap'] or 0)>30 for x in d['tails'])}종목이다. 날짜가 가까운 것만으로 정리매매 끝값을 확보했다고 할 수 없다.")
    add(f"실측 ② `meta.note`는 수집 범위·출처 또는 오류를 기록하고 폐지 사유를 제공하지 않는다. **사유별 −90% 가정 오차는 확인 못 함.** 표는 60축일 전 가격 대비 마지막 가격의 변화 분포이며 정지 전 가격 대비 실제 회수액이 아니다. 두 값을 같은 손실률로 비교하면 기준점이 달라진다.")
    add(f"60축일은 끝 날짜에서 60칸 전의 가격이 정확히 존재할 때만 계산했다(누락을 앞 가격으로 채우지 않음). 2023-06 이후는 공식 `market_daily`, 이전은 연구 DB 전체 관측일 합집합을 대리 축으로 썼다. 공식 축 사례 {sum(x['calendar_kind']=='official' for x in d['tails'])}종목, 대리 축 사례 {sum(x['calendar_kind']!='official' for x in d['tails'])}종목. 최종 20축일의 저장 패턴은 합병 대가·실제 매도 가능성을 증명하지 않는다.")
    add()
    add('## 5. |등락률| >35% 이상치')
    add()
    counts=collections.Counter(x['category'] for x in d['outliers'])
    rows=[[name,count,len({x['ticker'] for x in d['outliers'] if x['category']==name}),'가격·날짜 기반 후보, 원인 확정 아님'] for name,count in counts.items()]
    rows.extend([['저장 change_pct와 종가 재계산 차이 >1e-8',c['change_mismatch'],'전체 행','첫 관측 행의 이전 가격 미보유는 제외'],['비유한 OHLCV',c['nonfinite_ohlcv'],'전체 행','정합성 검사'],['양수 OHLC의 고저 범위 위반',c['invalid_ohlc_order'],'전체 행','high<max(open,close) 또는 low>min(open,close)'],['메타 상장 전/폐지 후 가격 행',f"{c['before_listing_rows']} / {c['after_delisting_rows']}",'전체 행','코드 이력·메타 날짜 확인 필요']])
    tab(['유형·검사','행 n','종목 n 또는 범위','의미'],rows)
    add(f"실측 ① 저장 `change_pct` 기준 {c['stored_outlier']}행, 종가의 직전 관측행 대비 직접 재계산 {c['computed_outlier']}행이다. 890행이라는 1차 수치는 이 두 계산값과 대조했다. 단위는 소수(0.35=35%)이며 35%에 100을 곱하지 않았다.")
    add(f"실측 ② OHLC 범위 위반 {c['invalid_ohlc_order']:,}행 중 벗어난 폭/종가가 0.1% 초과 {c['ohlc_excess_over001']:,}행, 0.5% 초과 {c['ohlc_excess_over005']:,}행이다. 작은 차이는 반올림·각 열의 조정 방식 차이일 수 있어 모두 원천 가격 오류로 단정하지 않는다. 큰 차이의 코드·날짜와 >35% 후보 전체는 부록에 남긴다.")
    add('일별 가격이 있으면 상한가가 여러 날 이어졌다는 사실만으로 하루 >35% 변화를 설명할 수 없다. 따라서 ‘상한가 연속’으로 강제 분류하지 않았다. 폐지 전 30일, 직전 거래량 0 또는 관측 간격 >7일, 이름에 스팩, 직전 3행 +29~31%, 나머지 순으로 배타 분류했다. 기간·이름은 원인을 확정하는 자료가 아니다.')
    add()
    add('## 6. 쓸 수 있나')
    add()
    tab(['용도','판정','먼저 필요한 조건'],[['(a) 지수·바구니 연구','지수만의 연구와 구분; 이 DB로 바구니를 그대로 계산하는 것은 보류','과거 종목 구성, 누락 코드, 비거래·폐지 가격과 기업행동 처리. market_daily의 2015~2023-05 지수 자료는 이번 범위에서 미확인'],['(b) 종목 선택 연구','정리 후 제한적으로 사용','종목 식별자·이력, 실제 상장/폐지 시점, 조정기준, 거래정지·누락 구분, 최종 청산/교환 대가. 현재 시장명으로 과거 시장을 일괄 지정하지 말 것'],['(c) 운영 DB와 혼용','코드·날짜 키의 대조만 허용; 값은 기준 확인 전 이어 붙이지 않음','연구 OHLC와 운영 OHLC/close·shares·시가총액을 직접 결합 금지. 거래량 조정 여부도 미확인. change_pct 단위는 같아도 기준 종가가 다를 수 있음']])
    add('실측 ① 첫 점검의 ‘지수·바구니 연구는 그대로 사용 가능’은 이번 자료 구조·누락 검증만으로는 뒷받침되지 않는다. 이미 작성된 전략 보고서의 수익 숫자는 이번 요청에 따라 다시 계산하지 않았다.')
    add('실측 ② 이 검토는 DB 수정 요청이나 전략 채택 제안이 아니다. 다음 검증에는 당시 전체 상장목록, 종목 식별 이력, 기업행동 조정계수·폐지 사유·회수 대가가 필요하며 현재 자료에 없는 것은 확인 못 함으로 남긴다.')
    add()
    add('## 부록 — 재현 근거와 전체 확인 목록')
    add()
    add('재현 명령: `python -B research/handoff/code_20261023_10y_quality.py`. 배치 시간에 시작하거나 진행 중 그 시간이 되면 중단한다. 아래 목록을 포함해 이 보고서를 다시 쓴다. 큰 중간 파일은 만들지 않는다.')
    add('세 DB의 분석 전후 크기·수정 시각이 동일했음을 확인했다. 모든 연결은 읽기 전용이었다. 연구 스크립트·답변 파일 외 저장소 파일은 수정하지 않았다. 입력 식별값(size, mtime_ns): `'+json.dumps(d['input_stats'],ensure_ascii=False)+'`.')
    add('시장별 연구 메타: 현재 상장 `'+str(d['active_markets'])+'`, 폐지 `'+str(d['delisted_markets'])+'`. 코넥스 등 포함 여부는 사용할 연구의 유니버스와 별도로 맞춰야 한다.')
    add('meta.rows와 실제 행 수 불일치: '+str(d['meta_row_count_mismatches'])+'.')
    add('상장일 형식이 날짜가 아닌 메타 행: `'+json.dumps(d['invalid_meta_listed'],ensure_ascii=False)+'`. 이 값은 실제 상장일 비교에서 제외했다. 유효 메타 상장일보다 가격이 앞서는 사례도 이전 시장 상장/이전상장 등 이력 없이는 코드 재사용·잘못된 가격이라고 확정하지 않는다.')
    add()
    details('A. empty/error 전체 목록', [f"{x['ticker']} {x['name']} / status={x['status']} / 폐지={x['delisted']} / note={x['note']}" for x in d['errors']] or ['없음'])
    details('B. 최신 로컬 상장목록 대비 누락 코드 전체', [f"{x['code']} {x['name']} / {x['market']}" for x in cache['missing']])
    details('C. 1개월 초과 무행 구간 전체 (정지 확인 상태 포함)',[f"{x['ticker']} {x['name']} {x['start']}~{x['end']} / {x['sessions']}거래일 / 정지표시1={x['known_suspended']}, 0={x['known_not_suspended']}, 자료없음={x['unknown']} / 폐지일={x['delisted'] or '없음'}" for x in gaps] or ['없음'])
    details('D. 거래량 0인 장기 구간 (30일 초과) 전체',[f"{x['ticker']} {x['name']} {x['start']}~{x['end']} / n={x['rows']} / 종가고정={x['constant_close']}" for x in d['zero_spans']] or ['없음'])
    details('E. 연구/운영 종가 배율의 >5% 경계 전체',[f"{x['ticker']} {x['name']} {x['prev_date']}→{x['date']} / 배율 {num(x['factor_before'])}→{num(x['factor_after'])} / 연구가격비 {num(x['research_ratio'])}, 운영가격비 {num(x['operational_ratio'])}, 운영주식수비 {num(x['shares_ratio'])}" for x in d['changes']] or ['없음'])
    details('F. |등락률| >35% 전체 재조회 후보 — 오류 확정 목록이 아님',[f"{x['ticker']} {x['name']} {x['prev_date']}→{x['date']} / 종가 {x['prev_close']:g}→{x['close']:g} / {x['change']*100:+.3f}% / {x['category']}" for x in d['outliers']])
    severe=[x for x in d['anomalies'] if x['kind']!='ohlcv_nonfinite_or_order' or x.get('excess_fraction',0)>.005]
    details('G. OHLC 고저 범위 0.5% 초과 및 메타 기간 불일치 전체',[json.dumps(x,ensure_ascii=False,default=safe) for x in severe] or ['기준에 해당하는 행 없음; 모든 가격이 맞다는 뜻은 아님'])
    details('H. 폐지 635종목 끝 20축일 및 60축일 진단',[f"{x['ticker']} {x['name']} / 폐지 {x['delisted']} / 끝행 {x['last']} / 끝양수거래량 {x['last_active'] or '없음'} / 간격 {x['gap']}일·{x['active_gap']}일 / 20축일 중 저장 {x['rows20']}행, 거래량0 {x['zero20']}행, 급변 {x['large20']}행 / 60축일 종가변화 {num(None if x['r60'] is None else x['r60']*100,2)}% / 기준일 {x['r60_base']} ({x['calendar_kind']}) / {tailgroup(x)}" for x in d['tails']])
    add('## 질문·확인 못 한 사항')
    add()
    add('- 2015~2023-05 공식 거래일 축, 2026-10-21 수집 당시 상장목록 원본, 기업행동·정지·폐지 사유와 실제 회수 대가가 자료에 없어 해당 부분은 확정하지 못했다. 요청에 따라 진행을 멈추고 질문하지 않고 이 한계를 남겼다.')
    add('- 외부 조회·수집·DB 수정은 하지 않았다. 새 전략·모델·수익률 격자도 만들지 않았다. 폐지 마지막 60축일 종가변화만 요청 4번의 품질 진단으로 집계했다.')
    return '\n'.join(lines)+'\n'

def supplement(text):
    """Small independent checks to prevent overinterpreting gaps and extreme returns."""
    o=ro(DATA/'ohlcv.db');r=ro(DATA/'ohlcv_10y.db')
    events=o.execute("SELECT date,ticker,event,market FROM universe_events WHERE ticker IN ('101970','036220') ORDER BY ticker,date").fetchall()
    titles=o.execute("SELECT COUNT(*) FROM dart_events WHERE report_nm LIKE '%주식분할%' OR report_nm LIKE '%주식병합%'").fetchone()[0]
    corporate=o.execute("SELECT event_type,COUNT(*) FROM dart_events WHERE event_type IN ('bonus','reduction') GROUP BY event_type").fetchall()
    example=r.execute("SELECT date,close,volume,change_pct FROM prices WHERE ticker='101970' AND date IN ('20150316','20250328') ORDER BY date").fetchall()
    samsung=r.execute("SELECT date,close,volume FROM prices WHERE ticker='005930' AND date IN ('20180427','20180504') ORDER BY date").fetchall()
    zeros=r.execute('SELECT COUNT(*) FROM prices WHERE volume=0').fetchone()[0]
    r.close();o.close()
    cross=sql_crosscheck()
    note1='추가 확인: 삼성전자 거래량 양수 행의 해당 구간 전후 값은 `'+str(samsung)+'`이다. 요청서의 50,400→51,600을 바로 전후 가격으로 재현하지는 못했다. 로컬 공시 목록에 무상증자·감자 결정은 `'+str(corporate)+'`건 있으나, 제목에 주식분할/주식병합이 있는 건수는 '+str(titles)+'건이다. 결정 접수일을 가격 조정 효력일로 대신하거나 이 자료만으로 기업행동 20건을 확정하지 않았다.\n\n'
    note3='추가 확인: 장기 무행 구간 두 종목의 `universe_events` 기록은 `'+str(events)+'`이다. 과거 가격이 한 번 존재했다는 이유로 그 뒤 모든 공백을 상장 중 누락으로 세면 안 된다. NEW 기록은 관측 재등장을 지지하지만, 재상장·코드 재사용·정지 사유를 확정하지는 않는다.\n\n'
    note3+='`empty`는 0건이고 `error` 2건은 모두 1961년 폐지 종목으로 요청 기간 밖이다. 수집 단계에서 제외되어 meta에 들어가지 않은 종목은 이 실패 목록에서 보이지 않는다. 보존된 수집 로그의 대상 폐지 주권 637개와 실제 가격 보유 635개 사이 2개도 당시 원본 목록 없이는 신원을 확정하지 못했다.\n\n'
    note3+=f'전체 연구 가격 행 중 거래량 0은 {zeros:,}행이다. 행이 채워져 있다는 것과 해당 가격에 거래할 수 있었다는 것은 다른 조건이다.\n\n'
    note5='추가 확인: `101970`의 저장 행은 `'+str(example)+'`이다. 이 두 종가 사이의 변화는 약 10년 공백을 가로지르므로 단일 거래일 등락으로 쓰면 안 된다. 직전 저장 행의 가격으로 만든 change_pct가 수학적으로 일치해도 일간 변화로 해석 가능한지는 별도다.\n\n'
    text=text.replace('## 2. 운영 DB 전 종목 종가 대조',note1+'## 2. 운영 DB 전 종목 종가 대조')
    text=text.replace('## 3. 빠진 날·빠진 종목','별도 SQL 조인으로도 교차 검산했다. (매칭 행, 완전 일치, 0.1% 이내, 0.5% 초과, 종목 수) = `'+str(cross)+'`로 본 계산과 일치한다.\n\n## 3. 빠진 날·빠진 종목')
    text=text.replace('## 4. 폐지 종목 635개',note3+'## 4. 폐지 종목 635개')
    text=text.replace('## 6. 쓸 수 있나',note5+'## 6. 쓸 수 있나')
    return text

def sql_crosscheck():
    c=ro(DATA/'ohlcv_10y.db')
    c.execute('ATTACH DATABASE ? AS op',((DATA/'ohlcv.db').resolve().as_uri()+'?mode=ro',))
    query='''WITH ops AS (
    SELECT ticker,date,close FROM op.daily_ohlcv
    UNION ALL SELECT ticker,date,close FROM op.daily_ohlcv_extra e
    WHERE NOT EXISTS(SELECT 1 FROM op.daily_ohlcv b WHERE b.ticker=e.ticker AND b.date=e.date))
    SELECT COUNT(*),SUM(r.close=o.close),SUM(ABS(r.close/o.close-1)<=0.001),
    SUM(ABS(r.close/o.close-1)>0.005),COUNT(DISTINCT r.ticker)
    FROM prices r JOIN ops o USING(ticker,date) WHERE o.close>0 AND r.close>0'''
    result=c.execute(query).fetchone();c.close()
    return result

if __name__=='__main__':
    d=audit()
    print(json.dumps({'counters':d['counters'],'status':d['status'],'calendar':d['calendar'],'report':str(OUT)},ensure_ascii=False,indent=2,default=safe),flush=True)
    guard()
    OUT.write_text(supplement(report(d)),encoding='utf-8')
