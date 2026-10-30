"""Independent, offline fresh/stale oversold study; no repository code imports.

Run: python -X utf8 -B research/handoff/code_20261031_fresh_oversold_blind.py
Checks only: append --self-check
Reads only the specified 10-year SQLite DB; writes only the paired REPLY file.
Never reads the comparison paper, IDEA_MAP, worklogs, or operating databases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

DB = Path(r"C:\Users\SAMSUNG\Documents\GitHub\dh-q7m3k-data\ohlcv_10y.db")
REPORT = Path(__file__).with_name("REPLY_20261031_fresh_oversold_blind.md")
EXCLUDE = re.compile(r"금융|은행|증권|보험|캐피탈|카드|손해보험|생명|화재|저축|여신|신탁|리츠|REIT|부동산투자|스팩|SPAC", re.I)
VARIANTS = ("기본", "최근5일 fresh", "5일 stale만", "10일 stale", "깊이 맞춤", "상폐 −90%")
PARTS = ("전체", "A", "B·C", "D", "~2020", "2021~")
FIELDS = ("ret", "loss", "q10", "depth", "vol", "liq")


def guard_time():
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    minute = now.hour * 60 + now.minute
    if now.weekday() < 5 and 1210 <= minute < 1350:
        raise RuntimeError("Weekday 20:10–22:30 KST: no file/DB access")
    return now.isoformat(timespec="seconds")


def classify(eligible, oversold, t):
    n = oversold.shape[1]
    empty = np.zeros(n, dtype=bool)
    if t < 5:
        return empty, empty, empty, empty, empty
    current = oversold[t]
    fresh = current & eligible[t - 5] & ~oversold[t - 5]
    stale = current & oversold[t - 5]
    strict = current & eligible[t - 5:t].all(axis=0) & ~oversold[t - 5:t].any(axis=0)
    ten = stale & oversold[t - 10] if t >= 10 else empty.copy()
    five = stale & eligible[t - 10] & ~oversold[t - 10] if t >= 10 else empty.copy()
    assert not np.any(fresh & stale)
    assert np.all(~strict | fresh)
    assert not np.any(five & ten)
    return fresh, stale, strict, five, ten


def exit_returns(close, t, delist_index, final_close):
    entry, end = t + 1, t + 41
    price = close[end].copy()
    dead = (delist_index > entry) & (delist_index <= end)
    price[dead] = final_close[dead]
    good = np.isfinite(price) & (price > 0) & (close[entry] > 0)
    result = np.full(close.shape[1], np.nan)
    np.divide(price, close[entry], out=result, where=good)
    result = (result - 1) * 100
    downside = result.copy()
    downside[dead & good] = -90.0
    return result, downside, dead


def weighted_quantile(x, w, q):
    order = np.argsort(x, kind="stable")
    x, w = x[order], w[order]
    positions = np.cumsum(w) - 0.5 * w
    target = positions[0] + q * (positions[-1] - positions[0])
    return float(np.interp(target, positions, x))


def stats_for(mask, weights, returns, depth, vol, liq):
    ix = np.flatnonzero(mask & np.isfinite(returns) & (weights > 0))
    if not len(ix):
        return None
    w, r = weights[ix], returns[ix]
    out = {"n": len(ix), "weight": float(w.sum())}
    for key, a in (("ret", returns), ("loss", (returns <= -20).astype(float) * 100),
                   ("depth", depth), ("vol", vol), ("liq", liq)):
        good = np.isfinite(a[ix])
        out[key] = float(np.average(a[ix][good], weights=w[good])) if good.any() else np.nan
    out["q10"] = weighted_quantile(r, w, 0.1)
    out["n_vol"] = int(np.isfinite(vol[ix]).sum())
    return out


def depth_weights(fresh, stale, current, depth, returns):
    wf, ws = np.zeros(len(depth)), np.zeros(len(depth))
    cuts = np.unique(np.quantile(depth[current], np.linspace(0, 1, 11)))
    bins = np.searchsorted(cuts[1:-1], depth, side="right")
    for b in np.unique(bins[current]):
        f = fresh & (bins == b) & np.isfinite(returns)
        s = stale & (bins == b) & np.isfinite(returns)
        nf, ns = int(f.sum()), int(s.sum())
        if nf and ns:
            common = min(nf, ns)
            wf[f], ws[s] = common / nf, common / ns
    return wf, ws


def paired_record(fresh, stale, wf, ws, ret, depth, vol, liq):
    f = stats_for(fresh, wf, ret, depth, vol, liq)
    s = stats_for(stale, ws, ret, depth, vol, liq)
    if f is None or s is None:
        return None
    rec = {"nf": f["n"], "ns": s["n"], "wf": f["weight"], "ws": s["weight"],
           "nf_vol": f["n_vol"], "ns_vol": s["n_vol"]}
    for key in FIELDS:
        rec["f_" + key], rec["s_" + key] = f[key], s[key]
        rec["d_" + key] = f[key] - s[key]
    return rec


def bootstrap(df, event=False):
    columns = [c for c in df.columns if c.startswith(("f_", "s_", "d_", "policy_"))]
    if df.empty:
        return {}
    labels = df["date"] if event else df["date"].str[:6]
    values = df[columns].astype(float)
    sums = values.groupby(labels).sum().to_numpy()
    counts = values.notna().astype(float).groupby(labels).sum().to_numpy()
    blocks = len(sums)
    reps, seed = (4000, 20261030) if event else (2000, 7)
    rng = np.random.default_rng(seed)
    sampled = rng.integers(0, blocks, size=(reps, blocks))
    mult = np.zeros((reps, blocks), dtype=float)
    np.add.at(mult, (np.arange(reps)[:, None], sampled), 1)
    numerator, denominator = mult @ sums, mult @ counts
    draw = np.full_like(numerator, np.nan)
    np.divide(numerator, denominator, out=draw, where=denominator > 0)
    avg = values.mean()
    out = {}
    for j, col in enumerate(columns):
        good = np.isfinite(draw[:, j])
        lo, hi = np.quantile(draw[good, j], [0.025, 0.975]) if good.any() else (np.nan, np.nan)
        out[col] = (float(avg[col]), float(lo), float(hi))
    out["blocks"] = blocks
    return out


def fmt(value):
    if isinstance(value, tuple):
        return f"{value[0]:+.2f} [{value[1]:+.2f}, {value[2]:+.2f}]"
    return f"{value:.2f}"


def subset(df, part):
    if part in ("A", "B·C", "D"):
        return df.loc[df.cell == part]
    if part == "~2020":
        return df.loc[df.date < "20210101"]
    if part == "2021~":
        return df.loc[df.date >= "20210101"]
    return df


def self_check():
    elig = np.ones((16, 5), dtype=bool)
    os = np.zeros_like(elig)
    os[15] = True
    os[10, [1, 2, 3]] = True
    os[5, 2] = True
    os[13, 4] = True
    elig[10, 3] = False
    os[10, 3] = False
    f, s, strict, five, ten = classify(elig, os, 15)
    assert f.tolist() == [True, False, False, False, True]
    assert s.tolist() == [False, True, True, False, False]
    assert strict.tolist() == [True, False, False, False, False]
    assert five.tolist() == [False, True, False, False, False]
    assert ten.tolist() == [False, False, True, False, False]
    c = np.full((45, 3), 100.0)
    c[41] = [120, np.nan, np.nan]
    r, r90, dead = exit_returns(c, 0, np.array([999, 20, 999]), np.array([100, 20, 100]))
    np.testing.assert_allclose(r[:2], [20, -80])
    assert np.isnan(r[2]) and r90[1] == -90 and dead.tolist() == [False, True, False]
    x, y = np.array([10., 30.]), np.array([-10., 0., 10.])
    np.testing.assert_allclose(x.mean() - np.r_[x, y].mean(), (x.mean() - y.mean()) * 3 / 5)
    np.testing.assert_allclose(weighted_quantile(np.arange(20.), np.ones(20), .1), np.quantile(np.arange(20.), .1))
    depth = np.arange(20.)
    wf, ws = depth_weights(np.arange(20) % 2 == 0, np.arange(20) % 2 == 1,
                           np.ones(20, bool), depth, depth)
    assert wf.sum() == ws.sum() == 10
    constant = pd.DataFrame({"date": ["20200101", "20200102", "20200203"], "d_ret": [3., 3., 3.]})
    assert bootstrap(constant)["d_ret"] == (3., 3., 3.)
    print("SELF_CHECK_OK: membership/history, delisting/missing exit, policy identity, weighted depth, block bootstrap", flush=True)


def load_data():
    stamp = DB.stat()
    with sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True) as con:
        con.execute("PRAGMA query_only=ON")
        assert con.execute("PRAGMA query_only").fetchone()[0] == 1
        meta = pd.read_sql_query("SELECT ticker,name,market,listed,delisted,status FROM meta", con)
        ix = pd.read_sql_query("SELECT series,date,close FROM index_daily", con)
        index = ix.pivot(index="date", columns="series", values="close")[["KOSPI", "KOSDAQ"]].dropna().sort_index()
        index = index.loc[(index > 0).all(axis=1)]
        dates = index.index.to_numpy(dtype=str)
        selected = meta.market.isin(["KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"])
        selected &= meta.ticker.str.endswith("0")
        selected &= ~meta.name.fillna("").str.contains(EXCLUDE)
        selected &= ~meta.ticker.isin(["055550", "001450"])
        universe = meta.loc[selected].sort_values("ticker").reset_index(drop=True)
        tickers = universe.ticker.tolist()
        rowmap, colmap = {d: i for i, d in enumerate(dates)}, {k: i for i, k in enumerate(tickers)}
        close = np.full((len(dates), len(tickers)), np.nan)
        volume = np.full_like(close, np.nan)
        loaded, skipped_date, source_counts = 0, 0, {}
        query = """SELECT p.ticker,p.date,p.close,p.volume,p.source FROM prices p JOIN meta m ON p.ticker=m.ticker
                   WHERE m.market IN ('KOSPI','KOSDAQ','KOSDAQ GLOBAL') AND substr(p.ticker,-1)='0'"""
        cur = con.execute(query)
        while True:
            chunk = cur.fetchmany(50000)
            if not chunk:
                break
            for ticker, date, price, vol, source in chunk:
                j = colmap.get(ticker)
                if j is None:
                    continue
                i = rowmap.get(date)
                if i is None:
                    skipped_date += 1
                    continue
                close[i, j] = float(price) if price is not None else np.nan
                volume[i, j] = float(vol) if vol is not None else np.nan
                source_counts[source] = source_counts.get(source, 0) + 1
                loaded += 1
    delist_index = np.full(len(tickers), float(len(dates) + 100))
    final_close = np.full(len(tickers), np.nan)
    for j, raw in enumerate(universe.delisted.fillna("")):
        d = str(raw).replace("-", "")
        if not re.fullmatch(r"\d{8}", d):
            continue
        # Non-trading-day delistings lie strictly between neighboring sessions.
        k = int(np.searchsorted(dates, d, side="left"))
        if k == len(dates) or dates[k] != d:
            k -= 0.5
        delist_index[j] = k
        valid = np.flatnonzero(np.isfinite(close[:, j]) & (close[:, j] > 0) & (dates <= d))
        if len(valid):
            final_close[j] = close[valid[-1], j]
    info = {"calendar_n": len(dates), "calendar_start": dates[0], "calendar_end": dates[-1],
            "universe_n": len(tickers), "loaded_price_rows": loaded, "off_calendar_rows": skipped_date,
            "source_rows": source_counts, "db_size": stamp.st_size, "db_mtime_ns": stamp.st_mtime_ns,
            "meta_empty_names": int(universe.name.fillna("").eq("").sum()),
            "no_price_tickers": int((~np.isfinite(close).any(axis=0)).sum())}
    price_days = np.isfinite(close).any(axis=1)
    info["price_first_date"] = dates[price_days][0]
    info["price_last_date"] = dates[price_days][-1]
    info["tail_positive_close_counts"] = {dates[k]: int((close[k] > 0).sum()) for k in range(len(dates)-3, len(dates))}
    return dates, index, close, volume, delist_index, final_close, info


def main():
    started = time.perf_counter()
    run_at = guard_time()
    self_check()
    dates, index, close, volume, delist_idx, final_close, info = load_data()
    print("READ_ONLY_LOAD", json.dumps(info, ensure_ascii=False), flush=True)
    nday, nstock = close.shape
    r20 = np.full_like(close, np.nan)
    np.divide(close[20:], close[:-20], out=r20[20:], where=close[:-20] > 0)
    r20 = (r20 - 1) * 100
    eligible = np.isfinite(r20) & (close >= 1000) & (volume > 0)
    eligible[:-1] &= (close[1:] > 0) & (volume[1:] > 0)
    eligible[-1] = False
    oversold = np.zeros_like(eligible)
    ties_extra = 0
    for t in range(20, nday - 1):
        vals = r20[t, eligible[t]]
        if len(vals):
            cutoff = np.quantile(vals, 0.2)
            oversold[t] = eligible[t] & (r20[t] <= cutoff)
            ties_extra += max(0, int(oversold[t].sum()) - int(np.ceil(len(vals) * .2)))
    one_ret = np.full_like(close, np.nan)
    np.divide(close[1:], close[:-1], out=one_ret[1:], where=close[:-1] > 0)
    one_ret = (one_ret - 1) * 100
    one_ret[close <= 0] = np.nan
    volatility = pd.DataFrame(one_ret).rolling(20, min_periods=20).std(ddof=1).to_numpy()
    del one_ret
    liq = pd.DataFrame(np.where(eligible, close * volume, np.nan)).rank(axis=1, pct=True).to_numpy() * 100
    kr20 = (index.KOSPI / index.KOSPI.shift(20) - 1).to_numpy() * 100
    grid = np.arange(20, nday - 41, 5)
    grid_events, previous = [], -10**9
    for t in grid:
        if kr20[t] <= -5 and t - previous >= 40:
            grid_events.append(t)
            previous = t
    events, previous = [], -10**9
    for t in range(20, nday - 41):
        if kr20[t] <= -5 and t - previous >= 40:
            events.append(t)
            previous = t
    event_set = set(events)
    grid_set, grid_event_set = set(grid), set(grid_events)
    rows = []
    attempts = []
    audit = {"missing_exit_stock_dates": 0, "delisted_stock_dates": 0, "unknown_prior_stock_dates": 0,
             "oversold_stock_dates": 0, "min_ret": np.inf, "max_ret": -np.inf,
             "abs_return_over_200_stock_dates": 0, "ties_extra_all_daily": ties_extra}
    ones = np.ones(nstock)
    for t in sorted(grid_set | event_set):
        current = oversold[t]
        ret, ret90, dead = exit_returns(close, t, delist_idx, final_close)
        f, s, strict, five, ten = classify(eligible, oversold, t)
        wf, ws = depth_weights(f, s, current, r20[t], ret) if current.any() else (np.zeros(nstock), np.zeros(nstock))
        valid_current = current & np.isfinite(ret)
        unknown = current & ~eligible[t - 5] if t >= 5 else current
        if t in grid_set:
            audit["missing_exit_stock_dates"] += int((current & ~np.isfinite(ret)).sum())
            audit["delisted_stock_dates"] += int((valid_current & dead).sum())
            audit["unknown_prior_stock_dates"] += int((unknown & valid_current).sum())
            audit["oversold_stock_dates"] += int(valid_current.sum())
        if t in grid_set and valid_current.any():
            audit["min_ret"] = min(audit["min_ret"], float(ret[valid_current].min()))
            audit["max_ret"] = max(audit["max_ret"], float(ret[valid_current].max()))
            audit["abs_return_over_200_stock_dates"] += int((np.abs(ret[valid_current]) > 200).sum())
        variants = ((f, s, ones, ones, ret), (strict, s, ones, ones, ret),
                    (f, five, ones, ones, ret), (f, ten, ones, ones, ret),
                    (f, s, wf, ws, ret), (f, s, ones, ones, ret90))
        cell = "A" if kr20[t] <= -5 else "D" if kr20[t] > 5 else "B·C"
        for name, (fm, sm, fw, sw, rr) in zip(VARIANTS, variants):
            nf = int((fm & np.isfinite(rr) & (fw > 0)).sum())
            ns = int((sm & np.isfinite(rr) & (sw > 0)).sum())
            attempts.append({"date": dates[t], "cell": cell, "variant": name, "event": t in event_set, "is_grid": t in grid_set,
                             "nf": nf, "ns": ns, "eligible_n": int(eligible[t].sum()),
                             "prior_eligible_n": int(eligible[t - 5].sum()), "oversold_n": int(current.sum()),
                             "selected_f": int(fm.sum()), "selected_s": int(sm.sum())})
            record = paired_record(fm, sm, fw, sw, rr, r20[t], volatility[t], liq[t])
            if record is None:
                continue
            record.update(date=dates[t], cell=cell, variant=name, event=t in event_set,
                          grid_event=t in grid_event_set, is_grid=t in grid_set,
                          n_current=int(valid_current.sum()), n_unknown=int((unknown & valid_current).sum()))
            if name == "기본":
                all_classified = (record["f_ret"] * record["nf"] + record["s_ret"] * record["ns"]) / (record["nf"] + record["ns"])
                record["policy_class"] = record["f_ret"] - all_classified
                record["policy_literal"] = record["f_ret"] - float(rr[valid_current].mean())
                record["stale_share"] = record["ns"] / (record["nf"] + record["ns"])
                np.testing.assert_allclose(record["policy_class"], record["d_ret"] * record["stale_share"], atol=1e-10)
            rows.append(record)
    all_data = pd.DataFrame(rows)
    event_data = all_data.loc[all_data.event]
    data = all_data.loc[all_data.is_grid]
    all_attempted = pd.DataFrame(attempts)
    attempted = all_attempted.loc[all_attempted.is_grid]
    assert (np.diff(events) >= 40).all()
    assert data[["f_ret", "s_ret", "d_ret", "f_loss", "s_loss", "f_q10", "s_q10"]].notna().all().all()
    after = DB.stat()
    assert (after.st_size, after.st_mtime_ns) == (info["db_size"], info["db_mtime_ns"]), "DB changed during study"
    daily = {}
    event_stats = {}
    grid_event_stats = {}
    for variant in VARIANTS:
        v = data.loc[data.variant == variant]
        for part in PARTS:
            daily[(variant, part)] = bootstrap(subset(v, part))
        event_stats[variant] = bootstrap(event_data.loc[event_data.variant == variant], event=True)
        grid_event_stats[variant] = bootstrap(v.loc[v.grid_event], event=True)
    info.update(grid_n=len(grid), first_signal=dates[grid[0]], last_signal=dates[grid[-1]],
                candidate_events=len(events), grid_candidate_events=len(grid_events), run_at=run_at, numpy=np.__version__, pandas=pd.__version__)
    info["code_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    lines = ["## 1. 데이터·실행 확인(실측)", "", "```json", json.dumps(info, ensure_ascii=False, indent=2), "```", "",
             "- 데이터 가격 행은 한 번 순회하여 메모리에 적재했다. DB 연결은 읽기 전용·query_only이고 실행 전후 DB 크기·수정 시각이 같았다.",
             "- 조건 미달·상폐·청산 누락 집계는 종목×격자일 수이며 독립 종목 수가 아니다.", "", "```json", json.dumps(audit, ensure_ascii=False, indent=2), "```", "",
             "- 셀프 체크: 과거 조건 미달 제외, 5일 연속 비과매도, stale 분할, 상폐 마지막 가격/−90%, 일반 청산 누락, 운용 번역 항등식, 깊이 가중, 월 블록 상수 보존 통과.",
             "- 원가격과 meta를 그대로 사용했다. 분할·병합·배당의 시점별 조정 여부와 과거 시장/이름 변경은 별도 검증하지 못했다. 큰 수익률을 임의로 자르지 않았다.", "",
             "## 2. 날 단위 평균 수익과 표본 수(실측)", "",
             "수익은 %, 차이는 %p. 대괄호는 월 블록 95% CI. n은 포함 날짜/월 수. 종목 수는 포함 날짜의 중앙값(최소). 제외는 양쪽 중 하나라도 수익이 없는 날짜 수다.", "",
             "| 비교 | 구간 | n일/월 | 제외일 | fresh 수 | stale 수 | fresh 수익 [CI] | stale 수익 [CI] | 차이 [CI] |",
             "|---|---|---:|---:|---:|---:|---|---|---|"]
    for variant in VARIANTS:
        for part in PARTS:
            d = subset(data.loc[data.variant == variant], part)
            a = subset(attempted.loc[attempted.variant == variant], part)
            b = daily[(variant, part)]
            if d.empty:
                lines.append(f"| {variant} | {part} | 0/0 | {len(a)} | — | — | — | — | — |")
                continue
            lines.append(f"| {variant} | {part} | {len(d)}/{b['blocks']} | {len(a)-len(d)} | {d.nf.median():.0f}({d.nf.min()}) | {d.ns.median():.0f}({d.ns.min()}) | {fmt(b['f_ret'])} | {fmt(b['s_ret'])} | {fmt(b['d_ret'])} |")
    omitted = attempted.loc[(attempted.variant == "기본") & ((attempted.nf == 0) | (attempted.ns == 0))]
    lines += ["", "기본 비교 제외 날짜 진단(표본 수 자체의 실측):", "",
              "| 날짜 | t 조건 통과 | t−5 조건 통과 | t 과매도 | fresh 선정/수익 유효 | stale 선정/수익 유효 |",
              "|---|---:|---:|---:|---:|---:|"]
    for r in omitted.itertuples():
        lines.append(f"| {r.date} | {r.eligible_n} | {r.prior_eligible_n} | {r.oversold_n} | {r.selected_f}/{r.nf} | {r.selected_s}/{r.ns} |")
    lines += ["", "### 2-1. 손실 집중", "", "같은 날짜 표본과 부트스트랩을 사용한다. −20% 이하 비율은 %이고 차이는 %p. Q10은 **날별 하위 10% 분위의 평균**(%)이다. 깊이 맞춤은 해당 공통 가중치를 사용하는 분위다.", "",
              "| 비교 | 구간 | n일 | fresh 손실비율 [CI] | stale 손실비율 [CI] | 비율 차이 [CI] | fresh Q10 [CI] | stale Q10 [CI] | Q10 차이 [CI] |",
              "|---|---|---:|---|---|---|---|---|---|"]
    for variant in VARIANTS:
        for part in PARTS:
            d = subset(data.loc[data.variant == variant], part)
            b = daily[(variant, part)]
            if len(d):
                cells = " | ".join(fmt(b[k]) for k in ("f_loss", "s_loss", "d_loss", "f_q10", "s_q10", "d_q10"))
                lines.append(f"| {variant} | {part} | {len(d)} | {cells} |")
    lines += ["", "## 3. A 사건 단위(실측)", "", "요청서의 예상 사건 수와 초회 격자 사건 수가 달라 정의를 대조했다. 먼저 **모든 A 거래일**에서 40거래일 이상 띄운 첫 날 결과를 제시하고, 초회 **격자 A일** 결과도 아래에 보존한다. n은 실제 비교 가능한 사건 수. CI는 사건 쌍 4,000회 재추출이다.", "",
              "| 비교 | 사건 n/후보 | fresh 수익 [CI] | stale 수익 [CI] | 차이 [CI] | 손실비율 차이 [CI] | Q10 차이 [CI] |",
              "|---|---:|---|---|---|---|---|"]
    for variant in VARIANTS:
        d = event_data.loc[event_data.variant == variant]
        b = event_stats[variant]
        if len(d):
            cells = " | ".join(fmt(b[k]) for k in ("f_ret", "s_ret", "d_ret", "d_loss", "d_q10"))
            lines.append(f"| {variant} | {len(d)}/{len(events)} | {cells} |")
    lines += ["", "사건별 기본 비교의 날짜·종목 수·점추정은 아래와 같다. 개별 사건 하나에는 사건 재추출 CI를 정의할 수 없으므로 집합의 CI는 위 표에만 제시한다. 제외 사건을 다른 날짜로 교체하지 않았다.", "",
              "| 사건일 | fresh n | stale n | fresh 수익 % | stale 수익 % | 차이 %p |",
              "|---|---:|---:|---:|---:|---:|"]
    eb = event_data.loc[event_data.variant == "기본"].set_index("date")
    excluded_event_notes = []
    for t in events:
        day = dates[t]
        if day in eb.index:
            r = eb.loc[day]
            lines.append(f"| {day} | {int(r.nf)} | {int(r.ns)} | {r.f_ret:+.3f} | {r.s_ret:+.3f} | {r.d_ret:+.3f} |")
        else:
            lines.append(f"| {day} | — | — | 제외 | 제외 | 제외 |")
            a = all_attempted.loc[(all_attempted.date == day) & (all_attempted.variant == "기본")].iloc[0]
            excluded_event_notes.append(f"제외 사건 {day}: t 조건 통과 {a.eligible_n}, t−5 조건 통과 {a.prior_eligible_n}, t 과매도 {a.oversold_n}, fresh 선정/수익 유효 {a.selected_f}/{a.nf}, stale {a.selected_s}/{a.ns}.")
    lines += [""] + excluded_event_notes
    lines += ["", "### 3-1. 초회 격자 A 사건 결과 보존", "", "이 표는 모든 A 거래일 해석을 추가하기 전에 얻은 정의를 유지한다.", "",
              "| 비교 | 사건 n/후보 | fresh 수익 [CI] | stale 수익 [CI] | 차이 [CI] | 손실비율 차이 [CI] | Q10 차이 [CI] |",
              "|---|---:|---|---|---|---|---|"]
    for variant in VARIANTS:
        b = grid_event_stats[variant]
        cells = " | ".join(fmt(b[k]) for k in ("f_ret", "s_ret", "d_ret", "d_loss", "d_q10"))
        n = int(((data.variant == variant) & data.grid_event).sum())
        lines.append(f"| {variant} | {n}/{len(grid_events)} | {cells} |")
    lines += ["", "격자 사건 날짜: " + ", ".join(dates[t] for t in grid_events) + ".", "",
              "## 4. t 시점 특성과 깊이 맞춤(실측)", "", "날별 그룹 평균을 날짜 동일가중으로 요약하며 CI는 월 블록이다. R20과 변동성은 %, 거래대금 순위는 0~100 백분위다. 변동성은 20개 수익률이 있는 종목만 사용한다.", "",
              "| 비교 | 구간 | n일 | fresh R20 [CI] | stale R20 [CI] | R20 차이 [CI] | fresh 변동성 [CI] | stale 변동성 [CI] | fresh 거래대금 순위 [CI] | stale 거래대금 순위 [CI] |",
              "|---|---|---:|---|---|---|---|---|---|---|"]
    for variant in ("기본", "깊이 맞춤"):
        for part in ("전체", "A", "~2020", "2021~"):
            d = subset(data.loc[data.variant == variant], part)
            b = daily[(variant, part)]
            cells = " | ".join(fmt(b[k]) for k in ("f_depth", "s_depth", "d_depth", "f_vol", "s_vol", "f_liq", "s_liq"))
            lines.append(f"| {variant} | {part} | {len(d)} | {cells} |")
    base = data.loc[data.variant == "기본"]
    matched = data.loc[data.variant == "깊이 맞춤"]
    lines += ["", f"- 기본 비교의 변동성 유효 종목×날 수: fresh {int(base.nf_vol.sum()):,}/{int(base.nf.sum()):,}, stale {int(base.ns_vol.sum()):,}/{int(base.ns.sum()):,}.",
              f"- 깊이 맞춤 공통 가중치 합의 날별 중앙값/최소: {matched.wf.median():.1f}/{matched.wf.min():.1f}. 같은 분위 안에도 남는 R20 차이가 있으므로 인과효과로 해석하지 않는다.", "",
              "## 5. 운용 규칙으로 번역(실측 범위)", "", "처음만 매수한 평균과 비교 평균의 차이(%p). 같은 날별 차이를 월 블록으로 추출했다. 아래 n은 기본 비교의 날짜 수다.", "",
              "| 구간 | n일 | stale 비중 평균 % | 직전 조건 미달 종목×날 수 | fresh−분류 가능한 전체 [CI] | fresh−문자 그대로 전체 과매도 [CI] |",
              "|---|---:|---:|---:|---|---|"]
    for part in PARTS:
        d = subset(base, part)
        b = daily[("기본", part)]
        lines.append(f"| {part} | {len(d)} | {d.stale_share.mean()*100:.2f} | {int(d.n_unknown.sum()):,} | {fmt(b['policy_class'])} | {fmt(b['policy_literal'])} |")
    lines += ["", "- `차이×stale 비중`은 **날마다 곱한 뒤 평균**이다. 평균 차이×평균 비중으로 대체하지 않았다. 모든 기본 날짜에서 해당 항등식을 검증했다.",
              "- 두 그룹은 보유기간이 같아 비용을 0으로 두었다. 실제 재매수·현금 대기·체결·회전 수는 운용 방식에 따라 달라져 이 차이를 순비용 후 계좌 성과로 간주할 수 없다.",
              "- 정리 바구니는 실제 점수 상위 10 목록이 아니다. 종목 수 감소, 자금 재배분, 이미 보유한 종목 건너뛰기의 효과는 이 계산으로 알 수 없다.", "",
              "## 6. 독립 계산 해석·한계", "",
              "(결과 확인 후, 금지 문서 열기 전에 아래 독립 해석을 작성한다.)", "",
              "- 이 연구는 과매도 목록 잔류 상태를 비교한다. 실제 보유 중복 여부를 관측하지 않았다. 20일 창에서 반등하지 않은 상태를 다시 표현한 것일 수 있다.",
              "- §11은 40거래일 OOS 관측 및 h=20d IC 등을 사용하는 모델 판정이다. 이 연구의 h=40d 대리 바구니 평균차는 그 판정을 대체하지 않는다. 현재 점수의 과매도/반전 성분과 개념적으로 겹칠 수 있으나 실제 조건부 IC 중복은 측정하지 않았다.",
              "- 현재 meta 필터, t+1 체결 가능 조건, 상폐 마지막 저장 가격, 40일 겹침, 월 블록 길이, 깊이 분위 안 잔여 차이, 사후 가설이라는 한계를 유지한다. 표본 종목×날 수를 독립 표본 수로 쓰지 않는다.",
              "- 명목 95% CI이며 사건 정의 대조까지 총 156개 성과 대비를 살폈다. 다중비교 보정 또는 새 창 검증 없이 운영 채택·새 모델 판정을 하지 않는다.", "",
              "### 재현", "", "```powershell", "python -X utf8 -B research/handoff/code_20261031_fresh_oversold_blind.py --self-check",
              "python -X utf8 -B research/handoff/code_20261031_fresh_oversold_blind.py", "```", "",
              "이 명령은 독립 결과 구간을 다시 계산해 답 파일에 반영한다. §7 문서는 코드에서 열지 않는다. 자료가 바뀐 재실행 후에는 수동 해석과 §7 대조를 다시 검토해야 한다. 큰 중간 파일 없음.", "",
              f"실행 경과: {time.perf_counter()-started:.1f}초. 독립 결과 저장 시각: {guard_time()}."]
    content = REPORT.read_text(encoding="utf-8")
    begin, end = "<!-- GENERATED_RESULTS_START -->", "<!-- GENERATED_RESULTS_END -->"
    left, remainder = content.split(begin, 1)
    _, right = remainder.split(end, 1)
    REPORT.write_text(left + begin + "\n" + "\n".join(lines) + "\n" + end + right, encoding="utf-8")
    print("BLIND_RESULTS_WRITTEN", str(REPORT), flush=True)
    for variant in VARIANTS:
        print(variant, "ALL", daily[(variant, "전체")].get("d_ret"), "A_EVENTS", event_stats[variant].get("d_ret"), flush=True)
    print("EVENT_DATES", ",".join(dates[t] for t in events), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    options = parser.parse_args()
    guard_time()
    if options.self_check:
        self_check()
    else:
        main()
