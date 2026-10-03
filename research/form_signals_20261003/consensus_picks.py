# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/form_signals_20261003/ 에서 실행. 읽기 전용.
"""consensus_picks.py — 종목 단위 합의: 같은 날 2개 이상 모델의 상위10 에 동시에 든 종목은 하나만 고른 종목보다 나은가 (2026-10-03, 관측)

규칙(결과 보기 전 고정): 모델 = form_signals.py 와 같은 10개(대형 제외), 동결 점수 전부, 게이트·앵커 규약 동일.
  앵커마다 시장별로 각 모델 상위10 을 모아 종목별 '고른 모델 수' k 를 센다. k=1 / k=2 / k>=3 묶음의
  다음 20거래일 수익 − 같은 시장 전종목 동일가중 평균(%p). 앵커별 묶음 평균을 낸 뒤 앵커 평균, 20일 블록 CI.
  짝비교: 같은 앵커에서 (k>=2 평균 − k=1 평균).
"""
import sqlite3, sys, json
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
import leaderboard as lb, build_scoreboard as bs           # noqa: E402
from form_signals import block_ci, MODELS                   # noqa: E402

H, TOP = 20, bs.TOP


def main():
    close, mktmap = lb.load_ohlcv(); dates = list(close.index); N = len(dates)
    mk = pd.Series(mktmap).str.lower(); mk_t = {m: close.columns.intersection(mk.index[mk == m]) for m in ("kospi", "kosdaq")}
    con = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    lbj = json.loads((REPO / "docs/leaderboard.json").read_text(encoding="utf-8"))
    picks = {}   # (t, market) -> {ticker: set(models)}
    for m in lbj["models"]:
        if m["model"] not in MODELS: continue
        S = bs.load_scores(con, m); S["run_id"] = S.run_id.astype(str)
        for rid in lb.dedupe_by_anchor(S, didx, excl, reg=None):
            t = lb.anchor(rid, didx)
            if t is None or t + 1 + H >= N: continue
            g = S[S.run_id == rid].dropna(subset=["score"])
            for mkt, gm in g.groupby("market"):
                d = picks.setdefault((t, mkt), {})
                for tk in gm.nlargest(TOP, "score").ticker: d.setdefault(tk, set()).add(m["model"])
    con.close()
    rows = []
    for (t, mkt), d in sorted(picks.items()):
        nmodels = len({m for s in d.values() for m in s})
        if nmodels < 3: continue
        r = (close.iloc[t + 1 + H] / close.iloc[t + 1] - 1) * 100
        bench = r.reindex(mk_t[mkt]).dropna().mean()
        grp = {"k1": [], "k2": [], "k3+": []}
        for tk, s in d.items():
            v = r.get(tk)
            if v is None or np.isnan(v): continue
            grp["k1" if len(s) == 1 else "k2" if len(s) == 2 else "k3+"].append(v - bench)
        rows.append(dict(t=t, date=dates[t], mkt=mkt, nmodels=nmodels,
                         **{k: (np.mean(v) if v else np.nan) for k, v in grp.items()},
                         **{"n_" + k: len(v) for k, v in grp.items()}))
    df = pd.DataFrame(rows)
    by_day = df.groupby("t").agg(date=("date", "first"), k1=("k1", "mean"), k2=("k2", "mean"), k3=("k3+", "mean"),
                                 n1=("n_k1", "sum"), n2=("n_k2", "sum"), n3=("n_k3+", "sum")).sort_index()
    print(f"앵커 {len(by_day)}일({by_day.date.min()}~{by_day.date.max()}) · 독립 20일 구간 약 {len(by_day)//20} · 종목 수 평균/일: k1 {by_day.n1.mean():.0f} · k2 {by_day.n2.mean():.0f} · k3+ {by_day.n3.mean():.0f}")
    out = {}
    for k, nm in (("k1", "한 모델만"), ("k2", "두 모델"), ("k3", "세 모델 이상")):
        x = by_day[k].dropna().values
        out[k] = dict(name=nm, n_days=int(len(x)), mean=round(float(x.mean()), 2), ci=[round(v, 2) for v in block_ci(x)], pos=round(float((x > 0).mean()), 2))
        print(f"  {nm:<8} 시장보다 {x.mean():+.2f}%p [{out[k]['ci'][0]:+.2f}, {out[k]['ci'][1]:+.2f}] 양수 {out[k]['pos']:.0%} n={len(x)}일")
    both = by_day.dropna(subset=["k1", "k2"])
    d2 = (both.k2 - both.k1).values
    kk = by_day.dropna(subset=["k1", "k3"]); d3 = (kk.k3 - kk.k1).values
    out["k2_minus_k1"] = dict(mean=round(float(d2.mean()), 2), ci=[round(v, 2) for v in block_ci(d2)], pos=round(float((d2 > 0).mean()), 2), n=int(len(d2)))
    out["k3_minus_k1"] = dict(mean=round(float(d3.mean()), 2), ci=[round(v, 2) for v in block_ci(d3)], pos=round(float((d3 > 0).mean()), 2), n=int(len(d3))) if len(d3) else None
    print(f"  두 모델 − 한 모델: {d2.mean():+.2f}%p [{out['k2_minus_k1']['ci'][0]:+.2f}, {out['k2_minus_k1']['ci'][1]:+.2f}] 양수 {out['k2_minus_k1']['pos']:.0%} n={len(d2)}")
    if len(d3): print(f"  셋 이상 − 한 모델: {d3.mean():+.2f}%p [{out['k3_minus_k1']['ci'][0]:+.2f}, {out['k3_minus_k1']['ci'][1]:+.2f}] 양수 {out['k3_minus_k1']['pos']:.0%} n={len(d3)}")
    (HERE / "consensus_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
