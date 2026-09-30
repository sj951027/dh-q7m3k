import os, sys, pickle, numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE,'..','downside_20260930')); import flags as fl
import tempfile as _tf
_WORK=os.path.join(_tf.gettempdir(),'dh_v30_formula_20260930'); os.makedirs(_WORK,exist_ok=True)   # 큰 중간파일(pkl·npy)은 저장소 밖
R=np.load(os.path.join(_WORK,('search_real.npy'))); base=np.load(os.path.join(_WORK,('search_base.npy')))
forms,FE,anchors=pickle.load(open(os.path.join(_WORK,('search_meta.pkl')),'rb')); A=np.array(anchors); TI=fl.TI
D=R-base[:,None,:]          # 4×M×A : 공식 − v30  (0=ex20,1=ex40,2=ex5,3=now)
mon=A.astype(str); m6=np.char.startswith(mon,'202606'); m7=np.char.startswith(mon,'202607'); m8=np.char.startswith(mon,'202608')
closed20=~np.isnan(base[0]); closed40=~np.isnan(base[1])
a8l=(mon>='20260818')&(mon<'20260901'); a9=mon>='20260901'
def name(f):
    b,w,flt=f; s=('v30' if b else '')+''.join(f" {'+' if x>0 else '−'}{abs(x):g}·{FE[i]}" for i,x in w.items())
    if flt: s+=f" [{FE[flt[0]]} {'상위' if flt[1]=='hi' else '하위'}20% 제외]"
    return s.strip()
def m(x,msk): return np.nanmean(x[:,msk],axis=1)
T=pd.DataFrame({'h20':m(D[0],closed20),'6월':m(D[0],m6&closed20),'7월':m(D[0],m7&closed20),'8월':m(D[0],m8&closed20),'h40':m(D[1],closed40),
                '8말(중간)':m(D[3],a8l),'9월(중간)':m(D[3],a9),'9월 5일':m(D[2],a9&~np.isnan(base[2]))})
per=['6월','7월','8월','8말(중간)','9월(중간)']; T['양수기간']=(T[per]>0).sum(1); T['최악']=T[per].min(1)
T['name']=[name(f) for f in forms]
null=np.load(os.path.join(_WORK,('search_null.npy')))
print(f"공식 {len(T):,}개 · 기준 v30 h20 top10 {np.nanmean(base[0][closed20]):+.2f}")
print(f"[운의 최고치] 수익 섞은 가짜 데이터 {len(null)}회: 1등 h20 평균 {null[:,0].mean():+.2f} (범위 {null[:,0].min():+.2f}~{null[:,0].max():+.2f}), 상위0.1% {null[:,1].mean():+.2f}")
print(f"[진짜 데이터] 1등 h20 {T.h20.max():+.2f} · 상위0.1% {T.h20.quantile(.999):+.2f} · 상위1% {T.h20.quantile(.99):+.2f} · 중앙값 {T.h20.median():+.2f}")
print(f"5개 기간 모두 v30보다 나은 공식: {(T['양수기간']==5).sum():,}개 ({(T['양수기간']==5).mean():.1%})")
pd.set_option('display.width',280); pd.set_option('display.max_colwidth',90)
cols=['name','h20','6월','7월','8월','h40','8말(중간)','9월(중간)','9월 5일','양수기간']
print("\n=== (1) 같은 기간 h20 상위 10"); print(T.sort_values('h20',ascending=False).head(10)[cols].round(2).to_string(index=False))
print("\n=== 5개 기간 모두 양수 중 '최악 기간' 상위 10"); print(T[T['양수기간']==5].sort_values('최악',ascending=False).head(10)[cols+['최악']].round(2).to_string(index=False))
# (3) walk-forward: 매 앵커마다 그 시점에 h20 확정된 과거 앵커로 h20 평균 1등(및 상위 20개 평균) 선택
wf=[];wf20=[]
for j,a in enumerate(anchors):
    known=[i for i,x in enumerate(anchors) if TI[x]+21<=TI[a] and closed20[i]]
    if len(known)<8: continue
    sc=np.nanmean(D[0][:,known],axis=1); best=int(np.nanargmax(sc)); top20=np.argsort(-np.nan_to_num(sc,nan=-9))[:20]
    wf.append(dict(anchor=a,best=name(forms[best]),ex20=D[0][best,j],ex40=D[1][best,j],now=D[3][best,j],ex20_top20=np.nanmean(D[0][top20,j]),now_top20=np.nanmean(D[3][top20,j])))
W=pd.DataFrame(wf)
def bb(x,block=5):
    x=np.asarray(x,float); x=x[np.isfinite(x)]; L=len(x)
    if L<6: return (np.nan,np.nan)
    r=np.random.default_rng(7); b=max(1,min(block,L//3)); st=r.integers(0,L,(3000,int(np.ceil(L/b)))); ix=(st[:,:,None]+np.arange(b))%L
    mm=x[ix.reshape(3000,-1)[:,:L]].mean(1); return tuple(np.quantile(mm,[.025,.975]))
print("\n=== (3) 매번 과거로만 1등 골라 적용(정직한 시험)")
for c,lab in (('ex20','20일 확정'),('ex40','40일 확정'),('now','9/29까지')):
    x=W[c].dropna(); lo,hi=bb(x.values); print(f"   1등 공식: {lab} v30 대비 {x.mean():+.2f} [{lo:+.2f},{hi:+.2f}] 이긴날 {(x>0).mean():.0%} (n{len(x)})")
for c,lab in (('ex20_top20','20일 확정'),('now_top20','9/29까지')):
    x=W[c].dropna(); lo,hi=bb(x.values); print(f"   상위20 평균: {lab} v30 대비 {x.mean():+.2f} [{lo:+.2f},{hi:+.2f}] (n{len(x)})")
W['m']=W.anchor.str[4:6]; print("   월별(1등, 20일 확정 / 9/29까지):", W.groupby('m')[['ex20','now']].mean().round(2).to_dict('index'))
print("   시점별로 고른 1등(바뀐 것만):")
prev=None
for r in W.itertuples():
    if r.best!=prev: print(f"     {r.anchor}: {r.best}"); prev=r.best
T.to_csv(os.path.join(_WORK,'search_summary.csv'),index=False); pd.concat([T[T['양수기간']==5],T.nlargest(300,'h20')]).drop_duplicates('name').to_csv(os.path.join(HERE,'search_top.csv'),index=False); W.to_csv(os.path.join(HERE,'search_walkforward.csv'),index=False)
