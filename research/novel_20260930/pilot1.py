import panel, numpy as np, pandas as pd
P=panel.load(); c=P['close']; o=P['open'].where(P['open']>0); v=P['volume']
on=o/c.shift(1)-1; intr=c/o-1
lv60=c.pct_change(fill_method=None).rolling(60).std()
def corr_with(sig,ref,name):
    cs=[sig.iloc[i].rank().corr(ref.iloc[i].rank()) for i in range(80,len(c),20)]
    print(f"   rank-corr with {name}: {np.nanmean(cs):+.2f}")
# A. CTO: (밤사이- & 장중+) 빈도 − (밤사이+ & 장중-) 빈도
for w in (20,60):
    neg_pos=((on<0)&(intr>0)).astype(float).where(on.notna()&intr.notna())
    pos_neg=((on>0)&(intr<0)).astype(float).where(on.notna()&intr.notna())
    cto=(neg_pos-pos_neg).rolling(w,min_periods=int(w*.8)).mean()
    panel.evaluate(cto,P,label=f"CTO{w} (high=good)")
    if w==20: corr_with(cto,lv60,'lv60')
# 참고: 순수 밤사이 누적(on60 재확인)
onc=np.log1p(on).rolling(60,min_periods=48).sum()
panel.evaluate(onc,P,label="overnight cum60 (high=good)")
# C. MAX20
r=c.pct_change(fill_method=None)
mx=r.rolling(20).max()
panel.evaluate(mx,P,label="MAX20 (low=good)",higher_better=False)
corr_with(mx,lv60,'lv60')
