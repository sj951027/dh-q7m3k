#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compute_ic.py — 점수 적중도(IC)를 계산해 대시보드 카드용 JSON으로 저장
=====================================================================
history.db에 쌓인 추천 종목들이 '이후에 실제로 올랐는지'를 측정해서,
폰 대시보드(docs/)에 "점수 적중도" 카드로 띄울 데이터를 만든다.

  - validate_scores.py 의 계산 로직을 그대로 재사용 (단일 출처)
  - 결과: docs/ic_summary.json  (대시보드가 읽음)
  - 추세: docs/ic_history.json  (실행할 때마다 한 줄씩 누적 → 시간에 따른 변화)

네트워크(시세 조회)가 안 되거나 데이터가 부족해도 안전하게 종료한다
(기존 json을 유지하거나 'pending' 상태로 기록 — 대시보드는 안 깨짐).

단독 실행:  python compute_ic.py
launcher가 스크리너 다음에 자동으로 호출하기도 한다.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE / "docs"
SUMMARY_PATH = DOCS / "ic_summary.json"
HISTORY_PATH = DOCS / "ic_history.json"

# 대시보드 카드용 짧은 라벨
FACTOR_LABELS = {
    "final_score_v3": "최종점수(v3)",
    "final_score": "최종점수",
    "oversold_score": "과매도",
    "acc_score": "매집",
    "trend_score": "추세전환",
    "supply_score": "수급",
    "fundamental_score": "펀더멘털",
    "ocf_score": "현금흐름",
    "momentum_score": "모멘텀",
    # 관측 후보(데이터 있는 것만 카드에 노출). 내부자/소각은 catalyst 누적 후 추가.
    "smartmoney_score": "스마트머니",
    "roe_value": "ROE",
}
CARD_HORIZONS = [5, 20]   # 카드에 보여줄 기간 (60일은 데이터 쌓인 뒤)
MIN_N = 10                # 이 표본 미만이면 '데이터 쌓는 중'으로 표시
IC_TOP_N = 50             # 시장·날짜별 상위 N개만 측정 (속도 + 실제 관심권)
IC_MAX_DATES = 40         # 최근 N개 거래일만 (최신 시장 반영 + 속도)


def _write_pending(reason):
    """계산 불가 시: 기존 summary가 있으면 두고, 없으면 pending 기록."""
    DOCS.mkdir(exist_ok=True)
    if SUMMARY_PATH.exists():
        print(f"   ℹ️  IC 계산 보류({reason}) — 기존 카드 유지")
        return
    payload = {
        "status": "pending",
        "reason": reason,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": "데이터를 더 쌓는 중입니다.",
    }
    SUMMARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(f"   ℹ️  IC 카드: 데이터 쌓는 중 ({reason})")


def _load_v3_scores():
    """v3_archive 의 모든 v3_*.csv 에서 (run_id, market, ticker)→final_score_v3.

    history.db(stage3_final)에는 v3 점수가 없으므로, 헤드라인/구간격차를 v3로
    계산하려면 여기서 끌어와 rets 에 합친다. 파일이 없으면 None(→ v2.6 폴백).
    """
    import re
    import pandas as pd
    v3dir = HERE / "v3_archive"
    if not v3dir.exists():
        return None
    files = sorted(v3dir.glob("v3_*.csv"))
    # 최근 IC_MAX_DATES 개 run_id 의 파일만 읽는다(보관 파일이 수백 개로 늘어도 빠르게).
    def _rid(p):
        m = re.search(r"_(\d{8})\.csv$", p.name)
        return m.group(1) if m else ""
    recent_rids = sorted({_rid(p) for p in files if _rid(p)})[-IC_MAX_DATES:]
    files = [p for p in files if _rid(p) in recent_rids]
    frames = []
    for f in files:
        try:
            d = pd.read_csv(f, usecols=lambda c: c in (
                "run_id", "market", "ticker", "final_score_v3"))
        except Exception:
            continue
        if "final_score_v3" in d.columns:
            frames.append(d)
    if not frames:
        return None
    v = pd.concat(frames, ignore_index=True)
    v["run_id"] = v["run_id"].astype(str)
    v["market"] = v["market"].astype(str)
    v["ticker"] = v["ticker"].astype(str).str.zfill(6)
    v["final_score_v3"] = pd.to_numeric(v["final_score_v3"], errors="coerce")
    v = v.dropna(subset=["final_score_v3"])
    return v.drop_duplicates(["run_id", "market", "ticker"], keep="last")


def main():
    print(f"\n{'━'*64}\n▶  점수 적중도(IC) 계산\n{'━'*64}")
    try:
        import validate_scores as vs
    except Exception as e:
        _write_pending(f"validate_scores 임포트 실패: {e}")
        return

    db = HERE / "history.db"
    if not db.exists():
        _write_pending("history.db 없음")
        return

    # 1) 추천 로드 (속도: 시장·날짜별 상위 N개, 최근 거래일만)
    try:
        picks = vs.load_picks(str(db), top=IC_TOP_N)
    except SystemExit:
        _write_pending("추천 기록 없음")
        return
    except Exception as e:
        _write_pending(f"로드 오류: {e}")
        return

    # [부분실행일 게이트] 그날 스크리너 유니버스(stage3_final)가 정상 중앙값의 30% 미만이면
    #  IC 에서 제외(추천은 top-N 이라 행수가 비슷해 못 걸러지므로 원 유니버스 기준).
    try:
        import sqlite3 as _sq, statistics as _st
        _con = _sq.connect(str(db))
        _rows = _con.execute("SELECT run_id, COUNT(*) FROM stage3_final GROUP BY run_id").fetchall()
        _con.close()
        if _rows:
            _cnt = {str(r[0]): r[1] for r in _rows}
            _floor = _st.median(list(_cnt.values())) * 0.3
            _bad = {rid for rid, n in _cnt.items() if n < _floor}
            if _bad:
                picks = picks[~picks["run_id"].astype(str).isin(_bad)].reset_index(drop=True)
                print("   [게이트] 부분실행일 IC 제외(유니버스<%.0f): %s" % (_floor, sorted(_bad)))
    except Exception as _e:
        print("   (커버리지 게이트 생략: %s)" % _e)

    recent_dates = sorted(picks["run_id"].unique())[-IC_MAX_DATES:]
    picks = picks[picks["run_id"].isin(recent_dates)].reset_index(drop=True)

    n_dates = picks["run_id"].nunique()
    n_picks = len(picks)

    # 2) 이후 수익률 (시세 조회 — 네트워크 필요, 캐시 사용)
    try:
        provider = vs.PriceProvider()
        rets = vs.compute_forward_returns(picks, CARD_HORIZONS, provider)
    except Exception as e:
        _write_pending(f"시세 조회 실패: {e}")
        return

    # 2.5) v3 점수를 rets 에 합치기 (헤드라인을 final_score_v3 로)
    score_main = "final_score"          # 기본(폴백): v2.6
    try:
        v3 = _load_v3_scores()
    except Exception:
        v3 = None
    if v3 is not None and not v3.empty:
        rets["run_id"] = rets["run_id"].astype(str)
        rets["market"] = rets["market"].astype(str)
        rets["ticker"] = rets["ticker"].astype(str).str.zfill(6)
        rets = rets.merge(v3, on=["run_id", "market", "ticker"], how="left")
        if rets["final_score_v3"].notna().sum() >= MIN_N:
            score_main = "final_score_v3"   # v3 점수로 적중도 계산

    # 3) 요소별 IC (시장초과 수익 기준) — 헤드라인 점수 먼저, 그다음 하위 요소들
    factors_out = []
    sub_factors = [c for c in vs.FACTOR_COLUMNS
                   if c in FACTOR_LABELS and c not in ("final_score", "final_score_v3")]
    for fac in [score_main] + sub_factors:
        rec = {"name": fac, "label": FACTOR_LABELS.get(fac, fac), "ic": {}, "n": {}}
        for h in CARD_HORIZONS:
            ic, ng, n = vs.grouped_spearman_ic(rets, fac, f"exret_{h}d")
            rec["ic"][str(h)] = ic
            rec["n"][str(h)] = n
        factors_out.append(rec)

    # 4) 헤드라인 (헤드라인 점수, 가장 짧은 기간 우선)
    head_ic = head_n = head_h = head_groups = None
    for h in CARD_HORIZONS:
        ic, ng, n = vs.grouped_spearman_ic(rets, score_main, f"exret_{h}d")
        if ic is not None and n >= MIN_N:
            head_ic, head_n, head_h, head_groups = ic, n, h, ng
            break
    # 구간 격차(상위1/3 − 하위1/3) — IC와 동일하게 (날짜,시장)별 평균
    spread = None
    if head_h is not None:
        spread, _ = vs.grouped_spread(rets, score_main, f"exret_{head_h}d", q=3)

    status = "ok" if head_ic is not None else "pending"
    payload = {
        "status": status,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n_dates": int(n_dates),
        "n_picks": int(n_picks),
        "horizons": CARD_HORIZONS,
        "headline": {
            "horizon": head_h,
            "ic": head_ic,
            "n": head_n,
            "n_groups": head_groups,
            "spread": spread,
            "score": score_main,
            "verdict": vs.interpret_ic(head_ic) if head_ic is not None else None,
        },
        "factors": factors_out,
        "note": ("표본이 적어 참고용입니다. 거래일마다 쌓일수록 정확해집니다."
                 if n_dates < 20 else "최근 추천 기준 점수 적중도."),
    }

    DOCS.mkdir(exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    # 5) 추세 누적 (한 줄 추가)
    hist = []
    if HISTORY_PATH.exists():
        try:
            hist = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            hist = []
    today = datetime.now().strftime("%Y-%m-%d")
    hist = [h for h in hist if h.get("date") != today]   # 같은 날 갱신
    hist.append({
        "date": today,
        "n_dates": int(n_dates),
        "ic5": next((f["ic"]["5"] for f in factors_out if f["name"] == score_main), None),
        "ic20": next((f["ic"]["20"] for f in factors_out if f["name"] == score_main), None),
    })
    hist = hist[-120:]   # 최근 120개만
    HISTORY_PATH.write_text(json.dumps(hist, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    if head_ic is not None:
        print(f"   ✅ {score_main} IC(+{head_h}일) = {head_ic:+.3f}  "
              f"(날짜·시장별 평균, 그룹 {head_groups}개·N={head_n})  "
              f"{payload['headline']['verdict']}")
    else:
        print(f"   ℹ️  아직 표본 부족 — 카드는 '데이터 쌓는 중'으로 표시 "
              f"({n_dates}일치)")
    print(f"   💾 docs/ic_summary.json 저장")


if __name__ == "__main__":
    main()
