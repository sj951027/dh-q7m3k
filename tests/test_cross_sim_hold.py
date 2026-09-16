# -*- coding: utf-8 -*-
"""build_cross_sim.simulate 고정 사례 테스트 — 2026-09-16 (외부 검토 조건: 손계산과 일치해야 함)
규약: 신호일 t → t+1 종가 교체 → 새 바구니 수익은 t+2 부터. t→t+1 수익은 기존 보유 귀속.
신호 없는 날 보유 유지(수익 복사 없음). 못 사는 종목 몫은 현금. 보유 중 결측은 직전가 평가. 마지막 미실현 구간 계산 안 함.
실행: python tests/test_cross_sim_hold.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_cross_sim import simulate  # noqa: E402

D = ["d0", "d1", "d2", "d3", "d4", "d5"]
fails = 0


def check(name, got, exp):
    global fails
    got = {k: round(float(v), 6) for k, v in got.items()}
    ok = list(got.keys()) == list(exp.keys()) and all(abs(got[k] - exp[k]) < 1e-6 for k in exp)
    print(f"  {'ok ' if ok else 'FAIL'} {name}  got={got} exp={exp}")
    fails += 0 if ok else 1


def panel(**cols):
    return pd.DataFrame(cols, index=D, dtype=float)

# 1) 첫 매수 전날(신호 다음 날) 상승은 수익이 아니다: A 100→110→121. d0 신호 → d1 종가 110 매수 → d2 +10%.
C = panel(A=[100, 110, 121, 121, 121, 121])
check("1 첫 매수 전날 상승 미포함", simulate({"d0": ["A"]}, C, D, "d0", "d5"),
      {"d2": 0.10, "d3": 0.0, "d4": 0.0, "d5": 0.0})

# 2) 교체일 수익은 기존 보유분 귀속: d0 신호 A, d2 신호 B. d3(교체일) 수익 = A 100→120 = +20%, d4 = B 50→60 = +20%.
C = panel(A=[100, 100, 100, 120, 120, 120], B=[50, 50, 50, 50, 60, 60])
check("2 교체일 수익 기존 보유 귀속", simulate({"d0": ["A"], "d2": ["B"]}, C, D, "d0", "d5"),
      {"d2": 0.0, "d3": 0.20, "d4": 0.20, "d5": 0.0})

# 3) 신호 누락일에 직전 수익률을 복사하지 않는다: d0 신호만. A 100,100,110,110,121,121 → d2 +10%, d3 0%, d4 +10%, d5 0%.
C = panel(A=[100, 100, 110, 110, 121, 121])
check("3 신호 없는 날 보유 유지·수익 복사 없음", simulate({"d0": ["A"]}, C, D, "d0", "d5"),
      {"d2": 0.10, "d3": 0.0, "d4": 0.10, "d5": 0.0})

# 4a) 교체일에 가격 없는 종목 몫은 현금: d0 신호 A,B. B 는 d1 결측 → 절반 현금. A 100→110(d2) → 포트 +5%.
C = panel(A=[100, 100, 110, 110, 110, 110], B=[50, np.nan, 50, 50, 50, 50])
check("4a 미매수 종목 몫 현금", simulate({"d0": ["A", "B"]}, C, D, "d0", "d5"),
      {"d2": 0.05, "d3": 0.0, "d4": 0.0, "d5": 0.0})

# 4b) 보유 중 결측(거래정지)은 직전가로 평가, 재개 시 재평가: A,B 반반. B d3 결측, d4 60. d2: A 100→100,B 50→50 → 0. d3: B 결측(50 유지) → 0. d4: B 50→60 → +10%.
C = panel(A=[100, 100, 100, 100, 100, 100], B=[50, 50, 50, np.nan, 60, 60])
check("4b 보유 중 결측은 직전가 평가", simulate({"d0": ["A", "B"]}, C, D, "d0", "d5"),
      {"d2": 0.0, "d3": 0.0, "d4": 0.10, "d5": 0.0})

# 5) 마지막 날 미실현 구간 제외: d4 신호 → d5 종가 매수 → 수익 행 없음. d5 신호 → 진입 불가. 기존 보유 A 의 d5 수익은 포함.
C = panel(A=[100, 100, 100, 100, 100, 110], B=[50, 50, 50, 50, 50, 50])
check("5 마지막 미실현 구간 제외", simulate({"d0": ["A"], "d4": ["B"], "d5": ["A"]}, C, D, "d0", "d5"),
      {"d2": 0.0, "d3": 0.0, "d4": 0.0, "d5": 0.10})

# 6) 동일가중 수량 고정(보유 중 리밸런스 없음): 0.5원씩 → A 0.005주·B 0.01주. d2 A 200 → 1.5 (+50%). d3 A 100 → 1.0 → 1.0/1.5−1 = −33.3%.
C = panel(A=[100, 100, 200, 100, 100, 100], B=[50, 50, 50, 50, 50, 50])
check("6 수량 고정 보유", simulate({"d0": ["A", "B"]}, C, D, "d0", "d5"),
      {"d2": 0.5, "d3": -1/3, "d4": 0.0, "d5": 0.0})

# 7) 비용: 교체 시 왕복 0.5% 차감(첫 진입 제외). d2 신호 B → d3 교체일 value *= 0.995 → d3 수익 = −0.5%.
C = panel(A=[100, 100, 100, 100, 100, 100], B=[50, 50, 50, 50, 50, 50])
check("7 교체 비용", simulate({"d0": ["A"], "d2": ["B"]}, C, D, "d0", "d5", cost=0.005),
      {"d2": 0.0, "d3": -0.005, "d4": 0.0, "d5": 0.0})

print("\n" + ("❌ cross_sim simulate 실패 " + str(fails) if fails else "✅ cross_sim simulate 고정 사례 7개 통과"))
sys.exit(1 if fails else 0)
