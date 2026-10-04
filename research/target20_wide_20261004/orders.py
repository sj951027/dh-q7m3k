# -*- coding: utf-8 -*-
"""orders — 일봉 고가·저가로 흉내 내는 진입·청산 주문(벡터). PLAN.md E2·E3 규약. 실제 호가·체결 재현 아님.
signals: (t 목록일 index, k 종목 index) 배열. 진입 → (e 진입봉, p 진입가). 청산은 진입 다음 봉부터, 20봉째 종가가 만기."""
import numpy as np, pandas as pd
from w20lib import COST, H

W = H + 6   # 만기 뒤 매도 지연 5봉 여유
ENTRIES = {"open": "다음날 시가", "stop1": "돌파 매수(목록일 고가 위·1일)", "stop3": "돌파 매수(3일 유효)", "limit3": "눌림 지정가(종가−3%·1일)", "close_up": "다음날 양봉 확인·종가 매수"}
EXITS = {"hold": "20봉 보유", "tp": "지정가 +20%", "tp_stop": "+20% 지정가·장중 −10% 손절", "tp_cstop": "+20% 지정가·종가 −10% 손절",
         "tp_time10": "+20% 지정가·10봉째 손실이면 정리", "tp_be": "+20% 지정가·+10% 뒤 본전 손절"}


def pad(a, n=W + 4):
    return np.vstack([a, np.full((n, a.shape[1]), np.nan)])


class Sim:
    def __init__(self, s):
        self.s = s; self.O, self.Hh, self.L, self.C, self.V = (pad(x) for x in (s.o, s.h, s.l, s.c, s.v)); self.FF = pad(s.ff)
        self.FF[s.T:] = s.ff[-1]

    def entry(self, mode, t, k):
        """→ e(진입봉 index, 미체결 −1), p(진입가)"""
        O, Hh, L, C, V = self.O, self.Hh, self.L, self.C, self.V; n = len(t)
        e = np.full(n, -1); p = np.full(n, np.nan); pc = C[t, k]

        def tradable(x):   # 그 봉에 살 수 있나(거래 있음·상한가 잠김 아님)
            lockup = (np.abs(Hh[x, k] - L[x, k]) < 1e-8) & (C[x, k] / C[x - 1, k] - 1 >= .295)
            return np.isfinite(O[x, k]) & (O[x, k] > 0) & (V[x, k] > 0) & ~lockup
        if mode == "open":
            x = t + 1; f = tradable(x); e[f] = x[f]; p[f] = O[x, k][f]
        elif mode in ("stop1", "stop3"):
            trig = Hh[t, k]
            for j in range(1, 2 if mode == "stop1" else 4):
                x = t + j; f = tradable(x) & (e < 0) & np.isfinite(trig)
                at_open = f & (O[x, k] >= trig); intr = f & ~at_open & (Hh[x, k] >= trig)
                e[at_open | intr] = x[at_open | intr]; p[at_open] = O[x, k][at_open]; p[intr] = trig[intr]
        elif mode == "limit3":
            lim = pc * .97; x = t + 1; f = tradable(x)
            at_open = f & (O[x, k] <= lim); intr = f & ~at_open & (L[x, k] <= lim)
            e[at_open | intr] = x[at_open | intr]; p[at_open] = O[x, k][at_open]; p[intr] = lim[intr]
        elif mode == "close_up":
            x = t + 1; f = tradable(x) & (C[x, k] > O[x, k]) & (C[x, k] > pc) & (C[x, k] / pc - 1 < .295)
            e[f] = x[f]; p[f] = C[x, k][f]
        return e, p

    def exits(self, e, p, k, modes=tuple(EXITS)):
        """체결된 진입(e>=0)에 대해 청산별 net·보유봉·사유·mae. dict mode -> DataFrame 열 묶음"""
        O, Hh, L, C, V, FF = self.O, self.Hh, self.L, self.C, self.V, self.FF
        n = len(e); j = np.arange(W); X = e[:, None] + j[None, :]; K = k[:, None]
        o, h, l, c, v, ff = O[X, K], Hh[X, K], L[X, K], C[X, K], V[X, K], FF[X, K]
        prev = np.where(np.isfinite(C[X - 1, K]), C[X - 1, K], ff)
        lockdn = (np.abs(h - l) < 1e-8) & (c / prev - 1 <= -.295)
        S = np.isfinite(o) & (o > 0) & (v > 0) & ~lockdn; S[:, 0] = False                      # 진입봉에는 팔지 않는다
        P = p[:, None]; r = lambda a: a / P - 1
        tgt = P * (1.20 + COST); stp = P * .90
        live = (j[None, :] >= 1) & (j[None, :] <= H - 1) & S                                   # 주문이 살아 있는 봉(1..19)
        # 만기: 20봉째 종가(S 이면), 아니면 이후 5봉 안 첫 매도 가능 시가, 없으면 평가(ffill 종가)
        mat_ok = S[:, H - 1]
        late = S[:, H:H + 5]; late_any = late.any(axis=1); late_j = H + late.argmax(axis=1)
        mat_px = np.where(mat_ok, c[:, H - 1], np.where(late_any, o[np.arange(n), late_j], ff[:, H - 1]))
        mat_j = np.where(mat_ok, H - 1, np.where(late_any, late_j, H - 1)); unresolved = ~mat_ok & ~late_any
        lowpath = np.where(j[None, :] == 0, c, np.where(np.isfinite(l), l, ff))
        out = {}
        for m in modes:
            flag = np.zeros((n, W), bool); px = np.full((n, W), np.nan); why = np.zeros((n, W), np.int8)

            def put(f, price, code):
                f = f & ~flag; flag[f] = True; px[f] = np.broadcast_to(price, f.shape)[f]; why[f] = code
            if m != "hold":
                if m == "tp_cstop":      # 종가 −10% 확인 → 다음 매도 가능 시가
                    pend = np.maximum.accumulate((c <= stp) & (j[None, :] <= H - 2), axis=1); pend = np.c_[np.zeros((n, 1), bool), pend[:, :-1]]
                    put(pend & S & (j[None, :] <= H + 4), o, 3)
                if m == "tp_time10":
                    pend = ((c[:, 9] / p - 1) < 0)[:, None] & (j[None, :] >= 10); put(pend & S & (j[None, :] <= H + 4), o, 4)
                put(live & (o >= tgt), o, 1)
                if m == "tp_stop":
                    put(live & (o <= stp), o, 2); put(live & (l <= stp), stp, 2)
                if m == "tp_be":
                    armed = np.maximum.accumulate((h >= P * 1.10) & (j[None, :] >= 1), axis=1); armed = np.c_[np.zeros((n, 1), bool), armed[:, :-1]]
                    put(live & armed & (o <= P), o, 5); put(live & armed & (l <= P), P, 5)
                put(live & (h >= tgt), tgt, 1)
            any_ = flag.any(axis=1); first = flag.argmax(axis=1); rows = np.arange(n)
            early = any_ & (first <= mat_j)
            xj = np.where(early, first, mat_j); sell = np.where(early, px[rows, first], mat_px); code = np.where(early, why[rows, first], 0)
            cm = np.minimum.accumulate(lowpath, axis=1)[rows, np.minimum(xj, W - 1)]
            out[m] = dict(net=sell / p - 1 - COST, bars=xj + 1, why=code, mae=cm / p - 1, unresolved=unresolved & ~early,
                          d0_up=c[:, 0] > p, d1_up=ff[:, 1] > p)
        return out


def run(sim, name, t, k, dates, entries=tuple(ENTRIES), exits=tuple(EXITS), slots=10):
    """signals(t,k) → 거래 표(long). slot 수익 = 그 날 신호 수익 합 / slots (미체결 = 0)."""
    rows = []
    for em in entries:
        e, p = sim.entry(em, t, k); f = e >= 0
        ex = sim.exits(e[f], p[f], k[f], exits)
        for xm, d in ex.items():
            df = pd.DataFrame(dict(rule=name, entry=em, exit=xm, t=t[f], date=dates[t[f]], k=k[f], e=e[f], **d))
            rows.append(df)
    return pd.concat(rows, ignore_index=True)
