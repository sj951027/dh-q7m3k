# -*- coding: utf-8 -*-
"""
collect_dart_history.py — DART 과거 재무(연간·분기 보고서) 3년치 수집 (2026-10-03, 사용자 승인 — research 전용)

왜: "실제 v30 이 시기에 상관없이 우상향인가"를 3년 자료로 보려면 v30 의 재무 항(영업이익 YoY·OCF·패턴)을
   과거 시점마다 "그때 알 수 있었던 보고서"로 다시 계산해야 한다. 현재 dart_cache 는 최근 보고서만 있다.
무엇: 종목(3년 패널 + 상장목록)마다 연간보고서(2022~2025) · 분기/반기/3분기(2023~2026)의
   영업이익·영업활동현금흐름·자본·당기순이익 항목만 골라 sqlite 에 저장(보고서 전체는 저장하지 않음 — 용량).
   보고서 접수번호(rcept_no 앞 8자리 = 접수일)를 같이 저장해 뒤에 PIT(그 날짜에 알 수 있었나) 재구성에 쓴다.
안전: 호출 속도는 dart_rate(분당 600) 그대로 · 평일 19:55~22:40 KST 는 자동으로 쉼(배치가 DART 를 쓰는 시간) ·
   DART 한도 초과(status 020)면 다음날 00:10 까지 쉼 · 중단해도 재실행하면 이어서(저장된 건 건너뜀) ·
   운영 캐시(dart_cache/fin)·history.db·ohlcv.db 는 건드리지 않는다. API 키는 .env 에서 읽되 출력하지 않는다.

사용:
  python research/dart_history/collect_dart_history.py --limit 3        # 시험(종목 3개)
  python research/dart_history/collect_dart_history.py                  # 전체(며칠 걸림, 중단·재개 가능)
  python research/dart_history/collect_dart_history.py --status
"""
import argparse, json, os, sqlite3, sys, time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
import requests
import dart_rate as _drate                                   # noqa: E402  분당 상한(배치와 같은 규칙)
import stage3_fundamental_momentum_v2_6 as S3               # noqa: E402  계정 매칭 함수 재사용(네트워크 함수는 안 씀)
from run_and_diversify import load_dotenv                   # noqa: E402  .env → os.environ (값은 출력 안 함)

DB = HERE / "dart_hist.db"; LOG = HERE / "collect.log"
YEARS_ANNUAL = (2022, 2023, 2024, 2025); YEARS_Q = (2023, 2024, 2025, 2026)
REPRT = {"Y": "11011", "Q1": "11013", "H1": "11012", "Q3": "11014"}
URL_ALL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"; URL_SINGLE = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
KEEP_ID_KEYS = ("ProfitLossFromOperatingActivities", "OperatingIncomeLoss", "OperatingProfitLoss",
                "CashFlowsFromUsedInOperatingActivities", "CashFlowsFromOperatingActivities",
                "ifrs-full_Equity", "EquityAttributableToOwnersOfParent", "ifrs-full_ProfitLoss", "ProfitLossAttributableToOwnersOfParent",
                "ifrs-full_Revenue", "IssuedCapital")
KEEP_NM = ("영업이익", "영업손실", "영업이익(손실)", "영업손익", "영업활동현금흐름", "영업활동으로인한현금흐름", "자본총계", "당기순이익", "당기순이익(손실)", "매출액", "수익(매출액)")
FIELDS = ("account_id", "account_nm", "sj_div", "fs_div", "thstrm_amount", "frmtrm_amount", "thstrm_add_amount", "frmtrm_add_amount", "bfefrmtrm_amount",
          "frmtrm_q_amount", "bfefrmtrm_q_amount", "thstrm_q_amount", "ord", "rcept_no")   # [16:40] *_q_amount 추가(3개월 기준 전년동기 — 앞서 받은 2,140종목 행엔 없음 → 재계산 때 전년 보고서로 유도)


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")


def in_batch_window(now=None):
    now = now or datetime.now()
    return now.weekday() < 5 and (now.hour, now.minute) >= (19, 55) and (now.hour, now.minute) <= (22, 40)


def ensure_db():
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS reports(corp_code TEXT, stock_code TEXT, year INTEGER, reprt TEXT, api TEXT, fs TEXT,
        status TEXT, message TEXT, rcept_no TEXT, n_items INTEGER, kept INTEGER, items TEXT, fetched_at TEXT,
        PRIMARY KEY(corp_code, year, reprt, api, fs));
    CREATE TABLE IF NOT EXISTS corps(corp_code TEXT PRIMARY KEY, stock_code TEXT, done INTEGER DEFAULT 0, updated TEXT);
    CREATE INDEX IF NOT EXISTS idx_rep_stock ON reports(stock_code, year, reprt);
    """)
    return con


def universe():
    """3년 패널 종목 ∪ 상장목록 캐시 → corp_code 매핑(dart_cache/corp_code.csv)."""
    import pandas as pd
    cc = pd.read_csv(REPO / "dart_cache" / "corp_code.csv", dtype=str, encoding="utf-8-sig")
    cc = cc.dropna(subset=["stock_code"]); cc["stock_code"] = cc.stock_code.str.strip().str.zfill(6)
    m = dict(zip(cc.stock_code, cc.corp_code))
    ticks = set()
    try:
        import numpy as np
        z = np.load(REPO / "research" / "fullscan_20260903" / "panel.npz", allow_pickle=True); ticks |= set(z["tick"].astype(str))
    except Exception as e:
        log(f"panel.npz 없음({e}) — 상장목록만")
    try:
        import listing_cache
        rows, _ = listing_cache.load("KRX"); ticks |= {r["code"] for r in (rows or []) if r.get("market") in ("KOSPI", "KOSDAQ")}
    except Exception as e:
        log(f"listing_cache 없음({e})")
    out = [(m[t], t) for t in sorted(ticks) if t in m]
    log(f"대상 종목 {len(ticks)} 중 corp_code 매핑 {len(out)}")
    return out


def keep_items(items):
    out = []
    for it in items or []:
        aid = (it.get("account_id") or ""); nm = (it.get("account_nm") or "").replace(" ", "")
        if any(k.lower() in aid.lower() for k in KEEP_ID_KEYS) or any(k == nm for k in KEEP_NM) or ("영업활동" in nm and "현금흐름" in nm):
            out.append({k: it.get(k) for k in FIELDS if it.get(k) is not None})
    return out


def call(url, params, api_key):
    """stage3._request_json 와 같은 재시도·상태 처리(캐시는 안 씀 — 운영 캐시 오염 방지). 반환 (list|None, status, message)."""
    last = None
    for attempt in range(3):
        try:
            _drate.wait()
            r = requests.get(url, params=dict(params, crtfc_key=api_key), timeout=20); d = r.json()
            st = str(d.get("status", "")); msg = d.get("message", "")
            if st == "000": return d.get("list", []) or [], st, msg
            if st in ("1020", "900", "901", "902") and attempt < 2: time.sleep(3 ** attempt); continue
            return None, st or "NO_STATUS", msg
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            last = e
            if attempt < 2: time.sleep(3 ** attempt); continue
        except Exception as e:
            return None, "REQUEST_ERROR", str(e)[:120]
    return None, "REQUEST_ERROR", f"after retries: {str(last)[:100]}"


def plan():
    """(year, reprt) 목록 — 연간 4개 + 분기 12개(2026 Q3 는 아직 없음 → 13 대신 11까지)."""
    p = [(y, "Y") for y in YEARS_ANNUAL]
    for y in YEARS_Q:
        for q in ("Q1", "H1", "Q3"):
            if y == 2026 and q == "Q3": continue
            p.append((y, q))
    return p


def fetch_one(con, api_key, corp, stock, year, reprt):
    """ALL CFS → (없으면) ALL OFS → (없으면) SINGLE. 저장된 건 건너뜀. 반환 호출 수."""
    calls = 0
    have = {r[0] + "|" + r[1]: r[2] for r in con.execute("SELECT api, fs, status FROM reports WHERE corp_code=? AND year=? AND reprt=?", (corp, year, reprt))}
    def save(api, fs, items, st, msg):
        kept = keep_items(items) if items else []
        rc = (items[0].get("rcept_no") if items else None)
        con.execute("INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (corp, stock, year, reprt, api, fs, st, (msg or "")[:120], rc, len(items or []), len(kept), json.dumps(kept, ensure_ascii=False), datetime.now().strftime("%Y%m%d_%H%M%S")))
    for fs in ("CFS", "OFS"):
        k = f"ALL|{fs}"
        if k in have:
            if have[k] == "000": return calls
            continue
        items, st, msg = call(URL_ALL, {"corp_code": corp, "bsns_year": str(year), "reprt_code": REPRT[reprt], "fs_div": fs}, api_key); calls += 1
        if st == "020": raise RuntimeError("DART_DAILY_LIMIT")
        if st == "REQUEST_ERROR": raise RuntimeError("REQUEST_ERROR " + msg)
        save("ALL", fs, items, st, msg); con.commit()
        if items: return calls
    if "SINGLE|-" not in have:
        items, st, msg = call(URL_SINGLE, {"corp_code": corp, "bsns_year": str(year), "reprt_code": REPRT[reprt]}, api_key); calls += 1
        if st == "020": raise RuntimeError("DART_DAILY_LIMIT")
        if st == "REQUEST_ERROR": raise RuntimeError("REQUEST_ERROR " + msg)
        save("SINGLE", "-", items, st, msg); con.commit()
    return calls


def status(con):
    n_c = con.execute("SELECT COUNT(*), SUM(done) FROM corps").fetchone()
    n_r = con.execute("SELECT COUNT(*), SUM(status='000'), SUM(kept>0) FROM reports").fetchone()
    log(f"상태: 종목 {n_c[1] or 0}/{n_c[0]} 완료 · 보고서 행 {n_r[0]} (정상 {n_r[1] or 0}, 항목 있음 {n_r[2] or 0})")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=None); ap.add_argument("--status", action="store_true"); ap.add_argument("--max-calls", type=int, default=None)
    a = ap.parse_args()
    con = ensure_db()
    if a.status: status(con); return 0
    load_dotenv(str(REPO / ".env")); api_key = os.environ.get("DART_API_KEY", "")
    if len(api_key) < 30: log("DART_API_KEY 없음(.env)"); return 1
    uni = universe()
    for corp, stock in uni: con.execute("INSERT OR IGNORE INTO corps(corp_code, stock_code, done) VALUES (?,?,0)", (corp, stock))
    con.commit()
    todo = [(c, s) for c, s in uni if not con.execute("SELECT done FROM corps WHERE corp_code=?", (c,)).fetchone()[0]]
    if a.limit: todo = todo[:a.limit]
    log(f"시작: 남은 종목 {len(todo)} · 보고서 기간 {len(plan())}개/종목")
    calls = 0; t0 = time.time(); done_n = 0
    for corp, stock in todo:
        while in_batch_window():
            log("배치 시간(평일 19:55~22:40) — 쉼"); time.sleep(600)
        try:
            for year, reprt in plan():
                calls += fetch_one(con, api_key, corp, stock, year, reprt)
                if a.max_calls and calls >= a.max_calls: raise RuntimeError("MAX_CALLS")
        except RuntimeError as e:
            if str(e) == "DART_DAILY_LIMIT":
                nxt = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=10, second=0)
                log(f"DART 일일 한도(020) — {nxt:%m/%d %H:%M} 까지 쉼 (호출 {calls})"); time.sleep(max(60, (nxt - datetime.now()).total_seconds())); continue
            if str(e) == "MAX_CALLS": log(f"max-calls 도달 {calls}"); break
            log(f"오류 {stock}: {e} — 60초 뒤 계속"); time.sleep(60); continue
        con.execute("UPDATE corps SET done=1, updated=? WHERE corp_code=?", (datetime.now().strftime("%Y%m%d_%H%M%S"), corp)); con.commit(); done_n += 1
        if done_n % 25 == 0:
            el = time.time() - t0; log(f"진행 {done_n}/{len(todo)} 종목 · 호출 {calls} · {calls/max(el,1)*60:.0f}/분 · 경과 {el/60:.0f}분")
    status(con); log(f"끝: 종목 {done_n} · 호출 {calls} · {(time.time()-t0)/60:.1f}분")
    return 0


if __name__ == "__main__":
    sys.exit(main())
