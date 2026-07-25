# -*- coding: utf-8 -*-
"""
fetch_consensus.py — 컨센서스(투자의견·목표주가·커버리지) 주간 스냅샷 (관측 전용)
================================================================================
[2026-07-25 신설] 네이버 금융 종목 메인페이지에서 투자의견 점수·목표주가를 긁어
ohlcv.db `consensus_daily` 에 스냅샷으로 적재한다. 목적은 두 가지 팩터 후보의 재료:
  ① 커버리지 유무(coverage) — 애널 커버 없는 소형주의 정보 비효율 가설
  ② 목표주가 괴리/리비전 — 추정치 변화 모멘텀 가설(스냅샷이 쌓여야 리비전 계산 가능)

규율:
  - 관측 전용. 어떤 점수식에도 넣지 않는다(검증은 §11: 사전등록 → OOS 40거래일 후).
  - 포인트-인-타임: date = 수집일. 과거 소급 생성 금지(리비전은 forward 축적으로만).
  - 주간 가드: 컨센서스는 느리게 변함 → 마지막 스냅샷 후 5일(달력일) 미만이면 스킵.
    (batch 에 매일 넣어도 실제 수집은 주 1회. --force 로 강제.)
  - 비치명: 실패해도 배치 계속. 미수집 종목은 coverage 판단에서 제외(NULL ≠ 무커버).
  - 크롤 예절: 기존 스크리너와 동일 UA·단일 스레드·sleep(기본 0.25s, 전 종목 ~11분).

사용:
  python fetch_consensus.py                  # 주간 가드 하에 전 종목 스냅샷
  python fetch_consensus.py --force          # 가드 무시하고 오늘 스냅샷
  python fetch_consensus.py --self-test 005930   # 1종목 파싱 확인(적재 없음)

⚠️ 파서 주의: 네이버 페이지 구조는 예고 없이 바뀔 수 있다. --self-test 로 먼저 확인 권장.
   구조 변경 시 PARSERS 의 정규식만 고치면 된다(적재 스키마 불변).
"""
import argparse
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
OHLCV_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))
GUARD_DAYS = 5          # 마지막 스냅샷 후 이 일수(달력일) 미만이면 스킵
SLEEP = 0.25

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
}

OPINION_LABELS = "매수|적극매수|비중확대|중립|보유|비중축소|매도"


def parse_main_page(html):
    """finance.naver.com/item/main.naver 에서 (의견점수, 의견라벨, 목표주가) 추출.
    구조가 바뀌어도 최대한 버티도록 '투자의견' 앵커 주변 텍스트에서 정규식으로 뽑는다.
    커버리지 없는 종목은 해당 블록에 'N/A' 류가 뜨거나 블록이 비어 있음 → (None,None,None)."""
    # '투자의견' 이후 600자 윈도만 본다(페이지 다른 곳의 숫자 오인 방지)
    m = re.search(r"투자의견", html)
    if not m:
        return None, None, None
    win = html[m.start(): m.start() + 600]
    score = label = target = None
    sm = re.search(r"([0-9]\.[0-9]{2})\s*(?:<[^>]*>)*\s*(" + OPINION_LABELS + ")", win)
    if sm:
        score = float(sm.group(1))
        label = sm.group(2)
    # 목표주가: 의견 뒤에 나오는 첫 콤마숫자(4자리 이상)
    tm = re.search(r"목표주가", win)
    tw = win[tm.start():] if tm else win
    pm = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})", tw)
    if pm:
        target = float(pm.group(1).replace(",", ""))
    return score, label, target


def fetch_one(ticker, session):
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    r = session.get(url, headers=HEADERS, timeout=10)
    r.encoding = r.apparent_encoding or "euc-kr"
    return parse_main_page(r.text)


def load_universe(con):
    last = con.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()[0]
    rows = con.execute(
        "SELECT DISTINCT ticker FROM daily_ohlcv WHERE date=? AND is_suspended IS NOT 1",
        (last,)).fetchall()
    return sorted({str(r[0]) for r in rows})


def ensure_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS consensus_daily(
        date TEXT, ticker TEXT, opinion_score REAL, opinion_label TEXT,
        target_price REAL, coverage INTEGER, fetched_at TEXT,
        PRIMARY KEY(date, ticker))""")
    con.commit()


def main():
    ap = argparse.ArgumentParser(description="컨센서스 주간 스냅샷 (관측 전용)")
    ap.add_argument("--force", action="store_true", help="주간 가드 무시")
    ap.add_argument("--sleep", type=float, default=SLEEP)
    ap.add_argument("--self-test", metavar="TICKER", default=None)
    ap.add_argument("--limit", type=int, default=0, help="앞 N종목만(테스트용)")
    args = ap.parse_args()

    if args.self_test:
        s = requests.Session()
        sc, lb, tp = fetch_one(args.self_test, s)
        print(f"[self-test] {args.self_test}: 의견점수={sc} 라벨={lb} 목표주가={tp}")
        print("→ 값이 전부 None 이면 파서 수정 필요(PARSERS 정규식). 커버리지 없는 종목이면 정상.")
        return

    today = datetime.now().strftime("%Y%m%d")
    con = sqlite3.connect(OHLCV_DB)
    ensure_table(con)
    last = con.execute("SELECT MAX(date) FROM consensus_daily").fetchone()[0]
    if last and not args.force:
        gap = (datetime.strptime(today, "%Y%m%d") - datetime.strptime(last, "%Y%m%d")).days
        if gap < GUARD_DAYS:
            print(f"⏭  컨센서스 스냅샷 스킵 — 마지막 {last} 이후 {gap}일 < {GUARD_DAYS}일 (주간 가드)")
            con.close(); return

    tickers = load_universe(con)
    if args.limit:
        tickers = tickers[:args.limit]
    print(f"▶ 컨센서스 스냅샷 {today} — {len(tickers)}종목 · sleep {args.sleep}s "
          f"(예상 ~{len(tickers)*(args.sleep+0.15)/60:.0f}분)")
    s = requests.Session()
    rows, fail = [], 0
    t0 = time.time()
    for i, tk in enumerate(tickers, 1):
        try:
            sc, lb, tp = fetch_one(tk, s)
            cov = 1 if (tp is not None or sc is not None) else 0
            rows.append((today, tk, sc, lb, tp, cov,
                         datetime.now().strftime("%Y%m%d_%H%M")))
        except Exception:
            fail += 1          # 실패는 저장 안 함(NULL 오염 방지) — 다음 주 재시도
        if i % 200 == 0:
            print(f"   [{i}/{len(tickers)}] {int(time.time()-t0)}s · 수집 {len(rows)} · 실패 {fail}")
        time.sleep(args.sleep)
    con.execute("DELETE FROM consensus_daily WHERE date=?", (today,))   # 재실행 안전
    con.executemany("INSERT OR REPLACE INTO consensus_daily VALUES(?,?,?,?,?,?,?)", rows)
    con.commit()
    ncov = sum(r[5] for r in rows)
    print(f"💾 consensus_daily {today}: {len(rows)}행 적재 (커버리지 {ncov} · 무커버 {len(rows)-ncov} · 실패 {fail})")
    tot = con.execute("SELECT COUNT(*), COUNT(DISTINCT date) FROM consensus_daily").fetchone()
    print(f"   누적 {tot[0]}행 · 스냅샷 {tot[1]}회 — 리비전 팩터는 스냅샷 4~8회부터 계산 가능")
    con.close()


if __name__ == "__main__":
    main()
