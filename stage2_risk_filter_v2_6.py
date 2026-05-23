#!/usr/bin/env python3
"""
[V2.6] 3단계: 펀더멘털 + 모멘텀 + OCF(영업활동현금흐름)
======================================================
V2.6 핵심 변경:
  ① 분기 YoY 복구: thstrm_amount vs frmtrm_q_amount 우선, 누적값은 q_basis='누적'으로 별도 표시
  ② 분기 영업이익은 fnlttSinglAcntAll 실패 시 fnlttSinglAcnt(주요계정)로 폴백
  ③ DART 진단 컬럼 추가: status/message/fs_div/account/key 정보를 CSV에 저장
  ④ OCF 점수 고도화: 단순 부호가 아니라 OCF / 영업이익 비율까지 반영
  ⑤ stock_score와 final_score 분리: 종목 자체 점수와 시장 레짐 반영 점수를 구분
  ⑥ 모멘텀 점수 보정: 단순 하락 둔화와 명확한 단기 반등을 분리
  ⑦ 0원 값을 None처럼 처리하던 if latest 버그 수정
  ⑧ [추가 패치] OCF 점수에 산업별 임계값 적용 — false positive 감소
        • 건설/조선/제약/해운 등 OCF 변동성 큰 산업은 음수도 일시적일 수 있어
          밸류트랩 페널티를 -10 → -5로 완화 (lenient 그룹)
        • IT/플랫폼/게임은 OCF/OP 평균이 높아 0.9/0.5로 엄격 적용 (strict 그룹)
        • 일반 제조업은 기존 0.7/0.3 유지 (default 그룹)
        • 산업 분류는 1단계에서 sector 컬럼으로 전달받아 사용
  ⑨ [P0 패치] 분기 보고서 attempts 동적 생성 (build_quarterly_attempts)
        • 기존 attempts 하드코딩이 시기에 따라 부정확:
          - 8월 이후 실행 시 cy H1(반기보고서) 미시도
          - 11월 이후 실행 시 cy Q3(3분기보고서) 미시도
        • DART 마감일(Q1 5/15, H1 8/14, Q3 11/14) 기준으로 다음 달부터
          현재 연도 보고서를 우선 시도, 전년도는 fallback으로 유지

[실행]
    python stage3_fundamental_momentum_v2_6.py
"""

import requests
import pandas as pd
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


import os

# [V2.6 자동화] 환경변수에서 로드 (GitHub Secrets / 로컬 .env)
DART_API_KEY = os.environ.get("DART_API_KEY", "")
INPUT_CSV = None
MIN_OVERSOLD_SCORE = 50  # [V2.6 자동화] 40 → 50 (3단계 검사 대상 축소, ~100개 예상)
TOP_N = 20
REQUEST_SLEEP = 0.05

# [V2.6 자동화] 병렬 처리 — DART rate limit 고려 4스레드
MAX_WORKERS = 4

REPRT_CODES = {'Q1': '11013', 'H1': '11012', 'Q3': '11014', 'Y': '11011'}


# ============================================================
# DART API
# ============================================================

def _request_json(url, params, timeout=15):
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        data = resp.json()
        status = str(data.get('status', ''))
        message = data.get('message', '')
        if status == '000':
            return data.get('list', []) or [], status, message
        return None, status or 'NO_STATUS', message or 'DART 응답 오류'
    except Exception as e:
        return None, 'REQUEST_ERROR', str(e)[:120]


def fetch_report_all(corp_code, year, reprt_code, api_key, fs_div='CFS'):
    """DART 단일회사 전체 재무제표: BS + IS/CIS + CF 등."""
    return _request_json(
        "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json",
        {
            'crtfc_key': api_key,
            'corp_code': corp_code,
            'bsns_year': str(year),
            'reprt_code': reprt_code,
            'fs_div': fs_div,
        },
    )


def fetch_report_single(corp_code, year, reprt_code, api_key):
    """DART 단일회사 주요계정. 분기 영업이익 폴백용."""
    return _request_json(
        "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json",
        {
            'crtfc_key': api_key,
            'corp_code': corp_code,
            'bsns_year': str(year),
            'reprt_code': reprt_code,
        },
    )


def filter_items_by_fs(items, fs_div):
    if not items:
        return []
    has_fs = any('fs_div' in item for item in items)
    if not has_fs:
        return items
    matched = [item for item in items if item.get('fs_div') == fs_div]
    return matched


# ============================================================
# 계정 항목 매칭
# ============================================================

_IS_LIKE = ('IS', 'CIS')
_OP_ACCOUNT_ID_KEYWORDS = (
    'ProfitLossFromOperatingActivities',
    'OperatingIncomeLoss',
    'OperatingProfitLoss',
)


def _is_is_like(item):
    sj = item.get('sj_div')
    # 주요계정 API에는 sj_div가 없거나 비어있는 경우가 있어, 없으면 허용한다.
    return (not sj) or sj in _IS_LIKE


def find_operating_profit(items):
    """손익계산서 / 포괄손익계산서에서 영업이익 항목 추출."""
    if not items:
        return None

    # 1순위: XBRL account_id 기반 매칭
    for item in items:
        if not _is_is_like(item):
            continue
        account_id = item.get('account_id', '') or ''
        if any(k.lower() in account_id.lower() for k in _OP_ACCOUNT_ID_KEYWORDS):
            return item

    exact_names = ('영업이익', '영업손실', '영업이익(손실)', '영업손익')
    for item in items:
        if not _is_is_like(item):
            continue
        if (item.get('account_nm') or '').strip() in exact_names:
            return item

    for item in items:
        if not _is_is_like(item):
            continue
        nm = item.get('account_nm', '') or ''
        # 영업수익은 매출성 계정일 수 있어 영업이익 대용으로 쓰지 않는다.
        if '영업이익' in nm or '영업손실' in nm or '영업손익' in nm:
            return item
    return None


_OCF_ACCOUNT_ID_KEYWORDS = (
    'CashFlowsFromUsedInOperatingActivities',
    'CashFlowsFromOperatingActivities',
)

_OCF_EXACT_KEYWORDS = (
    '영업활동현금흐름',
    '영업활동으로인한현금흐름',
    '영업활동으로인한순현금흐름',
    '영업활동순현금흐름',
    '영업활동에서창출된현금흐름',
    '영업활동으로부터의현금흐름',
)


def find_operating_cash_flow(items):
    """현금흐름표(sj_div='CF')에서 영업활동현금흐름 항목 추출."""
    if not items:
        return None

    for item in items:
        if item.get('sj_div') != 'CF':
            continue
        account_id = item.get('account_id', '') or ''
        if any(k.lower() in account_id.lower() for k in _OCF_ACCOUNT_ID_KEYWORDS):
            return item

    for item in items:
        if item.get('sj_div') != 'CF':
            continue
        nm = (item.get('account_nm') or '').replace(' ', '')
        if any(kw in nm for kw in _OCF_EXACT_KEYWORDS):
            return item

    for item in items:
        if item.get('sj_div') != 'CF':
            continue
        nm = (item.get('account_nm') or '').replace(' ', '')
        if '영업활동' in nm and '현금흐름' in nm:
            return item
    return None


# ============================================================
# 금액/YoY 유틸
# ============================================================

def parse_amount(value):
    if value is None:
        return None
    text = str(value).replace(',', '').replace('\xa0', '').replace(' ', '').replace('−', '-')
    if text in ('', '-', 'nan', 'None'):
        return None
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def first_amount(item, keys):
    for key in keys:
        value = parse_amount(item.get(key))
        if value is not None:
            return value, key
    return None, None


def amount_to_억(value):
    return round(value / 1e8, 1) if value is not None else None


def calculate_yoy(current, prev):
    if current is None or prev is None or prev == 0:
        return None
    return round((current - prev) / abs(prev) * 100, 1)


def safe_num(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


# ============================================================
# 연간 / 분기 추출
# ============================================================

def empty_annual(status='not_found', message='연간 영업이익을 찾지 못함'):
    return {
        'annual_year': None,
        'annual_latest_억': None,
        'annual_prev_억': None,
        'annual_yoy_%': None,
        'annual_fs_div': None,
        'annual_op_account_nm': None,
        'annual_op_account_id': None,
        'ocf_latest_억': None,
        'ocf_prev_억': None,
        'ocf_account_nm': None,
        'ocf_account_id': None,
        'dart_annual_status': status,
        'dart_annual_message': message,
        'dart_ocf_status': 'not_found',
        'dart_ocf_message': 'OCF 항목을 찾지 못함',
    }


def get_annual_metrics(corp_code, api_key):
    """연간 보고서에서 영업이익 YoY + OCF를 한 번의 호출로 함께 추출."""
    cy = datetime.now().year
    last_message = ''

    for year in [cy - 1, cy - 2]:
        for fs in ['CFS', 'OFS']:
            items, status, message = fetch_report_all(corp_code, year, REPRT_CODES['Y'], api_key, fs)
            time.sleep(REQUEST_SLEEP)
            if not items:
                last_message = f'{year} {fs}: {status} {message}'
                continue

            op = find_operating_profit(items)
            if not op:
                last_message = f'{year} {fs}: op_account_not_found'
                continue

            latest_op = parse_amount(op.get('thstrm_amount'))
            prev_op = parse_amount(op.get('frmtrm_amount'))
            annual_yoy = calculate_yoy(latest_op, prev_op)

            ocf_item = find_operating_cash_flow(items)
            ocf_latest = parse_amount(ocf_item.get('thstrm_amount')) if ocf_item else None
            ocf_prev = parse_amount(ocf_item.get('frmtrm_amount')) if ocf_item else None

            annual_status = 'ok' if annual_yoy is not None else 'op_found_yoy_missing'
            annual_message = '연간 영업이익 YoY 계산 성공' if annual_yoy is not None else '영업이익 항목은 찾았지만 현재/전기 금액 또는 전기 0 문제로 YoY 계산 실패'
            ocf_status = 'ok' if ocf_latest is not None else 'not_found'
            ocf_message = 'OCF 추출 성공' if ocf_latest is not None else 'OCF 항목 또는 금액을 찾지 못함'

            return {
                'annual_year': year,
                'annual_latest_억': amount_to_억(latest_op),
                'annual_prev_억': amount_to_억(prev_op),
                'annual_yoy_%': annual_yoy,
                'annual_fs_div': fs,
                'annual_op_account_nm': op.get('account_nm'),
                'annual_op_account_id': op.get('account_id'),
                'ocf_latest_억': amount_to_억(ocf_latest),
                'ocf_prev_억': amount_to_억(ocf_prev),
                'ocf_account_nm': ocf_item.get('account_nm') if ocf_item else None,
                'ocf_account_id': ocf_item.get('account_id') if ocf_item else None,
                'dart_annual_status': annual_status,
                'dart_annual_message': annual_message,
                'dart_ocf_status': ocf_status,
                'dart_ocf_message': ocf_message,
            }

    return empty_annual(message=last_message or '연간 보고서 데이터 없음')


def empty_quarterly(status='not_found', message='분기 영업이익을 찾지 못함'):
    return {
        'q_period': None,
        'q_basis': None,
        'q_latest_억': None,
        'q_prev_억': None,
        'quarterly_yoy_%': None,
        'q_latest_key': None,
        'q_prev_key': None,
        'q_fs_div': None,
        'q_source_api': None,
        'q_op_account_nm': None,
        'q_op_account_id': None,
        'dart_q_status': status,
        'dart_q_message': message,
    }


def _quarterly_from_op(op, year, period, fs, source_api):
    """영업이익 item에서 3개월 기준 → 누적 기준 순으로 YoY를 계산."""
    # 1순위: 3개월 기준. 전년 동기 3개월은 frmtrm_q_amount를 우선 사용.
    latest, latest_key = first_amount(op, ['thstrm_amount'])
    prev, prev_key = first_amount(op, ['frmtrm_q_amount', 'frmtrm_amount'])
    yoy = calculate_yoy(latest, prev)
    if yoy is not None:
        return {
            'q_period': f'{year} {period}',
            'q_basis': '3개월',
            'q_latest_억': amount_to_억(latest),
            'q_prev_억': amount_to_억(prev),
            'quarterly_yoy_%': yoy,
            'q_latest_key': latest_key,
            'q_prev_key': prev_key,
            'q_fs_div': fs,
            'q_source_api': source_api,
            'q_op_account_nm': op.get('account_nm'),
            'q_op_account_id': op.get('account_id'),
            'dart_q_status': 'ok',
            'dart_q_message': '3개월 기준 YoY 계산 성공',
        }

    # 2순위: 누적 기준. H1/Q3에서는 분기 YoY가 아니라 누적 YoY라 q_basis로 명시.
    latest, latest_key = first_amount(op, ['thstrm_add_amount'])
    prev, prev_key = first_amount(op, ['frmtrm_add_amount'])
    yoy = calculate_yoy(latest, prev)
    if yoy is not None:
        return {
            'q_period': f'{year} {period}',
            'q_basis': '누적',
            'q_latest_억': amount_to_억(latest),
            'q_prev_억': amount_to_억(prev),
            'quarterly_yoy_%': yoy,
            'q_latest_key': latest_key,
            'q_prev_key': prev_key,
            'q_fs_div': fs,
            'q_source_api': source_api,
            'q_op_account_nm': op.get('account_nm'),
            'q_op_account_id': op.get('account_id'),
            'dart_q_status': 'ok',
            'dart_q_message': '누적 기준 YoY 계산 성공',
        }

    return None


def build_quarterly_attempts(today=None):
    """
    [V2.6 패치] 현재 날짜 기준으로 가장 최근에 공시됐을 분기보고서부터 시도하는 리스트.

    DART 보고서 공시 마감일 (분기 종료 후 45일):
      • Q1 (1분기보고서): 5월 15일까지
      • H1 (반기보고서):  8월 14일까지
      • Q3 (3분기보고서): 11월 14일까지

    공시 지연 가능성을 감안해 마감일 다음 달 1일부터 안전하게 사용.
    전년도 보고서는 항상 fallback으로 포함 (이번 보고서 미공시 종목 보완).

    Returns: [(year, period), ...] 최신부터 오래된 순서
    """
    today = today or datetime.now()
    cy = today.year
    month = today.month

    attempts = []
    # 현재 연도 보고서 (마감일 + 여유)
    if month >= 12:                       # Q3 마감 11/14 → 12월부터
        attempts.append((cy, 'Q3'))
    if month >= 9:                        # H1 마감 8/14 → 9월부터
        attempts.append((cy, 'H1'))
    if month >= 6:                        # Q1 마감 5/15 → 6월부터
        attempts.append((cy, 'Q1'))

    # 전년도 보고서 (항상 fallback)
    attempts.extend([
        (cy - 1, 'Q3'),
        (cy - 1, 'H1'),
        (cy - 1, 'Q1'),
    ])

    return attempts


def get_quarterly_yoy(corp_code, api_key):
    """분기/반기/3분기 보고서에서 영업이익 YoY 추출."""
    attempts = build_quarterly_attempts()
    last_message = ''

    for year, period in attempts:
        reprt_code = REPRT_CODES[period]

        # 1) 전체 재무제표 API 우선
        for fs in ['CFS', 'OFS']:
            items, status, message = fetch_report_all(corp_code, year, reprt_code, api_key, fs)
            time.sleep(REQUEST_SLEEP)
            if not items:
                last_message = f'{year} {period} {fs} ALL: {status} {message}'
                continue
            op = find_operating_profit(items)
            if not op:
                last_message = f'{year} {period} {fs} ALL: op_account_not_found'
                continue
            result = _quarterly_from_op(op, year, period, fs, 'fnlttSinglAcntAll')
            if result:
                return result
            last_message = f'{year} {period} {fs} ALL: op_amount_missing_or_prev_zero'

        # 2) 주요계정 API 폴백. OCF는 없지만 분기 영업이익 매칭률 보완용.
        items, status, message = fetch_report_single(corp_code, year, reprt_code, api_key)
        time.sleep(REQUEST_SLEEP)
        if not items:
            last_message = f'{year} {period} SINGLE: {status} {message}'
            continue
        for fs in ['CFS', 'OFS']:
            fs_items = filter_items_by_fs(items, fs)
            if not fs_items:
                continue
            op = find_operating_profit(fs_items)
            if not op:
                last_message = f'{year} {period} {fs} SINGLE: op_account_not_found'
                continue
            result = _quarterly_from_op(op, year, period, fs, 'fnlttSinglAcnt')
            if result:
                return result
            last_message = f'{year} {period} {fs} SINGLE: op_amount_missing_or_prev_zero'

    return empty_quarterly(message=last_message or '분기 보고서 데이터 없음')


# ============================================================
# 점수 계산
# ============================================================

def classify_pattern(annual_yoy, quarterly_yoy):
    if annual_yoy is None or quarterly_yoy is None:
        return '데이터부족', 0
    if annual_yoy < -5 and quarterly_yoy > 10:
        return '턴어라운드', 20
    if annual_yoy > 5 and quarterly_yoy > 0:
        return '성장지속', 10
    if annual_yoy > 20 and quarterly_yoy < -10:
        return '피크아웃', -15
    if annual_yoy < 0 and quarterly_yoy < 0:
        return '하락지속', -10
    return '관망', 0


# ============================================================
# [V2.6 패치] OCF 점수 산업별 보정
# ============================================================
#
# 배경: OCF/OP 비율의 "정상 범위"는 산업마다 매우 다름.
#   - 건설/조선/해운: 매출 인식 시차로 OCF가 일시적으로 음수 가능 (밸류트랩 아님)
#   - IT/플랫폼/게임:  감가상각 작고 무형자산 큰 구조 → OCF/OP 평균이 1.0 이상
#   - 일반 제조업:     OCF/OP 0.7~1.2가 정상
#
# 이를 무시하고 단일 임계값(0.7/0.3)을 적용하면:
#   - 건설/조선 종목이 정상인데도 '밸류트랩의심'으로 잡힘 (false positive)
#   - IT 종목이 약함 신호인데도 '양호'로 잡힘 (false negative)
#
# FDR이 제공하는 Sector 컬럼을 키워드로 매칭해 3그룹으로 분류:
#   lenient: 관대  (OCF 변동성 큰 산업, 음수도 -5로 완화)
#   default: 표준  (0.7/0.3, 음수는 -10)
#   strict : 엄격  (높은 OCF/OP가 정상이라 0.9/0.5)

OCF_LENIENT_SECTOR_KEYWORDS = (
    '건설', '조선', '해운', '항공운수', '항공',
    '제약', '바이오', '의약',
    '플랜트', '엔지니어링', '기계',
)

OCF_STRICT_SECTOR_KEYWORDS = (
    '소프트웨어', '게임', '인터넷', '플랫폼',
    '서비스업',  # KRX 분류상 IT/플랫폼 다수 포함
)

# 그룹별 (good, mid, value_trap_penalty) — 음수 OCF일 때의 페널티 강도
OCF_THRESHOLDS = {
    'lenient': {'good': 0.5, 'mid': 0.2, 'neg_penalty': -5},
    'default': {'good': 0.7, 'mid': 0.3, 'neg_penalty': -10},
    'strict':  {'good': 0.9, 'mid': 0.5, 'neg_penalty': -10},
}


def classify_sector_group(sector):
    """sector 문자열을 'lenient' / 'default' / 'strict' 중 하나로 분류."""
    if not sector or (isinstance(sector, float) and pd.isna(sector)):
        return 'default'
    s = str(sector)
    for kw in OCF_LENIENT_SECTOR_KEYWORDS:
        if kw in s:
            return 'lenient'
    for kw in OCF_STRICT_SECTOR_KEYWORDS:
        if kw in s:
            return 'strict'
    return 'default'


def calculate_ocf_score(annual_op_억, ocf_latest_억, sector=None):
    """
    영업이익 대비 OCF 현금전환율을 산업 그룹별 임계값으로 점수화.

    Returns:
        (score, pattern, ratio, threshold_group)
    """
    group = classify_sector_group(sector)
    th = OCF_THRESHOLDS[group]

    if annual_op_억 is None or ocf_latest_억 is None:
        return 0, '데이터없음', None, group

    try:
        annual_op_억 = float(annual_op_억)
        ocf_latest_억 = float(ocf_latest_억)
    except Exception:
        return 0, '데이터없음', None, group

    if annual_op_억 > 0:
        ratio = ocf_latest_억 / annual_op_억
        if ocf_latest_억 < 0:
            # lenient 산업에선 음수도 일시적일 수 있어 페널티 완화 (-5)
            penalty = th['neg_penalty']
            return penalty, '밸류트랩의심', round(ratio, 2), group
        if ratio >= th['good']:
            return 5, '현금창출양호', round(ratio, 2), group
        if ratio >= th['mid']:
            return 2, '현금창출보통', round(ratio, 2), group
        return -3, '현금창출약함', round(ratio, 2), group

    if annual_op_억 <= 0 and ocf_latest_억 > 0:
        return 0, '회계손실현금유입', None, group
    return -5, '이중적자', None, group


def calculate_momentum_score(row):
    score = 0
    r1w = row.get('return_1w_%')
    r1m = row.get('return_1m_%')
    vol = row.get('volume_vs_avg')

    if pd.notna(r1w) and pd.notna(r1m):
        r1w = safe_num(r1w)
        r1m = safe_num(r1m)
        if r1w > 0 and r1m < 0:
            score += 5          # 명확한 단기 반등
        elif r1m < 0 and r1w > r1m / 4:
            score += 2          # 하락 둔화
        elif r1w > r1m / 4:
            score += 1          # 상승 추세 둔화 없음

        if r1m < 0 and r1w < r1m / 2:
            score -= 3          # 하락 가속

    if pd.notna(vol):
        vol = safe_num(vol)
        if 0.8 <= vol <= 1.3:
            score += 2
        elif vol >= 1.8:
            score += 1

    return max(-3, min(10, score))


def fmt_signed(value, digits=1, suffix=''):
    if value is None or pd.isna(value):
        return '?'
    return f'{float(value):+.{digits}f}{suffix}'


# ============================================================
# 메인
# ============================================================

def main():
    print(f"\n{'='*72}")
    print(f"🚀  [V2.6] 3단계: 펀더멘털 + 모멘텀 + OCF")
    print(f"{'='*72}")
    print(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    if "여기에" in DART_API_KEY or len(DART_API_KEY) < 30:
        print("❌ DART_API_KEY를 입력해주세요.")
        return

    # [V2.6 코스피/코스닥 통합] V2_INPUT_MARKET 환경변수로 시장 선택
    market = os.environ.get("V2_INPUT_MARKET", "kospi")
    input_pattern = f'v2_{market}_filtered_safe_*.csv'

    input_path = INPUT_CSV
    if not input_path or not Path(input_path).exists():
        candidates = sorted(Path('.').glob(input_pattern), reverse=True)
        if not candidates:
            print(f"❌ V2 2단계 결과({input_pattern})가 없습니다.")
            return
        input_path = str(candidates[0])

    print(f"1️⃣  입력: {input_path}")
    df = pd.read_csv(input_path, dtype={'ticker': str, 'corp_code': str})
    df['ticker'] = df['ticker'].astype(str).str.zfill(6)
    df['corp_code'] = df['corp_code'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(8)
    print(f"   ✓ {len(df)}개 종목 로드")

    if 'market_regime' in df.columns and len(df) > 0:
        regime = df['market_regime'].iloc[0]
        regime_score = safe_num(df['regime_score'].iloc[0]) if 'regime_score' in df.columns else 0
        emoji = {'강세': '🟢', '조정': '🟡', '반등': '🟠', '약세': '🔴'}.get(regime, '⚪')
        print(f"   🏛️  시장 레짐: {emoji} {regime}장 (전 종목 {regime_score:+.0f}점)")

    df['oversold_score'] = pd.to_numeric(df.get('oversold_score', 0), errors='coerce').fillna(0)
    df = df[df['oversold_score'] >= MIN_OVERSOLD_SCORE].copy().reset_index(drop=True)
    print(f"   ✓ 과매도 {MIN_OVERSOLD_SCORE}점 이상: {len(df)}개 분석\n")

    print(f"2️⃣  DART 실적 추세 + OCF 분석")
    print(f"   ({len(df) * 0.8 / MAX_WORKERS:.0f}초 예상, 병렬 {MAX_WORKERS}스레드)\n")

    # [V2.6 자동화] 병렬 처리 — 각 종목 분석은 독립적이라 안전
    def analyze_one(row_dict):
        """한 종목의 펀더멘털/OCF 분석. 스레드에서 독립 실행 가능."""
        annual = get_annual_metrics(row_dict['corp_code'], DART_API_KEY)
        quarterly = get_quarterly_yoy(row_dict['corp_code'], DART_API_KEY)

        pattern, fund_score = classify_pattern(
            annual['annual_yoy_%'], quarterly['quarterly_yoy_%']
        )

        sector_val = row_dict.get('sector')
        ocf_score, ocf_pattern, ocf_ratio, ocf_group = calculate_ocf_score(
            annual['annual_latest_억'], annual['ocf_latest_억'], sector=sector_val
        )

        # name은 print용으로만 사용. results 들어가는 dict엔 포함 안 함 (merge 충돌 방지)
        return row_dict.get('name', row_dict['ticker']), {
            'ticker': row_dict['ticker'],
            **annual,
            **quarterly,
            'earnings_pattern': pattern,
            'fundamental_score': fund_score,
            'ocf_score': ocf_score,
            'ocf_pattern': ocf_pattern,
            'ocf_to_op_ratio': ocf_ratio,
            'ocf_threshold_group': ocf_group,
        }

    results = []
    annual_op_count = 0
    quarterly_op_count = 0
    ocf_found_count = 0
    print_lock = threading.Lock()
    completed = 0
    total = len(df)
    start_time = time.time()

    # iterrows 결과를 dict로 변환 (스레드 안전)
    rows_list = [row.to_dict() for _, row in df.iterrows()]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(analyze_one, r): r for r in rows_list}

        for future in as_completed(futures):
            try:
                name_for_log, result = future.result()
            except Exception as e:
                row = futures[future]
                print(f"   ⚠️  {row.get('name', row.get('ticker'))} 분석 실패: {e}")
                continue

            results.append(result)

            if result.get('annual_yoy_%') is not None:
                annual_op_count += 1
            if result.get('quarterly_yoy_%') is not None:
                quarterly_op_count += 1
            if result.get('ocf_latest_억') is not None:
                ocf_found_count += 1

            with print_lock:
                completed += 1
                if completed % 10 == 0 or completed == total:
                    elapsed = time.time() - start_time
                    name = str(name_for_log)[:10]
                    basis = result.get('q_basis') or '-'
                    pattern = result.get('earnings_pattern', '-')
                    ocf_pat = result.get('ocf_pattern', '-')
                    ocf_grp = result.get('ocf_threshold_group', '-')
                    eta = (elapsed / completed) * (total - completed) if completed > 0 else 0
                    print(f"   [{completed:>3}/{total}] {name:<12} "
                          f"→ {pattern} / Q:{basis} / OCF:{ocf_pat}({str(ocf_grp)[:3]}) "
                          f"({elapsed:.0f}s, 남은 ~{eta:.0f}s)")

    df_fund = pd.DataFrame(results)
    df_final = df.merge(df_fund, on='ticker', how='left')

    df_final['momentum_score'] = df_final.apply(calculate_momentum_score, axis=1)

    for col in ['acc_score', 'trend_score', 'supply_score', 'regime_score',
                'fundamental_score', 'momentum_score', 'ocf_score', 'oversold_score']:
        if col not in df_final.columns:
            df_final[col] = 0
        df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0)

    if 'falling_knife' in df_final.columns:
        df_final['falling_knife'] = df_final['falling_knife'].fillna(False).astype(str).str.lower().isin(['true', '1', 'yes'])
    else:
        df_final['falling_knife'] = False

    df_final['ocf_pattern'] = df_final['ocf_pattern'].fillna('데이터없음')
    df_final['earnings_pattern'] = df_final['earnings_pattern'].fillna('데이터부족')

    # stock_score: 종목 자체 점수. final_score: 시장 레짐까지 반영한 실전 점수.
    df_final['stock_score'] = (
        df_final['oversold_score']
        + df_final['acc_score']
        + df_final['trend_score']
        + df_final['supply_score']
        + df_final['fundamental_score']
        + df_final['momentum_score']
        + df_final['ocf_score']
    ).round(1)

    df_final['final_score'] = (df_final['stock_score'] + df_final['regime_score']).round(1)
    df_final = df_final.sort_values('final_score', ascending=False).reset_index(drop=True)

    # ===== DART 매칭 진단 =====
    n = len(df)
    ann_rate = annual_op_count / n * 100 if n > 0 else 0
    qtr_rate = quarterly_op_count / n * 100 if n > 0 else 0
    ocf_rate = ocf_found_count / n * 100 if n > 0 else 0

    print(f"\n{'='*72}")
    print(f"📊  DART 매칭 진단")
    print(f"{'='*72}")
    print(f"   • 연간 영업이익 YoY: {annual_op_count}/{n} ({ann_rate:.0f}%)")
    print(f"   • 분기/누적 영업이익 YoY: {quarterly_op_count}/{n} ({qtr_rate:.0f}%)")
    print(f"   • OCF(영업현금흐름): {ocf_found_count}/{n} ({ocf_rate:.0f}%)")

    if 'dart_q_status' in df_final.columns:
        print(f"\n   분기 DART 상태 분포:")
        for status, cnt in df_final['dart_q_status'].fillna('unknown').value_counts().items():
            print(f"     - {status}: {cnt}개")

    if qtr_rate < 30 and n >= 20:
        print(f"   ⚠️  분기 영업이익 매칭률이 낮습니다. CSV의 dart_q_message/q_latest_key/q_prev_key를 확인하세요.")

    print(f"\n📈  실적 패턴 분포")
    emoji_map = {'턴어라운드': '⭐', '성장지속': '✅', '관망': '⚪',
                 '데이터부족': '❓', '하락지속': '⚠️', '피크아웃': '❌'}
    for pat, cnt in df_final['earnings_pattern'].value_counts().items():
        print(f"   {emoji_map.get(pat, '·')} {pat}: {cnt}개")

    print(f"\n💰  OCF 패턴 분포")
    ocf_emoji = {'현금창출양호': '💚', '현금창출보통': '✅', '현금창출약함': '🟡',
                 '밸류트랩의심': '🚨', '회계손실현금유입': '⚪',
                 '이중적자': '🔻', '데이터없음': '❓'}
    for pat, cnt in df_final['ocf_pattern'].value_counts().items():
        print(f"   {ocf_emoji.get(pat, '·')} {pat}: {cnt}개")

    # [V2.6 패치] 산업 그룹 분포 + sector coverage 표시
    if 'ocf_threshold_group' in df_final.columns:
        print(f"\n🏷️  OCF 산업 그룹 분포 (false positive 보정)")
        group_emoji = {'lenient': '🟦', 'default': '⚪', 'strict': '🟥'}
        for grp, cnt in df_final['ocf_threshold_group'].fillna('default').value_counts().items():
            label = {'lenient': '관대 (건설/조선/제약 등)',
                     'default': '표준',
                     'strict':  '엄격 (IT/플랫폼 등)'}.get(grp, grp)
            print(f"   {group_emoji.get(grp, '·')} {label}: {cnt}개")

        # sector 컬럼 매칭률 (FDR이 제공했는지 확인)
        if 'sector' in df_final.columns:
            sec_n = df_final['sector'].notna().sum()
            sec_rate = sec_n / len(df_final) * 100 if len(df_final) > 0 else 0
            print(f"   ℹ️   sector 컬럼 매칭: {sec_n}/{len(df_final)} ({sec_rate:.0f}%)")
            if sec_rate < 50:
                print(f"   ⚠️   sector 매칭률 낮음 — 대부분 default 임계값으로 처리됨")

    value_traps = df_final[df_final['ocf_pattern'] == '밸류트랩의심']
    if len(value_traps) > 0:
        print(f"\n🚨  밸류트랩 의심 종목 (영업이익 흑자 / OCF 적자):")
        for _, row in value_traps.head(10).iterrows():
            op_str = fmt_signed(row.get('annual_latest_억'), 0, '억')
            ocf_str = fmt_signed(row.get('ocf_latest_억'), 0, '억')
            ratio = row.get('ocf_to_op_ratio')
            ratio_str = f", OCF/OP {ratio:.2f}x" if pd.notna(ratio) else ''
            grp = row.get('ocf_threshold_group') or 'default'
            penalty = OCF_THRESHOLDS[grp]['neg_penalty']
            grp_tag = f" [{grp}]" if grp != 'default' else ''
            print(f"   • {row['name']} ({row['ticker']}){grp_tag}  "
                  f"OP {op_str} / OCF {ocf_str}{ratio_str}  → {penalty}점")

    weak_cash = df_final[df_final['ocf_pattern'] == '현금창출약함']
    if len(weak_cash) > 0:
        print(f"\n🟡  현금창출 약함 종목 (OP 대비 OCF 낮음): {len(weak_cash)}개")

    fk_count = int(df_final['falling_knife'].sum())
    if fk_count > 0:
        print(f"\n⚠️  떨어지는 칼날 (추세 -30점 패널티): {fk_count}개")

    print(f"\n{'='*72}")
    print(f"🏆  [V2.6] 최종 점수 TOP {TOP_N}")
    print(f"{'='*72}\n")

    print(f"{'#':>3} {'종목명':<12} {'코드':<8} "
          f"{'과매':>5} {'매집':>3} {'추세':>4} {'수급':>3} "
          f"{'펀더':>4} {'모멘':>4} {'OCF':>4} {'종목':>6} {'레짐':>4} {'최종':>6}  {'패턴':<8}")
    print('-' * 122)
    for i, row in df_final.head(TOP_N).iterrows():
        name = (str(row['name']) or row['ticker'])[:10]
        print(f"{i+1:>3} {name:<12} {row['ticker']:<8} "
              f"{row['oversold_score']:>5.1f} "
              f"{row['acc_score']:>+3.0f} "
              f"{row['trend_score']:>+4.0f}  "
              f"{row['supply_score']:>+3.0f} "
              f"{row['fundamental_score']:>+3.0f}  "
              f"{row['momentum_score']:>+3.0f}  "
              f"{row['ocf_score']:>+3.0f}  "
              f"{row['stock_score']:>5.1f} "
              f"{row['regime_score']:>+4.0f} "
              f"{row['final_score']:>5.1f}  "
              f"{row['earnings_pattern']:<8}")

    turnaround = df_final[df_final['earnings_pattern'] == '턴어라운드']
    if len(turnaround) > 0:
        print(f"\n⭐ 턴어라운드 종목 (최우선 후보)")
        for _, row in turnaround.head(10).iterrows():
            f5 = row.get('foreign_5d_억')
            i5 = row.get('inst_5d_억')
            f_str = fmt_signed(f5, 0, '억') if pd.notna(f5) else '데이터없음'
            i_str = fmt_signed(i5, 0, '억') if pd.notna(i5) else '데이터없음'
            ocf_str = fmt_signed(row.get('ocf_latest_억'), 0, '억') if pd.notna(row.get('ocf_latest_억')) else '?'
            q_yoy = fmt_signed(row.get('quarterly_yoy_%'), 1, '%') if pd.notna(row.get('quarterly_yoy_%')) else '?'
            print(f"\n• {row['name']} ({row['ticker']}) - 최종: {row['final_score']}")
            print(f"  연간 YoY: {fmt_signed(row.get('annual_yoy_%'), 1, '%')} ({row.get('annual_year')})  "
                  f"OCF: {ocf_str} → {row['ocf_pattern']}")
            print(f"  분기/누적 YoY: {q_yoy} ({row.get('q_period')}, {row.get('q_basis')})")
            print(f"  외인5일: {f_str} / 기관5일: {i_str}")

    if 'foreign_5d_억' in df_final.columns:
        div = df_final[
            (pd.to_numeric(df_final['return_1m_%'], errors='coerce') <= -10) &
            ((pd.to_numeric(df_final['foreign_5d_억'], errors='coerce').fillna(0) > 0) |
             (pd.to_numeric(df_final['inst_5d_억'], errors='coerce').fillna(0) > 0))
        ].head(10)
        if len(div) > 0:
            print(f"\n💎 다이버전스 종목 (낙폭 + 큰손 매수):")
            for _, row in div.iterrows():
                f5 = safe_num(row.get('foreign_5d_억'))
                i5 = safe_num(row.get('inst_5d_억'))
                ocf_mark = ''
                if row['ocf_pattern'] == '밸류트랩의심':
                    ocf_mark = ' 🚨밸류트랩'
                elif row['ocf_pattern'] in ('현금창출양호', '현금창출보통'):
                    ocf_mark = ' 💚현금OK'
                print(f"   • {str(row['name'])[:12]:<14} ({row['ticker']}) "
                      f"최종 {row['final_score']:>5.1f}점  "
                      f"1개월 {safe_num(row.get('return_1m_%')):+5.1f}%  "
                      f"외인 {f5:+5.0f}억  기관 {i5:+5.0f}억{ocf_mark}")

    if 'market_regime' in df_final.columns and len(df_final) > 0:
        if df_final['market_regime'].iloc[0] == '약세':
            print(f"\n{'!'*72}")
            print(f"⚠️  현재 약세장 — final_score는 레짐 페널티가 반영되어 있습니다.")
            print(f"   종목 자체 순위는 stock_score도 함께 보세요.")
            print(f"{'!'*72}")

    fk_in_top = df_final.head(TOP_N)[df_final.head(TOP_N)['falling_knife']]
    if len(fk_in_top) > 0:
        print(f"\n⚠️  TOP {TOP_N} 안에 떨어지는 칼날 종목이 있습니다 (주의):")
        for _, row in fk_in_top.iterrows():
            print(f"   • {row['name']} ({row['ticker']}) - 최종 {row['final_score']}점")

    df_final = df_final.replace(r'[\r\n]+', ' ', regex=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    output_file = f"v2_{market}_final_{timestamp}.csv"
    df_final.to_csv(output_file, index=False, encoding='utf-8-sig')

    print(f"\n💾 [V2.6] 최종 결과: {output_file}\n")


if __name__ == "__main__":
    main()
