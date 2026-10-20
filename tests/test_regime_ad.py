# -*- coding: utf-8 -*-
"""A~D 진입 국면 표시(2026-10-20) — 합성 입력만, 운영 DB 미접촉, 전송 없음.

계약:
  A. cell_of: −5% 이하 = A(급락 뒤), −5~0 = B(약세), 0~+5 = C(강세), +5% 초과 = D(급등 뒤). 경계값은 아래 칸. NaN/None → None.
  B. classify: 처음 20일은 칸 없음 · 같은 칸이 이어지면 며칠째가 1,2,3… · 칸이 바뀌면 1부터.
  C. line/describe: '코스피 -13.0% 급락 뒤 8일째 · 코스닥 -0.4% 약세 3일째' 꼴. 한 시장만 있어도 되고, 깨진 입력은 None.
  D. notify_telegram._regime_ad_text: 위 줄에 머리말을 붙이고, 비면 None(예외 없음).
실행: python tests/test_regime_ad.py
"""
import math
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import regime_ad as ra

fails = 0


def check(name, cond):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        fails += 1


print("A. 칸 나누기")
check("-13% → A", ra.cell_of(-0.13) == "A")
check("-5% 경계 → A", ra.cell_of(-0.05) == "A")
check("-4.9% → B", ra.cell_of(-0.049) == "B")
check("0 경계 → B", ra.cell_of(0.0) == "B")
check("+3% → C", ra.cell_of(0.03) == "C")
check("+5% 경계 → C", ra.cell_of(0.05) == "C")
check("+5.1% → D", ra.cell_of(0.051) == "D")
check("NaN → None", ra.cell_of(float("nan")) is None)
check("None → None", ra.cell_of(None) is None)
check("문자 → None", ra.cell_of("x") is None)

print("B. 시계열 분류·며칠째")
# 20일 평평(100) → 21일째부터 R20 계산. 그 뒤 3일은 급락(85), 2일은 약세(99), 1일은 급등(110) 수준으로 만든다.
base = [100.0] * 20
closes = base + [85.0, 85.0, 85.0] + [99.0, 99.0] + [110.0]
# R20 은 20일 전과 비교 — 20일 전은 모두 100 이므로 85→-15%(A), 99→-1%(B), 110→+10%(D)
idx = [f"2026{i:04d}" for i in range(1, len(closes) + 1)]
df = ra.classify(pd.Series(closes, index=idx))
check("처음 20일 칸 없음", all(v is None for v in df["cell"].iloc[:20]))
check("처음 20일 며칠째 없음(NaN)", df["days"].iloc[:20].isna().all())
check("급락 3일 = A,A,A", list(df["cell"].iloc[20:23]) == ["A", "A", "A"])
check("며칠째 1,2,3", list(df["days"].iloc[20:23]) == [1, 2, 3])
check("칸 바뀌면 1부터(B 1,2)", list(df["cell"].iloc[23:25]) == ["B", "B"] and list(df["days"].iloc[23:25]) == [1, 2])
check("급등 D 1일째", df["cell"].iloc[25] == "D" and df["days"].iloc[25] == 1)
check("r20 값(-15%)", math.isclose(df["r20"].iloc[20], -0.15, abs_tol=1e-9))

print("C. 한 줄 말")
info = {"kospi": {"r20_pct": -13.0, "cell": "A", "label": "급락 뒤", "days": 8},
        "kosdaq": {"r20_pct": -0.4, "cell": "B", "label": "약세", "days": 3}}
check("두 시장", ra.line(info) == "코스피 -13.0% 급락 뒤 8일째 · 코스닥 -0.4% 약세 3일째")
check("플러스 부호", ra.describe({"r20_pct": 6.2, "label": "급등 뒤", "days": 1}) == "+6.2% 급등 뒤 1일째")
check("한 시장만", ra.line({"kosdaq": info["kosdaq"]}) == "코스닥 -0.4% 약세 3일째")
check("빈 입력 → None", ra.line({}) is None and ra.line(None) is None)
check("깨진 입력 → None", ra.describe({"r20_pct": "x"}) is None and ra.line({"kospi": {"bad": 1}}) is None)
check("칸 이름 넷", tuple(ra.CELLS[k] for k in ra.ORDER) == ("급락 뒤", "약세", "강세", "급등 뒤"))

print("D. 텔레그램 줄(순수 함수)")
import notify_telegram as nt
check("머리말 붙음", nt._regime_ad_text(info) == "🧭 시장국면: 코스피 -13.0% 급락 뒤 8일째 · 코스닥 -0.4% 약세 3일째")
check("비면 None", nt._regime_ad_text({}) is None and nt._regime_ad_text(None) is None)
check("깨진 입력도 None(예외 없음)", nt._regime_ad_text({"kospi": "oops"}) is None)

print("\n" + ("❌ 실패 %d" % fails if fails else "✅ test_regime_ad 통과"))
sys.exit(1 if fails else 0)
