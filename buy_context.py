# -*- coding: utf-8 -*-
"""'이만큼 빠졌던 때 과거엔 어땠나' — 표시 전용 (2026-10-20 밤 초안, 임시 폴더)

지수 20거래일 수익(R20)을 여섯 칸으로 나누고(A~D 를 깊이로 두 번 더 쪼갬), 칸마다 **40일이 끝난 과거 날들**의
전 종목 바구니 수익(다음날 종가 매수 → 40거래일 뒤 종가)을 모아 숫자만 보여 준다. 규칙·신호 아님. 과거형으로만 쓴다.

칸(문턱 ±5·±10 은 A~D 와 같은 관례값 — 결과를 보고 고른 것이 아님):
  A2 ≤ −10%  "3년 중 가장 많이 빠진 축"   A1 (−10, −5]  "크게 빠진 편"
  B  (−5, 0]  "보통 수준의 약세"            C  (0, +5]    "보통 수준의 강세"
  D1 (+5, +10] "많이 오른 편"               D2 > +10%     "3년 중 가장 많이 오른 축"
'사건' = 같은 칸의 날을 시간순으로 보며 직전 사건과 40거래일 이상 떨어진 날만 센 것(독립을 보장하진 않음).
'더 빠진 뒤 올랐음' = 사건의 신호일 종가 대비 20거래일 안에 지수가 5% 더 내려갔는데 40일 뒤 바구니는 플러스.
"""
import math

import numpy as np
import pandas as pd

CELLS6 = (("A2", -10.0, "3년 중 가장 많이 빠진 축"), ("A1", -5.0, "크게 빠진 편"), ("B", 0.0, "보통 수준의 약세"),
          ("C", 5.0, "보통 수준의 강세"), ("D1", 10.0, "많이 오른 편"), ("D2", math.inf, "3년 중 가장 많이 오른 축"))
LABEL6 = {k: lab for k, _, lab in CELLS6}
NAMES = {"kospi": "코스피", "kosdaq": "코스닥"}
MIN_EVENTS = 5       # 이보다 적으면 '표본 부족'
HOLD = 40
FURTHER_DROP = -0.05  # 신호일 종가 대비 20일 안 −5%
FURTHER_WIN = 20


def cell6(r20_pct):
    """R20(%) → 'A2'…'D2'. NaN/None → None. 경계는 아래 칸(−10 은 A2, −5 는 A1, 0 은 B, +5 는 C, +10 은 D1)."""
    try:
        x = float(r20_pct)
    except (TypeError, ValueError):
        return None
    if x != x:
        return None
    for k, hi, _ in CELLS6:
        if x <= hi:
            return k
    return "D2"


def stats(dates, r20_pct, basket_r40, idx_close):
    """dates: 거래일 목록 · r20_pct: Series(date→R20 %) · basket_r40: Series(date→신호일 기준 40일 바구니 수익 %, 미완결 NaN)
    · idx_close: Series(date→지수 종가). 반환 {cell: {n_days, n_events, mean, events_pos, events_n, further_then_up, further_n, worst_event}}.
    40일이 끝난 날만 쓴다(미완결 제외). 순수 함수."""
    dates = [str(d) for d in dates]
    r20 = pd.Series(r20_pct).reindex(dates).astype(float)
    b40 = pd.Series(basket_r40).reindex(dates).astype(float)
    ic = pd.Series(idx_close).reindex(dates).astype(float).to_numpy()
    cells = [cell6(v) for v in r20]
    out = {}
    N = len(dates)
    groups = [(k, (k,)) for k, _, _ in CELLS6] + [("A", ("A2", "A1")), ("D", ("D1", "D2"))]   # 부모 칸 A(≤−5%)·D(>+5%)도 함께
    for k, members in groups:
        days = [i for i in range(N) if cells[i] in members and b40.iloc[i] == b40.iloc[i]]
        if not days:
            continue
        ev, last = [], -10 ** 9
        for i in days:
            if i - last >= HOLD:
                ev.append(i); last = i
        rets_all = b40.iloc[days].to_numpy()
        ev_rets = b40.iloc[ev].to_numpy()
        further, further_up = 0, 0
        for i in ev:
            seg = ic[i + 1:i + 1 + FURTHER_WIN]
            if len(seg) and ic[i] == ic[i] and np.nanmin(seg) / ic[i] - 1 <= FURTHER_DROP:
                further += 1
                if b40.iloc[i] > 0:
                    further_up += 1
        out[k] = dict(n_days=int(len(days)), n_events=int(len(ev)),
                      mean=float(np.nanmean(ev_rets)) if len(ev_rets) else None,    # [검토 P2-2] 문장의 "N번 → 평균"과 같은 모수(사건 평균)
                      mean_days=float(np.nanmean(rets_all)),                          # 참고: 겹치는 전 날짜 평균
                      events_pos=int((ev_rets > 0).sum()), events_n=int(len(ev_rets)),
                      further_n=int(further), further_then_up=int(further_up),
                      worst_event=float(np.nanmin(ev_rets)) if len(ev_rets) else None,
                      first=dates[days[0]], last=dates[days[-1]])
    return out


def _sign(x):
    return f"{x:+.0f}%" if abs(x) >= 0.95 else f"{x:+.1f}%"


PARENT = {"A2": "A", "A1": "A", "D1": "D", "D2": "D"}
PARENT_WHEN = {"A": "5% 넘게 빠졌던 때", "D": "5% 넘게 올랐던 때"}


def pick(stats_mkt, k):
    """칸 k 의 통계. 사건이 MIN_EVENTS 미만이면 부모 칸(A·D)으로 대체 — (통계, 쓴 칸) 반환."""
    st = (stats_mkt or {}).get(k)
    if st and st.get("events_n", 0) >= MIN_EVENTS:
        return st, k
    pk = PARENT.get(k)
    pst = (stats_mkt or {}).get(pk) if pk else None
    if pst and pst.get("events_n", 0) >= MIN_EVENTS:
        return pst, pk
    return st, k


def lines(mkt, r20_pct, st, years="3년", used=None, pos10=None):
    """한 시장의 세 줄(사용자 확정 형식 2026-10-20). st = stats()[cell]. 표본 부족이면 두 줄.
    예)
    🧭 코스피 -17.3% (3년 중 가장 많이 빠진 축)
       이만큼 빠졌던 때 3년간 6번 → 다음날 사서 40일 뒤 평균 +12%, 6번 중 5번 플러스
       단 6번 중 2번은 사고 나서 더 떨어진 뒤 올랐음
    """
    k = cell6(r20_pct)
    if k is None:
        return None
    nm = NAMES.get(mkt, mkt)
    score = ""
    try:
        if pos10 is not None and math.isfinite(float(pos10)):
            score = f"{float(pos10):.1f}/10 · "          # 0~10 자리 점수(10 = 3년 중 가장 많이 빠진 쪽) — 좋다/나쁘다가 아니라 위치
    except (TypeError, ValueError):
        score = ""
    head = f"🧭 {nm} {score}{float(r20_pct):+.1f}% ({LABEL6[k]} · 시장 전체 기준)"   # [사용자 결정 10/20] v30 아님을 분명히
    if not st:
        return [head, "   과거 기록 아직 없음"]                      # 통계 자체가 없을 때(배선 전·계산 실패)
    if st.get("events_n", 0) < MIN_EVENTS:
        n = st.get("events_n", 0)
        return [head, f"   비슷했던 때가 {years}간 {n}번뿐 → 과거 성적은 표본 부족"]
    n, pos, mean = st["events_n"], st["events_pos"], st["mean"]
    if used in PARENT_WHEN:                                   # 부모 칸으로 대체된 경우 말도 넓힌다
        when = PARENT_WHEN[used]
    else:
        when = "이만큼 빠졌던 때" if k in ("A2", "A1") else ("이만큼 올랐던 때" if k in ("D1", "D2") else "이 정도일 때")
    second = f"   {when} {years}간 {n}번 → 다음날 사서 40일 뒤 평균 {_sign(mean)}, {n}번 중 {pos}번 플러스"
    out = [head, second]
    if pos / n < 0.5:                                         # 과반이 손해였을 때만(평균만 마이너스면 숫자가 말하게 둔다)
        out[-1] += " → 과거엔 좋은 자리 아니었음"
    if st.get("further_n", 0):
        fu, fn = st["further_then_up"], st["further_n"]
        if fu == fn:
            out.append(f"   단 {n}번 중 {fn}번은 사고 나서 더 떨어진 뒤 올랐음")
        else:
            out.append(f"   단 {n}번 중 {fn}번은 사고 나서 더 떨어졌고 그중 {fu}번만 40일 뒤 플러스")
    return out


def block(info_ad, stats_by_mkt, years="3년"):
    """두 시장 묶음 → 줄 목록(텔레그램용). info_ad = regime_ad.now() 꼴({'kospi': {'r20_pct': …}, …}). years = 자료 길이 말("3년")."""
    out = []
    for mkt in ("kospi", "kosdaq"):
        v = (info_ad or {}).get(mkt)
        if not v or v.get("r20_pct") is None:
            continue
        k = cell6(v["r20_pct"])
        st, used = pick((stats_by_mkt or {}).get(mkt, {}), k) if k else (None, None)
        ls = lines(mkt, v["r20_pct"], st, years=years, used=used, pos10=v.get("pos10"))
        if ls:
            out += ls
    return out
