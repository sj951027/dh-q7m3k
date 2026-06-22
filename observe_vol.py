# -*- coding: utf-8 -*-
"""
observe_vol.py — '관측 전용' realized_vol 컬럼을 history.db(stage3_final)에 배선
==============================================================================
목적: low-vol(저변동성) 가설 검정용 trailing 실현변동성을 *가중치 0* 으로 적재.
      점수식(final_score / final_score_v3)에는 절대 안 들어간다. validate_scores 의
      FACTOR_COLUMNS 에 'realized_vol' 등록 → IC 하니스가 자동 측정.

정의(동결):
  realized_vol[run R, ticker] = std( trailing WINDOW 활성런 종가수익률 )
    * 활성런 정의는 v3_backtest.filter_active_runs 와 동일(주말/부분실행/정적 run 제거)
      → realized_vol 윈도우가 IC 포워드리턴의 활성런과 같은 시계열을 본다.
    * WINDOW=21 활성런(≈1개월, 저변동성 문헌 표준). MIN_OBS 미만이면 NaN(=pending).
    * 가격은 run R 시점까지만 사용 → 포인트-인-타임 안전(룩어헤드 없음).
    * 부호는 데이터에 맡긴다(low-vol 가설이면 raw vol 의 IC 가 음(-): 저변동→고수익).

안전:
  * 점수 미사용(v3_rescore 가 realized_vol 을 읽지 않음 — 0-diff).
  * 재실행 안전(idempotent): 컬럼은 없을 때만 ALTER, 값은 (run_id,ticker) 로 UPDATE.
    trailing 이라 과거 run 의 realized_vol 은 새 run 이 와도 불변 → 기본은 '미채움 run' 만 증분.
  * 커버리지 한계 명시: 가격이 stage1_oversold 패널(과매도 유니버스)에만 있어, 최근 WINDOW
    동안 충분히 머문 종목만 계산됨(신규 편입은 NaN=pending). 기존 IC 와 동일한 제약.

사용:
    python observe_vol.py                 # 미채움 run 만 증분(파이프라인 일일)
    python observe_vol.py --full          # 전체 run 재계산
    python observe_vol.py --db history.db
"""
import argparse
import sqlite3
import numpy as np
import pandas as pd

import v3_backtest as bt   # price_panel, filter_active_runs 재사용(동일 활성런 정의)

DB_DEFAULT = "history.db"
WINDOW = 21    # trailing 활성런 수(≈1개월). 동결 — 시작하면 변경 금지.
MIN_OBS = 8    # 최소 수익률 관측수. 미만이면 NaN(=pending, 윈도우 채워질 때까지).


def compute_realized_vol(db_path):
    """모든 활성런 R 에 대해 trailing WINDOW 수익률 표준편차(종목별)."""
    panel, runs, tk_mkt = bt.price_panel(db_path)
    active = bt.filter_active_runs(panel, runs)
    sub = panel[active]                                  # ticker × 활성런
    rets = sub.pct_change(axis=1, fill_method=None)      # 인접 활성런 수익률(미존재=NaN)
    recs = []
    for i, R in enumerate(active):
        win = active[max(0, i - WINDOW + 1): i + 1]      # trailing 윈도우(R 포함)
        wret = rets[win]
        n = wret.notna().sum(axis=1)
        vol = wret.std(axis=1, ddof=1).where(n >= MIN_OBS)
        d = pd.DataFrame({"ticker": vol.index, "realized_vol": vol.values})
        d["run_id"] = str(R)
        recs.append(d.dropna(subset=["realized_vol"]))
    if not recs:
        return pd.DataFrame(columns=["market", "ticker", "run_id", "realized_vol"])
    out = pd.concat(recs, ignore_index=True)
    out["market"] = out["ticker"].map(tk_mkt)            # idx_stage3_mrt(market,run_id,ticker) 사용 위해 동반
    return out


def ensure_column(con):
    cur = con.cursor()
    existing = {r[1] for r in cur.execute('PRAGMA table_info("stage3_final")')}
    if "realized_vol" not in existing:
        cur.execute('ALTER TABLE "stage3_final" ADD COLUMN "realized_vol" REAL')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_stage3_mrt '
                'ON "stage3_final"(market, run_id, ticker)')
    con.commit()


def filled_runs(con):
    """realized_vol non-null 이 1개라도 있는 run = '처리됨'(개별 NaN 은 무관)."""
    cur = con.cursor()
    rows = cur.execute(
        'SELECT run_id, SUM(realized_vol IS NULL), COUNT(*) '
        'FROM "stage3_final" GROUP BY run_id').fetchall()
    return {str(r[0]) for r in rows if (r[2] - r[1]) > 0}


def update(con, df):
    if df.empty:
        return 0
    # (market,run_id,ticker) 3키 → idx_stage3_mrt 사용(풀스캔 방지). executemany 일괄.
    rows = [(float(rv), str(mk), str(rid), str(tk))
            for mk, rid, tk, rv in zip(df["market"], df["run_id"],
                                       df["ticker"], df["realized_vol"])
            if pd.notna(mk)]
    cur = con.cursor()
    cur.executemany('UPDATE "stage3_final" SET realized_vol=? '
                    'WHERE market=? AND run_id=? AND ticker=?', rows)
    con.commit()
    return cur.rowcount if (cur.rowcount and cur.rowcount > 0) else len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_DEFAULT)
    ap.add_argument("--full", action="store_true",
                    help="모든 run 재계산(기본=미채움 run 만 증분)")
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    ensure_column(con)
    done = set() if a.full else filled_runs(con)
    df = compute_realized_vol(a.db)
    if not a.full and done:
        df = df[~df["run_id"].isin(done)]
    n = update(con, df)
    con.close()
    print(f"realized_vol UPDATE: {n}행 "
          f"(WINDOW={WINDOW} 활성런, MIN_OBS={MIN_OBS}, {'전체' if a.full else '증분'})")


if __name__ == "__main__":
    main()
