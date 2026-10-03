"""Final research diagnostics. Reads raw panel and research outputs; writes research only."""
import sys
sys.dont_write_bytecode=True
import numpy as np,pandas as pd,json
from code_target20_20261003 import Study,OUT,ROOT,block_idx,interval,summarize,log
from code_target20_extensions import add_rule

s=Study();s.features()
mask=s.ok&(s.feats['volume_ratio']>=2)&(np.abs(s.r)<=.03)
add_rule(s,'quiet_volume',s.R['volume_ratio'],mask)
add_rule(s,'quiet_volume_relative',s.R['volume_ratio']+s.R['rs60'],mask)
dd,tt=s.evaluate(only=['quiet_volume','quiet_volume_relative'])
dd.to_csv(OUT/'daily_quiet.csv',index=False);tt.to_parquet(OUT/'trades_quiet.parquet',index=False)
summarize(dd,'summary_quiet.csv')
base=pd.read_csv(OUT/'daily_results.csv',dtype={'date':str})
extra=pd.read_csv(OUT/'daily_additional.csv',dtype={'date':str})
df=pd.concat([base,extra,dd],ignore_index=True)
df=df[(df.h==20)&(df.date>='20250101')]
tr=pd.concat([pd.read_parquet(OUT/'trades20.parquet'),pd.read_parquet(OUT/'trades_additional.parquet'),tt],ignore_index=True)
tr=tr[tr.date>='20250101']
rows=[]
for rule,g in df.groupby('rule'):
 g=g.sort_values('date');ix=block_idx(len(g),20)
 row={'rule':rule,'n_dates':len(g),'basket_hit20':float((g.ret>=20).mean()),'basket_loss':float((g.ret<0).mean())}
 for col in ['hit_rate','joint_rate','first_up']:
  numerator=(g[col].fillna(0)*g.n_filled).to_numpy();den=g.n_filled.to_numpy()
  estimates=numerator[ix].sum(axis=1)/np.maximum(den[ix].sum(axis=1),1)
  row[col+'_lo'],row[col+'_hi']=np.quantile(estimates,[.025,.975])
 sub=tr[tr.rule==rule];row['unique_tickers']=sub.ticker.nunique()
 rows.append(row)
pd.DataFrame(rows).to_csv(OUT/'rate_intervals.csv',index=False)
flow_names=['highbeta_flow_positive','highbeta_plus_flow']
flow_start=max(df[(df.rule==n)&(df.n_filled>0)].date.min() for n in flow_names)
common=df[(df.date>=flow_start)&df.rule.isin(flow_names+['highbeta_high','control_amount','universe'])]
summarize(common,'summary_flow_common.csv')
log('FLOW_COMMON',{'start':flow_start,'end':common.date.max(),'dates':common.date.nunique()})
pivot=df.pivot(index='date',columns='rule',values='ret')
pairs=[]
for a,b in [('highbeta_high','control_amount'),('highbeta_market60_cash','highbeta_high'),('ml_smooth_boost','control_amount'),('quiet_volume_relative','control_amount')]:
 v=(pivot[a]-pivot[b]).dropna();lo,hi=interval(v,20);pairs.append(dict(a=a,b=b,n=len(v),difference=v.mean(),lo=lo,hi=hi))
pd.DataFrame(pairs).to_csv(OUT/'paired_differences.csv',index=False)
# Independent raw-path check, rather than calling Study.paths/evaluate.
rng=np.random.default_rng(20261003);sample=tr.sample(n=400,random_state=20261003);errors=[]
for row in sample.itertuples():
 t=s.di[row.date];j=np.where(s.tick==row.ticker)[0][0]
 price=s.o[t+1,j];cl=pd.Series(s.c[:t+21,j]).ffill().to_numpy()[t+1:t+21]
 rel=cl/price-1;profit=(cl[-1]/price-1-.005)*100
 peak=np.maximum.accumulate(np.r_[price,cl])[1:];mdd=np.min(cl/peak-1)*100
 assert np.isclose(profit,row.ret,atol=1e-8,equal_nan=True)
 assert np.isclose(mdd,row.mdd,atol=1e-8,equal_nan=True)
 assert bool(rel[0]>0)==row.first_up
 assert bool(rel[-1]-.005>=.2)==row.hit
 assert bool(rel[-1]-.005>=.2 and rel.min()>=-.1 and (rel>0).mean()>=.8 and rel[0]>0)==row.joint
 errors.append(abs(profit-row.ret))
audit=pd.read_csv(OUT/'ml_training_audit.csv');assert (audit.last_label_date<=audit.first_test_date).all()
# Both readings of 'next-day rise', with the chosen open entry kept unchanged.
up=[]
for rule,sub in tr.groupby('rule'):
 prev=[]
 for row in sub.itertuples():
  t=s.di[row.date];j=np.where(s.tick==row.ticker)[0][0];prev.append(s.c[t+1,j]>s.c[t,j])
 up.append(dict(rule=rule,n=len(prev),next_close_above_signal_close=np.mean(prev)))
pd.DataFrame(up).to_csv(OUT/'next_day_alternative.csv',index=False)
checks=dict(raw_path_checks=400,max_return_error=max(errors),ml_month_models=len(audit),all_labels_finished=True,flow_common_start=flow_start)
(OUT/'verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8');log('VERIFIED',checks)
# Static, exportable research chart; all axes explicitly identify stock-path risk.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.family']='Malgun Gothic';plt.rcParams['axes.unicode_minus']=False
summ=pd.concat([pd.read_csv(OUT/'summary.csv'),pd.read_csv(OUT/'summary_additional.csv'),pd.read_csv(OUT/'summary_quiet.csv')])
names={'universe':'전체 후보','control_amount':'거래대금 상위','highbeta_high':'고베타·고점 근접','control_price4':'가격 4요소','defensive_high':'방어·고점 근접','ml_smooth_boost':'목표 직접 학습','quiet_volume_relative':'조용한 거래량 증가'}
q=summ[(summ.h==20)&(summ.period=='2025-26')&summ.rule.isin(names)]
fig,ax=plt.subplots(figsize=(10,6));
for row in q.itertuples():
 ax.scatter(-row.mean_mdd,row.hit_rate*100,s=85);ax.annotate(names[row.rule],(-row.mean_mdd,row.hit_rate*100),xytext=(6,6),textcoords='offset points',fontsize=10)
ax.set(xlabel='종목별 20일 경로의 평균 최대 낙폭 크기 (%) — 왼쪽일수록 작음',ylabel='20일 종료 수익 +20% 이상 비율 (%)',title='급등 적중률을 높일수록 중간 낙폭도 커졌다\n2025–26 관측 · 다음날 시가 · 왕복 비용 0.5%')
ax.grid(alpha=.2);ax.set_xlim(0,32);ax.set_ylim(0,32);fig.tight_layout();fig.savefig(OUT/'risk_vs_hit.png',dpi=160);plt.close(fig)
log('DONE','diagnostics')
