# -*- coding: utf-8 -*-
"""
build_mom_filter.py — 모멘텀 대조 모델 mom_a '관측 페이지'용 CSV 생성 (로컬·테스트)
==============================================================================
build_lowvol_filter.py 의 mom_a 판. lowvol_scores 테이블(mom_a)을 최신 run 기준으로 읽어
종목명·섹터·핵심지표를 stage3_final 에서 조인한 `latest_{market}_mom.csv` 를 docs/ 에 만든다.
mom.html(전용 경량 페이지)이 이 CSV 를 fetch 해 점수순으로 그린다.

⚠️ 규율(PROJECT_KNOWLEDGE §15):
  - mom_a 는 검증 전 관측 모델(가중치 0, 등록 20260627, post-hoc → forward-only).
  - 유니버스가 '과매도 30~70' 이라 진짜 상승 주도주는 풀에 없음 — 하락장에선
    '상승포착'이 아니라 '덜 빠진 종목 상대방어'로 작동(§15 실측). 페이지에 명시.
  - v3·large·lowvol(lv_a) 산출물은 일절 안 건드림. history.db·ohlcv.db 읽기 전용.
  - 이 CSV·페이지는 매수신호가 아님. 판정은 OOS 40거래일 + 상승장 표본 충분 시.

사용:
    python build_mom_filter.py               # 최신 run
    python build_mom_filter.py --run-id 20260710
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "history.db"
OHLCV_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))
DOCS = HERE / "docs"
MARKETS = ["kospi", "kosdaq"]
MODEL = "mom_a"   # 노출 모델. 점수식 = sma20(핵심) + mom_1m + vol_exp 순위합.

# stage3 에서 가져올 표시용 컬럼(있는 것만 조인)
DISPLAY_COLS = [
    "name", "sector", "oversold_score",
    '"vs_SMA20_%"', '"return_1m_%"', '"vol_1w_vs_1m_ratio"',
    '"return_1w_%"', '"drawdown_52w_high_%"', '"amt_avg_1m_억"',
    '"foreign_5d_억"', '"foreign_20d_억"', '"inst_5d_억"', '"inst_20d_억"',
    '"quarterly_yoy_%"',
]


def _name_fallback(con, g):
    """stage3 조인에서 빈 종목명을 stage1_oversold + large_universe 로 보충(원본 보존).
    build_lowvol_filter._name_fallback 과 동일 로직."""
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


def _stage1_fill(con, rid, mkt, g):
    """stage3 결측분을 stage1_oversold 실재값으로 보충(과매도·수급). 재무는 갭 유지.
    build_lowvol_filter._stage1_fill 과 동일 로직."""
    S1_MAP = {"oversold_score": "oversold_score",
              "foreign_5d_억": '"foreign_5d_억"', "foreign_20d_억": '"foreign_20d_억"',
              "inst_5d_억": '"inst_5d_억"', "inst_20d_억": '"inst_20d_억"'}
    targets = [c for c in S1_MAP if c in g.columns]
    if not targets or not g[targets].isna().any().any():
        return g
    try:
        sel = ", ".join(f"{S1_MAP[c]} AS {c}" for c in targets)
        s1 = pd.read_sql(
            f"SELECT ticker, {sel} FROM stage1_oversold WHERE run_id=? AND market=?",
            con, params=(rid, mkt))
        s1["ticker"] = s1["ticker"].astype(str)
        s1 = s1.drop_duplicates("ticker").set_index("ticker")
        for col in targets:
            need = g[col].isna()
            if need.any():
                fill = g.loc[need, "ticker"].astype(str).map(s1[col])
                g.loc[need, col] = g.loc[need, col].where(g.loc[need, col].notna(), fill)
    except Exception:
        pass
    return g


def _ohlcv_fill(g, rid):
    """stage3 에 없어 비어버린 '가격 유도' 표시지표를 ohlcv 로 채운다(결측분만, 원본 보존).
    mom_a 표시용으로 vs_SMA20_%·vol_1w_vs_1m_ratio 를 추가 계산(스크리너 정의와 동일:
    sma20=(close/SMA20-1)x100, ratio=std5/std21). 재무(ROE·YoY·과매도)는 갭 유지(매직넘버 금지).
    ⚠️ stage3 에 값이 있는 행은 절대 덮지 않음(0-diff 원칙, build_lowvol_filter 와 동일)."""
    PRICE_COLS = ["vs_SMA20_%", "return_1m_%", "vol_1w_vs_1m_ratio",
                  "return_1w_%", "drawdown_52w_high_%", "amt_avg_1m_억"]
    have = [c for c in PRICE_COLS if c in g.columns]
    if not have:
        return g
    need_mask = g[have].isna().any(axis=1)
    if not need_mask.any():
        return g
    if not os.path.exists(OHLCV_DB):
        print(f"  ⚠️ ohlcv.db 없음({OHLCV_DB}) — 결측 가격지표 채우지 못함(갭 유지)")
        return g
    try:
        oc = sqlite3.connect(f"file:{OHLCV_DB}?mode=ro", uri=True)
        dates = [d for (d,) in oc.execute(
            "SELECT DISTINCT date FROM daily_ohlcv WHERE date<=? ORDER BY date", (rid,))]
        if not dates:
            oc.close(); return g
        cutoff = dates[max(0, len(dates) - 290)]
        df = pd.read_sql("SELECT ticker,date,close,volume FROM daily_ohlcv "
                         "WHERE date>=? AND date<=?", oc, params=(cutoff, rid))
        oc.close()
        c = df.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
        v = df.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(c.index)
        r = c.pct_change(fill_method=None)
        if rid not in c.index:
            return g
        t = c.index.get_loc(rid)
        calc = pd.DataFrame(index=c.columns)
        calc["vs_SMA20_%"] = (c.iloc[t] / c.rolling(20, min_periods=10).mean().iloc[t] - 1) * 100
        calc["return_1m_%"] = (c.iloc[t] / c.iloc[max(0, t - 20)] - 1) * 100
        std5 = r.rolling(5, min_periods=3).std().iloc[t]
        std21 = r.rolling(21, min_periods=8).std().iloc[t]
        calc["vol_1w_vs_1m_ratio"] = std5 / std21
        calc["return_1w_%"] = (c.iloc[t] / c.iloc[max(0, t - 5)] - 1) * 100
        calc["drawdown_52w_high_%"] = (c.iloc[t] / c.rolling(252, min_periods=60).max().iloc[t] - 1) * 100
        calc["amt_avg_1m_억"] = (c * v).rolling(20, min_periods=10).mean().iloc[t] / 1e8
        rnd = {"vs_SMA20_%": 1, "return_1m_%": 1, "vol_1w_vs_1m_ratio": 2,
               "return_1w_%": 1, "drawdown_52w_high_%": 1, "amt_avg_1m_억": 1}
        idx = g.index[need_mask]
        for col in have:
            fill = g.loc[idx, "ticker"].astype(str).map(calc[col]).round(rnd[col])
            g.loc[idx, col] = g.loc[idx, col].where(g.loc[idx, col].notna(), fill)
        return g
    except Exception as e:
        print(f"  ⚠️ ohlcv 가격지표 폴백 실패(갭 유지): {e}")
        return g


def build_one(con, rid, mkt, sector_map=None):
    ms = pd.read_sql(
        "SELECT ticker, lowvol_score AS mom_score, n_universe FROM lowvol_scores "
        "WHERE run_id=? AND market=? AND model_id=?",
        con, params=(rid, mkt, MODEL))
    if ms.empty:
        return None
    cols = ",".join(["ticker"] + DISPLAY_COLS)
    s3 = pd.read_sql(
        f"SELECT {cols} FROM stage3_final WHERE run_id=? AND market=?",
        con, params=(rid, mkt))
    s3.columns = [c.strip('"') for c in s3.columns]
    g = ms.merge(s3, on="ticker", how="left")
    g = _name_fallback(con, g)
    g = _stage1_fill(con, rid, mkt, g)
    g = _ohlcv_fill(g, rid)

    # lv_a 순위 참고 컬럼(같은 유니버스의 대조 모델 — 섞지 않고 비교 표시만).
    try:
        lva = pd.read_sql(
            "SELECT ticker, lowvol_score AS lv_a_score FROM lowvol_scores "
            "WHERE run_id=? AND market=? AND model_id='lv_a'",
            con, params=(rid, mkt))
        if not lva.empty:
            lva = lva.sort_values("lv_a_score", ascending=False).reset_index(drop=True)
            lva["lv_a_rank"] = lva.index + 1
            g = g.merge(lva[["ticker", "lv_a_rank"]], on="ticker", how="left")
    except Exception:
        pass

    # mom_b 순위 참고 컬럼(mom_a+눌림목 챌린저, 등록 20260717 — 섞지 않고 비교 표시만).
    #   PREREGISTER_mom_b.md. 관측용 병기이며 매수신호 아님. 없으면(구 DB) 컬럼 생략.
    try:
        mb = pd.read_sql(
            "SELECT ticker, lowvol_score AS mom_b_score FROM lowvol_scores "
            "WHERE run_id=? AND market=? AND model_id='mom_b'",
            con, params=(rid, mkt))
        if not mb.empty:
            mb = mb.sort_values("mom_b_score", ascending=False).reset_index(drop=True)
            mb["mom_b_rank"] = mb.index + 1
            g = g.merge(mb[["ticker", "mom_b_rank"]], on="ticker", how="left")
    except Exception:
        pass

    # 섹터 채움(sector_cache)
    if sector_map:
        filled = g["ticker"].astype(str).map(sector_map)
        g["sector"] = filled.where(filled.notna(), g.get("sector"))

    # v3 bucket 참고용
    try:
        v3 = pd.read_sql(
            "SELECT ticker, bucket AS v3_bucket, grade AS v3_grade "
            "FROM v3_scores WHERE run_id=? AND market=? AND model_id='v30'",
            con, params=(rid, mkt))
        if not v3.empty:
            g = g.merge(v3, on="ticker", how="left")
    except Exception:
        pass

    g = g.sort_values("mom_score", ascending=False).reset_index(drop=True)
    g.insert(0, "rank", g.index + 1)
    g["mom_score"] = g["mom_score"].round(3)
    n = len(g)
    g["top10pct"] = (g["rank"] <= max(1, round(n * 0.10))).astype(int)
    g["top20pct"] = (g["rank"] <= max(1, round(n * 0.20))).astype(int)
    return g


def main():
    ap = argparse.ArgumentParser(description="mom_a 관측 CSV 생성(로컬)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--docs", default=str(DOCS))
    args = ap.parse_args()

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    runs = pd.read_sql(
        "SELECT DISTINCT run_id FROM lowvol_scores WHERE model_id=?", con, params=(MODEL,))
    if runs.empty:
        print("❌ lowvol_scores 에 mom_a 없음 — 먼저 `python lowvol_score.py`.")
        sys.exit(1)
    rid = str(args.run_id) if args.run_id else str(runs["run_id"].astype(str).max())
    docs = Path(args.docs)
    docs.mkdir(parents=True, exist_ok=True)

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
            print(f"  ⚠️ {mkt}: run {rid} mom_a 데이터 없음 — 건너뜀")
            continue
        # [2026-09-05] 희석 공시 60거래일 배지(표시 전용, 점수·순위 무반영) — dilution_flag.py
        try:
            import dilution_flag as _dil
            g, _nd = _dil.attach(g, asof=rid)
            if _nd: print(f"  ⚠️ {mkt}: 희석 공시 60거래일 내 {_nd}종목(배지)")
        except Exception as _e:
            print(f"  ⚠️ 희석 배지 생략(비치명): {_e}")
        for path in (docs / f"latest_{mkt}_mom.csv", HERE / f"latest_{mkt}_mom.csv"):
            g.to_csv(path, index=False, encoding="utf-8-sig")
        n_uni = int(g["n_universe"].iloc[0]) if "n_universe" in g else len(g)
        print(f"  ✓ {mkt}: {len(g)}종목(유니버스 {n_uni}) → docs/latest_{mkt}_mom.csv")
        total += len(g)
    con.close()
    # [2026-08-29] 기준일 메타 — 관측 페이지 '오래된 목록' 경고 배지용(lowvol 과 동일 패턴).
    import json as _json
    from datetime import datetime as _dt
    (docs / "mom_meta.json").write_text(
        _json.dumps({"run_id": rid, "model": MODEL,
                     "generated_at": _dt.now().isoformat(timespec="seconds")},
                    ensure_ascii=False), encoding="utf-8")
    print(f"💾 mom_a 관측 CSV 생성 — run {rid}, 합계 {total}종목. (+mom_meta.json)")
    print("   mom.html 을 docs/ 에 두고 커밋하면 열람. (v3·large·lv_a 산출물 불변)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
