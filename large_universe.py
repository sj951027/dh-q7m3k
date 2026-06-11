# -*- coding: utf-8 -*-
"""
large_universe.py — 대형 가치주 트랙 1단계 (LARGE_SCORE_DESIGN §11 로드맵)
==========================================================================
FDR StockListing(KOSPI/KOSDAQ)에서 시가총액·상장주식수를 받아
'시총 상위 유니버스'를 만들고, N 확정을 위한 분포 리포트를 출력한다.

핵심 원칙 (설계 문서 준수):
  - 점수 계산 없음. 수집·랭킹·플래그·리포트만 (관측 우선).
  - 금융주 포함, 과매도 게이트 없음 (설계 §2). 우선주/스팩/리츠/금융/지주는
    '제외'가 아니라 '플래그'만 단다 (매직넘버 금지, §5).
  - v3 테이블(stage1/2/3, runs)·코드 무접촉. 새 테이블 large_universe만 생성.
  - 재실행 멱등: 같은 (market, run_id)는 삭제 후 재적재 (accumulate_history 방식).
  - 포인트-인-타임(§8): 매 실행의 시총·주식수를 run_id별로 적재 → 이후 백테스트에서
    '당시' 데이터로 사용 가능. in_universe 컬럼은 일부러 두지 않음 — N 확정 전이며,
    멤버십은 분석 시 rank ≤ N 으로 파생(낡은 플래그 방지).

산출:
  - large_universe_{run_id}.csv  : 전 종목(유효 시총 전부) — N 분포 검토용
  - history.db : large_universe 테이블 (시총 상위 --store-top, 기본 500)

실행 (네트워크 필요 — FDR):
    python large_universe.py                 # run_id=최신 stage3 run, 상위 500 적재
    python large_universe.py --no-db         # CSV만 (DB 미접촉)
    python large_universe.py --store-top 400
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_PATH = Path("history.db")
SECTOR_CACHE = Path("sector_cache.json")
TABLE = "large_universe"

# N 후보 — 분포 리포트에서 컷오프를 같이 보여줄 구간 (확정은 분포 보고 결정)
N_CANDIDATES = (150, 200, 250, 300, 400)

# ------------------------------------------------------------
# 플래그용 키워드 — screener_fdr_v2_6 의 목록을 그대로 재사용(동기화).
# 단, v3와 달리 '제외'가 아니라 '플래그'에만 쓴다.
# import 실패(예: FDR 미설치 환경에서의 오프라인 검증) 시 아래 사본으로 폴백.
# ------------------------------------------------------------
try:
    from screener_fdr_v2_6 import (
        FINANCIAL_KEYWORDS, REIT_KEYWORDS, SPAC_KEYWORDS, KNOWN_FINANCIAL_TICKERS,
    )
except Exception:
    FINANCIAL_KEYWORDS = [
        '금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드',
        '손해보험', '생명', '화재', '저축', '여신', '신탁',
    ]
    REIT_KEYWORDS = ['리츠', 'REIT', '부동산투자']
    SPAC_KEYWORDS = ['스팩', 'SPAC']
    KNOWN_FINANCIAL_TICKERS = {'055550', '001450'}

HOLDING_KEYWORDS = ['지주', '홀딩스']   # 설계 §5: 지주/물적분할 플래그(이름 기반 v1)


# ============================================================
# 수집 (네트워크 — 사용자 PC에서만 동작)
# ============================================================
def fetch_listing():
    """KOSPI + KOSDAQ StockListing을 합쳐 반환. Marcap 없으면 즉시 실패(거래대금 폴백 금지)."""
    import FinanceDataReader as fdr   # 지연 import — 오프라인 검증에서 이 함수만 안 쓰면 됨

    frames = []
    for market in ('KOSPI', 'KOSDAQ'):
        print(f"   • fdr.StockListing('{market}') 시도...")
        df = fdr.StockListing(market)
        if df is None or len(df) < 100:
            raise RuntimeError(f"{market} StockListing 결과가 비정상(행수 {0 if df is None else len(df)})")

        code_col = next((c for c in ['Code', 'Symbol'] if c in df.columns), None)
        name_col = 'Name' if 'Name' in df.columns else None
        # 주의: 시총은 Marcap/MarketCap만 인정. 'Amount'(거래대금) 폴백은 유니버스를 망치므로 금지.
        marcap_col = next((c for c in ['Marcap', 'MarketCap'] if c in df.columns), None)
        stocks_col = next((c for c in ['Stocks', 'Shares'] if c in df.columns), None)
        close_col = 'Close' if 'Close' in df.columns else None
        if not (code_col and name_col and marcap_col):
            raise RuntimeError(
                f"{market}: 필수 컬럼 누락 (Code/Name/Marcap). 보유 컬럼={list(df.columns)[:12]}"
            )

        out = pd.DataFrame({
            'ticker': df[code_col].astype(str).str.zfill(6),
            'name': df[name_col].astype(str),
            'close': pd.to_numeric(df[close_col], errors='coerce') if close_col else float('nan'),
            'marcap': pd.to_numeric(df[marcap_col], errors='coerce'),
            'stocks': pd.to_numeric(df[stocks_col], errors='coerce') if stocks_col else float('nan'),
            'market': market.lower(),
        })
        print(f"   ✓ {market}: {len(out)}개 (시총 컬럼={marcap_col})")
        frames.append(out)
    return pd.concat(frames, ignore_index=True)


# ============================================================
# 가공 (순수 로직 — 오프라인 검증 대상)
# ============================================================
def _flag_name(name, keywords):
    s = str(name) if name is not None else ''
    su = s.upper()
    return int(any(kw in s or kw in su for kw in keywords))


def load_sector_map(path=SECTOR_CACHE):
    """sector_cache.json이 있으면 무료(네트워크 0)로 업종 채움. 없으면 빈 dict.
    주의: 캐시는 v3 유니버스 기반이라 금융·우선주는 '미분류'가 정상(현재 데이터 갭)."""
    try:
        import json
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
        return {str(k).zfill(6): str(v) for k, v in raw.items()}
    except Exception:
        return {}


def build_universe(listing, sector_map=None):
    """정제 + 플래그 + 시총 랭킹. 어떤 종목도 '제외'하지 않는다(유효 시총 없는 행만 탈락)."""
    sector_map = sector_map or {}
    df = listing.copy()

    n_raw = len(df)
    df = df.drop_duplicates(subset=['ticker'], keep='first')
    df = df[df['marcap'].notna() & (df['marcap'] > 0)].copy()
    n_drop = n_raw - len(df)
    if n_drop:
        print(f"   • 정제: 중복/무효시총 {n_drop}개 제외 (유효 {len(df)}개)")

    df['is_pref'] = (~df['ticker'].str.endswith('0')).astype(int)          # 우선주(종목코드 끝자리≠0)
    df['is_spac'] = df['name'].map(lambda n: _flag_name(n, SPAC_KEYWORDS))
    df['is_reit'] = df['name'].map(lambda n: _flag_name(n, REIT_KEYWORDS))
    df['is_holding'] = df['name'].map(lambda n: _flag_name(n, HOLDING_KEYWORDS))
    df['is_financial'] = (
        df['ticker'].isin(KNOWN_FINANCIAL_TICKERS)
        | df['name'].map(lambda n: bool(_flag_name(n, FINANCIAL_KEYWORDS)))
    ).astype(int)
    df['sector'] = df['ticker'].map(sector_map).fillna('미분류')

    # 양 시장 합산 시총 랭킹 (설계 §2: '시가총액 상위 N' — 시장 구분 없이)
    df = df.sort_values('marcap', ascending=False).reset_index(drop=True)
    df['marcap_rank'] = range(1, len(df) + 1)
    return df


def report_distribution(df, n_candidates=N_CANDIDATES):
    """N 확정을 위한 분포 리포트. 점수·판단 없음, 사실만 출력."""
    print("\n" + "=" * 64)
    print("📊 시총 유니버스 분포 리포트 (N 확정용)")
    print("=" * 64)
    total_marcap = df['marcap'].sum()
    print(f"유효 종목 {len(df)}개 · 합산 시총 {total_marcap / 1e12:,.0f}조원")
    for mkt, g in df.groupby('market'):
        print(f"  - {mkt}: {len(g)}개, {g['marcap'].sum() / 1e12:,.0f}조원")

    print(f"\n{'N':>5} | {'컷오프시총(억)':>12} | {'코스닥':>5} | {'우선주':>5} | "
          f"{'금융':>4} | {'지주':>4} | {'리츠':>4} | {'스팩':>4} | {'누적시총비중':>8}")
    for n in n_candidates:
        if n > len(df):
            continue
        top = df.head(n)
        print(f"{n:>5} | {top['marcap'].iloc[-1] / 1e8:>12,.0f} | "
              f"{(top['market'] == 'kosdaq').sum():>5} | {top['is_pref'].sum():>5} | "
              f"{top['is_financial'].sum():>4} | {top['is_holding'].sum():>4} | "
              f"{top['is_reit'].sum():>4} | {top['is_spac'].sum():>4} | "
              f"{top['marcap'].sum() / total_marcap:>7.1%}")

    top500 = df.head(500)
    matched = (top500['sector'] != '미분류').sum()
    print(f"\n업종 캐시 매칭(상위 500): {matched}/{len(top500)}개"
          f"  ← 금융·우선주는 v3 캐시에 없어 미분류가 정상(추후 rebuild_sectors 확장으로 해소)")
    print("\n시총 상위 10:")
    for _, r in df.head(10).iterrows():
        flags = ''.join([
            '우' if r['is_pref'] else '', '金' if r['is_financial'] else '',
            '持' if r['is_holding'] else '',
        ])
        print(f"  {r['marcap_rank']:>3}. {r['name']}({r['ticker']}) "
              f"{r['marcap'] / 1e12:,.1f}조 {flags}")
    print("=" * 64)


# ============================================================
# 저장 (CSV 전 종목 + DB 상위 store_top)
# ============================================================
def default_run_id(db_path=DB_PATH):
    """기본 run_id = history.db의 최신 stage3_final run (catalyst_insider와 동일 규칙)."""
    try:
        with sqlite3.connect(db_path) as con:
            rid = con.execute("SELECT MAX(run_id) FROM stage3_final").fetchone()[0]
        if rid:
            return str(rid)
    except Exception:
        pass
    return datetime.now().strftime("%Y%m%d")


def save_csv(df, run_id):
    out = Path(f"large_universe_{run_id}.csv")
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"\n💾 CSV 저장: {out} ({len(df)}행 — 전 종목)")
    return out


def save_db(df, run_id, db_path=DB_PATH, store_top=500):
    """large_universe 테이블에 상위 store_top 적재. 같은 run_id는 삭제 후 재적재(멱등).
    v3 테이블에는 어떤 쿼리도 날리지 않는다(읽기 포함 — 이 함수 한정)."""
    keep = df.head(store_top).copy()
    keep.insert(0, 'run_id', str(run_id))
    keep.insert(1, 'run_timestamp', datetime.now().strftime("%Y%m%d_%H%M"))

    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
        )
        if cur.fetchone():
            cur.execute(f"DELETE FROM {TABLE} WHERE run_id=?", (str(run_id),))
            con.commit()
        keep.to_sql(TABLE, con, if_exists='append', index=False)
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_large_universe_rt ON {TABLE}(run_id, ticker)"
        )
        con.commit()
        n = cur.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE run_id=?", (str(run_id),)).fetchone()[0]
    print(f"💾 DB 적재: {TABLE} run_id={run_id} {n}행 (시총 상위 {store_top})")
    return n


# ============================================================
def main():
    ap = argparse.ArgumentParser(description="대형 가치주 트랙 1단계 — 시총 유니버스 생성")
    ap.add_argument("--run-id", default=None, help="기본: 최신 stage3 run(history.db), 없으면 오늘")
    ap.add_argument("--store-top", type=int, default=500,
                    help="DB에 적재할 시총 상위 개수(기본 500 — N 후보 최대 400 + 버퍼)")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--no-db", action="store_true", help="CSV/리포트만 (DB 미접촉)")
    args = ap.parse_args()

    print("=" * 64)
    print("🏛️  대형 가치주 트랙 — 1단계: 시총 유니버스 (관측·수집 전용, 점수 없음)")
    print("=" * 64)

    run_id = args.run_id or default_run_id(Path(args.db))
    today = datetime.now().strftime("%Y%m%d")
    if run_id != today:
        print(f"⚠️  run_id={run_id} ≠ 오늘({today}) — 시총은 '지금' 기준이므로 "
              f"비거래일 직후가 아니면 --run-id 확인 권장")

    listing = fetch_listing()
    df = build_universe(listing, load_sector_map())
    report_distribution(df)
    save_csv(df, run_id)
    if not args.no_db:
        save_db(df, run_id, Path(args.db), args.store_top)

    print("\n✅ 유니버스 적재 완료. 분석 유니버스는 rank≤300으로 파생(확정 N=300).")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
