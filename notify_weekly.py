# -*- coding: utf-8 -*-
"""
notify_weekly.py — 주간 리캡 텔레그램 (일요일 1회, 표시 전용)
================================================================
[2026-07-25 신설] 지난 7일의 상태를 한 메시지로 요약해 보낸다:
  ① 판정 카운트다운(§11 OOS 진행) ② 트랙별 선두(h5 보조지표, n·정직 표기)
  ③ 데이터 적재 현황 ④ 특이사항(미실행 거래일 감지)

원칙: 읽기 전용(history.db·ohlcv.db·docs/*.json) · 점수·판정 계산 없음(leaderboard.json 인용)
      · 비치명 · 전송은 notify_telegram.send() 재사용(.env 토큰 없으면 조용히 스킵).

실행:
  python notify_weekly.py            # 전송
  python notify_weekly.py --dry-run  # 콘솔 출력만(전송 안 함)

스케줄(1회 등록, 관리자 불필요):
  schtasks /Create /TN "dh-q7m3k-weekly" /SC WEEKLY /D SUN /ST 20:00 ^
    /TR "cmd /c cd /d C:\\Users\\SAMSUNG\\Documents\\GitHub\\dh-q7m3k && python notify_weekly.py"
"""
import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
HDB = HERE / "history.db"
ODB = HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"

FAMILY = [("v3", "🔵", "과매도 v3"), ("lowvol", "🟢", "저변동"),
          ("mom", "🟠", "모멘텀"), ("wu", "🟣", "전체종목")]


def bar(oos, goal=40, width=8):
    k = max(0, min(width, round(width * oos / goal)))
    return "▓" * k + "░" * (width - k)


def build_message():
    now = datetime.now()
    d0 = (now - timedelta(days=7)).strftime("%Y%m%d")
    d1 = now.strftime("%Y%m%d")
    lines = [f"📅 <b>주간 리캡</b> · {d0[4:6]}/{d0[6:]} ~ {d1[4:6]}/{d1[6:]}", ""]

    # ① 판정 카운트다운 + ② 트랙 선두 — leaderboard.json 인용(§11 판정은 그쪽 몫)
    try:
        lb = json.loads((HERE / "docs" / "leaderboard.json").read_text(encoding="utf-8"))
        min_oos = lb.get("min_oos", 40)
        fams = {}
        for m in lb.get("models", []):
            fam = "mom" if str(m["model"]).startswith("mom") else m["track"]
            fams.setdefault(fam, []).append(m)
        lines.append("🏁 <b>판정 카운트다운</b>")
        for fam, emoji, label in FAMILY:
            ms = fams.get(fam)
            if not ms:
                continue
            mx = max(ms, key=lambda m: m.get("oos_days", 0))
            o = mx.get("oos_days", 0)
            left = max(0, min_oos - o)
            eta = "판정 가능" if left == 0 else f"{left}거래일 남음"
            lines.append(f"  {emoji} {label:8s} {bar(o, min_oos)} {o}/{min_oos}일 · {eta}")
        lines.append("")
        lines.append("📈 <b>트랙 선두</b> (h5 보조지표 — 판정 아님)")
        for fam, emoji, label in FAMILY:
            ms = fams.get(fam)
            if not ms:
                continue
            best = None
            for m in ms:
                ic = (m.get("h5") or {}).get("ic")
                if ic is None:
                    continue
                if best is None or ic > (best.get("h5") or {}).get("ic", -9):
                    best = m
            if best is None:
                lines.append(f"  {emoji} {label}: 측정 전")
                continue
            h5, h20 = best["h5"], best.get("h20") or {}
            extra = f" · h20 {h20['ic']:+.3f}(n{h20['n']})" if h20.get("ic") is not None else ""
            lines.append(f"  {emoji} {label}: <b>{best['model']}</b> "
                         f"{h5['ic']:+.3f}(n{h5['n']}){extra}")
    except Exception as e:
        lines.append(f"📊 리더보드 요약 실패(비치명): {str(e)[:60]}")
    lines.append("")

    # ③ 데이터 적재 현황 (ohlcv.db 실측)
    try:
        oc = sqlite3.connect(f"file:{ODB}?mode=ro", uri=True)
        q = lambda s: oc.execute(s).fetchone()[0]
        df_d = q("SELECT COUNT(DISTINCT date) FROM daily_flows")
        sf_d = q("SELECT COUNT(DISTINCT date) FROM short_flows")
        cr_d = q("SELECT COUNT(DISTINCT date) FROM short_flows WHERE credit_bal_rate IS NOT NULL")
        ln_d = q("SELECT COUNT(DISTINCT date) FROM short_flows WHERE loan_bal_amt IS NOT NULL")
        vl_d = q("SELECT COUNT(DISTINCT date) FROM valuation_daily")
        try:
            cs_d = q("SELECT COUNT(DISTINCT date) FROM consensus_daily")
        except Exception:
            cs_d = 0
        oc.close()
        lines.append("💾 <b>데이터 적재</b>")
        lines.append(f"  수급 {df_d}일 · 공매도 {sf_d}일 · 신용 {cr_d}일 · 대차 {ln_d}일")
        lines.append(f"  밸류 {vl_d}일 · 컨센서스 {cs_d}회(주간)")
    except Exception as e:
        lines.append(f"💾 데이터 현황 실패(비치명): {str(e)[:60]}")
    lines.append("")

    # ④ 특이사항 — 지난 7일 중 '거래일인데 run 없음' 감지 (거래일 = market_daily 실측 달력)
    try:
        hc = sqlite3.connect(f"file:{HDB}?mode=ro", uri=True)
        runs = {str(r[0]) for r in hc.execute(
            "SELECT DISTINCT run_id FROM stage3_final WHERE CAST(run_id AS TEXT)>=?", (d0,))}
        hc.close()
        oc = sqlite3.connect(f"file:{ODB}?mode=ro", uri=True)
        tdays = [str(r[0]) for r in oc.execute(
            "SELECT DISTINCT date FROM market_daily WHERE series='KOSPI' AND date>=? AND date<=? "
            "ORDER BY date", (d0, d1))]
        oc.close()
        missed = [d for d in tdays if d not in runs]
        if missed:
            lines.append("⚠️ <b>미실행 감지</b> — 거래일인데 run 없음: "
                         + ", ".join(f"{d[4:6]}/{d[6:]}" for d in missed))
            lines.append("   (휴장·의도적 스킵이면 무시. 놓친 거면 §24 규칙대로 새벽 처리 or RUN_ID_OVERRIDE)")
        else:
            lines.append(f"✅ 지난 7일 거래일 {len(tdays)}일 전부 실행됨")
    except Exception as e:
        lines.append(f"⚠️ 미실행 감지 실패(비치명): {str(e)[:60]}")

    lines.append("")
    lines.append('🔗 <a href="https://sj951027.github.io/dh-q7m3k/leaderboard.html">리더보드 상세</a>')
    return "\n".join(lines)


def _load_dotenv():
    """단독 실행 대응: .env 를 os.environ 에 로드(이미 있으면 안 덮음).
    평소 배치는 run_and_diversify 가 해주지만, 스케줄러 단독 실행 경로엔 없어서 필요."""
    import os
    p = HERE / ".env"
    if not p.exists():
        return
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="주간 리캡 텔레그램(표시 전용)")
    ap.add_argument("--dry-run", action="store_true", help="콘솔 출력만, 전송 안 함")
    args = ap.parse_args()
    msg = build_message()
    if args.dry_run:
        print(msg)
        return
    _load_dotenv()
    import notify_telegram
    notify_telegram.send(message=msg)


if __name__ == "__main__":
    main()
