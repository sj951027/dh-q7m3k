# -*- coding: utf-8 -*-
"""data_health.py — 자료 건강 점검표 (2026-10-18 도입, 표시·알림 전용 — 점수·판정·게이트 무관)

왜: 자료가 조용히 멈춘 사고가 세 번 있었다(지수 9/17 · 보충표 10/02 · 수급 9/11). 셋 다 며칠 뒤에 사람이 발견했다.
    갈래마다 "마지막 날짜가 기준일(시세 본표 마지막 날짜)보다 몇 거래일 뒤처졌나"와 "마지막 날 건수가 평소의 절반 밑인가"를
    매일 한 표로 본다. 갈래별 '정상 지연'은 실측으로 정했다(아래 BRANCHES 주석).

무엇을 보나 (갈래 = 표 또는 표의 열 하나):
  시세 본표 · 보충표(대형 136종목) · 수급(KIS) · 공매도 · 대차잔고 · 신용잔고(정상 3거래일 지연) · PER/PBR ·
  지수 코스피·코스닥 · 컨센서스(주 1회) · DART 공시 · 상장 변화 · 실적 증분 수집 · 점수 run

출력:
  python data_health.py            → docs/data_health.json · docs/data_health.md 갱신 + 콘솔 표. 항상 종료코드 0(감시 도구가 배치를 막지 않게).
  notify_telegram._freshness_warnings 가 telegram_lines() 를 불러 ⚠️ 줄만 싣는다(정상이면 아무 줄도 없음).
읽기 전용(mode=ro). 되감기: collect(asof='YYYYMMDD_HHMM') 은 fetched_at 이 있는 표(보충표·수급·공매도·신용·대차)를 그 시점 상태로 본다 —
  과거 사고를 그대로 재현해 시험하는 데 쓴다(tests/test_data_health.py).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
OHLCV_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))
HISTORY_DB = os.environ.get("HISTORY_DB", str(HERE / "history.db"))
EARNINGS_DB = os.environ.get("EARNINGS_DB", str(HERE / ".." / "dh-q7m3k-data" / "earnings.db"))
DOCS = HERE / "docs"

COUNT_DROP = 0.5          # 마지막 날 건수 < 직전 날들 중앙값 × 0.5 → 건수 급감
HIST_DAYS = 10            # 중앙값을 낼 직전 날짜 수
LOOKBACK_CAL_DAYS = 60    # 조회 범위(달력일) — 큰 표를 통째로 훑지 않게

# 갈래 정의: (키, 이름, 허용 지연(거래일), 건수 검사 여부)
#   허용 지연 실측(2026-10-18, 10/16 배치 뒤): 시세·보충표·수급·공매도·대차·PER/PBR·지수·실적수집·run = 0
#   신용잔고 credit_bal_rate = 3거래일(10/13 값이 10/16 에 마지막) → 허용 4 · 컨센서스 = 6~10 달력일 간격 → 허용 10거래일
#   DART 공시·상장 변화 = 거래일마다 있으나 0건인 날이 있을 수 있어 허용 1, 건수 검사 안 함
BRANCHES = [
    ("ohlcv",      "시세 본표",        0, True),
    ("extra",      "보충표(대형 136)", 0, True),
    ("flows",      "수급(KIS)",        0, True),
    ("short",      "공매도",           0, True),
    ("loan",       "대차잔고",         0, True),
    ("credit",     "신용잔고",         4, True),
    ("valuation",  "PER/PBR",          0, True),
    ("idx_kospi",  "지수 코스피",      0, False),
    ("idx_kosdaq", "지수 코스닥",      0, False),
    ("consensus",  "컨센서스",        10, True),
    ("dart",       "DART 공시",        1, False),
    ("uni_events", "상장 변화",        1, False),
    ("earn_fetch", "실적 증분 수집",   1, False),
    ("runs",       "점수 run",         0, False),
    # [2026-10-18 추가] 업종 분류(sector_cache.json, DART 산업코드 → 업종 버킷 · diversify_picks 가 씀). 파일 날짜는 새 종목이 있을 때만 바뀌어
    #   지연 허용 30. 대신 '최신 run 종목 중 업종 있는 비율'(cover)이 90% 밑이면 ⚠️ — 조용히 비는 것을 잡는다.
    ("sector",     "업종 분류",       30, False),
]
SECTOR_CACHE = HERE / "sector_cache.json"
COVER_MIN = 0.9
ALLOWED = {k: a for k, _, a, _ in BRANCHES}
NAMES = {k: n for k, n, _, _ in BRANCHES}
CHECK_COUNT = {k: c for k, _, _, c in BRANCHES}


# ──────────────────────────────────────────────── 순수 함수 ────────────────────────────────────────────────
def trading_lag(last_date, ref_date, calendar):
    """last_date 이후 ref_date 까지의 거래일 수(달력 = 거래일 날짜 집합). last_date 가 없으면 None.
    달력에 없는 날짜(주말 행 등)도 '그 사이 거래일 수'로 센다. last_date >= ref_date 면 0."""
    if not last_date:
        return None
    if last_date >= ref_date:
        return 0
    return sum(1 for d in calendar if last_date < d <= ref_date)


def assess(branches, ref_date, calendar):
    """branches = {key: {"last": 'YYYYMMDD'|None, "n_last": int|None, "n_hist": [int,...]}} → 행 목록.
    각 행: key·name·last·lag·allowed·n_last·n_med·status('ok'|'lag'|'count'|'missing')·note. 순수 함수(예외 없음)."""
    rows = []
    for key, name, allowed, check_count in BRANCHES:
        b = (branches or {}).get(key) or {}
        last = b.get("last")
        n_last = b.get("n_last")
        hist = [x for x in (b.get("n_hist") or []) if x is not None]
        n_med = sorted(hist)[len(hist) // 2] if hist else None
        lag = trading_lag(last, ref_date, calendar)
        status, note = "ok", ""
        if last is None:
            status, note = "missing", "자료 없음(표가 비었거나 읽기 실패)"
        elif lag is not None and lag > allowed:
            status, note = "lag", f"{lag}거래일 뒤처짐(허용 {allowed})"
        elif check_count and n_last is not None and n_med and n_last < COUNT_DROP * n_med:
            status, note = "count", f"마지막 날 건수 {n_last} — 평소 {n_med}의 절반 미만"
        elif b.get("cover") is not None and float(b["cover"]) < COVER_MIN:
            status, note = "count", f"최신 run 종목 중 {float(b['cover']):.0%}만 값 있음(기준 {COVER_MIN:.0%})"
        rows.append({"key": key, "name": name, "last": last, "lag": lag, "allowed": allowed,
                     "n_last": n_last, "n_med": n_med, "status": status, "note": note})
    return rows


def _md(d):
    return f"{d[4:6]}/{d[6:8]}" if d and len(d) >= 8 else "없음"


def warning_lines(rows, ref_date):
    """⚠️ 줄 목록(정상이면 빈 목록). 텔레그램·콘솔 공용."""
    out = []
    for r in rows:
        if r["status"] == "lag":
            out.append(f"⚠️ 자료 뒤처짐: {r['name']} 마지막 {_md(r['last'])} (시세 {_md(ref_date)} · {r['note']})")
        elif r["status"] == "count":
            out.append(f"⚠️ 자료 건수 급감: {r['name']} {r['note']} ({_md(r['last'])})")
        elif r["status"] == "missing":
            out.append(f"⚠️ 자료 없음: {r['name']}")
    return out


def to_markdown(rows, ref_date, asof_text):
    lines = [f"# 자료 건강 점검표 — 기준 시세 {ref_date} (생성 {asof_text})", "",
             "갈래마다 마지막 날짜가 시세 본표보다 몇 거래일 뒤처졌는지(허용값 초과 = ⚠️)와 마지막 날 건수가 평소(직전 10일 중앙값)의 절반 밑인지를 본다. 표시·알림 전용.",
             "", "| 갈래 | 마지막 날짜 | 지연(허용) | 건수(마지막일 / 평소) | 상태 |", "|---|---|---|---|---|"]
    mark = {"ok": "✅", "lag": "⚠️ 뒤처짐", "count": "⚠️ 건수 급감", "missing": "⚠️ 없음"}
    for r in rows:
        lag = "—" if r["lag"] is None else f"{r['lag']}({r['allowed']})"
        cnt = ("—" if r["n_last"] is None else f"{r['n_last']:,}") + (f" / {r['n_med']:,}" if r["n_med"] else "")
        lines.append(f"| {r['name']} | {r['last'] or '없음'} | {lag} | {cnt} | {mark[r['status']]} {r['note']} |")
    lines += ["", "정상 지연 실측(2026-10-18): 신용잔고 3거래일 · 컨센서스 주 1회 · 나머지 0. 되감기 시험: `tests/test_data_health.py`."]
    return "\n".join(lines) + "\n"


# ──────────────────────────────────────────────── 수집(읽기 전용) ────────────────────────────────────────────────
def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _hist(con, sql, params=()):
    """[(date, n), ...] 최신이 앞 → (last, n_last, n_hist)."""
    rows = con.execute(sql, params).fetchall()
    if not rows:
        return {"last": None, "n_last": None, "n_hist": []}
    return {"last": str(rows[0][0]), "n_last": int(rows[0][1]), "n_hist": [int(r[1]) for r in rows[1:1 + HIST_DAYS]]}


def collect(ohlcv_db=OHLCV_DB, history_db=HISTORY_DB, earnings_db=EARNINGS_DB, asof=None):
    """갈래별 {last, n_last, n_hist} 와 기준일·거래일 달력. asof='YYYYMMDD_HHMM' 이면 fetched_at 이 있는 표는 그 시점으로 되감고,
    시세 본표·지수·run 은 날짜 ≤ asof 날짜로 자른다(본표 fetched_at 은 재수집 때 덮어써져 되감기에 못 쓴다). 실패한 갈래는 비워 둔다."""
    out, ref, cal = {}, None, []
    asof_d = asof[:8] if asof else None
    lim = (datetime.strptime(asof_d, "%Y%m%d") if asof_d else datetime.now()) - timedelta(days=LOOKBACK_CAL_DAYS)
    lower = lim.strftime("%Y%m%d")
    try:
        con = _ro(ohlcv_db)
        try:
            # 기준일·달력: 시세 본표 날짜(최근 60달력일)
            dsql = "SELECT date, COUNT(*) FROM daily_ohlcv WHERE date >= ?" + (" AND date <= ?" if asof_d else "") + " GROUP BY date ORDER BY date DESC"
            dp = (lower, asof_d) if asof_d else (lower,)
            drows = con.execute(dsql, dp).fetchall()
            if drows:
                ref = str(drows[0][0])
                cal = sorted(str(r[0]) for r in drows)
                out["ohlcv"] = {"last": ref, "n_last": int(drows[0][1]), "n_hist": [int(r[1]) for r in drows[1:1 + HIST_DAYS]]}
            fa = " AND fetched_at <= ?" if asof else ""
            fp = (lower, asof) if asof else (lower,)
            out["extra"] = _hist(con, f"SELECT date, COUNT(*) FROM daily_ohlcv_extra WHERE date >= ?{fa} GROUP BY date ORDER BY date DESC", fp)
            out["flows"] = _hist(con, f"SELECT date, COUNT(*) FROM daily_flows WHERE date >= ?{fa} GROUP BY date ORDER BY date DESC", fp)
            out["short"] = _hist(con, f"SELECT date, COUNT(short_qty) FROM short_flows WHERE date >= ?{fa} GROUP BY date HAVING COUNT(short_qty) > 0 ORDER BY date DESC", fp)
            out["loan"] = _hist(con, f"SELECT date, COUNT(loan_bal_qty) FROM short_flows WHERE date >= ?{fa} GROUP BY date HAVING COUNT(loan_bal_qty) > 0 ORDER BY date DESC", fp)
            out["credit"] = _hist(con, f"SELECT date, COUNT(credit_bal_rate) FROM short_flows WHERE date >= ?{fa} GROUP BY date HAVING COUNT(credit_bal_rate) > 0 ORDER BY date DESC", fp)
            vd = " AND date <= ?" if asof_d else ""
            vp = (lower, asof_d) if asof_d else (lower,)
            out["valuation"] = _hist(con, f"SELECT date, COUNT(*) FROM valuation_daily WHERE date >= ?{vd} GROUP BY date ORDER BY date DESC", vp)
            for key, series in (("idx_kospi", "KOSPI"), ("idx_kosdaq", "KOSDAQ")):
                out[key] = _hist(con, f"SELECT date, COUNT(*) FROM market_daily WHERE series = ? AND date >= ?{vd} GROUP BY date ORDER BY date DESC",
                                 ((series, lower, asof_d) if asof_d else (series, lower)))
            out["consensus"] = _hist(con, f"SELECT date, COUNT(*) FROM consensus_daily WHERE date >= ?{vd} GROUP BY date ORDER BY date DESC",
                                     vp)
            out["dart"] = _hist(con, f"SELECT rcept_dt, COUNT(*) FROM dart_events WHERE rcept_dt >= ?{' AND rcept_dt <= ?' if asof_d else ''} GROUP BY rcept_dt ORDER BY rcept_dt DESC", vp)
            out["uni_events"] = _hist(con, f"SELECT date, COUNT(*) FROM universe_events WHERE date >= ?{vd} GROUP BY date ORDER BY date DESC", vp)
        finally:
            con.close()
    except Exception:
        pass
    try:
        con = _ro(history_db)
        try:
            sql = "SELECT run_id, COUNT(*) FROM stage1_oversold WHERE run_id >= ?" + (" AND run_id <= ?" if asof_d else "") + " GROUP BY run_id ORDER BY run_id DESC"
            out["runs"] = _hist(con, sql, (lower, asof_d) if asof_d else (lower,))
            # 업종 분류 — 파일 날짜 + 최신 run 종목의 커버 비율
            try:
                last_run = (out.get("runs") or {}).get("last")
                if SECTOR_CACHE.exists() and last_run:
                    sec = json.loads(SECTOR_CACHE.read_text(encoding="utf-8"))
                    have = {str(k).zfill(6) for k, v in (sec or {}).items() if v and v != "미분류"}
                    ticks = {str(r[0]).zfill(6) for r in con.execute("SELECT DISTINCT ticker FROM stage1_oversold WHERE run_id = ?", (last_run,))}
                    mdate = datetime.fromtimestamp(SECTOR_CACHE.stat().st_mtime).strftime("%Y%m%d")
                    cov = (len(ticks & have) / len(ticks)) if ticks else None
                    out["sector"] = {"last": mdate, "n_last": len(have), "n_hist": [], "cover": cov}
            except Exception:
                pass
        finally:
            con.close()
    except Exception:
        pass
    try:
        con = _ro(earnings_db)
        try:
            sql = "SELECT substr(fetched_at,1,8) AS d, COUNT(*) FROM earnings_raw WHERE fetched_at >= ?" + (" AND fetched_at <= ?" if asof else "") + " GROUP BY d ORDER BY d DESC"
            out["earn_fetch"] = _hist(con, sql, (lower, asof) if asof else (lower,))
        finally:
            con.close()
    except Exception:
        pass
    return out, ref, cal


def run(asof=None):
    """수집 + 판정 → (rows, ref, warnings). ref 를 못 구하면 빈 결과(예외 없음)."""
    try:
        branches, ref, cal = collect(asof=asof)
        if not ref:
            return [], None, ["⚠️ 자료 없음: 시세 본표(기준일을 못 구함)"]
        rows = assess(branches, ref, cal)
        return rows, ref, warning_lines(rows, ref)
    except Exception as e:
        return [], None, [f"⚠️ 자료 점검표 실행 실패({e.__class__.__name__})"]


def telegram_lines(max_lines=4):
    """텔레그램에 실을 ⚠️ 줄(정상이면 빈 목록). 많으면 앞 max_lines 줄 + 'docs/data_health.md 참고'."""
    try:
        _, _, warns = run()
        if len(warns) > max_lines:
            warns = warns[:max_lines] + [f"⚠️ 자료 경고 {len(warns) - max_lines}건 더 — docs/data_health.md"]
        return warns
    except Exception:
        return []


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows, ref, warns = run()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        DOCS.mkdir(exist_ok=True)
        (DOCS / "data_health.json").write_text(json.dumps(
            {"generated": now, "ref_date": ref, "rows": rows, "warnings": warns}, ensure_ascii=False, indent=1), encoding="utf-8")
        if ref:
            (DOCS / "data_health.md").write_text(to_markdown(rows, ref, now), encoding="utf-8")
    except Exception as e:
        print(f"[data_health] docs 쓰기 실패: {e}")
    print(f"[data_health] 기준 시세 {ref} · 갈래 {len(rows)} · 경고 {len(warns)}")
    for r in rows:
        print(f"  {r['name']:<14} {r['last'] or '없음':<9} 지연 {('-' if r['lag'] is None else r['lag']):>2}(허용 {r['allowed']})  건수 {r['n_last']}/{r['n_med']}  {r['status']} {r['note']}")
    for w in warns:
        print("  " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
