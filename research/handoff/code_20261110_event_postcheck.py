"""Post-unblinding reconciliation only; preserves all blind outputs."""
import ast
import numpy as np
import pandas as pd
from code_20261110_event_common import ROOT,DATA,OUT,ro,save,meta,stat,tenyr

assert (OUT/'event_unblind_access.json').exists()
con=ro(DATA/'ohlcv.db')
px=pd.concat([pd.read_sql('SELECT ticker,date,close,volume,is_suspended FROM '+t,con)
              for t in ['daily_ohlcv_extra','daily_ohlcv']]).drop_duplicates(['ticker','date'],keep='last')
con.close()
C=px.pivot(index='date',columns='ticker',values='close').sort_index()
V=px.pivot(index='date',columns='ticker',values='volume').reindex_like(C)
S=px.pivot(index='date',columns='ticker',values='is_suspended').reindex_like(C)
R=C/C.shift(20)-1
ev=pd.read_csv(OUT/'event_records_blind.csv',dtype={'date':str,'ticker':str})
ev=ev[(ev.sensitivity=='original') & ev.kind.isin(['bb_trust_new','bb_trust_end','bb_direct']) & ev.T4.notna()]
rows=[]
for date,g in ev.groupby('date'):
    t=C.index.get_loc(date)
    ok=(C.iloc[t]>=1000)&(V.iloc[t]>0)&(V.iloc[t+1]>0)&(S.iloc[t]==0)&(S.iloc[t+1]==0)&C.iloc[t+1].gt(0)&C.iloc[t+6].notna()
    ok40=ok & C.iloc[t+41].notna()
    eligible20=ok & R.iloc[t].notna()
    # Missing R20 is NOT silently put into the outside-oversold group.
    if eligible20.sum()<300: continue
    osm=eligible20 & R.iloc[t].le(R.iloc[t,eligible20.to_numpy()].quantile(.2))
    ret=(C.iloc[t+41]/C.iloc[t+1]-1)*100
    for kind,gg in g.groupby('kind'):
        for level,mask in [('inside',osm),('outside',eligible20 & ~osm)]:
            bench=ok40 & mask
            selected=gg[gg.ticker.isin(C.columns[bench])]
            if bench.sum()<30 or selected.empty: continue
            rows.append(dict(kind=kind,date=date,level=level,events=len(selected),
                             T4_matched=selected.ret40.mean()-ret[bench].mean(),
                             T4_all=selected.ret40.mean()-ret[ok40].mean()))
days=pd.DataFrame(rows); save(days,'event_cells_matched_days_postcheck')
cells=[]
for (kind,level),g in days.groupby(['kind','level']):
    cells.append(dict(kind=kind,level=level,events=int(g.events.sum()),**stat(g.set_index('date').T4_matched)))
save(pd.DataFrame(cells),'event_cells_matched_postcheck')
print(pd.DataFrame(cells)[['kind','level','events','n','mean','lo','hi']].round(4).to_string(index=False),flush=True)

# Reproduce only the two pure summary functions, never the original module's IO.
source=ROOT/'research/event_after_20261110.py'
tree=ast.parse(source.read_text(encoding='utf-8-sig'))
pure=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['block_q','summarize']],type_ignores=[])
ns={'np':np,'pd':pd,'tenyr':tenyr,'CLASSES':['bb_trust_new','bb_trust_end','bb_direct','bb_sell','paid_in','cb','bonus','reduction'],'QC':[100*.05/16/2,100*(1-.05/16/2)]}
exec(compile(pure,str(source),'exec'),ns)
their_days=pd.read_csv(ROOT/'research/out_event_after/days.csv',dtype={'date':str,'month':str})
their_summary=pd.read_csv(ROOT/'research/out_event_after/summary.csv')
tenyr.reset_rng(7)
reproduced=ns['summarize'](their_days[their_days.tag=='orig'])
save(reproduced,'event_claude_rng_reproduced')
cols=['up5차','하한','상한','보정하한','보정상한','T1하한','T1상한','T4하한','T4상한']
delta=(reproduced.set_index('cls')[cols]-their_summary.set_index('cls')[cols]).abs().max().max()
meta('event_rng_audit',dict(max_abs_error=float(delta),note='Claude daily data, original summary call order; independent output unchanged'))
print('CI summary RNG max error',delta,flush=True)

con=ro(DATA/'earnings.db')
tables=[x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
schema={t:[x[1] for x in con.execute('PRAGMA table_info('+t+')')] for t in tables if t=='earnings_q'}
info={'schema':schema}
if 'earnings_q' in schema:
    info['rows']=con.execute('SELECT COUNT(*) FROM earnings_q').fetchone()[0]
    for name in ['rcept_dt','period','year','quarter','fetched_at']:
        if name in schema['earnings_q']:
            info[name]=con.execute(f'SELECT MIN({name}),MAX({name}),COUNT(DISTINCT {name}) FROM earnings_q').fetchone()
con.close()
meta('earnings_coverage_postcheck',info)
print(info)
