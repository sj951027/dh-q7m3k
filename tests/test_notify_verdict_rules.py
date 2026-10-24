# -*- coding: utf-8 -*-
"""판정 도달 알림(notify_verdict_ready) 규칙 회귀 테스트 (합성 — 실제 DB·네트워크·상태 파일 불사용)

고정하는 규칙 (2026-10-24 Codex 재점검 R1·R2):
  1. 셈 = leaderboard 의 유효 앵커 — 등록일 run 포함 · 게이트 run 제외 · 주말 run 은 직전 거래일로 중복 제거(R1).
  2. 옛 셈(대체 경로)도 등록일 run 을 포함한다.
  3. 텔레그램 전송이 실패하면 '알림 완료' 상태를 쓰지 않는다 · 성공하면 쓴다(R2).
  3b. 정확한 셈(gate_ctx)이 실패한 날은 알림·완료 기록을 건너뛴다 — 옛 셈이 주말 중복으로 많게 세는 것을 실제로 재현(Codex 재검토 F1).
  4. 등록 대상에 lv_e·sv_b·v32a, sv_b 는 wu 트랙.
실행: python tests/test_notify_verdict_rules.py
"""
import sqlite3, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import leaderboard as lb
import notify_verdict_ready as nv

P = 0
def check(n, c, info=""):
    global P
    assert c, f"FAIL: {n} {info}"
    P += 1
    print(f"  ok  {n}" + (f"  [{info}]" if info else ""))

print("[1] 유효 앵커 셈 = leaderboard")
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE lowvol_scores (run_id TEXT, model_id TEXT)")
runs = ["20260831", "20260901", "20260902", "20260905", "20260906", "20260907", "20260908"]   # 0831 등록 전 · 0905(토)·0906(일) 은 0904 앵커 · 0908 게이트
con.executemany("INSERT INTO lowvol_scores VALUES (?, 'lv_e')", [(r,) for r in runs])
trade = ["20260831", "20260901", "20260902", "20260903", "20260904", "20260907", "20260908"]
didx = {d: i for i, d in enumerate(trade)}
ctx = (lb, didx, {"20260908"})
n = nv.oos_days(con, "lv_e", ctx)
check("등록일 0901 포함 · 0831 제외 · 주말 2개 → 1 · 게이트 0908 제외 → 4(0901·0902·0904앵커·0907)", n == 4, str(n))
check("옛 셈도 등록일 포함(>=)", nv.oos_days(con, "lv_e", None) == 6, str(nv.oos_days(con, "lv_e", None)))   # 고정 GATES 에 0908 없음 → 0901~0908 6개
check("옛 셈은 주말 중복을 못 걸러 많게 셈(그래서 알림엔 안 씀)", nv.oos_days(con, "lv_e", None) > n)

print("[2] 등록 대상")
check("lv_e·sv_b·v32a 등록", all(m in nv.REG_DATE for m in ("lv_e", "sv_b", "v32a")))
check("sv_b = wu 트랙 · v32a = v3 · lv_e = lowvol", (nv.TRACK["sv_b"], nv.TRACK["v32a"], nv.TRACK["lv_e"]) == ("wu", "v3", "lowvol"))

print("[3] 전송 성공 때만 상태 기록")
orig = (nv.REG_DATE, nv.oos_days, nv.send_telegram, nv.STATE, nv.DB_PATH, nv.gate_ctx, sys.argv)
with tempfile.TemporaryDirectory() as td:
    try:
        db = Path(td) / "h.db"; sqlite3.connect(db).close()
        nv.DB_PATH = db; nv.STATE = Path(td) / "state.json"; sys.argv = ["notify_verdict_ready.py"]
        nv.REG_DATE = {"lv_e": "20260901"}; nv.oos_days = lambda con, m, ctx=None: 40
        sent = []
        nv.gate_ctx = lambda con: None; nv.send_telegram = lambda msg: sent.append(msg) or True
        nv.main(); check("정확한 셈 실패한 날 → 전송 안 함 · 상태 안 씀", sent == [] and not nv.STATE.exists())
        nv.gate_ctx = lambda con: ("ctx",)                     # 정확한 셈 준비 성공(값은 oos_days 가 대신)
        nv.send_telegram = lambda msg: False
        nv.main(); check("전송 실패 → 상태 파일 안 씀", not nv.STATE.exists())
        nv.send_telegram = lambda msg: True
        nv.main(); check("전송 성공 → 상태 파일에 lv_e", nv.STATE.exists() and "lv_e" in nv.STATE.read_text(encoding="utf-8"))
        sent = []
        nv.send_telegram = lambda msg: sent.append(msg) or True
        nv.main(); check("이미 알린 모델은 다시 안 보냄", sent == [])
    finally:
        nv.REG_DATE, nv.oos_days, nv.send_telegram, nv.STATE, nv.DB_PATH, nv.gate_ctx, sys.argv = orig

print(f"\n✅ 판정 도달 알림 규칙 {P}개 체크 통과")
