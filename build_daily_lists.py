# -*- coding: utf-8 -*-
"""build_daily_lists.py — 모델 페이지 '지난 날짜 리스트' 탭 데이터 (표시 전용, 2026-09-17)

history.db 의 동결 점수(v3_scores·lowvol_scores·wu_scores)에서 최근 N거래일 앵커별 시장별 상위 K 를 뽑아
docs/hist/{model}.json 으로 내보낸다. 종목명은 같은 run 의 stage3_final, 없으면 listing_cache. 가격은 ohlcv.db close
(그날 종가 → 최신 종가 등락%). run_id→거래일·게이트는 leaderboard.py 규약(anchor/dedupe_by_anchor/build_gates).
점수·판정 코드 미접촉 · 읽기 전용 · 실패해도 비치명. 실행: python build_daily_lists.py [--days 10] [--top 50]
"""
import argparse, json, sqlite3, sys
from datetime import datetime
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import leaderboard as lb

MODELS = {
    "lv_b": ("lowvol_scores", "lowvol_score", None, "20260625"),
    "v30":  ("v3_scores", "final_score_v3", "grade, bucket", "20260606"),
    "sv_a": ("wu_scores", "wu_score", None, "20260715"),
    "px_a": ("wu_scores", "wu_score", None, "20260810"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--top", type=int, default=50)
    a = ap.parse_args()
    out_dir = HERE / "docs" / "hist"; out_dir.mkdir(exist_ok=True)
    close, mktmap = lb.load_ohlcv()
    dates = list(close.index); N = len(dates)
    last = close.iloc[-1]
    con = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    names_cache = {}
    try:
        lc = json.loads((HERE.parent / "dh-q7m3k-data" / "listing_cache.json").read_text(encoding="utf-8"))
        names_cache = {str(r["code"]).zfill(6): r.get("name", "") for r in lc.get("rows", [])}
    except Exception:
        pass
    for model, (tbl, col, extra, reg) in MODELS.items():
        cols = f"run_id, market, ticker, {col} AS score" + (f", {extra}" if extra else "")
        S = pd.read_sql(f"SELECT {cols} FROM {tbl} WHERE model_id=?", con, params=(model,))
        if S.empty:
            print(f"  ⏭ {model}: 점수 없음"); continue
        S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str); S["market"] = S.market.str.lower()
        keep = lb.dedupe_by_anchor(S, didx, excl, reg=reg)
        anchors = sorted(((lb.anchor(r, didx), r) for r in keep if lb.anchor(r, didx) is not None), reverse=True)[:a.days]
        today_rank = {}
        days = []
        for t, rid in anchors:
            g = S[S.run_id == rid]
            nm = pd.read_sql("SELECT ticker, name FROM stage3_final WHERE run_id=?", con, params=(rid,))
            nm["ticker"] = nm.ticker.astype(str).str.zfill(6); nm = nm.drop_duplicates("ticker").set_index("ticker")["name"]
            rows = []
            for mk, gm in g.groupby("market"):
                gm = gm.sort_values("score", ascending=False).head(a.top)
                for rank, r in enumerate(gm.itertuples(index=False), 1):
                    tk = r.ticker
                    p0 = close.iloc[t].get(tk); p1 = last.get(tk)
                    p0 = float(p0) if (p0 is not None and p0 == p0) else None
                    p1 = float(p1) if (p1 is not None and p1 == p1) else None
                    chg = round((p1 / p0 - 1) * 100, 1) if (p0 and p1 and p0 > 0) else None
                    rows.append({"rank": rank, "ticker": tk, "name": nm.get(tk) or names_cache.get(tk, ""), "market": mk,
                                 "score": round(float(r.score), 2) if r.score == r.score else None,
                                 "grade": getattr(r, "grade", None), "bucket": getattr(r, "bucket", None),
                                 "px_then": p0, "px_now": p1, "chg_pct": chg})
            if not today_rank:      # 첫 앵커(최신) = 오늘 순위
                today_rank = {(x["market"], x["ticker"]): x["rank"] for x in rows}
            for x in rows:
                x["rank_today"] = today_rank.get((x["market"], x["ticker"]))
            days.append({"run_id": rid, "date": dates[t], "rows": rows})
        payload = {"model": model, "asof": dates[-1], "generated": datetime.now().isoformat(timespec="seconds"),
                   "note": "당시 동결 점수(history.db) 기준 시장별 상위 목록 · 등락 = 그날 종가→최신 종가 · 표시 전용", "days": days}
        (out_dir / f"{model}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"  ✓ docs/hist/{model}.json — {len(days)}일 ({days[-1]['date'] if days else '-'}~{days[0]['date'] if days else '-'}), 일당 {len(days[0]['rows']) if days else 0}행")
    con.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠ daily_lists 생성 실패(비치명): {e}")
