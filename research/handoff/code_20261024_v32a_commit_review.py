"""142077b 독립 검토: 운영 파일 무수정, DB mode=ro, 페이지 출력은 임시 폴더.
실행: python -B research/handoff/code_20261024_v32a_commit_review.py
"""
import os, sys, sqlite3, subprocess, types, hashlib, json, tempfile, warnings
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore', category=RuntimeWarning)
CONNECT = sqlite3.connect
def ro(db, *args, **kwargs):
    s = str(db)
    if not s.startswith('file:'):
        s = 'file:' + Path(s).resolve().as_posix()
    s = s.split('?')[0] + '?mode=ro'
    kwargs['uri'] = True
    c = CONNECT(s, *args, **kwargs)
    c.execute('PRAGMA query_only=ON')
    return c
sqlite3.connect = ro
import v3_rescore as cur
import build_v32a_page as page
import leaderboard as lb
import freeze_scores as freeze
old = types.ModuleType('v3_before')
old.__file__ = str(ROOT / 'v3_rescore.py')
exec(compile(subprocess.check_output(['git','show','142077b~1:v3_rescore.py']).decode('utf-8'), old.__file__, 'exec'), old.__dict__)
with ro(ROOT/'history.db') as c:
    data = pd.read_sql('SELECT * FROM stage3_final', c)
    print('DB models', c.execute('SELECT model_id,count(*),min(run_id),max(run_id) FROM v3_scores GROUP BY model_id').fetchall())
data['run_id'] = data.run_id.astype(str)
hash_ = lambda s: hashlib.sha256(json.dumps(s,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()[:12]
print('hashes', {m: (hash_(s),hash_(cur.MODELS[m])) for m,s in old.MODELS.items()})
runs = sorted(data.run_id.unique()); cells = rows = 0; bad = []; breaches = []
for mid in old.MODELS:
    subset = data if mid == 'v30' else data[data.run_id.isin(runs[-10:])]
    for (rid,mkt), sub in subset.groupby(['run_id','market']):
        a=old.rescore(sub.copy(),rid,mkt,spec=old.MODELS[mid])
        b=cur.rescore(sub.copy(),rid,mkt,spec=cur.MODELS[mid])
        try: pd.testing.assert_frame_equal(a,b,check_exact=True)
        except AssertionError as e: bad.append((mid,rid,mkt,str(e)[:100]))
        cells+=1; rows+=len(a)
        if mid=='v30':
            w=cur.rescore(sub.copy(),rid,mkt,spec=cur.MODELS['v32a'])
            amt=pd.to_numeric(w['amt_avg_1m_억'],errors='coerce'); mask=~(amt<=amt.median())
            assert (w.loc[mask,'final_score_v3']==-999).all()
            assert (w.loc[mask,'entry_score']==-999).all()
            assert (~w.loc[mask,'main_candidate']).all()
            keep=w.loc[~mask].set_index('ticker').sort_index()
            ref=b.set_index('ticker').loc[keep.index]
            pd.testing.assert_frame_equal(keep,ref,check_exact=True)
            top=page.top(w); out=~(pd.to_numeric(top['amt_avg_1m_억'])<=amt.median())
            if out.any(): breaches.append((rid,mkt,len(sub),int(out.sum()),int((w.final_score_v3>-999).sum())))
print('ZERO_DIFF',cells,rows,'bad',bad,flush=True)
print('TOP10_CAP_BREACHES',len(breaches),breaches[:20],flush=True)

# 합성: 실측 stage3 한 행을 복제해 정상·동점·결측·하드 제외/비연속 인덱스.
seed=data.iloc[0].copy()
fake=pd.DataFrame([seed]*6).reset_index(drop=True)
fake['ticker']=[f'{n:06}' for n in range(6)]
fake['amt_avg_1m_억']=[1,2,2,3,np.nan,4]
fake['falling_knife']=0; fake['risk_level']='안전'; fake['ocf_pattern']='현금창출양호'
fake.index=[20,25,30,35,40,45]
with patch.object(cur,'attach_valuation',side_effect=lambda d,*a: d.assign(value_score=0.,value_source='UNAVAILABLE_OFFLINE')):
    w=cur.rescore(fake,'20261026','kospi',spec=cur.MODELS['v32a'])
    print('SYNTH_RULE',w[['ticker','amt_avg_1m_억','main_candidate','final_score_v3','grade','bucket']].to_dict('records'))
    print('SYNTH_TOP10',page.top(w).ticker.tolist())

# 페이지 함수 실제 호출, DB SQL 반환과 가격/게이트만 합성 주입. DB는 ro로만 열림.
def history(n=1, keep=True, one_market=False, missing_entry=False, weekend=False):
    dates=pd.bdate_range('2026-10-23', periods=n).strftime('%Y%m%d').tolist()
    rid='20261024' if weekend else '20261026'
    sc=[]
    for mkt in (['kospi'] if one_market else ['kospi','kosdaq']):
        for mid,tk in [('v32a','000001'),('v30','000002')]:
            sc.append(dict(run_id=rid,market=mkt,ticker=tk,model_id=mid,score=10.))
    prices=pd.DataFrame({'000001':np.linspace(100,120,n),'000002':np.full(n,100.)},index=dates)
    if missing_entry: prices.iloc[2 if not weekend else 1,0]=np.nan
    didx={d:i for i,d in enumerate(dates)}
    with patch.object(page.pd,'read_sql',return_value=pd.DataFrame(sc)), patch.object(lb,'load_ohlcv',return_value=(prices,None)), patch.object(lb,'build_gates',return_value=(set() if keep else {rid},set(),didx)), patch.dict(page.REG_DATE,{'v32a':'20261024' if weekend else '20261026'}):
        return page.d20_history('2026-10-26')

sample=data[data.run_id==runs[-1]].copy()
with tempfile.TemporaryDirectory(prefix='v32a_review_') as td:
    for label,kwargs in [('first',{'n':2}),('all_gated',{'n':2,'keep':False}),('mature',{'n':25}),('one_market',{'n':25,'one_market':True}),('entry_missing',{'n':25,'missing_entry':True}),('weekend',{'n':25,'weekend':True})]:
        hist,msg=history(**kwargs)
        print('HISTORY',label,hist.to_dict('records'),msg)
        with patch.object(cur,'load_runs',return_value=sample),patch.object(page,'d20_history',return_value=(hist,msg)),patch.object(page,'OUT',str(Path(td)/(label+'.html'))):
            try: page.main(); print('RENDER',label,'OK')
            except Exception as e: print('RENDER',label,type(e).__name__,str(e))
    with patch.object(page,'OUT',str(Path(td)/'real.html')):
        page.main()
    with patch.object(cur,'load_runs',return_value=data.iloc[:0]),patch.object(page,'d20_history',return_value=(None,'대기')),patch.object(page,'OUT',str(Path(td)/'empty.html')):
        try: page.main(); print('RENDER empty_stage3 OK')
        except Exception as e: print('RENDER empty_stage3',type(e).__name__,str(e))
    # 등록일 필터는 archive 탐색 자체에 없음(실제 적재/쓰기 실행하지 않음).
    ad=Path(td)/'v32a_archive'; ad.mkdir()
    (ad/'v32a_kospi_20261023.csv').write_text('ticker,final_score_v3\n000001,10\n')
    print('PRE_REG_ARCHIVE',[(p.name,r,m) for p,r,m in freeze._iter_archive_files(td,'v32a')], 'latest',freeze._latest_run(td,['v32a']))

raw=(ROOT/'run_all_and_diversify.bat').read_bytes()
print('BAT ascii',raw.isascii(),'CRLF',raw.count(b'\r\n'),'bareLF',raw.count(b'\n')-raw.count(b'\r\n'))
reg=json.loads((ROOT/'docs/models_registry.json').read_text(encoding='utf-8'))
print('REGISTRY v32a',reg.get('observe',{}).get('v32a'))
print('shadow_models',[m for m in cur.MODELS if m!='v30' and m not in cur.RETIRED])
print('freeze_models',[m for m in freeze.ARCHIVE_MAP if m not in cur.RETIRED])
exec(compile((ROOT/'tests/test_v3_models_rules.py').read_text(encoding='utf-8'),'tests/test_v3_models_rules.py','exec'),{'__file__':str(ROOT/'tests/test_v3_models_rules.py'),'__name__':'__review_test__'})
