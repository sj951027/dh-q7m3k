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
  - [E3 2026-10-30] 스위치 계좌 = 같은 규칙에 '그날 어느 목록을 쓰나'만 다름 → switch_picks() 로 목록을 미리 합쳐 simulate 에 넘긴다.
  - [2판 2026-10-30] 상폐 감도: gone(ticker → 시세가 끊긴 첫 날) + gone_ret 를 주면, 그날부터 그 종목은
    '마지막 유효 종가 × (1 + gone_ret)' 로 평가·청산한다(기본 None = 1판과 완전히 같은 경로). 사라진 종목 판별은 gone_dates().
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
GONE_RET = -0.90       # 상폐 감도: 시세가 끊긴 종목을 마지막 가격 대비 −90% 로 치는 경우(worklog 2026-10-23 '상폐 −90% 민감도')


def last_px(arr, col, i):
    """i 이하 마지막 유효 종가(없으면 NaN)."""
    j = i
    while j >= 0:
        v = arr[j, col]
        if v == v and v > 0:
            return float(v)
        j -= 1
    return float("nan")


def gone_dates(close):
    """종가 표(index=날짜 오름차순, columns=ticker) → {ticker: 시세가 끊긴 첫 날짜}.
    '끊김' = 마지막 유효 종가 날짜가 표의 마지막 날짜보다 앞섬(그 뒤로 끝까지 시세 없음 = 상장폐지 또는 목록에서 사라짐).
    끝 하루이틀만 비는 종목도 들어간다(감도이므로 보수적으로). 순수 함수."""
    valid = close.notna() & (close > 0)
    dates = list(close.index)
    if not dates:
        return {}
    last_i = len(dates) - 1
    out = {}
    for tk, col in valid.items():
        idx = np.flatnonzero(col.to_numpy())
        if len(idx) and idx[-1] < last_i:
            out[str(tk)] = str(dates[idx[-1] + 1])
    return out


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


def switch_picks(dates, cells, picks_a, picks_other, a_cells=("A",)):
    """[E3 스위치] 날짜별 칸으로 두 목록 중 하나만 고른다 → (picks, info).
    cells: Series/dict(date → 'A'~'D' 또는 NaN). 칸이 a_cells 면 picks_a[그날], 그 밖(칸 없음 포함)은 picks_other[그날].
    고른 쪽 목록이 그날 없으면 그날 신규 없음(현금) → days_missing. info: days_A·days_other·days_missing·source{date: 'A'|'other'}. 순수 함수."""
    out, src = {}, {}
    n_a = n_o = n_m = 0
    for d in dates:
        d = str(d)
        c = cells.get(d) if cells is not None else None
        use_a = c in a_cells
        pk = (picks_a if use_a else picks_other).get(d)
        if pk is None:
            n_m += 1
            continue
        out[d] = list(pk); src[d] = "A" if use_a else "other"
        if use_a:
            n_a += 1
        else:
            n_o += 1
    return out, dict(days_A=n_a, days_other=n_o, days_missing=n_m, source=src)


def tradable_mask(susp, chg, limit_up):
    """정지 표·등락률 표 → 진입 가능(bool) 표. 두 표의 열을 합집합으로 맞춘 뒤 비교한다 — 등락률이 전부 비어 열이 빠진 종목(상장 첫날 등)이
    있으면 `|` 뒤에 float 열이 생겨 `~` 가 TypeError 로 죽는다(2026-10-30 배치 실측). 빈 값은 '정지 아님·상한가 아님' 으로 읽는다."""
    cols = susp.columns.union(chg.columns)
    susp = susp.reindex(columns=cols).fillna(0)
    chg = chg.reindex(columns=cols)
    return ~((susp > 0) | (chg >= limit_up)).fillna(False).astype(bool)


def simulate(dates, close, picks, *, slots=SLOTS, hold=HOLD, cost=COST_MAIN, new_ratio=None, entry_lag=ENTRY_LAG, start_nav=1.0, tradable=None,
             gone=None, gone_ret=GONE_RET):
    """dates: 거래일 목록(오름차순, str) · close: DataFrame(index=dates, columns=ticker) · picks: {추천일: [ticker]} ·
    new_ratio: {추천일: 0~1} 또는 None(=1) 또는 float(상수). tradable: DataFrame(bool, index=dates, columns=ticker) — False 면 그날 진입 불가(정지·상한가) → 현금.
    gone: {ticker: 시세가 끊긴 첫 날짜} 또는 None. 주면 그날부터 그 종목은 마지막 유효 종가 × (1 + gone_ret) 로 평가·청산(상폐 감도).
    반환: (nav DataFrame[date, nav, cash, n_pos, invested, ret_1d, entries, exits], slots list[dict])."""
    dates = [str(d) for d in dates]
    didx = {d: i for i, d in enumerate(dates)}
    close = close.reindex(dates)
    cols = {t: k for k, t in enumerate(close.columns)}
    arr = close.to_numpy(dtype=float)
    trd = tradable.reindex(index=dates, columns=close.columns).fillna(True).to_numpy(dtype=bool) if tradable is not None else None
    N = len(dates)
    half = cost / 2.0
    gone_i = {}
    if gone:
        for tk, d in gone.items():
            c = cols.get(str(tk))
            if c is None:
                continue
            d = str(d)
            if d in didx:
                gone_i[c] = didx[d]
            elif d > dates[-1]:
                continue                                        # 표 끝 뒤에 끊김 → 이 구간에선 살아 있음
            else:
                gone_i[c] = sum(1 for x in dates if x < d)     # 구간 시작 전에 끊김 → 0, 그 밖은 첫 날짜 이상
    gone_mult = 1.0 + gone_ret

    def mark_px(col, i):
        """평가·청산 가격: 마지막 유효 종가, 끊긴 종목은 × (1 + gone_ret)."""
        px = last_px(arr, col, i)
        g = gone_i.get(col)
        if g is not None and i >= g and px == px:
            px *= gone_mult
        return px

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
                px = mark_px(p["col"], i)
                proceeds = p["shares"] * px * (1.0 - half)
                cash += proceeds
                p.update(exit_date=dates[i], exit_px=px, proceeds=proceeds, status="closed",
                         ret=(px * (1.0 - half)) / (p["entry_px"] / (1.0 - half)) - 1.0,
                         gone=bool(gone_i.get(p["col"]) is not None and i >= gone_i[p["col"]]))
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
                if trd is not None and not trd[i, c]:
                    continue                                # 거래정지·상한가 → 현금(대체 없음)
                shares = per * (1.0 - half) / px
                cash -= per
                open_pos.append(dict(ticker=tk, col=c, shares=shares, entry_i=i, entry_date=dates[i], exit_i=i + hold,
                                     entry_px=px, invested=per, run=rid, status="open"))
                n_entry += 1
        # ③ 평가
        val = 0.0
        for p in open_pos:
            px = mark_px(p["col"], i)
            val += p["shares"] * (px if px == px else 0.0)
        nav = cash + val
        rows.append(dict(date=dates[i], nav=nav, cash=cash, n_pos=len(open_pos), invested=val,
                         ret_1d=(nav / prev_nav - 1.0) if prev_nav > 0 else float("nan"), entries=n_entry, exits=n_exit))
        prev_nav = nav
    for p in open_pos:                                   # 끝에 열린 것(평가만)
        px = mark_px(p["col"], N - 1)
        p.update(exit_date=None, exit_px=px, status="open", gone=bool(gone_i.get(p["col"]) is not None and N - 1 >= gone_i[p["col"]]))
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
