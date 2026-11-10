"""Post-unblinding arithmetic, calendar and coverage audit."""
import json
import numpy as np
import pandas as pd
from code_20261110_event_common import ROOT,DATA,OUT,ro,meta,save

assert (OUT/'event_unblind_access.json').exists()
a=pd.read_csv(OUT/'event_days_blind.csv',dtype={'date':str})
b=pd.read_csv(ROOT/'research/out_event_after/days.csv',dtype={'date':str})
a=a[a.sensitivity=='original']
b=b[b.tag=='orig']
cmp=a.merge(b,left_on=['kind','date'],right_on=['cls','date'],how='outer',indicator=True,suffixes=('_ours','_claude'))
mapping={'events5':'n','events40':'n40','up5_ours':'up5_claude','base_up5':'base','up_diff':'d_up5','T1':'t1','T4':'t4','tail_diff':'d_tail','both_diff':'d_both'}
bad=np.zeros(len(cmp),bool)
for x,y in mapping.items():
    left,right=cmp[x],cmp[y]
    if x=='events40':
        left,right=left.fillna(0),right.fillna(0)
    cmp['delta_'+x]=left-right
    bad|=~np.isclose(left,right,atol=1e-10,rtol=1e-10,equal_nan=True)
save(cmp[bad],'event_differing_days')
print(cmp[bad][['kind','cls','date','_merge']+['delta_'+k for k in mapping]].to_string(index=False))
con=ro(DATA/'ohlcv.db')
cal=[str(x[0]) for x in con.execute('SELECT DISTINCT date FROM daily_ohlcv ORDER BY date')]
ev=pd.read_sql("SELECT event_type,report_nm,rcept_dt,ticker FROM dart_events WHERE rcept_dt<?",con,params=[cal[0]])
print('Pre-calendar events',len(ev),'before',cal[0])
cov={}
for tb in ['daily_ohlcv','daily_flows','short_flows','dart_events','universe_events']:
    col='rcept_dt' if tb=='dart_events' else 'date'
    cov[tb]=dict(zip(['rows','dates','first','last'],con.execute(f'SELECT COUNT(*),COUNT(DISTINCT {col}),MIN({col}),MAX({col}) FROM {tb}').fetchone()))
cov['maturity']={'latest_price':cal[-1],'last_signal_h5':cal[-7],'last_signal_h40':cal[-42]}
cov['pre_calendar_events']=len(ev)
ov=con.execute('SELECT COUNT(*) FROM daily_ohlcv a JOIN daily_ohlcv_extra b ON a.ticker=b.ticker AND a.date=b.date').fetchone()[0]
cov['overlap_main_extra']=ov
cov['positive_volume_suspended_entry']=con.execute('SELECT COUNT(*) FROM daily_ohlcv WHERE volume>0 AND is_suspended!=0').fetchone()[0]
con.close()
meta('coverage_audit',cov)
meta('event_difference_audit',dict(differing_days=int(bad.sum()),dates=sorted(cmp.loc[bad,'date'].unique()),
                                  max_nonfirst_difference=float(cmp[cmp.date!=cal[0]].filter(regex='^delta_').abs().max().max())))
print(json.dumps(cov,ensure_ascii=False,indent=2))
