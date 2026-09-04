# DART RemoteDisconnected 진단 (2026-09-04) — 사용자 실행(네트워크). 읽기 전용, DB 무접촉.
# 배경: 9/1~9/4 KOSDAQ 3단계에서 매일 60~90종목이 fnlttSinglAcntAll 호출에 'Remote end closed connection' 으로
#       실패(3회 재시도 후 not_found 처리) → 3단계 61분 + 해당 종목 펀더멘털 결측. 같은 종목이 반복(000250·019210·028300 등).
# 사용: python research/dart_probe_20260904.py   (약 1~2분)
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from run_and_diversify import load_dotenv; load_dotenv()
import requests
KEY = os.environ.get("DART_API_KEY", ""); URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
CASES = [("000250 삼천당제약", "00128546"), ("028300 HLB", "00199252"), ("019210 와이지-원", "00139719"),
         ("005930 삼성전자(대조, 정상)", "00126380")]
VARIANTS = {
    "기본(requests.get)": dict(headers=None, session=False),
    "Connection: close": dict(headers={"Connection": "close"}, session=False),
    "UA+gzip 없음": dict(headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity", "Connection": "close"}, session=False),
    "Session 재사용": dict(headers=None, session=True),
}
def call(corp, year, fs, v):
    p = {"crtfc_key": KEY, "corp_code": corp, "bsns_year": str(year), "reprt_code": "11011", "fs_div": fs}
    t = time.time()
    try:
        s = requests.Session() if v["session"] else requests
        r = s.get(URL, params=p, headers=v["headers"], timeout=20)
        n = len(r.content); st = r.json().get("status"); return f"ok status={st} bytes={n} {time.time()-t:.1f}s"
    except Exception as e:
        return f"FAIL {type(e).__name__}: {str(e)[:70]} {time.time()-t:.1f}s"
for name, corp in CASES:
    print("=" * 70); print(name, corp)
    for vn, v in VARIANTS.items():
        for year, fs in [(2025, "CFS"), (2025, "OFS"), (2024, "OFS")]:
            print(f"  [{vn:16s}] {year} {fs}: {call(corp, year, fs, v)}"); time.sleep(0.3)
print("\n해석: 정상 대조(삼성전자)만 ok 이고 문제 종목이 변형 불문 FAIL 이면 DART 서버측 종목별 문제,\n      특정 변형(예: Connection: close / gzip 없음)에서만 ok 이면 클라이언트 헤더 수정으로 해결 가능.")
