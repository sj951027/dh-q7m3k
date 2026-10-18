# -*- coding: utf-8 -*-
"""자료 건강 점검표(2026-10-18) — 순수 함수 계약 + 과거 사고 되감기 재현(운영 DB 읽기 전용).

계약:
  A. trading_lag: 거래일 달력으로 센다(주말·휴장 건너뜀). 같은 날이면 0, 자료 없으면 None.
  B. assess: 허용 지연 초과 → 'lag', 마지막 날 건수가 평소 절반 미만 → 'count', 자료 없음 → 'missing', 나머지 'ok'.
     건수 검사를 안 하는 갈래(공시 등)는 건수가 줄어도 'ok'. 신용잔고는 허용 4(정상 3거래일 지연).
  C. 되감기(실제 DB, fetched_at 기준): 보충표 10/06 시점 → 뒤처짐 경고 · 수급 9/11 시점 → 뒤처짐 경고 ·
     현재 시점 → 그 두 갈래는 ok(사고가 고쳐진 상태). DB 가 없으면 C 는 건너뛴다.
  D. telegram_lines 는 예외 없이 목록을 돌려준다.
실행: python tests/test_data_health.py
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import data_health as dh  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    print(("  OK  " if cond else "  FAIL") + " " + name)
    if not cond:
        fails += 1


print("[A] trading_lag")
cal = ["20261006", "20261007", "20261008", "20261012", "20261013", "20261014", "20261015", "20261016"]   # 10/9 휴장·주말 없음
check("같은 날 0", dh.trading_lag("20261016", "20261016", cal) == 0)
check("하루 전 1", dh.trading_lag("20261015", "20261016", cal) == 1)
check("주말·휴장 건너뛰고 셈(10/08 → 10/16 = 5거래일)", dh.trading_lag("20261008", "20261016", cal) == 5)
check("달력에 없는 날짜(10/11 토)도 그 사이 거래일로 셈(10/12~16 = 5)", dh.trading_lag("20261011", "20261016", cal) == 5)
check("자료 없음 None", dh.trading_lag(None, "20261016", cal) is None)
check("기준일보다 뒤면 0", dh.trading_lag("20261017", "20261016", cal) == 0)

print("[B] assess")
ok = {"last": "20261016", "n_last": 2600, "n_hist": [2630] * 10}
br = {k: dict(ok) for k, *_ in dh.BRANCHES}
br["credit"] = {"last": "20261013", "n_last": 2416, "n_hist": [2420] * 10}      # 정상 3거래일 지연
br["consensus"] = {"last": "20261012", "n_last": 2515, "n_hist": [2516] * 5}   # 주 1회
rows = dh.assess(br, "20261016", cal)
st = {r["key"]: r["status"] for r in rows}
check("전부 정상이면 전부 ok", all(v == "ok" for v in st.values()))
check("경고 줄 없음", dh.warning_lines(rows, "20261016") == [])
br2 = {k: dict(v) for k, v in br.items()}
br2["extra"] = {"last": "20261008", "n_last": 136, "n_hist": [136] * 10}
br2["credit"] = {"last": "20261007", "n_last": 2400, "n_hist": [2420] * 10}    # 6거래일 → 허용 4 초과
br2["flows"] = {"last": "20261016", "n_last": 900, "n_hist": [2760] * 10}      # 건수 급감
br2["dart"] = {"last": "20261016", "n_last": 1, "n_hist": [23] * 10}           # 건수 검사 안 함
br2["uni_events"] = {"last": None, "n_last": None, "n_hist": []}
rows2 = dh.assess(br2, "20261016", cal)
st2 = {r["key"]: r for r in rows2}
check("보충표 5거래일 뒤처짐 → lag", st2["extra"]["status"] == "lag" and st2["extra"]["lag"] == 5)
check("신용잔고 6거래일 → lag(허용 4)", st2["credit"]["status"] == "lag")
check("수급 건수 절반 미만 → count", st2["flows"]["status"] == "count")
check("공시는 건수 검사 안 함 → ok", st2["dart"]["status"] == "ok")
check("상장 변화 자료 없음 → missing", st2["uni_events"]["status"] == "missing")
w = dh.warning_lines(rows2, "20261016")
check("경고 줄 4개, 전부 ⚠️ 로 시작", len(w) == 4 and all(x.startswith("⚠️") for x in w))
check("경고 문구에 갈래 이름·날짜", any("보충표" in x and "10/08" in x for x in w))
md = dh.to_markdown(rows2, "20261016", "now")
check("markdown 표에 14갈래 행", md.count("\n| ") == len(dh.BRANCHES) + 1)

print("[C] 되감기 — 과거 사고 재현(실제 DB, 읽기 전용)")
if os.path.exists(dh.OHLCV_DB):
    rows_a, ref_a, w_a = dh.run(asof="20261006_2359")
    ex = {r["key"]: r for r in rows_a}
    check("보충표 10/06 시점: 뒤처짐 경고(실측 마지막 9/23)", ex.get("extra", {}).get("status") == "lag" and ref_a == "20261006")
    rows_b, ref_b, w_b = dh.run(asof="20260911_2359")
    fb = {r["key"]: r for r in rows_b}
    check("수급 9/11 시점: 뒤처짐 경고(실측 마지막 9/09)", fb.get("flows", {}).get("status") == "lag")
    rows_c, ref_c, w_c = dh.run()
    fc = {r["key"]: r for r in rows_c}
    check("현재: 보충표·수급은 ok(고쳐진 상태)", fc.get("extra", {}).get("status") == "ok" and fc.get("flows", {}).get("status") == "ok")
    check("현재: 신용잔고 지연이 허용 안(3≤4)", fc.get("credit", {}).get("status") == "ok" and (fc["credit"]["lag"] or 0) <= 4)
    print("   현재 경고:", w_c or "없음")
else:
    print("   (DB 없음 — 건너뜀)")

print("[D] telegram_lines 예외 없음")
check("목록 반환", isinstance(dh.telegram_lines(), list))

print("\n" + ("❌ 실패 %d" % fails if fails else "✅ test_data_health 통과"))
sys.exit(1 if fails else 0)
