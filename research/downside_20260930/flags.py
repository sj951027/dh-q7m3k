# 하락 플래그 12개 (prereg_downside.md 고정 정의) + 공통 데이터
import os, sqlite3, numpy as np, pandas as pd, panel
P=panel.load(); C=P['close']; O=P['open'].where(P['open']>0); V=P['volume'].astype(float); MK=P['mk']
DATES=list(C.index); TI={d:i for i,d in enumerate(DATES)}
R=C.pct_change(fill_method=None)
AMT20=(C*V).rolling(20,min_periods=10).mean()
SUSP=P['susp'].reindex_like(C).fillna(0)
JUMP21=R.abs().rolling(21,min_periods=1).max()
GUARD=(AMT20>=5e8)&C.notna()&(C>0)&(SUSP==0)&(JUMP21<=0.30)
con=sqlite3.connect(f"file:{panel.OHLCV}?mode=ro",uri=True)
SH=pd.read_sql("select ticker,date,shares from daily_ohlcv",con).pivot(index='date',columns='ticker',values='shares').reindex_like(C).ffill()
MD=pd.read_sql("select series,date,close from market_daily",con).pivot(index='date',columns='series',values='close').reindex(C.index).ffill()
EV=pd.read_sql("select ticker,rcept_dt,event_type from dart_events where report_nm not like '%정정%'",con)
UE=pd.read_sql("select date,ticker,event from universe_events",con)
EV['ticker']=EV.ticker.astype(str).str.zfill(6); UE['ticker']=UE.ticker.astype(str).str.zfill(6)
def _ti(d):  # 공시일 → 그 날 또는 다음 거래일 인덱스
    return int(np.searchsorted(DATES,str(d)))
def event_matrix(df,datecol):
    M=np.zeros(C.shape,bool); cols={t:j for j,t in enumerate(C.columns)}
    for t,d in zip(df.ticker,df[datecol]):
        j=cols.get(t); i=_ti(d)
        if j is not None and i<len(DATES): M[i,j]=True
    return pd.DataFrame(M,index=C.index,columns=C.columns)
def recent(E,w):   # 최근 w 거래일(당일 포함) 안에 사건
    return E.astype(float).rolling(w,min_periods=1).max()>0
def recent_count(E,w): return E.astype(float).rolling(w,min_periods=1).sum()
def uni_top10(X):   # 그날 같은 시장 유동(GUARD) 유니버스 상위 10%
    out=pd.DataFrame(False,index=C.index,columns=C.columns)
    for m in('kospi','kosdaq'):
        idx=MK.index[MK==m]; q=X[idx].where(GUARD[idx]).rank(axis=1,pct=True)
        out[idx]=q>0.9
    return out
DIL_TYPES=('paid_in','cb','bw','eb','paid_bonus_mix')
DIL_E=event_matrix(EV[EV.event_type.isin(DIL_TYPES)],'rcept_dt')
DIL60=recent(DIL_E,60)   # 운용 규약 기준선용
def build():
    F={}
    vavg=V.shift(1).rolling(20,min_periods=15).mean()
    F['F1_VSHOCK']=recent((V>5*vavg)&(vavg>0),20)
    r5=C/C.shift(5)-1; r15=C/C.shift(15)-1
    F['F2_OVERHEAT']=recent((r5>0.6)|(r15>1.0),20)
    on=np.log(O/C.shift(1)); F['F3_ON60']=uni_top10(on.rolling(60,min_periods=48).sum())
    F['F4_MAX20']=uni_top10(R.rolling(20,min_periods=15).max())
    F['F5_CRASHDAY']=recent(R<=-0.15,60)
    F['F6_PENNY']=C<1000
    F['F7_REPEAT']=recent_count(DIL_E,250)>=2
    F['F8_REDUCTION']=recent(event_matrix(EV[EV.event_type=='reduction'],'rcept_dt'),120)
    F['F9_RESUMED']=recent(event_matrix(UE[UE.event=='RESUMED'],'date'),60)
    newE=event_matrix(UE[UE.event=='NEW'],'date'); F['F10_NEWLIST']=recent(newE,252)
    lo52=C.rolling(252,min_periods=120).min(); r60=C/C.shift(60)-1
    F['F11_KNIFE']=(C<=lo52*1.05)&(r60<-0.20)
    rm=pd.DataFrame(index=C.index,columns=C.columns,dtype=float)
    for m,s in(('kospi','KOSPI'),('kosdaq','KOSDAQ')):
        idx=MK.index[MK==m]; rm[idx]=np.repeat(MD[s].pct_change().values[:,None],len(idx),axis=1)
    F['F12_IVOL']=uni_top10((R-rm).rolling(60,min_periods=40).std())
    return {k:v.reindex_like(C).fillna(False).astype(bool) for k,v in F.items()}
