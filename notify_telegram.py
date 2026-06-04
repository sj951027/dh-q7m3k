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

TOP_N = 3   # 버킷별로 보여줄 상위 후보 수

# 버킷 → 표시 라벨 (정렬키가 '점수'가 아니라 '등급'임을 메시지에서 드러냄)
BUCKET_LABEL = {
    "BUY":  "🅰️ BUY(매수후보)",
    "WAIT": "🅱️ WAIT(대기)",
    "REF":  "▫️ 참고후보",
}


def _latest_v3(mkt):
    """v3_archive 에서 가장 최근 v3_{mkt}_*.csv 경로."""
    import glob
    files = sorted(glob.glob(str(HERE / "v3_archive" / f"v3_{mkt}_*.csv")))
    return files[-1] if files else None


def _picks_by_bucket(mkt, per_bucket=TOP_N):
    """버킷별 후보를 {bucket: [(이름, 점수, 등급), ...]} 로 반환.

    BUY / WAIT 버킷을 '각각' final_score_v3 내림차순으로 per_bucket개까지 담는다.
    (버킷 간 점수를 섞지 않으므로 '점수는 높은데 순위는 낮은' 오해가 사라진다.)
    OBSERVE/WATCH/EXCLUDE 는 절대 후보로 올리지 않음.

    v3 결과가 없거나 bucket 컬럼이 없으면 폴백을 'REF'(참고) 그룹 하나로 반환.
      폴백: latest_*_final.csv + 안전필터(이중적자·밸류트랩·주의·위험 제외).
    """
    import pandas as pd
    # 1) v3 우선 — 버킷별로 분리
    vf = _latest_v3(mkt)
    if vf:
        try:
            df = pd.read_csv(vf)
            df["final_score_v3"] = pd.to_numeric(df["final_score_v3"], errors="coerce")
            df = df.dropna(subset=["final_score_v3"])
            if "bucket" in df.columns:
                out = {}
                for bk in ["BUY", "WAIT"]:           # 표시 순서: BUY 먼저
                    part = df[df["bucket"] == bk].sort_values(
                        "final_score_v3", ascending=False).head(per_bucket)
                    rows = [(str(r["name"]), float(r["final_score_v3"]),
                             str(r.get("grade", ""))) for _, r in part.iterrows()]
                    if rows:
                        out[bk] = rows
                return out   # 둘 다 비면 {} (=오늘 후보 없음)
            # bucket 컬럼이 없는 옛 v3 파일이면 메인후보만 참고그룹으로
            if "main_candidate" in df.columns:
                df = df[df["main_candidate"] == True]  # noqa: E712
            df = df.sort_values("final_score_v3", ascending=False).head(per_bucket)
            rows = [(str(r["name"]), float(r["final_score_v3"]), str(r.get("grade", "")))
                    for _, r in df.iterrows()]
            return {"REF": rows} if rows else {}
        except Exception:
            pass
    # 2) 폴백: v2.6 final + 안전 필터 → 참고그룹
    try:
        df = pd.read_csv(HERE / f"latest_{mkt}_final.csv")
        if "ocf_pattern" in df.columns:
            df = df[~df["ocf_pattern"].isin(["이중적자", "밸류트랩의심"])]
        if "risk_level" in df.columns:
            df = df[~df["risk_level"].isin(["주의", "위험"])]
        df["final_score"] = pd.to_numeric(df["final_score"], errors="coerce")
        df = df.dropna(subset=["final_score"]).sort_values(
            "final_score", ascending=False).head(per_bucket)
        rows = [(str(r["name"]), float(r["final_score"]), "") for _, r in df.iterrows()]
        return {"REF": rows} if rows else {}
    except Exception:
        return {}


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
        groups = _picks_by_bucket(mkt)
        lines.append(f"{emoji} {label}")
        if not groups:
            lines.append("  후보 없음 (BUY/WAIT 없음)")
        else:
            for bk in ["BUY", "WAIT", "REF"]:
                rows = groups.get(bk)
                if not rows:
                    continue
                picks = "  ".join(f"{i}. {name}({sc:.1f})"
                                  for i, (name, sc, _g) in enumerate(rows, 1))
                lines.append(f"  {BUCKET_LABEL[bk]}  {picks}")
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
