# -*- coding: utf-8 -*-
"""
v3_backtest.py
==============
교정된 검증. 기존 compute_ic는 날짜·시장을 한꺼번에 섞는 pooled Spearman이라
시장/시점 차이가 IC를 부풀린다. 여기서는:

  * (run_id, market) 별 cross-sectional Spearman IC 를 각각 구하고
  * 그 평균/중앙값/양수비율/top-bottom 스프레드/hit rate 로 요약한다.
  * 옛 final_score 와 새 final_score_v3 를 같은 방식으로 비교한다.

forward return 은 history.db 의 일자별 종가 패널(stage1_oversold, 전 종목)에서
구한다(네트워크/parquet 불필요). 시장초과수익 = 종목수익 - 동일시장 유니버스 중앙값.

주의: 현재 히스토리는 8 거래일(주말 run 포함)뿐이라 표본이 매우 작다.
     결과는 '판정값'이 아니라 '검증 파이프라인 + 조기 진단'으로 본다.
"""
import sqlite3
import warnings
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from scipy.stats import ConstantInputWarning

warnings.filterwarnings("ignore", category=ConstantInputWarning)

import v3_rescore as v3

DB_PATH = "history.db"
HORIZONS = [1, 2, 3]      # run-step(거래일) 기준 forward
SCORES = ["final_score", "final_score_v3"]


def filter_active_runs(panel, runs, zero_threshold=0.99):
    """직전 run 대비 가격이 사실상 전부 동일한(주말/정적) run 제거."""
    keep = [runs[0]]
    for r in runs[1:]:
        ret = (panel[r] / panel[keep[-1]] - 1).dropna()
        if len(ret) and (ret.abs() < 1e-12).mean() < zero_threshold:
            keep.append(r)
    return keep


def price_panel(db_path=DB_PATH):
    con = sqlite3.connect(db_path)
    uni = pd.read_sql(
        "SELECT market, run_id, ticker, price FROM stage1_oversold", con)
    con.close()
    uni["price"] = pd.to_numeric(uni["price"], errors="coerce")
    runs = sorted(uni["run_id"].unique())
    panel = uni.pivot_table(index="ticker", columns="run_id",
                            values="price", aggfunc="last")
    tk_mkt = uni.drop_duplicates("ticker").set_index("ticker")["market"]
    return panel, runs, tk_mkt


def forward_returns(panel, runs, tk_mkt, horizons):
    """각 (run_id, ticker, h) 의 단순수익률과 시장초과수익률."""
    recs = []
    run_idx = {r: i for i, r in enumerate(runs)}
    # 시장별 유니버스 중앙값 수익률 캐시
    for r in runs:
        i = run_idx[r]
        for h in horizons:
            j = i + h
            if j >= len(runs):
                continue
            r2 = runs[j]
            ret = (panel[r2] / panel[r] - 1.0)
            tmp = pd.DataFrame({"ticker": panel.index, "ret": ret.values})
            tmp["market"] = tmp["ticker"].map(tk_mkt)
            tmp = tmp.dropna(subset=["ret"])
            # 시장별 중앙값을 빼서 시장초과수익
            med = tmp.groupby("market")["ret"].transform("median")
            tmp["exret"] = tmp["ret"] - med
            tmp["run_id"] = r
            tmp["h"] = h
            recs.append(tmp)
    return pd.concat(recs, ignore_index=True)


def build_scored_history(db_path=DB_PATH):
    """모든 run×market 을 v3로 재점수화하여 picks 테이블을 만든다."""
    allruns = v3.load_runs(db_path)
    frames = []
    for (rid, mkt), sub in allruns.groupby(["run_id", "market"]):
        rs = v3.rescore(sub, run_id=str(rid), market=str(mkt))
        frames.append(rs[["run_id", "market", "ticker", "name",
                          "final_score", "final_score_v3", "entry_score",
                          "grade", "main_candidate"]])
    return pd.concat(frames, ignore_index=True)


def cross_sectional_ic(picks, fwd, score, horizons, min_n=8):
    """(run_id, market) 별 Spearman IC 의 분포를 요약."""
    rows = []
    for h in horizons:
        f = fwd[fwd["h"] == h][["run_id", "ticker", "exret"]]
        merged = picks.merge(f, on=["run_id", "ticker"], how="inner")
        ics, ns, spreads, hitrates = [], [], [], []
        for (rid, mkt), g in merged.groupby(["run_id", "market"]):
            g = g[[score, "exret"]].dropna()
            if len(g) < min_n or g[score].nunique() < 3:
                continue
            ic = spearmanr(g[score], g["exret"]).correlation
            if np.isnan(ic):
                continue
            ics.append(ic); ns.append(len(g))
            # 상위 20% vs 하위 20% 평균 초과수익 스프레드
            q_hi = g[score].quantile(0.8); q_lo = g[score].quantile(0.2)
            hi = g[g[score] >= q_hi]["exret"].mean()
            lo = g[g[score] <= q_lo]["exret"].mean()
            spreads.append(hi - lo)
            hitrates.append((g[g[score] >= q_hi]["exret"] > 0).mean())
        if ics:
            rows.append({
                "horizon": h, "n_groups": len(ics),
                "mean_IC": round(float(np.mean(ics)), 4),
                "median_IC": round(float(np.median(ics)), 4),
                "IC>0_ratio": round(float(np.mean(np.array(ics) > 0)), 3),
                "top-bot_spread%": round(float(np.nanmean(spreads)) * 100, 3),
                "top_hit_rate": round(float(np.nanmean(hitrates)), 3),
                "avg_n": int(np.mean(ns)),
            })
    return pd.DataFrame(rows)


def main():
    panel, all_runs, tk_mkt = price_panel()
    runs = filter_active_runs(panel, all_runs)          # 정적 run 제거
    dropped = [r for r in all_runs if r not in runs]
    fwd = forward_returns(panel, runs, tk_mkt, HORIZONS)
    picks = build_scored_history()

    print("=" * 70)
    print("교정 백테스트: (run_id, market)별 cross-sectional Spearman IC")
    print(f"전체 run {len(all_runs)} → 활성 거래일 {len(runs)}  "
          f"(정적/주말 제거: {dropped})")
    print(f"picks {len(picks)} 행  |  horizon(거래일) {HORIZONS}")
    print("시장초과수익 = 종목수익 - 동일시장 유니버스 중앙값")
    print("=" * 70)

    for sc in SCORES:
        tbl = cross_sectional_ic(picks, fwd, sc, HORIZONS)
        label = "옛 점수 final_score" if sc == "final_score" else "새 점수 final_score_v3"
        print(f"\n----- {label} (전체 universe) -----")
        print(tbl.to_string(index=False) if not tbl.empty else "  유효 표본 부족")

    main_only = picks[picks["main_candidate"]]
    print("\n----- 메인후보만 (주의/위험/이중적자/밸류트랩/falling_knife 제외) -----")
    for sc in ["final_score_v3", "entry_score"]:
        tbl = cross_sectional_ic(main_only, fwd, sc, HORIZONS, min_n=6)
        tag = "final_score_v3(후보품질)" if sc == "final_score_v3" else "entry_score(진입타이밍)"
        print(f"  · {tag}")
        print(tbl.to_string(index=False) if not tbl.empty else "    유효 표본 부족")

    print(f"\n[주의] 활성 거래일 {len(runs)}개뿐이라 통계적 신뢰도는 여전히 낮음.")
    print("       매 거래일 누적될수록 위 표가 의미를 갖는다.")
    print("       또한 valuation_*.csv 가 없는 과거 회차는 value_score=0 으로 채점되어,")
    print("       해당 회차의 v3 점수는 실거래 당시 v3 와 약간 다를 수 있다(밸류 누적 시 해소).")

    # 대시보드/기록용 요약 저장
    import json
    summary = {
        "method": "cross_sectional_spearman_ic_per_run_market",
        "active_runs": runs, "dropped_runs": dropped,
        "horizons_tradingdays": HORIZONS,
        "old_final_score": cross_sectional_ic(picks, fwd, "final_score", HORIZONS).to_dict("records"),
        "new_final_score_v3": cross_sectional_ic(picks, fwd, "final_score_v3", HORIZONS).to_dict("records"),
        "main_only_final_score_v3": cross_sectional_ic(main_only, fwd, "final_score_v3", HORIZONS, min_n=6).to_dict("records"),
        "main_only_entry_score": cross_sectional_ic(main_only, fwd, "entry_score", HORIZONS, min_n=6).to_dict("records"),
        "note": "표본 매우 작음(활성 거래일 적음). 판정값 아님.",
    }
    out_path = "docs/v3_ic_summary.json" if __import__("os").path.isdir("docs") else "v3_ic_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("요약 저장:", out_path)


if __name__ == "__main__":
    main()
