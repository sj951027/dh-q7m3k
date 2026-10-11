# -*- coding: utf-8 -*-
"""넓게 찾기 ① 보유 비중 조절 — 지수만으로 '하락장에서 덜 잃는' 규칙이 있는지 (2026-10-11 · 연구 · 운영 코드·점수·판정 무관)

질문: 시장 상태에 따라 주식 비중을 줄이는 단순 규칙이, 같은 평균 비중을 그냥 들고 있는 것보다 낙폭을 줄였나. 줄였다면 상승을 얼마나 놓쳤나.
자료: ../dh-q7m3k-data/ohlcv.db market_daily 의 KOSPI·KOSDAQ 종가(읽기 전용, 2023-06-01~). 모델 점수는 쓰지 않는다(판정 눈가림과 무관).
규칙(사전 고정 — 이 파일에 적힌 20개가 시험한 전부다. 결과를 보고 더하거나 빼지 않는다):
  A. 이동평균: 종가가 N일선 아래면 비중 X.  N ∈ {20,50,100,200} · X ∈ {0, 0.5}                      (8)
  B. 고점 대비 낙폭: 60일 고점 대비 −k% 아래면 비중 X.  k ∈ {5,10,15} · X ∈ {0, 0.5}                 (6)
  C. 변동성 목표: 비중 = min(1, 목표/최근 20일 연환산 변동성).  목표 ∈ {0.15, 0.20, 0.25}            (3)
  D. 스크리너 국면 라벨(200일선·50일선 둘 다 아래 = '약세')일 때만 비중 X.  X ∈ {0, 0.5}              (2)
  E. 단계식: 200·50일선 둘 다 위 1.0 · 하나만 위 0.5 · 둘 다 아래 0.0                                 (1)
실행 가정: t일 종가로 정하고 t+1일 종가에 바꾼다 → 새 비중은 t+1 종가~t+2 종가 수익부터 적용. 비용 = 비중 변화 1 당 0.175%(왕복 0.35%).
  현금 수익 0(보수적). 지수를 그대로 살 수 있다고 가정(실제 보유 종목과 다르다 — 한계).
기간: 탐색 = 200일선이 생긴 날 ~ 2026-04-10 · 남겨 둔 기간 = 2026-04-13 ~ 2026-10-08(한 번만 본다).
비교 대상: ① 그냥 보유(비중 1) ② **같은 평균 비중을 늘 들고 있기** — 규칙이 '덜 들고 있어서' 덜 빠진 것과 '때를 맞춰서' 덜 빠진 것을 가른다.
우연 가르기: 규칙의 비중 흐름을 날짜만 임의로 밀어(원형 이동 2,000회) 같은 평균 비중·같은 바꾸는 횟수의 '때를 못 맞춘' 흐름을 만들고, 규칙이 그중 몇 백분위인지.
출력: research/RESEARCH_exposure_rules_20261011.md
사용: python research/exposure_rules_20261011.py
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OHLCV = HERE.parent.parent / "dh-q7m3k-data" / "ohlcv.db"
OUT = HERE / "RESEARCH_exposure_rules_20261011.md"
HOLD_START = "20260413"
COST = 0.00175
SHIFTS = 2000


def rules(c):
    """종가 Series → {이름: 비중 Series(그날 종가로 정한 값)}."""
    out = {}
    ma = {n: c.rolling(n).mean() for n in (20, 50, 100, 200)}
    for n in (20, 50, 100, 200):
        for x in (0.0, 0.5):
            out[f"A 이동평균 {n}일선 아래면 {x:g}"] = pd.Series(np.where(c >= ma[n], 1.0, x), c.index).where(ma[n].notna())
    dd = c / c.rolling(60).max() - 1
    for k in (5, 10, 15):
        for x in (0.0, 0.5):
            out[f"B 60일 고점 대비 -{k}% 아래면 {x:g}"] = pd.Series(np.where(dd >= -k / 100, 1.0, x), c.index).where(dd.notna())
    vol = c.pct_change().rolling(20).std() * np.sqrt(252)
    for tgt in (0.15, 0.20, 0.25):
        out[f"C 변동성 목표 {tgt:.0%}"] = (tgt / vol).clip(upper=1.0)
    bear = (c < ma[200]) & (c < ma[50])
    for x in (0.0, 0.5):
        out[f"D 약세(200·50일선 둘 다 아래)면 {x:g}"] = pd.Series(np.where(bear, x, 1.0), c.index).where(ma[200].notna())
    out["E 단계식(둘 다 위 1 · 하나 0.5 · 둘 다 아래 0)"] = (((c >= ma[200]).astype(float) + (c >= ma[50]).astype(float)) / 2).where(ma[200].notna())
    return out


def run(expo, ret):
    """expo[t](t일 종가로 정함) → t+2일 수익에 적용. 반환 (일별 순수익, 적용 비중)."""
    e = expo.shift(2)
    turn = e.diff().abs().fillna(0.0)
    return e * ret - turn * COST, e


def stats(r):
    eq = (1 + r).cumprod()
    return dict(tot=eq.iloc[-1] - 1, mdd=(eq / eq.cummax() - 1).min(), ann=eq.iloc[-1] ** (252 / len(r)) - 1)


def evaluate(name, expo, ret, lo, hi, rng):
    r, e = run(expo, ret)
    m = (r.index >= lo) & (r.index <= hi) & e.notna()
    r, e, base = r[m], e[m], ret[m]
    if len(r) < 60:
        return None
    s, b = stats(r), stats(base)
    avg = float(e.mean())
    c = stats(avg * base)                                    # 같은 평균 비중을 늘 들고 있기
    up, dn = base > 0, base < 0
    # 우연 가르기: 비중 흐름을 원형으로 밀기(같은 평균·같은 전환 횟수, 때만 어긋남)
    ev = e.to_numpy(); bv = base.to_numpy(); n = len(ev)
    ks = rng.integers(5, n - 5, SHIFTS)
    tot, mdd = np.empty(SHIFTS), np.empty(SHIFTS)
    for i, k in enumerate(ks):
        es = np.roll(ev, k)
        rr = es * bv - np.abs(np.diff(es, prepend=es[0])) * COST
        eq = np.cumprod(1 + rr)
        tot[i] = eq[-1] - 1; mdd[i] = (eq / np.maximum.accumulate(eq) - 1).min()
    return dict(rule=name, days=len(r), avg=avg, switches=int((e.diff().abs() > 1e-9).sum()),
                tot=s["tot"], mdd=s["mdd"], b_tot=b["tot"], b_mdd=b["mdd"], c_tot=c["tot"], c_mdd=c["mdd"],
                up_cap=float(r[up].sum() / base[up].sum()), dn_cap=float(r[dn].sum() / base[dn].sum()),
                p_tot=float((tot < s["tot"]).mean() * 100), p_mdd=float((mdd < s["mdd"]).mean() * 100))


def table(rows, picked=None):
    h = ["규칙", "평균 비중", "바꾼 횟수", "수익", "최대 낙폭", "그냥 보유 수익/낙폭", "같은 비중 수익/낙폭", "상승일 가져간 몫", "하락일 맞은 몫", "때맞춤 백분위(수익/낙폭)"]
    out = ["| " + " | ".join(h) + " |", "|" + "---|" * len(h)]
    for x in rows:
        star = " ★" if picked and x["rule"] in picked else ""
        out.append(f"| {x['rule']}{star} | {x['avg']:.0%} | {x['switches']} | {x['tot']:+.1%} | {x['mdd']:.1%} | {x['b_tot']:+.1%} / {x['b_mdd']:.1%} | "
                   f"{x['c_tot']:+.1%} / {x['c_mdd']:.1%} | {x['up_cap']:.0%} | {x['dn_cap']:.0%} | {x['p_tot']:.0f} / {x['p_mdd']:.0f} |")
    return "\n".join(out)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    con = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    md = pd.read_sql("SELECT series, date, close FROM market_daily WHERE series IN ('KOSPI','KOSDAQ')", con)
    con.close()
    px = md.pivot(index="date", columns="series", values="close").sort_index()
    rng = np.random.default_rng(20261011)
    L = ["# 넓게 찾기 ① 보유 비중 조절 — 지수 규칙 20개 (2026-10-11)", "",
         "> 연구 산출물. 운영·점수·판정과 무관. 규칙 20개는 실행 전에 스크립트에 고정했고, **아래 표가 시험한 전부**다(좋은 것만 고르지 않았다).",
         "> 읽는 법: '같은 비중'은 그 규칙의 평균 비중을 늘 들고 있었을 때다. 규칙이 그보다 나아야 '때를 맞춘 것'이다.",
         "> '때맞춤 백분위'는 같은 비중 흐름을 날짜만 임의로 민 2,000개 중 이 규칙이 몇 번째인지(수익은 높을수록, 낙폭은 얕을수록 높다. 50 이 우연 수준).", ""]
    summary = []
    for mk in ("KOSPI", "KOSDAQ"):
        c = px[mk].dropna(); ret = c.pct_change()
        rs = rules(c)
        first = c.index[201]
        dev_hi = c.index[c.index < HOLD_START][-1]
        dev = [evaluate(n, e, ret, first, dev_hi, rng) for n, e in rs.items()]
        hold = [evaluate(n, e, ret, HOLD_START, c.index[-1], rng) for n, e in rs.items()]
        # 탐색 기간에서 고르는 기준(사전 고정): 같은 비중보다 수익이 높고 · 낙폭이 얕고 · 낙폭 때맞춤 백분위 ≥ 90
        picked = {x["rule"] for x in dev if x and x["tot"] > x["c_tot"] and x["mdd"] > x["c_mdd"] and x["p_mdd"] >= 90}
        L += [f"## {mk}", "", f"### 탐색 기간 {first} ~ {dev_hi} ({dev[0]['days']}거래일) — ★ = 기준 통과(같은 비중보다 수익↑·낙폭↓·낙폭 때맞춤 ≥ 90)", "", table(dev, picked), "",
              f"### 남겨 둔 기간 {HOLD_START} ~ {c.index[-1]} ({hold[0]['days']}거래일) — 한 번만 봄. ★ = 탐색 기간에서 고른 것", "", table(hold, picked), ""]
        hp = [x for x in hold if x["rule"] in picked]
        ok = [x for x in hp if x["tot"] > x["c_tot"] and x["mdd"] > x["c_mdd"]]
        allok = [x for x in hold if x["tot"] > x["c_tot"] and x["mdd"] > x["c_mdd"]]
        summary.append(f"- **{mk}**: 20개 중 탐색 기간 통과 {len(picked)}개 → 그중 남겨 둔 기간에서도 같은 비중보다 수익↑·낙폭↓ {len(ok)}개"
                       f" · (참고) 고르지 않고 20개 전부로 보면 남겨 둔 기간에 그런 규칙 {len(allok)}개.")
        print(mk, "탐색 통과", len(picked), "· 남겨 둔 기간에서도", len(ok), "· 전부 중", len(allok))
    L += ["## 요약", ""] + summary + ["",
          "## 한계", "- 지수 자료가 2023-06 부터라 200일선이 생긴 뒤의 탐색 기간이 약 2년, 남겨 둔 기간이 6개월(큰 하락 1번 포함)이다. 국면이 몇 개 안 된다.",
          "- 지수를 그대로 사고판다고 가정했다. 실제 보유 종목은 지수와 다르게 움직인다. 현금 수익 0 · 세금 미반영.",
          "- 규칙 20개 × 지수 2개 = 40번 시험했다. 그중 몇 개가 좋아 보이는 것은 우연으로도 생긴다 — 그래서 남겨 둔 기간과 때맞춤 백분위를 같이 본다.",
          "- 원형 이동은 '같은 비중 흐름인데 때만 어긋난' 비교군이다. 규칙이 추세를 따라가는 성질 자체가 이 기간의 지수 모양과 맞았는지는 가르지 못한다."]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("저장:", OUT)


if __name__ == "__main__":
    main()
