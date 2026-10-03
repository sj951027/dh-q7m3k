# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/regime_gate_20261003/ 에서 실행. 읽기 전용. 가설 생성용(판정 아님).
"""regime_split_money.py — 국면(진입 전날 KOSDAQ 종가 vs 20일선)별로 바스켓 절대수익·시장 동일가중·초과를 나란히 (2026-10-03)
질문: 모델 바스켓(시장별 상위10·40일)이 약세 국면에서 '시장보다 덜 빠지는' 것인지 '실제로 버는' 것인지. 상승 국면에서는 시장을 사는 게 나은지.
규칙: build_scoreboard.observe 의 앵커별 ret40/bench40 그대로(등록 후 앵커·40일 완결). 국면 = 앵커 거래일 종가 기준 KOSDAQ > SMA20 (스크리너는 종가 뒤 돌고 다음날 사므로 PIT).
"""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]; sys.path.insert(0, str(REPO))
import leaderboard as lb, build_scoreboard as bs

def main():
    close, mktmap = lb.load_ohlcv(); dates = list(close.index); mk = pd.Series(mktmap).str.lower()
    con = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    lbj = json.loads((REPO / "docs/leaderboard.json").read_text(encoding="utf-8"))
    reg_json = json.loads((REPO / "docs/models_registry.json").read_text(encoding="utf-8"))
    regime = bs.load_regime(dates)
    out = []
    for m in lbj["models"]:
        if m["model"] not in ("v30", "lv_b", "sv_a", "le_a", "lv_a", "mom_a", "sm_a", "qs_a"): continue
        r = bs.observe(con, m, close, mk, dates, didx, excl, reg_json)
        d = r["_df"]; d = d[d.done.astype(bool)].copy()
        d["regime"] = d.date.map(lambda x: regime.loc[x] if x in regime.index else None)
        d["exc"] = d.ret40 - d.bench40
        for rg, g in d.groupby("regime"):
            if len(g) < 4: continue
            out.append(dict(model=m["model"], regime=rg, n=len(g), basket=g.ret40.mean(), market=g.bench40.mean(), exc=g.exc.mean(),
                            exc_ci=bs.boot(g.exc.values), basket_pos=(g.ret40 > 0).mean(), beat_mkt=(g.exc > 0).mean()))
    con.close()
    df = pd.DataFrame(out)
    print("국면 = 앵커일 KOSDAQ 종가 > 20일선('상승') / 아래('약세') · 40일 보유 · 등록 후 앵커")
    print(f"{'모델':<6}{'국면':<5}{'n':>4} {'바스켓40일%':>10} {'시장EW%':>8} {'초과%p':>8} {'초과CI':>18} {'바스켓>0':>8} {'시장이김':>8}")
    for _, x in df.iterrows():
        print(f"{x.model:<6}{x.regime:<5}{x.n:>4} {x.basket:>+10.2f} {x.market:>+8.2f} {x.exc:>+8.2f} [{x.exc_ci[0]:+.2f},{x.exc_ci[1]:+.2f}] {x.basket_pos:>8.0%} {x.beat_mkt:>8.0%}")
    df.to_csv(HERE / "regime_split_money.csv", index=False, encoding="utf-8-sig")

if __name__ == "__main__":
    main()
