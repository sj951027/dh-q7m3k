# -*- coding: utf-8 -*-
"""KRX 시장 수급 **탐색 조회**(수집 아님) — 하루치 2건(2015-01-02 · 2026-10-29), KOSPI, 투자자 상세 11열, 순매수·매수·매도 (2026-10-31)

목적(Codex 명세서 REPLY_20261031_flow_data_spec.md 의 미확인 4가지): ① 2015 가 오나 ② 열 이름 11개 그대로인가 ③ 단위(매수 '전체' ≈ 그날 코스피 거래대금인가)
④ 로그인 필요 여부·응답 시간. 로그인 없는 셸에서는 JSON 이 아닌 응답(= 로그인 요구)이 온다(10/31 00:40 실측).
로그인: 배치와 같은 경로 — `market_series._load_dotenv()` 가 .env 를 os.environ 에 올리고(값 출력 없음) pykrx 가 import 때 로그인한다.
산출: research/out_market_flows_probe/*.csv (하루치 표만) · DB 안 만듦 · 수집기 아님. 호출 8회, 1초 간격.
실행: python research/krx_probe_market_flows_20261031.py"""
import sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent))
import market_series; market_series._load_dotenv()          # .env → os.environ (값은 읽어 쓰기만, 출력 없음)
import pandas as pd
from pykrx import stock                                     # import 때 KRX 로그인 시도(ID 앞 3자만 찍힘)

OUT = HERE / "out_market_flows_probe"; OUT.mkdir(exist_ok=True)
APPROX_KOSPI_TURNOVER_20261029 = 267996e8                   # 운영 DB Σ(volume×close), 원 — 단위 확인용 근사(실측 10/31)
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 20)
t0 = time.time(); log = []


def say(s):
    print(s); log.append(s)


for d in ["20150102", "20261029"]:
    for on, detail in [("순매수", True), ("매수", True), ("매도", True), ("순매수", False)]:
        t1 = time.time()
        try:
            df = stock.get_market_trading_value_by_date(d, d, "KOSPI", etf=False, etn=False, elw=False, on=on, detail=detail)
            tag = f"{d}_{on}_{'상세' if detail else '일반'}"
            say(f"\n[{tag}] {time.time()-t1:.1f}s · shape {df.shape} · 열 {list(df.columns)}")
            if len(df):
                say(df.T.to_string()); df.to_csv(OUT / f"{tag}.csv", encoding="utf-8-sig")
                if on == "매수" and detail and "전체" in df.columns and d == "20261029":
                    tot = float(df["전체"].iloc[0]); say(f"  단위 확인: 매수 전체 {tot:,.0f} vs 운영 DB 근사 거래대금 {APPROX_KOSPI_TURNOVER_20261029:,.0f} → 비율 {tot/APPROX_KOSPI_TURNOVER_20261029:.3f} (≈1 이면 원 단위)")
                if on == "순매수" and detail:
                    cols = [c for c in df.columns if c != "전체"]; say(f"  보존식: 11개 순매수 합 = {float(df[cols].iloc[0].sum()):,.0f} (0 이어야)")
            else:
                say("  EMPTY (로그인 요구 또는 자료 없음)")
        except Exception as e:
            say(f"\n[{d} {on} {'상세' if detail else '일반'}] ERROR {type(e).__name__}: {e}")
        time.sleep(1)
say(f"\n끝 {time.time()-t0:.0f}s → {OUT}")
(OUT / "probe_log_20261031.txt").write_text("\n".join(log), encoding="utf-8")
