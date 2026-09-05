# -*- coding: utf-8 -*-
"""ptw_counterfactual_20260905.py — 실제 매수일(7/1~9/3, 26일)에 '어느 모델 상위를 사서 어떻게 팔았으면' 얼마였나 (관측 전용)
규칙은 전부 사전에 정할 수 있는 것만(뒤늦게 아는 정보 없음): 매수=그날 종가(사용자 매수일), 청산=20일/40일/트레일링 10·15%/보유중.
상한선(사후 최적 타이밍)은 '얼마나 못 잡는지' 보여주려고만 병기."""
import sqlite3, pandas as pd, numpy as np
oc=sqlite3.connect("file:../dh-q7m3k-data/ohlcv.db?mode=ro",uri=True); hc=sqlite3.connect("file:history.db?mode=ro",uri=True)
px=pd.read_sql("select ticker,date,close,high,low from daily_ohlcv where date>='20260601'",oc); px["ticker"]=px.ticker.astype(str)
C=px.pivot_table(index="date",columns="ticker",values="close"); H=px.pivot_table(index="date",columns="ticker",values="high"); L=px.pivot_table(index="date",columns="ticker",values="low")
dates=list(C.index); di={d:i for i,d in enumerate(dates)}; last=dates[-1]
MODELS={"lv_b":("lowvol_scores","lowvol_score"),"lv_a":("lowvol_scores","lowvol_score"),"v30":("v3_scores","final_score_v3"),"sv_a":("wu_scores","wu_score"),"px_a":("wu_scores","wu_score"),"lv_e":("lowvol_scores","lowvol_score")}
S={}
for m,(tb,col) in MODELS.items():
    s=pd.read_sql(f"select run_id,market,ticker,{col} s from {tb} where model_id=?",hc,params=(m,)); s["ticker"]=s.ticker.astype(str); s["run_id"]=s.run_id.astype(str); S[m]=s
def picks(m,a,n=10):
    s=S[m]; runs=sorted(r for r in s.run_id.unique() if r<a)
    if not runs: return []
    g=s[s.run_id==runs[-1]]
    if m in ("sv_a","px_a"): top=g.nlargest(2*n,"s").ticker.tolist()           # 전체시장 단일 순위 → 20
    else: top=g.sort_values("s",ascending=False).groupby("market").head(n).ticker.tolist()
    return [t for t in top if t in C.columns and np.isfinite(C.loc[a,t]) if a in C.index]
def path(t,a):
    i=di[a]; c=C[t].values[i:]; h=H[t].values[i:]; l=L[t].values[i:]; return c,h,l
def exit_ret(t,a,rule):
    c,h,l=path(t,a); e=c[0]
    if not np.isfinite(e) or e<=0: return np.nan,np.nan
    n=len(c)-1
    if rule.startswith("hold"):
        k=int(rule[4:]); j=min(k,n); return c[j]/e-1, j
    if rule.startswith("trail"):
        pct=float(rule[5:])/100; peak=e
        for j in range(1,n+1):
            peak=max(peak,h[j] if np.isfinite(h[j]) else peak)
            if np.isfinite(l[j]) and l[j]<=peak*(1-pct): return peak*(1-pct)/e-1, j
            if j>=40: return c[j]/e-1, j
        return c[n]/e-1, n
    if rule=="best":   # 사후 최적(상한): 40일 내 최고 종가
        j=min(40,n); k=int(np.nanargmax(c[1:j+1]))+1; return c[k]/e-1, k
cl=pd.read_csv("research/ptw_closed_20260905.csv",dtype={"code":str}); po=pd.read_csv("research/ptw_positions_20260905.csv",dtype={"code":str})
buys=sorted(set(["2026"+x.replace("-","") for x in cl[cl.strategy!="스윙"].first_buy]+[x.replace("-","") for x in po.first_buy]))
buys=[b for b in buys if b in di and b>="20260701"]
print("실제 매수일",len(buys),"일:",buys[0],"~",buys[-1])
RULES=["hold20","hold40","trail10","trail15","best"]
rows=[]
for m in MODELS:
    for rule in RULES:
        per=[]; closed=0; tot=0
        for a in buys:
            pk=picks(m,a)
            if not pk: continue
            rs=[exit_ret(t,a,rule)[0] for t in pk]; rs=[r for r in rs if np.isfinite(r)]
            if rs: per.append(np.mean(rs)); tot+=1
            k=int(rule[4:]) if rule.startswith("hold") else 40
            if di[a]+k<len(dates): closed+=1
        rows.append(dict(model=m,rule=rule,n_days=tot,closed_windows=closed,mean_ret=np.mean(per)*100 if per else np.nan,median=np.median(per)*100 if per else np.nan,win=np.mean(np.array(per)>0) if per else np.nan))
D=pd.DataFrame(rows); pd.set_option("display.width",250)
print("\n== 모델 상위(시장별 10 / 전체 20)를 실제 매수일 종가에 사서 규칙대로 팔았을 때 — 매수일별 평균수익의 평균 (창 안 닫힌 건 9/4 종가로 절단)")
print(D.pivot(index="model",columns="rule",values="mean_ret").round(2).to_string()); print("\n승률(매수일 기준):"); print(D.pivot(index="model",columns="rule",values="win").round(2).to_string())
# 실제 종목에 규칙 적용
print("\n== 실제로 산 종목(저변동·모멘텀 태그 + 보유중)에 같은 규칙을 적용했다면 (매수가=실제 평단 아님, 매수일 종가 기준)")
act=pd.concat([cl[cl.strategy!="스윙"][["code","first_buy","ret_pct"]].assign(a=lambda d:"2026"+d.first_buy.str.replace("-","")), po[["code","first_buy","pnl"]].rename(columns={"pnl":"ret_pct"}).assign(a=lambda d:d.first_buy.str.replace("-",""))])
act=act[act.a.isin(di)]
out=[]
for _,r in act.iterrows():
    t=r.code
    if t not in C.columns: continue
    rec=dict(code=t,a=r.a,actual=r.ret_pct)
    for rule in RULES: rec[rule]=exit_ret(t,r.a,rule)[0]*100
    out.append(rec)
A=pd.DataFrame(out); print(A[["actual"]+RULES].mean().round(2).to_string()); print("건수",len(A),"| 실제 평균 대비: ", {k: round(A[k].mean()-A.actual.mean(),2) for k in RULES})
A.to_csv("research/fullscan_20260903/out/ptw_counterfactual_actual.csv",index=False); D.to_csv("research/fullscan_20260903/out/ptw_counterfactual_models.csv",index=False)
