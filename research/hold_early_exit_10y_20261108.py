# -*- coding: utf-8 -*-
"""조기 매도 규칙 — 11년 대리 검증 (2026-11-08, 관측·읽기 전용 · 채택 아님). `hold_early_exit_20261108.py`(v30 실제 5개월)의 짝.

10년 DB(ohlcv_10y.db, 2015~, 폐지 포함·수정주가)만 읽는다. 틀은 `pick_exec_hold_10y_20261030.py` 그대로:
정리 유니버스 · 과매도 대리 = 20일 수익 하위 20%(v30 점수 아님) · 신호일 5거래일 간격 · 거래량 0·동전주 제외 · 상폐 = 마지막 가격 · 동일가중 · 월 블록 부트스트랩 2,000회 seed 7.
진입 t+1 종가, 규칙은 v30 쪽과 같음(A40·A20·A10·U5_20·U5_5·U20·UP20+·TP10/15/20), 비용 왕복 0.35%.
잣대 ①(창 수익, 판 뒤 현금) · ③(판 돈을 남은 날 '전 종목 바구니' 평균 일수익률로 재투자 + 비용 1번) — 둘 다 과매도 바구니 − 전 종목 바구니(같은 규칙 적용) 초과도.
출력: research/out_hold_early_exit/tenyr_*.csv. 실행 약 2~3분."""
import os, sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
OUT = HERE / "out_hold_early_exit"; OUT.mkdir(exist_ok=True)
STEP = 5; SPLIT = "20210101"; H = 40; COST = 0.0035; rng = np.random.default_rng(7)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
pd.set_option("display.width", 240)

def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5))

t0 = time.time()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index()
con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
dates = list(close.index); N = len(dates); tick = list(close.columns)
ks_r20 = (ks / ks.shift(20) - 1).reindex(dates)
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, vol
tick = list(cu.columns)
dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
cf = cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()
r20 = cu / cu.shift(20) - 1
penny = cu < 1000
CF = cf.values; CU = cu.values; VU = vu.fillna(0).values; PEN = penny.fillna(True).values; R20 = r20.values
print(f"유니버스 {cu.shape[1]} 종목 · 날 {N} · {time.time()-t0:.0f}s")

RULES = ["A40", "A20", "A10", "U5_20", "U5_5", "U20", "UP20+", "TP10", "TP15", "TP20"]
def exit_days(P):
    """P: (n종목, 41) 진입가=1 경로 → {rule: k 배열}"""
    up = P > 1.0; n = P.shape[0]; out = {}
    out["A40"] = np.full(n, H); out["A20"] = np.full(n, 20); out["A10"] = np.full(n, 10)
    out["U5_20"] = np.where(up[:, 5], 20, H); out["U5_5"] = np.where(up[:, 5], 5, H); out["U20"] = np.where(up[:, 20], 20, H)
    w = up[:, 20:]; first = np.where(w.any(1), w.argmax(1) + 20, H); out["UP20+"] = first
    for th in (10, 15, 20):
        w = P[:, 1:] >= 1 + th / 100; out[f"TP{th}"] = np.where(w.any(1), w.argmax(1) + 1, H)
    return out

rows = []
for i in range(130, N - H - 1, STEP):
    r = R20[i]
    v0 = (VU[i] == 0) | (VU[i + 1] == 0)
    e = CU[i + 1]; path = CF[i + 1:i + 2 + H].T       # (종목, 41)
    ok = ~np.isnan(r) & ~v0 & ~PEN[i] & ~np.isnan(e) & (e > 0) & ~np.isnan(path).any(1)
    if ok.sum() < 300: continue
    d = dates[i]; A = bool(ks_r20.iloc[i] == ks_r20.iloc[i] and ks_r20.iloc[i] <= -0.05)
    thr = np.quantile(r[ok], 0.20); os_ = ok & (r <= thr)
    P = path / e[:, None]
    Pos, Pall = P[os_], P[ok]
    Kos, Kall = exit_days(Pos), exit_days(Pall)
    all40_daily = (Pall[:, H].mean() - 1 - COST) / H           # 재투자 근사: 그날 전 종목 바구니의 40일 평균 일수익률(비용 뒤)
    row = dict(date=d, month=d[:6], i=i, A=A, half=("앞" if d < SPLIT else "뒤"), n_os=int(os_.sum()))
    for rl in RULES:
        for tag, PP, K in (("os", Pos, Kos[rl]), ("all", Pall, Kall[rl])):
            g = PP[np.arange(len(K)), K] - 1 - COST
            rv = (1 + g) * (1 + np.where(K < H, all40_daily * (H - K) - COST, 0.0)) - 1
            row[f"{tag}_win_{rl}"] = g.mean() * 100; row[f"{tag}_reinv_{rl}"] = rv.mean() * 100; row[f"{tag}_k_{rl}"] = K.mean()
        row[f"exc_win_{rl}"] = row[f"os_win_{rl}"] - row[f"all_win_{rl}"]; row[f"exc_reinv_{rl}"] = row[f"os_reinv_{rl}"] - row[f"all_reinv_{rl}"]
    rows.append(row)
R = pd.DataFrame(rows); R.to_csv(OUT / "tenyr_days.csv", index=False, encoding="utf-8-sig")
print(f"신호일 {len(R)} · {time.time()-t0:.0f}s")
SCOPES = (("전체", R), ("코스피 급락 날", R[R.A]), ("그 밖", R[~R.A]), ("앞반 2015~20", R[R.half == "앞"]), ("뒤반 2021~", R[R.half == "뒤"]))
out = []
for scope, sub in SCOPES:
    for metric, lab in (("os_win", "① 과매도 창 수익(%)"), ("exc_win", "① 창 초과(%p)"), ("os_reinv", "③ 과매도 창 수익+재투자(%)"), ("exc_reinv", "③ 창 초과+재투자(%p)")):
        base = sub[f"{metric}_A40"]
        for rl in RULES:
            v = sub[f"{metric}_{rl}"]; d_ = v - base
            lo, hi = block_ci(v, sub.month); dlo, dhi = block_ci(d_, sub.month) if rl != "A40" else (np.nan, np.nan)
            out.append(dict(범위=scope, 잣대=lab, rule=rl, 날수=len(sub), 평균=v.mean(), 하한=lo, 상한=hi, A40대비=d_.mean(), 차하한=dlo, 차상한=dhi,
                            양수비율=(v > 0).mean() * 100, 평균보유=sub[f"os_k_{rl}"].mean()))
T = pd.DataFrame(out); T.to_csv(OUT / "tenyr_summary.csv", index=False, encoding="utf-8-sig")
for (scope, lab), g in T.groupby(["범위", "잣대"], sort=False):
    print(f"\n### {scope} · {lab} (신호일 {g.날수.iloc[0]})")
    print(g[["rule", "평균", "하한", "상한", "A40대비", "차하한", "차상한", "양수비율", "평균보유"]].round(2).to_string(index=False))
print(f"\n{time.time()-t0:.0f}s")
