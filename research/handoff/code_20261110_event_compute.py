"""Independent event reproduction. Does not read Claude result/code files."""
import hashlib
import json
import numpy as np
import pandas as pd
from code_20261110_event_common import ROOT,DATA,OUT,ro,save,meta,now,stat

KINDS=['bb_trust_new','bb_trust_end','bb_direct','bb_sell','paid_in','cb','bonus','reduction']

def classify(events):
    kind=events.event_type.map({'buyback_sell':'bb_sell','paid_in':'paid_in','cb':'cb','bonus':'bonus','reduction':'reduction'})
    bb=events.event_type.eq('buyback')
    nm=events.report_nm.fillna('')
    new=bb & nm.str.contains('신탁계약체결',regex=False)
    end=bb & nm.str.contains('신탁계약해지',regex=False)
    assert not (new & end).any()
    kind.loc[new]='bb_trust_new'; kind.loc[end]='bb_trust_end'
    kind.loc[bb & ~new & ~end]='bb_direct'
    return kind

def main():
    start=now()
    c=ro(DATA/'ohlcv.db')
    # Table precedence: main daily OHLCV wins any duplicate ticker/date.
    query='SELECT ticker,date,close,volume,is_suspended FROM {}'
    mainpx=pd.read_sql(query.format('daily_ohlcv'),c)
    extra=pd.read_sql(query.format('daily_ohlcv_extra'),c)
    calendar=sorted(mainpx.date.unique())
    px=pd.concat([extra,mainpx],ignore_index=True).drop_duplicates(['ticker','date'],keep='last')
    events=pd.read_sql('SELECT rcept_no,rcept_dt,ticker,event_type,report_nm FROM dart_events',c)
    market=pd.read_sql("SELECT date,close FROM market_daily WHERE series='KOSPI'",c)
    assert not market.empty,'KOSPI series missing'
    c.close()
    def pivot(col): return px.pivot(index='date',columns='ticker',values=col).reindex(calendar)
    close=pivot('close'); volume=pivot('volume').reindex(columns=close.columns)
    suspension=pivot('is_suspended').reindex(columns=close.columns)
    dates=np.asarray(calendar); tick=list(close.columns); ti={k:j for j,k in enumerate(tick)}
    C=close.to_numpy(float); V=volume.to_numpy(float); S=suspension.to_numpy(float)
    R20=(close/close.shift(20)-1).to_numpy()
    kospi=market.drop_duplicates('date',keep='last').set_index('date').close.reindex(calendar)
    k20=kospi/kospi.shift(20)-1
    events['ticker']=events.ticker.astype(str).str.zfill(6)
    events['kind']=classify(events)
    events=events[events.kind.notna()].copy()
    events['correction']=events.report_nm.fillna('').str.startswith('[')
    # Do not map dates before the available price calendar onto its first day.
    events=events[(events.rcept_dt>=dates[0])&(events.rcept_dt<=dates[-1])].copy()
    events['t']=np.searchsorted(dates,events.rcept_dt.to_numpy())
    events=events[events.t<len(dates)]
    events['date']=dates[events.t.to_numpy()]
    events['j']=events.ticker.map(ti)
    evrecords=[]; funnel=[]
    for sensitivity in ['original','include_corrections']:
        ev=events[~events.correction].copy() if sensitivity=='original' else events.copy()
        before=ev.groupby('kind').size().to_dict()
        ev=ev.sort_values(['rcept_dt','rcept_no']).drop_duplicates(['kind','ticker','t'],keep='first')
        dedup=ev.groupby('kind').size().to_dict()
        for kind in KINDS:
            funnel.append(dict(sensitivity=sensitivity,kind=kind,original_rows=before.get(kind,0),dedup_rows=dedup.get(kind,0)))
        for t,g in ev.groupby('t'):
            if t+6>=len(dates): continue
            ok=(C[t]>=1000)&(V[t]>0)&(V[t+1]>0)&(S[t]==0)&(S[t+1]==0)&np.isfinite(C[t+1])&(C[t+1]>0)&np.isfinite(C[t+6])
            if not ok.any(): continue
            with np.errstate(invalid='ignore',divide='ignore'):
                ret5=C[t+6]/C[t+1]-1
            up5=ret5>0
            b5=ret5[ok].mean(); bu=up5[ok].mean()
            f40=np.full(len(tick),np.nan); ok40=np.zeros(len(tick),dtype=bool)
            b40=btail=bboth=np.nan
            oversold=np.full(len(tick),np.nan)
            if t+41<len(dates):
                ok40=ok & np.isfinite(C[t+41])
                with np.errstate(invalid='ignore',divide='ignore'):
                    f40=C[t+41]/C[t+1]-1
                if ok40.any():
                    b40=f40[ok40].mean(); btail=(f40[ok40]<=-.20).mean()
                    bboth=(up5[ok40] & ((f40[ok40]-b40)>0)).mean()
                    valid20=ok40 & np.isfinite(R20[t])
                    if valid20.any():
                        threshold=np.quantile(R20[t,valid20],.20)
                        oversold[valid20]=(R20[t,valid20]<=threshold).astype(float)
            kr=k20.iloc[t]
            regime='unknown' if not np.isfinite(kr) else ('A' if kr<=-.05 else ('D' if kr>.05 else 'BC'))
            for r in g.itertuples():
                if pd.isna(r.j): continue
                j=int(r.j)
                if not ok[j]: continue
                has40=bool(ok40[j])
                evrecords.append(dict(sensitivity=sensitivity,kind=r.kind,ticker=r.ticker,rcept_no=r.rcept_no,rcept_dt=r.rcept_dt,
                                      date=dates[t],t=t,entry_date=dates[t+1],exit5=dates[t+6],
                                      exit40=dates[t+41] if has40 else None,regime=regime,
                                      oversold=oversold[j] if has40 else np.nan,n_universe5=int(ok.sum()),n_universe40=int(ok40.sum()),
                                      up5=float(up5[j])*100,base_up5=bu*100,up_diff=(float(up5[j])-bu)*100,
                                      ret5=ret5[j]*100,T1=(ret5[j]-b5)*100,
                                      ret40=f40[j]*100 if has40 else np.nan,
                                      T4=(f40[j]-b40)*100 if has40 else np.nan,
                                      tail_diff=(float(f40[j]<=-.2)-btail)*100 if has40 else np.nan,
                                      both_diff=(float(up5[j] and f40[j]-b40>0)-bboth)*100 if has40 else np.nan))
    records=pd.DataFrame(evrecords)
    metrics=['up5','base_up5','up_diff','ret5','T1','ret40','T4','tail_diff','both_diff']
    daily=records.groupby(['sensitivity','kind','date'],as_index=False)[metrics].mean()
    daily=daily.merge(records.groupby(['sensitivity','kind','date']).agg(events5=('ticker','size'),events40=('T4','count')).reset_index())
    summary=[]
    for (sens,kind),g in daily.groupby(['sensitivity','kind']):
        row=dict(sensitivity=sens,kind=kind,events5=int(g.events5.sum()),events40=int(g.events40.sum()),days5=len(g),days40=int(g.T4.notna().sum()))
        for metric in metrics:
            result=stat(g.set_index('date')[metric])
            row.update({metric+'_'+k:v for k,v in result.items()})
        row['candidate']=bool(row['up_diff_lo']>5 and row['days5']>=200 and
                              row['up_diff_front']>0 and row['up_diff_back']>0 and
                              row['up_diff_blo']>0 and np.isfinite(row['T4_hi']) and row['T4_hi']>=0)
        summary.append(row)
        print(sens,kind,'days',len(g),'up difference',row['up_diff_mean'],'candidate',row['candidate'],flush=True)
    cells=[]
    original=records[records.sensitivity=='original']
    for kind in KINDS[:3]:
        for axis,levels in [('regime',['A','BC','D']),('oversold',[1.,0.])]:
            for level in levels:
                selected=original[(original.kind==kind)&(original[axis]==level)].dropna(subset=['T4'])
                s=selected.groupby('date').T4.mean()
                cells.append(dict(kind=kind,axis=axis,level=level,events=len(selected),**stat(s)))
    save(records,'event_records_blind'); save(daily,'event_days_blind')
    save(pd.DataFrame(summary),'event_summary_blind'); save(pd.DataFrame(cells),'event_cells_blind'); save(pd.DataFrame(funnel),'event_funnel_blind')
    filenames=['event_records_blind.csv','event_days_blind.csv','event_summary_blind.csv','event_cells_blind.csv','event_funnel_blind.csv']
    hashes={n:hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in filenames}
    meta('event_blind_saved',dict(started=start,completed=now(),claude_results_opened=False,files=hashes,
                                price_start=dates[0],price_end=dates[-1],calendar_days=len(dates),tickers=len(tick),
                                source_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                interpretation='main precedence; no forward fill; suspension t and t+1 must equal 0; horizon-specific universes; event-date regime; all-universe T4 baseline within subgroups',
                                time_exception='User explicitly confirmed batch finished and authorized proceeding during time restriction'))
    print('BLIND RESULTS SAVED',now(),flush=True)

from pathlib import Path
if __name__=='__main__': main()
