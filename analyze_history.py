#!/usr/bin/env python3
"""
[V2.6] 누적 데이터 분석 예시
============================
history.db에서 시계열 분석을 하는 SQL/pandas 예시 모음.

[실행]
    python analyze_history.py
"""

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path("history.db")


def show(title: str, df: pd.DataFrame, n: int = 10):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")
    if df.empty:
        print("  (데이터 없음)")
        return
    print(df.head(n).to_string(index=False))


def main():
    if not DB_PATH.exists():
        print(f"❌ {DB_PATH}가 없습니다. accumulate_history.py를 먼저 실행하세요.")
        return

    conn = sqlite3.connect(DB_PATH)

    # 1) 전체 실행 이력 (시장 레짐 변화)
    df = pd.read_sql(
        """
        SELECT run_id, market_regime, regime_score, usdkrw,
               foreign_kospi_5d_억, stage1_count
        FROM runs
        ORDER BY run_id DESC
        """,
        conn,
    )
    show("📅 일별 시장 레짐 변화 (최근 10일)", df)

    # 2) 최신 실행 기준 final_score TOP 종목
    df = pd.read_sql(
        """
        SELECT ticker, name, final_score, stock_score, q_basis
        FROM stage3_final
        WHERE run_id = (SELECT MAX(run_id) FROM stage3_final)
        ORDER BY final_score DESC
        LIMIT 20
        """,
        conn,
    )
    show("🎯 최신 실행 TOP 20", df)

    # 3) 자주 등장한 종목 (지난 30일간)
    df = pd.read_sql(
        """
        SELECT name, ticker,
               COUNT(*) AS appearances,
               ROUND(AVG(final_score), 1) AS avg_score,
               MAX(final_score) AS max_score
        FROM stage3_final
        WHERE run_id >= strftime('%Y%m%d', date('now', '-30 days'))
        GROUP BY ticker, name
        HAVING appearances >= 3
        ORDER BY appearances DESC, avg_score DESC
        LIMIT 20
        """,
        conn,
    )
    show("🔁 최근 30일간 3회 이상 등장한 단골 종목", df)

    # 4) 특정 종목 점수 추이 (예: 첫 번째 종목)
    df_any = pd.read_sql(
        "SELECT DISTINCT ticker, name FROM stage3_final LIMIT 1", conn
    )
    if not df_any.empty:
        sample_ticker = df_any.iloc[0]["ticker"]
        sample_name = df_any.iloc[0]["name"]
        df = pd.read_sql(
            """
            SELECT run_id, final_score, stock_score, q_basis
            FROM stage3_final
            WHERE ticker = ?
            ORDER BY run_id DESC
            LIMIT 30
            """,
            conn,
            params=(sample_ticker,),
        )
        show(f"📈 {sample_name}({sample_ticker}) 점수 추이", df)

    # 5) 점수대별 분포 (최신 회차)
    df = pd.read_sql(
        """
        SELECT
          CASE
            WHEN final_score >= 80 THEN '80+'
            WHEN final_score >= 70 THEN '70-79'
            WHEN final_score >= 60 THEN '60-69'
            WHEN final_score >= 50 THEN '50-59'
            ELSE '<50'
          END AS score_band,
          COUNT(*) AS count
        FROM stage3_final
        WHERE run_id = (SELECT MAX(run_id) FROM stage3_final)
        GROUP BY score_band
        ORDER BY score_band DESC
        """,
        conn,
    )
    show("📊 최신 회차 점수 분포", df)

    conn.close()
    print(f"\n{'='*70}")
    print("  💡 더 많은 분석은 직접 SQL을 작성하거나 pandas로 가공하세요.")
    print(f"  예: df = pd.read_sql('SELECT ...', sqlite3.connect('{DB_PATH}'))")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
