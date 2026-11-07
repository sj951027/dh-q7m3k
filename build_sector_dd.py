# -*- coding: utf-8 -*-
"""업종 캐시 날짜별 스냅샷 + 업종 낙폭(표시 전용) — 2026-11-08 (CHECK_20261108 §5 결정 1·2)

하는 일(둘 다 비치명 · 점수·게이트·판정·선정 무접촉):
  (1) sector_cache.json(저장소 루트, 현재 분류만 — 시점 이력 없음) 을
      ../dh-q7m3k-data/sector_snapshots/sector_cache_YYYYMMDD.json 으로 복사.
      날짜 = daily_ohlcv 의 마지막 거래일(= 시세 기준일, 관측 시각 아님). 같은 날 재실행: 내용이 같으면 그대로(원본 보존),
      다르면 _v2, _v3… 로 추가 저장. index.jsonl 에 관측 시각·내용 해시(Codex 11/8 검토 ⑤).
      내용이 전날과 같아도 저장 — 목적은 '그날 무슨 분류를 썼나' 를 남기는 것(업종 연구의 생존·재분류 편향 제거, 2027~).
  (2) 업종 동일가중 지수의 20·60거래일 고점 대비 낙폭 → docs/sector_dd.json.
      정의는 research/SECTOR_DRAWDOWN_20261108.md §1 과 같다:
        업종 = sector_cache 의 현재 분류 · 지수 = 구성 종목 일간 수익률(change_pct) 동일가중 평균의 누적(종목 ≥ 10 인 날만)
        dd20 = 당일 지수 ÷ 직전 20거래일(당일 포함) 최고 − 1 (dd60 도 같은 식). 시장 구분 없이 한 업종 한 지수.
        창은 본표 거래일 달력 기준 — 창 안에 구성 종목 < 10 인 날이 있으면 값 없음(Codex 11/8 검토 ②: 결측일을 빼고 당겨 채우지 않는다).
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
    return df, max(dates), sorted(dates)


def sector_drawdowns(df, cache, calendar):
    """업종별 {dd20, dd60, n, last_date} — 동일가중 일수익 누적 지수의 고점 대비.
    [Codex 11/8 검토 ②⑥] 창은 '본표 거래일 달력' 기준 고정: 마지막 20(60)거래일 안에 구성 종목 < 10 인 날이 하나라도 있으면
    그 낙폭은 None(배지 없음) — 결측일을 빼고 당겨 채운 값을 20·60거래일이라 부르지 않는다. 마지막 날에 자료가 없는 업종도 같은 이유로 None."""
    df = df[df.ticker.isin(cache.keys())].copy()
    df["sector"] = df.ticker.map(cache)
    cal = list(calendar)                      # 오름차순 거래일 전체(최근 LOAD_DAYS)
    out, stale = {}, []
    for sec, g in df.groupby("sector"):
        daily = g.groupby("date").change_pct.agg(["mean", "count"]).reindex(cal)
        ok = (daily["count"].fillna(0) >= MIN_MEMBERS)
        if not bool(ok.iloc[-1]):
            stale.append(sec); continue
        ret = daily["mean"].where(ok)       # 구성 부족일은 NaN
        idx = (1.0 + ret.fillna(0.0)).cumprod()

        def dd(win):
            if len(cal) < win or not bool(ok.iloc[-win:].all()):
                return None
            w = idx.iloc[-win:]
            return round(float(w.iloc[-1] / w.max() - 1.0) * 100, 1)
        d20, d60 = dd(20), dd(60)
        if d20 is None:
            stale.append(sec); continue
        out[sec] = {"dd20": d20, "dd60": d60, "n": int(daily["count"].iloc[-1]), "last_date": str(cal[-1])}
    return out, stale


def _sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def snapshot(asof, n):
    """[Codex 11/8 검토 ⑤] 같은 시세일이라도 내용이 다르면 덮어쓰지 않고 _v2, _v3… 로 보존. index.jsonl 에 관측 시각·내용 해시를 남긴다.
    주의: 파일 이름의 날짜는 '시세 기준일' 이지 관측 시각이 아니다(첫 파일 sector_cache_20261106.json 은 11/8 05:32 에 만듦)."""
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    h = _sha(CACHE)
    base = SNAP_DIR / f"sector_cache_{asof}.json"
    cands = [base] + sorted(SNAP_DIR.glob(f"sector_cache_{asof}_v*.json"))
    for c in cands:
        if c.exists() and _sha(c) == h:
            return c, False                   # 같은 내용이 이미 있음 — 원본(관측 시각) 보존
    dst = base if not base.exists() else SNAP_DIR / f"sector_cache_{asof}_v{len([c for c in cands if c.exists()]) + 1}.json"
    shutil.copyfile(CACHE, dst)
    with open(SNAP_DIR / "index.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"asof": asof, "file": dst.name, "observed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "sha256_16": h, "n": n}, ensure_ascii=False) + chr(10))
    return dst, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
        df, asof, calendar = load_returns()
        if asof is None:
            print("  ⚠️ daily_ohlcv 비어 있음 — 건너뜀"); return 0
        if not a.no_snapshot:
            dst, new = snapshot(asof, len(cache))
            print(f"  📸 업종 캐시 스냅샷: {dst.name} ({len(cache)}종목) " + ("새로 저장" if new else "같은 내용 이미 있음 — 원본 보존"))
        secs, stale = sector_drawdowns(df, cache, calendar)
        payload = {"asof": asof, "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "definition": "업종 동일가중 지수(일수익 평균 누적, 종목≥10)의 20·60거래일 고점 대비 %. 사실 표시 — 경고·위험 아님, 향후 수익 미확인(SECTOR_DRAWDOWN_20261108)",
                   "window_rule": "본표 거래일 달력 기준 마지막 20(60)거래일 — 그 안에 구성 종목<10 인 날이 있으면 값 없음(배지 없음)",
                   "n_sectors": len(secs), "sectors": secs, "stale": stale}
        Path(a.out).write_text(json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8")
        worst = sorted(secs.items(), key=lambda kv: kv[1]["dd20"])[:3]
        print(f"  📉 업종 낙폭 {len(secs)}개 업종(값 없음 {len(stale)}) · 기준일 {asof} → {Path(a.out).name} · 20일 고점 대비 가장 깊은 3: "
              + " · ".join(f"{k} {v['dd20']:+.1f}%" for k, v in worst))
        return 0
    except Exception as e:                       # 비치명: 표시 자료라 배치를 세우지 않는다
        print(f"  ⚠️ build_sector_dd 실패(비치명): {type(e).__name__}: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
