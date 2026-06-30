#!/usr/bin/env python3
"""
[V2.6] 1단계: 과매도 스크리너 (KOSPI / KOSDAQ 통합)
=============================================================
시장별 파라미터를 MARKET_CONFIG로 분리한 단일 스크리너.
  python screener_fdr_v2_6.py --market kospi
  python screener_fdr_v2_6.py --market kosdaq
  (인자 없으면 환경변수 V2_INPUT_MARKET, 그것도 없으면 kospi)

기능:
  ⑬ 원/달러 환율(USD/KRW) 추세를 regime_score에 통합
  ⑭ 외국인 누적 순매수 (시총 상위 10개 종목 합산)
  ⑦ 시장 레짐 필터 (지수 분석: KOSPI=KS11, KOSDAQ=KQ11)
  • 네이버 금융 외국인/기관 수급 크롤링
  • 추세 전환 신호, 떨어지는 칼날 방어, 매집/거래량, 금융주·리츠(·코스닥 스팩) 제외

  최종 regime_score = 지수 점수 + 환율 점수 + 외인 점수

[시장별 튜닝 — MARKET_CONFIG]
  코스닥은 변동성↑·외인비중↓·수출주↓를 반영해 코스피보다 완화:
    • 레짐 페널티   약세 -10→-7, 반등 -5→-3, 조정 -2→-1
    • 환율 페널티   강한약세 -3→-1, 경미 -1→0, 강세 +2→+1
    • 외인 페널티   강한이탈 -3→-2, 이탈 -1→-1, 유입 +2→+1
    • 외인 임계값   -5000/-2000/+3000 → -2500/-1000/+1500 (약 50% 완화)
    • 과매도 최소점  50 → 45
    • 스팩(SPAC) 자동 제외

[출력]
    v2_<market>_oversold_*.csv  (2/3단계와 호환)
    메타 컬럼명은 시장과 무관하게 동일 (regime_kospi_score / kospi_vs_sma200_%
    / foreign_kospi_5d_억 ...) — history.db 스키마 및 하위 단계 호환 유지.
"""

import argparse
import os

import requests
_original_get = requests.get
def _patched_get(*args, **kwargs):
    kwargs.setdefault('timeout', 15)
    return _original_get(*args, **kwargs)
requests.get = _patched_get

import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
import time
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# 공통 설정
# ============================================================
LOOKBACK_DAYS = 400

# ─── Phase 2: 가격 소스를 ohlcv.db 로 (fdr 중복 수집 제거) ───────────────
# analyze_ticker 가 종목별로 fdr.DataReader 하던 것을, ohlcv.db(전체 OHLCV)에서 읽어 재활용.
# 0-diff 보장: ohlcv 도 fdr 로 적재된 수정주가 → verify_ohlcv_screener.py 로 30종목 동일 확인.
# 전제(필수): universe_ohlcv.py 가 스크리너보다 '먼저' 돌아 ohlcv 최신일==오늘 이어야 함.
# 안전망: USE_OHLCV_PRICES=0 (env) 로 끄면 기존 fdr 경로. ohlcv 없거나 종목 결손 시 fdr 폴백.
import os as _os
USE_OHLCV_PRICES = _os.environ.get("USE_OHLCV_PRICES", "1") != "0"
OHLCV_DB_PATH = _os.environ.get(
    "OHLCV_DB", _os.path.join("..", "dh-q7m3k-data", "ohlcv.db"))
_OHLCV_OK = USE_OHLCV_PRICES and _os.path.exists(OHLCV_DB_PATH)


def _read_prices_ohlcv(ticker, from_date, to_date):
    """ohlcv.db 에서 한 종목 OHLCV 를 fdr.DataReader 와 동일 형식으로 반환.
    fdr: index=날짜(Timestamp), cols=Open/High/Low/Close/Volume(대문자).
    실패/결손 시 None → 호출부가 fdr 폴백."""
    if not _OHLCV_OK:
        return None
    import sqlite3
    fd = from_date.replace("-", "")
    td = to_date.replace("-", "")
    try:
        con = sqlite3.connect(OHLCV_DB_PATH)
        df = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM daily_ohlcv "
            "WHERE ticker=? AND date>=? AND date<=? AND is_suspended=0 ORDER BY date",
            con, params=(ticker, fd, td))
        con.close()
    except Exception:
        return None
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df = df.set_index("date").rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume"})
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _get_prices(ticker, from_date, to_date):
    """가격 로드: ohlcv 우선, 없으면 fdr 폴백(네트워크). analyze_ticker 의 단일 진입점.
    ohlcv 적중 시 sleep 없음(네트워크 0) → 스크리너 가속. 폴백 시에만 REQUEST_DELAY."""
    df = _read_prices_ohlcv(ticker, from_date, to_date)
    if df is not None and len(df) >= 50:
        return df
    time.sleep(REQUEST_DELAY)                          # fdr 호출 전에만 예의상 지연
    return fdr.DataReader(ticker, from_date, to_date)   # 폴백(기존 경로)
# ────────────────────────────────────────────────────────────────────────
TOP_N = 30
MAX_WORKERS = 3
REQUEST_DELAY = 0.15

# 수급
SUPPLY_MIN_OVERSOLD = 30
SUPPLY_REQUEST_DELAY = 0.25
SUPPLY_MAX_WORKERS = 4


# ============================================================
# 금융주/리츠/스팩 키워드
# ============================================================
FINANCIAL_KEYWORDS = [
    '금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드',
    '손해보험', '생명', '화재', '저축', '여신', '신탁',
]
REIT_KEYWORDS = ['리츠', 'REIT', '부동산투자']
SPAC_KEYWORDS = ['스팩', 'SPAC']
KNOWN_FINANCIAL_TICKERS = {'055550', '001450'}


# ============================================================
# 내장 주요 종목 (StockListing 실패 시 백업)
# ============================================================
KOSPI_MAJOR = [
    ('005930', '삼성전자'), ('000660', 'SK하이닉스'), ('373220', 'LG에너지솔루션'),
    ('005490', 'POSCO홀딩스'), ('207940', '삼성바이오로직스'), ('006400', '삼성SDI'),
    ('051910', 'LG화학'), ('035420', 'NAVER'), ('035720', '카카오'),
    ('068270', '셀트리온'), ('005380', '현대차'), ('000270', '기아'),
    ('012330', '현대모비스'), ('161390', '한국타이어앤테크놀로지'),
    ('096770', 'SK이노베이션'), ('010130', '고려아연'), ('011170', '롯데케미칼'),
    ('011780', '금호석유'), ('010950', 'S-Oil'), ('010060', 'OCI홀딩스'),
    ('120110', '코오롱인더'), ('011790', 'SKC'), ('047810', '한국항공우주'),
    ('012450', '한화에어로스페이스'), ('017670', 'SK텔레콤'),
    ('030200', 'KT'), ('032640', 'LG유플러스'), ('097950', 'CJ제일제당'),
    ('282330', 'BGF리테일'), ('023530', '롯데쇼핑'), ('004170', '신세계'),
    ('139480', '이마트'), ('051900', 'LG생활건강'), ('090430', '아모레퍼시픽'),
    ('271560', '오리온'), ('001680', '대상'), ('008770', '호텔신라'),
    ('028260', '삼성물산'), ('000720', '현대건설'), ('006360', 'GS건설'),
    ('329180', 'HD현대중공업'), ('010140', '삼성중공업'),
    ('009540', 'HD한국조선해양'), ('010620', 'HD현대미포'), ('042660', '한화오션'),
    ('003490', '대한항공'), ('011200', 'HMM'), ('086280', '현대글로비스'),
    ('128940', '한미약품'), ('000100', '유한양행'), ('170900', '동아에스티'),
    ('015760', '한국전력'), ('036460', '한국가스공사'),
    ('001040', 'CJ'), ('003550', 'LG'), ('034730', 'SK'),
    ('267250', 'HD현대'), ('266390', '한화'), ('000150', '두산'),
    ('241560', '두산밥캣'), ('042670', 'HD현대인프라코어'),
    ('034220', 'LG디스플레이'), ('066570', 'LG전자'), ('009150', '삼성전기'),
    ('018260', '삼성에스디에스'), ('011070', 'LG이노텍'),
    ('267260', 'HD현대일렉트릭'), ('010120', 'LS ELECTRIC'), ('006260', 'LS'),
    ('259960', '크래프톤'), ('251270', '넷마블'), ('036570', '엔씨소프트'),
    ('004020', '현대제철'), ('001230', '동국제강'), ('103140', '풍산'),
    ('272210', '한화시스템'), ('079550', 'LIG넥스원'),
]

# 코스닥 백업 — StockListing('KOSDAQ') 실패 시에만 쓰이는 degraded 모드용
# (정상 경로에선 FDR 전체 목록을 사용하므로 대표 종목만)
KOSDAQ_MAJOR = [
    ('247540', '에코프로비엠'), ('086520', '에코프로'), ('196170', '알테오젠'),
    ('068760', '셀트리온제약'), ('035760', 'CJ ENM'), ('277810', '레인보우로보틱스'),
    ('028300', 'HLB'), ('357780', '솔브레인'), ('293490', '카카오게임즈'),
    ('058470', '리노공업'), ('067310', '하나마이크론'), ('240810', '원익IPS'),
    ('036930', '주성엔지니어링'), ('039030', '이오테크닉스'), ('098460', '고영'),
    ('213420', '덕산네오룩스'), ('005290', '동진쎄미켐'), ('222800', '심텍'),
    ('140860', '파크시스템스'), ('095340', 'ISC'),
]

# 외국인 누적용 시총 상위 proxy (동적 구성 실패 시 폴백)
KOSPI_PROXY = [
    ('005930', '삼성전자'), ('000660', 'SK하이닉스'), ('373220', 'LG에너지솔루션'),
    ('207940', '삼성바이오로직스'), ('005380', '현대차'), ('005490', 'POSCO홀딩스'),
    ('000270', '기아'), ('035420', 'NAVER'), ('012330', '현대모비스'),
    ('006400', '삼성SDI'),
]
KOSDAQ_PROXY = [
    ('247540', '에코프로비엠'), ('086520', '에코프로'), ('091990', '셀트리온헬스케어'),
    ('196170', '알테오젠'), ('068760', '셀트리온제약'), ('035760', 'CJ ENM'),
    ('277810', '레인보우로보틱스'), ('028300', 'HLB'), ('357780', '솔브레인'),
    ('293490', '카카오게임즈'),
]


# ============================================================
# 시장별 파라미터 (튜닝은 전부 여기서만 관리)
# ============================================================
MARKET_CONFIG = {
    'kospi': {
        'name': 'KOSPI',
        'listing': 'KOSPI',
        'index_code': 'KS11',
        'min_score': 50,
        'exclude_spac': False,
        'major_fallback': KOSPI_MAJOR,
        'proxy_fallback': KOSPI_PROXY,
        # 레짐(지수) 점수
        'regime_scores': {'강세': 0, '조정': -2, '반등': -5, '약세': -10},
        # 환율 점수 (강한약세 / 경미약세 / 강세)
        'fx_scores': {'strong': -3, 'mild': -1, 'won_strong': 2},
        # 외인 흐름 임계값(억) + 점수
        'flow_thresholds': {'strong_out': -5000, 'out': -2000, 'in': 3000},
        'flow_scores': {'strong_out': -3, 'out': -1, 'in': 2},
    },
    'kosdaq': {
        'name': 'KOSDAQ',
        'listing': 'KOSDAQ',
        'index_code': 'KQ11',
        'min_score': 45,            # 등락 폭 큼 → 완화
        'exclude_spac': True,       # 스팩 매우 많음, 합병 전 가격 무의미
        'major_fallback': KOSDAQ_MAJOR,
        'proxy_fallback': KOSDAQ_PROXY,
        'regime_scores': {'강세': 0, '조정': -1, '반등': -3, '약세': -7},
        'fx_scores': {'strong': -1, 'mild': 0, 'won_strong': 1},
        'flow_thresholds': {'strong_out': -2500, 'out': -1000, 'in': 1500},
        'flow_scores': {'strong_out': -2, 'out': -1, 'in': 1},
    },
}


def resolve_market(cli_market=None):
    """--market > 환경변수 V2_INPUT_MARKET > 'kospi' 순으로 시장 결정."""
    m = (cli_market or os.environ.get('V2_INPUT_MARKET') or 'kospi').lower()
    if m not in MARKET_CONFIG:
        raise ValueError(f"알 수 없는 market: {m} (kospi/kosdaq 중 하나)")
    return m


def is_financial_or_reit(ticker, name, exclude_spac=False):
    if not name:
        return False
    if ticker in KNOWN_FINANCIAL_TICKERS:
        return True
    name_str = str(name)
    if exclude_spac:
        name_upper = name_str.upper()
        for kw in SPAC_KEYWORDS:
            if kw in name_upper:
                return True
    for kw in FINANCIAL_KEYWORDS + REIT_KEYWORDS:
        if kw in name_str:
            return True
    return False


def _get_foreign_flow_proxy_tickers(cfg, limit=10):
    """시총 상위 proxy를 동적으로 구성하고, 실패하면 내장 리스트를 사용."""
    try:
        listing = fdr.StockListing(cfg['listing'])
        if listing is None or len(listing) == 0:
            raise ValueError('empty listing')

        code_col = next((c for c in ['Code', 'Symbol'] if c in listing.columns), None)
        name_col = next((c for c in ['Name'] if c in listing.columns), None)
        marcap_col = next((c for c in ['Marcap', 'MarketCap', 'Amount'] if c in listing.columns), None)
        if not code_col or not name_col or not marcap_col:
            raise ValueError('required columns not found')

        rows = []
        for _, row in listing.iterrows():
            code = str(row[code_col]).zfill(6)
            name = str(row[name_col])
            if not code.endswith('0'):
                continue
            if is_financial_or_reit(code, name, cfg['exclude_spac']):
                continue
            try:
                marcap = float(row[marcap_col])
            except Exception:
                continue
            rows.append((marcap, code, name))

        rows.sort(reverse=True)
        picked = [(code, name) for _, code, name in rows[:limit]]
        if len(picked) >= max(5, limit // 2):
            print(f"   • 외인 proxy 동적 구성: 시총 상위 {len(picked)}개")
            return picked
    except Exception as e:
        print(f"   ⚠️  외인 proxy 동적 구성 실패: {str(e)[:80]} → 내장 리스트 사용")

    return cfg['proxy_fallback'][:limit]


def get_universe(cfg):
    """
    종목 목록 반환. Returns: (tickers, name_map, sector_map)
        sector_map은 FDR이 sector 컬럼을 제공할 때만 채워지고, 없으면 빈 dict.
    """
    listing = cfg['listing']
    print(f"   • fdr.StockListing('{listing}') 시도...")
    try:
        df = fdr.StockListing(listing)
        if df is not None and len(df) > 100:
            code_col = next((c for c in ['Code', 'Symbol'] if c in df.columns), None)
            name_col = next((c for c in ['Name'] if c in df.columns), None)
            # FDR 버전마다 산업 분류 컬럼명이 다름 — 자동 탐지
            sector_col = next(
                (c for c in ['Sector', 'sector', 'Industry', 'industry', 'IndustryName']
                 if c in df.columns),
                None
            )
            if code_col and name_col:
                tickers, name_map, sector_map = [], {}, {}
                excluded = 0
                for _, row in df.iterrows():
                    code = str(row[code_col]).zfill(6)
                    name = row[name_col]
                    if not code.endswith('0'):
                        continue
                    if is_financial_or_reit(code, name, cfg['exclude_spac']):
                        excluded += 1
                        continue
                    tickers.append(code)
                    name_map[code] = name
                    if sector_col:
                        sector_val = row.get(sector_col)
                        if sector_val and not pd.isna(sector_val):
                            sector_map[code] = str(sector_val).strip()
                print(f"   ✓ 로드: {len(tickers)}개")
                print(f"   🚫 금융주/리츠{'/스팩' if cfg['exclude_spac'] else ''} 제외: {excluded}개")
                if sector_col:
                    print(f"   🏷️  산업 분류({sector_col}): {len(sector_map)}/{len(tickers)}개 매칭")
                else:
                    print(f"   ⚠️  산업 분류 컬럼 없음 — OCF 점수 산업 보정 비활성")
                return tickers, name_map, sector_map
    except Exception as e:
        print(f"   ⚠️  StockListing 실패: {str(e)[:80]}")

    print("   • 내장 리스트 사용")
    seen = set()
    unique = [(c, n) for c, n in cfg['major_fallback']
              if c not in seen and not seen.add(c)
              and not is_financial_or_reit(c, n, cfg['exclude_spac'])]
    tickers = [c for c, _ in unique]
    name_map = dict(unique)
    print(f"   ✓ {len(tickers)}개")
    return tickers, name_map, {}    # 내장 리스트엔 산업 정보 없음


# ============================================================
# 시장 레짐: 지수 + 환율 + 외국인 누적
# ============================================================

def _analyze_index_regime(cfg):
    """
    지수(KS11/KQ11) 분석으로 시장 레짐 판단.
      🟢 강세: 200일선 위 + 50일선 위
      🟡 조정: 200일선 위 + 50일선 아래
      🟠 반등: 200일선 아래 + 50일선 위
      🔴 약세: 200일선 아래 + 50일선 아래
    """
    today = datetime.now()
    from_date = (today - timedelta(days=450)).strftime("%Y-%m-%d")

    try:
        df = fdr.DataReader(cfg['index_code'], from_date)
        if df is None or len(df) < 200:
            print("   ⚠️  지수 데이터 부족 (200일 이상 필요)")
            return None

        close = df['Close']
        latest = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1])

        vs_sma50_pct = (latest / sma50 - 1) * 100
        vs_sma200_pct = (latest / sma200 - 1) * 100
        daily_change_pct = (latest / prev - 1) * 100
        return_1m_pct = (latest / float(close.iloc[-22]) - 1) * 100 if len(close) >= 22 else 0
        return_3m_pct = (latest / float(close.iloc[-63]) - 1) * 100 if len(close) >= 63 else 0

        above_200 = vs_sma200_pct > 0
        above_50 = vs_sma50_pct > 0

        if above_200 and above_50:
            regime, emoji, signal = '강세', '🟢', '적극적 매수 가능'
        elif above_200 and not above_50:
            regime, emoji, signal = '조정', '🟡', '매수 신중 (강세장 내 조정)'
        elif not above_200 and above_50:
            regime, emoji, signal = '반등', '🟠', '약세장 내 단기 반등 (역추세 주의)'
        else:
            regime, emoji, signal = '약세', '🔴', '관망 / 현금 비중 확대'

        regime_index_score = cfg['regime_scores'].get(regime, 0)

        # 메타 컬럼명은 시장 무관하게 'kospi_*'로 유지 (history.db/하위 단계 호환)
        return {
            'regime': regime,
            'emoji': emoji,
            'signal': signal,
            'regime_kospi_score': regime_index_score,
            'kospi': round(latest, 2),
            'kospi_daily_change_%': round(daily_change_pct, 2),
            'kospi_vs_sma50_%': round(vs_sma50_pct, 1),
            'kospi_vs_sma200_%': round(vs_sma200_pct, 1),
            'kospi_return_1m_%': round(return_1m_pct, 1),
            'kospi_return_3m_%': round(return_3m_pct, 1),
        }
    except Exception as e:
        print(f"   ⚠️  지수 조회 실패: {str(e)[:80]}")
        return None


def _analyze_fx_trend(cfg):
    """
    원/달러 환율 추세 분석. 환율 상승(원화 약세) → 외국인 매도 압력.
    페널티 강도는 cfg['fx_scores']로 시장별 조정 (코스닥은 영향 작음).
    """
    today = datetime.now()
    from_date = (today - timedelta(days=120)).strftime("%Y-%m-%d")
    fx = cfg['fx_scores']

    try:
        df = fdr.DataReader('USD/KRW', from_date)
        if df is None or len(df) < 22:
            print("   ⚠️  USD/KRW 데이터 부족 (22일 이상 필요)")
            return None

        close = df['Close']
        latest = float(close.iloc[-1])
        sma20 = float(close.rolling(20).mean().iloc[-1])
        vs_sma20_pct = (latest / sma20 - 1) * 100
        return_1m_pct = (latest / float(close.iloc[-22]) - 1) * 100

        above_20 = vs_sma20_pct > 0.5
        rising_1m = return_1m_pct > 1.0
        below_20 = vs_sma20_pct < -0.5
        falling_1m = return_1m_pct < -1.0

        if above_20 and rising_1m:
            fx_state, fx_score, fx_emoji = '원화약세_강함', fx['strong'], '🔻'
        elif above_20 or rising_1m:
            fx_state, fx_score, fx_emoji = '원화약세_경미', fx['mild'], '🟡'
        elif below_20 and falling_1m:
            fx_state, fx_score, fx_emoji = '원화강세', fx['won_strong'], '🟢'
        else:
            fx_state, fx_score, fx_emoji = '환율안정', 0, '⚪'

        return {
            'fx_state': fx_state,
            'fx_emoji': fx_emoji,
            'regime_fx_score': fx_score,
            'usdkrw': round(latest, 2),
            'usdkrw_vs_sma20_%': round(vs_sma20_pct, 2),
            'usdkrw_return_1m_%': round(return_1m_pct, 2),
        }
    except Exception as e:
        print(f"   ⚠️  환율 조회 실패: {str(e)[:80]}")
        return None


def _classify_foreign_flow(foreign_sum_억, cfg):
    """외인 5일 누적 합계 → (state, score, emoji). 임계값/점수 모두 시장별."""
    th = cfg['flow_thresholds']
    sc = cfg['flow_scores']
    if foreign_sum_억 < th['strong_out']:
        return '외인이탈_강함', sc['strong_out'], '🔻'
    if foreign_sum_억 < th['out']:
        return '외인이탈', sc['out'], '🟡'
    if foreign_sum_억 > th['in']:
        return '외인유입', sc['in'], '🟢'
    return '외인중립', 0, '⚪'


def _analyze_foreign_flow(cfg):
    """
    시총 상위 대형주의 외국인 5일 누적 순매수를 합산해 시장 외인 방향성 추정.
    조회 성공률이 100%가 아닐 때는 raw 합계를 coverage로 보정해 threshold 왜곡을 줄인다.
    """
    proxy_tickers = _get_foreign_flow_proxy_tickers(cfg, limit=len(cfg['proxy_fallback']))
    print(f"   📊 시총 상위 {len(proxy_tickers)}개 외인 수급 합산 중...")

    foreign_sum = 0.0
    inst_sum = 0.0
    success_count = 0
    contributions = []   # (name, foreign_5d_억)

    with ThreadPoolExecutor(max_workers=SUPPLY_MAX_WORKERS) as executor:
        futures = {
            executor.submit(fetch_supply_for_ticker, ticker): (ticker, name)
            for ticker, name in proxy_tickers
        }
        for future in as_completed(futures):
            ticker, name = futures[future]
            try:
                result = future.result()
                if (result.get('supply_fetched')
                        and result.get('foreign_5d_억') is not None):
                    f5 = float(result['foreign_5d_억'])
                    foreign_sum += f5
                    inst_sum += float(result.get('inst_5d_억') or 0)
                    success_count += 1
                    contributions.append((name, f5))
            except Exception:
                pass

    total = len(proxy_tickers)

    if success_count < max(1, total // 2):
        print(f"   ⚠️  시총 상위 종목 절반 이상 조회 실패 "
              f"({success_count}/{total}) → 외인 점수 0으로 처리")
        return None

    coverage = success_count / total if total else 0
    adjusted_foreign_sum = foreign_sum / coverage if coverage > 0 else foreign_sum
    adjusted_inst_sum = inst_sum / coverage if coverage > 0 else inst_sum

    if success_count < total:
        print(f"   ℹ️   부분 성공: {success_count}/{total}개 합산 "
              f"→ coverage 보정 {foreign_sum:+,.0f}억 → {adjusted_foreign_sum:+,.0f}억")
    else:
        print(f"   ✓ 전체 {total}개 합산 완료")

    flow_state, flow_score, flow_emoji = _classify_foreign_flow(adjusted_foreign_sum, cfg)

    contributions.sort(key=lambda x: abs(x[1]), reverse=True)
    top_contributors = ', '.join(f"{n} {v:+.0f}억" for n, v in contributions[:3])

    return {
        'flow_state': flow_state,
        'flow_emoji': flow_emoji,
        'regime_flow_score': flow_score,
        'foreign_kospi_5d_억': round(adjusted_foreign_sum, 0),
        'foreign_kospi_5d_raw_억': round(foreign_sum, 0),
        'foreign_kospi_5d_adjusted_억': round(adjusted_foreign_sum, 0),
        'inst_kospi_5d_억': round(adjusted_inst_sum, 0),
        'foreign_proxy_success': success_count,
        'foreign_proxy_total': total,
        'foreign_proxy_coverage': round(coverage, 2),
        'foreign_top_contributors': top_contributors,
    }


def analyze_market_regime(cfg):
    """
    통합 시장 레짐 분석. 지수 추세 + 환율 + 외국인 누적을 합산해 통합 regime_score 산출.
    지수 데이터가 없으면 None 반환. FX/Flow는 sub-실패해도 점수 0으로 처리하고 진행.
    """
    index_info = _analyze_index_regime(cfg)
    if not index_info:
        return None

    fx = _analyze_fx_trend(cfg) or {}
    flow = _analyze_foreign_flow(cfg) or {}

    info = {**index_info, **fx, **flow}

    info['regime_kospi_score'] = index_info.get('regime_kospi_score', 0)
    info['regime_fx_score'] = fx.get('regime_fx_score', 0)
    info['regime_flow_score'] = flow.get('regime_flow_score', 0)
    info['regime_score'] = (
        info['regime_kospi_score']
        + info['regime_fx_score']
        + info['regime_flow_score']
    )

    return info


def print_regime_box(regime_info, cfg):
    """시장 레짐 정보 박스 출력 (지수 + 환율 + 외인 통합)"""
    market_name = cfg['name']
    if not regime_info:
        print(f"\n{'─'*72}")
        print(f"⚠️  시장 레짐 분석 실패 → regime_score 0으로 진행")
        print(f"{'─'*72}\n")
        return

    r = regime_info
    daily = r.get('kospi_daily_change_%', 0)
    daily_sign = '+' if daily >= 0 else ''

    print(f"\n{'═'*72}")
    print(f"🏛️   시장 레짐: {r.get('emoji', '⚪')} {r.get('regime', '미정')}장 "
          f"(통합 Score: {r['regime_score']:+d})")
    print(f"{'═'*72}")
    print(f"   {market_name}: {r.get('kospi', 0):,.2f}  ({daily_sign}{daily:.2f}% vs 어제)  "
          f"→ 지수 점수: {r['regime_kospi_score']:+d}")

    sma50_mark = '✅' if r.get('kospi_vs_sma50_%', 0) > 0 else '❌'
    sma200_mark = '✅' if r.get('kospi_vs_sma200_%', 0) > 0 else '❌'
    print(f"   {sma50_mark} 50일선:  {r.get('kospi_vs_sma50_%', 0):+.1f}%")
    print(f"   {sma200_mark} 200일선: {r.get('kospi_vs_sma200_%', 0):+.1f}%")
    print(f"   📈 1개월: {r.get('kospi_return_1m_%', 0):+.1f}%  /  "
          f"3개월: {r.get('kospi_return_3m_%', 0):+.1f}%")

    # 환율
    if 'usdkrw' in r:
        print(f"   ─────────────────────────────────────────")
        print(f"   {r.get('fx_emoji', '⚪')} USD/KRW: {r['usdkrw']:.2f}원  "
              f"(20일선 {r['usdkrw_vs_sma20_%']:+.2f}%, 1개월 {r['usdkrw_return_1m_%']:+.2f}%)")
        print(f"        → {r.get('fx_state', '?')}, 환율 점수: {r['regime_fx_score']:+d}")
    else:
        print(f"   ⚪ 환율 데이터 없음 → 환율 점수: 0")

    # 외인 누적
    if 'foreign_kospi_5d_억' in r:
        proxy_n = r.get('foreign_proxy_success', '?')
        proxy_total = r.get('foreign_proxy_total', '?')
        coverage = r.get('foreign_proxy_coverage')
        cov_txt = f", coverage {coverage:.0%}" if isinstance(coverage, (int, float)) else ""
        print(f"   {r.get('flow_emoji', '⚪')} 외국인 5일 누적 "
              f"(시총상위 {proxy_n}/{proxy_total}개 합산{cov_txt}): "
              f"{r['foreign_kospi_5d_억']:+,.0f}억")
        if 'foreign_kospi_5d_raw_억' in r and r.get('foreign_proxy_success') != r.get('foreign_proxy_total'):
            print(f"        raw {r['foreign_kospi_5d_raw_억']:+,.0f}억 → adjusted {r['foreign_kospi_5d_adjusted_억']:+,.0f}억")
        print(f"        → {r.get('flow_state', '?')}, 외인 점수: {r['regime_flow_score']:+d}")
        if r.get('foreign_top_contributors'):
            print(f"        주요 기여: {r['foreign_top_contributors']}")
    else:
        print(f"   ⚪ 외국인 수급 데이터 부족 → 외인 점수: 0")

    print(f"   ─────────────────────────────────────────")
    print(f"   💡 {r.get('signal', '?')}")
    print(f"{'═'*72}\n")


# ============================================================
# 기술적 지표
# ============================================================

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_bollinger_bands(prices, period=20, std=2.0):
    middle = prices.rolling(window=period).mean()
    std_dev = prices.rolling(window=period).std()
    return middle + std_dev * std, middle, middle - std_dev * std


def calculate_stochastic(df, period=14):
    low_n = df['Low'].rolling(period).min()
    high_n = df['High'].rolling(period).max()
    return 100 * (df['Close'] - low_n) / (high_n - low_n).replace(0, np.nan)


def calculate_accumulation_score(df):
    if len(df) < 25:
        return {'acc_score': 0, 'acc_signal_vol': False,
                'acc_signal_return': False, 'acc_signal_candle': False}

    score = 0
    signals = {}

    recent_vol = df['Volume'].iloc[-5:].mean()
    prev_vol = df['Volume'].iloc[-20:-5].mean()
    if prev_vol > 0 and recent_vol / prev_vol > 1.5:
        score += 5
        signals['vol'] = True
    else:
        signals['vol'] = False

    if len(df) >= 11:
        recent_ret = (df['Close'].iloc[-1] / df['Close'].iloc[-6] - 1) * 100
        prev_ret = (df['Close'].iloc[-6] / df['Close'].iloc[-11] - 1) * 100
        if recent_ret > prev_ret + 2:
            score += 5
            signals['return'] = True
        else:
            signals['return'] = False
    else:
        signals['return'] = False

    recent = df.iloc[-5:]
    up_days = (recent['Close'] > recent['Open']).sum()
    if up_days >= 3:
        score += 5
        signals['candle'] = True
    else:
        signals['candle'] = False

    return {
        'acc_score': score,
        'acc_signal_vol': signals['vol'],
        'acc_signal_return': signals['return'],
        'acc_signal_candle': signals['candle'],
    }


def calculate_volume_metrics(df):
    if len(df) < 21:
        return {
            'avg_volume_1w': None, 'avg_volume_1m': None,
            'amt_today_억': None,
            'amt_avg_1w_억': None, 'amt_avg_1m_억': None,
            'vol_1w_vs_1m_ratio': None,
        }
    df = df.copy()
    df['TradeAmount'] = df['Volume'] * df['Close']
    latest = df.iloc[-1]
    vol_5d = df['Volume'].tail(5).mean()
    vol_21d = df['Volume'].tail(21).mean()
    amt_5d = df['TradeAmount'].tail(5).mean()
    amt_21d = df['TradeAmount'].tail(21).mean()
    today_amt = latest['Volume'] * latest['Close']
    vol_ratio = vol_5d / vol_21d if vol_21d > 0 else 1.0
    return {
        'avg_volume_1w': int(vol_5d),
        'avg_volume_1m': int(vol_21d),
        'amt_today_억': round(today_amt / 1e8, 1),
        'amt_avg_1w_억': round(amt_5d / 1e8, 1),
        'amt_avg_1m_억': round(amt_21d / 1e8, 1),
        'vol_1w_vs_1m_ratio': round(vol_ratio, 2),
    }


def calculate_trend_reversal(df):
    DEFAULT = {
        'trend_score': 0,
        'falling_knife': False,
        'reversal_above_sma5': False,
        'reversal_rebound_3pct': False,
        'reversal_vol_up_candle': False,
        'trend_details': '데이터부족',
    }
    if len(df) < 22:
        return DEFAULT

    close = df['Close']
    sma5 = close.rolling(5).mean()
    sma20 = close.rolling(20).mean()
    latest_close = close.iloc[-1]
    latest_sma5 = sma5.iloc[-1]
    latest_sma20 = sma20.iloc[-1]
    recent5 = df.iloc[-5:]
    recent5_low = recent5['Low'].min()

    near_5d_low = latest_close <= recent5_low * 1.01
    sma5_below_sma20 = (pd.notna(latest_sma5) and pd.notna(latest_sma20)
                       and latest_sma5 < latest_sma20)
    bull_candles_5d = (recent5['Close'] > recent5['Open']).sum()
    no_bull_candles = bull_candles_5d == 0
    falling_knife = bool(near_5d_low and sma5_below_sma20 and no_bull_candles)

    trend_score = 0
    sig_above_sma5 = False
    sig_rebound = False
    sig_vol_candle = False

    if pd.notna(latest_sma5) and latest_close >= latest_sma5:
        trend_score += 3
        sig_above_sma5 = True

    if len(df) >= 10:
        prev_5d_low = df['Low'].iloc[-10:-5].min()
        if (pd.notna(prev_5d_low) and prev_5d_low > 0
                and latest_close >= prev_5d_low * 1.03):
            trend_score += 3
            sig_rebound = True

    latest = df.iloc[-1]
    vol_5d_avg_prev = df['Volume'].iloc[-6:-1].mean()
    today_bull = latest['Close'] > latest['Open']
    today_vol_up = vol_5d_avg_prev > 0 and latest['Volume'] > vol_5d_avg_prev * 1.2
    if today_bull and today_vol_up:
        trend_score += 4
        sig_vol_candle = True

    if falling_knife:
        trend_score = -30

    details = []
    if falling_knife:
        details.append('⚠️떨어지는칼날')
    if sig_above_sma5:
        details.append('5일선회복')
    if sig_rebound:
        details.append('+3%반등')
    if sig_vol_candle:
        details.append('거래량동반양봉')

    return {
        'trend_score': trend_score,
        'falling_knife': falling_knife,
        'reversal_above_sma5': sig_above_sma5,
        'reversal_rebound_3pct': sig_rebound,
        'reversal_vol_up_candle': sig_vol_candle,
        'trend_details': '/'.join(details) if details else '-',
    }


# ============================================================
# 네이버 금융 수급 크롤링
# ============================================================

NAVER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}

EMPTY_SUPPLY = {
    'foreign_5d_억': None,
    'inst_5d_억': None,
    'foreign_20d_억': None,
    'inst_20d_억': None,
    'supply_fetched': False,
}


def _to_num(s):
    if pd.isna(s):
        return None
    s = str(s).replace(',', '').replace('\xa0', '').strip()
    if s in ('', '-', 'nan', 'None'):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _flatten_columns(cols):
    if isinstance(cols, pd.MultiIndex):
        return [' '.join(str(c) for c in tup
                        if 'Unnamed' not in str(c) and str(c) != 'nan').strip()
                for tup in cols]
    return [str(c) for c in cols]


def fetch_supply_data_naver(ticker):
    url = f"https://finance.naver.com/item/frgn.naver?code={ticker}"
    try:
        resp = requests.get(url, headers=NAVER_HEADERS, timeout=10)
        if resp.status_code != 200:
            return dict(EMPTY_SUPPLY)
        resp.encoding = resp.apparent_encoding or 'euc-kr'
        html = resp.text
        if len(html) < 1000:
            return dict(EMPTY_SUPPLY)
        try:
            tables = pd.read_html(StringIO(html))
        except ValueError:
            return dict(EMPTY_SUPPLY)

        target_df = None
        for t in tables:
            if len(t) < 3:
                continue
            cols_flat = _flatten_columns(t.columns)
            cols_str = ' '.join(cols_flat)
            if '외국인' in cols_str and '기관' in cols_str:
                target_df = t.copy()
                target_df.columns = cols_flat
                break

        if target_df is None or len(target_df) == 0:
            return dict(EMPTY_SUPPLY)

        close_col = next((c for c in target_df.columns if '종가' in c), None)
        inst_col = next((c for c in target_df.columns
                        if '기관' in c
                        and ('순매매' in c or '순매수' in c)), None)
        foreign_col = next((c for c in target_df.columns
                           if '외국인' in c
                           and ('순매매' in c or '순매수' in c)
                           and '보유' not in c), None)

        if not all([close_col, inst_col, foreign_col]):
            return dict(EMPTY_SUPPLY)

        target_df['_close'] = target_df[close_col].apply(_to_num)
        target_df['_inst'] = target_df[inst_col].apply(_to_num)
        target_df['_foreign'] = target_df[foreign_col].apply(_to_num)
        target_df = target_df.dropna(subset=['_close', '_inst', '_foreign'])

        if len(target_df) == 0:
            return dict(EMPTY_SUPPLY)

        target_df['_inst_amt'] = target_df['_inst'] * target_df['_close']
        target_df['_foreign_amt'] = target_df['_foreign'] * target_df['_close']

        recent_5 = target_df.head(5)
        recent_20 = target_df.head(20)

        return {
            'foreign_5d_억': round(recent_5['_foreign_amt'].sum() / 1e8, 1),
            'inst_5d_억': round(recent_5['_inst_amt'].sum() / 1e8, 1),
            'foreign_20d_억': round(recent_20['_foreign_amt'].sum() / 1e8, 1),
            'inst_20d_억': round(recent_20['_inst_amt'].sum() / 1e8, 1),
            'supply_fetched': True,
        }
    except Exception:
        return dict(EMPTY_SUPPLY)


def fetch_supply_for_ticker(ticker):
    time.sleep(SUPPLY_REQUEST_DELAY)
    result = fetch_supply_data_naver(ticker)
    result['_ticker'] = ticker
    return result


def calculate_supply_score(row):
    if not row.get('supply_fetched'):
        return 0
    score = 0
    foreign_5d = row.get('foreign_5d_억') or 0
    inst_5d = row.get('inst_5d_억') or 0
    return_1m = row.get('return_1m_%') or 0
    foreign_buying = foreign_5d > 0
    inst_buying = inst_5d > 0
    if foreign_buying:
        score += 3
    if inst_buying:
        score += 3
    if foreign_buying and inst_buying:
        score += 4
    if return_1m <= -10 and (foreign_buying or inst_buying):
        score += 5
    return min(15, max(0, score))


# ============================================================
# 종목 분석
# ============================================================

def analyze_ticker(ticker, name_map, sector_map, from_date, to_date):
    try:
        df = _get_prices(ticker, from_date, to_date)   # Phase2: ohlcv 우선, fdr 폴백(폴백 시 내부 sleep)

        if df is None or len(df) < 50:
            return None
        if df['Close'].iloc[-1] < 1000:
            return None
        if df['Volume'].tail(5).sum() == 0:
            return None

        df['RSI'] = calculate_rsi(df['Close'])
        df['BB_U'], df['BB_M'], df['BB_L'] = calculate_bollinger_bands(df['Close'])
        df['SMA20'] = df['Close'].rolling(20).mean()
        df['SMA50'] = df['Close'].rolling(50).mean()
        df['SMA200'] = df['Close'].rolling(200).mean()
        df['Vol_MA20'] = df['Volume'].rolling(20).mean()
        df['Stoch'] = calculate_stochastic(df)

        latest = df.iloc[-1]
        price = latest['Close']
        recent = df.tail(252) if len(df) >= 252 else df
        high_52w = recent['High'].max()
        low_52w = recent['Low'].min()

        def pct_change(n):
            if len(df) < n + 1:
                return np.nan
            return (price / df['Close'].iloc[-(n+1)] - 1) * 100

        bb_range = latest['BB_U'] - latest['BB_L']
        bb_pos = ((price - latest['BB_L']) / bb_range * 100) if bb_range > 0 else 50

        accum = calculate_accumulation_score(df)
        vol_metrics = calculate_volume_metrics(df)
        trend = calculate_trend_reversal(df)

        return {
            'ticker': ticker,
            'name': name_map.get(ticker, ticker),
            'sector': sector_map.get(ticker) if sector_map else None,
            'price': int(price),
            'RSI': round(latest['RSI'], 1) if pd.notna(latest['RSI']) else None,
            'Stoch_K': round(latest['Stoch'], 1) if pd.notna(latest['Stoch']) else None,
            'BB_pct': round(bb_pos, 1),
            'drawdown_52w_high_%': round((price - high_52w) / high_52w * 100, 1),
            'distance_to_52w_low_%': round((price - low_52w) / low_52w * 100, 1),
            'return_1w_%': round(pct_change(5), 1),
            'return_1m_%': round(pct_change(21), 1),
            'return_3m_%': round(pct_change(63), 1),
            'vs_SMA20_%': round((price / latest['SMA20'] - 1) * 100, 1) if pd.notna(latest['SMA20']) else None,
            'vs_SMA50_%': round((price / latest['SMA50'] - 1) * 100, 1) if pd.notna(latest['SMA50']) else None,
            'vs_SMA200_%': round((price / latest['SMA200'] - 1) * 100, 1) if pd.notna(latest['SMA200']) else None,
            'volume_vs_avg': round(latest['Volume'] / latest['Vol_MA20'], 2) if latest['Vol_MA20'] > 0 else None,
            '52w_high': int(high_52w),
            '52w_low': int(low_52w),
            **accum,
            **vol_metrics,
            **trend,
        }
    except Exception:
        return None


def calculate_oversold_score(row):
    score = 0.0
    rsi = row.get('RSI')
    if pd.notna(rsi):
        score += max(0, min(30, (50 - rsi) * 1.5))
    bb = row.get('BB_pct')
    if pd.notna(bb):
        score += max(0, min(20, (50 - bb) * 0.4))
    dd = row.get('drawdown_52w_high_%')
    if pd.notna(dd):
        score += max(0, min(20, abs(dd) * 0.4))
    r1m = row.get('return_1m_%')
    if pd.notna(r1m) and r1m < 0:
        score += min(15, abs(r1m) * 0.5)
    vol = row.get('volume_vs_avg')
    if pd.notna(vol) and vol > 1:
        score += min(10, (vol - 1) * 5)
    stoch = row.get('Stoch_K')
    if pd.notna(stoch):
        score += max(0, min(5, (30 - stoch) * 0.25))
    return round(score, 1)


# ============================================================
# 메인
# ============================================================

def run_screener(market='kospi'):
    cfg = MARKET_CONFIG[market]
    market_name = cfg['name']
    min_score = cfg['min_score']

    print(f"\n{'='*72}")
    print(f"📊  [V2.6] {market_name} 과매도 스크리너 (레짐 + 환율 + 외인 통합)")
    print(f"     • 금융주/리츠{'/스팩' if cfg['exclude_spac'] else ''} 자동 제외")
    print(f"     • 매집 / 거래량 / 추세 전환")
    print(f"     • 외국인/기관 수급 (네이버)")
    print(f"     • 시장 레짐 + 환율(USD/KRW) + 외국인 누적")
    print(f"{'='*72}")
    print(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ===== 통합 레짐 분석 (지수 + 환율 + 외인) =====
    print(f"0️⃣  시장 레짐 분석 ({market_name} + USD/KRW + 외국인 {market_name})")
    regime_info = analyze_market_regime(cfg)
    print_regime_box(regime_info, cfg)

    print("1️⃣  종목 유니버스 구성")
    tickers, name_map, sector_map = get_universe(cfg)
    if not tickers:
        print("❌ 종목 리스트 가져오기 실패")
        return

    today = datetime.now()
    from_date = (today - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")

    print(f"\n2️⃣  {len(tickers)}개 종목 기술적 분석 (병렬 {MAX_WORKERS}스레드)\n")

    results = []
    completed = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(analyze_ticker, t, name_map, sector_map, from_date, to_date): t
            for t in tickers
        }
        for future in as_completed(futures):
            completed += 1
            data = future.result()
            if data:
                results.append(data)
            if completed % 20 == 0 or completed == len(tickers):
                elapsed = time.time() - start_time
                eta = (elapsed / completed) * (len(tickers) - completed)
                print(f"   [{completed:>3}/{len(tickers)}] 성공: {len(results):>3} "
                      f"경과: {elapsed:>4.0f}초 남은: {eta:>4.0f}초")

    if not results:
        print("❌ 분석 데이터 없음")
        return

    df = pd.DataFrame(results)
    df['oversold_score'] = df.apply(calculate_oversold_score, axis=1)

    # ===== 수급 수집 =====
    for k in EMPTY_SUPPLY:
        df[k] = EMPTY_SUPPLY[k]

    target_mask = df['oversold_score'] >= SUPPLY_MIN_OVERSOLD
    targets = df[target_mask]['ticker'].tolist()

    expected_time = (len(targets) * SUPPLY_REQUEST_DELAY) / SUPPLY_MAX_WORKERS
    print(f"\n3️⃣  외국인/기관 수급 분석 - 네이버 금융 크롤링")
    print(f"   대상: {len(targets)}개 종목 (oversold ≥ {SUPPLY_MIN_OVERSOLD}점)")
    print(f"   병렬: {SUPPLY_MAX_WORKERS}스레드, 예상 시간: {expected_time:.0f}초\n")

    supply_results = {}
    supply_done = 0
    supply_start = time.time()

    with ThreadPoolExecutor(max_workers=SUPPLY_MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_supply_for_ticker, t): t for t in targets}
        for future in as_completed(futures):
            supply_done += 1
            result = future.result()
            tkr = result.pop('_ticker', None)
            if tkr:
                supply_results[tkr] = result
            if supply_done % 20 == 0 or supply_done == len(targets):
                elapsed = time.time() - supply_start
                success = sum(1 for r in supply_results.values()
                            if r.get('supply_fetched'))
                print(f"   [{supply_done:>3}/{len(targets)}] 성공: {success:>3} "
                      f"경과: {elapsed:>4.0f}초")

    for ticker, supply in supply_results.items():
        for k, v in supply.items():
            df.loc[df['ticker'] == ticker, k] = v

    success_count = int(df['supply_fetched'].sum())
    fail_count = len(targets) - success_count
    print(f"   ✓ 수급 데이터 확보: {success_count}/{len(targets)}개")
    if fail_count > 0:
        print(f"   ⚠️  실패: {fail_count}개")

    df['supply_score'] = df.apply(calculate_supply_score, axis=1)

    # ===== 통합 레짐 점수 + 메타 컬럼 부여 (지수 + 환율 + 외인) =====
    # 컬럼명은 시장 무관하게 'kospi_*'/'foreign_kospi_*' 유지 (history.db/하위 단계 호환)
    if regime_info:
        df['market_regime'] = regime_info.get('regime', '미정')
        df['regime_score'] = regime_info['regime_score']
        df['regime_kospi_score'] = regime_info.get('regime_kospi_score', 0)
        df['regime_fx_score'] = regime_info.get('regime_fx_score', 0)
        df['regime_flow_score'] = regime_info.get('regime_flow_score', 0)
        df['kospi_vs_sma200_%'] = regime_info.get('kospi_vs_sma200_%')
        df['kospi_return_1m_%'] = regime_info.get('kospi_return_1m_%')
        df['usdkrw'] = regime_info.get('usdkrw')
        df['usdkrw_vs_sma20_%'] = regime_info.get('usdkrw_vs_sma20_%')
        df['usdkrw_return_1m_%'] = regime_info.get('usdkrw_return_1m_%')
        df['foreign_kospi_5d_억'] = regime_info.get('foreign_kospi_5d_억')
        df['foreign_kospi_5d_raw_억'] = regime_info.get('foreign_kospi_5d_raw_억')
        df['foreign_kospi_5d_adjusted_억'] = regime_info.get('foreign_kospi_5d_adjusted_억')
        df['foreign_proxy_success'] = regime_info.get('foreign_proxy_success')
        df['foreign_proxy_total'] = regime_info.get('foreign_proxy_total')
        df['foreign_proxy_coverage'] = regime_info.get('foreign_proxy_coverage')
    else:
        df['market_regime'] = '미정'
        df['regime_score'] = 0
        df['regime_kospi_score'] = 0
        df['regime_fx_score'] = 0
        df['regime_flow_score'] = 0
        df['kospi_vs_sma200_%'] = None
        df['kospi_return_1m_%'] = None
        df['usdkrw'] = None
        df['usdkrw_vs_sma20_%'] = None
        df['usdkrw_return_1m_%'] = None
        df['foreign_kospi_5d_억'] = None
        df['foreign_kospi_5d_raw_억'] = None
        df['foreign_kospi_5d_adjusted_억'] = None
        df['foreign_proxy_success'] = None
        df['foreign_proxy_total'] = None
        df['foreign_proxy_coverage'] = None

    # stock_score_stage1: 종목 자체 점수. composite_score: 시장 레짐까지 반영한 1단계 점수.
    df['stock_score_stage1'] = (
        df['oversold_score']
        + df['acc_score']
        + df['trend_score']
        + df['supply_score']
    )
    df['composite_score'] = df['stock_score_stage1'] + df['regime_score']
    df = df.sort_values('composite_score', ascending=False).reset_index(drop=True)

    # 통계
    fk_count = int(df['falling_knife'].sum())
    strong_supply = int((df['supply_score'] >= 10).sum())
    divergence = int(((df['return_1m_%'] <= -10) &
                     ((df['foreign_5d_억'].fillna(0) > 0) |
                      (df['inst_5d_억'].fillna(0) > 0))).sum())

    print(f"\n{'='*72}")
    print(f"📊  분석 통계")
    print(f"{'='*72}")
    if regime_info:
        print(f"   🏛️  시장 레짐:  {regime_info.get('emoji', '⚪')} "
              f"{regime_info.get('regime', '미정')}장  → 통합 점수 {regime_info['regime_score']:+d}")
        print(f"      └ 지수 {regime_info['regime_kospi_score']:+d} / "
              f"환율 {regime_info['regime_fx_score']:+d} / "
              f"외인 {regime_info['regime_flow_score']:+d}")
    print(f"   ⚠️  떨어지는 칼날:              {fk_count}개")
    print(f"   📈 수급 데이터 확보:            {success_count}개")
    print(f"   🔥 강한 수급 (score ≥ 10):     {strong_supply}개")
    print(f"   💎 다이버전스 (낙폭+큰손매수): {divergence}개")

    print(f"\n{'='*72}")
    print(f"🎯  누적 점수 상위 {TOP_N}개  (과매도+매집+추세+수급+레짐)")
    print(f"{'='*72}\n")

    candidates = df[df['oversold_score'] >= min_score].head(TOP_N)
    if len(candidates) == 0:
        candidates = df.head(20)

    print(f"{'#':>3} {'종목명':<12} {'코드':<8} "
          f"{'과매':>5} {'매집':>4} {'추세':>4} {'수급':>4} {'레짐':>4}  "
          f"{'외인5일':>8} {'기관5일':>8}")
    print("-" * 88)
    for i, row in candidates.iterrows():
        name = (row['name'] or row['ticker'])[:10]
        foreign = row.get('foreign_5d_억')
        inst = row.get('inst_5d_억')
        f_str = f"{foreign:+7.0f}억" if pd.notna(foreign) else "    -   "
        i_str = f"{inst:+7.0f}억" if pd.notna(inst) else "    -   "
        print(f"{i+1:>3} {name:<12} {row['ticker']:<8} "
              f"{row['oversold_score']:>5.1f} "
              f"{row['acc_score']:>+4.0f}  "
              f"{row['trend_score']:>+4.0f}  "
              f"{row['supply_score']:>+4.0f}  "
              f"{row['regime_score']:>+4.0f}  "
              f"{f_str} {i_str}")

    # 다이버전스 강조
    div_df = df[(df['return_1m_%'] <= -10) &
                ((df['foreign_5d_억'].fillna(0) > 0) |
                 (df['inst_5d_억'].fillna(0) > 0))].head(10)
    if len(div_df) > 0:
        print(f"\n💎 다이버전스 종목 (주가 -10% 이상 + 큰손 매수) - 최우선 후보:")
        for _, row in div_df.iterrows():
            f5 = row.get('foreign_5d_억', 0) or 0
            i5 = row.get('inst_5d_억', 0) or 0
            print(f"   • {str(row['name'])[:12]:<14} ({row['ticker']}) "
                  f"1개월 {row['return_1m_%']:+5.1f}%  "
                  f"외인 {f5:+6.0f}억  기관 {i5:+6.0f}억")

    # 통합 레짐 페널티 경고
    if regime_info and regime_info['regime_score'] <= -8:
        print(f"\n{'!'*72}")
        print(f"⚠️  통합 레짐 점수 {regime_info['regime_score']:+d}점 — 강한 페널티 적용 중")
        details = []
        if regime_info['regime_kospi_score'] < 0:
            details.append(f"{market_name} 약세({regime_info['regime_kospi_score']:+d})")
        if regime_info['regime_fx_score'] < 0:
            details.append(f"원화 약세({regime_info['regime_fx_score']:+d})")
        if regime_info['regime_flow_score'] < 0:
            details.append(f"외인 이탈({regime_info['regime_flow_score']:+d})")
        if details:
            print(f"   원인: {', '.join(details)}")
        print(f"   포지션 사이즈를 평소보다 줄이거나 현금 비중을 유지하세요.")
        print(f"{'!'*72}")

    filename = f"v2_{market}_oversold_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"\n💾 저장: {filename}\n")


def main():
    parser = argparse.ArgumentParser(description="V2.6 과매도 스크리너 (KOSPI/KOSDAQ 통합)")
    parser.add_argument('--market', choices=['kospi', 'kosdaq'], default=None,
                        help='대상 시장 (없으면 환경변수 V2_INPUT_MARKET, 기본 kospi)')
    args = parser.parse_args()
    market = resolve_market(args.market)
    run_screener(market)


if __name__ == "__main__":
    main()
