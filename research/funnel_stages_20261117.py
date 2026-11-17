# -*- coding: utf-8 -*-
"""선별 단계 진단('단계 제거 되감기') — stage1 → stage2 → stage3 → 하드 제외 → v30 상위 10 을 지날 때마다 남은 종목의 40일 성과가 어떻게 달라지나.
(2026-11-17, 읽기 전용 · 모델 등록 없음. 설계·읽는 조건·기대는 RESEARCH_funnel_stages_20261117.md §0 — 이 스크립트를 돌리기 전에 적음)

앵커 = v30 등록(20260606) 뒤 게이트 통과·중복 제거 run(leaderboard 함수). 진입 t+1 종가(없거나 0 이하면 제외) · 청산 t+1+h(없으면 마지막 가격) · ohlcv.db 본표 · 비용 없음.
시장별 바구니 동일가중 평균 → 두 시장 평균 = 앵커 값. 주지표 h40 · 보조 h20(run ≤ 20261023). 구간 = 주 블록 부트스트랩 4,000회 seed 7.
수익·구간 함수는 판정 도구 research/verdict_v32a_20261116.py 의 것을 그대로 쓴다(ret_matrix · week_of · week_block_ci), 상위 10 은 build_v32a_page.top.
출력: research/out_funnel_stages/anchors_h40.csv · anchors_h20.csv · summary.json · stdout."""
import importlib.util, json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import leaderboard as lb            # noqa: E402
import build_v32a_page as pg        # noqa: E402
_spec = importlib.util.spec_from_file_location("verdict_v32a", HERE / "verdict_v32a_20261116.py")
vt = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(vt)

OUT = HERE / "out_funnel_stages"; OUT.mkdir(exist_ok=True)
MARKETS = ("kospi", "kosdaq"); H_MAIN, H_AUX = 40, 20; AUX_LAST_RUN = "20261023"; LOSS, WIN = -20.0, 30.0   # §0 에 적은 값
BASKETS = ["S1", "S2", "S3", "S3e", "T10"]
STEPS = [("S2−S1 위험 필터(stage2)", "S2", "S1"), ("S3−S2 재무·수급(stage3)", "S3", "S2"), ("S3e−S3 하드 제외", "S3e", "S3"), ("T10−S3e 점수로 상위 10", "T10", "S3e"), ("합 T10−S1", "T10", "S1")]
DROPS = [("S1−S2 위험 필터에서 탈락", "S1", "S2"), ("S2−S3 재무·수급에서 탈락", "S2", "S3"), ("S3−S3e 하드 제외", "S3", "S3e"), ("S3e−T10 적격인데 상위 10 밖", "S3e", "T10")]

# ── 자료 ─────────────────────────────────────────────────────────────────
close, _ = lb.load_ohlcv(); close.index = close.index.astype(str); close.columns = close.columns.astype(str)
dates = list(close.index); N = len(dates); col = {t: j for j, t in enumerate(close.columns)}
con = sqlite3.connect(f"file:{REPO / 'history.db'}?mode=ro", uri=True)
reg = lb.REG_DATE.get("v30")
V = pd.read_sql("SELECT run_id, market, ticker, final_score_v3 FROM v3_scores WHERE model_id='v30' AND run_id >= ?", con, params=[reg])
ST = {k: pd.read_sql(f'SELECT run_id, market, ticker FROM "{t}" WHERE run_id >= ?', con, params=[reg])
      for k, t in (("S1", "stage1_oversold"), ("S2", "stage2_filtered"), ("S3", "stage3_final"))}
partial, dbl, didx = lb.build_gates(con, close.index); con.close()
for d in [V] + list(ST.values()):
    d["run_id"] = d.run_id.astype(str); d["ticker"] = d.ticker.astype(str); d["market"] = d.market.str.lower()
keep = lb.dedupe_by_anchor(V.rename(columns={"final_score_v3": "score"}), didx, partial | dbl, reg=reg)
rids = sorted(keep, key=lambda r: lb.anchor(r, didx)); ts = [lb.anchor(r, didx) for r in rids]
weeks = np.array([vt.week_of(dates[t]) for t in ts])
sig60 = np.log(close.where(close > 0)).diff().rolling(60, min_periods=40).std().to_numpy()

SETS = {}                                                   # (rid, mkt, 바구니) → 종목 집합
for k, d in ST.items():
    for (rid, mkt), g in d[d.run_id.isin(keep)].groupby(["run_id", "market"]):
        SETS[(rid, mkt, k)] = set(g.ticker)
for (rid, mkt), g in V[V.run_id.isin(keep)].groupby(["run_id", "market"]):
    SETS[(rid, mkt, "S3e")] = set(g[g.final_score_v3 > -999].ticker)
    SETS[(rid, mkt, "T10")] = set(pg.top(g)["ticker"])
    SETS[(rid, mkt, "S3v")] = set(g.ticker)
incl = [all(SETS.get((r, m, "S2"), set()) <= SETS.get((r, m, "S1"), set()) and SETS.get((r, m, "S3"), set()) <= SETS.get((r, m, "S2"), set())
            and SETS.get((r, m, "S3v"), set()) == SETS.get((r, m, "S3"), set()) for m in MARKETS) for r in rids]
print(f"앵커 {len(rids)}개 [{rids[0]}~{rids[-1]}] · 가격 마지막 {dates[-1]} · 포함 관계(S1⊃S2⊃S3 = v30 행)가 맞는 앵커 {sum(incl)}/{len(rids)}")
sz = {k: np.mean([len(SETS.get((r, m, k), ())) for r in rids for m in MARKETS]) for k in BASKETS}
print("  시장·앵커당 평균 종목 수: " + " → ".join(f"{k} {sz[k]:.0f}" for k in BASKETS))


def stats(vals):
    v = np.asarray(vals, float); v = v[np.isfinite(v)]
    return (float(v.mean()), float(np.median(v)), float((v <= LOSS).mean() * 100), float((v >= WIN).mean() * 100), len(v)) if len(v) else (np.nan,) * 4 + (0,)


def run(h, last_run=None):
    R, done = vt.ret_matrix(close, ts, h)
    rows, pooled = [], {k: [] for k in BASKETS + [d[0] for d in DROPS]}
    fate = {"stage2 탈락": 0, "stage3 탈락": 0, "하드 제외": 0, "적격·상위 10 밖": 0, "상위 10": 0}; fate_all = dict.fromkeys(fate, 0)
    for i, rid in enumerate(rids):
        if not done[i] or (last_run and rid > last_run):
            continue
        rec = dict(run_id=rid, week=weeks[i])
        per = {k: [] for k in BASKETS}
        for m in MARKETS:
            arr = {}
            for k in BASKETS:
                idx = [col[t] for t in SETS.get((rid, m, k), ()) if t in col]
                v = R[i, idx] if idx else np.array([]); v = v[np.isfinite(v)]; arr[k] = v
                rec[f"{k}_{m}"] = float(v.mean()) if len(v) else np.nan
                per[k].append(rec[f"{k}_{m}"]); pooled[k].extend(v.tolist())
            for name, a, b in DROPS:
                idx = [col[t] for t in SETS.get((rid, m, a), set()) - SETS.get((rid, m, b), set()) if t in col]
                v = R[i, idx] if idx else np.array([]); v = v[np.isfinite(v)]
                rec[f"{name}_{m}"] = float(v.mean()) if len(v) else np.nan; pooled[name].extend(v.tolist())
            # 40일 수익 상위 10%(그 시장·앵커의 S1 안)가 어느 단계에서 떨어졌나
            s1 = [t for t in SETS.get((rid, m, "S1"), ()) if t in col]; r1 = pd.Series(R[i, [col[t] for t in s1]], index=s1).dropna()
            if len(r1) >= 20:
                hot = set(r1[r1 >= r1.quantile(0.90)].index)
                def where(t):
                    if t not in SETS.get((rid, m, "S2"), ()): return "stage2 탈락"
                    if t not in SETS.get((rid, m, "S3"), ()): return "stage3 탈락"
                    if t not in SETS.get((rid, m, "S3e"), ()): return "하드 제외"
                    return "상위 10" if t in SETS.get((rid, m, "T10"), ()) else "적격·상위 10 밖"
                for t in r1.index:
                    w = where(t); fate_all[w] += 1
                    if t in hot: fate[w] += 1
        for k in BASKETS:
            rec[k] = float(np.mean(per[k])) if all(np.isfinite(per[k])) else np.nan
        rows.append(rec)
    return pd.DataFrame(rows), pooled, fate, fate_all


def ci(vals, wk):
    v = np.asarray(vals, float); m = np.isfinite(v); v, wk = v[m], np.asarray(wk)[m]
    wb = vt.week_block_ci(v, wk)
    return dict(n=int(len(v)), mean=float(v.mean()) if len(v) else np.nan, lo=wb[0] if wb else np.nan, hi=wb[1] if wb else np.nan, nw=wb[2] if wb else 0, pos=float((v > 0).mean() * 100) if len(v) else np.nan)


S = {}
A40, pooled40, fate, fate_all = run(H_MAIN)
A20, pooled20, _, _ = run(H_AUX, last_run=AUX_LAST_RUN)
A40.to_csv(OUT / "anchors_h40.csv", index=False, encoding="utf-8-sig"); A20.to_csv(OUT / "anchors_h20.csv", index=False, encoding="utf-8-sig")
t40 = [didx.get(r, lb.anchor(r, didx)) for r in A40.run_id]
print(f"\n=== 1. 바구니 수준 — 40일(앵커 {len(A40)}개 [{A40.run_id.min()}~{A40.run_id.max()}] · {A40.week.nunique()}주 · 겹치지 않는 앵커 {len(vt.nonoverlap(t40, H_MAIN))}개) ===")
print("  바구니 | 앵커 평균(두 시장 평균) | 종목 단위: 평균 · 중앙값 · 큰 손실(≤−20%) · 큰 상승(≥+30%) · 종목·날 수")
for k in BASKETS:
    mean, med, loss, win, n = stats(pooled40[k]); S[f"lvl_{k}"] = dict(anchor_mean=float(A40[k].mean()), mean=mean, median=med, loss=loss, win=win, n=n)
    print(f"  {k:4s} | {A40[k].mean():+6.2f}% | {mean:+6.2f} · {med:+6.2f} · {loss:5.1f}% · {win:5.1f}% · {n:,}")
print("  떨어진 종목:")
for name, _, _ in DROPS:
    mean, med, loss, win, n = stats(pooled40[name]); S[f"drop_{name}"] = dict(mean=mean, median=med, loss=loss, win=win, n=n)
    print(f"  {name:22s} | 평균 {mean:+6.2f} · 중앙값 {med:+6.2f} · 큰 손실 {loss:5.1f}% · 큰 상승 {win:5.1f}% · {n:,}")

print(f"\n=== 2. 단계 차이(%p) — 40일 주지표 · 20일 보조(run ≤ {AUX_LAST_RUN}, 앵커 {len(A20)}개) · 주 블록 95% ===")
verdicts = {}
for name, a, b in STEPS:
    d40 = ci(A40[a] - A40[b], A40.week); d20 = ci(A20[a] - A20[b], A20.week)
    mk = {m: float((A40[f"{a}_{m}"] - A40[f"{b}_{m}"]).mean()) for m in MARKETS}
    same = np.sign(d40["mean"]) == np.sign(d20["mean"]) and np.sign(mk["kospi"]) == np.sign(mk["kosdaq"]) == np.sign(d40["mean"])
    lab = "도움(방향)" if (d40["mean"] > 0 and d40["lo"] > 0 and same) else ("해(방향)" if (d40["mean"] < 0 and d40["hi"] < 0 and same) else "못 가름")
    verdicts[name] = lab; S[f"step_{name}"] = dict(h40=d40, h20=d20, market=mk, label=lab)
    print(f"  {name:24s}: 40일 {d40['mean']:+.2f} [{d40['lo']:+.2f}, {d40['hi']:+.2f}] 양수 앵커 {d40['pos']:.0f}% ({d40['nw']}주) · 20일 {d20['mean']:+.2f} [{d20['lo']:+.2f}, {d20['hi']:+.2f}] · "
          f"코스피 {mk['kospi']:+.2f} / 코스닥 {mk['kosdaq']:+.2f} → **{lab}**")

print(f"\n=== 3. 40일 수익 상위 10% 종목(그 날·그 시장의 stage1 안)은 어디서 떨어졌나 ===")
tot_hot = sum(fate.values()); tot_all = sum(fate_all.values())
for k in fate:
    S[f"fate_{k}"] = dict(hot=fate[k], all=fate_all[k])
    print(f"  {k:14s}: 상위 10% 종목의 {100 * fate[k] / tot_hot:5.1f}% (전체 stage1 종목에서는 {100 * fate_all[k] / tot_all:5.1f}%) → 배율 {(fate[k] / tot_hot) / (fate_all[k] / tot_all):.2f}")

print(f"\n=== 4. 덧붙임(K42 축 2 — 구성) : stage1 을 σ60 5분위로 나눴을 때 가장 요동친 5분위(Q5)가 단계마다 남는 비율 ===")
share = {k: [] for k in BASKETS}; q5ret, restret = [], []
R40, done40 = vt.ret_matrix(close, ts, H_MAIN)
for i, rid in enumerate(rids):
    for m in MARKETS:
        s1 = [t for t in SETS.get((rid, m, "S1"), ()) if t in col]
        sg = pd.Series(sig60[ts[i], [col[t] for t in s1]], index=s1).dropna()
        if len(sg) < 50:
            continue
        q5 = set(sg[sg >= sg.quantile(0.80)].index); known = set(sg.index)
        for k in BASKETS:
            b = SETS.get((rid, m, k), set()) & known
            if b: share[k].append(len(b & q5) / len(b))
        if done40[i]:
            r = pd.Series(R40[i, [col[t] for t in sg.index]], index=sg.index).dropna()
            if len(r) >= 50:
                q5ret.append(float(r[r.index.isin(q5)].mean())); restret.append(float(r[~r.index.isin(q5)].mean()))
print("  바구니 안 Q5 비율(정의상 S1 에서 20%): " + " → ".join(f"{k} {100 * np.mean(share[k]):.1f}%" for k in BASKETS))
print(f"  참고(탐색 — 조건에 안 씀): stage1 안 Q5 의 40일 {np.mean(q5ret):+.2f}% vs 나머지 {np.mean(restret):+.2f}% (시장·앵커 {len(q5ret)}칸 평균)")
S["q5_share"] = {k: float(np.mean(share[k])) for k in BASKETS}; S["q5_ret"] = dict(q5=float(np.mean(q5ret)), rest=float(np.mean(restret)))

print(f"\n=== 5. 읽는 조건 대조(§0) ===")
for k, v in verdicts.items():
    print(f"  {k}: {v}")
# ── 6. 탐색(결과를 본 뒤 19:42 에 붙임 — §5 에 쓰지 않는다): 앞 절반 주 / 뒤 절반 주로 나눈 단계 차이 ──
print(f"\n=== 6. 탐색 — 40일 단계 차이를 앞 8주 / 뒤 8주로 ===")
wk_sorted = sorted(A40.week.unique()); first = set(wk_sorted[:len(wk_sorted) // 2]); isf = A40.week.isin(first)
for name, a, b in STEPS:
    d = A40[a] - A40[b]; S[f"split_{name}"] = dict(first=float(d[isf].mean()), second=float(d[~isf].mean()))
    print(f"  {name:24s}: 앞({wk_sorted[0]}~) {d[isf].mean():+.2f} (n{int(isf.sum())}) · 뒤({wk_sorted[len(wk_sorted) // 2]}~) {d[~isf].mean():+.2f} (n{int((~isf).sum())})")
print(f"  바구니 수준: 앞 S1 {A40.S1[isf].mean():+.2f} · T10 {A40.T10[isf].mean():+.2f} / 뒤 S1 {A40.S1[~isf].mean():+.2f} · T10 {A40.T10[~isf].mean():+.2f}")
S["verdicts"] = verdicts; S["n_anchor_h40"] = len(A40); S["n_anchor_h20"] = len(A20)
(OUT / "summary.json").write_text(json.dumps(S, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
print(f"\n💾 {OUT}")
