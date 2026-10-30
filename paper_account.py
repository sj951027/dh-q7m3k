# -*- coding: utf-8 -*-
"""모의 계좌(현금 포함) 적재 — 설계 `research/PAPER_ACCOUNT_DESIGN_20261018.md` §2~§5·§8 + 게이트 초안 3차 §1 (2026-10-20 밤 1판 · 2026-10-30 2판)

계좌(전부 같은 규칙: 슬롯 40 · 다음날 종가 진입 · 40거래일 뒤 종가 청산 · 왕복 0.5% · 정지·상한가·가격 없음 = 현금):
  v30            v30 시장별 상위 10(희석 배지 제외)                        — 기본
  v30_gateD0     같은 목록, 앵커일 코스피 R20 > +5% 면 신규 0               — 게이트 초안 3차 정본 가설
  v30_fixq       같은 목록, 매일 신규를 q₀ 만큼만(q₀ = 1 − 추정 구간의 코스피 D 비율) — 대조군(현금 효과)
  B0_market      그날 시세 있는 전 종목 동일가중                            — 시장 평균
  B1_bigcap      시장별 시총 상위 10                                       — 그냥 큰 회사
  B2_quiet_big   시장별 60일 변동성 하위 20% 안에서 시총 상위 10              — 조용한 회사
  B3_random      시장별 무작위 10(seed = 날짜 정수) × N_DRAWS 벌 평균          — 운의 폭(2.5/97.5 백분위 병기)
  [2판] lv_b · le_a · lv_e · sv_a · sv_b   각 모델 시장별 상위 10(희석 제외) — v30 기본과 같은 규칙(§8-3 대상 모델, 은퇴 모델 제외)
  [E3]  switch_v30_lvb  앵커일 코스피 칸이 A(R20 ≤ −5%)면 v30 상위 10, 그 밖(B·C·D·칸 없음)이면 lv_b 상위 10 — 칸은 v30_gateD0 와 같은 함수·같은 날짜
                        (regime_ad.classify 앵커일 칸). 고른 목록이 그날 없으면 신규 0(현금, days_missing). 변수는 '목록 선택' 하나(EXPERIMENT_PLAN_20261030 E3 · 사후 설계)
되감기 시작 20260810(v30 2차 창 시작). 이 문서가 '등록'되기 전 구간은 전부 '사후' 라벨. 라벨(앞섬/뒤짐)은 만들지 않는다 — 숫자만.
  [2판] 모델 계좌는 등록일(REG_DATE) 전 적재 행(사후 백필)도 그대로 쓴다 — 요약에 reg_date·first_anchor·anchors_pre_reg 로 표시.
  [2판] 감도 두 가지를 모든 계좌 요약에 숫자로: total_ret_cost035(왕복 0.35%) · total_ret_delist90(시세 끊긴 종목 = 마지막 가격 −90%).
적재: ../dh-q7m3k-data/paper_account.db (paper_nav · paper_meta) + docs/paper_account.json. history.db·ohlcv.db 는 읽기 전용.
실행: python paper_account.py [--start 20260810] [--no-write] [--draws 100] [--out DIR]   (--out: 산출물을 다른 폴더에 — 0-diff 대조용)
"""
import argparse, json, math, os, sqlite3, sys, time
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
         "B0_market": "시장 평균(전 종목)", "B1_bigcap": "큰 회사 10", "B2_quiet_big": "조용한 큰 회사 10", "B3_random": "아무 종목 10(평균)",
         "lv_b": "lv_b 기본", "le_a": "le_a 기본", "lv_e": "lv_e 기본", "sv_a": "sv_a 기본", "sv_b": "sv_b 기본",
         "switch_v30_lvb": "스위치 · 급락 뒤 v30, 그 밖 lv_b"}
SWITCH_ID = "switch_v30_lvb"; SWITCH_A_CELLS = ("A",)          # [E3] A 칸 = v30 목록, 그 밖 = lv_b 목록
# [2판] 모델 계좌: model_id → (점수 표, 점수 열). 표·열은 leaderboard.TRACKS 와 같다(v30 은 1판 경로 그대로).
MODEL_SRC = {"lv_b": ("lowvol_scores", "lowvol_score"), "le_a": ("wu_scores", "wu_score"), "lv_e": ("lowvol_scores", "lowvol_score"),
             "sv_a": ("wu_scores", "wu_score"), "sv_b": ("wu_scores", "wu_score")}
MODEL_ACCOUNTS = ["lv_b", "le_a", "lv_e", "sv_a", "sv_b"]     # §8-3 대상(은퇴 모델 제외) — v30 은 1판 계좌 그대로


def load_prices():
    con = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
    px = pd.read_sql("SELECT ticker,date,close,change_pct,shares,is_suspended,market FROM daily_ohlcv", con)
    # [2026-10-31 J06 실측] lv_b 뽑힘의 9%(90/980)·lv_e 3%·스위치 7% 가 '시세표에 없음' 으로 현금이 되고 있었다 — 그 종목들은 전부 보충표
    #   daily_ohlcv_extra(코스닥 글로벌·영문코드 136종목, 본표와 겹침 0)에 있다. 리더보드와 같게 보충표를 합친다. 끄려면 PAPER_USE_EXTRA=0(0-diff 대조용).
    if os.environ.get("PAPER_USE_EXTRA", "1") != "0":
        try:
            ex = pd.read_sql("SELECT ticker,date,close,change_pct,shares,is_suspended,market FROM daily_ohlcv_extra", con)
        except Exception as e:                               # [Codex 검토 10/31] 켜 놓고 조용히 생략하면 '보충 종목 = 현금' 결과가 정상처럼 게시된다 → 올려서 단계 전체를 비치명 실패로
            con.close(); raise RuntimeError(f"보충표 daily_ohlcv_extra 를 읽지 못함: {type(e).__name__}") from None
        for f in (px, ex):
            f["ticker"] = f.ticker.astype(str).str.zfill(6)
        px = pd.concat([ex, px], ignore_index=True).drop_duplicates(["ticker", "date"], keep="last")   # 같은 (종목, 날짜)만 본표 우선 — 보충표의 과거 이력은 보존
    con.close()
    px["ticker"] = px.ticker.astype(str).str.zfill(6)
    piv = lambda c: px.pivot_table(index="date", columns="ticker", values=c, aggfunc="last")
    close = piv("close").sort_index(); idx = close.index
    chg = piv("change_pct").reindex(idx); susp = piv("is_suspended").reindex(idx).fillna(0); shares = piv("shares").reindex(idx).ffill()
    mkt = px.groupby("ticker")["market"].last().str.lower()
    tradable = pe.tradable_mask(susp, chg, LIMIT_UP)      # [2026-10-30 수정] 등락률 열이 빠진 신규 상장 종목이 있어도 bool 표
    return close.where(close > 0), tradable, shares, mkt


_DIL_CACHE = {}


def _dil_flags(rid):
    if rid not in _DIL_CACHE:
        _DIL_CACHE[rid] = set(dil.load(asof=rid).keys())
    return _DIL_CACHE[rid]


def model_picks(mid, table, col, dates, didx, excl, reg=None):
    """모델 앵커 → {앵커 거래일: [ticker…]} (시장별 상위 10, 희석 배지 제외). leaderboard 게이트·중복 제거 적용.
    reg 를 주면 등록 전 run 제외(1판 v30 경로), None 이면 적재된 행 전부(2판 모델 계좌 — 등록 전 백필도 '사후'로 포함)."""
    con = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    S = pd.read_sql(f"SELECT run_id, market, ticker, {col} AS score FROM {table} WHERE model_id=?", con, params=(mid,)); con.close()
    S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str); S["market"] = S.market.str.lower()
    keep = lb.dedupe_by_anchor(S, didx, excl, reg=reg)
    picks = {}
    for rid in sorted(keep):
        t = lb.anchor(rid, didx)
        if t is None:
            continue
        picks[dates[t]] = pe.picks_from_scores(S[S.run_id == rid], top=TOP, exclude=_dil_flags(rid)).get(rid, [])
    return picks


def load_gates(dates):
    con = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    partial, dbl, _ = lb.build_gates(con, dates); con.close()
    return partial | dbl


def v30_picks(dates, didx, excl=None):
    """등록 후 v30 앵커 → {앵커 거래일: [ticker…]} (1판 경로 — reg=REG_V30)."""
    if excl is None:
        excl = load_gates(dates)
    return model_picks("v30", "v3_scores", "final_score_v3", dates, didx, excl, reg=REG_V30)


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


def _tot(nav):
    return float((nav.iloc[-1] / nav.iloc[0] - 1) * 100)


def run(start=START_DEFAULT, write=True, n_draws=N_DRAWS_DEFAULT, out_dir=None):
    t0 = time.time()
    db_path, json_path = DB_PATH, JSON_PATH
    if out_dir:
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        db_path, json_path = out_dir / "paper_account.db", out_dir / "paper_account.json"
    close, tradable, shares, mkt = load_prices()
    dates_all = list(close.index); didx_all = {d: i for i, d in enumerate(dates_all)}
    ks = regime_ad.load_index("KOSPI", lb.OHLCV_DB); ks_r20 = (ks / ks.shift(regime_ad.LOOKBACK) - 1)
    cells = regime_ad.classify(ks)["cell"]
    q0 = q0_fixed(ks_r20, start)
    excl = load_gates(dates_all)
    picks_all = v30_picks(dates_all, didx_all, excl)
    i0 = next((i for i, d in enumerate(dates_all) if d >= start), None)
    if i0 is None:
        print("⚠ paper_account: start 이후 거래일 없음(비치명)"); return None
    dates = dates_all[i0:]; sub = close.loc[dates]; trd = tradable.loc[dates]
    picks = {d: v for d, v in picks_all.items() if d >= start}
    ratio_gate = pe.ratio_by_cell(cells.reindex(dates))
    gone = pe.gone_dates(close)                                       # 전체 시세 기준 '시세가 끊긴 종목'(상폐·사라짐) — 감도용
    print(f"  시세 {sub.shape} · 되감기 {dates[0]}~{dates[-1]} · v30 앵커 {len(picks)} · q₀ {q0:.3f} · 끊긴 종목 {len(gone)} · {time.time()-t0:.1f}s")
    # [2판] 모델 계좌 목록(등록 전 백필 포함 — 전부 '사후')
    mpicks, minfo = {}, {}
    for mid in MODEL_ACCOUNTS:
        tb, col = MODEL_SRC[mid]
        pk_all = model_picks(mid, tb, col, dates_all, didx_all, excl, reg=None)
        pk = {d: v for d, v in pk_all.items() if d >= start}
        mpicks[mid] = pk
        reg = lb.REG_DATE.get(mid)
        minfo[mid] = dict(reg_date=reg, first_anchor=(min(pk) if pk else None), anchors=len(pk),
                          anchors_pre_reg=int(sum(1 for d in pk if reg and d < reg)))
    print("  모델 앵커 " + " · ".join(f"{m} {minfo[m]['anchors']}(등록 전 {minfo[m]['anchors_pre_reg']})" for m in MODEL_ACCOUNTS) + f" · {time.time()-t0:.1f}s")
    b0, b1, b2, b3 = bench_picks(dates, close, trd, shares, mkt, n_draws)
    # 계좌 정의: aid → (picks, new_ratio). 같은 정의로 주(0.5%) · 0.35% · 상폐 −90% 세 벌을 돌린다.
    defs = {"v30": (picks, None), "v30_gateD0": (picks, ratio_gate), "v30_fixq": (picks, q0),
            "B0_market": (b0, None), "B1_bigcap": (b1, None), "B2_quiet_big": (b2, None)}
    for mid in MODEL_ACCOUNTS:
        defs[mid] = (mpicks[mid], None)
    sw_picks, sw_info = pe.switch_picks(dates, cells.reindex(dates), picks, mpicks["lv_b"], a_cells=SWITCH_A_CELLS)   # [E3] 칸 = gateD0 와 같은 Series
    defs[SWITCH_ID] = (sw_picks, None)
    print(f"  스위치 앵커 A {sw_info['days_A']} · 그 밖 {sw_info['days_other']} · 목록 없음 {sw_info['days_missing']}")
    accounts, sens = {}, {}
    for aid, (pk, nr) in defs.items():
        accounts[aid] = pe.simulate(dates, sub, pk, tradable=trd, new_ratio=nr)
        nav_g, led_g = pe.simulate(dates, sub, pk, tradable=trd, new_ratio=nr, gone=gone)
        sens[aid] = dict(cost035=_tot(pe.simulate(dates, sub, pk, tradable=trd, new_ratio=nr, cost=pe.COST_ALT)[0]["nav"]),
                         cost100=_tot(pe.simulate(dates, sub, pk, tradable=trd, new_ratio=nr, cost=pe.COST_HI)[0]["nav"]),      # [C11] 왕복 1.0%
                         delist90=_tot(nav_g["nav"]), slots_gone=int(sum(1 for p in led_g if p.get("gone"))))
    navs3 = [pe.simulate(dates, sub, p, tradable=trd)[0]["nav"].to_numpy() for p in b3]
    M3 = np.vstack(navs3)
    nav3 = accounts["v30"][0].copy(); nav3["nav"] = M3.mean(axis=0); nav3["cash"] = np.nan; nav3["n_pos"] = np.nan
    nav3["ret_1d"] = nav3["nav"] / nav3["nav"].shift(1) - 1
    accounts["B3_random"] = (nav3, [])
    p_lo, p_hi = np.percentile(M3[:, -1], 2.5), np.percentile(M3[:, -1], 97.5)
    M3c = np.vstack([pe.simulate(dates, sub, p, tradable=trd, cost=pe.COST_ALT)[0]["nav"].to_numpy() for p in b3]).mean(axis=0)
    M3g = np.vstack([pe.simulate(dates, sub, p, tradable=trd, gone=gone)[0]["nav"].to_numpy() for p in b3]).mean(axis=0)
    M3h = np.vstack([pe.simulate(dates, sub, p, tradable=trd, cost=pe.COST_HI)[0]["nav"].to_numpy() for p in b3]).mean(axis=0)
    sens["B3_random"] = dict(cost035=float((M3c[-1] / M3c[0] - 1) * 100), cost100=float((M3h[-1] / M3h[0] - 1) * 100), delist90=float((M3g[-1] / M3g[0] - 1) * 100))
    # 요약
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    summary = {}
    for aid, (nav, slots) in accounts.items():
        s = pe.summarize(nav); s["name"] = NAMES[aid]; s["slots_closed"] = int(sum(1 for p in slots if p.get("status") == "closed"))
        summary[aid] = s
    summary["v30"]["total_ret_cost035"] = sens["v30"]["cost035"]
    summary["B3_random"]["p2_5"] = float((p_lo - 1) * 100); summary["B3_random"]["p97_5"] = float((p_hi - 1) * 100); summary["B3_random"]["draws"] = n_draws
    v_last = accounts["v30"][0]["nav"].iloc[-1]; summary["v30"]["random_pctile"] = float((M3[:, -1] < v_last).mean() * 100)
    for aid, s in summary.items():                                   # [2판] 감도 두 가지 — 모든 계좌(B3 는 벌 평균, 슬롯 수 없음)
        s["total_ret_cost035"] = sens[aid]["cost035"]; s["total_ret_delist90"] = sens[aid]["delist90"]; s["total_ret_cost100"] = sens[aid]["cost100"]   # [C11]
        if "slots_gone" in sens[aid]:
            s["slots_gone"] = sens[aid]["slots_gone"]
    for mid in MODEL_ACCOUNTS:
        summary[mid].update(minfo[mid])
    sw_src = sw_info["source"]; sw_led = accounts[SWITCH_ID][1]
    summary[SWITCH_ID].update(days_A=sw_info["days_A"], days_other=sw_info["days_other"], days_missing=sw_info["days_missing"],
                              slots_from_v30=int(sum(1 for p in sw_led if sw_src.get(p["run"]) == "A")),
                              slots_from_lvb=int(sum(1 for p in sw_led if sw_src.get(p["run"]) == "other")))
    print(f"\n== 모의 계좌 {dates[0]}~{dates[-1]} (사후 되감기 · 비용 0.5% · 라벨 없음) ==")
    for aid, s in summary.items():
        extra = f" · 0.35%: {s['total_ret_cost035']:+.1f}% · 1.0%: {s['total_ret_cost100']:+.1f}% · 상폐−90%: {s['total_ret_delist90']:+.1f}%"
        extra += f" · 무작위 2.5/97.5: {s['p2_5']:+.1f}/{s['p97_5']:+.1f}%" if "p2_5" in s else ""
        extra += f" · 끊긴 슬롯 {s['slots_gone']}" if "slots_gone" in s else ""
        extra += f" · A {s['days_A']}/그 밖 {s['days_other']}/없음 {s['days_missing']} · 슬롯 v30 {s['slots_from_v30']}/lv_b {s['slots_from_lvb']}" if "days_A" in s else ""
        print(f"  {s['name']:<18} 누적 {s['total_ret']:+6.1f}% · 최대낙폭 {s['mdd']:6.1f}% · 평균 현금 {s['cash_share']:5.1f}% · 끝난 슬롯 {s['slots_closed']}{extra}")
    print(f"  v30 이 무작위 {n_draws}벌 중 아래에서 {summary['v30']['random_pctile']:.0f} 백분위 · q₀ {q0:.3f}")
    if write:
        db_path.parent.mkdir(exist_ok=True)
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE IF NOT EXISTS paper_nav (account_id TEXT, date TEXT, nav REAL, cash REAL, n_pos INTEGER, ret_1d REAL, label TEXT, generated TEXT, PRIMARY KEY(account_id, date))")
        con.execute("CREATE TABLE IF NOT EXISTS paper_meta (key TEXT PRIMARY KEY, value TEXT)")
        for aid, (nav, _) in accounts.items():
            con.execute("DELETE FROM paper_nav WHERE account_id=?", (aid,))
            con.executemany("INSERT INTO paper_nav VALUES (?,?,?,?,?,?,?,?)",
                            [(aid, r.date, float(r.nav), None if pd.isna(r.cash) else float(r.cash), None if pd.isna(r.n_pos) else int(r.n_pos),
                              None if pd.isna(r.ret_1d) else float(r.ret_1d), "사후", gen) for r in nav.itertuples()])
        for k, v in {"start": start, "q0": f"{q0:.6f}", "cost": "0.005", "slots": "40", "hold": "40", "draws": str(n_draws), "generated": gen,
                     "version": "2", "switch": SWITCH_ID, "cost_alt": f"{pe.COST_ALT}", "gone_ret": f"{pe.GONE_RET}", "models": ",".join(MODEL_ACCOUNTS)}.items():
            con.execute("INSERT OR REPLACE INTO paper_meta VALUES (?,?)", (k, v))
        con.commit(); con.close()
        payload = {"generated": gen, "start": start, "end": dates[-1], "q0": q0, "cost": 0.005, "slots": 40, "hold": 40, "label": "사후(등록 전 되감기)",
                   "note": "현금 포함 모의 계좌 · 숫자만(앞섬/뒤짐 라벨 없음) · 설계 PAPER_ACCOUNT_DESIGN_20261018 §2~§5·§8",
                   "version": 2, "models": MODEL_ACCOUNTS,
                   "switch": {SWITCH_ID: {"a_cells": list(SWITCH_A_CELLS), "list_A": "v30", "list_other": "lv_b", "cell_basis": "앵커일 코스피 칸(v30_gateD0 와 같음)",
                                          "note": "days_A/days_other = 그 목록을 쓴 앵커 수 · days_missing = 고른 목록이 없어 신규 0 인 날 · slots_from_v30/lvb = 체결 슬롯 수 · 사후 설계(2026-10-30)"}},
                   "sens": {"cost_alt": pe.COST_ALT, "gone_ret": pe.GONE_RET, "gone_tickers": len(gone),
                            "cost_hi": pe.COST_HI,
                            "note": "total_ret_cost035 = 왕복 0.35% · total_ret_cost100 = 왕복 1.0%(코스닥 소형주 현실 비용 가정) · total_ret_delist90 = 시세가 끊긴 종목을 마지막 가격 −90% 로 평가·청산 · slots_gone = 그 영향을 받은 슬롯 수"},
                   "accounts": {aid: {"name": NAMES[aid], "summary": summary[aid], "nav": [[d, round(float(v), 6)] for d, v in zip(dates, accounts[aid][0]["nav"])]} for aid in accounts}}
        def _clean(x):                                   # [Codex 검토 2] NaN/inf 는 null 로 — 브라우저 JSON.parse 가 NaN 을 거부한다
            if isinstance(x, dict): return {k: _clean(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)): return [_clean(v) for v in x]
            if isinstance(x, float) and not math.isfinite(x): return None
            return x
        json_path.write_text(json.dumps(_clean(payload), ensure_ascii=False, allow_nan=False), encoding="utf-8")
        print(f"  ✓ {db_path.name} · {json_path.name} ({time.time()-t0:.0f}s)")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--start", default=START_DEFAULT); ap.add_argument("--no-write", action="store_true"); ap.add_argument("--draws", type=int, default=N_DRAWS_DEFAULT)
    ap.add_argument("--out", default=None, help="산출물(paper_account.db·json)을 이 폴더에 — 0-diff 대조용")
    a = ap.parse_args()
    try:
        run(a.start, write=not a.no_write, n_draws=a.draws, out_dir=a.out)
    except BaseException as e:                       # SystemExit·KeyboardInterrupt 포함 — 배치를 절대 막지 않는다
        print(f"⚠ paper_account 실패(비치명): {e!r}")
    sys.exit(0)
