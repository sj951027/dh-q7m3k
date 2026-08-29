# -*- coding: utf-8 -*-
"""leaderboard 판정 프로토콜 동결창 골든 테스트 (실 DB 읽기 전용)

원리: 2026-07-29 이전에 h20 창이 닫힌 앵커들의 IC 는 **영원히 불변**이다(과거 시세·동결점수).
따라서 게이트·앵커·dedupe·REG_DATE·JUMP_CAP·MIN_GROUP·IC 계산 어디가 바뀌어도
아래 골든값이 깨진다 — "조용히 틀어지는" 회귀(2026-08-12 게이트 사건 유형)를 잡는 그물.
⚠ 골든이 깨지면 골든을 고치지 말 것 — 로직 변경이 의도된 것인지(전/후 비교·사용자 승인)부터 확인.
실행: python tests/test_leaderboard_frozen.py  (repo 루트 기준 상대경로, history.db 필요, ~20초)
"""
import sys, sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
import leaderboard as lb

P = 0
def check(n, c, info=""):
    global P
    assert c, f"FAIL: {n} {info}"
    P += 1
    print(f"  ok  {n}" + (f"  [{info}]" if info else ""))

FREEZE = "20260729"   # 이 날짜 이전 앵커의 h20 창은 전부 마감 — 데이터가 늘어도 불변
GOLDEN = {  # 2026-08-29 동결. (VERDICT_20260829_lowvol.md·docs/leaderboard.json 과 교차확인된 값)
    # (table, score_col, model_id): (n_anchors, mean_ic)
    ("lowvol_scores", "lowvol_score", "lv_b"): (22, 0.0687),
    ("lowvol_scores", "lowvol_score", "lv_c"): (22, -0.0962),
    ("v3_scores", "final_score_v3", "v30"):    (35, 0.0584),
}
TOL = 5e-4

close, _ = lb.load_ohlcv()
dates = list(close.index); N = len(dates)
con = sqlite3.connect(f"file:{ROOT/'history.db'}?mode=ro", uri=True)
partial, dbl, didx = lb.build_gates(con, dates)
excl = partial | dbl

print("[1] 게이트 동결값")
check("부분실행 게이트 == {20260608}", partial == {"20260608"}, str(sorted(partial)))
check("이중실행 게이트 == {20260703}", dbl == {"20260703"}, str(sorted(dbl)))

print("\n[2] REG_DATE 원장 핵심값")
for m, d in (("v30", "20260606"), ("lv_b", "20260625"), ("mom_b", "20260717")):
    check(f"REG_DATE[{m}] == {d}", str(lb.REG_DATE.get(m)) == d, str(lb.REG_DATE.get(m)))

print("\n[3] 동결창 h20 IC 골든 (앵커 ≤ %s)" % FREEZE)
H = lb.H_PRIMARY
for (tb, sc_col, mid), (g_n, g_ic) in GOLDEN.items():
    S = pd.read_sql(f"SELECT run_id,market,ticker,{sc_col} AS score FROM {tb} WHERE model_id=?",
                    con, params=(mid,))
    S["ticker"] = S.ticker.astype(str); S["run_id"] = S.run_id.astype(str)
    keep = lb.dedupe_by_anchor(S, didx, excl, reg=lb.REG_DATE.get(mid))
    out = {}
    for rid, g in S.groupby("run_id"):
        if rid in excl or rid not in keep or rid > FREEZE:
            continue
        t = lb.anchor(rid, didx)
        if t is None or t + lb.ENTRY_LAG + H >= N:
            continue
        fwd = close.iloc[t + lb.ENTRY_LAG + H] / close.iloc[t + lb.ENTRY_LAG] - 1
        jump = close.pct_change(fill_method=None).abs()\
            .iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + H + 1].max()
        fwd = fwd.where(jump <= lb.JUMP_CAP)
        ics = []
        for mk, gm in g.groupby("market"):
            s = gm.set_index("ticker")["score"].astype(float)
            b = fwd.reindex(s.index)
            msk = s.notna() & b.notna()
            if msk.sum() < lb.MIN_GROUP or s[msk].nunique() < 3 or b[msk].nunique() < 3:
                continue
            ics.append(np.corrcoef(s[msk].rank(), b[msk].rank())[0, 1])
        if ics:
            out[rid] = float(np.mean(ics))
    sr = pd.Series(out)
    check(f"{mid} 앵커수 == {g_n}", len(sr) == g_n, str(len(sr)))
    check(f"{mid} 평균 IC == {g_ic:+.4f} (±{TOL})", abs(sr.mean() - g_ic) < TOL, f"{sr.mean():+.6f}")

print("\n[4] 프로토콜 상수 동결")
for name, val in (("ENTRY_LAG", 1), ("H_PRIMARY", 20), ("MIN_GROUP", 8), ("JUMP_CAP", 0.32)):
    check(f"{name} == {val}", getattr(lb, name) == val, str(getattr(lb, name)))

print(f"\n✅ leaderboard 동결 골든 {P}개 체크 통과")
