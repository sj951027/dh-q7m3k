# -*- coding: utf-8 -*-
"""모의 계좌(현금 포함) 순수 엔진 — 설계 `research/PAPER_ACCOUNT_DESIGN_20261018.md` §2·§8 (2026-10-20 밤, 임시 폴더 초안)

DB 를 열지 않는다. 입력은 전부 인자(날짜·종가 표·날짜별 바구니·신규 비율). 배선(history.db 점수 → 바구니, 비교군 B0~B3,
paper_account.db 적재, docs/paper_account.json)은 `paper_account.py` 가 맡는다(다음 세션).

규칙(§2 그대로):
  - 시작 자본 1. 슬롯 40 = 매 거래일 '전날 종가 NAV / 40 × 신규 비율' 을 그날 바구니에 투입(현금이 모자라면 현금만큼).
  - 바구니 = 추천일 t 의 종목 목록(시장별 상위 10, 희석 제외는 호출자가 미리). 진입 = t+ENTRY_LAG 종가, 종목당 돈 = 슬롯 돈 / 목록 길이.
    진입일 가격 없음 → 그 몫은 현금(대체 없음).
  - 청산 = 진입 HOLD 거래일 뒤 종가. 가격 없음(정지·상폐) → 마지막 유효 종가. 중간 매도 없음.
  - 비용 = 왕복 cost 를 진입 때 절반, 청산 때 절반 차감.
  - 평가 = 매일 종가(없으면 마지막 유효 종가). NAV = 현금 + 보유 평가.
  - 게이트 계좌 = 같은 규칙에 new_ratio(날짜 → 0~1)만 다름. 상시 비중 축소 계좌 = new_ratio 가 상수 q.
"""
import math
import numbers

import numpy as np
import pandas as pd

SLOTS = 40
HOLD = 40
ENTRY_LAG = 1
COST_MAIN = 0.005      # 왕복 0.5% (주)
COST_ALT = 0.0035      # 왕복 0.35% (병기)


def last_px(arr, col, i):
    """i 이하 마지막 유효 종가(없으면 NaN)."""
    j = i
    while j >= 0:
        v = arr[j, col]
        if v == v and v > 0:
            return float(v)
        j -= 1
    return float("nan")


def picks_from_scores(S, top=10, exclude=None):
    """DataFrame(run_id, market, ticker, score) → {run_id: [ticker, …]} (시장별 상위 top, 제외 집합 뺀 뒤). 순수 함수."""
    exclude = set(exclude or ())
    out = {}
    for rid, g in S.dropna(subset=["score"]).groupby("run_id"):
        lst = []
        for _, gm in g[~g["ticker"].isin(exclude)].groupby("market"):
            lst += list(gm.sort_values(["score", "ticker"], ascending=[False, True])["ticker"].head(top))
        out[str(rid)] = lst
    return out


def ratio_by_cell(cells, zero_cells=("D",), half_cells=()):
    """칸 Series(date → 'A'~'D' 또는 NaN) → {date: 신규 비율}. zero_cells 는 0, half_cells 는 0.5, 그 밖(칸 없음 포함)은 1."""
    out = {}
    for d, c in cells.items():
        if c in zero_cells:
            out[str(d)] = 0.0
        elif c in half_cells:
            out[str(d)] = 0.5
        else:
            out[str(d)] = 1.0
    return out


def simulate(dates, close, picks, *, slots=SLOTS, hold=HOLD, cost=COST_MAIN, new_ratio=None, entry_lag=ENTRY_LAG, start_nav=1.0):
    """dates: 거래일 목록(오름차순, str) · close: DataFrame(index=dates, columns=ticker) · picks: {추천일: [ticker]} ·
    new_ratio: {추천일: 0~1} 또는 None(=1) 또는 float(상수).
    반환: (nav DataFrame[date, nav, cash, n_pos, invested, ret_1d, entries, exits], slots list[dict])."""
    dates = [str(d) for d in dates]
    didx = {d: i for i, d in enumerate(dates)}
    close = close.reindex(dates)
    cols = {t: k for k, t in enumerate(close.columns)}
    arr = close.to_numpy(dtype=float)
    N = len(dates)
    half = cost / 2.0

    def ratio_of(d):
        if new_ratio is None:
            return 1.0
        if isinstance(new_ratio, numbers.Real):      # np.float64·np.int64 포함
            return float(new_ratio)
        return float(new_ratio.get(d, 1.0))

    # 진입 예정: 진입 인덱스 e → [(추천일, ticker 목록, 비율)]
    sched = {}
    for rid, lst in picks.items():
        t = didx.get(str(rid))
        if t is None:
            continue
        e = t + entry_lag
        if e < N:
            sched.setdefault(e, []).append((str(rid), list(lst), ratio_of(str(rid))))

    cash = float(start_nav)
    open_pos = []      # dict(ticker, col, shares, entry_i, exit_i, entry_px, run)
    ledger = []
    rows = []
    prev_nav = float(start_nav)
    for i in range(N):
        n_exit = 0
        # ① 청산(만기 = i)
        still = []
        for p in open_pos:
            if p["exit_i"] == i:
                px = last_px(arr, p["col"], i)
                proceeds = p["shares"] * px * (1.0 - half)
                cash += proceeds
                p.update(exit_date=dates[i], exit_px=px, proceeds=proceeds, status="closed",
                         ret=(px * (1.0 - half)) / (p["entry_px"] / (1.0 - half)) - 1.0)
                ledger.append(p)
                n_exit += 1
            else:
                still.append(p)
        open_pos = still
        # ② 진입(예정 = i) — 슬롯 돈 = 전날 NAV/slots × 비율, 현금 한도
        n_entry = 0
        for rid, lst, ratio in sched.get(i, []):
            budget = min(cash, prev_nav / slots * ratio) if ratio > 0 else 0.0
            if budget <= 0 or not lst:
                continue
            per = budget / len(lst)
            for tk in lst:
                c = cols.get(tk)
                if c is None:
                    continue                                # 시세표에 없음 → 현금
                px = arr[i, c]
                if not (px == px and px > 0):
                    continue                                # 진입일 가격 없음 → 현금(대체 없음)
                shares = per * (1.0 - half) / px
                cash -= per
                open_pos.append(dict(ticker=tk, col=c, shares=shares, entry_i=i, entry_date=dates[i], exit_i=i + hold,
                                     entry_px=px, invested=per, run=rid, status="open"))
                n_entry += 1
        # ③ 평가
        val = 0.0
        for p in open_pos:
            px = last_px(arr, p["col"], i)
            val += p["shares"] * (px if px == px else 0.0)
        nav = cash + val
        rows.append(dict(date=dates[i], nav=nav, cash=cash, n_pos=len(open_pos), invested=val,
                         ret_1d=(nav / prev_nav - 1.0) if prev_nav > 0 else float("nan"), entries=n_entry, exits=n_exit))
        prev_nav = nav
    for p in open_pos:                                   # 끝에 열린 것(평가만)
        px = last_px(arr, p["col"], N - 1)
        p.update(exit_date=None, exit_px=px, status="open")
        ledger.append(p)
    return pd.DataFrame(rows), ledger


def summarize(nav):
    """NAV 표 → 누적 수익(%), 최대낙폭(%), 평균 현금 비중(%), 일수. 라벨 없음(숫자만)."""
    if nav is None or not len(nav):
        return None
    v = nav["nav"].to_numpy(float)
    peak = np.maximum.accumulate(v)
    dd = (v / peak - 1.0).min() * 100.0
    return dict(days=int(len(v)), total_ret=float((v[-1] / v[0] - 1.0) * 100.0), mdd=float(dd),
                cash_share=float((nav["cash"] / nav["nav"]).mean() * 100.0), last=nav["date"].iloc[-1])
