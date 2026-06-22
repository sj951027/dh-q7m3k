# -*- coding: utf-8 -*-
"""
build_v31g_filter.py — 챌린저 v31g(거래량팽창) '필터 페이지'용 CSV 생성 (로컬·비공개)
==============================================================================
filter.html 은 latest_{market}_*.csv 를 받아 컬럼을 동적으로 그린다. 이 스크립트는
history.db 최신 run 을 **v31g 스펙으로 재점수**해 챔피언 CSV와 같은 스키마의
`latest_{market}_v31g.csv` 를 docs/ 에 만든다. 그러면 filter_v31g.html(= filter.html
복사본, fetch 경로만 v31g)이 **v30 필터와 똑같은 화면**으로 v31g 를 보여준다.

비교용으로 v30 의 등급/버킷/점수와 Δ점수를 컬럼으로 덧붙인다(섞는 게 아니라 '관측 표시').

⚠️ 규율: v31g 는 검증 전 섀도우. 사용자 노출/판정 기준은 여전히 v30.
   이 CSV·페이지는 매수신호가 아니다. 판정은 compare_models --since 20260622 (OOS h=20d).
   챔피언 산출물(latest_{mkt}_final.csv·data.json·filter.html)은 일절 안 건드린다.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

import v3_rescore as v3

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "history.db"
DOCS = HERE / "docs"
MARKETS = ["kospi", "kosdaq"]


def build_one(allruns, rid, mkt):
    sub = allruns[(allruns["run_id"] == rid) & (allruns["market"] == mkt)]
    if sub.empty:
        return None
    # v31g = 페이지 본체(컬럼 전부 보존됨). v30 = 비교용.
    g = v3.rescore(sub, run_id=rid, market=mkt, spec=v3.MODELS["v31g"]).copy()
    a = v3.rescore(sub, run_id=rid, market=mkt, spec=v3.MODELS["v30"])[
        ["ticker", "final_score_v3", "grade", "bucket"]].rename(
        columns={"final_score_v3": "v30_final_score_v3",
                 "grade": "v30_grade", "bucket": "v30_bucket"})
    g = g.merge(a, on="ticker", how="left")
    g["dscore_v3"] = (pd.to_numeric(g["final_score_v3"], errors="coerce")
                      - pd.to_numeric(g["v30_final_score_v3"], errors="coerce")).round(2)
    # 버킷순 → 점수순 정렬(챔피언 표시 관례와 동일)
    br = {"BUY": 0, "WAIT": 1, "OBSERVE": 2, "WATCH": 3, "EXCLUDE": 4}
    g["_br"] = g["bucket"].map(br).fillna(9)
    g = g.sort_values(["_br", "final_score_v3"], ascending=[True, False]).drop(columns="_br")
    return g


def main():
    ap = argparse.ArgumentParser(description="v31g 필터용 CSV 생성(로컬)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--docs", default=str(DOCS))
    args = ap.parse_args()

    allruns = v3.load_runs(args.db)
    allruns["run_id"] = allruns["run_id"].astype(str)
    rid = str(args.run_id) if args.run_id else allruns["run_id"].max()
    docs = Path(args.docs)
    docs.mkdir(parents=True, exist_ok=True)

    total = 0
    for mkt in MARKETS:
        g = build_one(allruns, rid, mkt)
        if g is None:
            print(f"  ⚠️ {mkt}: run {rid} 데이터 없음 — 건너뜀")
            continue
        # docs/ 와 루트 둘 다(루트는 로컬 확인용). filter_v31g.html 은 docs/ 의 것을 fetch.
        for path in (docs / f"latest_{mkt}_v31g.csv", HERE / f"latest_{mkt}_v31g.csv"):
            g.to_csv(path, index=False, encoding="utf-8-sig")
        nbuy = int((g["bucket"] == "BUY").sum())
        nflip = int((g["bucket"] != g["v30_bucket"]).sum())
        print(f"  ✓ {mkt}: {len(g)}종목 (BUY {nbuy} · v30과 버킷갈림 {nflip}) → docs/latest_{mkt}_v31g.csv")
        total += len(g)
    print(f"💾 v31g 필터 CSV 생성 완료 — run {rid}, 합계 {total}종목.")
    print("   filter_v31g.html 을 docs/ 에 두고 커밋하면 v30 필터와 같은 화면으로 열람.")
    print("   (챔피언 latest_*_final.csv·data.json·filter.html 불변)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
