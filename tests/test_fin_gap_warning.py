# -*- coding: utf-8 -*-
"""텔레그램 재무 결손 경고 기준(2026-10-02) — 합성 입력만, 네트워크·운영 DB 미접촉.

계약:
  A. 시장별 결손률이 FIN_GAP_WARN 이상이면 그 시장 이름·건수·비율로 경고 한 줄. 미만이면 없음.
  B. 두 시장을 합치면 10% 아래로 희석되는 날(KOSDAQ 만 빔)도 잡는다 — 2026-10-02 20:10 배치가 그 사례.
  C. 전일도 나빴던 '연속 결손일'에도 울린다(종전 '전일의 2배' 조건 없음).
  D. 시장별 종목 수가 FIN_GAP_MIN_N 미만이면 판단하지 않는다. 입력이 비거나 깨져도 예외 없음.
  E. 경고 줄은 ⚠️ 로 시작한다 → build_message 첫 줄이 '확인 필요'가 된다.
실행: python tests/test_fin_gap_warning.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import notify_telegram as nt

fails = 0


def check(name, cond):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        fails += 1


F = nt._fin_gap_lines
print("A. 기준선")
check("상수: 5% · 시장별 30종목", nt.FIN_GAP_WARN == 0.05 and nt.FIN_GAP_MIN_N == 30)
check("평소(1/289, 4/334) → 경고 없음", F({"kospi": (289, 1), "kosdaq": (334, 4)}, {"kospi": (325, 1), "kosdaq": (394, 6)}) == [])
check("평소 최대(7/421 = 1.7%) → 경고 없음", F({"kosdaq": (421, 7)}) == [])
r = F({"kospi": (276, 1), "kosdaq": (296, 50)}, {"kospi": (289, 1), "kosdaq": (334, 4)})
check("KOSDAQ 50/296 → 한 줄", len(r) == 1)
check("  시장·건수·비율·전일", r and "KOSDAQ 50/296 (17%, 전일 1%)" in r[0])
check("  ⚠️ 로 시작(첫 줄 '확인 필요' 조건)", r and r[0].startswith("⚠️ 재무 결손"))
check("경계: 정확히 5%(15/300) → 경고", len(F({"kosdaq": (300, 15)})) == 1)
check("경계 바로 아래(14/300) → 없음", F({"kosdaq": (300, 14)}) == [])

print("B. 합산하면 희석되는 날")
now = {"kospi": (276, 1), "kosdaq": (296, 46)}
tot = sum(v[1] for v in now.values()) / sum(v[0] for v in now.values())
check(f"합산 결손률 {tot:.1%} < 10%(종전 기준 미달)", tot < 0.10)
check("새 기준은 KOSDAQ 으로 잡는다", len(F(now, {"kospi": (289, 1), "kosdaq": (334, 4)})) == 1)

print("C. 연속 결손일")
r = F({"kospi": (224, 0), "kosdaq": (647, 68)}, {"kospi": (220, 0), "kosdaq": (610, 70)})   # 9/03, 전일 9/02 도 11%
check("전일도 나빴어도 울린다(9/03 사례)", len(r) == 1 and "전일 11%" in r[0])

print("D. 가드")
check("시장별 30종목 미만은 판단 안 함(18종목 중 9개)", F({"kospi": (18, 9), "kosdaq": (4, 4)}) == [])
check("두 시장 모두 나쁘면 두 줄(시장 이름순)", [x.split()[3] for x in F({"kosdaq": (300, 60), "kospi": (300, 30)})] == ["KOSDAQ", "KOSPI"])
check("전일 정보 없음 → '전일' 표기 생략", "전일" not in F({"kosdaq": (300, 60)})[0])
check("빈 입력·None", F({}) == [] and F(None) == [] and F({"kosdaq": (300, 60)}, None) != [])
check("깨진 값은 건너뛴다(예외 없음)", F({"kosdaq": (None, None), "kospi": ("x", 1)}) == [])
check("결손 수 None 은 0 으로", F({"kosdaq": (300, None)}) == [])

print(("\n❌ 실패 %d건" % fails) if fails else "\n✅ test_fin_gap_warning 통과")
sys.exit(1 if fails else 0)
