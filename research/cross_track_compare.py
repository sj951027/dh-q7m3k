# -*- coding: utf-8 -*-
"""
cross_track_compare.py — 트랙 간 '공통 잣대' 모의계좌 비교 (§14 탐색·관측 전용, 2026-08-14)
=============================================================================================
문제: 리더보드의 IC·초과%p는 각자 '자기 유니버스' 기준이라 트랙 간 직접 비교 불가.
해법: 잣대 통일 — **같은 기간 · 같은 규칙(매일 상위20 동일가중, ENTRY_LAG=1) · 같은 벤치마크
      (전체 상장 가드 EW · KOSPI)** 로 모의 계좌를 돌려 절대수익/공통초과/변동성/MDD 비교.
정직성: 판정(§11) 아님 — 관측. 공통 창이 짧아(수십 거래일) 노이즈 크고, 거래비용·슬리피지
      미반영, 상위20 매일 리밸런스는 실거래보다 회전 큼. 등록일 이후 forward 점수만 사용.
실행: python research/cross_track_compare.py
"""
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
hc = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
oc = sqlite3.connect(f"file:{HERE.parent/'dh-q7m3k-data'/'ohlcv.db'}?mode=ro", uri=True)

# (모델, 테이블, 점수컬럼, 모델컬럼값, REG_DATE)
MODELS = [
    ("v30",    "v3_scores",     "final_score_v3", "v30",   "20260606"),
    ("lv_b",   "lowvol_scores", "lowvol_score",   "lv_b",  "20260625"),
    ("lv_a",   "lowvol_scores", "lowvol_score",   "lv_a",  "20260625"),
    ("mom_a",  "lowvol_scores", "lowvol_score",   "mom_a", "20260627"),
    ("wu_a",   "wu_scores",     "wu_score",       "wu_a",  "20260702"),
    ("sv_a",   "wu_scores",     "wu_score",       "sv_a",  "20260715"),
    ("qs_a",   "wu_scores",     "wu_score",       "qs_a",  "20260723"),
]
TOPN = 20

print("[로드] 점수")
scores = {}
for name, tbl, col, mid, reg in MODELS:
    df = pd.read_sql(f"SELECT run_id, ticker, {col} AS s FROM {tbl} "
                     f"WHERE model_id=? AND run_id>=?", hc, params=(mid, reg))
    scores[name] = df
    print(f"  {name}: {df.run_id.nunique()} runs ({df.run_id.min()}~{df.run_id.max()})")

tk = sorted(set().union(*[set(d.ticker) for d in scores.values()]))
ph = ",".join("?" * len(tk))
px = pd.read_sql(f"SELECT ticker,date,close,volume,change_pct FROM daily_ohlcv WHERE date>='20260601'", oc)
dts = sorted(px.date.unique())
R = px.pivot_table(index="date", columns="ticker", values="change_pct", aggfunc="last").reindex(dts)
C = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").reindex(dts)
V = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(dts)
amt20 = (C * V).rolling(20, min_periods=10).mean() / 1e8
K = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSPI'", oc).set_index("date")["close"].reindex(dts).ffill()

def sim(name, start, end):
    """start~end 구간: 각 거래일 t의 점수 상위 TOPN → t+1 일수익(동일가중). NAV·지표."""
    df = scores[name]
    rets = []
    days = [d for d in dts if start <= d <= end]
    for t in days:
        sub = df[df.run_id == t]
        if len(sub) == 0:
            i = dts.index(t)
            if i + 1 < len(dts):
                rets.append((dts[i + 1], np.nan))
            continue
        top = sub.nlargest(TOPN, "s").ticker
        i = dts.index(t)
        if i + 1 >= len(dts):
            continue
        nxt = dts[i + 1]
        r = R.loc[nxt, [c for c in top if c in R.columns]].astype(float)
        rets.append((nxt, float(r.mean(skipna=True))))
    s = pd.Series(dict(rets)).sort_index()
    s = s.ffill(limit=2).fillna(0)  # 결측 run(주말 인접 등)은 보수적으로 0
    nav = (1 + s).cumprod()
    mdd = float((nav / nav.cummax() - 1).min())
    return s, dict(cum=float(nav.iloc[-1] - 1) * 100, vol=float(s.std()) * 100,
                   mdd=mdd * 100, n=len(s))

def bench(start, end):
    days = [d for d in dts if start <= d <= end]
    out = []
    for t in days:
        i = dts.index(t)
        if i + 1 >= len(dts):
            continue
        nxt = dts[i + 1]
        g = amt20.loc[t] >= 5
        out.append((nxt, float(R.loc[nxt, g[g].index].astype(float).mean(skipna=True))))
    s = pd.Series(dict(out)).sort_index()
    nav = (1 + s).cumprod()
    return s, float(nav.iloc[-1] - 1) * 100

for label, group, start in [
    ("A: 7/02~ (v30·lv·mom·wu 공통창)", ["v30", "lv_b", "lv_a", "mom_a", "wu_a"], "20260702"),
    ("B: 7/24~ (전 모델 공통창 — 매우 짧음)", ["v30", "lv_b", "lv_a", "mom_a", "wu_a", "sv_a", "qs_a"], "20260724"),
]:
    end = dts[-2]
    bs, bcum = bench(start, end)
    k0, k1 = K.loc[[d for d in dts if d >= start][0]], K.iloc[-1]
    kospi_cum = (k1 / k0 - 1) * 100
    print(f"\n===== 패널 {label} → {end} · 공통벤치(전체상장 가드EW) {bcum:+.1f}% · KOSPI {kospi_cum:+.1f}% =====")
    rows = []
    for m in group:
        s, st = sim(m, start, end)
        common = s.index.intersection(bs.index)
        exc = float((s.reindex(common) - bs.reindex(common)).mean()) * 100
        sharpe = st["cum"] / st["vol"] / np.sqrt(st["n"]) if st["vol"] > 0 else np.nan
        rows.append(dict(model=m, 누적수익pct=st["cum"], 공통벤치초과_일평균bp=exc * 100,
                         일변동성pct=st["vol"], MDD=st["mdd"], n일=st["n"]))
    out = pd.DataFrame(rows).sort_values("누적수익pct", ascending=False)
    print(out.to_string(index=False, float_format=lambda x: f"{x:+.2f}"))

print("\n⚠ 관측 전용 — §11 판정 아님. 공통 창이 짧고(특히 B), 거래비용 0 가정, 매일 top20")
print("  전량 리밸런스(실거래보다 회전 큼). '이 기간 이 장에서'의 성적일 뿐 일반화 금지.")
