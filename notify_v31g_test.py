#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notify_v31g_test.py — 챌린저 v31g(거래량팽창) '테스트·관측' 텔레그램 알림
==============================================================================
챔피언용 notify_telegram.py 와 같은 방식(env 토큰, sendMessage)으로,
**별도의 '[테스트·관측]' 메시지**를 보낸다. 챔피언 알림(v30)은 일절 안 건드린다.

키(.env):
    TELEGRAM_BOT_TOKEN=...            (notify_telegram 과 동일 토큰 재사용)
    TELEGRAM_TEST_CHAT_ID=...         (선택: 테스트 전용 채널/토픽. 없으면 ↓)
    TELEGRAM_CHAT_ID=...              (위가 없으면 기존 'screener' 그룹으로 — 단, 테스트 라벨 명시)

⚠️ 규율:
  - v31g 는 **검증 전 섀도우**. 메시지 전체가 '테스트·관측·매수신호 아님'으로 도배돼 있다.
  - v31g 신호(거래량팽창)=사후(낚시) 발견 → 지금 점수는 **가설**. 판정은 compare_models --since 20260622.
  - 점수는 history.db 최신 run 을 v31g 스펙으로 재점수(shadow_run 과 동일 결과)해 계산. 네트워크 불필요.

사용:
    python notify_v31g_test.py            # 미리보기 후 전송(토큰 있으면)
    python notify_v31g_test.py --dry-run  # 전송 없이 메시지 출력만
"""
import argparse
import html
import os
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
import v3_rescore as v3

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "history.db"
V31G_FILTER_URL = "https://sj951027.github.io/dh-q7m3k/filter_v31g.html"
REGISTER_RUN = "20260622"
TOP_N = 3
MARKETS = [("kospi", "🔵", "KOSPI"), ("kosdaq", "🟠", "KOSDAQ")]
_BR = {"BUY": 0, "WAIT": 1, "OBSERVE": 2, "WATCH": 3, "EXCLUDE": 4}


def _rescore_run(db_path, rid=None):
    """최신 run 을 v30·v31g 두 스펙으로 재점수해 시장별로 모은다."""
    allruns = v3.load_runs(str(db_path))
    allruns["run_id"] = allruns["run_id"].astype(str)
    rid = str(rid) if rid else allruns["run_id"].max()
    out = {}
    for mkt, _, _ in MARKETS:
        sub = allruns[(allruns["run_id"] == rid) & (allruns["market"] == mkt)]
        if sub.empty:
            out[mkt] = None
            continue
        g = v3.rescore(sub, run_id=rid, market=mkt, spec=v3.MODELS["v31g"])[
            ["ticker", "name", "final_score_v3", "grade", "bucket"]].copy()
        a = v3.rescore(sub, run_id=rid, market=mkt, spec=v3.MODELS["v30"])[
            ["ticker", "bucket"]].rename(columns={"bucket": "v30_bucket"})
        out[mkt] = g.merge(a, on="ticker", how="left")
    return rid, out


def _picks(df, per_bucket=TOP_N):
    """{bucket: [(name, score, grade), ...]} — BUY, WAIT 각각 점수순 상위."""
    res = {}
    for bk in ["BUY", "WAIT"]:
        part = df[df["bucket"] == bk].sort_values("final_score_v3", ascending=False).head(per_bucket)
        if len(part):
            res[bk] = [(str(r["name"]), float(r["final_score_v3"]), str(r.get("grade", "")))
                       for _, r in part.iterrows()]
    return res


BUCKET_LABEL = {"BUY": "🅰️ BUY · 매수후보(관측)", "WAIT": "🅱️ WAIT · 대기(관측)"}


def build_message(db_path=DB_PATH, rid=None):
    today = datetime.now().strftime("%Y-%m-%d")
    rid, data = _rescore_run(db_path, rid)
    lines = [
        f"🧪 <b>[테스트·관측] v31g 챌린저</b> · {today}",
        f"   <i>run {rid}</i>",
        "",
        "⚠️ <b>검증 전 섀도우 — 매수신호 아님.</b> 실제 기준은 챔피언 <b>v30</b>.",
        "   v31g 신호(거래량팽창)=사후(낚시) 발견 → 지금 점수는 <b>가설</b>.",
        "   판정: OOS 40거래일·h=20d 후 <code>compare_models --since 20260622</code>.",
        "",
    ]
    nflip_total = 0
    for mkt, emoji, label in MARKETS:
        df = data.get(mkt)
        lines.append(f"{emoji} <b>{label}</b> <i>(v31g 점수 기준)</i>")
        if df is None or df.empty:
            lines += ["  데이터 없음", ""]
            continue
        nflip_total += int((df["bucket"] != df["v30_bucket"]).sum())
        groups = _picks(df)
        if not groups:
            lines.append("  BUY/WAIT 없음 (관측)")
        else:
            for bk in ["BUY", "WAIT"]:
                rows = groups.get(bk)
                if not rows:
                    continue
                lines.append(BUCKET_LABEL[bk])
                for i, (name, sc, _g) in enumerate(rows, 1):
                    lines.append(f" {i}. {html.escape(str(name), quote=False)} ({sc:.1f})")
        lines.append("")
    lines += [
        f"↹ v30과 버킷이 갈린 종목: <b>{nflip_total}개</b> (오늘 기준)",
        "",
        "※ <b>테스트 관측</b> · BUY/WAIT만 · 챔피언 텔레그램(v30)과 <b>별개</b> · 참고용",
        f'🔍 <a href="{V31G_FILTER_URL}">v31g 필터 페이지(테스트)</a>',
    ]
    return "\n".join(lines)


def send(message=None, db_path=DB_PATH):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    # 테스트 전용 채널 우선 → 없으면 기존 그룹(메시지 자체가 '테스트'라 라벨됨)
    chat_id = (os.environ.get("TELEGRAM_TEST_CHAT_ID", "").strip()
               or os.environ.get("TELEGRAM_CHAT_ID", "").strip())
    if not token or not chat_id:
        print("   ⏭  텔레그램 토큰/챗ID가 없어 건너뜁니다 "
              "(.env: TELEGRAM_BOT_TOKEN + TELEGRAM_TEST_CHAT_ID 또는 TELEGRAM_CHAT_ID).")
        return False
    msg = message or build_message(db_path)
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": "true"},
            timeout=15)
        if r.status_code == 200 and r.json().get("ok"):
            tgt = "테스트 채널" if os.environ.get("TELEGRAM_TEST_CHAT_ID", "").strip() else "기존 그룹(테스트 라벨)"
            print(f"   ✅ v31g 테스트 알림 전송 완료 → {tgt}")
            return True
        print(f"   ⚠️  전송 실패: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        print(f"   ⚠️  전송 오류: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="v31g 테스트·관측 텔레그램 알림")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--dry-run", action="store_true", help="전송 없이 메시지만 출력")
    args = ap.parse_args()
    print(f"\n{'━'*64}\n▶  v31g 테스트·관측 텔레그램 알림\n{'━'*64}")
    msg = build_message(Path(args.db), args.run_id)
    print("   메시지 미리보기:\n")
    print("   " + re.sub(r"<[^>]+>", "", msg).replace("\n", "\n   "))
    print()
    if args.dry_run:
        print("   (--dry-run: 전송 생략)")
        return
    send(msg, Path(args.db))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
