# -*- coding: utf-8 -*-
"""모의 계좌(현금 포함) 적재 — 설계 `research/PAPER_ACCOUNT_DESIGN_20261018.md` §2~§5·§8 + 게이트 초안 3차 §1 (2026-10-20 밤 1판)

계좌(전부 같은 규칙: 슬롯 40 · 다음날 종가 진입 · 40거래일 뒤 종가 청산 · 왕복 0.5% · 정지·상한가·가격 없음 = 현금):
  v30            v30 시장별 상위 10(희석 배지 제외)                        — 기본
  v30_gateD0     같은 목록, 앵커일 코스피 R20 > +5% 면 신규 0               — 게이트 초안 3차 정본 가설
  v30_fixq       같은 목록, 매일 신규를 q₀ 만큼만(q₀ = 1 − 추정 구간의 코스피 D 비율) — 대조군(현금 효과)
  B0_market      그날 시세 있는 전 종목 동일가중                            — 시장 평균
  B1_bigcap      시장별 시총 상위 10                                       — 그냥 큰 회사
  B2_quiet_big   시장별 60일 변동성 하위 20% 안에서 시총 상위 10              — 조용한 회사
  B3_random      시장별 무작위 10(seed = 날짜 정수) × N_DRAWS 벌 평균          — 운의 폭(2.5/97.5 백분위 병기)
되감기 시작 20260810(v30 2차 창 시작). 이 문서가 '등록'되기 전 구간은 전부 '사후' 라벨. 라벨(앞섬/뒤짐)은 만들지 않는다 — 숫자만.
적재: ../dh-q7m3k-data/paper_account.db (paper_nav · paper_meta) + docs/paper_account.json. history.db·ohlcv.db 는 읽기 전용.
실행: python paper_account.py [--start 20260810] [--no-write] [--draws 100]
"""
import argparse, json, math, sqlite3, sys, time
from datetime import datetime
from pathlib import Path

import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import leaderboard as lb, regime_ad, dilution_flag as dil, paper_engine as pe

DB_PATH = HERE / ".." / "dh-q7m3k-data" / "paper_account.db"
JSON_PATH = HERE / "docs" / "paper_account.json"
START_DEFAULT = "20260810"
REG_V30 = "20260606"
Q0_FROM = "20230630"                 # 게이트 초안 3차 §1: q₀ 추정 구간 시작(지수 자료 시작)
LIMIT_UP = 0.29                      # daily_ohlcv.change_pct 는 소수(0.29 = +29%) — 검토에서 29.0 으로 적어 상한가 필터가 죽어 있던 것 수정
TOP = 10; N_DRAWS_DEFAULT = 100       # 설계는 1,000벌 — 1판은 100벌(실행 시간), --draws 로 조정
NAMES = {"v30": "v30 기본", "v30_gateD0": "v30 · 급등 뒤 신규 0", "v30_fixq": "v30 · 고정 비율 축소",
         "B0_market": "시장 평균(전 종목)", "B1_bigcap": "큰 회사 10", "B2_quiet_big": "조용한 큰 회사 10", "B3_random": "아무 종목 10(평균)"}


def load_prices():
    con = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
    px = pd.read_sql("SELECT ticker,date,close,change_pct,shares,is_suspended,market FROM daily_ohlcv", con); con.close()
    px["ticker"] = px.ticker.astype(str).str.zfill(6)
    piv = lambda c: px.pivot_table(index="date", columns="ticker", values=c, aggfunc="last")
    close = piv("close").sort_index(); idx = close.index
    chg = piv("change_pct").reindex(idx); susp = piv("is_suspended").reindex(idx).fillna(0); shares = piv("shares").reindex(idx).ffill()
    mkt = px.groupby("ticker")["market"].last().str.lower()
    tradable = ~((susp > 0) | (chg >= LIMIT_UP))
    return close.where(close > 0), tradable, shares, mkt


def v30_picks(dates, didx):
    """등록 후 v30 앵커 → {앵커 거래일: [ticker…]} (시장별 상위 10, 희석 배지 제외). leaderboard 게이트·중복 제거 적용."""
    con = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    S = pd.read_sql("SELECT run_id, market, ticker, final_score_v3 AS score FROM v3_scores WHERE model_id='v30'", con)
    partial, dbl, _ = lb.build_gates(con, dates); con.close()
    S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str); S["market"] = S.market.str.lower()
    keep = lb.dedupe_by_anchor(S, didx, partial | dbl, reg=REG_V30)
    picks = {}
    for rid in sorted(keep):
        t = lb.anchor(rid, didx)
        if t is None:
            continue
        flags = set(dil.load(asof=rid).keys())
        picks[dates[t]] = pe.picks_from_scores(S[S.run_id == rid], top=TOP, exclude=flags).get(rid, [])
    return picks


def bench_picks(dates, close_full, tradable, shares_full, mkt, n_draws):
    """B0~B3 의 날짜별 목록. B3 는 벌(draw)마다 별도 dict. 변동성·시총은 **전체 시세**로 계산(되감기 구간만 쓰면 60일 창이 비어 B2 가 빈다 — 1판 실측)."""
    vol60 = close_full.pct_change(fill_method=None).rolling(60, min_periods=40).std()
    mcap = close_full * shares_full
    close = close_full
    b0, b1, b2 = {}, {}, {}
    b3 = [dict() for _ in range(n_draws)]
    for d in dates:
        c = close.loc[d]; ok = c.notna() & tradable.loc[d].fillna(True)
        b0[d] = list(c.index[ok])
        p1, p2 = [], []
        rng = np.random.default_rng(int(d))
        for m in ("kospi", "kosdaq"):
            tk = c.index[ok & (mkt.reindex(c.index) == m)]
            mc = mcap.loc[d, tk].dropna().sort_values(ascending=False)
            p1 += list(mc.index[:TOP])
            v = vol60.loc[d, tk].dropna()
            if len(v) >= 50:
                quiet = v.index[v <= v.quantile(0.20)]
                p2 += list(mc.reindex(quiet).dropna().sort_values(ascending=False).index[:TOP])
            if len(tk) >= TOP:
                for k in range(n_draws):
                    b3[k][d] = b3[k].get(d, []) + list(rng.choice(tk, TOP, replace=False))
        b1[d] = p1; b2[d] = p2
    return b0, b1, b2, b3


def q0_fixed(kospi_r20, start):
    """q₀ = 1 − (Q0_FROM ~ start 전날의 코스피 D(R20 > +5%) 비율). 등록 전 추정 구간 고정값."""
    s = kospi_r20[(kospi_r20.index >= Q0_FROM) & (kospi_r20.index < start)].dropna()
    return (1.0 - float((s > 0.05).mean())) if len(s) else 1.0


def run(start=START_DEFAULT, write=True, n_draws=N_DRAWS_DEFAULT):
    t0 = time.time()
    close, tradable, shares, mkt = load_prices()
    dates_all = list(close.index); didx_all = {d: i for i, d in enumerate(dates_all)}
    ks = regime_ad.load_index("KOSPI", lb.OHLCV_DB); ks_r20 = (ks / ks.shift(regime_ad.LOOKBACK) - 1)
    cells = regime_ad.classify(ks)["cell"]
    q0 = q0_fixed(ks_r20, start)
    picks_all = v30_picks(dates_all, didx_all)
    i0 = next((i for i, d in enumerate(dates_all) if d >= start), None)
    if i0 is None:
        print("⚠ paper_account: start 이후 거래일 없음(비치명)"); return None
    dates = dates_all[i0:]; sub = close.loc[dates]; trd = tradable.loc[dates]
    picks = {d: v for d, v in picks_all.items() if d >= start}
    ratio_gate = pe.ratio_by_cell(cells.reindex(dates))
    print(f"  시세 {sub.shape} · 되감기 {dates[0]}~{dates[-1]} · v30 앵커 {len(picks)} · q₀ {q0:.3f} · {time.time()-t0:.1f}s")
    b0, b1, b2, b3 = bench_picks(dates, close, trd, shares, mkt, n_draws)
    accounts = {}
    accounts["v30"] = pe.simulate(dates, sub, picks, tradable=trd)
    accounts["v30_gateD0"] = pe.simulate(dates, sub, picks, tradable=trd, new_ratio=ratio_gate)
    accounts["v30_fixq"] = pe.simulate(dates, sub, picks, tradable=trd, new_ratio=q0)
    accounts["B0_market"] = pe.simulate(dates, sub, b0, tradable=trd)
    accounts["B1_bigcap"] = pe.simulate(dates, sub, b1, tradable=trd)
    accounts["B2_quiet_big"] = pe.simulate(dates, sub, b2, tradable=trd)
    navs3 = [pe.simulate(dates, sub, p, tradable=trd)[0]["nav"].to_numpy() for p in b3]
    M3 = np.vstack(navs3)
    nav3 = accounts["v30"][0].copy(); nav3["nav"] = M3.mean(axis=0); nav3["cash"] = np.nan; nav3["n_pos"] = np.nan
    nav3["ret_1d"] = nav3["nav"] / nav3["nav"].shift(1) - 1
    accounts["B3_random"] = (nav3, [])
    p_lo, p_hi = np.percentile(M3[:, -1], 2.5), np.percentile(M3[:, -1], 97.5)
    v30_cost035 = pe.simulate(dates, sub, picks, tradable=trd, cost=pe.COST_ALT)[0]["nav"]
    # 요약
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    summary = {}
    for aid, (nav, slots) in accounts.items():
        s = pe.summarize(nav); s["name"] = NAMES[aid]; s["slots_closed"] = int(sum(1 for p in slots if p.get("status") == "closed"))
        summary[aid] = s
    summary["v30"]["total_ret_cost035"] = float((v30_cost035.iloc[-1] / v30_cost035.iloc[0] - 1) * 100)
    summary["B3_random"]["p2_5"] = float((p_lo - 1) * 100); summary["B3_random"]["p97_5"] = float((p_hi - 1) * 100); summary["B3_random"]["draws"] = n_draws
    v_last = accounts["v30"][0]["nav"].iloc[-1]; summary["v30"]["random_pctile"] = float((M3[:, -1] < v_last).mean() * 100)
    print(f"\n== 모의 계좌 {dates[0]}~{dates[-1]} (사후 되감기 · 비용 0.5% · 라벨 없음) ==")
    for aid, s in summary.items():
        extra = f" · 0.35%: {s['total_ret_cost035']:+.1f}%" if "total_ret_cost035" in s else ""
        extra += f" · 무작위 2.5/97.5: {s['p2_5']:+.1f}/{s['p97_5']:+.1f}%" if "p2_5" in s else ""
        print(f"  {s['name']:<18} 누적 {s['total_ret']:+6.1f}% · 최대낙폭 {s['mdd']:6.1f}% · 평균 현금 {s['cash_share']:5.1f}% · 끝난 슬롯 {s['slots_closed']}{extra}")
    print(f"  v30 이 무작위 {n_draws}벌 중 아래에서 {summary['v30']['random_pctile']:.0f} 백분위 · q₀ {q0:.3f}")
    if write:
        DB_PATH.parent.mkdir(exist_ok=True)
        con = sqlite3.connect(DB_PATH)
        con.execute("CREATE TABLE IF NOT EXISTS paper_nav (account_id TEXT, date TEXT, nav REAL, cash REAL, n_pos INTEGER, ret_1d REAL, label TEXT, generated TEXT, PRIMARY KEY(account_id, date))")
        con.execute("CREATE TABLE IF NOT EXISTS paper_meta (key TEXT PRIMARY KEY, value TEXT)")
        for aid, (nav, _) in accounts.items():
            con.execute("DELETE FROM paper_nav WHERE account_id=?", (aid,))
            con.executemany("INSERT INTO paper_nav VALUES (?,?,?,?,?,?,?,?)",
                            [(aid, r.date, float(r.nav), None if pd.isna(r.cash) else float(r.cash), None if pd.isna(r.n_pos) else int(r.n_pos),
                              None if pd.isna(r.ret_1d) else float(r.ret_1d), "사후", gen) for r in nav.itertuples()])
        for k, v in {"start": start, "q0": f"{q0:.6f}", "cost": "0.005", "slots": "40", "hold": "40", "draws": str(n_draws), "generated": gen}.items():
            con.execute("INSERT OR REPLACE INTO paper_meta VALUES (?,?)", (k, v))
        con.commit(); con.close()
        payload = {"generated": gen, "start": start, "end": dates[-1], "q0": q0, "cost": 0.005, "slots": 40, "hold": 40, "label": "사후(등록 전 되감기)",
                   "note": "현금 포함 모의 계좌 · 숫자만(앞섬/뒤짐 라벨 없음) · 설계 PAPER_ACCOUNT_DESIGN_20261018 §2~§5·§8",
                   "accounts": {aid: {"name": NAMES[aid], "summary": summary[aid], "nav": [[d, round(float(v), 6)] for d, v in zip(dates, accounts[aid][0]["nav"])]} for aid in accounts}}
        def _clean(x):                                   # [Codex 검토 2] NaN/inf 는 null 로 — 브라우저 JSON.parse 가 NaN 을 거부한다
            if isinstance(x, dict): return {k: _clean(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)): return [_clean(v) for v in x]
            if isinstance(x, float) and not math.isfinite(x): return None
            return x
        JSON_PATH.write_text(json.dumps(_clean(payload), ensure_ascii=False, allow_nan=False), encoding="utf-8")
        print(f"  ✓ {DB_PATH.name} · docs/paper_account.json ({time.time()-t0:.0f}s)")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--start", default=START_DEFAULT); ap.add_argument("--no-write", action="store_true"); ap.add_argument("--draws", type=int, default=N_DRAWS_DEFAULT)
    a = ap.parse_args()
    try:
        run(a.start, write=not a.no_write, n_draws=a.draws)
    except BaseException as e:                       # SystemExit·KeyboardInterrupt 포함 — 배치를 절대 막지 않는다
        print(f"⚠ paper_account 실패(비치명): {e!r}")
    sys.exit(0)
