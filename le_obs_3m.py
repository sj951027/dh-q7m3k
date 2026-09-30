# -*- coding: utf-8 -*-
"""le_obs_3m.py — le.html 지난 날짜 탭용 3개월 관측 컬럼 (표시 전용 · le_a 점수·판정 무반영) [2026-09-30]

hist/le_a.json 의 날짜(run_id)마다, 그날 le_a 전체 목록(wu_scores le_a) 기준으로
  r63      = 3개월(63거래일) 수익률 %            (그날 종가 기준, v30 return_3m_% 와 같은 정의)
  r3m_low  = 같은 시장 안 3개월 수익률 낮은 순위 (1 = 가장 덜 오름)
  le3m     = le점수 백분위 + 0.3 × (1 − 3개월 수익률 백분위), 결측 0.5  (le.html 오늘 탭과 같은 식)
  le3m_rank= le3m 같은 시장 안 순위 (1 = 최우선)
를 계산해 docs/hist/le_a_3m.json 에 쓴다. le_a.json(상위 50) 밖이지만 le3m 상위 20 에 드는 종목은
그날 종가·최신 종가·등락까지 extra 로 넣어, 지난 탭에서 le+3개월 상위 10 을 온전히 볼 수 있게 한다.
기존 hist/le_a.json 은 건드리지 않는다(다른 소비자 보호). 읽기 전용 · 실패해도 비치명(build_daily_lists.py 끝에서 호출).
"""
import json, sqlite3, sys
from datetime import datetime
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
W3M = 0.3          # 'le_a 순위 + 3개월↓ 0.3' (research 2026-09-30) — 바꾸려면 새 컬럼으로
LOOK = 63          # 3개월 = 63거래일 (v30 return_3m_% 와 동일)
TOP_EXTRA = 20


def main():
    import leaderboard as lb
    src = HERE / "docs" / "hist" / "le_a.json"
    base = json.loads(src.read_text(encoding="utf-8"))
    close, _ = lb.load_ohlcv()
    dates = list(close.index); didx = {d: i for i, d in enumerate(dates)}; last = close.iloc[-1]
    con = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    S = pd.read_sql("SELECT run_id, market, ticker, wu_score AS score FROM wu_scores WHERE model_id='le_a'", con)
    con.close()
    S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str); S["market"] = S.market.str.lower()
    names = {}
    try:
        lc = json.loads((HERE.parent / "dh-q7m3k-data" / "listing_cache.json").read_text(encoding="utf-8"))
        names = {str(r["code"]).zfill(6): r.get("name", "") for r in lc.get("rows", [])}
    except Exception:
        pass
    for d in base["days"]:
        for r in d["rows"]:
            names[r["ticker"]] = r.get("name") or names.get(r["ticker"], "")
    days = []
    for d in base["days"]:
        rid, dt = d["run_id"], d["date"]
        t = didx.get(dt)
        g = S[S.run_id == rid].dropna(subset=["score"])
        if t is None or g.empty:
            continue
        shown = {(r["market"], r["ticker"]) for r in d["rows"]}
        rows, extra = {}, []
        for mk, gm in g.groupby("market"):
            gm = gm.copy()
            tk = gm.ticker.values
            c0 = close.iloc[t].reindex(tk).values
            cb = close.iloc[t - LOOK].reindex(tk).values if t >= LOOK else [float("nan")] * len(tk)
            gm["r63"] = (pd.Series(c0, index=gm.index) / pd.Series(cb, index=gm.index) - 1) * 100
            lp = gm.score.rank(pct=True); rp = gm.r63.rank(pct=True)
            gm["le3m"] = lp + W3M * (1 - rp.fillna(0.5))
            gm["le_rank"] = gm.score.rank(ascending=False, method="first").astype(int)
            gm["le3m_rank"] = gm.le3m.rank(ascending=False, method="first").astype(int)
            gm["r3m_low"] = gm.r63.rank(ascending=True, method="first")
            keep = gm[(gm.le_rank <= 60) | (gm.le3m_rank <= 30) | (gm.r3m_low <= 30)]
            for x in keep.itertuples(index=False):
                rows[f"{mk}:{x.ticker}"] = [int(x.le3m_rank), round(float(x.le3m), 3),
                                            (int(x.r3m_low) if x.r3m_low == x.r3m_low else None),
                                            (round(float(x.r63), 1) if x.r63 == x.r63 else None), int(x.le_rank)]
            for x in gm[gm.le3m_rank <= TOP_EXTRA].itertuples(index=False):
                if (mk, x.ticker) in shown:
                    continue
                p0 = close.iloc[t].get(x.ticker); p1 = last.get(x.ticker)
                p0 = float(p0) if (p0 is not None and p0 == p0) else None
                p1 = float(p1) if (p1 is not None and p1 == p1) else None
                extra.append({"rank": int(x.le_rank), "ticker": x.ticker, "name": names.get(x.ticker, ""), "market": mk,
                              "score": round(float(x.score), 2), "px_then": p0, "px_now": p1,
                              "chg_pct": round((p1 / p0 - 1) * 100, 1) if (p0 and p1 and p0 > 0) else None,
                              "rank_today": None, "extra": True})
        days.append({"run_id": rid, "date": dt, "rows": rows, "extra": extra})
    payload = {"asof": dates[-1], "generated": datetime.now().isoformat(timespec="seconds"), "w3m": W3M, "look": LOOK,
               "fields": ["le3m_rank", "le3m_score", "r3m_low_rank", "r63d_%", "le_rank_full"],
               "note": "le.html 지난 탭용 3개월 관측(표시 전용) · le3m = le 백분위 + 0.3×(1−3개월 백분위)", "days": days}
    (HERE / "docs" / "hist" / "le_a_3m.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ docs/hist/le_a_3m.json — {len(days)}일 · 일당 extra {sum(len(x['extra']) for x in days) / max(1, len(days)):.1f}행")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠ le_obs_3m 생성 실패(비치명): {e}")
        sys.exit(1)
