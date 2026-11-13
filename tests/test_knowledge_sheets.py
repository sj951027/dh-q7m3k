# -*- coding: utf-8 -*-
"""지식 세 장(KNOWLEDGE.md · DECISIONS.md · PITFALLS.md) 자동 검사 — 2026-11-08 도입, 같은 날 저녁 Codex 지적 반영. DB 불필요·즉시.
[1] 세 장이 있고 KNOWLEDGE·DECISIONS 머리말에 '마지막 정리 YYYY-MM-DD'(날짜 형식)가 있다 — 30일 넘으면 경고(실패 아님).
[2] 크기 상한(KNOWLEDGE 24KB · DECISIONS 15KB · PITFALLS 5KB — CLAUDE.md 마무리 8; 값은 아래 CAPS 가 정본).
[3] 세 장이 가리키는 정본이 실재한다: .md/.py 경로 + 확장자 없는 축약 정본 이름(RESEARCH_*, VERDICT_*, PREREGISTER_*, 대문자_날짜 메모)도 접두 glob 으로 찾는다(PTW 파일 제외).
[4] 원장 `MODELS_LEDGER.md` 현역 표의 model_id 가 KNOWLEDGE 어딘가에 한 번은 나온다(고정 목록 아님 — 원장을 읽는다). 은퇴·대조 모델은 제외하지 않음(지식에 라벨이 있어야 하므로).
[5] 행 ID 중복 없음(K##·D##)."""
import datetime as dt, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CAPS = {"KNOWLEDGE.md": 24_000, "DECISIONS.md": 15_000, "PITFALLS.md": 5_000}
PTW_FILES = {"backup_pull.py", "market_data.py", "benchmark.py"}
SEARCH_DIRS = ["", "research", "research/handoff", "docs", "tests", "patch_note", "worklog"]


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
    for f, s in texts.items():
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
    for f, pat in (("KNOWLEDGE.md", r"^\| (K\d{2}) "), ("DECISIONS.md", r"^\| (D\d{2}) ")):
        found = re.findall(pat, texts.get(f, ""), re.M)
        dup = {x for x in found if found.count(x) > 1}
        if dup:
            bad.append(f"[5] {f} ID 중복 {sorted(dup)}")
    for w in warn:
        print("WARN " + w)
    if bad:
        print("\n".join(bad)); return 1
    print("OK 지식 세 장: 크기 " + " · ".join(f"{f} {len(texts[f].encode()):,}B" for f in CAPS) + f" · 링크·축약 정본 확인 · 원장 모델 {len(ids)}개 모두 KNOWLEDGE 에 있음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
