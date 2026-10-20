# -*- coding: utf-8 -*-
"""모의 계좌 엔진 합성 테스트 — DB 없음. python test_paper_engine.py"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import paper_engine as pe

fails = 0


def check(name, cond):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        fails += 1


D = [f"2026{(i // 28) + 1:02d}{(i % 28) + 1:02d}" for i in range(120)]   # 120 '거래일'
N = len(D)

print("A. 가격이 안 변하면 NAV 는 비용만큼만 준다")
close = pd.DataFrame({"AAA": 100.0, "BBB": 50.0}, index=D)
picks = {D[0]: ["AAA", "BBB"]}
nav, led = pe.simulate(D, close, picks, slots=40, hold=40, cost=0.005)
# 슬롯 돈 = 1/40 = 0.025, 진입 때 0.25% → 보유 평가 0.025*(1-0.0025)
check("진입 다음날(ENTRY_LAG=1) 포지션 2", nav.loc[1, "n_pos"] == 2 and nav.loc[0, "n_pos"] == 0)
check("진입 직후 NAV = 1 − 0.025×0.0025", math.isclose(nav.loc[1, "nav"], 1 - 0.025 * 0.0025, rel_tol=1e-12))
check("40일 뒤 청산(포지션 0)", nav.loc[41, "n_pos"] == 0 and nav.loc[40, "n_pos"] == 2)
check("왕복 비용 0.5% 만 빠짐", math.isclose(nav.loc[41, "nav"], 1 - 0.025 * (1 - (1 - 0.0025) ** 2), rel_tol=1e-9))
check("원장 2건 closed · ret = −0.5% 근사", len(led) == 2 and all(p["status"] == "closed" for p in led)
      and all(math.isclose(p["ret"], (1 - 0.0025) ** 2 - 1, rel_tol=1e-9) for p in led))

print("B. 가격이 두 배가 되면 그 슬롯 몫만 늘어난다")
close2 = close.copy(); close2.loc[D[20]:, "AAA"] = 200.0
nav2, _ = pe.simulate(D, close2, picks, cost=0.0)
check("비용 0 · AAA 두 배 → NAV = 1 + 0.0125", math.isclose(nav2.loc[41, "nav"], 1.0125, rel_tol=1e-12))

print("C. 진입일 가격 없음 → 현금(대체 없음)")
close3 = close.copy(); close3.loc[D[1], "BBB"] = np.nan
nav3, led3 = pe.simulate(D, close3, picks, cost=0.0)
check("포지션 1개 · 현금 1 − 0.0125", nav3.loc[1, "n_pos"] == 1 and math.isclose(nav3.loc[1, "cash"], 1 - 0.0125, rel_tol=1e-12))

print("D. 보유 중 가격 끊기면 마지막 가격으로 평가·청산")
close4 = close.copy(); close4.loc[D[30]:, "AAA"] = np.nan
nav4, led4 = pe.simulate(D, close4, picks, cost=0.0)
check("NAV 흔들림 없음(마지막 가격 100)", math.isclose(nav4.loc[41, "nav"], 1.0, rel_tol=1e-12) and led4[0]["exit_px"] == 100.0)

print("E. 매일 추천 → 슬롯 40개까지 차고, 현금 한도")
picks5 = {d: ["AAA"] for d in D[:80]}
nav5, _ = pe.simulate(D, close, picks5, cost=0.0)
check("41일째 포지션 40", nav5.loc[40, "n_pos"] == 40)
check("42일째도 40(하나 나가고 하나 들어옴)", nav5.loc[41, "n_pos"] == 40 and nav5.loc[41, "exits"] == 1 and nav5.loc[41, "entries"] == 1)
check("현금 ≥ 0 항상", (nav5["cash"] >= -1e-12).all())

print("F. 게이트 계좌 — 비율 0 인 날은 안 산다, 상수 q 는 그만큼만")
ratio = {d: (0.0 if k % 2 == 0 else 1.0) for k, d in enumerate(D[:80])}
nav6, _ = pe.simulate(D, close, picks5, cost=0.0, new_ratio=ratio)
check("짝수 날 추천은 진입 0", nav6.loc[1, "entries"] == 0 and nav6.loc[2, "entries"] == 1)
nav7, _ = pe.simulate(D, close, picks5, cost=0.0, new_ratio=0.5)
check("q=0.5 → 투입 절반", math.isclose(nav7.loc[1, "invested"], 0.0125, rel_tol=1e-12))

print("G. 도우미")
cells = pd.Series(["A", "B", "D", None], index=D[:4])
r = pe.ratio_by_cell(cells)
check("D → 0, 나머지 1(칸 없음 포함)", r[D[2]] == 0.0 and r[D[0]] == 1.0 and r[D[3]] == 1.0)
S = pd.DataFrame({"run_id": ["20260101"] * 4, "market": ["kospi", "kospi", "kosdaq", "kosdaq"],
                  "ticker": ["A1", "A2", "Q1", "Q2"], "score": [1, 2, 3, 4]})
p = pe.picks_from_scores(S, top=1, exclude={"Q2"})
check("시장별 상위 1 · 제외 반영", p["20260101"] == ["Q1", "A2"] or p["20260101"] == ["A2", "Q1"])
s = pe.summarize(nav5)
check("요약 키", set(s) >= {"days", "total_ret", "mdd", "cash_share"} and s["mdd"] <= 0)

print("\n" + ("❌ 실패 %d" % fails if fails else "✅ paper_engine 합성 테스트 통과"))
sys.exit(1 if fails else 0)
