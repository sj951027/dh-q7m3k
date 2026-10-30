# -*- coding: utf-8 -*-
"""실험 E3 1단계 — 국면 스위치(급락 뒤엔 과매도, 그 밖엔 저변동) 11년 대리 되감기 (2026-10-30, 사후 관측 · 채택 아님)

history.db 의 v30·lv_b 실제 목록은 2026-05/06 부터라 11년 DB 대리로 본다:
  과매도(v30 대리) = 그날 유니버스 20일 수익 하위 20% · 저변동(lv_b 대리) = 60일 일수익 표준편차 하위 20%(최소 40일) · 전 종목.
  스위치 S1: 코스피 R20 ≤ −5%(A 칸) 신호일 → 과매도, 그 밖 → 저변동.  스위치 S2: 코스피 R20 > +5%(D 칸) → 저변동, 그 밖 → 과매도.
틀은 `pick_exclude_10y_20261030.py` 와 같다(정리 유니버스 · 거래량 0·동전주 제외 · 40일 안 상폐 = 마지막 가격 · 신호일 5거래일 간격 · t+1 종가 매수 → t+41 종가 매도 · 동일가중 · 월 블록 부트스트랩 2,000회 seed 7).
칸은 신호일 t 종가의 R20 (운영 PTW 는 전 거래일 기준 — 대리라 t 로 통일, 한계에 적음).
재현: python research/regime_switch_proxy_10y_20261030.py → research/out_regime_switch/*.csv (약 30초)."""
import os, sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("DH_REPO", HERE.parent))
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
OUT = Path(os.environ.get("OUT_DIR", HERE / "out_regime_switch")); OUT.mkdir(exist_ok=True, parents=True)
H = 40; STEP = 5; SPLIT = "20210101"; rng = np.random.default_rng(7)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)


def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    if len(um) < 2 or len(vals) < 2:
        return (np.nan, np.nan)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


def nonov(pos, gap=H):
    c = 0; last = -10 ** 9
    for p in sorted(pos):
        if p - last >= gap:
            c += 1; last = p
    return c


t0 = time.time()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index()
con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
dates = list(close.index); N = len(dates); tick = list(close.columns)
ks_r20 = ((ks / ks.shift(20) - 1) * 100).reindex(dates)
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, vol
tick = list(cu.columns)
dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
cf = cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()
fwd = (cf.shift(-1 - H) / cu.shift(-1) - 1) * 100; del cf
ret = cu.pct_change(fill_method=None)
r20 = cu / cu.shift(20) - 1
vol60 = ret.rolling(60, min_periods=40).std()
penny = cu < 1000
print(f"유니버스 {cu.shape[1]} · 날 {N} · {time.time()-t0:.0f}s")

rows = []
for i in range(130, N - H - 1, STEP):
    f = fwd.iloc[i]; r = r20.iloc[i]; v = vol60.iloc[i]
    v0 = (vu.iloc[i].fillna(0) == 0) | (vu.iloc[i + 1].fillna(0) == 0)
    ok = f.notna() & r.notna() & v.notna() & ~v0 & ~penny.iloc[i].fillna(True)
    if ok.sum() < 300:
        continue
    d = dates[i]; k = ks_r20.iloc[i]
    if k != k:
        continue
    os_ = ok & (r <= r[ok].quantile(0.20)); lv = ok & (v <= v[ok].quantile(0.20))
    cell = "A" if k <= -5 else ("D" if k > 5 else "BC")
    o, l, a = float(f[os_].mean()), float(f[lv].mean()), float(f[ok].mean())
    rows.append(dict(date=d, month=d[:6], i=i, cell=cell, half=("앞" if d < SPLIT else "뒤"), ks_r20=k, all=a, os=o, lv=l,
                     S1=(o if cell == "A" else l), S2=(l if cell == "D" else o), overlap=float((os_ & lv).sum() / max(1, os_.sum()))))
R = pd.DataFrame(rows); R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
print(f"신호일 {len(R)} · 비겹침 {nonov(R.i)} · 칸별 날수 {R.cell.value_counts().to_dict()} · 과매도∩저변동 겹침 {R.overlap.mean()*100:.1f}% · {time.time()-t0:.0f}s")

print("\n[1] 칸별 — 40일 바구니(%): 전 종목 · 과매도 · 저변동 · (과매도 − 저변동) [월블록 95%]")
out = []
for scope, sub in (("전체", R), ("A 급락 뒤(≤−5)", R[R.cell == "A"]), ("B·C 보통(−5~+5)", R[R.cell == "BC"]), ("D 급등 뒤(>+5)", R[R.cell == "D"]),
                   ("앞반 2015~20", R[R.half == "앞"]), ("뒤반 2021~", R[R.half == "뒤"])):
    if len(sub) < 8:
        continue
    d = sub.os - sub.lv; lo, hi = block_ci(d, sub.month)
    out.append(dict(범위=scope, 날수=len(sub), 비겹침=nonov(sub.i), 전종목=sub["all"].mean(), 과매도=sub.os.mean(), 저변동=sub.lv.mean(), 과매도_저변동=d.mean(), 하한=lo, 상한=hi, 양수비율=(d > 0).mean() * 100,
                    과매도초과=(sub.os - sub["all"]).mean(), 저변동초과=(sub.lv - sub["all"]).mean()))
T1 = pd.DataFrame(out); print(T1.round(2).to_string(index=False)); T1.to_csv(OUT / "by_cell.csv", index=False, encoding="utf-8-sig")

print("\n[2] 스위치 규칙 — 40일 바구니 평균과 단독 대비 차이 [월블록 95%]")
out = []
for scope, sub in (("전체", R), ("앞반 2015~20", R[R.half == "앞"]), ("뒤반 2021~", R[R.half == "뒤"])):
    for rule in ("S1", "S2"):
        d1 = sub[rule] - sub.os; d2 = sub[rule] - sub.lv; d3 = sub[rule] - sub["all"]
        out.append(dict(범위=scope, 규칙=rule, 날수=len(sub), 스위치=sub[rule].mean(), 과매도=sub.os.mean(), 저변동=sub.lv.mean(), 전종목=sub["all"].mean(),
                        vs과매도=d1.mean(), CI1=block_ci(d1, sub.month), vs저변동=d2.mean(), CI2=block_ci(d2, sub.month), vs전종목=d3.mean(), CI3=block_ci(d3, sub.month),
                        스위치_표준편차=sub[rule].std(), 과매도_표준편차=sub.os.std(), 저변동_표준편차=sub.lv.std()))
T2 = pd.DataFrame(out)
T2["CI1"] = T2.CI1.apply(lambda c: f"[{c[0]:+.2f}, {c[1]:+.2f}]"); T2["CI2"] = T2.CI2.apply(lambda c: f"[{c[0]:+.2f}, {c[1]:+.2f}]"); T2["CI3"] = T2.CI3.apply(lambda c: f"[{c[0]:+.2f}, {c[1]:+.2f}]")
print(T2.round(2).to_string(index=False)); T2.to_csv(OUT / "switch.csv", index=False, encoding="utf-8-sig")
print(f"\n끝 {time.time()-t0:.0f}s")
