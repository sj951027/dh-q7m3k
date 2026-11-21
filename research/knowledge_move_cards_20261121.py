# -*- coding: utf-8 -*-
"""KNOWLEDGE.md 옛 행 → 결론 카드(knowledge/K##.md) 옮기기 — 2026-11-21 (D45).

무엇: 12월 판정 3건(v32a · ls_t1 · lv_e)과 무관한 옛 행만 카드로 옮기고, KNOWLEDGE.md 에는 색인 한 줄을 남긴다.
원칙: 원문은 글자 그대로 카드에(행 전체 한 줄 + 칸별) — 새로 쓰는 것은 색인 줄뿐이고, 색인 줄의 숫자는 원문 행에 있는 숫자만.
쓰는 법:
    python -X utf8 research/knowledge_move_cards_20261121.py            # 모의 실행(파일을 안 바꾼다) + 검사
    python -X utf8 research/knowledge_move_cards_20261121.py --apply    # 검사를 전부 통과했을 때만 쓴다
점수·판정·DB 무관(문서만).
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
import test_knowledge_sheets as ts  # noqa: E402  (링크·원장 모델 검사를 그대로 빌려 쓴다)

TODAY = "2026-11-21"
KFILE = REPO / "KNOWLEDGE.md"
CARD_DIR = REPO / "knowledge"
ARCHIVE = REPO / "KNOWLEDGE_ARCHIVE.md"

# ── 남기는 행(판정에 걸림) — 기준 둘 ──
# (가) 행 글에 v32a · ls_t1 · lv_e 가 나온다  (나) WHERE.md 의 '모델 판정'·'v30·챌린저'·'저변동'·'대형' 줄이 가리킨다
# (다) K20 은 같은 세션에 P18(sv_b 자리바꿈 감도)로 손대는 행이라 남긴다
VERDICT_WORDS = ("v32a", "ls_t1", "lv_e")
KEEP_WHERE = {"K23", "K36", "K40", "K38", "K15", "K16", "K17", "K37", "K25", "K02", "K18", "K19", "K24"}
KEEP_EXTRA = {"K20": "같은 세션 P18(sv_b 감도)로 손대는 행"}

# ── 색인 줄(새로 쓰는 것은 이것뿐): 번호 → (결론, 대표 근거, 상태·재검 한마디). 첫 두 칸(ID·자리, 축)은 원문 그대로 ──
# 규칙: 숫자는 원문 행에 있는 것만(스크립트가 본다). 근거 칸은 ' · ' 로 나눈 조각마다 원문 행의 부분 문자열이어야 한다.
INDEX = {
    "K01": ('40일 뒤 평균 플러스지만 "거의 안 잃음"은 아님(7번 손실)', "27사건 · 전 종목 +4.22 [+1.49, +6.98] · 20/27 · 2015~26", '3년 "9/9" 는 운 좋은 창 · 최악 −12.6'),
    "K03": ("급락 날에 몰려 있고 평소 날은 0 근처", "대리 · 급락 날 +3.95 [+2.45, +5.55] · 그 밖 +0.25 [−0.10, +0.61]", "2021~ 알파가 '급락 뒤'로 좁아짐(H6 열림)"),
    "K04": ("코스피엔 하한 증거 없음 — 깊을수록 좋았다", "사건 ≤−10 10/10 · ≤−20 2/2 · Codex 일치", '"없다"가 아니라 "증거 없음"(≤−20 두 사건뿐)'),
    "K05": ("**모양은 못 가르고 깊이만 가른다** — 전부 닫음", "대리 58일 · 업종 몰림−골고루 +2.33 [−0.56, +5.24]", "닫음 · 업종은 현재 분류(사후 편향)"),
    "K06": ("경고 불허(거짓 경고) · 회피 후보 아님 — 배지는 '사실'로만", "경고 검정 +2.96 [−1.16, +6.79] · v30 dd20≤−20 61건·19앵커", '10년 "깊을수록 좋음"은 사후·생존 편향 가능'),
    "K07": ("증거 부족 — 규칙은 코스피 기준", "코스닥 ≤−5% 38사건 +1.8 [−0.9, +4.3] 23/38", "2026-05~08 단독 하락은 깊어져도 실패"),
    "K08": ("10년에선 사라짐(+0.7~+2.0) → 게이트 가설 근거 약화", "11년 플러스 70%", "과매도의 *상대* 초과(D −1.10)는 음 — 둘을 섞지 말 것"),
    "K09": ("세울 수 없음", "1~3일째 vs 4일째+ −6.16 [−13.25, +0.15] · 사건 6개 3승3패", "깊이가 연속 하락을 담음"),
    "K10": ("전부 닫음 — 외국인은 오른 뒤 산다(A 날 91% 매도) · 역효과는 외국인 탓 아님 · 2026은 연속선의 끝", "순매수 뒤 과매도 −3.0 [−5.4, −0.5] · 사건 7개", "닫음"),
    "K11": ("셋 다 닫음(Codex 눈가림, 사전 조건표)", "A 사건 20 · FX 차 −7.6 [−15.6, +0.2] 이나 부호 반전", "Claude 재현 일치(11/16) · A 뒤반 FX −5.8 은 표본 부족"),
    "K12": ("채택 없음 · 못 긋는다(A 안에서 변동성·60일 낙폭·폭은 못 가름)", "3년 0/20 · 26년 ★1/20 · 전부 0 걸침", "자리 점수 0~10 은 표시용"),
    "K13": ("⛔ 돈 안 됨 · 무조건 보유와 못 가름", "비용 뒤 전부 음(Codex 일치) · KODEX +4.85 [+0.50, +10.15] vs 무조건 +2.9", "세 사건이 평균을 끌어올림"),
    "K14": ("효과는 있으나 규칙 아님 — 배지 후보 · 공시 직후 진입은 **K41**", "150일 +2.24 [+0.46, +4.16]", "과매도의 1.4% · A 칸 0(17일) · K41 과 설계가 달라 서로 반증 아님"),
    "K21": ("대리로는 우위 → E3 모의 계좌 진행 중(실제 목록 미확인) · 3년 스위칭 앙상블은 size 효과", "대리 A 과매도−저변동 +5.55 [+2.73, +8.81]", "전향 코호트 ≥20261109 · 비교군 50/50 계좌"),
    "K22": ("전부 근거 없음 — 갈아타지 않는다 · 시너지 없음 · IC 천장 0.18 · 획기적 후보 없음", "승률 52% 0 걸침 · 앙상블 행 v30 대비 −1.54 [−2.23, −0.83]", "나누기(섞기)는 변동만 줄임"),
    "K26": ("닫음(0 / 차이 없음 / → K42 / 돈 안 됨 / 차이 없음 / 없음)", "대리 120일 +0.42 [−0.65, +1.49] · fresh −0.20 [−0.51, +0.12](Codex 일치)", "v30 실제 목록은 깔때기가 이미 거름"),
    "K27": ("더 나쁘다 → 표시 열 `earn_recent_20d`(2026.10.49) · 빼기 규칙 이득 미식별", "94일 −2.85 [−4.70, −1.11] · Codex −2.83", "챌린저는 2027-01 재측정 뒤"),
    "K29": ("전 종목에선 예측되나 v30·lv_b 에서 빼면 효과 없음 · lv_b 필터 없음 · v30 은 11~20위보다 상위10 이 낫다", "v30 11~20위 −0.70", "효과는 관측 모델(mom_a·le_a)에만"),
    "K30": ("추세주 = 다른 종족 → ld_a 트랙(판정 ≈2028-03) · 편입 예측 못 씀 · 공시 뒤 꼬리 위험 = 현행 희석 60일 제외와 일치", "적중 15~19% · 7회차", "미채택"),
    "K41": ("**자사주 신탁계약 '체결' 원공시만 첫 주 후보(경계)** — 채택 아님(배지·전향 관측 계좌 후보)", "체결 1,033건·528일 up5 차 +10.12 [+5.89, +14.45] · 40일 +3.21 [+1.73, +4.66] · Codex 독립 계산 일치", "약점: 정정 포함 하단 +4.7 · 2025~ 단독 0 걸침 · 거래대금 ≥5억 중앙값 −0.3 · A 칸 못 가름(나머지는 카드)"),
    "K31": ("상관없음(t+1 종가 유지, 자동화는 동시호가 시장가) · 기다리기·나누기·반전 확인은 전부 손해/이득 없음 → 닫음 · 소액은 0.7%p 이내", "대리 시가 +0.10 [−0.01, +0.23] · 매수 n=115 +0.06 [−0.39, +0.53]", "계좌 커지면 E5 체결 한도"),
    "K32": ("맞다 — 40일 넘기면 깎이고 20 vs 40 은 같다 · 짧게·조기 매도·적극 재투자·국면(D 칸 진입) 청산 전부 못 이김(수익 = 첫 주 패자의 되돌림) · 손절 손해 · 익절선 15~20% 만 기움", "대리 41~60일 −0.24 [−0.48, −0.01] · v30 A20−A40 −1.24 [−2.26, −0.18]", "첫 주 승자는 미리 못 가름(K28) · 익절선은 사전등록 뒤 관측 계좌 후보"),
    "K33": ("없음(최대 2.4% NAV) · 철회(현금 계좌 −13~−19%p) · 미미 · 현금 유지 — 전부 닫음", "J06 배율 1.03 · J05 −0.03%p", "닫음"),
    "K35": ('"안 잃음"이 아니라 **시장보다 덜 잃음** · 게이트 효과 = 현금 효과와 못 가름', "10월 v30 −9.6 vs 시장 −13.5 · 차 +0.91 [−0.49, +2.88]", "gateD0·fixq 계좌 관측 중 · 게이트 초안 미등록"),
    "K39": ("공매도·대차·신용·종목 수급은 **2026년만** · 10년 DB 2015-01~2026-10 수정주가 · **주식 수 없음** · **업종은 현재 분류만**(11/8 부터 날짜별 스냅샷) · 공시 표·운영 시세 2023-06~ (나머지 범위는 카드)", "실측", "업종·크기 연구는 편향 명시 필수"),
}

NUM = re.compile(r"\d+(?:[.,]\d+)*")
ROW = re.compile(r"^\| (K\d{2,3}) ")


def cells(line):
    """표 한 줄을 칸으로(\\| 는 칸 구분이 아니다). 앞뒤 공백만 뗀다."""
    parts = re.split(r"(?<!\\)\|", line)
    return [p.strip() for p in parts[1:-1]]


def make_index(kid, c):
    concl, ev, st = INDEX[kid]
    return f"| {c[0]} | {c[1]} | {concl} | {ev} | {st} | knowledge/{kid}.md |"


def make_card(kid, line, c, arch_ids):
    place = c[0][len(kid):].strip() or "자리 미기재"
    blank = "(옮길 때 채우지 않음 — 원문 행에 없다. 이 번호를 다시 볼 때 정본에서 채운다)"
    out = [
        f"# {kid} — {c[1]} (자리 {place})",
        "",
        f"옛 행을 {TODAY} 에 글자 그대로 옮긴 카드다. 아래 칸은 원문 행의 칸을 그대로 나눠 담았고, 새로 쓴 해석은 없다.",
        "",
        f"- 상태: {blank}   · 결론 종류: {blank}",
        f"- 결론(한정해서): {c[2]}",
        f"- 비교 기준: {blank}   · 진입·측정 시점: {blank}",
        f"- 근거: {c[3]}",
        "- 독립 재현: (따로 적힌 칸이 없었다 — 근거·재검 칸에 'Codex 일치'·'재현'이 적혀 있으면 그것이 전부)",
        f"- 닫힌 이유 / 재검 조건(원문 칸 그대로 — 적용 범위·오독 방지도 여기 섞여 있다): {c[4]}",
        f"- 정본: {c[5]}   · 근거 확인일: (옮긴 날 숫자를 정본과 다시 맞춰 보지 않았다 — 행의 글자를 옮기기만 함)",
        f"- 관련: {blank}",
        f"- 꼬리표: {blank}",
        "",
        f"## 원문 행 ({TODAY} 옮기기 직전 `KNOWLEDGE.md` 의 한 줄 — 글자 그대로)",
        "```text",
        line,
        "```",
        "",
        "## 이력",
        f"- {TODAY} 옛 행을 카드로 옮김(`research/knowledge_move_cards_20261121.py` · 내용 불변 — `KNOWLEDGE.md` 에는 색인 한 줄만 남김 · D45).",
    ]
    if kid in arch_ids:
        out.append(f"- 이보다 앞선 문구(11/13·11/17 에 줄이기 전 원문)는 `KNOWLEDGE_ARCHIVE.md` 의 `{kid}` 절.")
    return "\n".join(out) + "\n"


def link_problems(name, s):
    bad = []
    for m in set(re.findall(r"[A-Za-z0-9_./\-]+\.(?:md|py)", s)):
        base = m.split("/")[-1]
        if base in ts.PTW_FILES or m.startswith("http"):
            continue
        if not (ts.exists_any(m) or ts.exists_any(base)):
            bad.append(f"{name} → {m} 없음")
    for stem in set(re.findall(r"\b((?:RESEARCH|VERDICT|PREREGISTER|SECTOR|SIGNAL|HOLD|EARLY|LARGECAP|FULL|CAPITAL|OBSERVATION|AUTOMATION|LEDGER|IDEA|KIS|CHECK|REPLY|REQUEST)_[A-Za-z0-9_]+)", s)):
        if not ts.exists_prefix(stem.rstrip("_")):
            bad.append(f"{name} → 축약 정본 {stem}* 없음")
    return bad


def main():
    apply = "--apply" in sys.argv
    raw = KFILE.read_bytes()
    text = raw.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    where = (REPO / "WHERE.md").read_text(encoding="utf-8")
    arch = ARCHIVE.read_text(encoding="utf-8") if ARCHIVE.exists() else ""
    arch_ids = set(re.findall(r"^## .*KNOWLEDGE\.md · (K\d{2,3})", arch, re.M))
    ledger = sorted(ts.ledger_ids())

    plan, keep, already = {}, {}, []
    for i, ln in enumerate(lines):
        m = ROW.match(ln)
        if not m:
            continue
        kid = m.group(1)
        if f"knowledge/{kid}.md" in ln:
            already.append(kid)
            continue
        why = []
        hit = [w for w in VERDICT_WORDS if w in ln]
        if hit:
            why.append("행에 " + "·".join(hit))
        if kid in KEEP_WHERE:
            why.append("WHERE.md 판정 줄이 가리킴")
        if kid in KEEP_EXTRA:
            why.append(KEEP_EXTRA[kid])
        if why:
            keep[kid] = " / ".join(why)
        else:
            plan[kid] = i

    fails, notes = [], []
    # 0. 계획과 색인 문구가 맞물리는가
    for kid in sorted(set(INDEX) ^ set(plan)):
        fails.append(f"[0] {kid}: 옮길 행 목록과 색인 문구 목록이 서로 다르다")
    for kid in KEEP_WHERE:
        if not re.search(rf"(?<!\d){kid}(?!\d)", where):
            fails.append(f"[0] 남길 행 {kid} 가 WHERE.md 에 없다(기준 확인)")
    if fails:
        print("\n".join(fails))
        return 1

    new_lines = list(lines)
    cards = {}
    for kid, i in plan.items():
        ln = lines[i]
        c = cells(ln)
        if len(c) != 6:
            fails.append(f"[1] {kid}: 칸이 6개가 아니다({len(c)})")
            continue
        idx = make_index(kid, c)
        card = make_card(kid, ln, c, arch_ids)
        new_lines[i] = idx
        cards[kid] = card
        # 2. 원문 행이 카드에 글자 그대로 있다 + 칸별로도 있다
        if ("\n" + ln + "\n") not in card:
            fails.append(f"[2] {kid}: 카드에 원문 행이 글자 그대로 없다")
        for j in (2, 3, 4, 5):
            if c[j] not in card.split("## 원문 행")[0]:
                fails.append(f"[2] {kid}: 칸 {j + 1} 이 카드 머리에 그대로 없다")
        # 3. 색인 줄의 숫자는 원문 행에 있는 숫자뿐
        src_nums = set(NUM.findall(ln))
        extra = [n for n in NUM.findall(idx.rsplit("|", 2)[0]) if n not in src_nums]
        if extra:
            fails.append(f"[3] {kid}: 색인 줄에 원문에 없는 숫자 {extra}")
        # 4. 근거 칸 조각은 원문 행의 부분 문자열
        for piece in INDEX[kid][1].split(" · "):
            if piece not in ln:
                fails.append(f"[4] {kid}: 근거 조각이 원문에 없다 — {piece}")
        # 5. 색인 줄 칸 수·카드 경로·이미 있는 카드 파일
        if len(cells(idx)) != 6:
            fails.append(f"[5] {kid}: 색인 줄 칸이 6개가 아니다")
        if (CARD_DIR / f"{kid}.md").exists():
            fails.append(f"[5] {kid}: 카드 파일이 이미 있다(덮어쓰지 않는다)")
        # 6. 카드의 정본 링크가 실재
        fails += [f"[6] {x}" for x in link_problems(f"knowledge/{kid}.md", card)]

    new_text = nl.join(new_lines)
    # 7. 옮기지 않는 줄은 글자 그대로 · 줄 수 같음 · 번호 집합·순서 같음
    changed = [i for i, (a, b) in enumerate(zip(lines, new_lines)) if a != b]
    if len(lines) != len(new_lines) or sorted(changed) != sorted(plan.values()):
        fails.append("[7] 옮기는 행 말고 다른 줄이 바뀌었다")
    ids_before = [m.group(1) for ln in lines if (m := ROW.match(ln))]
    ids_after = [m.group(1) for ln in new_lines if (m := ROW.match(ln))]
    if ids_before != ids_after or len(set(ids_after)) != len(ids_after):
        fails.append("[7] 행 번호의 집합·순서가 달라졌거나 중복이 있다")
    # 8. 원장 모델 이름이 전부 남아 있다 · KNOWLEDGE 링크 실재 · 크기
    for mid in ledger:
        if not re.search(rf"(?<![A-Za-z0-9_]){re.escape(mid)}(?![A-Za-z0-9_])", new_text):
            fails.append(f"[8] 옮긴 뒤 KNOWLEDGE 에 원장 모델 {mid} 가 없다")
    planned = {f"knowledge/{k}.md 없음" for k in cards}  # 모의 실행에서는 아직 안 쓴 카드 — 이번에 만들 것만 봐준다
    fails += [f"[8] {x}" for x in link_problems("KNOWLEDGE.md(옮긴 뒤)", new_text) if x.split("→ ")[1] not in planned]
    size_b, size_a = len(raw), len(new_text.encode("utf-8"))
    if size_a > ts.CAPS["KNOWLEDGE.md"]:
        fails.append(f"[8] 옮긴 뒤 크기 {size_a:,}B 가 상한을 넘는다")
    # 9. 남기는 행(판정에 걸림)은 한 글자도 안 바뀐다
    for kid in keep:
        a = [ln for ln in lines if ln.startswith(f"| {kid} ")]
        b = [ln for ln in new_lines if ln.startswith(f"| {kid} ")]
        if a != b:
            fails.append(f"[9] 남길 행 {kid} 가 바뀌었다")

    print(f"== 옛 행 → 카드 옮기기 ({'적용' if apply else '모의 실행 — 파일 안 바꿈'}) ==")
    print(f"행 {len(ids_before)}개 = 이미 카드 {len(already)}({', '.join(already)}) + 남김 {len(keep)} + 옮김 {len(plan)}")
    print("\n[남기는 행 — 판정에 걸림]")
    for kid in ids_before:
        if kid in keep:
            print(f"  {kid}: {keep[kid]}")
    print("\n[옮기는 행]  번호  원문 → 색인(B)")
    for kid in ids_before:
        if kid in plan:
            a = len(lines[plan[kid]].encode("utf-8")); b = len(new_lines[plan[kid]].encode("utf-8"))
            print(f"  {kid}  {a:>5,} → {b:>4,}")
    print(f"\nKNOWLEDGE.md {size_b:,}B → {size_a:,}B (상한 {ts.CAPS['KNOWLEDGE.md']:,}B · 남는 자리 {ts.CAPS['KNOWLEDGE.md'] - size_a:,}B)")
    checks = ["[0] 계획·색인 문구 맞물림", "[1] 칸 6개", "[2] 원문 행·칸이 카드에 글자 그대로", "[3] 색인 숫자 ⊂ 원문 숫자",
              "[4] 근거 조각 ⊂ 원문", "[5] 색인 칸 수·기존 카드 없음", "[6] 카드 링크 실재", "[7] 다른 줄 불변·번호 순서 불변",
              "[8] 원장 모델 27개 유지·링크·크기", "[9] 남길 행 불변"]
    for c in checks:
        tag = c.split("]")[0] + "]"
        n = sum(1 for f in fails if f.startswith(tag))
        print(f"  {'ok  ' if n == 0 else 'FAIL'} {c}" + (f" — {n}건" if n else ""))
    if fails:
        print("\n" + "\n".join(fails))
        print("\n검사 실패 — 아무것도 쓰지 않았다.")
        return 1
    if not apply:
        print("\n모의 실행 통과. 쓰려면 --apply")
        return 0
    for kid, card in cards.items():
        (CARD_DIR / f"{kid}.md").write_bytes(card.encode("utf-8"))
    KFILE.write_bytes(new_text.encode("utf-8"))
    print(f"\n적용함: 카드 {len(cards)}장 + KNOWLEDGE.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
