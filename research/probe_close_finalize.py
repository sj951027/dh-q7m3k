# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행. 네트워크: 네이버 일봉 API 읽기만. 파일·DB 쓰기 없음(출력 CSV 1개, research/out_probe/).
"""probe_close_finalize.py — 애프터마켓(16~20시) 도입 후 '오늘 종가'가 몇 시에 확정되는지 관찰 (2026-09-18)

배경: 9/14·9/16 배치(20:10 수집)에서 약 2% 종목의 종가가 다음날 재수집값(=공식 종가)과 달랐다.
      원인 후보: 20:10 시점 네이버/FDR 일봉의 closePrice 가 아직 애프터마켓 마지막 체결가.
사용법: 평일 19:50 이전에 시작해 두면 21:10 까지 5분마다 표본 종목의 closePrice·거래량을 기록한다.
        python research/probe_close_finalize.py [--tickers 40] [--until 2110]
다음날 공식 종가와 비교해 "언제부터 값이 안 바뀌는지"를 본다(research/out_probe/probe_YYYYMMDD.csv).
"""
import argparse, csv, json, random, sqlite3, time, urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
ap = argparse.ArgumentParser(); ap.add_argument("--tickers", type=int, default=40); ap.add_argument("--until", default="2110"); ap.add_argument("--every", type=int, default=300)
a = ap.parse_args()
con = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
last_run = con.execute("SELECT MAX(run_id) FROM stage3_final").fetchone()[0]
tk = [r[0] for r in con.execute("SELECT DISTINCT ticker FROM stage3_final WHERE run_id=?", (last_run,))]; con.close()
random.seed(7); sample = random.sample(tk, min(a.tickers, len(tk)))
today = datetime.now().strftime("%Y%m%d")
out = HERE / "out_probe"; out.mkdir(exist_ok=True); f = out / f"probe_{today}.csv"
new = not f.exists()
w = csv.writer(open(f, "a", newline="", encoding="utf-8"))
if new: w.writerow(["probe_time", "ticker", "date", "close", "volume"])
print(f"표본 {len(sample)}종목 · {a.every}s 간격 · {a.until} 까지 · 출력 {f}")
while True:
    now = datetime.now(); stamp = now.strftime("%H:%M")
    for t in sample:
        try:
            req = urllib.request.Request(f"https://api.stock.naver.com/chart/domestic/item/{t}/day?startDateTime={today}0000&endDateTime={today}2359", headers={"User-Agent": "Mozilla/5.0"})
            for r in json.load(urllib.request.urlopen(req, timeout=10)):
                w.writerow([stamp, t, r["localDate"], r["closePrice"], r["accumulatedTradingVolume"]])
        except Exception as e:
            w.writerow([stamp, t, today, "", f"ERR {str(e)[:40]}"])
        time.sleep(0.1)
    print(f"  {stamp} 기록")
    if now.strftime("%H%M") >= a.until: break
    time.sleep(a.every)
print("끝. 다음날 공식 종가와 비교: 시각별로 close 가 마지막 값과 같은 비율을 보면 확정 시각이 나온다.")
