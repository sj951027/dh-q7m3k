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

    # 3) 요소별 IC (시장초과 수익 기준)
    factors_out = []
    for fac in ["final_score"] + [c for c in vs.FACTOR_COLUMNS
                                  if c in FACTOR_LABELS and c != "final_score"]:
        rec = {"name": fac, "label": FACTOR_LABELS.get(fac, fac), "ic": {}, "n": {}}
        for h in CARD_HORIZONS:
            ic, n = vs.spearman_ic(rets, fac, f"exret_{h}d")
            rec["ic"][str(h)] = ic
            rec["n"][str(h)] = n
        factors_out.append(rec)

    # 4) 헤드라인 (final_score, 가장 짧은 기간 우선)
    head_ic = head_n = head_h = None
    for h in CARD_HORIZONS:
        ic, n = vs.spearman_ic(rets, "final_score", f"exret_{h}d")
        if ic is not None and n >= MIN_N:
            head_ic, head_n, head_h = ic, n, h
            break
    # 구간 격차(상위1/3 - 하위1/3)
    spread = None
    if head_h is not None:
        qt = vs.quantile_table(rets, "final_score", f"exret_{head_h}d", q=3)
        if qt is not None and "Q3" in qt.index and "Q1" in qt.index:
            spread = round(float(qt.loc["Q3", "mean"] - qt.loc["Q1", "mean"]), 2)

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
            "spread": spread,
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
        "ic5": next((f["ic"]["5"] for f in factors_out if f["name"] == "final_score"), None),
        "ic20": next((f["ic"]["20"] for f in factors_out if f["name"] == "final_score"), None),
    })
    hist = hist[-120:]   # 최근 120개만
    HISTORY_PATH.write_text(json.dumps(hist, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    if head_ic is not None:
        print(f"   ✅ final_score IC(+{head_h}일) = {head_ic:+.3f}  "
              f"(N={head_n})  {payload['headline']['verdict']}")
    else:
        print(f"   ℹ️  아직 표본 부족 — 카드는 '데이터 쌓는 중'으로 표시 "
              f"({n_dates}일치)")
    print(f"   💾 docs/ic_summary.json 저장")


if __name__ == "__main__":
    main()
