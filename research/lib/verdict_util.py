# -*- coding: utf-8 -*-
"""verdict_util.py — 판정 도구들이 같이 쓰는 작은 순수 함수(자리바꿈의 층 나누기). 2026-11-16.

왜 여기: 각주 ④의 '시총 5분위 안에서만 섞는 감도'를 v32a·lv_e 2차 창 도구가 둘 다 쓴다 — 복사하지 않고 한 곳에 둔다(CLAUDE.md 불변 규칙).
정의 출처: `research/handoff/REPLY_20261012_placebo_null.md` — "시장 × 창 안 첫 유효 close×shares 의 5분위 안에서만 섞음. 시총 결측은 별도 6번째 층.
          이름표가 그대로인 경우도 허용하는 일반 순열."
검사: `tests/test_v32a_verdict_rules.py` 7번(1:1 · 같은 층 안 · 결측 6번째 층).
"""
import numpy as np
import pandas as pd


def strata_perm(names, strata, rng):
    """같은 층(strata 값이 같은 것끼리) 안에서 이름표를 1:1 로 뒤섞은 {종목: 종목'}. 제자리도 허용하는 일반 순열."""
    out = {}
    names = np.asarray(names); strata = np.asarray(strata)
    for s in sorted(set(strata.tolist())):
        grp = names[strata == s]
        out.update(dict(zip(grp.tolist(), rng.permutation(grp).tolist())))
    return out


def cap_quintiles(tickers, cap):
    """시총 5분위(1~5), 결측은 6번째 층. cap = {종목: 창 안 첫 유효 close×shares}. 순위 동률은 종목코드 순."""
    s = pd.Series({t: cap.get(t, np.nan) for t in sorted(tickers)}, dtype=float)
    q = pd.Series(6, index=s.index, dtype=int)
    v = s.dropna()
    if len(v) >= 5:
        q.loc[v.index] = (pd.qcut(v.rank(method="first"), 5, labels=False) + 1).astype(int)
    return q


def first_cap(sh, start_date):
    """sh(date, ticker, close, shares) → {종목: start_date 이후 첫 유효(> 0) close×shares}."""
    z = sh[sh.date.astype(str) >= str(start_date)].copy()
    z["cap"] = z.close * z.shares
    return z[z.cap > 0].sort_values("date").groupby("ticker").cap.first().to_dict()
