import panel, sqlite3, numpy as np, pandas as pd
P=panel.load(); c=P['close']; v=P['volume']; mk=P['mk']
r=c.pct_change(fill_method=None)
amt20=(c*v).rolling(20).mean(); liq=amt20>=5e8
def mkt_ew(f):
    out=pd.DataFrame(index=f.index,columns=f.columns,dtype=float)
    for m in('kospi','kosdaq'):
        idx=mk.index[mk==m]; sub=f[idx].where(liq[idx])
        out[idx]=np.repeat(sub.mean(axis=1).values[:,None],len(idx),axis=1)
    return out
FW={h:panel.fwd(c,h) for h in(5,20,40)}
jump=r.abs()
EX={}
for h,f in FW.items():
    jm=jump[::-1].rolling(h+1,min_periods=1).max()[::-1].shift(-1)
    EX[h]=(f-mkt_ew(f)).where(jm<=0.5)
def event_study(E,label,start=None):
    E=E&liq
    if start: E=E.loc[start:]
    out=[]
    for h in(5,20,40):
        ex=EX[h].reindex_like(E).where(E)
        s=ex.stack(); 
        if s.empty: continue
        by_day=s.groupby(level=0).mean()
        x=by_day.values; n=len(x); blk=min(20,max(1,n//5)); rng=np.random.default_rng(7); bs=[]
        for _ in range(2000):
            st=rng.integers(0,max(1,n-blk+1),max(1,n//blk)); bs.append(np.concatenate([x[a:a+blk] for a in st]).mean())
        lo,hi=np.percentile(bs,[2.5,97.5])
        out.append(f"h{h}: {s.mean()*100:+.2f}%p (ev{len(s)},days{n}) dayCI[{lo*100:+.2f},{hi*100:+.2f}] win{(s>0).mean():.0%}")
    yr=EX[20].where(E&liq).stack(); yr=yr.groupby(yr.index.get_level_values(0).str[:4]).agg(['mean','size'])
    print(f"[{label}] "+" | ".join(out)); print("   h20 by year:", "; ".join(f"{y}: {a['mean']*100:+.2f} (n{int(a['size'])})" for y,a in yr.iterrows()))
# B. 거래량 충격: 당일 거래량 > 20일 평균(전일까지)×5
vavg=v.shift(1).rolling(20).mean()
shock=(v>5*vavg)&(vavg>0)
event_study(shock&(r>0.0),"volshock5x & up")
event_study(shock&(r>0.10),"volshock5x & up>10%")
event_study(shock&(r<0),"volshock5x & down")
# F. 급등 과열(시장경보 근사): 5일 +60% 또는 15일 +100%
r5=c/c.shift(5)-1; r15=c/c.shift(15)-1
hot=(r5>0.6)|(r15>1.0)
first=hot&~hot.shift(1,fill_value=False)
event_study(first,"overheat first day (5d+60% or 15d+100%)")
# 투자자 유형 조건 (2026-04~)
con=sqlite3.connect(f"file:{panel.OHLCV}?mode=ro",uri=True)
fl=pd.read_sql("select ticker,date,person_net_val,foreign_net_val,inst_net_val from daily_flows",con)
fn=fl.pivot(index='date',columns='ticker',values='foreign_net_val').reindex(index=c.index,columns=c.columns)
inn=fl.pivot(index='date',columns='ticker',values='inst_net_val').reindex(index=c.index,columns=c.columns)
pn=fl.pivot(index='date',columns='ticker',values='person_net_val').reindex(index=c.index,columns=c.columns)
tv=c*v
sh=shock&(r>0)
fi=(fn.fillna(0)+inn.fillna(0))
print("flows coverage from", fl.date.min(), "events up-shock since 20260428:", int((sh&liq).loc['20260428':].sum().sum()))
event_study(sh&(fi>0)&(pn<0),"up-shock, foreign+inst buy & person sell",start='20260428')
event_study(sh&(fi<0)&(pn>0),"up-shock, person buy & foreign+inst sell",start='20260428')
event_study(sh,"up-shock all (same period)",start='20260428')
# D. 대차잔고 변화 (재개 후 2025-04~)
sf=pd.read_sql("select ticker,date,loan_bal_qty from short_flows",con)
lb_=sf.pivot(index='date',columns='ticker',values='loan_bal_qty').reindex(index=c.index,columns=c.columns)
shares=pd.read_sql("select ticker,date,shares from daily_ohlcv where date>='20250301'",con).pivot(index='date',columns='ticker',values='shares').reindex(index=c.index,columns=c.columns).ffill()
lratio=lb_/shares
dl=lratio-lratio.shift(20)
print("loan coverage (non-null tickers on 20250602, 20260901):", int(lb_.loc['20250602'].notna().sum()) if '20250602' in lb_.index else None, int(lb_.loc['20260901'].notna().sum()))
sig=dl.where(dl.index.to_series().ge('20250401').values[:,None])
panel.evaluate(sig,P,label="loan ratio 20d increase (low=good), 2025-04~",higher_better=False)
sig2=lratio.where(lratio.index.to_series().ge('20250401').values[:,None])
panel.evaluate(sig2,P,label="loan ratio level (low=good), 2025-04~",higher_better=False)
