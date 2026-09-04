# -*- coding: utf-8 -*-
"""
notify_weekly.py — 주간 리캡 텔레그램 (일요일 1회, 표시 전용)
================================================================
[2026-07-25 신설] 지난 7일의 상태를 한 메시지로 요약해 보낸다:
  ① 판정 카운트다운(§11 OOS 진행) ② 이번 주 성적(상위20 따라사기 r5 − 시장평균, 2026-09-04) ③ 이번 주 달라진 것
  ④ 데이터 적재 현황 ⑤ 특이사항(미실행 거래일 감지)

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
import sys
from datetime import datetime, timedelta
from pathlib import Path

# [2026-07-26] 리다이렉트 인코딩 방어: 스케줄러가 출력을 파일로 보내면 cp949 가 되어
# 이모지 print 에서 UnicodeEncodeError 로 죽는다(locktest 실측). UTF-8 로 강제.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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
        # [2026-09-04] 은퇴 모델 제외 — json retired 플래그(각 스크립트 RETIRED 단일소스) + 구 json 폴백.
        #   종전엔 v31a(8/09 은퇴)·lv_a3 등이 h5 IC 최대값으로 '트랙 선두'에 뽑히는 버그.
        _ret_fb = {"v31a", "v31b", "v31c", "v31d", "v31f", "v31g",
                   "lv_c", "lv_d", "lv_a3", "lv_short", "hv_a", "wu_a", "wu_b"}
        for m in lb.get("models", []):
            if m.get("retired") or m["model"] in _ret_fb:
                continue
            fam = "mom" if str(m["model"]).startswith("mom") else m["track"]
            fams.setdefault(fam, []).append(m)
        lines.append("🏁 <b>판정 카운트다운</b>")
        for fam, emoji, label in FAMILY:
            ms = fams.get(fam)
            if not ms:
                continue
            # [2026-09-04] 판정 대기(40일 미만) 모델 중 가장 임박한 것을 표시. 대기 모델이 없으면 '전부 판정 완료'.
            #   종전엔 누적 최대 OOS 로 '판정 가능'이 늘 떠서(이미 판정 끝난 모델) 정보가 없었음.
            pend = [m for m in ms if (m.get("oos_days") or 0) < min_oos]
            if not pend:
                lines.append(f"  {emoji} {label:8s} 전부 판정 완료(정본은 VERDICT 문서)")
                continue
            mx = max(pend, key=lambda m: m.get("oos_days", 0))
            o = mx.get("oos_days", 0)
            left = max(0, min_oos - o)
            more = f" 외 {len(pend)-1}" if len(pend) > 1 else ""
            lines.append(f"  {emoji} {label:8s} {bar(o, min_oos)} {mx['model']} {o}/{min_oos}일 · {left}거래일 남음{more}")
        lines.append("")
        # [2026-09-04] '트랙 선두(h5 IC 최대)' 제거 → ② 이번 주 성적(cross_sim trailing r5 − 시장평균) + ③ 이번 주 달라진 것.
        #   사용자 지적: 주간 리캡의 선두는 '이번 주 성적'이어야지 등록 후 누적 IC 최대가 아니다. 1주는 운 비중이 커서
        #   순서가 아니라 '시장 대비 ±'만 읽도록 문구를 붙인다. 표시 전용·비치명.
        try:
            cs = json.loads((HERE / "docs" / "cross_sim.json").read_text(encoding="utf-8"))
            tr = cs.get("trailing") or {}
            b5 = (tr.get("bench") or {}).get("r5")
            act_ids = {m["model"] for ms in fams.values() for m in ms}
            rows = [(r["model"], r["r5"] - b5) for r in tr.get("rows", [])
                    if r.get("r5") is not None and b5 is not None and r["model"] in act_ids]
            rows.sort(key=lambda x: -x[1])
            if rows:
                lines.append(f"📈 <b>이번 주 성적</b> (상위20 따라사기 · 시장평균 {b5:+.1f}% 대비 · 비용 0)")
                lines.append("  " + " · ".join(f"{m} {v:+.1f}%p" for m, v in rows))
                lines.append("  ※ 1주는 운 비중이 큼 — 순서보다 시장 대비 ±만 보기 · 판정 정본은 §11")
        except Exception as e:
            lines.append(f"📈 이번 주 성적 실패(비치명): {str(e)[:60]}")
        # ③ 이번 주 달라진 것 — leaderboard_history 7일 범위(판정 표본 도달·자동 라벨 변경·은퇴)
        try:
            hist = json.loads((HERE / "docs" / "leaderboard_history.json").read_text(encoding="utf-8"))
            week = [h for h in hist if str(h.get("date", "")) >= d0]
            ev = []
            if len(week) >= 2:
                first = {x["m"]: x for x in week[0].get("models", [])}
                last = {x["m"]: x for x in week[-1].get("models", [])}
                for mid, x in last.items():
                    q = first.get(mid)
                    if not q or mid not in act_ids:
                        continue
                    nd = 60 if x.get("t") == "large" else min_oos
                    if (q.get("o") or 0) < nd <= (x.get("o") or 0):
                        ev.append(f"{mid} 판정 표본 {nd}일 도달")
                    elif q.get("v") != x.get("v"):
                        ev.append(f"{mid} 자동 라벨 {q.get('v')}→{x.get('v')}(참고)")
            lines.append("")
            lines.append("🔔 <b>이번 주 달라진 것</b>: " + (" · ".join(ev) if ev else "없음"))
        except Exception:
            pass
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

    # ※ 포지션 트래커 요약은 여기 넣지 않는다(2026-07-26 사용자 결정) — 이 메시지는
    #   '공유 채팅방'으로 가므로 개인 자산 정보 금지. 트래커 소식은 트래커 봇(개인 챗) 몫.
    lines.append("")
    lines.append('🔗 <a href="https://sj951027.github.io/dh-q7m3k/leaderboard.html">리더보드 상세</a>')
    # [2026-07-29] qs_a 노출 개정(PREREGISTER_qs.md §6) — 주간에도 관측 페이지 링크 1줄
    lines.append('🧪 <a href="https://sj951027.github.io/dh-q7m3k/qs.html">조용한 강자 qs_a</a> '
                 '(테스트 · 관측데이터, 검증 전)')
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
    _load_dotenv()
    msg = build_message()
    if args.dry_run:
        print(msg)
        return
    import notify_telegram
    notify_telegram.send(message=msg)


if __name__ == "__main__":
    main()
