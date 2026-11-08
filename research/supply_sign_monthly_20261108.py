# -*- coding: utf-8 -*-
"""수급 외국인/기관 부호 — 월별 되감기 (2026-11-08, 읽기 전용 · 채택 아님). `EARLY_RISE_SCAN_20261108.md` §5 의 짝.
사용자 질문 "시기에 따라 외인·기관 손바뀜이 생길 텐데 등록해도 되나" → 스캔 패널(out_early_rise_scan/panel.pkl, 스캔 스크립트가 만든 것)을
run_id 달력월로 묶어 외국인·기관 5일/20일 순매수(억 — stage3 저장값, 수량×종가 근사; daily_flows 금액 합 아님)의 날·시장별 순위상관(3단계 n≥20, 상위20 n≥8)을 월별로 평균하고 양수 셀 비율을 센다.
분모는 목표가 완결된 행만 센다(11/8 Codex 대조 뒤 수정 — 그 전 판은 결측 제거 전 분모를 적어 9월을 19일로 보이게 했다).
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
# [11/8 Codex 대조 뒤 수정] 분모는 목표(T) 완결 행만 · 상위20 도 시장별(n≥8, 두 시장 혼합은 참고열) — 9월 T4 는 9/1~9/4 네 날뿐
def ic8(d, v, T):
    s = d[[v, T]].dropna(); return s[v].corr(s[T], method="spearman") if len(s) >= 8 else np.nan
for lab, D, grp in [("stage3", P, ["run_id", "mk"]), ("v30_top10", P[P.in_v30_top10 == 1], ["run_id", "mk"])]:
    for T in ["T1", "T4"]:
        for m, d0 in D.groupby("m"):
            d = d0.dropna(subset=[T])
            if d.empty: continue
            r = {"표본": lab, "목표": T, "월": m, "완결행": len(d), "완결날": d.run_id.nunique()}
            for v in V:
                f = ic8 if lab == "v30_top10" else ic
                vals = [x for x in (f(dd, v, T) for _, dd in d.groupby(grp)) if x == x]
                r[v] = np.mean(vals) if vals else np.nan; r[v + "_양수셀%"] = 100 * np.mean([x > 0 for x in vals]) if vals else np.nan
                if lab == "v30_top10":
                    mix = [x for x in (ic(dd, v, T) for _, dd in d.groupby("run_id")) if x == x]; r[v + "_혼합참고"] = np.mean(mix) if mix else np.nan
            out.append(r)
R = pd.DataFrame(out); R.to_csv(HERE / "out_early_rise_scan" / "supply_sign_monthly.csv", index=False, encoding="utf-8-sig")
for (lab, T), g in R.groupby(["표본", "목표"], sort=False):
    print(f"\n### {lab} · {T} — 월별 평균 날별 순위상관 · 양수인 날 비율"); print(g.drop(columns=["표본", "목표"]).round(3).to_string(index=False))
