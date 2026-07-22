# -*- coding: utf-8 -*-
"""
factor_scan.py — ohlcv.db 전 구간(748거래일) 정직한 팩터 스캔 (관측 전용)
=========================================================================
원칙:
  - 포인트-인-타임: 팩터는 t일까지 데이터만, 수익은 t+1 진입(ENTRY_LAG=1) 후 h일.
    시총 = 당시 close×shares. 정지종목·미거래 제외. 우선주 제외(코드 끝자리 0만).
  - 프로젝트 상수 재사용: ENTRY_LAG=1, JUMP_CAP=0.32(우선주 점프 컷과 동일 사상).
  - IC = 날짜×시장(KOSPI/KOSDAQ) cross-sectional Spearman 평균 (leaderboard 동일 사상).
  - h20 날짜 IC는 창이 겹쳐 자기상관 → CI는 블록 부트스트랩(블록=h)으로 보수적으로.
  - 다중검정: 시도한 팩터×호라이즌 수를 결과에 기록(Bonferroni 분모). '스캔'은 관측이며
    여기서 좋아 보여도 채택이 아니라 '사전등록 챌린저 후보'가 될 뿐이다.
스테이지: price | shortcredit | flows | spread (argv[1], 기본 price)
산출: factor_scan_<stage>.json (스크립트 옆)
"""
import json
import os
import sqlite3
import sys
import time

import numpy as np
import pandas as pd
from scipy.stats import rankdata

OHLCV = os.environ.get("OHLCV_DB",
                       os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dh-q7m3k-data", "ohlcv.db"))
OUTD = os.path.dirname(os.path.abspath(__file__))
LAG = 1
JUMP = 0.32
MIN_N = 30          # 전시장 스캔이라 그룹 최소 30종목(leaderboard MIN_GROUP=8은 소유니버스용)
BOOT = 2000
HS = [5, 20]
T0 = time.time()


def log(msg):
    print(f"[{time.time()-T0:5.1f}s] {msg}", flush=True)


def load_panels():
    con = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    px = pd.read_sql("SELECT ticker,date,close,volume,shares,market,is_suspended "
                     "FROM daily_ohlcv", con)
    con.close()
    px["ticker"] = px["ticker"].astype(str)
    common = px["ticker"].str.endswith("0")      # 보통주만(우선주 제외)
    px = px[common & px["market"].isin(["KOSPI", "KOSDAQ"])]
    close = px.pivot_table(index="date", columns="ticker", values="close",
                           aggfunc="last").sort_index()
    vol = px.pivot_table(index="date", columns="ticker", values="volume",
                         aggfunc="last").reindex(close.index)[close.columns]
    shares = px.pivot_table(index="date", columns="ticker", values="shares",
                            aggfunc="last").reindex(close.index)[close.columns].ffill()
    susp = px.pivot_table(index="date", columns="ticker", values="is_suspended",
                          aggfunc="last").reindex(close.index)[close.columns]
    susp = susp.fillna(0).astype(bool)
    mkt = px.groupby("ticker")["market"].last()[close.columns]
    log(f"패널 {close.shape} (보통주 {close.shape[1]}종목)")
    return close, vol, shares, susp, mkt


def fwd_panels(close):
    ret = close.pct_change(fill_method=None)
    out = {}
    for h in HS:
        f = close.shift(-(LAG + h)) / close.shift(-LAG) - 1
        jmax = ret.abs().rolling(h, min_periods=1).max().shift(-(LAG + h))
        out[h] = f.where(jmax <= JUMP)
    return ret, out


def scan_ic(factors, fwd, vol, susp, mkt, close, start_lb):
    """factors: {이름: DataFrame}. 반환: {이름: {h: 날짜IC 시리즈}}"""
    dates = close.index
    N = len(dates)
    cols = close.columns
    mk_idx = {m: np.where((mkt == m).to_numpy())[0] for m in ("KOSPI", "KOSDAQ")}
    F = {k: v.to_numpy(np.float64) for k, v in factors.items()}
    FW = {h: fwd[h].to_numpy(np.float64) for h in HS}
    V = vol.to_numpy(np.float64)
    S = susp.to_numpy(bool)
    res = {k: {h: {} for h in HS} for k in factors}
    for di in range(start_lb, N - LAG - min(HS)):
        traded = (V[di] > 0) & ~S[di]
        for h in HS:
            if di >= N - LAG - h:
                continue
            fw = FW[h][di]
            base = traded & np.isfinite(fw)
            for k, fp in F.items():
                fv = fp[di]
                day = []
                for m, idx in mk_idx.items():
                    msk = base[idx] & np.isfinite(fv[idx])
                    if msk.sum() < MIN_N:
                        continue
                    a = rankdata(fv[idx][msk])
                    b = rankdata(fw[idx][msk])
                    if len(np.unique(a)) < 3 or len(np.unique(b)) < 3:
                        continue
                    day.append(np.corrcoef(a, b)[0, 1])
                if day:
                    res[k][h][dates[di]] = float(np.mean(day))
    return res


def block_boot_ci(arr, block):
    n = len(arr)
    if n < 2:
        return [None, None]
    rng = np.random.default_rng(7)
    k = int(np.ceil(n / block))
    means = np.empty(BOOT)
    for i in range(BOOT):
        starts = rng.integers(0, max(1, n - block + 1), k)
        sample = np.concatenate([arr[s:s + block] for s in starts])[:n]
        means[i] = sample.mean()
    return [round(float(np.percentile(means, 2.5)), 4),
            round(float(np.percentile(means, 97.5)), 4)]


def summarize(res, n_tests):
    rows = []
    for k, byh in res.items():
        for h, d in byh.items():
            if not d:
                continue
            dates = sorted(d)
            arr = np.array([d[x] for x in dates])
            thirds = np.array_split(arr, 3)
            folds = [round(float(t.mean()), 4) for t in thirds if len(t)]
            rows.append(dict(
                factor=k, h=h, n_days=len(arr),
                ic=round(float(arr.mean()), 4),
                ci_block=block_boot_ci(arr, h),
                pos=round(float((arr > 0).mean()), 3),
                folds=folds,
                fold_consistent=bool(all(np.sign(f) == np.sign(folds[0])
                                         for f in folds)) if folds and folds[0] != 0 else False,
                span=f"{dates[0]}~{dates[-1]}"))
    rows.sort(key=lambda r: -abs(r["ic"]))
    return dict(status="ok", n_tests=n_tests,
                note=f"관측 전용 스캔. Bonferroni 분모={n_tests}. 채택 아님 — 사전등록 후보 탐색.",
                rows=rows)


def stage_price():
    close, vol, shares, susp, mkt = load_panels()
    ret, fwd = fwd_panels(close)
    val = close * vol
    log("팩터 계산")
    factors = {
        "rev_5":       close / close.shift(5) - 1,
        "mom_21":      close / close.shift(21) - 1,
        "mom_63":      close / close.shift(63) - 1,
        "mom_126_21":  close.shift(21) / close.shift(126) - 1,
        "mom_252_21":  close.shift(21) / close.shift(252) - 1,
        "vol_20":      ret.rolling(20).std(),
        "vol_60":      ret.rolling(60).std(),
        "dist_52wH":   close / close.rolling(252).max(),
        "maxret_20":   ret.rolling(20).max(),
        "amihud_20":   (ret.abs() / val.replace(0, np.nan)).rolling(20).mean(),
        "logval_20":   np.log(val.rolling(20).mean()),
        "vsurge_5_60": vol.rolling(5).mean() / vol.rolling(60).mean(),
        "size":        np.log((close * shares).replace(0, np.nan)),
    }
    log("IC 스캔 시작")
    res = scan_ic(factors, fwd, vol, susp, mkt, close, start_lb=252)
    out = summarize(res, n_tests=len(factors) * len(HS))
    path = os.path.join(OUTD, "factor_scan_price.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(f"저장 {path}")
    for r in out["rows"]:
        ci = r["ci_block"]
        log(f"{r['factor']:12s} h{r['h']:<3d} n={r['n_days']:3d} IC {r['ic']:+.4f} "
            f"CI[{ci[0]:+.3f},{ci[1]:+.3f}] pos{r['pos']:.0%} folds={r['folds']} "
            f"{'일관' if r['fold_consistent'] else '불일치'}")


def stage_shortcredit():
    close, vol, shares, susp, mkt = load_panels()
    ret, fwd = fwd_panels(close)
    con = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    sf = pd.read_sql("SELECT ticker,date,short_vol_ratio,credit_bal_rate,loan_bal_amt "
                     "FROM short_flows", con)
    con.close()
    sf["ticker"] = sf["ticker"].astype(str)

    def pv(c):
        return sf.pivot_table(index="date", columns="ticker", values=c, aggfunc="last")\
                 .reindex(index=close.index, columns=close.columns)

    sr = pv("short_vol_ratio")
    cr = pv("credit_bal_rate")
    loan = pv("loan_bal_amt")
    factors = {
        "short_ratio_20":  sr.rolling(20, min_periods=10).mean(),
        "short_surge":     sr.rolling(5, min_periods=3).mean()
                           - sr.rolling(60, min_periods=30).mean(),
        "credit_rate":     cr,
        "credit_chg_20":   cr - cr.shift(20),
        "loan_chg_20":     (loan / loan.shift(20) - 1).replace([np.inf, -np.inf], np.nan),
    }
    first = sf["date"].min()
    start_lb = int(np.searchsorted(np.array(close.index), first)) + 60
    log(f"short/credit 스캔 시작(개시 {close.index[start_lb]})")
    res = scan_ic(factors, fwd, vol, susp, mkt, close, start_lb=start_lb)
    out = summarize(res, n_tests=len(factors) * len(HS))
    path = os.path.join(OUTD, "factor_scan_shortcredit.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for r in out["rows"]:
        ci = r["ci_block"]
        log(f"{r['factor']:15s} h{r['h']:<3d} n={r['n_days']:3d} IC {r['ic']:+.4f} "
            f"CI[{ci[0]:+.3f},{ci[1]:+.3f}] pos{r['pos']:.0%} folds={r['folds']}")


def stage_flows():
    close, vol, shares, susp, mkt = load_panels()
    ret, fwd = fwd_panels(close)
    con = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    fl = pd.read_sql("SELECT ticker,date,foreign_net_val,inst_net_val,pension_net_val "
                     "FROM daily_flows", con)
    con.close()
    fl["ticker"] = fl["ticker"].astype(str)
    marcap = close * shares

    def pv(c):
        return fl.pivot_table(index="date", columns="ticker", values=c, aggfunc="last")\
                 .reindex(index=close.index, columns=close.columns)

    factors = {}
    for c, nm in [("foreign_net_val", "frgn_20"), ("inst_net_val", "inst_20"),
                  ("pension_net_val", "pension_20")]:
        factors[nm] = pv(c).rolling(20, min_periods=10).sum() / marcap
    first = fl["date"].min()
    start_lb = int(np.searchsorted(np.array(close.index), first)) + 20
    log(f"flows 스캔 시작(개시 {close.index[start_lb]}) — 표본 짧음 주의")
    res = scan_ic(factors, fwd, vol, susp, mkt, close, start_lb=start_lb)
    out = summarize(res, n_tests=len(factors) * len(HS))
    path = os.path.join(OUTD, "factor_scan_flows.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for r in out["rows"]:
        ci = r["ci_block"]
        log(f"{r['factor']:12s} h{r['h']:<3d} n={r['n_days']:3d} IC {r['ic']:+.4f} "
            f"CI[{ci[0]:+.3f},{ci[1]:+.3f}] pos{r['pos']:.0%} folds={r['folds']}")


def stage_spread():
    """상위 팩터의 경제적 크기: 5분위 롱숏 스프레드 + 상위분위 승률(h20)."""
    names = sys.argv[2:] or ["vol_20", "dist_52wH", "maxret_20", "mom_252_21", "rev_5"]
    close, vol, shares, susp, mkt = load_panels()
    ret, fwd = fwd_panels(close)
    val = close * vol
    all_f = {
        "rev_5": close / close.shift(5) - 1, "mom_21": close / close.shift(21) - 1,
        "mom_63": close / close.shift(63) - 1,
        "mom_126_21": close.shift(21) / close.shift(126) - 1,
        "mom_252_21": close.shift(21) / close.shift(252) - 1,
        "vol_20": ret.rolling(20).std(), "vol_60": ret.rolling(60).std(),
        "dist_52wH": close / close.rolling(252).max(), "maxret_20": ret.rolling(20).max(),
        "amihud_20": (ret.abs() / val.replace(0, np.nan)).rolling(20).mean(),
        "logval_20": np.log(val.rolling(20).mean()),
        "vsurge_5_60": vol.rolling(5).mean() / vol.rolling(60).mean(),
        "size": np.log((close * shares).replace(0, np.nan)),
    }
    h = 20
    fw = fwd[h].to_numpy(np.float64)
    V = vol.to_numpy(np.float64)
    S = susp.to_numpy(bool)
    N = len(close.index)
    out = []
    for nm in names:
        fp = all_f[nm].to_numpy(np.float64)
        sp, wr = [], []
        for di in range(252, N - LAG - h):
            fv, f2 = fp[di], fw[di]
            m = (V[di] > 0) & ~S[di] & np.isfinite(fv) & np.isfinite(f2)
            if m.sum() < 100:
                continue
            q = np.quantile(fv[m], [0.2, 0.8])
            lo, hi_ = f2[m][fv[m] <= q[0]], f2[m][fv[m] >= q[1]]
            sp.append(hi_.mean() - lo.mean())
            med = np.median(f2[m])
            wr.append((hi_ > med).mean())
        sp, wr = np.array(sp), np.array(wr)
        out.append(dict(factor=nm, h=h, n_days=len(sp),
                        q5q1_spread=round(float(sp.mean()), 4),
                        spread_ci=block_boot_ci(sp, h),
                        top_winrate_vs_mkt=round(float(wr.mean()), 3)))
        r = out[-1]
        log(f"{nm:12s} 상위-하위20% h20 스프레드 {r['q5q1_spread']:+.2%} "
            f"CI[{r['spread_ci'][0]:+.3f},{r['spread_ci'][1]:+.3f}] "
            f"상위분위 승률(시장중앙값 대비) {r['top_winrate_vs_mkt']:.0%}")
    json.dump(dict(status="ok", rows=out),
              open(os.path.join(OUTD, "factor_scan_spread.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "price"
    dict(price=stage_price, shortcredit=stage_shortcredit,
         flows=stage_flows, spread=stage_spread)[stage]()
