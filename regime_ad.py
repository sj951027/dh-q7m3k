# -*- coding: utf-8 -*-
"""A~D 진입 국면 — 표시 전용 (2026-10-20)

지수(코스피·코스닥 각각)의 **20거래일 수익(R20)** 으로 장을 넷으로 나눈다:
  A 급락 뒤 (R20 ≤ −5%) · B 약세 (−5% < R20 ≤ 0) · C 강세 (0 < R20 ≤ +5%) · D 급등 뒤 (R20 > +5%)
'며칠째' = 같은 칸이 이어진 거래일 수(들어온 날 = 1일째).

근거(관측 — 규칙 아님): research/RESEARCH_entry_regime_20261020.md · RESEARCH_entry_regime_deep_20261020.md ·
  Codex 독립 재현 research/handoff/REPLY_20261020_entry_regime_blind.md (코스피 A 뒤 40일 +6.78%, 사건 9/9 플러스 — 일치).
문턱 −5/+5 는 두 연구가 결과를 보기 전에 정한 관례값이고 여기서는 **표시 칸 이름**으로만 쓴다.
점수·판정·게이트에 넣지 않는다. 소비자: build_dashboard(docs/data.json 'regime_ad') · notify_telegram(시장국면 줄) ·
  build_scoreboard(국면별 기록 A~D 병기) · PTW(data.json 읽기). 읽기는 ohlcv.db mode=ro 만.
"""
import os
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))

LOOKBACK = 20          # 거래일
TH_DOWN = -0.05        # A: R20 ≤ −5%
TH_UP = 0.05           # D: R20 > +5%
CELLS = {"A": "급락 뒤", "B": "약세", "C": "강세", "D": "급등 뒤"}
ORDER = ("A", "B", "C", "D")
SERIES = {"kospi": "KOSPI", "kosdaq": "KOSDAQ"}   # market_daily.series
NAMES = {"kospi": "코스피", "kosdaq": "코스닥"}


def cell_of(r20):
    """R20(소수, 예 −0.13) → 'A'~'D'. NaN/None 은 None. 경계: −5% 는 A, 0 은 B, +5% 는 C."""
    if r20 is None:
        return None
    try:
        x = float(r20)
    except (TypeError, ValueError):
        return None
    if x != x:   # NaN
        return None
    if x <= TH_DOWN:
        return "A"
    if x <= 0:
        return "B"
    if x <= TH_UP:
        return "C"
    return "D"


def classify(close):
    """지수 종가(날짜 오름차순 index) → DataFrame[r20, cell, days]. 처음 20일은 cell None·days None.
    days = 같은 칸이 이어진 일수(칸이 바뀌면 1부터)."""
    c = pd.Series(close).astype(float)
    r20 = c / c.shift(LOOKBACK) - 1
    cell = [cell_of(v) for v in r20]
    days, prev, run = [], None, 0
    for v in cell:
        if v is None:
            prev, run = None, 0
            days.append(None)
            continue
        run = run + 1 if v == prev else 1
        prev = v
        days.append(run)
    return pd.DataFrame({"r20": r20.values, "cell": cell, "days": days}, index=c.index)


POS_WINDOW = 750     # 거래일(≈3년)
POS_MIN = 250        # 이보다 짧으면 점수 없음


def pos10_of(r20_values):
    """R20 수열(오름차순 날짜, 마지막이 오늘) → 0~10 '자리 점수'. 지난 POS_WINDOW 안에서 오늘보다 큰 날의 비율 × 10
    (가장 많이 빠진 날 = 10, 가장 많이 오른 날 = 0). 유효값이 POS_MIN 미만이면 None. 좋다/나쁘다가 아니라 위치다."""
    try:
        v = [float(x) for x in list(r20_values)[-POS_WINDOW:]]
    except Exception:
        return None
    v = [x for x in v if x == x]
    if len(v) < POS_MIN or v[-1] != v[-1]:
        return None
    today = v[-1]
    return round(10.0 * sum(1 for x in v if x > today) / len(v), 1)


def load_index(series, ohlcv_db=DEFAULT_DB, asof=None):
    """market_daily 에서 지수 종가(index 'YYYYMMDD' 문자열, 오름차순). 읽기 전용."""
    con = sqlite3.connect(f"file:{ohlcv_db}?mode=ro", uri=True)
    try:
        df = pd.read_sql("SELECT date, close FROM market_daily WHERE series=? ORDER BY date", con, params=(series,))
    finally:
        con.close()
    df["date"] = df["date"].astype(str).str.replace("-", "", regex=False)
    if asof:
        df = df[df["date"] <= str(asof)]
    return df.set_index("date")["close"].astype(float)


def now(ohlcv_db=DEFAULT_DB, asof=None):
    """지금(또는 asof 까지) 두 지수의 칸 — {'kospi': {date, r20_pct, cell, label, days}, 'kosdaq': {...}}.
    못 구한 시장은 빠진다(예외를 밖으로 내지 않음)."""
    out = {}
    for k, s in SERIES.items():
        try:
            df = classify(load_index(s, ohlcv_db, asof))
            df = df[df["cell"].notna()]
            if not len(df):
                continue
            last = df.iloc[-1]
            out[k] = {"date": str(df.index[-1]), "r20_pct": round(float(last["r20"]) * 100, 1),
                      "cell": str(last["cell"]), "label": CELLS[str(last["cell"])], "days": int(last["days"]),
                      "pos10": pos10_of(df["r20"].values)}   # [2026-10-20 밤] 0~10 자리 점수(표시 전용)
        except Exception:
            continue
    return out


def cell_series(dates, ohlcv_db=DEFAULT_DB):
    """날짜 목록에 맞춘 칸 문자('A'~'D') Series 를 시장별로 — {'kospi': Series, 'kosdaq': Series}. 실패한 시장은 빠진다."""
    out = {}
    for k, s in SERIES.items():
        try:
            df = classify(load_index(s, ohlcv_db))
            out[k] = df["cell"].reindex([str(d) for d in dates])
        except Exception:
            continue
    return out


def history(ohlcv_db=DEFAULT_DB):
    """[2026-10-21] 거래일별 시장 상황 이력 — {date: {'kospi': {r20_pct, cell, cell6, label, days, pos10}, 'kosdaq': {...}}}.
    매 날짜의 값은 **그날까지의 지수 자료만** 쓴다(pos10 은 지난 750거래일 안 위치). PTW 가 매수 거래일의 전 거래일 행을 찾아 쓴다.
    기준이 바뀌면 이 함수만 고치면 과거 전부가 새 기준으로 다시 나온다(값을 저장하지 않고 원자료에서 매번 계산)."""
    try:
        import buy_context as bc
        c6 = bc.cell6
    except Exception:
        c6 = lambda x: None
    out = {}
    for k, s in SERIES.items():
        try:
            df = classify(load_index(s, ohlcv_db))
        except Exception:
            continue
        r = df["r20"].to_numpy(dtype=float)
        for i, (d, row) in enumerate(df.iterrows()):
            if row["cell"] is None:
                continue
            w = r[max(0, i - POS_WINDOW + 1):i + 1]; w = w[w == w]
            pos = round(10.0 * float((w > r[i]).sum()) / len(w), 1) if (len(w) >= POS_MIN and r[i] == r[i]) else None
            pct = round(float(r[i]) * 100, 1)
            out.setdefault(str(d), {})[k] = {"r20_pct": pct, "cell": str(row["cell"]), "cell6": c6(pct), "label": CELLS[str(row["cell"])],
                                             "days": int(row["days"]), "pos10": pos}
    return out


def describe(v):
    """한 시장 dict → '-13.0% 급락 뒤 8일째'. 깨진 입력은 None."""
    try:
        return f"{float(v['r20_pct']):+.1f}% {v['label']} {int(v['days'])}일째"
    except Exception:
        return None


def line(info):
    """'코스피 -13.0% 급락 뒤 8일째 · 코스닥 -0.4% 약세 3일째'. 둘 다 없으면 None."""
    parts = []
    for k in ("kospi", "kosdaq"):
        s = describe((info or {}).get(k))
        if s:
            parts.append(f"{NAMES[k]} {s}")
    return " · ".join(parts) or None


if __name__ == "__main__":
    import json
    print(json.dumps(now(), ensure_ascii=False, indent=1))
    print(line(now()))
