"""Offline financial PIT audit; writes only the companion REPLY.

Run: python -B research/handoff/code_20261020_fin_pit_audit.py
Sample rule fixed before drawing: seed=20261020; 4 rows per within-run
market-cap quintile, targeting (December/non-December) x (amendment observed/
not observed). Empty cells fall back within quintile, favoring as-yet unused
metadata categories, then a seeded permutation. Unique tickers, 20 rows.
No collector/module imports, network, credentials, production writes.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import ast
import hashlib
import json
import re
import sqlite3
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('REPLY_20261020_fin_pit_audit.md')
END = '20261019'
SEED = 20261020
BOOT = 4000
KEY = ['ticker', 'year', 'reprt']


def guard():
    n = datetime.now(timezone(timedelta(hours=9)))
    if n.weekday() < 5 and (20, 10) <= (n.hour, n.minute) <= (22, 30):
        raise SystemExit('평일 배치 제한 시간: 중단')


def ro(p):
    guard()
    c = sqlite3.connect(p.resolve().as_uri() + '?mode=ro', uri=True)
    c.execute('PRAGMA query_only=ON')
    return c


def extract(filename, names, constants=(), env=None):
    """Execute explicitly selected pure definitions only, never module imports/main."""
    tree = ast.parse((ROOT / filename).read_text(encoding='utf-8-sig'))
    body = []
    for x in tree.body:
        if isinstance(x, ast.FunctionDef) and x.name in names:
            body.append(x)
        elif isinstance(x, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in x.targets):
            body.append(x)
    assert len([x for x in body if isinstance(x, ast.FunctionDef)]) == len(names)
    env = dict(env or {})
    exec(compile(ast.Module(body=body, type_ignores=[]), filename + ':pure', 'exec'), env)
    return env


def pct(k, n):
    if not n:
        return '확인 못 함 (n=0)'
    p, z = k/n, 1.959963984540054
    den = 1+z*z/n
    mid = (p+z*z/(2*n))/den
    half = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return f'{k:,}/{n:,} = {100*p:.3f}% [{100*max(0,mid-half):.3f}, {100*min(1,mid+half):.3f}]'


def table(head, rows):
    def esc(x):
        return str(x).replace('|', '/').replace('\n', ' ')
    return '\n'.join(['| '+' | '.join(head)+' |', '|'+'|'.join(['---']*len(head))+'|']+
                     ['| '+' | '.join(esc(x) for x in r)+' |' for r in rows])


def fmt(x, d=1):
    return '없음' if pd.isna(x) else f'{x:,.{d}f}'


def same(a, b):
    return pd.notna(a) and pd.notna(b) and abs(float(a)-float(b)) < 1e-7


def finite_round(x, unit=1):
    return round(float(x)/unit, 1) if x is not None and pd.notna(x) else None


def bootstrap(sr, denom=7):
    sr = sr.dropna().sort_index()
    if not len(sr):
        return ['산출 불가']*7
    a = sr.to_numpy(float)
    rng = np.random.default_rng(7)
    boots = a[rng.integers(0, len(a), (BOOT, len(a)))].mean(axis=1)
    labs = pd.to_datetime(sr.index).to_period('W').astype(str)
    groups = [a[labs == w] for w in sorted(set(labs))]
    rng = np.random.default_rng(7)
    wb = np.array([np.concatenate([groups[j] for j in rng.integers(0,len(groups),len(groups))]).mean() for _ in range(BOOT)])
    inter = lambda arr, alpha: '['+', '.join(f'{x:+.6f}' for x in np.quantile(arr,[alpha/2,1-alpha/2]))+']'
    return [len(a), f'{a.mean():+.6f}', inter(boots,.05), inter(wb,.05),
            inter(boots,.05/denom), inter(wb,.05/denom), pct(sum(g.mean()>0 for g in groups),len(groups))]


def load_catalog(con, raw, sf):
    """Preserved financial items; later snapshots are NOT assumed PIT truth."""
    catalog = {}
    def add(t, y, r, fs, api, rc, items, source):
        op = sf['find_operating_profit'](items)
        cf = sf['find_operating_cash_flow'](items)
        if not op:
            return
        rc = str(op.get('rcept_no') or rc or '')
        cf_rc = str((cf or {}).get('rcept_no') or rc)
        rec = dict(ticker=t, year=y, reprt=r, fs=fs, api=api, rc=rc,
                   date=rc[:8] if re.fullmatch(r'\d{14}',rc) else None,
                   cf_date=cf_rc[:8] if re.fullmatch(r'\d{14}',cf_rc) else None,
                   op=op, cf=cf, source=source)
        catalog.setdefault((t,y,r),[]).append(rec)
    for t,y,r,fs,api,rc,js in con.execute("SELECT stock_code,year,reprt,fs,api,rcept_no,items FROM reports WHERE status='000' AND kept>0 AND year>=2024 ORDER BY stock_code,year,reprt,api,fs"):
        items=json.loads(js)
        if api=='SINGLE':
            for f in ['CFS','OFS']:
                add(t,y,r,f,api,rc,sf['filter_items_by_fs'](items,f),'dart_hist')
        else:
            add(t,y,r,fs,api,rc,items,'dart_hist')
    fields={'th':'thstrm_amount','th_add':'thstrm_add_amount','fr':'frmtrm_amount',
            'fr_q':'frmtrm_q_amount','fr_add':'frmtrm_add_amount'}
    for x in raw.to_dict('records'):
        op={'account_id':'dart_OperatingIncomeLoss','sj_div':'IS','rcept_no':x['rcept_no']}
        op.update({out:x[col] for col,out in fields.items() if pd.notna(x[col])})
        add(x['ticker'],x['year'],x['reprt'],x['fs'],'ALL',x['rcept_no'],[op],'earnings_raw')
    return catalog


def q_match(row, records, sf):
    available, matches = [], []
    for rec in records:
        api = 'ALL' if row.q_source_api=='fnlttSinglAcntAll' else 'SINGLE'
        if rec['fs'] != row.q_fs_div or rec['api'] != api:
            continue
        x=rec['op']
        a=sf['parse_amount'](x.get(row.q_latest_key))
        b=sf['parse_amount'](x.get(row.q_prev_key))
        if a is None or b is None or b==0:
            continue
        available.append(rec)
        if (same(row['q_latest_억'],finite_round(a,1e8)) and
            same(row['q_prev_억'],finite_round(b,1e8)) and
            same(row['quarterly_yoy_%'],sf['calculate_yoy'](a,b))):
            matches.append(rec)
    dated=[x for x in matches if x['date']]
    before=[x for x in dated if x['date']<=row.run_id]
    if before:
        return '공시본 수치 일치',min(before,key=lambda x:x['date'])
    if dated:
        return '후일 공시본만 일치',min(dated,key=lambda x:x['date'])
    return ('보존본과 불일치' if available else '값 대조 못 함'),None


def annual_match(row, records, sf):
    complete, matches=[],[]
    for x in records:
        if x['fs']!=row.annual_fs_div or x['api']!='ALL' or not x['cf']:
            continue
        vals=[sf['parse_amount'](it.get(k)) for it,k in [(x['op'],'thstrm_amount'),(x['op'],'frmtrm_amount'),(x['cf'],'thstrm_amount'),(x['cf'],'frmtrm_amount')]]
        if any(v is None for v in vals):
            continue
        complete.append(x)
        if all(same(row[c],finite_round(v,1e8)) for c,v in zip(['annual_latest_억','annual_prev_억','ocf_latest_억','ocf_prev_억'],vals)) and same(row['annual_yoy_%'],sf['calculate_yoy'](*vals[:2])):
            if x['date'] and x['cf_date']:
                matches.append((max(x['date'],x['cf_date']),x))
    before=[x for d,x in matches if d<=row.run_id]
    if before:
        return '공시본 수치 일치',min(before,key=lambda x:x['date'])['rc']
    if matches:
        return '후일 공시본만 일치',min(matches,key=lambda a:a[0])[1]['rc']
    return ('보존본과 불일치' if complete else '값 대조 못 함'),''


def main():
    guard()
    paths=[ROOT/'history.db',ROOT.parent/'dh-q7m3k-data/earnings.db',ROOT.parent/'dh-q7m3k-data/ohlcv.db',ROOT/'research/dart_history/dart_hist.db']
    before=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]
    sf=extract('stage3_fundamental_momentum_v2_6.py',
               ['filter_items_by_fs','_is_is_like','find_operating_profit','find_operating_cash_flow','parse_amount','first_amount','calculate_yoy','amount_to_억','_quarterly_from_op'],
               ['_IS_LIKE','_OP_ACCOUNT_ID_KEYWORDS','_OCF_ACCOUNT_ID_KEYWORDS','_OCF_EXACT_KEYWORDS'])
    with ro(paths[0]) as h:
        s=pd.read_sql_query('SELECT * FROM stage3_final WHERE run_id<=? ORDER BY run_id,market,ticker',h,params=(END,))
        run_count=h.execute('SELECT count(distinct run_id) FROM runs WHERE run_id<=?',(END,)).fetchone()[0]
        missing14={tb:h.execute(f'SELECT count(*) FROM {tb} WHERE run_id=?',('20261014',)).fetchone()[0] for tb in ['runs','stage3_final','v3_scores']}
        scores=pd.read_sql_query("SELECT run_id,market,ticker,final_score_v3 score FROM v3_scores WHERE model_id='v30' AND run_id<=?",h,params=(END,))
        denom=h.execute('SELECT count(distinct model_id) FROM v3_scores').fetchone()[0]
    assert not s.duplicated(['run_id','ticker']).any()
    s[['year','reprt']]=s.q_period.str.extract(r'^(\d{4}) (Q1|H1|Q3)$')
    s.year=pd.to_numeric(s.year)
    with ro(paths[1]) as e:
        q=pd.read_sql_query('SELECT * FROM earnings_q ORDER BY ticker,year,reprt',e)
        raw=pd.read_sql_query('SELECT * FROM earnings_raw ORDER BY ticker,year,reprt',e)
    with ro(paths[3]) as d:
        filings=pd.read_sql_query("SELECT stock_code ticker,kind,report_nm,rcept_dt,rcept_no FROM filings WHERE kind IN ('A001','A002','A003') ORDER BY rcept_dt,rcept_no",d)
        catalog=load_catalog(d,raw,sf)
    assert not q.duplicated(KEY).any()
    z=s.merge(q[KEY+['rcept_dt','q_op','q_op_prev','source']],on=KEY,how='left',validate='many_to_one')
    z['dated']=z.rcept_dt.str.fullmatch(r'\d{8}',na=False)
    z['future']=z.dated & (z.run_id<z.rcept_dt)
    z['q_eq']=np.isclose(z['q_latest_억'],(z.q_op/1e8).round(1),atol=1e-7,rtol=0) & np.isclose(z['q_prev_억'],(z.q_op_prev/1e8).round(1),atol=1e-7,rtol=0)
    annual=q[q.reprt=='Y'][['ticker','year','rcept_dt']].rename(columns={'year':'annual_year','rcept_dt':'annual_date'})
    z=z.merge(annual,on=['ticker','annual_year'],how='left',validate='many_to_one')
    z['annual_dated']=z.annual_date.str.fullmatch(r'\d{8}',na=False)
    z['annual_future']=z.annual_dated & (z.run_id<z.annual_date)
    z['month']=z.run_id.str[:6]
    print('PRIMARY',len(z),int(z.dated.sum()),int(z.future.sum()),flush=True)

    # Evaluate each distinct financial vector and run date with retained snapshots.
    qcache,acache={},{}
    qstate,qreceipt,astate,areceipt=[],[],[],[]
    for _,x in z.iterrows():
        k=tuple(x[c] for c in ['ticker','year','reprt','run_id','q_fs_div','q_source_api','q_latest_key','q_prev_key','q_latest_억','q_prev_억','quarterly_yoy_%'])
        if k not in qcache:
            qcache[k]=q_match(x,catalog.get((x.ticker,x.year,x.reprt),[]),sf)
        status,rec=qcache[k];qstate.append(status);qreceipt.append(rec['rc'] if rec else '')
        ak=tuple(x[c] for c in ['ticker','annual_year','run_id','annual_fs_div','annual_latest_억','annual_prev_억','ocf_latest_억','ocf_prev_억','annual_yoy_%'])
        if ak not in acache:
            acache[ak]=annual_match(x,catalog.get((x.ticker,x.annual_year,'Y'),[]),sf)
        annual_status,arc=acache[ak];astate.append(annual_status);areceipt.append(arc)
    z['q_state']=qstate;z['q_receipt']=qreceipt;z['annual_state']=astate
    z['annual_receipt']=areceipt
    z['later_only']=z.q_state.eq('후일 공시본만 일치') | z.annual_state.eq('후일 공시본만 일치')
    print('VERSIONS',z.q_state.value_counts().to_dict(),z.annual_state.value_counts().to_dict(),flush=True)

    # Only daily prices and valuation are read from ohlcv; dart_events never used.
    with ro(paths[2]) as o:
        px=pd.read_sql_query('SELECT ticker,date,close,shares,market FROM daily_ohlcv WHERE date BETWEEN ? AND ? ORDER BY date,ticker',o,params=('20260501',END))
        ex=pd.read_sql_query('SELECT ticker,date,close,shares,market FROM daily_ohlcv_extra WHERE date BETWEEN ? AND ? ORDER BY date,ticker',o,params=('20260501',END))
        val=pd.read_sql_query('SELECT * FROM valuation_daily WHERE date BETWEEN ? AND ?',o,params=('20260501',END))
    close=px.pivot(index='date',columns='ticker',values='close').sort_index()
    didx={d:i for i,d in enumerate(close.index)}
    pp=pd.concat([px,ex]).drop_duplicates(['ticker','date'],keep='first')
    pp['mcap']=pp.close*pp.shares
    env=extract('leaderboard.py',['anchor','dedupe_by_anchor','build_gates','model_ic'],env=dict(np=np,pd=pd,
                GATE_FRAC=.30,TRACKS={'v3':('v3_scores','final_score_v3',None),'lv':('lowvol_scores','lowvol_score',None),'wu':('wu_scores','wu_score',None)},
                ENTRY_LAG=1,HORIZONS=[20],MIN_GROUP=8,JUMP_CAP=.32,TOP_EXC=20,BOOT=BOOT))
    rid_date={r:close.index[a] if (a:=env['anchor'](r,didx)) is not None else None for r in z.run_id.unique()}
    z['price_date']=z.run_id.map(rid_date)
    z=z.merge(pp[['ticker','date','mcap']].rename(columns={'date':'price_date'}),on=['ticker','price_date'],how='left',validate='many_to_one')
    z.loc[z.mcap<=0,'mcap']=np.nan
    z['quintile']=z.groupby('run_id').mcap.transform(lambda x: pd.qcut(x.rank(method='first'),5,labels=False)+1)

    filings[['report_year','report_month']]=filings.report_nm.str.extract(r'\((\d{4})\.(\d{2})\)')
    filings['amended']=filings.report_nm.str.contains('정정',na=False)
    # Fiscal month from latest annual filing visible by run, not receipt-month guess.
    fiscal={t:g for t,g in filings[filings.kind=='A001'].groupby('ticker')}
    by_rc=filings.set_index('rcept_no').to_dict('index')
    amendment_keys=set(zip(filings.loc[filings.amended,'ticker'],filings.loc[filings.amended,'kind'],filings.loc[filings.amended,'report_year'],filings.loc[filings.amended,'report_month']))
    fiscal_cache={}
    def metadata(x):
        key=(x.ticker,x.run_id)
        if key not in fiscal_cache:
            g=fiscal.get(x.ticker)
            g=g[g.rcept_dt<=x.run_id] if g is not None else pd.DataFrame()
            mm=g.iloc[-1].report_month if len(g) else None
            fiscal_cache[key]=('12월' if mm=='12' else '비12월('+str(mm)+')' if pd.notna(mm) else '확인 못 함')
        known=by_rc.get(x.q_receipt)
        if not known:
            recs=catalog.get((x.ticker,x.year,x.reprt),[])
            known=next((by_rc[r['rc']] for r in recs if r['fs']==x.q_fs_div and r['rc'] in by_rc),None)
        if known:
            ky=(x.ticker,known['kind'],known['report_year'],known['report_month'])
            amend='있음' if ky in amendment_keys else '목록 내 미관측'
        else:
            amend='확인 못 함'
        return fiscal_cache[key],amend
    metas=[metadata(x) for _,x in z.iterrows()]
    z['fiscal']=[a for a,b in metas];z['amend']=[b for a,b in metas]
    rng=np.random.default_rng(SEED)
    pool=z[z.quintile.notna()].copy()
    pool['random_order']=rng.permutation(len(pool))
    chosen=[];used=set();fallbacks=[]
    targets=[('12월','있음'),('12월','목록 내 미관측'),('비12월','있음'),('비12월','목록 내 미관측')]
    for b in range(1,6):
        for fiscal_target,amend_target in targets:
            p=pool[(pool.quintile==b)&~pool.ticker.isin(used)]
            match=p[p.fiscal.str.startswith(fiscal_target)&(p.amend==amend_target)]
            if not len(match):
                # Favor same fiscal group, then amendment status, before general fallback.
                match=p[p.fiscal.str.startswith(fiscal_target)]
                if not len(match):match=p[p.amend==amend_target]
                if not len(match):match=p
                fallbacks.append((b,fiscal_target,amend_target))
            x=match.sort_values('random_order').iloc[0]
            chosen.append(x);used.add(x.ticker)
    sample=pd.DataFrame(chosen).reset_index(drop=True)
    assert len(sample)==20 and sample.ticker.nunique()==20 and (sample.groupby('quintile').size()==4).all()

    # Supplemental ROE arithmetic reproduction only: no report-vintage metadata in valuation_daily.
    rz=z.merge(val[['ticker','date','eps','bps','per','pbr']].rename(columns={'date':'run_id'}),on=['ticker','run_id'],how='left',validate='many_to_one')
    calc=(rz.eps/rz.bps*100).where(rz.bps>0)
    calc=calc.fillna((rz.pbr/rz.per*100).where((rz.pbr>0)&(rz.per>0))).clip(-200,200).round(2)
    rvalid=calc.notna()&rz.roe_value.notna()
    req=np.isclose(calc,rz.roe_value,atol=1e-7,rtol=0)&rvalid

    # Canonical IC helpers, plus independent scipy per-run reproduction.
    regtree=ast.parse((ROOT/'checkup.py').read_text(encoding='utf-8-sig'))
    reg=next(ast.literal_eval(n.value)['v30'] for n in regtree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REG_DATE' for t in n.targets))
    with ro(paths[0]) as h:
        partial,double,_=env['build_gates'](h,list(close.index))
    assert reg=='20260606'
    scores.market=scores.market.str.lower()
    sj=scores.merge(z[['run_id','ticker','future','annual_future','later_only']],on=['run_id','ticker'],how='left',validate='one_to_one')
    flagged=(sj.future.eq(True)|sj.annual_future.eq(True))
    suspect=sj.later_only.eq(True)
    changes=close.pct_change(fill_method=None).abs()
    keep=env['dedupe_by_anchor'](scores,didx,partial|double,reg=reg)
    def measure(sc):
        rows={};usedrows=0
        for rid,g in sc.groupby('run_id'):
            if rid not in keep:continue
            a=env['anchor'](rid,didx)
            if a+21>=len(close):continue
            ret=(close.iloc[a+21]/close.iloc[a+1]-1).where(changes.iloc[a+2:a+22].max()<=.32)
            day=[]
            for mk,p in g.groupby('market'):
                x=p.set_index('ticker').score.astype(float);y=ret.reindex(x.index);m=x.notna()&y.notna()
                if m.sum()<8 or x[m].nunique()<3 or y[m].nunique()<3:continue
                ic=spearmanr(x[m],y[m]).statistic
                assert np.isclose(ic,np.corrcoef(x[m].rank(),y[m].rank())[0,1],atol=1e-12)
                day.append(ic);usedrows+=int(m.sum())
            if day:rows[rid]=np.mean(day)
        return pd.Series(rows,dtype=float),usedrows
    base,bn=measure(sj);clean,cn=measure(sj[~flagged]);sens,sn=measure(sj[~suspect])
    canonical=env['model_ic'](scores,close,len(close),didx,partial|double,reg=reg)[20]
    assert canonical['n']==len(base) and canonical['ic']==round(base.mean(),4)
    bstats=bootstrap(base,denom)
    ci=[float(x) for x in bstats[2].strip('[]').split(',')]
    assert all(abs(a-b)<.000051 for a,b in zip(ci,canonical['ci']))
    paired=(clean-base).dropna();spaired=(sens-base).dropna()
    print('IC',bstats,'SENS',bootstrap(sens,denom),'DIFF',bootstrap(spaired,denom),flush=True)

    # Report: count intervals are descriptive Wilson intervals, not iid claims.
    sec=['# REPLY — 재무 자료 “그날 알던 값” 감사 (2026-10-20)',
    f'**결론: 분기 최초 접수일 기준 공시 전 사용은 {pct(int(z.future.sum()),int(z.dated.sum()))}; 그러나 정정 이력·OCF·ROE까지 포함한 “그날 알던 값” 보장은 확인 못 함. v30·재무 기반 v3 및 ROE 기반 lowvol 판정에는 자료 시점 한계 각주가 필요하다. 판정·점수 변경 제안이 아니다.**',
    '## 1. 범위·수치 읽는 법',
    f'- 실측 범위: stage3 {len(z):,}행, {z.run_id.nunique()} run ({z.run_id.min()}~{END}), {z.ticker.nunique():,}종목; runs 표 고유 run {run_count}. 결과가 있는 행 전수이며 점수 유효성 게이트는 이 전수표에 적용하지 않았다. IC에만 정본 게이트를 적용했다.',
    '- 요청된 history.db·earnings.db와 시총/가격/ROE 대조용 ohlcv.db를 mode=ro + query_only로 열었다. earnings.db 생성 코드가 가리키는 기존 로컬 원본 `research/dart_history/dart_hist.db`도 같은 방식으로 읽었다. 이 보조 DB의 reports·filings는 결산월·정정 여부·OCF 값 확인에 필요했다. 수집기를 실행하거나 외부 공시를 새로 받지 않았다.',
    '- 모든 비율은 분자/분모 n과 참고용 Wilson 95% 구간(% 단위)을 병기한다. 전수 집계 자체에는 표본오차가 없고, 같은 종목/재무 값이 여러 run에 반복되므로 이 구간을 모집단 추론이나 독립 시행의 신뢰도로 해석하지 않는다. 표본 20건의 원금액·날짜·파일 수에는 통계 구간이 해당하지 않는다. IC 구간은 아래 날짜/주 재표집 방식이다.',
    '## 2. 대응 규칙과 날짜 검사가 증명하지 못하는 것',
    table(['stage3','대응/의미'],[
    ['q_period = YYYY Q1/H1/Q3','earnings_q (ticker, year=YYYY, reprt=Q1/H1/Q3). DART 코드 11013/11012/11014; reprt_ord=1/2/3.'],
    ['q_prev_key','분기 키가 아니라 같은 응답의 전년 금액 필드명. frmtrm_q_amount → frmtrm_amount 순; 누적 폴백이면 frmtrm_add_amount. 전년 보고서 접수일로 잘못 연결하지 않는다.'],
    ['q_latest_억, q_prev_억, quarterly_yoy_%','thstrm_amount와 위 전년 필드 우선. 실패 시 thstrm_add_amount/frmtrm_add_amount. 금액=원/1e8을 소수 1자리, YoY=(현재−전년)/abs(전년)×100을 소수 1자리.'],
    ['annual_year / OCF','연간 Y(11011, reprt_ord=4). annual_latest/prev 및 ocf_latest/prev는 같은 연간 보고서의 thstrm/frmtrm. earnings_q Y의 q_op는 4분기 차분이라 연간 영업이익과 직접 비교 불가. earnings_q에 OCF 자체는 없다.'],
    ['roe_value','catalyst_observe.compute_roe: EPS/BPS×100, 보조 PBR/PER×100, ±200 제한, 소수 2자리. q_period와 대응하지 않는다. valuation_daily에도 재무 보고서·접수일·수집시각 열이 없어 공시 시점은 확인 못 함.']]),
    '- 코드 근거: `stage3_fundamental_momentum_v2_6.py:319,389,436,473`, `catalyst_observe.py:96`, `earnings_flag.py:111,178`, `earnings_incr.py:335`. 분기 후보는 6월부터 당년 Q1, 9월부터 H1, 12월부터 Q3; 이후 전년 Q3/H1/Q1. 연간은 실행연도−1, −2. 개별 접수일을 비교하는 조건은 없고 CFS→OFS, ALL→SINGLE 순으로 찾는다. run_id가 아닌 실행시점 datetime.now를 사용한다. 과거 run 재처리 시 위험 경로지만 이번 감사가 실제 재처리를 증명하지는 않는다.',
    f'- q_period NULL: {pct(int(z.q_period.isna().sum()),len(z))}. 비NULL 형식 대응 실패: {pct(int((z.q_period.notna()&z.year.isna()).sum()),int(z.q_period.notna().sum()))}. 발견 형식·키·기준은 아래와 같다.',
    table(['q_period','q_basis','q_prev_key','행 n'],[[*k,int(v)] for k,v in s.groupby(['q_period','q_basis','q_prev_key'],dropna=False).size().items()]),
    '- earnings_q는 12월 결산만 넣으며 값은 최신 정정본으로 바뀔 수 있다. 원본 접수일은 유지되고 이전 금액은 보존하지 않는다(기본키 ticker/year/reprt). earnings_raw도 같은 기본키로 덮어쓴다. 따라서 `run>=rcept_dt`는 해당 보고서가 처음 나왔다는 확인일 뿐, 저장된 정확한 값이 그날 공개됐다는 확인이 아니다. 후일 공시본과 값이 같아도 원본 값이 같았을 수 있으므로 그 자체를 미래 참조 확정으로 세지 않는다.',
    '## 3. 전수 대조 — 최초 접수일',
    table(['범위','날짜 확인 가능/전체 [95%]','공시 전 사용/확인 가능 [95%]','확인 못 함 n'],[
      ['분기',pct(int(z.dated.sum()),len(z)),pct(int(z.future.sum()),int(z.dated.sum())),int((~z.dated).sum())],
      ['연간(OP·OCF 보고서)',pct(int(z.annual_dated.sum()),len(z)),pct(int(z.annual_future.sum()),int(z.annual_dated.sum())),int((~z.annual_dated).sum())]]),
    f'- 분기 미확인 {int((~z.dated).sum()):,}행 = q_period 없음 {int(z.q_period.isna().sum()):,} + 분기 키는 있으나 earnings_q 날짜 없음 {int((~z.dated&z.q_period.notna()).sum()):,}. 모두 미래 참조 비율 분모에서 제외. 보조 원본의 날짜를 끼워 넣어 주 대조 분모를 바꾸지 않았다.',
    table(['월','전체 n','분기 날짜 확인 n','분기 공시 전/확인 [95%]','분기 미확인 n','연간 공시 전/확인 [95%]','연간 미확인 n','OCF 데이터없음/전체 [95%]'],[
      [m,len(g),int(g.dated.sum()),pct(int(g.future.sum()),int(g.dated.sum())),int((~g.dated).sum()),pct(int(g.annual_future.sum()),int(g.annual_dated.sum())),int((~g.annual_dated).sum()),pct(int(g.ocf_pattern.eq('데이터없음').sum()),len(g))] for m,g in z.groupby('month')]),
    '### 정확한 값의 보조 대조 (공시본 보존자료 기준)',
    f'- earnings_q의 분기 현재·전년 두 금액과 소수 1자리까지 동시 일치: {pct(int((z.q_eq&z.dated).sum()),int(z.dated.sum()))}. 불일치에는 정정, 연결/별도, 전년 값 선택, 누적 차분 방식 차이가 섞여 있어 미래 참조로 분류하지 않았다.',
    table(['상태','분기 현재/전년/YoY [95%]','연간 OP 현재/전년·OCF 현재/전년·YoY [95%]'],[
      [st,pct(int(z.q_state.eq(st).sum()),len(z)),pct(int(z.annual_state.eq(st).sum()),len(z))] for st in ['공시본 수치 일치','후일 공시본만 일치','보존본과 불일치','값 대조 못 함']]),
    '- “공시본 수치 일치”는 같은 연결/별도·API 계열, 저장된 필드명과 반올림값이 run 이전 접수번호의 보존본에 있다는 뜻이다. 실제 배치가 그 접수번호를 썼다는 이력은 아니다. 과거 연구 DB가 일부 frmtrm_q_amount를 저장하지 않아 값 대조를 못 하는 경우도 있다. “후일 공시본만 일치”는 의심 집합이며 원본도 같은 값이었는지 확인 못 함. OCF는 연간 금액 4개와 YoY를 함께 비교했다.',
    f'- ROE의 같은 run 날짜 valuation_daily 산식 대조 가능 {pct(int(rvalid.sum()),int(z.roe_value.notna().sum()))}; 그중 산식 일치 {pct(int(req.sum()),int(rvalid.sum()))}. 값 일치가 재무 공시 시점 검증을 대신하지 않는다.',
    '## 4. 표본 20건 — 먼저 고정한 추출 규칙',
    '- seed=20261020. (run, market, ticker) 정렬 후 난수 순열. run별 stage3의 당시 시총(가격일≤run, close×shares; 본표 우선, 없는 날짜·종목은 보충표)을 순위 동률 (market,ticker)순으로 나눠 5분위. 각 분위에서 12월/비12월 × 정정 관측/목록 내 미관측 4칸당 1건, 종목 중복 없이 총 20건. 빈 칸은 같은 분위에서 결산월 우선→정정 상태 우선→전체 순으로 대체하고 난수순 첫 행을 선택. 값 일치·수익·IC는 추출 조건에 사용하지 않았다.',
    '- 결산월은 run까지 접수된 가장 최근 사업보고서 제목의 월로 확인. 정정 유무는 감사 시점 로컬 filings에 있는 해당 분기 보고서의 기재/첨부 정정을 포함한다(후일 정정도 포함). “미관측”은 정정이 절대 없었다는 뜻이 아니다. 연결된 접수번호가 없으면 미확인. 비12월 종목을 earnings_q 미등재만으로 추정하지 않았다.',
    f'- 시총 결측 {pct(int(z.mcap.isna().sum()),len(z))}은 추출에서 제외. 빈 칸 대체 {len(fallbacks)}건: {fallbacks}. 추출 규칙은 이 코드의 최초 작성 시 고정했고 결과를 보고 seed를 바꾸지 않았다.',
    table(['분위','결산월','정정 관측','n'],[[int(k[0]),k[1],k[2],int(v)] for k,v in sample.groupby(['quintile','fiscal','amend']).size().items()]),
    '- 아래 금액은 억 원, ROE/YoY는 %. Δ일=run−접수일(음수는 접수 전). `E`=earnings_q 원본 접수일, `R`=같은 값의 보존 공시본 접수번호. E만 있고 R이 없으면 그 값의 보고서를 특정한 것이 아니다.']

    rows=[];arows=[];latestrows=[];evidence=[]
    for i,x in sample.iterrows():
        num=i+1
        delta=(pd.Timestamp(x.run_id)-pd.Timestamp(x.rcept_dt)).days if x.dated else '확인 못 함'
        rc=x.q_receipt
        rd=(pd.Timestamp(x.run_id)-pd.Timestamp(rc[:8])).days if rc else '확인 못 함'
        rows.append([num,x.run_id,x.ticker,x['name'] if pd.notna(x['name']) else '이름 미저장',f'{int(x.quintile)}/{fmt(x.mcap/1e8)}',x.fiscal,x.amend,
                     f'{x.q_period}/{x.q_fs_div}/{x.q_prev_key}',f"{fmt(x['q_latest_억'])}/{fmt(x['q_prev_억'])}/{fmt(x['quarterly_yoy_%'])}",
                     f"E {x.rcept_dt if x.dated else '확인 못 함'} (Δ{delta}); R {rc or '확인 못 함'} (Δ{rd})",x.q_state])
        arc=x.annual_receipt
        ard=(pd.Timestamp(x.run_id)-pd.Timestamp(arc[:8])).days if arc else '확인 못 함'
        arows.append([num,f'{int(x.annual_year) if pd.notna(x.annual_year) else "없음"} Y/{x.annual_fs_div}',
            f"{fmt(x['annual_latest_억'])}/{fmt(x['annual_prev_억'])}",f"{fmt(x['ocf_latest_억'])}/{fmt(x['ocf_prev_억'])}",fmt(x.roe_value,2),
            str(x.annual_date) if x.annual_dated else '확인 못 함',f'{arc or "확인 못 함"} (Δ{ard})',x.annual_state])
        # Direct stored fields: never substitute cumulative amounts for missing quarter fields.
        matched=[r for r in catalog.get((x.ticker,x.year,x.reprt),[]) if r['fs']==x.q_fs_div]
        selected=next((r for r in matched if rc and r['rc']==rc),None)
        if selected is None:
            candidates=[r for r in matched if r['date'] and r['date']<=x.run_id]
            selected=max(candidates,key=lambda r:r['date']) if candidates else (matched[0] if matched else None)
        if selected:
            it=selected['op']
            av=sf['parse_amount'](it.get(x.q_latest_key));bv=sf['parse_amount'](it.get(x.q_prev_key))
            ym=by_rc.get(selected['rc'],{}).get('report_nm','제목 미보존')
            evidence.append([num,selected['source'],selected['rc'],ym,
                f'{fmt(finite_round(av,1e8))}/{fmt(finite_round(bv,1e8))}',
                '금액 필드 일부 미보존' if av is None or bv is None else '원표와 비교(일치는 위 표의 상태)'])
        else:
            evidence.append([num,'확인 못 함','확인 못 함','확인 못 함','확인 못 함','보존자료 없음'])
        # Latest visible filing even if its exact vintage/fields were not retained.
        fg=filings[(filings.ticker==x.ticker)&filings.kind.isin(['A002','A003'])&(filings.rcept_dt<=x.run_id)].dropna(subset=['report_year','report_month'])
        lf=fg.sort_values(['report_year','report_month','rcept_dt','rcept_no']).iloc[-1] if len(fg) else None
        eligible=[]
        for (t,y,r),recs in catalog.items():
            if t!=x.ticker or r=='Y':continue
            for rec in recs:
                if lf is not None and rec['rc']==lf.rcept_no:
                    eligible.append(rec)
        eligible.sort(key=lambda r:(r['fs']=='CFS',r['api']=='ALL'))
        if eligible:
            rec=eligible[-1]
            a,_=sf['first_amount'](rec['op'],['thstrm_amount'])
            b,bkey=sf['first_amount'](rec['op'],['frmtrm_q_amount','frmtrm_amount'])
            yy=sf['calculate_yoy'](a,b)
            txt=f"{lf.report_nm}; {rec['rc']} (Δ{(pd.Timestamp(x.run_id)-pd.Timestamp(lf.rcept_dt)).days}); {rec['fs']} {fmt(finite_round(a,1e8))}/{fmt(finite_round(b,1e8))}/{fmt(yy)}"
            if a is None or b is None:
                judgement='확인 못 함: 3개월 필드 일부 미보존(누적으로 대체하지 않음)'
            else:
                different=not (x.q_period==f"{rec['year']} {rec['reprt']}" and same(x['q_latest_억'],finite_round(a,1e8)) and same(x['q_prev_억'],finite_round(b,1e8)) and same(x['quarterly_yoy_%'],yy))
                judgement=('다름(기간/연결기준/값 중 차이)' if different else '같음')+f'; 전년필드={bkey}'
        else:
            txt=(f'{lf.report_nm}; {lf.rcept_no} / {lf.rcept_dt}; 값 확인 못 함(해당 버전 미보존)' if lf is not None else '확인 못 함(당시 공시 목록 없음)')
            judgement='확인 못 함'
        latestrows.append([num,txt,judgement,'원본·정정 모든 버전 미보존: 유일한 당시 정답은 확인 못 함'])
    sec += [table(['#','run','ticker','종목','시총분위/억','결산월','정정','stage3 분기/기준/전년필드','현재/전년/YoY','보고서·날짜·Δ일','값 대조'],rows),
            '### 표본별 보존 원자료 확인',
            '- 아래는 저장된 q_latest_key/q_prev_key를 그대로 대조한 값이다. 전년 필드 미보존을 다른 기간의 값으로 메우지 않았다. 값 불일치나 일부 미보존이면 이 접수번호가 실제 stage3 출처라고 단정하지 않는다.',
            table(['#','로컬 원본','접수번호','보고서 제목','보존된 현재/전년(억)','해석'],evidence),
            '### 같은 20건의 연간·OCF·ROE',table(['#','연간/기준','OP 현재/전년','OCF 현재/전년','ROE','Y 최초 접수일','값 일치 공시본·Δ일','연간 값 대조'],arows),
            '### 그날 가장 최근 공시를 썼을 경우의 비교 후보',
            '- 로컬 filings에서 run 이전 분기/반기 보고서를 남겨 보고서 종료연월 최신→접수일 최신으로 고른 뒤, 그 접수번호의 보존값만 확인했다(연결 우선). 연간 Y의 4분기를 끼워 넣지 않는다. 해당 버전이나 3개월 전년 필드가 없으면 확인 못 함으로 남기며, 더 오래된 보고서나 누적값으로 대신하지 않는다. 이 목록 밖의 공시는 확인 못 함. 6·9·12월 사용 시작 규칙 때문에 이미 나온 다음 분기를 아직 쓰지 않은 차이는 미래 참조와 별개다.',
            table(['#','run 이전 보존본의 후보: 현재/전년/YoY·접수번호','stage3와 비교','④ 당시 썼어야 할 값의 한계'],latestrows)]

    sec += ['## 5. v30 h20 영향 — 각주용 관측, 판정 재작성 아님',
    f'- 등록일 단일소스 checkup.REG_DATE={reg}; 종료 시세 {close.index.max()}. v3 본 시세만 사용(시총 표본용 보충 시세를 IC에 합치지 않음). 게이트: 부분실행 {sorted(partial)}, 이중실행 {sorted(double)}; 비거래일→직전 거래일, 같은 앵커 중복 제거. 유효 OOS 앵커 {len(keep)}, h20 완결 IC 앵커 {len(base)}. stage3 감사행과 동결점수 미대응 {int(sj.future.isna().sum())}행은 안전하다고 간주하지 않고 원 점수를 유지.',
    '- t+1 종가→t+21 종가; 구간 일변화 절댓값>32% 제외; 시장별 유효쌍≥8·점수/수익 고유값≥3; Spearman을 시장 동일가중→날짜 동일가중 평균. leaderboard 순수 함수 AST 추출과 scipy 별도 계산을 대조했다. 날짜·주 블록 4,000회 seed 7, 95% 및 실제 distinct model_id 분모 보정 구간. 주간 양(+)비율은 주평균 기준. 주 블록도 h20 겹침을 완전히 없애지는 못한다.',
    f'- 최초 접수일 기준 분기 또는 연간 공시 전 행과 겹친 v30 행 {int(flagged.sum())}개(등록일 이후 {int((flagged&(sj.run_id>=reg)).sum())}개). 0건이면 제외 전후는 같은 표본이므로 변화 0은 정의상 결과다. 정정 문제가 없다는 증거가 아니다.',
    table(['각주용 집합','IC 앵커 n','평균 IC','날짜95%','주블록95%',f'날짜 보정 /{denom}',f'주블록 보정 /{denom}','주별 양(+) [95%]'],[
        ['원본',*bstats],['최초 접수일 미래행 제외',*bootstrap(clean,denom)],['짝 차이(제외−원본)',*bootstrap(paired,denom)],
        ['후일 공시본만 일치도 제외(의심 감도)',*bootstrap(sens,denom)],['의심 감도 짝 차이',*bootstrap(spaired,denom)]]),
    f'- 원본/최초접수 제외/의심 감도의 유효 종목×run 쌍 n={bn:,}/{cn:,}/{sn:,}. 의심 감도 제거 대상 동결행 {int(suspect.sum()):,}개, 등록일 이후 {int((suspect&(sj.run_id>=reg)).sum()):,}개. 가격·게이트 때문에 실제 IC에 쓰인 감소와 제거 대상 수는 다르다. 의심 감도는 원본도 같았을 수 있는 행을 과잉 제외한 것으로 실제 미래 참조 교정 효과가 아니다. 미확인행은 계속 포함되며 표본 선택도 달라진다.',
    '- 현재 보존된 stage3 행과 동결점수를 run×ticker로 연결했으며, 동결 당시 입력 원본까지 동일했는지는 확인 못 함. 기존 8/09·10/18 판정 창이나 라벨을 변경하지 않았다. 여기 원본 수치는 등록일부터 10/19까지 누적 관측이며 특정 판정문의 숫자를 대체하지 않는다.',
    '## 6. 각주·커버리지',
    f'- 20261014 없음(실측): {missing14}. 수익률 달력에는 실제 시세 날짜를 그대로 사용하며 없는 stage3 run을 만들지 않았다.',
    table(['결측 항목','분자/전체 [95%]'],[
        ['ocf_pattern=데이터없음',pct(int(z.ocf_pattern.eq('데이터없음').sum()),len(z))],
        ['dart_ocf_status≠ok',pct(int(z.dart_ocf_status.ne('ok').sum()),len(z))],
        ['q_period 없음',pct(int(z.q_period.isna().sum()),len(z))],
        ['roe_value 없음',pct(int(z.roe_value.isna().sum()),len(z))]]),
    f'- earnings_q 전체 {len(q):,}행/{q.ticker.nunique():,}종목. 비12월 결산·금액/시세/계정 조건 탈락이 섞여 있어 빈 행을 무공시로 볼 수 없다. 분기 표본의 결산월은 보조 filings로 확인했고 earnings_q만으로는 비12월 층을 만들 수 없었다.']
    listed=set(pp.loc[pp.date==END,'ticker'])
    cov=[]
    for label,qq in [('어느 기간이든',q),('2026 Q1',q[(q.year==2026)&(q.reprt=='Q1')]),('2026 H1',q[(q.year==2026)&(q.reprt=='H1')]),('2025 Y',q[(q.year==2025)&(q.reprt=='Y')])]:
        cov.append([label,pct(len(listed&set(qq.ticker)),len(listed)),len(set(qq.ticker)-listed)])
    sec += [f'- 상장종목 대비 분모는 {END} daily_ohlcv∪daily_ohlcv_extra에 있는 {len(listed):,}종목(본표 우선)의 로컬 시세 유니버스다. 별도 공식 상장명부 DB가 없으므로 그날 실제 전체 상장종목 수와의 정확한 비율은 확인 못 함. 현재 상장/시세 종목에 대한 교집합 비율이며 과거 생존편향이 없는 커버리지가 아니다.',
      table(['earnings_q 범위','10/19 로컬 상장 시세 유니버스 교집합 [95%]','현재 분모 밖 종목 n'],cov),
      '## 7. 모델별 해석과 질문',
      '- **검토 의견/추정 구분:** 위 집계는 로컬 자료에서 직접 확인한 실측이다. 후일 공시본 일치 행이 실제 미래 참조였다는 추정은 확정하지 않는다. 아래 각주 권고는 증명되지 않은 범위를 표시하자는 검토 의견이다.',
      '- v30 및 재무 성분을 공유하는 v3: `quality_score`는 OCF·분기/연간 YoY, `turnaround_score`는 실적 패턴·분기 YoY를 쓴다. 최초 접수일 오류는 관측되지 않았으나 정확한 정정본 출처가 stage3에 없어 과거 판정에 “원본 접수일 대조 통과, 정정본 시점 일부 확인 못 함” 각주가 적절하다.',
      '- lowvol의 lv_a·lv_b·lv_c·lv_d·lv_a3·lv_short·hv_a·sm_a·lv_e는 roe 팩터를 쓴다(은퇴 모델도 과거 판정 포함). ROE를 분기 DART와 연결해 검증했다고 쓰면 안 된다. ROE 기반 판정에는 “가치평가 스냅샷 산식과 공시 시점 검증은 별개” 각주가 필요하다. 가격만 쓰는 모델 및 별도 대형 트랙의 재무까지 이번 결과로 안전/오염을 일반화하지 않는다.',
      '- 확인 못 함: 원본·정정 모든 버전의 당시 값, stage3가 실제 사용한 접수번호, ROE의 기초 재무 공시일, 로컬 목록 밖 공시와 정확한 전체 상장명부. 이를 확정하려면 앞으로 접수번호·응답시각·버전별 원자료를 보존하는 방안이 필요하지만 여기서는 운영 변경을 하지 않는다.',
      '- 질문(진행을 막지 않음): 정정본 시점 미확인을 기존 판정문에 어떤 문구로 남길지는 정본 작성자가 결정해야 한다. 이번 보고서는 숫자와 한계를 제시할 뿐 모델 판정·은퇴·승격을 하지 않는다.',
      '## 8. run별 전수표',
      table(['run','전체 n','분기 날짜 확인 n','분기 미래/확인 [95%]','분기 미확인 n','연간 날짜 확인 n','연간 미래/확인 [95%]','연간 미확인 n'],[
       [rid,len(g),int(g.dated.sum()),pct(int(g.future.sum()),int(g.dated.sum())),int((~g.dated).sum()),int(g.annual_dated.sum()),pct(int(g.annual_future.sum()),int(g.annual_dated.sum())),int((~g.annual_dated).sum())] for rid,g in z.groupby('run_id')]),
      '## 9. 재현·검증',
      '- 실행: `python -B research/handoff/code_20261020_fin_pit_audit.py`. numpy·pandas·scipy 필요. 실행 제한 시간 가드 포함. 운영 모듈 import 없이 필요한 순수 함수만 AST로 추출했다. 임시 대용량 파일·새 DB·수집·외부 호출 없음. 재실행은 20261019로 run/가격 상한을 고정하지만 기존 DB가 정정으로 덮어써지면 결과도 바뀔 수 있다.',
      f'- 검증: stage3 run×ticker 및 earnings_q 기본키 중복 없음; join many_to_one/one_to_one 검증; 표본 20종목·분위당 4건 확인; 독립 scipy 상관과 순위상관 일치, 정본 model_ic의 n·평균·95% 구간 반올림 일치. 분모 /{denom}은 DB distinct model_id 실측.',
      f'- 표본 (run,ticker) SHA256: `{hashlib.sha256("|".join(sample.run_id+":"+sample.ticker).encode()).hexdigest()}`.',
      f'- v30 유효 IC 앵커 SHA256: `{hashlib.sha256("|".join(base.index).encode()).hexdigest()}`.']
    assert before==[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths], 'Input DB changed during audit'
    sec += ['- 읽은 4개 DB의 실행 전후 크기·수정시각 동일. 전체 내용 해시를 검증했다는 뜻은 아니다. 생성 파일은 이 REPLY와 동반 코드뿐이며 운영·점수·판정·docs·worklog는 수정하지 않았다.']
    guard()
    OUT.write_text('\n\n'.join(sec)+'\n',encoding='utf-8')
    print('SAMPLE',sample[['run_id','ticker','quintile','fiscal','amend','q_state']].to_string(index=False),flush=True)
    print('WROTE',OUT,OUT.stat().st_size,flush=True)


if __name__=='__main__':
    main()
