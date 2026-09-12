# -*- coding: utf-8 -*-
"""dart_backfill.py — DART 연결오류로 비어버린 재무 데이터를 '나중에' 채운다 (캐시 워밍 전용)

배경 (2026-09-12 실측):
  배치 중 stage3 의 DART 호출이 RemoteDisconnected 로 무더기 실패하고, 바로 뒤의 2차 시도(순차 0.3s)도
  전부 실패한다. 그런데 몇 시간 뒤 같은 키·같은 엔드포인트로 순차 호출하면 100% 정상(status 000)이다.
  → DART 쪽이 배치의 대량 호출 직후 얼마간 막고, 시간이 지나면 풀리는 패턴으로 보인다.
  실측 추이(stage3_final.ocf_pattern='데이터없음'): 09-07 5 · 09-08 4 · 09-09 47 · 09-11 98(541 중).

무엇을 하나:
  최근 run 에서 재무가 빈 종목만 골라 stage3 의 fetch 함수를 그대로(순차·간격) 다시 호출한다.
  성공하면 stage3 와 같은 캐시(dart_cache/fin, 정상응답 TTL 14일)에 들어가므로 **다음 실행이 캐시로 읽는다**.

무엇을 하지 않나 (중요):
  - 이미 동결된 점수·stage3_final 행을 고치지 않는다. 소급 수정 없음(§11 동결 원칙).
  - 점수식·게이트·판정 로직을 건드리지 않는다. 이 스크립트는 캐시만 데운다.
  - history.db 에 쓰지 않는다(읽기 전용으로만 연다).

실행:
  python dart_backfill.py                 # 최신 run 의 결손 종목
  python dart_backfill.py --run-id 20260911
  python dart_backfill.py --sleep 0.5 --limit 50
배치에서는 맨 끝(대형 push·텔레그램 뒤)에 두는 것을 권장 — stage3 로부터 1시간 이상 떨어뜨리려는 것.
"""
import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "history.db"
GAP_PATTERNS = ("데이터없음", "데이터부족")


def load_gaps(run_id=None, limit=None):
    """(run_id, [(ticker, name, corp_code), ...]) — 재무가 빈 종목."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rid = run_id or con.execute("SELECT MAX(run_id) FROM stage3_final").fetchone()[0]
    q = ("SELECT ticker, name, corp_code, ocf_pattern, dart_ocf_status FROM stage3_final "
         "WHERE run_id=? AND (ocf_pattern IN (%s) OR ocf_latest_억 IS NULL)"
         % ",".join("?" * len(GAP_PATTERNS)))
    rows = con.execute(q, (rid,) + GAP_PATTERNS).fetchall()
    con.close()
    out = []
    seen = set()
    for tk, nm, cc, pat, st in rows:
        cc = str(cc or "").replace(".0", "").zfill(8)
        if not cc or cc == "00000000" or cc in seen:
            continue
        seen.add(cc)
        out.append((str(tk).zfill(6), nm or tk, cc))
    return rid, (out[:limit] if limit else out)


def main():
    ap = argparse.ArgumentParser(description="DART 재무 결손 종목 캐시 백필(점수·DB 무변경)")
    ap.add_argument("--run-id", default=None, help="기본: stage3_final 최신 run")
    ap.add_argument("--sleep", type=float, default=0.4, help="호출 간격 초(기본 0.4)")
    ap.add_argument("--limit", type=int, default=None, help="상위 N종목만")
    ap.add_argument("--dry-run", action="store_true", help="대상만 세고 호출은 안 함")
    args = ap.parse_args()

    rid, gaps = load_gaps(args.run_id, args.limit)
    print("=" * 64)
    print(f"🩹 DART 재무 백필 — run {rid} · 결손 {len(gaps)}종목 · 간격 {args.sleep}s")
    print("   (캐시만 데운다 — 동결 점수·stage3_final 행은 그대로)")
    print("=" * 64)
    if not gaps:
        print("   채울 것이 없습니다. 정상."); return 0
    if args.dry_run:
        for tk, nm, cc in gaps[:20]:
            print(f"   {nm}({tk}) corp={cc}")
        print(f"   … 총 {len(gaps)}종목 (드라이런 — 호출 안 함)")
        return 0

    sys.path.insert(0, str(HERE))
    import stage3_fundamental_momentum_v2_6 as S3
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        try:
            from catalyst_insider import load_env
            load_env()
            key = os.environ.get("DART_API_KEY", "").strip()
        except Exception:
            pass
    if not key:
        print("   ❌ DART_API_KEY 없음(.env 확인) — 중단"); return 1

    ok = miss = fail = 0
    t0 = time.time()
    for i, (tk, nm, cc) in enumerate(gaps, 1):
        time.sleep(args.sleep)
        try:
            annual = S3.get_annual_metrics(cc, key)
            time.sleep(args.sleep)
            S3.get_quarterly_yoy(cc, key)
            st = str((annual or {}).get("dart_annual_status", "") or "")
            if (annual or {}).get("ocf_latest_억") is not None:
                ok += 1            # 재무 확보 — 다음 실행이 캐시로 읽는다
            elif "REQUEST_ERROR" in st:
                fail += 1          # 아직 DART 가 막혀 있음
            else:
                miss += 1          # 응답은 정상이나 해당 보고서 없음(신규상장·결산월 등) — 정상 케이스
        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f"   ⚠️  {nm}({tk}) 실패: {str(e)[:70]}")
        if i % 20 == 0 or i == len(gaps):
            print(f"   [{i}/{len(gaps)}] 복구 {ok} · 자료없음(정상) {miss} · 연결실패 {fail} "
                  f"· {time.time() - t0:.0f}s")

    print(f"\n💾 완료 — 복구 {ok} / 자료없음 {miss} / 연결실패 {fail} (총 {len(gaps)}종목, "
          f"{time.time() - t0:.0f}s)")
    print("   다음 배치의 stage3 가 이 캐시를 읽는다(정상응답 TTL 14일). 오늘 동결분은 그대로 둔다.")
    if fail and fail >= len(gaps) // 2:
        print("   ⚠️  절반 이상 연결 실패 — DART 차단이 아직 안 풀렸을 수 있다. 나중에 한 번 더 실행.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
