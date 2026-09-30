# 5일 기준 공식 — 전수 탐색 결과(search_real.npy) 재사용 + 5일 귀무 + 5일 walk-forward
import os, sys, pickle, numpy as np, pandas as pd
import tempfile as _tf
_WORK=os.path.join(_tf.gettempdir(),'dh_v30_formula_20260930'); os.makedirs(_WORK,exist_ok=True)
HERE=os.path.dirname(os.path.abspath(__file__))
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE,'..','downside_20260930')); import flags as fl
R=np.load(os.path.join(_WORK,'search_real.npy')); base=np.load(os.path.join(_WORK,'search_base.npy')); forms,FE,anchors=pickle.load(open(os.path.join(_WORK,'search_meta.pkl'),'rb'))
A=np.array(anchors); TI=fl.TI
D5=R[2]-base[2][None,:]; closed=~np.isnan(base[2])
mon=A.astype(str)
M={m:np.char.startswith(mon,'2026'+m)&closed for m in ('06','07','08','09')}
def name(f):
    b,w,flt=f; s=('v30' if b else '')+''.join(f" {'+' if x>0 else '−'}{abs(x):g}·{FE[i]}" for i,x in w.items())
    if flt: s+=f" [{FE[flt[0]]} {'상위' if flt[1]=='hi' else '하위'}20% 제외]"
    return s.strip()
T=pd.DataFrame({'h5전체':np.nanmean(D5[:,closed],1),**{f'{m}월':np.nanmean(D5[:,M[m]],1) for m in M},'h20전체':np.nanmean((R[0]-base[0][None,:])[:,~np.isnan(base[0])],1)})
T['양수월']=(T[['06월','07월','08월','09월']]>0).sum(1); T['최악월']=T[['06월','07월','08월','09월']].min(1); T['name']=[name(f) for f in forms]
print(f"5일 확정 앵커 {closed.sum()} (9월 {M['09'].sum()}) · v30 기준 5일 top10 {np.nanmean(base[2][closed]):+.2f}")
print(f"진짜 1등 h5 {T.h5전체.max():+.2f} · 상위0.1% {T.h5전체.quantile(.999):+.2f} · 4개월 모두 양수 {(T.양수월==4).sum():,}개")
pd.set_option('display.width',260); pd.set_option('display.max_colwidth',80)
cols=['name','h5전체','06월','07월','08월','09월','h20전체','최악월']
print("\n[5일 전체 상위 8]"); print(T.nlargest(8,'h5전체')[cols].round(2).to_string(index=False))
print("\n[4개월 모두 양수 중 최악월 상위 10]"); print(T[T.양수월==4].nlargest(10,'최악월')[cols].round(2).to_string(index=False))
# walk-forward: 앵커 a 에서 5일 결과가 확정된(TI[x]+6<=TI[a]) 과거로 1등/상위20 선택
wf=[]
for j,a in enumerate(anchors):
    kn=[i for i,x in enumerate(anchors) if TI[x]+6<=TI[a] and closed[i]]
    if len(kn)<8 or not closed[j]: continue
    sc=np.nanmean(D5[:,kn],1); b=int(np.nanargmax(sc)); t20=np.argsort(-np.nan_to_num(sc,nan=-9))[:20]
    wf.append((a,D5[b,j],np.nanmean(D5[t20,j]),name(forms[b])))
W=pd.DataFrame(wf,columns=['a','best','top20','nm']); W['m']=W.a.str[4:6]
print("\n[정직한 시험: 매번 과거로만 5일 1등 선택]")
print(f"  1등: {W.best.mean():+.2f} (이긴날 {(W.best>0).mean():.0%}, n{len(W)}) · 상위20 평균: {W.top20.mean():+.2f} (이긴날 {(W.top20>0).mean():.0%})")
print("  월별(1등/상위20):", {m:(round(g.best.mean(),2),round(g.top20.mean(),2),len(g)) for m,g in W.groupby('m')})
prev=None
for r in W.itertuples():
    if r.nm!=prev: print(f"    {r.a}: {r.nm}"); prev=r.nm
T.to_csv(os.path.join(_WORK,'h5_summary.csv'),index=False); pd.concat([T[T['양수월']==4].nlargest(300,'최악월'),T.nlargest(300,'h5전체')]).drop_duplicates('name').to_csv(os.path.join(HERE,'h5_top.csv'),index=False); W.to_csv(os.path.join(HERE,'h5_walkforward.csv'),index=False)
