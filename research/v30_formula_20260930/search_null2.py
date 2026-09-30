import os, numpy as np, pandas as pd
src=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'v30_search.py'),encoding='utf-8').read().split("t0=time.time()")[0]; exec(src)
mon=np.array(anchors); per_masks=[np.char.startswith(mon,'202606'),np.char.startswith(mon,'202607'),np.char.startswith(mon,'202608'),(mon>='20260818')&(mon<'20260901'),mon>='20260901']
cntb=np.zeros(len(anchors))
for ai,F,v30,Y in groups: cntb[ai]+=1
res=[]
for p in range(4):
    rng=np.random.default_rng(2000+p); gp=[]
    for ai,F,v30,Y in groups: gp.append((ai,F,v30,Y[rng.permutation(len(Y))]))
    Rn=run(gp); bn=np.zeros((4,len(anchors)),np.float32)
    for ai,F,v30,Y in gp: bn[:,ai]+=np.nanmean(Y[np.argsort(-v30)[:10]],axis=0)
    bn/=cntb; D=Rn-bn[:,None,:]
    cols=[np.nanmean(D[0][:,per_masks[0]],1),np.nanmean(D[0][:,per_masks[1]],1),np.nanmean(D[0][:,per_masks[2]],1),np.nanmean(D[3][:,per_masks[3]],1),np.nanmean(D[3][:,per_masks[4]],1)]
    P=np.column_stack(cols); allpos=(P>0).all(1); worst=P.min(1)
    res.append((allpos.mean(),allpos.sum(),np.nanmax(worst),np.sort(worst)[-10]))
    print(f"perm{p}: 5기간 모두 양수 {allpos.sum():,}개 ({allpos.mean():.1%}) · 최악기간 최고 {np.nanmax(worst):+.2f} · 10위 {np.sort(worst)[-10]:+.2f}",flush=True)
