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


def _latest_v3(mkt):
    """v3_archive 에서 가장 최근 v3_{mkt}_*.csv 경로."""
    import glob
    files = sorted(glob.glob(str(HERE / "v3_archive" / f"v3_{mkt}_*.csv")))
    return files[-1] if files else None


def _top_names(mkt, n=TOP_N):
    """후보 상위 n개 (이름, 점수, 등급) 반환. BUY → WAIT 버킷에서만 뽑는다.

    1순위: v3 결과의 BUY(=A+/A) 우선, 모자라면 WAIT(=B+반전)로 채움.
           OBSERVE/WATCH/EXCLUDE 는 절대 후보로 올리지 않음.
    2순위(v3 없으면): latest_*_final.csv + 안전필터(이중적자·밸류트랩·주의·위험 제외).
    """
    import pandas as pd
    # 1) v3 우선 — BUY 먼저, 그다음 WAIT
    vf = _latest_v3(mkt)
    if vf:
        try:
            df = pd.read_csv(vf)
            df["final_score_v3"] = pd.to_numeric(df["final_score_v3"], errors="coerce")
            df = df.dropna(subset=["final_score_v3"])
            if "bucket" in df.columns:
                picks = []
                for bk in ["BUY", "WAIT"]:           # 순서 중요: BUY 먼저
                    part = df[df["bucket"] == bk].sort_values(
                        "final_score_v3", ascending=False)
                    for _, r in part.iterrows():
                        picks.append((str(r["name"]), float(r["final_score_v3"]),
                                      str(r.get("grade", ""))))
                        if len(picks) >= n:
                            break
                    if len(picks) >= n:
                        break
                return picks   # 후보가 없으면 빈 리스트(=오늘 후보 없음)
            # bucket 컬럼이 없는 옛 v3 파일이면 메인후보만
            if "main_candidate" in df.columns:
                df = df[df["main_candidate"] == True]  # noqa: E712
            df = df.sort_values("final_score_v3", ascending=False)
            return [(str(r["name"]), float(r["final_score_v3"]), str(r.get("grade", "")))
                    for _, r in df.head(n).iterrows()]
        except Exception:
            pass
    # 2) 폴백: v2.6 final + 안전 필터
    try:
        df = pd.read_csv(HERE / f"latest_{mkt}_final.csv")
        if "ocf_pattern" in df.columns:
            df = df[~df["ocf_pattern"].isin(["이중적자", "밸류트랩의심"])]
        if "risk_level" in df.columns:
            df = df[~df["risk_level"].isin(["주의", "위험"])]
        df["final_score"] = pd.to_numeric(df["final_score"], errors="coerce")
        df = df.dropna(subset=["final_score"]).sort_values(
            "final_score", ascending=False)
        return [(str(r["name"]), float(r["final_score"]), "")
                for _, r in df.head(n).iterrows()]
    except Exception:
        return []


def _ic_line():
    """교정된 v3_ic_summary.json 에서 검증 IC 한 줄(표본 크기 포함, 정직하게)."""
    p = HERE / "docs" / "v3_ic_summary.json"
    if not p.exists():
        return "📊 검증 IC: 데이터 쌓는 중 (v3_backtest.py 미실행)"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        rows = d.get("new_final_score_v3") or []
        runs = d.get("active_runs") or []
        if not rows:
            return "📊 검증 IC: 데이터 쌓는 중"
        row = sorted(rows, key=lambda r: r.get("horizon", 0))[-1]  # 가장 긴 horizon
        ic, h, ndays = row.get("mean_IC"), row.get("horizon"), len(runs)
        if ic is None:
            return "📊 검증 IC: 데이터 쌓는 중"
        verdict = "양호" if ic > 0.02 else ("중립" if ic > -0.02 else "약함")
        caveat = " · 표본 적음" if ndays < 15 else ""
        return (f"📊 검증 IC(v3, +{h}일): {ic:+.3f} "
                f"({verdict}, {ndays}거래일{caveat})")
    except Exception:
        return "📊 검증 IC: 데이터 쌓는 중"


def build_message():
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"✅ 스크리너 완료 · {today}", ""]

    ic = _ic_line()
    if ic:
        lines += [ic, ""]

    for mkt, emoji, label in [("kospi", "🔵", "KOSPI"), ("kosdaq", "🟠", "KOSDAQ")]:
        tops = _top_names(mkt)
        if tops:
            lines.append(f"{emoji} {label} 후보 TOP{len(tops)}")
            for i, (name, sc, grade) in enumerate(tops, 1):
                gtag = f" [{grade}]" if grade else ""
                lines.append(f" {i}. {name} ({sc:.1f}){gtag}")
        else:
            lines.append(f"{emoji} {label} 후보 없음 (BUY/WAIT 없음)")
        lines.append("")

    lines += [
        "※ BUY/WAIT 등급만, 위험종목 제외한 참고용 후보입니다.",
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
