# T3 — 3년 근사 바구니(가격만) × 플래그 12: 제외 후 다음 순위로 채움 − 기준, 무작위 교체 100회
import numpy as np, pandas as pd, flags as fl, basket as bk
_b=fl.build
def _build_any():
    F=_b(); A=F['F2_OVERHEAT']|F['F4_MAX20']|F['F7_REPEAT']|F['F9_RESUMED']|F['F12_IVOL']
    B=A|F['F5_CRASHDAY']|F['F3_ON60']
    return {'X_ANY5':A,'X_ANY7':B}
fl.build=_build_any

F=fl.build(); FN=list(F); C=fl.C; R=fl.R; V=fl.V; G=fl.GUARD; MK=fl.MK; SH=fl.SH
amt20=fl.AMT20
def rk(X,high_good):  # 행별 백분위 점수(클수록 좋음). high_good=False 면 값이 작을수록 높은 점수
    return X.rank(axis=1,pct=True,ascending=high_good)
lv60=R.rolling(60,min_periods=30).std(); lv20=R.rolling(20,min_periods=10).std(); lv63=R.rolling(63,min_periods=30).std()
nh252=C/C.rolling(252,min_periods=120).max()-1; dlow52=C/C.rolling(252,min_periods=120).min()-1
to20=(V/SH.where(SH>0)).rolling(20,min_periods=10).mean()
vol63=V.rolling(63,min_periods=30).sum(); obv63=(np.sign(R)*V).rolling(63,min_periods=30).sum()/vol63.where(vol63>0)
sma20=C/C.rolling(20).mean()-1; r20=C/C.shift(20)-1; vexp=V.rolling(20).mean()/V.rolling(60).mean()
def combo(core,aux):  # core 실측 필수, aux NaN=0.5 (wu_score 방식)
    s=core.copy()
    for a in aux: s=s+a.fillna(0.5)
    return s.where(core.notna())
import oversold as ov
AMTB=fl.AMT20/1e8
G30=G&(ov.OS>=30)&(ov.OS<70)&(AMTB>=5)
GSM=fl.C.notna()&(fl.SUSP==0)&(fl.JUMP21<=0.30)&(ov.OS>=30)&(ov.OS<70)&(AMTB>=1)&(AMTB<5)
r21=C/C.shift(21)-1; vexp2=V/V.rolling(20).mean()
PROXY={
 'LVG':lambda G_: rk(ov.RV21.where(G30),False),
 'SMG':lambda G_: rk(ov.RV21.where(GSM),False),
 'MOMG':lambda G_: combo(rk(sma20.where(G30),True),[rk(r21.where(G30),True),rk(vexp2.where(G30),True)]),
}
mark=C.ffill()
rng=np.random.default_rng(930)
anch=[i for i,d in enumerate(fl.DATES) if d>='20240701'][::5]
cols=np.array(C.columns); mkt=MK.reindex(C.columns).values
Farr={k:v.values for k,v in F.items()}; DIL=fl.DIL60.values
recs=[]
for pname,fn in PROXY.items():
    S=fn(G).values
    for a in anch:
        e=a+1
        for h in(20,40):
            if e+h>=len(fl.DATES): continue
            ent=C.values[e]; ex=mark.values[e+h]
            ret=np.clip(ex/ent-1,-0.95,3.0)
            per=[]
            for m in('kospi','kosdaq'):
                js=np.where((mkt==m)&np.isfinite(S[a])&~DIL[a]&np.isfinite(ret))[0]
                if len(js)<60: continue
                order=list(js[np.argsort(-S[a][js],kind='stable')])
                bench=np.nanmean(ret[(mkt==m)&G.values[a]&np.isfinite(ret)])
                base,out=bk.run_one(order,ret,{f:Farr[f][a] for f in FN},rng=rng)
                per.append((base-bench,out))
            if len(per)==2:
                rec=dict(proxy=pname,date=fl.DATES[a],h=h,base_ex=np.mean([p[0] for p in per]))
                for f in FN:
                    rec[f]=np.mean([p[1][f][0] for p in per]); rec[f+'_k']=np.mean([p[1][f][1] for p in per]); rec[f+'_pl']=np.mean([p[1][f][2] for p in per],axis=0)
                recs.append(rec)
D=pd.DataFrame(recs)
rows=[]
for (p,h),g in D.groupby(['proxy','h']):
    b=bk.bci(g.base_ex.values,max(1,h//5))
    for f in FN:
        ci=bk.bci(g[f].values,max(1,h//5)); plm=np.stack(g[f+'_pl'].values).mean(axis=0); pct=float((plm<g[f].mean()).mean())
        ys={y:g[g.date.str.startswith(y)][f].mean() for y in('2024','2025','2026')}
        rows.append(dict(proxy=p,h=h,n=len(g),base_ex=b[0],flag=f,k=g[f+'_k'].mean(),diff=ci[0],lo=ci[1],hi=ci[2],pl_mean=plm.mean(),pl_pct=pct,**{'y'+y:v for y,v in ys.items()}))
out=pd.DataFrame(rows); out.to_csv('x_t3b_proxy.csv',index=False)
pd.set_option('display.width',250); pd.set_option('display.max_rows',500)
o=out.copy()
for c_ in('base_ex','diff','lo','hi','pl_mean','y2024','y2025','y2026'): o[c_]=(o[c_]*100).round(2)
o['k']=o.k.round(2); o['pl_pct']=(o.pl_pct*100).round(0)
print(o[o.h==40].to_string(index=False)); print(); print(o[o.h==20][['proxy','flag','k','diff','lo','hi','pl_pct']].to_string(index=False))
