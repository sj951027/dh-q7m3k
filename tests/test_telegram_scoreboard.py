# -*- coding: utf-8 -*-
"""텔레그램 성적표 줄(2026-10-02) — 합성 입력만, 네트워크·운영 DB 미접촉, 전송 없음.

계약:
  A. _scoreboard_row: 40일 끝난 매수분이 있으면 '모델 +x.x%p · n일 · 쉬운 결론', 없으면 '결과 대기 · 결론'.
     결론 말은 리더보드 첫 화면과 같은 뜻(유의=효과 확인됨·기움=확정 못 함·노이즈=차이 없음·역작동=반대로 감·없음=결론 전).
  B. 본문: 성적표 블록이 나오고, '최근 1개월'(시장 대비 %p) 블록은 매일 알림에 없다.
  C. 맨 아래 링크는 성적표가 먼저이고, 표시 모델의 목록 페이지가 뒤따른다.
  D. 깨진 입력에도 예외 없이 None/폴백.
실행: python tests/test_telegram_scoreboard.py
"""
import re
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


R = nt._scoreboard_row
print("A. 한 줄 만들기")
check("완료분 있음 + 유의", R("v30", {"fix": {"n": 38, "exc_mean": 3.84}, "sealed": {"v": "유의"}}) == "v30    +3.8%p · 38일 · 효과 확인됨")
check("두 자리 수익도 폭 유지", R("le_a", {"fix": {"n": 13, "exc_mean": 10.73}, "sealed": {"v": "노이즈"}}) == "le_a  +10.7%p · 13일 · 차이 없음")
check("음수", R("lv_b", {"fix": {"n": 25, "exc_mean": -1.66}, "sealed": {"v": "기움"}}) == "lv_b   -1.7%p · 25일 · 확정 못 함")
check("역작동", R("mom_b", {"fix": {"n": 11, "exc_mean": -1.1}, "sealed": {"v": "역작동"}}).endswith("반대로 감"))
check("완료분 없음 + 판정 전", R("px_a", {"fix": None, "sealed": None}) == "px_a  결과 대기 · 결론 전")
check("성적표에 없는 모델(None)", R("zz_z", None) == "zz_z  결과 대기 · 결론 전")
check("시장 대비 값은 %p 로 적는다(0 도 +0.0%p)", R("v30", {"fix": {"n": 1, "exc_mean": 0.0}}).startswith("v30    +0.0%p · 1일"))
check("깨진 행은 None(예외 없음)", R("v30", {"fix": {"n": "x", "exc_mean": "y"}}) is None)

print("B·C. 본문")
body = nt._status_lines_v3()
txt = "\n".join(body)
check("성적표 블록", any(x.startswith("📊 <b>성적표</b>") for x in body))
check("매일 알림에 '최근 1개월' 없음", "최근 1개월" not in txt and nt.MONEY_DAILY_V3 is False)
check("표시 모델이 <pre> 안에 순서대로", all(m in txt for m in nt.SHOW_V3)
      and [txt.index(f"\n{m}") if f"\n{m}" in txt else txt.index(m) for m in nt.SHOW_V3] == sorted(
          [txt.index(f"\n{m}") if f"\n{m}" in txt else txt.index(m) for m in nt.SHOW_V3]))
msg = nt.build_message()
link = [x for x in msg.split("\n") if x.startswith("🔎")]
check("링크 줄 하나", len(link) == 1)
hrefs = re.findall(r'href="([^"]+)"', link[0]) if link else []
check("성적표(leaderboard.html)가 첫 링크", hrefs and hrefs[0].endswith("/leaderboard.html"))
check("표시 모델 목록 링크가 뒤따름", [h.rsplit("/", 1)[1] for h in hrefs[1:]] == [nt.MODEL_PAGE_V3[m].rsplit("/", 1)[1] for m in nt.SHOW_V3 if m in nt.MODEL_PAGE_V3])
check("'저변동 종목 보기' 문구 없음", "저변동 종목 보기" not in msg)
check("첫 줄은 ✅ 또는 ⚠️", msg.startswith("✅") or msg.startswith("⚠️"))

print(("\n❌ 실패 %d건" % fails) if fails else "\n✅ test_telegram_scoreboard 통과")
sys.exit(1 if fails else 0)
