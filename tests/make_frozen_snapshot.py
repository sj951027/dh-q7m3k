# -*- coding: utf-8 -*-
"""동결창 forward 수익 스냅샷 생성 (1회성, 2026-09-04)

왜: test_leaderboard_frozen 은 "마감된 창의 시세는 불변"을 전제했는데, 원천(FDR)이 과거 가격을 정정하면
    (감자 재조정 재적재, 권리락 정정 — patch_note/20260904_ops_fixes.md) 골든이 코드와 무관하게 깨진다.
    → 동결창 앵커(≤FREEZE)의 종목별 h20 forward 수익(JUMP_CAP 적용 후)을 CSV 로 박아 두고 테스트는 이걸 읽는다.
    이러면 테스트는 '코드'만 검사한다. 시세 정정으로 스냅샷을 다시 뜨는 것은 의도된 갱신이며 patch_note 로 남긴다.
실행: python tests/make_frozen_snapshot.py  → tests/frozen_fwd_h20.csv (run_id,ticker,fwd)
"""
import sys, sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pandas as pd
import leaderboard as lb

FREEZE = "20260729"
close, _ = lb.load_ohlcv()
dates = list(close.index); N = len(dates)
con = sqlite3.connect(f"file:{ROOT/'history.db'}?mode=ro", uri=True)
partial, dbl, didx = lb.build_gates(con, dates)
H = lb.H_PRIMARY
need = {}   # run_id -> 그 run 의 점수 테이블에 실제로 있는 종목만(파일 크기 절약)
for tb in ("lowvol_scores", "v3_scores"):
    d = pd.read_sql(f"SELECT DISTINCT run_id, ticker FROM {tb} WHERE run_id<=?", con, params=(FREEZE,))
    for rid, tk in zip(d.run_id.astype(str), d.ticker.astype(str)):
        need.setdefault(rid, set()).add(tk)
rids = sorted(set(pd.read_sql("SELECT DISTINCT run_id FROM v3_scores", con).run_id.astype(str))
              | set(pd.read_sql("SELECT DISTINCT run_id FROM lowvol_scores", con).run_id.astype(str)))
rows = []
pc = close.pct_change(fill_method=None).abs()
for rid in rids:
    if rid > FREEZE:
        continue
    t = lb.anchor(rid, didx)
    if t is None or t + lb.ENTRY_LAG + H >= N:
        continue
    fwd = close.iloc[t + lb.ENTRY_LAG + H] / close.iloc[t + lb.ENTRY_LAG] - 1
    jump = pc.iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + H + 1].max()
    fwd = fwd.where(jump <= lb.JUMP_CAP)
    want = need.get(rid, set())
    for tk, v in fwd.items():
        if str(tk) in want:
            rows.append((rid, str(tk), None if pd.isna(v) else round(float(v), 6)))
out = pd.DataFrame(rows, columns=["run_id", "ticker", "fwd"])
out.to_csv(ROOT / "tests" / "frozen_fwd_h20.csv", index=False)
print(f"저장: tests/frozen_fwd_h20.csv — 앵커 {out.run_id.nunique()}개 · {len(out):,}행 · 종목 {out.ticker.nunique()} (NaN=JUMP_CAP 컷 {out.fwd.isna().sum()})")
