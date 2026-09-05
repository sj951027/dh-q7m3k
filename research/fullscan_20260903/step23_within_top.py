# step23 (2026-09-05): ① '크게 오른 종목'은 어디서 나오나(사전에 걸러지나) ② 조용함 상위10% 안에서 2차 정렬로 더 오를 종목을 고를 수 있나 (3년, h20)
import numpy as np, pandas as pd, os
from fslib import *
exec(open("step18_factor_zoo2.py",encoding="utf-8").read().split("H=[5,20,40,60]")[0])
def fwdh(hh):
    f=np.full_like(c,np.nan); a=1; b=1+hh
    with np.errstate(all="ignore"): f[:P.T-b]=c[b:]/c[a:P.T-b+a]-1
    f[np.abs(f)>5]=np.nan; return f
F.update({k:v for k,v in F0.items() if k not in F}); f20=fwdh(20); ex20=excess(f20,ok)
quiet=rank_sum(F,["lv60","to20"],HYP,ok); rq=rank01(np.where(ok,quiet,np.nan))
anch=np.arange(start,P.T)[::5]
# ① 20일 수익 상위10%(대박)·하위10%(대손) 종목이 조용함 순위 어느 구간에서 나왔나
bins=[0,0.1,0.3,0.5,0.7,0.9,1.0]; lab=["하위10%","10~30","30~50","50~70","70~90","상위10%"]
win_cnt=np.zeros(6); lose_cnt=np.zeros(6); tot=np.zeros(6); avg=np.zeros(6); win_avg=np.zeros(6)
for t in anch:
    m=np.isfinite(rq[t])&np.isfinite(f20[t]); r=f20[t][m]; q=rq[t][m]
    hi=r>=np.nanquantile(r,0.9); lo=r<=np.nanquantile(r,0.1)
    for i in range(6):
        s=(q>bins[i])&(q<=bins[i+1]) if i>0 else (q<=bins[1])
        tot[i]+=s.sum(); win_cnt[i]+=(s&hi).sum(); lose_cnt[i]+=(s&lo).sum(); avg[i]+=np.nansum(ex20[t][m][s])
print("① 조용함 순위 구간별 — 20일 '대박(상위10%)' 비율 / '대손(하위10%)' 비율 / 평균 초과수익(%p)")
for i in range(6): print(f"  {lab[i]:8s} 대박 {win_cnt[i]/tot[i]:5.1%}  대손 {lose_cnt[i]/tot[i]:5.1%}  평균초과 {avg[i]/tot[i]*100:+.2f}")
# ② 상위10% 안에서 2차 정렬: 각 후보 X 로 5분위 → 최상 5분위 − 최하 5분위 초과수익, 국면별·연도별 부호
SIGN={"nh252":+1,"mom_consist":+1,"size":+1,"amihud20":-1,"upvol20":-1,"clv20":+1,"min_ret20":+1,"dlow252":-1,"rsi14":-1,"ret5":-1,"mom21":+1,"mom63":+1,"hl_range20":-1,"lv60":-1,"to20":-1,"sma20gap":+1,"max5_21":-1,"skew60":-1,"gap_abs20":-1,"logprice":+1,"vol_dry":-1,"days_since_high":-1}
rg=R.regime_pit.values; rows=[]
for nm,sg in SIGN.items():
    x=F[nm]*sg; d=[]; top_ex=[]; d_rg={g:[] for g in ["강세","조정","반등","약세"]}; d_yr={y:[] for y in ["2024","2025","2026"]}
    for t in anch:
        m=(rq[t]>=0.9)&np.isfinite(x[t])&np.isfinite(ex20[t])
        if m.sum()<30: continue
        xv=x[t][m]; ev=ex20[t][m]; q1,q4=np.nanquantile(xv,[0.2,0.8])
        hi=ev[xv>=q4].mean(); lo=ev[xv<=q1].mean(); d.append(hi-lo); top_ex.append(hi-ev.mean())
        if rg[t] in d_rg: d_rg[rg[t]].append(hi-lo)
        d_yr[P.dates[t][:4]].append(hi-lo)
    m_,lo_,hi_,n=boot_ci(d,500,block=4)
    rows.append(dict(second=nm,spread_pp=m_*100,lo=lo_*100,hi=hi_*100,n=n,top_vs_all_pp=np.mean(top_ex)*100,
                     **{f"rg_{g}":np.mean(v)*100 if v else np.nan for g,v in d_rg.items()},**{f"y{y}":np.mean(v)*100 if v else np.nan for y,v in d_yr.items()}))
D=pd.DataFrame(rows).sort_values("spread_pp",ascending=False); pd.set_option("display.width",250)
print("\n② 조용함 상위10% 안에서 X 최상5분위 − 최하5분위 h20 초과(%p) · '최상5분위 − 상위10% 전체 평균' · 국면·연도 부호")
print(D.round(2).to_string(index=False))
D.to_csv(os.path.join(OUT,"within_top_second_sort.csv"),index=False)
