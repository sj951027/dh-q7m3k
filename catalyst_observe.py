# -*- coding: utf-8 -*-
"""
catalyst_observe.py — '관측 전용' 팩터를 history.db(stage3_final)에 배선
=====================================================================
목적: 새 후보 팩터들을 *가중치 0* 으로 stage3_final 에 컬럼으로 쌓아두고,
      validate_scores / compute_ic 의 IC 하니스가 자동으로 예측력을 재게 한다.
      → 점수(final_score / final_score_v3)는 '전혀' 건드리지 않는다.
      → 데이터가 (몇 주 뒤) 어느 팩터를 final_score_v3 로 승격할지 결정한다.

추가하는 관측 컬럼 (stage3_final):
  • smartmoney_score   (0~15) : [과매도]+[거래대금 폭발]+[양봉]+[외인/기관 순매수]
                                 — 멀티플라이어 아님, 상한 있는 '가산' 보너스.
                                 stage3_final 에 이미 있는 컬럼으로만 계산 → '미채움 run' 만 증분 채움(--full 시 전체).
  • roe_value          (%)    : EPS/BPS×100 (자본잠식=BPS≤0 은 NaN). 연속값(IC용).
  • roe_gate           (0/1)  : PBR<1 & ROE≥8% (밸류업 '싸지만 부실하지 않은' 셀). '게이트' 용도.
  • insider_score      (0~15) : catalyst_insider.py 산출(프록시) — 있을 때만.
  • buyback_cancel_flag(0/1)  : 자사주 '소각' 공시 — 있을 때만.
  (부가 저장: smartmoney_trigger, insider_source, catalyst_score)

데이터 출처별 채움 정책 (NULL = '관측 안 됨', 0 과 구분):
  - smartmoney_*   : stage3_final 자체 컬럼으로 계산 → 미채움 run 만(이미 채운 run 은 건너뜀)
  - roe_*          : valuation_{market}_{run_id}.csv 있는 run 만
  - insider/buyback: catalyst_{market}_{run_id}.csv 있는 run 만 (없으면 NULL 유지)

실행 순서 (반드시 이 스크립트를 '먼저' 1회 돌려 컬럼을 만든 뒤 validate_scores 편집):
    python accumulate_history.py            # stage3_final 적재(평소 파이프라인)
    python fetch_valuation.py               # valuation_*.csv (ROE 재료)
    python catalyst_insider.py --market ... # catalyst_*.csv (내부자/소각) — 선택
    python catalyst_observe.py              # ← 관측 컬럼 ALTER + 백필(UPDATE)
    python validate_scores.py               # 이제 새 팩터 IC도 같이 나옴

재실행 안전(idempotent): 컬럼은 없을 때만 ALTER, 값은 (market,run_id,ticker)로 UPDATE.
"""
import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = "history.db"

# (컬럼명, SQLite 타입). 관측 전용 — 점수식에는 안 들어감.
OBS_COLUMNS = [
    ("smartmoney_score", "REAL"),
    ("smartmoney_trigger", "INTEGER"),
    ("roe_value", "REAL"),
    ("roe_gate", "INTEGER"),
    ("insider_score", "REAL"),
    ("insider_source", "TEXT"),
    ("buyback_cancel_flag", "INTEGER"),
    ("catalyst_score", "REAL"),
]

# validate_scores.FACTOR_COLUMNS 에 '숫자형'으로 등록할 것 (IC 측정 대상)
FACTOR_COLUMNS_TO_REGISTER = [
    "smartmoney_score", "roe_value", "insider_score", "buyback_cancel_flag",
]


# ----------------------------------------------------------------- 헬퍼
def _num(s):
    return pd.to_numeric(s, errors="coerce")


# ----------------------------------------------------------------- 스마트머니
def compute_smartmoney(df):
    """
    stage3_final 한 묶음(df) → (smartmoney_score 0~15, smartmoney_trigger 0/1).
    조건: 과매도 구간에서 거래대금이 20일 평균 대비 폭발 + 양봉 + 외인/기관 순매수.
    방향(양봉)·수급을 같이 걸어 '투매(공포매도)'성 거래량 폭발과 구분한다.
    """
    amt_today = _num(df.get("amt_today_억")).fillna(0)
    amt_avg = _num(df.get("amt_avg_1m_억")).fillna(0).clip(lower=0.01)
    ratio = amt_today / amt_avg

    up = (_num(df.get("reversal_vol_up_candle")).fillna(0) > 0) | \
         (_num(df.get("acc_signal_candle")).fillna(0) > 0)
    f = _num(df.get("foreign_5d_억")).fillna(0)
    i = _num(df.get("inst_5d_억")).fillna(0)
    flow_both = (f > 0) & (i > 0)
    flow_any = (f > 0) | (i > 0)
    osv = _num(df.get("oversold_score")).fillna(0)

    score = pd.Series(0.0, index=df.index)
    score += np.select([ratio >= 5, ratio >= 3, ratio >= 2], [6, 4, 2], default=0)
    score += up.astype(int) * 3
    score += np.select([flow_both, flow_any], [4, 2], default=0)
    score = score.clip(0, 15).round(1)

    trigger = ((ratio >= 3) & up & flow_any & (osv > 0)).astype(int)
    return score, trigger


# ----------------------------------------------------------------- ROE
def compute_roe(val_df):
    """valuation_*.csv(ticker,PBR,PER,DIV,BPS,EPS) → (roe_value %, roe_gate 0/1)."""
    pbr = _num(val_df.get("PBR"))
    per = _num(val_df.get("PER"))
    bps = _num(val_df.get("BPS"))
    eps = _num(val_df.get("EPS"))

    # 1순위: EPS/BPS (적자=음수 ROE 자연 반영). 자본잠식(BPS≤0)은 NaN.
    roe = (eps / bps * 100.0).where(bps > 0)
    # 보조: BPS/EPS 결측이면 PBR/PER (PER>0,PBR>0 일 때만). ROE = PBR/PER.
    fb = (pbr / per * 100.0).where((per > 0) & (pbr > 0))
    roe = roe.fillna(fb).clip(-200, 200)

    gate = ((pbr > 0) & (pbr < 1.0) & (roe >= 8.0)).astype(int)
    gate = gate.where(roe.notna(), 0)
    out = pd.DataFrame({"ticker": val_df["ticker"].astype(str).str.zfill(6),
                        "roe_value": roe.round(2), "roe_gate": gate})
    return out


# ----------------------------------------------------------------- 마이그레이션
def ensure_columns(con):
    cur = con.cursor()
    existing = {r[1] for r in cur.execute('PRAGMA table_info("stage3_final")')}
    added = []
    for name, typ in OBS_COLUMNS:
        if name not in existing:
            cur.execute(f'ALTER TABLE "stage3_final" ADD COLUMN "{name}" {typ}')
            added.append(name)
    # [성능] UPDATE WHERE(market,run_id,ticker) 가 풀스캔되지 않도록 인덱스 보장.
    # IF NOT EXISTS 라 1회만 생성되고 이후엔 무료. 값/결과는 안 바뀜.
    cur.execute('CREATE INDEX IF NOT EXISTS idx_stage3_mrt '
                'ON "stage3_final"(market, run_id, ticker)')
    con.commit()
    if added:
        print(f"   🧱 컬럼 추가: {', '.join(added)}")
    else:
        print("   🧱 컬럼 이미 존재 (스킵)")


# ----------------------------------------------------------------- UPDATE
def _update_cols(con, market, run_id, df, cols):
    """df(ticker + cols)를 (market,run_id,ticker) 키로 stage3_final 에 UPDATE."""
    cur = con.cursor()
    set_clause = ", ".join(f'"{c}"=?' for c in cols)
    sql = (f'UPDATE "stage3_final" SET {set_clause} '
           f'WHERE market=? AND run_id=? AND ticker=?')
    rows = []
    for _, r in df.iterrows():
        vals = []
        for c in cols:
            v = r[c]
            if isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating,)):
                v = None if pd.isna(v) else float(v)
            elif pd.isna(v):
                v = None
            vals.append(v)
        rows.append(vals + [market, run_id, str(r["ticker"]).zfill(6)])
    cur.executemany(sql, rows)
    con.commit()
    return len(rows)


def _run_status(con, market, run_id):
    """이 (market,run)이 관측 컬럼별로 이미 채워졌는지 판정.
    - sm_filled : smartmoney_score 가 모든 행에 채워짐(컴퓨트는 항상 0~15 부여 → NULL 0개면 완료)
    - roe_filled: roe_gate 가 1개라도 채워짐(처리 1회 흔적; 자본잠식 등 개별 NULL 은 무관)
    - cat_filled: insider_source 가 1개라도 채워짐
    """
    q = pd.read_sql(
        'SELECT SUM(smartmoney_score IS NULL) AS sm_null, '
        'SUM(roe_gate IS NOT NULL) AS roe_done, '
        'SUM(insider_source IS NOT NULL) AS cat_done, '
        'COUNT(*) AS n '
        'FROM stage3_final WHERE market=? AND run_id=?',
        con, params=[market, run_id])
    r = q.iloc[0]
    n = int(r["n"] or 0)
    return {
        "n": n,
        "sm_filled": n > 0 and int(r["sm_null"] or 0) == 0,
        "roe_filled": int(r["roe_done"] or 0) > 0,
        "cat_filled": int(r["cat_done"] or 0) > 0,
    }


def observe_run(con, market, run_id, force=False):
    # [성능] 이미 채워진 run 은 건너뛴다(값이 안 변하므로 결과 동일). --full 로 강제 가능.
    st = _run_status(con, market, run_id)
    if st["n"] == 0:
        return
    vpath = Path(f"valuation_{market}_{run_id}.csv")
    cpath = Path(f"catalyst_{market}_{run_id}.csv")
    need_sm = force or not st["sm_filled"]
    need_roe = vpath.exists() and (force or not st["roe_filled"])
    need_cat = cpath.exists() and (force or not st["cat_filled"])
    if not (need_sm or need_roe or need_cat):
        print(f"   [{market} {run_id}] 이미 채워짐 — 건너뜀")
        return

    base = pd.read_sql(
        'SELECT ticker, amt_today_억, amt_avg_1m_억, reversal_vol_up_candle, '
        'acc_signal_candle, foreign_5d_억, inst_5d_억, oversold_score '
        'FROM stage3_final WHERE market=? AND run_id=?',
        con, params=[market, run_id])
    if base.empty:
        return
    base["ticker"] = base["ticker"].astype(str).str.zfill(6)

    tags = []
    # 1) 스마트머니 (항상 계산 가능)
    if need_sm:
        sm, tr = compute_smartmoney(base)
        sm_df = pd.DataFrame({"ticker": base["ticker"],
                              "smartmoney_score": sm, "smartmoney_trigger": tr})
        n_sm = _update_cols(con, market, run_id, sm_df,
                            ["smartmoney_score", "smartmoney_trigger"])
        tags.append(f"smart {n_sm}")
    else:
        tags.append("smart 유지")

    # 2) ROE (valuation csv 있을 때만)
    if need_roe:
        val = pd.read_csv(vpath, dtype={"ticker": str})
        roe = compute_roe(val)
        roe = base[["ticker"]].merge(roe, on="ticker", how="left")
        n_roe = _update_cols(con, market, run_id, roe, ["roe_value", "roe_gate"])
        tags.append(f"roe {n_roe}")
    elif vpath.exists():
        tags.append("roe 유지")

    # 3) 내부자/소각 (catalyst csv 있을 때만; 없으면 NULL 유지)
    if need_cat:
        cat = pd.read_csv(cpath, dtype={"ticker": str})
        cat["ticker"] = cat["ticker"].astype(str).str.zfill(6)
        for col, default in [("insider_score", 0.0), ("insider_source", "NONE"),
                             ("buyback_cancel_flag", 0), ("catalyst_score", 0.0)]:
            if col not in cat.columns:
                cat[col] = default
        cat = base[["ticker"]].merge(
            cat[["ticker", "insider_score", "insider_source",
                 "buyback_cancel_flag", "catalyst_score"]], on="ticker", how="left")
        n_cat = _update_cols(con, market, run_id, cat,
                             ["insider_score", "insider_source",
                              "buyback_cancel_flag", "catalyst_score"])
        tags.append(f"catalyst {n_cat}")
    else:
        tags.append("catalyst 없음(NULL)" if not cpath.exists() else "catalyst 유지")

    print(f"   [{market} {run_id}] " + " · ".join(tags))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--run_id", default=None, help="특정 run 만. 기본: 미채움 run 전체 증분")
    ap.add_argument("--market", choices=["kospi", "kosdaq"], default=None)
    ap.add_argument("--full", action="store_true",
                    help="이미 채워진 run 도 강제 재계산(기본: 채워진 run 은 건너뜀)")
    args = ap.parse_args()

    if not Path(args.db).exists():
        raise SystemExit(f"❌ DB 없음: {args.db}")

    con = sqlite3.connect(args.db)
    print(f"\n{'='*60}\n▶  관측 팩터 배선 (가중치 0, 점수식 불변)\n{'='*60}")
    ensure_columns(con)

    pairs = pd.read_sql(
        "SELECT DISTINCT market, run_id FROM stage3_final ORDER BY run_id, market", con)
    if args.market:
        pairs = pairs[pairs["market"] == args.market]
    if args.run_id:
        pairs = pairs[pairs["run_id"] == args.run_id]
    mode = "전체 강제(--full)" if args.full else "증분(미채움 run 만)"
    print(f"   대상 {len(pairs)}개 (market,run) — {mode}\n")

    for _, p in pairs.iterrows():
        observe_run(con, p["market"], str(p["run_id"]), force=args.full)

    # 요약
    print(f"\n{'─'*60}\n요약(관측 컬럼 채움 현황)")
    chk = pd.read_sql(
        'SELECT '
        'SUM(smartmoney_score IS NOT NULL) sm, '
        'SUM(roe_value IS NOT NULL) roe, '
        'SUM(insider_score IS NOT NULL) ins, '
        'SUM(buyback_cancel_flag IS NOT NULL) buy, '
        'COUNT(*) tot FROM stage3_final', con)
    print(chk.to_string(index=False))
    con.close()
    print(f"\n다음: validate_scores.py 의 FACTOR_COLUMNS 에 다음을 추가하면 IC가 잡습니다 →")
    print(f"   {FACTOR_COLUMNS_TO_REGISTER}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
