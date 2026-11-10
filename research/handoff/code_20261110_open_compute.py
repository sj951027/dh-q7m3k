"""Two separately preregistered single-variable checks, no combinations."""
import hashlib
import numpy as np
import pandas as pd
from code_20261110_event_common import ROOT,OUT,tenyr,save,meta,now,stat

def main():
    OUT.mkdir(exist_ok=True)
    frozen=OUT/'open_preregistered.md'
    if not frozen.exists():
        reply=ROOT/'research/handoff/REPLY_20261110_event_and_open_search.md'
        text=reply.read_text(encoding='utf-8')
        assert text.startswith('# ② 직접 계산 조건 — 계산 전 고정')
        assert '이하 결과는 계산 완료 후 채운다.' in text
        frozen.write_text(text,encoding='utf-8')
        meta('open_preregistered',dict(condition_sha256=hashlib.sha256(frozen.read_bytes()).hexdigest(),
                                      results_not_computed_yet=True,reference_reply=str(reply)))
    P=tenyr.load_panel()
    known=np.isfinite(P.R20)&(P.CU>=1000)&(P.VU>0)
    history=np.full(P.CU.shape,np.nan,dtype=np.float32)
    for i in range(P.N):
        m=known[i]
        if m.sum()<300: continue
        q=np.quantile(P.R20[i,m],.2)
        history[i,m]=(P.R20[i,m]<=q).astype(float)
    count=pd.DataFrame(history).rolling(20,min_periods=20).sum().to_numpy()
    ret=P.cu.pct_change(fill_method=None)
    positives=(ret>0).astype(float).where(ret.notna())
    consist=positives.rolling(126,min_periods=80).mean().to_numpy()
    rows=[]; skipped={'O1':0,'O2':0}
    for i in range(tenyr.START,P.N-tenyr.H-1,tenyr.STEP):
        e=P.CU[i+1]
        ok=np.isfinite(P.R20[i])&(P.VU[i]>0)&(P.VU[i+1]>0)&~P.PEN[i]&np.isfinite(e)&(e>0)&np.isfinite(P.CF[i+41])
        if ok.sum()<300: continue
        osmask=ok & (P.R20[i]<=np.quantile(P.R20[i,ok],.2))
        with np.errstate(divide='ignore',invalid='ignore'):
            r5=P.CF[i+6]/e-1; r40=P.CF[i+41]/e-1
        path=(P.CF[i+2:i+7]>=e).all(axis=0)
        up=r5>0
        for name,base,x in [('O1',osmask,count[i]),('O2',ok,consist[i])]:
            valid=base & np.isfinite(x)
            if base.sum()<50 or valid.sum()<50:
                skipped[name]+=1; continue
            q20,q80=np.quantile(x[valid],[.2,.8])
            if q20==q80:
                skipped[name]+=1; continue
            selected=valid & (x>=q80)
            if selected.sum()<10:
                skipped[name]+=1; continue
            assert np.isfinite(r5[ok]).all() and np.isfinite(r40[ok]).all()
            rows.append(dict(method=name,date=P.dates[i],n_all=int(ok.sum()),n_base=int(base.sum()),n_select=int(selected.sum()),
                             up5=up[selected].mean()*100,base_up5=up[base].mean()*100,
                             up_diff=(up[selected].mean()-up[base].mean())*100,
                             T1_net=(r5[selected].mean()-r5[ok].mean()-tenyr.COST)*100,
                             T4_net=(r40[selected].mean()-r40[ok].mean()-tenyr.COST)*100,
                             increment40=(r40[selected].mean()-r40[base].mean())*100,
                             ret40_net=(r40[selected].mean()-tenyr.COST)*100,
                             path_diff=(path[selected].mean()-path[base].mean())*100,
                             tail_diff=((r40[selected]<=-.2).mean()-(r40[base]<=-.2).mean())*100))
    days=pd.DataFrame(rows); summary=[]
    for name,g in days.groupby('method'):
        row=dict(method=name,n=len(g),first=g.date.min(),last=g.date.max(),skipped_days=skipped[name],
                 median_selected=float(g.n_select.median()),median_base=float(g.n_base.median()))
        for metric in ['up5','base_up5','up_diff','T1_net','T4_net','increment40','ret40_net','path_diff','tail_diff']:
            result=stat(g.set_index('date')[metric],split='20210101',alpha=.05/4)
            row.update({metric+'_'+k:v for k,v in result.items()})
        row['week_candidate']=bool(row['n']>=200 and row['up_diff_lo']>5 and row['up_diff_blo']>0 and
                                   row['up_diff_front']>0 and row['up_diff_back']>0 and row['T4_net_hi']>=0)
        row['forty_candidate']=bool(row['n']>=200 and row['T4_net_lo']>0 and row['T4_net_blo']>0 and
                                    row['T4_net_front']>0 and row['T4_net_back']>0 and
                                    (name!='O1' or row['increment40_lo']>0))
        summary.append(row)
    save(days,'open_days'); save(pd.DataFrame(summary),'open_summary')
    meta('open_saved',dict(completed=now(),methods=2,price_start=P.dates[0],price_end=P.dates[-1],tickers=len(P.tick),
                           prereg_sha256=hashlib.sha256(frozen.read_bytes()).hexdigest(),
                           summary_sha256=hashlib.sha256((OUT/'open_summary.csv').read_bytes()).hexdigest()))
    print(pd.DataFrame(summary)[['method','n','up_diff_mean','up_diff_lo','up_diff_hi','T4_net_mean','T4_net_lo','T4_net_hi','increment40_mean','increment40_lo','increment40_hi','week_candidate','forty_candidate']].to_string(index=False),flush=True)

if __name__=='__main__': main()
