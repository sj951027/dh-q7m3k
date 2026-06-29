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
# 전체 종목 유니버스(--universe all)는 ohlcv.db(레포 밖)의 종목 목록을 사용.
# 수급/공매도 저장은 여전히 history.db(점수 코드 호환). raw 분석은 §21-8 참고.
OHLCV_DB = Path("..") / "dh-q7m3k-data" / "ohlcv.db"
TOKEN_CACHE = Path("kis_token.json")
BASE = "https://openapi.koreainvestment.com:9443"      # 실전투자 도메인 (조회)
TR_INVESTOR = "FHKST01010900"                          # 주식현재가 투자자(일별) — 구버전(보존)
# [v1.1.0] 종목별 투자자매매동향(일별): 기관을 연기금·투신·증권·사모·보험·은행으로 세분.
#   한 번 호출에 ~30거래일 윈도(output2)를 돌려줌(기존 inquire-investor와 동일 패턴).
#   외인/기관계/개인 필드명도 동일(frgn/orgn/prsn_ntby_qty) → 기존 컬럼 0-diff 호환.
TR_INVESTOR_DETAIL = "FHPTJ04160001"
USE_DETAIL = True                                      # True=세부API(연기금 포함). False=구버전 폴백.

# 세부 투자자 추가 컬럼(daily_flows 에 ALTER 로 자동 추가). 기금=연기금등.
#   {DB컬럼: (수량 API키, 대금 API키)}
DETAIL_COLS = {
    "pension_net_qty": ("fund_ntby_qty",   "fund_ntby_tr_pbmn"),   # 연기금등(기금)
    "trust_net_qty":   ("ivtr_ntby_qty",   "ivtr_ntby_tr_pbmn"),   # 투자신탁(투신)
    "secfirm_net_qty": ("scrt_ntby_qty",   "scrt_ntby_tr_pbmn"),   # 금융투자(증권)
    "prveq_net_qty":   ("pe_fund_ntby_vol", "pe_fund_ntby_tr_pbmn"), # 사모펀드
    "insu_net_qty":    ("insu_ntby_qty",   "insu_ntby_tr_pbmn"),   # 보험
    "bank_net_qty":    ("bank_ntby_qty",   "bank_ntby_tr_pbmn"),   # 은행
}
# 대금 컬럼은 _qty → _val 로 파생(아래 parse 에서 함께 채움)
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
# 세부 투자자 컬럼(수량+대금). 기존 테이블엔 ensure_table 이 ALTER 로 추가.
DETAIL_DDL_COLS = []
for _q in DETAIL_COLS:
    DETAIL_DDL_COLS.append(_q)                  # *_net_qty
    DETAIL_DDL_COLS.append(_q.replace("_net_qty", "_net_val"))  # *_net_val


# ============================================================
# 공매도 / 신용 / 대차 (별도 테이블 short_flows — daily_flows 와 분리)
# ============================================================
# [v1.2.0] 공매도(기본 ON)·신용(--with-credit)·대차(--with-loan) 관측 적재.
#   셋은 각각 별도 KIS API → 종목당 호출 수 = 켠 API 수. 공매도+연기금 기본 ~9분.
#   데이터 성격이 투자자 수급과 달라 별도 테이블에 저장(daily_flows 0-diff 보존).
SHORT_API = dict(tr="FHPST04830000",
                 url="/uapi/domestic-stock/v1/quotations/daily-short-sale", out="output2")
CREDIT_API = dict(tr="FHPST04760000",
                  url="/uapi/domestic-stock/v1/quotations/daily-credit-balance",
                  out="output", scr="20476")
LOAN_API = dict(tr="HHPST074500C0",
                url="/uapi/domestic-stock/v1/quotations/daily-loan-trans", out="output1")

SHORT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS short_flows (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,
    short_qty REAL, short_vol_ratio REAL, short_val REAL,
    credit_bal_qty REAL, credit_bal_amt REAL, credit_bal_rate REAL,
    loan_bal_qty REAL, loan_bal_amt REAL, loan_chg REAL,
    fetched_at TEXT,
    PRIMARY KEY (ticker, date)
)
"""
SHORT_COLS = ["short_qty", "short_vol_ratio", "short_val",
              "credit_bal_qty", "credit_bal_amt", "credit_bal_rate",
              "loan_bal_qty", "loan_bal_amt", "loan_chg"]


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
        # 세부 투자자(연기금 등) — 세부 API 응답에만 존재. 구버전 응답엔 키가 없어 None(무해).
        for db_qty, (api_qty, api_val) in DETAIL_COLS.items():
            db_val = db_qty.replace("_net_qty", "_net_val")
            row[db_qty] = pick(api_qty)
            row[db_val] = pick(api_val)
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
    # 세부 투자자 컬럼 자가치유: 기존 daily_flows 에 없으면 ALTER 로 추가(있으면 skip).
    #   accumulate_history.write_to_sqlite 와 동일한 안전 패턴. 기존 행은 NULL 로 남음(무해).
    existing = {r[1] for r in con.execute("PRAGMA table_info(daily_flows)")}
    for col in DETAIL_DDL_COLS:
        if col not in existing:
            con.execute(f'ALTER TABLE daily_flows ADD COLUMN "{col}" REAL')
    con.commit()


def upsert_flows(con, ticker, rows):
    """INSERT OR REPLACE. 반환 (신규 날짜 수, 재기록 수). 행이 없으면 (0,0) — 에러 미저장.
    기존 9컬럼 + 세부 투자자 컬럼을 동적으로 구성(누락/순서 오류 방지)."""
    if not rows:
        return 0, 0
    have = {d for (d,) in con.execute(
        "SELECT date FROM daily_flows WHERE ticker=?", (ticker,))}
    new = sum(1 for r in rows if r['date'] not in have)
    base_cols = ['date', 'close', 'person_net_qty', 'foreign_net_qty', 'inst_net_qty',
                 'person_net_val', 'foreign_net_val', 'inst_net_val', 'fetched_at']
    cols = base_cols + DETAIL_DDL_COLS                 # 세부 컬럼 뒤에 append
    placeholders = ",".join(["?"] * (len(cols) + 1))   # +1 = ticker
    col_sql = ",".join(['ticker'] + [f'"{c}"' for c in cols])
    con.executemany(
        f"INSERT OR REPLACE INTO daily_flows ({col_sql}) VALUES ({placeholders})",
        [tuple([ticker] + [r.get(c) for c in cols]) for r in rows])
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


def load_lowvol_tickers(db_path=DB_PATH, run_id=None):
    """lv_a 유니버스: stage3 최신 run 과매도 30~70 + 유동성 5억(LOWVOL §2)."""
    with sqlite3.connect(db_path) as con:
        rid = run_id or con.execute("SELECT MAX(run_id) FROM stage3_final").fetchone()[0]
        rows = con.execute(
            'SELECT ticker, name FROM stage3_final '
            'WHERE run_id=? AND oversold_score>=30 AND oversold_score<70 '
            'AND "amt_avg_1m_억">=5 ORDER BY "amt_avg_1m_억" DESC',
            (str(rid),)).fetchall()
    return str(rid), rows


def load_combined_tickers(db_path=DB_PATH, top=None):
    """large(대형 시총상위) + lv_a(중소형 과매도) 합집합, 종목 중복 제거.
    연기금은 대형주 현상이라 large 가 주력이지만, 공매도는 중소형(lv_a)에서도
    신호 가능성이 있어 두 유니버스를 합쳐 한 번에 받는다."""
    lrid, large = load_universe_tickers(db_path, None, top)
    srid, lowvol = load_lowvol_tickers(db_path, None)
    seen, merged = set(), []
    for tk, name in list(large) + list(lowvol):   # large 우선(시총순), 그다음 lv_a
        if tk not in seen:
            seen.add(tk)
            merged.append((tk, name))
    return f"large{lrid}+lv{srid}", merged


def load_all_tickers(ohlcv_path=OHLCV_DB):
    """ohlcv.db(전체 종목 raw)에서 활발 거래 전체 종목을 유니버스로.
    수급/공매도를 전체 KOSPI/KOSDAQ 으로 확장(§21-8 — KIS는 과거 못 받으니 일찍 넓게).
    저장은 history.db 그대로(점수 코드 호환). 최신일 거래정지 종목(죽은 종목)은 제외.
    name 은 ohlcv 에 없으므로 ticker 로 대체(수급 적재엔 name 불필요)."""
    if not Path(ohlcv_path).exists():
        raise RuntimeError(
            f"ohlcv.db 없음({ohlcv_path}) — universe_ohlcv.py 로 먼저 적재 필요")
    with sqlite3.connect(ohlcv_path) as con:
        latest = con.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()[0]
        rows = con.execute(
            """SELECT ticker FROM daily_ohlcv
               WHERE date=? AND is_suspended=0 AND close IS NOT NULL
               ORDER BY close*COALESCE(shares,0) DESC""",
            (latest,)).fetchall()
    tickers = [(r[0], r[0]) for r in rows]   # (ticker, name=ticker)
    return f"all_ohlcv_{latest}", tickers


# ============================================================
# KIS 호출 (네트워크 — 사용자 PC 전용)
# ============================================================
def fetch_investor(ticker, token, app_key, app_secret):
    """구버전: 주식현재가 투자자(일별). output 1개 키. 외인/기관/개인만. (폴백·보존)"""
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


def fetch_investor_detail(ticker, token, app_key, app_secret, date):
    """[v1.1.0] 종목별 투자자매매동향(일별). 일자별 데이터는 output2(~30거래일).
    외인/기관계/개인 + 연기금 등 세부. date=기준일(YYYYMMDD), 그날 포함 과거 윈도 반환."""
    import requests
    r = requests.get(
        f"{BASE}/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily",
        headers={"content-type": "application/json",
                 "authorization": f"Bearer {token}",
                 "appkey": app_key, "appsecret": app_secret,
                 "tr_id": TR_INVESTOR_DETAIL, "custtype": "P"},
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": date, "FID_ORG_ADJ_PRC": "", "FID_ETC_CLS_CODE": ""},
        timeout=10)
    j = r.json()
    if j.get("rt_cd") not in (None, "0"):
        raise RuntimeError(f"rt_cd={j.get('rt_cd')} {j.get('msg1', '')}".strip())
    # 일자별 세부는 output2. (output1 은 현재가 요약 — 사용 안 함)
    return j.get("output2") or []


def fetch_rows(ticker, token, app_key, app_secret, date):
    """USE_DETAIL 스위치에 따라 세부/구버전 호출. parse_rows 에 넘길 list[dict] 반환."""
    if USE_DETAIL:
        return fetch_investor_detail(ticker, token, app_key, app_secret, date)
    return fetch_investor(ticker, token, app_key, app_secret)


# ── 공매도/신용/대차 (short_flows) ─────────────────────────
def ensure_short_table(con):
    con.execute(SHORT_TABLE_SQL)
    existing = {r[1] for r in con.execute("PRAGMA table_info(short_flows)")}
    for col in SHORT_COLS:
        if col not in existing:
            con.execute(f'ALTER TABLE short_flows ADD COLUMN "{col}" REAL')
    con.commit()


def parse_short(rows):
    """공매도 output2 → {date: {필드}}."""
    out = {}
    for r in rows or []:
        d = str(r.get('stck_bsop_date') or '').strip()
        if len(d) == 8 and d.isdigit():
            out[d] = {'short_qty': _num(r.get('ssts_cntg_qty')),
                      'short_vol_ratio': _num(r.get('ssts_vol_rlim')),
                      'short_val': _num(r.get('ssts_tr_pbmn'))}
    return out


def parse_credit(rows):
    """신용 output → {date: {필드}}. 날짜키 deal_date."""
    out = {}
    for r in rows or []:
        d = str(r.get('deal_date') or '').strip()
        if len(d) == 8 and d.isdigit():
            out[d] = {'credit_bal_qty': _num(r.get('whol_loan_rmnd_stcn')),
                      'credit_bal_amt': _num(r.get('whol_loan_rmnd_amt')),
                      'credit_bal_rate': _num(r.get('whol_loan_rmnd_rate'))}
    return out


def parse_loan(rows):
    """대차 output1 → {date: {필드}}. 날짜키 bsop_date."""
    out = {}
    for r in rows or []:
        d = str(r.get('bsop_date') or '').strip()
        if len(d) == 8 and d.isdigit():
            out[d] = {'loan_bal_qty': _num(r.get('rmnd_stcn')),
                      'loan_bal_amt': _num(r.get('rmnd_amt')),
                      'loan_chg': _num(r.get('prdy_rmnd_vrss'))}
    return out


def _merge_by_date(*dicts):
    """{date:{col:val}} 여러 개 → 날짜 합집합 병합."""
    all_dates = set()
    for d in dicts:
        all_dates |= set(d.keys())
    return {dt: {k: v for d in dicts for k, v in d.get(dt, {}).items()}
            for dt in all_dates}


def _get_short(url, tr, token, ak, sk, params):
    import requests
    r = requests.get(f"{BASE}{url}",
                     headers={"content-type": "application/json",
                              "authorization": f"Bearer {token}",
                              "appkey": ak, "appsecret": sk,
                              "tr_id": tr, "custtype": "P"},
                     params=params, timeout=10)
    j = r.json()
    if j.get("rt_cd") not in (None, "0"):
        raise RuntimeError(f"rt_cd={j.get('rt_cd')} {j.get('msg1', '')}".strip())
    return j


def collect_short(ticker, token, ak, sk, d1, d2, with_credit, with_loan):
    """한 종목 공매도(+옵션 신용·대차) → 날짜별 병합 dict.
    어느 단계 실패인지 구분되도록 단계명을 예외에 실어 올린다."""
    parts = []
    try:
        j = _get_short(SHORT_API["url"], SHORT_API["tr"], token, ak, sk,
                       {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker,
                        "FID_INPUT_DATE_1": d1, "FID_INPUT_DATE_2": d2})
        parts.append(parse_short(j.get(SHORT_API["out"]) or []))
    except Exception as e:
        raise RuntimeError(f"공매도:{e}")
    if with_credit:
        try:
            # 신용은 FID_INPUT_DATE_1(결제일자) 필수. d2(최근일) 기준 과거 30건.
            #   결제일 기준이라 최근 1~2거래일은 비어 올 수 있음(정상).
            j = _get_short(CREDIT_API["url"], CREDIT_API["tr"], token, ak, sk,
                           {"FID_COND_MRKT_DIV_CODE": "J",
                            "FID_COND_SCR_DIV_CODE": CREDIT_API["scr"],
                            "FID_INPUT_ISCD": ticker,
                            "FID_INPUT_DATE_1": d2})
            parts.append(parse_credit(j.get(CREDIT_API["out"]) or []))
        except Exception as e:
            raise RuntimeError(f"신용:{e}")
    if with_loan:
        try:
            # 대차 조회구분 "3"(종목코드 기반) — 코스피/코스닥 무관하게 종목으로.
            # CTS=연속조회 키(첫 조회는 빈값 필수).
            j = _get_short(LOAN_API["url"], LOAN_API["tr"], token, ak, sk,
                           {"MRKT_DIV_CLS_CODE": "3", "MKSC_SHRN_ISCD": ticker,
                            "START_DATE": d1, "END_DATE": d2, "CTS": ""})
            parts.append(parse_loan(j.get(LOAN_API["out"]) or []))
        except Exception as e:
            raise RuntimeError(f"대차:{e}")
    return _merge_by_date(*parts)


def upsert_short(con, ticker, by_date, fetched_at):
    """short_flows 적재. 반환 (신규, 재기록)."""
    if not by_date:
        return 0, 0
    have = {d for (d,) in con.execute(
        "SELECT date FROM short_flows WHERE ticker=?", (ticker,))}
    new = sum(1 for d in by_date if d not in have)
    cols = ["date"] + SHORT_COLS + ["fetched_at"]
    placeholders = ",".join(["?"] * (len(cols) + 1))
    col_sql = ",".join(['ticker'] + [f'"{c}"' for c in cols])
    payload = [tuple([ticker, dt] + [vals.get(c) for c in SHORT_COLS] + [fetched_at])
               for dt, vals in by_date.items()]
    con.executemany(
        f"INSERT OR REPLACE INTO short_flows ({col_sql}) VALUES ({placeholders})", payload)
    con.commit()
    return new, len(by_date) - new


def run_short_phase(con, tickers, token, ak, sk, sleep, days, with_credit, with_loan):
    """공매도(+옵션) 적재 단계. main 의 연기금 적재 뒤에 이어서 호출."""
    from datetime import timedelta
    today = datetime.now()
    d2 = today.strftime("%Y%m%d")
    d1 = (today - timedelta(days=days * 2 + 10)).strftime("%Y%m%d")
    ensure_short_table(con)
    apis = "공매도" + ("·신용" if with_credit else "") + ("·대차" if with_loan else "")
    per = 1 + int(with_credit) + int(with_loan)
    print("=" * 64)
    print(f"📉 {apis} 적재 — {len(tickers)}종목 · 종목당 {per}회 · "
          f"예상 ~{len(tickers) * per * sleep / 60:.1f}분")
    print("=" * 64)
    fetched_at = today.strftime("%Y%m%d_%H%M")
    n_new = n_rep = n_fail = 0
    t0 = time.time()
    for i, (tk, name) in enumerate(tickers, 1):
        time.sleep(sleep)
        try:
            by_date = collect_short(tk, token, ak, sk, d1, d2, with_credit, with_loan)
            a, b = upsert_short(con, tk, by_date, fetched_at)
            n_new += a
            n_rep += b
        except Exception as e:
            n_fail += 1
            if n_fail <= 5:
                print(f"   ⚠️  {name}({tk}) 공매도 실패: {str(e)[:70]}")
        if i % 100 == 0 or i == len(tickers):
            el = time.time() - t0
            print(f"   [{i}/{len(tickers)}] {el:.0f}s · 신규 {n_new} · 재기록 {n_rep} · 실패 {n_fail}")
    total, days_n = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT date) FROM short_flows").fetchone()
    print(f"💾 short_flows 누적: {total:,}행 · 거래일 {days_n}일"
          + (f" · 실패 {n_fail}(다음 실행 보충)" if n_fail else ""))


def run_verify(con, tickers, token, app_key, app_secret, date, limit):
    """검증 모드: 새 세부 API 의 외인/기관/개인 값이 기존 daily_flows 와 일치하는지 대조.
    DB 에 쓰지 않는다. INSERT OR REPLACE 로 기존 값을 덮기 전에 '같은 숫자인가'를 확인하는 안전장치.
    세부 API 가 다른 숫자를 주면(예: 잠정/확정 차이) 여기서 불일치로 드러나 오염을 막는다."""
    print("=" * 64)
    print(f"🔎 검증 모드 — 새 세부 API vs 기존 daily_flows (상위 {limit}종목, DB 미기록)")
    print(f"   기준일 {date} · 외인/기관/개인 net_qty 가 같은 날짜에서 일치하는지 대조")
    print("=" * 64)
    checked = match = mismatch = nodata = 0
    examples = []
    for tk, name in tickers[:limit]:
        time.sleep(KIS_REQ_INTERVAL)
        try:
            rows = parse_rows(fetch_investor_detail(tk, token, app_key, app_secret, date),
                              datetime.now().strftime("%Y%m%d_%H%M"))
        except Exception as e:
            print(f"   ⚠️  {name}({tk}) 호출 실패: {str(e)[:70]}")
            continue
        new_by_date = {r['date']: r for r in rows}
        # 기존 DB 의 같은 종목 행
        old = con.execute(
            "SELECT date, foreign_net_qty, inst_net_qty, person_net_qty "
            "FROM daily_flows WHERE ticker=?", (tk,)).fetchall()
        if not old:
            nodata += 1
            continue
        for d, of, oi, op in old:
            nr = new_by_date.get(d)
            if nr is None:
                continue  # 새 윈도에 없는 과거 날짜는 스킵
            checked += 1
            # 부동소수 안전 비교(정수 수량이라 1주 이내면 동일로 간주)
            def eq(a, b):
                if a is None or b is None:
                    return a is None and b is None
                return abs(a - b) < 1.0
            if eq(of, nr['foreign_net_qty']) and eq(oi, nr['inst_net_qty']) and eq(op, nr['person_net_qty']):
                match += 1
            else:
                mismatch += 1
                if len(examples) < 8:
                    examples.append(
                        f"     {name}({tk}) {d}: 외인 기존{of}/신{nr['foreign_net_qty']} "
                        f"기관 기존{oi}/신{nr['inst_net_qty']}")
    print(f"\n[검증 결과] 대조 {checked}건 · 일치 {match} · 불일치 {mismatch} · DB무종목 {nodata}")
    if examples:
        print("  불일치 예시:")
        for e in examples:
            print(e)
    print()
    if checked == 0:
        print("⚠️  대조할 겹치는 날짜가 없음 — --date 를 기존 데이터(최근) 범위로 맞춰 재시도.")
    elif mismatch == 0:
        print("✅ 외인/기관/개인 값 100% 일치 — 새 API 로 교체해도 기존 컬럼 0-diff. 안전.")
        print("   이제 --verify 없이 정상 실행하면 연기금 등 세부 컬럼이 추가 적재된다.")
    else:
        rate = 100 * mismatch / checked
        print(f"❌ 불일치 {rate:.1f}% — 두 API 가 다른 숫자를 줌. 교체 보류 권장.")
        print("   원인 후보: 잠정치 vs 확정치, 수정주가 기준 차이. 위 예시를 Claude 에게 전달.")
    return mismatch == 0 and checked > 0


def main():
    ap = argparse.ArgumentParser(description="KIS 일별 투자자 수급 증분 적재(조회 전용)")
    ap.add_argument("--run-id", default=None, help="유니버스 run (기본: large_universe 최신)")
    ap.add_argument("--universe", choices=["large", "combined", "all"], default="combined",
                    help="종목 출처: large(대형500만) / combined(large+lv_a, 기본) / "
                         "all(ohlcv.db 전체 KOSPI·KOSDAQ ~2645)")
    ap.add_argument("--top", type=int, default=None, help="시총 상위 N만 (기본: 적재분 전체=500)")
    ap.add_argument("--sleep", type=float, default=KIS_REQ_INTERVAL)
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--date", default=None,
                    help="세부 API 기준일 YYYYMMDD (기본: 오늘). 그날 포함 과거 ~30거래일 윈도 반환")
    ap.add_argument("--verify", type=int, default=0, metavar="N",
                    help="검증 모드: 상위 N종목만 받아 기존 daily_flows 의 외인/기관 값과 "
                         "대조만 하고 DB 기록 안 함. 첫 실전 전 0-diff 확인용")
    ap.add_argument("--no-short", action="store_true",
                    help="공매도 적재 건너뛰기(연기금 수급만). 기본은 공매도까지 적재")
    ap.add_argument("--with-credit", action="store_true",
                    help="공매도 단계에 신용잔고도 추가(호출 +1/종목)")
    ap.add_argument("--with-loan", action="store_true",
                    help="공매도 단계에 대차잔고도 추가(호출 +1/종목)")
    ap.add_argument("--short-days", type=int, default=40,
                    help="공매도/대차 조회 기간(일). 기본 40")
    args = ap.parse_args()

    load_env()
    app_key = os.environ.get("KIS_APP_KEY", "").strip()
    app_secret = os.environ.get("KIS_APP_SECRET", "").strip()
    if not (app_key and app_secret):
        raise SystemExit("❌ .env 의 KIS_APP_KEY / KIS_APP_SECRET 확인")

    if args.universe == "all":
        rid, tickers = load_all_tickers()
    elif args.universe == "combined":
        rid, tickers = load_combined_tickers(Path(args.db), args.top)
    else:
        rid, tickers = load_universe_tickers(Path(args.db), args.run_id, args.top)
    date = args.date or datetime.now().strftime("%Y%m%d")   # 세부 API 기준일

    token = get_token(app_key, app_secret)
    con = sqlite3.connect(args.db)
    ensure_table(con)

    # 검증 모드: DB 에 쓰지 않고 기존 값과 대조만.
    if args.verify > 0:
        run_verify(con, tickers, token, app_key, app_secret, date, args.verify)
        # 공매도(+옵션)도 같이 켰으면 필드 확인
        if not args.no_short:
            from datetime import timedelta
            d2 = datetime.now().strftime("%Y%m%d")
            d1 = (datetime.now() - timedelta(days=args.short_days * 2 + 10)).strftime("%Y%m%d")
            print("\n" + "=" * 64)
            print(f"🔎 공매도 필드 확인 (상위 {min(args.verify,5)}종목)")
            print("=" * 64)
            for tk, name in tickers[:min(args.verify, 5)]:
                time.sleep(args.sleep)
                try:
                    bd = collect_short(tk, token, app_key, app_secret, d1, d2,
                                       args.with_credit, args.with_loan)
                except Exception as e:
                    print(f"   ⚠️  {name}({tk}) 실패: {str(e)[:60]}")
                    continue
                if not bd:
                    print(f"   {name}({tk}): 데이터 없음")
                    continue
                ds = sorted(bd.keys(), reverse=True)
                v = bd[ds[0]]
                n_credit = sum(1 for d in bd if bd[d].get('credit_bal_qty') is not None)
                n_loan = sum(1 for d in bd if bd[d].get('loan_bal_qty') is not None)
                cd = next((d for d in ds if bd[d].get('credit_bal_qty') is not None), None)
                cval = bd[cd].get('credit_bal_qty') if cd else None
                print(f"   {name}({tk}) {len(ds)}일: 공매도={v.get('short_qty')} "
                      f"비중={v.get('short_vol_ratio')}% 대차={v.get('loan_bal_qty')}")
                print(f"      └ 융자 {n_credit}일(최근 {cd}={cval}) · 대차 {n_loan}일"
                      if cd else f"      └ 융자 0일 · 대차 {n_loan}일")
        con.close()
        return

    mode = "세부(연기금 포함)" if USE_DETAIL else "구버전(외인/기관만)"
    print("=" * 64)
    print(f"🏛️  KIS 일별 투자자 수급 적재 — 유니버스 run {rid}, {len(tickers)}종목 · {mode}")
    print(f"   기준일 {date} · 간격 {args.sleep}s · 예상 ~{len(tickers) * args.sleep / 60:.1f}분")
    print("=" * 64)

    fetched_at = datetime.now().strftime("%Y%m%d_%H%M")
    n_new = n_rep = n_fail = 0
    t0 = time.time()
    for i, (tk, name) in enumerate(tickers, 1):
        time.sleep(args.sleep)
        try:
            rows = parse_rows(fetch_rows(tk, token, app_key, app_secret, date), fetched_at)
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
    print(f"\n💾 daily_flows 누적: {total:,}행 · 거래일 {days}일")
    if n_fail:
        print(f"   (실패 {n_fail}종목은 저장 안 함 — 내일 윈도 재기록이 자동 보충)")
    print("✅ 연기금 등 세부 수급 적재 완료.")

    # 공매도(+옵션 신용·대차) 단계 — 같은 토큰·유니버스 재사용. 기본 ON.
    if not args.no_short:
        print()
        run_short_phase(con, tickers, token, app_key, app_secret,
                        args.sleep, args.short_days, args.with_credit, args.with_loan)

    con.close()
    print("\n✅ 전체 완료. 수급·공매도는 관측 적재 — 검증 후에만 활용(점수 미투입).")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
