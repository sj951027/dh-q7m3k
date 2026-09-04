# step13: 국면 스위칭 앙상블 백테스트 (3년, PIT 국면 라벨=전일 기준). 기준=조용함(lv60+to20, lv_e 뼈대) 상시.
# 스위칭 규칙은 사전 고정(1차 보고서 §2 표에서 유도 — in-sample) → 정직한 숫자는 검증창(2025-07~)만.
import numpy as np, pandas as pd, os
from fslib import *
P=Panel(); ok=guards(P); F=factors(P); R=regimes(P); c=P.close.astype(np.float64)
F["hl_range20"]=roll_mean((P.high-P.low)/P.close,20,10)
H2=dict(HYP); H2.update({"hl_range20":-1})
FW={h:excess(fwd(P,h),ok) for h in [20,60]}; start=P.idx("20240101"); te0=P.idx("20250701"); rg=R.regime_pit.values
# 빠른 국면(보조): 코스닥 > 20일선 (전일 기준)
kq=pd.Series(P.kosdaq).ffill(); fast=(kq>kq.rolling(20).mean()).shift(1).values
base=rank_sum(F,["lv60","to20"],H2,ok)
RK={n:rank01(np.where(ok,F[n]*H2[n],np.nan)) for n in ["rsi14","amt20","upratio63","nh252","size","on60","dlow252"]}
RK={k:np.where(np.isfinite(v),v,0.5) for k,v in RK.items()}
def mk(rules):
    """rules: regime -> list of add factors. 국면별로 다른 순위합."""
    sc=base.copy()
    for g,adds in rules.items():
        rows=(rg==g) if g in ("강세","조정","반등","약세") else (fast==(g=="fast_up"))
        for a in adds: sc[rows]=sc[rows]+RK[a][rows]
    return sc
S={"A 조용함 상시(lv_e)":base,
   "S1 약세·반등:+RSI↓ / 강세·조정:+upratio":mk({"약세":["rsi14"],"반등":["rsi14"],"강세":["upratio63"],"조정":["upratio63"]}),
   "S2 약세:+RSI↓+저유동 / 강세:+size+nh252":mk({"약세":["rsi14","amt20"],"강세":["size","nh252"]}),
   "S3 약세만 +RSI↓":mk({"약세":["rsi14"]}),
   "S4 강세만 +size":mk({"강세":["size"]}),
   "S5 빠른국면: 20일선 아래 +RSI↓ / 위 +upratio":mk({"fast_dn":["rsi14"],"fast_up":["upratio63"]}),
   "S6 약세:+on60회피 / 강세:+upratio+nh252":mk({"약세":["on60"],"강세":["upratio63","nh252"]}),
   "B 항상 +RSI↓ (대조)":base+RK["rsi14"],"C 항상 +upratio (대조)":base+RK["upratio63"]}
rows=[]
IC={k:spearman_rows(v,FW[20],ok) for k,v in S.items()}
def kret(mask,k,t):
    a=t+1;b=a+k
    if b>=P.T: return np.nan
    with np.errstate(all="ignore"): r=c[b]/c[a]-1
    v=r[mask[t]]; v=v[np.isfinite(v)&(np.abs(v)<5)]; return v.mean() if len(v)>=5 else np.nan
for k,v in S.items():
    d=IC[k]-IC["A 조용함 상시(lv_e)"]; o=dict(model=k)
    for nm,sel in [("전체3년",np.arange(P.T)>=start),("검증창(25-07~)",np.arange(P.T)>=te0)]:
        s=sel&np.isfinite(d); m,lo,hi,n=boot_ci(d[s],400,block=5); ic=float(np.nanmean(IC[k][s]))
        o[nm]=f"IC {ic:+.3f} | diff {m:+.3f}[{lo:+.2f},{hi:+.2f}]"
    for g in ["강세","조정","반등","약세"]:
        s=(rg==g)&np.isfinite(d); s[:start]=False; m,lo,hi,n=boot_ci(d[s],300,block=5); o[g]=f"{m:+.3f}[{lo:+.2f},{hi:+.2f}]"
    M=pd.DataFrame(np.where(ok,v,np.nan)).rank(axis=1,ascending=False).values<=20
    rr=np.array([kret(M,40,t) for t in range(start,P.T)]); s=np.isfinite(rr)
    rt=np.array([kret(M,40,t) for t in range(te0,P.T)]); st=np.isfinite(rt)
    o["top20 40d 비용후/20d 전체"]=f"{(rr[s].mean()*0.5-0.0025)*100:+.2f}%"; o["검증창"]=f"{(rt[st].mean()*0.5-0.0025)*100:+.2f}%"
    rows.append(o)
pd.set_option("display.width",320); pd.set_option("display.max_colwidth",60)
df=pd.DataFrame(rows); print(df.to_string()); df.to_csv(os.path.join(OUT,"regime_switch.csv"),index=False)
print("\n국면 라벨 일수(검증창):",pd.Series(rg[te0:]).value_counts().to_dict())
