# -*- coding: utf-8 -*-
"""verdict_lv_e_20261104.py — lv_e(lowvol, REG 20260901) §11 판정 계산 (준비 2026-11-03 · 판정 = 유효 앵커 40 도달 뒤 1회)

규약: `VERDICT_RULES.md`(2026-10-20) + `PREREGISTER_lv_e.md`(정본). verdict_v30_w2_px_a_20261009.py 구조 그대로(leaderboard.py import).
  ① h20 주지표 IC · iid 95% CI(4,000·seed 7) · 주별 일관(≥60%) · Bonferroni(분모 = lowvol_scores distinct 실측, 사전등록 11 병기)
  ② h10 재현(사후 출신 — h20 만 통과하면 '기움'까지) · h5 보조
  ③ 짝비교 lv_e − lv_b 같은 앵커 h20·h10(각자 유니버스 = 참고, 같은 종목 교집합 = 감도) — 짝 우위 없으면 승격 불가
  ④ 주블록 부트스트랩(감도 — 유의→기움 내리기만)  ⑤ 게이트: 유효 앵커(리더보드 oos_days 정의) ≥40 이 판정 조건 · 가격 날짜 차 병기 · run 없는 날
  ⑥ to20 커버리지(사전등록 §4: 90% 미만 run 있으면 보류)  ⑦ 국면 KOSDAQ>SMA20  ⑧ 돈 관점  ⑨ 각주 ④ 참고값(겹치지 않는 앵커·하루 지속성·자리바꿈 --perm N)
읽기 전용(mode=ro) · 출력만. 유효 앵커 < 40 이면 머리에 '중간 관측' 표시(판정 아님).
"""
import sys, sqlite3, argparse
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import leaderboard as lb   # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("--perm", type=int, default=0, help="자리바꿈 횟수(0=생략, 정본 2,000·seed 20261012)"); args = ap.parse_args()
BOOT = 4000; MID = "lv_e"; PAIR = "lv_b"; DEN_PRE = 11
close, mktmap = lb.load_ohlcv()
dates = list(close.index); N = len(dates)
con = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
LV = pd.read_sql("SELECT run_id, market, ticker, model_id, lowvol_score AS score FROM lowvol_scores WHERE model_id IN ('lv_e','lv_b')", con)
LV['ticker'] = LV.ticker.astype(str).str.zfill(6); LV['run_id'] = LV.run_id.astype(str); LV['market'] = LV.market.str.lower()
REG = dict(lb.REG_DATE); R0 = REG.get(MID, "20260901")
DEN_LV = con.execute("SELECT COUNT(DISTINCT model_id) FROM lowvol_scores").fetchone()[0]
DENOM = [("사전등록·실측", DEN_LV)] if DEN_LV == DEN_PRE else [("사전등록", DEN_PRE), ("lowvol 실측", DEN_LV)]
pct = close.pct_change(fill_method=None).abs()


def boot_ci(a, lo=2.5, hi=97.5, seed=7):
    a = np.asarray(a, float); rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(BOOT)]
    return float(np.percentile(b, lo)), float(np.percentile(b, hi))


def keep_set(mid, reg):
    s = LV[LV.model_id == mid]
    return s, lb.dedupe_by_anchor(s, didx, excl, reg=reg)


def fwd_ret(t, h):
    f = close.iloc[t + lb.ENTRY_LAG + h] / close.iloc[t + lb.ENTRY_LAG] - 1
    jump = pct.iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + h + 1].max()
    return f.where(jump <= lb.JUMP_CAP)


def per_anchor_ic(mid, reg, h=20, restrict=None):
    """restrict: {run_id: set(ticker)} — 같은 종목 교집합 감도."""
    s, keep = keep_set(mid, reg); out = {}; dropped = 0; jumped = 0
    for rid, g in s.groupby("run_id"):
        if rid in excl or rid not in keep: continue
        t = lb.anchor(rid, didx)
        if t is None or t + lb.ENTRY_LAG + h >= N: continue
        if restrict is not None: g = g[g.ticker.isin(restrict.get(rid, set()))]
        fwd = fwd_ret(t, h); ics = []
        for mk, gm in g.groupby("market"):
            sc = gm.set_index("ticker")["score"].astype(float)
            b = fwd.reindex(sc.index); m = sc.notna() & b.notna()
            dropped += int((~b.index.isin(close.columns)).sum()); jumped += int(b.reindex(sc.index[sc.index.isin(close.columns)]).isna().sum())
            if m.sum() < lb.MIN_GROUP or sc[m].nunique() < 3 or b[m].nunique() < 3: continue
            ics.append(np.corrcoef(sc[m].rank(), b[m].rank())[0, 1])
        if ics: out[rid] = float(np.mean(ics))
    sr = pd.Series(out, dtype=float).sort_index(); sr.attrs["dropped"] = dropped; sr.attrs["jumped"] = jumped
    return sr


def weekly(sr):
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W")
    return sr.groupby(wk).mean()


def week_block_ci(sr, seed=7, lo=2.5, hi=97.5):
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W")
    blocks = [g.values for _, g in sr.groupby(wk)]; rng = np.random.default_rng(seed)
    means = [np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))]).mean() for _ in range(BOOT)]
    return float(np.percentile(means, lo)), float(np.percentile(means, hi)), len(blocks)


# ── ⑤ 게이트 먼저 (판정 조건) ───────────────────────────────────────────
s_e, keep_e = keep_set(MID, R0); s_b, keep_b = keep_set(PAIR, R0)
t_reg = next((i for i, d in enumerate(dates) if str(d) >= R0), None)
price_gap = N - 1 - t_reg
allr = sorted({r for r in s_e.run_id.unique() if r >= R0}); miss = [str(d) for d in dates if R0 <= str(d) <= str(dates[-1]) and str(d) not in set(allr)]
status = "판정 가능(유효 앵커 ≥40)" if len(keep_e) >= 40 else f"★ 중간 관측 — 유효 앵커 {len(keep_e)}/40, 판정 아님"
print(f"[lv_e 판정 준비] {status}")
print(f"[분모] lowvol 실측 {DEN_LV} (사전등록 {DEN_PRE})  |  가격 마지막 {dates[-1]}  |  제외 run: 부분 {sorted(partial)} · 이중 {sorted(dbl)}")
print(f"[창] 시작 {R0} · 유효 앵커 {len(keep_e)}개 [{min(keep_e)}~{max(keep_e)}] · 가격 날짜 차 {price_gap}거래일 · 창 안 run 없는 날 {miss or '없음'} · 창 안 게이트 제외 {[r for r in allr if r in excl] or '없음'}")
print(f"[짝] lv_b 유효 앵커 {len(keep_b)}개 · 공통 {len(set(keep_e) & set(keep_b))}개")

# ── ⑥ 유니버스 동일성 · to20 커버리지 ───────────────────────────────────
ocon = sqlite3.connect(f'file:{REPO.parent/"dh-q7m3k-data"/"ohlcv.db"}?mode=ro', uri=True)
print("\n=== ⑥ lv_e·lv_b 유니버스 동일성 · to20 커버리지(사전등록 §4: 90% 미만 run → 보류) ===")
cov_rows = []
for rid in sorted(keep_e):
    te = set(s_e[s_e.run_id == rid].ticker); tb = set(s_b[s_b.run_id == rid].ticker)
    t = lb.anchor(rid, didx); d0 = dates[max(0, t - 19)]; d1 = dates[t]
    q = pd.read_sql("SELECT ticker, COUNT(volume) nv, COUNT(shares) ns FROM daily_ohlcv WHERE date BETWEEN ? AND ? GROUP BY ticker", ocon, params=(d0, d1))
    q['ticker'] = q.ticker.astype(str).str.zfill(6); q = q.set_index('ticker')
    ok = q.reindex(sorted(te)); cov = float(((ok.nv > 0) & (ok.ns > 0)).mean()) if len(te) else float('nan')
    cov_rows.append((rid, len(te), len(tb), len(te & tb), cov))
cv = pd.DataFrame(cov_rows, columns=["run", "n_lv_e", "n_lv_b", "교집합", "to20_cov"])
print(f"  run {len(cv)}개 · 종목 수 lv_e 중앙 {cv.n_lv_e.median():.0f} · lv_b 중앙 {cv.n_lv_b.median():.0f} · 교집합/lv_e 평균 {100*(cv['교집합']/cv.n_lv_e).mean():.1f}% · 완전 동일 run {int(((cv.n_lv_e == cv['교집합']) & (cv.n_lv_b == cv['교집합'])).sum())}/{len(cv)}")
low = cv[cv.to20_cov < 0.9]
print(f"  to20 커버리지(앵커 포함 직전 20거래일 volume·shares 모두 있음): 최소 {100*cv.to20_cov.min():.1f}% · 중앙 {100*cv.to20_cov.median():.1f}% · 90% 미만 run {len(low)}개 {list(low.run) if len(low) else ''}")

# ── ① h20 주지표 ────────────────────────────────────────────────────────
TARGETS = [("lv_e", MID, R0)]; REFS = [("lv_b(9/01~)", PAIR, R0)]
base = {}
print("\n=== ① h20 주지표 (iid CI · 주별 일관 · Bonferroni) ===")
for name, mid, reg in TARGETS + REFS:
    sr = per_anchor_ic(mid, reg); base[name] = sr
    if len(sr) == 0: print(f"  {name}: 표본 없음"); continue
    c95 = boot_ci(sr.values); w = weekly(sr)
    line = f"  {name:13s} n={len(sr):2d} [{sr.index.min()}~{sr.index.max()}]  IC {sr.mean():+.4f} (중앙 {sr.median():+.4f} · 양수 {100*(sr > 0).mean():.0f}%)  CI95[{c95[0]:+.4f},{c95[1]:+.4f}]  주별양 {100*(w > 0).mean():.0f}%({len(w)}주)"
    if (name, mid, reg) in TARGETS:
        for lab, dn in DENOM:
            a = 0.05 / dn; cb = boot_ci(sr.values, 100 * a / 2, 100 * (1 - a / 2)); line += f"  Bonf({lab}/{dn})[{cb[0]:+.4f},{cb[1]:+.4f}]"
        line += f"  | 시세 없는 관측 {sr.attrs['dropped']} · 점프컷/결측 {sr.attrs['jumped']}"
    print(line)
    print("     앵커별:", " ".join(f"{k[4:]}:{v:+.3f}" for k, v in sr.items()))

print("\n=== ② h10 재현(사후 출신 조건) · h5 보조 ===")
aux = {}
for name, mid, reg in TARGETS + REFS:
    for hh in (10, 5):
        sr = per_anchor_ic(mid, reg, h=hh); aux[(name, hh)] = sr
        if len(sr) == 0: print(f"  {name} h{hh}: 표본 없음"); continue
        c = boot_ci(sr.values); w = weekly(sr); lo, hi, nb = week_block_ci(sr)
        line = f"  {name:13s} h{hh:2d}: n={len(sr)}  IC {sr.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]  주블록({nb})[{lo:+.4f},{hi:+.4f}]  주별양 {100*(w > 0).mean():.0f}%({len(w)}주)"
        if (name, mid, reg) in TARGETS and hh == 10:
            for lab, dn in DENOM:
                a = 0.05 / dn; cb = boot_ci(sr.values, 100 * a / 2, 100 * (1 - a / 2)); line += f"  Bonf({lab}/{dn})[{cb[0]:+.4f},{cb[1]:+.4f}]"
        print(line)

print("\n=== ③ 짝비교 lv_e − lv_b (같은 앵커; 각자 유니버스 = 참고 · 같은 종목 교집합 = 감도) ===")
inter = {rid: set(s_e[s_e.run_id == rid].ticker) & set(s_b[s_b.run_id == rid].ticker) for rid in keep_e}
for hh in (20, 10):
    a = base["lv_e"] if hh == 20 else aux[("lv_e", 10)]; b = base["lv_b(9/01~)"] if hh == 20 else aux[("lv_b(9/01~)", 10)]
    common = a.index.intersection(b.index)
    if len(common) < 3: print(f"  h{hh}: 공통 앵커 부족({len(common)})"); continue
    d = pd.Series((a[common] - b[common]).values, index=common); c = boot_ci(d.values); lo, hi, nb = week_block_ci(d); w = weekly(d)
    print(f"  h{hh} 각자 유니버스: n={len(common)}  diff {d.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]  주블록({nb})[{lo:+.4f},{hi:+.4f}]  주별양 {100*(w > 0).mean():.0f}%  앵커 양 {100*(d > 0).mean():.0f}%")
    ae = per_anchor_ic(MID, R0, h=hh, restrict=inter); ab = per_anchor_ic(PAIR, R0, h=hh, restrict=inter); cm = ae.index.intersection(ab.index)
    d2 = pd.Series((ae[cm] - ab[cm]).values, index=cm); c2 = boot_ci(d2.values)
    print(f"  h{hh} 같은 종목 교집합(감도): n={len(cm)}  diff {d2.mean():+.4f}  CI95[{c2[0]:+.4f},{c2[1]:+.4f}]")

print("\n=== ④ 주블록 부트스트랩 (감도 — 유의→기움 내리기만) · 주별 IC ===")
for name, mid, reg in TARGETS:
    sr = base[name]; lo, hi, nb = week_block_ci(sr); w = weekly(sr)
    line = f"  {name}: 주블록 {nb}개  CI95[{lo:+.4f},{hi:+.4f}]"
    for lab, dn in DENOM:
        a = 0.05 / dn; l2, h2, _ = week_block_ci(sr, lo=100 * a / 2, hi=100 * (1 - a / 2)); line += f"  Bonf({lab}/{dn})[{l2:+.4f},{h2:+.4f}]"
    print(line)
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W"); cnt = sr.groupby(wk).size()
    print("     주별:", "  ".join(f"{str(k)[5:10]}~ {v:+.3f}(n{cnt[k]})" for k, v in w.items()))

print("\n=== ⑦ 국면 분할 KOSDAQ>SMA20 (관측) ===")
kq = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSDAQ' ORDER BY date", ocon)
kq['date'] = kq.date.astype(str).str.replace('-', ''); kq = kq.set_index('date')['close'].astype(float)
above = kq > kq.rolling(20).mean()
for name, mid, reg in TARGETS:
    sr = base[name]; st = above.reindex(sr.index)
    for lab, m in (("KOSDAQ>SMA20", st == True), ("KOSDAQ<SMA20", st == False)):
        x = sr[m.fillna(False).values]
        if len(x) < 3: print(f"  {name} {lab}: n={len(x)} (부족)"); continue
        c = boot_ci(x.values); print(f"  {name} {lab}: n={len(x)}  IC {x.mean():+.4f}  CI95[{c[0]:+.4f},{c[1]:+.4f}]")

print("\n=== ⑧ 돈 관점 (h20, 관측) ===")
for name, mid, reg in TARGETS + REFS:
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
    if not ex: print(f"  {name}: 표본 없음"); continue
    c = boot_ci(ex); c2 = boot_ci(spread)
    print(f"  {name} 상위10 초과(후보군 중앙값 대비): n={len(ex)}  {np.mean(ex):+.2f}%p  CI95[{c[0]:+.2f},{c[1]:+.2f}]  양(+) {100*np.mean(np.array(ex) > 0):.0f}%")
    print(f"  {name} 점수 상위10% − 하위10%: n={len(spread)}  {np.mean(spread):+.2f}%p  CI95[{c2[0]:+.2f},{c2[1]:+.2f}]  상위가 이긴 앵커 {100*np.mean(topwin):.0f}%")

# ── ⑨ 각주 ④ 참고값 ────────────────────────────────────────────────────
print("\n=== ⑨ 각주 ④ 참고값 (라벨에 쓰지 않음) ===")
def nonoverlap(sr, h):
    pos = [didx[r] if r in didx else lb.anchor(r, didx) for r in sr.index]; pick = []; last = -10**9
    for p, r in sorted(zip(pos, sr.index)):
        if p - last >= h: pick.append(r); last = p
    return pick
for hh in (20, 10):
    sr = base["lv_e"] if hh == 20 else aux[("lv_e", 10)]; k = nonoverlap(sr, hh)
    print(f"  h{hh} 완결 앵커 {len(sr)} → 겹치지 않는 앵커 {len(k)}개 {k}")
rs = sorted(keep_e); rho, same = [], []
for a_, b_ in zip(rs[:-1], rs[1:]):
    ga = s_e[s_e.run_id == a_].set_index("ticker").score; gb = s_e[s_e.run_id == b_].set_index("ticker").score
    cm = ga.index.intersection(gb.index)
    if len(cm) >= 8: rho.append(ga[cm].rank().corr(gb[cm].rank())); same.append(len(cm) / max(len(ga), 1))
print(f"  점수 하루 지속성(lv_e, run 쌍 {len(rho)}): 순위 상관 {np.mean(rho):+.3f} · 하루 뒤 같은 종목 비율 {100*np.mean(same):.1f}%")

if args.perm > 0:
    print(f"\n  자리바꿈 {args.perm}회(seed 20261012 · 같은 시장 안 1:1 · lv_e·lv_b 같은 자리바꿈) …")
    rng = np.random.default_rng(20261012)
    win_e = s_e[s_e.run_id.isin(keep_e)]; win_b = s_b[s_b.run_id.isin(keep_b)]
    def ic_from(sdf, mid):
        global LV
        saved = LV; LV = sdf
        try: return per_anchor_ic(mid, R0)
        finally: LV = saved
    real_e = base["lv_e"].mean(); real_d = (base["lv_e"] - base["lv_b(9/01~)"]).dropna().mean()
    pe, pdiff, sig = [], [], 0
    for i in range(args.perm):
        maps = {}
        for mk in ("kospi", "kosdaq"):
            names = sorted(set(win_e[win_e.market == mk].ticker) | set(win_b[win_b.market == mk].ticker)); perm = rng.permutation(names)
            maps.update(dict(zip(names, perm)))
        pe_df = pd.concat([win_e.assign(ticker=win_e.ticker.map(maps)), win_b.assign(ticker=win_b.ticker.map(maps))])
        se = ic_from(pe_df, MID); sb = ic_from(pe_df, PAIR); pe.append(se.mean()); pdiff.append((se - sb).dropna().mean())
        c = boot_ci(se.values, seed=i); w = weekly(se); sig += int(c[0] > 0 and (w > 0).mean() >= 0.6)
    pe = np.array(pe); pdiff = np.array(pdiff)
    pct_e = 100 * (pe < real_e).mean(); pct_d = 100 * (pdiff < real_d).mean()
    print(f"  lv_e 평균 IC: 뒤섞은 2.5/50/97.5 = {np.percentile(pe,2.5):+.3f}/{np.percentile(pe,50):+.3f}/{np.percentile(pe,97.5):+.3f} · 실제 {real_e:+.4f} 는 {pct_e:.1f} 백분위 · 뒤섞은 점수에 '유의' 준 비율 {100*sig/args.perm:.1f}%")
    print(f"  짝 diff: 뒤섞은 2.5/50/97.5 = {np.percentile(pdiff,2.5):+.3f}/{np.percentile(pdiff,50):+.3f}/{np.percentile(pdiff,97.5):+.3f} · 실제 {real_d:+.4f} 는 {pct_d:.1f} 백분위")

# ── ⑩ 돈 관측표 (관측 계약 2026-11-07 §2 — 라벨 아님) ──────────────────────
print("\n=== ⑩ 돈 관측표 (계약 §2: 시장별 상위10 · t+1 종가 · 40거래일 · 동일가중 · 희석 제외 · 비용 왕복 차감 · 같은 시장 전종목 동일가중 대비 · 40일 코호트 블록 부트스트랩 4,000 seed 7 · 라벨 아님) ===")
try:
    import paper_account as _pa; _dil_of = _pa._dil_flags
except Exception as _e:
    _dil_of = None; print(f"  (희석 제외 못 함 — paper_account import 실패: {_e!r})")
H40 = 40; mkt_lower = mktmap.astype(str).str.lower()
def money_table(mid, reg, cost):
    s, keep = keep_set(mid, reg); rows = []
    for rid, g in s.groupby("run_id"):
        if rid in excl or rid not in keep: continue
        t = lb.anchor(rid, didx)
        if t is None or t + lb.ENTRY_LAG + H40 >= N: continue
        r40 = close.iloc[t + lb.ENTRY_LAG + H40] / close.iloc[t + lb.ENTRY_LAG] - 1
        dil = _dil_of(rid) if _dil_of else set(); ex = []
        for mk, gm in g.groupby("market"):
            gm = gm.dropna(subset=["score"]); gm = gm[~gm.ticker.isin(dil)]
            top = r40.reindex(gm.nlargest(10, "score").ticker).dropna()
            allm = r40.reindex(mkt_lower.index[mkt_lower == mk]).dropna()
            if len(top) < 5 or len(allm) < 50: continue
            ex.append((top.mean() - cost - allm.mean()) * 100)
        if ex: rows.append((rid, t, float(np.mean(ex))))
    if not rows: return None
    t0 = rows[0][1]; blocks = {}
    for rid, t, v in rows: blocks.setdefault((t - t0) // H40, []).append(v)
    vals = np.array([v for _, _, v in rows]); bl = [np.array(b) for b in blocks.values()]
    rng = np.random.default_rng(7)
    means = [np.concatenate([bl[i] for i in rng.integers(0, len(bl), len(bl))]).mean() for _ in range(BOOT)]
    return dict(n=len(rows), cohorts=len(bl), mean=float(vals.mean()), lo=float(np.percentile(means, 2.5)), hi=float(np.percentile(means, 97.5)), pos=float((vals > 0).mean()), first=rows[0][0], last=rows[-1][0])
for name, mid, reg in TARGETS + REFS:
    for cost in (0.005, 0.0035):
        m = money_table(mid, reg, cost)
        if m is None: print(f"  {name} 비용 {cost*100:.2f}%: 표본 없음"); continue
        flag = "" if m["cohorts"] >= 4 else "  (코호트 <4 → n 부족, 구간은 참고)"
        print(f"  {name:13s} 비용 {cost*100:.2f}%: 상위10 40일 초과(전종목 대비) {m['mean']:+.2f}%p  코호트블록 CI95[{m['lo']:+.2f},{m['hi']:+.2f}]  n={m['n']} 앵커 [{m['first']}~{m['last']}] · 코호트 {m['cohorts']} · 양(+) {100*m['pos']:.0f}%{flag}")

# ── 해석표 (PREREGISTER_lv_e §2·§4 + VERDICT_RULES §2) ──────────────────
print("\n=== 해석표 (조건 충족 ✔/✘ — 라벨은 사용자 확정) ===")
sr = base["lv_e"]; c95 = boot_ci(sr.values); w = weekly(sr); wb = week_block_ci(sr)
h10 = aux[("lv_e", 10)]; c10 = boot_ci(h10.values) if len(h10) else (float('nan'),) * 2
a_, b_ = base["lv_e"], base["lv_b(9/01~)"]; cm = a_.index.intersection(b_.index); d = (a_[cm] - b_[cm]); cd = boot_ci(d.values) if len(cm) >= 3 else (float('nan'),) * 2
bonf = {dn: boot_ci(sr.values, 100 * (0.05 / dn) / 2, 100 * (1 - (0.05 / dn) / 2)) for _, dn in DENOM}
rows = [("유효 앵커 ≥40 (판정 조건)", len(keep_e) >= 40, f"{len(keep_e)}"),
        ("h20 날짜 CI 하단 > 0", c95[0] > 0, f"[{c95[0]:+.4f},{c95[1]:+.4f}]"),
        ("주별 양(+) ≥ 60%", (w > 0).mean() >= 0.6, f"{100*(w>0).mean():.0f}% ({len(w)}주)"),
        ] + [(f"Bonferroni /{dn} 하단 > 0", bonf[dn][0] > 0, f"[{bonf[dn][0]:+.4f},{bonf[dn][1]:+.4f}]") for _, dn in DENOM] + [
        ("h10 재현 CI 하단 > 0 (사후 출신)", c10[0] > 0, f"IC {h10.mean():+.4f} [{c10[0]:+.4f},{c10[1]:+.4f}] n={len(h10)}"),
        ("짝 lv_e−lv_b h20 CI 하단 > 0 (승격 조건)", cd[0] > 0, f"diff {d.mean():+.4f} [{cd[0]:+.4f},{cd[1]:+.4f}] n={len(cm)}"),
        ("주블록 구간 0 안 걸침 (감도: 걸치면 유의→기움)", wb[0] > 0, f"[{wb[0]:+.4f},{wb[1]:+.4f}] ({wb[2]}블록)"),
        ("to20 커버리지 전 run ≥ 90% (보류 조건)", len(low) == 0, f"최소 {100*cv.to20_cov.min():.1f}%"),
        ("기움 대안: IC > +0.03 이고 CI 하단 > −0.02", sr.mean() > 0.03 and c95[0] > -0.02, f"IC {sr.mean():+.4f}")]
for lab, ok, val in rows: print(f"  {'✔' if ok else '✘'} {lab}: {val}")
print("  라벨 규칙(VERDICT_RULES §2): 유의 = 날짜 CI>0 ∧ 주별≥60% ∧ Bonf>0 ∧ h10 재현 ∧ 짝 diff>0(주블록 걸치면 기움) / 기움 = 날짜 CI>0 이나 하나라도 미달, 또는 IC>+0.03∧하단>−0.02 / 노이즈 = 그 외(IC 부호 무관) / 역작동 = 상단<0(보정·주블록까지 전부면 유의)")
