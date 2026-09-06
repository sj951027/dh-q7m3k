# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행. 읽기 전용(history.db·ohlcv.db mode=ro), seed 고정.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent

"""shadow_ops_portfolio.py — OPS_GUIDE §3 '그림자 포트' 자동 산출 (관측 전용, 판정 아님)

규약(OPS_GUIDE.md §1)을 history.db 위에 그대로 적용한다:
  대상 v30(v3_scores)·lv_b(lowvol_scores) — 시장별 상위 10 — 희석 배지(dilution_flag, 60거래일) 제외
  — 진입 t+1 (종가 기준=§11 잣대 / 시가 기준=운영 권장, 둘 다 산출) — 보유 K거래일(40 기본, 20 비교)
  — 초과 = 종목 수익 − 같은 시장 전종목 중앙값 수익(기본, 연구 잣대와 동일) / 지수 대비는 참고 병기
    (2026-09-06 실측: 6~8월 KOSPI −23%·KOSDAQ −14% 급락 국면에서 지수 대비는 +20%p 로 부풀려짐 — 대형주 쏠림 착시)
두 표본 단위:
  (A) 앵커 단위: 등록 후 게이트 통과 앵커마다 '그날 상위10 바스켓' 1개 → n≈40, iid+주블록 CI (§11 앵커 규약과 같은 표본)
  (B) 트랜치 단위: 5거래일마다 1개 바스켓(4트랜치 운영과 같은 간격) → n 작음, 운영 장부와 직접 비교용
출력: research/out_shadow/shadow_{model}_anchor.csv · shadow_tranche.csv · 콘솔 요약
"""
import sys, sqlite3
import numpy as np
import pandas as pd

REPO = _P(str(_REPO))
sys.path.insert(0, str(REPO))
import leaderboard as lb
import dilution_flag as dil

OUT = _HERE / "out_shadow"; OUT.mkdir(exist_ok=True)
TOP_N = 10
HOLDS = (40, 20)
TRANCHE_STEP = 5
BOOT = 4000

close, mktmap = lb.load_ohlcv()
ocon = sqlite3.connect(f'file:{lb.OHLCV_DB}?mode=ro', uri=True)
opn = pd.read_sql("SELECT ticker,date,open FROM daily_ohlcv", ocon)\
        .pivot_table(index="date", columns="ticker", values="open", aggfunc="last").reindex(close.index)
idx = pd.read_sql("SELECT series,date,close FROM market_daily", ocon)\
        .pivot_table(index="date", columns="series", values="close").reindex(close.index)
ocon.close()
dates = list(close.index); N = len(dates)
con = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
partial, dbl, didx = lb.build_gates(con, dates)
excl = partial | dbl

SRC = {
    "v30":  ("SELECT run_id, market, ticker, final_score_v3 AS score FROM v3_scores WHERE model_id='v30'", "20260602"),
    "lv_b": ("SELECT run_id, market, ticker, lowvol_score AS score FROM lowvol_scores WHERE model_id='lv_b'", "20260605"),
}
IDX_OF = {"kospi": "KOSPI", "kosdaq": "KOSDAQ"}

def boot_ci(a, seed=7):
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    if len(a) < 3: return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(BOOT)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))

def week_block_ci(sr, seed=7):
    wk = pd.to_datetime(pd.Series(sr.index, index=sr.index), format="%Y%m%d").dt.to_period("W")
    blocks = [g.values for _, g in sr.groupby(wk)]
    if len(blocks) < 3: return (np.nan, np.nan, len(blocks))
    rng = np.random.default_rng(seed)
    means = [np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))]).mean() for _ in range(BOOT)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), len(blocks)

def basket(g, rid):
    """그날 시장별 상위 TOP_N (희석 배지 제외) → [(ticker, market)]"""
    flags = dil.load(asof=rid)
    out = []
    for mk, gm in g.groupby("market"):
        gm = gm[~gm.ticker.isin(flags)].sort_values("score", ascending=False)
        for t in gm.ticker.head(TOP_N):
            out.append((t, mk))
    return out

_uni_cache = {}
def uni_median(mk, t0, t1):
    """같은 시장 전 종목의 t0→t1 종가 수익 중앙값(연구 잣대 fslib 과 동일 사상). 지수(시총가중)와 달리 대형주 쏠림 없음."""
    key = (mk, t0, t1)
    if key not in _uni_cache:
        cols = [c for c in close.columns if str(mktmap.get(c, "")).lower() == mk]
        r = close.iloc[t1][cols] / close.iloc[t0][cols] - 1
        _uni_cache[key] = float(np.nanmedian(r.values)) if len(cols) else 0.0
    return _uni_cache[key]

def basket_ret(bk, t, K, entry="close", bench="uni"):
    """진입 t+1 (종가|시가) → 청산 t+1+K 종가. bench: 'uni'(시장별 전종목 중앙값, 기본) | 'idx'(시장지수). (초과%, 완결, 종목수)"""
    t0 = t + lb.ENTRY_LAG; t1 = t0 + K
    if t1 >= N: return (np.nan, False, 0)
    ex = []
    for tic, mk in bk:
        if tic not in close.columns: continue
        p0 = (opn if entry == "open" else close).iloc[t0].get(tic, np.nan)
        p1 = close.iloc[t1].get(tic, np.nan)
        if not (np.isfinite(p0) and np.isfinite(p1)) or p0 <= 0: continue
        jump = close[tic].pct_change(fill_method=None).abs().iloc[t0 + 1:t1 + 1].max()
        if jump > lb.JUMP_CAP: continue
        if bench == "idx":
            i0 = idx.iloc[t0].get(IDX_OF[mk]); i1 = idx.iloc[t1].get(IDX_OF[mk])
            m = (i1 / i0 - 1) if (i0 and i1) else 0.0
        else:
            m = uni_median(mk, t0, t1)
        ex.append((p1 / p0 - 1 - m) * 100)
    return (float(np.mean(ex)) if ex else np.nan, True, len(ex))

rows_a, rows_t = [], []
for mid, (sql, reg) in SRC.items():
    S = pd.read_sql(sql, con); S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str)
    keep = lb.dedupe_by_anchor(S, didx, excl, reg=reg)
    anchors = sorted((lb.anchor(r, didx), r) for r in keep if lb.anchor(r, didx) is not None)
    # (A) 앵커 단위
    for t, rid in anchors:
        g = S[S.run_id == rid]; bk = basket(g, rid)
        rec = {"model": mid, "run_id": rid, "n_stocks": len(bk)}
        for K in HOLDS:
            for e in ("close", "open"):
                v, done, n = basket_ret(bk, t, K, e)
                rec[f"exc{K}_{e}"] = v
            rec[f"excidx{K}_close"], _, _ = basket_ret(bk, t, K, "close", bench="idx")
        rows_a.append(rec)
    # (B) 트랜치 단위: 첫 앵커부터 5거래일 간격, 그 날 앵커 없으면 다음 앵커
    want = anchors[0][0] if anchors else None; used = set()
    for t, rid in anchors:
        if want is None or t < want or rid in used: continue
        g = S[S.run_id == rid]; bk = basket(g, rid); used.add(rid)
        rec = {"model": mid, "tranche_run": rid, "n_stocks": len(bk)}
        for K in HOLDS:
            v, done, n = basket_ret(bk, t, K, "close"); rec[f"exc{K}_close"] = v; rec[f"done{K}"] = done
        vo, _, _ = basket_ret(bk, t, 40, "open"); rec["exc40_open"] = vo
        rows_t.append(rec); want = t + TRANCHE_STEP

A = pd.DataFrame(rows_a); T = pd.DataFrame(rows_t)
A.to_csv(OUT / "shadow_anchor.csv", index=False); T.to_csv(OUT / "shadow_tranche.csv", index=False)

print("=== (A) 앵커 단위 그림자 포트 — 시장별 상위10·희석 제외·t+1 진입, 초과 = 같은 시장 전종목 중앙값 대비 %p (지수 대비는 병기) ===")
for mid in SRC:
    a = A[A.model == mid]
    print(f"  [{mid}] 앵커 {len(a)}개 ({a.run_id.min()}~{a.run_id.max()}), 바스켓 평균 {a.n_stocks.mean():.1f}종목")
    for K in HOLDS:
        for e in ("close", "open"):
            s = a.set_index("run_id")[f"exc{K}_{e}"].dropna()
            if len(s) == 0: print(f"     h{K} {e:5s}: 완결 표본 없음"); continue
            lo, hi = boot_ci(s.values); blo, bhi, nb = week_block_ci(s)
            print(f"     h{K} {e:5s}: n={len(s):2d}  평균 {s.mean():+.2f}%p  iid CI[{lo:+.2f},{hi:+.2f}]  주블록({nb}주) CI[{blo:+.2f},{bhi:+.2f}]  양(+) {100*(s>0).mean():.0f}%")
    for K in HOLDS:
        s = a.set_index("run_id")[f"excidx{K}_close"].dropna()
        if len(s): lo, hi = boot_ci(s.values); print(f"     (참고) h{K} 지수 대비: n={len(s)}  평균 {s.mean():+.2f}%p  CI[{lo:+.2f},{hi:+.2f}]  ← 시총가중 지수라 대형주 급락 국면에선 부풀려짐")
    # 40 vs 20 같은 앵커 차이
    d = (a["exc40_close"] - a["exc20_close"]).dropna()
    if len(d) >= 3:
        lo, hi = boot_ci(d.values)
        print(f"     40일−20일(같은 앵커, 종가): n={len(d)}  {d.mean():+.2f}%p  CI[{lo:+.2f},{hi:+.2f}]")
    d = (a["exc40_open"] - a["exc40_close"]).dropna()
    if len(d) >= 3:
        lo, hi = boot_ci(d.values)
        print(f"     시가진입−종가진입(40일): n={len(d)}  {d.mean():+.2f}%p  CI[{lo:+.2f},{hi:+.2f}]")

print("\n=== (B) 5거래일 간격 트랜치 (운영 장부 비교용) ===")
for mid in SRC:
    t = T[T.model == mid]
    done = t[t.done40]
    print(f"  [{mid}] 트랜치 {len(t)}개, 40일 완결 {len(done)}개")
    for _, r in t.iterrows():
        f = lambda v: "   —  " if pd.isna(v) else f"{v:+6.2f}"
        print(f"     {r.tranche_run}  {r.n_stocks:2d}종목  h20 {f(r.exc20_close)}  h40 {f(r.exc40_close)}  h40(시가) {f(r.exc40_open)}")
    if len(done) >= 3:
        s = done.exc40_close; lo, hi = boot_ci(s.values)
        print(f"     완결 40일 평균 {s.mean():+.2f}%p  CI[{lo:+.2f},{hi:+.2f}]  양(+) {100*(s>0).mean():.0f}%")
print(f"\n산출: {OUT/'shadow_anchor.csv'} · {OUT/'shadow_tranche.csv'}")
