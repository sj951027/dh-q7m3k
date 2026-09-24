# -*- coding: utf-8 -*-
"""lead_eval.py — lead 트랙 관측 픽(lead_picks)의 사후 성과 (PREREGISTER_ld_a.md §3 잣대). 읽기 전용.

각 앵커(run_id)에 대해 t+1 종가 진입 → t+1+H 종가(기본 H=120) 청산, 동일가중, 왕복 비용 0.5%.
비교 3중: ① 픽 시장비중 지수(코스피/코스닥 비중 = 픽 구성비) ② 같은 앵커 가드 유니버스 동일가중 ③ 대조군 ld_ctl_amt.
집계: 6개월 원형 블록 부트스트랩 95% + 비겹침(≥H 간격) 창 개별 표기. 라벨은 문서 §3 규칙대로 사람이 붙인다(자동 라벨 없음).
실행: python lead_eval.py [--h 120] [--cost 0.005]
"""
import argparse, os, sqlite3, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lead_observe as lo

def block_ci(x, block=6, reps=3000, seed=924):
    x = np.asarray(x, float); x = x[np.isfinite(x)]; L = len(x)
    if L < 3: return (float(np.mean(x)) if L else np.nan, np.nan, np.nan, L)
    rng = np.random.default_rng(seed); block = min(block, L)
    st = rng.integers(0, L, (reps, int(np.ceil(L / block)))); ix = (st[:, :, None] + np.arange(block)) % L
    mm = x[ix.reshape(reps, -1)[:, :L]].mean(axis=1)
    return (float(x.mean()), float(np.quantile(mm, .025)), float(np.quantile(mm, .975)), L)

def fmt(t): return f"{t[0]*100:+.2f} [{t[1]*100:+.2f}, {t[2]*100:+.2f}] n={t[3]}" if np.isfinite(t[1]) else f"{t[0]*100:+.2f} n={t[3]}"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--h", type=int, default=120); ap.add_argument("--cost", type=float, default=0.005)
    a = ap.parse_args(); H = a.h
    hc = sqlite3.connect(f"file:{lo.HIST}?mode=ro", uri=True)
    picks = pd.read_sql(f"SELECT * FROM {lo.TABLE}", hc); hc.close()
    if picks.empty: print("lead_picks 없음"); return 0
    oc = sqlite3.connect(f"file:{lo.OHLCV}?mode=ro", uri=True)
    dates = [r[0] for r in oc.execute("SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
    md = pd.read_sql("SELECT series,date,close FROM market_daily", oc).pivot(index="date", columns="series", values="close").reindex(dates).ffill()
    rows = []
    for run_id, g in picks.groupby("run_id"):
        t = dates.index(run_id); e, end = t + 1, t + 1 + H
        if end >= len(dates): print(f"  {run_id}: 아직 {H}거래일 미도달 (경과 {len(dates)-1-t})"); continue
        de, dend = dates[e], dates[end]
        px = pd.read_sql("SELECT ticker,date,close,volume FROM daily_ohlcv WHERE date IN (?,?)", oc, params=(de, dend))
        pe = px[px.date == de].set_index("ticker"); pend = px[px.date == dend].set_index("ticker")
        # 마지막 관측가 대체(청산일 결측)
        last = pd.read_sql("SELECT ticker, close FROM daily_ohlcv WHERE date<=? GROUP BY ticker HAVING date=max(date)", oc, params=(dend,)).set_index("ticker").close
        def basket(tks):
            rets = []
            for tk in tks:
                if tk in pe.index and pe.loc[tk, "close"] > 0 and pe.loc[tk, "volume"] > 0:
                    out = pend.loc[tk, "close"] if tk in pend.index else last.get(tk, np.nan)
                    rets.append(out / pe.loc[tk, "close"] - 1 if np.isfinite(out) else -1.0)
                else: rets.append(0.0)
            return float(np.mean(rets)) - a.cost
        gm = g[g.model_id == lo.MODEL]; gc = g[g.model_id == lo.CONTROL]
        rm, rc = basket(gm.ticker), basket(gc.ticker)
        pk = (gm.market == "KOSPI").mean()
        ik = md.loc[dend, "KOSPI"] / md.loc[de, "KOSPI"] - 1; iq = md.loc[dend, "KOSDAQ"] / md.loc[de, "KOSDAQ"] - 1
        bench = pk * ik + (1 - pk) * iq
        # 가드 유니버스 EW(앵커 재계산)
        P, _ = lo.load_panel(run_id); F = lo.compute(P); ai = int(np.where(P["dates"] == run_id)[0][0])
        uni = P["tick"][F["ok"][ai]]
        ew = basket(uni) if len(uni) else np.nan
        rows.append(dict(run_id=run_id, entry=de, exit=dend, ret=rm, bench=bench, ew=ew, ctl=rc, ex_idx=rm - bench, ex_ew=rm - ew, ex_ctl=rm - rc, kospi_share=pk))
        print(f"  {run_id}: 수익 {rm*100:+.1f} · 지수 {bench*100:+.1f} · EW {ew*100:+.1f} · 대조 {rc*100:+.1f} → 지수초과 {(rm-bench)*100:+.1f} / EW초과 {(rm-ew)*100:+.1f} / 대조초과 {(rm-rc)*100:+.1f}")
    oc.close()
    if not rows: return 0
    R = pd.DataFrame(rows)
    print(f"\n== 집계 (H={H}, 비용 {a.cost}, 6개월 블록 CI, n={len(R)} 앵커)")
    for k, lab in [("ex_idx", "① 픽비중 지수 초과"), ("ex_ew", "② 동일가중 초과"), ("ex_ctl", "③ 대조군(거래대금) 초과")]:
        print(f"  {lab}: {fmt(block_ci(R[k]))}")
    # 비겹침 창
    non, lastt = [], -10**9
    for _, r in R.iterrows():
        t = dates.index(r.run_id)
        if t - lastt >= H: non.append(r); lastt = t
    print(f"  비겹침 창 {len(non)}개:", " | ".join(f"{r.run_id} 지수초과 {r.ex_idx*100:+.1f} EW {r.ex_ew*100:+.1f} 대조 {r.ex_ctl*100:+.1f}" for r in non))
    print("  (판정 라벨은 PREREGISTER_ld_a.md §3 규칙으로 — 비겹침 창 ≥3 전에는 '관측 중')")
    return 0

if __name__ == "__main__":
    sys.exit(main())
