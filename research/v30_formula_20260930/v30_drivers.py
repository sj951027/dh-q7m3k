# v30 후보 안에서 무엇이 수익을 가르나 — 관측 전용, DB·아카이브 사본 읽기
import os, sys, glob, sqlite3, numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); SNAP=os.environ.get('V30R_SNAP')   # DB 사본 폴더(권장). 없으면 원본 mode=ro — 평일 20:10~22:30 실행 금지
import tempfile as _tf
_WORK=os.path.join(_tf.gettempdir(),'dh_v30_formula_20260930'); os.makedirs(_WORK,exist_ok=True)   # 큰 중간파일(pkl·npy)은 저장소 밖
OHLCV=os.path.join(SNAP,'ohlcv.db') if SNAP else os.path.normpath(os.path.join(HERE,'..','..','..','dh-q7m3k-data','ohlcv.db'))
HISTDB=os.path.join(SNAP,'history.db') if SNAP else os.path.normpath(os.path.join(HERE,'..','..','history.db'))
sys.path.insert(0, os.path.normpath(os.path.join(HERE,"..",".."))); import leaderboard as lb
con=sqlite3.connect(f"file:{OHLCV}?mode=ro",uri=True)
raw=pd.read_sql("select ticker,date,close from daily_ohlcv where date>='20260501'",con)
close=raw.pivot(index='date',columns='ticker',values='close').sort_index(); dates=list(close.index); didx={d:i for i,d in enumerate(dates)}
P=close.values; col={t:i for i,t in enumerate(close.columns)}
hc=sqlite3.connect(f"file:{HISTDB}?mode=ro",uri=True)
partial,dbl,_=lb.build_gates(hc,dates); excl=partial|dbl
runs=sorted({os.path.basename(f).split('_')[-1][:8] for f in glob.glob(os.path.join(HERE,'..','..','v3_archive','v3_kospi_*.csv'))})
S=pd.DataFrame({'run_id':runs}); keep=lb.dedupe_by_anchor(S,didx,excl,reg='20260606')
JUMP=0.32
def fwd(t,H):
    if t+1+H>=len(dates): return None,None
    blk=P[t+1:t+H+2]
    with np.errstate(divide='ignore',invalid='ignore'):
        f=blk[-1]/blk[0]-1; j=np.abs(blk[1:]/blk[:-1]-1)
    ok=np.isfinite(f)&(blk[0]>0)&(np.nanmax(np.where(np.isnan(j),-np.inf,j),axis=0)<=JUMP)
    return f,ok
frames=[]
for run in sorted(keep):
    t=lb.anchor(run,didx)
    if t is None: continue
    F={H:fwd(t,H) for H in (5,20,40)}
    for mkt in ('kospi','kosdaq'):
        p=os.path.join(HERE,'..','..','v3_archive',f'v3_{mkt}_{run}.csv')
        if not os.path.exists(p): continue
        g=pd.read_csv(p,dtype={'ticker':str},encoding='utf-8-sig',low_memory=False); g['ticker']=g.ticker.str.zfill(6)
        g=g[g.ticker.isin(col)].copy(); ci=g.ticker.map(col).values
        g['rank']=g.final_score_v3.rank(ascending=False,method='first'); g['anchor']=dates[t]; g['mkt']=mkt
        for H,(f,ok) in F.items():
            if f is None: g[f'ex{H}']=np.nan; continue
            v=np.where(ok[ci],f[ci]*100,np.nan); g[f'ex{H}']=v-np.nanmedian(v)
        frames.append(g)
D=pd.concat(frames,ignore_index=True)
D.to_pickle(os.path.join(_WORK,('v30_panel.pkl')))
print('anchors',D.anchor.nunique(),'rows',len(D),'per anchor-mkt',round(len(D)/D.groupby(['anchor','mkt']).ngroups),'h20 anchors',D.dropna(subset=['ex20']).anchor.nunique(),'h40',D.dropna(subset=['ex40']).anchor.nunique())
print('bucket',D.bucket.value_counts().to_dict()); print('grade',D.grade.value_counts().to_dict())
