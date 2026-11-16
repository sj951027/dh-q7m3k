"""D44 independent reproduction, as of 20261116. Reads SQLite mode=ro, prints only.
Run: python -X utf8 -B research/handoff/code_20261116_d44_review.py
No imports of production calculation modules; no production entry points or writers.
"""
import datetime as dt
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ASOF, REG, BOOT = "20261116", "20260806", 2000


def ro(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def summarize(values):
    x = np.array(values, dtype=float)
    if len(x) == 0:
        return dict(ic=None, n=0, ci=[None, None], pos=None)
    rng = np.random.default_rng(7)
    boot = rng.choice(x, size=(BOOT, len(x))).mean(axis=1)
    return dict(ic=round(float(x.mean()), 4), n=len(x),
                ci=np.percentile(boot, [2.5, 97.5]).round(4).tolist(),
                pos=round(float((x > 0).mean()), 3))


with ro(ROOT / "history.db") as con:
    g = pd.read_sql_query("SELECT run_id,market,ticker,per,pbr,rim_spread,div_yield FROM large_final WHERE run_id<=?", con, params=[ASOF])
    counts = pd.read_sql_query("SELECT run_id,count(*) n FROM stage1_oversold WHERE run_id<=? GROUP BY run_id", con, params=[ASOF])
    partial = set(counts.loc[counts.n < counts.n.median() * .30, "run_id"].astype(str))
    double = set()
    for table in ("v3_scores", "lowvol_scores", "wu_scores"):
        rows = pd.read_sql_query("SELECT run_id,model_id,frozen_at FROM " + table + " WHERE run_id<=?", con, params=[ASOF])
        rows["ts"] = pd.to_datetime(rows.frozen_at, errors="coerce", utc=True)
        for (rid, model), z in rows.dropna(subset=["ts"]).groupby(["run_id", "model_id"]):
            if (z.ts.max() - z.ts.min()).total_seconds() >= 3600:
                double.add(str(rid))
with ro(ROOT.parent / "dh-q7m3k-data" / "ohlcv.db") as con:
    px = pd.read_sql_query("SELECT date,ticker,close FROM daily_ohlcv WHERE date<=?", con, params=[ASOF])
    ex = pd.read_sql_query("SELECT date,ticker,close FROM daily_ohlcv_extra WHERE date<=?", con, params=[ASOF])
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
ex = ex[~ex.ticker.isin(close.columns)]
extra = ex.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
close = close.join(extra.reindex(close.index))
dates = list(close.index)
didx = {d: i for i, d in enumerate(dates)}
changes = close.pct_change(fill_method=None).abs()


def anchor(rid):
    day = dt.datetime.strptime(str(rid), "%Y%m%d")
    return next((didx[d] for k in range(6) if (d := (day - dt.timedelta(days=k)).strftime("%Y%m%d")) in didx), None)


g["run_id"] = g.run_id.astype(str)
g["ticker"] = g.ticker.astype(str)
f = pd.DataFrame(dict(ep=1 / g.per.where(g.per > 0), bp=1 / g.pbr.where(g.pbr > 0), rim=g.rim_spread, dv=g.div_yield))
ranks = f.groupby(g.run_id).rank(pct=True)
g["score"] = ranks.mean(axis=1).where(ranks.notna().sum(axis=1) >= 2)
g = g.dropna(subset=["score"])
candidates = {}
for rid in sorted(g.run_id.unique()):
    t = anchor(rid)
    if rid >= REG and rid not in partial | double and t is not None:
        candidates.setdefault(t, []).append(rid)
keep = {min([r for r in runs if r in didx] or runs) for runs in candidates.values()}
weeks = {}
for rid in sorted(keep):
    wk = dt.datetime.strptime(dates[anchor(rid)], "%Y%m%d").isocalendar()[:2]
    weeks.setdefault(wk, rid)
weekly = set(weeks.values())


def calculate(h, selected):
    records = []
    for rid, sub in g[g.run_id.isin(selected)].groupby("run_id", sort=True):
        t = anchor(rid)
        if t + 1 + h >= len(dates):
            continue
        fwd = (close.iloc[t + 1 + h] / close.iloc[t + 1] - 1).where(changes.iloc[t + 2:t + 2 + h].max() <= .32)
        pieces, ics, market_counts = [], [], {}
        markets = list(sub.groupby("market"))
        for mk, sm in markets:
            z = sm[["score", "ticker"]].copy()
            z["ret"] = fwd.reindex(z.ticker).to_numpy()
            z = z.dropna(subset=["score", "ret"])
            market_counts[str(mk)] = len(z)
            if len(z) >= 8 and z.score.nunique() >= 3 and z.ret.nunique() >= 3:
                ics.append(float(np.corrcoef(z.score.rank(), z.ret.rank())[0, 1]))
                pieces.append(z)
        pooled = None
        if len(markets) >= 2 and len(pieces) == len(markets):
            all_values = pd.concat(pieces)
            pooled = float(np.corrcoef(all_values.score.rank(), all_values.ret.rank())[0, 1])
        records.append(dict(run=rid, end=dates[t + 1 + h], market_counts=market_counts,
                            pooled=pooled, market_mean=float(np.mean(ics)) if ics else None))
    return records


report = dict(asof=ASOF, price_columns=close.shape[1], daily=len(keep), weekly=len(weekly),
              excluded_partial=sorted(partial), excluded_double=sorted(double), reproduction={})
for name, h, selected in (("daily_h20", 20, keep), ("weekly_h60", 60, weekly)):
    rows = calculate(h, selected)
    report["reproduction"][name] = {definition: summarize([r[definition] for r in rows if r[definition] is not None])
                                     for definition in ("pooled", "market_mean")}
    report["reproduction"][name]["rows_with_missing_definition"] = [r for r in rows if r["pooled"] is None or r["market_mean"] is None]
    if h == 60:
        report["weekly_h60_rows"] = rows
for h in (60, 120):
    closed = []
    for rid in sorted(weekly):
        end = anchor(rid) + 1 + h
        if end < len(dates) and dates[end] <= ASOF:
            closed.append(dict(run=rid, end=dates[end]))
    report[f"excluded_at_decision_h{h}"] = closed
report["boundary_at_decision"] = {f"h{h}": [dict(run=r, weekly=r in weekly)
    for r in sorted(keep) if anchor(r) + 1 + h == didx[ASOF]] for h in (20, 60, 120)}
report["market_names_after_score"] = sorted(g[g.run_id.isin(keep)].market.dropna().unique().tolist())
report["weekly_market_counts"] = {rid: int(sub.market.nunique()) for rid, sub in g[g.run_id.isin(weekly)].groupby("run_id")}
print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
