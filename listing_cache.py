# -*- coding: utf-8 -*-
"""
listing_cache.py — FDR StockListing 예비 캐시 (2026-09-08 사건 대응)
=====================================================================
왜: 2026-09-08 20:10 `FinanceDataReader.StockListing('KRX'/'KOSPI'/'KOSDAQ')` 이 HTTP 404 를 내자
    universe_ohlcv(시세 수집)·스크리너 유니버스·대형 트랙 유니버스가 전부 무너져 그날 측정이 통째로 날아갔다
    (stage1 75/20행 → 완전성 게이트 배포 보류, lowvol/wu 적재 0, 9/08 시세 미수집).
    상장 목록은 하루 사이에 거의 안 바뀌므로 **성공한 날의 목록을 저장해 두고, 실패한 날엔 그걸 쓴다.**

동작:
  save(market, rows)  성공 시 저장 — rows: [{code, name, market, shares, marcap, sector}] (없는 값은 None)
  load(market)        → (rows, saved_at) 또는 (None, None). market: 'KRX'(전체) | 'KOSPI' | 'KOSDAQ'
  seed_from_db()      캐시가 없을 때 1회 — ohlcv.db 최신일(종목·시장·주식수·종가) + history.db 이름 + sector_cache.json 으로 만든다.

파일: ../dh-q7m3k-data/listing_cache.json (레포 밖, raw 데이터 격리 원칙과 동일). 형식:
  {"saved_at": "YYYY-MM-DD HH:MM:SS", "source": "fdr"|"seed", "rows": [...]}   — 시장별 파일이 아니라 KRX 전체 1개.
정상인 날엔 save() 한 줄만 더 도는 것이라 산출 0-diff. 실패한 날에만 load() 경로를 탄다.
"""
import json
import os
import sqlite3
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DH_DATA_DIR", os.path.join(HERE, "..", "dh-q7m3k-data"))
CACHE_PATH = os.environ.get("LISTING_CACHE", os.path.join(DATA_DIR, "listing_cache.json"))
OHLCV_DB = os.environ.get("OHLCV_DB", os.path.join(DATA_DIR, "ohlcv.db"))
HISTORY_DB = os.path.join(HERE, "history.db")
SECTOR_CACHE = os.path.join(HERE, "sector_cache.json")

_FIELDS = ("code", "name", "market", "shares", "marcap", "sector")


def _norm(r):
    d = {k: r.get(k) for k in _FIELDS}
    d["code"] = str(d["code"] or "").strip().zfill(6)
    d["market"] = str(d["market"] or "").strip().upper()
    d["name"] = (str(d["name"]).strip() if d.get("name") is not None else "") or ""
    for k in ("shares", "marcap"):
        try:
            d[k] = int(float(d[k])) if d[k] is not None and d[k] == d[k] else None
        except Exception:
            d[k] = None
    d["sector"] = (str(d["sector"]).strip() if d.get("sector") else "") or ""
    return d


def save(market, rows, source="fdr"):
    """성공한 목록을 저장. market='KRX' 면 전체 교체, 'KOSPI'/'KOSDAQ' 면 그 시장 행만 교체(다른 시장 행 보존).
    실패해도 예외 없음(비치명)."""
    try:
        rows = [_norm(r) for r in rows if str(r.get("code", "")).strip()]
        if len(rows) < 100:          # 비정상 목록은 저장 안 함(빈 캐시로 덮어쓰기 방지)
            return False
        market = str(market).upper()
        if market == "KRX":
            merged = rows
        else:
            old, _ = load("KRX")
            keep = [r for r in (old or []) if r["market"] != market]
            merged = keep + [dict(r, market=market) for r in rows]
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "source": source, "rows": merged}, f, ensure_ascii=False)
        os.replace(tmp, CACHE_PATH)
        return True
    except Exception as e:
        print(f"   ⚠️ listing_cache 저장 실패(비치명): {e}")
        return False


def load(market="KRX"):
    """→ (rows, saved_at). 없으면 (None, None)."""
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        rows = [_norm(r) for r in d.get("rows", [])]
        market = str(market).upper()
        if market != "KRX":
            rows = [r for r in rows if r["market"] == market]
        return (rows if rows else None), d.get("saved_at")
    except Exception:
        return None, None


def seed_from_db(force=False):
    """캐시가 없을 때 DB 로 만든다(네트워크 0). 이름은 history.db(stage1_oversold 최신·large_universe)에서,
    업종은 sector_cache.json 에서. 이름 없는 종목은 '' (스크리너의 금융/리츠 이름 필터는 그 종목엔 안 걸림)."""
    if not force and load("KRX")[0]:
        return 0
    con = sqlite3.connect(f"file:{OHLCV_DB}?mode=ro", uri=True)
    last = con.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()[0]
    rows = con.execute(
        "SELECT ticker, market, shares, close FROM daily_ohlcv WHERE date=?", (last,)).fetchall()
    con.close()
    names = {}
    try:
        h = sqlite3.connect(f"file:{HISTORY_DB}?mode=ro", uri=True)
        for t, n in h.execute("SELECT ticker, name FROM large_universe WHERE name IS NOT NULL AND name<>''"):
            names[str(t).zfill(6)] = n
        for t, n in h.execute(
                "SELECT ticker, name FROM stage1_oversold WHERE name IS NOT NULL AND name<>'' "
                "ORDER BY run_id"):          # 뒤에 올수록 최신 → 최신 이름이 남음
            names[str(t).zfill(6)] = n
        h.close()
    except Exception as e:
        print(f"   ⚠️ 이름 소스(history.db) 읽기 실패(비치명): {e}")
    sectors = {}
    try:
        with open(SECTOR_CACHE, encoding="utf-8") as f:
            sectors = {str(k).zfill(6): str(v) for k, v in json.load(f).items()}
    except Exception:
        pass
    out = []
    for t, mkt, shares, close in rows:
        code = str(t).zfill(6)
        marcap = int(float(shares) * float(close)) if shares and close else None
        out.append({"code": code, "name": names.get(code, ""), "market": mkt,
                    "shares": shares, "marcap": marcap, "sector": sectors.get(code, "")})
    ok = save("KRX", out, source=f"seed:{last}")
    print(f"   💾 listing_cache 시드 — 기준일 {last}, {len(out)}종목, 이름 {sum(1 for r in out if r['name'])}개"
          + ("" if ok else " (저장 실패)"))
    return len(out) if ok else 0


if __name__ == "__main__":
    import sys
    if "--seed" in sys.argv:
        seed_from_db(force="--force" in sys.argv)
    rows, at = load("KRX")
    print(f"listing_cache: {CACHE_PATH} · {len(rows) if rows else 0}종목 · saved_at {at}")
