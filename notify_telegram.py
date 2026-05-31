#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notify_telegram.py — 스크리너 완료 후 텔레그램으로 결과 알림
=============================================================
push가 끝난 뒤, 텔레그램으로 "완료 + 점수 적중도(IC) + TOP3 + 링크"를 보낸다.
PC/폰 어디서든 텔레그램 알림의 링크를 누르면 웹 대시보드로 바로 이동.

키(.env 에 두 줄):
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...

토큰이 없으면 조용히 건너뛴다(에러 아님). 전송 실패해도 전체 작업은 계속.

단독 테스트:  python notify_telegram.py
"""

import json
import os
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 대시보드/필터 주소 (네 GitHub Pages)
DASHBOARD_URL = "https://sj951027.github.io/dh-q7m3k/"
FILTER_URL = "https://sj951027.github.io/dh-q7m3k/filter.html"

TOP_N = 3


def _top_names(csv_path, n=TOP_N):
    """latest_*_final.csv 에서 final_score 상위 n개 (이름, 점수) 반환."""
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        df["final_score"] = pd.to_numeric(df["final_score"], errors="coerce")
        df = df.dropna(subset=["final_score"]).sort_values("final_score", ascending=False)
        return [(str(r["name"]), float(r["final_score"]))
                for _, r in df.head(n).iterrows()]
    except Exception:
        return []


def _ic_line():
    """ic_summary.json 에서 점수 적중도 한 줄."""
    p = HERE / "docs" / "ic_summary.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if d.get("status") != "ok" or not d.get("headline"):
        return "📊 점수 적중도(IC): 데이터 쌓는 중"
    h = d["headline"]
    ic = h.get("ic")
    verdict = (h.get("verdict") or "").split("(")[0].strip()
    if ic is None:
        return "📊 점수 적중도(IC): 데이터 쌓는 중"
    return f"📊 점수 적중도(IC, +{h.get('horizon')}일): {ic:+.3f}  {verdict}"


def build_message():
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"✅ 스크리너 완료 · {today}", ""]

    ic = _ic_line()
    if ic:
        lines += [ic, ""]

    for mkt, emoji, label in [("kospi", "🔵", "KOSPI"), ("kosdaq", "🟠", "KOSDAQ")]:
        csv = HERE / f"latest_{mkt}_final.csv"
        tops = _top_names(csv)
        if tops:
            lines.append(f"{emoji} {label} TOP{len(tops)}")
            for i, (name, sc) in enumerate(tops, 1):
                lines.append(f" {i}. {name} ({sc:.1f})")
            lines.append("")

    lines += [
        f"🔗 대시보드: {DASHBOARD_URL}",
        f"🔍 필터·정렬: {FILTER_URL}",
    ]
    return "\n".join(lines)


def send(message=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("   ⏭  텔레그램 토큰이 없어 알림을 건너뜁니다 "
              "(.env에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 추가 시 작동).")
        return False

    msg = message or build_message()
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": msg,
                  "disable_web_page_preview": "true"},
            timeout=15)
        if r.status_code == 200 and r.json().get("ok"):
            print("   ✅ 텔레그램 알림 전송 완료")
            return True
        print(f"   ⚠️  텔레그램 전송 실패: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        print(f"   ⚠️  텔레그램 전송 오류: {e}")
        return False


def main():
    print(f"\n{'━'*64}\n▶  텔레그램 알림\n{'━'*64}")
    print("   메시지 미리보기:\n")
    print("   " + build_message().replace("\n", "\n   "))
    print()
    send()


if __name__ == "__main__":
    main()
