# -*- coding: utf-8 -*-
"""지식 세 층 자동 감시 — Claude Code hook 용 (2026-11-08 · 같은 날 저녁 Codex 검토 반영). `.claude/settings.json` 이 부른다.

이 장치는 "지식이 저절로 쌓임을 보증"하지 않는다. **누락 후보를 알려 주고, 허용된 세션에서 정리를 시작하게 하는 장치**다. 내용의 적절성은 정본 대조와 기록으로 남는다.

--start (SessionStart): 세 장 검사(test_knowledge_sheets) + 정리 주기 + "정리 후보"(마지막 정리 뒤 날짜가 붙은 기록 중 세 장이 이름으로 안 가리키는 것 — 누락 확정 아님).
         이 세션(session_id)의 세 장 내용 해시를 `.claude/guard/<session>.json` 에 저장(resume·compact 로 다시 불려도 처음 값을 덮지 않음). 막지 않는다.
--stop  (Stop): 기록 층(worklog/·research 메모·handoff/CHECK_*·VERDICT_*·PREREGISTER_*·patch_note/)이 작업본에서 바뀌었는데
         **이 세션 시작 뒤** 세 장이 하나도 안 바뀌었고(시작 해시가 없으면 git 작업본 기준), 바뀐 worklog 에 독립된 한 줄 `지식 층: 변경 없음(이유)` 선언도 없으면
         끝내기를 한 번 막는다(세션·기록 내용이 같은 동안 두 번 안 막음 · stop_hook_active 면 안 막음).
공통: 평일 20:10~22:30(KST, 배치 시간)에 **배치가 아직 도는 중이면** 시작 알림만 읽기 전용으로 띄우고(상태 파일·git 없음) 끝 검사는 하지 않는다.
      그날 배치가 끝났으면(로그 끝 줄 'Done.  End:') 평소처럼 동작한다(2026-11-15 사용자 결정 D39 — 그 전엔 창 전체에서 꺼져 있어 저녁 세션이 알림을 못 받았다) ·
      시작 알림은 약속 장부 `PROMISES.md` 의 지난·임박 약속도 띄운다 · `KNOWLEDGE_GUARD_OFF=1` 이면 끈다 · git 호출 10초 제한 · 예외는 조용히 통과.
쓰는 것은 `.claude/guard/` 상태 파일뿐(본문은 읽기만)."""
import datetime as dt, hashlib, json, os, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHEETS = ("KNOWLEDGE.md", "DECISIONS.md", "PITFALLS.md")
RECORD_RE = re.compile(r"^(worklog/.+\.md|research/[^/]+\.md|research/handoff/CHECK_.+\.md|VERDICT_.+\.md|PREREGISTER_.+\.md|patch_note/\d{8}.+\.md)$")
RECORD_EXCLUDE = {"research/large_verdict_status.md"}  # 배치 산출물
DECLARE_RE = re.compile(r"^\s*(?:[-*]\s*)?지식 층: 변경 없음\((?P<why>[^)]+)\)", re.M)  # 독립된 한 줄 + 비어 있지 않은 이유(백틱·설명문 제외)
GUARD_DIR = REPO / ".claude" / "guard"
TIDY_DAYS, TIDY_LOGS = 30, 10


LOG_DIR = REPO / "logs"
BATCH_FROM, BATCH_TO = 20 * 60 + 10, 22 * 60 + 30  # 배치 창: 평일 20:10~22:30
PROMISES = REPO / "PROMISES.md"
CARD_DIR = REPO / "knowledge"  # [2026-11-15] 결론 카드(K42~ 부터) — 카드가 바뀌면 지식 층이 바뀐 것으로 본다
DUE_SOON_DAYS = 14


def in_batch_window(now=None):
    now = now or dt.datetime.now()  # 이 PC 는 KST
    return now.weekday() < 5 and BATCH_FROM <= now.hour * 60 + now.minute <= BATCH_TO


def batch_done(now=None, log_dir=None):
    """[2026-11-15 사용자 결정 D39] 오늘 배치가 끝났나 — 읽기만 한다(git·쓰기 없음).
    끝남 = 오늘 날짜의 `auto_run_YYYYMMDD_*.log`(SKIPPED 아닌 것) 꼬리에 끝 줄 'Done.  End:' 가 있거나, 오늘 것이 SKIPPED 로그뿐일 때.
    로그가 아직 없거나 끝 줄이 없으면 False(도는 중으로 본다 — 애매하면 막는 쪽)."""
    now = now or dt.datetime.now(); log_dir = Path(log_dir) if log_dir else LOG_DIR
    try:  # [2026-11-15 Codex 점검] 수동 실행 로그(manual_run_*)도 본다 — 자동 배치가 끝난 뒤 수동 재실행이 돌 수 있다
        logs = sorted(log_dir.glob(f"auto_run_{now:%Y%m%d}_*.log")) + sorted(log_dir.glob(f"manual_run_{now:%Y%m%d}_*.log"))
    except Exception:
        return False
    runs = [p for p in logs if not p.name.endswith("_SKIPPED.log")]
    if not runs:
        return bool(logs)  # SKIPPED 로그만 있으면 오늘 배치는 없다
    for p in runs:
        try:
            data = p.read_bytes()
        except Exception:
            return False
        # 같은 로그에 재실행이 덧붙는다(>>) → '마지막 시작 표식 뒤에' 끝 줄이 있어야 끝난 것. 실패한 단계가 있어도 끝 줄은 찍힌다(끝남 = 멈춤이지 성공이 아님).
        if data.rfind(b"Done.  End:") <= data.rfind(b"  Start: "):
            return False
    return True


def other_python_running():
    """[2026-11-15] 이 감시 장치(와 그 부모) 말고 python.exe 가 돌고 있나 — True / False / None(확인 못 함).
    배치의 python 은 명령줄에 저장소 경로가 없어(`python run_and_diversify.py`) 가려낼 수 없다 → 다른 python 이 하나라도 있으면 '돌고 있을 수 있다'로 본다(막는 쪽).
    tasklist 한 번(읽기만 — 이 PC 실측 약 5초, hook 제한 30초 안). 배치 창 안에서 로그가 끝났다고 나올 때만 부른다."""
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace", timeout=5)
        if r.returncode != 0:
            return None
        pids = set()
        for ln in r.stdout.splitlines():
            parts = [x.strip('"') for x in ln.split('","')]
            if len(parts) >= 2 and parts[0].strip('"').lower() == "python.exe" and parts[1].isdigit():
                pids.add(int(parts[1]))
        return bool(pids - {os.getpid(), os.getppid()})
    except Exception:
        return None


def run_mode(now=None, log_dir=None, proc_check=None):
    """'off' = 아무것도 안 함 · 'readonly' = 시작 알림만(상태 파일·git 없이 읽고 출력만) · 'full' = 시작 알림 + 상태 저장 + 끝 검사.
    배치 창 안이라도 그날 배치가 끝났으면 'full'(2026-11-15 규칙 변경), 도는 중이면 'readonly'."""
    if os.environ.get("KNOWLEDGE_GUARD_OFF") == "1":
        return "off"
    if not in_batch_window(now):
        return "full"
    if not batch_done(now, log_dir):
        return "readonly"
    if proc_check is None and log_dir is None:  # 실제 사용 때만 프로세스를 본다(시험은 임시 폴더 — 필요하면 proc_check 를 넘긴다)
        proc_check = other_python_running
    if proc_check is not None and proc_check() is True:  # 확인 못 함(None)은 로그 판단을 따른다 — 프로세스 확인은 '도는 것이 보일 때만' 막는다
        return "readonly"
    return "full"


def off():  # 옛 이름(다른 스크립트가 부를 수 있어 남김): 끝 검사·상태 쓰기를 하면 안 되는 때
    return run_mode() != "full"


def git(*args):
    try:
        r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def changed_files():
    out = set()
    for ln in git("status", "--porcelain", "--untracked-files=all").splitlines():
        if len(ln) > 3:
            p = ln[3:].strip().strip('"')
            if " -> " in p:
                p = p.split(" -> ")[-1]
            out.add(p.replace("\\", "/"))
    return out


def sha(p):
    try:
        return hashlib.sha1((REPO / p).read_bytes()).hexdigest()
    except Exception:
        return "missing"


def state_path(payload):
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(payload.get("session_id") or "nosession"))[:64]
    return GUARD_DIR / f"{sid}.json"


def load_state(payload):
    try:
        return json.loads(state_path(payload).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(payload, st):
    try:
        GUARD_DIR.mkdir(parents=True, exist_ok=True)
        state_path(payload).write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        for old in sorted(GUARD_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)[:-20]:  # 오래된 상태 20개 넘으면 정리
            old.unlink()
    except Exception:
        pass


def last_tidy():
    m = re.search(r"마지막 정리 (\d{4}-\d{2}-\d{2})", (REPO / "KNOWLEDGE.md").read_text(encoding="utf-8").split("\n", 1)[0])
    return dt.date.fromisoformat(m.group(1)) if m else None


def tidy_backlog(since):
    """정리 후보(누락 확정 아님): 파일명 날짜 > 마지막 정리 날짜이고 세 장 본문에 그 파일 stem 이 없는 연구·판정 파일 + 그 뒤 worklog 파일 수."""
    k = "".join((REPO / s).read_text(encoding="utf-8") for s in SHEETS)
    items = []
    for p in sorted(REPO.glob("research/*_20[0-9][0-9][0-9][0-9][0-9][0-9]*.md")) + sorted(REPO.glob("VERDICT_20*.md")):
        m = re.search(r"(20\d{6})", p.name)
        try:
            d = dt.date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8]))
        except Exception:
            continue
        if d > since and p.stem not in k:
            items.append(p.name)
    wl = [p.name for p in sorted(REPO.glob("worklog/20*.md")) if re.match(r"\d{4}-\d{2}-\d{2}", p.name) and dt.date.fromisoformat(p.name[:10]) > since]
    return items, wl


def todo_lines():
    """[2026-11-13] 세션 시작에 챙길 것(알림일 뿐, 판단은 사람·정본): 다음 ID · 사용자 결정 대기 수 · 판정 도래 모델 · 답 없는 Codex 요청.
    전부 읽기 전용. 한 항목이 실패하면 그 줄만 빠진다."""
    out = []
    try:
        k = (REPO / "KNOWLEDGE.md").read_text(encoding="utf-8"); d = (REPO / "DECISIONS.md").read_text(encoding="utf-8")
        nk = max([int(x) for x in re.findall(r"^\| K(\d{2,3}) ", k, re.M)] + [int(p.stem[1:]) for p in CARD_DIR.glob("K[0-9]*.md") if p.stem[1:].isdigit()] or [0]) + 1
        nd = max([int(x) for x in re.findall(r"^\| D(\d{2,3}) ", d, re.M)] or [0]) + 1
        try:  # [2026-11-15] 묶음 안 번호·결정 이력(DECISIONS_LOG.md)까지 본 다음 번호 — 실패하면 위의 옛 계산 그대로
            if str(REPO / "tests") not in sys.path:
                sys.path.insert(0, str(REPO / "tests"))
            import test_knowledge_sheets as _t
            _lp = REPO / _t.LOG_FILE
            nd = max(nd, _t.decision_ids(d, _lp.read_text(encoding="utf-8") if _lp.exists() else "")[0])
        except Exception:
            pass
        pend = REPO / "DECISIONS_PENDING.md"  # [2026-11-27] 대기 목록은 별도 파일로 옮김(D53) — 없으면 옛 자리(DECISIONS.md §B)에서 센다
        src, where = (pend.read_text(encoding="utf-8"), "DECISIONS_PENDING.md") if pend.exists() else (d, "DECISIONS §B")
        wait = len(re.findall(r"^\d+\. ", src.split("## B.", 1)[1], re.M)) if "## B." in src else 0
        out.append(f"다음 번호 K{nk:02d} · D{nd:02d} (새 행은 이 번호로) · 사용자 결정 대기 {wait}묶음({where})")
    except Exception:
        pass
    try:  # 판정 도래: 리더보드 유효 앵커 ≥40 인데 등록 표(sealed·retired)에 판정이 없는 모델. 대형·주도주는 잣대가 달라 제외.
        lbj = json.loads((REPO / "docs" / "leaderboard.json").read_text(encoding="utf-8"))
        reg = json.loads((REPO / "docs" / "models_registry.json").read_text(encoding="utf-8"))
        done = set(reg.get("sealed") or {}) | set(reg.get("retired") or {})
        due = [f"{m.get('model')}(유효 앵커 {m.get('oos_days')})" for m in lbj.get("models", [])
               if m.get("track") not in ("large", "lead") and not m.get("retired") and (m.get("oos_days") or 0) >= 40 and m.get("model") not in done]
        if due:
            out.append("판정 도래 — 유효 앵커 ≥40 인데 판정 기록이 없음: " + ", ".join(due) + " (VERDICT_RULES 대로 1회 · 사전등록 확인)")
    except Exception:
        pass
    try:  # 최근 30일 안 Codex 요청 중 같은 이름의 답이 없는 것
        h = REPO / "research" / "handoff"; today = dt.date.today(); miss = []
        for p in sorted(h.glob("REQUEST_20*.md")):
            m = re.match(r"REQUEST_(20\d{6})_(.+)\.md$", p.name)
            if not m:
                continue
            d0 = dt.date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8]))
            core = re.sub(r"_blind$", "", m.group(2))  # 답 파일은 날짜·'_blind' 꼬리가 달라도 같은 주제 이름이면 인정
            if (today - d0).days > 30:
                continue
            try:  # [2026-11-15] 답을 파일이 아닌 길(사용자 전달 등)로 받았으면 요청서에 '> 닫음(날짜): 사유' 한 줄 — 거짓 알림 방지
                if re.search(r"^> 닫음\(", p.read_text(encoding="utf-8"), re.M):
                    continue
            except Exception:
                pass
            answered = False
            for r in h.glob(f"REPLY_*{core}*.md"):  # 날짜 없는 답은 인정, 날짜가 있으면 요청일 이후여야 함(옛 답과 이름이 겹치는 경우 제외)
                rd = re.search(r"(20\d{6})", r.name)
                if not rd or rd.group(1) >= m.group(1):
                    answered = True
            if not answered:
                miss.append(p.name)
        if miss:
            out.append("답 없는 Codex 요청(30일 안): " + ", ".join(miss[:5]) + (" …" if len(miss) > 5 else "") + " — 안 보냈거나 답 파일 이름이 다를 수 있음")
    except Exception:
        pass
    try:
        out.extend(promise_lines())
    except Exception:
        pass
    return out


PROMISE_ROW = re.compile(r"^\| *(P\d{2,3}) *\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", re.M)


def parse_promises(text):
    """약속 장부 표 한 행 = (ID, 기한·조건, 무엇, 나온 곳, 상태, 완료 근거). 기한 칸의 첫 YYYY-MM-DD 가 날짜(없으면 조건부 약속)."""
    rows = []
    for m in PROMISE_ROW.finditer(text):
        pid, due, what, src, status, proof = [x.strip() for x in m.groups()]
        dm = re.search(r"(20\d{2})-(\d{2})-(\d{2})", due)
        try:
            d = dt.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3))) if dm else None
        except ValueError:
            d = None
        rows.append({"id": pid, "due": due, "date": d, "what": what, "src": src, "status": status, "proof": proof})
    return rows


def promise_lines(text=None, today=None):
    """[2026-11-15] 약속 장부(`PROMISES.md` — 날짜·조건이 붙은 약속의 원본)에서 열린 약속 중 기한이 지났거나 임박한 것, 조건부로 열린 것의 수.
    판정 도래 알림이 못 보는 후속 창(lv_e 2차)·대형·주도주 일정도 여기서 뜬다. 완료로 적혔는데 근거 칸이 빈 행도 알린다."""
    if text is None:
        if not PROMISES.exists():
            return []
        text = PROMISES.read_text(encoding="utf-8")
    today = today or dt.date.today(); rows = parse_promises(text)
    opened = [r for r in rows if r["status"].startswith("열림")]
    late = [r for r in opened if r["date"] and r["date"] < today]
    soon = [r for r in opened if r["date"] and today <= r["date"] <= today + dt.timedelta(days=DUE_SOON_DAYS)]
    cond = [r for r in opened if not r["date"]]
    noproof = [r for r in rows if r["status"].startswith("완료") and r["proof"] in ("", "—", "-")]
    out = []
    fmt = lambda r: f"{r['id']} {r['what'][:40]}({r['due'][:24]})"  # noqa: E731
    if late:
        out.append("약속 기한 지남: " + " · ".join(fmt(r) for r in late[:6]) + (" …" if len(late) > 6 else "") + " — 하거나, 미루면 장부의 기한을 고치고 사유를 적는다")
    if soon:
        out.append(f"약속 임박({DUE_SOON_DAYS}일 안): " + " · ".join(fmt(r) for r in soon[:6]) + (" …" if len(soon) > 6 else ""))
    if opened:
        out.append(f"열린 약속 {len(opened)}건(날짜 있는 것 {len(opened) - len(cond)} · 조건부 {len(cond)}) — `PROMISES.md`. 모델을 판정할 땐 그 모델 이름이 든 행을 전부 본다(`VERDICT_CHECKLIST.md`)")
    if noproof:
        out.append("완료로 적혔는데 근거 칸이 빈 약속: " + ", ".join(r["id"] for r in noproof[:8]))
    return out


def log_tamper_lines():
    """[2026-11-15] 결정 이력(DECISIONS_LOG.md)은 덧붙이기 전용 — 커밋된 줄이 지워지거나 바뀌었으면 알린다(git 읽기만, 파일이 아직 커밋 전이면 조용)."""
    try:
        parts = git("diff", "--numstat", "HEAD", "--", "DECISIONS_LOG.md").split()
        if len(parts) >= 2 and parts[1].isdigit() and int(parts[1]) > 0:
            return [f"⚠ 결정 이력 `DECISIONS_LOG.md` 에서 커밋된 줄 {parts[1]}개가 지워지거나 바뀌었습니다 — 덧붙이기 전용 파일(정정은 그 절 끝에 '정정(날짜):'). `git diff HEAD -- DECISIONS_LOG.md` 로 보고 원문을 되살릴 것."]
    except Exception:
        pass
    return []


def start(payload, readonly=False):
    if not readonly:
        st = load_state(payload)
        if "sheets" not in st:  # resume·compact 로 다시 불려도 처음 값 유지
            st = {"sheets": {s: sha(s) for s in SHEETS}, "head": git("rev-parse", "HEAD").strip(), "started": dt.datetime.now().isoformat(timespec="minutes")}
            save_state(payload, st)
    sys.path.insert(0, str(REPO / "tests"))
    import io, contextlib
    buf = io.StringIO()
    try:
        import test_knowledge_sheets as t
        with contextlib.redirect_stdout(buf):
            rc = t.main()
        sheet = buf.getvalue().strip()
    except Exception as e:  # noqa
        rc, sheet = 1, f"세 장 검사 실행 실패: {e}"
    since = last_tidy()
    lines = ["[지식 세 층 감시 · 세션 시작 — 누락 후보 알림이지 반영 보증이 아님]"]
    if readonly:  # 배치 도는 중: 읽고 출력만(상태 파일·git 없음). 끝 검사도 이 세션엔 꺼져 있다
        lines.append("⚠ 지금은 평일 배치 시간대(20:10~22:30)이고 오늘 배치가 아직 끝나지 않았거나(로그 끝 줄 없음) 다른 python 프로세스가 돌고 있습니다 — 파일·DB 를 고치지 말고 읽기만. 로그 `logs/auto_run_YYYYMMDD_*.log` 의 마지막 실행에 끝 줄 'Done.  End:' 가 찍히고 배치의 python 프로세스가 없을 때부터 작업해도 됩니다(CLAUDE.md 실행 주의).")
    elif in_batch_window():
        lines.append("평일 배치 시간대지만 오늘 배치 로그는 끝 줄까지 찍혔고(수동 실행 로그 포함) 다른 python 프로세스도 보이지 않습니다 — 작업 가능(프로세스 확인이 실패했으면 로그만 본 것이니 한 번 더 볼 것).")
    lines.append(("OK " if rc == 0 else "FAIL ") + sheet.replace("\n", " / "))
    if since:
        age = (dt.date.today() - since).days
        items, wl = tidy_backlog(since)
        lines.append(f"마지막 정리 {since} ({age}일 전) · 그 뒤 worklog 파일 {len(wl)}건 · 정리 날짜 뒤 파일명 기준·세 장에 명시 참조 없는 후보 {len(items)}건(누락 확정 아님)" + (": " + ", ".join(items[:8]) + (" …" if len(items) > 8 else "") if items else ""))
        if age >= TIDY_DAYS or len(wl) >= TIDY_LOGS:
            lines.append("→ 정리 주기가 됐습니다(CLAUDE.md 마무리 8). 이번 요청이 문서 수정을 허용하고 배치 시간 밖이면, 현재 요청을 방해하지 않는 시점에 바뀐 기록과 연결된 지식 행을 대조·압축하세요. 읽기 전용 요청·긴급 작업엔 미룹니다. 완료한 범위와 남긴 범위를 worklog 에 적고, 전체를 마쳤을 때만 '마지막 정리' 날짜를 갱신합니다. 새 결정·판정·등록은 하지 않습니다.")
    lines.extend(todo_lines())
    if not readonly:
        lines.extend(log_tamper_lines())
    if any(("FAIL" in x or "WARN" in x or "⚠" in x or "기한 지남" in x) for x in lines[1:]):  # [2026-11-15, D40] 문제는 조용히 넘기지 않는다
        lines.append("→ 위의 FAIL·WARN·⚠·'기한 지남' 줄은 **첫 답에서 사용자에게 쉬운 말로 알린다**(무엇이 문제이고 무엇을 하면 되는지 한두 줄). 결정 번호 어긋남·이력 훼손은 다른 작업보다 먼저 고친다.")
    lines.append("규칙: 결론·사용자 결정·당한 함정이 생기면 같은 세션에 세 장에 한 줄(마무리 7), worklog 엔 '지식 반영: K##/D##' 로 잇는다. 정말 없었으면 worklog 에 독립된 한 줄 '지식 층: 변경 없음(이유)' — 없으면 세션 끝에서 한 번 막힌다.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}}, ensure_ascii=False))


def stop(payload):
    if payload.get("stop_hook_active"):
        return
    ch = changed_files()
    records = sorted(p for p in ch if RECORD_RE.match(p) and p not in RECORD_EXCLUDE)
    if not records:
        return
    st = load_state(payload)
    if st.get("sheets"):  # 이 세션 시작 뒤 세 장이 바뀌었나(내용 해시)
        if any(sha(s) != st["sheets"].get(s) for s in SHEETS):
            return
    elif any(s in ch for s in SHEETS):  # 시작 해시가 없으면 git 작업본 기준
        return
    if any(re.match(r"knowledge/K\d{2,3}\.md$", p) for p in ch):  # 결론 카드(K##.md)가 바뀌었으면 지식 층 갱신으로 본다 — README 등은 아님
        return
    if any(re.match(r"pitfalls/(?!README\.md$)[A-Za-z0-9_]+\.md$", p) for p in ch):  # [2026-11-27] 함정 주제 파일이 바뀌었으면 지식 층 갱신으로 본다(D52) — README 는 아님
        return
    for p in records:
        if p.startswith("worklog/"):
            try:
                m = DECLARE_RE.search((REPO / p).read_text(encoding="utf-8"))
                if m and m.group("why").strip() not in ("", "이유"):
                    return
            except Exception:
                pass
    key = hashlib.sha1("|".join(f"{p}:{sha(p)}" for p in records).encode()).hexdigest()  # 같은 세션·같은 기록 내용이면 한 번만
    if st.get("blocked") == key:
        return
    st["blocked"] = key
    save_state(payload, st)
    reason = ("[지식 세 층 감시] 기록 층이 바뀌었는데 이 세션에서 세 장(KNOWLEDGE.md·DECISIONS.md·PITFALLS.md)은 안 바뀌었습니다: "
              + ", ".join(records[:6]) + (" …" if len(records) > 6 else "")
              + ". 끝내기 전에 (a) 이번 세션의 결론·사용자 결정·당한 함정을 세 장에 한 줄씩 적고 worklog 에 '지식 반영: K##/D##' 로 잇거나, (b) 정말 없으면 worklog 에 독립된 한 줄 '지식 층: 변경 없음(이유)' 를 적으세요. 그 뒤 다시 끝내면 통과합니다(같은 내용에서는 한 번만 알림). 이전 세션이 남긴 기록이라 내가 판단할 것이 없으면 (b) 에 그렇게 적으세요.")
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--start"
    try:
        rm = run_mode()
        if rm == "off":
            return 0
        try:
            payload = json.loads(sys.stdin.read() or "{}") if not sys.stdin.isatty() else {}
        except Exception:
            payload = {}
        if mode == "--start":
            start(payload, readonly=(rm == "readonly"))
        elif mode == "--stop" and rm == "full":  # 배치 도는 중엔 끝 검사를 하지 않는다(git status 가 배치의 커밋과 겹칠 수 있다)
            stop(payload)
    except Exception as e:  # 감시 장치의 오류는 작업을 막지 않는다
        print(json.dumps({"systemMessage": f"knowledge_guard 오류(무시): {e}"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
