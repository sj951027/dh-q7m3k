# -*- coding: utf-8 -*-
"""지식 세 층 자동 감시 — Claude Code hook 용 (2026-11-08 · 같은 날 저녁 Codex 검토 반영). `.claude/settings.json` 이 부른다.

이 장치는 "지식이 저절로 쌓임을 보증"하지 않는다. **누락 후보를 알려 주고, 허용된 세션에서 정리를 시작하게 하는 장치**다. 내용의 적절성은 정본 대조와 기록으로 남는다.

--start (SessionStart): 세 장 검사(test_knowledge_sheets) + 정리 주기 + "정리 후보"(마지막 정리 뒤 날짜가 붙은 기록 중 세 장이 이름으로 안 가리키는 것 — 누락 확정 아님).
         이 세션(session_id)의 세 장 내용 해시를 `.claude/guard/<session>.json` 에 저장(resume·compact 로 다시 불려도 처음 값을 덮지 않음). 막지 않는다.
--stop  (Stop): 기록 층(worklog/·research 메모·handoff/CHECK_*·VERDICT_*·PREREGISTER_*·patch_note/)이 작업본에서 바뀌었는데
         **이 세션 시작 뒤** 세 장이 하나도 안 바뀌었고(시작 해시가 없으면 git 작업본 기준), 바뀐 worklog 에 독립된 한 줄 `지식 층: 변경 없음(이유)` 선언도 없으면
         끝내기를 한 번 막는다(세션·기록 내용이 같은 동안 두 번 안 막음 · stop_hook_active 면 안 막음).
공통: 평일 20:10~22:30(KST, 배치 시간)엔 아무것도 안 하고 안 쓴다 · `KNOWLEDGE_GUARD_OFF=1` 이면 끈다 · git 호출 10초 제한 · 예외는 조용히 통과.
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


def off():
    if os.environ.get("KNOWLEDGE_GUARD_OFF") == "1":
        return True
    now = dt.datetime.now()  # 이 PC 는 KST
    t = now.hour * 60 + now.minute
    return now.weekday() < 5 and 20 * 60 + 10 <= t <= 22 * 60 + 30  # 배치 창: 평일 20:10~22:30


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
        nk = max([int(x) for x in re.findall(r"^\| K(\d{2}) ", k, re.M)] or [0]) + 1
        nd = max([int(x) for x in re.findall(r"^\| D(\d{2}) ", d, re.M)] or [0]) + 1
        wait = len(re.findall(r"^\d+\. ", d.split("## B.", 1)[1], re.M)) if "## B." in d else 0
        out.append(f"다음 번호 K{nk:02d} · D{nd:02d} (새 행은 이 번호로) · 사용자 결정 대기 {wait}묶음(DECISIONS §B)")
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
    return out


def start(payload):
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
    lines = ["[지식 세 층 감시 · 세션 시작 — 누락 후보 알림이지 반영 보증이 아님]", ("OK " if rc == 0 else "FAIL ") + sheet.replace("\n", " / ")]
    if since:
        age = (dt.date.today() - since).days
        items, wl = tidy_backlog(since)
        lines.append(f"마지막 정리 {since} ({age}일 전) · 그 뒤 worklog 파일 {len(wl)}건 · 정리 날짜 뒤 파일명 기준·세 장에 명시 참조 없는 후보 {len(items)}건(누락 확정 아님)" + (": " + ", ".join(items[:8]) + (" …" if len(items) > 8 else "") if items else ""))
        if age >= TIDY_DAYS or len(wl) >= TIDY_LOGS:
            lines.append("→ 정리 주기가 됐습니다(CLAUDE.md 마무리 8). 이번 요청이 문서 수정을 허용하고 배치 시간 밖이면, 현재 요청을 방해하지 않는 시점에 바뀐 기록과 연결된 지식 행을 대조·압축하세요. 읽기 전용 요청·긴급 작업엔 미룹니다. 완료한 범위와 남긴 범위를 worklog 에 적고, 전체를 마쳤을 때만 '마지막 정리' 날짜를 갱신합니다. 새 결정·판정·등록은 하지 않습니다.")
    lines.extend(todo_lines())
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
        if off():
            return 0
        try:
            payload = json.loads(sys.stdin.read() or "{}") if not sys.stdin.isatty() else {}
        except Exception:
            payload = {}
        if mode == "--start":
            start(payload)
        elif mode == "--stop":
            stop(payload)
    except Exception as e:  # 감시 장치의 오류는 작업을 막지 않는다
        print(json.dumps({"systemMessage": f"knowledge_guard 오류(무시): {e}"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
