# -*- coding: utf-8 -*-
"""연구용 — 코스피·코스닥 지수의 긴 이력을 한 번 받아 CSV 로 둔다 (2026-10-12 · 사용자 승인 · 운영 DB 미접촉)

왜: 보유 비중 조절 규칙(research/exposure_rules_20261011.py)을 3년이 아니라 20년 넘는 지수로 다시 보려고.
무엇: FinanceDataReader 로 KS11·KQ11 일별 종가(2000-01-04~). 운영의 market_series.py 와 같은 소스·같은 코드.
저장: research/data_index_long_20261012.csv (date, KOSPI, KOSDAQ). ohlcv.db 에는 쓰지 않는다.
주의: FDR 지수는 2026-09-17 뒤로 갱신이 멈춘 적이 있다(10/05 발견). 받은 뒤 운영 market_daily 와 겹치는 구간을 대조하고, 최근 구간은 운영 값으로 잇는다.
사용: python research/fetch_index_long_20261012.py
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "data_index_long_20261012.csv"
OHLCV = HERE.parent.parent / "dh-q7m3k-data" / "ohlcv.db"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import FinanceDataReader as fdr
    cols = {}
    for name, code in (("KOSPI", "KS11"), ("KOSDAQ", "KQ11")):
        df = fdr.DataReader(code, "2000-01-01")
        s = df["Close"].dropna()
        s.index = pd.to_datetime(s.index).strftime("%Y%m%d")
        cols[name] = s
        print(f"  {name}({code}): {len(s)}행 · {s.index[0]} ~ {s.index[-1]}")
    long = pd.DataFrame(cols).sort_index()
    con = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    md = pd.read_sql("SELECT series, date, close FROM market_daily WHERE series IN ('KOSPI','KOSDAQ')", con).pivot(index="date", columns="series", values="close")
    con.close()
    both = long.index.intersection(md.index)
    for name in ("KOSPI", "KOSDAQ"):
        d = (long.loc[both, name] / md.loc[both, name] - 1).abs().dropna()
        print(f"  {name}: 운영 market_daily 와 겹치는 {len(d)}일 · 종가 차이 최대 {d.max():.4%} · 0.1% 넘게 다른 날 {(d > 0.001).sum()}")
    # 겹치는 구간과 그 뒤는 운영 값이 정본(FDR 가 멈춘 구간 보정)
    merged = long[long.index < md.index[0]]
    merged = pd.concat([merged, md[["KOSPI", "KOSDAQ"]]]).sort_index()
    merged.index.name = "date"
    merged.to_csv(OUT, encoding="utf-8")
    print(f"저장: {OUT} · {len(merged)}행 · {merged.index[0]} ~ {merged.index[-1]} · 빈 칸 KOSPI {merged.KOSPI.isna().sum()} / KOSDAQ {merged.KOSDAQ.isna().sum()}")
    r = merged.pct_change()
    print("  하루 변화 절댓값 최대:", {k: f"{v:.1%}" for k, v in r.abs().max().items()}, "· 이음매(", md.index[0], ") 하루 변화:", {k: f"{r.loc[md.index[0], k]:+.2%}" for k in ("KOSPI", "KOSDAQ")})


if __name__ == "__main__":
    main()
