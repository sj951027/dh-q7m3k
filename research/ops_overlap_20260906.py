# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행. 읽기 전용. OPS_GUIDE(운영 권고) §5-1(v30·lv_b 둘 다 운용?) 참고 자료.
"""v30 vs lv_b 시장별 상위10 바스켓의 겹침·상관 — 같은 앵커에서 (a) 겹치는 종목 수 (b) h20·h40 초과의 앵커별 상관 (c) 반반 합친 바스켓의 성과."""
import sys; sys.argv=['x']
src=open('shadow_ops_portfolio.py',encoding='utf-8').read().split('rows_a, rows_t = [], []')[0]
exec(src)
B={}
for mid,(sql,reg) in SRC.items():
    S=pd.read_sql(sql,con); S["ticker"]=S.ticker.astype(str).str.zfill(6); S["run_id"]=S.run_id.astype(str)
    keep=lb.dedupe_by_anchor(S,didx,excl,reg=reg)
    for rid in keep:
        t=lb.anchor(rid,didx); B.setdefault(rid,{})[mid]=(t,basket(S[S.run_id==rid],rid))
rows=[]
for rid,d in sorted(B.items()):
    if len(d)<2: continue
    (t,b1),(t2,b2)=d["v30"],d["lv_b"]; s1=set(x[0] for x in b1); s2=set(x[0] for x in b2)
    rec=dict(run_id=rid,n_v30=len(s1),n_lvb=len(s2),overlap=len(s1&s2))
    for K in (20,40):
        e1,_,_=basket_ret(b1,t,K); e2,_,_=basket_ret(b2,t,K); eu,_,_=basket_ret(list({x[0]:x for x in b1+b2}.values()),t,K)
        rec[f"v30_{K}"]=e1; rec[f"lvb_{K}"]=e2; rec[f"union_{K}"]=eu
    rows.append(rec)
D=pd.DataFrame(rows); D.to_csv(OUT/"ops_overlap.csv",index=False)
print(f"공통 앵커 {len(D)}개 ({D.run_id.min()}~{D.run_id.max()})  바스켓 20+20 중 겹침 평균 {D.overlap.mean():.1f}종목 (최대 {D.overlap.max()})")
for K in (20,40):
    d=D.dropna(subset=[f"v30_{K}",f"lvb_{K}"])
    if len(d)<3: continue
    r=np.corrcoef(d[f"v30_{K}"],d[f"lvb_{K}"])[0,1]
    print(f" h{K}: n={len(d)}  v30 {d[f'v30_{K}'].mean():+.2f}  lv_b {d[f'lvb_{K}'].mean():+.2f}  합집합 {d[f'union_{K}'].mean():+.2f}%p | 앵커별 초과 상관 {r:+.2f} | 종목수 합집합 평균 {40-d.overlap.mean():.0f}")
    diff=(d[f"lvb_{K}"]-d[f"v30_{K}"]).values; lo,hi=boot_ci(diff); print(f"      lv_b−v30 {diff.mean():+.2f}  CI[{lo:+.2f},{hi:+.2f}]  · 앵커별 표준편차 v30 {d[f'v30_{K}'].std():.2f} lv_b {d[f'lvb_{K}'].std():.2f} 합집합 {d[f'union_{K}'].std():.2f}")
