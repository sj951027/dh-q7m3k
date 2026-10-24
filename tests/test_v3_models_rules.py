# -*- coding: utf-8 -*-
"""v3 트랙 모델 스펙 골든 회귀 테스트 (정적 — DB 불필요)

고정하는 규칙 (PREREGISTER_v32a.md, 2026-10-24 배선):
  1. spec_hash 골든 — v30 510c58bd5f31(챔피언, v3_scores 전 행과 같은 값) · v32a ac5f7b6ca5d0. 은퇴 v31a~g 도 불변.
  2. v32a 의 훅 키(liquidity_cap_median)는 v32a 에만 있다 — SPEC_V30 에 넣으면 v30·v31* 해시가 바뀐다.
  3. v32a 는 RETIRED 가 아니고(섀도우·동결 대상), freeze_scores·checkup 등록일에 올라 있다.
v30 결과 0-diff 는 history.db 로 따로 보였다(research/v32a_zero_diff_20261024.txt — 325셀 다른 칸 0).
실행: python tests/test_v3_models_rules.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import v3_rescore as v3
import freeze_scores as fz
import checkup

P = 0
def check(n, c, info=""):
    global P
    assert c, f"FAIL: {n} {info}"
    P += 1
    print(f"  ok  {n}" + (f"  [{info}]" if info else ""))

print("[1] spec_hash 골든")
GOLDEN = {"v30": "510c58bd5f31", "v31a": "e7ee14ab191d", "v31b": "f48659fce4e9", "v31c": "07f08b1f8f90",
          "v31d": "8b92771c4785", "v31f": "fbadd2eb31a9", "v31g": "89162416ffc5", "v32a": "ac5f7b6ca5d0"}
for m, h in GOLDEN.items():
    check(f"{m} spec_hash = {h}", fz.spec_hash(m) == h, fz.spec_hash(m))

print("[2] v32a 훅은 v32a 에만")
check("SPEC_V30 에 liquidity_cap_median 없음", "liquidity_cap_median" not in v3.SPEC_V30)
check("v32a liquidity_cap_median=True", v3.MODELS["v32a"].get("liquidity_cap_median") is True)
others = {k: v for k, v in v3.MODELS.items() if k != "v32a"}
check("다른 모델엔 키 없음", all("liquidity_cap_median" not in s for s in others.values()), str([k for k, s in others.items() if "liquidity_cap_median" in s]))
diff_keys = {k for k in set(v3.MODELS["v32a"]) | set(v3.SPEC_V30) if v3.MODELS["v32a"].get(k) != v3.SPEC_V30.get(k)}
check("v30 대비 다른 키 = label·liquidity_cap_median 뿐(변수 1개)", diff_keys == {"label", "liquidity_cap_median"}, str(sorted(diff_keys)))

print("[3] 적재·등록 연결")
check("v32a RETIRED 아님", "v32a" not in v3.RETIRED)
check("freeze_scores ARCHIVE_MAP 에 v32a_archive", fz.ARCHIVE_MAP.get("v32a") == ("v32a_archive", None), str(fz.ARCHIVE_MAP.get("v32a")))
check("checkup.REG_DATE 에 v32a", "v32a" in checkup.REG_DATE, checkup.REG_DATE.get("v32a", ""))

print(f"\n✅ v3 모델 스펙 골든 {P}개 체크 통과")
