# -*- coding: utf-8 -*-
"""첫 주에 뛸 종목을 미리 가릴 수 있나 — 매수 전 변수 전수 스캔, A 표본(5개월 실제 stage3_final) (2026-11-08, 탐색·읽기 전용 · 채택 아님)
틀은 research/EARLY_RISE_SCAN_20261108.md §0 (결과 전 고정). 출력 research/out_early_rise_scan/*.csv + 표준출력.
표본: stage3_final 전 행(3단계 통과) 2026-06-02~, 게이트·앵커 중복 제거 = leaderboard.py. 보조: v30 시장별 상위 10.
목표: T1 5일 초과 · T2 성공(5일째 비용 0.5% 뒤 >0 and 20일째 > 5일째) · T3 20일 초과 · T4 40일 초과. 진입 t+1 종가, 시장 = 같은 시장 전 종목 동일가중.
변수: stage3 숫자 열(식별자·가격 수준·run 상수 제외) + 동결 점수(v30·lv_b·wu 각 모델) + ohlcv 파생(수급 비중·공매도·신용·PBR·PER·가격 파생) + 업종 dd20(현재 분류).
잣대: 날짜별(시장 안) 스피어만 IC → 날짜 평균, 20일 블록 부트스트랩 2,000회 seed 7; 상위20%−하위20% 차이; Bonferroni 0.05/(2M); 앞/뒤 절반."""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent; sys.path.insert(0, str(REPO))
import leaderboard as lb
OUT = HERE / "out_early_rise_scan"; OUT.mkdir(exist_ok=True)
rng = np.random.default_rng(7); NB = 2000; BLOCK = 20; COST = 0.005; MIN_N = 20
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)

# ---------- 가격·시장 ----------
close, mkt = lb.load_ohlcv()
dates = list(close.index); didx = {d: i for i, d in enumerate(dates)}; N = len(dates)
cf = close.ffill(); C = cf.values; tick_idx = {t: j for j, t in enumerate(cf.columns)}
ret = close.pct_change(fill_method=None)
ew = {}
for m in ("KOSPI", "KOSDAQ"):
    cols = [t for t in close.columns if mkt.get(t) == m]
    ew[m] = (1 + ret[cols].mean(axis=1).fillna(0)).cumprod().values
con_o = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
raw = pd.read_sql("SELECT ticker,date,open,high,low,close,volume FROM daily_ohlcv WHERE date>='20260401'", con_o)
hi = raw.pivot_table(index="date", columns="ticker", values="high").reindex(dates); lo = raw.pivot_table(index="date", columns="ticker", values="low").reindex(dates)
vol = raw.pivot_table(index="date", columns="ticker", values="volume").reindex(dates); opn = raw.pivot_table(index="date", columns="ticker", values="open").reindex(dates)
del raw
flows = pd.read_sql("SELECT ticker,date,person_net_val,foreign_net_val,inst_net_val,pension_net_val,trust_net_val,secfirm_net_val,prveq_net_val,insu_net_val FROM daily_flows", con_o)
shorts = pd.read_sql("SELECT ticker,date,short_vol_ratio,credit_bal_rate,loan_bal_qty FROM short_flows WHERE date>='20260501'", con_o)
valn = pd.read_sql("SELECT ticker,date,pbr,per FROM valuation_daily", con_o)
con_o.close()
# 수급 5일 비중: 투자자별 5일 순매수액 합 / 5일 |개인|+|외국인|+|기관| 합
F = flows.sort_values(["ticker", "date"]).set_index(["date", "ticker"]).sort_index()
Fw = {}
for c in ["person_net_val", "foreign_net_val", "inst_net_val", "pension_net_val", "trust_net_val", "secfirm_net_val", "prveq_net_val", "insu_net_val"]:
    Fw[c] = flows.pivot_table(index="date", columns="ticker", values=c).reindex(dates)
den = (Fw["person_net_val"].abs() + Fw["foreign_net_val"].abs() + Fw["inst_net_val"].abs()).rolling(5, min_periods=3).sum()
flow_share = {c.replace("_net_val", "_5d_share"): Fw[c].rolling(5, min_periods=3).sum() / den.replace(0, np.nan) for c in Fw}
sv = shorts.pivot_table(index="date", columns="ticker", values="short_vol_ratio").reindex(dates)
cr = shorts.pivot_table(index="date", columns="ticker", values="credit_bal_rate").reindex(dates)
ln = shorts.pivot_table(index="date", columns="ticker", values="loan_bal_qty").reindex(dates)
pbr = valn.pivot_table(index="date", columns="ticker", values="pbr").reindex(dates).ffill(limit=5)
per = valn.pivot_table(index="date", columns="ticker", values="per").reindex(dates).ffill(limit=5)
r1 = close.pct_change(fill_method=None)
rv5 = r1.rolling(5).std()
vol20 = vol.rolling(20).mean()
low20 = close.rolling(20).min()
# 업종 dd20(현재 분류)
try:
    sc = json.loads((REPO / "sector_cache.json").read_text(encoding="utf-8"))
    sec_of = {k: (v.get("sector") if isinstance(v, dict) else v) for k, v in sc.items()}
except Exception as e:
    print("sector_cache 로드 실패", e); sec_of = {}
sec_dd = {}
if sec_of:
    secs = pd.Series(sec_of).reindex(close.columns)
    for s in secs.dropna().unique():
        cols = list(secs[secs == s].index)
        if len(cols) < 5: continue
        idx = (1 + ret[cols].mean(axis=1).fillna(0)).cumprod()
        sec_dd[s] = (idx / idx.rolling(20).max() - 1).values
print(f"가격 {N}일 · 업종 {len(sec_dd)}개")

# ---------- stage3 ----------
con = sqlite3.connect(f"file:{lb.DB}?mode=ro", uri=True)
partial, dbl, _ = lb.build_gates(con, dates); excl = partial | dbl
S3 = pd.read_sql("SELECT * FROM stage3_final WHERE run_id>='20260602'", con)
S3["ticker"] = S3["ticker"].astype(str).str.zfill(6)
V = pd.read_sql("SELECT run_id,ticker,final_score_v3 AS v30_score FROM v3_scores WHERE model_id='v30'", con); V["ticker"] = V["ticker"].str.zfill(6)
L = pd.read_sql("SELECT run_id,ticker,lowvol_score AS lvb_score FROM lowvol_scores WHERE model_id='lv_b'", con); L["ticker"] = L["ticker"].str.zfill(6)
W = pd.read_sql("SELECT run_id,ticker,model_id,wu_score FROM wu_scores WHERE model_id IN ('sv_a','le_a','qs_a','px_a','sv_b')", con); W["ticker"] = W["ticker"].str.zfill(6)
W = W.pivot_table(index=["run_id", "ticker"], columns="model_id", values="wu_score").reset_index(); W.columns = [c if c in ("run_id", "ticker") else f"wu_{c}" for c in W.columns]
con.close()
keep = lb.dedupe_by_anchor(S3.rename(columns={}), didx, excl, reg=None)
S3 = S3[S3["run_id"].isin(keep)].merge(V, on=["run_id", "ticker"], how="left").merge(L, on=["run_id", "ticker"], how="left").merge(W, on=["run_id", "ticker"], how="left")
S3["t"] = S3["run_id"].map(lambda r: lb.anchor(r, didx))
S3 = S3.dropna(subset=["t"]); S3["t"] = S3["t"].astype(int)
S3["mk"] = S3["market"].str.upper().map(lambda m: "KOSPI" if m == "KOSPI" else "KOSDAQ")
print(f"stage3 행 {len(S3):,} · 앵커 {S3.t.nunique()} · 게이트 제외 {sorted(excl)}")

# ---------- 목표 ----------
def fwd(row_t, j, h):
    e = row_t + 1
    if e + h >= N or np.isnan(C[e, j]) or C[e, j] <= 0: return np.nan
    return C[e + h, j] / C[e, j] - 1
J = S3["ticker"].map(tick_idx)
S3 = S3[J.notna()].copy(); S3["j"] = J[J.notna()].astype(int).values
T = S3["t"].values; Jv = S3["j"].values; M = S3["mk"].values
for h, nm in ((5, "r5"), (20, "r20"), (40, "r40")):
    S3[nm] = [fwd(t, j, h) for t, j in zip(T, Jv)]
    S3[f"m{h}"] = [ew[m][t + 1 + h] / ew[m][t + 1] - 1 if t + 1 + h < N else np.nan for t, m in zip(T, M)]
S3["T1"] = (S3["r5"] - S3["m5"]) * 100; S3["T3"] = (S3["r20"] - S3["m20"]) * 100; S3["T4"] = (S3["r40"] - S3["m40"]) * 100
S3["T2"] = np.where(S3["r20"].isna(), np.nan, ((S3["r5"] - COST > 0) & ((1 + S3["r20"]) > (1 + S3["r5"]))).astype(float))

# ---------- 변수 ----------
EXCL = {"price", "52w_high", "52w_low", "corp_code", "regime_score", "regime_kospi_score", "regime_fx_score", "regime_flow_score", "kospi_vs_sma200_%", "kospi_return_1m_%",
        "usdkrw", "usdkrw_vs_sma20_%", "usdkrw_return_1m_%", "foreign_kospi_5d_억", "foreign_kospi_5d_raw_억", "foreign_kospi_5d_adjusted_억", "foreign_proxy_success",
        "foreign_proxy_total", "foreign_proxy_coverage", "supply_fetched", "annual_year", "t", "j", "r5", "r20", "r40", "m5", "m20", "m40", "T1", "T2", "T3", "T4"}
num_cols = [c for c in S3.select_dtypes("number").columns if c not in EXCL]
# ohlcv 파생(t 기준)
def at(mat, t, tk):
    try: return mat.iat[t, mat.columns.get_loc(tk)]
    except KeyError: return np.nan
tk = S3["ticker"].values
for name, mat in list(flow_share.items()) + [("short_vol_ratio", sv), ("credit_bal_rate", cr), ("pbr", pbr), ("per", per)]:
    S3[name] = [at(mat, t, k) for t, k in zip(T, tk)]
S3["ret_t"] = [at(r1, t, k) * 100 for t, k in zip(T, tk)]
S3["range_t"] = [(at(hi, t, k) - at(lo, t, k)) / at(close, t, k) * 100 for t, k in zip(T, tk)]
S3["close_pos_t"] = [(at(close, t, k) - at(lo, t, k)) / max(at(hi, t, k) - at(lo, t, k), 1e-9) for t, k in zip(T, tk)]   # 당일 봉 안에서 종가 위치(0 저가~1 고가)
S3["gap_t"] = [(at(opn, t, k) / C[t - 1, tick_idx[k]] - 1) * 100 if t > 0 and C[t - 1, tick_idx[k]] > 0 else np.nan for t, k in zip(T, tk)]
S3["rv5"] = [at(rv5, t, k) * 100 for t, k in zip(T, tk)]
S3["vol_t_vs20"] = [at(vol, t, k) / at(vol20, t, k) if at(vol20, t, k) else np.nan for t, k in zip(T, tk)]
S3["vs_low20_%"] = [(at(close, t, k) / at(low20, t, k) - 1) * 100 for t, k in zip(T, tk)]
S3["sector_dd20"] = [sec_dd[sec_of[k]][t] * 100 if (k in sec_of and sec_of[k] in sec_dd) else np.nan for t, k in zip(T, tk)]
S3["in_v30_top10"] = 0
for (rid, m), g in S3.dropna(subset=["v30_score"]).groupby(["run_id", "mk"]):
    top = g.sort_values(["v30_score", "ticker"], ascending=[False, True]).head(10).index
    S3.loc[top, "in_v30_top10"] = 1
VARS = num_cols + list(flow_share) + ["short_vol_ratio", "credit_bal_rate", "pbr", "per", "ret_t", "range_t", "close_pos_t", "gap_t", "rv5", "vol_t_vs20", "vs_low20_%", "sector_dd20"]
VARS = [v for v in VARS if v != "in_v30_top10"]
S3.to_pickle(OUT / "panel.pkl")
print(f"변수 {len(VARS)}개: {VARS}")

# ---------- 스캔 ----------
GROUP = ["t", "mk"]
def day_ic(df, var, tgt):
    out = []
    for key, g in df.groupby(GROUP):
        t = key[0] if isinstance(key, tuple) else key
        g = g[[var, tgt]].dropna()
        if len(g) < MIN_N or g[var].nunique() < 2 or g[tgt].nunique() < 2: continue
        out.append((t, g[var].rank().corr(g[tgt].rank())))
    return pd.DataFrame(out, columns=["t", "ic"])
def day_q(df, var, tgt):
    out = []
    for key, g in df.groupby(GROUP):
        t = key[0] if isinstance(key, tuple) else key
        g = g[[var, tgt]].dropna()
        if len(g) < MIN_N or g[var].nunique() < 5: continue
        q1, q4 = g[var].quantile(0.2), g[var].quantile(0.8)
        a, b = g.loc[g[var] >= q4, tgt], g.loc[g[var] <= q1, tgt]
        if len(a) >= 3 and len(b) >= 3: out.append((t, a.mean() - b.mean()))
    return pd.DataFrame(out, columns=["t", "d"])
def boot(x_by_t, level=0.95):
    s = x_by_t.groupby("t")[x_by_t.columns[-1]].mean(); x = s.values; n = len(x)
    if n < 4: return (np.nan, np.nan)
    nb = int(np.ceil(n / BLOCK)); ms = []
    for _ in range(NB):
        st = rng.integers(0, n, nb); idx = np.concatenate([(k + np.arange(BLOCK)) % n for k in st])[:n]; ms.append(x[idx].mean())
    a = (1 - level) / 2 * 100
    return (float(np.percentile(ms, a)), float(np.percentile(ms, 100 - a)))

def scan(df, label):
    Mv = len(VARS); bonf = 1 - 0.05 / (2 * Mv)
    rows = []
    for v in VARS:
        rec = dict(sample=label, var=v, cover=float(df[v].notna().mean()))
        for tg in ("T1", "T2", "T3", "T4"):
            ic = day_ic(df, v, tg)
            if ic.empty: continue
            s = ic.groupby("t")["ic"].mean(); rec[f"{tg}_ic"] = s.mean(); rec[f"{tg}_n"] = len(s)
            rec[f"{tg}_lo"], rec[f"{tg}_hi"] = boot(ic)
            if tg in ("T1", "T2"):
                rec[f"{tg}_blo"], rec[f"{tg}_bhi"] = boot(ic, bonf)
                med = np.median(s.index); a, b = s[s.index <= med], s[s.index > med]
                rec[f"{tg}_front"] = a.mean(); rec[f"{tg}_back"] = b.mean()
                rec[f"{tg}_back_lo"], rec[f"{tg}_back_hi"] = boot(ic[ic.t > med])
                q = day_q(df, v, tg); rec[f"{tg}_q"] = q.groupby("t")["d"].mean().mean() if not q.empty else np.nan
        for tg in ("T1", "T2"):
            ok = all(k in rec for k in (f"{tg}_blo", f"{tg}_back_lo"))
            rec[f"{tg}_cand"] = bool(ok and (rec[f"{tg}_blo"] > 0 or rec[f"{tg}_bhi"] < 0) and np.sign(rec[f"{tg}_front"]) == np.sign(rec[f"{tg}_back"]) and (rec[f"{tg}_back_lo"] > 0 or rec[f"{tg}_back_hi"] < 0))
        rows.append(rec)
    R = pd.DataFrame(rows); R["absT1"] = R["T1_ic"].abs(); R = R.sort_values("absT1", ascending=False).drop(columns="absT1")
    return R, bonf

for label, df in (("A_stage3_all", S3), ("A_v30_top10", S3[S3.in_v30_top10 == 1])):
    if label == "A_v30_top10": GROUP = ["t"]; MIN_N = 12      # 하루 20종목뿐이라 두 시장 합쳐 날짜 단위
    R, bonf = scan(df, label)
    R.to_csv(OUT / f"{label}_summary.csv", index=False, encoding="utf-8-sig")
    print(f"\n########## {label}: 행 {len(df):,} · 앵커 {df.t.nunique()} · T1 분모 {df.T1.notna().sum():,} · T2 {df.T2.notna().sum():,} · T4 {df.T4.notna().sum():,} · 변수 {len(VARS)} · Bonferroni 구간 {bonf*100:.2f}%")
    show = ["var", "cover", "T1_ic", "T1_lo", "T1_hi", "T1_blo", "T1_bhi", "T1_front", "T1_back", "T1_back_lo", "T1_back_hi", "T1_q", "T1_cand", "T2_ic", "T2_lo", "T2_hi", "T2_blo", "T2_bhi", "T2_front", "T2_back", "T2_q", "T2_cand", "T3_ic", "T4_ic", "T4_lo", "T4_hi", "T1_n"]
    print(R[[c for c in show if c in R.columns]].round(3).to_string(index=False))
    cands = R[(R.get("T1_cand", False) == True) | (R.get("T2_cand", False) == True)]
    print(f"\n후보(사전 규칙 통과): {list(cands['var'])}")
