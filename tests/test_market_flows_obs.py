# -*- coding: utf-8 -*-
"""market_flows_obs 순수 함수 테스트 — 네트워크·DB 없음. python tests/test_market_flows_obs.py (2026-10-31 · 보강 2026.10.46 Codex 검토 반영)"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import market_flows_obs as mo

fails = 0


def check(name, cond):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        fails += 1


print("A. summarize — 20·60일 누적과 거래대금 대비 %, 창 완전성")
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
n2 = net.copy(); n2.iloc[-3, 0] = np.nan
check("20일 창 안 한 칸 결측 → w20 None(19일을 20일로 내지 않음), w60 도 None", mo.summarize(n2, T)["w20"] is None and mo.summarize(n2, T)["w60"] is None)
n3 = net.copy(); n3.iloc[0, 0] = np.nan
check("60일 창 밖(첫날) 결측은 w20·w60 에 영향 없음", mo.summarize(n3, T)["w20"] is not None and mo.summarize(n3, T)["w60"] is not None)
T2 = T.copy(); T2.iloc[-1] = 0
check("거래대금 0 인 날이 창에 있으면 None", mo.summarize(net, T2)["w20"] is None)

print("B. to_rows — 행 생성·집계 플래그·수량 정책")
idx = pd.to_datetime(["2026-10-29", "2026-10-30"])
mk = lambda v: pd.DataFrame({c: [v, v] for c in mo.DETAIL}, index=idx)
got = {("val", "매수"): mk(5), ("val", "매도"): mk(3), ("val", "순매수"): mk(2), ("qty", "매수"): mk(50), ("qty", "매도"): mk(30), ("qty", "순매수"): mk(20)}
rows = mo.to_rows("KOSPI", got, "2026-10-31 00:00:00")
check("2일 × 12구분 = 24행", len(rows) == 24)
r = [x for x in rows if x[1] == "20261030" and x[2] == "연기금"][0]
check("날짜 YYYYMMDD · 값 매수5/매도3/순2 · 수량 50/30/20", r[3:6] == (5, 3, 2) and r[6:9] == (50, 30, 20))
check("'전체' 만 집계 플래그 1", sum(x[9] for x in rows) == 2 and all(x[9] == 1 for x in rows if x[2] == "전체"))
check("qty_ok=False 면 수량 None(기존 보존용)", all(x[6:9] == (None, None, None) for x in mo.to_rows("KOSPI", got, "x", qty_ok=False)))
check("순매수 표 없으면 빈 목록", mo.to_rows("KOSPI", {}, "x") == [])

print("C. valid_snapshot — 보존식·열·날짜·정수")
def snap(buy, sell, qty=True):
    # 11구분 순매수 합 0 · 매수/매도 구분 합 = 전체 가 되도록 구성
    cols = [c for c in mo.DETAIL if c != "전체"]
    b = pd.DataFrame({c: [buy] * 2 for c in cols}, index=idx); s_ = pd.DataFrame({c: [sell] * 2 for c in cols}, index=idx)
    b["개인"] = buy + (sell - buy) * len(cols)             # Σ매수 = Σ매도 가 되도록 한 구분을 조정 → 11구분 순매수 합 0 (buy<sell 로 호출해 음수 안 생기게)
    b["전체"] = b[cols].sum(axis=1); s_["전체"] = s_[cols].sum(axis=1); n = b - s_
    g = {("val", "매수"): b, ("val", "매도"): s_, ("val", "순매수"): n}
    if qty:
        g.update({("qty", "매수"): b, ("qty", "매도"): s_, ("qty", "순매수"): n})
    return g
ok, why, qok = mo.valid_snapshot(snap(3, 5))
check("정상 묶음 통과 · 수량 OK", ok and qok and why == "")
ok, why, qok = mo.valid_snapshot(snap(3, 5, qty=False))
check("수량 표 없음 → 통과하되 qty_ok False", ok and not qok and "수량 없음" in why)
g = snap(3, 5); g[("val", "순매수")] = g[("val", "순매수")] + 1
check("매수−매도≠순매수 → 거부", not mo.valid_snapshot(g)[0])
g = snap(3, 5); g[("val", "매수")].iloc[0, 0] = np.nan
check("결측 → 거부", not mo.valid_snapshot(g)[0])
g = snap(3, 5); g[("val", "매도")] = g[("val", "매도")].rename(columns={"연기금": "연기금 등"})
check("열 이름 다름 → 거부", not mo.valid_snapshot(g)[0])
g = snap(3, 5); g[("val", "매수")] = g[("val", "매수")].iloc[:1]
check("날짜 축 불일치 → 거부", not mo.valid_snapshot(g)[0])
g = snap(0, 0)
check("전체 매수 0(빈 응답 꼴) → 거부", not mo.valid_snapshot(g)[0])
check("순매수 표 자체가 없음 → 거부", not mo.valid_snapshot({})[0])

print("\n" + ("❌ 실패 %d" % fails if fails else "✅ test_market_flows_obs 통과"))
sys.exit(1 if fails else 0)
