# 지수 정기변경 편입 예측기 — PREREG_index_predictor.md 규칙 그대로. DB 사본 읽기 전용.
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "downside_20260930"))   # flags.py·panel.py 재사용(DB 경로는 panel.py 참조)
import flags as fl
C=fl.C; V=fl.V; SH=fl.SH; MK=fl.MK; D=fl.DATES; TI=fl.TI; MD=fl.MD
HERE=os.path.dirname(os.path.abspath(__file__))
ch=pd.read_csv(os.path.join(HERE,'index_changes.csv'),dtype=str)
sp=pd.read_csv(os.path.join(HERE,'index_special_events.csv'),dtype=str)
cur={ 'KOSPI200':set(pd.read_csv(os.path.join(HERE,'constituents_KOSPI200.csv'),dtype=str).code.str.zfill(6)),
      'KOSDAQ150':set(pd.read_csv(os.path.join(HERE,'constituents_KOSDAQ150.csv'),dtype=str).code.str.zfill(6))}
ch['code']=ch.code.str.zfill(6)
REV=['202312','202406','202412','202506','202512','202606']
CFG={'KOSPI200':dict(mkt='kospi',N=200,liq=0.85,inq=0.9,outq=1.1,bench='KOSPI'),
     'KOSDAQ150':dict(mkt='kosdaq',N=150,liq=0.80,inq=0.8,outq=1.2,bench='KOSDAQ')}
def last_td(yyyymm):  # 그 달 마지막 거래일
    c=[d for d in D if d.startswith(yyyymm)]; return c[-1] if c else None
def review_date(rev):  # 6월 변경→4월 말, 12월 변경→10월 말
    y,m=rev[:4],rev[4:]; return last_td(y+('04' if m=='06' else '10'))
# 구성종목 복원(거꾸로): 적용 후 명단 → 적용 전 명단
member_before={}
for idx in CFG:
    M=set(cur[idx])
    # 2025-11-25 삼성에피스 특례(12월 정기변경 전) — 12월 적용 전 명단엔 있으나 10월 심사 때는 없음
    for rev in sorted(ch.review.unique(),reverse=True):
        g=ch[(ch['index']==idx)&(ch.review==rev)]
        ins=set(g[g.action=='IN'].code); outs=set(g[g.action=='OUT'].code)
        before=(M-ins)|outs
        if idx=='KOSPI200' and rev=='202512': before-= {'0126Z0'}
        if idx=='KOSPI200' and rev=='202312': before=(before-{'450080'})|{'381970'}
        member_before[(idx,rev)]=before; M=before
first_px=C.notna().idxmax()
rows=[]; evs=[]
for idx,cfg in CFG.items():
    for rev in REV:
        rd=review_date(rev); t=TI[rd]; w0=max(0,t-125)
        g=ch[(ch['index']==idx)&(ch.review==rev)]
        ann=g.announce_date.iloc[0]; eff=g.effective_date.iloc[0]
        cols=[c for c in C.columns if MK.get(c)==cfg['mkt'] and c.endswith('0')]
        win=slice(D[w0],rd)
        cw=C.loc[win,cols]; mc=(cw*SH.loc[win,cols]).mean(); tv=(cw*V.loc[win,cols]).mean()
        cover=cw.notna().mean()
        fp=first_px[cols]
        age_ok=(fp==D[0])|(fp.map(lambda d: TI[d])<=t-126)
        elig=(cover>=0.6)&age_ok&mc.notna()&tv.notna()
        u=elig[elig].index
        tvr=tv[u].rank(ascending=False); liq_ok=tvr<=cfg['liq']*len(u)
        u2=liq_ok[liq_ok].index; r=mc[u2].rank(ascending=False)
        mem=member_before[(idx,rev)]
        pred_in=set(r[(r<=cfg['inq']*cfg['N'])&~r.index.isin(mem)].index)
        pred_out=set(m for m in mem if m in cols and (m not in r.index or r[m]>cfg['outq']*cfg['N']))
        act_in=set(g[g.action=='IN'].code); act_out=set(g[g.action=='OUT'].code)
        k=len(act_in); topk=set(r[~r.index.isin(mem)].sort_values().index[:k])
        rows.append(dict(index=idx,rev=rev,review_date=rd,ann=ann,eff=eff,n_member_rebuilt=len(mem),n_elig=len(u2),
            act_in=len(act_in),pred_in=len(pred_in),hit_in=len(pred_in&act_in),
            act_out=len(act_out),pred_out=len(pred_out),hit_out=len(pred_out&act_out),topk_hit=len(topk&act_in),
            miss_names='|'.join(sorted(g[(g.action=='IN')&~g.code.isin(pred_in)].name)),
            false_names=','.join(sorted(pred_in-act_in))))
        # 수익 창
        def idx_of(d,after=False):
            i=int(np.searchsorted(D,d)); 
            if after: i=i if (i<len(D) and D[i]>d) else i+1
            return i
        tA=t+1; tAnn=idx_of(ann) if ann in TI else int(np.searchsorted(D,ann)); tEff=int(np.searchsorted(D,eff)); tPre=tEff-1
        wins={'W1':(tA,tAnn),'W2':(tAnn+1,tPre),'W3':(tPre,min(tPre+20,len(D)-1)),'FULL':(tA,tPre)}
        liq=fl.GUARD.iloc[t][cols]
        groups={'pred_in':pred_in,'act_in':act_in,'hit':pred_in&act_in,'false_in':pred_in-act_in,'miss_in':act_in-pred_in,'pred_out':pred_out,'act_out':act_out}
        for wn,(a,b) in wins.items():
            if b>=len(D) or a>=b: continue
            ret=C.iloc[b][cols]/C.iloc[a][cols]-1
            bench_ew=ret[liq[liq].index].mean(); bench_ix=MD[cfg['bench']].iloc[b]/MD[cfg['bench']].iloc[a]-1
            for gn,s in groups.items():
                s=[x for x in s if x in ret.index and np.isfinite(ret[x])]
                for x in s: evs.append(dict(index=idx,rev=rev,win=wn,group=gn,code=x,ret=ret[x],ex_ew=ret[x]-bench_ew,ex_ix=ret[x]-bench_ix,days=b-a))
R=pd.DataFrame(rows); E=pd.DataFrame(evs)
R.to_csv(os.path.join(HERE,'pred_hits.csv'),index=False); E.to_csv(os.path.join(HERE,'pred_returns.csv'),index=False)
pd.set_option('display.width',250); pd.set_option('display.max_colwidth',80)
print(R.drop(columns=['miss_names','false_names']).to_string(index=False))
for idx in CFG:
    s=R[R['index']==idx]
    print(f"\n{idx} 합계: 편입 정밀도 {s.hit_in.sum()}/{s.pred_in.sum()} = {s.hit_in.sum()/max(1,s.pred_in.sum()):.0%} · 재현율 {s.hit_in.sum()}/{s.act_in.sum()} = {s.hit_in.sum()/s.act_in.sum():.0%} · "
          f"편출 정밀도 {s.hit_out.sum()}/{s.pred_out.sum()} = {s.hit_out.sum()/max(1,s.pred_out.sum()):.0%} · 재현율 {s.hit_out.sum()}/{s.act_out.sum()} = {s.hit_out.sum()/s.act_out.sum():.0%} · 참고 top-k {s.topk_hit.sum()}/{s.act_in.sum()}")
def rbci(df,col):  # 회차 블록 부트스트랩
    revs=df.rev.unique(); rng=np.random.default_rng(930); bs=[]
    by={r:df[df.rev==r][col].values for r in revs}
    for _ in range(3000):
        pick=rng.choice(revs,len(revs)); v=np.concatenate([by[p] for p in pick]); bs.append(v.mean() if len(v) else np.nan)
    return np.nanpercentile(bs,[2.5,97.5])
print("\n수익(%p, 동일가중 대비 / 지수 대비) - n=종목·회차 수")
out=[]
for (idx,wn,gn),g in E.groupby(['index','win','group']):
    lo,hi=rbci(g,'ex_ew'); byrev=g.groupby('rev').ex_ew.mean()
    out.append(dict(index=idx,win=wn,group=gn,n=len(g),days=round(g.days.mean()),ex_ew=g.ex_ew.mean()*100,lo=lo*100,hi=hi*100,ex_ix=g.ex_ix.mean()*100,
                    pos_rev=f"{(byrev>0).sum()}/{len(byrev)}",win_rate=(g.ex_ew>0).mean()))
O=pd.DataFrame(out); O.to_csv(os.path.join(HERE,'pred_summary.csv'),index=False)
order={'W1':0,'W2':1,'W3':2,'FULL':3}; O['o']=O.win.map(order)
print(O.sort_values(['index','group','o']).drop(columns='o').round(2).to_string(index=False))
print("\n미적중 편입(예측 못한 실제 편입):"); print(R[['index','rev','miss_names']].to_string(index=False))
