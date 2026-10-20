# -*- coding: utf-8 -*-
"""'이만큼 빠졌던 때 과거엔 어땠나' 3줄 표시(2026-10-20 밤) — 합성 입력만, DB·네트워크 없음, 전송 없음.

계약:
  A. cell6: 여섯 칸 경계(−10 은 A2, −5 는 A1, 0 은 B, +5 는 C, +10 은 D1), NaN/None/문자 → None.
  B. stats: 40일 끝난 날만 · 사건 = 같은 칸의 날을 40거래일 간격으로 센 것 · '더 빠진 뒤 올랐음' 셈.
  C. lines/block: 사용자 확정 3줄 형식. 사건 5개 미만이면 '표본 부족' 두 줄. 사건의 과반이 손해(플러스 < 50%)일 때만 '과거엔 좋은 자리 아니었음'(평균만 마이너스면 안 붙임).
  D. notify_telegram._regime_block: 성적표 buy_context 없으면 종전 한 줄로 폴백(예외 없음).
실행: python tests/test_buy_context.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import buy_context as bc

fails = 0


def check(name, cond):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        fails += 1


print("A. 칸")
check("경계값", bc.cell6(-17.3) == "A2" and bc.cell6(-10) == "A2" and bc.cell6(-9.9) == "A1" and bc.cell6(-5) == "A1"
      and bc.cell6(-4.2) == "B" and bc.cell6(0) == "B" and bc.cell6(3) == "C" and bc.cell6(5) == "C" and bc.cell6(7) == "D1"
      and bc.cell6(10) == "D1" and bc.cell6(11) == "D2")
check("깨진 입력 → None", bc.cell6(None) is None and bc.cell6(float("nan")) is None and bc.cell6("x") is None)

print("B. 통계")
D = [f"d{i:04d}" for i in range(300)]
r20 = pd.Series(0.0, index=D); b40 = pd.Series(1.0, index=D); idx = pd.Series(100.0, index=D)
for s in (20, 120, 220):
    r20.iloc[s:s + 10] = -12.0; b40.iloc[s:s + 10] = 8.0
b40.iloc[120:130] = -2.0          # 둘째 사건 마이너스
idx.iloc[21:40] = 90.0            # 첫 사건 뒤 20일 안 −10% 더 빠짐
b40.iloc[280:] = np.nan           # 미완결
st = bc.stats(D, r20, b40, idx)
a2 = st["A2"]
check("A2 날 30 · 사건 3 · 플러스 2", a2["n_days"] == 30 and a2["n_events"] == 3 and a2["events_pos"] == 2)
check("더 빠진 사건 1 · 그중 올라온 1", a2["further_n"] == 1 and a2["further_then_up"] == 1)
check("평균 = 사건 평균((8 + −2 + 8)/3) · 전 날 평균은 mean_days", abs(a2["mean"] - (8 - 2 + 8) / 3) < 1e-9 and abs(a2["mean_days"] - (8 * 20 - 2 * 10) / 30) < 1e-9)
check("미완결 20일은 B 에서 빠짐", st["B"]["n_days"] == 270 - 20)
check("없는 칸은 키 없음", "D2" not in st)
check("부모 칸 A = A2+A1 합산", st["A"]["n_days"] == 30 and st["A"]["n_events"] == 3)

print("C. 문구")
st_k = {"events_n": 6, "events_pos": 5, "mean": 12.0, "further_n": 2, "further_then_up": 2}
st_q = {"events_n": 10, "events_pos": 4, "mean": -1.0, "further_n": 7, "further_then_up": 3}
out = bc.block({"kospi": {"r20_pct": -17.3}, "kosdaq": {"r20_pct": -4.2}}, {"kospi": {"A2": st_k}, "kosdaq": {"B": st_q}})
check("코스피 1줄(시장 전체 기준 표기)", out[0] == "🧭 코스피 -17.3% (3년 중 가장 많이 빠진 축 · 시장 전체 기준)")
check("코스피 2줄", out[1] == "   이만큼 빠졌던 때 3년간 6번 → 다음날 사서 40일 뒤 평균 +12%, 6번 중 5번 플러스")
check("코스피 3줄", out[2] == "   단 6번 중 2번은 사고 나서 더 떨어진 뒤 올랐음")
check("코스닥 1줄", out[3] == "🧭 코스닥 -4.2% (보통 수준의 약세 · 시장 전체 기준)")
check("코스닥 2줄(좋은 자리 아니었음)", out[4].endswith("10번 중 4번 플러스 → 과거엔 좋은 자리 아니었음"))
check("코스닥 3줄(반반이면 풀어 씀)", out[5] == "   단 10번 중 7번은 사고 나서 더 떨어졌고 그중 3번만 40일 뒤 플러스")
check("표본 부족", bc.lines("kospi", 12.0, {"events_n": 3})[1].endswith("표본 부족"))
check("통계 없음 → 과거 기록 아직 없음", bc.lines("kospi", 12.0, None)[1].strip() == "과거 기록 아직 없음")
st_a = {"events_n": 9, "events_pos": 9, "mean": 6.8, "further_n": 4, "further_then_up": 4}
outp = bc.block({"kospi": {"r20_pct": -17.3}}, {"kospi": {"A2": {"events_n": 4, "events_pos": 4, "mean": 6.7}, "A": st_a}})
check("사건 4개뿐이면 부모 칸(≤−5%)으로 대체·말도 넓힘", outp[1] == "   5% 넘게 빠졌던 때 3년간 9번 → 다음날 사서 40일 뒤 평균 +7%, 9번 중 9번 플러스")
check("평균만 마이너스(과반 플러스)면 '좋은 자리 아니었음' 안 붙임", "좋은 자리" not in bc.lines("kosdaq", -4.2, {"events_n": 16, "events_pos": 11, "mean": -0.7})[1])
check("years 인자", bc.block({"kospi": {"r20_pct": -17.3}}, {"kospi": {"A2": st_k}}, years="2년")[1].startswith("   이만큼 빠졌던 때 2년간"))
check("빈 입력 → []", bc.block({}, {}) == [] and bc.block(None, None) == [])
check("점수 있으면 첫 줄에 9.8/10", bc.block({"kospi": {"r20_pct": -17.3, "pos10": 9.8}}, {"kospi": {"A2": st_k}})[0] == "🧭 코스피 9.8/10 · -17.3% (3년 중 가장 많이 빠진 축 · 시장 전체 기준)")
check("점수 깨지면 생략", bc.block({"kospi": {"r20_pct": -17.3, "pos10": "x"}}, {"kospi": {"A2": st_k}})[0].startswith("🧭 코스피 -17.3%"))
check("점수 NaN 도 생략", bc.block({"kospi": {"r20_pct": -17.3, "pos10": float("nan")}}, {"kospi": {"A2": st_k}})[0].startswith("🧭 코스피 -17.3%"))
check("깨진 r20 → 건너뜀", bc.block({"kospi": {"r20_pct": "x"}}, {}) == [])

print("D. 텔레그램 폴백")
import notify_telegram as nt
check("_regime_block 은 리스트 또는 None(예외 없음)", isinstance(nt._regime_block(), (list, type(None))))
check("종전 한 줄 함수 유지", nt._regime_ad_text({"kospi": {"r20_pct": -13.0, "label": "급락 뒤", "days": 7}}) == "🧭 시장국면: 코스피 -13.0% 급락 뒤 7일째")

print("\n" + ("❌ 실패 %d" % fails if fails else "✅ test_buy_context 통과"))
sys.exit(1 if fails else 0)
