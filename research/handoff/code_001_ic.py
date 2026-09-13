"""REQUEST 001 independent h20 replication; stdout only, SQLite read-only.

Run from any directory: python -B research/handoff/code_001_ic.py
No project module imports. Missing interior prices are not filled; the jump
maximum uses observed adjacent pairs. --strict-path requires all 21 prices.
"""
import argparse
import bisect
import hashlib
import json
import platform
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[2]
MODELS = {
    "lv_b": ("lowvol_scores", "lowvol_score", "20260625"),
    "v30": ("v3_scores", "final_score_v3", "20260606"),
    "sv_a": ("wu_scores", "wu_score", "20260715"),
}
EXCLUDE = {"20260608", "20260703"}


def read_only(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def bootstrap(values):
    # Descriptive iid anchor CI, not a new model verdict.
    rng = np.random.default_rng(7)
    a = np.asarray(values)
    samples = rng.choice(a, size=(20000, len(a))).mean(axis=1)
    return np.quantile(samples, [0.025, 0.975]).tolist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-path", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone(timedelta(hours=9)))
    if now.weekday() < 5 and "20:10" <= now.strftime("%H:%M") < "22:30":
        raise SystemExit("Weekday batch window: no file/DB access.")
    start = time.perf_counter()
    price_path = ROOT.parent / "dh-q7m3k-data" / "ohlcv.db"
    con = read_only(price_path)
    try:
        dates = [r[0] for r in con.execute(
            "SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
        # Global calendar is retained; only the necessary price window is read.
        floor = dates[max(0, bisect.bisect_right(dates, "20260606") - 1)]
        raw = pd.read_sql_query(
            "SELECT ticker,date,close FROM daily_ohlcv WHERE date>=? ORDER BY date,ticker",
            con, params=(floor,))
    finally:
        con.close()
    raw["ticker"] = raw["ticker"].astype(str).str.zfill(6)
    close = raw.pivot(index="date", columns="ticker", values="close").reindex(dates)
    prices = close.to_numpy(dtype=float)
    lookup = {ticker: i for i, ticker in enumerate(close.columns)}
    board_bytes = (ROOT / "docs" / "leaderboard.json").read_bytes()
    board = {m["model"]: m["h20"] for m in json.loads(board_bytes)["models"]}
    result = {"started_kst": now.isoformat(), "python": platform.python_version(),
              "platform": platform.platform(), "numpy": np.__version__,
              "pandas": pd.__version__, "scipy": scipy.__version__,
              "calendar": [dates[0], dates[-1], len(dates)],
              "strict_path": args.strict_path, "bootstrap": "iid 20000 seed=7 percentile 95%",
              "leaderboard_sha256": hashlib.sha256(board_bytes).hexdigest(), "models": {}}
    con = read_only(ROOT / "history.db")
    try:
        for model, (table, score, reg) in MODELS.items():
            data = pd.read_sql_query(
                f"SELECT run_id,market,ticker,{score} AS score FROM {table} WHERE model_id=?",
                con, params=(model,))
            ticker_text = data.ticker.astype(str)
            short_numeric = int((ticker_text.str.fullmatch(r"\d+") &
                                 (ticker_text.str.len() < 6)).sum())
            nonnumeric = sorted(ticker_text[~ticker_text.str.fullmatch(r"\d+")].unique())
            data["ticker"] = data.ticker.astype(str).str.zfill(6)
            data["market"] = data.market.str.lower()
            candidates = {}
            for run in sorted(data.run_id.unique()):
                if run < reg or run in EXCLUDE:
                    continue
                t = bisect.bisect_right(dates, run) - 1
                if t >= 0:
                    candidates.setdefault(t, []).append(run)
            chosen = {t: (dates[t] if dates[t] in runs else min(runs))
                      for t, runs in candidates.items()}
            anchors = []
            omitted = []
            for t, run in sorted(chosen.items()):
                if t + 21 >= len(dates):
                    omitted.append({"run": run, "reason": "immature"})
                    continue
                group = data[data.run_id == run]
                block = prices[t + 1:t + 22]
                with np.errstate(divide="ignore", invalid="ignore"):
                    forward = block[-1] / block[0] - 1
                    jumps = np.abs(block[1:] / block[:-1] - 1)
                # Ignore missing adjacent pairs, but exclude an entirely missing jump window.
                present = ~np.isnan(jumps)
                max_jump = np.where(present, jumps, -np.inf).max(axis=0)
                usable = (np.isfinite(forward) & (block[0] > 0) & (block[-1] > 0)
                          & present.any(axis=0) & (max_jump <= 0.32))
                complete = np.isfinite(block).all(axis=0) & (block > 0).all(axis=0)
                if args.strict_path:
                    usable &= complete
                markets = {}
                for market, rows in group.groupby("market"):
                    if market not in {"kospi", "kosdaq"}:
                        raise ValueError(f"Unexpected market: {market}")
                    if rows.ticker.duplicated().any():
                        raise ValueError("Duplicate normalized ticker within market/run")
                    pairs = []
                    incomplete_kept = unmatched = jump_cut = 0
                    for row in rows.itertuples(index=False):
                        col = lookup.get(row.ticker)
                        if col is None:
                            unmatched += 1
                            continue
                        if max_jump[col] > 0.32:
                            jump_cut += 1
                        if usable[col] and pd.notna(row.score) and np.isfinite(row.score):
                            pairs.append((row.score, forward[col]))
                            incomplete_kept += int(not complete[col])
                    ic = None
                    if len(pairs) >= 8:
                        x, y = np.asarray(pairs).T
                        if len(np.unique(x)) >= 3 and len(np.unique(y)) >= 3:
                            ic = float(np.corrcoef(rankdata(x, method="average"),
                                                  rankdata(y, method="average"))[0, 1])
                    markets[market] = {"ic": ic, "n_stocks": len(pairs),
                                       "unmatched": unmatched, "jump_cut": jump_cut,
                                       "incomplete_kept": incomplete_kept}
                ics = [m["ic"] for m in markets.values() if m["ic"] is not None]
                if ics:
                    anchors.append({"run": run, "anchor": dates[t],
                                    "entry": dates[t + 1], "exit": dates[t + 21],
                                    "ic": float(np.mean(ics)), "markets": markets})
                else:
                    omitted.append({"run": run, "reason": "no valid market", "markets": markets})
            vals = [a["ic"] for a in anchors]
            mean = float(np.mean(vals))
            result["models"][model] = {
                "ic": mean, "n": len(vals), "ci95": bootstrap(vals),
                "leaderboard": board[model], "diff": mean - board[model]["ic"],
                "short_numeric_score_rows": short_numeric,
                "nonnumeric_score_tickers": nonnumeric,
                "dedupe": [{"anchor": dates[t], "runs": runs, "kept": chosen[t]}
                           for t, runs in candidates.items() if len(runs) > 1],
                "anchors": anchors, "omitted": omitted}
    finally:
        con.close()
    result["elapsed_seconds"] = round(time.perf_counter() - start, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
