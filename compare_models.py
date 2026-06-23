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
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

import v3_backtest as bt
import v3_rescore as v3

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "history.db"
HORIZONS = [1, 2, 3, 5, 20]   # 20 = §11 주력 호라이즌. 미성숙 구간은 '—'(셀 0).


def _frozen_scores(mid, db_path=DB_PATH):
    """v3_scores(동결 테이블)에서 모델 점수를 읽는다(그날 얼린 원본). 없으면 None."""
    con = sqlite3.connect(str(db_path))
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                           "AND name='v3_scores'").fetchone():
            return None
        df = pd.read_sql("SELECT run_id, market, ticker, final_score_v3, bucket "
                         "FROM v3_scores WHERE model_id=?", con, params=(mid,))
    finally:
        con.close()
    if not len(df):
        return None
    df["run_id"] = df["run_id"].astype(str)
    df["market"] = df["market"].astype(str)
    df["ticker"] = df["ticker"].astype(str)
    df["final_score_v3"] = pd.to_numeric(df["final_score_v3"], errors="coerce")
    df["main_candidate"] = False   # compare_models 미사용(호환용 컬럼)
    return df


def scored(mid, spec, use_frozen=True):
    """모델 점수 확보. 기본 = 동결값(v3_scores) 우선 → 입력 드리프트에 면역(감사 #5).
    동결값이 없으면(미적재 모델 등) 재계산으로 폴백. 반환 = (df, 출처)."""
    if use_frozen:
        fz = _frozen_scores(mid)
        if fz is not None:
            return fz, "frozen"
    allruns = v3.load_runs()
    frames = []
    for (rid, mkt), sub in allruns.groupby(["run_id", "market"]):
        rs = v3.rescore(sub, run_id=str(rid), market=str(mkt), spec=spec)
        frames.append(rs[["run_id", "market", "ticker",
                          "final_score_v3", "bucket", "main_candidate"]])
    return pd.concat(frames, ignore_index=True), "recompute"


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
    ap.add_argument("--since", default=None,
                    help="기준 run_id(YYYYMMDD) 이상만 집계 — §11 OOS 판정용(챌린저 등록일 이후만). "
                         "낚시로 찾은 v31f/v31g 는 발견기간을 빼야 정직함.")
    ap.add_argument("--recompute", action="store_true",
                    help="동결값(v3_scores) 대신 현재 코드로 강제 재계산(디버그/대조용).")
    args = ap.parse_args()

    panel, all_runs, tk_mkt = bt.price_panel()
    runs = bt.filter_active_runs(panel, all_runs)
    fwd = bt.forward_returns(panel, runs, tk_mkt, HORIZONS)

    # --since: 기준 run_id(=picks 산출일) 이상만 집계. forward 수익은 전체 패널로 이미
    # 계산됐으니(미래 종가 사용엔 영향 없음), 기준 run 만 잘라 OOS 구간으로 제한한다.
    # run_id 는 'YYYYMMDD' 라 문자열 비교 = 날짜순.
    if args.since:
        fwd = fwd[fwd["run_id"].astype(str) >= str(args.since)].copy()
    n_eval = int(fwd["run_id"].astype(str).nunique()) if len(fwd) else 0
    if args.since:
        print(f"[--since {args.since}] OOS 기준일 {n_eval}개만 집계 "
              f"(전체 활성 {len(runs)}개 중). h=20d 미성숙이면 셀이 비어 '—' 로 나옴.\n")
    else:
        print(f"활성 거래일 {len(runs)}개 · horizon {HORIZONS}\n")

    summary = {}
    sources = {}
    ic_table, buy_table, bw_table = {}, {}, {}
    for mid in args.models:
        spec = v3.MODELS[mid]
        picks, sources[mid] = scored(mid, spec, use_frozen=not args.recompute)
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

    # 점수 출처(동결 vs 재계산) 표기 — 투명성
    _nf = sum(1 for v in sources.values() if v == "frozen")
    _nr = len(sources) - _nf
    _src = f"점수 출처: 동결값(v3_scores) {_nf}모델"
    if _nr:
        _rec = ",".join(m for m, v in sources.items() if v == "recompute")
        _src += f" · 재계산 폴백 {_nr}모델({_rec})"
    if args.recompute:
        _src += "  [--recompute 강제]"
    print(_src + "\n")

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
    if args.since:
        print(f"       [OOS] --since {args.since} 적용 — 이 표는 등록 이후 구간만. "
              f"이게 §11 판정용 숫자다(발견기간 제외).")

    out = HERE / "docs" / "model_compare.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"horizons": HORIZONS, "models": summary,
                               "n_active_runs": (n_eval if args.since else len(runs)),
                               "since": args.since},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n요약 저장: {out}")


if __name__ == "__main__":
    main()
