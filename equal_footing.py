# -*- coding: utf-8 -*-
"""equal_footing.py — '같은 날짜·같은 잣대' 동등 비교 (관측 전용)
  A) 트랙 내: 전 모델 공통 날짜 교집합에서 h5 IC 순위(표본<5일 모델은 교집합에서 제외·별도 표기)
  B) 트랙 간: 전 트랙 공통 날짜에서 각 모델 top10 종목의 h5 시장초과수익(유일한 공정 공통 잣대)
  주의: 전부 표본<40일 → '기움'까지만. IC 절대값의 트랙 간 비교는 여전히 금지."""
import os, sys, sqlite3
os.environ.setdefault('REPO', '.')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import pair_compare as pc
import leaderboard as lb

H = 5
MIN_DAYS = 5
close, _ = lb.load_ohlcv(); dates = list(close.index); N = len(dates)
chg = close.pct_change(fill_method=None).abs(); fwd = pc.build_fwd_cache(close, chg, N)
con = sqlite3.connect(f"file:{lb.DB}?mode=ro", uri=True)
partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl

data = {}   # (trk,mid) -> dict(scores, amap, ics{t:ic}, top10{t:[tickers]})
for trk, (tb, sc, _u) in lb.TRACKS.items():
    for (mid,) in con.execute(f"SELECT DISTINCT model_id FROM {tb}"):
        s = pd.read_sql(f"SELECT run_id, market, ticker, {sc} AS score FROM {tb} WHERE model_id=?",
                        con, params=(mid,))
        s['run_id'] = s['run_id'].astype(str); s['ticker'] = s['ticker'].astype(str)
        keep = lb.dedupe_by_anchor(s, didx, excl, reg=lb.REG_DATE.get(mid))
        amap = {}
        for rid in keep:
            t = lb.anchor(rid, didx)
            if t is not None: amap[t] = rid
        ics, top10 = {}, {}
        for t, rid in amap.items():
            f = fwd(t, H)
            if f is None: continue
            g = s[s['run_id'] == rid]
            ic = pc.day_ic(g, f)
            if ic is not None: ics[t] = ic
            gg = g.dropna(subset=['score']).sort_values('score', ascending=False)
            top10[t] = gg['ticker'].head(10).tolist()
        data[(trk, mid)] = dict(ics=ics, top10=top10)
con.close()

def boot(arr):
    rng = np.random.default_rng(7)
    b = [rng.choice(arr, len(arr)).mean() for _ in range(2000)]
    return np.percentile(b, 2.5), np.percentile(b, 97.5)

# ---- A) 트랙 내 공통 날짜 IC ----
print("A) 트랙 내 — 전 모델 공통 날짜(h5) IC 순위 [동일 표본]")
for trk in lb.TRACKS:
    mids = [m for (t, m) in data if t == trk]
    ok = [m for m in mids if len(data[(trk, m)]['ics']) >= MIN_DAYS]
    small = [m for m in mids if m not in ok]
    if not ok: continue
    common = set.intersection(*[set(data[(trk, m)]['ics']) for m in ok])
    rows = []
    for m in ok:
        arr = np.array([data[(trk, m)]['ics'][t] for t in sorted(common)])
        lo, hi = boot(arr)
        rows.append((m, arr.mean(), lo, hi, (arr > 0).mean()))
    rows.sort(key=lambda r: -r[1])
    print(f" [{trk}] 공통 {len(common)}일 · 제외(표본<{MIN_DAYS}일): {small or '없음'}")
    for m, ic, lo, hi, pos in rows:
        print(f"   {m:9s} IC {ic:+.4f} CI[{lo:+.3f},{hi:+.3f}] 양일 {pos:.0%}")

# ---- B) 트랙 간 — 전 트랙 공통 날짜, top10 시장초과수익 ----
ok_all = [(t, m) for (t, m) in data if len(data[(t, m)]['top10']) >= MIN_DAYS]
gcommon = sorted(set.intersection(*[set(data[k]['top10']) for k in ok_all]))
mkt_mean = {}
for t in gcommon:
    f = fwd(t, H)
    mkt_mean[t] = np.nanmean(f.to_numpy(float))
print(f"\nB) 트랙 간 — 전 트랙 공통 {len(gcommon)}일({dates[gcommon[0]]}~{dates[gcommon[-1]]}) · "
      f"각 모델 top10 의 h5 시장초과수익 [유일한 공정 공통 잣대]")
rows = []
for (trk, m) in ok_all:
    exc = []
    for t in gcommon:
        f = fwd(t, H)
        r = f.reindex(data[(trk, m)]['top10'][t]).to_numpy(float)
        r = r[np.isfinite(r)]
        if len(r) >= 5: exc.append(r.mean() - mkt_mean[t])
    arr = np.array(exc)
    if len(arr) < MIN_DAYS: continue
    lo, hi = boot(arr)
    rows.append((trk, m, len(arr), arr.mean(), lo, hi, (arr > 0).mean()))
rows.sort(key=lambda r: -r[3])
for trk, m, n, mu, lo, hi, pos in rows:
    print(f"   {trk:7s} {m:9s} n={n:2d} 초과수익 {mu:+.2%}/5d CI[{lo:+.2%},{hi:+.2%}] 승률 {pos:.0%}")
print("\n※ 표본 전부 <40일 — 순위는 '기움'. B는 시장평균 대비, 비용 미반영, top10 고정.")
