# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행. 읽기 전용.
"""sv_le_decile_20260906.py — sv_a·le_a 'IC≠돈' 해부: 점수 십분위별 초과수익(h10·h20), 시장별 합산.
초과 = 같은 run·시장 유니버스 중앙값 대비 %p. 앵커·게이트·진입 t+1 종가 = leaderboard.py 규약."""
from pathlib import Path as _P
import sys, sqlite3
import numpy as np, pandas as pd
_HERE=_P(__file__).resolve().parent; REPO=_HERE.parent; sys.path.insert(0,str(REPO))
import leaderboard as lb
close,_=lb.load_ohlcv(); dates=list(close.index); N=len(dates)
con=sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro',uri=True)
partial,dbl,didx=lb.build_gates(con,dates); excl=partial|dbl
S=pd.read_sql("SELECT run_id,market,ticker,model_id,wu_score AS score FROM wu_scores WHERE model_id IN ('sv_a','le_a')",con)
S['ticker']=S.ticker.astype(str).str.zfill(6); S['run_id']=S.run_id.astype(str)
jump_all=close.pct_change(fill_method=None).abs()
def fwd(t,h):
    if t+1+h>=N: return None
    f=close.iloc[t+1+h]/close.iloc[t+1]-1; j=jump_all.iloc[t+2:t+2+h].max(); return f.where(j<=lb.JUMP_CAP)
def boot(a,seed=7):
    a=np.asarray(a,float); rng=np.random.default_rng(seed); b=[rng.choice(a,len(a)).mean() for _ in range(3000)]
    return np.percentile(b,2.5),np.percentile(b,97.5)
for mid in ("sv_a","le_a"):
    s=S[S.model_id==mid]; keep=lb.dedupe_by_anchor(s,didx,excl,reg=lb.REG_DATE[mid])
    for h in (10,20):
        rec=[]  # (run, decile, excess)
        for rid,g in s.groupby("run_id"):
            if rid not in keep: continue
            t=lb.anchor(rid,didx); f=fwd(t,h)
            if f is None: continue
            for mk,gm in g.groupby("market"):
                sc=gm.set_index("ticker")["score"].astype(float); b=f.reindex(sc.index)
                m=sc.notna()&b.notna()
                if m.sum()<30: continue
                sc,b=sc[m],b[m]; ex=(b-b.median())*100
                dec=pd.qcut(sc.rank(method="first"),10,labels=False)+1  # 10 = 최고점
                top20=ex.reindex(sc.sort_values(ascending=False).head(20).index).mean()
                for d in range(1,11): rec.append((rid,d,ex[dec==d].mean()))
                rec.append((rid,"top20",top20))
        df=pd.DataFrame(rec,columns=["run","dec","ex"]); per=df.groupby(["run","dec"]).ex.mean().unstack()
        print(f"\n[{mid}] h{h}  앵커 n={per.shape[0]}  (십분위 10=최고점, 초과%p = 유니버스 중앙값 대비, 앵커 평균 · iid CI)")
        for d in list(range(1,11))+["top20"]:
            x=per[d].dropna(); lo,hi=boot(x.values)
            print(f"   {str(d):>5s}: {x.mean():+6.2f}  [{lo:+.2f},{hi:+.2f}]" + ("  ◀ 상위20" if d=="top20" else ""))
        top=per[10].dropna(); bot=per[1].dropna(); common=top.index.intersection(bot.index)
        d10=(top[common]-bot[common]).values; lo,hi=boot(d10)
        print(f"   10분위−1분위 (같은 앵커): {d10.mean():+.2f}  [{lo:+.2f},{hi:+.2f}]  n={len(common)}")
