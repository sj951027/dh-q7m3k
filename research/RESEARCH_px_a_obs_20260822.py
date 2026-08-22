# -*- coding: utf-8 -*-
"""px_a 관측 9거래일(20260810~20260821) 세부 분해 — 관측 전용, 판정 아님.
재현: repo 루트에서 python research/RESEARCH_px_a_obs_20260822.py
규약: ENTRY_LAG=1(다음날 종가 진입), 이상치 |ret|>32% 컷(leaderboard §25와 정합),
     일별 시장효과 제거 = 당일 유니버스 중앙값 차감(excess, %p)."""
import sqlite3, json, numpy as np, pandas as pd

hist = sqlite3.connect("file:history.db?mode=ro", uri=True)
oh = sqlite3.connect("file:../dh-q7m3k-data/ohlcv.db?mode=ro", uri=True)

px = pd.read_sql("SELECT CAST(run_id AS TEXT) run_id, market, ticker, wu_rank, n_universe "
                 "FROM wu_scores WHERE model_id='px_a'", hist)
px["rank_pct"] = px.wu_rank / px.n_universe
days = sorted(px.run_id.unique())
print("앵커일:", days, "| 일평균 유니버스:", int(px.groupby('run_id').size().mean()))

P = pd.read_sql("SELECT ticker, date, close, volume, shares FROM daily_ohlcv WHERE date>='20250601'", oh)
C = P.pivot_table(index="date", columns="ticker", values="close")
V = P.pivot_table(index="date", columns="ticker", values="volume")
S = P.pivot_table(index="date", columns="ticker", values="shares")
dates = list(C.index)
r = C.pct_change(fill_method="pad")

# 성분(wu_score.py 정의 그대로)
F = {
 "lv60": r.rolling(60, min_periods=30).std(),
 "lv20": r.rolling(20, min_periods=10).std(),
 "to20": (V / S.where(S > 0)).rolling(20, min_periods=10).mean(),
 "nh252": C / C.rolling(252, min_periods=120).max() - 1,
}
amt20 = (C * V).rolling(20, min_periods=10).mean() / 1e8  # 억원
mcap = (C * S) / 1e12  # 조원

def fwd(day, h):
    i = dates.index(day)
    if i + 1 + h >= len(dates): return None
    e, x = C.iloc[i+1], C.iloc[i+1+h]
    ret = (x/e - 1) * 100
    return ret.where(ret.abs() <= 32)

rows = []
for d in days:
    sub = px[px.run_id == d].set_index("ticker")
    rec = pd.DataFrame({"rank_pct": sub.rank_pct, "market": sub.market})
    for h in (1, 3, 5):
        fr = fwd(d, h)
        rec[f"h{h}"] = fr.reindex(rec.index) if fr is not None else np.nan
    for k in F: rec[k] = F[k].loc[d].reindex(rec.index)
    rec["amt20"] = amt20.loc[d].reindex(rec.index)
    rec["mcap"] = mcap.loc[d].reindex(rec.index)
    rec["price"] = C.loc[d].reindex(rec.index)
    for h in (1,3,5):
        col=f"h{h}"
        if rec[col].notna().sum()>50: rec[f"e{h}"]=rec[col]-rec[col].median()
        else: rec[f"e{h}"]=np.nan
    rec["run_id"]=d; rows.append(rec.reset_index())
A = pd.concat(rows, ignore_index=True)
navail = {h: A.groupby("run_id")[f"e{h}"].apply(lambda s: s.notna().sum()>0).sum() for h in (1,3,5)}
print("h별 관측 앵커일수:", navail)

print("\n[A] 십분위(순위%) 초과수익 %p — pooled, 일별 중앙값 차감")
A["dec"] = np.minimum((A.rank_pct*10).astype(int)+1, 10)
for h in (1,3,5):
    g = A.groupby("dec")[f"e{h}"].agg(["mean","count"]).round(2)
    print(f" h{h} (앵커 {navail[h]}일):", {i:(row['mean'],int(row['count'])) for i,row in g.iterrows()})

print("\n[B] 상위 10%(1분위) 내부 — h5 승자 vs 패자 특성 중앙값 (h5 앵커 3일 pooled)")
top = A[(A.dec==1) & A.e5.notna()].copy()
med = top.e5.median()
w, l = top[top.e5>med], top[top.e5<=med]
for c in ("price","mcap","amt20","lv60","lv20","to20","nh252"):
    print(f"  {c:6}: 승자 {w[c].median():.4g} vs 패자 {l[c].median():.4g}")
print("  시장: 승자", dict(w.market.value_counts()), "패자", dict(l.market.value_counts()), "| n =", len(w), "/", len(l))

print("\n[C] 성분별 h5 excess 상관(스피어만, 앵커 3일 각각)")
for k in ("lv60","lv20","to20","nh252","amt20","mcap"):
    ics = []
    for d in days:
        s = A[(A.run_id==d) & A.e5.notna()]
        if len(s) < 100: continue
        ics.append(round(float(s[k].rank().corr(s.e5.rank())), 3))
    print(f"  {k:6}: {ics}")

print("\n[D] 상위 50 단골(9일 중 7일 이상) + 8/11종가→8/21종가 수익")
cnt = px[px.wu_rank<=50].groupby("ticker").size()
regs = cnt[cnt>=7].index.tolist()
names = dict(pd.read_sql("SELECT DISTINCT ticker, name FROM stage1_oversold WHERE CAST(run_id AS TEXT)>='20260810'", hist).values)
e_, x_ = C.loc["20260811"], C.loc["20260821"]
out=[]
for t in regs:
    if t in C.columns and not np.isnan(e_.get(t, np.nan)):
        out.append((t, names.get(t, "?"), cnt[t], round((x_[t]/e_[t]-1)*100, 2)))
out.sort(key=lambda z: -z[3])
for o in out: print("  ", o)
uni_med = ((x_/e_-1)*100).median()
print("  (참고: 전 종목 같은 구간 중앙값 %.2f%%)" % uni_med)

print("\n[E] 상위 10% 층화 — 시장/시총3분위 h5 excess 평균")
top_all = A[(A.dec==1) & A.e5.notna()]
print("  시장:", top_all.groupby("market").e5.agg(["mean","count"]).round(2).to_dict("index"))
top_all = top_all.assign(szb=pd.qcut(top_all.mcap, 3, labels=["소","중","대"]))
print("  시총:", top_all.groupby("szb", observed=True).e5.agg(["mean","count"]).round(2).to_dict("index"))
