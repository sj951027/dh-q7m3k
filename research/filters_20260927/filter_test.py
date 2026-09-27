# filter_test.py — RESEARCH_filters_20260927 §0 의 사전 가설 9개만 시험. 읽기 전용.
# A) 동결 점수 OOS(history.db v30·lv_b) · B) 3년 가격 패널 근사(lv_b = 저변동만)
import os, sys, sqlite3, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "research", "fullscan_20260903"))
import leaderboard as lb, dilution_flag as dil
rng = np.random.default_rng(927); N_PLACEBO = 300; TOP = 10
OUT = HERE

def bci(x, block, reps=3000, seed=927):
    x = np.asarray(x, float); x = x[np.isfinite(x)]; L = len(x)
    if L < 4: return (float(np.mean(x)) if L else np.nan, np.nan, np.nan, L)
    block = max(1, min(block, L // 2)); r = np.random.default_rng(seed)
    st = r.integers(0, L, (reps, int(np.ceil(L / block)))); ix = (st[:, :, None] + np.arange(block)) % L
    mm = x[ix.reshape(reps, -1)[:, :L]].mean(axis=1)
    return (float(x.mean()), float(np.quantile(mm, .025)), float(np.quantile(mm, .975)), L)
def f(t): return f"{t[0]*100:+.2f} [{t[1]*100:+.2f}, {t[2]*100:+.2f}] n={t[3]}" if np.isfinite(t[1]) else f"{t[0]*100:+.2f} n={t[3]}"

# ---------------- 공통 데이터 ----------------
close, mkt = lb.load_ohlcv(); dates = list(close.index); NT = len(dates); didx = {d: i for i, d in enumerate(dates)}
oc = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
vol = pd.read_sql("SELECT ticker,date,volume FROM daily_ohlcv WHERE date>='20260301'", oc).pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index)
newl = pd.read_sql("SELECT date,ticker FROM universe_events WHERE event='NEW'", oc); oc.close()
list_date = {str(t).zfill(6): d for d, t in zip(newl.date, newl.ticker)}
cv20 = (vol.rolling(20, min_periods=15).std() / vol.rolling(20, min_periods=15).mean())
hc = sqlite3.connect(f"file:{REPO}/history.db?mode=ro", uri=True)
partial, dbl, _ = lb.build_gates(hc, dates); excl = partial | dbl
S3 = pd.read_sql("SELECT run_id, market, ticker, oversold_score, realized_vol, roe_value, falling_knife, volume_vs_avg FROM stage3_final", hc)
S3["ticker"] = S3.ticker.astype(str).str.zfill(6); S3["market"] = S3.market.str.lower()
S3 = S3.drop_duplicates(["run_id", "market", "ticker"]).set_index(["run_id", "market", "ticker"])
def load_scores(tbl, col, mid):
    s = pd.read_sql(f"SELECT run_id, market, ticker, {col} AS score FROM {tbl} WHERE model_id=?", hc, params=(mid,))
    s["ticker"] = s.ticker.astype(str).str.zfill(6); s["market"] = s.market.str.lower(); return s
MODELS = {"v30": load_scores("v3_scores", "final_score_v3", "v30"), "lv_b": load_scores("lowvol_scores", "lowvol_score", "lv_b")}

def young(tk, d):   # 상장 12개월(252거래일) 미만?
    ld = list_date.get(tk)
    if not ld or ld > d: return False
    i0 = didx.get(ld) or int(np.searchsorted(dates, ld)); i1 = didx.get(d, int(np.searchsorted(dates, d)))
    return (i1 - i0) < 252

FILTERS = {  # id -> (model, 함수(cand_df, run_date) -> 통과 bool Series)  cand 는 점수 내림차순, stage3 필드 포함
    "V1": ("v30", lambda c, d: ~(c.oversold_score >= 60)),
    "V2": ("v30", lambda c, d: ~(c.realized_vol > c.realized_vol.quantile(2/3))),
    "V3": ("v30", lambda c, d: ~(c.roe_value <= 0)),
    "V4": ("v30", lambda c, d: ~c.ticker.map(lambda t: young(t, d))),
    "V5": ("v30", lambda c, d: ~c.falling_knife.astype(str).str.lower().isin(["true", "1", "1.0", "y", "yes"])),
    "L1": ("lv_b", lambda c, d: ~c.ticker.map(lambda t: young(t, d))),
    "L2": ("lv_b", lambda c, d: ~(c.volume_vs_avg > c.volume_vs_avg.quantile(2/3))),
    "L4": ("lv_b", lambda c, d: c.cv20 <= c.cv20.median()),
}

# ---------------- A) 동결 점수 OOS ----------------
recs = []   # (fid, h, date, base, filt, k, placebo_diffs[N])
base_rows = []
for mid, S in MODELS.items():
    keep = lb.dedupe_by_anchor(S, didx, excl, reg=lb.REG_DATE.get(mid))
    for rid in sorted(keep):
        t = lb.anchor(rid, didx)
        if t is None or t + 1 + 20 >= NT: continue
        flags = dil.load(asof=rid)
        for h in (20, 40):
            if t + 1 + h >= NT: continue
            r = close.iloc[t + 1 + h] / close.iloc[t + 1] - 1
            per_f = {}
            for mk_, g in S[S.run_id == rid].groupby("market"):
                c = g[~g.ticker.isin(flags.keys())].sort_values("score", ascending=False).reset_index(drop=True)
                try: c = c.join(S3.loc[rid].loc[mk_], on="ticker")
                except Exception: c = c.assign(oversold_score=np.nan, realized_vol=np.nan, roe_value=np.nan, falling_knife=np.nan, volume_vs_avg=np.nan)
                c["cv20"] = c.ticker.map(cv20.iloc[t]) if dates[t] in cv20.index else np.nan
                rr = c.ticker.map(r)
                ok_ = rr.notna()
                base_idx = list(c.index[ok_][:TOP]); base = rr[base_idx].mean()
                uni = r.reindex(mkt.index[mkt.str.lower() == mk_]).dropna().mean()
                base_rows.append(dict(model=mid, h=h, date=dates[t], market=mk_, base=base, bench=uni, top20=rr[list(c.index[ok_][:20])].mean()))
                for fid, (fm, fn) in FILTERS.items():
                    if fm != mid: continue
                    pas = fn(c, dates[t]).fillna(True).values & ok_.values
                    fidx = list(c.index[pas][:TOP])
                    if len(fidx) < 5: fidx = base_idx
                    k = len(set(base_idx) - set(fidx))
                    filt = rr[fidx].mean()
                    # 플라시보: 기준 상위10 에서 k 개 무작위로 빼고 다음 순위(유효 수익)로 채움
                    pool = list(c.index[ok_])
                    pl = np.empty(N_PLACEBO)
                    for i in range(N_PLACEBO):
                        if k == 0: pl[i] = base; continue
                        drop = set(rng.choice(base_idx, k, replace=False))
                        pick = [j for j in pool if j not in drop][:TOP]
                        pl[i] = rr[pick].mean()
                    per_f.setdefault(fid, []).append((filt - base, k, pl - base))
            for fid, lst in per_f.items():
                recs.append(dict(fid=fid, h=h, date=dates[t], diff=np.mean([x[0] for x in lst]), k=np.mean([x[1] for x in lst]),
                                 pl=np.mean([x[2] for x in lst], axis=0)))
B0 = pd.DataFrame(base_rows); B0.to_csv(os.path.join(OUT, "oos_baseline.csv"), index=False)
lines = ["=== A) 동결 점수 OOS — 필터 바구니 − 기준 바구니(시장별 상위10·희석 제외), 두 시장 평균, 비용 무시(양쪽 동일)"]
for (mid, h), g in B0.groupby(["model", "h"]):
    d = g.groupby("date").mean(numeric_only=True)
    lines.append(f"  [기준] {mid} h{h}: 매수일 {len(d)} · 기준 상위10 시장 대비 {f(bci(d.base - d.bench, h))} · 상위20−상위10 {f(bci(d.top20 - d.base, h))}   ← L3")
R = pd.DataFrame(recs); rows = []
for (fid, h), g in R.groupby(["fid", "h"]):
    g = g.sort_values("date"); ci = bci(g["diff"].values, h)
    plm = np.stack(g.pl.values).mean(axis=0)   # 플라시보 draw 별 전체 평균
    pct = float((plm < g["diff"].mean()).mean())
    half = len(g) // 2; h1, h2 = g["diff"].values[:half].mean(), g["diff"].values[half:].mean()
    rows.append(dict(fid=fid, h=h, n=len(g), k_avg=g.k.mean(), diff=ci[0], lo=ci[1], hi=ci[2], placebo_mean=plm.mean(), placebo_sd=plm.std(), placebo_pct=pct, first_half=h1, second_half=h2))
    lines.append(f"  {fid} h{h}: 빠진 종목 평균 {g.k.mean():.1f}/10 · 개선 {f(ci)} · 무작위 교체 대비 백분위 {pct*100:.0f}% (무작위 평균 {plm.mean()*100:+.2f}±{plm.std()*100:.2f}) · 전반 {h1*100:+.2f} / 후반 {h2*100:+.2f}")
pd.DataFrame(rows).to_csv(os.path.join(OUT, "oos_filters.csv"), index=False)

# ---------------- B) 3년 패널 근사 — lv_b ≈ 저변동(lv60↓), 가드 유니버스, 시장별 상위10 ----------------
os.environ["FS_PANEL"] = os.path.join(REPO, "research", "bigwinners_20260924", "panel.npz")
import fslib as fs
PP = os.environ["FS_PANEL"]
if not os.path.exists(PP):
    import subprocess; subprocess.run([sys.executable, os.path.join(REPO, "research", "fullscan_20260903", "step0_panel.py"), PP], check=True)
P = fs.Panel(PP); T, Nn = P.T, P.N; ok = fs.guards(P); cf = P.close.astype(float); v = P.vol.astype(float)
lv60 = fs.roll_std(P.ret, 60, 40); cvp = fs.roll_std(v, 20, 15) / fs.roll_mean(v, 20, 15); vspike = v / fs.roll_mean(v, 20, 10)
mark = pd.DataFrame(cf).ffill().values; idxm = np.where(P.mk == "KOSPI", 0, 1)
tick = list(P.tick); pd_dates = list(P.dates); pdi = {d: i for i, d in enumerate(pd_dates)}
youngm = np.zeros((T, Nn), bool)
for tk, ld in list_date.items():
    if tk in tick:
        j = tick.index(tk); i0 = int(np.searchsorted(P.dates, ld)); youngm[i0:min(T, i0 + 252), j] = True
anch = list(range(P.idx("20240701"), T - 21, 5)); rowsB = []
for a in anch:
    e = a + 1
    for h in (20, 40):
        if e + h >= T: continue
        res = {}
        for m_ in (0, 1):
            m = ok[a] & (idxm == m_) & np.isfinite(lv60[a]); js = np.where(m)[0]
            if len(js) < 60: continue
            order = js[np.argsort(lv60[a][js], kind="stable")]
            ret = np.where(np.isfinite(cf[e, order]) & (cf[e, order] > 0), mark[e + h, order] / cf[e, order] - 1, 0.)
            rr = dict(zip(order, ret))
            def bask(idxs): return np.mean([rr[j] for j in idxs[:TOP]])
            base = bask(list(order)); top20 = np.mean([rr[j] for j in order[:20]])
            cands = list(order)
            L1 = [j for j in cands if not youngm[a, j]]
            thr = np.nanquantile(vspike[a][order], 2/3); L2 = [j for j in cands if not (vspike[a, j] > thr)]
            med = np.nanmedian(cvp[a][order]); L4 = [j for j in cands if cvp[a, j] <= med]
            out = dict(base=base, L3=top20 - base)
            for nm, lst in (("L1", L1), ("L2", L2), ("L4", L4)):
                k = len(set(order[:TOP]) - set(lst[:TOP]))
                pl = []
                for _ in range(60):
                    if k == 0: pl.append(0.0); continue
                    drop = set(rng.choice(order[:TOP], k, replace=False)); pick = [j for j in cands if j not in drop]
                    pl.append(bask(pick) - base)
                out[nm] = bask(lst) - base; out[nm + "_pl"] = np.array(pl); out[nm + "_k"] = k
            res[m_] = out
        if len(res) == 2:
            rec = dict(date=pd_dates[a], h=h, L3=np.mean([res[x]["L3"] for x in res]))
            for nm in ("L1", "L2", "L4"):
                rec[nm] = np.mean([res[x][nm] for x in res]); rec[nm + "_k"] = np.mean([res[x][nm + "_k"] for x in res])
                rec[nm + "_pl"] = np.mean([res[x][nm + "_pl"] for x in res], axis=0)
            rowsB.append(rec)
RB = pd.DataFrame(rowsB)
lines.append("\n=== B) 3년 패널 근사(lv_b ≈ 가드 유니버스 저변동 lv60↓, ROE·과매도 게이트 없음) · 5일 앵커 2024-07~ · 두 시장 평균")
for h, g in RB.groupby("h"):
    for nm in ("L1", "L2", "L3", "L4"):
        ci = bci(g[nm].values, max(1, h // 5))
        ys = " / ".join(f"{y}:{g[g.date.str.startswith(y)][nm].mean()*100:+.2f}" for y in ("2024", "2025", "2026"))
        if nm != "L3":
            plm = np.stack(g[nm + "_pl"].values).mean(axis=0); pct = float((plm < g[nm].mean()).mean())
            extra = f" · 빠진 종목 {g[nm+'_k'].mean():.1f}/10 · 무작위 교체 대비 백분위 {pct*100:.0f}%"
        else: extra = ""
        lines.append(f"  {nm} h{h}: 개선 {f(ci)}{extra} · 연도 {ys}")
RB.drop(columns=[c for c in RB.columns if c.endswith("_pl")]).to_csv(os.path.join(OUT, "panel_lvb_proxy.csv"), index=False)
txt = "\n".join(lines); open(os.path.join(OUT, "summary.txt"), "w", encoding="utf-8").write(txt); print(txt)
