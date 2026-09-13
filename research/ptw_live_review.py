# -*- coding: utf-8 -*-
"""ptw_live_review.py — 실거래 원장(Position Tracker) 정기 점검 (읽기 전용·관측)

왜: 그림자 포트(권고를 기계적으로 따랐을 때)는 있는데, **실제로 사고판 결과**를 같은 잣대로
재는 도구가 없었다. 2026-09-12 세션에서 1회성으로 계산해 보니 판단에 직접 쓸 값이 나와서
스크립트로 고정한다. 월 1회 실행을 권장(국면이 바뀔 때 성적 변화를 빨리 보려는 것).

무엇을:
  ① 청산 거래: 같은 보유구간 지수 대비 초과수익(%p) — 전략별 평균·중앙·승률·부트스트랩 CI
  ② 보유 중 종목: 평가손익(미실현) — '청산한 것만 세는' 편향을 같이 보여준다
  ③ ①+② 합산 관점: 실현 금액 vs 미실현 금액

무엇을 하지 않나:
  - 판정하지 않는다. §11(팩터 유효성)도, 운용 채택 기준도 여기서 정하지 않는다. 관측 기록일 뿐.
  - 어떤 DB에도 쓰지 않는다. history.db·ohlcv.db 는 mode=ro, PTW 스냅샷은 CSV 읽기만.

입력(PTW 웹에서 내보낸 CSV — research/ 에 날짜별로 둔다):
  research/ptw_closed_YYYYMMDD.csv     code,strategy,first_buy,closed_at,realized_pnl,qty,buy_avg,sell_avg,ret_pct
  research/ptw_positions_YYYYMMDD.csv  code,name,strategy,first_buy,qty,avg,cur,pnl,rs,tdays,signal,...
  (없으면 가장 최근 날짜 파일을 자동으로 찾는다)

실행:
  python research/ptw_live_review.py                 # 최신 스냅샷
  python research/ptw_live_review.py --asof 20260905
  python research/ptw_live_review.py --bench index   # 잣대: 지수(기본) | median(유니버스 중앙값)
"""
import argparse
import glob
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OHLCV = REPO / ".." / "dh-q7m3k-data" / "ohlcv.db"
BOOT = 4000
RNG = np.random.default_rng(20260912)      # 재현 가능한 부트스트랩


def _latest(kind, asof=None):
    if asof:
        p = HERE / f"ptw_{kind}_{asof}.csv"
        return p if p.exists() else None
    files = sorted(glob.glob(str(HERE / f"ptw_{kind}_*.csv")))
    return Path(files[-1]) if files else None


def _year_of(path):
    m = re.search(r"_(\d{4})\d{4}\.csv$", str(path))
    return m.group(1) if m else str(datetime.now().year)


def _to_date(v, year):
    """PTW 스냅샷은 'MM-DD' 또는 'YYYY-MM-DD' 둘 다 나온다 → 'YYYYMMDD'."""
    s = str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s.replace("-", "")
    if re.fullmatch(r"\d{2}-\d{2}", s):
        return year + s.replace("-", "")
    return None


def _load_market():
    con = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    md = pd.read_sql("SELECT series, date, close FROM market_daily "
                     "WHERE series IN ('KOSPI','KOSDAQ')", con)
    last = con.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()[0]
    mk = pd.read_sql("SELECT DISTINCT ticker, market FROM daily_ohlcv WHERE date=?",
                     con, params=(last,))
    px = pd.read_sql("SELECT ticker, date, close FROM daily_ohlcv WHERE close IS NOT NULL", con)
    con.close()
    mk["ticker"] = mk.ticker.astype(str).str.zfill(6)
    px["ticker"] = px.ticker.astype(str).str.zfill(6)
    idx = {s: g.set_index("date").close.sort_index() for s, g in md.groupby("series")}
    return idx, dict(zip(mk.ticker, mk.market)), px


def _idx_ret(idx, series, d0, d1):
    s = idx.get(series)
    if s is None or d0 is None or d1 is None:
        return np.nan
    a = s[s.index <= d0]
    b = s[s.index <= d1]
    if a.empty or b.empty:
        return np.nan
    return (b.iloc[-1] / a.iloc[-1] - 1) * 100


def _median_ret(px, market_of, series, d0, d1):
    """같은 시장 전종목 중앙값 수익률(%) — 스크리너 판정과 같은 잣대."""
    sub = px[px.date.isin([d0, d1])]
    if sub.empty:
        return np.nan
    w = sub.pivot_table(index="ticker", columns="date", values="close")
    if d0 not in w.columns or d1 not in w.columns:
        return np.nan
    w = w.dropna()
    w = w[[market_of.get(t) == series for t in w.index]]
    if w.empty:
        return np.nan
    return float(((w[d1] / w[d0] - 1) * 100).median())


def _ci(x):
    if len(x) < 4:
        return (np.nan, np.nan)
    bs = [np.mean(RNG.choice(x, len(x), replace=True)) for _ in range(BOOT)]
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def main():
    ap = argparse.ArgumentParser(description="실거래 원장 정기 점검(관측 전용)")
    ap.add_argument("--asof", default=None, help="스냅샷 날짜 YYYYMMDD (기본: 최신)")
    ap.add_argument("--bench", choices=["index", "median"], default="index",
                    help="잣대: index(시장지수, 기본) | median(같은 시장 전종목 중앙값)")
    args = ap.parse_args()

    fc = _latest("closed", args.asof)
    fp = _latest("positions", args.asof)
    if fc is None:
        print("❌ research/ptw_closed_YYYYMMDD.csv 가 없습니다 (PTW 웹에서 내보내 두세요).")
        return 1
    year = _year_of(fc)
    idx, market_of, px = _load_market()

    c = pd.read_csv(fc, dtype={"code": str})
    c["code"] = c.code.str.zfill(6)
    c["d0"] = [_to_date(v, year) for v in c.first_buy]
    c["d1"] = [_to_date(v, year) for v in c.closed_at]
    c["market"] = [market_of.get(t, "KOSPI") for t in c.code]
    if args.bench == "index":
        c["bench"] = [_idx_ret(idx, m, a, b) for m, a, b in zip(c.market, c.d0, c.d1)]
    else:
        c["bench"] = [_median_ret(px, market_of, m, a, b) for m, a, b in zip(c.market, c.d0, c.d1)]
    c["excess"] = c.ret_pct - c.bench
    ok = c.dropna(subset=["excess"])

    print("=" * 70)
    print(f"📒 실거래 원장 점검 — {fc.name} · 잣대 {args.bench} · 청산 {len(c)}건(계산 가능 {len(ok)}건)")
    print("   관측 기록입니다. 판정(§11)도, 운용 채택 결정도 아닙니다.")
    print("=" * 70)
    rows = []
    for st, g in ok.groupby("strategy"):
        lo, hi = _ci(g.excess.values)
        rows.append((st, len(g), g.ret_pct.mean(), g.bench.mean(), g.excess.mean(),
                     g.excess.median(), 100 * (g.excess > 0).mean(), lo, hi,
                     g.realized_pnl.sum() if "realized_pnl" in g else np.nan))
    t = pd.DataFrame(rows, columns=["전략", "n", "수익%", "잣대%", "초과%p", "초과중앙",
                                    "초과승률", "CI저", "CI고", "실현손익"])
    t = t.sort_values("n", ascending=False)
    print(t.round(2).to_string(index=False))
    print("\n   ※ n<10 이면 평균은 흔들립니다. CI 가 0을 걸치면 '차이 있다'고 말하지 않습니다.")

    if fp and fp.exists():
        p = pd.read_csv(fp, dtype={"code": str})
        if "strategy" in p.columns:
            gp = p.groupby("strategy").agg(보유=("code", "size"), 평가손익=("pnl", "mean"),
                                           금액=("pnl_amt", "sum") if "pnl_amt" in p.columns
                                           else ("pnl", "sum"))
            print(f"\n== 보유 중({fp.name}) — 청산분만 보면 생기는 치우침 점검")
            print(gp.round(2).to_string())
            real = ok.realized_pnl.sum() if "realized_pnl" in ok else np.nan
            unre = p["pnl_amt"].sum() if "pnl_amt" in p.columns else np.nan
            if pd.notna(real) and pd.notna(unre):
                print(f"   실현 {real:+,.0f}원 · 미실현 {unre:+,.0f}원 · 합 {real + unre:+,.0f}원")

    print("\n== 보유기간(달력일) — 운영 권고는 40거래일(≈58일)")
    hold = []
    for a, b in zip(ok.d0, ok.d1):
        try:
            hold.append((datetime.strptime(b, "%Y%m%d") - datetime.strptime(a, "%Y%m%d")).days)
        except Exception:
            pass
    if hold:
        h = pd.Series(hold)
        print(f"   중앙 {h.median():.0f}일 · 평균 {h.mean():.0f}일 · 40거래일 이상 보유 비율 "
              f"{100 * (h >= 58).mean():.0f}%")
    print("\n다음: 국면이 바뀌면(하락·횡보) 같은 표를 다시 뽑아 비교하세요. 한 국면 성적은 근거가 약합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
