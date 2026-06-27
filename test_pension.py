# -*- coding: utf-8 -*-
"""
test_pension.py — 연기금 수급 API 1회 테스트 (조회 전용)
==============================================================================
목적: KIS '종목별 투자자매매동향(일별)' API(FHPTJ04160001)가
  ① 한 번 호출에 며칠치를 주는지
  ② 날짜 컬럼이 있는지
  ③ 연기금(fund_ntby_qty='기금') 값이 실제로 들어오는지
를 확인한다. kis_flows.py 의 토큰·호출 방식을 그대로 재사용.

사용: kis_flows.py 와 같은 폴더(.env, kis_token.json 있는 곳)에서
    python test_pension.py
    python test_pension.py --ticker 005930 --date 20260626
"""
import argparse
import json
import os
import sys
from datetime import datetime

# kis_flows.py 의 함수/상수 재사용 (같은 폴더에 있어야 함)
from kis_flows import get_token, load_env, BASE

TR_PENSION = "FHPTJ04160001"   # 종목별 투자자매매동향(일별)


def fetch_pension(ticker, date, token, app_key, app_secret):
    """연기금 포함 기관 세부 수급. output1/output2 둘 다 받아 본다."""
    import requests
    r = requests.get(
        f"{BASE}/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily",
        headers={"content-type": "application/json",
                 "authorization": f"Bearer {token}",
                 "appkey": app_key, "appsecret": app_secret,
                 "tr_id": TR_PENSION, "custtype": "P"},
        params={"FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": date,
                "FID_ORG_ADJ_PRC": "",
                "FID_ETC_CLS_CODE": ""},
        timeout=10)
    j = r.json()
    return j


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="005930", help="종목코드 6자리 (기본 삼성전자)")
    ap.add_argument("--date", default="20260626", help="기준 날짜 YYYYMMDD (거래일로)")
    args = ap.parse_args()

    load_env()
    app_key = os.environ.get("KIS_APP_KEY", "").strip()
    app_secret = os.environ.get("KIS_APP_SECRET", "").strip()
    if not (app_key and app_secret):
        raise SystemExit("❌ .env 의 KIS_APP_KEY / KIS_APP_SECRET 확인")

    print("=" * 64)
    print(f"🔍 연기금 수급 테스트 — {args.ticker}, 기준일 {args.date}")
    print("=" * 64)

    token = get_token(app_key, app_secret)
    j = fetch_pension(args.ticker, args.date, token, app_key, app_secret)

    # 1) 응답 상태
    print(f"\n[1] rt_cd={j.get('rt_cd')}  msg={j.get('msg1', '')}")
    if j.get("rt_cd") not in (None, "0"):
        print("    ❌ 호출 실패 — 위 메시지 확인 (날짜를 거래일로, 또는 tr_id 점검)")
        print(f"    전체 응답(앞부분): {str(j)[:300]}")
        return

    # 2) output1 / output2 구조
    for name in ("output1", "output2"):
        out = j.get(name)
        if not out:
            print(f"\n[{name}] 비어있음")
            continue
        rows = out if isinstance(out, list) else [out]
        print(f"\n[{name}] {len(rows)}행")
        # 첫 행의 키 목록 (어떤 필드가 오는지)
        keys = sorted(rows[0].keys())
        print(f"    필드({len(keys)}개): {keys}")
        # 날짜 컬럼 후보
        date_keys = [k for k in keys if 'date' in k.lower() or 'bsop' in k.lower()]
        print(f"    날짜컬럼 후보: {date_keys}")
        # 연기금 관련 필드 확인
        fund_keys = [k for k in keys if 'fund' in k.lower() or k.startswith('orgn')
                     or 'ivtr' in k.lower() or 'scrt' in k.lower()]
        print(f"    기관세부 필드: {fund_keys}")
        # 처음 3행에서 핵심값 출력 (날짜·기관계·연기금·외국인)
        print(f"    --- 처음 3행 핵심값 ---")
        for row in rows[:3]:
            d = row.get('stck_bsop_date', '?')
            org = row.get('orgn_ntby_qty', '?')
            fund = row.get('fund_ntby_qty', '?')
            frgn = row.get('frgn_ntby_qty', '?')
            print(f"      날짜={d}  기관계={org}  기금(연기금)={fund}  외국인={frgn}")

    print("\n" + "=" * 64)
    print("✅ 위 결과를 Claude 에게: ① 몇 행 나오나(며칠치) ② 날짜컬럼 ③ 기금값 들어오나")
    print("=" * 64)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
