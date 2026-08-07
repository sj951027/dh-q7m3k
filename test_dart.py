# -*- coding: utf-8 -*-
"""test_dart.py - DART API 상태 진단 (읽기 전용, 약 35회 호출, 수 초 소요)
용도: 8/4부터 stage2/3 축소의 원인 확인 - 상태코드 분포와 응답 지연을 실측.
  000=정상 / 010,011=키 문제(만료 등) / 020=요청 한도 초과 / 800=시스템 점검 / 900=기타
실행: python test_dart.py   (아무 때나, 여러 시간대에 돌려 비교하면 좋음)
"""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from collections import Counter

# .env에서 키 로드 (환경변수 우선)
import os
KEY = os.environ.get("DART_API_KEY", "").strip()
if not KEY:
    env = Path(__file__).parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("DART_API_KEY"):
                KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
if not KEY:
    print("[FAIL] DART_API_KEY 를 찾지 못했습니다(.env 확인)")
    raise SystemExit(1)

def call(url, timeout=10):
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d.get("status", "?"), time.time() - t0
    except urllib.error.HTTPError as e:
        return f"http{e.code}", time.time() - t0
    except Exception as e:
        return type(e).__name__, time.time() - t0

print(f"진단 시작: {time.strftime('%Y-%m-%d %H:%M:%S')}  (키 끝 4자리: ...{KEY[-4:]})")

# 1) 공시목록 API 30회 (stage2가 쓰는 것)
st = Counter(); lat = []
for i in range(1, 31):
    s, t = call(f"https://opendart.fss.or.kr/api/list.json?crtfc_key={KEY}"
                f"&bgn_de=20260801&end_de=20260807&page_no={i}&page_count=10")
    st[s] += 1; lat.append(t)
    time.sleep(0.15)
print(f"[공시목록 30회] 상태 분포: {dict(st)}")
print(f"  지연: 평균 {sum(lat)/len(lat):.2f}s / 최대 {max(lat):.2f}s")

# 2) 재무 API 5회 (stage3가 쓰는 것, 삼성전자 등 대형 5종)
st2 = Counter(); lat2 = []
for corp in ["00126380", "00164779", "00164742", "00401731", "00356370"]:
    s, t = call(f"https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json?crtfc_key={KEY}"
                f"&corp_code={corp}&bsns_year=2025&reprt_code=11011&fs_div=CFS")
    st2[s] += 1; lat2.append(t)
    time.sleep(0.3)
print(f"[재무 5회] 상태 분포: {dict(st2)}")
print(f"  지연: 평균 {sum(lat2)/len(lat2):.2f}s / 최대 {max(lat2):.2f}s")

print()
print("해석: 000만 나오고 지연이 짧으면 지금은 정상(=시간대 부하 문제 가능성).")
print("      020이 섞이면 호출 한도, 010/011이면 키 문제, 800/타임아웃 다수면 서버 불안정.")
