# 공통: 후보 순서(점수 내림차순)에서 기준 top10 vs 플래그 제외 top10, 무작위 교체 플라시보
import numpy as np
def run_one(order_js, ret, flagrows, top=10, n_pl=100, rng=None):
    """order_js: 후보 열 인덱스(점수 내림차순, 희석 제외·진입가 있음). ret: 열 인덱스→수익 배열. flagrows: {flag: bool 배열(열 전체)}.
    반환 {flag: (diff, k, placebo_diffs)} 및 base"""
    base_idx=order_js[:top]; base=ret[base_idx].mean(); out={}
    for fn,fr in flagrows.items():
        keep=[j for j in order_js if not fr[j]]
        if len(keep)<5: out[fn]=(0.0,0,np.zeros(n_pl)); continue
        fidx=keep[:top]; k=len(set(base_idx)-set(fidx)); diff=ret[fidx].mean()-base
        pl=np.zeros(n_pl)
        if k>0:
            for i in range(n_pl):
                drop=set(rng.choice(base_idx,k,replace=False)); pick=[j for j in order_js if j not in drop][:top]
                pl[i]=ret[pick].mean()-base
        out[fn]=(diff,k,pl)
    return base,out
def bci(x,block,reps=3000,seed=930):
    x=np.asarray(x,float); x=x[np.isfinite(x)]; L=len(x)
    if L<4: return (float(np.mean(x)) if L else np.nan,np.nan,np.nan)
    block=max(1,min(block,L//2)); rng=np.random.default_rng(seed); st=rng.integers(0,L,(reps,int(np.ceil(L/block)))); ix=(st[:,:,None]+np.arange(block))%L
    mm=x[ix.reshape(reps,-1)[:,:L]].mean(axis=1); return (float(x.mean()),float(np.quantile(mm,.025)),float(np.quantile(mm,.975)))
