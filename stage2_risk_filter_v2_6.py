#!/usr/bin/env python3
"""
[V2.6] 2단계: 리스크 필터 (개선 버전)
========================================
V2.6 개선 사항:
  ① 가짜 악재 방어 패턴을 2단계로 분리 (STRONG/SOFT)
     - STRONG (사실무근/정지해제) → 위험에서 안전으로
     - SOFT (해명/조회공시/미확정) → 위험에서 '주의'로 강등 (확인 권장)
  ② CSV 저장 시 셀 내 줄바꿈 자동 제거 (HTML 파싱 안전성)

[실행]
    1. DART_API_KEY 입력
    2. v2_kospi_oversold_*.csv가 같은 폴더에 있어야 함
    3. python stage2_risk_filter_v2.py
"""

import io
import zipfile
import xml.etree.ElementTree as ET
import requests
import pandas as pd
import time
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


# ============================================================
# 설정
# ============================================================

import os

# [V2.6 자동화] 환경변수 우선, 없으면 빈 값 → 자동화 시 GitHub Secrets 사용
# 로컬 실행 시: .env 파일에 DART_API_KEY="..." 작성 후 export 또는 python-dotenv 사용
DART_API_KEY = os.environ.get("DART_API_KEY", "")
INPUT_CSV = None
LOOKBACK_DAYS = 365
CACHE_DIR = "dart_cache"

# [V2.6 자동화] 병렬 처리 — DART rate limit 고려 4스레드
MAX_WORKERS = 4


# ============================================================
# 위험/주의/제외 키워드
# ============================================================

DANGER_KEYWORDS = [
    "감사의견거절", "감사의견한정", "감사의견 거절", "감사의견 한정",
    "관리종목", "상장폐지",
    "주권매매거래정지", "거래정지",
    "횡령", "배임", "분식회계",
    "회생절차", "법정관리", "워크아웃",
    "자본잠식",
]

WARNING_KEYWORDS = [
    "유상증자", "전환사채", "신주인수권부사채",
    "주식병합", "감자결정",
    "최대주주변경", "대규모손실",
]

# [개선 #1] 가짜 악재 방어 패턴 (V2.6: 2단계 분리)
# STRONG: 명백한 부인/호재 → 위험에서 안전으로 (false positive 처리)
# SOFT  : 모호한 답변/진행 중 → 위험에서 주의로 강등 (확인 필요)
STRONG_EXCLUDE_PATTERNS = [
    "사실무근",        # 풍문 완전 부인
    "정지해제",        # 거래정지 → 해제 (호재)
]

SOFT_EXCLUDE_PATTERNS = [
    "해명",            # 해명 공시 (일부 인정 가능성)
    "부인",            # 부인 표명 (재발 가능)
    "조회공시",        # 조회공시 답변 (미확정/진행 중일 수 있음)
    "미확정",          # 확정 안 됨 (폭탄 진행 중)
]


# ============================================================
# OpenDART API (V1과 동일)
# ============================================================

def get_corp_code_mapping(api_key):
    Path(CACHE_DIR).mkdir(exist_ok=True)
    cache_file = Path(CACHE_DIR) / "corp_code.csv"

    if cache_file.exists():
        age_days = (datetime.now() -
                    datetime.fromtimestamp(cache_file.stat().st_mtime)).days
        if age_days < 30:
            print(f"   📂 캐시된 기업코드 매핑 사용 ({age_days}일 전)")
            return pd.read_csv(cache_file, dtype=str)

    print("   📥 DART 기업코드 매핑 다운로드 중...")
    resp = requests.get(
        "https://opendart.fss.or.kr/api/corpCode.xml",
        params={"crtfc_key": api_key}, timeout=30,
    )
    if resp.headers.get('Content-Type', '').startswith('application/json'):
        raise ValueError(f"DART API 오류: {resp.text}")

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        xml_data = z.read(z.namelist()[0])

    root = ET.fromstring(xml_data)
    records = []
    for item in root.findall('list'):
        stock_code = (item.findtext('stock_code') or '').strip()
        if stock_code:
            records.append({
                'corp_code': (item.findtext('corp_code') or '').strip(),
                'corp_name': (item.findtext('corp_name') or '').strip(),
                'stock_code': stock_code,
            })

    df = pd.DataFrame(records)
    df.to_csv(cache_file, index=False, encoding='utf-8-sig')
    print(f"   ✓ {len(df)}개 상장기업 매핑 저장")
    return df


def fetch_disclosures(corp_code, api_key, days_back=365):
    """DART 공시 목록을 total_page 기준으로 끝까지 조회."""
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")

    all_disclosures = []
    page = 1
    while True:
        try:
            resp = requests.get(
                "https://opendart.fss.or.kr/api/list.json",
                params={
                    "crtfc_key": api_key,
                    "corp_code": corp_code,
                    "bgn_de": start_date,
                    "end_de": end_date,
                    "page_no": page,
                    "page_count": 100,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get('status') != '000':
                break

            disclosures = data.get('list', []) or []
            all_disclosures.extend(disclosures)

            try:
                total_page = int(data.get('total_page', page))
            except Exception:
                total_page = page

            if page >= total_page or len(disclosures) == 0:
                break

            page += 1
            time.sleep(0.05)
        except Exception:
            break

    return all_disclosures


# ============================================================
# [개선 #1] 가짜 악재 방어가 추가된 키워드 검사
# ============================================================

def _dart_viewer_url(rcept_no):
    if not rcept_no:
        return ''
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


def _disc_entry(disc):
    report_name = disc.get('report_nm', '') or ''
    rcept_dt = disc.get('rcept_dt', '') or ''
    rcept_no = disc.get('rcept_no', '') or ''
    url = _dart_viewer_url(rcept_no)
    return f"[{rcept_dt}] {report_name} ({rcept_no})", url, rcept_no


def check_risk_keywords(disclosures):
    danger_hits, danger_urls, danger_rcepts = [], [], []
    warning_hits, warning_urls, warning_rcepts = [], [], []
    false_positive_avoided, fp_urls, fp_rcepts = [], [], []
    soft_downgraded, soft_urls, soft_rcepts = [], [], []

    for disc in disclosures:
        report_name = disc.get('report_nm', '') or ''
        name_norm = report_name.replace(' ', '')
        entry, url, rcept_no = _disc_entry(disc)

        # 제외 패턴 사전 확인 (STRONG / SOFT 분리)
        has_strong = any(ex.replace(' ', '') in name_norm for ex in STRONG_EXCLUDE_PATTERNS)
        has_soft = any(ex.replace(' ', '') in name_norm for ex in SOFT_EXCLUDE_PATTERNS)

        danger_found = False
        for kw in DANGER_KEYWORDS:
            if kw.replace(' ', '') in name_norm:
                danger_found = True
                if has_strong:
                    false_positive_avoided.append(entry)
                    fp_urls.append(url)
                    fp_rcepts.append(rcept_no)
                elif has_soft:
                    soft_downgraded.append(entry)
                    soft_urls.append(url)
                    soft_rcepts.append(rcept_no)
                    warning_hits.append(entry)
                    warning_urls.append(url)
                    warning_rcepts.append(rcept_no)
                else:
                    danger_hits.append(entry)
                    danger_urls.append(url)
                    danger_rcepts.append(rcept_no)
                break

        if not danger_found and not has_strong and not has_soft:
            for kw in WARNING_KEYWORDS:
                if kw.replace(' ', '') in name_norm:
                    warning_hits.append(entry)
                    warning_urls.append(url)
                    warning_rcepts.append(rcept_no)
                    break

    return {
        'danger_count': len(danger_hits),
        'warning_count': len(warning_hits),
        'fp_avoided_count': len(false_positive_avoided),
        'soft_downgraded_count': len(soft_downgraded),
        'danger_details': ' || '.join(danger_hits[:3]),
        'warning_details': ' || '.join(warning_hits[:3]),
        'fp_avoided_details': ' || '.join(false_positive_avoided[:3]),
        'soft_downgraded_details': ' || '.join(soft_downgraded[:3]),
        'danger_urls': ' || '.join([u for u in danger_urls[:3] if u]),
        'warning_urls': ' || '.join([u for u in warning_urls[:3] if u]),
        'fp_avoided_urls': ' || '.join([u for u in fp_urls[:3] if u]),
        'soft_downgraded_urls': ' || '.join([u for u in soft_urls[:3] if u]),
        'danger_rcept_nos': ' || '.join([r for r in danger_rcepts[:3] if r]),
        'warning_rcept_nos': ' || '.join([r for r in warning_rcepts[:3] if r]),
    }


# ============================================================
# 메인
# ============================================================

def main():
    print(f"\n{'='*72}")
    print(f"🛡️   [V2] 2단계 리스크 필터 (가짜 악재 방어 적용)")
    print(f"{'='*72}")
    print(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    if "여기에" in DART_API_KEY or len(DART_API_KEY) < 30:
        print("❌ DART_API_KEY를 입력해주세요.")
        return

    # [V2.6 코스피/코스닥 통합] V2_INPUT_MARKET 환경변수로 시장 선택
    market = os.environ.get("V2_INPUT_MARKET", "kospi")
    input_pattern = f'v2_{market}_oversold_*.csv'
    output_market = market

    # [V2] V2 입력 파일 자동 탐색
    input_path = INPUT_CSV
    if not input_path or not Path(input_path).exists():
        candidates = sorted(Path('.').glob(input_pattern), reverse=True)
        if not candidates:
            print(f"❌ V2 1단계 결과({input_pattern})를 찾을 수 없습니다.")
            print(f"   먼저 {market}_screener_fdr_v2_6.py 실행")
            return
        input_path = str(candidates[0])

    print(f"1️⃣  입력 CSV: {input_path}")
    df_input = pd.read_csv(input_path, dtype={'ticker': str})
    df_input['ticker'] = df_input['ticker'].str.zfill(6)
    print(f"   ✓ {len(df_input)}개 종목 로드")

    # V2에서는 composite_score 기준으로 필터 (oversold + acc_score)
    score_col = 'composite_score' if 'composite_score' in df_input.columns else 'oversold_score'
    # [V2.6 자동화] 2단계 검사 대상을 composite_score 40 이상으로 제한
    # (기존 30은 실행 시간 과다 — 코스피 520개 → 200개로 축소)
    df_input = df_input[df_input[score_col] >= 40].copy()
    print(f"   ✓ {score_col} 30점 이상: {len(df_input)}개 (DART 검사 대상)")

    print(f"\n2️⃣  DART 기업코드 매핑")
    df_corp = get_corp_code_mapping(DART_API_KEY)
    df_corp['stock_code'] = df_corp['stock_code'].str.zfill(6)

    df_merged = df_input.merge(
        df_corp[['stock_code', 'corp_code']],
        left_on='ticker', right_on='stock_code', how='left',
    )
    no_match = df_merged['corp_code'].isna().sum()
    if no_match > 0:
        print(f"   ⚠️  DART 미등록: {no_match}개 (제외)")
    df_merged = df_merged.dropna(subset=['corp_code']).reset_index(drop=True)

    print(f"\n3️⃣  {len(df_merged)}개 종목 공시 검사 중...")
    print(f"   ({len(df_merged) * 0.2 / MAX_WORKERS:.0f}초 예상, 병렬 {MAX_WORKERS}스레드)\n")

    # [V2.6 자동화] 병렬 처리
    def check_one(row_dict):
        """한 종목의 DART 공시 위험 검사. 스레드 안전."""
        disclosures = fetch_disclosures(row_dict['corp_code'], DART_API_KEY, LOOKBACK_DAYS)
        risk = check_risk_keywords(disclosures)
        risk['ticker'] = row_dict['ticker']
        return row_dict.get('name', row_dict['ticker']), risk

    risk_results = []
    print_lock = threading.Lock()
    completed = 0
    total = len(df_merged)
    start_time = time.time()

    rows_list = [row.to_dict() for _, row in df_merged.iterrows()]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(check_one, r): r for r in rows_list}

        for future in as_completed(futures):
            try:
                name_for_log, risk = future.result()
            except Exception as e:
                row = futures[future]
                print(f"   ⚠️  {row.get('name', row.get('ticker'))} 검사 실패: {e}")
                continue

            risk_results.append(risk)

            with print_lock:
                completed += 1
                if completed % 10 == 0 or completed == total:
                    elapsed = time.time() - start_time
                    eta = (elapsed / completed) * (total - completed) if completed > 0 else 0
                    print(f"   [{completed:>3}/{total}] {str(name_for_log)[:10]} "
                          f"({elapsed:.0f}s, 남은 ~{eta:.0f}s)")

    df_risk = pd.DataFrame(risk_results)

    # 결합
    df_final = df_merged.merge(df_risk, on='ticker', how='left')
    for col in ['danger_count', 'warning_count', 'fp_avoided_count', 'soft_downgraded_count']:
        if col in df_final.columns:
            df_final[col] = df_final[col].fillna(0).astype(int)
        else:
            df_final[col] = 0

    df_final['risk_level'] = '안전'
    df_final.loc[df_final['warning_count'] > 0, 'risk_level'] = '주의'
    df_final.loc[df_final['danger_count'] > 0, 'risk_level'] = '위험'

    safe = df_final[df_final['risk_level'] == '안전']
    caution = df_final[df_final['risk_level'] == '주의']
    danger = df_final[df_final['risk_level'] == '위험']
    fp_count = df_final['fp_avoided_count'].sum()
    soft_count = df_final['soft_downgraded_count'].sum()

    print(f"\n{'='*72}")
    print(f"📊  검사 결과")
    print(f"{'='*72}")
    print(f"   ✅ 안전:           {len(safe):>3}개")
    print(f"   ⚠️  주의:           {len(caution):>3}개")
    print(f"   ❌ 위험:           {len(danger):>3}개")
    print(f"   🛡️  명백한 부인 (안전 처리): {fp_count:>3}건")
    print(f"   ⚠️  모호한 답변 (주의 강등): {soft_count:>3}건  ← 원문 확인 권장")

    if soft_count > 0:
        print(f"\n⚠️ 주의로 강등된 종목 (TOP 5) - DART에서 원문 직접 확인 권장:")
        soft_rows = df_final[df_final['soft_downgraded_count'] > 0].head(5)
        for _, row in soft_rows.iterrows():
            print(f"   • {row['name']} ({row['ticker']}): {row['soft_downgraded_details']}")

    if fp_count > 0:
        print(f"\n🛡️ 가짜 악재 방어로 살아남은 종목 (TOP 5):")
        saved = df_final[df_final['fp_avoided_count'] > 0].head(5)
        for _, row in saved.iterrows():
            print(f"   • {row['name']} ({row['ticker']}): {row['fp_avoided_details']}")

    if len(danger) > 0:
        print(f"\n❌ 위험 종목 상세 (V2 기준):")
        for _, row in danger.iterrows():
            print(f"\n   • {row['name']} ({row['ticker']})")
            print(f"     점수: {row[score_col]:.1f}")
            print(f"     발견: {row['danger_details']}")

    # 저장 (CSV 안전성: 셀 내 줄바꿈 → 공백 치환)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    safe_with_caution = df_final[df_final['risk_level'].isin(['안전', '주의'])]

    # [개선 #3] 셀 안의 줄바꿈 문자 제거 (HTML 파싱 안전성)
    safe_with_caution = safe_with_caution.replace(r'[\r\n]+', ' ', regex=True)
    df_final_safe = df_final.replace(r'[\r\n]+', ' ', regex=True)

    safe_file = f"v2_{output_market}_filtered_safe_{timestamp}.csv"
    safe_with_caution.to_csv(safe_file, index=False, encoding='utf-8-sig')

    all_file = f"v2_{output_market}_filtered_all_{timestamp}.csv"
    df_final_safe.to_csv(all_file, index=False, encoding='utf-8-sig')

    print(f"\n💾 결과 파일:")
    print(f"   • {safe_file}  ({len(safe_with_caution)}개)")
    print(f"   • {all_file}   ({len(df_final)}개)\n")


if __name__ == "__main__":
    main()
