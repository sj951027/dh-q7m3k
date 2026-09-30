# 예비 점검 공통 패널 (DB 사본, 읽기 전용) — 연구용·채택 아님
import sqlite3, numpy as np, pandas as pd, os
# DB: 환경변수 DOWNSIDE_SNAP(사본 폴더: ohlcv.db·history.db) 권장. 없으면 원본을 mode=ro (평일 20:10~22:30 실행 금지)
_HERE=os.path.dirname(os.path.abspath(__file__))
SNAP=os.environ.get("DOWNSIDE_SNAP")
OHLCV=os.path.join(SNAP,"ohlcv.db") if SNAP else os.path.normpath(os.path.join(_HERE,"../../../dh-q7m3k-data/ohlcv.db"))
HIST=os.path.join(SNAP,"history.db") if SNAP else os.path.normpath(os.path.join(_HERE,"../../history.db"))
import tempfile
CACHE=os.path.join(tempfile.gettempdir(),"dh_downside_panel_20260930.pkl")   # 저장소 밖
def load():
    if os.path.exists(CACHE): return pd.read_pickle(CACHE)
    c=sqlite3.connect(f"file:{OHLCV}?mode=ro",uri=True)
    d=pd.read_sql("select ticker,date,open,high,low,close,volume,market,is_suspended from daily_ohlcv",c)
    P={k:d.pivot(index='date',columns='ticker',values=k).sort_index() for k in('open','high','low','close','volume')}
    mk=d.groupby('ticker').market.last().str.lower()
    susp=d.pivot(index='date',columns='ticker',values='is_suspended').sort_index()
    P['mk']=mk; P['susp']=susp
    pd.to_pickle(P,CACHE); return P
def fwd(close,h,lag=1):
    e=close.shift(-lag); x=close.shift(-lag-h)
    return x/e-1
def evaluate(sig, P, h=20, top=10, label="", higher_better=True, min_amt=5e8, blk=20):
    close=P['close']; vol=P['volume']; mk=P['mk']
    amt20=(close*vol).rolling(20).mean()
    ok=(amt20>=min_amt)&close.notna()&(vol>0)
    s=sig.where(ok)
    if not higher_better: s=-s
    f=fwd(close,h)
    jump=close.pct_change(fill_method=None).abs()
    # 점프컷(보유기간 중 일간 ±50% 초과 종목 제외 — leaderboard JUMP_CAP 사상)
    jmax=jump[::-1].rolling(h+1,min_periods=1).max()[::-1].shift(-1)
    f=f.where(jmax<=0.5)
    dates=close.index; rows=[]
    for i,dt in enumerate(dates):
        if i%1: continue
        si=s.iloc[i]; fi=f.iloc[i]
        ics=[];exc=[]
        for m in('kospi','kosdaq'):
            idx=mk.index[mk==m]
            a=si.reindex(idx); b=fi.reindex(idx); msk=a.notna()&b.notna()
            if msk.sum()<50: continue
            ics.append(a[msk].rank().corr(b[msk].rank()))
            t=a[msk].nlargest(top).index
            exc.append(b[msk][t].mean()-b[msk].mean())
        if ics: rows.append((dt,np.mean(ics),np.mean(exc)))
    r=pd.DataFrame(rows,columns=['date','ic','exc']).set_index('date')
    def bci(x):
        x=x.values; n=len(x); nb=max(1,n//blk); rng=np.random.default_rng(7); out=[]
        for _ in range(2000):
            st=rng.integers(0,n-blk+1,nb); out.append(np.concatenate([x[s:s+blk] for s in st]).mean())
        return np.percentile(out,[2.5,97.5])
    lo,hi=bci(r.ic); elo,ehi=bci(r.exc)
    print(f"[{label}] h{h} n={len(r)} IC {r.ic.mean():+.4f} blockCI[{lo:+.4f},{hi:+.4f}] pos {(r.ic>0).mean():.0%} | top{top} exc {r.exc.mean()*100:+.2f}%p CI[{elo*100:+.2f},{ehi*100:+.2f}]")
    yr=r.groupby(r.index.str[:4]).agg(ic=('ic','mean'),exc=('exc','mean'),n=('ic','size'))
    print("   by year:", "; ".join(f"{y}: IC {a.ic:+.3f} exc {a.exc*100:+.2f} (n{a.n})" for y,a in yr.iterrows()))
    return r
