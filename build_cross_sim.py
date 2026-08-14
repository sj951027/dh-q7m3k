# -*- coding: utf-8 -*-
"""
build_cross_sim.py — 트랙 간 '공통 잣대' 모의계좌 → docs/cross_sim.json (표시 전용)
====================================================================================
리더보드 하단 '공통 잣대 모의계좌' 섹션의 데이터 생성기 (2026-08-14 사용자 결정).
원리(research/cross_track_compare.py와 동일): 같은 기간 · 매일 점수 상위 20 동일가중 ·
ENTRY_LAG=1 · 공통 벤치마크(전체상장 거래대금≥5억 EW, KOSPI 병기)로 모의 계좌 비교.

⚠ 관측 전용 — §11 판정과 무관(판정 도구 leaderboard.py 는 일절 안 건드림).
  거래비용 0 · 매일 전량 리밸런스 가정. 실패해도 파이프라인 비치명.
등록일(REG_DATE) 이후 forward 점수만 사용. 패널:
  A = 주력 공통창(v30·lv_a·lv_b·mom_a·wu_a, 20260702~)
  B = 전 모델 공통창(+sv_a·qs_a, 20260724~)
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OHLCV = HERE.parent / "dh-q7m3k-data" / "ohlcv.db"
TOPN = 20

MODELS = [
    ("v30",   "v3_scores",     "final_score_v3", "v30",   "20260606"),
    ("lv_b",  "lowvol_scores", "lowvol_score",   "lv_b",  "20260625"),
    ("lv_a",  "lowvol_scores", "lowvol_score",   "lv_a",  "20260625"),
    ("mom_a", "lowvol_scores", "lowvol_score",   "mom_a", "20260627"),
    ("wu_a",  "wu_scores",     "wu_score",       "wu_a",  "20260702"),
    ("sv_a",  "wu_scores",     "wu_score",       "sv_a",  "20260715"),
    ("qs_a",  "wu_scores",     "wu_score",       "qs_a",  "20260723"),
]
PANELS = [
    ("주력 공통창 (7/02~)", ["v30", "lv_b", "lv_a", "mom_a", "wu_a"], "20260702"),
    ("전 모델 공통창 (7/24~ · 짧음)", ["v30", "lv_b", "lv_a", "mom_a", "wu_a", "sv_a", "qs_a"], "20260724"),
]


def main():
    hc = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    oc = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    scores = {}
    for name, tbl, col, mid, reg in MODELS:
        scores[name] = pd.read_sql(
            f"SELECT run_id, ticker, {col} AS s FROM {tbl} WHERE model_id=? AND run_id>=?",
            hc, params=(mid, reg))
    px = pd.read_sql("SELECT ticker,date,close,volume,change_pct FROM daily_ohlcv "
                     "WHERE date>='20260601'", oc)
    dts = sorted(px.date.unique())
    R = px.pivot_table(index="date", columns="ticker", values="change_pct", aggfunc="last").reindex(dts)
    C = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").reindex(dts)
    V = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(dts)
    amt20 = (C * V).rolling(20, min_periods=10).mean() / 1e8
    K = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSPI'",
                    oc).set_index("date")["close"].reindex(dts).ffill()

    def daily_series(fn_top, start, end):
        out = []
        for t in [d for d in dts if start <= d <= end]:
            i = dts.index(t)
            if i + 1 >= len(dts):
                continue
            nxt = dts[i + 1]
            sel = fn_top(t)
            if sel is None:
                out.append((nxt, np.nan))
            else:
                out.append((nxt, float(R.loc[nxt, sel].astype(float).mean(skipna=True))))
        s = pd.Series(dict(out)).sort_index()
        return s.ffill(limit=2).fillna(0)

    def stats(s):
        nav = (1 + s).cumprod()
        return dict(cum=round(float(nav.iloc[-1] - 1) * 100, 1),
                    vol=round(float(s.std()) * 100, 2),
                    mdd=round(float((nav / nav.cummax() - 1).min()) * 100, 1),
                    n=int(len(s)))

    panels = []
    end = dts[-2]
    for label, group, start in PANELS:
        bench = daily_series(lambda t: amt20.loc[t][amt20.loc[t] >= 5].index.intersection(R.columns),
                             start, end)
        k_days = [d for d in dts if d >= start]
        kospi_cum = round(float(K.iloc[-1] / K.loc[k_days[0]] - 1) * 100, 1)
        rows = []
        for m in group:
            df = scores[m]

            def top(t, df=df):
                sub = df[df.run_id == t]
                if len(sub) == 0:
                    return None
                return [c for c in sub.nlargest(TOPN, "s").ticker if c in R.columns]
            s = daily_series(top, start, end)
            st = stats(s)
            common = s.index.intersection(bench.index)
            st["exc_bp"] = round(float((s.reindex(common) - bench.reindex(common)).mean()) * 10000, 1)
            st["model"] = m
            rows.append(st)
        rows.sort(key=lambda r: -r["cum"])
        panels.append(dict(label=label, start=start, end=end,
                           bench_cum=round(float(((1 + bench).cumprod().iloc[-1] - 1) * 100), 1),
                           kospi_cum=kospi_cum, rows=rows))
    out = dict(status="ok", generated=datetime.now().isoformat(timespec="seconds"),
               topn=TOPN, panels=panels)
    (HERE / "docs" / "cross_sim.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"💾 docs/cross_sim.json 생성 — 패널 {len(panels)}개, 기준일 {end}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠ cross_sim 생성 실패(비치명): {e}")
