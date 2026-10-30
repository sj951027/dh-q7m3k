# -*- coding: utf-8 -*-
"""갈래 다 — 모의 계좌 장부로 J06·J10 사실 확인 (2026-10-31, 사후 관측 · 채택 아님)

J06 목록 부족: 앵커(추천일)마다 뽑힌 종목 수가 20(시장별 10)에 못 미칠 때 현재 엔진은 슬롯 돈(NAV/40)을 **뽑힌 수로 나눠** 넣는다(= 재분배). 못 사는 종목(정지·상한가·가격 없음) 몫은 **현금**(대체 없음).
  → 센다: 앵커별 목록 크기 분포 · 실제 진입 수 · 못 산 수(사유별) · 재분배로 한 종목 몫이 기본(0.125% NAV)보다 커진 비율.
J10 못 파는 날 청산: 엔진은 40일째 무조건 마지막 유효 종가로 판다. → 청산일에 `is_suspended=1` 이던 슬롯 수(팔 수 없었을 가능성)와 그 손익.
대상 계좌: v30 · lv_b · lv_e · sv_a · le_a · sv_b · switch. 재현: python research/paper_slot_gaps_20261031.py → research/out_slot_gaps/ (20초). DB 읽기만."""
import os, sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent))
import leaderboard as lb, regime_ad, paper_engine as pe, paper_account as pa
OUT = HERE / "out_slot_gaps"; OUT.mkdir(exist_ok=True)
pd.set_option("display.width", 240); LOG = []


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


t0 = time.time()
close, tradable, shares, mkt = pa.load_prices()
dates_all = list(close.index); didx_all = {d: i for i, d in enumerate(dates_all)}
ks = regime_ad.load_index("KOSPI", lb.OHLCV_DB); cells = regime_ad.classify(ks)["cell"]
excl = pa.load_gates(dates_all); start = pa.START_DEFAULT
i0 = next(i for i, d in enumerate(dates_all) if d >= start); dates = dates_all[i0:]; sub = close.loc[dates]; trd = tradable.loc[dates]
picks = {d: v for d, v in pa.v30_picks(dates_all, didx_all, excl).items() if d >= start}
mp = {}
for mid in pa.MODEL_ACCOUNTS:
    tb, col = pa.MODEL_SRC[mid]; mp[mid] = {d: v for d, v in pa.model_picks(mid, tb, col, dates_all, didx_all, excl, reg=None).items() if d >= start}
sw, _ = pe.switch_picks(dates, cells.reindex(dates), picks, mp["lv_b"], a_cells=pa.SWITCH_A_CELLS)
defs = {"v30": picks, **{m: mp[m] for m in pa.MODEL_ACCOUNTS}, pa.SWITCH_ID: sw}
con = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
susp = pd.read_sql("SELECT ticker, date FROM daily_ohlcv WHERE is_suspended>0 AND date>=?", con, params=(start,)); con.close()
susp["ticker"] = susp.ticker.astype(str).str.zfill(6); susp_set = set(zip(susp.ticker, susp.date))
didx = {d: i for i, d in enumerate(dates)}; cols = set(sub.columns)
say(f"되감기 {dates[0]}~{dates[-1]} · 계좌 {len(defs)} · 정지 행 {len(susp)} · {time.time()-t0:.0f}s")

rows = []
for aid, pk in defs.items():
    nav, led = pe.simulate(dates, sub, pk, tradable=trd)
    L = pd.DataFrame(led) if led else pd.DataFrame(columns=["run", "ticker", "exit_date", "ret", "status", "invested"])
    ent_by_run = L.groupby("run").size() if len(L) else pd.Series(dtype=int)
    sizes, entered, skip_price, skip_trd, skip_absent = [], [], 0, 0, 0
    for rid, lst in pk.items():
        t = didx.get(rid)
        if t is None or t + 1 >= len(dates):
            continue
        e = t + 1; sizes.append(len(lst)); entered.append(int(ent_by_run.get(rid, 0)))
        for tk in lst:
            if tk not in cols:
                skip_absent += 1; continue
            px = sub.iloc[e][tk]
            if not (px == px and px > 0):
                skip_price += 1; continue
            if not bool(trd.iloc[e][tk]):
                skip_trd += 1
    sizes = np.array(sizes); entered = np.array(entered)
    short = (sizes < 20).mean() if len(sizes) else np.nan
    boost = (20 / np.maximum(sizes, 1)).mean() if len(sizes) else np.nan           # 재분배로 한 종목 몫이 기본의 몇 배가 되나(평균)
    cl = L[L.status == "closed"] if len(L) else L
    cl_s = cl[[(tk, d) in susp_set for tk, d in zip(cl.ticker, cl.exit_date)]] if len(cl) else cl
    rows.append(dict(account=aid, anchors=len(sizes), list_median=float(np.median(sizes)) if len(sizes) else np.nan, list_min=int(sizes.min()) if len(sizes) else 0,
                     anchors_short=float(short), per_pos_boost=float(boost), picks_total=int(sizes.sum()), entered=int(entered.sum()),
                     skip_untradable=skip_trd, skip_no_price=skip_price, skip_absent=skip_absent,
                     closed=len(cl), closed_on_suspended=len(cl_s), susp_ret_mean=float(cl_s.ret.mean() * 100) if len(cl_s) else np.nan,
                     susp_invested_pct=float(cl_s.invested.sum() * 100) if len(cl_s) else 0.0))
    say(f"\n== {aid} == 앵커 {len(sizes)} · 목록 크기 중앙 {np.median(sizes):.0f}(최소 {sizes.min()}) · 20 미만 앵커 {short:.0%} · 재분배 배율 평균 {boost:.2f}")
    say(f"  뽑힘 {sizes.sum()} → 진입 {entered.sum()} · 못 삼: 정지/상한가 {skip_trd} · 가격 없음 {skip_price} · 시세표에 없음 {skip_absent}")
    say(f"  끝난 슬롯 {len(cl)} 중 청산일 정지 {len(cl_s)}" + (f" · 그 수익 평균 {cl_s.ret.mean()*100:+.1f}% · 투자금 합 NAV 의 {cl_s.invested.sum()*100:.2f}%" if len(cl_s) else ""))
    if len(cl_s):
        say(cl_s[["run", "ticker", "exit_date", "ret"]].assign(ret=lambda x: (x.ret * 100).round(1)).to_string(index=False))
S = pd.DataFrame(rows); S.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
say("\n== 요약 =="); say(S.round(3).to_string(index=False))
(OUT / "run_20261031.txt").write_text("\n".join(LOG), encoding="utf-8"); say(f"\n끝 {time.time()-t0:.0f}s")
