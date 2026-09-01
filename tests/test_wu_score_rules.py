# -*- coding: utf-8 -*-
"""wu_score spec 골든 회귀 테스트 (합성/정적 — DB 불필요)

고정하는 규칙:
  1. spec_hash 골든 — 등록 6모델 해시 불변(스펙 드리프트 감지). 2026-09-01 동결 —
     라이브 spec_hash() == history.db wu_scores 저장값 == PREREGISTER 문서값 3중 일치 확인 후 고정.
     ⚠ 새 모델 추가는 허용(sv_b 등 — 목록에 골든 추가만). 기존 해시가 바뀌면 스펙 변경 사고.
     배경: 9/11 sv_b 배선 패치가 wu_score.py 를 수정하므로 그 전에 안전망으로 깔았다.
  2. 방향 골든 — svr5 ascending=True(공매도비중 '높을수록' 상위 — 2026-08-29 방향 혼동 사건),
     nh252·mom12 도 True(높을수록 상위).
  3. 기존 모델 id 는 제거·개명 불가(부활·변경은 새 model_id — §11).
실행: python tests/test_wu_score_rules.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wu_score as ws

P = 0
def check(n, c, info=""):
    global P
    assert c, f"FAIL: {n} {info}"
    P += 1
    print(f"  ok  {n}" + (f"  [{info}]" if info else ""))

print("[1] spec_hash 골든 (2026-09-01 동결 — DB·PREREGISTER 3중 일치 확인분)")
GOLDEN = {
    "wu_a": "6c146134b5a1",   # PREREGISTER_wu.md
    "wu_b": "f09894fd2fcf",   # PREREGISTER_wu.md
    "le_a": "29cb040142b0",   # PREREGISTER_le_sv.md
    "sv_a": "e38efdfc260d",   # PREREGISTER_le_sv.md / PREREGISTER_sv_b.md 대조값
    "qs_a": "77ece1338941",   # PREREGISTER_qs.md
    "px_a": "44350297d4cc",   # PREREGISTER_px_a.md
}
for mid, h in GOLDEN.items():
    check(f"spec_hash: {mid}", ws.spec_hash(mid) == h, h)

print("[2] 팩터 방향 골든")
check("svr5 ascending=True(공매도비중 높을수록 상위)", ws.FACTORS["svr5"][0] is True)
check("nh252 ascending=True", ws.FACTORS["nh252"][0] is True)
check("mom12 ascending=True", ws.FACTORS["mom12"][0] is True)

print("[3] 등록 모델 보존(추가만 허용)")
check("기존 6모델 전부 존재", set(GOLDEN) <= set(ws.MODELS), str(sorted(ws.MODELS)))

print(f"\n✅ test_wu_score_rules: {P}개 체크 전체 통과")
