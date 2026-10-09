# -*- coding: utf-8 -*-
"""verdict_v30_w2_px_a_20261009.py — v30 2차 창(W2b, 20260810~) · px_a(wu) §11 판정 계산 (2026-10-09, 가격 마지막 20261008)

verdict_mom_b_qs_a_prep_20260917.py · verdict_v30_window2_prep_20260906.py 규약 그대로(leaderboard.py import):
  ① h20 주지표 IC · iid 95% CI(4,000) · 주별 일관 · Bonferroni 보정 CI
     — 분모: v30 = v3_scores distinct(사전등록 7, 실측 병기) / px_a = 사전등록 6 · wu_scores 실측 병기
  ② 보조 지평 h5·h10 (px_a 는 사전등록상 h10 재현까지 봐야 '유의')
  ③ 짝비교(같은 앵커): lv_b−v30(사전등록 보조) · px_a−sv_a(같은 트랙) · px_a−lv_b(참고 — 유니버스 다름)
  ④ 주블록 부트스트랩(각주③)  ⑤ §11 게이트(등록 후 유효 앵커 수)·표본 창  ⑥ 국면 분할 KOSDAQ>SMA20
  ⑦ 돈 관점: 상위10 h20 초과(후보군 중앙값 대비) · 점수 상위 10% − 하위 10%
읽기 전용(mode=ro)·seed 고정 — 점수·판정 산출물 미변경. 출력만.
"""
import sys, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import leaderboard as lb   # noqa: E402

BOOT = 4000
close, mktmap = lb.load_ohlcv()
dates = list(close.index); N = len(dates)
con = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
V3 = pd.read_sql("SELECT run_id, market, ticker, model_id, final_score_v3 AS score FROM v3_scores WHERE model_id='v30'", con)
LV = pd.read_sql("SELECT run_id, market, ticker, model_id, lowvol_score AS score FROM lowvol_scores WHERE model_id='lv_b'", con)
WU = pd.read_sql("SELECT run_id, market, ticker, model_id, wu_score AS score FROM wu_scores WHERE model_id IN ('px_a','sv_a')", con)
for S in (V3, LV, WU):
    S['ticker'] = S.ticker.astype(str).str.zfill(6); S['run_id'] = S.run_id.astype(str); S['market'] = S.market.str.lower()
TBL = {"v30": V3, "lv_b": LV, "px_a": WU, "sv_a": WU}
W2B = "20260810"
REG = dict(lb.REG_DATE)
DEN_V3 = con.execute("SELECT COUNT(DISTINCT model_id) FROM v3_scores").fetchone()[0]
DEN_WU = con.execute("SELECT COUNT(DISTINCT model_id) FROM wu_scores").fetchone()[0]
DEN_LV = con.execute("SELECT COUNT(DISTINCT model_id) FROM lowvol_scores").fetchone()[0]
DENOM = {"v30": [("사전등록·실측", DEN_V3)] if DEN_V3 == 7 else [("사전등록", 7), ("v3 실측", DEN_V3)],
         "px_a": [("사전등록", 6), ("wu 실측", DEN_WU)]}
print(f"[분모] v3 실측 {DEN_V3} · wu 실측 {DEN_WU} · lowvol 실측 {DEN_LV}  |  가격 마지막 {dates[-1]}  |  제외 run: 부분 {sorted(partial)} · 이중 {sorted(dbl)}")
print(f"[등록일] px_a {REG.get('px_a')} · sv_a {REG.get('sv_a')} · lv_b {REG.get('lv_b')} · v30 1차 {REG.get('v30')} · v30 W2b {W2B}")
pct = close.pct_change(fill_method=None).abs()


def boot_ci(a, lo=2.5, hi=97.5, seed=7):
    a = np.asarray(a, float); rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(BOOT)]
    return float(np.percentile(b, lo)), float(np.percentile(b, hi))


def keep_set(mid, reg):
    S = TBL[mid]; s = S[S.model_id == mid]
    return s, lb.dedupe_by_anchor(s, didx, excl, reg=reg)


def fwd_ret(t, h):
    f = close.iloc[t + lb.ENTRY_LAG + h] / close.iloc[t + lb.ENTRY_LAG] - 1
    jump = pct.iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + h + 1].max()
    return f.where(jump <= lb.JUMP_CAP)


def per_anchor_ic(mid, reg, h=20):
    s, keep = keep_set(mid, reg); out = {}
    for rid, g in s.groupby("run_id"):
        if rid in excl or rid not in keep: continue
        t = lb.anchor(rid, didx)
        if t is None or t + lb.ENTRY_LAG + h >= N: continue
        fwd = fwd_ret(t, h); ics = []
        for mk, gm in g.groupby("market"):
            sc = gm.set_index("ticker")["score"].astype(float)
            b = fwd.reindex(sc.index); m = sc.notna() & b.notna()
            if m.sum() < lb.MIN_GROUP or sc[m].nunique() < 3 or b[m].nunique() < 3: continue
            ics.append(np.corrcoef(sc[m].rank(), b[m].rank())[0, 1])
        if ics: out[rid] = float(np.mean(ics))
    return pd.Series(out, dtype=float).sort_index()


def weekly(sr):
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W")
    return sr.groupby(wk).mean()


def week_block_ci(sr, seed=7, lo=2.5, hi=97.5):
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W")
    blocks = [g.values for _, g in sr.groupby(wk)]; rng = np.random.default_rng(seed)
    means = [np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))]).mean() for _ in range(BOOT)]
    return float(np.percentile(means, lo)), float(np.percentile(means, hi)), len(blocks)


# 판정 대상: (표시 이름, model_id, 창 시작)
TARGETS = [("v30 W2b", "v30", W2B), ("px_a", "px_a", REG.get("px_a"))]
REFS = [("lv_b(8/10~)", "lv_b", W2B), ("sv_a(8/10~)", "sv_a", W2B), ("v30 1차 누적", "v30", REG.get("v30"))]
base = {}
print("\n=== ① h20 주지표 (iid CI · 주별 일관 · Bonferroni) ===")
for name, mid, reg in TARGETS + REFS:
    sr = per_anchor_ic(mid, reg); base[name] = sr
    if len(sr) == 0: print(f"  {name}: 표본 없음"); continue
    c95 = boot_ci(sr.values); w = weekly(sr)
    line = f"  {name:13s} n={len(sr):2d}  IC {sr.mean():+.4f} (중앙 {sr.median():+.4f} · 양수 {100*(sr > 0).mean():.0f}%)  CI95[{c95[0]:+.4f},{c95[1]:+.4f}]  주별양 {100*(w > 0).mean():.0f}%({len(w)}주)"
    for lab, dn in DENOM.get(mid, []) if (name, mid, reg) in TARGETS else []:
        a = 0.05 / dn; cb = boot_ci(sr.values, 100 * a / 2, 100 * (1 - a / 2)); line += f"  Bonf({lab}/{dn})[{cb[0]:+.4f},{cb[1]:+.4f}]"
    print(line)

print("\n=== ② 보조 지평 h5 · h10 ===")
for name, mid, reg in TARGETS:
    for hh in (5, 10):
        sr = per_anchor_ic(mid, reg, h=hh)
        if len(sr) == 0: print(f"  {name} h{hh}: 표본 없음"); continue
        c = boot_ci(sr.values); w = weekly(sr); lo, hi, nb = week_block_ci(sr)
        print(f"  {name} h{hh:2d}: n={len(sr)}  IC {sr.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]  주블록({nb})[{lo:+.4f},{hi:+.4f}]  주별양 {100*(w > 0).mean():.0f}%({len(w)}주)")

print("\n=== ③ 짝비교 (같은 앵커 h20 diff = 앞 − 뒤) ===")
for x, y in (("lv_b(8/10~)", "v30 W2b"), ("px_a", "sv_a(8/10~)"), ("px_a", "lv_b(8/10~)")):
    a, b = base[x], base[y]; common = a.index.intersection(b.index)
    if len(common) < 3: print(f"  {x} − {y}: 공통 앵커 부족({len(common)})"); continue
    d = pd.Series((a[common] - b[common]).values, index=common); c = boot_ci(d.values); lo, hi, nb = week_block_ci(d)
    print(f"  {x} − {y}: n={len(common)}  diff {d.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]  주블록({nb})[{lo:+.4f},{hi:+.4f}]")

print("\n=== ④ 주블록 부트스트랩 (각주③) · 주별 IC ===")
for name, mid, reg in TARGETS:
    sr = base[name]; lo, hi, nb = week_block_ci(sr); w = weekly(sr)
    line = f"  {name}: 주블록 {nb}개  CI95[{lo:+.4f},{hi:+.4f}]"
    for lab, dn in DENOM[mid]:
        a = 0.05 / dn; l2, h2, _ = week_block_ci(sr, lo=100 * a / 2, hi=100 * (1 - a / 2)); line += f"  Bonf({lab}/{dn})[{l2:+.4f},{h2:+.4f}]"
    print(line); print("     주별:", "  ".join(f"{str(k)[5:10]}~ {v:+.3f}(n{int((weekly(sr).index == k).sum() and len(sr[[pd.Timestamp(d).to_period('W') == k for d in pd.to_datetime(sr.index, format='%Y%m%d')]]))})" for k, v in w.items()))

print("\n=== ⑤ §11 게이트(등록 후 유효 앵커 수) · 표본 창 ===")
for name, mid, reg in TARGETS:
    s, keep = keep_set(mid, reg); sr = base[name]
    t_reg = next((i for i, d in enumerate(dates) if str(d) >= reg), None)
    ks = sorted(keep)
    print(f"  {name}: 창 시작 {reg} · 유효 앵커(리더보드 oos_days 정의) {len(keep)}개 [{ks[0]}~{ks[-1]}] · 가격 날짜 차 {N-1-t_reg}거래일 · h20 완결 앵커 {len(sr)}개 [{sr.index.min()}~{sr.index.max()}]")
    allr = sorted({r for r in s.run_id.unique() if r >= reg}); miss = [str(d) for d in dates if reg <= str(d) <= str(dates[-1]) and str(d) not in set(allr)]
    print(f"     창 안 거래일 중 run 없는 날: {miss or '없음'} · 게이트 제외 run: {[r for r in allr if r in excl] or '없음'}")

print("\n=== ⑥ 국면 분할 KOSDAQ>SMA20 (관측) ===")
ocon = sqlite3.connect(f'file:{REPO.parent/"dh-q7m3k-data"/"ohlcv.db"}?mode=ro', uri=True)
kq = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSDAQ' ORDER BY date", ocon); ocon.close()
kq['date'] = kq.date.astype(str).str.replace('-', ''); kq = kq.set_index('date')['close'].astype(float)
above = kq > kq.rolling(20).mean()
for name, mid, reg in TARGETS:
    sr = base[name]; st = above.reindex(sr.index)
    for lab, m in (("KOSDAQ>SMA20", st == True), ("KOSDAQ<SMA20", st == False)):
        x = sr[m.fillna(False).values]
        if len(x) < 3: print(f"  {name} {lab}: n={len(x)} (부족)"); continue
        c = boot_ci(x.values); print(f"  {name} {lab}: n={len(x)}  IC {x.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]")

print("\n=== ⑦ 돈 관점 (h20, 관측) ===")
for name, mid, reg in TARGETS:
    s, keep = keep_set(mid, reg); ex, spread, topwin = [], [], []
    for rid, g in s.groupby("run_id"):
        if rid in excl or rid not in keep: continue
        t = lb.anchor(rid, didx)
        if t is None or t + lb.ENTRY_LAG + 20 >= N: continue
        fwd = fwd_ret(t, 20); per, sp = [], []
        for mk, gm in g.groupby("market"):
            gm = gm.dropna(subset=["score"]); b = fwd.reindex(gm.ticker).dropna()
            if len(b) < 8: continue
            top = fwd.reindex(gm.nlargest(10, "score").ticker).dropna()
            if len(top): per.append((top.mean() - b.median()) * 100)
            k = max(1, int(len(gm) * 0.1)); hi_ = fwd.reindex(gm.nlargest(k, "score").ticker).dropna(); lo_ = fwd.reindex(gm.nsmallest(k, "score").ticker).dropna()
            if len(hi_) and len(lo_): sp.append((hi_.mean() - lo_.mean()) * 100)
        if per: ex.append(np.mean(per))
        if sp: spread.append(np.mean(sp)); topwin.append(np.mean(sp) > 0)
    c = boot_ci(ex); c2 = boot_ci(spread)
    print(f"  {name} 상위10 초과(후보군 중앙값 대비): n={len(ex)}  {np.mean(ex):+.2f}%p  CI95[{c[0]:+.2f},{c[1]:+.2f}]  양(+) {100*np.mean(np.array(ex) > 0):.0f}%")
    print(f"  {name} 점수 상위10% − 하위10%: n={len(spread)}  {np.mean(spread):+.2f}%p  CI95[{c2[0]:+.2f},{c2[1]:+.2f}]  상위가 이긴 앵커 {100*np.mean(topwin):.0f}%")
