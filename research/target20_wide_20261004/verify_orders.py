# -*- coding: utf-8 -*-
"""검증 — orders.py(벡터)의 hold·tp·tp_stop 결과를 표본 600건에서 단순 반복문으로 다시 계산해 대조. python verify_orders.py"""
import json
import numpy as np, pandas as pd
from w20lib import *
s = study(choose=False); o, h, l, c, v, ff = s.o, s.h, s.l, s.c, s.v, s.ff; tix = {t: i for i, t in enumerate(s.tick)}
TR = pd.read_parquet(HERE / "orders_trades.parquet"); TR = TR[(TR.entry == "open") & TR.exit.isin(["hold", "tp", "tp_stop"]) & (TR.e + 26 < s.T)]
smp = TR.sample(600, random_state=1); bad = 0; mx = 0.0
for _, r in smp.iterrows():
    k, e = int(r.k), int(r.e); p = o[e, k]; tgt = p * 1.205; stp = p * .9; sell = None
    def can(x):
        prev = c[x - 1, k] if np.isfinite(c[x - 1, k]) else ff[x - 1, k]
        return np.isfinite(o[x, k]) and o[x, k] > 0 and v[x, k] > 0 and not (abs(h[x, k] - l[x, k]) < 1e-8 and c[x, k] / prev - 1 <= -.295)
    if r.exit != "hold":
        for x in range(e + 1, e + 20):
            if not can(x): continue
            if o[x, k] >= tgt: sell = o[x, k]; break
            if r.exit == "tp_stop" and o[x, k] <= stp: sell = o[x, k]; break
            if r.exit == "tp_stop" and l[x, k] <= stp: sell = stp; break
            if h[x, k] >= tgt: sell = tgt; break
    if sell is None:
        if can(e + 19): sell = c[e + 19, k]
        else:
            nxt = [x for x in range(e + 20, e + 25) if can(x)]; sell = o[nxt[0], k] if nxt else ff[e + 19, k]
    net = sell / p - 1 - COST; d = abs(net - r.net); mx = max(mx, d); bad += d > 1e-9
res = dict(sample=len(smp), mismatches=int(bad), max_abs_diff=float(mx)); print(res); json.dump(res, open(HERE / "verification.json", "w"))
