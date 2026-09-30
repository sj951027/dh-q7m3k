import panel, sqlite3, numpy as np, pandas as pd
P=panel.load(); c=P['close']; v=P['volume']; mk=P['mk']
r=c.pct_change(fill_method=None); amt20=(c*v).rolling(20).mean(); liq=amt20>=5e8
lv60=r.rolling(60).std()
f20=panel.fwd(c,20); jm=r.abs()[::-1].rolling(21,min_periods=1).max()[::-1].shift(-1); f20=f20.where(jm<=0.5)
# 변동성 5분위 안에서 '사건 종목 − 같은 분위 비사건 종목' (최근 20일 안에 사건 있었는지)
vavg=v.shift(1).rolling(20).mean(); shock=((v>5*vavg)&(vavg>0))
r5=c/c.shift(5)-1; r15=c/c.shift(15)-1; hot=(r5>0.6)|(r15>1.0)
def within_vol(E,label,win=20):
    Er=E.astype(float).rolling(win,min_periods=1).max()>0
    q=lv60.where(liq).rank(axis=1,pct=True)
    rows=[]
    for i in range(80,len(c)-21,5):
        qi=q.iloc[i]; ei=Er.iloc[i]; fi=f20.iloc[i]
        for m in('kospi','kosdaq'):
            idx=mk.index[mk==m]
            d=pd.DataFrame({'q':qi.reindex(idx),'e':ei.reindex(idx),'f':fi.reindex(idx)}).dropna()
            if d.empty: continue
            d['b']=np.ceil(d.q*5).clip(1,5)
            for b,g in d.groupby('b'):
                if g.e.sum()>=3 and (~g.e.astype(bool)).sum()>=10:
                    rows.append((c.index[i][:4],b,g[g.e.astype(bool)].f.mean()-g[~g.e.astype(bool)].f.mean(),int(g.e.sum())))
    df=pd.DataFrame(rows,columns=['y','b','d','n'])
    print(f"[{label} within lv60 quintile, past {win}d] mean diff h20 {df.d.mean()*100:+.2f}%p (cells {len(df)})")
    print("   by vol quintile:", "; ".join(f"Q{int(b)}: {g.d.mean()*100:+.2f}" for b,g in df.groupby('b')))
    print("   by year:", "; ".join(f"{y}: {g.d.mean()*100:+.2f}" for y,g in df.groupby('y')))
within_vol(shock&(r>0),"volshock up")
within_vol(hot,"overheat")
# 대차잔고
con=sqlite3.connect(f"file:{panel.OHLCV}?mode=ro",uri=True)
sf=pd.read_sql("select ticker,date,loan_bal_qty from short_flows where loan_bal_qty is not null",con)
cov=sf.groupby('date').size(); print("loan coverage: first date",cov.index.min(),"; n tickers by month:",cov.groupby(cov.index.str[:6]).median().tail(18).to_dict())
lb_=sf.pivot(index='date',columns='ticker',values='loan_bal_qty').reindex(index=c.index,columns=c.columns)
sh=pd.read_sql("select ticker,date,shares from daily_ohlcv where date>='20250101'",con).pivot(index='date',columns='ticker',values='shares').reindex(index=c.index,columns=c.columns).ffill()
lr=lb_/sh; dl=lr-lr.shift(20)
m=pd.Series(c.index>= '20250401',index=c.index)
panel.evaluate(dl.where(m,axis=0),P,label="loan ratio 20d change (low=good) 2025-04~",higher_better=False)
panel.evaluate(lr.where(m,axis=0),P,label="loan ratio level (low=good) 2025-04~",higher_better=False)
