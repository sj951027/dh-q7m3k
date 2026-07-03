#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notify_wu_test.py — 전체종목 트랙 wu_a '테스트·관측' 텔레그램 알림 (수동 미리보기용)
==============================================================================
notify_lowvol_test.py 와 같은 방식. 평소 알림은 v3 메시지 푸터의 wu.html 링크로 대체(lowvol 4b 와
동일 결정) — 이 스크립트는 **수동 미리보기/원할 때 전송**용이다. 챔피언(v30)·large·lowvol 알림은
일절 안 건드린다.

키(.env): TELEGRAM_BOT_TOKEN (+ TELEGRAM_TEST_CHAT_ID 또는 TELEGRAM_CHAT_ID)

⚠️ 규율(PREREGISTER_wu.md):
  - wu_a 는 검증 전 섀도우(발견 2024-07~2026-07 in-sample, **대형 독주 국면**). 메시지 전체가
    '테스트·관측·매수신호 아님' 라벨. 판정은 등록일 이후 OOS 40거래일.
  - history.db 만 읽는다(wu_scores + 종목명 stage1). 네트워크는 전송 시 텔레그램 API 뿐.

사용:
    python notify_wu_test.py --dry-run   # 전송 없이 메시지 출력만
    python notify_wu_test.py             # 미리보기 후 전송(토큰 있으면)
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
WU_URL = "https://sj951027.github.io/dh-q7m3k/wu.html"
MODEL = "wu_a"
TOP_N = 5
MKT_EMOJI = {"KOSPI": "🔵", "KOSDAQ": "🟠"}


def build_message(db_path=DB_PATH, rid=None):
    con = sqlite3.connect(str(db_path))
    runs = pd.read_sql("SELECT DISTINCT run_id FROM wu_scores", con)
    if runs.empty:
        con.close()
        return "wu_scores 비어 있음 — 먼저 wu_score.py."
    rid = str(rid) if rid else str(runs["run_id"].astype(str).max())
    top = pd.read_sql(
        "SELECT ticker, market, wu_score, wu_rank FROM wu_scores "
        "WHERE run_id=? AND model_id=? ORDER BY wu_rank LIMIT ?",
        con, params=(rid, MODEL, TOP_N))
    top["ticker"] = top["ticker"].astype(str)
    # 종목명: stage1(전 run, 최신 우선) + large_universe 폴백 — build_wu_filter 와 동일 로직.
    try:
        frames = []
        for q in ("SELECT ticker, name, run_id FROM stage1_oversold",
                  "SELECT ticker, name, run_id FROM large_universe"):
            try:
                frames.append(pd.read_sql(q, con))
            except Exception:
                pass
        nm = pd.concat(frames, ignore_index=True).dropna(subset=["name"])
        nm["ticker"] = nm["ticker"].astype(str)
        nm = nm.sort_values("run_id").drop_duplicates("ticker", keep="last")
        top = top.merge(nm[["ticker", "name"]], on="ticker", how="left")
    except Exception:
        top["name"] = None
    try:
        wb = pd.read_sql("SELECT ticker, wu_rank AS wu_b_rank FROM wu_scores "
                         "WHERE run_id=? AND model_id='wu_b'", con, params=(rid,))
        wb["ticker"] = wb["ticker"].astype(str)
        top = top.merge(wb, on="ticker", how="left")
    except Exception:
        pass
    con.close()

    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"🧪 <b>[테스트·관측] 전체종목 트랙 wu_a</b> · {today}",
        f"   <i>run {rid}</i>",
        "",
        "⚠️ <b>검증 전 섀도우 — 매수신호 아님.</b> 실제 기준은 v3.",
        "   발견(2024-07~2026-07)은 <b>대형 독주 국면 in-sample</b> → 지금 점수는 <b>가설</b>.",
        "   판정: 등록일 이후 <b>OOS 40거래일</b> 누적 후. 점수↑=선호(사라 아님).",
        "",
        f"🏆 <b>wu_a 점수 상위 {TOP_N}</b> <i>(전체 유니버스 단일 순위)</i>",
    ]
    if top.empty:
        lines.append("  데이터 없음")
    else:
        for r in top.itertuples():
            nm_ = html.escape(str(r.name) if pd.notna(r.name) else r.ticker, quote=False)
            em = MKT_EMOJI.get(str(r.market), "▫️")
            wb_ = f"{int(r.wu_b_rank)}" if ("wu_b_rank" in top.columns and pd.notna(r.wu_b_rank)) else "-"
            lines.append(f" {int(r.wu_rank)}. {em} {nm_} (wu {r.wu_score:.2f} · wu_b순위 {wb_})")
    lines += [
        "",
        "※ <b>테스트 관측</b> · 구성=저변동63+52주고점근접+12-1모멘텀+시총(순위합) · v3·large·lowvol 과 <b>별개</b>",
        "   wu_b(고점근접+모멘텀만, 시총 무베팅)는 대조 관측 — 순위 차이가 크면 시총 항이 끌어올린 종목",
        f'🔍 <a href="{WU_URL}">전체종목 트랙 페이지(테스트)</a>',
    ]
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
            print(f"   ✅ wu 테스트 알림 전송 완료 → {tgt}")
            return True
        print(f"   ⚠️  전송 실패: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        print(f"   ⚠️  전송 오류: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="wu_a 테스트 텔레그램 알림")
    ap.add_argument("--dry-run", action="store_true", help="전송 없이 메시지만 출력")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()
    msg = build_message(rid=args.run_id)
    print("─" * 50)
    print(msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
    print("─" * 50)
    if not args.dry_run:
        send(msg)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
