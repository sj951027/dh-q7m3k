# -*- coding: utf-8 -*-
"""조기 매도 규칙 되감기 — "사고 일주일 안에 올랐으면 20일에 판다" 류가 40거래일 고정 보유보다 나은가 (2026-11-08, 관측·읽기 전용 · 채택 아님)

사용자 질문(11/8): "사고 40일은 너무 길다. 사고 일주일 내에 오른 상태로 한 20일 동안 올라서 팔거나 이런 방법은 없을까?"
자료: history.db(ro) v3_scores(v30, 2026-06-02~) × ../dh-q7m3k-data/ohlcv.db(ro) daily_ohlcv. 목록 = 시장별 상위 10(=20종목, 희석 제외 없음 — 성적표와 같은 규약은 아님),
진입 = 추천 다음 거래일 종가(ENTRY_LAG 1), 비용 왕복 0.35%, 가격 없음 = 마지막 유효 종가. 게이트(부분·이중실행)·앵커 중복 제거는 leaderboard.py 그대로.
40거래일 창이 자료 끝(11/06) 안에 닫힌 앵커만(모든 규칙을 같은 앵커·같은 종목으로 비교).
규칙(진입 다음 날부터 k=1..40 거래일 종가):
  A40 40일 고정(기준) · A20 20일 고정 · A10 10일 고정
  U5_20  5일째 종가가 진입가보다 높으면 20일에, 아니면 40일에  ← 사용자 안
  U5_5   5일째 높으면 바로(5일) 팔고, 아니면 40일
  U20    20일째 높으면 20일에, 아니면 40일(익절 조건부)
  UP20+  20일째부터 '진입가보다 높은' 첫날 팔고, 40일까지 없으면 40일
  TP10/TP15/TP20  종가가 +10/15/20% 이상인 첫날 팔기, 없으면 40일(익절선)
세 잣대: ① 같은 40일 창 안 수익(판 뒤 현금 0%) — "그 돈이 40일 뒤 얼마가 됐나" · ③ ① + 판 돈을 남은 날 새 목록에 재투자(새 목록 수익 = A40 앵커 평균 일수익률 근사, 비용 1번 더) — "매일 새 목록이 있으니 바로 다시 굴린다면" · ② 보유 20일당 수익(= 수익 ÷ 보유일 × 20) — 참고(이긴 것만 일찍 팔면 저절로 커지는 잣대).
둘 다 절대수익과 같은 시장 전 종목 동일가중 대비 초과(보유한 날만). 불확실성 = 앵커 20개 블록 원형 부트스트랩 2,000회 seed 7, 95%.
출력: research/out_hold_early_exit/*.csv + 표준출력. 실행: python research/hold_early_exit_20261108.py (약 1분)."""
import os, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent; sys.path.insert(0, str(REPO))
import leaderboard as lb
OUT = HERE / "out_hold_early_exit"; OUT.mkdir(exist_ok=True)
H = 40; TOP = 10; COST = 0.0035; MODEL = "v30"; rng = np.random.default_rng(7); BLOCK = 20; NB = 2000
pd.set_option("display.width", 220)

close, mkt = lb.load_ohlcv()
dates = list(close.index); didx = {d: i for i, d in enumerate(dates)}; N = len(dates)
con = sqlite3.connect(f"file:{lb.DB}?mode=ro", uri=True)
partial, dbl, _ = lb.build_gates(con, dates); excl = partial | dbl
S = pd.read_sql("SELECT run_id, market, ticker, final_score_v3 AS score FROM v3_scores WHERE model_id=?", con, params=(MODEL,))
con.close()
reg = lb.REG_DATE.get(MODEL)
keep = lb.dedupe_by_anchor(S, didx, excl, reg=reg)
S = S[S["run_id"].astype(str).isin(keep)]
from paper_engine import picks_from_scores
picks = picks_from_scores(S, top=TOP)

# 시장 동일가중 지수(전 종목, 일수익 평균 누적) — 같은 보유일 비교용
ret = close.pct_change(fill_method=None)
ew = {}
for m in ("KOSPI", "KOSDAQ"):
    cols = [t for t in close.columns if mkt.get(t) == m]
    ew[m] = (1 + ret[cols].mean(axis=1).fillna(0)).cumprod().values
cf = close.ffill()   # 가격 없음 → 마지막 유효 종가(paper_engine 과 같은 사상)

rows = []
for rid, lst in picks.items():
    t = lb.anchor(rid, didx)
    if t is None: continue
    e = t + 1
    if e + H >= N: continue          # 40일 창이 안 닫힘
    for tk in lst:
        if tk not in cf.columns: continue
        p = cf[tk].values[e:e + H + 1]
        if np.isnan(p[0]) or p[0] <= 0: continue
        m = mkt.get(tk, "KOSDAQ"); m = "KOSPI" if m == "KOSPI" else "KOSDAQ"
        rows.append((rid, t, tk, m, p / p[0], ew[m][e:e + H + 1] / ew[m][e]))
print(f"앵커 {len(set(r[0] for r in rows))}개 · 종목-앵커 {len(rows)}건 · 자료 끝 {dates[-1]} · 게이트 제외 {sorted(excl)}")

def exit_day(path, rule):
    up = path > 1.0
    if rule == "A40": return H
    if rule == "A20": return 20
    if rule == "A10": return 10
    if rule == "U5_20": return 20 if up[5] else H
    if rule == "U5_5": return 5 if up[5] else H
    if rule == "U20": return 20 if up[20] else H
    if rule == "UP20+":
        w = np.where(up[20:])[0]; return 20 + w[0] if len(w) else H
    if rule.startswith("TP"):
        th = 1 + int(rule[2:]) / 100; w = np.where(path[1:] >= th)[0]; return 1 + w[0] if len(w) else H
    raise ValueError(rule)

RULES = ["A40", "A20", "A10", "U5_20", "U5_5", "U20", "UP20+", "TP10", "TP15", "TP20"]
rec = []
for rid, t, tk, m, path, mp in rows:
    for r in RULES:
        k = exit_day(path, r)
        g = path[k] - 1 - COST; mk_ = mp[k] - 1
        rec.append(dict(run_id=rid, anchor=t, ticker=tk, rule=r, k=k, win=g, win_exc=g - mk_, per20=g / k * 20, per20_exc=(g - mk_) / k * 20,
                        early=int(k < H), mk_rest=(mp[H] / mp[k] - 1)))
R = pd.DataFrame(rec)
# ③ 창 수익 + 재투자: 일찍 판 돈을 남은 날 동안 '그 시점의 새 목록' 에 다시 넣었다고 치고, 새 목록의 수익은 A40 의 앵커 평균 일수익률(비용 뒤)로 근사 + 왕복 비용 1번 더.
a40_daily = R[R.rule == "A40"].groupby("anchor")["win"].mean().mean() / H
R["reinv"] = (1 + R["win"]) * (1 + np.where(R.k < H, a40_daily * (H - R.k) - COST, 0.0)) - 1
R["reinv_exc"] = R["reinv"] - ((1 + R["win"] - R["win_exc"]) * (1 + R["mk_rest"]) - 1)   # 시장은 40일 내내 들고 있었다고 치고
R.to_csv(OUT / "per_pick.csv", index=False, encoding="utf-8-sig")
A = R.groupby(["anchor", "rule"])[["win", "win_exc", "per20", "per20_exc", "k", "early", "reinv", "reinv_exc"]].mean().reset_index()   # 앵커 = 20종목 평균
piv = {c: A.pivot(index="anchor", columns="rule", values=c) for c in ("win", "win_exc", "per20", "per20_exc", "k", "early", "reinv", "reinv_exc")}
anchors = piv["win"].index.values; nA = len(anchors)

def boot_ci(x):
    x = np.asarray(x, float); n = len(x); nb = int(np.ceil(n / BLOCK)); out = []
    for _ in range(NB):
        st = rng.integers(0, n, nb); idx = np.concatenate([(s + np.arange(BLOCK)) % n for s in st])[:n]
        out.append(x[idx].mean())
    return np.percentile(out, 2.5), np.percentile(out, 97.5)

lines = []
for metric, lab in (("win", "① 40일 창 수익(절대,%)"), ("win_exc", "① 창 초과(보유일 시장 대비,%p)"), ("reinv", "③ 창 수익 + 남은 날 재투자(절대,%)"), ("reinv_exc", "③ 창 초과 + 재투자(40일 시장 대비,%p)"), ("per20", "② 보유 20일당 수익(절대,%)"), ("per20_exc", "② 보유 20일당 초과(%p)")):
    P = piv[metric] * 100
    for r in RULES:
        v = P[r].values; d = v - P["A40"].values
        lo, hi = boot_ci(v); dlo, dhi = boot_ci(d) if r != "A40" else (np.nan, np.nan)
        lines.append(dict(metric=lab, rule=r, n_anchor=nA, mean=v.mean(), lo=lo, hi=hi, diff_vs_A40=d.mean(), d_lo=dlo, d_hi=dhi,
                          pos_share=(v > 0).mean(), avg_hold=piv["k"][r].mean(), early_share=piv["early"][r].mean()))
T = pd.DataFrame(lines)
T.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
for lab, g in T.groupby("metric", sort=False):
    print(f"\n### {lab}  (앵커 n={nA}, 블록 {BLOCK}앵커 부트스트랩 {NB}회)")
    print(g[["rule", "mean", "lo", "hi", "diff_vs_A40", "d_lo", "d_hi", "pos_share", "avg_hold", "early_share"]].round(2).to_string(index=False))

# 보조: 5일째 올라 있던 종목 vs 아니던 종목의 5→20→40일 경로(사용자 안의 전제 "일주일 안에 오르면 이어진다" 확인)
P5 = {}
for rid, t, tk, m, path, mp in rows:
    P5.setdefault(bool(path[5] > 1), []).append((path[5] - 1, path[20] - 1, path[40] - 1, path[20] / path[5] - 1, path[40] / path[20] - 1,
                                                  (path[20] - 1) - (mp[20] - 1), (path[40] - 1) - (mp[40] - 1)))
print("\n### 보조: 5일째 상태별 그 뒤 경로(종목-앵커 단순 평균, %)")
for k_, v in sorted(P5.items(), reverse=True):
    a = np.array(v) * 100
    print(f"5일째 {'상승' if k_ else '하락'} n={len(v)}: 5일 {a[:,0].mean():+.2f} · 20일 {a[:,1].mean():+.2f} · 40일 {a[:,2].mean():+.2f} · 5→20일 구간 {a[:,3].mean():+.2f} · 20→40일 구간 {a[:,4].mean():+.2f} · 초과 20일 {a[:,5].mean():+.2f} / 40일 {a[:,6].mean():+.2f}")
# 반기 나눔
half = np.median(anchors)
for nm, msk in (("앞 절반", anchors <= half), ("뒤 절반", anchors > half)):
    P = piv["win"] * 100; Q = piv["per20"] * 100
    print(f"\n{nm}(앵커 {msk.sum()}): 창 수익 A40 {P['A40'][msk].mean():+.2f} · A20 {P['A20'][msk].mean():+.2f} · U5_20 {P['U5_20'][msk].mean():+.2f} · TP15 {P['TP15'][msk].mean():+.2f} | 20일당 A40 {Q['A40'][msk].mean():+.2f} · A20 {Q['A20'][msk].mean():+.2f} · U5_20 {Q['U5_20'][msk].mean():+.2f} · TP15 {Q['TP15'][msk].mean():+.2f}")
print(f"\n앵커 범위 {dates[int(anchors.min())]}~{dates[int(anchors.max())]}")
