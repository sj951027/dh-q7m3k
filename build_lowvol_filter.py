# -*- coding: utf-8 -*-
"""
build_lowvol_filter.py — 저변동 트랙 lv_a '관측 페이지'용 CSV 생성 (로컬·테스트)
==============================================================================
lowvol_scores 테이블(lv_a)을 최신 run 기준으로 읽어, 종목명·섹터·핵심지표를 stage3_final
에서 조인한 `latest_{market}_lowvol.csv` 를 docs/ 에 만든다. lowvol.html(전용 경량 페이지)이
이 CSV 를 fetch 해 점수순으로 그린다.

v31g 와 다른 점: lowvol 은 **자체 점수(lowvol_score)** 라 v3 의 grade/bucket 이 없다. 그래서
filter.html 재활용이 아니라 전용 페이지(lowvol.html)를 쓴다. 비교용으로 v3 의 bucket(있으면)을
참고 컬럼으로 덧붙인다(섞는 게 아니라 '관측 표시').

⚠️ 규율(LOWVOL_TRACK_DESIGN §5-6):
   lv_a 는 **검증 전 섀도우**. 신호(저변동·반전)=사후(낚시) 발견 → 지금 점수는 **가설**.
   이 CSV·페이지는 매수신호가 아니다. 판정은 등록일 이후 OOS 40거래일.
   v3·large 산출물은 일절 안 건드린다. 점수는 history.db 만 읽어 계산(네트워크 불필요).
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "history.db"
DOCS = HERE / "docs"
MARKETS = ["kospi", "kosdaq"]
MODEL = "lv_a"   # 노출 모델(견고성 최상위). 나머지는 shadow.

# stage3 에서 가져올 표시용 컬럼(있는 것만 조인)
DISPLAY_COLS = [
    "name", "sector", "oversold_score", "realized_vol", "roe_value",
    '"return_1w_%"', '"return_1m_%"', '"drawdown_52w_high_%"',
    '"amt_avg_1m_억"', '"foreign_20d_억"', '"inst_20d_억"',
    '"quarterly_yoy_%"', "final_score",
]


def build_one(con, rid, mkt, sector_map=None):
    ls = pd.read_sql(
        "SELECT ticker, lowvol_score, n_universe FROM lowvol_scores "
        "WHERE run_id=? AND market=? AND model_id=?",
        con, params=(rid, mkt, MODEL))
    if ls.empty:
        return None
    # 표시 컬럼 조인 (stage3_final)
    cols = ",".join(["ticker"] + DISPLAY_COLS)
    s3 = pd.read_sql(
        f"SELECT {cols} FROM stage3_final WHERE run_id=? AND market=?",
        con, params=(rid, mkt))
    s3.columns = [c.strip('"') for c in s3.columns]
    g = ls.merge(s3, on="ticker", how="left")

    # 섹터: stage3_final 의 sector 는 비어 있음(100% 결측) → sector_cache.json 으로 채움.
    #   (PROJECT_KNOWLEDGE §4-C: sector_cache 가 현재 universe 100% 커버.)
    if sector_map:
        filled = g["ticker"].astype(str).map(sector_map)
        # 캐시에 있으면 캐시값, 없으면 기존(보통 빈값) 유지
        g["sector"] = filled.where(filled.notna(), g.get("sector"))

    # v3 bucket 참고용(있으면). 섞지 않고 '비교 표시'만.
    try:
        v3 = pd.read_sql(
            "SELECT ticker, bucket AS v3_bucket, grade AS v3_grade "
            "FROM v3_scores WHERE run_id=? AND market=? AND model_id='v30'",
            con, params=(rid, mkt))
        if not v3.empty:
            g = g.merge(v3, on="ticker", how="left")
    except Exception:
        pass

    # lowvol_score 내림차순 = 이 트랙의 순위(높을수록 선호)
    g = g.sort_values("lowvol_score", ascending=False).reset_index(drop=True)
    g.insert(0, "rank", g.index + 1)
    g["lowvol_score"] = g["lowvol_score"].round(3)
    return g


def main():
    ap = argparse.ArgumentParser(description="lowvol lv_a 관측 CSV 생성(로컬)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--docs", default=str(DOCS))
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    runs = pd.read_sql("SELECT DISTINCT run_id FROM lowvol_scores", con)
    if runs.empty:
        print("❌ lowvol_scores 비어 있음 — 먼저 `python lowvol_score.py --full`.")
        sys.exit(1)
    rid = str(args.run_id) if args.run_id else str(runs["run_id"].astype(str).max())
    docs = Path(args.docs)
    docs.mkdir(parents=True, exist_ok=True)

    # 섹터 캐시 로드(있으면). stage3_final.sector 가 비어 있어 이걸로 채운다.
    sector_map = None
    sc_path = HERE / "sector_cache.json"
    if sc_path.exists():
        try:
            import json
            sector_map = {str(k): v for k, v in json.loads(sc_path.read_text(encoding="utf-8")).items()}
        except Exception as e:
            print(f"  ⚠️ sector_cache.json 로드 실패(섹터 빈칸 유지): {e}")

    total = 0
    for mkt in MARKETS:
        g = build_one(con, rid, mkt, sector_map=sector_map)
        if g is None:
            print(f"  ⚠️ {mkt}: run {rid} lv_a 데이터 없음 — 건너뜀")
            continue
        for path in (docs / f"latest_{mkt}_lowvol.csv", HERE / f"latest_{mkt}_lowvol.csv"):
            g.to_csv(path, index=False, encoding="utf-8-sig")
        n_uni = int(g["n_universe"].iloc[0]) if "n_universe" in g else len(g)
        print(f"  ✓ {mkt}: {len(g)}종목(유니버스 {n_uni}) → docs/latest_{mkt}_lowvol.csv")
        total += len(g)
    con.close()
    print(f"💾 lowvol(lv_a) 관측 CSV 생성 — run {rid}, 합계 {total}종목.")
    print("   lowvol.html 을 docs/ 에 두고 커밋하면 열람. (v3·large 산출물 불변)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
