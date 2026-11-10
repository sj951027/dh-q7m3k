"""Post-calculation comparison only; run after compute.py a has finished."""
from pathlib import Path
import numpy as np
import pandas as pd
from code_20261110_first_week_compute import OUT, ROOT, guard, save, metadata

guard()
ours = pd.read_csv(OUT / 'A_summary.csv')
days = pd.read_csv(OUT / 'A_days.csv')
ref = pd.read_csv(ROOT / 'research/out_first_week/by_model.csv')
comp = ours.merge(ref, on='model', suffixes=('_ours','_ref'), validate='one_to_one')
for our, theirs in [('n_ours','n_ref'),('up5_ours','up5_ref'),('baseline','기준율'),('diff','차'),('excess','초과5'),('path5','경로5')]:
    comp['delta_'+our] = comp[our] - comp[theirs]

audit = []
for mid, g in days.groupby('model'):
    rng = np.random.default_rng(7)
    rr = ref.set_index('model').loc[mid]
    rec = dict(model=mid)
    for col, lcol, hcol in [('up5','up5하한','up5상한'), ('diff','차하한','차상한'), ('excess','초과하한','초과상한'), ('path5','경로하한','경로상한')]:
        x = g[col].to_numpy() / 100
        bs = np.array([rng.choice(x,len(x)).mean() for _ in range(2000)])
        lo, hi = np.percentile(bs,[2.5,97.5])*100
        rec.update({col+'_aligned_lo':lo, col+'_aligned_hi':hi,
                    col+'_error_lo':lo-rr[lcol], col+'_error_hi':hi-rr[hcol]})
    audit.append(rec)
save(comp,'A_comparison'); save(pd.DataFrame(audit),'A_rng_audit')
maxmeans = float(comp.filter(regex='^delta_').abs().max().max())
maxci = float(pd.DataFrame(audit).filter(regex='_error_').abs().max().max())
metadata('comparison_meta', dict(max_abs_point_difference=maxmeans,
                               max_abs_CI_difference_after_rng_alignment=maxci,
                               note='Independent primary CIs reset RNG per statistic; original advances up/diff/excess/path.'))
print('max point difference',maxmeans,'aligned CI difference',maxci)
print(comp[['model','diff_lo','차하한','diff_hi','차상한']].to_string(index=False))
