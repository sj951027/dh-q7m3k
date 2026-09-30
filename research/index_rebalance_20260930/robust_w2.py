# 발표 후(W2) 편입 종목 효과 강건성 — 회차별 · 상위 기여 제외 · 진입 지연 · 비용 · 중앙값 · 편출 대칭
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "downside_20260930"))   # flags.py·panel.py 재사용(DB 경로는 panel.py 참조)
import flags as fl
C=fl.C; D=fl.DATES; MK=fl.MK; MD=fl.MD
ch=pd.read_csv('index_changes.csv',dtype=str); ch['code']=ch.code.str.zfill(6)
rows=[]
for (idx,rev),g in ch[ch.review>='202312'].groupby(['index','review']):
    mkt='kospi' if idx=='KOSPI200' else 'kosdaq'; bench='KOSPI' if mkt=='kospi' else 'KOSDAQ'
    ann=g.announce_date.iloc[0]; eff=g.effective_date.iloc[0]
    tAnn=int(np.searchsorted(D,ann)); tEff=int(np.searchsorted(D,eff)); tPre=tEff-1
    cols=[c for c in C.columns if MK.get(c)==mkt]
    for lag in (1,2,3):
        a=tAnn+lag; b=tPre
        if a>=b: continue
        ret=C.iloc[b][cols]/C.iloc[a][cols]-1
        liq=fl.GUARD.iloc[tAnn][cols]; ew=ret[liq[liq].index].mean(); ix=MD[bench].iloc[b]/MD[bench].iloc[a]-1
        for act in ('IN','OUT'):
            for code,name in zip(g[g.action==act].code,g[g.action==act].name):
                if code in ret.index and np.isfinite(ret[code]):
                    rows.append(dict(index=idx,rev=rev,lag=lag,act=act,code=code,name=name,ret=ret[code],ex=ret[code]-ew,exi=ret[code]-ix,days=b-a))
E=pd.DataFrame(rows); E.to_csv('w2_robust.csv',index=False)
for idx in ('KOSDAQ150','KOSPI200'):
    for act in ('IN','OUT'):
        s=E[(E['index']==idx)&(E.act==act)&(E.lag==1)]
        byr=s.groupby('rev').agg(ex=('ex','mean'),n=('ex','size'),med=('ex','median'))
        print(f"\n[{idx} {act}] 발표 다음날 진입 → 변경일 전날: 평균 {s.ex.mean()*100:+.2f}%p · 중앙값 {s.ex.median()*100:+.2f}%p · 지수대비 {s.exi.mean()*100:+.2f}%p · n={len(s)} · 평균 보유 {s.days.mean():.0f}일")
        print("   회차별(평균/중앙값/n):", "; ".join(f"{r}: {a.ex*100:+.1f}/{a.med*100:+.1f}/{int(a.n)}" for r,a in byr.iterrows()))
        if act=='IN':
            srt=s.sort_values('ex',ascending=False)
            print("   상위 기여:", ", ".join(f"{r.name}({r.rev}) {r.ex*100:+.0f}" for r in srt.head(5).itertuples()))
            for k in (1,3,5): print(f"   상위 {k}개 제외 평균 {srt.iloc[k:].ex.mean()*100:+.2f}%p")
            for lag in (2,3):
                t=E[(E['index']==idx)&(E.act==act)&(E.lag==lag)]
                print(f"   진입 {lag}일 늦춤: {t.ex.mean()*100:+.2f}%p (보유 {t.days.mean():.0f}일, 회차 + {int((t.groupby('rev').ex.mean()>0).sum())}/{t.rev.nunique()})")
            print(f"   왕복비용 0.35%(규약)·0.5% 차감: {(s.ex.mean()-0.0035)*100:+.2f} / {(s.ex.mean()-0.005)*100:+.2f}%p")
            # 동일 회차 동일가중 바구니 = 회차 평균의 평균
            print(f"   회차 평균의 평균(바구니 기준): {byr.ex.mean()*100:+.2f}%p · 최저 회차 {byr.ex.min()*100:+.2f}")
