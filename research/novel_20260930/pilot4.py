import panel, sqlite3, numpy as np, pandas as pd
P=panel.load(); c=P['close']; v=P['volume']
r=c.pct_change(fill_method=None)
vavg=v.shift(1).rolling(20).mean(); shock=((v>5*vavg)&(vavg>0))
r5=c/c.shift(5)-1; r15=c/c.shift(15)-1; hot=(r5>0.6)|(r15>1.0)
recent_up=(shock&(r>0)).astype(float).rolling(20,min_periods=1).max()>0
recent_any=shock.astype(float).rolling(20,min_periods=1).max()>0
recent_hot=hot.astype(float).rolling(20,min_periods=1).max()>0
f40=panel.fwd(c,40); f20=panel.fwd(c,20)
h=sqlite3.connect(f"file:{panel.HIST}?mode=ro",uri=True)
for mid,tb,col,reg in (('v30','v3_scores','final_score_v3','20260606'),('lv_b','lowvol_scores','lowvol_score','20260626')):
    S=pd.read_sql(f"select run_id,market,ticker,{col} s from {tb} where model_id=?",h,params=(mid,))
    S['ticker']=S.ticker.astype(str).str.zfill(6); S['run_id']=S.run_id.astype(str)
    rows=[]
    for rid,g in S[S.run_id>=reg].groupby('run_id'):
        if rid not in c.index: continue
        for m,gm in g.groupby('market'):
            t=gm.nlargest(10,'s').ticker
            for tk in t:
                if tk not in c.columns: continue
                rows.append((rid,tk,bool(recent_up.at[rid,tk]),bool(recent_any.at[rid,tk]),bool(recent_hot.at[rid,tk]),f20.at[rid,tk],f40.at[rid,tk]))
    d=pd.DataFrame(rows,columns=['rid','tk','up','any','hot','f20','f40'])
    print(f"{mid}: picks {len(d)} days {d.rid.nunique()} | recent up-shock {d.up.mean():.1%} any-shock {d['any'].mean():.1%} overheat {d.hot.mean():.1%}")
    for k in('any','up','hot'):
        a=d[d[k]]; b=d[~d[k]]
        print(f"   {k}: flagged n={len(a)} f20 {a.f20.mean()*100:+.2f}% (n{a.f20.notna().sum()}) vs rest {b.f20.mean()*100:+.2f}% | f40 {a.f40.mean()*100:+.2f}% (n{a.f40.notna().sum()}) vs {b.f40.mean()*100:+.2f}%")
