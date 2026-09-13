# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/fullscan_20260903 에서 실행. 읽기 전용.
"""regime_persistence.py — "미래의 레짐을 알 수 있나"에 대한 대체 질문 (관측 전용)

미래 예측은 안 한다. 대신 **오늘 알 수 있는 라벨이 앞으로 며칠이나 유지되나**를 잰다.
보유기간을 국면별로 바꾸려면 "진입일 라벨이 그 보유기간 동안 대체로 유지"돼야 하기 때문이다.

라벨 정의는 fslib.regimes() 그대로(코스닥 60일선 × 20일수익 4상태, 전일 종가 기준 PIT).
재는 것:
  ① 국면 지속(런) 길이 분포 — 한 번 들어가면 며칠 가나
  ② 오늘 라벨 L 일 때, 앞으로 K거래일 중 같은 라벨인 날의 비율(평균)
  ③ 오늘 라벨 L 일 때, K거래일 뒤 라벨이 여전히 L 일 확률
  ④ 기준선: 라벨을 모르고 그냥 전체 분포로 찍었을 때의 적중률(비교용)

실행:  cd research/fullscan_20260903 && python ../regime_persistence.py
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FS = os.path.join(HERE, "fullscan_20260903")
sys.path.insert(0, FS)
os.chdir(FS)
from fslib import Panel, regimes    # noqa: E402

LABELS = ["강세", "조정", "반등", "약세"]
KS = [5, 10, 20, 40, 60]


def main():
    P = Panel()
    R = regimes(P)
    lab = pd.Series(R.regime_pit.values, index=pd.Index(R.date.values, name="date")).dropna()
    print("=" * 74)
    print(f"🧭 국면 라벨 지속성 — {lab.index[0]}~{lab.index[-1]} · {len(lab)}거래일 (PIT: 전일 종가 기준)")
    print("=" * 74)
    print("\n== 전체 분포")
    share = lab.value_counts(normalize=True).reindex(LABELS).fillna(0)
    print("   " + " · ".join(f"{k} {v*100:.0f}%" for k, v in share.items()))

    # ① 런 길이
    grp = (lab != lab.shift()).cumsum()
    runs = lab.groupby(grp).agg(["first", "size"])
    print("\n== ① 한 번 들어가면 며칠 가나 (런 길이, 거래일)")
    t = runs.groupby("first")["size"].agg(["count", "median", "mean", "max"]).reindex(LABELS)
    t.columns = ["구간수", "중앙", "평균", "최장"]
    print("   " + t.round(1).to_string().replace("\n", "\n   "))

    v = lab.values
    n = len(v)
    print("\n== ② 오늘 라벨일 때, 앞으로 K일 중 같은 라벨인 날 비율(평균)")
    print("   " + "라벨   " + "  ".join(f"K={k:<3d}" for k in KS))
    for L in LABELS:
        idx = np.where(v == L)[0]
        row = []
        for K in KS:
            keep = idx[idx + K < n]
            if len(keep) < 20:
                row.append("  n/a"); continue
            frac = np.mean([(v[i + 1:i + 1 + K] == L).mean() for i in keep])
            row.append(f"{frac*100:5.0f}%")
        print(f"   {L:4s} " + " ".join(row))

    print("\n== ③ K일 뒤에도 같은 라벨일 확률  (괄호 = 그 라벨의 전체 비중 = 아무것도 모를 때 기준선)")
    print("   " + "라벨   " + "  ".join(f"K={k:<3d}" for k in KS))
    for L in LABELS:
        idx = np.where(v == L)[0]
        row = []
        for K in KS:
            keep = idx[idx + K < n]
            if len(keep) < 20:
                row.append("  n/a"); continue
            row.append(f"{np.mean(v[keep + K] == L)*100:5.0f}%")
        print(f"   {L:4s} " + " ".join(row) + f"   (기준선 {share.get(L,0)*100:.0f}%)")

    print("\n== ④ 보유 40일 동안 진입 라벨이 유지된 비율의 분포(조정 진입 기준)")
    idx = np.where(v == "조정")[0]
    keep = idx[idx + 40 < n]
    if len(keep) >= 20:
        fr = np.array([(v[i + 1:i + 41] == "조정").mean() for i in keep])
        print(f"   n={len(fr)} · 평균 {fr.mean()*100:.0f}% · 중앙 {np.median(fr)*100:.0f}% "
              f"· 절반 이상 유지된 경우 {100*(fr>=0.5).mean():.0f}%")
    print("\n※ 라벨은 '지금 상태'지 '앞으로의 예보'가 아니다. K 가 커질수록 기준선에 수렴하면,")
    print("   그 K 만큼의 보유기간을 라벨로 고르는 것은 근거가 없다는 뜻이다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
