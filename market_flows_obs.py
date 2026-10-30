# -*- coding: utf-8 -*-
"""시장 수급(KRX 투자자별 매매) 일일 갱신 + 관측 요약 JSON — 표시·점수 어디에도 아직 안 들어감(자료만 쌓음) (2026-10-31 · 보강 2026.10.46)

무엇: ① `../dh-q7m3k-data/market_flows_10y.db`(연구 수집기 research/fetch_market_flows_10y.py 가 만든 11년 표)에 최근 N 일을 덧붙인다.
      ② 코스피·코스닥 11구분의 20일·60일 누적 순매수(원·거래대금 대비 %)를 `docs/market_flows_obs.json` 에 쓴다(관측·가중 0).
왜: 10/31 연구(RESEARCH_flow_regime_a_10y_20261031·_explore_) — 축 채택은 없지만 재검토(A 사건 30개)를 위해 자료는 계속 쌓는다.
안전 장치(Codex 검토 2026-10-31 반영): 수집은 **자식 프로세스**(시간 제한 TIMEOUT_S, pykrx 가 찍는 로그인 ID 등 출력은 부모가 버림) · 저장 전 **스냅샷 검사**(열·날짜·정수·보존식 — 실패한 시장은 저장 안 함) ·
  UPSERT 는 수량이 NULL 이면 기존 수량을 보존(COALESCE) · 값이 바뀐 행은 revision 표에 보존(BEGIN IMMEDIATE) · 20/60일 누적은 창이 **완전할 때만**(결측·거래대금 0 이면 None) ·
  JSON 은 임시 파일 → replace(잘림 방지), 시장별 data_as_of·refresh_status·last_success_at 기록 · 어떤 경로든 종료코드 0.
배치: run_all_and_diversify.bat 의 market_series.py 뒤. 로그인은 .env(KRX_ID/KRX_PW) — market_series._load_dotenv 와 같은 경로(자식 안에서만, 값 출력 없음).
순수 함수(테스트 tests/test_market_flows_obs.py): summarize · to_rows · valid_snapshot.
실행: python market_flows_obs.py [--days 30] [--no-fetch] [--out 경로] [--timeout 300]   (--worker 는 내부용)"""
import sys

DETAIL = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금", "기타법인", "개인", "외국인", "기타외국인", "전체"]
AGG = {"전체", "기관합계", "외국인합계"}
SOURCE = "KRX via pykrx MDCSTAT02203 (etf/etn/elw=False, detail) · daily refresh"
MARKETS = ["KOSPI", "KOSDAQ"]
TIMEOUT_S = 300


def summarize(net, T, windows=(20, 60)):
    """net: DataFrame(index=date 오름차순, columns=투자자, 순매수 원) · T: Series(index=date, 그날 거래대금 원).
    → {"date", "w20": {투자자: {"sum", "pct"}} 또는 None, "T20", ...}. 창 w 는 **마지막 w 행이 모두 유효하고 거래대금 > 0** 일 때만 값, 아니면 None(결측을 건너뛰어 19일을 20일로 내지 않음)."""
    import numpy as np, pandas as pd
    if net is None or not len(net):
        return None
    net = net.sort_index(); T = T.reindex(net.index)
    cols = [c for c in net.columns if c != "전체"]
    out = {"date": str(net.index[-1])}
    for w in windows:
        if len(net) < w:
            out[f"w{w}"] = None; out[f"T{w}"] = None; continue
        z = net[cols].iloc[-w:].to_numpy(dtype=float); tw = T.iloc[-w:].to_numpy(dtype=float)
        if not (np.isfinite(z).all() and np.isfinite(tw).all() and (tw > 0).all()):
            out[f"w{w}"] = None; out[f"T{w}"] = None; continue
        tsum = float(tw.sum()); sums = z.sum(axis=0)
        out[f"T{w}"] = tsum
        out[f"w{w}"] = {c: {"sum": float(sums[k]), "pct": float(sums[k] / tsum * 100)} for k, c in enumerate(cols)}
    return out


def valid_snapshot(got):
    """{(kind, on): DataFrame} 묶음이 저장할 만한가 — 대금(val) 세 표는 필수: 열 = DETAIL · 날짜 유일·동일 · 유한 정수 · 매수−매도=순매수 · 11구분 순매수 합 0 ·
    11구분 매수(매도) 합 = 전체 · 전체 매수 > 0. 수량(qty) 표는 있으면 같은 검사, 없거나 비면 '수량 없음'(허용). 반환 (ok, 사유, qty_ok)."""
    import numpy as np
    def check(kind):
        base = got.get((kind, "순매수"))
        if base is None or not len(base) or not base.index.is_unique:
            return False, f"{kind}: 순매수 표 없음/중복"
        for on in ("매수", "매도", "순매수"):
            f = got.get((kind, on))
            if f is None or not len(f):
                return False, f"{kind} {on}: 표 없음"
            if list(f.columns) != DETAIL:
                return False, f"{kind} {on}: 열 집합 다름"
            if not f.index.is_unique or not f.index.equals(base.index):
                return False, f"{kind} {on}: 날짜 축 불일치"
            v = f.to_numpy(dtype=float)
            if not np.isfinite(v).all() or not np.equal(v, np.trunc(v)).all():
                return False, f"{kind} {on}: 결측/비정수"
        buy, sell, net = (got[(kind, x)] for x in ("매수", "매도", "순매수"))
        if (buy < 0).any().any() or (sell < 0).any().any():
            return False, f"{kind}: 음수 매수/매도"
        if not (buy - sell).eq(net).all().all():
            return False, f"{kind}: 매수−매도≠순매수"
        if not net.drop(columns="전체").sum(axis=1).eq(0).all() or not net["전체"].eq(0).all():
            return False, f"{kind}: 순매수 합≠0"
        for g in (buy, sell):
            if not g.drop(columns="전체").sum(axis=1).eq(g["전체"]).all():
                return False, f"{kind}: 구분 합≠전체"
        if kind == "val" and not (buy["전체"] > 0).all():
            return False, "val: 전체 매수 0 인 날"
        return True, ""
    ok, why = check("val")
    if not ok:
        return False, why, False
    qok, qwhy = check("qty")
    return True, ("" if qok else f"수량 없음({qwhy})"), qok


def to_rows(market, got, fetched_at, qty_ok=True):
    """저장 행 — 수량은 qty_ok 일 때만, 아니면 None(UPSERT 가 기존 수량 보존)."""
    import pandas as pd
    rows = []
    base = got.get(("val", "순매수"))
    if base is None or not len(base):
        return rows
    for d in base.index:
        ds = pd.Timestamp(d).strftime("%Y%m%d")
        for inv in DETAIL:
            def g(kind, on):
                if kind == "qty" and not qty_ok:
                    return None
                df = got.get((kind, on))
                return int(df.at[d, inv]) if (df is not None and len(df) and d in df.index and inv in df.columns and pd.notna(df.at[d, inv])) else None
            rows.append((market, ds, inv, g("val", "매수"), g("val", "매도"), g("val", "순매수"), g("qty", "매수"), g("qty", "매도"), g("qty", "순매수"),
                         1 if inv in AGG else 0, fetched_at, SOURCE))
    return rows


UPSERT = """INSERT INTO investor_daily(market,date,investor,buy_val,sell_val,net_val,buy_qty,sell_qty,net_qty,is_aggregate,fetched_at,source)
VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(market,date,investor) DO UPDATE SET
  buy_val=excluded.buy_val, sell_val=excluded.sell_val, net_val=excluded.net_val,
  buy_qty=COALESCE(excluded.buy_qty, investor_daily.buy_qty), sell_qty=COALESCE(excluded.sell_qty, investor_daily.sell_qty), net_qty=COALESCE(excluded.net_qty, investor_daily.net_qty),
  is_aggregate=excluded.is_aggregate, fetched_at=excluded.fetched_at, source=excluded.source"""


def store_rows(con, rows, fetched_at):
    """BEGIN IMMEDIATE 안에서: 바뀐 행은 revision 보존 → UPSERT. 반환 (저장 행, revision 행)."""
    if not rows:
        return 0, 0
    cur = con.cursor(); cur.execute("BEGIN IMMEDIATE")
    try:
        mk = rows[0][0]; ds = sorted({r[1] for r in rows})
        q = f"SELECT market,date,investor,buy_val,sell_val,net_val,buy_qty,sell_qty,net_qty,fetched_at FROM investor_daily WHERE market=? AND date BETWEEN ? AND ?"
        old = {(m, d, i): r for m, d, i, *r in cur.execute(q, (mk, ds[0], ds[-1]))}
        nrev = 0
        for r in rows:
            k = (r[0], r[1], r[2]); o = old.get(k)
            if o is not None and tuple(o[:3]) != tuple(r[3:6]):
                cur.execute("INSERT INTO investor_daily_revision VALUES(?,?,?,?,?,?,?,?,?,?,?)", (*k, *o[:6], o[6], fetched_at)); nrev += 1
        cur.executemany(UPSERT, rows); con.commit(); return len(rows), nrev
    except Exception:
        con.rollback(); raise


def worker(days, db_path):
    """자식 프로세스: .env → 로그인 → 수집 → 검사 → 저장. 마지막 줄 'STATUS {json}' 만 부모가 읽는다. 다른 출력(로그인 ID 등)은 버려진다."""
    import io, json, sqlite3, time, contextlib
    from datetime import datetime
    import pandas as pd
    import market_series; market_series._load_dotenv()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from pykrx import stock                                               # import 때 로그인 — 출력 차단
    end = datetime.now().strftime("%Y%m%d"); start = (datetime.now() - pd.Timedelta(days=int(days * 1.6) + 7)).strftime("%Y%m%d")
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S"); status = {"markets": {}, "fetched_at": fetched_at}
    con = sqlite3.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS investor_daily_revision(market TEXT, date TEXT, investor TEXT, buy_val INTEGER, sell_val INTEGER, net_val INTEGER,
                   buy_qty INTEGER, sell_qty INTEGER, net_qty INTEGER, fetched_at TEXT, replaced_at TEXT)""")
    con.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
    for mk in MARKETS:
        got = {}
        for kind, fn in [("val", stock.get_market_trading_value_by_date), ("qty", stock.get_market_trading_volume_by_date)]:
            for on in ["매수", "매도", "순매수"]:
                try:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        got[(kind, on)] = fn(start, end, mk, etf=False, etn=False, elw=False, on=on, detail=True)
                except Exception as e:
                    got[(kind, on)] = pd.DataFrame(); status["markets"][mk] = {"err": f"{kind} {on} {type(e).__name__}"}
                time.sleep(0.5)
        ok, why, qok = valid_snapshot(got)
        if not ok:
            status["markets"][mk] = {"ok": False, "why": why}; continue
        rows = to_rows(mk, got, fetched_at, qty_ok=qok)
        n, nrev = store_rows(con, rows, fetched_at)
        status["markets"][mk] = {"ok": True, "rows": n, "days": n // len(DETAIL), "revision": nrev, "qty": qok, "note": why, "last": str(pd.Timestamp(got[("val", "순매수")].index[-1]).strftime("%Y%m%d"))}
    if any(v.get("ok") for v in status["markets"].values()):
        con.execute("INSERT OR REPLACE INTO meta VALUES('last_success_at',?)", (fetched_at,)); con.commit()
    con.close()
    print("STATUS " + json.dumps(status, ensure_ascii=False))


def build_json(con, refresh):
    import pandas as pd
    from datetime import datetime
    since = (datetime.now() - pd.Timedelta(days=200)).strftime("%Y%m%d")
    F = pd.read_sql("SELECT market, date, investor, net_val, buy_val FROM investor_daily WHERE date >= ?", con, params=(since,))
    last_ok = next((v for (k, v) in con.execute("SELECT key, value FROM meta WHERE key='last_success_at'")), None)
    out = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "last_success_at": last_ok, "refresh_status": refresh, "unit": "KRW",
           "note": "KRX 투자자별 매매 20·60일 누적 순매수(관측·가중 0 — 점수·판정·게이트·표시에 넣지 않음; 연구 RESEARCH_flow_regime_a_10y_20261031). 창이 불완전하면 null.", "markets": {}}
    for mk in MARKETS:
        f = F[F.market == mk]
        if f.empty:
            out["markets"][mk] = None; continue
        net = f.pivot(index="date", columns="investor", values="net_val").sort_index().tail(80)
        net = net[[c for c in DETAIL if c in net.columns]]
        T = f[f.investor == "전체"].set_index("date").buy_val.sort_index()
        s = summarize(net, T); s["data_as_of"] = s["date"]; out["markets"][mk] = s
    return out


def main():
    import argparse, json, os, sqlite3, subprocess, tempfile, time
    from pathlib import Path
    HERE = Path(__file__).resolve().parent; DB = HERE / ".." / "dh-q7m3k-data" / "market_flows_10y.db"; JSON_PATH = HERE / "docs" / "market_flows_obs.json"
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=30); ap.add_argument("--no-fetch", action="store_true"); ap.add_argument("--out", default=None)
    ap.add_argument("--timeout", type=int, default=TIMEOUT_S); ap.add_argument("--worker", action="store_true")
    a = ap.parse_args(); t0 = time.time()
    if a.worker:
        worker(a.days, str(DB)); return
    if not DB.exists():
        print("⚠ market_flows_obs: market_flows_10y.db 없음(연구 수집기 먼저) — 건너뜀(비치명)"); return
    refresh = {"status": "skipped" if a.no_fetch else "unknown"}
    if not a.no_fetch:
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--worker", "--days", str(a.days)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=a.timeout)
            line = next((ln for ln in reversed((r.stdout or "").splitlines()) if ln.startswith("STATUS ")), None)
            if line:
                refresh = json.loads(line[7:]); refresh["status"] = "ok" if any(v.get("ok") for v in refresh.get("markets", {}).values()) else "failed"
                for mk, v in refresh.get("markets", {}).items():
                    print(f"  {mk}: " + (f"{v.get('days')}일 덧붙임(~{v.get('last')}) · revision {v.get('revision')}" + (f" · {v.get('note')}" if v.get("note") else "") if v.get("ok") else f"저장 안 함 — {v.get('why') or v.get('err')}"))
            else:
                refresh = {"status": "failed", "why": f"worker exit {r.returncode}, no status"}; print(f"  ⚠ 수급 갱신 실패(비치명): 자식 종료코드 {r.returncode}")
        except subprocess.TimeoutExpired:
            refresh = {"status": "timeout", "why": f">{a.timeout}s"}; print(f"  ⚠ 수급 갱신 시간 초과({a.timeout}s) — 중단(비치명)")
        except Exception as e:
            refresh = {"status": "failed", "why": type(e).__name__}; print(f"  ⚠ 수급 갱신 실패(비치명): {type(e).__name__}")
        print(f"  수급 갱신 {refresh.get('status')} · {time.time()-t0:.0f}s")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); payload = build_json(con, refresh); con.close()
    p = Path(a.out) if a.out else JSON_PATH
    fd, tmpname = tempfile.mkstemp(prefix=p.name + ".", dir=str(p.parent)); os.close(fd)      # Windows: 열린 핸들을 닫아야 다시 쓸 수 있다
    Path(tmpname).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8"); os.replace(tmpname, p)
    k = payload["markets"].get("KOSPI") or {}; w = k.get("w20")
    print(f"  ✓ {p.name} · KOSPI {k.get('date')} · " + (f"20일 외국인 {w['외국인']['pct']:+.2f}% · 연기금 {w['연기금']['pct']:+.2f}%" if w else "20일 창 불완전(null)") + " (관측·가중 0)")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                               # 어떤 실패도 배치를 막지 않는다(SystemExit 포함)
        try:
            print(f"⚠ market_flows_obs 실패(비치명): {type(e).__name__}")
        except Exception:
            pass
    sys.exit(0)
