#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notify_lowvol_test.py — 저변동 트랙 lv_a '테스트·관측' 텔레그램 알림
==============================================================================
챔피언용 notify_telegram.py 와 같은 방식(env 토큰, sendMessage)으로, **별도의
'[테스트·관측]' 메시지**를 보낸다. 챔피언(v30)·v31g·large 알림은 일절 안 건드린다.

v31g 와 다른 점: lowvol 은 자체 점수(lowvol_score)라 grade/bucket 이 없다. lowvol_scores
테이블(lv_a)을 최신 run 으로 직접 읽어 점수 상위 N 종목을 보여준다(종목명은 stage3 에서 조인).

키(.env):
    TELEGRAM_BOT_TOKEN=...            (notify_telegram 과 동일 토큰 재사용)
    TELEGRAM_TEST_CHAT_ID=...         (선택: 테스트 전용. 없으면 ↓)
    TELEGRAM_CHAT_ID=...              (위 없으면 기존 그룹 — 단 메시지가 '테스트' 라벨)

⚠️ 규율(LOWVOL_TRACK_DESIGN §5-6):
  - lv_a 는 검증 전 섀도우. 메시지 전체가 '테스트·관측·매수신호 아님'으로 도배.
  - 신호(저변동·반전)=사후(낚시) 발견 → 지금 점수는 가설. 판정은 OOS 40거래일.
  - 점수는 history.db 만 읽어 계산. 네트워크 불필요.

사용:
    python notify_lowvol_test.py            # 미리보기 후 전송(토큰 있으면)
    python notify_lowvol_test.py --dry-run  # 전송 없이 메시지 출력만
"""
import argparse
import html
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "history.db"
LOWVOL_URL = "https://sj951027.github.io/dh-q7m3k/lowvol.html"
MODEL = "lv_a"
TOP_N = 5
MARKETS = [("kospi", "🔵", "KOSPI"), ("kosdaq", "🟠", "KOSDAQ")]


def _top(con, rid, mkt, n=TOP_N):
    ls = pd.read_sql(
        "SELECT ticker, lowvol_score FROM lowvol_scores "
        "WHERE run_id=? AND market=? AND model_id=? "
        "ORDER BY lowvol_score DESC LIMIT ?",
        con, params=(rid, mkt, MODEL, n))
    if ls.empty:
        return None
    s3 = pd.read_sql(
        'SELECT ticker, name, realized_vol, roe_value, "return_1w_%" AS r1w, '
        '"foreign_20d_억" AS f20, "inst_20d_억" AS i20 '
        "FROM stage3_final WHERE run_id=? AND market=?",
        con, params=(rid, mkt))
    return ls.merge(s3, on="ticker", how="left")


def build_message(db_path=DB_PATH, rid=None):
    con = sqlite3.connect(str(db_path))
    runs = pd.read_sql("SELECT DISTINCT run_id FROM lowvol_scores", con)
    if runs.empty:
        con.close()
        return "lowvol_scores 비어 있음 — 먼저 lowvol_score.py --full."
    rid = str(rid) if rid else str(runs["run_id"].astype(str).max())
    today = datetime.now().strftime("%Y-%m-%d")

    lines = [
        f"🧪 <b>[테스트·관측] 저변동 트랙 lv_a</b> · {today}",
        f"   <i>run {rid}</i>",
        "",
        "⚠️ <b>검증 전 섀도우 — 매수신호 아님.</b> 실제 기준은 v3.",
        "   신호(저변동·반전)=사후 발견 → 지금 점수는 <b>가설</b>.",
        "   판정: 등록일 이후 <b>OOS 40거래일</b> 누적 후. 점수↑=선호(사라 아님).",
        "",
    ]
    for mkt, emoji, label in MARKETS:
        df = _top(con, rid, mkt)
        lines.append(f"{emoji} <b>{label}</b> <i>(lv_a 점수 상위 {TOP_N})</i>")
        if df is None or df.empty:
            lines += ["  데이터 없음", ""]
            continue
        for i, r in enumerate(df.itertuples(), 1):
            nm = html.escape(str(r.name), quote=False)
            rv = f"{r.realized_vol:.3f}" if pd.notna(r.realized_vol) else "-"
            roe = f"{r.roe_value:.0f}" if pd.notna(r.roe_value) else "-"
            r1w = f"{r.r1w:+.0f}%" if pd.notna(r.r1w) else "-"
            f20 = f"{r.f20:+.0f}" if pd.notna(r.f20) else "-"
            i20 = f"{r.i20:+.0f}" if pd.notna(r.i20) else "-"
            lines.append(f" {i}. {nm} (lv {r.lowvol_score:.2f} · 변동성 {rv} · ROE {roe} · 1주 {r1w})")
            lines.append(f"     └ 수급20일 외인 {f20} · 기관 {i20} (억)")
        lines.append("")
    lines += [
        "※ <b>테스트 관측</b> · 점수 상위만 · v3·large 텔레그램과 <b>별개</b> · 참고용",
        f'🔍 <a href="{LOWVOL_URL}">저변동 트랙 페이지(테스트)</a>',
    ]
    con.close()
    return "\n".join(lines)


def send(message=None, db_path=DB_PATH):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
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
            print(f"   ✅ lowvol 테스트 알림 전송 완료 → {tgt}")
            return True
        print(f"   ⚠️  전송 실패: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        print(f"   ⚠️  전송 오류: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="lowvol lv_a 테스트 텔레그램 알림")
    ap.add_argument("--dry-run", action="store_true", help="전송 없이 메시지만 출력")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()
    msg = build_message(rid=args.run_id)
    print("─" * 50)
    print(msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
          .replace("<code>", "").replace("</code>", ""))
    print("─" * 50)
    if not args.dry_run:
        send(msg)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
