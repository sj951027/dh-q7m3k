# -*- coding: utf-8 -*-
"""
build_alpha_beta.py — 알파/베타 상시 관측 패널 → docs/alpha_beta.json (표시 전용)
==============================================================================
"요즘 수익이 실력(알파)인지 장 덕(베타)인지"를 매일 갱신한다 (2026-08-29 도입,
근거: research/RESEARCH_forward_levers_20260829.md B — §14-4 백로그 2번 '측정 인프라').

각 모델의 상위20 EW 일수익(등록일 이후, ENTRY_LAG=1, 비용 0)을 전종목(amt20≥5억) EW
벤치마크에 회귀: r = α + β·bench. 최근 W=40 유효일 롤링.
  · β = 장을 따라 움직인 몫 (1이면 시장과 동일 노출)
  · α = 장과 무관하게 종목 선택이 벌어준 일평균 몫 (t<2 면 아직 우연과 구분 안 됨)

⚠ 관측 전용 — §11 판정 무관·비용 0·짧은 창. leaderboard.py·점수 테이블 일절 무접촉(mode=ro).
실패해도 파이프라인 비치명. 대상: 트랙 대표 v30·lv_b·sv_a (wu_a 는 2026-09-04 은퇴).
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OHLCV = HERE.parent / "dh-q7m3k-data" / "ohlcv.db"
TOPN, WINDOW, HIST_KEEP = 20, 40, 60
MODELS = [
    ("v30",  "v3_scores",     "final_score_v3", "20260606"),
    ("lv_b", "lowvol_scores", "lowvol_score",   "20260625"),
    ("sv_a", "wu_scores",     "wu_score",       "20260715"),   # [2026-09-04] wu_a 은퇴 → wu 트랙 대표 sv_a
]


def main():
    hc = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    oc = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    px = pd.read_sql("SELECT ticker,date,close,volume,change_pct FROM daily_ohlcv "
                     "WHERE date>='20260501'", oc)
    px["ticker"] = px.ticker.astype(str)
    dts = sorted(px.date.unique())
    didx = {d: i for i, d in enumerate(dts)}
    R = px.pivot_table(index="date", columns="ticker", values="change_pct", aggfunc="last").reindex(dts)
    C = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").reindex(dts)
    V = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(dts)
    amt20 = (C * V).rolling(20, min_periods=10).mean() / 1e8

    bench = {}
    for t in dts:
        i = didx[t]
        if i + 1 >= len(dts):
            continue
        sel = amt20.loc[t][amt20.loc[t] >= 5].index.intersection(R.columns)
        bench[dts[i + 1]] = float(R.loc[dts[i + 1], sel].mean(skipna=True))
    bench = pd.Series(bench).sort_index()

    out = {"status": "ok", "generated": datetime.now().isoformat(timespec="seconds"),
           "window": WINDOW, "asof": dts[-1], "models": {}, "history": {}}
    for name, tb, col, reg in MODELS:
        S = pd.read_sql(f"SELECT run_id,ticker,{col} s FROM {tb} WHERE model_id=? AND run_id>=?",
                        hc, params=(name, reg))
        S["ticker"] = S.ticker.astype(str); S["run_id"] = S.run_id.astype(str)
        rets = {}
        for rid, g in S.groupby("run_id"):
            if rid not in didx or didx[rid] + 1 >= len(dts):
                continue
            sel = [c for c in g.nlargest(TOPN, "s").ticker if c in R.columns]
            if sel:
                rets[dts[didx[rid] + 1]] = float(R.loc[dts[didx[rid] + 1], sel].mean(skipna=True))
        r = pd.Series(rets).sort_index()
        com = r.index.intersection(bench.index)
        r, b = r[com], bench[com]
        hist = []
        for k in range(len(r)):
            if k + 1 < min(WINDOW, 15):     # 최소 15일부터 산출(초기 구간)
                continue
            rw = r.iloc[max(0, k + 1 - WINDOW):k + 1]
            bw = b.iloc[max(0, k + 1 - WINDOW):k + 1]
            vb = np.var(bw, ddof=1)
            if vb <= 0:
                continue
            beta = float(np.cov(rw, bw, ddof=1)[0, 1] / vb)
            alpha = float(rw.mean() - beta * bw.mean())
            hist.append({"d": r.index[k], "beta": round(beta, 3),
                         "alpha_d_pct": round(alpha * 100, 3)})
        if not hist:
            continue
        rw = r.iloc[-WINDOW:]; bw = b.iloc[-WINDOW:]
        beta = hist[-1]["beta"]; alpha = hist[-1]["alpha_d_pct"] / 100
        resid = rw - (alpha + beta * bw)
        a_t = float(alpha / (resid.std(ddof=2) / np.sqrt(len(rw)))) if len(rw) > 3 else None
        cum = float(((1 + rw).cumprod().iloc[-1] - 1) * 100)
        bcum = float(((1 + bw).cumprod().iloc[-1] - 1) * 100)
        beta_pp = round(beta * bcum, 1)     # 근사(선형) — 표시용
        out["models"][name] = {
            "n": len(rw), "beta": beta, "alpha_d_pct": hist[-1]["alpha_d_pct"],
            "alpha_t": round(a_t, 2) if a_t is not None else None,
            "cum_pct": round(cum, 1), "bench_cum_pct": round(bcum, 1),
            "beta_cum_pp": beta_pp, "alpha_cum_pp": round(cum - beta_pp, 1),
        }
        out["history"][name] = hist[-HIST_KEEP:]
    (HERE / "docs" / "alpha_beta.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"💾 docs/alpha_beta.json — asof {out['asof']} · " +
          " | ".join(f"{m} β{v['beta']:.2f} α{v['alpha_d_pct']:+.2f}%/일(t{v['alpha_t']})"
                     for m, v in out["models"].items()))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠ alpha_beta 생성 실패(비치명): {e}")
