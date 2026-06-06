# -*- coding: utf-8 -*-
"""
compare_models.py — 챔피언(v30) vs 챌린저(v31a~) 성능 비교
==========================================================
모든 등록 모델(v3_rescore.MODELS)을 *같은* forward-return 패널·*같은* 방식으로
채점해 나란히 보여준다. 두 종류 지표를 함께 본다:

  (1) 전체 universe IC  — final_score_v3(연속 점수)의 날짜·시장별 Spearman 평균.
        → E3(수급가중)·E5(섹터중립)처럼 '점수/순위'를 바꾸는 챌린저가 여기서 드러남.
  (2) BUY/WAIT 수익률   — 추천(BUY∪WAIT) 종목의 평균 시장초과수익 + 개수.
        → E2(반전게이트)·E4(유동성)처럼 '버킷 멤버십'을 바꾸는 챌린저가 여기서 드러남.

forward return 은 history.db 의 종가 패널에서 구한다(네트워크 불필요).
이 스크립트는 history.db 전체를 각 모델 스펙으로 재계산한다(스펙은 고정이므로 정당한 백테스트).
'그날그날 얼린' 진짜 OOS 기록은 shadow_run.py 가 {model}_archive/ 에 매일 쌓는다.

실행:  python compare_models.py            # 등록된 전 모델
       python compare_models.py --models v30 v31a v31c
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import v3_backtest as bt
import v3_rescore as v3

HERE = Path(__file__).resolve().parent
HORIZONS = [1, 2, 3, 5]


def scored(spec):
    """history.db 전 run×market 을 주어진 스펙으로 재점수화."""
    allruns = v3.load_runs()
    frames = []
    for (rid, mkt), sub in allruns.groupby(["run_id", "market"]):
        rs = v3.rescore(sub, run_id=str(rid), market=str(mkt), spec=spec)
        frames.append(rs[["run_id", "market", "ticker",
                          "final_score_v3", "bucket", "main_candidate"]])
    return pd.concat(frames, ignore_index=True)


def bucket_returns(picks, fwd, horizons, buckets=("BUY", "WAIT")):
    """추천(BUY∪WAIT) 종목의 평균 시장초과수익(%)과 개수."""
    sel = picks[picks["bucket"].isin(buckets)]
    out = {}
    for h in horizons:
        f = fwd[fwd["h"] == h][["run_id", "ticker", "exret"]]
        m = sel.merge(f, on=["run_id", "ticker"], how="inner")
        out[h] = (round(float(m["exret"].mean()) * 100, 3) if len(m) else None, int(len(m)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=list(v3.MODELS.keys()),
                    help="비교할 모델 id (기본: 전부)")
    args = ap.parse_args()

    panel, all_runs, tk_mkt = bt.price_panel()
    runs = bt.filter_active_runs(panel, all_runs)
    fwd = bt.forward_returns(panel, runs, tk_mkt, HORIZONS)
    print(f"활성 거래일 {len(runs)}개 · horizon {HORIZONS}\n")

    summary = {}
    ic_table, buy_table, bw_table = {}, {}, {}
    for mid in args.models:
        spec = v3.MODELS[mid]
        picks = scored(spec)
        ic = bt.cross_sectional_ic(picks, fwd, "final_score_v3", HORIZONS)
        ic_by_h = {int(r["horizon"]): r for _, r in ic.iterrows()}
        buy = bucket_returns(picks, fwd, HORIZONS, buckets=("BUY",))
        bw = bucket_returns(picks, fwd, HORIZONS, buckets=("BUY", "WAIT"))
        ic_table[mid], buy_table[mid], bw_table[mid] = ic_by_h, buy, bw
        summary[mid] = {
            "label": spec["label"],
            "full_universe_IC": {str(h): (None if ic_by_h.get(h) is None
                                          else ic_by_h[h]["mean_IC"]) for h in HORIZONS},
            "buy_only_exret_pct": {str(h): buy[h][0] for h in HORIZONS},
            "buy_only_n": {str(h): buy[h][1] for h in HORIZONS},
            "buy_wait_exret_pct": {str(h): bw[h][0] for h in HORIZONS},
            "buy_wait_n": {str(h): bw[h][1] for h in HORIZONS},
        }

    hdr = "  " + f"{'모델':<26}" + "".join(f"+{h}일".rjust(10) for h in HORIZONS)

    # ── 출력 (1) 전체 universe IC ──
    print("="*74)
    print("(1) 전체 universe IC  —  final_score_v3 의 날짜·시장별 평균 Spearman")
    print("    (E3 수급가중 · E5 섹터중립 처럼 '순위'를 바꾸는 챌린저가 여기서 드러남)")
    print("="*74)
    print(hdr)
    for mid in args.models:
        row = "  " + f"{v3.MODELS[mid]['label']:<26}"
        for h in HORIZONS:
            r = ic_table[mid].get(h)
            row += (f"{r['mean_IC']:+.4f}".rjust(10) if r is not None else "—".rjust(10))
        print(row)

    def _ret_block(title, sub, table):
        print("\n" + "="*74)
        print(title)
        print(sub)
        print("="*74)
        print(hdr)
        for mid in args.models:
            row = "  " + f"{v3.MODELS[mid]['label']:<26}"
            for h in HORIZONS:
                val, n = table[mid][h]
                row += (f"{val:+.2f}({n})".rjust(10) if val is not None else "—".rjust(10))
            print(row)

    # ── 출력 (2) BUY 전용 ── (E2 반전게이트가 BUY 멤버십을 바꾸므로 여기서 드러남)
    _ret_block("(2) BUY 전용 평균 시장초과수익(%)  [괄호=표본수]",
               "    (E2 반전게이트 · E4 유동성 — 표본이 작으니 추세로만; 단일일 과신 금지)",
               buy_table)
    # ── 출력 (3) BUY+WAIT ── (E4 유동성이 넓은 추천군을 바꾸므로 여기서 드러남)
    _ret_block("(3) BUY+WAIT 평균 시장초과수익(%)  [괄호=표본수]",
               "    (E4 유동성처럼 추천군 전체를 바꾸는 챌린저가 여기서 드러남)",
               bw_table)

    print("\n[주의] 활성 거래일이 적으면 모델 간 차이는 대부분 노이즈다.")
    print("       수십 거래일(이상적으로 60+) 쌓인 뒤, 사전에 정한 승격 기준으로 판단할 것.")
    print("       또 valuation_*.csv 없는 과거 회차는 value_score=0 으로 채점됨(누적 시 해소).")

    out = HERE / "docs" / "model_compare.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"horizons": HORIZONS, "models": summary,
                               "n_active_runs": len(runs)},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n요약 저장: {out}")


if __name__ == "__main__":
    main()
