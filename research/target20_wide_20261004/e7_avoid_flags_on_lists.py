# -*- coding: utf-8 -*-
"""E7 — '피할 것' 표시를 실제 모델 목록에 얹으면 무엇이 달라지나 (읽기 전용 · 관측 · 2026-10-04)
대상: 현역 매수 목록 6개(v30·lv_b·px_a·sv_a·le_a·qs_a)의 시장별 상위 10. 저장 점수 가운데 **목록 다음 거래일 09:00 전에 저장된 것만**(Codex 시점 점검 반영).
표시: ① 최근 60봉 안 상한가 마감 경험 ② 20일 변동성이 같은 시장 상위 20% ③ 20일 회전율이 같은 시장 상위 20% ④ 희석 공시 60거래일 내(이미 화면에 있는 💧 배지와 같은 정의).
잰 것: 표시 종목 비율 · 표시/비표시 종목의 20봉 수익(다음날 시가, 비용 0.5%)과 같은 날·같은 시장 전 종목 대비 초과 · '표시 종목을 빼고 다음 순위로 채운 상위 10' vs 원래 상위 10.
python e7_avoid_flags_on_lists.py"""
import sqlite3
import numpy as np, pandas as pd
from w20lib import *

s = study(choose=False); T, N = s.T, s.N; c, o, ok, ff, r, v = s.c, s.o, s.ok, s.ff, s.r, s.v; dates = s.d; di = s.di
tix = {t: i for i, t in enumerate(s.tick)}; shares = s.z["shares"].astype(float)
# ---- 표시(목록일 t 종가까지의 정보)
lu60 = rolling((r >= .295).astype(float), 60, 20, "sum") > 0
lv20 = rolling(r, 20, 15, "std"); to20 = rolling(v / np.where(shares > 0, shares, np.nan), 20, 10)


def mk_rank(a):
    out = np.full(a.shape, np.nan)
    for m in (0, 1):
        cols = s.mi == m; out[:, cols] = rank(a[:, cols], ok[:, cols])
    return out


hv = mk_rank(lv20) >= .8; ht = mk_rank(to20) >= .8
oc = sqlite3.connect(f"file:{ROOT.parent / 'dh-q7m3k-data/ohlcv.db'}?mode=ro", uri=True)
de = pd.read_sql("SELECT rcept_dt, ticker, report_nm FROM dart_events WHERE event_type IN ('paid_in','cb','bw','eb','paid_bonus_mix')", oc); oc.close()
de = de[~de.report_nm.str.contains("정정")]; de["ticker"] = de.ticker.astype(str).str.zfill(6); dil = np.zeros((T, N), bool)
for d8, tk in zip(de.rcept_dt, de.ticker):
    if tk in tix:
        a = int(np.searchsorted(dates, d8)); dil[a:min(a + 60, T), tix[tk]] = True
FLAGS = {"상한가 경험(60봉)": lu60, "변동성 상위20%": hv, "회전율 상위20%": ht, "희석 공시(60일)": dil}
ANY = lu60 | hv | ht | dil; PRICE = lu60 | hv | ht
# ---- 20봉 결과(다음날 시가 진입) · 같은 날 같은 시장 평균
ret = np.full((T, N), np.nan); mean_mk = np.full((T, 2), np.nan)
for t in range(s.t0, T - H - 1):
    f = entry_ok(s, t); ret[t] = np.where(f, (ff[t + H] / o[t + 1] - 1 - COST) * 100, np.nan)
    for m in (0, 1): mean_mk[t, m] = np.nanmean(ret[t, ok[t] & (s.mi == m)])
# ---- 모델 목록(제때 저장된 점수만)
hc = sqlite3.connect(f"file:{ROOT / 'history.db'}?mode=ro", uri=True)
SRC = {"v30": ("v3_scores", "final_score_v3"), "lv_b": ("lowvol_scores", "lowvol_score"), "px_a": ("wu_scores", "wu_score"), "sv_a": ("wu_scores", "wu_score"), "le_a": ("wu_scores", "wu_score"), "qs_a": ("wu_scores", "wu_score")}
rows = []; audit = []
for model, (tab, col) in SRC.items():
    d = pd.read_sql(f"SELECT run_id, market, ticker, {col} AS score, frozen_at FROM {tab} WHERE model_id=?", hc, params=(model,))
    d = d[d.score > -900]; d["ticker"] = d.ticker.astype(str).str.zfill(6); d["market"] = d.market.str.lower(); d = d[d.run_id.isin(di)]
    t_idx = d.run_id.map(di); nxt = pd.Series(dates[np.minimum(t_idx.values + 1, T - 1)], index=d.index)
    fz = pd.to_datetime(d.frozen_at.astype(str).str.slice(0, 19), errors="coerce"); dead = pd.to_datetime(nxt + " 09:00:00", format="%Y%m%d %H:%M:%S")
    on = (fz <= dead) & (t_idx < T - 1); audit.append((model, d.run_id.nunique(), d[on].run_id.nunique()))
    d = d[on]
    for (run, mkt), g in d.groupby(["run_id", "market"]):
        t = di[run]
        if t >= T - H - 1: continue
        g = g[g.ticker.isin(tix)].sort_values("score", ascending=False)
        if len(g) < 10: continue
        k = g.ticker.map(tix).values; m = 0 if mkt == "kospi" else 1
        top = k[:10]; clean = [x for x in k if not PRICE[t, x]][:10]; clean_any = [x for x in k if not ANY[t, x]][:10]
        for j, x in enumerate(top):
            rows.append(dict(model=model, run=run, mkt=mkt, rank=j + 1, k=x, ret=ret[t, x], exc=ret[t, x] - mean_mk[t, m], **{nm: bool(a[t, x]) for nm, a in FLAGS.items()}, price_flag=bool(PRICE[t, x]), any_flag=bool(ANY[t, x])))
        rows.append(dict(model=model, run=run, mkt=mkt, rank=0, basket=np.nanmean(ret[t, top]), clean=np.nanmean(ret[t, clean]) if len(clean) >= 5 else np.nan,
                         clean_any=np.nanmean(ret[t, clean_any]) if len(clean_any) >= 5 else np.nan, n_swapped=10 - len(set(top) & set(clean)), n_swapped_any=10 - len(set(top) & set(clean_any))))
hc.close()
D = pd.DataFrame(rows); P = D[D["rank"] > 0].dropna(subset=["ret"]).copy(); B = D[D["rank"] == 0]
for _c in list(FLAGS) + ["price_flag", "any_flag"]: P[_c] = P[_c].astype(bool)   # 목록 행(rank 0)과 섞여 object 가 된 열을 참/거짓으로
P.to_csv(HERE / "avoid_flags_picks.csv", index=False, encoding="utf-8-sig"); B.to_csv(HERE / "avoid_flags_baskets.csv", index=False, encoding="utf-8-sig")
print("[제때 저장된 날 수 / 전체]", {m: f"{b}/{a}" for m, a, b in audit}, f"· 20봉 결과가 있는 마지막 목록일 {dates[T - H - 2]}")


def ci_dates(g, col, k=2000):
    a = g.groupby("run")[col].agg(["sum", "count"]); n = len(a)
    if n < 8: return (np.nan, np.nan)
    idx = np.random.default_rng(7).integers(0, n, (k, n)); return tuple(np.quantile(a["sum"].values[idx].sum(1) / a["count"].values[idx].sum(1), [.025, .975]))


print("\n[모델별 상위 10 안에서 표시가 붙는 비율 % · 표시/비표시 종목의 20봉 초과(같은 날·같은 시장 전 종목 대비 %p)]")
for model, g in P.groupby("model"):
    line = f"  {model:<5} 목록일 {g.run.nunique():>2} · 종목 {len(g):>4} · 평균 초과 {g.exc.mean():+.2f}"
    for nm in list(FLAGS) + ["price_flag", "any_flag"]:
        a, b = g[g[nm]], g[~g[nm]]
        line += f" | {nm.replace('price_flag','가격 3종 중 하나').replace('any_flag','4종 중 하나')} {g[nm].mean()*100:.0f}%" + (f" ({a.exc.mean():+.1f} vs {b.exc.mean():+.1f})" if len(a) >= 15 else " (적음)")
    print(line)
print("\n[표시 종목만 모아서 — 모델 합] 표시별 n · 20봉 초과 [날짜 재추출 95%] · 비표시 종목 초과")
for nm in list(FLAGS) + ["price_flag", "any_flag"]:
    a, b = P[P[nm]], P[~P[nm]]; lo, hi = ci_dates(a, "exc"); lb, hb = ci_dates(b, "exc")
    print(f"  {nm:<14} 표시 n {len(a):>4}({len(a)/len(P)*100:.0f}%) 초과 {a.exc.mean():+.2f} [{lo:+.2f},{hi:+.2f}] · 절대 {a.ret.mean():+.2f}% | 비표시 n {len(b):>4} 초과 {b.exc.mean():+.2f} [{lb:+.2f},{hb:+.2f}] · 절대 {b.ret.mean():+.2f}%")
print("\n[목록 단위 — 원래 상위 10 vs 표시 종목을 빼고 다음 순위로 채운 10 (20봉 평균 수익 %)]")
for model, g in B.groupby("model"):
    g = g.dropna(subset=["basket"]); d1 = (g.clean - g.basket).dropna(); d2 = (g.clean_any - g.basket).dropna()
    def ci(x):
        gg = g.loc[x.index].assign(d=x); return ci_dates(gg, "d")
    l1, h1 = ci(d1); l2, h2 = ci(d2)
    print(f"  {model:<5} 목록(시장×날) {len(g):>3} · 원래 {g.basket.mean():+.2f}% · 가격 표시 제외 {g.clean.mean():+.2f}% (차이 {d1.mean():+.2f} [{l1:+.2f},{h1:+.2f}], 바뀐 종목 평균 {g.n_swapped.mean():.1f}개) · 4종 제외 {g.clean_any.mean():+.2f}% (차이 {d2.mean():+.2f} [{l2:+.2f},{h2:+.2f}], {g.n_swapped_any.mean():.1f}개)")
