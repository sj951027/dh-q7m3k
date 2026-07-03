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
    '"amt_avg_1m_억"', '"foreign_5d_억"', '"foreign_20d_억"',
    '"inst_5d_억"', '"inst_20d_억"',
    '"quarterly_yoy_%"', "final_score",
]


def _name_fallback(con, g):
    """stage3_final 조인에서 비어버린 종목명을 stage1_oversold(과매도 원본, 더 넓음)+
    large_universe 로 보충한다(원본 이름은 절대 덮지 않음).
    근거: lv_a 유니버스는 과매도 원본(stage1)에서 오는데 표시 이름은 stage3(과매도+DART 필터
    통과분)에서만 조인 → stage3 탈락 종목이 이름만 비는 표시 결함(2026-07-03 실측 60개, 전부 보통주).
    lv 유니버스엔 우선주가 없어 우선주 유도는 불필요 — 순수 이름 폴백만."""
    if "name" not in g.columns or not g["name"].isna().any():
        return g
    frames = []
    for q in ("SELECT ticker, name, run_id FROM stage1_oversold",
              "SELECT ticker, name, run_id FROM large_universe"):
        try:
            frames.append(pd.read_sql(q, con))
        except Exception:
            pass
    if not frames:
        return g
    nm = pd.concat(frames, ignore_index=True).dropna(subset=["name"])
    nm["ticker"] = nm["ticker"].astype(str)
    nm = nm.sort_values("run_id").drop_duplicates("ticker", keep="last")
    namemap = dict(zip(nm["ticker"], nm["name"]))
    miss = g["name"].isna()
    g.loc[miss, "name"] = g.loc[miss, "ticker"].astype(str).map(namemap)
    return g


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
    g = _name_fallback(con, g)   # stage3에서 안 붙은 종목명을 stage1+large로 보충(원본 보존)

    # lv_short 챌린저 점수도 나란히 표시(공매도 추가본). 비교용 — lv_a 와 어느 게 나은지 관찰.
    #   별도 컬럼 lv_short_score + 그 순위 lv_short_rank. lv_a 점수·순위는 그대로(0-diff).
    try:
        lss = pd.read_sql(
            "SELECT ticker, lowvol_score AS lv_short_score FROM lowvol_scores "
            "WHERE run_id=? AND market=? AND model_id='lv_short'",
            con, params=(rid, mkt))
        if not lss.empty:
            lss["lv_short_score"] = lss["lv_short_score"].round(3)
            # lv_short 기준 순위(공매도 반영 순위)
            lss = lss.sort_values("lv_short_score", ascending=False).reset_index(drop=True)
            lss["lv_short_rank"] = lss.index + 1
            g = g.merge(lss, on="ticker", how="left")
    except Exception:
        pass

    # lv_b 점수도 나란히 표시(저변동+ROE, 반전 제외). 비교용 — IC 백테스트에서 lv_b 가
    #   lv_a 보다 강함(h20 +0.115 vs +0.077, 전체장 in-sample)을 관찰 페이지에서 같이 본다.
    #   별도 컬럼 lv_b_score + 그 순위 lv_b_rank. lv_a 점수·순위는 그대로(0-diff).
    try:
        lbs = pd.read_sql(
            "SELECT ticker, lowvol_score AS lv_b_score FROM lowvol_scores "
            "WHERE run_id=? AND market=? AND model_id='lv_b'",
            con, params=(rid, mkt))
        if not lbs.empty:
            lbs["lv_b_score"] = lbs["lv_b_score"].round(3)
            lbs = lbs.sort_values("lv_b_score", ascending=False).reset_index(drop=True)
            lbs["lv_b_rank"] = lbs.index + 1
            g = g.merge(lbs, on="ticker", how="left")
    except Exception:
        pass

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
    # 표시용 집중도 플래그(점수 불변, 순위 기반 cutoff).
    #   오프라인 검증: lv_a 상위 10% 롱숏 알파 +4.09%p > 20% +3.26%p(in-sample 가설).
    #   '상위 10%'를 강조·필터하려는 표시 레이어. 매수신호 아님.
    n = len(g)
    g["top10pct"] = (g["rank"] <= max(1, round(n * 0.10))).astype(int)
    g["top20pct"] = (g["rank"] <= max(1, round(n * 0.20))).astype(int)
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
