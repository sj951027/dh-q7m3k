# -*- coding: utf-8 -*-
"""pair_all_now.py — h20 무시, '지금 측정 가능한' 최장 h(1~5)로 전 모델 paired 비교.
   프로토콜은 pair_compare/leaderboard 그대로. 관측 전용·읽기 전용."""
import os, sys, sqlite3
os.environ.setdefault('REPO', '.')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import pair_compare as pc
import leaderboard as lb

HORIZONS = [1, 2, 3, 5]
BASE = {'v3': 'v30', 'lowvol': 'lv_a', 'wu': 'wu_a'}

close, _ = lb.load_ohlcv(); dates = list(close.index); N = len(dates)
chg = close.pct_change(fill_method=None).abs(); fwd = pc.build_fwd_cache(close, chg, N)
con = sqlite3.connect(f"file:{lb.DB}?mode=ro", uri=True)
partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl

for trk, (tb, sc, _u) in lb.TRACKS.items():
    base = BASE[trk]
    mids = [m for (m,) in con.execute(f"SELECT DISTINCT model_id FROM {tb}")]
    data = {}
    for mid in mids:
        s = pd.read_sql(f"SELECT run_id, market, ticker, {sc} AS score FROM {tb} WHERE model_id=?",
                        con, params=(mid,))
        s['run_id'] = s['run_id'].astype(str); s['ticker'] = s['ticker'].astype(str)
        keep = lb.dedupe_by_anchor(s, didx, excl, reg=lb.REG_DATE.get(mid))
        amap = {}
        for rid in keep:
            t = lb.anchor(rid, didx)
            if t is not None: amap[t] = rid
        icmap = {h: {} for h in HORIZONS}
        for t, rid in amap.items():
            g = s[s['run_id'] == rid]
            for h in HORIZONS:
                f = fwd(t, h)
                if f is not None:
                    ic = pc.day_ic(g, f)
                    if ic is not None: icmap[h][t] = ic
        data[mid] = (amap, icmap)
    _ab, ibm = data[base]
    rows = []
    for mid in mids:
        if mid == base: continue
        _am, imm = data[mid]
        best = None
        for h in sorted(HORIZONS, reverse=True):
            ts = sorted(set(ibm[h]) & set(imm[h]))
            if ts: best = (h, ts); break
        if best is None:
            rows.append((mid, None)); continue
        h, ts = best
        im = np.array([imm[h][t] for t in ts]); ib = np.array([ibm[h][t] for t in ts])
        d = im - ib
        ci = pc.boot_ci(d) if len(d) > 1 else [None, None]
        rows.append((mid, dict(h=h, n=len(d), dic=float(d.mean()), ci=ci,
                               win=float((d > 0).mean()),
                               icm=float(im.mean()), icb=float(ib.mean()))))
    rows.sort(key=lambda r: -(r[1]['dic'] if r[1] else -9))
    print(f"\n[{trk}] 베이스={base} · ΔIC>0 = 베이스보다 우세 · h=각 모델 측정가능 최장")
    print(f"{'모델':9s} {'h':>2s} {'n':>3s} {'ΔIC':>8s} {'95%CI':>18s} {'승률':>5s} {'IC 모델/베이스':>15s}")
    for mid, r in rows:
        if r is None:
            print(f"{mid:9s}  — 아직 닫힌 수익률 창 없음"); continue
        ci = f"[{r['ci'][0]:+.3f},{r['ci'][1]:+.3f}]" if r['ci'][0] is not None else '(n=1, CI불가)'
        print(f"{mid:9s} {r['h']:2d} {r['n']:3d} {r['dic']:+8.4f} {ci:>18s} {r['win']:5.0%}"
              f" {r['icm']:+.3f}/{r['icb']:+.3f}")
con.close()
print("\n※ h가 다른 행끼리는 직접 비교 주의(같은 h끼리만) · 전부 표본<40일 = '기움'까지만")
