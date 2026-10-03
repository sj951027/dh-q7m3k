# -*- coding: utf-8 -*-
# [경로 이식] research/fullscan_20260903/ 에서 실행. 3년 패널(npz)·읽기 전용. 관측·판정 아님.
"""step27_accumulate_3yr.py — 3년 동안 "매일 같은 금액으로 그날 상위20을 사서" ① 계속 보유 ② 40일 보유 — 시기에 상관없이 우상향인 뼈대는? (2026-10-03)
뼈대(가격·거래량만 — 재무·공매도 필요한 v30·lv_b·sv_a 는 재현 불가):
  조용함(lv_e 뼈대)=lv60↓+to20↓ · 가격4팩터(px_a 식 그대로)=lv60↓+to20↓+lv20↓+nh252↑ · 저점탈출(le_a 뼈대)=dlow252↓+obv63↓ · 과매도프록시(v30 흉내)=rsi14↓
규약: fullscan 공통(가드 ok · 전종목 중 상위20 · 다음날 종가 매수 · 비용 0). 시장 = 가드 통과 전종목 동일가중, 같은 날 같은 금액.
출력: out/accumulate_3yr.csv · out/accumulate_3yr_bars.csv · ../accumulate_3yr_20261003.png
"""
import numpy as np, pandas as pd
from fslib import *

P = Panel(); ok = guards(P); F = factors(P); R = regimes(P); c = P.close.astype(np.float64); T, N = P.T, P.N
# obv63: sum(sign(ret)*vol,63)/sum(vol,63)
sv = np.sign(np.nan_to_num(P.ret)) * P.vol
F["obv63"] = roll_mean(sv, 63, 30) / np.where(roll_mean(P.vol, 63, 30) > 0, roll_mean(P.vol, 63, 30), np.nan)
HYP["obv63"] = -1
SK = {"조용함(lv_e뼈대)": ["lv60", "to20"], "가격4팩터(px_a)": ["lv60", "to20", "lv20", "nh252"],
      "저점탈출(le_a뼈대)": ["dlow252", "obv63"], "과매도프록시(RSI)": ["rsi14"]}
TOP, H = 20, 40
start = P.idx("20240102"); valid = np.isfinite(c) & ok


def topmask(score):
    r = pd.DataFrame(np.where(ok, score, np.nan)).rank(axis=1, ascending=False).values
    return r <= TOP


# 시장(동일가중) 계속 보유: 매수일 e 의 가드 통과 종목을 같은 금액 → d 시점 평균
def forever(mask):
    S = np.zeros(T); n = np.zeros(T)
    for e in range(start + ENTRY_LAG, T):   # e = 매수일(목록 e-1)
        m = mask[e - ENTRY_LAG] & np.isfinite(c[e])
        if m.sum() < 5: continue
        base = c[e, m]
        with np.errstate(all="ignore"): rr = c[e:, :][:, m] / base - 1
        rr[~np.isfinite(rr)] = np.nan; rr[np.abs(rr) > 5] = np.nan
        v = np.nanmean(rr, axis=1); good = np.isfinite(v)
        S[e:][good] += v[good] * 100; n[e:][good] += 1
    return np.where(n > 0, S / np.maximum(n, 1), np.nan), n


def hold40(mask):
    f = fwd(P, H) * 100; out = []
    for t in range(start, T - ENTRY_LAG - H):
        m = mask[t]; v = f[t, m]; v = v[np.isfinite(v)]
        u = f[t, ok[t]]; u = u[np.isfinite(u)]
        if len(v) >= 5 and len(u): out.append((P.dates[t], v.mean(), u.mean()))
    return pd.DataFrame(out, columns=["list_date", "basket", "market"])


mk_forever, _ = forever(ok)
rows, bars = [], []
for nm, fac in SK.items():
    sc = rank_sum(F, fac, HYP, ok); M = topmask(sc)
    bk, n = forever(M)
    df = pd.DataFrame({"date": P.dates, "skeleton": nm, "n_tranche": n, "basket": bk, "market": mk_forever}); df["excess"] = df.basket - df.market
    rows.append(df[df.n_tranche > 0])
    b = hold40(M); b["skeleton"] = nm; b["excess"] = b.basket - b.market; b["year"] = b.list_date.str[:4]
    b = b.merge(R[["date", "regime_pit"]], left_on="list_date", right_on="date", how="left"); bars.append(b)
    d = df[df.n_tranche > 0]
    print(f"\n== {nm}")
    print(f"  계속보유 끝값: 계좌 {d.basket.iloc[-1]:+.1f}% 시장 {d.market.iloc[-1]:+.1f}% 차이 {d.excess.iloc[-1]:+.1f}%p · 차이>0 날 비율 {(d.excess>0).mean():.0%} · 차이 최저 {d.excess.min():+.1f}%p")
    for y, g in b.groupby("year"):
        print(f"  {y}: 40일 초과 평균 {g.excess.mean():+.2f}%p · 양수 {(g.excess>0).mean():.0%} · 매수일 {len(g)} · 바스켓 절대 {g.basket.mean():+.1f}% / 시장 {g.market.mean():+.1f}%")
    for rg, g in b.groupby("regime_pit"):
        print(f"  국면 {rg}: 초과 {g.excess.mean():+.2f}%p · 양수 {(g.excess>0).mean():.0%} · {len(g)}일")
A = pd.concat(rows); B = pd.concat(bars)
A.to_csv("out/accumulate_3yr.csv", index=False, encoding="utf-8-sig"); B.to_csv("out/accumulate_3yr_bars.csv", index=False, encoding="utf-8-sig")

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt; from matplotlib import font_manager
for f in ("Malgun Gothic", "NanumGothic"):
    if any(f == x.name for x in font_manager.fontManager.ttflist): plt.rcParams["font.family"] = f; break
plt.rcParams["axes.unicode_minus"] = False
col = dict(zip(SK, ["#c9403a", "#2f5fd8", "#1a8f5a", "#e08a00"]))
fig = plt.figure(figsize=(14, 10)); gs = fig.add_gridspec(3, 2, height_ratios=[1.5, 1, 1])
ax = fig.add_subplot(gs[0, :])
for nm, g in A.groupby("skeleton"):
    x = pd.to_datetime(g.date); ax.plot(x, g.excess, color=col[nm], lw=1.8, label=f"{nm}  끝값 {g.excess.iloc[-1]:+.1f}%p · 0위 {(g.excess>0).mean():.0%}")
ax.axhline(0, color="#999", lw=.8); ax.grid(alpha=.3); ax.legend(fontsize=9)
ax.set_title("① 3년 — 매일 같은 금액으로 상위20을 사서 계속 들고 가는 계좌: 시장(같은 방식)과의 차이 %p")
for i, nm in enumerate(SK):
    a = fig.add_subplot(gs[1 + i // 2, i % 2]); b = B[B.skeleton == nm]; x = pd.to_datetime(b.list_date)
    m = b.excess.rolling(20).mean()
    a.bar(x, b.excess, color=[col[nm] if v > 0 else "#ccc" for v in b.excess], width=1.0, alpha=.7)
    a.plot(x, m, color="#222", lw=1.1, label="20일 이동평균")
    ys = " · ".join(f"{y} {g.excess.mean():+.1f}" for y, g in b.groupby("year"))
    a.axhline(0, color="#999", lw=.8); a.grid(alpha=.3); a.legend(fontsize=8); a.set_title(f"② {nm} — 매수일별 40일 초과(%p) · 연도별 평균 {ys}", fontsize=10)
fig.suptitle("3년 패널 2024-01~2026-09 · 가드 통과 전종목 상위20 · 다음날 종가 매수 · 비용 0 · 시장 = 가드 통과 전종목 동일가중", fontsize=10)
fig.tight_layout(); fig.savefig("../accumulate_3yr_20261003.png", dpi=120); print("\npng ok")
