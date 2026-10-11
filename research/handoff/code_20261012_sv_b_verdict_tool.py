"""sv_b 독립 판정 숫자 도구. 기본 실행은 메모리 DB 가짜 자료 검증뿐이다.

실제 자료는 명시적인 --real에서만 읽는다. 저장소 모듈 import, 외부 호출,
파일 출력, 점수 재계산은 없다. --schema는 PRAGMA table_info만 실행한다.
정본: PREREGISTER_sv_b.md; 방법: 20260913 wu / 20260906 prep iid/week-block 판정.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import time

REG = "20260914"
MODEL, BASE = "sv_b", "sv_a"
BOOT, SEED, DENOM = 4000, 7, 7
PLACEBO_REPS, PLACEBO_SEED = 2000, 20261012
MIN_GROUP, MIN_OOS, LAG, JUMP = 8, 40, 1, 0.32
ROOT = Path(__file__).resolve().parents[2]
PRICE_TABLES = ("daily_ohlcv", "short_flows")
PRIMARY_PRICE = "본 표만 (주 계산)"
NEEDED = {
    "wu_scores": "run_id market ticker model_id wu_score frozen_at spec_hash".split(),
    "stage1_oversold": ["run_id"],
    "v3_scores": "run_id model_id frozen_at".split(),
    "lowvol_scores": "run_id model_id frozen_at".split(),
    "daily_ohlcv": "ticker date close shares".split(),
    "short_flows": "ticker date credit_bal_rate".split(),
}


def time_guard(now=None):
    """금지 시간에는 skip_dates만 확인하고 즉시 종료. DB/분석은 시작 안 함."""
    now = now or datetime.now(timezone(timedelta(hours=9)))
    minute = now.hour * 60 + now.minute
    if now.weekday() < 5 and 1210 <= minute <= 1350:
        p = ROOT / "skip_dates.txt"
        skips = p.read_text(encoding="utf-8-sig").splitlines() if p.exists() else []
        if now.strftime("%Y%m%d") not in {s.strip() for s in skips}:
            raise SystemExit("중단: 평일 20:10~22:30 KST 실행 금지")


def ro(path):
    c = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    c.execute("PRAGMA query_only=ON")
    c.execute("BEGIN")
    return c


def schema(c, tables):
    out = {}
    for table in tables:
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})")]
        missing = set(NEEDED[table]) - set(cols)
        if missing:
            raise ValueError(f"확인 못 함: {table} 필수 열 없음 {sorted(missing)}")
        out[table] = cols
    return out


def anchor(rid, dates):
    if rid in dates:
        return dates[rid]
    d = datetime.strptime(rid, "%Y%m%d")
    for k in range(1, 6):
        key = (d - timedelta(days=k)).strftime("%Y%m%d")
        if key in dates:
            return dates[key]
    return None


def choose_runs(scores, dates, excluded, inclusive=True):
    candidates = {}
    for rid in sorted(set(scores.run_id)):
        if rid in excluded or rid < REG or (not inclusive and rid == REG):
            continue
        t = anchor(rid, dates)
        if t is not None:
            candidates.setdefault(t, []).append(rid)
    return {t: min([r for r in runs if r in dates] or runs)
            for t, runs in candidates.items()}


def read_inputs(hc, pc, as_of=None):
    """실제/가짜 DB 공통 읽기 경로. 호출자는 --real 또는 메모리 DB만 허용."""
    schema(hc, [t for t in NEEDED if t not in PRICE_TABLES])
    schema(pc, PRICE_TABLES)
    cutoff = as_of or pc.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()[0]
    if cutoff is None:
        raise ValueError("확인 못 함: 시세 날짜 없음")
    cutoff = str(cutoff)
    s = pd.read_sql_query(
        "SELECT run_id,market,ticker,model_id,wu_score AS score,spec_hash "
        "FROM wu_scores WHERE model_id IN (?,?) AND run_id>=? AND run_id<=?",
        hc, params=(MODEL, BASE, REG, cutoff))
    for col in ["run_id", "market", "ticker", "model_id"]:
        s[col] = s[col].astype(str)
    if s.duplicated(["run_id", "market", "ticker", "model_id"]).any():
        raise ValueError("확인 못 함: 동결점수 키 중복")
    stage1 = pd.read_sql_query(
        "SELECT run_id,COUNT(*) n FROM stage1_oversold WHERE run_id<=? GROUP BY run_id",
        hc, params=(cutoff,)).set_index("run_id")["n"]
    if stage1.empty:
        raise ValueError("확인 못 함: stage1 완전성 기준 없음")
    median = float(stage1.median())
    partial30 = set(stage1[stage1 < median * .30].index.astype(str))
    missing_stage1 = set(s.run_id) - set(stage1.index.astype(str))
    doubles, double_by_table, invalid_frozen = set(), {}, {}
    for table in ("v3_scores", "lowvol_scores", "wu_scores"):
        # 모델 간 백필 시간차는 제외 사유가 아니다. 원본 시간 문자열별 압축만 한다.
        f = pd.read_sql_query(
            f"SELECT DISTINCT run_id,model_id,frozen_at FROM {table} WHERE run_id<=?",
            hc, params=(cutoff,))
        f["ts"] = pd.to_datetime(f.frozen_at, errors="coerce", utc=True, format="mixed")
        invalid_frozen[table] = int(f.ts.isna().sum())
        bad = set()
        for (rid, _), g in f.dropna(subset=["ts"]).groupby(["run_id", "model_id"]):
            if (g.ts.max() - g.ts.min()).total_seconds() >= 3600:
                bad.add(str(rid))
        double_by_table[table] = sorted(bad)
        doubles |= bad
    # 전체 시장 가격 날짜를 먼저 만든다. 대상 종목만 읽어도 날짜 격자는 줄이지 않는다.
    calendar = [str(r[0]) for r in pc.execute(
        "SELECT DISTINCT date FROM daily_ohlcv WHERE date<=? AND close IS NOT NULL ORDER BY date",
        (cutoff,))]
    tickers = sorted(set(s.ticker))
    chunks = []
    for start in range(0, len(tickers), 800):
        tick = tickers[start:start + 800]
        chunks.append(pd.read_sql_query(
            "SELECT ticker,date,close,shares FROM daily_ohlcv WHERE date<=? "
            "AND ticker IN (" + ",".join("?" for _ in tick) + ") ORDER BY date,ticker",
            pc, params=(cutoff, *tick)))
    px = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(
        columns=["ticker", "date", "close", "shares"])
    if px.duplicated(["date", "ticker"]).any():
        raise ValueError("확인 못 함: daily_ohlcv 날짜·종목 키 중복")
    px["date"], px["ticker"] = px.date.astype(str), px.ticker.astype(str)
    close = px.pivot(index="date", columns="ticker", values="close").reindex(calendar)
    credit_chunks = []
    for start in range(0, len(tickers), 800):
        tick = tickers[start:start + 800]
        credit_chunks.append(pd.read_sql_query(
            "SELECT ticker,date,credit_bal_rate FROM short_flows WHERE date<=? AND ticker IN ("
            + ",".join("?" for _ in tick) + ") ORDER BY date,ticker", pc, params=(cutoff, *tick)))
    credit_rows = pd.concat(credit_chunks, ignore_index=True) if credit_chunks else pd.DataFrame(
        columns=["ticker", "date", "credit_bal_rate"])
    if credit_rows.duplicated(["date", "ticker"]).any():
        raise ValueError("확인 못 함: short_flows 날짜·종목 키 중복")
    credit_rows["date"] = credit_rows.date.astype(str)
    credit_rows["ticker"] = credit_rows.ticker.astype(str)
    credit_rows["credit_bal_rate"] = pd.to_numeric(credit_rows.credit_bal_rate, errors="coerce")
    credit = credit_rows.pivot(index="date", columns="ticker", values="credit_bal_rate").reindex(
        index=calendar, columns=tickers)
    # wu_score.load_window: main close 격자로 맞춘 뒤 rolling(5,min1), ffill 없음.
    crb5 = credit.rolling(5, min_periods=1).mean()
    cap_rows = px.loc[px.date.between(REG, cutoff)].copy()
    cap_rows["cap"] = cap_rows.close * cap_rows.shares
    cap_rows = cap_rows.loc[(cap_rows.close > 0) & (cap_rows.shares > 0)
                            & np.isfinite(cap_rows.cap)].sort_values("date").drop_duplicates("ticker")
    first_caps = cap_rows.set_index("ticker")["cap"]
    return dict(scores=s, close=close, crb5=crb5, credit=credit, cutoff=cutoff, first_caps=first_caps,
                dates={d: i for i, d in enumerate(calendar)}, median_stage1=median,
                gates={"판정30": partial30 | doubles},
                partial30=sorted(partial30),
                missing_stage1=sorted(missing_stage1), doubles=sorted(doubles),
                double_by_table=double_by_table, invalid_frozen=invalid_frozen,
                model_count=hc.execute("SELECT COUNT(DISTINCT model_id) FROM wu_scores").fetchone()[0],
                price_membership={m: dict(score_tickers=g.ticker.nunique(),
                    missing_ticker_count=len(set(g.ticker)-set(px.ticker)),
                    missing_tickers=sorted(set(g.ticker)-set(px.ticker)),
                    missing_observations=int((~g.ticker.isin(set(px.ticker))).sum()))
                    for m,g in s.groupby("model_id")})


def rank_ic(g):
    g = g.loc[g.score.notna() & g.ret.notna()]
    if len(g) < MIN_GROUP or g.score.nunique() < 3 or g.ret.nunique() < 3:
        return None
    return float(np.corrcoef(g.score.rank(method="average"),
                            g.ret.rank(method="average"))[0, 1])


def measures(g):
    by_market = {str(m): rank_ic(v) for m, v in g.groupby("market")}
    valid = [v for v in by_market.values() if v is not None]
    return {"시장평균": float(np.mean(valid)) if valid else None,
            "통합": rank_ic(g), **{"시장:" + k: v for k, v in by_market.items()}}


def forward(close, t, h, daily_jump):
    a, b = t + LAG, t + LAG + h
    if b >= len(close):
        return None
    entry, end = close.iloc[a], close.iloc[b]
    raw = end / entry - 1
    jump = daily_jump.iloc[a + 1:b + 1].max()
    missing = entry.isna() | end.isna()
    # 원 선행 코드의 max(skipna=True) 상속. 내부 구멍은 별도 수로 명시.
    valid = raw.notna() & (jump <= JUMP)
    return raw.where(valid), missing, jump.isna(), jump > JUMP, close.iloc[a:b + 1].isna().any()


def series_stats(values, run_dates=None):
    time_guard()
    sr = pd.Series(values, dtype=float).sort_index().dropna()
    if sr.empty:
        return dict(n=0, mean=None, iid95=None, iid_bonf=None, week95=None,
                    week_bonf=None, iid_bonf11=None, week_bonf11=None, iid2000=None, bonf2000=None, anchor_pos=None,
                    week_pos=None, weeks=0, first=None, last=None)
    arr = sr.to_numpy()
    rng = np.random.default_rng(SEED)
    draws = rng.choice(arr, size=(BOOT, len(arr))).mean(axis=1)
    tail = .05 / DENOM * 100 / 2
    ci = lambda x, q: tuple(float(v) for v in np.percentile(x, q))
    # 선행 판정은 run_id의 월~일 주. 비거래일 run의 실제 앵커 주도 감도로 병기.
    labels = pd.to_datetime([run_dates.get(d, d) if run_dates else d for d in sr.index],
                            format="%Y%m%d").to_period("W")
    aw = pd.to_datetime(sr.index, format="%Y%m%d").to_period("W")
    def weekly(labels):
        blocks = [arr[labels == w] for w in labels.unique()]
        indices = np.random.default_rng(SEED).integers(0, len(blocks), (BOOT, len(blocks)))
        sums = np.array([b.sum() for b in blocks])
        sizes = np.array([len(b) for b in blocks])
        draws = sums[indices].sum(axis=1) / sizes[indices].sum(axis=1)
        return dict(pos=float(np.mean([b.mean() > 0 for b in blocks])), n=len(blocks),
                    ci=ci(draws, [2.5, 97.5]), bonf=ci(draws, [tail, 100-tail]), bonf11=ci(draws, [2.5/11, 100-2.5/11]))
    w, actual = weekly(labels), weekly(aw)
    return dict(n=len(sr), mean=float(arr.mean()), iid95=ci(draws, [2.5, 97.5]),
                iid_bonf=ci(draws, [tail, 100-tail]), week95=w["ci"], week_bonf=w["bonf"],
                iid_bonf11=ci(draws, [2.5/11, 100-2.5/11]), week_bonf11=w["bonf11"],
                iid2000=ci(draws[:2000], [2.5, 97.5]), bonf2000=ci(draws[:2000], [tail, 100-tail]),
                anchor_pos=float((arr > 0).mean()), anchor_positive=int((arr > 0).sum()),
                week_pos=w["pos"], weeks=w["n"], actual_anchor_week=actual,
                first=sr.index[0], last=sr.index[-1])


def nonoverlapping(positions, h, calendar):
    """완결/유효 여부는 호출자가 정한다. 차이는 앵커 순번이 아닌 거래일 위치."""
    chosen = []
    for t in sorted(set(positions)):
        if not chosen or t - chosen[-1] >= h:
            chosen.append(t)
    return dict(n=len(chosen), dates=[calendar[t] for t in chosen])


def score_persistence(scores, keep, calendar):
    """연속 유지 run의 공통 종목 점수끼리만 비교. 가격·수익을 받지 않는다.

    같은 종목 비율 = 교집합 종목 수 / 앞 run 종목 수. 시장·종목 키로 정렬.
    2쌍 미만 또는 상수 순위는 상관을 정의할 수 없어 제외하고 건수를 남긴다.
    """
    by_run = {rid: g.set_index(["market", "ticker"])["score"]
              for rid, g in scores.groupby("run_id")}
    ordered = sorted(keep.items())
    rows, corrs, overlaps = [], {}, {}
    for (ta, ra), (tb, rb) in zip(ordered, ordered[1:]):
        left, right = by_run[ra], by_run[rb]
        common = left.index.intersection(right.index)
        pair = pd.concat([left.reindex(common).rename("a"),
                          right.reindex(common).rename("b")], axis=1).dropna()
        corr = None
        if len(pair) >= 2 and pair.a.nunique() > 1 and pair.b.nunique() > 1:
            corr = float(np.corrcoef(pair.a.rank(method="average"),
                                    pair.b.rank(method="average"))[0, 1])
            corrs[calendar[tb]] = corr
        ratio = len(common) / len(left)
        overlaps[calendar[tb]] = ratio
        rows.append(dict(previous_run=ra, next_run=rb, trading_day_gap=tb-ta,
                         previous_n=len(left), next_n=len(right), common_n=len(common),
                         valid_score_pairs=len(pair), rank_correlation=corr, same_ticker_ratio=ratio))
    c, o = series_stats(corrs), series_stats(overlaps)
    return dict(run_pairs=len(rows), valid_rank_run_pairs=c["n"], rank_mean=c["mean"],
                rank_iid95=c["iid95"], same_ticker_mean=o["mean"], same_ticker_iid95=o["iid95"],
                gap_gt1=sum(r["trading_day_gap"] > 1 for r in rows), details=rows)


def reference_values(scores, keep, dates, calendar, series):
    """각주 전용. 이 결과를 라벨/해석 함수에 전달하지 않는다."""
    completed, valid = {}, {}
    for model in (MODEL, BASE):
        for h in (20, 10):
            positions = [t for t in keep[model] if t + LAG + h < len(calendar)]
            completed[h, model] = {"completed_n": len(positions),
                                    **nonoverlapping(positions, h, calendar)}
    for key, values in series.items():
        valid[key] = {"valid_n": len(values),
                      **nonoverlapping([dates[d] for d in values], key[0], calendar)}
    persistence = {m: score_persistence(scores[scores.model_id == m], keep[m], calendar)
                   for m in (MODEL, BASE)}
    return dict(completed_nonoverlap=completed, valid_nonoverlap=valid, persistence=persistence)



def credit_diagnostics(data, keep, groups):
    coverage, daily = [], []
    calendar=list(data["close"].index)
    credit=data["credit"].reindex(calendar)
    # 과거의 마지막 실측 날짜만 전달; 값 자체 ffill로 커버리지를 늘리지 않는다.
    stamps=pd.DataFrame({ticker:pd.Series(np.where(credit[ticker].notna(),calendar,None),index=calendar)
                         for ticker in credit.columns}).ffill()
    for t,rid in sorted(keep.items()):
        time_guard()
        day=calendar[t]; ticks=groups[MODEL,rid].ticker
        values=data["crb5"].loc[day].reindex(ticks)
        present=int(values.notna().sum()); n=len(ticks)
        coverage.append(dict(anchor=day,run=rid,n=n,present=present,fraction=present/n,below90=present/n<.9))
        last=stamps.loc[day].reindex(ticks).dropna()
        lags=last.map(lambda d:t-data["dates"][d]).astype(int)
        hist={int(k):int(v) for k,v in lags.value_counts().sort_index().items()}
        freshest=int(lags.min()) if len(lags) else None
        worst=int(lags.max()) if len(lags) else None
        daily.append(dict(anchor=day,run=rid,last_nonnull=last.max() if len(last) else None,
                          freshest_lag=freshest,oldest_nonnull=last.min() if len(last) else None,
                          worst_lag=worst,unknown_tickers=n-len(last),known_tickers=len(last),
                          lag_histogram=hist,tickers_gt5=int((lags>5).sum()),
                          freshest_gt5=None if freshest is None else freshest>5,
                          worst_gt5=None if worst is None else worst>5))
    def stretches(key):
        runs=[]; current=[]; previous=None
        for row in daily:
            t=data["dates"][row["anchor"]]
            if row[key] is True:
                if current and t!=previous+1:
                    runs.append(current); current=[]
                current.append(row["anchor"])
            elif current:
                runs.append(current);current=[]
            previous=t
        if current:runs.append(current)
        longest=max(map(len,runs),default=0)
        return dict(anchors=sum(row[key] is True for row in daily),longest_trading_days=longest,
                    longest_ranges=[dict(start=x[0],end=x[-1],anchors=len(x)) for x in runs if len(x)==longest],
                    ranges=[dict(start=x[0],end=x[-1],anchors=len(x)) for x in runs])
    return coverage,dict(daily=daily,freshest_gt5=stretches("freshest_gt5"),worst_gt5=stretches("worst_gt5"),
                         unknown_anchors=sum(row["unknown_tickers"]>0 for row in daily))


def evaluate(data, gate_name):
    time_guard()
    s, close, dates = data["scores"], data["close"], data["dates"]
    excluded = data["gates"][gate_name]
    keep = {m: choose_runs(s[s.model_id == m], dates, excluded) for m in (MODEL, BASE)}
    groups = {(m, rid): g for (m, rid), g in s.groupby(["model_id", "run_id"])}
    ekeep = keep[MODEL]
    reg_t = anchor(REG, dates)
    delta = len(close) - 1 - reg_t if reg_t is not None else None
    condition = dict(anchors=len(ekeep), price_date_difference=delta,
                     inclusive_price_dates=delta + 1 if delta is not None else None,
                     anchors_excluding_registration=len(choose_runs(s[s.model_id == MODEL], dates, excluded, False)),
                     anchors40=len(ekeep) >= MIN_OOS,
                     price40=delta is not None and delta >= MIN_OOS)
    sets, coverage, notes = [], [], []
    for t in sorted(set(keep[MODEL]) | set(keep[BASE])):
        gs, ss = {}, {}
        for m in (MODEL, BASE):
            rid = keep[m].get(t)
            gs[m] = groups.get((m, rid), s.iloc[:0])
            ss[m] = set(zip(gs[m].market, gs[m].ticker))
        sets.append(dict(anchor=close.index[t], e_run=keep[MODEL].get(t), b_run=keep[BASE].get(t),
                         e=len(ss[MODEL]), b=len(ss[BASE]), common=len(ss[MODEL] & ss[BASE]),
                         e_only=len(ss[MODEL] - ss[BASE]), b_only=len(ss[BASE] - ss[MODEL]),
                         equal=ss[MODEL] == ss[BASE]))
    coverage, credit_delay = credit_diagnostics(data, ekeep, groups)
    jump = close.pct_change(fill_method=None).abs()
    series, drop = {}, []
    def put(key, day, value):
        if value is not None:
            series.setdefault(key, {})[day] = value
    for h in (20, 10):
        for t in sorted(set(keep[MODEL]) | set(keep[BASE])):
            time_guard()
            fw = forward(close, t, h, jump)
            if fw is None:
                continue
            ret, missing, nojump, jumps, holes = fw
            day, gs, own = close.index[t], {}, {}
            for m in (MODEL, BASE):
                rid = keep[m].get(t)
                if rid is None:
                    continue
                g = groups[m, rid].copy()
                g["ret"] = ret.reindex(g.ticker).to_numpy()
                valid = g.score.notna() & g.ret.notna()
                gs[m] = g
                own[m] = measures(g)
                for kind, val in own[m].items():
                    put((h, m, "각자", kind), day, val)
                drop.append(dict(h=h, model=m, run=rid, anchor=day, total=len(g),
                                 missing_prices=int(missing.reindex(g.ticker, fill_value=True).sum()),
                                 no_jump_observation=int(nojump.reindex(g.ticker, fill_value=True).sum()),
                                 jump_cut=int(jumps.reindex(g.ticker, fill_value=False).sum()),
                                 internal_hole=int(holes.reindex(g.ticker, fill_value=True).sum()),
                                 missing_score=int(g.score.isna().sum()), valid_pairs=int(valid.sum()),
                                 excluded_pairs=int((~valid).sum()),
                                 valid_markets=sum(v is not None for k,v in own[m].items() if k.startswith("시장:"))))
            if len(gs) != 2:
                continue
            for kind in set(own[MODEL]) & set(own[BASE]):
                x, y = own[MODEL][kind], own[BASE][kind]
                if x is not None and y is not None:
                    put((h, "차이", "각자", kind), day, x-y)
            # 교집합은 같은 시장·종목이며 점수와 수익도 양쪽 유효한 쌍이다.
            eg = gs[MODEL].set_index(["market", "ticker"])
            bg = gs[BASE].set_index(["market", "ticker"])
            common = eg.index.intersection(bg.index)
            good = (eg.loc[common, "score"].notna() & bg.loc[common, "score"].notna()
                    & eg.loc[common, "ret"].notna() & bg.loc[common, "ret"].notna())
            common = common[good]
            em, bm = measures(eg.loc[common].reset_index()), measures(bg.loc[common].reset_index())
            for kind in set(em) & set(bm):
                for m, mm in ((MODEL, em), (BASE, bm)):
                    put((h, m, "교집합", kind), day, mm[kind])
                if em[kind] is not None and bm[kind] is not None:
                    put((h, "차이", "교집합", kind), day, em[kind]-bm[kind])
    run_dates = {close.index[t]: rid for t, rid in ekeep.items()}
    stats = {}
    for key, values in series.items():
        mapping = run_dates if key[1] != BASE else {close.index[t]: r for t,r in keep[BASE].items()}
        if key[1] == "차이" and len(values) < 3:
            stats[key] = {**series_stats({}), "n": len(values),
                          "first": min(values), "last": max(values),
                          "note": "확인 못 함: 선행 짝비교 최소 공통앵커 3 미만"}
        else:
            stats[key] = series_stats(values, mapping)
    for h in (20, 10):
        for mid in (MODEL, BASE, "차이"):
            for pop in ("각자", "교집합"):
                for kind in ("시장평균", "통합"):
                    stats.setdefault((h, mid, pop, kind), series_stats({}))
    for rid in ("20261006", "20261007", "20261008"):
        rows = s[(s.run_id == rid) & (s.model_id == MODEL)]
        t = anchor(rid, dates)
        state = ("run 없음; 보간·이월 안 함" if rows.empty else
                 "게이트 제외" if rid in excluded else
                 "유지" if rid in ekeep.values() else "앵커 중복/매핑 실패 제외")
        notes.append(dict(run=rid, rows=len(rows), state=state,
                          anchor=close.index[t] if t is not None else None))
    return dict(condition=condition, stats=stats, series=series, sets=sets, coverage=coverage,
                hold=any(c["below90"] for c in coverage), drop=drop, special=notes,
                credit_delay=credit_delay,
                retained=ekeep, excluded=sorted(set(s.run_id) & excluded),
                reference=reference_values(s, keep, dates, list(close.index), series))


def interpretation(result, kind, pop, direction):
    c, st = result["condition"], result["stats"]
    if not (c["anchors40"] and c["price40"]):
        return ""
    h20, h10 = st[20,MODEL,pop,kind], st[10,MODEL,pop,kind]
    formal = lambda v: (v["iid95"] is not None and v["iid95"][0]>0
                        and v["iid_bonf"][0]>0 and v[direction]>=.6)
    clauses = []
    if result["hold"]:
        clauses.append("§2 crb5<90%: 판정 보류·보고")
    if result["credit_delay"]["freshest_gt5"]["anchors"]:
        clauses.append("§2 지연>5 관측; 지속 길이 정의는 확인 못 함")
    if formal(h20) and not formal(h10):
        clauses.append("§2 h20만 형식 통과: 기움까지; h10 재현 상세 문턱 확인 못 함")
    for h in (20,10):
        d=st[h,"차이",pop,kind]
        if d["mean"] is not None and d["mean"]<=0:
            clauses.append(f"§2 h{h} sv_b−sv_a 평균 우위 없음; 승격 불가 조항 검토")
    # 사전등록의 완전한 조합표, 경계값, 짝우위 상세 문턱은 없다.
    return "; ".join(clauses+["해당 칸 없음, §11 기본값"])


def f(value):
    if value is None:
        return "확인 못 함"
    if isinstance(value, (tuple, list)):
        return "[" + ", ".join(f(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(str(k) + ": " + f(v) for k,v in value.items()) + "}"
    if isinstance(value, (float, np.floating)):
        return f"{value:.6f}"
    return str(value)


def render(data, results):
    lines=[]
    if any(r["hold"] for r in results.values()):
        lines.append("보류 검토 — crb5 커버리지 90% 미만 앵커 있음")
    if any(r["credit_delay"]["worst_gt5"]["anchors"] for r in results.values()):
        lines.append("지연 검토 — 신용 자료 5거래일 초과 지연; 지속 길이 확인 못 함")
    lines += ["sv_b 판정 숫자 / 등록 20260914 / wu_scores.wu_score / 시세 본 표만",
              "짝비교 방향: sv_b − sv_a (양수=sv_b 우위); h20 주지표·h10 별도 재현",
              "4,000회·seed 7 / Bonferroni 7 주 기준·11 감도 / 진입 t+1 종가",
              "시장별 평균 계보·통합 병기 / 방향60% 주 기준 계보·앵커 기준 병기",
              "40일 두 정의 중 하나라도 미달하면 중간 관측, 판정 칸 비움",
              "사전등록 조합표 없음: 해당 칸 없음, §11 기본값. 승격·은퇴 결정하지 않음.",
              "날짜 구간·주 블록·분모11·2000회 감도는 별도; 비교는 반올림 전 값",
              f"자료 마감={data['cutoff']}; 분모 사전등록=7 / DB distinct={data['model_count']} / 공통 감도=11",
              "DB distinct가 7과 다르면 검토 필요; 자동으로 분모를 바꾸지 않음",
              "점수 종목의 시세 본 표 존재 여부="+f(data["price_membership"]),
              f"stage1 중앙값={f(data['median_stage1'])}; 부분30={data['partial30']}; stage1 없음={data['missing_stage1']}",
              "판정30=stage1 전체기간 중앙값30% 미만 + 전트랙 이중run; stage1 없는 run은 선행 방식대로 별도 계수",
              f"이중run={data['doubles']}; 출처={data['double_by_table']}; 동결시각 해석 불가={data['invalid_frozen']}",
              "종목8쌍·점수/수익 고유값3 이상; 짝비교 최소 공통앵커3(9/06 wu 계보)",
              "수익 구간 일별 점프>0.32 제외; 내부 결측 max(skipna) 계보·결손수 별도",
              "crb5=본 표 close 날짜 격자 rolling5/min1. 당일 원천 포함·미래값 미사용·이월 없음",
              "현재 원천표의 재구성 커버리지·자료일 지연이다. 동결 당시 수신/적재 지연은 확인 못 함",
              "지연 두 정의 병기: 유니버스 중 가장 최근 비NULL 날짜(최소 지연) / 종목별 가장 오래된 날짜(최대 지연)",
              "과거 비NULL 전무 종목=확인 못 함. NULL을 지연0으로 세지 않음. 지속 임계 길이는 정하지 않음"]
    for gate,r in results.items():
        c=r["condition"]; eligible=c["anchors40"] and c["price40"]
        lines += [f"\n[{gate}]", "조건="+f(c),
                  "상태="+("판정 숫자 확인 가능" if eligible else "중간 관측"),
                  "제외 run="+f(r["excluded"]),
                  "종목 집합 먼저: 앵커 | sv_b run | sv_a run | sv_b수 | sv_a수 | 공통 | sv_b만 | sv_a만 | 동일"]
        for row in r["sets"]:
            lines.append(" | ".join(f(row[k]) for k in ("anchor","e_run","b_run","e","b","common","e_only","b_only","equal")))
        lines.append("crb5 날짜별: 앵커 | run | sv_b수 | 존재 | 비율 | <90%")
        for row in r["coverage"]:
            lines.append(" | ".join(f(row[k]) for k in ("anchor","run","n","present","fraction","below90")))
        lines.append("<90% 앵커 수="+str(sum(x["below90"] for x in r["coverage"])))
        lines.append("신용 지연: 날짜별 마지막 비NULL 날짜·거래일 지연·종목별 지연 분포")
        lines.extend(f(row) for row in r["credit_delay"]["daily"])
        lines.append("5일 초과와 가장 긴 연속 구간="+f({k:v for k,v in r["credit_delay"].items() if k!="daily"}))
        lines.append("연속=가격 거래일이 이웃하는 관측 앵커; run 없는 거래일/불명/비초과는 끊음; 달력일 길이 아님")
        lines.append("통계: h | 모델/차이(sv_b−sv_a) | 종목범위 | 계산범위 | n | 처음~끝 | 평균 | iid95 | 주95 | Bonf7 iid | Bonf7 주 | Bonf11 iid | Bonf11 주 | 앵커양수 | 주양수 | 주수 | iid2000 | Bonf7 2000")
        for key,v in sorted(r["stats"].items()):
            lines.append(" | ".join([*(str(k) for k in key), str(v["n"]),f"{v['first']}~{v['last']}",
                *(f(v[k]) for k in ("mean","iid95","week95","iid_bonf","week_bonf","iid_bonf11","week_bonf11","anchor_pos","week_pos","weeks","iid2000","bonf2000"))]))
            if v.get("note"): lines.append(v["note"])
            if v.get("actual_anchor_week"): lines.append("  실제 앵커 주 감도="+f(v["actual_anchor_week"]))
        lines.append("조건·판정 칸: 범위 | 집합 | 방향 | h20 95>0/Bonf7>0/방향60% | h10 동일 | 짝h20 평균>0/95>0 | 짝h10 동일 | 판정 칸")
        positive=lambda v,k: None if v[k] is None else (v[k][0]>0 if isinstance(v[k],tuple) else v[k]>0)
        for kind in ("시장평균","통합"):
            for pop in ("각자","교집합"):
                for direction in ("week_pos","anchor_pos"):
                    vals=[kind,pop,direction]
                    for h in (20,10):
                        v=r["stats"][h,MODEL,pop,kind]
                        vals.append([positive(v,"iid95"),positive(v,"iid_bonf"),None if v[direction] is None else v[direction]>=.6])
                    for h in (20,10):
                        v=r["stats"][h,"차이",pop,kind]
                        vals.append([positive(v,"mean"),positive(v,"iid95")])
                    vals.append(interpretation(r,kind,pop,direction))
                    lines.append(" | ".join(f(v) for v in vals))
        lines.append("10/06~08 run 처리="+f(r["special"]))
        lines.append("결손 각주(모델×앵커×종목, 사유 중복 가능):")
        for h in (20,10):
            for mid in (MODEL,BASE):
                rows=[x for x in r["drop"] if x["h"]==h and x["model"]==mid]
                cols=("total","missing_prices","no_jump_observation","jump_cut","internal_hole","missing_score","valid_pairs","excluded_pairs")
                lines.append(f"h{h} {mid} 완결앵커={len(rows)} "+f({k:sum(x[k] for x in rows) for k in cols}))
                lines.extend(f(row) for row in rows)
        ref=r["reference"]
        lines.append("각주 ④ 참고값 — 라벨·해석에 사용하지 않음")
        lines.append("① 완결 앵커에서 시간순 h거래일 간격: "+f(ref["completed_nonoverlap"]))
        lines.append("① 상관 유효 앵커 감도: "+f(ref["valid_nonoverlap"]))
        lines.append("② 연속 유지run 공통종목 점수순위 상관; 같은종목비율=공통/앞run; run쌍 동등가중")
        lines.append("거래일 간격>1인 연속run도 포함·별도계수. 수익 미사용. 각주95 구간은 독립성 보장 아님")
        for mid,value in ref["persistence"].items():
            lines.append(mid+": "+f(value))
    return "\n".join(lines)


def analyze(data):
    out, cached = {}, {}
    for gate, excluded in data["gates"].items():
        key = tuple(sorted(excluded))
        if key not in cached:
            cached[key] = evaluate(data, gate)
        out[gate] = cached[key]
    return out


def placebo_prepare(data):
    """본 표·판정30 전용. 두 모델 합집합의 시장별 공통 이름표 공간을 만든다."""
    time_guard()
    s, close, dates = data["scores"], data["close"], data["dates"]
    keep = {m: choose_runs(s[s.model_id == m], dates, data["gates"]["판정30"])
            for m in (MODEL, BASE)}
    positions = sorted(set(keep[MODEL]) | set(keep[BASE]))
    jump = close.pct_change(fill_method=None).abs()
    returns = {}
    for h in (20, 10):
        returns[h] = pd.DataFrame(
            [forward(close,t,h,jump)[0] if t+LAG+h<len(close) else
             pd.Series(np.nan,index=close.columns) for t in positions],
            index=positions, columns=close.columns)
    panels = []
    for market, g in s.groupby("market", sort=True):
        # 판정 창의 모든 출현을 포함: 미완결·게이트 제외 run도 이름표 모집단에는 남긴다.
        tickers = sorted(g.ticker.unique())
        scores = {}
        for m in (MODEL,BASE):
            z = g[g.model_id == m].pivot(index="run_id", columns="ticker", values="score")
            z = z.reindex(index=[keep[m].get(t, "") for t in positions], columns=tickers)
            scores[m] = z.to_numpy(dtype=float)
        caps = data["first_caps"].reindex(tickers)
        bins = np.full(len(tickers), 5, dtype=int)
        ok = caps.notna().to_numpy()
        bins[ok] = np.clip(np.ceil(caps[ok].rank(method="average",pct=True).to_numpy()*5).astype(int)-1,0,4)
        panels.append(dict(market=market,tickers=tickers,scores=scores,cap_bins=bins,
                           cap_known=int(ok.sum()),
                           returns={h:r.reindex(columns=tickers).to_numpy(float) for h,r in returns.items()}))
    return dict(panels=panels, positions=positions,
                days=[close.index[t] for t in positions],
                run_dates=[keep[MODEL].get(t,keep[BASE].get(t)) for t in positions], keep=keep)


def placebo_correlations(x, y):
    """행별 pairwise 결측 제거 후 평균 동점 재순위. 주 계산의 8쌍/3고유값 상속."""
    mask = ~np.isnan(x) & ~np.isnan(y)
    xx, yy = np.where(mask,x,np.nan), np.where(mask,y,np.nan)
    n = mask.sum(axis=1)
    def centered(a):
        rank = pd.DataFrame(a).rank(axis=1,method="average").to_numpy()
        return np.where(mask,rank-(n[:,None]+1)/2,0.)
    rx, ry = centered(xx), centered(yy)
    den = np.sqrt(np.sum(rx*rx,axis=1)*np.sum(ry*ry,axis=1))
    corr = np.divide(np.sum(rx*ry,axis=1),den,out=np.full(len(n),np.nan),where=den>0)
    def unique_count(a):
        a = np.sort(a,axis=1)
        return (~np.isnan(a[:,0])).astype(int) + ((a[:,1:]!=a[:,:-1]) & ~np.isnan(a[:,1:])).sum(axis=1)
    unique_x, unique_y = unique_count(xx), unique_count(yy)
    corr[(n<MIN_GROUP)|(unique_x<3)|(unique_y<3)] = np.nan
    return corr


def placebo_batch(prepared, maps):
    """maps[시장][시도,source]=recipient. 같은 표를 전 날짜·두 모델에 함께 쓴다."""
    batch = len(maps[0]) if maps else 1
    nt = len(prepared["positions"])
    output = {}
    for h in (20,10):
        sums = np.zeros((4,batch,nt))
        counts = np.zeros((4,batch,nt),dtype=int)
        for panel, mapping in zip(prepared["panels"], maps):
            width = len(panel["tickers"])
            # 원 점수 열은 source, 수익 열만 recipient로 연결한다.
            ret = panel["returns"][h][:,mapping].transpose(1,0,2).reshape(-1,width)
            e = np.broadcast_to(panel["scores"][MODEL],(batch,nt,width)).reshape(-1,width)
            b = np.broadcast_to(panel["scores"][BASE],(batch,nt,width)).reshape(-1,width)
            common = ~np.isnan(e) & ~np.isnan(b)
            for slot, score in enumerate((e,b,np.where(common,e,np.nan),np.where(common,b,np.nan))):
                ic = placebo_correlations(score,ret).reshape(batch,nt)
                good = ~np.isnan(ic)
                sums[slot] += np.where(good,ic,0.)
                counts[slot] += good
        avg = np.divide(sums,counts,out=np.full_like(sums,np.nan),where=counts>0)
        output[h,MODEL,"각자"] = avg[0]
        output[h,BASE,"각자"] = avg[1]
        output[h,"차이","각자"] = avg[0]-avg[1]
        output[h,"차이","교집합"] = avg[2]-avg[3]
    return output


def placebo_draws(prepared, method, reps=PLACEBO_REPS, seed=PLACEBO_SEED, progress=None):
    rng = np.random.default_rng(seed)
    output = {}
    fixed, population, strata = 0, sum(len(p["tickers"]) for p in prepared["panels"]), []
    groups = []
    for p in prepared["panels"]:
        labels = p["cap_bins"] if method=="시총5분위" else np.zeros(len(p["tickers"]),int)
        ids = [np.flatnonzero(labels==k) for k in np.unique(labels)]
        groups.append(ids)
        strata.append(dict(market=p["market"],pool=len(labels),cap_known=p["cap_known"],
                           cap_missing=len(labels)-p["cap_known"],sizes=[len(i) for i in ids],
                           singleton_tickers=sum(len(i)==1 for i in ids)))
    for start in range(0,reps,32):
        time_guard()
        stop = min(reps,start+32)
        maps = []
        for panel, group in zip(prepared["panels"],groups):
            n = len(panel["tickers"])
            mapping = np.tile(np.arange(n),(stop-start,1))
            for ids in group:
                # 일반 순열: 자기 자신으로 가는 이름표도 허용한다.
                mapping[:,ids] = rng.permuted(np.tile(ids,(stop-start,1)),axis=1)
            assert np.all(np.sort(mapping,axis=1)==np.arange(n))
            fixed += int((mapping==np.arange(n)).sum())
            maps.append(mapping)
        for key, values in placebo_batch(prepared,maps).items():
            output.setdefault(key,np.full((reps,len(prepared["positions"])),np.nan))[start:stop] = values
        if progress:
            progress(f"{method} 자리바꿈 {stop}/{reps}")
    return output,dict(strata=strata,fixed_fraction=fixed/(reps*population) if population else None)


def placebo_distribution(values, actual, minimum=1):
    n = np.sum(~np.isnan(values),axis=1)
    means = np.divide(np.nansum(values,axis=1),n,out=np.full(len(n),np.nan),where=n>=minimum)
    good = means[~np.isnan(means)]
    result = dict(attempts=len(n),valid_attempts=len(good),invalid_attempts=len(n)-len(good),
                  anchor_n_min=int(n.min()) if len(n) else 0,anchor_n_max=int(n.max()) if len(n) else 0,
                  quantiles=None,actual_mean=actual,percentile_le=None,percentile_midrank=None,
                  lower_tail=None,upper_tail=None,two_sided_tail=None,
                  lower_tail_plus1=None,upper_tail_plus1=None)
    if len(good):
        result["quantiles"] = tuple(float(x) for x in np.percentile(good,[2.5,50,97.5]))
        if actual is not None:
            below, equal, above = int((good<actual).sum()),int((good==actual).sum()),int((good>actual).sum())
            low, high = (below+equal)/len(good),(above+equal)/len(good)
            result.update(percentile_le=100*low,percentile_midrank=100*(below+.5*equal)/len(good),
                          lower_tail=low,upper_tail=high,two_sided_tail=min(1.,2*min(low,high)),
                          lower_tail_plus1=(1+below+equal)/(len(good)+1),
                          upper_tail_plus1=(1+above+equal)/(len(good)+1))
    return result


def placebo_weights(n, week_labels):
    """series_stats와 동일 seed·복원추출 순서. 재표집 가중치만 한 번 만든다."""
    def counts(picks, width):
        out = np.zeros((len(picks),width))
        np.add.at(out,(np.arange(len(picks))[:,None],picks),1)
        return out
    idx = np.random.default_rng(SEED).integers(0,n,(BOOT,n))
    iid = counts(idx,n)/n
    weeks = int(week_labels.max())+1
    picks = np.random.default_rng(SEED).integers(0,weeks,(BOOT,weeks))
    wc = counts(picks,weeks)
    sizes = np.bincount(week_labels,minlength=weeks)
    week = wc[:,week_labels]/(wc@sizes)[:,None]
    return iid,week


def placebo_rates(values, run_dates, eligible, progress=None):
    """각주용 양(+) 통계 조건 비율. 최종 채택·coverage·h10·짝우위 라벨 아님."""
    if not eligible:
        return dict(status="중간 관측: 40일 미달, 유의 비율 칸 비움",rates=None)
    total = len(values)
    flags = {k:np.zeros(total,bool) for k in ("iid95","week95","bonf7_iid","bonf7_week","bonf11_iid","bonf11_week")}
    directions = {k:np.zeros(total,bool) for k in ("앵커60%","주60%")}
    patterns, inverse = np.unique(~np.isnan(values),axis=0,return_inverse=True)
    all_weeks = pd.to_datetime(run_dates,format="%Y%m%d").to_period("W")
    for group, mask in enumerate(patterns):
        rows = np.flatnonzero(inverse==group)
        n = int(mask.sum())
        if not n:
            continue
        labs = pd.factorize(all_weeks[mask],sort=True)[0]
        v = values[np.ix_(rows,mask)]
        directions["앵커60%"][rows] = (v>0).mean(axis=1)>=.6
        directions["주60%"][rows] = np.column_stack([v[:,labs==w].mean(axis=1)>0
                                                    for w in np.unique(labs)]).mean(axis=1)>=.6
        banks = placebo_weights(n,labs)
        for start in range(0,len(rows),128):
            time_guard()
            ids = rows[start:start+128]
            for bank,name in zip(banks,("iid","week")):
                samples = np.einsum("ij,kj->ik",v[start:start+128],bank,optimize=False)
                lower = np.percentile(samples,[2.5,2.5/DENOM,2.5/11],axis=1)
                flags[name+"95"][ids] = lower[0]>0
                flags["bonf7_"+name][ids] = lower[1]>0
                flags["bonf11_"+name][ids] = lower[2]>0
            if progress:
                progress(f"구간 검사 패턴 {group+1}/{len(patterns)}, 시도 {min(start+128,len(rows))}/{len(rows)}")
    flags["both95"] = flags["iid95"] & flags["week95"]
    flags["bonf7_both"] = flags["bonf7_iid"] & flags["bonf7_week"]
    flags["bonf11_both"] = flags["bonf11_iid"] & flags["bonf11_week"]
    return dict(status="각주용 통계 조건",attempts=total,
                no_ic_attempts=int(np.isnan(values).all(axis=1).sum()),
                rates={d:{k:dict(passes=int((v&direction).sum()),fraction=float((v&direction).mean()))
                          for k,v in flags.items()} for d,direction in directions.items()})


def placebo_reference(data, main_result, reps=PLACEBO_REPS, seed=PLACEBO_SEED,
                      methods=("시장내","시총5분위"), progress=None, include_rates=True):
    prepared = placebo_prepare(data)
    result = dict(seed=seed,repetitions=reps,bootstrap=BOOT,bootstrap_seed=SEED,
                  source="본 표·시장 평균·판정30만",methods={})
    identity = [np.arange(len(p["tickers"]))[None,:] for p in prepared["panels"]]
    observed = placebo_batch(prepared,identity)
    # 새 batch 구현과 기존 주 계산을 같은 자료·같은 앵커에서 연결 검증한다.
    for key, arr in observed.items():
        h,m,pop = key
        target = main_result["series"].get((h,m,pop,"시장평균"),{})
        expected = np.array([target.get(d,np.nan) for d in prepared["days"]])
        if not np.allclose(arr[0],expected,rtol=0,atol=1e-12,equal_nan=True):
            raise ValueError("확인 못 함: 자리바꿈 identity와 주 계산 불일치 " + str(key))
    for method in methods:
        draws, metadata = placebo_draws(prepared,method,reps,seed,progress)
        summaries = {}
        for key, values in draws.items():
            h,m,pop = key
            actual_stat = main_result["stats"][h,m,pop,"시장평균"]
            actual = actual_stat["mean"]
            summaries[key] = placebo_distribution(values,actual,3 if m=="차이" else 1)
            summaries[key].update(actual_anchor_n=actual_stat["n"],actual_iid95=actual_stat["iid95"])
        c = main_result["condition"]
        rates = placebo_rates(draws[20,MODEL,"각자"],prepared["run_dates"],
                              c["anchors40"] and c["price40"],progress) if include_rates else None
        result["methods"][method] = dict(distributions=summaries,rates=rates,**metadata)
    return result


def render_placebo(reference):
    lines = ["\n각주 ④ 참고값 ③ 자리바꿈 백분위 — 라벨·해석에 사용하지 않음",
             f"{reference['source']} / {reference['repetitions']}회 seed={reference['seed']}",
             f"각 시도 구간 {reference['bootstrap']}회 seed={reference['bootstrap_seed']}",
             "시장별 두 모델 출현 합집합 안 1:1 순열; 출현/결측을 포함한 전체 점수 흐름 이동; 두 모델에 같은 순열",
             "시총=창 안 첫 양수 close×shares; 시장별 평균 동점 백분위 5층, 시총 결측은 별도 6번째 층",
             "quantiles 순서=뒤섞은 평균의 2.5·50·97.5 백분위; actual_anchor_n/actual_iid95는 주 계산의 표본수/구간",
             "백분위: <= 경험누적(0~100), 동점 중간값도 병기. 꼬리 비율은 동점 포함; +1 보정 별도",
             "음수 실제값은 lower_tail을 읽음. 양측 꼬리=min(1,2*min(아래,위)). 0회 초과는 확률0의 증명 아님.",
             "유의 비율: 40일 조건 + 구간 하단>0 + 방향60%(앵커/주 병기). 최종 채택 라벨 재현 아님.",
             "비율 분모=전체 시도; 상관 없는 시도는 통과하지 않으며 따로 셈. 분포 백분위는 유효 시도만."]
    for method,row in reference["methods"].items():
        lines += ["["+method+"]", "층="+f(row["strata"]),"이름표 고정 비율="+f(row["fixed_fraction"])]
        for key,value in row["distributions"].items():
            if key[1]==BASE or (key[0]==10 and key[1]==MODEL):
                continue
            lines.append(" | ".join(map(str,key)) + " | " + f(value))
        lines.append("h20 sv_b 유의 통계 조건 비율="+f(row["rates"]))
    return "\n".join(lines)


def placebo_progress():
    start, last = time.monotonic(), [0.]
    def report(message):
        now = time.monotonic()
        if now-last[0]>=5:
            print(f"[자리바꿈 {now-start:.0f}초] {message}",file=sys.stderr,flush=True)
            last[0]=now
    return report


def fixture(case="perfect", count=45):
    """모든 값은 직접 만든 자료. DB는 둘 다 :memory:뿐."""
    hc, pc = sqlite3.connect(":memory:"), sqlite3.connect(":memory:")
    hc.executescript("""
      CREATE TABLE wu_scores(run_id TEXT,market TEXT,ticker TEXT,model_id TEXT,
        wu_score REAL,frozen_at TEXT,spec_hash TEXT);
      CREATE TABLE stage1_oversold(run_id TEXT,ticker TEXT);

      CREATE TABLE v3_scores(run_id TEXT,model_id TEXT,frozen_at TEXT);
      CREATE TABLE lowvol_scores(run_id TEXT,model_id TEXT,frozen_at TEXT);
    """)
    pc.execute("CREATE TABLE daily_ohlcv(ticker TEXT,date TEXT,close REAL,volume REAL,shares REAL)")
    pc.execute("CREATE TABLE short_flows(ticker TEXT,date TEXT,credit_bal_rate REAL)")
    dates = pd.bdate_range(REG, periods=max(count+25,75)).strftime("%Y%m%d").tolist()
    # 보통 8+24종목; 시장 부호 시험은 16+16으로 정확한 시장평균 0을 구성.
    split = 16 if case == "market" else 8
    specs = [(f"{i:06}", "kospi" if i<split else "kosdaq", i) for i in range(32)]
    prices = [(tick, d, 100*(1+(i+1)*.0001)**t,
               1000., 100000.)
              for t,d in enumerate(dates) for tick,_,i in specs]
    pc.executemany("INSERT INTO daily_ohlcv VALUES(?,?,?,?,?)", prices)
    pc.executemany("INSERT INTO short_flows VALUES(?,?,?)",
                   [(tick,d,None if case=="coverage" and i%2==0 else 1.+i)
                    for d in dates for tick,_,i in specs])
    run_dates = dates[:count]
    if case=="cluster":
        run_dates = pd.bdate_range("20260914",periods=5).strftime("%Y%m%d").tolist()+["20260921","20260928"]
    if case=="null":
        count = 60
        run_dates = dates[:count]
    rng = np.random.default_rng(7123)
    last = None
    for j,d in enumerate(run_dates):
        hc.executemany("INSERT INTO stage1_oversold VALUES(?,?)", [(d,t) for t,_,_ in specs])
        if case=="null":
            if j%2==0:
                last = rng.permutation(32)
            scores = last if j%2==0 else 31-last
        else:
            scores = np.arange(32,dtype=float)
        for tick,m,i in specs:
            score = float(scores[i])
            if case=="market" and m=="kosdaq":
                score = 47-score
            if case=="cluster" and j>=5:
                score = -score
            if case=="flip" and j%2:
                score = -score
            for model in (MODEL,BASE):
                # equal 검증은 sv_a와 완전히 동일. 나머지도 동일해 각자/교집합 경로 검증.
                hc.execute("INSERT INTO wu_scores VALUES(?,?,?,?,?,?,?)",
                           (d,m,tick,model,score,d[:4]+"-"+d[4:6]+"-"+d[6:]+"T21:00:00+09:00","fake"))
    hc.commit(); pc.commit()
    return hc,pc


def _self_test():
    rows = []
    results = {}
    for case in ("perfect","null","market","equal","cluster","coverage","39"):
        print(f"[가짜 검증] {case}", file=sys.stderr, flush=True)
        hc,pc = fixture(case, 39 if case=="39" else 60 if case=="null" else 45)
        try:
            data=read_inputs(hc,pc)
            rs=analyze(data)
            r=rs["판정30"]
            results[case]=r
            a=r["stats"][20,MODEL,"각자","시장평균"]
            b=r["stats"][20,MODEL,"각자","통합"]
            if case=="perfect":
                assert all(abs(r["stats"][h,MODEL,"각자",k]["mean"]-1)<1e-12
                           for h in (20,10) for k in ("시장평균","통합"))
            elif case=="null":
                assert abs(a["mean"])<.08 and a["iid95"][0]<0<a["iid95"][1]
                assert abs(b["mean"])<.08 and b["iid95"][0]<0<b["iid95"][1]
            elif case=="market":
                assert abs(a["mean"])<1e-12 and abs(a["mean"]-b["mean"])>.1
            elif case=="equal":
                for h in (20,10):
                    for pop in ("각자","교집합"):
                        for k in ("시장평균","통합"):
                            v=r["stats"][h,"차이",pop,k]
                            assert v["mean"]==0 and v["iid95"]==(0.,0.) and v["week95"]==(0.,0.)
            elif case=="cluster":
                assert abs(a["anchor_pos"]-5/7)<1e-12 and abs(a["week_pos"]-1/3)<1e-12
            elif case=="coverage":
                assert r["hold"] and all(x["fraction"]==.5 for x in r["coverage"])
                assert render(data,rs).startswith("보류 검토")

            else:
                assert r["condition"]["anchors"]==39
                assert interpretation(r,"시장평균","각자","anchor_pos")==""
                assert "상태=중간 관측" in render(data,rs)
            rows.append([case,"PASS",a["n"],f(a["mean"]),f(a["iid95"]),f(b["mean"]),f(a["anchor_pos"]),f(a["week_pos"]),r["hold"]])
        finally:
            hc.close(); pc.close()
    print("가짜 메모리 DB 전용: 실제 DB 접근 차단")
    print("case | 결과 | h20 n | 시장평균 | iid95 | 통합평균 | 앵커양수 | 주양수 | 보류")
    for row in rows:
        print(" | ".join(map(str,row)))
    print("[가짜 검증] 신용·계보·참고값", file=sys.stderr, flush=True)
    credit_tests()
    placebo_tests()



def credit_tests():
    import copy
    for case, expected in (("perfect",1.),("flip",-1.)):
        hc,pc=fixture(case)
        try:
            data=read_inputs(hc,pc);r=analyze(data)["판정30"]
            for m in (MODEL,BASE):
                ref=r["reference"]
                assert ref["completed_nonoverlap"][20,m]["n"]==3
                assert ref["completed_nonoverlap"][10,m]["n"]==5
                p=ref["persistence"][m]
                assert abs(p["rank_mean"]-expected)<1e-12 and p["same_ticker_mean"]==1
                assert p["run_pairs"]==44
            # 참고값을 지워도 해석은 동일. 가격을 건드리지 않고 지속성을 별도 계산.
            untouched=copy.deepcopy(r)
            untouched["reference"]={}
            for direction in ("week_pos","anchor_pos"):
                assert interpretation(r,"시장평균","각자",direction)==interpretation(untouched,"시장평균","각자",direction)
        finally: hc.close();pc.close()
    hc,pc=fixture()
    try:
        data=read_inputs(hc,pc);days=list(data["close"].index)
        before=analyze(data)["판정30"]
        pc.execute("UPDATE short_flows SET credit_bal_rate=NULL WHERE date>?",(days[0],))
        stale_data=read_inputs(hc,pc);stale=analyze(stale_data)["판정30"]
        lag=stale["credit_delay"]
        assert lag["daily"][6]["freshest_lag"]==6 and lag["daily"][6]["worst_lag"]==6
        assert lag["freshest_gt5"]["anchors"]==39 and lag["freshest_gt5"]["longest_trading_days"]==39
        assert lag["freshest_gt5"]["longest_ranges"]==[dict(start=days[6],end=days[44],anchors=39)]
        assert "지연 검토" in render(stale_data,{"판정30":stale})
        assert all(x["fraction"]==0 for x in stale["coverage"][5:])
        assert all(x["fraction"]==1 for x in stale["coverage"][:5])
        # 신용 참고값 변화는 수익/상관/짝비교를 바꾸지 않는다.
        assert before["stats"]==stale["stats"] and before["series"]==stale["series"]
        pc.execute("UPDATE short_flows SET credit_bal_rate=9 WHERE date=?",(days[6],))
        rolling=read_inputs(hc,pc)["crb5"]
        assert rolling.loc[days[4],"000000"]==1
        assert pd.isna(rolling.loc[days[5],"000000"])
        assert rolling.loc[days[6],"000000"]==9
        cut=read_inputs(hc,pc,days[5])
        assert pd.isna(cut["crb5"].loc[days[5],"000000"]) # 미래 행 읽기 금지
        # 가장 신선한 종목과 낡은 종목 정의를 나란히 유지.
        pc.execute("UPDATE short_flows SET credit_bal_rate=1 WHERE ticker='000000'")
        mixed=analyze(read_inputs(hc,pc))["판정30"]["credit_delay"]
        assert mixed["daily"][12]["freshest_lag"]==0 and mixed["daily"][12]["worst_lag"]==6
        assert mixed["freshest_gt5"]["anchors"]==0 and mixed["worst_gt5"]["anchors"]>0
        pc.execute("UPDATE short_flows SET credit_bal_rate=NULL WHERE ticker='000001'")
        unknown=analyze(read_inputs(hc,pc))["판정30"]["credit_delay"]
        assert all(row["unknown_tickers"]==1 for row in unknown["daily"])
        hc.execute("DELETE FROM wu_scores WHERE run_id=?",(days[20],))
        gap=analyze(read_inputs(hc,pc))["판정30"]["credit_delay"]["worst_gt5"]
        assert len(gap["ranges"])>=2
        # 본표 없는 종목 계수 및 수익 결손.
        pc.execute("DELETE FROM daily_ohlcv WHERE ticker='000031'")
        missing=read_inputs(hc,pc)
        assert missing["price_membership"][MODEL]["missing_tickers"]==["000031"]
        assert missing["price_membership"][MODEL]["missing_observations"]==44
        r=analyze(missing)["판정30"]
        assert sum(x["missing_prices"] for x in r["drop"] if x["model"]==MODEL and x["h"]==20)==44
    finally: hc.close();pc.close()
    # wu 계보 짝비교 최소3, 방향 부호, 각자/교집합 및 게이트·중복앵커.
    hc,pc=fixture(count=3)
    try:
        hc.execute("UPDATE wu_scores SET wu_score=-wu_score WHERE model_id=?",(BASE,))
        r=analyze(read_inputs(hc,pc))["판정30"]
        for h in (20,10):
            for pop in ("각자","교집합"):
                for kind in ("시장평균","통합"):
                    assert abs(r["stats"][h,"차이",pop,kind]["mean"]-2)<1e-12
        hc.execute("DELETE FROM wu_scores WHERE run_id=(SELECT MAX(run_id) FROM wu_scores)")
        r=analyze(read_inputs(hc,pc))["판정30"]
        assert r["stats"][20,"차이","각자","시장평균"]["mean"] is None
    finally: hc.close();pc.close()
    hc,pc=fixture()
    try:
        days=list(read_inputs(hc,pc)["close"].index)
        hc.execute("DELETE FROM stage1_oversold WHERE run_id=? AND ticker>='000008'",(days[1],))
        hc.execute("UPDATE wu_scores SET frozen_at=? WHERE run_id=? AND ticker='000031'",
                   (days[2][:4]+"-"+days[2][4:6]+"-"+days[2][6:]+"T22:01:00+09:00",days[2]))
        hc.execute("DELETE FROM wu_scores WHERE model_id=? AND ticker='000031'",(BASE,))
        data=read_inputs(hc,pc);r=analyze(data)["판정30"]
        assert days[1] in data["gates"]["판정30"] and days[2] in data["doubles"]
        assert len(r["excluded"])==2 and all(x["e_only"]==1 for x in r["sets"])
        sample=pd.DataFrame(dict(run_id=["20260918","20260919","20260920","20260921"]))
        assert choose_runs(sample,{"20260918":0,"20260921":1},set())=={0:"20260918",1:"20260921"}
        early=analyze(read_inputs(hc,pc,days[10]))["판정30"]
        assert early["stats"][20,MODEL,"각자","시장평균"]["n"]==0
        assert interpretation(early,"시장평균","각자","week_pos")==""
        flat=pd.DataFrame(dict(score=range(8),ret=[1.]*8))
        assert rank_ic(flat) is None and rank_ic(flat.iloc[:7]) is None
        px=pd.DataFrame(dict(x=[100.,100.,150.,151.]))
        fw=forward(px,0,2,px.pct_change(fill_method=None).abs())
        assert fw[0].isna().all() and fw[3].all()
    finally: hc.close();pc.close()
    values={"20260914":.4,"20260915":.1,"20260916":-.2,"20260921":-.8,"20260928":.3}
    st=series_stats(values);arr=np.array(list(values.values()))
    rng=np.random.default_rng(7)
    iid=np.array([rng.choice(arr,len(arr)).mean() for _ in range(4000)])
    blocks=[arr[:3],arr[3:4],arr[4:]]
    rng=np.random.default_rng(7)
    week=np.array([np.concatenate([blocks[i] for i in rng.integers(0,3,3)]).mean() for _ in range(4000)])
    for sample,key,bf7,bf11 in ((iid,"iid95","iid_bonf","iid_bonf11"),(week,"week95","week_bonf","week_bonf11")):
        for name,q in ((key,[2.5,97.5]),(bf7,[2.5/7,100-2.5/7]),(bf11,[2.5/11,100-2.5/11])):
            assert np.allclose(st[name],np.percentile(sample,q),rtol=0,atol=1e-15)
    # 원시 .6 비교: 표시에서 같아도 조건은 다르다.
    assert f(.599999999)==f(.600000001) and (.599999999>=.6) is False and (.600000001>=.6) is True
    print("신용 PASS: 6거래일 지연·초과39앵커/최장39, rolling5/min1·미래미사용·전무NULL·최신/최장 병기·연속구간 끊김")
    print("참고값 PASS: 완결45 h20 비겹침3/h10=5; 두 모델 지속성1/-1·같은종목1 (44run쌍)")
    print("추가 PASS: 신용 전후 주통계 불변·짝방향+2/최소3·종목차이·본표 결손·부분/이중run·중복앵커·점프·구간7/11·반올림 전 비교")


def placebo_tests():
    import copy
    hc,pc=fixture()
    try:
        # 시총 층을 실제로 나누되 수익/점수는 기존 정답 자료 유지.
        pc.execute("UPDATE daily_ohlcv SET shares=100000*(CAST(ticker AS INTEGER)+1)")
        data=read_inputs(hc,pc)
        main=analyze(data)["판정30"]
        progress=placebo_progress()
        first=placebo_reference(data,main,progress=progress)
        second=placebo_reference(data,main,progress=progress)
        assert first==second
        for method, row in first["methods"].items():
            q=row["distributions"][20,MODEL,"각자"]
            assert q["valid_attempts"]==2000 and q["percentile_le"]==100
            for h in (20,10):
                for pop in ("각자","교집합"):
                    assert row["distributions"][h,"차이",pop]["quantiles"]==(0.,0.,0.)
                    assert row["distributions"][h,"차이",pop]["percentile_midrank"]==50.
        prepared=placebo_prepare(data)
        draws,meta=placebo_draws(prepared,"시장내",progress=progress)
        for h in (20,10):
            for pop in ("각자","교집합"):
                assert np.all(draws[h,"차이",pop]==0)
        # 미리 만든 순열은 두 시장 각각 Spearman 정확히0. 일별로 동일한 가짜 점수.
        zero_perms={8:[4,6,0,5,3,2,1,7],
                    24:[18,2,1,21,13,15,23,22,7,5,3,19,0,9,11,8,6,14,12,20,4,16,10,17]}
        for p in prepared["panels"]:
            for source_index,tick in enumerate(p["tickers"]):
                hc.execute("UPDATE wu_scores SET wu_score=? WHERE market=? AND ticker=?",
                           (zero_perms[len(p["tickers"])][source_index],p["market"],tick))
        zero_data=read_inputs(hc,pc)
        zero_main=analyze(zero_data)["판정30"]
        assert abs(zero_main["stats"][20,MODEL,"각자","시장평균"]["mean"])<1e-14
        zero=placebo_reference(zero_data,zero_main,methods=("시장내",),progress=progress)
        center=zero["methods"]["시장내"]["distributions"][20,MODEL,"각자"]["percentile_le"]
        assert 40<=center<=60
        # seed만 바꾸어 같은 관측값을 재평가하면 위치가 안정적이어야 한다.
        alternate=placebo_reference(zero_data,zero_main,seed=PLACEBO_SEED+1,
                                    methods=("시장내",),include_rates=False,progress=progress)
        other_center=alternate["methods"]["시장내"]["distributions"][20,MODEL,"각자"]["percentile_le"]
        assert abs(other_center-center)<5
        # 고르게 퍼져야 하는 것은 독립 가짜 '관측 점수'를 새로 뽑았을 때의 위치다.
        # 40개의 사전 고정 생성 seed. 동일 순위 멀티셋이라 공유 null 2000회를 사용 가능.
        percentiles=[]
        for seed in range(1000,1040):
            rng=np.random.default_rng(seed)
            maps=[rng.permutation(len(p["tickers"]))[None,:] for p in prepared["panels"]]
            actual=float(np.mean(placebo_batch(prepared,maps)[20,MODEL,"각자"][0]))
            percentiles.append(placebo_distribution(draws[20,MODEL,"각자"],actual)["percentile_le"])
        bins=np.histogram(percentiles,bins=[0,20,40,60,80,100])[0]
        assert 35<=np.mean(percentiles)<=65 and np.all(bins>0)
        assert min(percentiles)<15 and max(percentiles)>85
        # 음수 아래 꼬리와 동점 규약.
        negative=placebo_distribution(draws[20,MODEL,"각자"],-1.)
        assert negative["lower_tail"]==0 and negative["upper_tail"]==1
        # 시총 결측은6번째층, 이후 값 대신 첫 유효 close*shares를 사용.
        pc.execute("UPDATE daily_ohlcv SET shares=NULL WHERE ticker='000000'")
        pc.execute("UPDATE daily_ohlcv SET shares=0 WHERE ticker='000001' AND date=?",(REG,))
        capped=read_inputs(hc,pc)
        cp=placebo_prepare(capped)
        for panel in cp["panels"]:
            if "000000" in panel["tickers"]:
                assert panel["cap_bins"][panel["tickers"].index("000000")]==5
        raw=pc.execute("SELECT close*shares FROM daily_ohlcv WHERE ticker='000001' AND shares>0 ORDER BY date LIMIT 1").fetchone()[0]
        assert capped["first_caps"].loc["000001"]==raw
        # 층별 제한·전체 흐름·희소 종목·서로 다른 유니버스와 scalar 주 계산 대조.
        sparse=copy.deepcopy(prepared)
        for panel in sparse["panels"]:
            panel["scores"][MODEL][1,0]=np.nan
            panel["scores"][BASE][2,1]=np.nan
            panel["returns"][20][3,2]=np.nan
        rng=np.random.default_rng(9)
        maps=[rng.permutation(len(p["tickers"]))[None,:] for p in sparse["panels"]]
        batched=placebo_batch(sparse,maps)
        for h in (20,10):
            for t in range(len(sparse["positions"])):
                gm={m:[] for m in (MODEL,BASE)}
                cm={m:[] for m in (MODEL,BASE)}
                for panel,mapping in zip(sparse["panels"],maps):
                    common=(~np.isnan(panel["scores"][MODEL][t]) & ~np.isnan(panel["scores"][BASE][t]))
                    for m in (MODEL,BASE):
                        g=pd.DataFrame(dict(score=panel["scores"][m][t],ret=panel["returns"][h][t,mapping[0]]))
                        v=rank_ic(g); w=rank_ic(g[common])
                        if v is not None: gm[m].append(v)
                        if w is not None: cm[m].append(w)
                means={m:np.mean(gm[m]) if gm[m] else np.nan for m in gm}
                inter={m:np.mean(cm[m]) if cm[m] else np.nan for m in cm}
                for key,expected in (((h,MODEL,"각자"),means[MODEL]),((h,BASE,"각자"),means[BASE]),
                                     ((h,"차이","각자"),means[MODEL]-means[BASE]),
                                     ((h,"차이","교집합"),inter[MODEL]-inter[BASE])):
                    assert np.allclose(batched[key][0,t],expected,rtol=0,atol=1e-12,equal_nan=True)
        # 구간 재표집 가중치가 기존 함수와 같은 결과인지 결측 패턴도 대조.
        days=["20260907","20260908","20260909","20260914","20260921"]
        values=np.array([[.4,.1,-.2,-.8,.3],[.2,np.nan,.1,.3,.4],[-.2,-.4,np.nan,-.1,-.3]])
        rates=placebo_rates(values,days,True)
        for direction,col in (("앵커60%","anchor_pos"),("주60%","week_pos")):
            checks={k:0 for k in rates["rates"][direction]}
            for row in values:
                st=series_stats(dict(zip(days,row)))
                passed=st[col]>=.6
                flags={"iid95":st["iid95"][0]>0,"week95":st["week95"][0]>0,
                       "bonf7_iid":st["iid_bonf"][0]>0,"bonf7_week":st["week_bonf"][0]>0,
                       "bonf11_iid":st["iid_bonf11"][0]>0,"bonf11_week":st["week_bonf11"][0]>0}
                flags["both95"]=flags["iid95"] and flags["week95"]
                flags["bonf7_both"]=flags["bonf7_iid"] and flags["bonf7_week"]
                flags["bonf11_both"]=flags["bonf11_iid"] and flags["bonf11_week"]
                for k,v in flags.items(): checks[k]+=int(passed and v)
            assert checks=={k:v["passes"] for k,v in rates["rates"][direction].items()}
        st=series_stats(dict(zip(days,values[0])))
        labs=pd.factorize(pd.to_datetime(days).to_period("W"),sort=True)[0]
        for bank,ci_key,bf_key in zip(placebo_weights(5,labs),("iid95","week95"),("iid_bonf","week_bonf")):
            sample=bank@values[0]
            assert np.allclose(np.percentile(sample,[2.5,97.5]),st[ci_key],atol=1e-15,rtol=0)
            assert np.allclose(np.percentile(sample,[2.5/DENOM,100-2.5/DENOM]),st[bf_key],atol=1e-15,rtol=0)
        assert placebo_rates(values,days,False)["rates"] is None
        assert "라벨·해석에 사용하지 않음" in render_placebo(first)
        print("자리바꿈 PASS: 2000회·seed20261012, 완전일치 백분위100, 동일모델 짝차이 h20/h10 전부0, 동일seed 재실행 일치")
        print(f"자리바꿈 PASS: 상관0 정답의 백분위={center:.3f}, 다른 순열seed={other_center:.3f}; 가짜점수 생성40seed 백분위평균={np.mean(percentiles):.3f}, 5구간 빈도={bins.tolist()}")
        print("자리바꿈 PASS: 음수꼬리·시총 첫유효/결측층·희소 종목 scalar 대조·구간/방향 규약·40미만 비율비움")
    finally:
        hc.close();pc.close()


def self_test():
    original = sqlite3.connect
    def memory_only(database, *args, **kwargs):
        if database != ":memory:":
            raise AssertionError("눈가림 위반: self-test에서 파일 DB 접근 차단")
        return original(database, *args, **kwargs)
    sqlite3.connect = memory_only
    try:
        _self_test()
    finally:
        sqlite3.connect = original


def main():
    time_guard()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--real",action="store_true",help="실제 성과 계산을 명시적으로 허용(판정 날만)")
    mode.add_argument("--schema",action="store_true",help="실제 열 이름만 확인; 점수/시세 읽기 없음")
    mode.add_argument("--self-test",action="store_true",help="가짜 메모리 DB 검증(기본값)")
    parser.add_argument("--history",type=Path,default=ROOT/"history.db")
    parser.add_argument("--ohlcv",type=Path,default=ROOT.parent/"dh-q7m3k-data"/"ohlcv.db")
    parser.add_argument("--as-of",help="--real 자료 마감일 YYYYMMDD (기본: 시세 마지막 날)")
    args=parser.parse_args()
    if args.as_of and not args.real:
        parser.error("--as-of는 --real에서만 사용")
    if args.as_of:
        datetime.strptime(args.as_of,"%Y%m%d")
    if args.schema:
        with closing(ro(args.history)) as hc, closing(ro(args.ohlcv)) as pc:
            for table,cols in {**schema(hc,[t for t in NEEDED if t not in PRICE_TABLES]),
                               **schema(pc,PRICE_TABLES)}.items():
                print(table+": "+", ".join(cols))
        return
    global np,pd
    import numpy as np
    import pandas as pd
    if not args.real:
        self_test()
        return
    with closing(ro(args.history)) as hc, closing(ro(args.ohlcv)) as pc:
        data=read_inputs(hc,pc,args.as_of)
    time_guard()
    results=analyze(data)
    print(render(data,results),flush=True)
    reference=placebo_reference(data,results["판정30"],progress=placebo_progress())
    print(render_placebo(reference))

if __name__=="__main__":
    try:
        main()
    except (ValueError,sqlite3.Error) as exc:
        print(f"확인 못 함: {exc}",file=sys.stderr)
        raise SystemExit(2)
