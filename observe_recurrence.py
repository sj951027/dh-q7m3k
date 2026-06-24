# -*- coding: utf-8 -*-
"""
observe_recurrence.py — '관측 전용' 과매도 재출현/신규성 컬럼을 history.db(stage3_final)에 배선
==============================================================================
목적(사용자 가설): "한 번 BUY로 떴다가 그 뒤에도 계속 스크리너에 나오는 종목은
      만성 하락(밸류트랩)에 가깝고, 딱 한 번 뜨고 사라지는 '신선한 이탈'이 더 좋다"를
      *검정 가능한 피처*로 만든다. 전부 **가중치 0 관측값** — 점수식(final_score / final_score_v3)
      에는 절대 안 들어간다. validate_scores 의 FACTOR_COLUMNS 에 등록 → IC 하니스가 자동 측정.
      ⚠️ 사용자 아이디어 발(發) post-hoc → §11 판정은 forward-only(등록 이후 OOS만).

정의(동결 — 시작하면 변경 금지):
  타임라인 = filter_active_runs(주말/정적/부분실행 제거) ∩ stage3_final 보유 run, 시간순.
    * v3_backtest 의 활성런 정의를 그대로 재사용 → 재출현 카운트가 IC 포워드리턴과 같은 시계열을 본다.
    * 주말/정적 중복 run 이 가짜 +1 로 잡히는 것을 차단(부분실행일도 제외).
  각 (run R, ticker∈stage3_final[R]) 에 대해 R '직전' 활성런들만 보고(=PIT, R 자신·미래 제외):
    os_count_20d : 직전 LOOKBACK(20) 활성런 중 ticker 가 stage3_final 에 있었던 run 수 (0~20).  [만성도]
    os_streak    : R 직전부터 '연속'으로 stage3_final 에 있었던 활성런 수 (0~).               [연속 갈림]
    os_is_new20  : os_count_20d==0 → 1 (최근 20활성런간 첫 등장 = 신규 진입자), 아니면 0.       [신선도]
  부호는 데이터에 맡긴다. (사용자 가설이면 os_count_20d/os_streak 의 IC 가 음(-), os_is_new20 이 양(+).
   반대일 수도 있다 — '오래 과매도 = 더 깊은 저평가 = 막상 돌면 더 큼'. 데이터가 정한다.)

안전:
  * 점수 미사용(v3_rescore / v3_merge 가 이 컬럼들을 읽지 않음 → 0-diff).
  * 카운트는 항상 정의됨(직전이 없으면 0) → MIN_OBS 불필요, 전 run 채움(realized_vol 보다 커버리지 넓음).
  * 재실행 안전(idempotent): 컬럼은 없을 때만 ALTER, 값은 (market,run_id,ticker) 로 UPDATE.
    trailing(직전만)이라 과거 run 값은 새 run 이 와도 불변 → 기본은 '미채움 run' 만 증분.
    (단 filter_active_runs 의 floor 가 새 run 으로 미세 이동해 경계 run 의 활성여부가 바뀌면
     과거 카운트가 달라질 수 있음 — observe_vol 과 동일 한계. 주기적으로 --full 권장.)

사용:
    python observe_recurrence.py            # 미채움 run 만 증분(파이프라인 일일)
    python observe_recurrence.py --full     # 전체 run 재계산
    python observe_recurrence.py --db history.db
"""
import argparse
import sqlite3
from collections import defaultdict

import pandas as pd

import v3_backtest as bt   # price_panel, filter_active_runs 재사용(동일 활성런 정의)

DB_DEFAULT = "history.db"
LOOKBACK = 20             # trailing 활성런 수(≈1개월, h=20d 호라이즌과 정렬). 동결.
COLS = ["os_count_20d", "os_streak", "os_is_new20"]


def compute(db_path):
    """모든 (활성 ∩ stage3) run R 의 종목별 직전-출현 카운트/연속/신규 플래그."""
    # 1) 활성런 타임라인(stage1 가격 패널 기반 — v3_backtest 와 동일)
    panel, runs, _ = bt.price_panel(db_path)
    active = [str(r) for r in bt.filter_active_runs(panel, runs)]

    # 2) stage3_final 멤버십(= '스크리너에 나온' 종목)
    con = sqlite3.connect(db_path)
    m = pd.read_sql("SELECT DISTINCT market, run_id, ticker FROM stage3_final", con)
    con.close()
    m["run_id"] = m["run_id"].astype(str)
    s3_runs = set(m["run_id"])

    timeline = [r for r in active if r in s3_runs]          # 활성 ∩ stage3, 시간순
    idx_of = {r: i for i, r in enumerate(timeline)}
    tk_mkt = m.drop_duplicates("ticker").set_index("ticker")["market"]

    # 3) ticker -> 등장한 타임라인 인덱스 집합
    appear = defaultdict(set)
    for r, g in m.groupby("run_id"):
        if r in idx_of:
            i = idx_of[r]
            for tk in g["ticker"]:
                appear[tk].add(i)

    # 4) 각 (ticker, 등장 run) 에서 '직전' 윈도우만 보고 카운트/연속/신규
    recs = []
    for tk, idxs in appear.items():
        for i in sorted(idxs):
            lo = i - LOOKBACK
            count = sum(1 for j in idxs if lo <= j <= i - 1)   # R 제외(직전만)
            st = 0                                             # 직전부터 연속
            j = i - 1
            while j in idxs:
                st += 1
                j -= 1
            recs.append((timeline[i], tk, count, st, 1 if count == 0 else 0))

    df = pd.DataFrame(recs, columns=["run_id", "ticker"] + COLS)
    df["market"] = df["ticker"].map(tk_mkt)                  # idx_stage3_mrt(market,run_id,ticker)
    return df.dropna(subset=["market"])


def ensure_columns(con):
    cur = con.cursor()
    existing = {r[1] for r in cur.execute('PRAGMA table_info("stage3_final")')}
    for c in COLS:
        if c not in existing:
            cur.execute(f'ALTER TABLE "stage3_final" ADD COLUMN "{c}" INTEGER')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_stage3_mrt '
                'ON "stage3_final"(market, run_id, ticker)')
    con.commit()


def filled_runs(con):
    """os_count_20d 가 non-null 인 행이 1개라도 있는 run = '처리됨'(0 은 유효값이라 NOT NULL 로 판정)."""
    cur = con.cursor()
    rows = cur.execute(
        'SELECT run_id, SUM(os_count_20d IS NOT NULL) '
        'FROM "stage3_final" GROUP BY run_id').fetchall()
    return {str(r[0]) for r in rows if (r[1] or 0) > 0}


def update(con, df):
    if df.empty:
        return 0
    rows = [(int(c), int(s), int(n), str(mk), str(rid), str(tk))
            for mk, rid, tk, c, s, n in zip(
                df["market"], df["run_id"], df["ticker"],
                df["os_count_20d"], df["os_streak"], df["os_is_new20"])
            if pd.notna(mk)]
    cur = con.cursor()
    cur.executemany(
        'UPDATE "stage3_final" SET os_count_20d=?, os_streak=?, os_is_new20=? '
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
    ensure_columns(con)
    done = set() if a.full else filled_runs(con)
    df = compute(a.db)
    if not a.full and done:
        df = df[~df["run_id"].isin(done)]
    n = update(con, df)
    con.close()
    print(f"recurrence UPDATE: {n}행 "
          f"(LOOKBACK={LOOKBACK} 활성런 · {COLS} · {'전체' if a.full else '증분'})")


if __name__ == "__main__":
    main()
