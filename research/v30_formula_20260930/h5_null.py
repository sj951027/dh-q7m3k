import os, numpy as np
src=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'v30_search.py'),encoding='utf-8').read().split("t0=time.time()")[0]; exec(src)
mon=np.array(anchors); cntb=np.zeros(len(anchors))
for ai,F,v30,Y in groups: cntb[ai]+=1
for p in range(4):
    rng=np.random.default_rng(3000+p); gp=[(ai,F,v30,Y[rng.permutation(len(Y))]) for ai,F,v30,Y in groups]
    Rn=run(gp); bn=np.zeros((4,len(anchors)),np.float32)
    for ai,F,v30,Y in gp: bn[:,ai]+=np.nanmean(Y[np.argsort(-v30)[:10]],axis=0)
    bn/=cntb; D=Rn[2]-bn[2][None,:]; cl=~np.isnan(bn[2])
    h5=np.nanmean(D[:,cl],1); P=np.column_stack([np.nanmean(D[:,np.char.startswith(mon,'2026'+m)&cl],1) for m in ('06','07','08','09')])
    print(f"perm{p}: 5일 1등 {np.nanmax(h5):+.2f} · 상위0.1% {np.nanpercentile(h5,99.9):+.2f} · 4개월 모두 양수 {int((P>0).all(1).sum()):,}개 · 최악월 최고 {np.nanmax(P.min(1)):+.2f}",flush=True)
