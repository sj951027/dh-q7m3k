# -*- coding: utf-8 -*-
"""market_flows_obs 순수 함수 테스트 — 네트워크·DB 없음. python tests/test_market_flows_obs.py"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import market_flows_obs as mo

fails = 0


def check(name, cond):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        fails += 1


print("A. summarize — 20·60일 누적과 거래대금 대비 %")
D = [f"2026{(i // 28) + 1:02d}{(i % 28) + 1:02d}" for i in range(70)]
net = pd.DataFrame({"외국인": [-100.0] * 70, "연기금": [10.0] * 70, "개인": [90.0] * 70, "전체": [0.0] * 70}, index=D)
T = pd.Series([1000.0] * 70, index=D)
s = mo.summarize(net, T)
check("마지막 날", s["date"] == D[-1])
check("20일 외국인 합 −2000 · −10%", s["w20"]["외국인"]["sum"] == -2000 and abs(s["w20"]["외국인"]["pct"] + 10.0) < 1e-9)
check("60일 연기금 합 600 · +1%", s["w60"]["연기금"]["sum"] == 600 and abs(s["w60"]["연기금"]["pct"] - 1.0) < 1e-9)
check("'전체' 는 요약에서 뺌 · T20 = 20000", "전체" not in s["w20"] and s["T20"] == 20000)
check("창보다 짧으면 None", mo.summarize(net.iloc[:10], T)["w20"] is None and mo.summarize(net.iloc[:10], T)["w60"] is None)
check("빈 입력 None", mo.summarize(pd.DataFrame(), T) is None and mo.summarize(None, T) is None)
check("순서 뒤집혀 들어와도 같은 답", mo.summarize(net.iloc[::-1], T)["w20"]["외국인"]["sum"] == -2000)

print("B. to_rows — 행 생성·집계 플래그·결측")
idx = pd.to_datetime(["2026-10-29", "2026-10-30"])
mk = lambda v: pd.DataFrame({c: [v, v] for c in mo.DETAIL}, index=idx)
got = {("val", "매수"): mk(5), ("val", "매도"): mk(3), ("val", "순매수"): mk(2), ("qty", "매수"): pd.DataFrame(), ("qty", "매도"): pd.DataFrame(), ("qty", "순매수"): pd.DataFrame()}
rows = mo.to_rows("KOSPI", got, "2026-10-31 00:00:00")
check("2일 × 12구분 = 24행", len(rows) == 24)
r = [x for x in rows if x[1] == "20261030" and x[2] == "연기금"][0]
check("날짜 YYYYMMDD · 값 매수5/매도3/순2 · 수량 None", r[3:6] == (5, 3, 2) and r[6:9] == (None, None, None))
check("'전체' 만 집계 플래그 1", sum(x[9] for x in rows) == 2 and all(x[9] == 1 for x in rows if x[2] == "전체"))
check("순매수 표 없으면 빈 목록", mo.to_rows("KOSPI", {}, "x") == [])

print("\n" + ("❌ 실패 %d" % fails if fails else "✅ test_market_flows_obs 통과"))
sys.exit(1 if fails else 0)
