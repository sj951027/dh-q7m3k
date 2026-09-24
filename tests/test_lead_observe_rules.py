# -*- coding: utf-8 -*-
"""lead_observe spec 골든 회귀 테스트 (합성/정적 — DB 불필요)

고정하는 규칙 (PREREGISTER_ld_a.md, 2026-09-24 등록):
  1. spec_hash 골든 — ld_a 4f01c8fcfb95 · ld_ctl_amt ea086b02aa03 (스펙 드리프트 감지).
  2. 순위합 — 핵심(beta60) NaN 은 제외, 보조(days_since_high) NaN=0.5, 높은 beta·최근 신고가일수록 상위.
  3. 첫 거래일 게이트 — 같은 달에 더 이른 거래일이 있으면 False.
  4. 그룹당 상한 — cap=4 이면 한 그룹에서 5번째는 건너뛰고 다음 순위로.
  5. 클러스터 결정성 — 같은 입력이면 같은 라벨(seed 고정).
실행: python tests/test_lead_observe_rules.py
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lead_observe as lo

P = 0
def check(n, c, info=""):
    global P
    assert c, f"FAIL: {n} {info}"
    P += 1
    print(f"  ok  {n}" + (f"  [{info}]" if info else ""))

print("[1] spec_hash 골든")
check("ld_a", lo.spec_hash("ld_a") == "4f01c8fcfb95", lo.spec_hash("ld_a"))
check("ld_ctl_amt", lo.spec_hash("ld_ctl_amt") == "ea086b02aa03", lo.spec_hash("ld_ctl_amt"))
check("상수 동결", (lo.TOP_N, lo.CLUSTER_K, lo.CLUSTER_CAP, lo.CLUSTER_SEED, lo.LOOKBACK) == (20, 25, 4, 0, 330))

print("[2] 순위합")
beta = np.array([[1.5, 1.2, np.nan, 0.8, 1.0]]); dsh = np.array([[0, 60, 5, np.nan, 300]])
rb = lo.rank01(beta)[0]; rd = lo.rank01(dsh)[0]
sc = lo.rank_sum(rb, [1 - rd])
check("핵심 NaN 제외", not np.isfinite(sc[2]))
check("보조 NaN=0.5", abs(sc[3] - (rb[3] + 0.5)) < 1e-12)
check("고베타+신고가 1위", int(np.nanargmax(sc)) == 0)
check("저베타+오래된 고점 최하위", int(np.nanargmin(np.where(np.isfinite(sc), sc, np.inf))) == 4)

print("[3] 첫 거래일 게이트")
dates = ["20260827", "20260828", "20260901", "20260902", "20261001"]
check("9/1 은 첫 거래일", lo.is_first_trading_day(dates, "20260901"))
check("9/2 는 아님", not lo.is_first_trading_day(dates, "20260902"))
check("10/1 (다음 달 첫날)", lo.is_first_trading_day(dates, "20261001"))

print("[4] 그룹당 상한")
order = np.arange(10); labels = {i: (0 if i < 6 else 1) for i in range(10)}
pick = lo.pick_with_cap(order, labels, 4, 6)
check("그룹0 은 4개까지, 5·6번째는 그룹1", pick == [0, 1, 2, 3, 6, 7], str(pick))
check("상한 0 = 상한 없음", lo.pick_with_cap(order, labels, 0, 6) == [0, 1, 2, 3, 4, 5])

print("[5] 클러스터 결정성")
rng = np.random.default_rng(1); r = rng.normal(size=(120, 60))
r[:, :30] += rng.normal(size=(120, 1)) * 2   # 두 블록
l1 = lo.cluster_labels(r, k=5); l2 = lo.cluster_labels(r, k=5)
check("같은 입력 → 같은 라벨", np.array_equal(l1, l2))
check("블록 구조 반영(앞 30개 다수 라벨 == 뒤 30개 다수 라벨 아님)", np.bincount(l1[:30]).argmax() != np.bincount(l1[30:]).argmax())

print(f"\n✅ test_lead_observe_rules: {P}개 체크 전체 통과")
