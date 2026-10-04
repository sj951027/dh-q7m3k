# -*- coding: utf-8 -*-
"""w20lib — target20 넓게 보기 공용. 읽기 전용. Codex Study(패널·가드·후보)를 그대로 불러 쓴다(비교 가능하도록).
규약은 PLAN.md. 목록일 t → t+1 시가 진입, 20봉(진입일 포함) 보유, 왕복 비용 0.5%."""
import sys, importlib.util, warnings
from pathlib import Path
import numpy as np, pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
_spec = importlib.util.spec_from_file_location("cx", ROOT / "research/handoff/code_target20_20261003.py")
cx = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(cx)
COST = 0.005; H = 20; TAIL = 26
RULES3 = {"control_amount": "거래대금 상위10", "highbeta_high": "고베타+고점 근접", "control_price4": "가격4요소"}
rolling, returns, lag, rank = cx.rolling, cx.returns, cx.lag, cx.rank


def study(choose=True):
    s = cx.Study(); s.features()
    if choose: s.choose()
    s.t0 = int(s.start); s.t1 = s.T - TAIL          # 목록일 범위 [t0, t1)
    s.year = np.array([d[:4] for d in s.d])
    return s


def entry_ok(s, t):
    """t+1 시가 체결 가능(Codex paths 와 같은 조건)."""
    base = s.o[t + 1]
    locked = (np.abs(s.h[t + 1] - s.l[t + 1]) < 1e-8) & (np.abs(base / s.c[t] - 1) >= .295)
    return np.isfinite(base) & (base > 0) & (s.v[t + 1] > 0) & ~locked


def fwd_metrics(s, h=H):
    """시가 진입·h봉 보유의 (T,N) 결과: term(비용 후 종료 수익) · hit · touch(5~h봉 종가 닿음) · mae(종가 최저) · first_up · frac(매수가 위 비율) · joint."""
    T, N = s.T, s.N
    out = {k: np.full((T, N), np.nan) for k in ("term", "hit", "touch", "mae", "first_up", "frac", "joint")}
    for t in range(s.t0, min(s.t1, T - h - 1)):
        f = entry_ok(s, t); base = np.where(f, s.o[t + 1], np.nan)
        val = s.ff[t + 1:t + 1 + h] / base - 1
        term = val[-1] - COST; mae = np.nanmin(val, axis=0); frac = (val > 0).mean(axis=0)
        hit = term >= .20; touch = (np.nanmax(val[4:], axis=0) - COST) >= .20; fu = val[0] > 0
        joint = hit & (mae >= -.10) & (frac >= .8) & fu
        for k, a in (("term", term), ("hit", hit), ("touch", touch), ("mae", mae), ("first_up", fu), ("frac", frac), ("joint", joint)):
            out[k][t] = np.where(f, a.astype(float), np.nan)
    return out


def block_ci(v, h=20, k=2000, seed=20261004):
    v = np.asarray(v, float); v = v[np.isfinite(v)]; n = len(v)
    if n <= h: return (np.nan, np.nan)
    st = np.random.default_rng(seed).integers(0, n - h + 1, (k, int(np.ceil(n / h))))
    idx = (st[:, :, None] + np.arange(h)).reshape(k, -1)[:, :n]
    return tuple(np.quantile(v[idx].mean(axis=1), [.025, .975]))


def fmt_ci(v, h=20):
    lo, hi = block_ci(v, h); return f"{np.nanmean(v):+.2f} [{lo:+.2f}, {hi:+.2f}]"
