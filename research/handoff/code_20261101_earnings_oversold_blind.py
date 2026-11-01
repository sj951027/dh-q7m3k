"""Independent earnings/oversold study. No repository imports, network, or DB writes.

Default: print report to stdout. --write-report: update only the designated reply
before its section 7 has been written. Python -B avoids bytecode files.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import sqlite3
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / "dh-q7m3k-data"
DBS = {"prices": DATA / "ohlcv.db", "earnings": DATA / "earnings.db",
       "history": ROOT / "history.db"}
REPLY = Path(__file__).with_name("REPLY_20261101_earnings_oversold_blind.md")
MARKER = "## 1. 계산 기록"
EVENTS = ("paid_in", "reduction", "cb", "bw", "eb")
ORIGINAL_TITLES = {
    "paid_in": {"주요사항보고서(유상증자결정)", "유상증자결정"},
    "reduction": {"주요사항보고서(감자결정)"},
    "cb": {"주요사항보고서(전환사채권발행결정)"},
    "bw": {"주요사항보고서(신주인수권부사채권발행결정)"},
    "eb": {"주요사항보고서(교환사채권발행결정)"},
}
METRICS = ("ret", "tail", "pos", "depth")


def guard_time():
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    if now.weekday() < 5 and "20:10" <= now.strftime("%H:%M") < "22:30":
        raise RuntimeError("평일 배치 제한 시간: 파일/DB 작업 중단")
    return now.isoformat(timespec="seconds")


def read_db(path, queries):
    guard_time()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as con:
        con.execute("PRAGMA query_only=ON")
        assert con.execute("PRAGMA query_only").fetchone()[0] == 1
        con.execute("BEGIN")
        frames = [pd.read_sql_query(sql, con) for sql in queries]
        con.rollback()
    con.close()
    return frames


def stamp(path):
    st = path.stat()
    return (st.st_size, st.st_mtime_ns)


def codes(series):
    return series.astype(str).str.strip().str.zfill(6)


def recent_matrix(events, dates, tickers, calendar, window, exclude_today=False):
    """Latest known raw receipt within an inclusive calendar-date interval."""
    ids = np.full((len(dates), len(tickers)), -1, dtype=np.int32)
    values = np.full(ids.shape, np.nan)
    tmap = {s: i for i, s in enumerate(tickers)}
    ci = np.searchsorted(calendar, dates)
    lower = calendar[np.maximum(0, ci - window + 1)]
    for ticker, sub in events.groupby("ticker", sort=False):
        j = tmap.get(ticker)
        if j is None:
            continue
        sub = sub.sort_values(["rcept_dt", "event_id"], kind="stable")
        receipt = sub.rcept_dt.to_numpy(dtype="U8")
        k = np.searchsorted(receipt, dates, side="left" if exclude_today else "right") - 1
        safe = np.maximum(k, 0)
        ok = (k >= 0) & (receipt[safe] >= lower)
        ids[ok, j] = sub.event_id.to_numpy()[safe[ok]]
        if "sue" in sub:
            values[ok, j] = sub.sue.to_numpy()[safe[ok]]
    return ids >= 0, values, ids


def bootstrap(values, months):
    """Resample whole months, then equally weight retained dates, not months."""
    values = np.asarray(values, float)
    levels, inv = np.unique(months, return_inverse=True)
    mean = values.mean(axis=0)
    if len(levels) < 2:
        return mean, np.full((2, values.shape[1]), np.nan)
    sums = np.zeros((len(levels), values.shape[1]))
    np.add.at(sums, inv, values)
    counts = np.bincount(inv)
    rng = np.random.default_rng(7)
    weights = rng.multinomial(len(levels), np.full(len(levels), 1 / len(levels)), size=2000)
    samples = (weights @ sums) / (weights @ counts)[:, None]
    return mean, np.quantile(samples, [.025, .975], axis=0)


def forecast_records(earnings, method):
    actual = {(r.ticker, int(r.year), r.reprt): r.rcept_dt
              for r in earnings.itertuples(index=False)}
    order = {"Q1": "H1", "H1": "Q3", "Q3": "Y", "Y": "Q1"}
    records = []
    for r in earnings.itertuples(index=False):
        if method == "365":
            year, quarter, delta = int(r.year) + 1, r.reprt, 365
        else:
            year = int(r.year) + (r.reprt == "Y")
            quarter, delta = order[r.reprt], 91
        pred = (datetime.strptime(r.rcept_dt, "%Y%m%d") + timedelta(days=delta)).strftime("%Y%m%d")
        records.append((r.ticker, r.rcept_dt, pred, year, quarter,
                        actual.get((r.ticker, year, quarter)), int(r.event_id)))
    return pd.DataFrame(records, columns=["ticker", "base", "pred", "year", "quarter", "actual", "event_id"])


def forecast_matrix(records, dates, tickers, calendar):
    ids = np.full((len(dates), len(tickers)), -1, dtype=np.int32)
    tmap = {s: i for i, s in enumerate(tickers)}
    ci = np.searchsorted(calendar, dates)
    for r in records.itertuples(index=False):
        j = tmap.get(r.ticker)
        if j is None:
            continue
        pi = int(np.searchsorted(calendar, r.pred))
        if pi >= len(calendar):
            continue
        # Actual future rows do not determine inclusion. Only already-known
        # target releases can cancel the pending prediction as of each date.
        ok = (dates >= r.base) & (pi - ci >= 0) & (pi - ci <= 10)
        if r.actual is not None:
            ok &= dates < r.actual
        ids[ok, j] = r.event_id
    return ids >= 0, ids


def self_checks():
    cal = np.array(["20260102", "20260105", "20260106", "20260107", "20260108"])
    ev = pd.DataFrame({"ticker": ["000001"] * 3,
                       "rcept_dt": ["20260103", "20260106", "20260107"],
                       "sue": [-1., 2., -3.], "event_id": [0, 1, 2]})
    f, s, _ = recent_matrix(ev, cal[2:4], ["000001"], cal, 3)
    assert f.all() and s[:, 0].tolist() == [2., -3.]
    f, s, _ = recent_matrix(ev, cal[2:4], ["000001"], cal, 3, True)
    assert f.all() and s[:, 0].tolist() == [-1., 2.]
    f, _, _ = recent_matrix(ev.iloc[:1], cal[3:4], ["000001"], cal, 2)
    assert not f.any()  # Holiday receipt before the fixed lower boundary.
    q = np.array([-10., -8., -8., 0., 1., 2.])
    assert (q <= np.quantile(q, .2, method="linear")).sum() == 3
    # Outcome availability must not change the entry quantile.
    ex = np.array([True, False, True, True, True, True])
    assert ((q <= np.quantile(q, .2)) & ex).sum() == 2
    v, ci = bootstrap(np.full((4, 2), 3.), ["a", "a", "b", "c"])
    assert np.allclose(v, 3) and np.allclose(ci, 3)
    v, _ = bootstrap(np.array([[1.], [1.], [10.]]), ["a", "a", "b"])
    assert np.isclose(v[0], 4.)  # Not a mean of monthly means (5.5).
    ret_e, ret_n, share = -2., 4., .3
    assert np.isclose(ret_n - (ret_e * share + ret_n * (1-share)), -(ret_e-ret_n)*share)
    minimal = pd.DataFrame([("000001", 2025, "Q3", "20251114", 0)],
                           columns=["ticker", "year", "reprt", "rcept_dt", "event_id"])
    future = forecast_records(minimal, "91")
    assert len(future) == 1 and future.actual.iloc[0] is None
    c2 = pd.bdate_range("20260202", "20260220").strftime("%Y%m%d").to_numpy()
    f, _ = forecast_matrix(future, c2, ["000001"], c2)
    assert f.any()  # Missing future target must still generate a forecast.
    future["actual"] = "20260210"
    f, _ = forecast_matrix(future, c2, ["000001"], c2)
    assert not f[c2 >= "20260210"].any()
    assert np.searchsorted(c2, "20260208") == np.where(c2 == "20260209")[0][0]
    return "PASS: 창 경계/휴일·당일 제외·최근 부호·분위 동률·미래 청산 독립·월 가중·정책 부호·미관측 대상 예측·발표 후 취소"


def scopes(dates, regimes):
    dates = np.asarray(dates)
    mm = np.array([int(x[4:6]) for x in dates])
    return {"전체": np.ones(len(dates), bool),
            "A": np.asarray(regimes) == "A", "BC": np.asarray(regimes) == "BC",
            "D": np.asarray(regimes) == "D",
            "2023-08~2024": (dates >= "20230801") & (dates <= "20241231"),
            "2025~": dates >= "20250101", "시즌(3/5/8/11)": np.isin(mm, [3, 5, 8, 11]),
            "비시즌": ~np.isin(mm, [3, 5, 8, 11])}


def paired_rows(masks1, masks0, panel, indices, eventids=None):
    rows, skipped = [], 0
    for k in indices:
        p = panel[k]
        if p["ret"] is None:
            continue
        finite = np.isfinite(p["ret"])
        m1, m0 = masks1[k] & finite, masks0[k] & finite
        assert not (m1 & m0).any()
        if not m1.any() or not m0.any():
            skipped += 1
            continue
        row = {"date": p["date"], "regime": p["regime"], "n1": int(m1.sum()),
               "n0": int(m0.sum()), "pre1": int(masks1[k].sum()), "pre0": int(masks0[k].sum()),
               "issuers1": np.where(m1)[0], "issuers0": np.where(m0)[0]}
        if eventids is not None:
            row["events1"] = np.unique(eventids[k, m1][eventids[k, m1] >= 0])
        else:
            row["events1"] = np.array([], dtype=int)
        for side, mask in ((1, m1), (0, m0)):
            r = p["ret"][mask]
            for name, value in (("ret", r.mean()), ("tail", 100*(r <= -20).mean()),
                                ("pos", 100*(r > 0).mean()), ("depth", p["r20"][mask].mean())):
                row[f"{name}{side}"] = float(value)
        rows.append(row)
    return rows, skipped


def summarize(rows):
    if not rows:
        return None
    x = np.array([[r[f"{m}1"] for m in METRICS] + [r[f"{m}0"] for m in METRICS] for r in rows])
    x = np.column_stack([x, x[:, :4] - x[:, 4:8]])
    means, ci = bootstrap(x, [r["date"][:6] for r in rows])
    issuers = [len(set(np.concatenate([r[f"issuers{s}"] for r in rows]))) for s in (1, 0)]
    nevents = len(set(np.concatenate([r["events1"] for r in rows])))
    months = len(set(r["date"][:6] for r in rows))
    return {"n": len(rows), "months": months, "means": means, "ci": ci,
            "slots": [sum(r[f"n{s}"] for r in rows) for s in (1, 0)], "issuers": issuers,
            "events": nevents, "med": [float(np.median([r[f"n{s}"] for r in rows])) for s in (1, 0)],
            "min": [min(r[f"n{s}"] for r in rows) for s in (1, 0)],
            "sparse": months < 6 or min(issuers) < 10}


def num(x):
    return "NA" if not np.isfinite(x) else f"{x:.2f}"


def interval(s, col):
    return f"{num(s['means'][col])} [{num(s['ci'][0,col])}, {num(s['ci'][1,col])}]"


def table_row(label, s):
    if s is None:
        return f"|{label}|0|—|—|—|—|—|—|—|—|판단 불가|"
    m = s["means"]
    return (f"|{label}|{s['n']}/{s['months']}|{s['slots'][0]}/{s['slots'][1]}|"
            f"{num(m[0])}/{num(m[4])}|{interval(s,8)}|"
            f"{num(m[1])}/{num(m[5])}; {interval(s,9)}|"
            f"{num(m[2])}/{num(m[6])}; {interval(s,10)}|"
            f"{num(m[3])}/{num(m[7])}; {interval(s,11)}|"
            f"{s['issuers'][0]}/{s['issuers'][1]}|{s['events']}|{'판단 불가/희소' if s['sparse'] else '탐색'}|")


TABLE_HEADER = ["|범위|짝 날짜/월|슬롯 좌/우|수익 좌/우 %|수익 차 [95%]|꼬리 좌/우 %; 차 [95%]|양수 좌/우 %; 차 [95%]|R20 좌/우 %; 차 [95%]|고유종목 좌/우|노출 접수 ID 수|해석|",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]


def accuracy_lines(records, calendar):
    end = datetime.strptime(calendar[-1], "%Y%m%d")
    mature = records[pd.to_datetime(records.pred, format="%Y%m%d") + pd.Timedelta(days=5) <= end].copy()
    lines = ["|대상 분기|생성 성숙 건|실제 접수 관측|미관측|±5달력일 적중/관측 %|전체 대비 확인 하한 %|±5거래일 적중/관측 %|절대오차 중앙값/90% (달력일)|",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    out = {}
    for label, f in [("전체", mature)] + [(q, mature[mature.quarter == q]) for q in ("Q1", "H1", "Q3", "Y")]:
        matched = f[f.actual.notna()].copy()
        err = (pd.to_datetime(matched.actual, format="%Y%m%d") - pd.to_datetime(matched.pred, format="%Y%m%d")).dt.days.abs().to_numpy()
        hit = int((err <= 5).sum())
        hit_trade = int((np.abs(np.searchsorted(calendar, matched.actual.to_numpy()) - np.searchsorted(calendar, matched.pred.to_numpy())) <= 5).sum())
        pct = lambda a, b: num(100*a/b) if b else "NA"
        med = num(np.median(err)) if len(err) else "NA"
        p90 = num(np.quantile(err, .9)) if len(err) else "NA"
        lines.append(f"|{label}|{len(f)}|{len(matched)}|{len(f)-len(matched)}|{hit}/{pct(hit,len(matched))}|{pct(hit,len(f))}|{hit_trade}/{pct(hit_trade,len(matched))}|{med}/{p90}|")
        out[label] = (len(f), len(matched), hit)
    return lines, out


def main(write_report=False):
    started, start_clock = guard_time(), time.monotonic()
    checks = self_checks()
    before = {k: stamp(v) for k, v in DBS.items()}
    price, extra, market, dart = read_db(DBS["prices"], [
        "SELECT ticker,date,close,volume,is_suspended,market FROM daily_ohlcv WHERE market IN ('KOSPI','KOSDAQ')",
        "SELECT ticker,date,close,volume,is_suspended,market FROM daily_ohlcv_extra WHERE market IN ('KOSPI','KOSDAQ')",
        "SELECT series,date,close FROM market_daily WHERE series IN ('KOSPI','KOSDAQ')",
        "SELECT rcept_no,rcept_dt,ticker,event_type,report_nm FROM dart_events WHERE event_type IN ('paid_in','reduction','cb','bw','eb')"])
    earnings, = read_db(DBS["earnings"], ["SELECT ticker,year,reprt,reprt_ord,rcept_dt,sue,source FROM earnings_q"])
    scores, = read_db(DBS["history"], ["SELECT run_id,market,ticker,final_score_v3 FROM v3_scores WHERE model_id='v30' AND run_id>='20260601'"])
    price_counts = [("본표", len(price), price.ticker.nunique(), price.date.min(), price.date.max()),
                    ("extra", len(extra), extra.ticker.nunique(), extra.date.min(), extra.date.max())]
    for f in (price, extra, earnings, dart, scores):
        f["ticker"] = codes(f.ticker)
    combined = pd.concat([price, extra], ignore_index=True)
    dup = int(combined.duplicated(["ticker", "date"]).sum())
    combined = combined.drop_duplicates(["ticker", "date"], keep="first")
    calendar = np.array(sorted(set(combined.loc[combined.market == "KOSPI", "date"]) & set(combined.loc[combined.market == "KOSDAQ", "date"])), dtype="U8")
    tickers = np.array(sorted(combined.ticker.unique()))
    close = combined.pivot(index="date", columns="ticker", values="close").reindex(index=calendar, columns=tickers).to_numpy(float)
    volume = combined.pivot(index="date", columns="ticker", values="volume").reindex(index=calendar, columns=tickers).to_numpy(float)
    suspended = combined.pivot(index="date", columns="ticker", values="is_suspended").reindex(index=calendar, columns=tickers).to_numpy(float)
    del price, extra, combined
    market_close = market[market.series == "KOSPI"].set_index("date").close.reindex(calendar).to_numpy(float)
    assert np.isfinite(market_close).all() and (market_close > 0).all()
    start = int(np.searchsorted(calendar, "20230731"))
    assert calendar[start] == "20230731" and start >= 20
    grid = np.arange(start, len(calendar)-41, 5)
    assert grid[-1]+41 < len(calendar)
    scores["market"] = scores.market.str.upper()
    scores = scores[scores.market.isin(["KOSPI", "KOSDAQ"])].copy()
    scores["anchor_i"] = np.searchsorted(calendar, scores.run_id.astype(str).to_numpy(), side="right")-1
    assert scores.anchor_i.min() >= 0 and scores.final_score_v3.notna().all()
    run_map = scores[["run_id", "anchor_i"]].drop_duplicates().sort_values("run_id")
    kept = run_map.drop_duplicates("anchor_i", keep="last")
    scores = scores.sort_values(["run_id", "market", "final_score_v3", "ticker"], ascending=[True, True, False, True])
    top_all = scores.groupby(["run_id", "market"], sort=False).head(10).copy()
    top = top_all[top_all.run_id.isin(kept.run_id)].copy()
    assert (top_all.groupby(["run_id", "market"]).size() == 10).all()
    assert (top_all.groupby("run_id").size() == 20).all()
    anchor_indices = sorted(top.anchor_i.unique())
    dates_i = np.array(sorted(set(grid) | set(anchor_indices)))
    dates = calendar[dates_i]
    date_to_k = {i: k for k, i in enumerate(dates_i)}
    grid_k = [date_to_k[i] for i in grid]
    v30_k = [date_to_k[i] for i in anchor_indices]
    nshape = (len(dates), len(tickers))
    os_mask = np.zeros(nshape, bool)
    eligible = np.zeros(nshape, bool)
    os_tonly = np.zeros(nshape, bool)
    panel = []
    missing_summary = {"eligible": 0, "oversold": 0, "eligible_missing_exit": 0, "os_missing_exit": 0,
                       "eligible_exit_zero_volume_or_suspended": 0, "os_exit_zero_volume_or_suspended": 0}
    for k, i in enumerate(dates_i):
        if i < 20:
            raise AssertionError("R20 미성숙")
        r20 = np.full(len(tickers), np.nan)
        ok = (close[i-20] > 0) & (close[i] > 0)
        r20[ok] = 100*(close[i, ok]/close[i-20, ok]-1)
        rmarket = 100*(market_close[i]/market_close[i-20]-1)
        regime = "A" if rmarket <= -5 else "D" if rmarket > 5 else "BC"
        ret = None
        if i+1 < len(calendar):
            base = (close[i] >= 1000) & (close[i+1] > 0) & (volume[i] > 0) & (volume[i+1] > 0) & (suspended[i] == 0) & (suspended[i+1] == 0) & np.isfinite(r20)
            eligible[k] = base & (close[i+1] >= 1000)
            for out, valid in ((os_mask, eligible[k]), (os_tonly, base)):
                if valid.any():
                    out[k] = valid & (r20 <= np.quantile(r20[valid], .2, method="linear"))
        if i+41 < len(calendar):
            ret = np.full(len(tickers), np.nan)
            ok = (close[i+1] > 0) & (close[i+41] > 0)
            ret[ok] = 100*(close[i+41, ok]/close[i+1, ok]-1)
            if i in grid:
                for label, mask in (("eligible", eligible[k]), ("oversold", os_mask[k])):
                    prefix = "os" if label == "oversold" else label
                    missing_summary[label] += int(mask.sum())
                    missing_summary[prefix+"_missing_exit"] += int((mask & ~np.isfinite(ret)).sum())
                    illiquid = (volume[i+41] <= 0) | (suspended[i+41] != 0)
                    missing_summary[prefix+"_exit_zero_volume_or_suspended"] += int((mask & np.isfinite(ret) & illiquid).sum())
        panel.append({"date": calendar[i], "regime": regime, "r20": r20, "ret": ret})
    earnings_raw = len(earnings)
    earnings = earnings.sort_values(["ticker", "year", "reprt", "rcept_dt"], kind="stable").drop_duplicates(["ticker", "year", "reprt"], keep="first")
    earnings = earnings.sort_values(["rcept_dt", "year", "reprt_ord", "ticker"], kind="stable").reset_index(drop=True)
    earnings["event_id"] = np.arange(len(earnings))
    assert earnings.rcept_dt.notna().all() and earnings.sue.notna().all()
    e = {w: recent_matrix(earnings, dates, tickers, calendar, w) for w in (10,20,40)}
    elag = recent_matrix(earnings, dates, tickers, calendar, 20, True)
    dart = dart.drop_duplicates("rcept_no").reset_index(drop=True)
    dart["event_id"] = np.arange(len(dart))
    d = {kind: recent_matrix(dart[dart.event_type == kind], dates, tickers, calendar, 20) for kind in EVENTS}
    dclean = {kind: recent_matrix(dart[(dart.event_type == kind) & dart.report_nm.isin(ORIGINAL_TITLES[kind])], dates, tickers, calendar, 20) for kind in EVENTS}
    forecasts = {m: forecast_records(earnings, m) for m in ("365", "91")}
    pflags = {m: forecast_matrix(forecasts[m], dates, tickers, calendar) for m in forecasts}
    coverage_prior, _, _ = recent_matrix(earnings, dates, tickers, calendar, len(calendar))
    lines = [MARKER, "", f"실측 실행 시작: {started}。새 코드·독립 구현; 저장소 모듈 import 없음。", "", checks, "",
             "모든 연결은 SQLite URI mode=ro와 query_only=ON, 읽기 트랜잭션을 사용했다。", "",
             "|시세 표|행|종목|시작|끝|", "|---|---:|---:|---|---|"]
    lines.extend(f"|{a}|{b:,}|{c}|{d0}|{d1}|" for a,b,c,d0,d1 in price_counts)
    lines += ["", f"결합 키 중복 {dup}; 전체 {len(tickers):,}종목, 공통 거래일 {len(calendar)}개 ({calendar[0]}~{calendar[-1]})。",
              f"5일 격자 {len(grid)}개: {calendar[grid[0]]}~{calendar[grid[-1]]}; 마지막 진입 {calendar[grid[-1]+1]}, 마지막 청산 {calendar[grid[-1]+41]}。",
              f"실적 원행 {earnings_raw:,}, 최초 접수 선택 후 {len(earnings):,}, 고유 종목 {earnings.ticker.nunique():,}。", "",
              "|결과 결측/거래 가능성 진단|반복 종목-날 슬롯 수|", "|---|---:|"]
    lines.extend(f"|{k}|{v:,}|" for k,v in missing_summary.items())
    allos = os_mask[grid_k]
    prior = coverage_prior[grid_k]
    raw_e_share = np.array([(os_mask[k] & e[20][0][k]).sum()/os_mask[k].sum() for k in grid_k])
    lines += ["", f"과매도 중 E20 비중: 날짜 평균 {100*raw_e_share.mean():.2f}%; 슬롯 합산 {100*(allos & e[20][0][grid_k]).sum()/allos.sum():.2f}%。",
              f"과매도 중 당시까지 저장된 실적 접수 이력이 있는 슬롯 {int((allos & prior).sum()):,}/{int(allos.sum()):,} ({100*(allos & prior).sum()/allos.sum():.2f}%)。없음은 미발표와 자료 미포함을 분리할 수 없다。", "",
              "## 2. 실적 접수 비교 — 독립 결과", "",
              "모든 표는 양쪽 모두 결과가 있는 날만 사용한다. 슬롯은 반복 관측을 포함한다. 접수 ID 수는 왼쪽 집단 결과에 연결된 서로 다른 저장 행 수이며 독립 기업 사건 수와 같지 않다. CI는 월 블록 2,000·seed 7, 보정 전이다. 꼬리/양수/R20 열은 좌/우 수준 뒤에 좌−우 차이와 CI를 적었다。", ""]
    attempted = valid_cells = infer_cells = 0
    summaries = {}
    stored_rows = {}

    def emit(name, m1, m0, indices=grid_k, ids=None, overall_only=False, extra_months=False):
        nonlocal attempted, valid_cells, infer_cells
        rows, skipped = paired_rows(m1, m0, panel, indices, ids)
        stored_rows[name] = rows
        lines.extend([f"### {name}", "", f"완결 후보 {sum(panel[k]['ret'] is not None for k in indices)}일 중 짝 비교 {len(rows)}일; 한쪽 부재 {skipped}일。", ""])
        lines.extend(TABLE_HEADER)
        ss = scopes([r["date"] for r in rows], [r["regime"] for r in rows])
        if overall_only:
            ss = {"전체": np.ones(len(rows), bool)}
        if extra_months:
            ss.update({f"{m:02d}월": np.array([int(r["date"][4:6]) == m for r in rows]) for m in range(1,13)})
        if name == "v30 E20 vs !E":
            ss.update({m: np.array([r["date"][:6] == m for r in rows]) for m in sorted(set(r["date"][:6] for r in rows))})
        for label, mask in ss.items():
            attempted += 1
            subset = [r for r, flag in zip(rows, mask) if flag]
            s = summarize(subset)
            summaries[(name,label)] = s
            if s:
                valid_cells += 1
                infer_cells += s["months"] >= 2
            lines.append(table_row(label,s))
        s = summarize(rows)
        if s:
            lines.extend(["", f"일별 집단 크기 최소 좌/우 {s['min'][0]}/{s['min'][1]}, 중앙값 {s['med'][0]:g}/{s['med'][1]:g}。"])
        lines.append("")
        return rows

    for w in (10,20,40):
        flag, sue, ids = e[w]
        emit(f"과매도 E{w} vs !E{w}", os_mask & flag, os_mask & ~flag, ids=ids, extra_months=w==20)
        emit(f"과매도 E{w} bad vs good", os_mask & flag & (sue < 0), os_mask & flag & (sue >= 0), ids=ids)
    nonos = eligible & ~os_mask
    flag, sue, ids = e[20]
    emit("비과매도 E20 vs !E20", nonos & flag, nonos & ~flag, ids=ids)
    emit("비과매도 E20 bad vs good", nonos & flag & (sue < 0), nonos & flag & (sue >= 0), ids=ids)
    flag, sue, ids = elag
    emit("과매도 E20 당일 제외 vs !E", os_mask & flag, os_mask & ~flag, ids=ids)
    emit("과매도 E20 당일 제외 bad vs good", os_mask & flag & (sue < 0), os_mask & flag & (sue >= 0), ids=ids)
    emit("과매도 E20 (1000원은 t만) vs !E", os_tonly & e[20][0], os_tonly & ~e[20][0], ids=e[20][2], overall_only=True)
    lines += ["## 3. 실제 v30 점수 상위 목록", "",
              f"원 run_id {len(run_map)}개 → 공통 가격 앵커 {len(kept)}개; 주말 등 동일 가격일 중복 {len(run_map)-len(kept)}개 제외。",
              "상위 20은 점수만으로 구성했으며 희석/완전성 게이트가 적용된 발송 목록 자체가 아니다. 앵커 내 짝 비교로 서로 다른 시즌의 슬롯을 직접 비교하는 오류를 피했지만 종목 특성 차이는 남는다。", ""]
    vmask = np.zeros(nshape, bool)
    tmap = {s:i for i,s in enumerate(tickers)}
    missing_top = 0
    exposure_rows = []
    for run, sub in top_all.groupby("run_id", sort=True):
        anchor = int(sub.anchor_i.iloc[0])
        k = date_to_k[anchor]
        known = [tmap[t] for t in sub.ticker if t in tmap]
        missing_top += len(sub)-len(known)
        own_mask = np.zeros(len(tickers), bool)
        own_mask[known] = True
        selected = run in set(kept.run_id)
        if selected:
            vmask[k] = own_mask
        total = len(sub)
        recent_n = int(e[20][0][k, known].sum())
        # Receipt-only flags for tickers absent from price matrix, if any.
        unknown = sub.loc[~sub.ticker.isin(tmap), "ticker"].tolist()
        if unknown:
            ff, _, _ = recent_matrix(earnings, dates[k:k+1], unknown, calendar, 20)
            recent_n += int(ff.sum())
        exposure_rows.append((k, run, total, recent_n, own_mask, selected))
    vr = emit("v30 E20 vs !E", vmask & eligible & e[20][0], vmask & eligible & ~e[20][0], indices=v30_k, ids=e[20][2])
    lookup = {r["date"]:r for r in vr}
    lines += [f"가격 표에 없는 상위 슬롯 {missing_top}개。상위 목록 조건 탈락은 보충하지 않음。",
              "아래 원 run_id별 표는 중복 제거 전 전부를 제시한다. 주 비교에는 '동일 가격일 중복 제외' 행을 넣지 않는다. E 창의 t는 가격 앵커로 통일했으므로 휴일 run_id 당일 새 접수를 반영한 실시간 발송 표시의 재현은 아니다。", "",
              "|가격 앵커|선택 run_id|원 상위 수|E 수/비중 %|진입 조건 통과|유효 결과|E 수익 %|!E 수익 %|짝 상태|", "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for k, run, total, en, own_mask, selected in exposure_rows:
        p = panel[k]
        valid = own_mask & eligible[k]
        returned = valid & np.isfinite(p["ret"]) if p["ret"] is not None else np.zeros(len(tickers),bool)
        r = lookup.get(p["date"])
        # Report single-sided means too, but never feed them into paired contrast.
        means = []
        for ef in (e[20][0][k], ~e[20][0][k]):
            mask = returned & ef
            means.append(num(p["ret"][mask].mean()) if mask.any() else "NA")
        status = "동일 가격일 중복 제외" if not selected else "짝" if r else "미완결" if p["ret"] is None else "한쪽 부재"
        lines.append(f"|{p['date']}|{run}|{total}|{en}/{100*en/total:.1f}|{valid.sum()}|{returned.sum()}|{means[0]}|{means[1]}|{status}|")
    lines += ["", "|가격 앵커의 월|중복 제거 앵커 수|상위 20 E 비율 날짜 평균 %|짝 비교 앵커 수|", "|---|---:|---:|---:|"]
    for month in sorted(set(panel[k]["date"][:6] for k,_,_,_,_,selected in exposure_rows if selected)):
        sub = [(k,total,en) for k,_,total,en,_,selected in exposure_rows if selected and panel[k]["date"].startswith(month)]
        share = np.mean([en/total for k,total,en in sub])
        paired = sum(panel[k]["date"] in lookup for k,_,_ in sub)
        lines.append(f"|{month}|{len(sub)}|{100*share:.2f}|{paired}|")
    lines += ["", "## 4. 발표 예정 대리", "",
              "정확도 표는 성과 표와 별개다. '미관측'은 늦은 실제 발표·표의 대상 제외·우측 절단을 구분할 수 없다. 아래 비율은 반복 종목/분기의 기술 통계이며 독립 베르누이 확률 구간을 붙이지 않았다。", ""]
    accuracy = {}
    for method in ("365", "91"):
        lines.extend([f"### +{method}일: 날짜 적중", ""])
        ac, numbers = accuracy_lines(forecasts[method], calendar)
        accuracy[method] = numbers
        lines.extend(ac)
        lines.append("")
        flag, ids = pflags[method]
        exposed = os_mask[grid_k] & flag[grid_k]
        overlap = exposed & e[20][0][grid_k]
        lines.append(f"신호 격자의 과매도 P 슬롯 {int(exposed.sum()):,}, 이 중 다른/최근 E20도 있는 슬롯 {int(overlap.sum()):,}。")
        lines.append("")
        emit(f"과매도 P{method} vs !P & !E20", os_mask & flag, os_mask & ~flag & ~e[20][0], ids=ids)
    lines += ["## 5. 공시 뒤 과매도 — 기본 5개 및 원본 결정 감도 5개", "",
              "paid_in 등에 정정·첨부 행이 많이 들어 있고 cb/bw에는 자기 사채 취득/매도·옵션 행사도 있다. 원본 결정 감도는 제목 필터이며 증권별 동일 경제 사건을 묶은 결과가 아니다. 관리/정지 공시는 자료의 분류 부재로 계산 불가。", "",
              "|분류|전체 저장 접수|제목에 정정|원본 발행/감자 결정|", "|---|---:|---:|---:|"]
    for kind in EVENTS:
        sub = dart[dart.event_type == kind]
        lines.append(f"|{kind}|{len(sub)}|{int(sub.report_nm.str.contains('정정').sum())}|{int(sub.report_nm.isin(ORIGINAL_TITLES[kind]).sum())}|")
    lines.append("")
    for kind in EVENTS:
        flag, _, ids = d[kind]
        emit(f"공시 {kind}20 vs 없음", os_mask & flag, os_mask & ~flag, ids=ids)
    for kind in EVENTS:
        flag, _, ids = dclean[kind]
        emit(f"원본 결정 {kind}20 vs 없음", os_mask & flag, os_mask & ~flag, ids=ids, overall_only=True)
    lines += ["## 6. 제거 정책 번역·검증·시험 수", "",
              "E20을 제외한 평균−원래 전체 과매도 평균을 같은 날 계산했다. 재투입/보유 종목 중복/현금/거래비용을 반영한 계좌 수익 개선은 아니다。", "",
              "|범위|짝 날짜/월|유효 결과 E 비중 %|전체 평균 %|!E 평균 %|제거 효과 %p [95%]|평균 차×평균 비중 %p(참고)|", "|---|---:|---:|---:|---:|---:|---:|"]
    erows = stored_rows["과매도 E20 vs !E20"]
    policy = {}
    for label, mask in scopes([r["date"] for r in erows],[r["regime"] for r in erows]).items():
        rows = [r for r, take in zip(erows, mask) if take]
        if not rows:
            lines.append(f"|{label}|0|NA|NA|NA|NA|NA|")
            continue
        share = np.array([r["n1"]/(r["n1"]+r["n0"]) for r in rows])
        re = np.array([r["ret1"] for r in rows]); rn = np.array([r["ret0"] for r in rows])
        overall = share*re + (1-share)*rn
        effect = rn-overall
        assert np.allclose(effect, -(re-rn)*share)
        # Independent pooled-slot arithmetic, checked per date.
        for r, expected in zip(rows, overall):
            k = date_to_k[int(np.searchsorted(calendar,r["date"]))]
            valid = os_mask[k] & np.isfinite(panel[k]["ret"])
            assert np.isclose(panel[k]["ret"][valid].mean(), expected)
        avg, ci = bootstrap(effect[:,None], [r["date"][:6] for r in rows])
        policy[label] = (avg[0],ci[0,0],ci[1,0])
        lines.append(f"|{label}|{len(rows)}/{len(set(r['date'][:6] for r in rows))}|{100*share.mean():.2f}|{overall.mean():.2f}|{rn.mean():.2f}|{avg[0]:.2f} [{num(ci[0,0])}, {num(ci[1,0])}]|{-np.mean(re-rn)*share.mean():.2f}|")
    # Post-run denominator audit: extend the already-frozen paired policy to
    # dates with no E (exactly zero effect). No new signal selection is tested.
    zero_e = all_e = no_valid = 0
    all_policy, all_dates = [], []
    for k in grid_k:
        ret = panel[k]["ret"]
        valid = os_mask[k] & np.isfinite(ret)
        event = valid & e[20][0][k]
        control = valid & ~e[20][0][k]
        if not valid.any():
            no_valid += 1
        elif not control.any():
            all_e += 1
        else:
            zero_e += not event.any()
            all_policy.append(float(ret[control].mean()-ret[valid].mean()))
            all_dates.append(panel[k]["date"])
    avg, ci = bootstrap(np.array(all_policy)[:,None], [d[:6] for d in all_dates])
    shares = np.array([r["n1"]/(r["n1"]+r["n0"]) for r in erows])
    gaps = np.array([r["ret1"]-r["ret0"] for r in erows])
    covariance = np.mean((shares-shares.mean())*(gaps-gaps.mean()))
    lines += ["", "### 첫 계산 뒤 분모 점검 (새 가설 아님)", "",
              f"격자 {len(grid_k)}일 중 E가 없는 날 {zero_e}, !E가 없는 날 {all_e}, 결과 자체가 없는 날 {no_valid}。E가 없는 날의 제거 효과는 정확히 0으로 두어 전체 격자로 넓히면 {len(all_policy)}일 평균 {avg[0]:.4f}%p [{num(ci[0,0])}, {num(ci[1,0])}]이다. 위 사전 고정 주값은 양쪽이 있는 날만의 정책 효과다。",
              f"짝 날짜의 E 비중과 수익 차이 공분산은 {covariance:.4f}%p이다. 따라서 −평균(차이)×평균(비중)에서 이 공분산을 빼야 직접 정책 효과가 된다. 전체 적용 비중 31%와 짝 날짜 차이를 단순히 곱하는 방식은 날짜 집합도 다르다。",
              f"짝 날짜 중 E 결과가 5개 이하인 날 {sum(r['n1'] <= 5 for r in erows)}/{len(erows)}일; 이 날도 날짜 동일가중이라는 계약에 따라 같은 비중을 갖는다. 이런 날의 큰 집단 차이는 E 전체를 빼는 효과와 다를 수 있다。", ""]
    after = {k: stamp(v) for k,v in DBS.items()}
    assert before == after, "실행 중 DB 크기/수정 시각 변경: 자료 동일성 재확인 필요"
    code_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    lines += ["", f"비교×범위 {attempted}개를 구성, 자료가 있는 칸 {valid_cells}개, 2개월 이상이라 CI를 계산한 칸 {infer_cells}개。",
              f"세 성과 기준 총 시험 설계 {attempted*3}개 = {attempted}×3; 값 산출 {valid_cells*3}개, CI 산출 {infer_cells*3}개。R20 설명 차이 {valid_cells}개, 정책 번역 {len(policy)}개 및 사후 분모 점검 1개는 별도이며 동일 표 재출력은 시험 수에 더하지 않았다。발표 대리 정확도는 2방법×(전체+4분기)=10 기술 요약이다。",
              "기본 공시 질문은 5개; 원본 결정 감도 5개와 범위별 반복을 총계에 포함했다. 반복된 전체/시즌/기간/월 표는 독립 시험이 아니지만 선택 기회를 숨기지 않도록 모두 셌다. 어떤 표도 다중비교 보정을 통과한 새 모델 판정으로 사용하지 않는다。", "",
              f"실행 종료 {guard_time()}, 경과 {time.monotonic()-start_clock:.1f}초。코드 SHA256 `{code_sha}`。",
              "DB 파일 크기/mtime_ns 실행 전후 동일(파일 내용 해시 검증과는 다름):", "",
              "|DB|크기 bytes|mtime_ns 전=후|", "|---|---:|---:|"]
    lines.extend(f"|{name}|{before[name][0]}|{before[name][1]}|" for name in DBS)
    lines += ["", "추가 실제 자료 단언 통과: 기준일/40일 청산 축, 시장지수 누락 없음, 집단 비중·정책 효과 부호와 직접 전체 평균 일치, 집단 중복 없음, DB metadata 불변。", ""]
    report = "\n".join(lines).replace("。", ".")
    if write_report:
        guard_time()
        prefix = REPLY.read_text(encoding="utf-8")
        if "## 7." in prefix:
            raise RuntimeError("§7 대조 완료 보고서는 덮어쓰지 않음; 기본 stdout으로 재현")
        prefix = prefix.split(MARKER)[0].rstrip()
        REPLY.write_text(prefix + "\n\n" + report + "\n", encoding="utf-8")
        print(f"REPORT {REPLY}\n{checks}\n시도 칸={attempted}, 값={valid_cells}, CI={infer_cells}, 총 성과 시험={attempted*3}")
        for key in [("과매도 E20 vs !E20","전체"), ("과매도 E20 bad vs good","전체"),
                    ("v30 E20 vs !E","전체"), ("과매도 P365 vs !P & !E20","전체"),
                    ("과매도 P91 vs !P & !E20","전체")]+[(f"공시 {kind}20 vs 없음","전체") for kind in EVENTS]:
            print(table_row(key[0],summaries[key]))
        print("POLICY",policy)
        print("ACCURACY",accuracy)
    else:
        print(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check-only", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    guard_time()
    if args.self_check_only:
        print(self_checks())
    else:
        main(args.write_report)
