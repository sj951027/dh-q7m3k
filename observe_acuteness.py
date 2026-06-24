# -*- coding: utf-8 -*-
"""
observe_acuteness.py — '관측 전용' 급락 급성도(drop_acuteness) 컬럼을 stage3_final 에 배선
==============================================================================
목적: "신선한 샤프 이탈(최근 며칠에 낙폭 집중) vs 만성 갈림(몇 주 슬슬)"을 한 축으로 잰다.
      재출현(os_count_20d=과매도 *상태*에 얼마나 오래)과 직교: 이건 *어떻게 빠졌나*(형태).
      가중치 0 관측값 — 점수식(final_score / final_score_v3)에 절대 안 들어감.
      validate_scores 의 FACTOR_COLUMNS 에 'drop_acuteness' 등록 → IC 하니스가 자동 측정.

정의(동결 — 시작하면 변경 금지):
  drop_acuteness[run R, ticker] = return_1w_% / return_1m_%      (단 return_1m_% <= DROP_FLOOR)
    * = '직전 1개월 낙폭 중 최근 1주에 실현된 비율'.
        ≈1  : 한 달 낙폭이 사실상 최근 1주에 다 일어남 = 급성 이탈(반등 후보).
        ≈0  : 한 달은 빠졌는데 최근 1주는 평평 = 만성 갈림/바닥 다지기.
        <0  : 최근 1주 반등 중(return_1w_% 양) = '덜 급성'으로 랭크(=반전축은 reversal_* 가 따로 봄).
    * return_1m_% > DROP_FLOOR(=의미있는 월 낙폭 없음) 이면 NaN(=특성화 대상 아님 → IC 단계 pending).
      → '한 달간 실제로 내린' 종목만 형태를 평가(분모가 0 근처라 비율이 폭주하는 것도 차단).
    * IC 는 Spearman(순위) 이라 비율 이상치는 무해 → 클립 안 함(정보 보존).

PIT: return_1w_% · return_1m_% 는 run R 의 스크리너 산출(가격 ≤ R) → 그 순수 변환이라 룩어헤드 없음.
안전: 점수 미사용(v3_rescore/v3_merge 가 안 읽음 → 0-diff). 재실행 안전(컬럼 없을 때만 ALTER,
      값은 (market,run_id,ticker) UPDATE). 결정적 변환이라 멱등.

사용:
    python observe_acuteness.py            # 미채움 run 만 증분(파이프라인 일일)
    python observe_acuteness.py --full     # 전체 run 재계산
    python observe_acuteness.py --db history.db
"""
import argparse
import sqlite3

import numpy as np
import pandas as pd

DB_DEFAULT = "history.db"
DROP_FLOOR = -3.0   # '한 달간 실제 하락'의 하한(%). 분모 폭주 차단용. 동결.
COL = "drop_acuteness"
SRC = ["return_1w_%", "return_1m_%"]


def compute(con):
    df = pd.read_sql(
        'SELECT market, run_id, ticker, "return_1w_%" AS w, "return_1m_%" AS m '
        'FROM stage3_final', con)
    df["run_id"] = df["run_id"].astype(str)
    w = pd.to_numeric(df["w"], errors="coerce")
    m = pd.to_numeric(df["m"], errors="coerce")
    val = w / m
    val = val.where(m <= DROP_FLOOR)        # 월 낙폭 충분할 때만, 아니면 NaN
    val = val.replace([np.inf, -np.inf], np.nan)
    df[COL] = val
    return df.dropna(subset=[COL])[["market", "run_id", "ticker", COL]]


def ensure_column(con):
    cur = con.cursor()
    existing = {r[1] for r in cur.execute('PRAGMA table_info("stage3_final")')}
    if COL not in existing:
        cur.execute(f'ALTER TABLE "stage3_final" ADD COLUMN "{COL}" REAL')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_stage3_mrt '
                'ON "stage3_final"(market, run_id, ticker)')
    con.commit()


def filled_runs(con):
    cur = con.cursor()
    rows = cur.execute(
        f'SELECT run_id, SUM("{COL}" IS NOT NULL) '
        'FROM "stage3_final" GROUP BY run_id').fetchall()
    return {str(r[0]) for r in rows if (r[1] or 0) > 0}


def update(con, df):
    if df.empty:
        return 0
    rows = [(float(v), str(mk), str(rid), str(tk))
            for mk, rid, tk, v in zip(df["market"], df["run_id"],
                                      df["ticker"], df[COL])
            if pd.notna(mk)]
    cur = con.cursor()
    cur.executemany(f'UPDATE "stage3_final" SET "{COL}"=? '
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
    df = compute(con)
    if not a.full and done:
        df = df[~df["run_id"].isin(done)]
    n = update(con, df)
    con.close()
    print(f"{COL} UPDATE: {n}행 "
          f"(DROP_FLOOR={DROP_FLOOR}% · {'전체' if a.full else '증분'})")


if __name__ == "__main__":
    main()
