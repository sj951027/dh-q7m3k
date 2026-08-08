# -*- coding: utf-8 -*-
"""
notify_verdict_ready.py — 판정일 도달 알림 (§11 판정 시즌 안전장치)
==============================================================================
왜: 모델별 OOS 40거래일 도달(8/13~ 순차)은 눈에 안 띄게 지나가기 쉽다. 이 스크립트는
매일 history.db 에서 모델별 OOS 거래일 수를 직접 세어, **40거래일에 처음 도달한 모델**이
생기면 텔레그램으로 한 번만 알린다("판정 가능 — leaderboard 실행하라").

원칙:
  * 자립형: leaderboard.json 신선도에 의존하지 않고 history.db 를 직접 계산
    (OOS = 등록일 이후 run 수, 게이트 run 제외 — leaderboard 와 동일 정의).
  * 1회성: 알린 모델은 verdict_notified.json(로컬 상태, git 제외)에 기록 — 중복 알림 없음.
  * 판정 자체는 안 함(그건 leaderboard.py §11 몫). 점수·표시 불변, 비치명.

사용:
    python notify_verdict_ready.py            # 도달 모델 있으면 전송
    python notify_verdict_ready.py --dry-run  # 전송 없이 현황 출력
파이프라인: run_and_diversify 2.9단계(비치명)가 매일 호출.
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "history.db"
STATE = HERE / "verdict_notified.json"
MIN_OOS = 40
GATES = {"20260608", "20260703"}          # leaderboard 게이트와 동일(부분·이중 실행)

# 등록일 원장(checkup.REG_DATE + wu). models_registry.json(P1-2) 생기면 그걸 읽도록 교체.
REG_DATE = {
    "v30": "20260606", "v31a": "20260606", "v31b": "20260606",
    "v31c": "20260606", "v31d": "20260606",
    "v31f": "20260622", "v31g": "20260622",
    "lv_a": "20260625", "lv_b": "20260625", "lv_c": "20260625",
    "lv_d": "20260625", "lv_a3": "20260625",
    "mom_a": "20260627", "lv_short": "20260627", "hv_a": "20260627", "sm_a": "20260627",
    "wu_a": "20260702", "wu_b": "20260702",
    # [2026-08-07 보수] 7/2 이후 등록분 누락 복구 + px_a 신규. ls_t1(large)은 판정
    # 호라이즌이 h60~120(§9)이라 40거래일 알림 대상 아님 — 의도적 제외.
    "sv_a": "20260715", "le_a": "20260715",
    "mom_b": "20260717", "qs_a": "20260723",
    "px_a": "20260810",
}
TABLE = {"v3": "v3_scores", "lowvol": "lowvol_scores", "wu": "wu_scores"}
TRACK = {m: ("v3" if m.startswith("v3") else "wu" if m.startswith("wu") else "lowvol")
         for m in REG_DATE}
# [2026-08-07 보수] 휴리스틱('wu' 접두어)이 못 잡는 wu 트랙 모델 명시 매핑 —
# sv_a·le_a·qs_a 는 wu_scores 소속인데 기존 코드는 lowvol_scores 를 조회(알림 불능 결함).
TRACK.update({"sv_a": "wu", "le_a": "wu", "qs_a": "wu", "px_a": "wu"})


def load_env():
    p = HERE / ".env"
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip():
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def oos_days(con, model):
    tbl = TABLE[TRACK[model]]
    runs = [r for (r,) in con.execute(
        f"SELECT DISTINCT run_id FROM {tbl} WHERE model_id=? AND run_id>?",
        (model, REG_DATE[model]))]
    return len([r for r in runs if str(r) not in GATES])


def send_telegram(msg):
    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("   ⏭ 텔레그램 키 없음 — 콘솔 출력만.")
        return False
    import requests
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
                      timeout=15)
    return r.ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not DB_PATH.exists():
        print("history.db 없음 — 생략(비치명).")
        return
    notified = set()
    if STATE.exists():
        try:
            notified = set(json.loads(STATE.read_text(encoding="utf-8")))
        except Exception:
            pass
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    status, newly = [], []
    for m in REG_DATE:
        try:
            d = oos_days(con, m)
        except Exception:
            continue
        status.append((m, d))
        if d >= MIN_OOS and m not in notified:
            newly.append((m, d))
    con.close()
    status.sort(key=lambda x: -x[1])
    print("OOS 현황: " + " · ".join(f"{m}={d}" for m, d in status[:8]) + " …")
    if not newly:
        print(f"판정 도달({MIN_OOS}일↑) 신규 모델 없음.")
        return
    lines = ["🔔 <b>판정 가능 도달</b> — OOS 40거래일 충족",
             ""] + [f" · {m}: {d}거래일 (등록 {REG_DATE[m]})" for m, d in newly] + [
        "", "판정 실행: <code>python leaderboard.py</code>",
        "⚠️ §11 그대로: CI·Bonferroni·방향일치 — '채택 안 함'도 정당한 결론."]
    msg = "\n".join(lines)
    print(msg)
    if args.dry_run:
        print("[dry-run] 전송·상태기록 생략.")
        return
    send_telegram(msg)
    notified |= {m for m, _ in newly}
    STATE.write_text(json.dumps(sorted(notified), ensure_ascii=False), encoding="utf-8")
    print(f"상태 기록: {STATE.name} ({len(notified)}개 모델 알림 완료)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 실패(비치명 — 파이프라인 계속): {e}")
        sys.exit(0)
