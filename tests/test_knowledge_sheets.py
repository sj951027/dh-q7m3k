# -*- coding: utf-8 -*-
"""지식 세 장(KNOWLEDGE.md · DECISIONS.md · PITFALLS.md) 자동 검사 — 2026-11-08 도입, 같은 날 저녁 Codex 지적 반영. DB 불필요·즉시.
[1] 세 장이 있고 KNOWLEDGE·DECISIONS 머리말에 '마지막 정리 YYYY-MM-DD'(날짜 형식)가 있다 — 30일 넘으면 경고(실패 아님).
[2] 크기 상한(KNOWLEDGE 24KB · DECISIONS 15KB · PITFALLS 5KB — CLAUDE.md 마무리 8; 값은 아래 CAPS 가 정본).
[3] 세 장이 가리키는 정본이 실재한다: .md/.py 경로 + 확장자 없는 축약 정본 이름(RESEARCH_*, VERDICT_*, PREREGISTER_*, 대문자_날짜 메모)도 접두 glob 으로 찾는다(PTW 파일 제외).
[4] 원장 `MODELS_LEDGER.md` 현역 표의 model_id 가 KNOWLEDGE 어딘가에 한 번은 나온다(고정 목록 아님 — 원장을 읽는다). 은퇴·대조 모델은 제외하지 않음(지식에 라벨이 있어야 하므로).
[5] 행 ID 중복 없음(K##). 결정 번호(D##)는 장부 행·묶음 안 번호·결정 이력(DECISIONS_LOG.md)을 합쳐 중복·빠짐·요약 없는 원문·원문 없는 요약을 본다(2026-11-15, D40).
[2-1] 남은 자리가 300B 아래면 경고(실패 아님) — 새 줄을 적기 전에 자리부터.
[3-1] 결정 대기 목록 DECISIONS_PENDING.md(2026-11-27 D53 — DECISIONS.md §B 에서 옮김)의 정본 링크도 [3] 처럼 본다. 크기 상한은 없다(매 세션 읽지 않음).
[6] 함정 주제 파일(pitfalls/*.md, 2026-11-27 D52): 정본 링크를 [3] 처럼 보고, README 를 뺀 주제 파일은 PITFALLS.md 가 이름으로 가리켜야 한다(가리키지 않는 파일은 아무도 안 읽는다)."""
import datetime as dt, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CAPS = {"KNOWLEDGE.md": 24_000, "DECISIONS.md": 15_000, "PITFALLS.md": 5_000}
PTW_FILES = {"backup_pull.py", "market_data.py", "benchmark.py"}
SEARCH_DIRS = ["", "research", "research/handoff", "docs", "tests", "patch_note", "worklog"]
LOG_FILE = "DECISIONS_LOG.md"  # 결정의 승인 원문(덧붙이기만 · 매 세션 읽지 않음)
LOG_FROM = 40  # 이 번호부터 원문은 LOG_FILE 에 있어야 한다(2026-11-15)
ROOM_WARN = 300  # 남은 자리(B)가 이보다 적으면 경고


def decision_ids(root, log=""):
    """[2026-11-15] 결정 번호가 '정의된 곳'을 모아 (다음 번호, 문제 목록)을 돌려준다.
    정의 = ① DECISIONS.md 표 행의 맨 앞 번호 ② 'D## 외' 묶음 행 안의 (D##) ③ DECISIONS_LOG.md 의 '## D## ' 절. 그 밖의 D## 는 가리킴일 뿐."""
    rows = [int(x) for x in re.findall(r"^\| D(\d{2,3}) ", root, re.M)]
    inner = []
    for m in re.finditer(r"^\| D(\d{2,3}) 외 .*$", root, re.M):
        inner += [int(x) for x in re.findall(r"\(D(\d{2,3})[,)]", m.group(0)) if int(x) != int(m.group(1))]
    logs = [int(x) for x in re.findall(r"^## D(\d{2,3}) ", log, re.M)]
    name = lambda xs: ", ".join(f"D{x:02d}" for x in xs)  # noqa: E731
    bad = []
    for label, xs in (("장부 행", rows), ("묶음 안 번호", inner), ("이력 절", logs)):
        dup = sorted({x for x in xs if xs.count(x) > 1})
        if dup:
            bad.append(f"{label} 번호 중복 {name(dup)}")
    both = sorted(set(rows) & set(inner))
    if both:
        bad.append(f"장부 행과 묶음 안에 같은 번호 {name(both)}")
    allid = set(rows) | set(inner) | set(logs)
    top = max(allid) if allid else 0
    gap = [x for x in range(1, top + 1) if x not in allid]
    if gap:
        bad.append(f"번호 빠짐 {name(gap)} — 원문이 장부·묶음·이력 어디에도 없다")
    for x in sorted(set(logs)):
        if not re.search(rf"(?<![A-Za-z0-9])D{x:02d}(?!\d)", root):
            bad.append(f"D{x:02d} 는 이력에만 있고 DECISIONS.md 에 요약 줄이 없다")
    for x in sorted(set(rows)):
        if x >= LOG_FROM and x not in logs:
            bad.append(f"D{x:02d} 의 원문이 {LOG_FILE} 에 없다(D{LOG_FROM} 부터는 원문을 이력에)")
    return top + 1, bad


def exists_any(name):
    for d in SEARCH_DIRS:
        if (REPO / d / name).exists():
            return True
    return False


def exists_prefix(stem):
    for d in SEARCH_DIRS:
        if list((REPO / d).glob(stem + "*")):
            return True
    return False


def ledger_ids():
    ids = set()
    for ln in (REPO / "MODELS_LEDGER.md").read_text(encoding="utf-8").splitlines():
        if not ln.startswith("| ") or ln.startswith("| 트랙") or ln.startswith("|---"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) < 3 or cells[0] not in ("v3", "lowvol", "wu", "large", "lead"):
            continue
        for tok in re.findall(r"[a-z]{2,3}_[a-z0-9]{1,6}|v3\d[a-z]?|ls_t\d", cells[1]):
            ids.add(tok)
    return ids


def main():
    bad, warn, texts = [], [], {}
    for f, cap in CAPS.items():
        p = REPO / f
        if not p.exists():
            bad.append(f"[1] {f} 없음"); continue
        s = p.read_text(encoding="utf-8"); texts[f] = s
        head = s.split("\n", 1)[0]
        if f != "PITFALLS.md":
            m = re.search(r"마지막 정리 (\d{4}-\d{2}-\d{2})", head)
            if not m:
                bad.append(f"[1] {f} 머리말에 '마지막 정리 YYYY-MM-DD' 없음")
            else:
                age = (dt.date.today() - dt.date.fromisoformat(m.group(1))).days
                if age > 30:
                    warn.append(f"[1] {f} 마지막 정리 {m.group(1)} → {age}일 지남 — 정리 주기(월 1회) 도래")
        n = len(s.encode("utf-8"))
        if n > cap:
            bad.append(f"[2] {f} {n:,}B > 상한 {cap:,}B — 압축·정정할 때")
        elif cap - n < ROOM_WARN:
            warn.append(f"[2] {f} 자리 {cap - n:,}B 남음(상한 {cap:,}B) — 새 줄 하나가 안 들어갈 수 있다. 적기 전에 자리부터")
    # [2026-11-21] 결론 카드(knowledge/K##.md)의 정본 링크도 같이 본다 — 옛 행을 카드로 옮기면 그 링크가 세 장 밖으로 나가므로
    linked = dict(texts)
    for c in sorted((REPO / "knowledge").glob("K*.md")):
        linked[f"knowledge/{c.name}"] = c.read_text(encoding="utf-8")
    n_cards = len(linked) - len(texts)
    # [2026-11-27] 함정 주제 파일(pitfalls/*.md)도 같이 본다 — 상세가 PITFALLS.md 밖으로 나갔으므로(D52)
    topics = sorted(p for p in (REPO / "pitfalls").glob("*.md") if p.name != "README.md")
    for p in topics:
        linked[f"pitfalls/{p.name}"] = p.read_text(encoding="utf-8")
        if f"pitfalls/{p.name}" not in texts.get("PITFALLS.md", ""):
            bad.append(f"[6] pitfalls/{p.name} 을 PITFALLS.md 가 가리키지 않는다 — '분야별' 표에 한 줄")
    pend = REPO / "DECISIONS_PENDING.md"  # [2026-11-27] 결정 대기 목록(DECISIONS.md §B 에서 옮김, D53) — 정본 링크를 같이 본다
    if pend.exists():
        linked[pend.name] = pend.read_text(encoding="utf-8")
    elif "DECISIONS_PENDING.md" in texts.get("DECISIONS.md", ""):
        bad.append("[3] DECISIONS.md 가 가리키는 DECISIONS_PENDING.md 없음")
    for f, s in linked.items():
        for m in set(re.findall(r"[A-Za-z0-9_./\-]+\.(?:md|py)", s)):
            base = m.split("/")[-1]
            if base in PTW_FILES or m.startswith("http"):
                continue
            if not (exists_any(m) or exists_any(base)):
                bad.append(f"[3] {f} → {m} 없음")
        for stem in set(re.findall(r"\b((?:RESEARCH|VERDICT|PREREGISTER|SECTOR|SIGNAL|HOLD|EARLY|LARGECAP|FULL|CAPITAL|OBSERVATION|AUTOMATION|LEDGER|IDEA|KIS|CHECK|REPLY|REQUEST)_[A-Za-z0-9_]+)", s)):
            stem = stem.rstrip("_")
            if not exists_prefix(stem):
                bad.append(f"[3] {f} → 축약 정본 {stem}* 없음")
    k = texts.get("KNOWLEDGE.md", "")
    ids = ledger_ids()
    if not ids:
        bad.append("[4] 원장에서 model_id 를 못 읽음")
    for mid in sorted(ids):
        if not re.search(rf"(?<![A-Za-z0-9_]){re.escape(mid)}(?![A-Za-z0-9_])", k):
            bad.append(f"[4] KNOWLEDGE 에 원장 모델 {mid} 없음")
    for f, pat in (("KNOWLEDGE.md", r"^\| (K\d{2,3}) "),):
        found = re.findall(pat, texts.get(f, ""), re.M)
        dup = {x for x in found if found.count(x) > 1}
        if dup:
            bad.append(f"[5] {f} ID 중복 {sorted(dup)}")
    logp = REPO / LOG_FILE
    bad += [f"[5] 결정 번호: {x}" for x in decision_ids(texts.get("DECISIONS.md", ""), logp.read_text(encoding="utf-8") if logp.exists() else "")[1]]
    for w in warn:
        print("WARN " + w)
    if bad:
        print("\n".join(bad)); return 1
    print("OK 지식 세 장: 크기 " + " · ".join(f"{f} {len(texts[f].encode()):,}B" for f in CAPS) + f" · 링크·축약 정본 확인(카드 {n_cards}장 · 함정 주제 파일 {len(topics)}개 포함) · 원장 모델 {len(ids)}개 모두 KNOWLEDGE 에 있음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
