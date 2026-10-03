"""Read-only review evidence. No project imports, credentials, network or DB writes.
Run: python -X utf8 research/handoff/code_20261003_review.py
"""
import ast
import json
import sqlite3
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PTW = ROOT.parent / 'Position-Tracker-Web'

def function(path, name, ns, remove_imports=False):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    fn.decorator_list = []
    if remove_imports:
        fn.body = [n for n in fn.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), str(path), 'exec'), ns)
    return ns[name]

def ro(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)

def main():
    out = {}
    with ro(ROOT.parent / 'dh-q7m3k-data/ohlcv.db') as c:
        out['db'] = {}
        for t in ('daily_ohlcv', 'daily_ohlcv_extra', 'daily_flows', 'market_daily'):
            out['db'][t] = c.execute(f'SELECT count(*),min(date),max(date) FROM {t}').fetchone()
        base = {r[0] for r in c.execute('select distinct ticker from daily_ohlcv')}
        extra = {r[0] for r in c.execute('select distinct ticker from daily_ohlcv_extra')}
        out['tickers'] = {'base':len(base),'extra':len(extra),'overlap':len(base & extra)}
        out['extra_latest'] = c.execute('select maxdate,count(*) from (select ticker,max(date) maxdate from daily_ohlcv_extra group by ticker) group by maxdate').fetchall()
    with ro(ROOT / 'history.db') as c:
        out['latest_runs'] = c.execute('select run_id,market,stage1_count from runs order by run_id desc limit 4').fetchall()
        tickers = {str(r[0]) for r in c.execute("select distinct ticker from large_final where run_id>='20260806'")}
        out['large_coverage'] = {'tickers':len(tickers),'missing_base':len(tickers-base),'missing_union':len(tickers-base-extra)}
        import pandas as pd
        import numpy as np
        ns={'pd':pd,'np':np}
        scores=function(ROOT/'large_verdict.py','ls_t1_scores',ns)(c)
        scored=set(scores[scores.run_id>='20260806'].ticker)
        out['large_scored_coverage']={'tickers':len(scored),'missing_base':len(scored-base),'missing_union':len(scored-base-extra)}
        latest=scores[scores.run_id==scores.run_id.max()]
        out['latest_large_top10']={str(m):{'n':len(g.nlargest(10,'score')),'missing_base':len(set(g.nlargest(10,'score').ticker)-base)} for m,g in latest.groupby('market')}
    sb=json.loads((ROOT/'docs/scoreboard.json').read_text(encoding='utf-8'))
    out['scoreboard']={'asof':sb['asof'],'generated':sb['generated'],'models':len(sb['models']), 'ensemble':{k:sb['ensemble'][k] for k in ('members','fix')}}
    out['scoreboard']['periods']=[{'model':m['model'],'n_anchors':m['n_anchors'],'fix_n':(m.get('fix') or {}).get('n'),'now_n':(m.get('now') or {}).get('n'),'first':(m.get('fix') or {}).get('first'),'last':(m.get('fix') or {}).get('last')} for m in sb['models']]
    # Actual main(), with argparse and collector replaced. Never runs the collector.
    ns={'argparse':__import__('argparse'),'collect':lambda **kw:136,'status':lambda **kw:None}
    out['all_extra_failed_exit']=function(ROOT/'extra_ohlcv.py','main',ns)()
    # Execute the exact non-overlap guard with synthetic missing/one-observation evidence.
    tree=ast.parse((ROOT/'large_verdict.py').read_text(encoding='utf-8'))
    guard=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and 'no_st' in ast.unparse(n.test))
    out['nonoverlap_guard']=[]
    for st in ({'ic':None,'ci':[None,None],'n':0},{'ic':0.1,'ci':[0.1,0.1],'n':1}):
        ns={'no_st':st,'lab':'유의','why':'synthetic','no_n':1}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[guard],type_ignores=[])),'guard','exec'),ns)
        out['nonoverlap_guard'].append({'n':st['n'],'result':ns['lab']})
    # Actual summary function catches user delivery exception; actual cron _do still marks success.
    user=types.SimpleNamespace(telegram_chat_id=True,id='synthetic')
    db=types.SimpleNamespace(query=lambda _:types.SimpleNamespace(all=lambda:[user]),close=lambda:None)
    marks=[]
    def fail(*a): raise RuntimeError('synthetic delivery failure')
    ns={'User':object,'_send_evening_one':fail,'kv_get':lambda *a:None,'kv_set':lambda *a:marks.append(a),'print':lambda *a:None}
    summary=function(PTW/'app/compute.py','send_evening_summary',ns,True)
    ns2={'SessionLocal':lambda:db,'mode':'evening','compute_all':lambda *a,**k:None,
         'record_daily_snapshots':lambda *a:None,'record_signal_log':lambda *a:None,
         'send_evening_summary':summary,'kv_set':lambda *a:marks.append(a),
         'EVENING_OK_KEY':'evening_ok_at','_kst_now':lambda:__import__('datetime').datetime(2026,10,3,21)}
    function(PTW/'app/main.py','_do',ns2)()
    out['failed_summary_still_marked']=bool(marks)
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
