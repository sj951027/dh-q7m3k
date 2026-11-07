# -*- coding: utf-8 -*-
"""업종 캐시 날짜별 스냅샷 + 업종 낙폭(표시 전용) — 2026-11-08 (CHECK_20261108 §5 결정 1·2)

하는 일(둘 다 비치명 · 점수·게이트·판정·선정 무접촉):
  (1) sector_cache.json(저장소 루트, 현재 분류만 — 시점 이력 없음) 을
      ../dh-q7m3k-data/sector_snapshots/sector_cache_YYYYMMDD.json 으로 복사.
      날짜 = daily_ohlcv 의 마지막 거래일(배치에서는 그날). 같은 날 재실행이면 덮어씀.
      내용이 전날과 같아도 저장 — 목적은 '그날 무슨 분류를 썼나' 를 남기는 것(업종 연구의 생존·재분류 편향 제거, 2027~).
  (2) 업종 동일가중 지수의 20·60거래일 고점 대비 낙폭 → docs/sector_dd.json.
      정의는 research/SECTOR_DRAWDOWN_20261108.md §1 과 같다:
        업종 = sector_cache 의 현재 분류 · 지수 = 구성 종목 일간 수익률(change_pct) 동일가중 평균의 누적(종목 ≥ 10 인 날만)
        dd20 = 당일 지수 ÷ 직전 20거래일(당일 포함) 최고 − 1 (dd60 도 같은 식). 시장 구분 없이 한 업종 한 지수.
      화면(filter.html·lowvol.html)은 이 값을 업종 옆에 '사실' 로만 보인다 — 경고·위험 아님, 향후 수익 미확인
      (실측 2026-06~09: 깊은 업종(dd20 ≤ −20)의 v30 추천이 나머지보다 나쁘지 않았음, 차이 구간이 0 을 걸침).
실행: python build_sector_dd.py [--no-snapshot] [--out docs/sector_dd.json]   (DB 는 읽기 전용)
"""
import argparse, json, shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path

import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
OHLCV_DB = HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"
SNAP_DIR = HERE / ".." / "dh-q7m3k-data" / "sector_snapshots"
CACHE = HERE / "sector_cache.json"
OUT = HERE / "docs" / "sector_dd.json"
MIN_MEMBERS = 10          # 연구 정의: 종목 ≥ 10 인 날만 지수 계산
LOAD_DAYS = 90            # 60일 고점 + 여유


def load_returns(n_days=LOAD_DAYS):
    con = sqlite3.connect(f"file:{OHLCV_DB}?mode=ro", uri=True)
    try:
        dates = [r[0] for r in con.execute(
            "SELECT DISTINCT date FROM daily_ohlcv ORDER BY date DESC LIMIT ?", (n_days,))]
        if not dates:
            return pd.DataFrame(), None
        d0 = min(dates)
        df = pd.read_sql("SELECT ticker, date, change_pct FROM daily_ohlcv WHERE date >= ? AND change_pct IS NOT NULL",
                         con, params=(d0,))
    finally:
        con.close()
    return df, max(dates)


def sector_drawdowns(df, cache):
    """업종별 {dd20, dd60, n(오늘 구성 종목 수)} — 동일가중 일수익 누적 지수의 고점 대비."""
    df = df[df.ticker.isin(cache.keys())].copy()
    df["sector"] = df.ticker.map(cache)
    out = {}
    for sec, g in df.groupby("sector"):
        daily = g.groupby("date").change_pct.agg(["mean", "count"]).sort_index()
        daily = daily[daily["count"] >= MIN_MEMBERS]
        if len(daily) < 20:
            continue
        idx = (1.0 + daily["mean"]).cumprod()
        last = idx.iloc[-1]
        dd20 = last / idx.iloc[-20:].max() - 1.0
        dd60 = (last / idx.iloc[-60:].max() - 1.0) if len(idx) >= 60 else None
        out[sec] = {"dd20": round(float(dd20) * 100, 1),
                    "dd60": (round(float(dd60) * 100, 1) if dd60 is not None else None),
                    "n": int(daily["count"].iloc[-1]),
                    "last_date": str(daily.index[-1])}
    return out


def snapshot(asof):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    dst = SNAP_DIR / f"sector_cache_{asof}.json"
    shutil.copyfile(CACHE, dst)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
        df, asof = load_returns()
        if asof is None:
            print("  ⚠️ daily_ohlcv 비어 있음 — 건너뜀"); return 0
        if not a.no_snapshot:
            dst = snapshot(asof)
            print(f"  📸 업종 캐시 스냅샷: {dst.name} ({len(cache)}종목)")
        secs = sector_drawdowns(df, cache)
        payload = {"asof": asof, "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "definition": "업종 동일가중 지수(일수익 평균 누적, 종목≥10)의 20·60거래일 고점 대비 %. 사실 표시 — 경고·위험 아님, 향후 수익 미확인(SECTOR_DRAWDOWN_20261108)",
                   "n_sectors": len(secs), "sectors": secs}
        Path(a.out).write_text(json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8")
        worst = sorted(secs.items(), key=lambda kv: kv[1]["dd20"])[:3]
        print(f"  📉 업종 낙폭 {len(secs)}개 업종 · 기준일 {asof} → {Path(a.out).name} · 20일 고점 대비 가장 깊은 3: "
              + " · ".join(f"{k} {v['dd20']:+.1f}%" for k, v in worst))
        return 0
    except Exception as e:                       # 비치명: 표시 자료라 배치를 세우지 않는다
        print(f"  ⚠️ build_sector_dd 실패(비치명): {type(e).__name__}: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
