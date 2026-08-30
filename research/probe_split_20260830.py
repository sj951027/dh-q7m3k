# -*- coding: utf-8 -*-
"""주식분할 공시가 DART 어느 유형으로 나오는지 진단 (2026-08-30, 1회용)
① 로컬 dart_events.py 의 패턴이 최신인지 출력
② 최근 3개월 '주요사항보고(B)' 전체에서 '분할/병합' 포함 보고서명 집계
③ ×4 주식수 급증 종목 032960 의 급증일(20260703) 전후 전체 공시 나열(유형 무관)
사용: python research/probe_split_20260830.py
"""
import datetime as dt, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dart_events as de
from catalyst_insider import load_env

print("[로컬 패턴]", [p for p, _ in de.EVENT_PATTERNS])
load_env()
key = os.environ["DART_API_KEY"].strip()

def pages(params):
    page = 1
    while True:
        js = de.fetch_json({**params, "crtfc_key": key, "page_no": page, "page_count": 100})
        if js.get("status") == "013": return
        if js.get("status") != "000": raise SystemExit(f"status {js.get('status')}: {js.get('message')}")
        yield from js.get("list", [])
        if page >= int(js.get("total_page") or 1): return
        page += 1; time.sleep(0.25)

print("\n[② 최근 3개월 주요사항보고(B) 중 '분할|병합' 포함 보고서명]")
from collections import Counter
cnt = Counter(); tot = 0
for cls in ("Y", "K"):
    for row in pages({"bgn_de": "20260601", "end_de": "20260830", "corp_cls": cls, "pblntf_ty": "B"}):
        tot += 1
        nm = row.get("report_nm") or ""
        if ("분할" in nm) or ("병합" in nm):
            cnt[nm] += 1
print(f"  B 전체 {tot}건 중:")
for nm, c in cnt.most_common():
    print(f"  {c:4d}  {nm}")
if not cnt: print("  (분할/병합 포함 보고서명 0건)")

print("\n[③ 032960 — 20260620~20260710 전체 공시(유형 무관)]")
for row in pages({"bgn_de": "20260620", "end_de": "20260710", "corp_cls": "K"}):
    if (row.get("stock_code") or "").strip() == "032960":
        print(f"  {row.get('rcept_dt')}  {row.get('report_nm')}")
print("끝")
