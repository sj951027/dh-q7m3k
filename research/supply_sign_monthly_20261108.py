# -*- coding: utf-8 -*-
"""수급 외국인/기관 부호 — 월별 되감기 (2026-11-08, 읽기 전용 · 채택 아님). `EARLY_RISE_SCAN_20261108.md` §5 의 짝.
사용자 질문 "시기에 따라 외인·기관 손바뀜이 생길 텐데 등록해도 되나" → 스캔 패널(out_early_rise_scan/panel.pkl, 스캔 스크립트가 만든 것)을
run_id 달력월로 묶어 외국인·기관 5일/20일 순매수(억)의 날별 순위상관(같은 시장 안, n≥12)을 월별로 평균하고 양수인 날 비율을 센다.
시장 전체 월별 순매수 합은 ../dh-q7m3k-data/ohlcv.db daily_flows(mode=ro)에서. 출력: research/out_early_rise_scan/supply_sign_monthly.csv"""
import sqlite3, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent)); import leaderboard as lb
pd.set_option("display.width", 250)
con = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
f = pd.read_sql("select date, sum(foreign_net_val) fo, sum(inst_net_val) inst, sum(person_net_val) per from daily_flows group by date", con); con.close()
f["m"] = f.date.astype(str).str[:6]
print("### 시장 전체 월별 순매수(전 종목 합 ÷ 1e4 — 자료 단위 미확인, 방향·크기 비교용)")
print((f.groupby("m")[["fo", "inst", "per"]].sum() / 1e4).round(0).astype(int).to_string())
P = pd.read_pickle(HERE / "out_early_rise_scan" / "panel.pkl"); P["m"] = P.run_id.astype(str).str[:6]
V = ["foreign_5d_억", "foreign_20d_억", "inst_5d_억", "inst_20d_억"]
def ic(d, v, T):
    s = d[[v, T]].dropna(); return s[v].corr(s[T], method="spearman") if len(s) >= 12 else np.nan
out = []
for lab, D, grp in [("stage3", P, ["run_id", "mk"]), ("v30_top10", P[P.in_v30_top10 == 1], ["run_id"])]:
    for T in ["T1", "T4"]:
        for m, d in D.groupby("m"):
            r = {"표본": lab, "목표": T, "월": m, "행": len(d), "날": d.run_id.nunique()}
            for v in V:
                vals = [x for x in (ic(dd, v, T) for _, dd in d.groupby(grp)) if x == x]
                r[v] = np.mean(vals) if vals else np.nan; r[v + "_양수날%"] = 100 * np.mean([x > 0 for x in vals]) if vals else np.nan
            out.append(r)
R = pd.DataFrame(out); R.to_csv(HERE / "out_early_rise_scan" / "supply_sign_monthly.csv", index=False, encoding="utf-8-sig")
for (lab, T), g in R.groupby(["표본", "목표"], sort=False):
    print(f"\n### {lab} · {T} — 월별 평균 날별 순위상관 · 양수인 날 비율"); print(g.drop(columns=["표본", "목표"]).round(3).to_string(index=False))
