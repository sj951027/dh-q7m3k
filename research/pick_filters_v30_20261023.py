# -*- coding: utf-8 -*-
"""가중 0 관측 넷 — v30 등록 후 실제 목록 안에서 '제외 필터·업종 상대'가 있었으면 성적이 어땠나 (2026-10-23, 사후 관측 · 채택 아님)
읽기 전용(history.db·ohlcv.db mode=ro). 적립 카드 §I-1(외부 조사) + 조사 1·5·6·9 의 후보를 v30 목록에 사후 적용.

앵커: leaderboard 규약(부분·이중 실행 제외·앵커 중복 제거·등록 20260606 이후), 40일 완결만. 바구니 = 시장별 상위 10 동일가중, 시장 = 전 종목 동일가중, 초과 = 바구니 − 시장(%p). 비용 0.
필터(앵커일 t 까지 자료만):
  F1 상·하한가 도달: 최근 5거래일 안 |등락률| ≥ 29%            F2 급등 후: 10일 수익 ≥ +50% 또는 5일 안 상한가(≥ +29%)
  F3 증자 공시: 최근 20거래일 안 DART '유상증자결정'/'무상증자결정'   F4 업종 상대 20일 수익: 종목 R20 − 같은 업종 중앙값(sector_cache) — 목록 안 하위 절반(업종보다 더 떨어짐) vs 상위 절반
재기: (a) 필터에 걸린 종목 비율 (b) 걸린 종목 vs 안 걸린 종목의 40일 수익(종목 단위, 목록 안) (c) 바구니 짝차이 = '걸린 종목을 빼고 다음 순위로 보충한 상위10' − '원래 상위10'(앵커 단위, 두 시장 평균, 월 블록 CI)
출력: research/out_pick_filters/*.csv + 표준출력."""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO))
import leaderboard as lb
OUT = HERE / "out_pick_filters"; OUT.mkdir(exist_ok=True)
H = 40; TOP = 10; REG = "20260606"; rng = np.random.default_rng(7)


def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); um = np.unique(months)
    if len(um) < 2 or len(vals) < 2: return (np.nan, np.nan)
    by = {m: vals[months == m] for m in um}
    ms = [np.concatenate([by[m] for m in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


print("자료 읽기…")
ocon = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker,date,close,change_pct FROM daily_ohlcv", ocon)
ev = pd.read_sql("SELECT ticker, rcept_dt, event_type, report_nm FROM dart_events", ocon); ocon.close()
px["ticker"] = px.ticker.astype(str).str.zfill(6)
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
chg = px.pivot_table(index="date", columns="ticker", values="change_pct", aggfunc="last").reindex(close.index)
dates = list(close.index); didx = {d: i for i, d in enumerate(dates)}; N = len(dates)
r20 = close / close.shift(20) - 1; r10 = close / close.shift(10) - 1
lim5 = (chg.abs() >= 0.29).rolling(5, min_periods=1).max() >= 1          # F1
up5 = (chg >= 0.29).rolling(5, min_periods=1).max() >= 1
sec = json.loads((REPO / "sector_cache.json").read_text(encoding="utf-8"))
secs = pd.Series({t: sec.get(t, "미분류") for t in close.columns})
ev["ticker"] = ev.ticker.astype(str).str.zfill(6); ev["rcept_dt"] = ev.rcept_dt.astype(str)
cap = ev[ev.report_nm.str.contains("유상증자결정|무상증자결정", na=False) | ev.event_type.astype(str).str.contains("rights|bonus|capital", case=False, na=False)]
print(f"  close {close.shape} · 증자 공시 {len(cap)}건(유형 {cap.event_type.value_counts().head(4).to_dict()})")
cap_by = cap.groupby("ticker")["rcept_dt"].apply(lambda s: sorted(set(s)))

hcon = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
S = pd.read_sql("SELECT run_id, market, ticker, final_score_v3 AS score FROM v3_scores WHERE model_id='v30'", hcon)
partial, dbl, _ = lb.build_gates(hcon, dates); hcon.close()
S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str); S["market"] = S.market.str.lower()
keep = lb.dedupe_by_anchor(S, didx, partial | dbl, reg=REG)
mk = px.groupby("ticker")["market"].last().str.lower() if "market" in px.columns else None


def had_cap(tk, t):
    ds = cap_by.get(tk, []); lo = dates[max(0, t - 20)]; hi = dates[t]
    return any(lo <= d <= hi for d in ds)


stock_rows, basket_rows = [], []
for rid in sorted(keep):
    t = lb.anchor(rid, didx)
    if t is None or t + 1 + H >= N: continue
    f40 = (close.iloc[t + 1 + H] / close.iloc[t + 1] - 1) * 100
    g = S[S.run_id == rid].dropna(subset=["score"])
    # 업종 상대 R20 (앵커일)
    rr = r20.iloc[t]; rel = rr - rr.groupby(secs.reindex(rr.index).fillna("미분류")).transform("median")
    per_mkt = {}
    for mkt, gm in g.groupby("market"):
        gm = gm.sort_values(["score", "ticker"], ascending=[False, True]); gm = gm[gm.ticker.isin(f40.dropna().index)]
        if len(gm) < 15: continue
        top = gm.ticker.head(TOP).tolist(); base = f40[top].mean()
        bench = f40.reindex(close.columns[(secs.index.isin(close.columns))]).dropna().mean()   # 전 종목(표시용)
        flags = {}
        for tk in gm.ticker:
            flags[tk] = dict(F1=bool(lim5.iloc[t].get(tk, False)), F2=bool((r10.iloc[t].get(tk, 0) or 0) >= 0.5 or up5.iloc[t].get(tk, False)),
                             F3=had_cap(tk, t), F4=bool(rel.get(tk, 0) <= np.nanmedian([rel.get(x, np.nan) for x in top])))
        for tk in top:
            stock_rows.append(dict(run=rid, month=rid[:6], market=mkt, ticker=tk, r40=f40[tk], **flags[tk]))
        for F in ("F1", "F2", "F3"):
            alt = [tk for tk in gm.ticker if not flags[tk][F]][:TOP]
            per_mkt.setdefault(F, []).append((f40[alt].mean() - base) if len(alt) == TOP else np.nan)
    for F, lst in per_mkt.items():
        v = [x for x in lst if x == x]
        if v: basket_rows.append(dict(run=rid, month=rid[:6], F=F, diff=float(np.mean(v))))

SR = pd.DataFrame(stock_rows); BR = pd.DataFrame(basket_rows)
SR.to_csv(OUT / "stock_flags.csv", index=False, encoding="utf-8-sig"); BR.to_csv(OUT / "basket_pairs.csv", index=False, encoding="utf-8-sig")
print(f"\n앵커(40일 완결) {SR.run.nunique()} · 목록 종목×앵커 {len(SR)}")
print("\n(a)(b) 목록 안 종목 단위 — 걸린 종목 vs 안 걸린 종목의 40일 수익(%)")
rows = []
for F, nm in (("F1", "상·하한가 5일 안"), ("F2", "급등 후(10일 +50% / 5일 상한가)"), ("F3", "증자 공시 20일 안"), ("F4", "업종 상대 R20 하위 절반(업종보다 더 떨어짐)")):
    a, b = SR[SR[F]], SR[~SR[F]]
    lo, hi = block_ci(a.r40, a.month) if len(a) >= 5 else (np.nan, np.nan)
    rows.append(dict(필터=nm, 걸린수=len(a), 비율=f"{len(a)/len(SR)*100:.1f}%", 걸린_40일=a.r40.mean() if len(a) else np.nan, 안걸린_40일=b.r40.mean(),
                     차이=(a.r40.mean() - b.r40.mean()) if len(a) else np.nan, 걸린_하한=lo, 걸린_상한=hi, 걸린_플러스=(a.r40 > 0).mean() if len(a) else np.nan))
T = pd.DataFrame(rows); pd.set_option("display.width", 220); print(T.round(2).to_string(index=False)); T.to_csv(OUT / "summary_stock.csv", index=False, encoding="utf-8-sig")
print("\n(c) 바구니 짝차이 — 걸린 종목을 빼고 다음 순위로 보충한 상위10 − 원래 상위10 (%p, 앵커 단위)")
rows = []
for F, g in BR.groupby("F"):
    lo, hi = block_ci(g["diff"], g.month)
    rows.append(dict(F=F, 앵커=len(g), 평균=g["diff"].mean(), 하한=lo, 상한=hi, 양수비율=(g["diff"] > 0).mean(), 바뀐앵커=int((g["diff"].abs() > 1e-9).sum())))
B = pd.DataFrame(rows); print(B.round(2).to_string(index=False)); B.to_csv(OUT / "summary_basket.csv", index=False, encoding="utf-8-sig")
