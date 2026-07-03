# -*- coding: utf-8 -*-
"""
build_wu_filter.py — 전체종목 트랙 wu_a '관측 페이지'용 CSV 생성 (로컬·테스트)
==============================================================================
wu_scores 테이블(wu_a)을 최신 run 기준으로 읽어 `docs/latest_wu.csv` 를 만든다(전체 유니버스
단일 순위 — 시장 분리 없음, market 컬럼으로 페이지에서 필터). wu.html 이 이 CSV 를 fetch 해 그린다.

lowvol(build_lowvol_filter.py)과 같은 계열, 다른 점:
  * wu 는 전체 상장 유니버스라 종목명이 stage3 에 거의 없음 → **stage1_oversold(최신 run, 전종목)** 에서 조인.
  * 표시지표(시총·변동성·고점대비·12-1모멘텀 등)는 **ohlcv.db 에서 계산**(점수와 동일 동결식,
    표시 전용). ohlcv 없으면 지표만 빈칸(점수·순위는 유지) — 실패로 안 만든다.
  * wu_b(순수선택 대조: 고점근접+모멘텀, 시총 무베팅) 점수·순위를 나란히 표시(비교 관측).

⚠️ 규율(PREREGISTER_wu.md):
   wu_a/b 는 **검증 전 섀도우**(발견 2024-07~2026-07 in-sample, 대형 독주 국면). 이 CSV·페이지는
   매수신호가 아니다. 판정은 등록일 이후 OOS 40거래일. v3·large·lowvol 산출물은 일절 안 건드린다.
   history.db(읽기)·ohlcv.db(읽기)만 사용 — 네트워크 0.
"""
import argparse
import json
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
MODEL = "wu_a"     # 노출 모델. wu_b 는 비교 컬럼으로만.
LOAD_PAD = 290     # 표시지표 계산 룩백(wu_score.py 와 동일)


def _ohlcv_metrics(rid, tickers):
    """표시 전용 지표를 ohlcv 에서 계산(동결식과 동일). 실패/부재 시 None."""
    if not os.path.exists(OHLCV_DB):
        print(f"  ⚠️ ohlcv.db 없음({OHLCV_DB}) — 표시지표 빈칸으로 진행")
        return None
    try:
        oc = sqlite3.connect(f"file:{OHLCV_DB}?mode=ro", uri=True)
        dates = [d for (d,) in oc.execute("SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
        if rid not in dates:
            print(f"  ⚠️ ohlcv 에 run {rid} 없음 — 표시지표 빈칸")
            oc.close(); return None
        cutoff = dates[max(0, dates.index(rid) - LOAD_PAD)]
        df = pd.read_sql("SELECT ticker,date,close,volume,shares FROM daily_ohlcv WHERE date>=?",
                         oc, params=(cutoff,))
        oc.close()
        piv = lambda v: df.pivot_table(index="date", columns="ticker", values=v, aggfunc="last").sort_index()
        c = piv("close"); v = piv("volume").reindex(c.index); sh = piv("shares").reindex(c.index)
        r = c.pct_change(fill_method=None)
        t = c.index.get_loc(rid)
        m = pd.DataFrame(index=c.columns)
        m["mcap_조"] = (c.iloc[t] * sh.iloc[t] / 1e12).round(2)
        m["lv63"] = r.rolling(63, min_periods=30).std().iloc[t].round(4)
        m["nh252_%"] = ((c.iloc[t] / c.rolling(252, min_periods=120).max().iloc[t] - 1) * 100).round(1)
        m["mom12_%"] = ((c.shift(21).iloc[t] / c.shift(252).iloc[t] - 1) * 100).round(1)
        m["r20d_%"] = ((c.iloc[t] / c.iloc[max(0, t - 20)] - 1) * 100).round(1)
        m["amt20_억"] = ((c * v).rolling(20, min_periods=10).mean().iloc[t] / 1e8).round(1)
        return m.reindex(tickers)
    except Exception as e:
        print(f"  ⚠️ ohlcv 지표 계산 실패(빈칸 진행): {e}")
        return None


def _name_map(con):
    """ticker→name 통합 사전(DataFrame). stage1(전 run, 최신 우선)에 large_universe 폴백."""
    frames = []
    for q in ("SELECT ticker, name, run_id FROM stage1_oversold",
              "SELECT ticker, name, run_id FROM large_universe"):
        try:
            frames.append(pd.read_sql(q, con))
        except Exception:
            pass
    if not frames:
        return pd.DataFrame(columns=["ticker", "name"])
    nm = pd.concat(frames, ignore_index=True).dropna(subset=["name"])
    nm["ticker"] = nm["ticker"].astype(str)
    nm = nm.sort_values("run_id").drop_duplicates("ticker", keep="last")
    return nm[["ticker", "name"]]


def _apply_pref_fallback(g, name_map_df):
    """결측 이름에 한해 우선주 유도명을 채운다(원본 이름은 절대 덮지 않음).
    한국 코드 관례: 보통주 XXXXX0, 우선주 XXXXX5/7/9·신형 …K·구형 …B. stage/large 어디에도
    없는 우선주·초소형주가 코드만 뜨는 문제(2026-07-03 실측 41개 대부분 우선주) 완화."""
    if "name" not in g.columns:
        return g
    base = dict(zip(name_map_df["ticker"].astype(str), name_map_df["name"])) if len(name_map_df) else {}
    miss = g["name"].isna()
    if not miss.any() or not base:
        return g

    def derive(tk):
        tk = str(tk)
        if len(tk) == 6 and tk[-1] != "0" and tk[:-1].isdigit():
            common = tk[:-1] + "0"
            if common in base:
                return base[common] + ("우" if tk[-1] in "5B" else f"우{tk[-1]}")
        return None

    g.loc[miss, "name"] = g.loc[miss, "ticker"].map(derive)
    return g


def _flows_metrics(rid, tickers, hist_con=None):
    """외인/기관 5·20거래일 순매수(억) — daily_flows(KIS, ohlcv.db 우선·history 폴백) 합산.
    단위: net_val(백만원)/100 = 억. flows에 존재하는 최근 거래일 기준으로 5·20일 창을 잡으므로
    당일(run) flows가 아직 적재 전이어도 '최근 5거래일'은 flows 최신일 기준으로 채워진다
    (파이프라인상 wu 단계가 KIS flows 적재보다 앞서는 문제를 흡수 — 2026-07-03 실측 반영).
    20일 창은 종목별 실제 적재일이 부족하면(초기 구간) NaN. 표시 전용 — 점수 미투입."""
    MIN5, MIN20 = 3, 12
    src, own = None, False
    try:
        oc = sqlite3.connect(f"file:{OHLCV_DB}?mode=ro", uri=True)
        if oc.execute("SELECT name FROM sqlite_master WHERE name='daily_flows'").fetchone():
            src, own = oc, True
        else:
            oc.close()
    except Exception:
        pass
    if src is None and hist_con is not None:
        try:
            if hist_con.execute("SELECT name FROM sqlite_master WHERE name='daily_flows'").fetchone():
                src = hist_con
        except Exception:
            pass
    if src is None:
        print("  ⚠️ daily_flows 없음(ohlcv/history) — 수급 컬럼 빈칸으로 진행")
        return None
    try:
        # 거래일 그리드: **flows에 실제 존재하는 거래일**을 기준으로 창을 잡는다.
        #   (ohlcv 그리드를 쓰면 당일 flows 미적재 시 5일창이 4일 미만으로 떨어져 전부 NaN이 됨.
        #    파이프라인상 wu 단계가 flows 적재보다 앞서므로 이 방어가 필요 — 2026-07-03 실측 반영.)
        fdates = [d for (d,) in src.execute(
            "SELECT DISTINCT date FROM daily_flows WHERE date<=? ORDER BY date", (rid,))]
        if not fdates:
            return None
        last5, last20 = set(fdates[-5:]), set(fdates[-20:])
        fl = pd.read_sql(
            "SELECT ticker, date, foreign_net_val, inst_net_val FROM daily_flows "
            "WHERE date>=? AND date<=?", src, params=(min(last20), max(fdates)))
        fl["ticker"] = fl["ticker"].astype(str)
        out = pd.DataFrame(index=pd.Index(tickers, name="ticker"))
        for win, wset, mn in (("5d", last5, MIN5), ("20d", last20, MIN20)):
            sub = fl[fl["date"].isin(wset)]
            agg = sub.groupby("ticker").agg(
                n=("date", "nunique"), f=("foreign_net_val", "sum"), i=("inst_net_val", "sum"))
            ok = agg["n"] >= mn
            out[f"foreign_{win}_억"] = (agg["f"].where(ok) / 100).round(1)
            out[f"inst_{win}_억"] = (agg["i"].where(ok) / 100).round(1)
        return out[["foreign_5d_억", "foreign_20d_억", "inst_5d_억", "inst_20d_억"]]
    except Exception as e:
        print(f"  ⚠️ 수급 계산 실패(빈칸 진행): {e}")
        return None
    finally:
        if own:
            src.close()


def build(con, rid, sector_map=None, use_ohlcv=True):
    g = pd.read_sql(
        "SELECT wu_rank AS rank, ticker, market, wu_score, n_universe FROM wu_scores "
        "WHERE run_id=? AND model_id=? ORDER BY wu_rank", con, params=(rid, MODEL))
    if g.empty:
        return None
    g["ticker"] = g["ticker"].astype(str)
    g["wu_score"] = g["wu_score"].round(3)

    # wu_b(순수선택 대조) 나란히 — wu_a 점수·순위는 그대로(0-diff).
    try:
        wb = pd.read_sql(
            "SELECT ticker, wu_score AS wu_b_score, wu_rank AS wu_b_rank FROM wu_scores "
            "WHERE run_id=? AND model_id='wu_b'", con, params=(rid,))
        if not wb.empty:
            wb["ticker"] = wb["ticker"].astype(str)
            wb["wu_b_score"] = wb["wu_b_score"].round(3)
            g = g.merge(wb, on="ticker", how="left")
    except Exception:
        pass

    # 종목명: stage1_oversold(전 run 통합, 최신 우선) + large_universe 폴백.
    #   wu 는 전체 상장 유니버스라 stage1(v3 유니버스)에 없는 대형주가 있음(예: 금융지주)
    #   → large 트랙 이름으로 보충. 어느 쪽도 없으면 코드만 표시.
    try:
        _nm = _name_map(con)
        g = g.merge(_nm, on="ticker", how="left")
        g = _apply_pref_fallback(g, _nm)   # 결측 우선주·초소형주 이름 유도(원본 보존)
    except Exception:
        g["name"] = None

    # 업종: sector_cache.json (stage 계열과 동일 소스)
    if sector_map:
        g["sector"] = g["ticker"].map(sector_map)

    # v3 bucket 참고(같은 run 있으면). 섞지 않고 '비교 표시'만.
    try:
        v3 = pd.read_sql(
            "SELECT ticker, bucket AS v3_bucket FROM v3_scores "
            "WHERE run_id=? AND model_id='v30'", con, params=(rid,))
        if not v3.empty:
            v3["ticker"] = v3["ticker"].astype(str)
            g = g.merge(v3.drop_duplicates("ticker"), on="ticker", how="left")
    except Exception:
        pass

    # 표시지표(ohlcv, 표시 전용)
    if use_ohlcv:
        m = _ohlcv_metrics(rid, g["ticker"].tolist())
        if m is not None:
            g = g.join(m.reset_index(drop=True).set_index(g.index))
        # 외인/기관 5·20거래일 순매수(억) — KIS daily_flows(표시 전용, 점수 미투입)
        fm = _flows_metrics(rid, g["ticker"].tolist(), hist_con=con)
        if fm is not None:
            g = g.join(fm.reset_index(drop=True).set_index(g.index))

    # 표시용 집중도 플래그(점수 불변, 순위 기반). top50 = 연구 시뮬 기준 바스켓 크기.
    n = len(g)
    g["top50"] = (g["rank"] <= 50).astype(int)
    g["top10pct"] = (g["rank"] <= max(1, round(n * 0.10))).astype(int)
    return g


def main():
    ap = argparse.ArgumentParser(description="wu(wu_a) 관측 CSV 생성(로컬)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--docs", default=str(DOCS))
    ap.add_argument("--no-ohlcv", action="store_true", help="표시지표 계산 생략(점수·순위만)")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    runs = pd.read_sql("SELECT DISTINCT run_id FROM wu_scores", con)
    if runs.empty:
        print("❌ wu_scores 비어 있음 — 먼저 `python wu_score.py`."); sys.exit(1)
    rid = str(args.run_id) if args.run_id else str(runs["run_id"].astype(str).max())

    sector_map = None
    sc_path = HERE / "sector_cache.json"
    if sc_path.exists():
        try:
            sector_map = {str(k): v for k, v in json.loads(sc_path.read_text(encoding="utf-8")).items()}
        except Exception as e:
            print(f"  ⚠️ sector_cache.json 로드 실패(업종 빈칸 유지): {e}")

    g = build(con, rid, sector_map=sector_map, use_ohlcv=not args.no_ohlcv)
    con.close()
    if g is None:
        print(f"❌ run {rid} wu_a 데이터 없음"); sys.exit(1)

    docs = Path(args.docs); docs.mkdir(parents=True, exist_ok=True)
    for path in (docs / "latest_wu.csv", HERE / "latest_wu.csv"):
        g.to_csv(path, index=False, encoding="utf-8-sig")
    n_uni = int(g["n_universe"].iloc[0]) if "n_universe" in g else len(g)
    nm_cov = g["name"].notna().mean() * 100 if "name" in g else 0
    print(f"  ✓ {len(g)}종목(유니버스 {n_uni}, 종목명 커버 {nm_cov:.0f}%) → docs/latest_wu.csv")
    print(f"💾 wu(wu_a) 관측 CSV 생성 — run {rid}. wu.html 을 docs/ 에 두고 커밋하면 열람.")
    print("   (v3·large·lowvol 산출물 불변 — history.db·ohlcv.db 읽기 전용)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
