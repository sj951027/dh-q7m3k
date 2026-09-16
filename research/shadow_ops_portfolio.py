# -*- coding: utf-8 -*-
"""shadow_ops_portfolio.py — 운용 채택 사전등록(PREREGISTER_ops_adoption) §1 규칙의 판정 도구 (v2, 2026-09-16)

§1 을 그대로 계산한다(값을 보고 규칙을 바꾸지 않는다):
  대상 lv_b(lowvol_scores)·v30(v3_scores) · 바구니 = 시장별 상위 10 동일가중, 희석 배지(dilution_60d, 진입일 PIT) 제외
  진입 = 추천 다음 거래일 종가(ENTRY_LAG=1). 진입일 가격 없음 = 그 종목 현금(대체 없음), 바구니 평균은 체결분만
  보유 = 40거래일 고정. 보유 중 정지·상폐 = 청산일까지 마지막 가격으로 청산
  잣대(주) = 종목 수익 − 같은 시장 전 종목 동일가중 평균 수익(PIT: 진입일 시세 있는 종목 전체, 청산도 마지막 가격)
  잣대(보조) = 전종목 중앙값 대비 · 지수 대비 (표기만)
  주지표 E = 앵커 단위 40일 초과수익 평균(%p), 비용 c 차감(0.35 정본 · 0.5 병기)
  판정 CI = 40거래일 블록 부트스트랩(앵커를 진입일 순으로 40거래일 창 단위 블록, 4,000회), Bonferroni α=0.05/2 → 97.5% 구간
  최소 표본 = 비중첩 40일 코호트 ≥4 · 국면 = 코스피·코스닥 지수 보유 40일 수익 평균(+3% 상승 / −3% 하락 / 사이 횡보)
  국면 조건 = 국면 2개 이상 · 국면당 비중첩 코호트 ≥2 · 국면별 블록 CI 하단 > −1.0%p
  크기 조건 = E − c ≥ +1.0%p(20일 환산 +0.5%p). 라벨 논리식 = §2.
  게이트 = §11 과 동일(부분실행·이중실행 run 제외). 점프 컷(§11 IC 용)은 **적용하지 않는다** — 돈 잣대는 실제 체결·보유 결과를 그대로 센다.
읽기 전용(history.db·ohlcv.db mode=ro). 실행:
  python research/shadow_ops_portfolio.py                      # 참고창(등록일~) 사전관찰
  python research/shadow_ops_portfolio.py --start 20260917     # 관찰기간 시작일 지정(등록 후 정식)
출력: research/out_shadow/ops_anchor_{model}.csv · research/out_shadow/ops_summary.md · 콘솔
"""
import argparse, sqlite3, sys
from pathlib import Path as _P
import numpy as np, pandas as pd

_HERE = _P(__file__).resolve().parent; _REPO = _HERE.parent
sys.path.insert(0, str(_REPO))
import leaderboard as lb
import dilution_flag as dil

OUT = _HERE / "out_shadow"; OUT.mkdir(exist_ok=True)
TOP_N, HOLD, BOOT, SEED = 10, 40, 4000, 7
COSTS = (0.35, 0.5)
ALPHA_FAMILY = 0.05 / 2          # Bonferroni: lv_b·v30 두 모델
REGIME_TH = 3.0                  # ±3% (지수 40일 수익 평균)
SRC = {
    "lv_b": ("SELECT run_id, market, ticker, lowvol_score AS score FROM lowvol_scores WHERE model_id='lv_b'", "20260625"),
    "v30":  ("SELECT run_id, market, ticker, final_score_v3 AS score FROM v3_scores WHERE model_id='v30'", "20260606"),
}
IDX_OF = {"kospi": "KOSPI", "kosdaq": "KOSDAQ"}


def load():
    close, mktmap = lb.load_ohlcv()
    ocon = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
    idx = pd.read_sql("SELECT series,date,close FROM market_daily", ocon).pivot_table(index="date", columns="series", values="close").reindex(close.index)
    ocon.close()
    con = sqlite3.connect(f"file:{_REPO/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, list(close.index))
    return close, mktmap, idx, con, (partial | dbl), didx


def last_px(close_np, col, t1):
    """t1 이하 마지막 유효 종가(보유 중 정지·상폐 → 마지막 가격 청산)."""
    j = t1
    while j >= 0:
        v = close_np[j, col]
        if np.isfinite(v) and v > 0:
            return v
        j -= 1
    return np.nan


def basket(g, rid):
    flags = dil.load(asof=rid)
    out = []
    for mk, gm in g.groupby("market"):
        gm = gm[~gm.ticker.isin(flags)].sort_values("score", ascending=False)
        out += [(t, mk) for t in gm.ticker.head(TOP_N)]
    return out


def anchor_row(bk, t, close, close_np, colidx, mkt_cols, idx):
    """앵커 1개: (초과 %p 동일가중평균 대비, 중앙값 대비, 지수 대비, 체결 종목 수, 국면 라벨, 진입일, 청산일)"""
    t0 = t + lb.ENTRY_LAG; t1 = t0 + HOLD
    if t1 >= close_np.shape[0]:
        return None
    dates = list(close.index)
    # 시장 벤치(PIT: 진입일 시세 있는 전 종목 · 청산 마지막 가격)
    bench = {}
    for mk, cols in mkt_cols.items():
        p0 = close_np[t0, cols]; ok = np.isfinite(p0) & (p0 > 0)
        p1 = np.array([last_px(close_np, c, t1) for c in cols[ok]])
        r = p1 / p0[ok] - 1
        bench[mk] = (float(np.nanmean(r)), float(np.nanmedian(r)))
    per = []
    for tic, mk in bk:
        c = colidx.get(tic)
        if c is None:
            continue
        p0 = close_np[t0, c]
        if not (np.isfinite(p0) and p0 > 0):
            continue                                  # 진입일 가격 없음 → 현금(제외)
        p1 = last_px(close_np, c, t1)
        r = p1 / p0 - 1
        i0 = idx.iloc[t0].get(IDX_OF[mk]); i1 = idx.iloc[t1].get(IDX_OF[mk])
        ir = (i1 / i0 - 1) if (i0 and i1 and np.isfinite(i0) and np.isfinite(i1)) else np.nan
        per.append(((r - bench[mk][0]) * 100, (r - bench[mk][1]) * 100, (r - ir) * 100 if np.isfinite(ir) else np.nan))
    if not per:
        return None
    a = np.array(per, float)
    ik = [idx.iloc[t1][s] / idx.iloc[t0][s] - 1 for s in ("KOSPI", "KOSDAQ") if s in idx.columns]
    reg_ret = float(np.nanmean(ik)) * 100
    regime = "상승" if reg_ret >= REGIME_TH else ("하락" if reg_ret <= -REGIME_TH else "횡보")
    return dict(exc_mean=float(np.nanmean(a[:, 0])), exc_median=float(np.nanmean(a[:, 1])), exc_idx=float(np.nanmean(a[:, 2])),
                n_filled=len(per), regime=regime, idx_ret=reg_ret, entry=dates[t0], exit=dates[t1])


def block_boot(vals, entry_idx, level=1 - ALPHA_FAMILY, seed=SEED):
    """40거래일 블록 부트스트랩: 진입일 인덱스를 HOLD 단위로 잘라 블록, 블록을 복원추출해 평균 분포. → (하단, 상단, 블록수)"""
    v = np.asarray(vals, float); e = np.asarray(entry_idx)
    if len(v) < 3:
        return (np.nan, np.nan, 0)
    b0 = e.min(); labels = (e - b0) // HOLD
    blocks = [v[labels == k] for k in np.unique(labels)]
    if len(blocks) < 2:
        return (np.nan, np.nan, len(blocks))
    rng = np.random.default_rng(seed)
    means = np.array([np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))]).mean() for _ in range(BOOT)])
    q = (1 - level) / 2
    return (float(np.quantile(means, q)), float(np.quantile(means, 1 - q)), len(blocks))


def cohorts(entry_idx):
    e = np.asarray(entry_idx)
    return int(len(np.unique((e - e.min()) // HOLD))) if len(e) else 0


def verdict(E_after_cost, lo, hi, n_cohort, pos, regime_ok, size_ok):
    """§2 논리식 (위에서부터 첫 번째)."""
    if np.isnan(lo):
        return "판정불가"
    if hi < 0:
        return "운용 부적합"
    if lo <= 0:
        return "운용 노이즈"
    if n_cohort < 4 or not regime_ok or not size_ok or pos < 0.60:
        return "운용 기움"
    return "운용 채택"


def run(start=None, end=None):
    close, mktmap, idx, con, excl, didx = load()
    close_np = close.to_numpy(float); colidx = {c: i for i, c in enumerate(close.columns)}
    mkt_cols = {mk: np.array([colidx[c] for c in close.columns if str(mktmap.get(c, "")).lower() == mk]) for mk in ("kospi", "kosdaq")}
    lines = [f"# 운용 채택 그림자 포트 — §1 계산 ({'관찰 시작 ' + start if start else '참고창(등록일~)'}, 기준일 {close.index[-1]})", ""]
    summary = {}
    for mid, (sql, reg) in SRC.items():
        S = pd.read_sql(sql, con); S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str)
        keep = lb.dedupe_by_anchor(S, didx, excl, reg=reg)
        anchors = sorted((lb.anchor(r, didx), r) for r in keep if lb.anchor(r, didx) is not None)
        rows = []
        for t, rid in anchors:
            d_entry = close.index[t + lb.ENTRY_LAG] if t + lb.ENTRY_LAG < len(close.index) else None
            if d_entry is None or (start and d_entry < start) or (end and d_entry > end):
                continue
            r = anchor_row(basket(S[S.run_id == rid], rid), t, close, close_np, colidx, mkt_cols, idx)
            if r:
                r.update(model=mid, run_id=rid, t=t); rows.append(r)
        A = pd.DataFrame(rows)
        A.to_csv(OUT / f"ops_anchor_{mid}.csv", index=False)
        if A.empty:
            lines.append(f"## {mid}: 완결 앵커 없음"); continue
        e_idx = A.t.values + lb.ENTRY_LAG
        E = A.exc_mean.mean(); pos = float((A.exc_mean > 0).mean()); nco = cohorts(e_idx)
        lo, hi, nb = block_boot(A.exc_mean.values, e_idx)
        lo_i, hi_i = (np.quantile(np.random.default_rng(SEED).choice(A.exc_mean.values, size=(BOOT, len(A))).mean(axis=1), [0.025, 0.975]) if len(A) > 2 else (np.nan, np.nan))
        reg_tab = []
        regime_ok = False
        rg = A.groupby("regime")
        reg_rows = {}
        for name, g in rg:
            glo, ghi, gnb = block_boot(g.exc_mean.values, g.t.values + lb.ENTRY_LAG)
            reg_rows[name] = (len(g), cohorts(g.t.values + lb.ENTRY_LAG), g.exc_mean.mean(), glo, ghi)
        good = [k for k, (n, c, m, glo, ghi) in reg_rows.items() if c >= 2 and m > 0 and (np.isnan(glo) or glo > -1.0)]
        regime_ok = len(good) >= 2
        lines += [f"## {mid} — 앵커 {len(A)}개 ({A.entry.min()}~{A.entry.max()} 진입), 코호트 {nco}, 블록 {nb}, 바구니 평균 {A.n_filled.mean():.1f}종목",
                  f"- 주지표 E(비용 전) **{E:+.2f}%p** · 40일 블록 97.5% CI [{lo:+.2f}, {hi:+.2f}] · (참고 iid 95% [{lo_i:+.2f}, {hi_i:+.2f}]) · 양(+) {pos:.0%}",
                  f"- 보조 잣대: 중앙값 대비 {A.exc_median.mean():+.2f}%p · 지수 대비 {A.exc_idx.mean():+.2f}%p",
                  "", "| 국면 | 앵커 | 코호트 | 평균 초과 | 블록 CI |", "|---|---:|---:|---:|---|"]
        for k, (n, c, m, glo, ghi) in reg_rows.items():
            lines.append(f"| {k} | {n} | {c} | {m:+.2f} | [{glo:+.2f}, {ghi:+.2f}] |")
        lines += ["", "| 비용 c | E−c | 크기 조건(E−c ≥ 1.0) | 라벨(§2) |", "|---|---:|---|---|"]
        for c in COSTS:
            Ec = E - c; size_ok = Ec >= 1.0
            lab = verdict(Ec, lo - c, hi - c, nco, pos, regime_ok, size_ok)
            lines.append(f"| {c:.2f} | {Ec:+.2f} | {'충족' if size_ok else '미달'} | **{lab}** |")
        lines += ["", f"- 국면 조건: {'충족' if regime_ok else '미달'} (조건 충족 국면 {good}) · 코호트 {'충족' if nco >= 4 else '미달'}({nco}/4)", ""]
        summary[mid] = dict(n=len(A), E=E, lo=lo, hi=hi, pos=pos, cohorts=nco, regime_ok=regime_ok)
    md = "\n".join(lines) + "\n"
    (OUT / "ops_summary.md").write_text(md, encoding="utf-8")
    print(md)
    con.close()
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None, help="관찰기간 시작(진입일 기준 YYYYMMDD). 없으면 등록일~ 참고창")
    ap.add_argument("--end", default=None)
    a = ap.parse_args()
    run(a.start, a.end)
