"""Independent sv_b calculation; writes only the paired REPLY Markdown.

Run: python -B -X utf8 research/handoff/code_sv_b_verdict_blind.py
No project module imports, network, collectors, scoring writes or verdict imports.
Reference: PREREGISTER_sv_b; VERDICT_RULES; VERDICT_NOTE_20261011_power.
The permitted lv_e script was read for structure, not executed or imported.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).with_name("REPLY_sv_b_verdict_blind.md")
HISTORY = ROOT / "history.db"
PRICES = ROOT.parent / "dh-q7m3k-data" / "ohlcv.db"
REG = "20260914"
BOOT = 4000
PERMS = 2000
KST = timezone(timedelta(hours=9))


def guard():
    now = datetime.now(KST)
    if now.weekday() < 5 and (20, 10) <= (now.hour, now.minute) < (22, 30):
        raise RuntimeError("평일 20:10~22:30 KST 파일·DB 접근 금지")


def connect_ro(path):
    guard()
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    con.execute("BEGIN")
    return con


def log(msg):
    print(msg, flush=True)


def stat(path):
    s = path.stat()
    return dict(bytes=s.st_size, mtime_ns=s.st_mtime_ns)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def boot_weights(n, seed=7):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(BOOT, n))
    out = np.zeros((BOOT, n))
    np.add.at(out, (np.repeat(np.arange(BOOT), n), idx.ravel()), 1 / n)
    return out


def week_weights(index, seed=7):
    periods = pd.to_datetime(index, format="%Y%m%d").to_period("W-SUN")
    unique = periods.unique().sort_values()
    groups = [np.flatnonzero(periods == w) for w in unique]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(groups), size=(BOOT, len(groups)))
    counts = np.zeros((BOOT, len(groups)))
    np.add.at(counts, (np.repeat(np.arange(BOOT), len(groups)), idx.ravel()), 1)
    out = np.zeros((BOOT, len(index)))
    for j, g in enumerate(groups):
        out[:, g] = counts[:, j, None]
    out /= out.sum(axis=1, keepdims=True)
    return out, periods, unique


def summary(sr, denom=7):
    sr = pd.Series(sr, dtype=float).dropna().sort_index()
    if not len(sr):
        return dict(n=0, mean=float("nan"), ci=[float("nan")] * 2)
    a = sr.to_numpy()
    b = boot_weights(len(a)) @ a
    wb, weeks, names = week_weights(sr.index)
    week_means = sr.groupby(weeks).mean()
    alpha = .05 / denom
    return dict(n=len(a), mean=float(a.mean()), ci=np.quantile(b, [.025, .975]).tolist(),
                bonf=np.quantile(b, [alpha / 2, 1-alpha / 2]).tolist(),
                week_ci=np.quantile(wb @ a, [.025, .975]).tolist(),
                n_weeks=len(names), pos_weeks=int((week_means > 0).sum()),
                weeks={str(k): float(v) for k, v in week_means.items()},
                start=str(sr.index[0]), end=str(sr.index[-1]))


def ci_text(ci):
    return f"[{ci[0]:+.6f}, {ci[1]:+.6f}]"


def wilson(k, n):
    if not n:
        return [float("nan")] * 2
    z = 1.959963984540054
    p = k / n
    d = 1 + z*z/n
    m = (p + z*z/(2*n))/d
    e = z*np.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return [100*(m-e), 100*(m+e)]


def label(s20, s10, pair20, oos):
    if oos < 40:
        return "중간 관측(판정 의견 없음)"
    if not s20["n"]:
        return "판정불가"
    lo, hi = s20["ci"]
    positive = (lo > 0 and s20["pos_weeks"] / s20["n_weeks"] >= .6
                and s20["bonf"][0] > 0 and s10["ci"][0] > 0
                and pair20["ci"][0] > 0 and s20["week_ci"][0] > 0)
    if positive:
        return "유의"
    if lo > 0 or (s20["mean"] > .03 and lo > -.02):
        return "기움"
    if lo <= 0 <= hi:
        return "노이즈"
    if hi < 0:
        return ("역작동(유의)" if s20["bonf"][1] < 0 and s20["week_ci"][1] < 0
                else "역작동(유의 아님)")
    return "판정불가"


def load():
    meta = {str(p): stat(p) for p in (HISTORY, PRICES)}
    with connect_ro(HISTORY) as c:
        scores = pd.read_sql_query("SELECT * FROM wu_scores WHERE model_id IN ('sv_b','sv_a') AND run_id>=?", c, params=[REG])
        models = [r[0] for r in c.execute("SELECT DISTINCT model_id FROM wu_scores ORDER BY model_id")]
        cnt = pd.read_sql_query("SELECT run_id, COUNT(*) n FROM stage1_oversold GROUP BY run_id", c)
        partial = set(cnt.loc[cnt.n < cnt.n.median() * .3, "run_id"].astype(str))
        doubles, gaps = set(), []
        for table in ("v3_scores", "lowvol_scores", "wu_scores"):
            x = pd.read_sql_query(f"SELECT run_id,model_id,MIN(frozen_at) first,MAX(frozen_at) last FROM {table} GROUP BY run_id,model_id", c)
            x["gap"] = (pd.to_datetime(x["last"], utc=True, errors="coerce") - pd.to_datetime(x["first"], utc=True, errors="coerce")).dt.total_seconds()/60
            for r in x[x.gap >= 60].itertuples():
                doubles.add(str(r.run_id)); gaps.append([table, str(r.run_id), str(r.model_id), float(r.gap)])
        actual_runs = set(str(r[0]) for r in c.execute("SELECT DISTINCT run_id FROM runs"))
    c.close()
    with connect_ro(PRICES) as c:
        dates = [str(r[0]) for r in c.execute("SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
        # Include sufficient pre-registration prices for five-day credit windows.
        px = pd.read_sql_query("SELECT ticker,date,close,market,shares FROM daily_ohlcv WHERE date>=?", c, params=["20260801"])
        sf = pd.read_sql_query("SELECT ticker,date,short_vol_ratio,credit_bal_rate,fetched_at FROM short_flows", c)
        extra = set(str(r[0]) for r in c.execute("SELECT DISTINCT ticker FROM daily_ohlcv_extra"))
    c.close()
    for df in (scores, px, sf):
        df["ticker"] = df.ticker.astype(str)
    scores["market"] = scores.market.str.lower()
    scores["run_id"] = scores.run_id.astype(str)
    assert not scores.duplicated(["run_id", "market", "ticker", "model_id"]).any()
    close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").reindex(dates)
    mcap = (px.assign(cap=pd.to_numeric(px.close) * pd.to_numeric(px.shares))
            .pivot_table(index="date", columns="ticker", values="cap", aggfunc="last").reindex(dates))
    return scores, models, dates, close, mcap, sf, partial, doubles, gaps, actual_runs, extra, meta


class Study:
    def __init__(self, scores, dates, close, excluded):
        self.scores = scores
        self.dates = dates
        self.didx = {d:i for i,d in enumerate(dates)}
        self.close = close
        self.pct = close.pct_change(fill_method=None).abs()
        self.excluded = excluded
        self.keep = {}
        self.groups = {}
        self.ret_cache = {}
        for model in ("sv_b", "sv_a"):
            ss = scores[scores.model_id == model]
            by_anchor = {}
            for rid in sorted(ss.run_id.unique()):
                t = self.anchor(rid)
                if rid >= REG and rid not in excluded and t is not None:
                    by_anchor.setdefault(t, []).append(rid)
            self.keep[model] = sorted(min([r for r in rr if r in self.didx] or rr) for rr in by_anchor.values())
            self.groups[model] = {rid:g.set_index("ticker") for rid,g in ss.groupby("run_id")}

    def anchor(self, rid):
        for k in range(6):
            d = (datetime.strptime(rid, "%Y%m%d") - timedelta(days=k)).strftime("%Y%m%d")
            if d in self.didx:
                return self.didx[d]
        return None

    def returns(self, rid, h):
        key = (rid, h)
        if key not in self.ret_cache:
            t = self.anchor(rid)
            if t + 1 + h >= len(self.dates):
                return None
            entry, end = self.close.iloc[t+1], self.close.iloc[t+1+h]
            raw = end / entry - 1
            jump = self.pct.iloc[t+2:t+2+h].max()
            self.ret_cache[key] = (raw, jump, raw.where(jump <= .32))
        return self.ret_cache[key]

    def calculate(self, model, h, intersection=False):
        out, audit = {}, dict(total=0, missing_ticker=0, missing_endpoint=0, jump=0,
                             jump_unknown=0, score_missing=0, valid_pairs=0, rejected_groups=0)
        for rid in self.keep[model]:
            ret = self.returns(rid, h)
            if ret is None:
                continue
            raw, jump, cut = ret
            g = self.groups[model][rid]
            if intersection:
                other = self.groups["sv_a" if model == "sv_b" else "sv_b"].get(rid)
                if other is None:
                    continue
                g = g.loc[g.index.intersection(other.index)]
            per = []
            for mk, gm in g.groupby("market"):
                s = gm.wu_score.astype(float)
                r = raw.reindex(s.index); j = jump.reindex(s.index); y = cut.reindex(s.index)
                absent = ~s.index.isin(self.close.columns)
                endpoint = ~absent & r.isna()
                jumped = ~absent & r.notna() & (j > .32)
                valid = s.notna() & y.notna()
                audit["total"] += len(s)
                audit["missing_ticker"] += int(absent.sum())
                audit["missing_endpoint"] += int(endpoint.sum())
                audit["jump"] += int(jumped.sum())
                audit["jump_unknown"] += int((~absent & r.notna() & j.isna()).sum())
                audit["score_missing"] += int(s.isna().sum())
                audit["valid_pairs"] += int(valid.sum())
                if valid.sum() >= 8 and s[valid].nunique() >= 3 and y[valid].nunique() >= 3:
                    per.append(float(spearmanr(s[valid], y[valid]).statistic))
                else:
                    audit["rejected_groups"] += 1
            if per:
                out[rid] = float(np.mean(per))
        return pd.Series(out, dtype=float).sort_index(), audit


def coverage(study, sf):
    q = sf.copy()
    q["credit_bal_rate"] = pd.to_numeric(q.credit_bal_rate, errors="coerce")
    q["short_vol_ratio"] = pd.to_numeric(q.short_vol_ratio, errors="coerce")
    raw = q.pivot_table(index="date", columns="ticker", values="credit_bal_rate", aggfunc="last").reindex(index=study.dates, columns=study.close.columns)
    direct = raw.rolling(5, min_periods=1).mean()
    # Same five calendar-trading-day window, but no values newer than D-3.
    delayed = raw.shift(3).rolling(2, min_periods=1).mean()
    pos = pd.DataFrame(np.where(raw.notna(), np.arange(len(raw))[:,None], np.nan), index=raw.index, columns=raw.columns).ffill()
    rows = []
    for rid in study.keep["sv_b"]:
        t = study.anchor(rid); day = study.dates[t]
        b = study.groups["sv_b"][rid]; a = study.groups["sv_a"].get(rid)
        names = b.index
        cr = direct.iloc[t].reindex(names); lag = delayed.iloc[t].reindex(names)
        age = t - pos.iloc[t].reindex(names)
        inter = names.intersection(a.index) if a is not None else pd.Index([])
        frozen = pd.to_datetime(b.frozen_at, utc=True, errors="coerce").dt.tz_convert(KST)
        late = int((frozen.dt.strftime("%Y%m%d") > rid).sum())
        # crb5 auxiliary rank 0.5 is necessary for missing, not sufficient: ties can also equal 0.5.
        aux = b.loc[inter].wu_score - a.loc[inter].wu_score if a is not None else pd.Series(dtype=float)
        rows.append(dict(run=rid, n_b=len(b), n_a=0 if a is None else len(a), intersection=len(inter),
                         n_credit=int(cr.notna().sum()), coverage=float(cr.notna().mean()),
                         lag3_n=int(lag.notna().sum()), lag3_coverage=float(lag.notna().mean()),
                         age_median=float(age.median()) if age.notna().any() else None,
                         stale_gt5=int((age > 5).sum()), no_credit_history=int(age.isna().sum()),
                         late_rows=late, frozen_first=str(b.frozen_at.min()), frozen_last=str(b.frozen_at.max()),
                         aux_half=int(np.isclose(aux, .5, atol=1e-12).sum())))
    return pd.DataFrame(rows), raw


def nonoverlap(study, index, h):
    selected, last = [], -10**9
    for rid in index:
        p = study.anchor(rid)
        if p-last >= h:
            selected.append(rid); last = p
    return selected


def persistence(study):
    values, ratios, gaps = {}, {}, []
    runs = study.keep["sv_b"]
    for before, after in zip(runs[:-1], runs[1:]):
        a = study.groups["sv_b"][before].wu_score
        b = study.groups["sv_b"][after].wu_score
        cm = a.index.intersection(b.index)
        if len(cm) >= 8:
            values[after] = float(spearmanr(a.loc[cm], b.loc[cm]).statistic)
            ratios[after] = len(cm)/len(a)
            gaps.append(study.anchor(after)-study.anchor(before))
    return summary(pd.Series(values)), summary(pd.Series(ratios)), gaps


def row_corr(x, y):
    mask = np.isfinite(x) & np.isfinite(y)
    xr = rankdata(np.where(mask, x, np.nan), axis=1, nan_policy="omit")
    yr = rankdata(np.where(mask, y, np.nan), axis=1, nan_policy="omit")
    n = mask.sum(axis=1)
    xm = np.nansum(xr, axis=1)/np.maximum(n, 1)
    ym = np.nansum(yr, axis=1)/np.maximum(n, 1)
    xc = np.where(mask, xr-xm[:,None], 0); yc = np.where(mask, yr-ym[:,None], 0)
    divisor = np.sqrt((xc*xc).sum(axis=1)*(yc*yc).sum(axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (xc*yc).sum(axis=1)/divisor
    # Count changes between adjacent finite sorted values: >=2 changes means >=3 distinct.
    xs = np.sort(np.where(mask, x, np.inf), axis=1)
    ys = np.sort(np.where(mask, y, np.inf), axis=1)
    ux = ((xs[:, 1:] != xs[:, :-1]) & np.isfinite(xs[:, 1:])).sum(axis=1)
    uy = ((ys[:, 1:] != ys[:, :-1]) & np.isfinite(ys[:, 1:])).sum(axis=1)
    r[(n < 8) | (ux < 2) | (uy < 2) | (divisor == 0)] = np.nan
    return r


def permute(study, mcap, real, denom, nperm):
    log(f"자리바꿈 시작: 시장 내 {nperm}회 + 시총 5분위 {nperm}회")
    common_runs = sorted(set(study.keep["sv_b"]) & set(study.keep["sv_a"]))
    all_scores = study.scores[study.scores.run_id.isin(common_runs)]
    markets = sorted(all_scores.market.unique())
    arrays, strata = {}, {}
    for mk in markets:
        pool = sorted(all_scores.loc[all_scores.market == mk, "ticker"].unique())
        score_mats = {}
        for model in ("sv_b", "sv_a"):
            ss = all_scores[(all_scores.market == mk) & (all_scores.model_id == model)]
            score_mats[model] = ss.pivot(index="run_id", columns="ticker", values="wu_score").reindex(index=common_runs, columns=pool).to_numpy(float)
        ret = {}
        for h in (20, 10):
            eligible = [i for i,r in enumerate(common_runs) if study.returns(r,h) is not None]
            ret[h] = (eligible, np.array([study.returns(common_runs[i],h)[2].reindex(pool).to_numpy(float) for i in eligible]))
        # Sensitivity definition: market cap at registration, deterministic rank qcut; missing is own stratum.
        cap = mcap.loc[REG].reindex(pool)
        stratum = np.full(len(pool), -1, dtype=int)
        valid = cap.notna() & (cap > 0)
        stratum[valid] = pd.qcut(cap[valid].rank(method="first"), 5, labels=False).to_numpy(int)
        strata[mk] = [np.flatnonzero(stratum == k) for k in sorted(set(stratum))]
        arrays[mk] = (pool, score_mats, ret)
    output = {}
    for mode in ("시장 내", "시장·등록일 시총5분위 내"):
        rng = np.random.default_rng(20261012)
        samples = {(model,h):[] for model in ("sv_b","sv_a") for h in (20,10)}
        for repeat in range(nperm):
            if repeat % 100 == 0:
                guard()
                if repeat % 500 == 0: log(f"{mode}: {repeat}/{nperm}")
            accum = {key:[] for key in samples}
            for mk in markets:
                pool, score_mats, ret = arrays[mk]
                mapping = np.arange(len(pool))
                if mode == "시장 내":
                    mapping = rng.permutation(len(pool))
                else:
                    for ix in strata[mk]: mapping[ix] = rng.permutation(ix)
                for h in (20,10):
                    ix, yy = ret[h]
                    moved_return = yy[:,mapping]
                    for model in ("sv_b","sv_a"):
                        accum[model,h].append(row_corr(score_mats[model][ix], moved_return))
            for key in samples:
                samples[key].append(np.nanmean(accum[key], axis=0))
        samples = {k:np.asarray(v) for k,v in samples.items()}
        assert all(np.isfinite(x).all() for x in samples.values()), "빈 자리바꿈 IC: 분모를 재검토할 것"
        idx20 = [r for r in common_runs if study.returns(r,20) is not None]
        idx10 = [r for r in common_runs if study.returns(r,10) is not None]
        bs20 = boot_weights(len(idx20)); bs10 = boot_weights(len(idx10))
        wb, periods, weeks = week_weights(idx20)
        a20, a10 = samples["sv_b",20], samples["sv_b",10]
        diff20 = a20-samples["sv_a",20]; diff10 = a10-samples["sv_a",10]
        boots20 = bs20 @ a20.T
        ci20 = np.quantile(boots20, [.025,.975], axis=0)
        bonf = np.quantile(boots20, [.025/denom,1-.025/denom], axis=0)
        ci10 = np.quantile(bs10 @ a10.T, [.025,.975], axis=0)
        ci_pair = np.quantile(bs20 @ diff20.T, [.025,.975], axis=0)
        ci_pair10 = np.quantile(bs10 @ diff10.T, [.025,.975], axis=0)
        week_ci = np.quantile(wb @ a20.T, [.025,.975], axis=0)
        week_pos = np.mean(np.array([a20[:,periods==w].mean(axis=1)>0 for w in weeks]), axis=0)
        basic = (ci20[0] > 0) & (week_pos >= .6)
        full = basic & (bonf[0]>0) & (ci10[0]>0) & (ci_pair[0]>0) & (week_ci[0]>0)
        counts = {"iid·주별":int(basic.sum()), "전체 라벨 조건":int(full.sum()),
                  "전체+짝h10":int((full & (ci_pair10[0]>0)).sum())}
        records = {}
        for name, data, observed in (
            ("sv_b h20", a20.mean(axis=1), real["sv_b",20].mean()),
            ("sv_b−sv_a h20", diff20.mean(axis=1), (real["sv_b",20]-real["sv_a",20]).dropna().mean()),
            ("sv_b h10", a10.mean(axis=1), real["sv_b",10].mean()),
            ("sv_b−sv_a h10", diff10.mean(axis=1), (real["sv_b",10]-real["sv_a",10]).dropna().mean())):
            below = int((data < observed).sum())
            tail = int((data >= observed).sum()) if observed >= 0 else int((data <= observed).sum())
            records[name] = dict(n=nperm, actual=float(observed), null_quantiles=np.quantile(data,[.025,.5,.975]).tolist(),
                                  percentile=100*below/nperm, percentile_ci=wilson(below,nperm),
                                  direction_tail=tail, direction_tail_ci=wilson(tail,nperm),
                                  two_sided_p=min(1., 2*(min(below,nperm-below)+1)/(nperm+1)))
        output[mode] = dict(records=records, pass_counts=counts,
                            pass_ci={k:wilson(v,nperm) for k,v in counts.items()},
                            strata_sizes={mk:[len(x) for x in strata[mk]] for mk in markets})
    return output


def markdown_table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "|"+"|".join(["---"]*len(headers))+"|"] + ["| " + " | ".join(map(str,row)) + " |" for row in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--perm", type=int, default=PERMS)
    args = parser.parse_args()
    guard(); start = time.monotonic()
    log("DB mode=ro 로 자료 읽기")
    scores, models, dates, close, mcap, sf, partial, doubles, gaps, runs, extra, meta = load()
    log(f"가격 마지막 {dates[-1]}, sv_b run {scores[scores.model_id=='sv_b'].run_id.nunique()}, wu 모델 {models}")
    if args.inspect:
        print(scores[["run_id","market","ticker","frozen_at"]].head().to_string(index=False))
        print(sf.groupby("date").credit_bal_rate.count().tail(8).to_string())
        return
    study = Study(scores, dates, close, partial|doubles)
    n_oos = len(study.keep["sv_b"]); denom = max(7, len(models))
    cv, credit = coverage(study,sf)
    real, audits, stats = {}, {}, {}
    for model in ("sv_b","sv_a"):
        for h in (20,10):
            real[model,h], audits[model,h] = study.calculate(model,h)
            stats[model,h] = summary(real[model,h],denom)
            log(f"{model} h{h}: {json.dumps(stats[model,h],ensure_ascii=False)}")
    pairs, intersection = {}, {}
    for h in (20,10):
        pairs[h] = summary((real["sv_b",h]-real["sv_a",h]).dropna(),denom)
        x,_ = study.calculate("sv_b",h,True); y,_=study.calculate("sv_a",h,True)
        intersection[h] = summary((x-y).dropna(),denom)
        # Independent array-path correctness check before costly permutation.
        for model in ("sv_b","sv_a"):
            for rid in real[model,h].index:
                r=study.returns(rid,h)[2]; gg=study.groups[model][rid]
                check=[]
                for _,g in gg.groupby("market"):
                    a=g.wu_score.to_numpy(float)[None,:]; b=r.reindex(g.index).to_numpy(float)[None,:]
                    check.append(row_corr(a,b)[0])
                assert np.isclose(np.nanmean(check),real[model,h][rid],atol=1e-12)
    low = cv.loc[cv.coverage < .9,"run"].tolist()
    sensitivity = {}
    for name, removed in (("crb5 현재 DB 커버리지 90% 미만 제외",set(low)),("10/14 사후 적재 제외",{"20261014"})):
        for h in (20,10):
            b=real["sv_b",h].drop(index=list(removed),errors="ignore")
            a=real["sv_a",h].drop(index=list(removed),errors="ignore")
            sensitivity[name,h] = (summary(b,denom),summary((b-a).dropna(),denom))
    persist, retention, day_gaps = persistence(study)
    permutation = permute(study,mcap,real,denom,args.perm) if args.perm else {}
    guard()
    changed = [str(p) for p in (HISTORY,PRICES) if stat(p) != meta[str(p)]]
    if changed:
        raise RuntimeError(f"계산 도중 DB 파일 변경: {changed}; 결과를 확정하지 않음")
    label_name=label(stats["sv_b",20],stats["sv_b",10],pairs[20],n_oos)
    missing_wu=[d for d in dates if REG<=d<=dates[-1] and d not in set(scores[scores.model_id=="sv_b"].run_id)]
    missing_runs=[d for d in dates if REG<=d<=dates[-1] and d not in runs]
    late=cv[cv.late_rows>0]
    out=["# sv_b §11 독립 재계산 답변", "",
         "> **완전한 눈가림 아님.** 필수 지침 worklog/README.md·최신 worklog·KNOWLEDGE K20·DECISIONS D37·MODELS_LEDGER에서 2026-11-13 sv_b 라벨과 중간/최종 요약 수치를 먼저 보았다.",
         "> 금지된 루트 sv_b VERDICT 문서·동일 날짜 sv_b 판정 스크립트·그 출력은 열거나 실행하지 않았다. 허용된 lv_e 스크립트는 구조 참고만 했으며 실행·import하지 않았다.",
         "> 계산은 아래 독립 코드로 DB 동결점수에서 다시 수행했다. 따라서 **독립 구현에 의한 사후 대조**이며 눈가림 검증으로 부르지 않는다.", "",
         f"- 작성 시각(KST): {datetime.now(KST).isoformat(timespec='seconds')}; 가격 기준일 {dates[-1]}.",
         "- 요청 범위: sv_b / wu_scores.wu_score / REG_DATE 20260914 / 짝 sv_a. 모델·점수·게이트·문서 정본·docs·배치는 변경하지 않았다.",
         "- DB 연결은 mode=ro + query_only=ON + 읽기 트랜잭션. 저장한 파일은 이 답변과 code_sv_b_verdict_blind.py뿐이다.",
         "- 표본 평균은 날짜 iid bootstrap 4,000회 seed 7의 95% 구간. Bonferroni 구간은 따로 표기한다. 행·날짜 전수 집계 n에는 표본추정 CI가 적용되지 않는다.",
         "- 순위 상관 = 각 run의 시장별 Spearman(8쌍·각 고유값 3개 이상) 평균 → run 동일가중; t+1 종가 진입, t+1+h 종가 청산, t+2~t+1+h의 절대 일간수익 >32% 제외.", "",
         "## 0. 조건·자료 범위 [실측]",
         f"- 유효 앵커 sv_b {n_oos}, sv_a {len(study.keep['sv_a'])}; 공통 {len(set(study.keep['sv_b'])&set(study.keep['sv_a']))}. 가격 날짜 차 {len(dates)-1-study.didx[REG]}거래일(양 끝 포함 수와 다름).",
         f"- 40일 조건: {'충족' if n_oos>=40 else '미충족 — 중간 관측, 판정 의견 없음'}. 유효 run {study.keep['sv_b'][0]}~{study.keep['sv_b'][-1]}.",
         f"- 분모: wu_scores distinct model_id={len(models)} ({', '.join(models)}), 사전등록 7; 적용 {denom}, 보정 신뢰수준 {100*(1-.05/denom):.6f}%.",
         f"- 전체 부분실행 제외 {sorted(partial)}; 전체 이중실행 제외 {sorted(doubles)}; 등록 후 제외 {sorted((partial|doubles)&set(scores.run_id))}.",
         f"- 창 안 wu run 없는 가격일 {missing_wu or '없음'}; runs 표에 없는 가격일 {missing_runs or '없음'}.",
         f"- frozen_at의 KST 날짜가 run_id 뒤인 sv_b run {len(late)}, 행 {int(late.late_rows.sum())}; 날짜 {late.run.tolist()}.",
         f"- sv_b spec_hash {scores[scores.model_id=='sv_b'].spec_hash.unique().tolist()}; sv_a {scores[scores.model_id=='sv_a'].spec_hash.unique().tolist()}.", "",
         "## 1. h20·h10 및 같은 앵커 짝 [실측]", ""]
    rows=[]
    for model in ("sv_b","sv_a"):
        for h in (20,10):
            s=stats[model,h]
            rows.append([model,f"h{h}",s["n"],f"{s['mean']:+.6f}",ci_text(s["ci"]),ci_text(s["bonf"]),ci_text(s["week_ci"]),f"{s['pos_weeks']}/{s['n_weeks']}",f"{s['start']}~{s['end']}"])
    out+=markdown_table(["모델","지평","n 앵커","평균 IC","iid 95%","Bonferroni","주블록 95%","양의 주/전체","앵커 범위"],rows)
    out += ["", "주블록은 월~일 주를 복원추출하고 주 안 앵커를 전부 연결한 평균(4,000회 seed 7); 주간 평균에 같은 가중치를 주는 방식이 아니다.", ""]
    out+=markdown_table(["짝 sv_b−sv_a","n","차이","iid 95%","주블록 95%","교집합 차이·95%"],
        [[f"h{h}",pairs[h]["n"],f"{pairs[h]['mean']:+.6f}",ci_text(pairs[h]["ci"]),ci_text(pairs[h]["week_ci"]),f"{intersection[h]['mean']:+.6f} {ci_text(intersection[h]['ci'])}"] for h in (20,10)])
    out += ["", f"유니버스 완전 동일 run {int(((cv.n_a==cv.intersection)&(cv.n_b==cv.intersection)).sum())}/{len(cv)}. 각 run의 종목 수와 교집합은 §5 전수표에 있다.", "",
            "### 주별 h20", ""]
    out+=markdown_table(["주","평균 IC","n 앵커"],[[w,f"{v:+.6f}",int((pd.to_datetime(real['sv_b',20].index).to_period('W-SUN').astype(str)==w).sum())] for w,v in stats['sv_b',20]['weeks'].items()])
    out += ["", "## 2. 커버리지·사후 적재·자료 결손 [실측과 한계]", "",
            "- crb5 출처는 ohlcv.db.short_flows.credit_bal_rate. kis_flows.parse_credit는 원천 deal_date에 whol_loan_rmnd_rate를 저장한다. wu_score.load_window/compute_frames는 가격 달력에 맞춰 rolling(5,min_periods=1), 보조 결측은 순위 0.5를 사용한다.",
            "- **코드에 3일 shift는 없다.** 3거래일은 원천 공표·적재 지연이라는 사전등록 가정이다. 현재 DB의 5일 창 재구성(주표)과 같은 창에서 D−2~D0를 숨긴 D−3 지연 가정(감도)을 분리했다.",
            "- short_flows는 INSERT OR REPLACE로 fetched_at도 덮어쓴다. 날짜별 원천 값·도착 시점의 과거 스냅샷과 당시 crb5 마스크가 없어, **현재 DB 커버리지를 당시 실제 사용 커버리지로 확정할 수 없다.** fetched_at만 과거 시각으로 잘라 초기 적재 이력을 복원하지 않았다.",
            f"- 현재 DB 5일 창 커버리지 <90%: {len(low)}/{len(cv)} run, {low}; 범위 {cv.coverage.min()*100:.3f}~{cv.coverage.max()*100:.3f}%.",
            f"- 같은 5일 창에 D−3 가정을 적용하면 <90% {int((cv.lag3_coverage<.9).sum())}/{len(cv)} run. 이는 추정 감도이고 사전등록 스펙을 바꿔 재점수화한 결과가 아니다.",
            f"- 현재 DB의 마지막 신용 관측이 5거래일보다 오래된 종목이 있는 run {int((cv.stale_gt5>0).sum())}/{len(cv)}. 당시 적재 지연 >5거래일의 지속 여부는 확인 못 함.",
            "- 사전등록 §2는 커버리지 <90% 또는 적재 지연 >5거래일 지속 시 보류다. 통계 라벨 조건과 별개이며, 감도 결과가 같다는 이유로 자동 해제하지 않는다.",
            "- DECISIONS D37·최신 worklog에는 초기 결손과 감도를 알고 사용자가 판정 진행을 확정했다고 적혀 있다. 기존 결정을 변경하지 않으며, 아래는 원래 조건의 충족 여부와 예외 결정 이력을 분리한 재계산이다.", "",
            "### 결손·사후 적재 제외 감도(주판정 창 변경 아님)", ""]
    out+=markdown_table(["제외 조건","지평","n","sv_b IC·95%","짝 차이·95%"],
        [[name,f"h{h}",s[0]["n"],f"{s[0]['mean']:+.6f} {ci_text(s[0]['ci'])}",f"{s[1]['mean']:+.6f} {ci_text(s[1]['ci'])}"] for (name,h),s in sensitivity.items()])
    out += ["", "### 수익 관측 제외 수", ""]
    out+=markdown_table(["모델·지평","관측 행","시세 종목 없음","진입/청산 결측","점프 >32%","점프 미확인","유효 쌍","IC 제외 시장그룹"],
        [[f"{m} h{h}",d['total'],d['missing_ticker'],d['missing_endpoint'],d['jump'],d['jump_unknown'],d['valid_pairs'],d['rejected_groups']] for (m,h),d in audits.items()])
    out += ["", "시세 결측과 점프컷을 따로 셌다(단위=종목×앵커 관측, 동일 종목 반복 포함). 준비되지 않은 미래 h 창은 제외 수에 넣지 않았다.",
            f"- 9/14~10/08 낡은 수급 사고의 daily_flows는 sv_b 성분이 아니다. svr5·crb5는 short_flows에서 오며 wu 유니버스와 수익은 daily_ohlcv 본표만 사용한다. 현재 extra 표 종목과 이 판정 창 sv_b 종목 교집합 {len(extra & set(scores[scores.model_id=='sv_b'].ticker))}개. 따라서 해당 daily_flows 사고의 직접 성분 경로는 없지만, 당시 short_flows 적재 신선도까지 정상이라고 단정하지 않는다.", "",
            "## 3. 규약 §2 해석표와 독립 의견", ""]
    s=stats['sv_b',20]; a=stats['sv_b',10]; p=pairs[20]
    checks=[("유효 앵커 ≥40",n_oos>=40,str(n_oos)),("h20 iid 하단 >0",s['ci'][0]>0,ci_text(s['ci'])),
            ("주별 양 ≥60%",s['pos_weeks']/s['n_weeks']>=.6,f"{s['pos_weeks']}/{s['n_weeks']}"),
            ("Bonferroni 하단 >0",s['bonf'][0]>0,ci_text(s['bonf'])),("h10 재현(iid 하단 >0)",a['ci'][0]>0,ci_text(a['ci'])),
            ("짝 h20 diff 하단 >0",p['ci'][0]>0,ci_text(p['ci'])),("짝 h10 diff 하단 >0(별도 병기)",pairs[10]['ci'][0]>0,ci_text(pairs[10]['ci'])),
            ("주블록 하단 >0",s['week_ci'][0]>0,ci_text(s['week_ci'])),("모든 run 현재 DB crb5 ≥90%",not low,f"미달 {len(low)} run")]
    out+=markdown_table(["조건","✔/✘","근거"],[[k,"✔" if ok else "✘",v] for k,ok,v in checks])
    out += ["", "h10 재현은 양의 날짜 95% CI로 읽었다. h10 보정 구간도 함께 제공했으며 이번 자료에서는 둘 모두 0을 걸쳐 해석 차이가 라벨을 바꾸지 않는다.", ""]
    conds=[("유의","iid 양 + 주별≥60% + 보정 양 + h10 재현 + 짝 양; 주블록 양"),
           ("기움","iid 양이나 추가 조건 미달, 또는 IC>0.03·iid 하단>−0.02"),
           ("노이즈","iid가 0을 걸치고 기움 조건 미달"),("역작동(유의 아님)","iid 상단<0, 보정 또는 주블록은 0 포함"),
           ("역작동(유의)","iid·보정·주블록 상단 전부<0"),("판정불가","40 도달했으나 h20 표본 없음/계산 불가")]
    out+=markdown_table(["라벨","조건","해당"],[[name,rule,"✔" if name==label_name else "✘"] for name,rule in conds])
    out += ["", f"**독립 의견:** {'유효 앵커 40 미만이므로 중간 관측이며 판정 의견을 내지 않는다.' if n_oos<40 else '통계 해석표상 '+label_name+'이며 sv_a 대비 승격 근거가 없다.'} 커버리지 보류 조건은 미달 이력을 명시하고, 이미 기록된 사용자 예외 결정을 별도로 존중한다. 모델 은퇴·가중 변경·공식 판정 갱신은 하지 않았다.",
            "효과가 없다는 증명이 아니라 이 창에서 양의 순위 예측력을 가리지 못했다는 뜻이다. 짝 차이는 이 창의 동결점수 비교이며, 결손이 있던 시기의 crb5 순수 인과효과로 단정하지 않는다.", "",
            "## 4. 각주 ④ 참고값(라벨에 사용하지 않음)", ""]
    for h in (20,10):
        selected=nonoverlap(study,real['sv_b',h].index,h)
        out.append(f"- h{h}: 완결 n={len(real['sv_b',h])}, 비겹침 {len(selected)}개 {selected}.")
    out += [f"- 점수 하루 지속성: run 쌍 n={persist['n']}, 평균 Spearman {persist['mean']:+.6f}, 날짜 iid 95% {ci_text(persist['ci'])}.",
            f"- 하루 뒤 같은 종목 비율(교집합/전날 유니버스): n={retention['n']}, 평균 {100*retention['mean']:.3f}%, 95% {ci_text([100*x for x in retention['ci']])}%; 거래일 간격 범위 {min(day_gaps)}~{max(day_gaps)}.",
            "- 자리바꿈: 시장별로 창 안 출현 종목의 이름표를 1:1 교환하고 그 매핑을 모든 날짜·두 모델·두 지평에 동일 적용. 2,000회 seed 20261012. 가격·결측·점프컷은 옮겨 받은 종목 기준으로 다시 검사.",
            "- 시총 감도는 **등록일 종가×주식수**의 시장별 5분위 내 교환(결측 별도 층); VERDICT_NOTE는 시총 기준일을 정하지 않아 이 구현 선택을 공개한다. 판정 라벨에는 사용하지 않는다.",
            "- 아래 null 95%는 순열분포의 2.5~97.5백분위이며 효과 CI가 아니다. 백분위·통과율 옆 95%는 2,000회 몬테카를로 오차의 Wilson 구간으로, 미래 성과 불확실성이 아니다.", ""]
    prows=[]
    for mode,v in permutation.items():
        for name,r in v['records'].items():
            q=r['null_quantiles']
            prows.append([mode,name,r['n'],f"{q[0]:+.6f}/{q[1]:+.6f}/{q[2]:+.6f}",f"{r['percentile']:.2f}% {ci_text(r['percentile_ci'])}",f"{r['direction_tail']}/{r['n']} {ci_text(r['direction_tail_ci'])}",f"{r['two_sided_p']:.4f}"])
    out+=markdown_table(["교환 범위","통계","n","null 2.5/50/97.5%","실제값 백분위·95%","관측 방향 꼬리·95%(%)","양측 순열 p(+1)"],prows)
    out += ["", "통과율의 ‘전체’는 h20 날짜·Bonferroni·주블록 하단>0, 주별 양≥60%, h10 날짜 하단>0, 짝 h20 하단>0을 함께 만족한 경우다. 신용자료 보류·사용자 결정은 순열 통계 라벨과 별개다. 기존 간이값과 구별하도록 iid·주별만의 비율과 짝 h10까지 요구한 비율도 병기한다.", ""]
    out+=markdown_table(["교환 범위","통과 조건","통과/횟수","비율·95%(%)"],
        [[mode,k,f"{v}/{args.perm}",f"{100*v/args.perm:.3f}% {ci_text(rec['pass_ci'][k])}"] for mode,rec in permutation.items() for k,v in rec['pass_counts'].items()])
    out += ["", "> ④ 이 창은 수익 구간이 겹치고 점수가 지속된다. 날짜 iid 구간과 주블록 구간도 장기 독립 표본의 증거로 읽지 않는다. 유의·기움은 그 한계 안에서, 노이즈는 ‘못 가렸다’로 읽는다.", "",
            "## 5. run별 유니버스·커버리지 전수표 [실측]", "",
            "현재 DB 창은 D−4~D0(5거래일, min1); 지연 감도는 그 중 D−4~D−3만. 동결 보조차 0.5에는 결측 중립과 실제 중앙 순위가 함께 들어갈 수 있어 실제 결측 수로 사용하지 않는다.", ""]
    out+=markdown_table(["run","sv_b","sv_a","교집합","crb5 유효/n (%)","D−3 가정 유효/n (%)","마지막 관측 나이 중앙",">5일 종목","신용 이력 없음","사후 적재 행","동결 보조차0.5"],
        [[r.run,r.n_b,r.n_a,r.intersection,f"{r.n_credit}/{r.n_b} ({100*r.coverage:.2f})",f"{r.lag3_n}/{r.n_b} ({100*r.lag3_coverage:.2f})",r.age_median,r.stale_gt5,r.no_credit_history,r.late_rows,r.aux_half] for r in cv.itertuples()])
    out += ["", "### 사후 적재 시각", ""]
    out+=markdown_table(["run","동결 시작","동결 끝","늦은 행"],[[r.run,r.frozen_first,r.frozen_last,r.late_rows] for r in late.itertuples()])
    out += ["", "### 완결 앵커별 IC(재현 대조용)", ""]
    indices=real['sv_b',20].index.union(real['sv_b',10].index)
    out+=markdown_table(["run","sv_b h20","sv_a h20","sv_b h10","sv_a h10"],[[r]+[f"{real[m,h].get(r,float('nan')):+.8f}" for h in (20,10) for m in ('sv_b','sv_a')] for r in indices])
    out += ["", "## 6. 재현·검증·확인 못 한 것", "",
            "- 실행: `python -B -X utf8 research/handoff/code_sv_b_verdict_blind.py` (기본 --perm 2000). 금지 시간은 코드에서 차단한다. 재실행하면 이 REPLY만 갱신한다.",
            "- 운영 모듈 import 없음. scipy Spearman으로 주계산 후 별도 배열 순위 구현의 모든 모델·지평·앵커 IC와 1e−12 이내 일치를 검사했다. DB 키 중복과 순열의 빈 IC도 assert로 검사했다.",
            "- frozen_at 간격 게이트는 트랙별 run·model 안 최소~최대 60분 기준을 독립 구현했다. 주말 중복 제거는 거래일 run 우선, 없으면 최소 run_id를 선택했다.",
            "- 숫자 성능을 맞추기 위해 기간·분모·시드·규칙을 조정하지 않았다. 시간·주별·짝 비교를 모두 동일한 날짜 순서로 계산했다.",
            "- 확인 못 함: 당시 crb5 유효 마스크·값 도착 이력, 실제 원천 신용 지연의 매일 상태, 이 창 밖 성과. 역사 입력을 현재 원천으로 재점수화하지 않았다.",
            "- 질문: 사전등록 커버리지 보류 조건의 예외 적용은 사용자 결정 D37에 있지만 사전등록 원문은 그대로다. 이번 보고서는 두 사실을 함께 남기며 새 예외 규칙을 만들지 않았다.",
            f"- 소요시간(이번 독립 계산): {time.monotonic()-start:.1f}초. 라이브러리: numpy {np.__version__}, pandas {pd.__version__}.", "",
            "### 입력 지문", ""]
    out+=markdown_table(["DB","바이트","mtime_ns(시작=종료)"],[[Path(p).name,v['bytes'],v['mtime_ns']] for p,v in meta.items()])
    source_names=['PREREGISTER_sv_b.md','VERDICT_RULES.md','VERDICT_NOTE_20261011_power.md','leaderboard.py','wu_score.py','kis_flows.py']
    out+=markdown_table(["파일","SHA256"],[[name,sha(ROOT/name)] for name in source_names]+[[Path(__file__).name,sha(Path(__file__))]])
    guard()
    REPORT.write_text('\n'.join(out)+'\n',encoding='utf-8')
    log(f"완료: {REPORT}")
    log(f"SUMMARY oos={n_oos} label={label_name} h20={stats['sv_b',20]['mean']:+.6f} h10={stats['sv_b',10]['mean']:+.6f} pair20={pairs[20]['mean']:+.6f} low_cov={len(low)}")


if __name__ == '__main__':
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    main()
