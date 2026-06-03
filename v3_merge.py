# -*- coding: utf-8 -*-
"""
v3_merge.py — v3 점수를 본체 CSV에 합쳐 넣기 (HTML/대시보드 통일용)
=====================================================================
v3_rescore 가 만든 결과(final_score_v3, grade, bucket, 세부점수)를
HTML·대시보드가 읽는 본체 파일에 컬럼으로 병합한다.

대상 파일(있으면 모두 갱신):
    docs/latest_{market}_enriched.csv   ← filter.html 이 우선으로 읽음
    docs/latest_{market}_final.csv
    latest_{market}_final.csv

옛 final_score 는 그대로 두고 v3 컬럼만 추가하므로, 언제든 비교/되돌리기 가능.

실행:
    python v3_merge.py                 # 최신 run_id 기준
    python v3_merge.py --run_id 20260603
"""
import argparse
import glob
import os
from pathlib import Path

import pandas as pd

import v3_rescore as v3

HERE = Path(__file__).resolve().parent

# 본체에 추가할 v3 컬럼
V3_COLS = ["final_score_v3", "grade", "bucket", "entry_score",
           "value_score", "value_source", "quality_score",
           "turnaround_score", "reversal_score", "supply_score_v2",
           "oversold_component", "main_candidate"]


def _v3_for(run_id, market):
    """v3 결과를 얻는다. 보관본(v3_archive)이 있으면 그걸, 없으면 즉석 재계산."""
    arch = sorted(glob.glob(str(HERE / "v3_archive" / f"v3_{market}_{run_id}.csv")))
    if arch:
        return pd.read_csv(arch[-1], dtype={"ticker": str})
    sub = v3.load_runs()
    sub = sub[(sub["run_id"].astype(str) == str(run_id)) & (sub["market"] == market)]
    if sub.empty:
        return None
    return v3.rescore(sub, run_id=str(run_id), market=market)


def _merge_into(path, vdf):
    """path CSV 에 v3 컬럼을 ticker 기준으로 병합 후 덮어쓴다."""
    if not os.path.exists(path):
        return False
    df = pd.read_csv(path, dtype={"ticker": str})
    if "ticker" not in df.columns:
        return False
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    add = vdf[["ticker"] + [c for c in V3_COLS if c in vdf.columns]].copy()
    add["ticker"] = add["ticker"].astype(str).str.zfill(6)
    # 기존에 같은 v3 컬럼이 있으면(재실행) 먼저 제거 후 새로 붙임
    drop = [c for c in add.columns if c != "ticker" and c in df.columns]
    df = df.drop(columns=drop, errors="ignore")
    out = df.merge(add, on="ticker", how="left")
    out.to_csv(path, index=False, encoding="utf-8-sig")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_id", default=None, help="기본: 가장 최근 run")
    args = ap.parse_args()

    allruns = v3.load_runs()
    run_id = args.run_id or sorted(allruns["run_id"].astype(str).unique())[-1]

    for market in ["kospi", "kosdaq"]:
        vdf = _v3_for(run_id, market)
        if vdf is None or vdf.empty:
            print(f"[skip] {market}: v3 결과 없음 (run_id={run_id})")
            continue
        targets = [
            HERE / "docs" / f"latest_{market}_enriched.csv",
            HERE / "docs" / f"latest_{market}_final.csv",
            HERE / f"latest_{market}_final.csv",
        ]
        done = [str(p.name) for p in targets if _merge_into(str(p), vdf)]
        nbuy = int((vdf["bucket"] == "BUY").sum()) if "bucket" in vdf else 0
        nwait = int((vdf["bucket"] == "WAIT").sum()) if "bucket" in vdf else 0
        print(f"[ok] {market} {run_id}: v3 병합 → {done}  (BUY {nbuy}, WAIT {nwait})")

    print("완료. filter.html 에서 v3 컬럼(grade/final_score_v3/bucket)을 쓸 수 있습니다.")


if __name__ == "__main__":
    main()
