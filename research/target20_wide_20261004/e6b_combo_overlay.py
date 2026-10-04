# -*- coding: utf-8 -*-
"""E6b — 사후 조합 목록(E6)을 20일 겹쳐 보유 계열로 바꿔 지수 대비 상승·하락 포획과 낙폭을 잰다(E5 와 같은 잣대). python e6b_combo_overlay.py"""
import io, contextlib, importlib
import numpy as np, pandas as pd
from w20lib import *
with contextlib.redirect_stdout(io.StringIO()):
    e5 = importlib.import_module("e5_overlay"); e6 = importlib.import_module("e6_combo")
ser = {"고베타+고점 근접(기준)": e5.ser["highbeta_high"], "놀람(+) ∩ 고베타+고점 점수순": e5.tranche_series(e6.picks["pos_highbeta"]),
       "놀람(+) ∩ 시총 상위20% → 고점 근접순": e5.tranche_series(e6.picks["pos_large_nearhigh"]), "지수 반반": e5.ser["index"]}
print(f"기간 {e5.dates[0]}~{e5.dates[-1]} · 20일 비겹침 구간 32개(상승 18·하락 14) · asym = 상승 포획 − 하락 포획 [구간 재추출 95%]")
for nm, R in ser.items():
    for sn in ("항상 보유", "코스닥>120일선"):
        x = e5.overlay(R, e5.SIG[sn]); st = e5.stats(x, e5.bench); yy = []
        for y in ("2024", "2025", "2026"):
            m = e5.yr == y; yy.append(f"{y} {(np.prod(1 + x[m]) - 1) * 100:+.0f}%")
        print(f"  {nm:<28} {sn:<10} 상승 구간 {st['up_ret']:+.2f}% · 하락 구간 {st['dn_ret']:+.2f}% · up {st['up_cap']:.2f} · dn {st['dn_cap']:.2f} · asym {st['asym']:+.2f} [{st['asym_lo']:+.2f},{st['asym_hi']:+.2f}] · 누적 {st['total']:+.0f}% · 낙폭 {st['mdd']:.0f}% · 하락 구간에 지수 이긴 비율 {st['win_beat_dn']:.0%} · 상승 구간 {st['win_beat_up']:.0%} | " + " ".join(yy))
