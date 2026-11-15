# -*- coding: utf-8 -*-
"""sv_b 판정문(11/13) 보충 계산 — 판정 뒤 추기용, 라벨에 쓰지 않는다 (2026-11-15).

왜: 판정문에서 두 가지가 빠졌다.
  ① 자리바꿈 백분위(VERDICT_RULES 각주 ④ · DECISIONS D16) — "노이즈라 쓸 곳이 없다"며 생략했다.
  ② 10/14 앵커 포함/제외 값(MODELS_LEDGER [10-18 추기]가 약속한 병기) — wu 트랙만 빠진 날을 사후 적재해 그날 앵커가 있다.

어떻게: 판정 스크립트 `verdict_sv_b_20261113.py` 를 **고치지 않고 그대로** 실행하되, 자료를 판정 당시(가격·run 모두 20261112 까지)로 자른다.
  잘라 낸 자료로 판정문의 주 숫자(n=19 · +0.0025)가 다시 나오는지 먼저 확인한다 — 안 나오면 보충 값도 믿지 않는다.
읽기 전용(history.db·ohlcv.db mode=ro, 파일을 쓰지 않는다 — 화면 출력만).

실행: python -X utf8 research/verdict_sv_b_addendum_20261115.py [--perm 2000]
"""
import runpy
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import leaderboard as lb  # noqa: E402

CUT = "20261112"          # 판정 당시 마지막 가격·run
DROP = "20261014"         # 사후 적재된 앵커
EXPECT_N, EXPECT_IC = 19, 0.0025   # 판정문 §1 주지표 — 재현 확인용

_load = lb.load_ohlcv


def load_cut():
    close, mktmap = _load()
    return close.loc[[d for d in close.index if str(d) <= CUT]], mktmap


_read = pd.read_sql


def read_cut(sql, con, *a, **k):
    df = _read(sql, con, *a, **k)
    if "run_id" in df.columns:
        df = df[df["run_id"].astype(str) <= CUT]
    return df


lb.load_ohlcv = load_cut
pd.read_sql = read_cut
try:
    g = runpy.run_path(str(REPO / "research" / "verdict_sv_b_20261113.py"), run_name="__main__")
finally:
    lb.load_ohlcv = _load
    pd.read_sql = _read

base, boot_ci, weekly = g["base"], g["boot_ci"], g["weekly"]
b = base["sv_b"]; a = base["sv_a(9/14~)"]
ok = len(b) == EXPECT_N and abs(round(float(b.mean()), 4) - EXPECT_IC) < 1e-9
print("\n=== 보충 ① 재현 확인(자료를 %s 까지로 자름) ===" % CUT)
print(f"  sv_b h20: n={len(b)} 평균 {b.mean():+.4f} — 판정문 n={EXPECT_N} {EXPECT_IC:+.4f} → {'일치' if ok else '불일치(보충 값 사용 금지)'}")
print(f"  분모(트랙 표 distinct model_id) = {g['DEN_LV']} — 이 값은 직접 SQL 이라 잘리지 않는다(CUT 뒤에 새 모델이 생겼으면 판정 당시와 다르다; 사전등록 값 {g['DEN_PRE']} 과 대조)")
print("  한계: 가격·run 만 판정 당시로 자른다 — 그 뒤 고쳐진 과거 행·신용 적재 마스크는 되돌리지 못한다(당시 DB 전체의 복원이 아님)")
if not ok or g["DEN_LV"] != g["DEN_PRE"]:
    sys.exit("재현 불일치 또는 분모 변화 — 보충 값을 내지 않는다")

print("\n=== 보충 ② 10/14 앵커(사후 적재) 포함/제외 ===")
for name, sr in (("sv_b", b), ("sv_a", a)):
    ex = sr.drop(index=[DROP], errors="ignore")
    c0 = boot_ci(sr.values); c1 = boot_ci(ex.values); w1 = weekly(ex)
    print(f"  {name}: 포함 n={len(sr)} {sr.mean():+.4f} [{c0[0]:+.4f}, {c0[1]:+.4f}] | 제외 n={len(ex)} {ex.mean():+.4f} [{c1[0]:+.4f}, {c1[1]:+.4f}] 주별양 {100*(w1>0).mean():.0f}%({len(w1)}주)"
          f" | 10/14 값 {sr.get(DROP, np.nan):+.4f}")
d = (b - a).dropna(); dx = d.drop(index=[DROP], errors="ignore")
c0 = boot_ci(d.values); c1 = boot_ci(dx.values)
print(f"  짝 sv_b−sv_a: 포함 n={len(d)} {d.mean():+.4f} [{c0[0]:+.4f}, {c0[1]:+.4f}] | 제외 n={len(dx)} {dx.mean():+.4f} [{c1[0]:+.4f}, {c1[1]:+.4f}]")
print("  (자리바꿈 값은 위 판정 스크립트 출력의 '자리바꿈' 줄 — --perm 을 준 경우)")
