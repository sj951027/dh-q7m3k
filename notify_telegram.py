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

import html
import json
import os
import re
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 대시보드/필터 주소 (네 GitHub Pages)
DASHBOARD_URL = "https://sj951027.github.io/dh-q7m3k/"
FILTER_URL = "https://sj951027.github.io/dh-q7m3k/filter.html"
# 대형 가치 트랙 관측 리포트 — 메인/필터 어디에도 링크하지 않는 비공개 경로(검증 전 관측 전용)
LARGE_OBS_URL = "https://sj951027.github.io/dh-q7m3k/_large_obs.html"
# v31g 챌린저 테스트 필터 — 메인/필터 미링크 비공개 경로(검증 전 관측 전용)
V31G_FILTER_URL = "https://sj951027.github.io/dh-q7m3k/filter_v31g.html"
# 저변동 트랙 lv_a 테스트 페이지 — 메인/필터 미링크 비공개 경로(검증 전 관측 전용)
LOWVOL_URL = "https://sj951027.github.io/dh-q7m3k/lowvol.html"
# 전체종목 트랙 wu_a 테스트 페이지 — 메인/필터 미링크 비공개 경로(검증 전 관측 전용)
WU_URL = "https://sj951027.github.io/dh-q7m3k/wu.html"
# 모멘텀 대조 모델 mom_a 테스트 페이지 — 메인/필터 미링크 비공개 경로(검증 전 관측 전용)
MOM_URL = "https://sj951027.github.io/dh-q7m3k/mom.html"

TOP_N = 3   # 버킷별로 보여줄 상위 후보 수

# 버킷 → 표시 라벨 (정렬키가 '점수'가 아니라 '등급'임을 메시지에서 드러냄)
BUCKET_LABEL = {
    "BUY":  "🅰️ BUY · 매수후보",
    "WAIT": "🅱️ WAIT · 대기",
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
        # §11: 1차 판정은 OOS 40거래일·h=20d. 그 전엔 단기·소표본이라 '관측중'으로만 표기
        #  (양호/약함 단정 금지 — 노이즈를 신호로 오인하지 않도록).
        PRELIM_DAYS = 40
        if ndays < PRELIM_DAYS:
            return (f"📊 검증 IC(v3, +{h}일) <b>{ic:+.3f}</b>\n"
                    f"   관측중(판정 전) · {ndays}/{PRELIM_DAYS}거래일 · 참고용")
        verdict = "양호" if ic > 0.02 else ("중립" if ic > -0.02 else "약함")
        return (f"📊 검증 IC(v3, +{h}일) <b>{ic:+.3f}</b>\n"
                f"   {verdict} · {ndays}거래일")
    except Exception:
        return "📊 검증 IC: 데이터 쌓는 중"


def _model_status_lines():
    """docs/leaderboard.json → 트랙별 선두 모델 현황(§11 정직 표기: n·CI·노이즈 라벨).
    2026-07-17: 종목 top3 나열(_picks_by_bucket) 대신 이걸 본문으로 사용(사용자 결정).
    데이터는 파이프라인 2.91단계(leaderboard.py)가 매일 갱신. 없거나 깨지면 비치명 스킵."""
    p = HERE / "docs" / "leaderboard.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("status") != "ok" or not d.get("models"):
            return ["📊 모델 현황: 리더보드 갱신 대기중(leaderboard.py)"]
        min_oos = d.get("min_oos", 40)
        by_track = {}
        for m in d["models"]:
            by_track.setdefault(m["track"], []).append(m)

        def metric(m):
            h20, h5 = m.get("h20") or {}, m.get("h5") or {}
            if h20.get("ic") is not None:
                return "h20", h20
            if h5.get("ic") is not None:
                return "h5", h5
            return None, None

        # 표시용 '계열' 분리: mom_* 은 lowvol 테이블을 빌려 쓰지만 정체성이 달라 따로 보여줌.
        FAMILY = [("v3", "🔵", "과매도 v3"), ("lowvol", "🟢", "저변동"),
                  ("mom", "🟠", "모멘텀"), ("wu", "🟣", "전체종목")]
        by_fam = {}
        for ms in by_track.values():
            for m in ms:
                fam = "mom" if str(m["model"]).startswith("mom") else m["track"]
                by_fam.setdefault(fam, []).append(m)

        def bar(oos):
            k = max(0, min(8, round(8 * oos / min_oos)))
            return "▓" * k + "░" * (8 - k)

        out = [f"📊 <b>모델 관측 현황</b> — 전부 판정 전(40거래일 필요)"]
        for fam, emoji, label in FAMILY:
            ms = by_fam.get(fam)
            if not ms:
                continue
            best, bh, bs = None, None, None
            for m in ms:
                h, s = metric(m)
                if s is None:
                    continue
                if best is None or s["ic"] > bs["ic"]:
                    best, bh, bs = m, h, s
            if best is None:
                m0 = max(ms, key=lambda m: m.get("oos_days", 0))
                out.append(f"{emoji} {label} — <b>{m0['model']}</b> 관측 시작 · "
                           f"{bar(m0['oos_days'])} {m0['oos_days']}/{min_oos}일")
                continue
            v = best.get("verdict", "노이즈")
            v_s = "" if v == "노이즈" else f" · {v}"
            out.append(
                f"{emoji} {label} — 선두 <b>{best['model']}</b> · {bar(best['oos_days'])} "
                f"{best['oos_days']}/{min_oos}일 · IC {bs['ic']:+.2f}({bh}·n{bs['n']}){v_s}")
        out.append("※ 참고용 · 계열 간 IC 비교 금지 · 상세는 리더보드")
        return out
    except Exception:
        return ["📊 모델 현황: 리더보드 데이터 없음(비치명)"]


def build_message():
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"✅ <b>스크리너 완료</b> · {today}", ""]

    # 2026-07-17 사용자 결정: v3 top3 종목 나열은 도움 안 됨 → 모델 관측 현황으로 대체.
    #   (종목 상세는 대시보드·필터 링크에서. _picks_by_bucket/_ic_line 은 보존 — 재활성화 가능.)
    lines += _model_status_lines()
    lines.append("")

    lines += [
        "※ 매수신호 아님 · 종목 상세는 아래 링크에서",
        f'🔗 <a href="{DASHBOARD_URL}">대시보드 열기</a>',
        f'🔍 <a href="{FILTER_URL}">필터·정렬 페이지</a>',
        f'🏛️ <a href="{LARGE_OBS_URL}">대형 가치 트랙</a> (준비중 · 관측데이터, 검증 전)',
        f'🧪 <a href="{V31G_FILTER_URL}">v31g 챌린저</a> (테스트 · 관측데이터, 검증 전)',
        f'🧪 <a href="{LOWVOL_URL}">저변동 트랙 lv_a</a> (테스트 · 관측데이터, 검증 전)',
        f'🧪 <a href="{WU_URL}">전체종목 트랙 wu_a</a> (테스트 · 관측데이터, 검증 전)',
        f'🧪 <a href="{MOM_URL}">모멘텀 mom_a</a> (테스트 · 관측데이터, 검증 전)',
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
                  "parse_mode": "HTML",
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
    preview = re.sub(r"<[^>]+>", "", build_message())   # 콘솔엔 태그 빼고
    print("   " + preview.replace("\n", "\n   "))
    print()
    send()


if __name__ == "__main__":
    main()
