# 모의계좌(cross_sim) 진입 지연 검증: 현행(신호 다음날 수익부터 반영) vs 올바른 방식(다음날 종가 매수 → 그 다음날 수익부터)
import sqlite3, sys
sys.path.insert(0, r"C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k")
import numpy as np, pandas as pd
import build_cross_sim as bcs
hc = sqlite3.connect(f"file:{bcs.HERE/'history.db'}?mode=ro", uri=True); oc = sqlite3.connect(f"file:{bcs.OHLCV}?mode=ro", uri=True)
scores = {}
for name, tbl, col, mid, reg in bcs.MODELS:
    if col is None:
        lg = pd.read_sql("SELECT run_id, ticker, per, pbr, rim_spread, div_yield FROM large_final WHERE run_id>=?", hc, params=(reg,))
        fz = pd.DataFrame({"ep": 1/lg.per.where(lg.per>0), "bp": 1/lg.pbr.where(lg.pbr>0), "rim": lg.rim_spread, "dv": lg.div_yield})
        rk = fz.groupby(lg.run_id).rank(pct=True); lg["s"] = rk.mean(axis=1, skipna=True).where(rk.notna().sum(axis=1) >= 2)
        lg["ticker"] = lg.ticker.astype(str).str.zfill(6); scores[name] = lg.loc[lg.s.notna(), ["run_id","ticker","s"]]; continue
    scores[name] = pd.read_sql(f"SELECT run_id, ticker, {col} AS s FROM {tbl} WHERE model_id=? AND run_id>=?", hc, params=(mid, reg))
px = pd.read_sql("SELECT ticker,date,change_pct FROM daily_ohlcv WHERE date>='20260601'", oc)
dts = sorted(px.date.unique()); R = px.pivot_table(index="date", columns="ticker", values="change_pct", aggfunc="last").reindex(dts)
def series(df, start, end, lag, fill):
    out = []
    for t in [d for d in dts if start <= d <= end]:
        i = dts.index(t)
        if i + lag >= len(dts): continue
        day = dts[i + lag]; sub = df[df.run_id == t]
        sel = [c for c in sub.nlargest(bcs.TOPN, "s").ticker if c in R.columns] if len(sub) else None
        out.append((day, np.nan if sel is None else float(R.loc[day, sel].astype(float).mean(skipna=True))))
    s = pd.Series(dict(out)).sort_index()
    return s.ffill(limit=2).fillna(0) if fill == "ffill" else s.fillna(0)
def cum(s): return round(float((1 + s).cumprod().iloc[-1] - 1) * 100, 1)
end = dts[-1]
print(f"{'model':6} | {'창':10} | 현행(lag1,ffill) | 올바른 지연(lag2,ffill) | 지연+결측0(lag2) | 차이(현행−올바른)")
for label, models, start in bcs.PANELS:
    for m in models:
        if bcs.MODELS and dict((n, r) for n, _, _, _, r in bcs.MODELS)[m] > start: continue
        a = cum(series(scores[m], start, end, 1, "ffill")); b = cum(series(scores[m], start, end, 2, "ffill")); c = cum(series(scores[m], start, end, 2, "zero"))
        print(f"{m:6} | {start}~ | {a:+7.1f}% | {b:+7.1f}% | {c:+7.1f}% | {a-b:+6.1f}%p")
print("\n최근 20거래일(trailing r20) — 현행 vs 올바른 지연")
for name, tbl, col, mid, reg in bcs.MODELS:
    s1 = series(scores[name], reg, end, 1, "ffill"); s2 = series(scores[name], reg, end, 2, "ffill")
    if len(s2) < 21: continue
    print(f"  {name:6} r20 현행 {cum(s1.iloc[-20:]):+5.1f}% → 올바른 {cum(s2.iloc[-20:]):+5.1f}%   등록후 누적 {cum(s1):+6.1f}% → {cum(s2):+6.1f}%")
