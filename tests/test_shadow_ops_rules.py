# -*- coding: utf-8 -*-
"""shadow_ops_portfolio(§1 판정 도구) 규칙 단위 테스트 — DB 없이 합성 자료로 손계산과 대조. 2026-09-16
실행: python tests/test_shadow_ops_rules.py
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import importlib.util
spec = importlib.util.spec_from_file_location("sop", Path(__file__).resolve().parents[1] / "research" / "shadow_ops_portfolio.py")
sop = importlib.util.module_from_spec(spec)
# 모듈 import 시 DB 를 열지 않는다(함수만 정의) — load() 는 호출하지 않음
spec.loader.exec_module(sop)
fails = 0


def ok(name, cond, detail=""):
    global fails
    print(f"  {'ok ' if cond else 'FAIL'} {name} {detail}")
    fails += 0 if cond else 1

# 1) last_px: 청산일에 가격 없으면 그 이전 마지막 유효가(보유 중 정지·상폐 = 마지막 가격 청산)
P = np.array([[100.0], [110.0], [np.nan], [np.nan]])
ok("1 청산일 결측 → 마지막 가격", sop.last_px(P, 0, 3) == 110.0, f"got {sop.last_px(P, 0, 3)}")
ok("1b 유효가 있으면 그날 가격", sop.last_px(P, 0, 1) == 110.0)

# 2) cohorts: 진입일 인덱스를 40거래일 단위로 → 0~39 → 1개, 0·40·41·85 → 3개
ok("2 코호트 수", sop.cohorts([0, 5, 39]) == 1 and sop.cohorts([0, 40, 41, 85]) == 3, f"{sop.cohorts([0,5,39])},{sop.cohorts([0,40,41,85])}")

# 3) block_boot: 블록 1개면 판정불가(nan); 블록 2개 이상이면 구간 산출, 상수 자료면 구간 폭 0
lo, hi, nb = sop.block_boot([1, 2, 3], [0, 1, 2])
ok("3a 블록 1개 → nan", np.isnan(lo) and nb == 1)
lo, hi, nb = sop.block_boot([2.0] * 6, [0, 1, 40, 41, 80, 81])
ok("3b 블록 3개·상수 → CI = 값", nb == 3 and abs(lo - 2.0) < 1e-9 and abs(hi - 2.0) < 1e-9, f"[{lo},{hi}] nb={nb}")

# 4) verdict §2 논리식
ok("4a 상단<0 → 부적합", sop.verdict(-2, -3, -0.5, 5, 0.3, True, False) == "운용 부적합")
ok("4b 하단≤0 → 노이즈", sop.verdict(1, -0.2, 2, 5, 0.7, True, True) == "운용 노이즈")
ok("4c 하단>0·코호트 부족 → 기움", sop.verdict(2, 0.5, 3, 3, 0.7, True, True) == "운용 기움")
ok("4d 하단>0·국면 미달 → 기움", sop.verdict(2, 0.5, 3, 5, 0.7, False, True) == "운용 기움")
ok("4e 하단>0·크기 미달 → 기움", sop.verdict(0.8, 0.5, 3, 5, 0.7, True, False) == "운용 기움")
ok("4f 하단>0·양(+) 50% → 기움", sop.verdict(2, 0.5, 3, 5, 0.5, True, True) == "운용 기움")
ok("4g 전부 충족 → 채택", sop.verdict(2, 0.5, 3, 5, 0.7, True, True) == "운용 채택")
ok("4h CI 없음 → 판정불가", sop.verdict(2, np.nan, np.nan, 5, 0.7, True, True) == "판정불가")

# 5) Bonferroni 수준: 두 모델 family → 97.5% 구간 (α/2)
ok("5 α/2 구간", abs((1 - sop.ALPHA_FAMILY) - 0.975) < 1e-12)

print("\n" + ("❌ shadow_ops 규칙 실패 " + str(fails) if fails else "✅ shadow_ops 규칙 테스트 통과"))
sys.exit(1 if fails else 0)
