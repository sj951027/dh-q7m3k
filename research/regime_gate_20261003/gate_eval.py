# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/regime_gate_20261003/ 에서 실행. 읽기 전용.
"""gate_eval.py — 국면 게이트(코스닥 전일 종가 < 20일선이면 신규 진입 0% / 50%)를 돈 잣대에 얹었을 때 (2026-10-03, 사전관찰 — 판정 아님)

PREREGISTER_regime_gate.md(초안)의 계산 도구. 등록 뒤에는 관찰기간 앵커만 쓴다(--start). 지금은 등록 전 참고창.
  · 바스켓·앵커·게이트 = build_scoreboard.observe(시장별 상위10 · 다음날 종가 매수 · 40일 보유 · 등록 후 앵커)
  · 신호 = 앵커 거래일(스크리너가 도는 날) KOSDAQ 종가 < SMA20 → 다음날 진입을 줄인다(0% 또는 50%). 보유 중인 것은 건드리지 않는다.
  · 잣대 ① 절대: 바스켓 40일 수익(%) 평균 — 게이트로 뺀 몫은 현금(0%)   ② 상대: 바스켓 − 시장 동일가중(%p), 뺀 몫은 시장 수익 0 으로 두지 않고 '참여한 날만' 평균
  · 비겹침 40일 코호트 수를 같이 적는다. 코호트 <2 면 구간 산출 불가.
"""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]; sys.path.insert(0, str(REPO))
import leaderboard as lb, build_scoreboard as bs

MODELS = ("v30", "lv_b", "sv_a")
VARIANTS = {"상시": 1.0, "게이트50%": 0.5, "게이트0%": 0.0}


def block_ci(x, h=40, k=4000, seed=7):
    x = np.asarray(x, float); n = len(x)
    if n < 2: return [float("nan")] * 2
    rng = np.random.default_rng(seed); nb = int(np.ceil(n / h)); res = []
    for _ in range(k):
        st = rng.integers(0, max(n - h + 1, 1), nb); res.append(np.concatenate([x[s:s + h] for s in st])[:n].mean())
    return [float(np.percentile(res, 2.5)), float(np.percentile(res, 97.5))]


def main(start=None):
    close, mktmap = lb.load_ohlcv(); dates = list(close.index); mk = pd.Series(mktmap).str.lower()
    con = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    lbj = json.loads((REPO / "docs/leaderboard.json").read_text(encoding="utf-8"))
    reg_json = json.loads((REPO / "docs/models_registry.json").read_text(encoding="utf-8"))
    regime = bs.load_regime(dates)
    rows = []
    for m in lbj["models"]:
        if m["model"] not in MODELS: continue
        d = bs.observe(con, m, close, mk, dates, didx, excl, reg_json)["_df"]
        d = d[d.done.astype(bool)].copy()
        if start: d = d[d.date >= start]
        if not len(d): continue
        d["below"] = d.date.map(lambda x: regime.loc[x] == "약세" if x in regime.index else False)
        d["t"] = d.date.map(didx); coh = ((d.t - d.t.min()) // 40).nunique()
        for nm, w in VARIANTS.items():
            part = np.where(d.below, w, 1.0)                       # 참여 비중
            abs_ret = (d.ret40 * part).values                      # 뺀 몫은 현금 0%
            rel = (d.ret40 - d.bench40).values; rel_in = rel[part > 0]
            rows.append(dict(model=m["model"], variant=nm, n=len(d), cohorts=int(coh), below_share=float(d.below.mean()),
                             abs_mean=float(abs_ret.mean()), abs_ci=block_ci(abs_ret), abs_pos=float((abs_ret > 0).mean()),
                             rel_mean=float(rel_in.mean()) if len(rel_in) else float("nan"), n_in=int(len(rel_in))))
    con.close()
    df = pd.DataFrame(rows)
    print(f"참고창(등록 후·40일 완결 앵커){' · 시작 '+start if start else ''} · 신호 = 앵커일 KOSDAQ 종가 < 20일선 → 다음날 신규 진입 축소")
    print(f"{'모델':<6}{'변형':<9}{'n':>4}{'코호트':>5}{'아래비율':>7} {'절대40일%':>9} {'블록CI':>18} {'양수':>5} {'참여일 초과%p':>12}{'참여n':>6}")
    for _, x in df.iterrows():
        print(f"{x.model:<6}{x.variant:<9}{x.n:>4}{x.cohorts:>5}{x.below_share:>7.0%} {x.abs_mean:>+9.2f} [{x.abs_ci[0]:+.2f},{x.abs_ci[1]:+.2f}] {x.abs_pos:>5.0%} {x.rel_mean:>+12.2f}{x.n_in:>6}")
    df.to_csv(HERE / "gate_eval.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--start", default=None, help="관찰기간 시작(앵커일 YYYYMMDD)")
    main(ap.parse_args().start)
