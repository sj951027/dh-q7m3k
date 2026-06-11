# -*- coding: utf-8 -*-
"""
kis_flows.py — 대형 가치주 트랙 3단계: KIS 일별 투자자 수급 적재 (조회 전용)
==============================================================================
large_universe 최신 run의 종목(상위 500)에 대해 KIS '주식현재가 투자자'
(FHKST01010900)를 종목당 1회 호출, 일자별 개인/외국인/기관 순매수를
새 테이블 daily_flows 에 적재한다. (설계 §7)

동작 원리:
  - 이 API는 최근 ~30영업일 윈도를 돌려준다 → 첫 실행 = 즉시 ~30일 확보,
    매일 실행 = 새 날짜 1개 추가 + 최근 윈도 재기록(INSERT OR REPLACE).
    재기록 덕에 당일 잠정치가 다음 날 확정치로 자동 보정되고, 며칠 빠져도
    윈도가 구멍을 덮는다(자가 치유). 120일 이력은 운영 누적으로 채워짐 —
    이 API로는 더 깊은 과거 백필이 불가하므로 갭으로 명시한다(§13 원칙).
  - 에러는 저장하지 않는다: 실패 종목은 행을 안 쓰고 다음 날 재시도.

안전 규칙 (설계 §7, §10):
  - 조회 전용. 주문/계좌 API 없음 — 계좌번호 자체를 받지 않는다.
  - 토큰은 kis_token.json 에 캐시, 만료 임박시에만 발급(.gitignore 필수).
    KIS는 유효기간(24h) 내 재요청 시 동일 토큰을 반환하므로, 같은 앱키를
    쓰는 다른 프로그램(예: Position Tracker)과 토큰이 자연 공유된다.
    발급 자체도 1분당 1회 제한이 있어 함부로 재발급하지 않는다.
  - [v1.0.1] 토큰 1분 게이트 충돌 시 65초 후 1회 재시도.
  - 레이트: 단일 스레드 + 호출 간 KIS_REQ_INTERVAL(기본 0.55s ≈ 초당 1.8건).
    500종목 ≈ 4.6분/일.

실행 (.bat 끝, large_score 다음 줄):
    python kis_flows.py                 # 유니버스 = large_universe 최신 run
    python kis_flows.py --top 300       # 상위 300만
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from catalyst_insider import load_env   # .env 로더 재사용 (KIS_APP_KEY/SECRET)

DB_PATH = Path("history.db")
TOKEN_CACHE = Path("kis_token.json")
BASE = "https://openapi.koreainvestment.com:9443"      # 실전투자 도메인 (조회)
TR_INVESTOR = "FHKST01010900"                          # 주식현재가 투자자(일별)
KIS_REQ_INTERVAL = 0.55                                # 호출 간격(초) — 트래커와 동일
TOKEN_MIN_LEFT = 1800                                  # 잔여 30분 미만이면 재발급

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS daily_flows (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,
    close  REAL,
    person_net_qty REAL, foreign_net_qty REAL, inst_net_qty REAL,
    person_net_val REAL, foreign_net_val REAL, inst_net_val REAL,
    fetched_at TEXT,
    PRIMARY KEY (ticker, date)
)
"""


# ============================================================
# 토큰 (캐시 우선 — 발급은 최후)
# ============================================================
def load_cached_token(path=TOKEN_CACHE, now=None):
    """캐시 토큰이 충분히(>TOKEN_MIN_LEFT) 남았으면 반환, 아니면 None. (순수)"""
    now = now if now is not None else time.time()
    try:
        d = json.loads(Path(path).read_text(encoding='utf-8'))
        if d.get('token') and float(d.get('expires_at', 0)) > now + TOKEN_MIN_LEFT:
            return d['token']
    except Exception:
        pass
    return None


def save_token(token, expires_at, path=TOKEN_CACHE):
    Path(path).write_text(json.dumps({'token': token, 'expires_at': expires_at}),
                          encoding='utf-8')


def get_token(app_key, app_secret, path=TOKEN_CACHE):
    tok = load_cached_token(path)
    if tok:
        return tok
    import requests
    print("   • 접근토큰 발급 요청 (캐시 만료/부재 — 1분당 1회 제한 유의)")
    for attempt in (1, 2):
        r = requests.post(f"{BASE}/oauth2/tokenP",
                          headers={"content-type": "application/json"},
                          data=json.dumps({"grant_type": "client_credentials",
                                           "appkey": app_key, "appsecret": app_secret}),
                          timeout=10)
        try:
            j = r.json()
        except Exception:
            j = {}
        tok = j.get("access_token")
        if tok:
            ttl = float(j.get("expires_in", 86400))
            save_token(tok, time.time() + ttl)
            return tok
        # 같은 앱키의 다른 프로그램(트래커)이 직전 1분 내 발급한 경우 — 잠시 기다려 재시도
        if attempt == 1 and ('EGW00133' in r.text or '1분' in r.text):
            print("   • 1분당 1회 발급 제한에 걸림 — 65초 대기 후 재시도")
            time.sleep(65)
            continue
        raise RuntimeError(f"토큰 발급 실패 (status={r.status_code}): {r.text[:200]}")


# ============================================================
# 파싱 (순수 — 오프라인 검증 대상)
# ============================================================
def _num(v):
    """KIS 숫자 문자열('1,234', '-56', '') → float | None."""
    if v is None:
        return None
    s = str(v).strip().replace(',', '')
    if s in ('', '-', '+'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_rows(output_rows, fetched_at):
    """API output(list[dict]) → daily_flows 행 dict 목록. 필드명 변형은 후보군으로 흡수.
    날짜 없는 행은 버리고, 알 수 없는 스키마면 첫 행 키를 진단 출력."""
    rows, warned = [], False
    for r in output_rows or []:
        date = str(r.get('stck_bsop_date') or '').strip()
        if len(date) != 8 or not date.isdigit():
            continue
        def pick(*keys):
            for k in keys:
                if k in r:
                    return _num(r[k])
            return None
        row = {
            'date': date,
            'close': pick('stck_clpr'),
            'person_net_qty': pick('prsn_ntby_qty'),
            'foreign_net_qty': pick('frgn_ntby_qty'),
            'inst_net_qty': pick('orgn_ntby_qty'),
            'person_net_val': pick('prsn_ntby_tr_pbmn', 'prsn_shnu_tr_pbmn'),
            'foreign_net_val': pick('frgn_ntby_tr_pbmn', 'frgn_shnu_tr_pbmn'),
            'inst_net_val': pick('orgn_ntby_tr_pbmn', 'orgn_shnu_tr_pbmn'),
            'fetched_at': fetched_at,
        }
        if row['foreign_net_qty'] is None and row['inst_net_qty'] is None and not warned:
            print(f"   ⚠️  예상 필드 없음 — 응답 키 진단: {sorted(r.keys())[:20]}")
            warned = True
        rows.append(row)
    return rows


# ============================================================
# DB (증분 — '없는 날짜' 추가 + 최근 윈도 재기록)
# ============================================================
def ensure_table(con):
    con.execute(TABLE_SQL)
    con.commit()


def upsert_flows(con, ticker, rows):
    """INSERT OR REPLACE. 반환 (신규 날짜 수, 재기록 수). 행이 없으면 (0,0) — 에러 미저장."""
    if not rows:
        return 0, 0
    have = {d for (d,) in con.execute(
        "SELECT date FROM daily_flows WHERE ticker=?", (ticker,))}
    new = sum(1 for r in rows if r['date'] not in have)
    con.executemany(
        "INSERT OR REPLACE INTO daily_flows "
        "(ticker, date, close, person_net_qty, foreign_net_qty, inst_net_qty, "
        " person_net_val, foreign_net_val, inst_net_val, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(ticker, r['date'], r['close'], r['person_net_qty'], r['foreign_net_qty'],
          r['inst_net_qty'], r['person_net_val'], r['foreign_net_val'],
          r['inst_net_val'], r['fetched_at']) for r in rows])
    con.commit()
    return new, len(rows) - new


def load_universe_tickers(db_path=DB_PATH, run_id=None, top=None):
    with sqlite3.connect(db_path) as con:
        rid = run_id or con.execute("SELECT MAX(run_id) FROM large_universe").fetchone()[0]
        if not rid:
            raise RuntimeError("large_universe 비어 있음 — large_universe.py 먼저 실행")
        q = "SELECT ticker, name FROM large_universe WHERE run_id=? ORDER BY marcap_rank"
        rows = con.execute(q, (str(rid),)).fetchall()
    if top:
        rows = rows[:top]
    return str(rid), rows


# ============================================================
# KIS 호출 (네트워크 — 사용자 PC 전용)
# ============================================================
def fetch_investor(ticker, token, app_key, app_secret):
    import requests
    r = requests.get(
        f"{BASE}/uapi/domestic-stock/v1/quotations/inquire-investor",
        headers={"content-type": "application/json",
                 "authorization": f"Bearer {token}",
                 "appkey": app_key, "appsecret": app_secret,
                 "tr_id": TR_INVESTOR, "custtype": "P"},
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        timeout=10)
    j = r.json()
    if j.get("rt_cd") not in (None, "0"):
        raise RuntimeError(f"rt_cd={j.get('rt_cd')} {j.get('msg1', '')}".strip())
    return j.get("output") or []


def main():
    ap = argparse.ArgumentParser(description="KIS 일별 투자자 수급 증분 적재(조회 전용)")
    ap.add_argument("--run-id", default=None, help="유니버스 run (기본: large_universe 최신)")
    ap.add_argument("--top", type=int, default=None, help="시총 상위 N만 (기본: 적재분 전체=500)")
    ap.add_argument("--sleep", type=float, default=KIS_REQ_INTERVAL)
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()

    load_env()
    app_key = os.environ.get("KIS_APP_KEY", "").strip()
    app_secret = os.environ.get("KIS_APP_SECRET", "").strip()
    if not (app_key and app_secret):
        raise SystemExit("❌ .env 의 KIS_APP_KEY / KIS_APP_SECRET 확인")

    rid, tickers = load_universe_tickers(Path(args.db), args.run_id, args.top)
    print("=" * 64)
    print(f"🏛️  KIS 일별 투자자 수급 적재 — 유니버스 run {rid}, {len(tickers)}종목 "
          f"(간격 {args.sleep}s, 예상 ~{len(tickers) * args.sleep / 60:.1f}분)")
    print("=" * 64)

    token = get_token(app_key, app_secret)
    con = sqlite3.connect(args.db)
    ensure_table(con)
    fetched_at = datetime.now().strftime("%Y%m%d_%H%M")
    n_new = n_rep = n_fail = 0
    t0 = time.time()
    for i, (tk, name) in enumerate(tickers, 1):
        time.sleep(args.sleep)
        try:
            rows = parse_rows(fetch_investor(tk, token, app_key, app_secret), fetched_at)
            a, b = upsert_flows(con, tk, rows)
            n_new += a
            n_rep += b
        except Exception as e:
            n_fail += 1
            if n_fail <= 5:
                print(f"   ⚠️  {name}({tk}) 실패: {str(e)[:80]}")
        if i % 100 == 0 or i == len(tickers):
            el = time.time() - t0
            print(f"   [{i}/{len(tickers)}] {el:.0f}s · 신규 {n_new} · 재기록 {n_rep} · 실패 {n_fail}")
    total, days = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT date) FROM daily_flows").fetchone()
    con.close()
    print(f"\n💾 daily_flows 누적: {total:,}행 · 거래일 {days}일")
    if n_fail:
        print(f"   (실패 {n_fail}종목은 저장 안 함 — 내일 윈도 재기록이 자동 보충)")
    print("✅ 완료. 수급 리버설 팩터는 이력 60일+ 누적 후 large_score 관측 컬럼으로 배선 예정.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
