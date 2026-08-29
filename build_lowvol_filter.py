# -*- coding: utf-8 -*-
"""
build_lowvol_filter.py — 저변동 트랙 lv_b '관측 페이지'용 CSV 생성 (로컬·테스트)
==============================================================================
lowvol_scores 테이블(lv_b)을 최신 run 기준으로 읽어, 종목명·섹터·핵심지표를 stage3_final
에서 조인한 `latest_{market}_lowvol.csv` 를 docs/ 에 만든다. lowvol.html(전용 경량 페이지)이
이 CSV 를 fetch 해 점수순으로 그린다.

[2026-07-25 사용자 결정] 표시 기준을 lv_a → lv_b(저변동+ROE, 반전 제외)로 전환.
비교용 lv_short/lv_b/v3참고 컬럼은 제거(페이지 단순화). ⚠️ 적재·측정은 불변 —
lowvol_score.py 는 여전히 전 모델(lv_a~d·lv_short 등)을 적재하고 리더보드가 전부 측정한다.
바뀐 것은 '어느 모델을 페이지에 보여주나' 뿐. 판정 전 표시 전환이므로 여전히 관측 전용.

v31g 와 다른 점: lowvol 은 **자체 점수(lowvol_score)** 라 v3 의 grade/bucket 이 없다. 그래서
filter.html 재활용이 아니라 전용 페이지(lowvol.html)를 쓴다.

⚠️ 규율(LOWVOL_TRACK_DESIGN §5-6):
   lv_b 는 **검증 전 섀도우**. 신호(저변동)=사후(낚시) 발견 → 지금 점수는 **가설**.
   이 CSV·페이지는 매수신호가 아니다. 판정은 등록일 이후 OOS 40거래일.
   v3·large 산출물은 일절 안 건드린다. 점수는 history.db 만 읽어 계산(네트워크 불필요).
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "history.db"
OHLCV_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))
DOCS = HERE / "docs"
MARKETS = ["kospi", "kosdaq"]
MODEL = "lv_b"   # 노출 모델(2026-07-25 lv_a→lv_b 전환 — h5 IC 선두, 저변동+ROE·반전 제외). 나머지는 shadow.

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


def _ohlcv_fill(g, rid):
    """stage3_final 에 없어서 비어버린 표시지표를 ohlcv 가격으로 채운다(결측분에만, 원본 보존).
    채우는 것: realized_vol, return_1w/1m_%, drawdown_52w_high_%, amt_avg_1m_억 (가격 유도).
    채우지 못하는 것(데이터 갭, 재무 소스 필요): oversold_score, roe_value, quarterly_yoy_%,
    final_score → 그대로 NaN. lv_a 유니버스(과매도 원본 stage1)와 표시지표 소스(stage3=과매도+DART
    통과분)의 유니버스 불일치로 60개 종목이 지표 전체 결측인 문제(2026-07-04 실측) 중 가격계만 복구.
    ⚠️ stage3 에 값이 있는 종목은 stage3 값을 그대로 둔다(계산값으로 덮으면 수정주가·실행일 차이로
    미세 불일치 → 0-diff 파괴). 오프라인 검증됨: stage3 보유 행은 전부 불변.
    ROE·oversold·YoY 는 상상으로 만들지 않는다(매직넘버 금지) — 갭으로 명시."""
    PRICE_COLS = ["realized_vol", "return_1w_%", "return_1m_%",
                  "drawdown_52w_high_%", "amt_avg_1m_억"]
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
        calc["realized_vol"] = r.rolling(21, min_periods=8).std().iloc[t]
        calc["return_1w_%"] = (c.iloc[t] / c.iloc[max(0, t - 5)] - 1) * 100
        calc["return_1m_%"] = (c.iloc[t] / c.iloc[max(0, t - 20)] - 1) * 100
        calc["drawdown_52w_high_%"] = (c.iloc[t] / c.rolling(252, min_periods=60).max().iloc[t] - 1) * 100
        calc["amt_avg_1m_억"] = (c * v).rolling(20, min_periods=10).mean().iloc[t] / 1e8
        rnd = {"realized_vol": 4, "return_1w_%": 1, "return_1m_%": 1,
               "drawdown_52w_high_%": 1, "amt_avg_1m_억": 1}
        idx = g.index[need_mask]
        for col in have:
            fill = g.loc[idx, "ticker"].astype(str).map(calc[col]).round(rnd[col])
            g.loc[idx, col] = g.loc[idx, col].where(g.loc[idx, col].notna(), fill)
        return g
    except Exception as e:
        print(f"  ⚠️ ohlcv 가격지표 폴백 실패(갭 유지): {e}")
        return g


def _stage1_fill(con, rid, mkt, g):
    """stage3_final 에 없어서 비어버린 항목 중 stage1_oversold 에 실재하는 값으로 채운다(결측분만).
    채우는 것: oversold_score(과매도), foreign/inst 5d·20d(수급) — 모두 stage1 에 존재.
    근거: lv_a 유니버스(stage1/2 기반)에서 과매도<40 등으로 stage3 탈락한 종목은 stage3 지표가
    비지만, 그 종목의 과매도·수급은 stage1 에 그대로 남아 있음(2026-07-04 실측: 과매도 60/60 복구).
    ⚠️ stage3 에 값이 있으면 유지(0-diff). 재무(ROE·YoY)는 stage1 에도 없어 갭으로 남김(매직넘버 금지)."""
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
    g = _stage1_fill(con, rid, mkt, g)  # 과매도·수급을 stage1에서 보충(stage3 결측분, 재무는 갭)
    g = _ohlcv_fill(g, rid)      # 가격계 지표 + 수급 잔여를 ohlcv로 보충(재무지표는 갭)

    # [2026-07-25] lv_short/lv_b 비교 컬럼·v3참고 제거 — 표시 기준이 lv_b 로 바뀌며 페이지 단순화.
    #   (전 모델 적재·리더보드 측정은 그대로. 비교는 leaderboard.html 에서.)

    # 섹터: stage3_final 의 sector 는 비어 있음(100% 결측) → sector_cache.json 으로 채움.
    #   (PROJECT_KNOWLEDGE §4-C: sector_cache 가 현재 universe 100% 커버.)
    if sector_map:
        filled = g["ticker"].astype(str).map(sector_map)
        # 캐시에 있으면 캐시값, 없으면 기존(보통 빈값) 유지
        g["sector"] = filled.where(filled.notna(), g.get("sector"))

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
    global MODEL
    ap = argparse.ArgumentParser(description=f"lowvol {MODEL} 관측 CSV 생성(로컬)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--docs", default=str(DOCS))
    # [2026-08-14] lv_a 열람 페이지 배선(lva.html) — 기본 호출은 종전과 0-diff(lv_b·lowvol).
    ap.add_argument("--model", default=MODEL, help="lowvol_scores 의 model_id (기본 lv_b)")
    ap.add_argument("--suffix", default="lowvol", help="출력 파일명 latest_{mkt}_{suffix}.csv (기본 lowvol)")
    args = ap.parse_args()
    MODEL = args.model

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
            print(f"  ⚠️ {mkt}: run {rid} {MODEL} 데이터 없음 — 건너뜀")
            continue
        for path in (docs / f"latest_{mkt}_{args.suffix}.csv", HERE / f"latest_{mkt}_{args.suffix}.csv"):
            g.to_csv(path, index=False, encoding="utf-8-sig")
        n_uni = int(g["n_universe"].iloc[0]) if "n_universe" in g else len(g)
        print(f"  ✓ {mkt}: {len(g)}종목(유니버스 {n_uni}) → docs/latest_{mkt}_{args.suffix}.csv")
        total += len(g)
    con.close()
    # [2026-08-29] 기준일 메타 — lowvol.html 의 '오래된 목록' 경고 배지용.
    #   배경: 20260804~10 게이트 오탐으로 적재가 빠졌을 때 화면이 8/03자 목록으로
    #   일주일 동결됐던 사건(patch_note 20260829). 페이지가 이 run_id 로 신선도를 표시한다.
    import json as _json
    from datetime import datetime as _dt
    (docs / f"{args.suffix}_meta.json").write_text(
        _json.dumps({"run_id": rid, "model": MODEL,
                     "generated_at": _dt.now().isoformat(timespec="seconds")},
                    ensure_ascii=False), encoding="utf-8")
    print(f"💾 lowvol({MODEL}) 관측 CSV 생성 — run {rid}, 합계 {total}종목. (+{args.suffix}_meta.json)")
    print("   lowvol.html 을 docs/ 에 두고 커밋하면 열람. (v3·large 산출물 불변)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
