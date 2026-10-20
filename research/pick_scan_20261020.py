# -*- coding: utf-8 -*-
"""무엇을 고르나 — 넓은 훑기 (2026-10-20 밤). 읽기 전용(ohlcv.db mode=ro). 사후 탐색 · 규칙 채택 아님.

날 t(5거래일 간격)마다 후보군 안에서 특징 하나로 5분위를 나누고 Q5 − Q1 의 40일 수익 차이(다음날 종가 매수·40일 뒤 종가 매도·동일가중)를
적는다. 후보군 3개 × 특징 18개 × 장세(전체/코스피 급락) × 기간(앞/뒤 반)을 전부 적고, **앞·뒤 반 모두 같은 부호이면서 전체 구간이
0 을 안 걸친 것**만 '남는 후보'로 표시한다. 본 칸 수를 함께 적는다(많이 볼수록 우연이 섞임).
출력: research/out_pick_scan/scan_all.csv · scan_survivors.csv · 표준출력 요약.
"""
import sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO))
import leaderboard as lb, regime_ad
OUT = HERE / "out_pick_scan"; OUT.mkdir(exist_ok=True)
H = 40; STEP = 5; Q = 5; K = 1500; SEED = 7; SPLIT = "20250101"
rng = np.random.default_rng(SEED)


def block_ci(vals, months):
    vals = np.asarray(vals, float); months = np.asarray(months); um = np.unique(months)
    if len(um) < 2 or len(vals) < 2:
        return (np.nan, np.nan)
    by = {m: vals[months == m] for m in um}
    ms = [np.concatenate([by[m] for m in rng.choice(um, len(um))]).mean() for _ in range(K)]
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


def nonov(pos, gap=H):
    c = 0; last = -10 ** 9
    for p in sorted(pos):
        if p - last >= gap:
            c += 1; last = p
    return c


print("자료 읽기…")
ocon = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker,date,open,high,low,close,volume,shares,is_suspended FROM daily_ohlcv", ocon); ocon.close()
px["ticker"] = px.ticker.astype(str).str.zfill(6)
def piv(col):
    return px.pivot_table(index="date", columns="ticker", values=col, aggfunc="last")
close = piv("close").sort_index(); idx = close.index
openp, high, low, vol = (piv(c).reindex(idx) for c in ("open", "high", "low", "volume"))
shares = piv("shares").reindex(idx).ffill(); susp = piv("is_suspended").reindex(idx).fillna(0)
dates = list(idx); N = len(dates)
close = close.where(close > 0)
ret = close.pct_change(fill_method=None)
sma = lambda n: close.rolling(n, min_periods=max(5, n // 2)).mean()
feat = {
    "5일 수익": close / close.shift(5) - 1,
    "20일 수익": close / close.shift(20) - 1,
    "60일 수익": close / close.shift(60) - 1,
    "120일 수익": close / close.shift(120) - 1,
    "10일 변동성": ret.rolling(10, min_periods=8).std(),
    "60일 변동성": ret.rolling(60, min_periods=40).std(),
    "20일 거래대금": (close * vol).rolling(20, min_periods=10).mean(),
    "시총": close * shares,
    "회전율(거래대금/시총)": (close * vol).rolling(20, min_periods=10).mean() / (close * shares),
    "60일 고점 낙폭": close / close.rolling(60, min_periods=40).max() - 1,
    "250일 고점 낙폭": close / close.rolling(250, min_periods=120).max() - 1,
    "250일 저점 대비": close / close.rolling(250, min_periods=120).min() - 1,
    "20일선 대비": close / sma(20) - 1,
    "60일선 대비": close / sma(60) - 1,
    "200일선 대비": close / sma(200) - 1,
    "거래량 급증(5일/60일)": vol.rolling(5, min_periods=3).mean() / vol.rolling(60, min_periods=30).mean(),
    "당일 캔들(종가−시가)/시가": (close - openp) / openp,
    "일중 폭(고−저)/종가 20일": ((high - low) / close).rolling(20, min_periods=10).mean(),
}
# RSI14
d = close.diff(); up = d.clip(lower=0).rolling(14, min_periods=10).mean(); dn = (-d.clip(upper=0)).rolling(14, min_periods=10).mean()
feat["RSI14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
fwd40 = close.shift(-1 - H) / close.shift(-1) - 1
r20 = feat["20일 수익"]; amt20 = feat["20일 거래대금"]
ks = regime_ad.load_index("KOSPI", lb.OHLCV_DB); ks_r20 = (ks / ks.shift(20) - 1).reindex(dates)
print(f"  close {close.shape} · 특징 {len(feat)}개")

rows = []
sig = [i for i in range(250, N - H - 1, STEP)]
for i in sig:
    f = fwd40.iloc[i]; r = r20.iloc[i]; a = amt20.iloc[i]; s_ = susp.iloc[i]
    ok = f.notna() & r.notna() & (s_ == 0)
    if ok.sum() < 300:
        continue
    thr = r[ok].quantile(0.20); over = ok & (r <= thr)
    liq = over & (a >= a[over].quantile(0.5))
    unis = {"전 종목": ok, "과매도(20일 하위20%)": over, "과매도·거래대금 상위 절반": liq}
    A = bool(ks_r20.iloc[i] == ks_r20.iloc[i] and ks_r20.iloc[i] <= -0.05)
    for un, mask in unis.items():
        fu = f[mask]
        if len(fu) < 60:
            continue
        for fn, F in feat.items():
            x = F.iloc[i][mask].replace([np.inf, -np.inf], np.nan).dropna()
            if len(x) < 60 or x.nunique() < Q:
                continue
            try:
                q = pd.qcut(x.rank(method="first"), Q, labels=False)
            except ValueError:
                continue
            g = fu[x.index].groupby(q.values).mean()
            if 0 not in g.index or Q - 1 not in g.index:
                continue
            rows.append(dict(date=dates[i], i=i, month=dates[i][:6], half=("앞" if dates[i] < SPLIT else "뒤"), A=A, uni=un, feat=fn,
                             q1=g[0] * 100, q5=g[Q - 1] * 100, spread=(g[Q - 1] - g[0]) * 100, n=int(len(x))))
R = pd.DataFrame(rows); R.to_csv(OUT / "scan_days.csv", index=False, encoding="utf-8-sig")
print(f"  신호일 {R.date.nunique()} · 날×칸 {len(R)}")

summ = []
for (un, fn), g in R.groupby(["uni", "feat"]):
    for scope, sub in (("전체", g), ("코스피 급락", g[g.A])):
        if len(sub) < 8:
            continue
        lo, hi = block_ci(sub.spread, sub.month)
        fr, bk = sub[sub.half == "앞"], sub[sub.half == "뒤"]
        summ.append(dict(후보군=un, 특징=fn, 장세=scope, 날수=len(sub), 비겹침=nonov(sub.i), Q1=sub.q1.mean(), Q5=sub.q5.mean(),
                         차이Q5_Q1=sub.spread.mean(), 하한=lo, 상한=hi, 양수비율=(sub.spread > 0).mean(),
                         앞반=fr.spread.mean() if len(fr) else np.nan, 뒤반=bk.spread.mean() if len(bk) else np.nan,
                         앞반n=len(fr), 뒤반n=len(bk)))
S = pd.DataFrame(summ)
S["같은부호"] = np.sign(S.앞반) == np.sign(S.뒤반)
S["구간0밖"] = (S.하한 > 0) | (S.상한 < 0)
S["남는후보"] = S.같은부호 & S.구간0밖 & (S.앞반n >= 8) & (S.뒤반n >= 8)
S = S.sort_values(["남는후보", "차이Q5_Q1"], ascending=[False, False])
S.to_csv(OUT / "scan_all.csv", index=False, encoding="utf-8-sig")
surv = S[S.남는후보]; surv.to_csv(OUT / "scan_survivors.csv", index=False, encoding="utf-8-sig")
print(f"\n본 칸 수: {len(S)} (후보군 {S.후보군.nunique()} × 특징 {S.특징.nunique()} × 장세 2) · 구간 0 밖: {int(S.구간0밖.sum())} · 앞뒤 같은 부호: {int(S.같은부호.sum())} · **남는 후보 {len(surv)}**")
pd.set_option("display.width", 250)
cols = ["후보군", "특징", "장세", "날수", "비겹침", "Q1", "Q5", "차이Q5_Q1", "하한", "상한", "양수비율", "앞반", "뒤반"]
print("\n== 남는 후보(앞·뒤 반 같은 부호 + 전체 구간 0 밖) ==")
print(surv[cols].round(2).to_string(index=False) if len(surv) else "없음")
print("\n== 전체 중 |차이| 큰 순 12개(참고 — 우연 포함) ==")
print(S.reindex(S.차이Q5_Q1.abs().sort_values(ascending=False).index)[cols].head(12).round(2).to_string(index=False))
