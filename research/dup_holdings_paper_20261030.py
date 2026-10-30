# -*- coding: utf-8 -*-
"""갈래 나 첫 실험 — J07 같은 종목 중복 보유: 모의 계좌 장부에서 '날마다 상위 10 이 겹쳐 한 종목에 돈이 몰린 정도'와 그 손익 (2026-10-30 밤, 사후 관측 · 채택 아님)

출처: Codex REPLY_20261030_idea_scan.md J07(종목×돈). 모의 계좌 2판 규칙 그대로(슬롯 40 · t+1 종가 · 40일 · 비용 0.5% · 되감기 20260810~)로 장부를 다시 만들고(쓰기 없음) 센다.
설계(결과 보기 전 고정):
  ① 진입 단위: 그 종목을 **이미 보유 중**(열린 슬롯 ≥1)인 상태에서 들어간 진입 = '중복 진입'. 비율, 동시 보유 슬롯 수 분포.
  ② 날 단위: 한 종목에 몰린 돈 = 그 종목 포지션 평가액 합 / NAV 의 그날 최대값(top1), 상위 3종목 합(top3), 보유 슬롯 수 대비 종목 수.
  ③ 손익: 끝난 슬롯에서 첫 진입 vs 중복 진입의 평균 수익(비용 뒤) · 중복 진입 슬롯의 NAV 기여(투자금×수익 합, 시작 NAV 대비 %p — 복리 무시한 근사).
  ④ 가상 규칙(J07) 근사: 중복 진입을 건너뛰고 현금으로 두었다면 = 총손익 − 중복 슬롯 기여(근사, 재투자 없음). 계좌를 새로 만들지 않는다.
대상 계좌: v30 · lv_b · lv_e · sv_a · le_a · sv_b · switch_v30_lvb · B1_bigcap(비교 — 같은 대형주가 날마다 뽑히는 극단). B0 시장 전체는 제외.
재현: python research/dup_holdings_paper_20261030.py → research/out_dup_holdings/ (약 30초). DB 읽기만."""
import os, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import leaderboard as lb, regime_ad, paper_engine as pe, paper_account as pa

OUT = Path(os.environ.get("OUT_DIR", HERE / "out_dup_holdings")); OUT.mkdir(exist_ok=True, parents=True)
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)
LOG = []


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


t0 = time.time()
close, tradable, shares, mkt = pa.load_prices()
dates_all = list(close.index); didx_all = {d: i for i, d in enumerate(dates_all)}
ks = regime_ad.load_index("KOSPI", lb.OHLCV_DB); cells = regime_ad.classify(ks)["cell"]
excl = pa.load_gates(dates_all)
start = pa.START_DEFAULT
i0 = next(i for i, d in enumerate(dates_all) if d >= start)
dates = dates_all[i0:]; sub = close.loc[dates]; trd = tradable.loc[dates]
picks = {d: v for d, v in pa.v30_picks(dates_all, didx_all, excl).items() if d >= start}
mp = {}
for mid in pa.MODEL_ACCOUNTS:
    tb, col = pa.MODEL_SRC[mid]
    mp[mid] = {d: v for d, v in pa.model_picks(mid, tb, col, dates_all, didx_all, excl, reg=None).items() if d >= start}
b0, b1, b2, _ = pa.bench_picks(dates, close, trd, shares, mkt, 1)
sw, _ = pe.switch_picks(dates, cells.reindex(dates), picks, mp["lv_b"], a_cells=pa.SWITCH_A_CELLS)
defs = {"v30": picks, **{m: mp[m] for m in pa.MODEL_ACCOUNTS}, pa.SWITCH_ID: sw, "B1_bigcap": b1}   # B0(시장 전체)는 하루 2,600종목이라 질문과 무관·제외
say(f"시세 {sub.shape} · 되감기 {dates[0]}~{dates[-1]} · 계좌 {len(defs)} · {time.time()-t0:.0f}s")

arr = sub.ffill().to_numpy(float); cols = {t: k for k, t in enumerate(sub.columns)}
N = len(dates)
summary = []
for aid, pk in defs.items():
    nav, led = pe.simulate(dates, sub, pk, tradable=trd)
    if not led:
        say(f"{aid}: 슬롯 없음"); continue
    L = pd.DataFrame(led).sort_values(["entry_i", "ticker"]).reset_index(drop=True)
    # ① 중복 진입: 진입 시점에 같은 종목의 열린 슬롯 수 k
    k_open = np.zeros(len(L), dtype=int)
    for _, g in L.groupby("ticker"):                                     # 종목별로만 비교(시장 전체 계좌에서 n² 이 되던 것 수정)
        e, x = g.entry_i.to_numpy(), g.exit_i.to_numpy()
        for j, idx in enumerate(g.index):
            k_open[idx] = int(((e < e[j]) & (x > e[j])).sum())
    L["k_open"] = k_open; L["dup"] = L.k_open >= 1
    # ② 날 단위 집중
    conc = []
    for i in range(N):
        op = L[(L.entry_i <= i) & (L.exit_i > i)]
        if not len(op):
            conc.append(dict(date=dates[i], n_pos=0, n_tk=0, top1=0.0, top3=0.0, top1_tk="")); continue
        val = op.shares.values * arr[i, op.col.values]
        byt = pd.Series(val, index=op.ticker.values).groupby(level=0).sum().sort_values(ascending=False)
        navv = float(nav.nav.iloc[i])
        conc.append(dict(date=dates[i], n_pos=len(op), n_tk=len(byt), top1=float(byt.iloc[0] / navv), top3=float(byt.iloc[:3].sum() / navv), top1_tk=byt.index[0]))
    C = pd.DataFrame(conc); C.to_csv(OUT / f"{aid}_daily.csv", index=False, encoding="utf-8-sig")
    L.to_csv(OUT / f"{aid}_entries.csv", index=False, encoding="utf-8-sig")
    # ③ 손익
    if "ret" not in L.columns:
        L["ret"] = np.nan                                                # 끝난 슬롯이 하나도 없는 계좌(sv_b 등)
    cl = L[L.status == "closed"]
    first, dup = cl[~cl.dup], cl[cl.dup]
    contrib_dup = float((dup.invested * dup.ret).sum() * 100)               # 시작 NAV=1 → %p
    contrib_all = float((cl.invested * cl.ret).sum() * 100)
    tot = float((nav.nav.iloc[-1] / nav.nav.iloc[0] - 1) * 100)
    s = dict(account=aid, slots=len(L), closed=len(cl), dup_share=float(L.dup.mean()), k_max=int(L.k_open.max()),
             k_ge2_share=float((L.k_open >= 2).mean()), distinct_tickers=int(L.ticker.nunique()),
             top1_mean=float(C.top1.mean()), top1_max=float(C.top1.max()), top1_max_tk=str(C.loc[C.top1.idxmax(), "top1_tk"]), top1_max_date=str(C.loc[C.top1.idxmax(), "date"]),
             top3_mean=float(C.top3.mean()), n_tk_over_n_pos=float((C.n_tk / C.n_pos.replace(0, np.nan)).mean()),
             ret_first=float(first.ret.mean() * 100) if len(first) else np.nan, n_first=len(first),
             ret_dup=float(dup.ret.mean() * 100) if len(dup) else np.nan, n_dup=len(dup),
             contrib_dup_pp=contrib_dup, contrib_all_pp=contrib_all, total_ret=tot, total_if_skip_dup=tot - contrib_dup)
    summary.append(s)
    say(f"\n== {aid} · 슬롯 {s['slots']}(끝남 {s['closed']}) · 종목 {s['distinct_tickers']} ==")
    say(f"  중복 진입 비율 {s['dup_share']:.1%} · 동시 보유 슬롯 최대 {s['k_max']+1} · 3슬롯 이상 겹친 진입 {s['k_ge2_share']:.1%}")
    say(f"  한 종목 몰림 top1 평균 {s['top1_mean']:.1%} · 최대 {s['top1_max']:.1%}({s['top1_max_tk']} {s['top1_max_date']}) · top3 평균 {s['top3_mean']:.1%} · 종목수/슬롯수 {s['n_tk_over_n_pos']:.2f}")
    say(f"  끝난 슬롯 수익: 첫 진입 {s['ret_first']:+.2f}%(n={s['n_first']}) · 중복 진입 {s['ret_dup']:+.2f}%(n={s['n_dup']}) · 중복 기여 {contrib_dup:+.2f}%p / 전체 기여 {contrib_all:+.2f}%p · 계좌 {tot:+.2f}% → 중복 건너뛰면(근사) {tot-contrib_dup:+.2f}%")
    top = L.groupby("ticker").size().sort_values(ascending=False).head(5)
    say("  가장 자주 뽑힌 종목(슬롯 수): " + " · ".join(f"{t} {n}" for t, n in top.items()))

S = pd.DataFrame(summary); S.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
say("\n== 요약 ==")
say(S[["account", "slots", "distinct_tickers", "dup_share", "k_max", "top1_mean", "top1_max", "top3_mean", "ret_first", "ret_dup", "n_dup", "contrib_dup_pp", "total_ret", "total_if_skip_dup"]].round(3).to_string(index=False))
(OUT / "run_20261030.txt").write_text("\n".join(LOG), encoding="utf-8")
say(f"\n끝 {time.time()-t0:.0f}s → {OUT}")
