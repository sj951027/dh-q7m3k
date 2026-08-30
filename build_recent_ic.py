# -*- coding: utf-8 -*-
"""
build_recent_ic.py — '요즘 폼' 관측 패널 → docs/recent_ic.json (표시 전용)
==============================================================================
리더보드의 누적 IC 는 §11 판정용(전체 평균)이라 최근 변화가 한 박자 늦게 보인다.
이 패널은 같은 프로토콜로 계산한 앵커별 IC 중 **최근 K=10개 마감 앵커만의 평균**을
전체 평균과 나란히 제공 — "요즘 뭐가 잘 맞나"의 직접 표시 (2026-08-30 사용자 요청).

⚠ 관측 전용 — 판정 무관(정본은 leaderboard.py·§11). 최근 10앵커는 창이 겹치는 소표본이라
노이즈가 크다: 서열·채택 판단 금지, '식었나/달아올랐나'의 방향 참고까지만.
leaderboard.py 함수 재사용(게이트·앵커·dedupe·IC 동일 규약), 읽기 전용·비치명.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
K = 10
TRACKS = [  # (트랙, 테이블, 점수컬럼)  ※ large(h60~120)는 h20 부적합이라 제외
    ("v3", "v3_scores", "final_score_v3"),
    ("lowvol", "lowvol_scores", "lowvol_score"),
    ("wu", "wu_scores", "wu_score"),
]


def main():
    import sys
    sys.path.insert(0, str(HERE))
    import leaderboard as lb
    close, _ = lb.load_ohlcv()
    dates = list(close.index); N = len(dates)
    con = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates)
    excl = partial | dbl
    out = {"status": "ok", "generated": datetime.now().isoformat(timespec="seconds"),
           "k": K, "h": lb.H_PRIMARY, "models": []}
    for track, tb, col in TRACKS:
        for (mid,) in con.execute(f"SELECT DISTINCT model_id FROM {tb}"):
            S = pd.read_sql(f"SELECT run_id,market,ticker,{col} AS score FROM {tb} "
                            "WHERE model_id=?", con, params=(mid,))
            S["ticker"] = S.ticker.astype(str); S["run_id"] = S.run_id.astype(str)
            keep = lb.dedupe_by_anchor(S, didx, excl, reg=lb.REG_DATE.get(mid))
            ics = {}
            for rid, g in S.groupby("run_id"):
                if rid in excl or rid not in keep:
                    continue
                t = didx.get(rid)
                if t is None or t + lb.ENTRY_LAG + lb.H_PRIMARY >= N:
                    continue
                fwd = close.iloc[t + lb.ENTRY_LAG + lb.H_PRIMARY] / close.iloc[t + lb.ENTRY_LAG] - 1
                jump = close.pct_change(fill_method=None).abs()\
                    .iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + lb.H_PRIMARY + 1].max()
                fwd = fwd.where(jump <= lb.JUMP_CAP)
                vals = []
                for mk, gm in g.groupby("market"):
                    sc = gm.set_index("ticker")["score"].astype(float)
                    b = fwd.reindex(sc.index)
                    m = sc.notna() & b.notna()
                    if m.sum() < lb.MIN_GROUP or sc[m].nunique() < 3 or b[m].nunique() < 3:
                        continue
                    vals.append(np.corrcoef(sc[m].rank(), b[m].rank())[0, 1])
                if vals:
                    ics[rid] = float(np.mean(vals))
            sr = pd.Series(ics).sort_index()
            if len(sr) < 5:      # 마감 앵커 5개 미만이면 표시 생략(신생 모델)
                continue
            recent = sr.iloc[-K:]
            out["models"].append({
                "track": track, "model": mid,
                "ic_all": round(float(sr.mean()), 4), "n_all": len(sr),
                "ic_recent": round(float(recent.mean()), 4), "n_recent": len(recent),
                "recent_span": f"{recent.index.min()}~{recent.index.max()}",
                "pos_recent": round(float((recent > 0).mean()), 2),
            })
    out["models"].sort(key=lambda x: (x["track"], -x["ic_recent"]))
    (HERE / "docs" / "recent_ic.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"💾 docs/recent_ic.json — 모델 {len(out['models'])}개 · 최근 {K}앵커 vs 전체")
    for m in out["models"]:
        arrow = "▲" if m["ic_recent"] > m["ic_all"] + 0.01 else ("▼" if m["ic_recent"] < m["ic_all"] - 0.01 else "→")
        print(f"  {m['track']:6s} {m['model']:9s} 요즘 {m['ic_recent']:+.3f} vs 전체 {m['ic_all']:+.3f} {arrow}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠ recent_ic 생성 실패(비치명): {e}")
