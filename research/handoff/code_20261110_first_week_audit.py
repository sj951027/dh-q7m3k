"""Read-only sample and statistical consistency checks for this reproduction."""
import json
import numpy as np
import pandas as pd
from code_20261110_first_week_compute import OUT, ROOT, guard, metadata, safe_lb

guard()
p = pd.read_pickle(ROOT / 'research/out_early_rise_scan/panel.pkl')
old = dict(rows=len(p), anchors=int(p.t.nunique()), run_min=str(p.run_id.min()),run_max=str(p.run_id.max()),
           T1_rows=int(p.T1.notna().sum()),T4_rows=int(p.T4.notna().sum()),
           top10_rows=int(p.in_v30_top10.sum()), duplicates=int(p.duplicated(['run_id','ticker']).sum()))
print('Original panel', json.dumps(old,ensure_ascii=False))
new = json.loads((OUT / 'D_actual_meta.json').read_text(encoding='utf-8'))
print('Rebuilt sample',json.dumps(new['samples'],ensure_ascii=False))
a = pd.read_csv(OUT / 'A_summary.csv')
assert len(a)==26 and a.model.is_unique
assert ((a.up5>=0)&(a.up5<=100)).all()
assert ((a.path5>=0)&(a.path5<=100)).all()
assert np.allclose(a.up5-a.baseline,a['diff'])
b = pd.read_csv(OUT / 'B_summary.csv')
d = pd.read_csv(OUT / 'D_actual_summary.csv')
dp = pd.read_csv(OUT / 'D_proxy_summary.csv')
assert len(b)==24 and b['var'].nunique()==8
assert len(d)==184 and d['var'].nunique()==92
assert len(dp)==40 and dp['var'].nunique()==20
for frame in [b,d,dp]:
    finite=frame['mean'].notna()
    assert frame.loc[finite,'mean'].abs().le(1+1e-12).all()
    assert (frame.loc[finite,'lo']<=frame.loc[finite,'hi']).all()
metadata('audit_meta',dict(original_panel=old, rebuilt=new['samples'], checks='26 models; 8/92/20 variables; rates/ranges/paired differences passed'))
print('Consistency checks passed')

# Check the rebuilt first-round sample against the available original panel.
# This audit reads it only after the new path scan has completed.
lb = safe_lb()
original_load = lb.load_ohlcv
def cutoff_load():
    c,m = original_load()
    return c.loc[:'20261106'],m
lb.load_ohlcv = cutoff_load
source_path = ROOT / 'research/early_rise_scan_20261108.py'
source = source_path.read_text(encoding='utf-8-sig')
prefix = source[:source.index('S3.to_pickle')]
prefix = prefix.replace('OUT = HERE / "out_early_rise_scan"; OUT.mkdir(exist_ok=True)', 'OUT = HANDOFF_OUT')
prefix = prefix.replace("WHERE run_id>='20260602'", "WHERE run_id>='20260602' AND run_id<='20261106'")
ns=dict(__file__=str(source_path),HANDOFF_OUT=OUT)
exec(compile(prefix,'sample_audit_readonly','exec'),ns)
key=['run_id','ticker']
oldp=p.set_index(key).sort_index()
newp=ns['S3'].set_index(key).sort_index()
assert oldp.index.equals(newp.index)
diffs={}
for col in ns['VARS']+['T4','in_v30_top10','t','j']:
    a,b=oldp[col].to_numpy(float),newp[col].to_numpy(float)
    neq=~np.isclose(a,b,rtol=1e-12,atol=1e-12,equal_nan=True)
    if neq.any(): diffs[col]=int(neq.sum())
metadata('sample_audit_meta',dict(same_row_keys=True,compared_rows=len(oldp),compared_variables=len(ns['VARS']),differences=diffs))
print('Full sample/feature comparison',json.dumps(diffs,ensure_ascii=False))
