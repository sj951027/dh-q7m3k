# -*- coding: utf-8 -*-
"""
shadow_run.py — 챌린저(v31a~) 섀도우 누적 (조용한 백그라운드)
=============================================================
챔피언 v30 은 v3_daily.py 가 v3_archive/ 에 이미 쌓는다.
이 스크립트는 v3_daily.py '직후'에 호출되어, 등록된 *챌린저* 모델을
그날 같은 스냅샷(stage3_final + valuation)으로 재점수화해
모델별 보관 폴더에 얼려 둔다:

    v31a_archive/v31a_{market}_{run_id}.csv
    v31b_archive/...

특징:
  * 추가 네트워크 0 — v3_daily 가 받아둔 valuation 을 재사용(수 초).
  * 챔피언/대시보드/텔레그램은 전혀 안 건드림 (검증 전 노출 금지).
  * 스펙은 v3_rescore.MODELS 에서 가져옴. 시작하면 스펙을 바꾸지 말 것
    (과거를 새 가중치로 덮으면 룩어헤드). 바꾸려면 새 모델 id 로.

실행:  python shadow_run.py                  # 최신 run_id, v30 제외 전 챌린저
       python shadow_run.py --run_id 20260605 --models v31a v31c
연결:  run_and_diversify.py 의 v3_daily 직후에 한 줄(launcher 에 이미 추가됨).
"""
import argparse
import os
import sqlite3
from pathlib import Path

import v3_rescore as v3

HERE = Path(__file__).resolve().parent
DB = HERE / "history.db"


def latest_run_id():
    con = sqlite3.connect(DB)
    try:
        rid = con.execute("SELECT MAX(run_id) FROM stage3_final").fetchone()[0]
    finally:
        con.close()
    return str(rid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_id", default=None, help="기본: 최신 run")
    ap.add_argument("--models", nargs="*", default=None,
                    help="기본: v30 제외 전 챌린저")
    args = ap.parse_args()

    if not DB.exists():
        print("[shadow] history.db 없음 — 스크리너를 먼저 실행하세요.")
        return 1

    run_id = args.run_id or latest_run_id()
    # [2026-08-09] §11 판정 기각 모델(v3_rescore.RETIRED)은 섀도우 중지 — --models 명시 시만 수동 가능.
    models = args.models or [m for m in v3.MODELS
                             if m != "v30" and m not in getattr(v3, "RETIRED", set())]
    allruns = v3.load_runs(str(DB))

    print(f"[shadow] run_id={run_id} · 챌린저={models}")
    for mid in models:
        spec = v3.MODELS[mid]
        archive = HERE / f"{mid}_archive"
        archive.mkdir(exist_ok=True)
        for mkt in ["kospi", "kosdaq"]:
            sub = allruns[(allruns["run_id"].astype(str) == run_id)
                          & (allruns["market"] == mkt)]
            if sub.empty:
                continue
            rs = v3.rescore(sub, run_id=run_id, market=mkt, spec=spec)
            rs.to_csv(archive / f"{mid}_{mkt}_{run_id}.csv",
                      index=False, encoding="utf-8-sig")
            vc = rs["bucket"].value_counts().to_dict()
            print(f"   [{mid}] {mkt} {run_id} 저장  버킷={vc}")
    print("[shadow] 완료. 비교는  python compare_models.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
