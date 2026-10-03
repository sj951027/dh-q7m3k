"""Common-calendar regime comparison and exploratory simultaneous comparison."""
import sys
sys.dont_write_bytecode=True
import pandas as pd,numpy as np
from code_target20_20261003 import OUT,PANEL,block_idx
z=np.load(PANEL,allow_pickle=True);dates=z['dates'].astype(str);di={d:i for i,d in enumerate(dates)}
x=np.column_stack([pd.Series(z[k]).ffill().to_numpy() for k in ['kospi','kosdaq']])
df=pd.concat([pd.read_csv(OUT/f,dtype={'date':str}) for f in ['daily_results.csv','daily_additional.csv','daily_quiet.csv']]);df=df[(df.h==20)&(df.date>='20250101')]
df['fixed_index']=[np.mean(x[di[d]+20]/x[di[d]]-1)*100 for d in df.date];rows=[]
for rule,g in df.groupby('rule'):
 for state,m in [('down',g.fixed_index<0),('up',g.fixed_index>0)]:
  q=g[m];rows.append(dict(rule=rule,state=state,n=len(q),ret=q.ret.mean(),index=q.fixed_index.mean(),difference=(q.ret-q.fixed_index).mean()))
pd.DataFrame(rows).to_csv(OUT/'common_regimes.csv',index=False)
full=df[~df.rule.isin(['universe','highbeta_flow_positive','highbeta_plus_flow'])].pivot(index='date',columns='rule',values='excess')
assert full.notna().all().all()
a=full.to_numpy();idx=block_idx(len(a),20);means=a.mean(axis=0);center=a-means
boot=center[idx].mean(axis=1);se=boot.std(axis=0,ddof=1);maxstat=(boot/se).max(axis=1)
p=(1+(maxstat[:,None]>=(means/se)[None,:]).sum(axis=0))/(len(maxstat)+1)
pd.DataFrame({'rule':full.columns,'excess_mean':means,'maxT_p':p,'family_size':len(full.columns)}).to_csv(OUT/'multiple_comparison_fullwindow.csv',index=False)
print('DONE common regimes and',len(full.columns),'full-window rules')
