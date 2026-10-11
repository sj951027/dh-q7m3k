# -*- coding: utf-8 -*-
"""넓게 찾기 ①-2 보유 비중 조절 — 같은 규칙 20개를 26년 지수로 다시 (2026-10-12 · 연구 · 운영·점수·판정 무관)

exposure_rules_20261011.py 의 규칙·실행 가정·비교 대상을 그대로 쓴다(규칙을 더하거나 바꾸지 않았다). 자료만 research/data_index_long_20261012.csv(2000-01-04~).
기간: 전체 탐색 = 200일선이 생긴 날 ~ 2026-04-10. 그 안을 넷으로 나눠 따로도 본다(국면이 다른 시기에서 되풀이되는지):
  ① ~2007 ② 2008~2012 ③ 2013~2019 ④ 2020~2026-04-10.  남겨 둔 기간(2026-04-13~)은 10/11 에 이미 한 번 봤다 — 여기서는 참고로만 다시 싣는다.
통과 기준(실행 전에 고정): 전체 탐색 기간에서 '같은 평균 비중을 늘 들고 있기'보다 수익↑·낙폭↓ 이고 낙폭 때맞춤 백분위 ≥ 90, 그리고 네 구간 중 셋 이상에서 수익↑·낙폭↓.
출력: research/RESEARCH_exposure_rules_long_20261012.md
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exposure_rules_20261011 as E   # noqa: E402

CSV = HERE / "data_index_long_20261012.csv"
OUT = HERE / "RESEARCH_exposure_rules_long_20261012.md"
SUBS = [("~2007", "00000000", "20071231"), ("2008~2012", "20080101", "20121231"), ("2013~2019", "20130101", "20191231"), ("2020~2026-04", "20200101", "20260410")]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    px = pd.read_csv(CSV, dtype={"date": str}).set_index("date")
    rng = np.random.default_rng(20261012)
    L = ["# 넓게 찾기 ①-2 보유 비중 조절 — 같은 규칙 20개, 26년 지수 (2026-10-12)", "",
         "> 연구 산출물. 규칙·가정은 10/11 과 같다(더하거나 바꾸지 않음). **표가 시험한 전부**다.",
         "> '같은 비중'은 그 규칙의 평균 비중을 늘 들고 있었을 때. '때맞춤 백분위'는 같은 비중 흐름을 날짜만 임의로 민 2,000개 중 몇 번째인지(50 이 우연 수준).",
         "> ★ = 통과(전체에서 같은 비중보다 수익↑·낙폭↓ · 낙폭 때맞춤 ≥ 90 · 네 구간 중 셋 이상에서 수익↑·낙폭↓).", ""]
    summ = []
    for mk in ("KOSPI", "KOSDAQ"):
        c = px[mk].dropna(); ret = c.pct_change(); rs = E.rules(c)
        first = c.index[201]
        full = {n: E.evaluate(n, e, ret, first, "20260410", rng) for n, e in rs.items()}
        subs = {lab: {n: E.evaluate(n, e, ret, max(lo, first), hi, rng) for n, e in rs.items()} for lab, lo, hi in SUBS}
        hold = {n: E.evaluate(n, e, ret, E.HOLD_START, c.index[-1], rng) for n, e in rs.items()}
        wins = {n: sum(1 for lab in subs if subs[lab][n]["tot"] > subs[lab][n]["c_tot"] and subs[lab][n]["mdd"] > subs[lab][n]["c_mdd"]) for n in rs}
        mddw = {n: sum(1 for lab in subs if subs[lab][n]["mdd"] > subs[lab][n]["c_mdd"]) for n in rs}
        picked = {n for n, x in full.items() if x["tot"] > x["c_tot"] and x["mdd"] > x["c_mdd"] and x["p_mdd"] >= 90 and wins[n] >= 3}
        b = next(iter(full.values()))
        L += [f"## {mk}", "", f"### 전체 탐색 기간 {first} ~ 20260410 ({b['days']}거래일) — 그냥 보유: 수익 {b['b_tot']:+.0%} · 최대 낙폭 {b['b_mdd']:.0%}", "",
              "| 규칙 | 평균 비중 | 바꾼 횟수 | 수익 | 최대 낙폭 | 같은 비중 수익 / 낙폭 | 상승일 가져간 몫 | 하락일 맞은 몫 | 때맞춤 백분위(수익/낙폭) | 넷 중 수익↑·낙폭↓ 구간 | 넷 중 낙폭만↓ 구간 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for n, x in full.items():
            L.append(f"| {n}{' ★' if n in picked else ''} | {x['avg']:.0%} | {x['switches']} | {x['tot']:+.0%} | {x['mdd']:.0%} | {x['c_tot']:+.0%} / {x['c_mdd']:.0%} | "
                     f"{x['up_cap']:.0%} | {x['dn_cap']:.0%} | {x['p_tot']:.0f} / {x['p_mdd']:.0f} | {wins[n]} | {mddw[n]} |")
        L += ["", "### 구간별 — 각 칸 = 규칙 수익 / 낙폭 (같은 비중 수익 / 낙폭)", "",
              "| 규칙 | " + " | ".join(f"{lab} (그냥 보유 {next(iter(subs[lab].values()))['b_tot']:+.0%} / {next(iter(subs[lab].values()))['b_mdd']:.0%})" for lab, _, _ in SUBS) + " | 남겨 둔 2026-04-13~ (참고) |",
              "|---|" + "---|" * (len(SUBS) + 1)]
        for n in rs:
            cells = [f"{subs[lab][n]['tot']:+.0%} / {subs[lab][n]['mdd']:.0%} ({subs[lab][n]['c_tot']:+.0%} / {subs[lab][n]['c_mdd']:.0%})" for lab, _, _ in SUBS]
            h = hold[n]
            L.append(f"| {n}{' ★' if n in picked else ''} | " + " | ".join(cells) + f" | {h['tot']:+.0%} / {h['mdd']:.0%} ({h['c_tot']:+.0%} / {h['c_mdd']:.0%}) |")
        L.append("")
        both_all = [n for n, x in full.items() if x["tot"] > x["c_tot"] and x["mdd"] > x["c_mdd"]]
        summ.append(f"- **{mk}**: 통과 ★ {len(picked)}개" + (f" — {', '.join(sorted(picked))}" if picked else "") +
                    f" · 전체 기간에서 같은 비중보다 수익↑·낙폭↓ 인 규칙 {len(both_all)}/20 · 낙폭 때맞춤 백분위 ≥ 90 인 규칙 {sum(1 for x in full.values() if x['p_mdd'] >= 90)}/20"
                    f" · 그냥 보유보다 수익이 높은 규칙 {sum(1 for x in full.values() if x['tot'] > x['b_tot'])}/20")
        print(mk, "통과", sorted(picked), "· 수익↑낙폭↓", len(both_all), "· 낙폭 때맞춤≥90", sum(1 for x in full.values() if x['p_mdd'] >= 90),
              "· 그냥 보유보다 수익↑", sum(1 for x in full.values() if x['tot'] > x['b_tot']))
    L += ["## 요약", ""] + summ + ["", "## 한계",
          "- 26년 지수 한 줄씩이다. 구간 넷도 서로 다른 '시기'일 뿐 독립된 시험 넷은 아니다. 규칙 20개 × 지수 2개 = 40번 시험.",
          "- 지수를 그대로 사고판다고 가정(2000년대 초에는 그럴 수단이 마땅치 않았다). 현금 수익 0 — 금리가 높던 시기에는 현금 쪽이 실제로 더 유리했다(규칙에 불리한 가정).",
          "- 비용 왕복 0.35% 고정. 세금·슬리피지 미반영. 하루 한 번 종가로만 바꾼다.",
          "- 통과한 규칙이 있어도 '과거 26년에 그랬다'이지 앞으로의 보장이 아니다. 쓰려면 새 사전등록으로 앞날 자료에서 다시 본다."]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("저장:", OUT)


if __name__ == "__main__":
    main()
