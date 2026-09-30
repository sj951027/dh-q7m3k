# exit_vs_hold.py — RESEARCH_signal_exit_vs_hold_20260930 §0 그대로. DB 무접촉(패널 npz + 추출 목록 csv).
# 사용: python exit_vs_hold.py <LVB|V30|Q3Y> <worker_idx> <n_workers> <out.csv>
import os, sys, time, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
S = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"C:\Users\SAMSUNG\Documents\GitHub\Position-Tracker-Web")
from app.engine_adapter import compute_signal
import signal_engine as se

SAMPLE, WI, NW, OUT = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
H = 40; COST = 0.0035; TOP = 10
S1 = {"🟡 부분익절", "🟠 익절 준비", "🔻 고점 이탈 익절", "🔻 추세 둔화 익절"}
S2 = S1 | {"🔻 모멘텀 둔화", "⚠️ RSI 급락", "📉 시장 대비 약세"}
PROF = "#과매도" if SAMPLE == "V30" else "#저변동"

z = np.load(os.path.join(S, "panel_0929.npz"), allow_pickle=True)
dstr = z["dates"].astype(str); dates = pd.to_datetime(dstr); tick = z["tick"].astype(str); mk = z["mk"].astype(str)
O, Hh, L, C, V, SH = (z[k].astype(float) for k in ("open", "high", "low", "close", "vol", "shares"))
T, N = C.shape; di = {d: i for i, d in enumerate(dstr)}; ti = {t: i for i, t in enumerate(tick)}
KS = pd.Series(z["kospi"].astype(float), index=dates).ffill(); KQ = pd.Series(z["kosdaq"].astype(float), index=dates).ffill()

# ---- 목록 ----
if SAMPLE in ("LVB", "V30"):
    Ls = pd.read_csv(os.path.join(S, "lists_" + ("lv_b" if SAMPLE == "LVB" else "v30") + ".csv"), dtype={"date": str, "ticker": str})
    LIST = {(d, m): list(g.sort_values("rank").ticker) for (d, m), g in Ls.groupby(["date", "market"])}
    list_dates = sorted(Ls.date.unique())
    def top_list(t, m):   # t 시점에 쓸 수 있는 최신 목록
        ds = [d for d in list_dates if di.get(d, 10**9) <= t]
        return [x for x in LIST.get((ds[-1], m), []) if x in ti] if ds else []
    anchors = [di[d] for d in list_dates if d in di]
else:
    ret = np.vstack([np.full((1, N), np.nan), C[1:] / C[:-1] - 1])
    amt20 = pd.DataFrame(C * V).rolling(20, min_periods=10).mean().values
    lv60 = pd.DataFrame(ret).rolling(60, min_periods=40).std().values
    to20 = pd.DataFrame(V / SH).rolling(20, min_periods=10).mean().values
    flat = pd.DataFrame((np.abs(ret) < 1e-9).astype(float)).rolling(63, min_periods=20).mean().values > 0.5
    jump = pd.DataFrame((np.abs(ret) > 0.32).astype(float)).rolling(21, min_periods=5).max().values > 0
    ok = (amt20 >= 5e8) & np.isfinite(C) & ~jump & ~flat & (lv60 >= 0.003) & np.isfinite(to20)
    def top_list(t, m):
        js = np.where(ok[t] & (mk == m))[0]
        if len(js) < 30: return []
        r1 = pd.Series(lv60[t, js]).rank(pct=True).values; r2 = pd.Series(to20[t, js]).rank(pct=True).values
        return [tick[j] for j in js[np.argsort(r1 + r2, kind="stable")][:TOP]]
    anchors = list(range(int(np.searchsorted(dstr, "20240102")), T, 5))
anchors = [a for a in anchors if a + 1 + H < T][WI::NW]

def price_df(j, t):
    lo = max(0, t - 110)
    df = pd.DataFrame({"Open": O[lo:t + 1, j], "High": Hh[lo:t + 1, j], "Low": L[lo:t + 1, j], "Close": C[lo:t + 1, j], "Volume": V[lo:t + 1, j]}, index=dates[lo:t + 1])
    return df[df.index >= dates[t] - pd.Timedelta(days=se.LOOKBACK_DAYS + 30)].dropna(subset=["Close"])

rot_cache = {}
def rot_ret(s_sell, m, end):
    key = (s_sell, m, end)
    if key not in rot_cache:
        lst = top_list(s_sell - 1, m)      # 신호일(s_sell-1) 저녁 목록 → 다음날 종가 매수
        rs = [C[end, ti[x]] / C[s_sell, ti[x]] - 1 for x in lst if np.isfinite(C[s_sell, ti[x]]) and C[s_sell, ti[x]] > 0 and np.isfinite(C[end, ti[x]])]
        rot_cache[key] = float(np.mean(rs)) if rs else 0.0
    return rot_cache[key]

rows = []; t0 = time.time()
for ai, a in enumerate(anchors):
    e = a + 1; end = e + H
    for m in ("KOSPI", "KOSDAQ"):
        for tk in top_list(a, m):
            j = ti[tk]
            if not (np.isfinite(C[e, j]) and C[e, j] > 0 and np.isfinite(C[end, j])): continue
            idx = KS if mk[j] == "KOSPI" else KQ
            hold = {"code": tk, "name": "", "qty": 10, "avg_price": C[e, j], "first_buy": dates[e].to_pydatetime(), "strategy": PROF}
            prev_sig, prev, s1 = "", None, None; s2 = None; sig1 = sig2 = ""
            for t in range(e, end - 1):          # 신호일 t → 매도 t+1 ≤ end-1
                df = price_df(j, t)
                if len(df) < 25 or df.index[-1] != dates[t]: continue
                h = dict(hold)
                if prev:
                    if prev.get("high_water_price") is not None: h["prev_high_water"] = prev["high_water_price"]
                    ms = {x: prev.get(x) for x in ("mfe_pct", "mae_pct", "mfe_date", "mae_date")}
                    if any(v is not None for v in ms.values()): h["mfe_state"] = ms
                try:
                    r = compute_signal(h, df, idx[idx.index <= dates[t]], None, prev_signal=prev_sig, asof=dates[t].to_pydatetime().replace(hour=20))
                except Exception:
                    r = None
                if not r: continue
                sg = r["signal"]; prev_sig, prev = sg, r
                if s2 is None and sg in S2: s2, sig2 = t, sg
                if s1 is None and sg in S1: s1, sig1 = t, sg
                if s1 is not None and s2 is not None: break
            A = C[end, j] / C[e, j] - 1 - COST
            rec = {"sample": SAMPLE, "anchor": dstr[a], "market": m, "ticker": tk, "A": A,
                   "ix": idx.iloc[end] / idx.iloc[e] - 1}
            for nm, s in (("1", s1), ("2", s2)):
                if s is None:
                    rec["B" + nm] = A; rec["C" + nm] = A; rec["day" + nm] = np.nan
                else:
                    sell = s + 1; gross = C[sell, j] / C[e, j]
                    rec["C" + nm] = gross - 1 - COST
                    rec["B" + nm] = gross * (1 + rot_ret(sell, m, end)) - 1 - 2 * COST
                    rec["day" + nm] = s - e
            rec["sig1"], rec["sig2"] = sig1, sig2
            rows.append(rec)
    if ai % 5 == 0: print(SAMPLE, WI, ai, len(anchors), f"{time.time()-t0:.0f}s", flush=True)
pd.DataFrame(rows).to_csv(OUT, index=False)
print("done", SAMPLE, WI, len(rows), f"{time.time()-t0:.0f}s")
