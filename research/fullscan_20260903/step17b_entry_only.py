import numpy as np, pandas as pd
exec(open("step17_regime_checks.py",encoding="utf-8").read().split("base=series(M)")[0])
base=series(M); on20=sig(20,1); on3=sig(20,3); on60=sig(60,1)
rows=[]
for nm,on in [("SMA20",on20),("확인3일",on3),("SMA60",on60)]:
    for low in [0.5,0.0]:
        r=series(M,on,"entry",low=low); st=stats(r); st.update(variant=f"신규진입만 {nm} → {int(low*100)}%",cut="전체"); rows.append(st)
        for y in ["2024","2025","2026"]:
            m=np.array([d.startswith(y) for d in P.dates]); s2=stats(np.where(m,r,np.nan)); s2.update(variant=f"신규진입만 {nm} → {int(low*100)}%",cut=y); rows.append(s2)
st=stats(base); st.update(variant="없음",cut="전체"); rows.append(st)
for y in ["2024","2025","2026"]:
    m=np.array([d.startswith(y) for d in P.dates]); s2=stats(np.where(m,base,np.nan)); s2.update(variant="없음",cut=y); rows.append(s2)
V=pd.DataFrame(rows); print(V.pivot_table(index="variant",columns="cut",values=["cagr","mdd","sharpe"],sort=False).round(3).to_string())
