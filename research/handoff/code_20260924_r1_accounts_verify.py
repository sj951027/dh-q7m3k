"""Independent cash/share ledger for one saved account, SQL price reads only."""
from pathlib import Path
import json,sqlite3
import numpy as np
import pandas as pd
O=Path(__file__).with_name('r1_controls_20260924');ROOT=Path(__file__).resolve().parents[2]
orders=pd.read_csv(O/'orders.csv',dtype={'date':str});orders=orders[(orders.name=='R1_amount')&~orders.matched]
hold=pd.read_csv(O/'holdings.csv',dtype={'date':str,'ticker':str});hold=hold[hold.name=='R1_amount']
actual=pd.read_csv(O/'account_paths.csv',dtype={'date':str});actual=actual[(actual.name=='R1_amount')&~actual.matched].set_index('date')
con=sqlite3.connect((ROOT.parent/'dh-q7m3k-data/ohlcv.db').as_uri()+'?mode=ro',uri=True)
con.execute('PRAGMA query_only=ON')
calendar=[x[0] for x in con.execute('SELECT DISTINCT date FROM daily_ohlcv ORDER BY date')]
raw=pd.read_sql_query('SELECT ticker,date,close,volume FROM daily_ohlcv WHERE date BETWEEN ? AND ?',con,params=(actual.index[0],actual.index[-1]));con.close()
price=raw.pivot(index='date',columns='ticker',values='close').reindex(actual.index)
volume=raw.pivot(index='date',columns='ticker',values='volume').reindex(actual.index)
mark=price.ffill();cash=1.;book=[];largest=0.;budget_err=0.;half=.0025
for date in actual.index:
    for entry in list(book):
        ticker,units,due=entry
        if date>=due and volume.loc[date,ticker]>0 and pd.notna(price.loc[date,ticker]):
            cash+=units*price.loc[date,ticker]*(1-half);book.remove(entry)
    if date in set(orders.date):
        row=orders[orders.date==date].iloc[0]
        pre=cash+sum(units*mark.loc[date,ticker] for ticker,units,due in book)
        invest=min(pre/6,cash/(1+half));budget_err=max(budget_err,abs(invest-row.invested))
        i=calendar.index(date);signal=calendar[i-1];ids=hold[hold.date==signal].ticker.tolist()
        assert len(ids)==20 and all(volume.loc[date,t]>0 for t in ids)
        for ticker in ids:book.append((ticker,invest/20/price.loc[date,ticker],calendar[i+120]))
        cash-=invest*(1+half)
    value=sum(units*mark.loc[date,ticker] for ticker,units,due in book)
    largest=max(largest,abs(cash+value-actual.loc[date,'nav']),abs(cash-actual.loc[date,'cash']))
assert largest<1e-10 and budget_err<1e-10
result=dict(account='R1_amount',days=len(actual),max_nav_cash_error=largest,max_budget_error=budget_err,
            remaining_positions=len(book),final_cash=cash,final_marked_value=value,final_nav=cash+value)
(O/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
