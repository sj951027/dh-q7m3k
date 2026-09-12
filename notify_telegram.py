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
# [2026-08-09] v31g 링크 제거 — §11 첫 판정 기각(VERDICT_20260809.md). 페이지 파일은 보존.
# 저변동 트랙 lv_b 테스트 페이지 — 메인/필터 미링크 비공개 경로(검증 전 관측 전용)
LOWVOL_URL = "https://sj951027.github.io/dh-q7m3k/lowvol.html"
# 전체종목 트랙 wu_a 테스트 페이지 — 메인/필터 미링크 비공개 경로(검증 전 관측 전용)
WU_URL = "https://sj951027.github.io/dh-q7m3k/wu.html"
# 모멘텀 대조 모델 mom_a 테스트 페이지 — 메인/필터 미링크 비공개 경로(검증 전 관측 전용)
MOM_URL = "https://sj951027.github.io/dh-q7m3k/mom.html"
# 조용한 강자 qs_a 테스트 페이지 — 메인/필터 미링크 비공개 경로(검증 전 관측 전용)
#   2026-07-29 PREREGISTER_qs.md §6 개정으로 노출 허용(점수·판정 불변)
QS_URL = "https://sj951027.github.io/dh-q7m3k/qs.html"
# 대형 트랙 테스트 모델 ls_t1 점수 페이지 — 메인/필터 미링크 비공개 경로(테스트·검증 전)
LARGE_TEST_URL = "https://sj951027.github.io/dh-q7m3k/_large_test.html"
# 전 트랙 모델 리더보드 상세(§11 판정 + h1~h20 관측) — 2026-07-25 추가
LEADERBOARD_URL = "https://sj951027.github.io/dh-q7m3k/leaderboard.html"

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
                  ("mom", "🟠", "모멘텀"), ("wu", "🟣", "전체종목"),
                  ("large", "🏛️", "대형 가치(판정 60~120d)")]
        by_fam = {}
        for ms in by_track.values():
            for m in ms:
                fam = "mom" if str(m["model"]).startswith("mom") else m["track"]
                by_fam.setdefault(fam, []).append(m)

        def bar(oos):
            k = max(0, min(8, round(8 * oos / min_oos)))
            return "▓" * k + "░" * (8 - k)

        # 2026-08-12 사용자 결정: 선두 모델의 최신 run 유니버스 크기 병기.
        #   근거: lv 유니버스가 381→26으로 마르는 걸 표시로 알 수 없었음(8/12 발견).
        #   판정 표본이 얇아지는 걸 실시간 인지하는 용도 — 표시 전용, 실패해도 생략(비치명).
        def uni_size(model):
            try:
                import sqlite3
                con = sqlite3.connect(f"file:{Path(__file__).resolve().parent / 'history.db'}?mode=ro",
                                      uri=True)
                for tbl, mcol in (("v3_scores", "model_id"), ("lowvol_scores", "model_id"),
                                  ("wu_scores", "model_id"), ("large_final", None)):
                    try:
                        if mcol:
                            r = con.execute(
                                f"SELECT COUNT(*) FROM {tbl} WHERE {mcol}=? AND run_id="
                                f"(SELECT MAX(run_id) FROM {tbl} WHERE {mcol}=?)",
                                (model, model)).fetchone()
                            if r and r[0]:
                                con.close(); return r[0]
                        elif model == "ls_t1":
                            r = con.execute("SELECT COUNT(*) FROM large_final WHERE run_id="
                                            "(SELECT MAX(run_id) FROM large_final)").fetchone()
                            if r and r[0]:
                                con.close(); return r[0]
                    except Exception:
                        continue
                con.close()
            except Exception:
                pass
            return None

        # 2026-08-11 사용자 결정: '모델 관측 현황' 헤더 제거 — 제목 아래 리더보드 링크가 그 역할.
        out = []
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
                u = uni_size(m0["model"])
                u_s = f" · uni {u}" if u else ""
                out.append(f"{emoji} {label} — <b>{m0['model']}</b> 관측 시작 · "
                           f"{bar(m0['oos_days'])} {m0['oos_days']}/{min_oos}일{u_s}")
                continue
            v = best.get("verdict", "노이즈")
            v_s = "" if v == "노이즈" else f" · {v}"
            u = uni_size(best["model"])
            u_s = f" · uni {u}" if u else ""
            out.append(
                f"{emoji} {label} — 선두 <b>{best['model']}</b> · {bar(best['oos_days'])} "
                f"{best['oos_days']}/{min_oos}일 · IC {bs['ic']:+.2f}({bh}·n{bs['n']}){u_s}{v_s}")
        out.append("※ 참고용 · 계열 간 IC 비교 금지 · 상세는 리더보드")
        return out
    except Exception:
        return ["📊 모델 현황: 리더보드 데이터 없음(비치명)"]


# ====================================================================================
# [2026-09-04] 텔레그램 요약 v2 — 리더보드 2안(쉬운 버전)과 같은 순서 (사용자 결정)
#   ① 지금 기준(정본 판정) → ② 돈(최근 1개월 시장대비) → ③ 판정 캘린더(D-day) → ④ 어제와 달라진 것
#   종전 _model_status_lines 는 보존(재활성화 가능). 표시 전용 · 비치명 · 판정/점수 무접촉.
#   버그 교정: 종전은 은퇴 모델(v31a)·h20 없는 모델(px_a, h5 n12)이 'IC 최대'로 선두에 뽑혔음.
# ====================================================================================
# 정본 판정(VERDICT 봉인) — 판정·은퇴 시 갱신(docs/leaderboard.html SEALED 맵과 동일하게 유지)
SEALED_V2 = {"v30": "유의(8/09 정본)", "lv_b": "기움(8/29 정본)",
             "lv_a": "노이즈(8/29)", "mom_a": "노이즈(8/29)", "sm_a": "노이즈(9/01)"}
RETIRED_FALLBACK_V2 = {"v31a", "v31b", "v31c", "v31d", "v31f", "v31g",
                       "lv_c", "lv_d", "lv_a3", "lv_short", "hv_a", "wu_a", "wu_b"}   # 구 json 폴백
MONEY_MODELS_V2 = ["v30", "lv_b"]      # ② 돈 줄 대표(+ 판정 캘린더 선두 1개 자동 추가)

# [2026-09-12] 표시 순서 = 실제 운용 순서. 사용자는 lv_b 로 운용한다(OPS_GUIDE §0 · PTW #저변동).
#   v30 은 챔피언(유의)이지만 실거래는 lv_b 라, 알림은 lv_b 를 먼저 놓고 v30 을 참고로 뒤에 둔다.
#   판정 라벨(기움/유의)은 그대로 병기한다 — 운용 여부와 §11 판정은 별개다.
LIVE_MODEL_V3 = "lv_b"                  # 실제 운용 중(표시 순서 1번)
REF_MODEL_V3 = "v30"                    # 참고(챔피언)
MODEL_ICON_V3 = {"lv_b": "🧪", "v30": "🏆"}


def _run_id_v3():
    """표시용 데이터 날짜 = stage3_final 최신 run_id. 실패 시 오늘 날짜(종전 동작)."""
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{HERE / 'history.db'}?mode=ro", uri=True)
        rid = con.execute("SELECT MAX(run_id) FROM stage3_final").fetchone()[0]
        con.close()
        if rid and len(str(rid)) == 8:
            return str(rid)
    except Exception:
        pass
    return datetime.now().strftime("%Y%m%d")


def _date_head_v3():
    """'9/11(금)' — 발송 시각이 아니라 데이터 날짜. 자정 넘김·주말 재실행에서 어긋나던 것 교정."""
    rid = _run_id_v3()
    try:
        d = datetime.strptime(rid, "%Y%m%d")
        return f"{d.month}/{d.day}({'월화수목금토일'[d.weekday()]})"
    except Exception:
        return rid


def _apply_registry():
    """[2026-09-06] docs/models_registry.json(정본 판정·은퇴 단일 소스)이 있으면 위 인라인 상수를 덮어쓴다.
    없거나 깨졌으면 인라인 폴백 그대로(비치명). 표시 전용."""
    global SEALED_V2, RETIRED_FALLBACK_V2, MONEY_MODELS_V2
    try:
        reg = json.loads((HERE / "docs" / "models_registry.json").read_text(encoding="utf-8"))
        ret = set((reg.get("retired") or {}).keys())
        sealed = {k: v.get("short") for k, v in (reg.get("sealed") or {}).items()
                  if v.get("short") and k not in ret}
        if sealed: SEALED_V2 = sealed
        if ret: RETIRED_FALLBACK_V2 = ret
        if reg.get("money"): MONEY_MODELS_V2 = list(reg["money"])
        # [2026-09-12] 운용 모델도 원장(registry)에서 읽는다 — 나중에 lv_b 가 아닌 모델로 옮기면
        #   models_registry.json 의 "live" 한 줄만 고치면 알림 순서가 따라온다(코드 수정 불필요).
        global LIVE_MODEL_V3, REF_MODEL_V3
        if reg.get("live"): LIVE_MODEL_V3 = str(reg["live"])
        if reg.get("reference"): REF_MODEL_V3 = str(reg["reference"])
    except Exception:
        pass


_apply_registry()


def _freshness_warnings():
    """[2026-09-09] 지수(market_daily KOSPI/KOSDAQ)·상장목록 캐시(listing_cache)가 시세(daily_ohlcv) 마지막 날짜보다
    뒤처지면 경고 문자열 목록. 실패 시 빈 목록(비치명). 판정·점수 무관, 텔레그램 표시 전용."""
    import sqlite3, json
    out = []
    px_last = None
    try:
        odb = HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"
        con = sqlite3.connect(f"file:{odb}?mode=ro", uri=True)
        px_last = con.execute("SELECT MAX(date) FROM daily_ohlcv").fetchone()[0]
        idx = dict(con.execute("SELECT series, MAX(date) FROM market_daily GROUP BY series").fetchall())
        con.close()
        stale = [f"{k} {v[4:6]}/{v[6:]}" for k, v in idx.items() if k in ("KOSPI", "KOSDAQ") and v and px_last and v < px_last]
        if stale:
            out.append(f"⚠️ 지수 시계열 정지: {' · '.join(stale)} (시세 {px_last[4:6]}/{px_last[6:]}) — 돈 표 코스피선 참고만")
    except Exception:
        pass
    try:
        # [2026-09-11] 수급 소스가 KIS daily_flows 로 바뀜 — 시세보다 뒤처지면 그날 수급 점수는 그날치 빠진 창
        con = sqlite3.connect(f"file:{HERE / '..' / 'dh-q7m3k-data' / 'ohlcv.db'}?mode=ro", uri=True)
        fl_last = con.execute("SELECT MAX(date) FROM daily_flows").fetchone()[0]
        con.close()
        if px_last and fl_last and fl_last < px_last:
            out.append(f"⚠️ KIS 수급 정지: {fl_last[4:6]}/{fl_last[6:]} (시세 {px_last[4:6]}/{px_last[6:]}) — 수급 점수는 그날치 빠진 창")
    except Exception:
        pass
    try:
        lc = HERE / ".." / "dh-q7m3k-data" / "listing_cache.json"
        if lc.exists():
            d = json.loads(lc.read_text(encoding="utf-8"))
            src = str(d.get("source", ""))
            at = str(d.get("saved_at", ""))[:10].replace("-", "")
            if src.startswith("seed:") and len(src) >= 13:
                at = src[5:13]                      # 시드는 저장 시각이 아니라 시드 기준일(ohlcv 최신일)
            if src.startswith("seed") or (px_last and at and at < px_last):
                out.append(f"⚠️ 상장목록 예비 캐시 사용 중(기준 {at[4:6]}/{at[6:]}{', DB 시드' if src.startswith('seed') else ''}) — FDR 목록 서버 복구 대기")
    except Exception:
        pass
    return out


def _uni_latest2(model):
    """대표 모델의 최신 run·직전 run 유니버스 크기 (표시 전용, 실패 시 None)."""
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{HERE / 'history.db'}?mode=ro", uri=True)
        for tbl in ("v3_scores", "lowvol_scores", "wu_scores"):
            rows = con.execute(
                f"SELECT run_id, COUNT(*) FROM {tbl} WHERE model_id=? GROUP BY run_id "
                f"ORDER BY run_id DESC LIMIT 2", (model,)).fetchall()
            if rows:
                con.close()
                return rows[0][1], (rows[1][1] if len(rows) > 1 else None)
        con.close()
    except Exception:
        pass
    return None, None


def _model_status_lines_v2():
    p = HERE / "docs" / "leaderboard.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("status") != "ok" or not d.get("models"):
            return ["📊 모델 현황: 리더보드 갱신 대기중(leaderboard.py)"]
        min_oos = d.get("min_oos", 40)
        need = lambda m: 60 if m.get("track") == "large" else min_oos
        act = [m for m in d["models"]
               if not m.get("retired") and m["model"] not in RETIRED_FALLBACK_V2]
        by = {m["model"]: m for m in act}
        out = []

        # ① 지금 기준 — 정본 판정 + 유니버스 크기(8/12 사건: 고갈 감시)
        parts = []
        for mid in ("v30", "lv_b"):
            u, _ = _uni_latest2(mid)
            parts.append(f"<b>{mid}</b> {SEALED_V2.get(mid, '')}" + (f" · uni {u}" if u else ""))
        out.append("🏆 지금 기준: " + " · ".join(parts))

        # ③ 판정 캘린더(먼저 계산 — ②의 자동 추가 모델에 필요)
        wait = sorted([m for m in act if (m.get("oos_days") or 0) < need(m)],
                      key=lambda m: need(m) - (m.get("oos_days") or 0))
        reached = [m for m in act if (m.get("oos_days") or 0) >= need(m)
                   and m["model"] not in SEALED_V2]

        # ② 돈 — cross_sim trailing 최근 20거래일 vs 시장평균
        try:
            cs = json.loads((HERE / "docs" / "cross_sim.json").read_text(encoding="utf-8"))
            tr = cs.get("trailing") or {}
            rows = {r["model"]: r for r in tr.get("rows", [])}
            b20 = (tr.get("bench") or {}).get("r20")
            money = list(MONEY_MODELS_V2) + [m["model"] for m in wait[:1]]
            mp = []
            for mid in money:
                r = rows.get(mid)
                if r and r.get("r20") is not None and b20 is not None:
                    mp.append(f"{mid} {r['r20'] - b20:+.1f}%p")
            if mp:
                out.append(f"💰 최근 1개월 시장대비: " + " · ".join(mp)
                           + f" (시장 {b20:+.1f}% · 상위20 따라사기·비용 0)")
        except Exception:
            pass

        cal = [f"<b>{m['model']}</b> D-{need(m) - (m.get('oos_days') or 0)}"
               + ("(h60)" if m.get("track") == "large" else "") for m in wait]
        if reached:
            cal = [f"<b>{m['model']}</b> 도달(판정 대기)" for m in reached] + cal
        out.append("📅 판정: " + (" · ".join(cal) if cal else "대기 중인 모델 없음"))

        # ④ 어제와 달라진 것 — leaderboard_history 마지막 2건 + 대표 유니버스 급감
        ev = []
        try:
            hist = json.loads((HERE / "docs" / "leaderboard_history.json").read_text(encoding="utf-8"))
            if isinstance(hist, list) and len(hist) >= 2:
                prev = {x["m"]: x for x in hist[-2].get("models", [])}
                for x in hist[-1].get("models", []):
                    mid = x["m"]
                    if mid not in by:
                        continue
                    q = prev.get(mid)
                    if not q:
                        continue
                    nd = 60 if x.get("t") == "large" else min_oos
                    if (q.get("o") or 0) < nd <= (x.get("o") or 0):
                        ev.append(f"{mid} 판정 표본 {nd}일 도달")
                    if q.get("v") != x.get("v") and mid not in SEALED_V2:
                        ev.append(f"{mid} 자동 라벨 {q.get('v')}→{x.get('v')}(참고)")
        except Exception:
            pass
        for mid in ("v30", "lv_b"):
            u, u0 = _uni_latest2(mid)
            if u and u0 and u < 0.5 * u0:
                ev.append(f"⚠️ {mid} 유니버스 {u0}→{u} 급감(판정 표본 얇아짐)")
        # [2026-09-09] 데이터 신선도 — 지수·상장목록이 시세보다 뒤처지면 알린다(조용히 낡는 것 방지, 표시 전용).
        try:
            for w in _freshness_warnings():
                ev.append(w)
        except Exception:
            pass
        out.append("🔔 달라진 것: " + (" · ".join(ev) if ev else "없음"))
        out.append("※ 계열 간 IC 비교 금지 · 판정 정본은 VERDICT 문서")
        return out
    except Exception:
        return ["📊 모델 현황: 리더보드 데이터 없음(비치명)"]


def _status_lines_v3():
    """[2026-09-12] 섹션형 본문. lv_b(운용) → v30(참고) → 돈 → 판정 일정 → (있을 때만) 달라진 것.
    한 줄에 정보를 몰아넣지 않는다 — 폰에서 줄바꿈으로 접히던 것을 없애려는 것. 표시 전용."""
    p = HERE / "docs" / "leaderboard.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("status") != "ok" or not d.get("models"):
            return ["📊 모델 현황: 리더보드 갱신 대기중(leaderboard.py)"]
        min_oos = d.get("min_oos", 40)
        need = lambda m: 60 if m.get("track") == "large" else min_oos
        act = [m for m in d["models"]
               if not m.get("retired") and m["model"] not in RETIRED_FALLBACK_V2]
        out = []

        # ① 운용 중 → 참고 순서. 유니버스 크기는 8/12 고갈 사건 이후 매일 보는 값.
        for mid in (LIVE_MODEL_V3, REF_MODEL_V3):
            u, _ = _uni_latest2(mid)
            line = f"{MODEL_ICON_V3.get(mid, '·')} <b>{mid}</b>"
            if u:
                line += f" {u}종목"
            if SEALED_V2.get(mid):
                line += f" · {SEALED_V2[mid]}"
            out.append(line)

        # ③ 판정 캘린더(먼저 계산 — ②의 '판정 임박' 모델에 필요)
        wait = sorted([m for m in act if (m.get("oos_days") or 0) < need(m)],
                      key=lambda m: need(m) - (m.get("oos_days") or 0))
        reached = [m for m in act if (m.get("oos_days") or 0) >= need(m)
                   and m["model"] not in SEALED_V2]
        soon = wait[0]["model"] if wait else None

        # ② 돈 — 공통 잣대(cross_sim) 최근 20거래일 vs 시장. 운용 2개 + 판정 임박 1개만.
        #    전부 싣지 않는 이유: 한 달 수익으로 줄 세우기가 되면 트랙 간 비교 금지 원칙과 어긋난다.
        try:
            cs = json.loads((HERE / "docs" / "cross_sim.json").read_text(encoding="utf-8"))
            tr = cs.get("trailing") or {}
            rows = {r["model"]: r for r in tr.get("rows", [])}
            b20 = (tr.get("bench") or {}).get("r20")
            picks = [(LIVE_MODEL_V3, "← 운용 중"), (REF_MODEL_V3, "")]
            if soon and soon not in (LIVE_MODEL_V3, REF_MODEL_V3):
                picks.append((soon, "← 판정 임박"))
            body = []
            for mid, tag in picks:
                r = rows.get(mid)
                if r and r.get("r20") is not None and b20 is not None:
                    body.append(f"{mid:<5} {r['r20'] - b20:+5.1f}%p" + (f"   {tag}" if tag else ""))
            if body:
                out.append("")
                out.append(f"💰 <b>최근 1개월</b> (시장 {b20:+.1f}%, 상위20 동일가중)")
                out.append("<pre>" + "\n".join(body) + "</pre>")
        except Exception:
            pass

        # ③ 표시 — 남은 일수가 같은 모델끼리 묶고 최대 3줄. 전체는 리더보드에.
        cal = []
        if reached:
            cal.append("· " + " · ".join(m["model"] for m in reached) + " → <b>판정 가능</b>")
        grp = {}
        for m in wait:
            grp.setdefault(need(m) - (m.get("oos_days") or 0), []).append(m["model"])
        for dd in sorted(grp)[:(2 if reached else 3)]:   # 판정 가능 줄이 있으면 합쳐 3줄
            cal.append(f"· {' · '.join(grp[dd])} → {dd}거래일 뒤")
        if cal:
            out.append("")
            out.append("📅 <b>판정 일정</b>")
            out += cal

        # ④ 달라진 것 — 있을 때만. '없음'을 매일 찍지 않는다.
        ev = _change_events_v3(act, min_oos, need)
        if ev:
            out.append("")
            out.append("🔔 " + " · ".join(ev))
        return out
    except Exception:
        return ["📊 모델 현황: 리더보드 데이터 없음(비치명)"]


def _change_events_v3(act, min_oos, need):
    """어제와 달라진 것 + 데이터 신선도 경고. v2 의 ④ 블록과 같은 규칙(표시 전용)."""
    by = {m["model"]: m for m in act}
    ev = []
    try:
        hist = json.loads((HERE / "docs" / "leaderboard_history.json").read_text(encoding="utf-8"))
        if isinstance(hist, list) and len(hist) >= 2:
            prev = {x["m"]: x for x in hist[-2].get("models", [])}
            for x in hist[-1].get("models", []):
                mid = x["m"]
                if mid not in by or not prev.get(mid):
                    continue
                q = prev[mid]
                nd = 60 if x.get("t") == "large" else min_oos
                if (q.get("o") or 0) < nd <= (x.get("o") or 0):
                    ev.append(f"{mid} 판정 표본 {nd}일 도달")
                if q.get("v") != x.get("v") and mid not in SEALED_V2:
                    ev.append(f"{mid} 자동 라벨 {q.get('v')}→{x.get('v')}(참고)")
    except Exception:
        pass
    for mid in (LIVE_MODEL_V3, REF_MODEL_V3):
        u, u0 = _uni_latest2(mid)
        if u and u0 and u < 0.5 * u0:
            ev.append(f"⚠️ {mid} 유니버스 {u0}→{u} 급감(판정 표본 얇아짐)")
    try:
        ev += _freshness_warnings()
    except Exception:
        pass
    return ev


def build_message():
    # [2026-09-12] v3 레이아웃. 종전 v2(제목+리더보드 링크+한 줄 요약 4개+링크 3줄)는
    #   _model_status_lines_v2() 로 보존 — 되돌리려면 아래 lines 구성만 v2 로 바꾸면 된다.
    #   바뀐 점: ① 날짜를 데이터 기준(run_id)으로 ② lv_b(운용)를 먼저, v30(참고)을 뒤로
    #   ③ 한 줄에 몰아넣지 않고 섹션 분리 ④ 링크 4개→2개(저변동 종목·리더보드)
    #   ⑤ '달라진 것: 없음' 줄 삭제(있을 때만 표시).
    lines = [f"✅ <b>스크리너 {_date_head_v3()}</b> · 이상 없음", ""]
    lines += _status_lines_v3()
    lines += [
        "",
        f'🔎 <a href="{LOWVOL_URL}">저변동 종목 보기</a> · '
        f'<a href="{LEADERBOARD_URL}">리더보드</a>(v30·다른 모델)',
        "<i>매수신호 아님 · 판정 정본은 VERDICT 문서</i>",
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
