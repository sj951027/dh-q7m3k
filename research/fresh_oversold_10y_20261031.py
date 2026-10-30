# -*- coding: utf-8 -*-
"""갈래 나 — '목록에 처음 올라온 과매도(fresh)' vs '머물러 있는 과매도(stale)' 11년 정리 바구니 — Claude 독립 계산 (2026-10-31, 사후 관측 · 채택 아님)

요청서 research/handoff/REQUEST_20261031_fresh_oversold_blind.md 의 정의 그대로(Codex 답은 이 계산이 끝난 뒤 §7 에서 맞춘다):
  과매도(t) = 조건 통과 종목(t·t+1 양수 종가·거래량, ≥1,000원, R20 유효) 중 R20 하위 20%.
  fresh = 과매도(t) ∧ t−5(직전 격자일) 조건 통과 ∧ t−5 에 과매도 아님 · stale = 과매도(t) ∧ t−5 에도 과매도. t−5 조건 미달은 제외.
  감도① fresh' = 최근 5거래일(t−5~t−1) 어느 날도 과매도 아님(각 날 조건 통과) · 감도② stale10 = t−5·t−10 모두 과매도.
  결과 = t+1 → t+41 종가(%), 비용 없음, 상폐 = 마지막 가격(−90% 감도). 날 단위 동일가중(양쪽 다 있는 날) · 월 블록 2,000(seed 7) · A 사건(≥40 간격) 사건 부트스트랩 4,000(seed 20261030).
  깊이 맞춤 = 같은 날 과매도 R20 10분위 안에서 양쪽 다 있는 구간의 평균 차를 min(n) 가중 평균. 운용 번역 = (fresh − stale) × stale 비중.
재현: python research/fresh_oversold_10y_20261031.py → research/out_fresh_oversold/ (2분)."""
import sqlite3, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
DB10 = str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db")
OUT = HERE / "out_fresh_oversold"; OUT.mkdir(exist_ok=True)
H = 40; STEP = 5; SPLIT = "20210101"; A_TH = -5.0
rng = np.random.default_rng(7); rng_ev = np.random.default_rng(20261030)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
LOG = []


def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s)


def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    if len(um) < 2:
        return (np.nan, np.nan)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


def ev_ci(vals, k=4000):
    v = np.asarray(vals, float); v = v[~np.isnan(v)]; n = len(v)
    if n < 2:
        return (np.nan, np.nan)
    ms = [v[rng_ev.integers(0, n, n)].mean() for _ in range(k)]
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


t0 = time.time()
con = sqlite3.connect(f"file:{DB10}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index(); con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
dates = list(close.index); N = len(dates); tick = list(close.columns)
ks_r20 = ((ks / ks.shift(20) - 1) * 100).reindex(dates)
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, vol
tick = list(cu.columns); dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
cff = cu.copy(); cff.loc[:, dl] = cff.loc[:, dl].ffill()
fwd = (cff.shift(-1 - H) / cu.shift(-1) - 1) * 100
fwd90 = fwd.copy()                                                   # 상폐 −90% 감도: 상폐 종목의 40일 안 끊김은 −90 으로
last_i = cu.notna().cumsum().idxmax() if False else None
del cff
r20 = cu / cu.shift(20) - 1; penny = cu < 1000; v0 = vu.fillna(0) == 0
# 조건 통과 표(t): t·t+1 양수 종가/거래량 · ≥1000 · R20 유효  (벡터화)
okm = (~penny.fillna(True)) & (~v0) & (~v0.shift(-1).fillna(True)) & r20.notna() & cu.shift(-1).notna()
# 과매도 표(t): 조건 통과 중 R20 하위 20%
q20 = r20.where(okm).quantile(0.20, axis=1)
osm = okm & (r20.le(q20, axis=0))
# 상폐 −90%: 상폐 종목 중 t+41 전에 마지막 가격이 끊기는 경우 → fwd 를 −90 으로(마지막 저장 가격 대신)
lastpos = cu.apply(lambda s: s.last_valid_index())
li = pd.Series({t: (dates.index(d) if d is not None else -1) for t, d in lastpos.items()})
say(f"유니버스 {cu.shape[1]} · 날 {N} · {time.time()-t0:.0f}s")

rows = []
for i in range(130, N - H - 1, STEP):
    k = ks_r20.iloc[i]
    if k != k:
        continue
    d = dates[i]; o_t = osm.iloc[i]; ok_t = okm.iloc[i]
    if ok_t.sum() < 300:
        continue
    ok5, o5 = okm.iloc[i - 5], osm.iloc[i - 5]
    fresh = o_t & ok5 & ~o5; stale = o_t & o5
    ok10, o10 = okm.iloc[i - 10], osm.iloc[i - 10]
    stale10 = stale & o10
    any5 = osm.iloc[i - 5:i].any(); all5ok = okm.iloc[i - 5:i].all()
    fresh5 = o_t & all5ok & ~any5
    f = fwd.iloc[i]
    # 상폐 −90% 감도: 상폐 종목이고 마지막 유효가 i+41 보다 앞이면 −90
    gone = pd.Series(dl, index=tick) & (li.values < i + 1 + H) & (li.values >= i + 1)
    f90 = f.where(~gone, -90.0)
    if fresh.sum() == 0 or stale.sum() == 0:
        continue
    # 깊이 맞춤: 그날 과매도 R20 10분위
    rr = r20.iloc[i]; dec = pd.qcut(rr[o_t].rank(method="first"), 10, labels=False)
    num = den = 0.0
    for b in range(10):
        idx = dec.index[dec == b]; fi = idx[fresh[idx]]; si = idx[stale[idx]]
        if len(fi) and len(si):
            w = min(len(fi), len(si)); num += w * (f[fi].mean() - f[si].mean()); den += w
    match = num / den if den else np.nan
    rows.append(dict(date=d, month=d[:6], i=i, half=("앞" if d < SPLIT else "뒤"), ks_r20=float(k), cell=("A" if k <= A_TH else ("D" if k > 5 else "BC")),
                     n_os=int(o_t.sum()), n_fresh=int(fresh.sum()), n_stale=int(stale.sum()), n_fresh5=int(fresh5.sum()), n_stale10=int(stale10.sum()),
                     fresh=float(f[fresh].mean()), stale=float(f[stale].mean()), fresh5=float(f[fresh5].mean()) if fresh5.sum() else np.nan,
                     stale10=float(f[stale10].mean()) if stale10.sum() else np.nan, os_all=float(f[o_t].mean()),
                     fresh90=float(f90[fresh].mean()), stale90=float(f90[stale].mean()),
                     tail_fresh=float((f[fresh] <= -20).mean()), tail_stale=float((f[stale] <= -20).mean()),
                     p10_fresh=float(f[fresh].quantile(0.1)), p10_stale=float(f[stale].quantile(0.1)),
                     r20_fresh=float(rr[fresh].mean() * 100), r20_stale=float(rr[stale].mean() * 100), match=match))
R = pd.DataFrame(rows); R["diff"] = R.fresh - R.stale; R["diff5"] = R.fresh5 - R.stale; R["diff10"] = R.fresh - R.stale10; R["diff90"] = R.fresh90 - R.stale90
R["tail_diff"] = R.tail_fresh - R.tail_stale; R["p10_diff"] = R.p10_fresh - R.p10_stale; R["stale_share"] = R.n_stale / (R.n_fresh + R.n_stale)
R["rule"] = R["diff"] * R.stale_share; R["rule_lit"] = R.fresh - R.os_all
R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
say(f"신호일 {len(R)} · fresh 중앙 {R.n_fresh.median():.0f} · stale 중앙 {R.n_stale.median():.0f} · stale 비중 평균 {R.stale_share.mean():.2f} · {time.time()-t0:.0f}s")


def tbl(df, label):
    def ci(c):
        lo, hi = block_ci(df[c], df.month); return f"{df[c].mean():+.2f} [{lo:+.2f}, {hi:+.2f}]"
    say(f"\n-- {label} · 날 {len(df)} · fresh {df.fresh.mean():+.2f} · stale {df.stale.mean():+.2f} · 전체 과매도 {df.os_all.mean():+.2f}")
    say(f"   fresh−stale {ci('diff')} · 감도①(5일 전부 아님) {ci('diff5')} · 감도②(10일 머묾) {ci('diff10')} · 상폐−90 {ci('diff90')} · 깊이 맞춤 {ci('match')}")
    say(f"   −20% 비율 차 {ci('tail_diff')} · 하위10% 분위 차 {ci('p10_diff')} · R20 fresh/stale {df.r20_fresh.mean():+.1f}/{df.r20_stale.mean():+.1f}")
    say(f"   운용 번역: (fresh−stale)×stale비중 {ci('rule')} · fresh − 전체 과매도 {ci('rule_lit')}")


for label, df in [("전체", R), ("A 급락 뒤", R[R.cell == "A"]), ("B·C", R[R.cell == "BC"]), ("D 급등 뒤", R[R.cell == "D"]), ("앞반 ~2020", R[R.half == "앞"]), ("뒤반 2021~", R[R.half == "뒤"])]:
    tbl(df, label)

# A 사건
A = R[R.cell == "A"].sort_values("i"); keep = []; last = -10 ** 9
for idx, r in A.iterrows():
    if r.i - last >= H:
        keep.append(idx); last = r.i
E = A.loc[keep]; E.to_csv(OUT / "events.csv", index=False, encoding="utf-8-sig")
say(f"\n== A 사건 {len(E)} ==")
for c, nm_ in [("diff", "fresh−stale"), ("diff5", "감도①"), ("diff10", "감도②"), ("match", "깊이 맞춤"), ("tail_diff", "−20% 비율 차"), ("rule", "운용 번역")]:
    lo, hi = ev_ci(E[c]); say(f"   {nm_:<10} {E[c].mean():+.2f} [{lo:+.2f}, {hi:+.2f}] · 플러스 사건 {(E[c] > 0).sum()}/{E[c].notna().sum()}")
say(E[["date", "ks_r20", "n_fresh", "n_stale", "fresh", "stale", "diff", "match", "r20_fresh", "r20_stale"]].round(2).to_string(index=False))
(OUT / "run_20261031.txt").write_text("\n".join(LOG), encoding="utf-8")
say(f"\n끝 {time.time()-t0:.0f}s → {OUT}")
