# -*- coding: utf-8 -*-
"""시장 수급(KRX 투자자별 매매) 일일 갱신 + 관측 요약 JSON — 표시·점수 어디에도 아직 안 들어감(자료만 쌓음) (2026-10-31)

무엇: ① `../dh-q7m3k-data/market_flows_10y.db`(연구 수집기 research/fetch_market_flows_10y.py 가 만든 11년 표)에 최근 N 일을 덧붙인다(같은 키는 덮어씀).
      ② 코스피·코스닥 11구분의 20일·60일 누적 순매수(원·거래대금 대비 %)를 `docs/market_flows_obs.json` 에 쓴다(관측·가중 0).
왜: 10/31 연구(research/RESEARCH_flow_regime_a_10y_20261031.md·_explore_)에서 "외국인 추종 닫음 · 연기금 보류(코스닥 반대 부호)" — 축 채택은 없지만 자료는 계속 쌓아야 재검토(A 사건 30개)가 된다.
배치: run_all_and_diversify.bat 의 market_series.py 뒤, 비치명(어떤 실패도 종료코드 0). 로그인은 .env(KRX_ID/KRX_PW) — market_series._load_dotenv 와 같은 경로, 값 출력 없음.
순수 함수(테스트 tests/test_market_flows_obs.py): summarize(net, T) · to_rows(...). 네트워크는 fetch_recent 에만.
실행: python market_flows_obs.py [--days 30] [--no-fetch](JSON 만 다시) [--out 경로]"""
import argparse, json, sqlite3, sys, time
from datetime import datetime
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
DB = HERE / ".." / "dh-q7m3k-data" / "market_flows_10y.db"
JSON_PATH = HERE / "docs" / "market_flows_obs.json"
DETAIL = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금", "기타법인", "개인", "외국인", "기타외국인", "전체"]
AGG = {"전체", "기관합계", "외국인합계"}
SOURCE = "KRX via pykrx MDCSTAT02203 (etf/etn/elw=False, detail) · daily refresh"
MARKETS = ["KOSPI", "KOSDAQ"]


def summarize(net, T, windows=(20, 60)):
    """net: DataFrame(index=date 오름차순, columns=투자자 11구분, 순매수 원) · T: Series(index=date, 그날 거래대금 원).
    → {"date": 마지막 날, "w20": {투자자: {"sum": 원, "pct": 거래대금 대비 %}}, "w60": {...}, "T20": 원, "T60": 원}. 창보다 짧으면 None 항목."""
    if net is None or not len(net):
        return None
    net = net.sort_index(); T = T.reindex(net.index)
    out = {"date": str(net.index[-1])}
    for w in windows:
        if len(net) < w:
            out[f"w{w}"] = None; out[f"T{w}"] = None; continue
        tw = float(T.iloc[-w:].sum()); out[f"T{w}"] = tw
        out[f"w{w}"] = {c: {"sum": float(net[c].iloc[-w:].sum()), "pct": (float(net[c].iloc[-w:].sum()) / tw * 100 if tw > 0 else None)}
                        for c in net.columns if c != "전체"}
    return out


def to_rows(market, got, fetched_at):
    """got: {("val"|"qty", "매수"|"매도"|"순매수"): DataFrame(index=날짜, columns=DETAIL)} → investor_daily 행."""
    rows = []
    base = got.get(("val", "순매수"))
    if base is None or not len(base):
        return rows
    for d in base.index:
        ds = pd.Timestamp(d).strftime("%Y%m%d")
        for inv in DETAIL:
            def g(kind, on):
                df = got.get((kind, on))
                return int(df.at[d, inv]) if (df is not None and len(df) and d in df.index and inv in df.columns and pd.notna(df.at[d, inv])) else None
            rows.append((market, ds, inv, g("val", "매수"), g("val", "매도"), g("val", "순매수"), g("qty", "매수"), g("qty", "매도"), g("qty", "순매수"),
                         1 if inv in AGG else 0, fetched_at, SOURCE))
    return rows


def fetch_recent(con, days, log):
    """최근 days 거래일(달력일 기준 넉넉히) 을 KRX 에서 받아 덧붙인다. 실패는 호출자가 비치명 처리."""
    import market_series; market_series._load_dotenv()                    # .env → os.environ (값 출력 없음)
    from pykrx import stock                                                # import 때 KRX 로그인
    end = datetime.now().strftime("%Y%m%d"); start = (datetime.now() - pd.Timedelta(days=int(days * 1.6) + 7)).strftime("%Y%m%d")
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S"); total = 0
    for mk in MARKETS:
        got = {}
        for kind, fn in [("val", stock.get_market_trading_value_by_date), ("qty", stock.get_market_trading_volume_by_date)]:
            for on in ["매수", "매도", "순매수"]:
                try:
                    df = fn(start, end, mk, etf=False, etn=False, elw=False, on=on, detail=True)
                    if list(df.columns) != DETAIL:
                        log.append(f"  ⚠ {mk} {kind} {on}: 열 집합 다름 → 건너뜀"); df = pd.DataFrame()
                except Exception as e:
                    log.append(f"  ⚠ {mk} {kind} {on}: {type(e).__name__}"); df = pd.DataFrame()
                got[(kind, on)] = df; time.sleep(0.5)
        rows = to_rows(mk, got, fetched_at)
        if rows:
            con.executemany("INSERT OR REPLACE INTO investor_daily VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows); con.commit(); total += len(rows)
            log.append(f"  {mk}: {len(rows)//len(DETAIL)}일 덧붙임({start}~{end})")
    return total


def build_json(con):
    F = pd.read_sql("SELECT market, date, investor, net_val, buy_val FROM investor_daily WHERE date >= date('now','-200 day') OR 1=1", con)
    out = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "unit": "KRW", "note": "KRX 투자자별 매매 20·60일 누적 순매수(관측·가중 0 — 점수·판정·게이트·표시에 넣지 않음; 연구 RESEARCH_flow_regime_a_10y_20261031)", "markets": {}}
    for mk in MARKETS:
        f = F[F.market == mk]
        if f.empty:
            out["markets"][mk] = None; continue
        net = f.pivot(index="date", columns="investor", values="net_val").sort_index().tail(80)
        T = f[f.investor == "전체"].set_index("date").buy_val.sort_index()
        net = net[[c for c in DETAIL if c in net.columns]]
        out["markets"][mk] = summarize(net, T)
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=30); ap.add_argument("--no-fetch", action="store_true"); ap.add_argument("--out", default=None)
    a = ap.parse_args(); log = []; t0 = time.time()
    try:
        if not DB.exists():
            print("⚠ market_flows_obs: market_flows_10y.db 없음(연구 수집기 먼저) — 건너뜀(비치명)"); return
        con = sqlite3.connect(DB)
        if not a.no_fetch:
            try:
                n = fetch_recent(con, a.days, log)
                print(f"  수급 갱신 {n}행 · {time.time()-t0:.0f}s"); [print(x) for x in log]
            except Exception as e:
                print(f"  ⚠ 수급 갱신 실패(비치명, JSON 은 기존 자료로): {type(e).__name__}: {e}")
        payload = build_json(con); con.close()
        p = Path(a.out) if a.out else JSON_PATH
        p.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        k = payload["markets"].get("KOSPI") or {}
        w = (k.get("w20") or {})
        print(f"  ✓ {p.name} · KOSPI {k.get('date')} · 20일 외국인 {((w.get('외국인') or {}).get('pct') or 0):+.2f}% · 연기금 {((w.get('연기금') or {}).get('pct') or 0):+.2f}% (관측·가중 0)")
    except BaseException as e:
        print(f"⚠ market_flows_obs 실패(비치명): {e!r}")
    sys.exit(0)


if __name__ == "__main__":
    main()
