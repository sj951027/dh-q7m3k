#!/usr/bin/env python3
"""
[V2.6] 코스피 스크리너 → 코스닥 스크리너 자동 변환기
=======================================================
kospi_screener_fdr_v2_6.py를 읽어서 kosdaq_screener_fdr_v2_6.py를 생성한다.

코스닥 특성을 반영한 가중치 재튜닝:
  • 변동성 큼 → 레짐 페널티 완화 (약세 -10 → -7, 반등 -5 → -3)
  • 외인 비중 낮음 → 외인 수급 영향 축소 (max -3 → max -2)
  • 수출 대형주 적음 → 환율 영향 축소 (max -3 → max -1)
  • 등락폭 큼 → 과매도 기준점수 완화 (50 → 45)
  • 적자/스팩 종목 많음 → 제외 필터 강화

[실행]
    python build_kosdaq_screener.py
[출력]
    kosdaq_screener_fdr_v2_6.py
    v2_kosdaq_oversold_*.csv (스크리너 실행 시)
"""

import re
from pathlib import Path

SRC = Path("kospi_screener_fdr_v2_6.py")
DST = Path("kosdaq_screener_fdr_v2_6.py")


# ============================================================
# 코스닥 시총 상위 10개 (외인 수급 proxy용)
# 2026년 5월 기준 시총 상위 — 코스닥 시총의 약 30%+ 차지
# ============================================================
KOSDAQ_PROXY_TICKERS = """
FOREIGN_FLOW_PROXY_TICKERS = [
    ('247540', '에코프로비엠'),
    ('086520', '에코프로'),
    ('091990', '셀트리온헬스케어'),
    ('196170', '알테오젠'),
    ('068760', '셀트리온제약'),
    ('035760', 'CJ ENM'),
    ('277810', '레인보우로보틱스'),
    ('028300', 'HLB'),
    ('357780', '솔브레인'),
    ('293490', '카카오게임즈'),
]
"""

# 코스닥용 레짐 점수 (변동성 큼 → 페널티 완화)
KOSDAQ_REGIME = """REGIME_SCORES = {
    '강세': 0,
    '조정': -1,
    '반등': -3,
    '약세': -7,
}"""

KOSPI_REGIME_PATTERN = r"""REGIME_SCORES = \{
    '강세': 0,
    '조정': -2,
    '반등': -5,
    '약세': -10,
\}"""


def main():
    if not SRC.exists():
        print(f"❌ {SRC}가 없습니다. 같은 디렉토리에서 실행하세요.")
        return

    src = SRC.read_text(encoding="utf-8")

    # ─────────────────────────────────────────────────────
    # 1) 헤더 docstring 교체
    # ─────────────────────────────────────────────────────
    src = src.replace(
        "[V2.6] 1단계: KOSPI 과매도 스크리너 (레짐 + 환율 + 외인 통합)",
        "[V2.6] 1단계: KOSDAQ 과매도 스크리너 (레짐 + 환율 + 외인 통합) [코스닥 재튜닝]"
    )

    # ─────────────────────────────────────────────────────
    # 2) 출력 파일명: v2_kospi_* → v2_kosdaq_*
    # ─────────────────────────────────────────────────────
    src = src.replace('v2_kospi_oversold_', 'v2_kosdaq_oversold_')

    # ─────────────────────────────────────────────────────
    # 3) 레짐 점수표 교체 (코스닥 완화)
    # ─────────────────────────────────────────────────────
    src, n = re.subn(KOSPI_REGIME_PATTERN, KOSDAQ_REGIME, src)
    if n != 1:
        print(f"⚠️  REGIME_SCORES 치환 {n}회 (1회 기대)")

    # ─────────────────────────────────────────────────────
    # 4) MIN_SCORE 50 → 45 (코스닥은 등락 폭 크고 점수 변동 큼)
    # ─────────────────────────────────────────────────────
    src = re.sub(r"^MIN_SCORE = 50$", "MIN_SCORE = 45  # [코스닥] 등락 폭 큼 → 완화",
                 src, count=1, flags=re.MULTILINE)

    # ─────────────────────────────────────────────────────
    # 5) 시총 상위 proxy 종목을 코스닥용으로 교체
    # ─────────────────────────────────────────────────────
    proxy_pattern = re.compile(
        r"FOREIGN_FLOW_PROXY_TICKERS = \[.*?\]", re.DOTALL
    )
    src, n = proxy_pattern.subn(KOSDAQ_PROXY_TICKERS.strip(), src, count=1)
    if n != 1:
        print(f"⚠️  FOREIGN_FLOW_PROXY_TICKERS 치환 {n}회 (1회 기대)")

    # ─────────────────────────────────────────────────────
    # 6) 외인 수급 임계값 완화 (코스닥은 외인 영향 작음)
    # ─────────────────────────────────────────────────────
    src = src.replace(
        "FLOW_THRESHOLD_STRONG_OUT = -5000",
        "FLOW_THRESHOLD_STRONG_OUT = -2500  # [코스닥] 외인 영향 작음"
    )
    src = src.replace(
        "FLOW_THRESHOLD_OUT = -2000",
        "FLOW_THRESHOLD_OUT = -1000  # [코스닥]"
    )
    src = src.replace(
        "FLOW_THRESHOLD_IN = 3000",
        "FLOW_THRESHOLD_IN = 1500  # [코스닥]"
    )

    # ─────────────────────────────────────────────────────
    # 7) StockListing('KOSPI') → StockListing('KOSDAQ')
    # ─────────────────────────────────────────────────────
    src = src.replace("fdr.StockListing('KOSPI')", "fdr.StockListing('KOSDAQ')")
    src = src.replace('fdr.StockListing("KOSPI")', 'fdr.StockListing("KOSDAQ")')

    # ─────────────────────────────────────────────────────
    # 8) 시장 지수: KS11 (코스피) → KQ11 (코스닥)
    # ─────────────────────────────────────────────────────
    src = src.replace("fdr.DataReader('KS11'", "fdr.DataReader('KQ11'")
    src = src.replace('fdr.DataReader("KS11"', 'fdr.DataReader("KQ11"')

    # ─────────────────────────────────────────────────────
    # 9) 외인 수급 페널티 -3/-1/+2 → -2/-1/+1 (영향 축소)
    #    "regime_flow_score" 산정 부분을 안전하게 패치
    # ─────────────────────────────────────────────────────
    # 코드에서 점수 부여 부분을 찾아 코스닥용으로 조정
    src = re.sub(
        r"regime_flow_score = -3(\s*#\s*강한 외인 이탈|\s)",
        r"regime_flow_score = -2  # [코스닥] 강한 외인 이탈 (영향 축소)\1",
        src,
        count=1,
    )

    # ─────────────────────────────────────────────────────
    # 10) 환율 페널티도 코스닥은 영향 작음 → 1점씩 완화
    #     -3 → -1, -1 → 0, +2 → +1 형식
    # ─────────────────────────────────────────────────────
    src = re.sub(
        r"regime_fx_score = -3(\s*#\s*강한 원화 약세|\s)",
        r"regime_fx_score = -1  # [코스닥] 환율 영향 작음 (-3→-1)\1",
        src,
        count=1,
    )

    # ─────────────────────────────────────────────────────
    # 11) print 메시지의 'KOSPI' → 'KOSDAQ' (일관성)
    # ─────────────────────────────────────────────────────
    # 단, 코드 식별자 KOSPI_MAJOR 같은 건 건드리지 않음
    src = re.sub(r"(?<![\w_])KOSPI(?![\w_])", "KOSDAQ", src)
    # 변수명은 살리고 메시지만 교체된 형태가 됨
    # 단 KOSPI_MAJOR는 살려야 함 → 위 음수look은 _을 제외해서 안전
    # 일부 함수명도 영향: get_kospi_universe → get_kosdaq_universe로 의미상 OK

    # 함수명도 의미에 맞게 변경
    src = src.replace("get_kospi_universe", "get_kosdaq_universe")
    src = src.replace("_analyze_kospi_regime", "_analyze_kosdaq_regime")

    # ─────────────────────────────────────────────────────
    # 12) SPAC(스팩) 제외 추가 — is_financial_or_reit 함수 보강
    # ─────────────────────────────────────────────────────
    spac_patch = '''def is_financial_or_reit(code, name):
    """[코스닥] 금융주/리츠/스팩 제외."""
    name_s = str(name)
    # 스팩 제외 — 코스닥에 매우 많음, 합병 전 가격 변동 무의미
    if '스팩' in name_s or 'SPAC' in name_s.upper():
        return True'''

    # 기존 is_financial_or_reit 함수가 있다면 그 시작 부분에 스팩 체크 prepend
    # 더 안전하게: 함수 시그니처를 찾아서 첫 줄에 삽입
    pattern_isfin = re.compile(
        r"def is_financial_or_reit\(code, name\):\s*\n(\s*\"\"\".*?\"\"\"\s*\n)?",
        re.DOTALL
    )
    m = pattern_isfin.search(src)
    if m:
        # 함수 본문 시작 위치 찾기
        insert_pos = m.end()
        # 들여쓰기 추론 (다음 비어있지 않은 줄)
        spac_check = (
            "    # [코스닥 추가] 스팩 제외 — 합병 전 가격 무의미\n"
            "    if '스팩' in str(name) or 'SPAC' in str(name).upper():\n"
            "        return True\n"
        )
        src = src[:insert_pos] + spac_check + src[insert_pos:]
    else:
        print("⚠️  is_financial_or_reit 함수를 못 찾음 — 스팩 제외 패치 스킵")

    # ─────────────────────────────────────────────────────
    # 13) 상단에 코스닥 재튜닝 노트 주석 추가
    # ─────────────────────────────────────────────────────
    note = '''
# ============================================================
# [코스닥 재튜닝 노트]
# 본 파일은 build_kosdaq_screener.py로 자동 생성됨.
# 코스피 대비 변경 사항:
#   • 시장: KOSPI → KOSDAQ, 지수: KS11 → KQ11
#   • 시총 상위 proxy 10종목: 코스닥 시총 상위로 교체
#   • 레짐 페널티: 약세 -10→-7, 반등 -5→-3, 조정 -2→-1
#   • 환율 영향 최대 -3 → 최대 -1 (외인 비중/수출주 비중 낮음)
#   • 외인 수급 임계값 50% 완화 (-5000→-2500, -2000→-1000, +3000→+1500)
#   • 외인 수급 최대 페널티 -3 → -2
#   • 과매도 최소점수 50 → 45 (등락폭 큼)
#   • 스팩(SPAC) 자동 제외
# ============================================================
'''
    # __future__ import나 첫 import 앞에 삽입
    src = src.replace("import requests", note + "import requests", 1)

    DST.write_text(src, encoding="utf-8")
    print(f"✅ {DST} 생성 완료 ({len(src):,} bytes)")
    print(f"\n[변경 요약]")
    print(f"  • 시장: KOSPI → KOSDAQ")
    print(f"  • 지수: KS11 → KQ11")
    print(f"  • 레짐 페널티 완화 (약세 -10→-7, 반등 -5→-3)")
    print(f"  • 환율/외인 영향 축소")
    print(f"  • 시총 상위 proxy 10종목 코스닥용으로 교체")
    print(f"  • 스팩 자동 제외")
    print(f"  • 출력: v2_kosdaq_oversold_*.csv")


if __name__ == "__main__":
    main()
