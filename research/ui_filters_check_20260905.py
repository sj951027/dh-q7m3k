# -*- coding: utf-8 -*-
"""
ui_filters_check_20260905.py — 표시 페이지의 '행동 유도' 필터·배지가 실제 h20 초과수익과 맞는지 (관측 전용, 읽기 전용)
대상(사용자 지적: 검증 없이 들어온 기능 점검): ① filter.html '떨어지는 칼날' 배지 ② '추천 종목만'(턴어라운드/성장지속+안전+final_score≥60)
③ '수급 반전'(20일 음수→5일 양수) ④ lowvol.html 빠른필터: 외인5일>0 · 기관5일>0 · 지난주 하락(return_1w<0) · ROE≥10
방법: stage3_final(run별 유니버스) × leaderboard 프로토콜 forward h20(t+1 종가 진입, JUMP_CAP) — 같은 run 안에서 '플래그 on vs off' 평균 초과(유니버스 중앙값 대비) 짝차이, 앵커 부트 CI.
lv_b 필터는 lv_b 상위 30 안에서만(실제 사용자가 보는 집합), v3 는 stage3 전체 + BUY/WAIT 안.
"""
import os, sys, sqlite3
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import leaderboard as lb
H=20
close,_=lb.load_ohlcv(); dates=list(close.index); N=len(dates); didx={d:i for i,d in enumerate(dates)}
con=sqlite3.connect(f"file:{lb.DB}?mode=ro",uri=True)
partial,dbl,_=lb.build_gates(con,dates); excl=partial|dbl
jump=close.pct_change(fill_method=None).abs()
s3=pd.read_sql("SELECT run_id,market,ticker,falling_knife,earnings_pattern,risk_level,final_score,\"return_1w_%\" r1w,\"foreign_5d_억\" f5,\"foreign_20d_억\" f20,\"inst_5d_억\" i5,\"inst_20d_억\" i20,roe_value FROM stage3_final",con)
v3b=pd.read_sql("SELECT run_id,market,ticker,bucket FROM v3_scores WHERE model_id='v30'",con); v3b["ticker"]=v3b.ticker.astype(str); v3b["run_id"]=v3b.run_id.astype(str)
s3=s3.merge(v3b,on=["run_id","market","ticker"],how="left")
s3["ticker"]=s3.ticker.astype(str); s3["run_id"]=s3.run_id.astype(str)
lvb=pd.read_sql("SELECT run_id,market,ticker,lowvol_score FROM lowvol_scores WHERE model_id='lv_b'",con); lvb["ticker"]=lvb.ticker.astype(str); lvb["run_id"]=lvb.run_id.astype(str)
def fwd(t):
    if t+1+H>=N: return None
    f=close.iloc[t+1+H]/close.iloc[t+1]-1; j=jump.iloc[t+2:t+2+H].max(); return f.where(j<=lb.JUMP_CAP)
def boot(a,B=2000,seed=7):
    a=np.asarray(a,float); a=a[np.isfinite(a)]; n=len(a)
    if n==0: return (np.nan,np.nan,np.nan,0)
    rng=np.random.default_rng(seed); bs=[rng.choice(a,n).mean() for _ in range(B)]; return (a.mean(),np.percentile(bs,2.5),np.percentile(bs,97.5),n)
keep=lb.dedupe_by_anchor(s3,didx,excl,reg="20260606")
TESTS={
 "떨어지는 칼날(stage3 전체)":      ("v3", lambda g: g.falling_knife.astype(float)==1),
 "떨어지는 칼날(BUY·WAIT 안)":      ("v3", lambda g: (g.falling_knife.astype(float)==1) if True else None, lambda g: g.bucket.isin(["BUY","WAIT"])),
 "추천 종목만(턴어라운드/성장지속+안전+옛점수60+)": ("v3", lambda g: g.earnings_pattern.isin(["턴어라운드","성장지속"])&(g.risk_level=="안전")&(pd.to_numeric(g.final_score,errors="coerce")>=60)),
 "수급 반전(외인 or 기관: 20일<0 & 5일>0)": ("v3", lambda g: ((pd.to_numeric(g.f20,errors="coerce")<0)&(pd.to_numeric(g.f5,errors="coerce")>0))|((pd.to_numeric(g.i20,errors="coerce")<0)&(pd.to_numeric(g.i5,errors="coerce")>0))),
 "lv_b top30: 외인5일>0":           ("lvb", lambda g: pd.to_numeric(g.f5,errors="coerce")>0),
 "lv_b top30: 기관5일>0":           ("lvb", lambda g: pd.to_numeric(g.i5,errors="coerce")>0),
 "lv_b top30: 지난주 하락(1주<0)":   ("lvb", lambda g: pd.to_numeric(g.r1w,errors="coerce")<0),
 "lv_b top30: ROE≥10":             ("lvb", lambda g: pd.to_numeric(g.roe_value,errors="coerce")>=10),
}
rows=[]
for name,spec in TESTS.items():
    kind,flag=spec[0],spec[1]; pre=spec[2] if len(spec)>2 else None
    diffs=[]; on_ex=[]; share=[]
    for rid in sorted(keep):
        t=lb.anchor(rid,didx); f=fwd(t)
        if f is None: continue
        g=s3[s3.run_id==rid]
        if kind=="lvb":
            l=lvb[lvb.run_id==rid]
            if l.empty: continue
            top=l.sort_values("lowvol_score",ascending=False).groupby("market").head(30)
            g=g.merge(top[["market","ticker"]],on=["market","ticker"])
        if pre is not None: g=g[pre(g)]
        d_run=[]
        for mk,gm in g.groupby("market"):
            gm=gm.drop_duplicates("ticker"); b=f.reindex(gm.ticker.values).values; ex=b-np.nanmedian(f.reindex(g.ticker.values).values) if kind=="v3" else b-np.nanmedian(b)
            fl=flag(gm).values.astype(bool); m=np.isfinite(ex)
            if (fl&m).sum()>=3 and ((~fl)&m).sum()>=3:
                d_run.append(np.nanmean(ex[fl&m])-np.nanmean(ex[(~fl)&m])); on_ex.append(np.nanmean(ex[fl&m])); share.append(fl[m].mean())
        if d_run: diffs.append(np.mean(d_run))
    m,lo,hi,n=boot(diffs)
    rows.append(dict(test=name,n_anchor=n,flag_share=round(float(np.mean(share)),2) if share else None,diff_pp=round(m*100,2),lo=round(lo*100,2),hi=round(hi*100,2),win=round(float(np.mean(np.array(diffs)>0)),2) if n else None))
    print(rows[-1],flush=True)
df=pd.DataFrame(rows); df.to_csv("research/fullscan_20260903/out/ui_filters_check.csv",index=False)
print(df.to_string(index=False))
