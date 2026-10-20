# -*- coding: utf-8 -*-
"""entry_regime_20261020.py — "어떤 장에서 샀을 때 좋았나" (2026-10-20, 읽기 전용 · 관측 · 판정 아님)

사용자 질문: 스크리너는 어떤 장에서 매수하는 게 좋았나? 특히 "하락할 때 샀으면 반등하면서 올라갈 확률이 크지 않나".
두 겹으로 나눈다:
  ① 시장 전체(3년, 모델 무관): 거래일 t 의 '그 전 20거래일 코스닥 수익'(진입 국면)으로 나눠, t+1 종가 매수 → t+1+h 종가(h=20·40)의
     전 종목 동일가중 수익 · 코스닥 지수 수익 · '떨어진 종목(자기 20일 수익 하위 20%)' 동일가중 수익. 승률(>0), 월 블록 부트스트랩 95%.
     겹침(이웃 날의 40일 수익은 39/40 겹침)이 크므로 '겹치지 않는 날 수'(40거래일 간격)를 함께 적는다.
  ② 모델(2026-06~): 운용 채택 사전등록 도구의 앵커별 40일 결과(research/out_shadow/ops_anchor_{v30,lv_b}.csv — 상위10 동일가중)에
     진입 국면(앵커일 전 20일 코스닥 수익 · 코스닥 종가 vs 20일선)을 붙여, 절대수익(≈ 지수 40일 + 지수 대비 초과)·동일가중 대비 초과·승률을 나눈다.
국면 칸(고정): 전 20일 코스닥 수익  A ≤ −5% (급락 뒤) · B −5~0% · C 0~+5% · D > +5% (급등 뒤).
주의: ①은 생존편향(상폐 종목 일부 결손)·같은 3년 자료, ②는 앵커 수십 개·한 사이클 — 규칙으로 쓰려면 사전등록.
실행: python research/entry_regime_20261020.py → research/out_entry_regime/summary.md
"""
import sys, sqlite3
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import leaderboard as lb  # noqa: E402

OUT = HERE / "out_entry_regime"; OUT.mkdir(exist_ok=True)
BOOT, SEED = 4000, 7
BUCKETS = [("A 급락 뒤(≤−5%)", -np.inf, -5.0), ("B 약세(−5~0%)", -5.0, 0.0), ("C 강세(0~+5%)", 0.0, 5.0), ("D 급등 뒤(>+5%)", 5.0, np.inf)]


def bucket_of(x):
    for name, lo, hi in BUCKETS:
        if lo < x <= hi or (lo == -np.inf and x <= hi):
            return name
    return None


def month_block_ci(vals, dates):
    """월 블록 부트스트랩 95%(달 단위 복원추출) — 겹친 창을 완전히 못 끊는 감도."""
    df = pd.DataFrame({"v": vals, "m": [str(d)[:6] for d in dates]}).dropna()
    if df.empty:
        return (np.nan, np.nan)
    groups = [g.v.values for _, g in df.groupby("m")]
    if len(groups) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(SEED); b = []
    for _ in range(BOOT):
        pick = rng.integers(0, len(groups), len(groups))
        b.append(np.concatenate([groups[i] for i in pick]).mean())
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def nonoverlap(dates, h):
    """시간순으로 앞에서 고른 날보다 h 거래일 이상 뒤인 날만 — 독립 표본 수."""
    k, last = 0, -10**9
    for d in dates:
        if d - last >= h:
            k += 1; last = d
    return k


con_o = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
idx = pd.read_sql("SELECT series, date, close FROM market_daily WHERE series IN ('KOSPI','KOSDAQ')", con_o)
idx = idx.pivot(index="date", columns="series", values="close").sort_index()
close, mkt = lb.load_ohlcv(); con_o.close()
dates = list(close.index); N = len(dates); pos = {d: i for i, d in enumerate(dates)}
kq = idx["KOSDAQ"].reindex(dates).ffill(); ks = idx["KOSPI"].reindex(dates).ffill()
kq_sma20 = kq.rolling(20).mean()
ret20_prior = (kq / kq.shift(20) - 1) * 100          # t 기준 전 20거래일 코스닥 수익
own20 = (close / close.shift(20) - 1) * 100          # 종목별 전 20일 수익

lines = ["# 어떤 장에서 샀을 때 좋았나 — 2026-10-20 (관측 · 판정 아님)", "",
         f"가격 {dates[0]}~{dates[-1]} · 국면 = 앵커일 전 20거래일 코스닥 수익 · 매수 = 다음 거래일 종가 · 구간 = 월 블록 부트스트랩 95% · 겹치지 않는 날 = 40거래일 간격으로 센 독립 표본", ""]

# ───────────── ① 시장 전체(3년) ─────────────
rows = []
for h in (20, 40):
    fwd = (close.shift(-(1 + h)) / close.shift(-1) - 1) * 100       # t+1 → t+1+h
    kq_f = (kq.shift(-(1 + h)) / kq.shift(-1) - 1) * 100
    for i in range(25, N - 1 - h):
        t = dates[i]
        r20 = ret20_prior.iloc[i]
        if np.isnan(r20):
            continue
        f = fwd.iloc[i]
        ok = f.notna()
        if ok.sum() < 500:
            continue
        ew = f[ok].mean()
        o = own20.iloc[i].reindex(f.index)
        fell = ok & o.notna() & (o <= o[ok].quantile(0.2))
        rows.append({"h": h, "date": t, "i": i, "r20": r20, "bucket": bucket_of(r20), "below_sma20": bool(kq.iloc[i] < kq_sma20.iloc[i]),
                     "ew": ew, "fell": f[fell].mean(), "kq": kq_f.iloc[i], "ew_hit": float(ew > 0), "fell_hit": float(f[fell].mean() > 0)})
D = pd.DataFrame(rows)
D.to_csv(OUT / "market_daily_buckets.csv", index=False, encoding="utf-8-sig")
for h in (20, 40):
    d = D[D.h == h]
    lines += [f"## ① 시장 전체 — {h}거래일 뒤 수익(%) · 날 수 {len(d)}", "",
              "| 진입 국면(전 20일 코스닥) | 날 수(겹치지 않는) | 전 종목 동일가중 [95%] | 승률 | 떨어진 종목(하위 20%) [95%] | 승률 | 코스닥 지수 [95%] |",
              "|---|---|---|---|---|---|---|"]
    for name, *_ in BUCKETS:
        g = d[d.bucket == name]
        if g.empty:
            continue
        c1 = month_block_ci(g.ew.values, g.date.values); c2 = month_block_ci(g.fell.values, g.date.values); c3 = month_block_ci(g.kq.values, g.date.values)
        lines.append(f"| {name} | {len(g)}({nonoverlap(sorted(g.i.values), 40)}) | {g.ew.mean():+.2f} [{c1[0]:+.2f},{c1[1]:+.2f}] | {g.ew_hit.mean():.0%} | {g.fell.mean():+.2f} [{c2[0]:+.2f},{c2[1]:+.2f}] | {g.fell_hit.mean():.0%} | {g.kq.mean():+.2f} [{c3[0]:+.2f},{c3[1]:+.2f}] |")
    for lab, m in (("코스닥 < 20일선", d.below_sma20), ("코스닥 ≥ 20일선", ~d.below_sma20)):
        g = d[m]
        c1 = month_block_ci(g.ew.values, g.date.values); c2 = month_block_ci(g.fell.values, g.date.values)
        lines.append(f"| {lab} | {len(g)}({nonoverlap(sorted(g.i.values), 40)}) | {g.ew.mean():+.2f} [{c1[0]:+.2f},{c1[1]:+.2f}] | {g.ew_hit.mean():.0%} | {g.fell.mean():+.2f} [{c2[0]:+.2f},{c2[1]:+.2f}] | {g.fell_hit.mean():.0%} | — |")
    lines.append("")
# 해마다(국면 효과 vs 시기 효과 분리)
d40 = D[D.h == 40].copy(); d40["year"] = d40.date.str[:4]
lines += ["### ① 보조 — 해마다 '급락 뒤(A)' 매수의 40일 수익(전 종목 동일가중)", "", "| 해 | 날 수 | A 급락 뒤 | 그 밖(B~D) | 차이 |", "|---|---|---|---|---|"]
for y, g in d40.groupby("year"):
    a = g[g.bucket == BUCKETS[0][0]]; b = g[g.bucket != BUCKETS[0][0]]
    lines.append(f"| {y} | {len(g)} | {a.ew.mean():+.2f}(n={len(a)}) | {b.ew.mean():+.2f}(n={len(b)}) | {(a.ew.mean() - b.ew.mean()) if len(a) else np.nan:+.2f} |")
lines.append("")

# ───────────── ② 모델별(2026) ─────────────
lines += ["## ② 모델 상위10(시장별, 동일가중) 40일 보유 — 진입 국면별 (운용 채택 사전등록 도구의 앵커별 결과)", "",
          "| 모델 | 진입 국면 | 앵커 n | 절대수익(%) [95%] | 승률(절대) | 동일가중 대비 초과(%p) [95%] | 승률(초과) | 보유 중 코스닥 |",
          "|---|---|---|---|---|---|---|---|"]
for mid in ("v30", "lv_b"):
    f = HERE / "out_shadow" / f"ops_anchor_{mid}.csv"
    if not f.exists():
        continue
    a = pd.read_csv(f, dtype={"run_id": str})
    a["anchor_date"] = a.run_id.astype(str)
    a["r20"] = a.anchor_date.map(lambda d: ret20_prior.iloc[pos[d]] if d in pos else np.nan)
    a["bucket"] = a.r20.map(lambda x: bucket_of(x) if not np.isnan(x) else None)
    a["below"] = a.anchor_date.map(lambda d: bool(kq.iloc[pos[d]] < kq_sma20.iloc[pos[d]]) if d in pos else None)
    a["abs"] = a.idx_ret + a.exc_idx          # 지수 40일 수익 + 지수 대비 초과 ≈ 바구니 절대수익
    a.to_csv(OUT / f"model_anchor_{mid}.csv", index=False, encoding="utf-8-sig")
    groups = [(name, a[a.bucket == name]) for name, *_ in BUCKETS] + [("코스닥 < 20일선", a[a.below == True]), ("코스닥 ≥ 20일선", a[a.below == False]), ("전체", a)]
    for name, g in groups:
        if g.empty:
            continue
        c1 = month_block_ci(g["abs"].values, g.anchor_date.values); c2 = month_block_ci(g.exc_mean.values, g.anchor_date.values)
        lines.append(f"| {mid} | {name} | {len(g)} | {g['abs'].mean():+.2f} [{c1[0]:+.2f},{c1[1]:+.2f}] | {(g['abs'] > 0).mean():.0%} | {g.exc_mean.mean():+.2f} [{c2[0]:+.2f},{c2[1]:+.2f}] | {(g.exc_mean > 0).mean():.0%} | {g.idx_ret.mean():+.2f} |")
lines += ["", "주의: ① 은 이웃한 날의 창이 거의 다 겹쳐 '겹치지 않는 날' 수가 진짜 표본 크기에 가깝다. ② 는 2026-06 이후 한 사이클(급락→반등→횡보→10/15 급락)뿐이라 '국면 효과'와 '그 시기 효과'를 못 가른다. "
          "절대수익은 대부분 시장(베타)의 몫이고, 모델이 고른 효과는 '동일가중 대비 초과' 열이다. 여기서 규칙을 만들려면 PREREGISTER_regime_gate(보류 중) 같은 사전등록이 필요하다.", ""]
(OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
