# -*- coding: utf-8 -*-
"""lowvol_score 점수 규칙 회귀 테스트 (합성 데이터 — DB 불필요, 어디서든 즉시 실행)

고정하는 규칙(전부 과거 실측·사건으로 확정된 것):
  1. 핵심 팩터(factors[0]) NaN 종목은 점수 NaN(제외) — 0.5 희석 금지(IC 0.199→0.119 사건)
  2. 보조 팩터 NaN 은 0.5 중립
  3. 점수 = run×시장 내 백분위 순위합 (방향은 FACTORS 의 ascending)
  4. spec_hash 골든 — 등록 모델 10종의 해시 불변(스펙 드리프트 감지).
     ⚠ 새 모델 추가는 허용(목록에 추가만) — 기존 해시가 바뀌면 그건 스펙 변경 사고다.
실행: python tests/test_lowvol_score_rules.py  (PTW test_positions.py 와 동일한 plain-script 스타일)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
import lowvol_score as lv

P = 0
def check(n, c, info=""):
    global P
    assert c, f"FAIL: {n} {info}"
    P += 1
    print(f"  ok  {n}" + (f"  [{info}]" if info else ""))

print("[1] pct_rank — NaN 보존·방향")
s = pd.Series([1.0, 2.0, None, 4.0])
r = lv.pct_rank(s, ascending=False)   # 낮을수록 좋음 → 1.0 이 최고 백분위
check("NaN 유지", pd.isna(r[2]))
check("낮은 값이 높은 순위(asc=False)", r[0] == r.dropna().max() and r[3] == r.dropna().min(),
      f"{list(r)}")

print("\n[2] score_run — 핵심/보조 NaN 규칙")
df = pd.DataFrame({
    "realized_vol": [0.01, 0.02, None, 0.04],   # 핵심(낮을수록 좋음) — 3번째 NaN
    "roe_value":    [10.0, None, 30.0, 40.0],   # 보조(높을수록 좋음) — 2번째 NaN
})
sc = lv.score_run(df, ["realized_vol", "roe"])
check("핵심 NaN 종목은 점수 NaN(제외)", pd.isna(sc[2]))
check("나머지는 점수 산출", sc.drop(2).notna().all())
# 보조 NaN=0.5: 2번째 종목 = rv순위(2/3중 중간) + 0.5
rv = lv.pct_rank(df["realized_vol"], False)
check("보조 NaN → 0.5 중립 합산", abs(sc[1] - (rv[1] + 0.5)) < 1e-12, f"{sc[1]} vs {rv[1]+0.5}")
check("최저변동+최고ROE 가 1위", sc.idxmax() == 0)

print("\n[3] score_run — 순위합 정합(전 팩터 실측 시)")
df2 = pd.DataFrame({"realized_vol": [0.01, 0.02, 0.03], "roe_value": [5.0, 15.0, 25.0]})
sc2 = lv.score_run(df2, ["realized_vol", "roe"])
exp = lv.pct_rank(df2["realized_vol"], False) + lv.pct_rank(df2["roe_value"], True)
check("순위합 일치", (sc2 - exp).abs().max() < 1e-12)

print("\n[4] spec_hash 골든 — 등록 10종 불변")
GOLDEN = {  # 2026-08-29 동결 (변경되면 스펙 드리프트 — 절대 이 골든을 고치지 말고 원인 규명 먼저)
    "lv_a": "3e47e1d5b706", "lv_b": "b7d6bd0b51d9", "lv_c": "46879e4d1896",
    "lv_d": "5eafceace283", "lv_a3": "8ca0e58a36a9", "lv_short": "37757d4562ae",
    "hv_a": "d698f6ad3d60", "sm_a": "844193565faa", "mom_a": "395395b9081d",
    "mom_b": "147021a88bb0",
}
for m, h in GOLDEN.items():
    check(f"spec_hash({m})", lv.spec_hash(m) == h, lv.spec_hash(m))

print(f"\n✅ lowvol_score 규칙 {P}개 체크 통과")
