"""Offline freshness audit. Only this script and its REPLY are retained.
No collector imports, network requests, performance calculations or database writes.
python -B research/handoff/code_20261010_stale_data_audit.py
"""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import Counter,defaultdict
from statistics import median
import sqlite3,re,os,json
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).with_name('REPLY_20261010_stale_data_audit.md')
END='20261008'
TZ=timezone(timedelta(hours=9))
DBS={'history':ROOT/'history.db','ohlcv':ROOT.parent/'dh-q7m3k-data/ohlcv.db','earnings':ROOT.parent/'dh-q7m3k-data/earnings.db'}
SECTIONS=[]


def guard():
    t=datetime.now(TZ)
    skipped={s.strip() for s in (ROOT/'skip_dates.txt').read_text(encoding='utf-8').splitlines()}
    if t.weekday()<5 and '20:10'<=t.strftime('%H:%M')<'22:30' and t.strftime('%Y%m%d') not in skipped:
        raise SystemExit('KST batch window. Partial REPLY retained.')
    return t.isoformat(timespec='seconds')


def qi(s):return '"'+s.replace('"','""')+'"'
def ro(path):return sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
def dex(c):return "substr(replace(replace(CAST("+qi(c)+" AS TEXT),'-',''),'/',''),1,8)"
def date8(v):
    if v is None:return None
    s=str(v).replace('-','').replace('/','')[:8]
    try:return s if len(s)==8 and datetime.strptime(s,'%Y%m%d') else None
    except ValueError:return None
def table(h,rows):
    def fmt(x):return str(x).replace('|','/').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(h)+' |','|'+'|'.join(['---']*len(h))+'|']+['| '+' | '.join(fmt(v) for v in r)+' |' for r in rows])
def save(title,body):
    guard();SECTIONS.append('## '+title+'\n\n'+body);OUT.write_text('\n\n'.join(SECTIONS)+'\n',encoding='utf-8')
    print('SAVED',title,flush=True)
def ranges(ds,cal):
    ds=sorted(set(ds));out=[]
    for d in ds:
        if out and cal.index(d)==cal.index(out[-1][-1])+1:out[-1].append(d)
        else:out.append([d])
    return ', '.join(x[0] if len(x)==1 else x[0]+'~'+x[-1]+f'(n={len(x)}일)' for x in out) or '없음'


def read_sources():
    # Source code only. Cache/data contents and secrets are never read.
    paths=list(ROOT.glob('*.py'))+list((ROOT/'scripts').glob('*.py'))
    out={}
    for p in sorted(paths):out[str(p.relative_to(ROOT))]=p.read_text(encoding='utf-8',errors='replace').splitlines()
    return out


def consumers(t,sources):
    hit=[]
    for f,lines in sources.items():
        if f.startswith('test'):continue
        for n,line in enumerate(lines,1):
            if re.search(r'\b'+re.escape(t)+r'\b',line):
                priority=0 if re.search(r'\b(FROM|JOIN)\s+'+re.escape(t)+r'\b',line,re.I) else 1
                hit.append((priority,f,n));break
    return ', '.join(f'{f}:{n}' for _,f,n in sorted(hit)[:3]) or '확인 못 함'


DATE_COLS={'date','run_id','run_timestamp','frozen_at','fetched_at','rcept_dt','px_dt','at_date','stage3_src_run'}
PERIOD_COLS={'year','annual_year','q_period'}
BRANCH_COLS={'series','market','model_id','source','event_type','event','reason','fs','reprt','insider_source','buyback_src'}


def inventory(conns,cal,sources):
    metas=[];rows=[];nodate=[]
    for db,c in conns.items():
        for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            guard(); cols=[x[1] for x in c.execute('PRAGMA table_info('+qi(t)+')')]
            ds=[x for x in cols if x in DATE_COLS or x.endswith('_date') or x.endswith('_timestamp')]
            periods=[x for x in cols if x in PERIOD_COLS]
            n=c.execute('SELECT COUNT(*) FROM '+qi(t)).fetchone()[0]
            primary=next((x for x in ('date','run_id','rcept_dt','at_date','fetched_at') if x in ds),None)
            values=[]
            for col in ds:
                mx,nn=c.execute('SELECT MAX('+qi(col)+'),COUNT('+qi(col)+') FROM '+qi(t)).fetchone()
                d=date8(mx);lag=sum(x>d for x in cal) if d else '확인 못 함'
                values.append(f'{col}: {mx if mx is not None else "NULL"} / 뒤처짐 {lag}거래일 / 유효 n={nn}')
            for col in periods:
                mx=c.execute('SELECT MAX('+qi(col)+') FROM '+qi(t)).fetchone()[0]
                values.append(f'{col}: {mx} (연도·보고기간 문자열MAX; 거래일 지연과 구분)')
            if db=='earnings' and t=='earnings_meta':
                v=c.execute("SELECT value FROM earnings_meta WHERE key='last_end'").fetchone()
                values.append('날짜 없음; value(last_end)='+str(v[0] if v else '없음'))
            meta=dict(db=db,t=t,cols=cols,ds=ds,n=n,primary=primary,consumer=consumers(t,sources))
            metas.append(meta)
            row=[db+'.'+t,f'n={n:,}', '; '.join(values) or '날짜 없음',meta['consumer']]
            (rows if ds else nodate).append(row)
    save('1. 모든 표의 재고와 마지막 날짜',
         '날짜·조회/저장 시각·보고기간을 구분했다. 뒤처짐은 해당 날짜 뒤부터 기준일 '+END+'까지의 DB 거래일 수다. 최신 fetched_at이 과거 date의 최신성을 보장하지 않는다. rcept_no는 접수 식별자이며 날짜 열로 세지 않았다. 표 이름을 운영 Python 코드에서 찾아 소비/저장 파일 최대 n=3개를 적었다.\n\n'+
         table(['표','행 수','날짜 열 전부: 마지막 값 / 지연 / 비NULL 수','사용 파일(줄)'],rows)+'\n\n### 날짜 열이 없는 표\n\n'+table(['표','행 수','상태','사용 파일(줄)'],nodate))
    return metas


def branches(conns,metas,cal):
    rows=[];records=[]
    for m in metas:
        guard();c=conns[m['db']];t=m['t'];ds=m['ds'];cols=m['cols']
        bs=[x for x in cols if x in BRANCH_COLS]
        groups=[[x] for x in bs]
        if 'market' in bs:
            groups += [['market',x] for x in ('model_id','event_type','source') if x in bs]
        for group in groups:
            sql='SELECT '+','.join(qi(x) for x in group)+',COUNT(*)'+''.join(',MAX('+qi(x)+')' for x in ds)+' FROM '+qi(t)+' GROUP BY '+','.join(qi(x) for x in group)
            for r in c.execute(sql):
                label=', '.join(f'{k}={v if v is not None else "NULL"}' for k,v in zip(group,r[:len(group)]))
                vals=r[len(group)+1:]; details=[]
                for col,v in zip(ds,vals):
                    d=date8(v); lag=sum(x>d for x in cal) if d else None
                    details.append(f'{col}={v} (뒤처짐 {lag if lag is not None else "확인 못 함"})')
                rows.append([m['db']+'.'+t,label,f'n={r[len(group)]:,}','; '.join(details) or '날짜 없음'])
                rec=dict(db=m['db'],t=t,group=group,label=label,n=r[len(group)],dates=dict(zip(ds,vals)))
                records.append(rec)
    save('2. 표 안 갈래별 마지막 날짜',
         '개별 구분 열과 market×model_id / market×event_type 조합을 모두 확인했다. NULL 갈래도 포함. 공시·분기·주간·은퇴 모델은 마지막 날짜가 오래되어도 수집 정지로 바로 판정하지 않는다.\n\n'+table(['표','갈래','행 수','날짜 열별 마지막 값(지연은 거래일)'],rows))
    return records


def market_map(conns):
    o=conns['ohlcv'];mp={};caps={};names={}
    for t in ('daily_ohlcv_extra','daily_ohlcv'):
        for tk,mk,px,sh in o.execute('SELECT ticker,market,close,shares FROM '+qi(t)+' WHERE date=?',(END,)):
            mp[tk]=str(mk).lower();caps[tk]=(px or 0)*(sh or 0)
    h=conns['history']
    for t in ('stage1_oversold','large_universe'):
        for tk,nm,mk in h.execute('SELECT ticker,name,market FROM '+qi(t)+' ORDER BY run_id'):
            names[tk]=nm
            if tk not in mp:mp[tk]=str(mk).lower()
    return mp,caps,names


def daily_counts(conns,metas,cal,mp):
    days=cal[-60:];base=cal[-80:]; anomalies=[];summary=[];snap={}
    for m in metas:
        guard();col=m['primary'];t=m['t'];c=conns[m['db']]
        if not col:continue
        de=dex(col);ticker='ticker' in m['cols'];own_market='market' in m['cols'];series='series' in m['cols']
        selected=de+' AS d,'+('LOWER(market)' if own_market else (qi('ticker') if ticker else 'LOWER(series)' if series else "'전체'"))+',COUNT(*),'+('COUNT(DISTINCT ticker)' if ticker else '0')
        rs=c.execute('SELECT '+selected+' FROM '+qi(t)+' WHERE '+de+'>=? AND '+de+'<=? GROUP BY 1,2',(base[0],END)).fetchall()
        buckets=defaultdict(lambda:defaultdict(lambda:[0,0]))
        for d,g,n,nt in rs:
            market=g if own_market or series else mp.get(g,'확인 못 함') if ticker else '전체'
            for domain in set(['전체',market]):
                z=buckets[domain][d];z[0]+=n;z[1]+=nt
        # Tables with market memberships get explicit zero domains too.
        if own_market or ticker or series:
            for domain in ('kospi','kosdaq'):buckets[domain]
        buckets['전체']
        minv=c.execute('SELECT MIN('+de+') FROM '+qi(t)).fetchone()[0]
        for domain,byday in sorted(buckets.items()):
            vals=[byday.get(d,[0,0]) for d in base]; zero=[];drops=[]
            for d in days:
                i=base.index(d); n,nt=vals[i]; prior=vals[max(0,i-20):i]
                medn=median(x[0] for x in prior) if len(prior)==20 else None
                medt=median(x[1] for x in prior) if len(prior)==20 else None
                cold=bool(minv and d<minv)
                if n==0:zero.append(d)
                low=(medn is not None and medn>0 and n<.7*medn) or (medt is not None and medt>0 and nt<.7*medt)
                if low:
                    known='알려진 사건일(09/08 상장목록 실패; 이 행의 원인 별도 확인 필요)' if d=='20260908' else '확인 필요'
                    if t in ('stage2_filtered','stage3_final','lowvol_scores','v3_scores','wu_scores'):known+='; 후보 수·신규/은퇴 영향 구분 필요'
                    if t in ('dart_events','universe_events','ohlcv_skips','earnings_q','earnings_raw','consensus_daily','lead_picks','lead_universe'):known+='; 비일별·사건/주기 자료'
                    anomalies.append([m['db']+'.'+t,domain,d,f'n={n}',f'n={nt}' if ticker else '종목 열 없음',f'{medn:g}',f'{medt:g}' if ticker else '해당 없음',known])
                    drops.append(d)
            summary.append([m['db']+'.'+t,col,domain,f'n={sum(vals[base.index(d)][0]>0 for d in days)}/60일',ranges(zero,cal),f'n={len(drops)}일'])
            snap[(m['db'],t,domain)]={d:byday.get(d,[0,0]) for d in days}
        print('COUNTS',m['db'],t,flush=True)
    save('3. 최근 n=60거래일 날짜별 행·종목 수 급감',
         '최근 n=80거래일을 읽어 각 날짜 직전 n=20일 중앙값을 만들었다. 현재 행 수 또는 종목 수가 중앙값의 70% 미만이면 아래에 적었다(0 포함). 집계는 날짜별 모든 run 합계이며 같은 날짜 재실행은 행 수에 중복될 수 있다. 종목 수는 시장 안에서 중복 제거. 종목이 없는 표에는 종목 수를 적용하지 않았다. 등록 전·월별·주간·공시 자료의 0은 정상일 수 있다.\n\n'+
         table(['표','기준 날짜 열','시장','비어 있지 않은 날','0인 날짜(연속 거래일 묶음)','70% 미만'],summary)+'\n\n### 70% 미만 날짜 전부\n\n'+
         table(['표','시장','날짜','행','종목','직전20일 행 중앙값','종목 중앙값','해석'],anomalies))
    return snap,anomalies


def constants(conns,metas,cal,mp):
    rows=[];out=[];coverage=[];days=cal[-10:]
    identity={'ticker','series','name','corp_name','market','model_id','spec_hash','rcept_no','key'}
    priority=re.compile(r'foreign|inst|person|pension|trust|secfirm|prveq|insu|bank|supply|short|credit|loan|shares|stocks|marcap|mcap',re.I)
    for m in metas:
        guard();date=m['primary'];t=m['t']
        entitycol=next((x for x in ('ticker','series','market') if x in m['cols']),None)
        if not date or not entitycol:continue
        values=[x for x in m['cols'] if x not in identity|set(m['ds'])]
        df=pd.read_sql_query('SELECT * FROM '+qi(t)+' WHERE '+dex(date)+'>=? AND '+dex(date)+'<=?',conns[m['db']],params=(days[0],END))
        if df.empty:
            coverage.append([m['db']+'.'+t,'관측 n=0; 10일 값 비교 불가']);continue
        df['_d']=df[date].map(date8);df=df[df._d.isin(days)]
        if 'market' not in df:df['market']=df.ticker.map(mp).fillna('확인 못 함') if 'ticker' in df else '전체'
        groups=[('전체',df)]+[(str(k),v) for k,v in df.groupby('market',dropna=False)]
        if entitycol=='series':groups += [('series='+str(k),v) for k,v in df.groupby('series',dropna=False)]
        if 'model_id' in df:
            groups += [(f'model_id={mid}; market={mk}',sub) for (mid,mk),sub in df.groupby(['model_id','market'],dropna=False)]
        for domain,sub in groups:
            entity=[entitycol]+(['model_id'] if 'model_id' in sub else [])
            by=sub.groupby(entity,dropna=False)
            eligible=by['_d'].nunique(); eligible=eligible[eligible==10].index
            unique=by[values].nunique(dropna=False)
            unique=unique.loc[eligible] if len(eligible) else unique.iloc[:0]
            for col in values:
                series=sub[col];null=series.isna().all();valid=series.dropna()
                zero=len(valid)>0 and pd.to_numeric(valid,errors='coerce').eq(0).all()
                nconst=int((unique[col]<=1).sum()) if len(unique) else 0
                frozen=len(unique)>0 and nconst/len(unique)>=.9
                if null or zero or frozen:
                    status='전부 NULL' if null else '비NULL 값 전부 0' if zero else '10일 불변≥90%'
                    row=[m['db']+'.'+t,domain,col,status,f'n={len(sub)}행',f'n={nconst}/{len(unique)}',f'{nconst/len(unique):.1%}' if len(unique) else '완전10일 표본 없음','우선 확인' if priority.search(col) else '정상 상수/선택 필드 가능']
                    rows.append(row);out.append(dict(db=m['db'],t=t,domain=domain,col=col,status=status,n=len(sub),constant=nconst,eligible=len(unique),priority=bool(priority.search(col))))
                today=sub[sub._d==END][col]
                if len(today):
                    tn=today.isna().all();tv=today.dropna()
                    tz=len(tv)>0 and pd.to_numeric(tv,errors='coerce').eq(0).all()
                    if (tn and not null) or (tz and not zero):
                        status='기준일 전부 NULL' if tn else '기준일 비NULL 값 전부 0'
                        rows.append([m['db']+'.'+t,domain,col,status,f'n={len(today)}행','당일 검사','해당 없음','우선 확인' if priority.search(col) else '선택 필드/상태 가능'])
                        out.append(dict(db=m['db'],t=t,domain=domain,col=col,status=status,n=len(today),constant=0,eligible=0,priority=bool(priority.search(col))))
        coverage.append([m['db']+'.'+t,f'n={len(df)}행 / 관측일 n={df._d.nunique()}/10 / {entitycol} n={df[entitycol].nunique()}'])
        print('VALUES',m['db'],t,flush=True)
    rows.sort(key=lambda r:(r[-1]!='우선 확인',r[0],r[1],r[2]))
    save('4. 최근 n=10거래일 값이 안 바뀐 열·전부 0/NULL',
         '10거래일 모두 등장한 종목(모델 표는 종목×model_id)만 불변 비율 분모에 넣었다. 같은 날짜 재실행 값이 서로 다르면 불변이 아니다. NULL만 있는 열, 비NULL 값이 모두 0인 열은 별도 표시한다(혼합 NULL 수도 유의). 최근10일 전체가 아니어도 기준일만 전부 NULL/0인 열을 추가했다. ticker가 없는 표는 series/market별 반복 관측도 확인했다. 이 조건만으로 복사를 확정하지 않는다. 주식수·보고기간·재무 스냅샷·불변 분류·가중 0 관측/비활성 필드는 정상일 수 있다. 점수·수익·순위 상관 등 성과 통계는 계산하지 않았으며 실제 값 대신 불변/결손 여부만 집계했다.\n\n'+table(['표','검사 표본'],coverage)+'\n\n'+table(['표','갈래','열','검출','행 수','불변/완전10일 종목','불변 비율','분류'],rows))
    return out


def holes(conns,cal,mp,caps,names):
    c=conns['ohlcv'];start=cal[-20];summary=[];details=[];records=[]
    def tickers(t,one=False):
        sql='SELECT DISTINCT ticker FROM '+qi(t)+' WHERE date'+('=?' if one else '>=? AND date<=?')
        return {r[0] for r in c.execute(sql,(END,) if one else (start,END))}
    for one in (False,True):
        base=tickers('daily_ohlcv',one)
        for t in ('daily_flows','short_flows','daily_ohlcv_extra','valuation_daily','consensus_daily'):
            other=tickers(t,one)
            for label,missing in [('본 표만',base-other),('비교 표만',other-base)]:
                summary.append(['최근20일 합집합' if not one else END,t,label,f'n={len(missing)}',f'kospi n={sum(mp.get(x)=="kospi" for x in missing)} / kosdaq n={sum(mp.get(x)=="kosdaq" for x in missing)} / 확인 못 함 n={sum(mp.get(x) not in ("kospi","kosdaq") for x in missing)}'])
                top=sorted(missing,key=lambda x:(-caps.get(x,-1),x))[:10]
                for tk in top:details.append(['최근20일' if not one else END,t,label,tk,names.get(tk) or '확인 못 함',mp.get(tk,'확인 못 함'),f'{caps[tk]/1e8:.2f}' if tk in caps else '확인 못 함'])
                records.append(dict(one=one,t=t,direction=label,n=len(missing),tickers=missing))
    h=conns['history'];rid=h.execute('SELECT MAX(run_id) FROM large_universe').fetchone()[0]
    expected={x[0] for x in h.execute('SELECT DISTINCT ticker FROM large_universe WHERE run_id=?',(rid,))}
    relevant=[]
    for t in ('daily_flows','short_flows'):
        missing=expected-tickers(t,True)
        relevant.append([t,str(rid),f'n={len(expected)}',f'n={len(missing)}',', '.join(sorted(missing,key=lambda x:(-caps.get(x,-1),x))[:10]) or '없음'])
    save('5. 종목 단위 구멍과 반대 방향',
         '최근 n=20거래일 합집합과 기준일 하루를 따로 비교했다. 시총은 기준일 DB 종가×주식수(본 표 우선·보충표 다음); 없는 종목은 확인 못 함이며 이름은 history.db에서만 가져왔다. 캐시 내용은 읽지 않았다. daily_flows/short_flows는 전 상장사가 아니라 대상 유니버스를 받으며, extra는 본 표 밖 종목의 보충표다. 따라서 단순 차집합 전체를 오류로 판정하지 않는다.\n\n'+table(['기간','비교 표','방향','종목 수','시장별'],summary)+'\n\n### 각 방향 시총 상위 최대 n=10종목\n\n'+table(['기간','표','방향','종목','이름','시장','시총 억원'],details)+'\n\n### 현재 large_universe 대비 기준일 누락\n\n'+table(['표','기대 유니버스 run','대상','기준일 없음','상위10 코드'],relevant))
    return records,relevant


def caches(cal):
    files=[];folders=Counter();excluded=0;old=[]
    oldlimit=cal[-20]
    for base,dirs,names in os.walk(ROOT):
        dirs[:]=[d for d in dirs if d not in {'.git','node_modules','.venv','venv','__pycache__'}]
        p=Path(base);cache=any('cache' in x.lower() for x in p.relative_to(ROOT).parts)
        for name in names:
            if re.search(r'(^\.env)|token|credential|secret|password',name,re.I):excluded+=1;continue
            f=p/name
            if not cache and not ('cache' in name.lower() and f.suffix.lower() not in {'.py','.md','.bat'}):continue
            s=f.stat();dt=datetime.fromtimestamp(s.st_mtime,TZ);d=dt.strftime('%Y%m%d')
            rel=str(f.relative_to(ROOT));row=[rel,f'n={s.st_size:,} bytes',dt.isoformat(timespec='seconds')]
            files.append(row);folders[str(p.relative_to(ROOT))]+=1
            if d<oldlimit:old.append(row)
    # listing_cache is intentionally outside the repository; metadata only.
    listing=ROOT.parent/'dh-q7m3k-data/listing_cache.json'
    lrows=[]
    if listing.exists():
        s=listing.stat();dt=datetime.fromtimestamp(s.st_mtime,TZ)
        lrows.append([str(listing),f'n={s.st_size:,} bytes',dt.isoformat(timespec='seconds')])
    else:lrows.append([str(listing),'없음','확인 못 함'])
    newest=sorted(files,key=lambda x:x[2],reverse=True)[:20]
    save('6. 캐시·파일 수정 시각(내용 미열람)',
         f'파일 메타데이터만 읽었다. 오래됨은 최근 n=20거래일 시작 {oldlimit}보다 수정일이 이른 경우이며, 이 기준은 감사용 후보 추출이지 운영 실패 판정이 아니다. 캐시 파일 n={len(files):,}, 오래된 파일 n={len(old):,}. 비밀 이름 파일은 제외했다. pycache/venv/node_modules/.git은 데이터 캐시가 아니므로 제외. 역사 연구 캐시는 고정 보관이 정상일 수 있고, mtime만으로 원자료 기준일은 **확인 못 함**.\n\n'+table(['폴더','파일 수'],[[k,f'n={v:,}'] for k,v in sorted(folders.items())])+'\n\n### listing_cache 파일\n\n'+table(['이름','크기','수정 시각 KST'],lrows)+'\n\n### 최근 수정 파일 최대 n=20개\n\n'+table(['이름','크기','수정 시각 KST'],newest)+'\n\n### 오래된 파일 전부(이름·크기·수정 시각만)\n\n'+table(['이름','크기','수정 시각 KST'],old))
    return dict(n=len(files),old=len(old),listing=lrows)


def focus(conns,cal,mp,caps,names):
    """Cross-table cohorts catch stale branches without a physical source column."""
    o,h=conns['ohlcv'],conns['history'];st20=cal[-20];st60=cal[-60]
    main={r[0] for r in o.execute('SELECT ticker FROM daily_ohlcv WHERE date=?',(END,))}
    active={r[0] for r in o.execute('SELECT ticker FROM daily_ohlcv WHERE date=? AND is_suspended=0',(END,))}
    extra={r[0] for r in o.execute('SELECT ticker FROM daily_ohlcv_extra WHERE date=?',(END,))}
    extra_active={r[0] for r in o.execute('SELECT ticker FROM daily_ohlcv_extra WHERE date=? AND is_suspended=0',(END,))}
    cohorts={'본 표 활발':active,'본 표 정지':main-active,'보충표 전체':extra,'보충표 활발':extra_active}
    rows=[];latest={};extra_detail=[];cohort_summary=[];cohort_dips=[];missing_active={}
    for tab in ('daily_flows','short_flows'):
        latest[tab]={t:(d,at) for t,d,at in o.execute('SELECT ticker,MAX(date),MAX(fetched_at) FROM '+qi(tab)+' GROUP BY ticker')}
        for label,tks in cohorts.items():
            hist=Counter(latest[tab].get(t,(None,None))[0] for t in tks)
            rows.append([tab,label,f'n={len(tks)}', '; '.join(f'{d or "자료 없음"}: n={n} (뒤처짐 {sum(x>d for x in cal) if d else "확인 못 함"})' for d,n in sorted(hist.items(),key=lambda x:str(x[0])))])
        for tk in sorted(extra):
            d,at=latest[tab].get(tk,(None,None))
            extra_detail.append([tab,tk,names.get(tk) or '확인 못 함',mp.get(tk,'확인 못 함'),d or '없음',sum(x>d for x in cal) if d else '확인 못 함',at or '없음'])
        perday=defaultdict(set)
        for d,t in o.execute('SELECT date,ticker FROM '+qi(tab)+' WHERE date>=? AND date<=?',(cal[-80],END)):
            perday[d].add(t)
        for label,tks in cohorts.items():
            nums={d:len(perday[d]&tks) for d in cal[-80:]};zero=[d for d in cal[-60:] if not nums[d]];drops=[]
            for d in cal[-60:]:
                i=cal.index(d);before=[nums[x] for x in cal[i-20:i] if x in nums]
                if len(before)==20 and median(before)>0 and nums[d]<.7*median(before):
                    drops.append(d);cohort_dips.append([tab,label,d,f'n={nums[d]}',f'{median(before):g}'])
            cohort_summary.append([tab,label,f'n={nums[END]}',f'n={len(zero)}일: '+ranges(zero,cal),f'n={len(drops)}일'])
        missing_active[tab]=active-{t for t,(d,_) in latest[tab].items() if d==END}
    rid=h.execute('SELECT MAX(run_id) FROM large_universe').fetchone()[0]
    large={r[0] for r in h.execute('SELECT ticker FROM large_universe WHERE run_id=?',(rid,))}
    top=[]
    for tab in ('daily_flows','short_flows'):
        miss={t for t in large if latest[tab].get(t,(None,None))[0]!=END}
        for tk in sorted(miss,key=lambda x:(-caps.get(x,-1),x))[:10]:
            d=latest[tab].get(tk,(None,None))[0]
            top.append([tab,tk,names.get(tk) or '확인 못 함',mp.get(tk,'확인 못 함'),f'{caps[tk]/1e8:.2f}' if tk in caps else '확인 못 함',d or '없음',sum(x>d for x in cal) if d else '확인 못 함','보충표' if tk in extra else '본 표'])
    nonnull=[]
    for tab in ('daily_flows','short_flows'):
        cols=[x[1] for x in o.execute('PRAGMA table_info('+qi(tab)+')') if x[1] not in {'ticker','date','fetched_at'}]
        sql='SELECT '+','.join('MAX(CASE WHEN '+qi(v)+' IS NOT NULL THEN date END)' for v in cols)+' FROM '+qi(tab)
        mx=o.execute(sql).fetchone()
        for col,d in zip(cols,mx):nonnull.append([tab,col,d or '없음',sum(x>d for x in cal) if d else '확인 못 함'])
    source_dist=h.execute('SELECT stage3_src_run,COUNT(*) FROM large_final WHERE run_id=? GROUP BY stage3_src_run ORDER BY stage3_src_run DESC',(rid,)).fetchall()
    srcfresh=sum(n for d,n in source_dist if d==rid);srcold=sum(n for d,n in source_dist if d and d<rid);srcnull=sum(n for d,n in source_dist if not d)
    oldmax=max(sum(x>d for x in cal) for d,n in source_dist if d)
    known=h.execute("SELECT market,COUNT(*),SUM(CASE WHEN supply_fetched IN (1,'1','True','true') THEN 1 ELSE 0 END),MIN(run_timestamp),MAX(run_timestamp) FROM stage3_final WHERE run_id='20260911' GROUP BY market").fetchall()
    frozen=h.execute("SELECT model_id,COUNT(*),MIN(frozen_at),MAX(frozen_at) FROM v3_scores WHERE run_id='20260911' GROUP BY model_id").fetchall()
    credit_daily=o.execute('SELECT date,COUNT(*),COUNT(credit_bal_qty),COUNT(credit_bal_amt),COUNT(credit_bal_rate) FROM short_flows WHERE date>=? AND date<=? GROUP BY date ORDER BY date',(cal[-10],END)).fetchall()
    credit_last=o.execute('SELECT MAX(date) FROM short_flows WHERE credit_bal_rate IS NOT NULL').fetchone()[0]
    credit_lag=sum(x>credit_last for x in cal)
    series_gaps=[]
    for (series,) in o.execute('SELECT DISTINCT series FROM market_daily ORDER BY series'):
        ds={r[0] for r in o.execute('SELECT date FROM market_daily WHERE series=? AND date>=? AND date<=?',(series,st60,END))}
        miss=sorted(set(cal[-60:])-ds)
        series_gaps.append([series,f'n={len(miss)}',', '.join(miss) or '없음'])
    input_rows=[];input_counts={};input_detail=[]
    marks=','.join('?' for _ in extra)
    for tab in ('stage1_oversold','stage3_final'):
        got=h.execute('SELECT ticker,supply_fetched FROM '+qi(tab)+' WHERE run_id=? AND ticker IN ('+marks+')',(END,*sorted(extra))).fetchall()
        ok=sum(str(v).lower() in {'1','true'} for tk,v in got)
        input_rows.append([tab,f'n={len(got)}',f'n={ok}']);input_counts[tab]=(len(got),ok)
        for tk,flag in got:
            d=latest['daily_flows'].get(tk,(None,None))[0]
            nd=o.execute('SELECT COUNT(DISTINCT date) FROM daily_flows WHERE ticker=? AND date>=? AND date<=?',(tk,st20,END)).fetchone()[0]
            if tab=='stage3_final':input_detail.append([tk,names.get(tk) or '확인 못 함',flag,d or '없음',f'n={nd}/20'])
    save('2·3·5 추가. 본 표/보충표 갈래와 원자료 시각(핵심)',
         '물리적인 market/source 열만으로 못 잡는 경우라 현재 시세 표의 종목 집합을 갈래로 추가했다. 최근 n=60일도 이 현재 집합으로 비교했으므로 과거 상장·편입 변화의 영향을 포함한다. 이 집계는 성과 검증이 아니다.\n\n'+
         table(['표','현재 종목 갈래','대상','종목별 마지막 날짜 분포'],rows)+'\n\n'+
         table(['표','갈래','기준일 종목 수','최근60일 0인 날','70% 미만 날'],cohort_summary)+'\n\n'+
         table(['표','갈래','70% 미만 날짜','종목 수','직전20일 중앙값'],cohort_dips)+'\n\n### 보충표 종목 전부의 마지막 날짜\n\n'+
         table(['표','종목','이름','시장','마지막 원자료일','뒤처짐 거래일','마지막 수신 시각'],extra_detail)+'\n\n### 현재 대형 유니버스에서 자료가 빠진 시총 상위 n=10개씩\n\n'+
         table(['표','종목','이름','시장','시총 억원','마지막 원자료일','지연 거래일','소속'],top)+'\n\n### 수급·공매도 개별 열의 마지막 비NULL 원자료일\n\n'+
         table(['표','열','비NULL 마지막 날짜','지연 거래일'],nonnull)+'\n\n### market_daily 시계열별 최근60거래일 구멍\n\n'+
         table(['series','빈 거래일 수','빈 날짜'],series_gaps)+'\n\n환율은 원자료 시장 달력이 다를 수 있다. 여기서는 요청한 국내 거래일 대비 구멍만 확인했으며 누락 원인은 확인 못 함.\n\n### 최근10거래일 신용 열의 비NULL 수\n\n'+
         table(['날짜','전체 행 수','신용 수량 비NULL','신용 금액 비NULL','신용 비율 비NULL'],[[d,*[f'n={x}' for x in nums]] for d,*nums in credit_daily])+'\n\n'+
         f'신용 비율 마지막 비NULL은 {credit_last}, 기준일보다 n={credit_lag}거래일 뒤처진다. kis_flows.py:459의 최근 1~2거래일 결손 설명보다 길지만, wu_score.py:166에는 3일 적재 지연 허용 설명도 있다. 휴장 전후 제공자 실제 게시 일정·응답은 **확인 못 함**이므로 비정상 정지 확정 대신 의심으로 분류한다.\n\n### 최신 입력에 실제 포함된 보충표 종목\n\n'+
         table(['입력 표','보충표 종목 행','그중 supply_fetched=True'],input_rows)+'\n\n'+
         table(['stage3 종목','이름','supply_fetched','실제 수급 마지막 날짜','최근20일 유효 날짜'],input_detail)+'\n\n'+
         '입력 포함·확보 플래그와 원자료 날짜만 확인했다. 점수·순위·수익·성과 변화는 계산하지 않았다.\n\n### 최신 large_final의 원자료 run 분포\n\n'+
         f'최신 run {rid}: 당일 원자료 n={srcfresh}, 과거 원자료 n={srcold}, 원자료 없음 n={srcnull}; 최대 지연 n={oldmax}거래일.\n\n'+
         table(['stage3_src_run','현재 행 수','지연 거래일'],[[d or 'NULL',f'n={n}',sum(x>d for x in cal) if d else '확인 못 함'] for d,n in source_dist])+'\n\n### 알려진 20260911 사건 현재 기록 대조\n\n'+
         table(['시장','stage3 행','수급 확보 행','최초 기록 시각','최종 기록 시각'],known)+'\n\n'+table(['모델','동결 행','최초 동결 시각','최종 동결 시각'],frozen)+
         '\n\n현재 DB에서 09/11 stage3 수급은 모두 확보되어 있고 v30 동결도 09/12 시각이다. 과거 사고는 **알려짐**으로 표시하되 현재 DB가 여전히 수급 0이라는 주장은 하지 않았다. 동결 점수 성과·당시 원본과의 점수 차이는 계산하지 않았다.')
    print('FOCUS_EXTRA', {t:dict(Counter(latest[t].get(tk,(None,None))[0] for tk in extra)) for t in latest},flush=True)
    print('FOCUS_ACTIVE_MISSING',missing_active,flush=True)
    print('COLUMN_DATES',nonnull,flush=True)
    return dict(extra=extra,latest=latest,active_missing=missing_active,srcfresh=srcfresh,srcold=srcold,srcnull=srcnull,maxlag=oldmax,input_counts=input_counts,credit_last=credit_last,credit_lag=credit_lag)


def monitoring_and_conclusions(conns,cal,f,anomalies,const,cache):
    o,h=conns['ohlcv'],conns['history']
    mon=[
        ['지수 KOSPI/KOSDAQ가 본 표보다 뒤처짐','감시 있음','notify_telegram.py:361~375; market_series.py:138~161','🔔 경고·예비 조회 코드 있음. 공통으로 같은 날 멈추거나 series 자체가 없으면 놓칠 수 있음'],
        ['daily_flows 전체 마지막 날짜 지연','감시 있음','notify_telegram.py:379~386; screener_fdr_v2_6.py:984~989','전체 MAX(date)와 전체 최신 종목 비율 90% 문턱. 특정 갈래 0%를 보장하지 않음'],
        ['보충표 종목만 수급 정지','감시 없음','kis_flows.py:290~325; 위 전체 감시','본 표/보충표 갈래 기대 목록의 최신 커버리지 경고 없음'],
        ['short/credit/loan의 갈래·종목·열별 날짜 정지','감시 없음','kis_flows.py:497~531; notify_weekly.py:150~162','개별 호출 실패는 로그에 있음. 표/열 최신일과 기대 대상의 지속 누락을 판단하는 정기 경고는 확인하지 못함'],
        ['단일 short 조회 실패','감시 있음','kis_flows.py:514~531','최초 실패 최대 n=5종목과 총 실패 수를 로그로 남김. 일부 실패에도 종료 0일 수 있어 배치 실패 알림과 다름'],
        ['daily_ohlcv_extra 날짜·종목별 멈춤','감시 없음','extra_ohlcv.py:60~145; notify_telegram.py 신선도 함수','수집 대상 수·적재 범위는 로그로 출력. 본 표 대비 지연/빠진 기대 종목을 🔔로 알리는 비교 없음'],
        ['stage1 행 수 급감','감시 있음','run_and_diversify.py:123~171','시장별 최근 n=10run 중앙값의 50% 미만이면 공개 배포 보류. 이 감사의 직전20일/70% 규칙과 다름'],
        ['수급 확보·재무 결손 급변','감시 있음','notify_telegram.py:636~674','수급 전일 대비 절반 미만·시장별 재무 결손 경고. 확보=True라도 원자료가 낡은 경우는 보장 안 됨'],
        ['거래일인데 run 자체 없음','감시 있음','notify_weekly.py:169~190','최근 n=7달력일의 KOSPI 달력과 stage3 run 차집합. 같은 날 배치가 전부 죽으면 당일 경고는 보장 안 됨'],
        ['과거 데이터 중간 날짜 구멍','감시 없음','위 주간 감시 범위 밖','최근 n=7달력일을 벗어난 과거 구멍의 정기 전수 경고는 찾지 못함'],
        ['valuation 일별·시장별 정지','감시 없음','accumulate_valuation.py; notify_weekly.py:155','누적 날짜 수 출력은 있음. 최신일/시장별 커버리지 경고는 찾지 못함'],
        ['consensus 수집 전체 무커버 오염','감시 있음','fetch_consensus.py:168~175; run_all_and_diversify.bat:106~109','커버리지 20% 미만이면 저장 거부·종료 1. 독립적인 주간 최신일 초과 경고는 없음'],
        ['large_final의 옛 stage3 원자료 운반','감시 있음','large_score.py:110~129,281~282','소스 run 저장·당일/과거 건수 로그 출력. 지연 문턱 경고·텔레그램/배포 차단은 없음'],
        ['earnings 자료의 장기 정지','감시 있음','earnings_flag.py:40~65','최신 접수일이 45거래일 오래되면 로그 경고, 60거래일 창 밖도 경고. 큐 실패/종목별 지속 누락 전수 감시는 별개'],
        ['listing_cache의 기준일/예비 사용','감시 있음','notify_telegram.py:389~400','source/saved_at 기준 경고 코드 있음. 이번 감사는 캐시 내용을 읽지 않아 실제 내부 기준일은 확인 못 함'],
        ['날짜만 진전·값 복사/전부0/NULL','감시 없음','기존 행수·최신일·재무 결손 감시만 확인','주식수 등 정상 상수와 구분한 수급/신용/공매도/시총의 연속 값 감시 없음'],
        ['모든 기준 자료가 함께 멈춤','감시 없음','지수·수급 경고가 daily_ohlcv를 상대 기준으로 삼음','외부 달력/예정 run 대비 모든 표의 절대 최신성을 보장하는 독립 감시 없음'],
        ['lowvol/wu 표시 목록 자체의 갱신 지연','감시 있음','docs/lowvol.html:76~101; docs/wu.html:68~91 (읽기만 함)','브라우저 현재일 대비 run이 주중 n=2일 이상 오래되면 경고 배지. 공휴일 예외는 문구만 있고, 배치 경고나 내부 원자료 freshness 검사는 아님'],
        ['PTW 지수 지연·지수 없음','감시 있음','../Position-Tracker-Web/app/market_data.py:269~290; app/main.py:190~193; app/compute.py:733~747','저녁 확인 index 실패·503와 요약 경고 코드 있음. 운영 배포·실제 알림 도달은 확인 못 함'],
        ['PTW 수급 지연·시장 대응표 결손','감시 없음','../Position-Tracker-Web/app/market_data.py:269~306; app/main.py:188~193','수급 behind/대응표 크기는 기록만 함. 저녁 실패 조건·요약 경고에는 미포함'],
    ]
    save('7. 현재 감시가 있는가(코드 정적 확인)',
         '감시 있음은 저장된 코드에 비교·경고/로그 경로가 있다는 뜻이다. 실제 발송·배포·스케줄러 실행은 확인 못 함. 단순 적재 건수·날짜 출력은 지연을 판단하는 경고와 구분했다. 모듈을 import하거나 경고 함수를 실행하지 않았다. PTW는 소스만 읽었으며 data/·운영 DB·API는 열지 않았다.\n\n'+table(['멈춤 유형','판정','근거 파일·줄','한계'],mon))
    ex=f['extra'];dl=f['latest']['daily_flows'];sl=f['latest']['short_flows']
    dcounter=Counter(dl.get(t,(None,None))[0] for t in ex);scounter=Counter(sl.get(t,(None,None))[0] for t in ex)
    stale_d=sum(n for d,n in dcounter.items() if d and d<END);stale_s=sum(n for d,n in scounter.items() if d and d<END)
    dlag=sum(d>'20260911' for d in cal)
    # Date/coverage only; no scores or performance values are selected.
    missing_days=[d for d in cal[-60:] if not h.execute('SELECT 1 FROM stage1_oversold WHERE run_id=? LIMIT 1',(d,)).fetchone()]
    syms=sorted(f['active_missing']['short_flows'])
    active_info=[]
    for tk in syms:
        d,at=sl.get(tk,(None,None))
        active_info.append([tk,names_from_history(h,tk),d or '없음',at or '없음',sum(x>d for x in cal) if d else '확인 못 함'])
    scope=[
        ['F1 보충표 종목의 daily_flows','멈춤 확정',f'기존 n={stale_d}종목 중 n={dcounter.get("20260911",0)}는 09/11(n={dlag}거래일 지연), n={dcounter.get("20260910",0)}는 09/10; 처음부터 자료 없음 n={dcounter.get(None,0)}. 최신 대형 n=500 중 수급 기준일 없음 n=52','점수 입력·대형 표시/관측, 해당 종목을 쓰는 후속 판정의 입력','감시 없음(갈래별)','본 표+보충표의 활발 종목을 기대 목록으로 고정하고 갈래별 최신일·20일 유효일 수·누락 건수를 검사. 이번에는 수정 안 함'],
        ['F2 보충표 종목의 short_flows','멈춤 확정',f'기존 n={stale_s}종목의 마지막 06/26 또는 06/29; 처음부터 없음 n={scounter.get(None,0)}. 코드가 --no-daily 때 보충 대상을 명시적으로 생략','공매도·신용·대차 관측; 현재 본 표 기반 wu 대상과 보충표의 관계는 구분 필요','감시 없음(갈래별)','의도한 지원 범위를 문서/배치 기대 목록에 명시하고, 지원 대상이면 보충표도 포함. 제외가 의도라면 오래된 원자료를 현재 지원처럼 취급하지 않기'],
        ['F3 활발 종목의 당일 short 결손','의심(단기 결손은 확정)',f'n={len(syms)}종목 '+', '.join(syms)+'; 10/08 로그에서 신용 조회의 초당 호출 초과로 실패 확인','short 기반 점수/관측 입력·표시. 성과 영향은 미계산','감시 있음(호출 실패 로그), 지속 결손 감시 없음','성공한 공매도/대차와 실패한 신용을 부분별로 보관하고 실패 부분만 재시도. 종목별 최신일·상태를 경고'],
        ['F4 과거 중간 날짜 공백','멈춤 확정(적재 공백)',f'최근60일 n={len(missing_days)}거래일 '+', '.join(missing_days)+'에 stage1/valuation과 여러 history 표가 0; 시세 표는 존재','점수·판정 앵커·표시','감시 있음(최근 주간 run 확인); 과거 구멍 감시 없음','당일 단계별 완료 표식과 기대 거래일별 저장 행 수를 보관. 원본 로그/아카이브로 원인 확인 후 처리안을 따로 결정'],
        ['F5 최신 large_final의 과거 stage3 운반','의심',f'당일 n={f["srcfresh"]}, 과거 n={f["srcold"]}, 없음 n={f["srcnull"]}; 최대 n={f["maxlag"]}거래일. 의도된 최신 과거 행 조인이나 동적 수급도 함께 운반','대형 재무/수급 표시·관측 입력, 품질 판별','감시 있음(정보 로그), 지연 문턱 경고 없음','재무의 보고기간과 수급의 실제 기준일을 분리. 동적 입력은 별도 최신 창에서 받고 소스 날짜를 함께 표시'],
        ['F6 날짜는 최신이나 신용 열만 NULL','의심',f'신용 n=3열 마지막 비NULL {f["credit_last"]}; 최근 n={f["credit_lag"]}거래일 전부 NULL, 10/08 short 표 n=2516행. 1~2일 결손 설명·3일 지연 허용 설명이 혼재','신용 관측·표시, credit_bal_rate를 읽는 sv_b 보조 입력. 5일 창 min_periods=1로 이전 값이 남을 수 있음','감시 없음(열별 신선도)','휴장·제공자 게시 지연을 반영한 열별 기대 갱신일과 마지막 비NULL 날짜를 저장하고, 허용 지연 초과를 경고. 실제 게시 일정 확인 후 문턱 결정'],
        ['F7 환율 시계열의 과거 중간 구멍','의심(기준 달력 대비 구멍)', 'USDKRW는 07/10 n=1거래일 행 없음. KOSPI/KOSDAQ는 존재하며 환율 최신일 자체는 10/08','환율을 읽는 관측·시장 표시. 해당 날짜 사용처별 대체 동작은 확인 못 함','감시 없음(환율 누락)','국내/원자료 시장의 기대 달력을 구분해 series별 구멍과 마지막 유효일을 경고. 제공자 휴장·적재 실패 여부부터 확인'],
        ['N1 본 표 종목의 당일 수급 없음','정상(거래정지)', '본 표만 n=111종목은 전부 is_suspended=1; 활발 본 표 수급 당일 누락 n=0','표시·입력 대상 범위','수집 대상에서 제외; 별도 정지 상태 있음','정지 종목의 기대 대상 제외를 감시 분모에 반영'],
        ['N2 월별 lead·은퇴 모델 갈래','정상(주기/은퇴)', 'lead 10/01은 월 첫 거래일 앵커. v31 계열·lv_c/lv_d/lv_a3/lv_short/hv_a/mom_b·wu_a/wu_b는 RETIRED에 있음','판정·표시','월 앵커·은퇴 분기 있음','활성/은퇴/월별 주기를 반영한 기대 갱신일로 비교'],
        ['N3 consensus·earnings의 비일별 접수','정상(주간/공시 주기)', 'consensus 10/06(주간 가드), earnings 접수 10/07·원자료 수신 10/08·last_end 10/08','표시·관측·실적 배지','일부 감시 있음','매일 새 보고서가 있어야 한다고 판정하지 말고 수집 커서/실패 상태와 갱신 주기를 별도로 감시'],
        ['N4 주식수·EPS/BPS·상태 필드 불변','정상(상수/공시 갱신)', '주식수는 본 표 n=2576/2626·보충표 n=133/134가 10일 불변. 주식수·분류·분기 재무 값은 매일 바뀌는 값이 아님','시총·점수 입력·표시','값 복사 자체 감시 없음','가격/거래량 변화·분할/증자 사건과 함께 보는 조건부 감시로 오탐 방지'],
        ['N5 bank_net_val 불변·선택 필드 0/NULL','의심(희소 값일 수 있음)', 'bank_net_val n=2293/2518가 10일 불변. 전체 금융 수급 정지나 복사라는 증거는 아님. 선택 상태/비활성 필드 0/NULL은 원래 정상 가능','수급 관측·표시','필드별 연속값 감시 없음','비활성/선택 필드는 제외하고, 원자료 기준일과 금액/수량의 동시 변화·비NULL 커버리지를 감시. 실제 제공자 응답은 확인 못 함'],
        ['N6 오래된 캐시 파일','의심(mtime 후보, 고정 역사 캐시일 수 있음)', f'메타데이터 n={cache["n"]}파일 중 감사용 20거래일 기준보다 오래된 n={cache["old"]}파일. listing_cache 파일 mtime은 10/08','재무·상장목록·분류 입력','listing 일부 감시 있음; 개별 캐시 내부 기준일 확인 못 함','mtime만으로 폐기하지 말고 원자료 기준일/만료 정책/사용처를 별도 기록. 이번에는 내용 미열람'],
        ['N7 지수·시세·현재 활성 모델 최신일','정상(기준일까지 존재)', 'KOSPI/KOSDAQ·본 표·보충표·밸류·활성 모델 표의 마지막 날짜는 10/08','점수·판정·표시','지수 일부·행수 일부 감시 있음','전체 최신일뿐 아니라 갈래별 최신일·기대 종목 커버리지를 함께 검사'],
        ['P1 PTW 뒤처짐 감시','정상(지수 감시 코드 확인, 운영 상태는 확인 못 함)', '지수 감시 코드 있음. 수급/시장 대응표는 정보용 기록. 운영 데이터·API·배포는 확인 안 함','PTW','지수 있음; 수급/대응표 경고 없음','기록된 수급 behind/시장 대응표 결손을 별도 경고로 올리는 안 검토. 여기서는 코드 수정/실행 안 함'],
    ]
    save('결론: 발견별 재현 방법 · 영향 · 고치는 안',
         f'모든 물리 표 n=24개, 갈래 집계 n=170개를 확인했다. 현재 날짜 전체의 장기 정지는 발견 n=0이지만, **종목 갈래별 원자료 멈춤 n=2유형(F1/F2)**과 **과거 적재 공백 n=1유형(F4)**을 직접 확인했다. F2는 코드상 지원 범위 제외가 명시되어 있어 수집기 고장과 범위 부족을 구분해야 한다. 단기 개별 실패·과거 입력 운반·값 불변은 따로 의심으로 분류했다. 판정 눈가림을 위해 수익·IC·순위 상관·점수 차이 등 성과 숫자는 계산하지 않았다.\n\n'+
         table(['발견','분류','실측/근거','영향 받는 곳','감시','고치는 안'],scope)+'\n\n'+
         '### 핵심 재현 방법과 원인 범위\n\n'+
         '1. F1/F2: `daily_ohlcv_extra WHERE date=20261008`의 종목 집합을 만든 뒤 daily_flows/short_flows를 LEFT JOIN하고 종목별 MAX(date)를 센다. 일반 표/market별 MAX(date)는 모두 최신이라 이 갈래를 놓쳤다. `kis_flows.load_all_tickers`는 본 표 활발 종목+listing_cache를 쓰며 기존 보충표 종목 집합을 사용하지 않는다(kis_flows.py:290~325). 실제 캐시 내용은 요청에 따라 읽지 않았다. 10/08 로그는 시세 보충 대상 n=136, 일별 수급의 상장목록 보충 n=111, 공매도 대상 n=2518을 기록한다. **캐시에서 보충표 종목이 빠졌다는 직접 확인은 못 함**; 수집 대상 구성과 원자료의 집단 정지를 대조한 원인 추정이다. 공매도 보충 생략은 코드에서 직접 확인한 사실이다.\n'+
         f'2. F1 영향 경로: screener_fdr_v2_6.py:955~989는 전 표의 최근20일 창 안에 보고된 행을 종목별 합산하고 supply_fetched=True로 둔다. 종목마다 당일 여부/유효20일을 필수로 요구하지 않는다. 10/08 로그의 최신일 보유는 91%, 경고 문턱은 90%라 전체 경고로는 누락 갈래를 잡지 못한다. 현재 stage1 보충표 종목 n={f["input_counts"]["stage1_oversold"][0]} 중 확보=True n={f["input_counts"]["stage1_oversold"][1]}, stage3 n={f["input_counts"]["stage3_final"][0]} 중 확보=True n={f["input_counts"]["stage3_final"][1]}를 직접 확인했다. stage3 상세 원자료 날짜·유효일 수는 위 표에 적었다. 점수/판정 수치가 얼마나 바뀌는지·성과 영향은 계산하지 않았다.\n'+
         '3. F3: 본 표 is_suspended=0이면서 10/08 short 행이 없는 종목을 구한다. 10/08 로그의 077360·217500 실패 사유는 신용 조회 초당 호출 초과다. collect_short는 신용 조회 실패 시 앞서 받은 공매도도 저장 단계로 넘기지 않는다(kis_flows.py:445~478). 해당 종목의 마지막 원자료는 아래 표에 적었다.\n\n'+
         table(['종목','이름','마지막 short 날짜','마지막 수신 시각','지연 거래일'],active_info)+'\n\n'+
         '4. F4: market_daily의 거래일별 stage1/valuation 행 수를 0까지 채워 대조한다. 해당 날짜의 자동 배치 로그 파일은 현재 저장소에서 찾지 못했고 원인·사용자가 일부러 비운 것인지는 **확인 못 함**. 사후 복원이나 앵커 제외 여부를 여기서 정하지 않았다.\n'+
         '5. F5: 현재 large_final의 stage3_src_run별 행 수와 지연 거래일을 센다. load_stage3_latest는 target_run 이하 가장 최근 행을 종목마다 고르므로 오래된 값 운반 자체는 설계에 있다. 재무는 분기 갱신이 정상이나 동적 수급까지 같은 소스 시각으로 운반되는 점은 구분이 필요하다.\n\n'+
         '6. F6: short_flows를 date로 묶어 세 credit 열의 COUNT(열)과 MAX(CASE WHEN 열 IS NOT NULL THEN date END)를 대조한다. 10/06·10/07·10/08은 행이 있으나 세 열 모두 비NULL n=0이다. 공매도·대차는 비NULL 마지막 날짜 10/08로 신용만 뒤처졌다. wu_score는 신용을 5일 창·최소 유효1일 평균으로 읽는다(정적 확인); 이 감사에서는 점수를 실행하지 않았다. 제공자 게시 지연인지 실패인지 확인 못 함.\n\n'+
         '7. F7: 국내 거래일 집합과 market_daily의 series별 날짜 집합을 차집합으로 비교한다. 07/10 USDKRW n=0은 확인됐으나 원자료 달력이나 수집 실패 원인은 확인 못 함. notify_telegram의 지수 경고는 KOSPI/KOSDAQ만 검사하므로 환율은 빠진다.\n\n'+
         '### 해석 한계와 재현 명령\n\n'+
         '- 날짜·행 수·종목 집합·NULL/0/불변 비율은 직접 계산한 사실이다. 전부 같은 값이라는 조건만으로 제공자가 복사했다고 확정할 수 없다. 감시 코드는 정적으로 확인했으며 텔레그램 발송/운영 배포는 확인 못 함.\n'+
         f'- 최근60일의 n={len(anomalies)}개 70% 미만 행은 진단 후보이지 서로 독립적인 사고 n={len(anomalies)}건이 아니다. 시장×표 중복, 주간·월별·공시 희소 자료, 은퇴와 등록, 후보 필터 변화가 함께 포함된다. stage1과 valuation의 공통 0 날짜·보충표 기대 목록의 연속 0은 별도로 확인했다.\n'+
         '- 실행: `python -B research/handoff/code_20261010_stale_data_audit.py`. 표/갈래/기간별 요약을 순서대로 답 파일에 저장한다. 캐시 파일은 이름·크기·mtime만 수집한다. 외부 호출·운영 코드 수정·DB 쓰기·성과 계산 n=0. 이미 본 저장 자료의 사후 감사이며 새로운 기간의 독립 성과 검증이 아니다.\n\n'+
         '### 감시가 없는 멈춤 유형\n\n'+
         '1. 전체 표는 최신인데 보충표·시장·모델·출처 등 일부 기대 갈래만 멈추거나 사라짐(활성/주기/정지 예외를 반영한 감시).\n'+
         '2. short_flows의 공매도·신용·대차 각각의 마지막 비NULL 날짜, 지속 누락 종목, 지원 범위 밖에 남은 오래된 자료.\n'+
         '3. daily_ohlcv_extra·valuation_daily의 기대 거래일/종목별 지연, 최근 주간 창을 벗어난 과거 적재 구멍.\n'+
         '4. 날짜만 진전하는 값 복사·전부0/NULL(정상 상수/선택 필드 제외), 기존 자료의 소스 날짜와 저장 날짜 분리 감시.\n'+
         '5. daily_ohlcv·market_daily·수급이 함께 멈춰 상대 날짜 비교를 통과하는 공통 정지의 배치 경고(일부 목록 화면에는 오래된 run 배지가 있음), USDKRW 등 시계열별 기대 달력 구멍.\n'+
         '6. 주간 consensus의 예정 갱신일 초과, 개별 캐시의 원자료 기준일/지원 범위 변화(파일 mtime 외).\n'+
         '7. PTW 수급 뒤처짐·시장 대응표 결손의 실패 경고(현재는 정보용 기록만 있음).\n')


def names_from_history(h,tk):
    for t in ('large_universe','stage1_oversold'):
        row=h.execute('SELECT name FROM '+qi(t)+' WHERE ticker=? AND name IS NOT NULL ORDER BY run_id DESC LIMIT 1',(tk,)).fetchone()
        if row:return row[0]
    return '확인 못 함'


def main():
    started=guard();conns={k:ro(v) for k,v in DBS.items()}
    try:
        o=conns['ohlcv']
        cal=[r[0] for r in o.execute("SELECT DISTINCT date FROM market_daily WHERE series IN ('KOSPI','KOSDAQ') AND date<=? ORDER BY date",(END,))]
        assert cal[-1]==END and len(cal)>=80,(cal[-1],len(cal))
        save('범위와 방법',f'실행 {started}. 기준일 {END}, 가장 최근 거래일 {cal[-1]}, 10/09 휴장. calendar=market_daily의 KOSPI/KOSDAQ 합집합. 최근 n=60일 {cal[-60]}~{END}, 최근 n=20일 {cal[-20]}~{END}, 최근 n=10일 {cal[-10]}~{END}. 거래일의 정확성은 DB 기록을 기준으로 했고 외부 달력과 별도 대조하지 않았다. 세 DB의 모든 물리 표(sqlite_master type=table)를 mode=ro로 읽었다. 수집기·배치·프로젝트 모듈 실행·DART·KIS·외부 호출 n=0. 성과 계산 n=0. 운영 코드·DB·docs 변경 없음. 날짜 뒤처짐은 실측, 오류 원인·영향 해석은 코드와 갱신 주기에 근거해 구분한다.')
        sources=read_sources();metas=inventory(conns,cal,sources);br=branches(conns,metas,cal)
        mp,caps,names=market_map(conns);counts,anomalies=daily_counts(conns,metas,cal,mp)
        const=constants(conns,metas,cal,mp);hole,relevant=holes(conns,cal,mp,caps,names);cache=caches(cal)
        foc=focus(conns,cal,mp,caps,names);monitoring_and_conclusions(conns,cal,foc,anomalies,const,cache)
        print('SUMMARY',len(metas),len(br),len(anomalies),'constant',len(const),flush=True)
        print('PRIORITY_CONSTANTS',json.dumps([r for r in const if r['priority'] and r['domain']=='전체'],ensure_ascii=False),flush=True)
    finally:
        for c in conns.values():c.close()


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
