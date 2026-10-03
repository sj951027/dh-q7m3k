"""Additional declared research tests, see EXTENSIONS.md. Offline, research output only."""
import sys
sys.dont_write_bytecode=True
import numpy as np,pandas as pd,sqlite3,json
from code_target20_20261003 import Study,OUT,ROOT,SEED,rank,rolling,lag,returns,summarize,log,interval,block_idx

def add_rule(s,name,score,mask):
    s.rules[name]=score;s.masks[name]=mask;s.picks[name]=[]
    for t in range(s.T):
        ix=np.where(mask[t]&np.isfinite(score[t]))[0]
        s.picks[name].append(ix[np.argsort(-score[t,ix],kind='stable')[:10]])

def labels(s):
    y1=np.full((s.T,s.N),np.nan,dtype=np.float32);y2=y1.copy()
    for t in range(s.start,s.T-20):
        path,filled=s.paths(t,20)
        hit=path[-1]-.005>=.2
        good=(path[0]>0)&(path.min(axis=0)>=-.1)&((path>0).mean(axis=0)>=.8)&hit
        valid=s.ok[t]&filled
        y1[t,valid]=hit[valid];y2[t,valid]=good[valid]
    return {'hit':y1,'smooth':y2}

def machine_learning(s):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    from threadpoolctl import threadpool_limits
    featnames=list(s.R)
    X=np.stack([s.R[k] for k in featnames],axis=-1).astype(np.float32)
    X=np.nan_to_num(X,nan=.5)
    Y=labels(s);predictions={f'ml_{target}_{kind}':np.full((s.T,s.N),np.nan,dtype=np.float32) for target in Y for kind in ('logit','boost')}
    audit=[]
    for month in sorted(set(x[:6] for x in s.d if x>='20250101')):
        te=np.where(np.char.startswith(s.d,month))[0];first=te[0]
        trdays=np.array([t for t in range(s.start,first-19,5) if t>=first-252])
        if len(trdays)<20:continue
        trainmask=np.isfinite(Y['hit'][trdays]);xt=X[trdays][trainmask];xtest=X[te].reshape(-1,len(featnames))
        assert max(trdays)+20<=first
        for target,yy in Y.items():
            yt=yy[trdays][trainmask]
            for kind in ('logit','boost'):
                model=LogisticRegression(C=1.,max_iter=300,solver='lbfgs') if kind=='logit' else HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=7,learning_rate=.05,l2_regularization=10,early_stopping=False,random_state=SEED)
                with threadpool_limits(limits=2):
                    model.fit(xt,yt);pp=model.predict_proba(xtest)[:,1].reshape(len(te),s.N)
                name=f'ml_{target}_{kind}';predictions[name][te]=pp
                audit.append(dict(month=month,rule=name,train_n=len(yt),train_dates=len(trdays),last_label_date=s.d[max(trdays)+20],first_test_date=s.d[first],train_positive=float(yt.mean())))
        log('ML_MONTH',dict(month=month,train_n=len(xt)))
    for name,pred in predictions.items():add_rule(s,name,pred,s.ok&np.isfinite(pred))
    np.savez_compressed(OUT/'ml_predictions.npz',**predictions)
    pd.DataFrame(audit).to_csv(OUT/'ml_training_audit.csv',index=False,encoding='utf-8-sig')
    calibration=[]
    for name,pred in predictions.items():
        label=Y['smooth' if '_smooth_' in name else 'hit']
        for year in ('2025','2026'):
            valid=np.isfinite(pred)&np.isfinite(label)&np.char.startswith(s.d,year)[:,None]
            pp=pred[valid];yy=label[valid]
            for left,right in [(0,.1),(.1,.2),(.2,.3),(.3,.5),(.5,1.01)]:
                m=(pp>=left)&(pp<right)
                if m.sum():calibration.append(dict(rule=name,year=year,lo=left,hi=right,n=int(m.sum()),forecast=float(pp[m].mean()),actual=float(yy[m].mean())))
    pd.DataFrame(calibration).to_csv(OUT/'ml_calibration.csv',index=False,encoding='utf-8-sig')

def extra_rules(s):
    con=sqlite3.connect(f'file:{ROOT.parent/"dh-q7m3k-data/ohlcv.db"}?mode=ro',uri=True)
    ev=pd.read_sql_query('SELECT ticker,rcept_dt,event_type,report_nm FROM dart_events',con)
    flow=pd.read_sql_query('SELECT ticker,date,foreign_net_val,inst_net_val FROM daily_flows',con);con.close()
    ti={k:i for i,k in enumerate(s.tick)};buy=np.zeros_like(s.ok);dil=buy.copy()
    ev=ev[~ev.report_nm.str.contains('정정',na=False)]
    for rec in ev.itertuples():
        if rec.ticker not in ti:continue
        t=np.searchsorted(s.d,rec.rcept_dt,side='right');j=ti[rec.ticker]
        if rec.event_type=='buyback':buy[t:min(t+5,s.T),j]=True
        if rec.event_type in ('paid_in','cb','bw','eb','paid_bonus_mix','reduction','buyback_sell'):dil[t:min(t+60,s.T),j]=True
    strong=s.rules['highbeta_high']
    add_rule(s,'buyback5_relative',s.rules['relative_high'],s.ok&buy)
    add_rule(s,'highbeta_no_dilution',strong,s.ok&~dil)
    net=np.full((s.T,s.N),np.nan)
    for rec in flow.itertuples():
        if rec.ticker in ti and rec.date in s.di:
            net[s.di[rec.date],ti[rec.ticker]]=rec.foreign_net_val+rec.inst_net_val
    intensity=lag(rolling(net,5,5,'sum'))/rolling(s.amt,20,15)
    rflow=rank(intensity,s.ok)
    add_rule(s,'highbeta_flow_positive',strong,s.ok&(intensity>0))
    add_rule(s,'highbeta_plus_flow',strong+rflow,s.ok&np.isfinite(rflow))
    bull=s.idx>rolling(s.idx,60)
    add_rule(s,'highbeta_market60_cash',strong,s.ok&bull[:,s.mi])
    # Entry restraint is a scenario applied after selection, not hindsight filtering/replacement.
    log('EXTRA_DATA',dict(events=len(ev),flow_rows=len(flow),flow_start=flow.date.min(),flow_end=flow.date.max()))

def stress_tables(df,td,s):
    base=df[(df.h==20)&(df.date>='20250101')].copy();tr=td[td.date>='20250101'].copy()
    rows=[]
    for name,g in tr.groupby('rule'):
        b=base[base.rule==name];dates=b.date.tolist();bydate=g.groupby('date')
        for scenario in ('base','cost1','gap10_cash','missing_exit_loss','top5_removed'):
            x=g.copy()
            if scenario=='cost1':x['ret']-=.5
            if scenario=='gap10_cash':x.loc[x.gap.abs()>=10,'ret']=0
            if scenario=='missing_exit_loss':x.loc[x.exit_missing,'ret']=-100.5
            top=x.groupby('ticker').ret.sum().nlargest(5).index
            if scenario=='top5_removed':x.loc[x.ticker.isin(top),'ret']=0
            daily=x.groupby('date').ret.sum().reindex(dates,fill_value=0)/10
            rows.append(dict(rule=name,scenario=scenario,n_dates=len(daily),ret=float(daily.mean()),ci_lo=interval(daily,20)[0],ci_hi=interval(daily,20)[1],top5=';'.join(top) if scenario=='top5_removed' else ''))
        # Realizable terminal target requires nonzero exit volume and not locked at lower limit.
        tt=np.array([s.di[d] for d in g.date]);jj=np.array([list(s.tick).index(t) for t in g.ticker])
        exit_t=tt+20;zero=s.v[exit_t,jj]<=0
        lockedlow=(s.h[exit_t,jj]==s.l[exit_t,jj])&(s.c[exit_t,jj]/s.c[exit_t-1,jj]-1<=-.295)
        rows.append(dict(rule=name,scenario='exit_executability',n_dates=len(dates),ret=np.nan,exit_zero=int(zero.sum()),exit_lockedlower=int(lockedlow.sum()),sellable_hit_rate=float((g.hit.to_numpy()&~zero&~lockedlow).mean())))
    pd.DataFrame(rows).to_csv(OUT/'stress.csv',index=False,encoding='utf-8-sig')
    # Finite-family max-statistic via centered joint date-block bootstrap, same date resamples.
    a=base.pivot(index='date',columns='rule',values='excess').sort_index()
    a=a.drop(columns=['universe'],errors='ignore');v=a.to_numpy();v=np.nan_to_num(v,nan=0)
    ids=block_idx(len(a),20,2000);delta=v[ids].mean(axis=1)-v.mean(axis=0)
    sd=delta.std(axis=0);sd=np.maximum(sd,1e-10)
    maximum=np.max(delta/sd,axis=1)
    stats=v.mean(axis=0)/sd
    tab=pd.DataFrame({'rule':a.columns,'excess_mean':v.mean(axis=0),'maxT_p':[(1+(maximum>=x).sum())/2001 for x in stats]})
    tab.to_csv(OUT/'multiple_comparison.csv',index=False,encoding='utf-8-sig')

def main():
    s=Study();s.features();s.choose()
    # All original families are checked, not just those which looked good.
    dclose,tclose=s.evaluate(close_entry=True,suffix='_close')
    summarize(dclose,'summary_close.csv');dclose.to_csv(OUT/'daily_close.csv',index=False,encoding='utf-8-sig')
    dnew,tnew=s.evaluate(suffix='_new20',cooldown=20)
    summarize(dnew,'summary_new20.csv');tnew.to_parquet(OUT/'trades_new20.parquet',index=False)
    dliq,tliq=s.evaluate(suffix='_amt50',liq=5e9)
    summarize(dliq,'summary_amt50.csv')
    machine_learning(s);extra_rules(s)
    names=[n for n in s.rules if n.startswith('ml_') or n not in ['control_amount','control_highvol','control_price4','relative_high','breakout20_volume','contraction_breakout','trend_pullback','strong_volume_day','smooth_momentum','risk_adjusted_mom','defensive_high','highbeta_high','acceleration_volume','oversold_reclaim','gap_continuation']]
    da,ta=s.evaluate(only=names)
    # Keep the full calendar, including cash before inputs exist. For flows, use
    # summary_flow_common.csv from diagnostics; pooled 2025-26 cash dilutes returns.
    da=da[da.date>='20250101'];ta=ta[ta.date>='20250101']
    da.to_csv(OUT/'daily_additional.csv',index=False,encoding='utf-8-sig');ta.to_parquet(OUT/'trades_additional.parquet',index=False)
    sm=summarize(da,'summary_additional.csv')
    log('ADDITIONAL',sm[(sm.h==20)&(sm.period=='2025-26')][['rule','n_picks','ret','excess','hit_rate','joint_rate','first_up','mean_mdd','down_index_excess','up_index_excess']].to_dict('records'))
    base=pd.read_csv(OUT/'daily_results.csv',dtype={'date':str});bt=pd.read_parquet(OUT/'trades20.parquet')
    stress_tables(pd.concat([base,da]),pd.concat([bt,ta]),s)
    current=[]
    for name in names:
        for k,j in enumerate(s.picks[name][-1],1):current.append(dict(asof=s.d[-1],rule=name,rank=k,ticker=s.tick[j],market=s.mk[j],close=s.c[-1,j],research_score=s.rules[name][-1,j]))
    pd.DataFrame(current).to_csv(OUT/'latest_additional_candidates.csv',index=False,encoding='utf-8-sig')
    log('DONE','extensions')

if __name__=='__main__':main()
