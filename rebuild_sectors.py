# -*- coding: utf-8 -*-
"""
rebuild_sectors.py  (댁의 PC에서 실행 — 네트워크 + DART API 키 필요)
====================================================================
sector_cache.json 을 전 종목으로 확장한다.
기존 캐시가 쓰는 업종 버킷과 100% 같은 분류를 쓰기 위해,
diversify_picks.py 의 ksic_to_sector(KSIC 산업분류 매핑)를 그대로 재사용한다.

동작:
  1) .env 에서 DART_API_KEY 로드
  2) DART corpCode.zip 한 번 받아 (종목코드 → corp_code) 매핑 생성
  3) history.db 의 전체 유니버스 종목 중, 캐시에 없거나 '미분류'인 종목만
     DART company.json → induty_code → ksic_to_sector 로 업종 채움
  4) sector_cache.json 갱신 (기존 파일은 .bak 로 백업)

이미 제대로 분류된 종목은 건드리지 않으므로 DART 호출은 빠진 종목 수만큼만 발생.
중간에 끊겨도 캐시에 계속 저장하므로 다시 돌리면 이어서 진행된다.

실행:
    python rebuild_sectors.py
    python rebuild_sectors.py --force        # 전부 다시 조회
    python rebuild_sectors.py --limit 50     # 테스트로 50개만
"""
import argparse
import io
import json
import os
import sqlite3
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
CACHE_FILE = HERE / "sector_cache.json"
DB_FILE = HERE / "history.db"
UNKNOWN = "미분류"


def load_env(p=None):
    p = Path(p) if p else (HERE / ".env")
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        s = raw.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

# 기존 분류 로직 재사용 (버킷 이름 일치 보장)
try:
    from diversify_picks import ksic_to_sector
except Exception as e:
    raise SystemExit(f"diversify_picks.ksic_to_sector 를 불러오지 못함: {e}")


def get_corpcode_map(api_key):
    """DART corpCode.zip → {6자리 종목코드: 8자리 corp_code}."""
    url = "https://opendart.fss.or.kr/api/corpCode.xml"
    r = requests.get(url, params={"crtfc_key": api_key}, timeout=30)
    r.raise_for_status()
    # 응답이 zip 이 아니라 에러 JSON 일 수 있음
    if r.content[:2] != b"PK":
        raise SystemExit(f"corpCode 다운로드 실패(키 확인): {r.text[:200]}")
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    xml = zf.read(zf.namelist()[0]).decode("utf-8")
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    m = {}
    for node in root.iter("list"):
        stock = (node.findtext("stock_code") or "").strip()
        corp = (node.findtext("corp_code") or "").strip()
        if stock and corp:
            m[stock.zfill(6)] = corp.zfill(8)
    return m


def dart_sector(api_key, corp_code):
    """company.json → induty_code → 업종 버킷. 실패 시 None."""
    try:
        r = requests.get("https://opendart.fss.or.kr/api/company.json",
                         params={"crtfc_key": api_key, "corp_code": corp_code},
                         timeout=10)
        j = r.json()
        if j.get("status") != "000":
            return None
        return ksic_to_sector(j.get("induty_code"))
    except Exception:
        return None


def universe_tickers(db_path):
    con = sqlite3.connect(db_path)
    try:
        df = pd.read_sql("SELECT DISTINCT ticker FROM stage1_oversold", con)
    finally:
        con.close()
    return [str(t).zfill(6) for t in df["ticker"].tolist()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="이미 분류된 것도 다시 조회")
    ap.add_argument("--limit", type=int, default=0, help="테스트용 최대 조회 수(0=무제한)")
    ap.add_argument("--sleep", type=float, default=0.05, help="DART 호출 간 간격(초)")
    args = ap.parse_args()

    api_key = os.environ.get("DART_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(".env 에 DART_API_KEY 가 없습니다.")

    cache = {}
    if CACHE_FILE.exists():
        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    before_unknown = sum(1 for v in cache.values() if v == UNKNOWN)
    print(f"기존 캐시 {len(cache)}개 (미분류 {before_unknown}개)")

    tickers = universe_tickers(DB_FILE)
    print(f"유니버스 종목 {len(tickers)}개")

    # 채워야 할 대상
    todo = [t for t in tickers
            if args.force or t not in cache or cache.get(t) in (None, "", UNKNOWN)]
    if args.limit:
        todo = todo[:args.limit]
    print(f"조회 대상 {len(todo)}개  (나머지는 기존 분류 유지)")
    if not todo:
        print("채울 종목이 없습니다. 끝."); return

    print("DART corpCode 매핑 다운로드 중...")
    code_map = get_corpcode_map(api_key)
    print(f"  종목코드→corp_code 매핑 {len(code_map)}개 확보")

    # 백업
    if CACHE_FILE.exists():
        (HERE / "sector_cache.json.bak").write_text(
            CACHE_FILE.read_text(encoding="utf-8"), encoding="utf-8")

    filled = miss = 0
    for i, t in enumerate(todo, 1):
        corp = code_map.get(t)
        sec = dart_sector(api_key, corp) if corp else None
        cache[t] = sec or UNKNOWN
        if sec:
            filled += 1
        else:
            miss += 1
        if i % 100 == 0:
            print(f"  {i}/{len(todo)}  (채움 {filled}, 실패 {miss})")
            CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=0),
                                  encoding="utf-8")
        time.sleep(args.sleep)

    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=0),
                          encoding="utf-8")

    # 결과 요약: 유니버스 기준 미분류 비율
    uni_unknown = sum(1 for t in tickers if cache.get(t, UNKNOWN) == UNKNOWN)
    print("\n완료.")
    print(f"  이번에 채운 종목: {filled}개 (DART 실패/미상장 {miss}개)")
    print(f"  유니버스 미분류: {uni_unknown}/{len(tickers)} "
          f"= {uni_unknown/len(tickers):.1%}")
    print("  → 이제 v3_rescore.py 를 다시 돌리면 sector 가 채워진 채로 반영됩니다.")


if __name__ == "__main__":
    main()
