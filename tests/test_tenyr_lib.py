# -*- coding: utf-8 -*-
"""research/lib/tenyr.py 가 2026-11-08 signal_board_10y 결과(tenyr_days.csv · e1_cells.csv)를 그대로 재현하는지 (0-diff).
ohlcv_10y.db 가 없으면 건너뛴다. 실행 약 1~2분. `python tests/test_tenyr_lib.py`"""
import os, sys
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))
from lib import tenyr

REF = REPO / "research" / "out_signal_board"


def main():
    if not os.path.exists(tenyr.DB):
        print("SKIP: ohlcv_10y.db 없음"); return 0
    tenyr.reset_rng()
    P = tenyr.load_panel(verbose=False)
    ks_rv = (np.log(P.ks).diff().rolling(20).std() * np.sqrt(250)).reindex(P.dates) * 100
    R = tenyr.signal_days(P, extra=lambda P_, i, ok: dict(rv=ks_rv.iloc[i]))
    R = R[R.cell.notna() & R.rv.notna()].copy()
    ref = pd.read_csv(REF / "tenyr_days.csv", dtype={"date": str, "month": str})
    assert len(R) == len(ref), (len(R), len(ref))
    for c in ["date", "cell"]:
        assert (R[c].values == ref[c].values).all(), c
    for c in ["r20", "rv", "n_os", "os40", "all40", "exc"]:
        assert np.allclose(R[c].values, ref[c].values, atol=1e-9, equal_nan=True), c
    # E1 — 원 스크립트와 같은 순서로 부트스트랩 → e1_cells.csv 와 같아야 한다
    e1 = []
    for scope, sub0 in (("전체", R), ("앞반 2015~20", R[R.half == "앞"]), ("뒤반 2021~", R[R.half == "뒤"])):
        for c in ["A2", "A1", "B", "C", "D1", "D2", "A", "D", "모두"]:
            sub = sub0 if c == "모두" else (sub0[sub0.cell4 == c] if c in ("A", "D") else sub0[sub0.cell == c])
            if len(sub) < 4:
                continue
            e1.append(dict(범위=scope, 칸=c, **tenyr.summ(sub)))
    E1 = pd.DataFrame(e1); ref1 = pd.read_csv(REF / "e1_cells.csv")
    assert list(E1.columns) == list(ref1.columns)
    assert (E1[["범위", "칸"]].values == ref1[["범위", "칸"]].values).all()
    num = [c for c in E1.columns if c not in ("범위", "칸")]
    assert np.allclose(E1[num].values.astype(float), ref1[num].values.astype(float), atol=1e-9), "E1 CI 불일치"
    print(f"OK tenyr lib 0-diff: 신호일 {len(R)} · E1 {len(E1)}행")
    return 0


if __name__ == "__main__":
    sys.exit(main())
