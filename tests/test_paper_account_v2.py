# -*- coding: utf-8 -*-
"""모의 계좌 2판 합성 테스트 — DB 없음. python test_paper_account_v2.py
새 모델 계좌 하나(lv_b 꼴)를 작은 합성 자료로: 점수 → 시장별 상위 목록 → t+1 종가 진입 → 40일 뒤 청산 · 비용 0.5/0.35% · 상폐 −90% 감도."""
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


D = [f"2026{(i // 28) + 1:02d}{(i % 28) + 1:02d}" for i in range(100)]   # 100 '거래일'
TK = ["K1", "K2", "K3", "Q1", "Q2", "Q3"]                                # 코스피 3 · 코스닥 3
close = pd.DataFrame(100.0, index=D, columns=TK)
close.loc[D[10]:, "K1"] = 110.0                                           # K1 은 보유 중 +10%
close.loc[D[20]:, "Q2"] = np.nan                                          # Q2 는 D[20] 부터 시세 끊김(상폐 꼴)

print("A. 점수 표 → 시장별 상위 2(희석 제외) = 1판 v30 과 같은 읽기")
S = pd.DataFrame({"run_id": [D[0]] * 6, "market": ["kospi"] * 3 + ["kosdaq"] * 3, "ticker": TK, "score": [3, 2, 1, 1, 3, 2]})
picks = pe.picks_from_scores(S, top=2, exclude={"Q3"})
check("코스피 K1,K2 · 코스닥 Q2,Q1(Q3 제외)", sorted(picks[D[0]]) == ["K1", "K2", "Q1", "Q2"])

print("B. t+1 종가 진입 · 40일 뒤 청산 · 왕복 0.5%")
nav, led = pe.simulate(D, close, picks, slots=40, hold=40, cost=0.005)
check("D[1] 에 4종목 진입(슬롯 돈 1/40 을 4등분)", nav.loc[1, "n_pos"] == 4 and math.isclose(nav.loc[1, "invested"], 0.025 * (1 - 0.0025), rel_tol=1e-12))
check("D[41] 청산 → 포지션 0", nav.loc[41, "n_pos"] == 0 and nav.loc[40, "n_pos"] == 4)
k1 = [p for p in led if p["ticker"] == "K1"][0]
check("K1 수익 = 1.1×(1−0.0025)² − 1", math.isclose(k1["ret"], 1.1 * (1 - 0.0025) ** 2 - 1, rel_tol=1e-12))
q2 = [p for p in led if p["ticker"] == "Q2"][0]
check("Q2 기본 경로 = 마지막 가격 100 으로 청산(1판과 같음)", q2["exit_px"] == 100.0 and q2.get("gone") is False)
nav_expect = 1 + 0.025 / 4 * (1.1 * (1 - 0.0025) ** 2 - 1) + 3 * 0.025 / 4 * ((1 - 0.0025) ** 2 - 1)
check("D[41] NAV = 1 + 슬롯 몫별 손익 합", math.isclose(nav.loc[41, "nav"], nav_expect, rel_tol=1e-12))

print("C. 비용 0.35% 감도 — 비용 차이만큼만 NAV 가 다르다")
nav_c, _ = pe.simulate(D, close, picks, cost=0.0035)
exp_c = 1 + 0.025 / 4 * (1.1 * (1 - 0.00175) ** 2 - 1) + 3 * 0.025 / 4 * ((1 - 0.00175) ** 2 - 1)
check("0.35% NAV 식 일치", math.isclose(nav_c.loc[41, "nav"], exp_c, rel_tol=1e-12))
check("0.35% 가 0.5% 보다 높다", nav_c.loc[41, "nav"] > nav.loc[41, "nav"])

print("D. 상폐 −90% 감도 — gone_dates 가 끊긴 종목을 찾고, 그 날부터 마지막 가격 × 0.1")
gone = pe.gone_dates(close)
check("끊긴 종목 = Q2 · 끊긴 첫 날 D[20]", gone == {"Q2": D[20]})
nav_g, led_g = pe.simulate(D, close, picks, cost=0.005, gone=gone, gone_ret=-0.9)
q2g = [p for p in led_g if p["ticker"] == "Q2"][0]
check("Q2 청산가 = 10 · gone 표식", math.isclose(q2g["exit_px"], 10.0, rel_tol=1e-12) and q2g["gone"] is True)
check("D[19] 까진 기본과 같고 D[20] 부터 낮다", math.isclose(nav_g.loc[19, "nav"], nav.loc[19, "nav"], rel_tol=1e-12) and nav_g.loc[20, "nav"] < nav.loc[20, "nav"])
exp_g = nav_expect + 0.025 / 4 * (0.1 - 1.0) * (1 - 0.0025) ** 2
check("D[41] NAV = 기본 − Q2 몫 × 90%", math.isclose(nav_g.loc[41, "nav"], exp_g, rel_tol=1e-12))
check("gone 안 주면(기본) 결과가 1판과 완전히 같다", pe.simulate(D, close, picks, cost=0.005)[0]["nav"].equals(nav["nav"]))
check("gone_ret=0 이면 기본과 같다", pe.simulate(D, close, picks, cost=0.005, gone=gone, gone_ret=0.0)[0]["nav"].equals(nav["nav"]))

print("E. 끊긴 날이 구간 밖이면 영향 없음 · 구간 시작 전이면 첫날부터")
check("표 끝 뒤 날짜 → 무시", pe.simulate(D, close, picks, cost=0.0, gone={"K1": "20991231"})[0]["nav"].equals(pe.simulate(D, close, picks, cost=0.0)[0]["nav"]))
nav_e, led_e = pe.simulate(D[5:], close.loc[D[5]:], {D[5]: ["K1"]}, cost=0.0, gone={"K1": D[2]})
check("시작 전에 끊긴 종목은 첫날부터 ×0.1", math.isclose(led_e[0]["exit_px"], 11.0, rel_tol=1e-12))

print("F. 요약 — 새 계좌도 같은 요약 함수")
s = pe.summarize(nav_g)
check("요약 키·낙폭 ≤ 0", set(s) >= {"days", "total_ret", "mdd", "cash_share"} and s["mdd"] <= 0 and s["days"] == 100)

print("G. [E3] 스위치 — A 칸 날엔 v30 목록, 그 밖 날엔 lv_b 목록, 목록 없는 날은 현금")
pv = {D[0]: ["K1"], D[1]: ["K2"], D[2]: ["K3"], D[3]: ["K1"]}            # 'v30' 꼴 목록
pl = {D[0]: ["Q1"], D[1]: ["Q2"], D[3]: ["Q1"]}                           # 'lv_b' 꼴 목록(D[2] 결손)
cells = pd.Series({D[0]: "A", D[1]: "B", D[2]: "C", D[3]: None}).reindex(D[:4])
sw, info = pe.switch_picks(D[:4], cells, pv, pl)
check("A 날(D0) = v30 목록 K1", sw[D[0]] == ["K1"] and info["source"][D[0]] == "A")
check("B 날(D1) = lv_b 목록 Q2", sw[D[1]] == ["Q2"] and info["source"][D[1]] == "other")
check("C 날인데 lv_b 결손(D2) → 목록 없음(v30 로 대체하지 않음)", D[2] not in sw and info["days_missing"] == 1)
check("칸 없음(D3) = 그 밖 → lv_b Q1", sw[D[3]] == ["Q1"])
check("날마다 한 목록만 · 셈 A 1/그 밖 2", all(len(v) == 1 for v in sw.values()) and info["days_A"] == 1 and info["days_other"] == 2)
nav_s, led_s = pe.simulate(D, close, sw, cost=0.0)
check("D1 진입 K1(v30) · D2 진입 Q2(lv_b) · D3 진입 없음(현금) · D4 진입 Q1",
      [p["ticker"] for p in sorted(led_s, key=lambda p: p["entry_i"])] == ["K1", "Q2", "Q1"] and nav_s.loc[3, "entries"] == 0 and nav_s.loc[3, "n_pos"] == 2)
check("체결 슬롯 출처 셈 v30 1 · lv_b 2", sum(1 for p in led_s if info["source"][p["run"]] == "A") == 1 and sum(1 for p in led_s if info["source"][p["run"]] == "other") == 2)
check("두 목록이 같은 날 둘 다 들어간 날 없음", all(sw[d] == pv[d] or sw[d] == pl.get(d) for d in sw) and all(not (set(pv[d]) & set(pl.get(d, []))) for d in sw))

print("F2. 진입 가능 표 — 등락률 열이 빠진 신규 상장 종목이 있어도 bool (2026-10-30 배치 TypeError 재현)")
susp = pd.DataFrame(0.0, index=D[:3], columns=["K1", "K2", "N1"]); susp.loc[D[1], "K2"] = 1
chg = pd.DataFrame(0.0, index=D[:3], columns=["K1", "K2"]); chg.loc[D[2], "K1"] = 0.30   # N1 = 상장 첫날 → 등락률 열 자체가 없음
trd = pe.tradable_mask(susp, chg, 0.29)
check("모든 열 bool · 열 = 합집합 3개", (trd.dtypes == bool).all() and list(trd.columns) == ["K1", "K2", "N1"])
check("정지일 K2 False · 상한가일 K1 False · 그 밖 True", (not trd.loc[D[1], "K2"]) and (not trd.loc[D[2], "K1"]) and trd.loc[D[0], "K1"] and trd.loc[D[1], "K1"])
check("등락률 없는 N1 은 진입 가능(True)", trd["N1"].all())
check("뒤집기 결과가 옛 식(열이 다 있을 때)과 같음", trd[["K1", "K2"]].equals(~((susp[["K1", "K2"]] > 0) | (chg >= 0.29))))

print("H. 비용 1.0% 감도 — 비용이 클수록 NAV 가 낮고, 두 비용의 차이는 회전×비용 차만큼 (2026-10-31 C11)")
nav5, _ = pe.simulate(D, close, picks, slots=40, hold=40, cost=0.005); nav10, _ = pe.simulate(D, close, picks, slots=40, hold=40, cost=pe.COST_HI)
check("COST_HI = 0.01", pe.COST_HI == 0.01)
check("1.0% NAV ≤ 0.5% NAV (모든 날)", bool((nav10.nav <= nav5.nav + 1e-12).all()) and nav10.nav.iloc[-1] < nav5.nav.iloc[-1])
check("비용 0 이면 둘보다 높음", pe.simulate(D, close, picks, slots=40, hold=40, cost=0.0)[0].nav.iloc[-1] > nav5.nav.iloc[-1])

print("I. 매도대금 T+2 결제 감도 — settle_days=0 은 종전과 동일, 2 면 결제 전 돈으론 못 사고 NAV 는 보존 (2026-11-01 J11)")
D2 = D[:12]; c2 = pd.DataFrame(100.0, index=D2, columns=["K1", "K2"]); c2.loc[D2[2]:, "K1"] = 120.0
nav0, _ = pe.simulate(D2, c2, {D2[0]: ["K1"], D2[3]: ["K2"]}, slots=1, hold=2, cost=0.0)             # K1 D1 진입 → D3 청산(대금 1.2) · 같은 날 K2 진입(종전: 그 돈으로 삼)
nav2, led2 = pe.simulate(D2, c2, {D2[0]: ["K1"], D2[3]: ["K2"]}, slots=1, hold=2, cost=0.0, settle_days=2)
nav00, _ = pe.simulate(D2, c2, {D2[0]: ["K1"], D2[3]: ["K2"]}, slots=1, hold=2, cost=0.0, settle_days=0)
check("settle_days=0 명시 = 기본값과 NAV 완전 동일", nav00.nav.equals(nav0.nav))
check("종전: D4 에 K2 진입(청산 대금 즉시 사용)", nav0.loc[4, "n_pos"] == 1)
check("T+2: D4 엔 현금 0(결제 대기) → K2 못 삼(현금), D5 에 대금 입금", nav2.loc[4, "n_pos"] == 0 and nav2.loc[4, "cash"] == 0.0 and nav2.loc[5, "cash"] > 1.19)
check("결제 대기 중에도 NAV 는 보존(D3·D4 NAV = 1.2)", abs(nav2.loc[3, "nav"] - 1.2) < 1e-12 and abs(nav2.loc[4, "nav"] - 1.2) < 1e-12)
check("SETTLE_DAYS = 2", pe.SETTLE_DAYS == 2)

print("K. [2026-11-07 F2] restrict_to_calendar — 보충표의 본표 밖 날짜(주말 등) 제거")
ex_df = pd.DataFrame({"ticker": ["A", "A", "A"], "date": [D[0], "20261231", D[1]], "close": [1.0, 2.0, 3.0]})   # 20261231 은 D(1~4월) 에 없는 날
kept, n_off = pe.restrict_to_calendar(ex_df, D)
check("본표 달력 밖 1행 제거·나머지 보존", n_off == 1 and list(kept.date) == [D[0], D[1]])
check("전부 달력 안이면 0-diff", pe.restrict_to_calendar(ex_df.iloc[[0, 2]], D)[1] == 0)

print("J. [관측 계약 11/07 · M1 교정] 정적 반반 mix_picks — 목록별 예산 절반 고정 → 종목 가중치 0.5/nA + 0.5/nB · 한쪽만 있는 날은 그 목록 · 둘 다 없으면 현금")
mx, mi = pe.mix_picks(D[:4], pv, pl)
check("둘 다 있는 날 = 가중치 반반", mx[D[0]] == {"K1": 0.5, "Q1": 0.5} and mx[D[1]] == {"K2": 0.5, "Q2": 0.5})
check("lv_b 결손일(D2) = v30 목록만(가중치 1)", mx[D[2]] == {"K3": 1.0} and mi["days_only_a"] == 1 and mi["days_both"] == 3)
w_dup = pe.mix_picks([D[0]], {D[0]: ["K1", "X"]}, {D[0]: ["X", "K1", "Y"]})[0][D[0]]
check("중복 종목은 두 몫을 더함(0.5/2+0.5/3) · 합 1", abs(w_dup["X"] - (0.25 + 0.5 / 3)) < 1e-12 and abs(w_dup["Y"] - 0.5 / 3) < 1e-12 and abs(sum(w_dup.values()) - 1) < 1e-12)
w_len = pe.mix_picks([D[0]], {D[0]: [f"A{i}" for i in range(20)]}, {D[0]: [f"B{i}" for i in range(10)]})[0][D[0]]
check("A 20개·B 10개여도 목록별 몫은 각각 0.5(Codex M1 반례)", abs(sum(v for k, v in w_len.items() if k.startswith("A")) - 0.5) < 1e-12 and abs(w_len["B0"] - 0.05) < 1e-12)
check("둘 다 없는 날·빈 목록은 현금", pe.mix_picks([D[0]], {}, {})[1]["days_missing"] == 1 and pe.mix_picks([D[0]], {D[0]: []}, {D[0]: ["Q1"]})[1]["days_only_b"] == 1)
nav_m, led_m = pe.simulate(D[:6], close.iloc[:6], {D[0]: {"K1": 0.5, "Q1": 0.5}}, cost=0.0)
check("엔진: 가중치 dict 목록 → 각 1/80 투입", len(led_m) == 2 and all(abs(p["invested"] - 1 / 80) < 1e-12 for p in led_m))
nav_w, led_w = pe.simulate(D[:6], close.iloc[:6], {D[0]: {"K1": 0.75, "Q1": 0.25}}, cost=0.0)
check("엔진: 가중치 3:1 → 투입 3/160·1/160", sorted(round(p["invested"], 12) for p in led_w) == sorted([round(3 / 160, 12), round(1 / 160, 12)]))
check("엔진: list 목록은 종전 동일가중 그대로(0-diff)", pe.simulate(D[:6], close.iloc[:6], {D[0]: ["K1", "Q1"]}, cost=0.0)[0]["nav"].equals(nav_m["nav"]))

print("\n" + ("❌ 실패 %d" % fails if fails else "✅ paper_account 2판 합성 테스트 통과"))
sys.exit(1 if fails else 0)
