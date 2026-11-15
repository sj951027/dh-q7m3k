# -*- coding: utf-8 -*-
"""지식 감시 장치의 배치 시간 판단·약속 장부 읽기(2026-11-15) — 임시 폴더·합성 글만, 저장소 파일·git·DB 미접촉.

사건: ① 감시 장치가 평일 20:10~22:30 에 통째로 꺼져 있어 저녁 세션(11/13 21:16)이 시작 알림을 못 받았다.
      ② 원장이 약속한 'sv_b 판정문 10/14 병기'와 규약의 자리바꿈 참고값이 판정문에서 빠졌는데 알려 주는 것이 없었다.
계약:
  A. 배치 창 = 평일 20:10~22:30. 주말·창 밖은 'full'.
  B. 창 안: 오늘 로그 꼬리에 끝 줄이 있으면 'full', 없거나 로그가 없으면 'readonly'. SKIPPED 로그만 있으면 'full'.
  C. KNOWLEDGE_GUARD_OFF=1 이면 'off'.
  D. 약속 장부: 열린 약속 중 기한 지난 것·임박한 것·조건부 수를 낸다. 완료 약속은 안 뜬다. 완료인데 근거가 비면 알린다.
  E. 저장소의 실제 `PROMISES.md` 가 형식대로 읽힌다(행 ≥ 1, 상태는 열림/완료/취소 로 시작, 완료 행은 근거 있음).
실행: python tests/test_knowledge_guard.py
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import knowledge_guard as g  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    if not cond:
        fails += 1
    print(("  ok  " if cond else "  FAIL ") + name)


os.environ.pop("KNOWLEDGE_GUARD_OFF", None)
FRI = dt.datetime(2026, 11, 13, 21, 16)   # 금요일 저녁(사건이 난 시각)
SUN = dt.datetime(2026, 11, 15, 21, 16)
print("A. 배치 창")
check("금 21:16 은 창 안", g.in_batch_window(FRI))
check("금 20:09 는 창 밖", not g.in_batch_window(dt.datetime(2026, 11, 13, 20, 9)))
check("금 22:31 은 창 밖", not g.in_batch_window(dt.datetime(2026, 11, 13, 22, 31)))
check("일 21:16 은 창 밖", not g.in_batch_window(SUN))

print("B. 배치 끝남 판단")
with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    check("로그 없음 → readonly", g.run_mode(FRI, d) == "readonly")
    log = d / "auto_run_20261113_2010.log"
    log.write_bytes(b"step 1\r\nstep 2\r\n")
    check("끝 줄 없음(도는 중) → readonly", g.run_mode(FRI, d) == "readonly")
    log.write_bytes(b"x" * 9000 + b"\r\n  [OK] Done.  End: 2026-11-13 21:06:10.80\r\n====\r\n  Output:\r\n")
    check("끝 줄 있음 → full", g.run_mode(FRI, d) == "full")
    (d / "auto_run_20261112_2010.log").write_bytes(b"  [OK] Done.  End: 2026-11-12 21:39:11.84\r\n")
    log.write_bytes(b"step 1\r\n")
    check("어제 로그의 끝 줄은 오늘에 안 쓴다 → readonly", g.run_mode(FRI, d) == "readonly")
    check("주말은 로그와 무관하게 full", g.run_mode(SUN, d) == "full")
    DONE = b"========\r\n  Start: 2026-11-13 20:10:00.00\r\nstep\r\n  [OK] Done.  End: 2026-11-13 21:06:10.80\r\n"
    log.write_bytes(DONE)
    check("시작 → 끝 줄 → full", g.run_mode(FRI, d) == "full")
    log.write_bytes(DONE + b"========\r\n  Start: 2026-11-13 21:10:00.00\r\nstep 1\r\n")
    check("같은 로그에 재실행이 덧붙어 도는 중 → readonly", g.run_mode(FRI, d) == "readonly")
    log.write_bytes(DONE)
    man = d / "manual_run_20261113_2112.log"
    man.write_bytes(b"========\r\n  Start: 2026-11-13 21:12:00.00\r\nstep 1\r\n")
    check("자동은 끝났지만 수동 실행이 도는 중 → readonly", g.run_mode(FRI, d) == "readonly")
    man.write_bytes(DONE)
    check("자동·수동 둘 다 끝남 → full", g.run_mode(FRI, d) == "full")
    check("로그는 끝났지만 다른 python 이 돈다 → readonly", g.run_mode(FRI, d, proc_check=lambda: True) == "readonly")
    check("로그 끝 + 다른 python 없음 → full", g.run_mode(FRI, d, proc_check=lambda: False) == "full")
    check("로그 끝 + 프로세스 확인 실패(None) → 로그 판단대로 full", g.run_mode(FRI, d, proc_check=lambda: None) == "full")
    log.write_bytes(b"step 1\r\n")
    check("로그가 안 끝났으면 프로세스가 없어도 readonly", g.run_mode(FRI, d, proc_check=lambda: False) == "readonly")
check("프로세스 확인은 True/False/None 중 하나를 돌려준다(예외 없음)", g.other_python_running() in (True, False, None))
with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    (d / "auto_run_20261113_2010_SKIPPED.log").write_bytes(b"[skip_dates] 20261113 is listed\r\n")
    check("SKIPPED 로그만 → full(오늘 배치 없음)", g.run_mode(FRI, d) == "full")

print("C. 끄기")
os.environ["KNOWLEDGE_GUARD_OFF"] = "1"
check("KNOWLEDGE_GUARD_OFF=1 → off", g.run_mode(SUN) == "off")
os.environ.pop("KNOWLEDGE_GUARD_OFF", None)

print("D. 약속 장부 읽기(합성)")
TXT = """
| ID | 기한·조건 | 무엇 | 나온 곳 | 상태 | 완료 근거 |
|---|---|---|---|---|---|
| P01 | 2026-11-10 | 지난 약속 | 원장 | 열림 | — |
| P02 | ≈2026-11-20 | 임박한 약속 | 지도 | 열림 | — |
| P03 | 2027-06-30 | 먼 약속 | 규약 | 열림 | — |
| P04 | 조건: 급락 사건 30개 | 조건부 약속 | K10 | 열림 | — |
| P05 | 판정 때(sv_b) | 끝난 약속 | 원장 | 완료(11/15) | VERDICT 추기 |
| P06 | 2026-11-01 | 끝났다고만 적은 약속 | 원장 | 완료 | — |
| P07 | 2026-11-01 | 취소한 약속 | 지도 | 취소(사유) | — |
"""
rows = g.parse_promises(TXT)
check("7행을 읽는다", len(rows) == 7)
check("≈ 붙은 날짜도 날짜로 읽는다", rows[1]["date"] == dt.date(2026, 11, 20))
check("조건부는 날짜 없음", rows[3]["date"] is None)
out = "\n".join(g.promise_lines(TXT, dt.date(2026, 11, 15)))
check("기한 지남에 P01", "기한 지남" in out and "P01" in out.split("기한 지남")[1].split("\n")[0])
check("임박에 P02", "임박" in out and "P02" in out.split("임박")[1].split("\n")[0])
check("먼 약속 P03 은 지남·임박 줄에 없다", "P03" not in out.split("열린 약속")[0])
check("열린 약속 4건(날짜 3 · 조건부 1)", "열린 약속 4건(날짜 있는 것 3 · 조건부 1)" in out)
check("완료·취소(P05·P07)는 지남 줄에 없다", "P05" not in out.split("열린 약속")[0] and "P07" not in out)
check("완료인데 근거 빈 P06 을 알린다", "근거 칸이 빈 약속: P06" in out)
check("장부가 없으면 빈 목록", g.promise_lines("", dt.date(2026, 11, 15)) == [])

print("E. 저장소의 실제 약속 장부")
p = REPO / "PROMISES.md"
if p.exists():
    real = g.parse_promises(p.read_text(encoding="utf-8"))
    check("행 1개 이상", len(real) >= 1)
    raw = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("| P")]
    check(f"'| P' 로 시작하는 줄({len(raw)})이 전부 읽힌다 — 칸이 모자라거나 밀리면 여기서 걸린다", len(raw) == len(real))
    cols = [ln for ln in raw if ln.count("|") != 7]
    check("모든 행이 6칸(세로줄 7개) — 글 안에 세로줄 금지" + (f" — 어긋남 {[c[:8] for c in cols]}" if cols else ""), not cols)
    check("ID 중복 없음", len({r["id"] for r in real}) == len(real))
    bad = [r["id"] for r in real if not r["status"].startswith(("열림", "완료", "취소"))]
    check("상태는 열림/완료/취소 로 시작" + (f" — 어긋남 {bad}" if bad else ""), not bad)
    np_ = [r["id"] for r in real if r["status"].startswith("완료") and r["proof"] in ("", "—", "-")]
    check("완료 행은 근거 칸이 있다" + (f" — 빈 행 {np_}" if np_ else ""), not np_)
else:
    check("PROMISES.md 가 있다", False)

print("F. 결론 카드와 색인(카드 0장이면 통과)")
import re  # noqa: E402
ktxt = (REPO / "KNOWLEDGE.md").read_text(encoding="utf-8")
cards = sorted((REPO / "knowledge").glob("K*.md")) if (REPO / "knowledge").exists() else []
badname = [c.name for c in cards if not re.fullmatch(r"K\d{2,3}\.md", c.name)]
check("카드 파일 이름은 K##.md" + (f" — {badname}" if badname else ""), not badname)
orphan = []; nohead = []
for c in cards:
    cid = c.stem
    rows = re.findall(rf"^\| {cid} .*$", ktxt, re.M)
    if len(rows) != 1 or f"knowledge/{cid}.md" not in rows[0]:
        orphan.append(cid)
    if not c.read_text(encoding="utf-8").lstrip().startswith(f"# {cid} "):
        nohead.append(cid)
check("카드마다 KNOWLEDGE 색인 줄이 정확히 하나이고 카드 경로를 가리킨다" + (f" — {orphan}" if orphan else ""), not orphan)
check("카드 첫 줄 제목의 번호가 파일 이름과 같다" + (f" — {nohead}" if nohead else ""), not nohead)
dangling = [m for m in re.findall(r"knowledge/(K\d{2,3})\.md", ktxt) if not (REPO / "knowledge" / f"{m}.md").exists()]
check("색인이 가리키는 카드가 실제로 있다" + (f" — {dangling}" if dangling else ""), not dangling)

# ── G. 결정 번호(2026-11-15, D40): 묶음 안 번호·결정 이력까지 본다 ──
import test_knowledge_sheets as ts  # noqa: E402


def _rows(ns):
    return "\n".join(f"| D{n:02d} 2026-01-01 | x | | | |" for n in ns)


nx, pb = ts.decision_ids("| D01 외 2026-10 | 묶음: 가(D01) · 나(D02, 끝) | | | |\n" + _rows([3]))
check("묶음 안 번호도 정의로 센다 → 다음 D04·문제 없음", nx == 4 and not pb)
nx, pb = ts.decision_ids(_rows([1, 3]))
check("번호가 빠지면 알린다", any("빠짐" in x for x in pb))
nx, pb = ts.decision_ids(_rows([1, 2, 2]))
check("장부 행 번호 중복을 알린다", any("중복" in x for x in pb))
nx, pb = ts.decision_ids(_rows(range(1, 40)), "## D40 · 2026-11-15 · x\n")
check("이력에만 있고 장부에 요약이 없으면 알린다(다음 번호는 D41)", nx == 41 and any("요약" in x for x in pb))
nx, pb = ts.decision_ids(_rows(range(1, 41)))
check("D40 부터 장부 줄만 있고 이력 원문이 없으면 알린다", any("원문" in x for x in pb))
nx, pb = ts.decision_ids(_rows(range(1, 41)), "## D40 · 2026-11-15 · x\n")
check("장부 한 줄 + 이력 원문 → 문제 없음·다음 D41", nx == 41 and not pb)
nx, pb = ts.decision_ids(_rows(range(1, 40)) + "\n요약 D40", "## D40 · a\n## D40 · b\n")
check("이력 절 번호 중복을 알린다", any("이력 절" in x and "중복" in x for x in pb))
big = _rows(range(1, 40)) + "\n| 요약 | " + " ".join(f"D{n}" for n in range(40, 300)) + " |"
nx, pb = ts.decision_ids(big, "".join(f"## D{n:02d} · x\n" for n in range(40, 300)))
check("세 자리 번호(D99→D100 · D299→D300)", nx == 300 and not pb)
droot = (REPO / "DECISIONS.md").read_text(encoding="utf-8"); dlp = REPO / ts.LOG_FILE
nx, pb = ts.decision_ids(droot, dlp.read_text(encoding="utf-8") if dlp.exists() else "")
check("실제 장부·이력: 번호 문제 없음" + (f" — {pb}" if pb else ""), not pb)
check(f"시작 알림의 다음 번호가 이력까지 본 값(D{nx:02d})과 같다", any(f"D{nx:02d} " in x for x in g.todo_lines()))
check("이력 훼손 확인은 목록을 돌려준다(예외 없음)", isinstance(g.log_tamper_lines(), list))

print("\n" + ("✅ test_knowledge_guard 통과" if not fails else f"❌ 실패 {fails}건"))
sys.exit(1 if fails else 0)
