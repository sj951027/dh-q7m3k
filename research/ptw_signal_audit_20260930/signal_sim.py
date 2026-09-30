# signal_sim.py — PTW 신호별 사후 성과: 가상 포지션에 운영 compute_signal 을 매일 저녁 적용. DB 무접촉(패널 npz 만).
# 사용: python signal_sim.py <profile:#스윙|#저변동> <n_entries> <seed> <out.csv>
import os, sys, time, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
S = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"C:\Users\SAMSUNG\Documents\GitHub\Position-Tracker-Web")
from app.engine_adapter import compute_signal
import signal_engine as se

prof, NE, seed, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
HOLD = 60
z = np.load(os.path.join(S, "panel_0929.npz"), allow_pickle=True)
dates = pd.to_datetime(z["dates"].astype(str)); tick = z["tick"].astype(str); mk = z["mk"].astype(str)
O, H, L, C, V = (z[k].astype(float) for k in ("open", "high", "low", "close", "vol"))
KS = pd.Series(z["kospi"].astype(float), index=dates).ffill(); KQ = pd.Series(z["kosdaq"].astype(float), index=dates).ffill()
T, N = C.shape
ret = np.vstack([np.full((1, N), np.nan), C[1:] / C[:-1] - 1])
amt20 = pd.DataFrame(C * V).rolling(20, min_periods=10).mean().values
lv60 = pd.DataFrame(ret).rolling(60, min_periods=40).std().values
jump = pd.DataFrame((np.abs(ret) > 0.32).astype(float)).rolling(21, min_periods=5).max().values > 0
ok = (amt20 >= 5e8) & np.isfinite(C) & ~jump & (lv60 >= 0.003)
rng = np.random.default_rng(seed)
cand_t = np.arange(np.searchsorted(dates, pd.Timestamp("2024-01-02")), T - 25)
entries = []
while len(entries) < NE:
    t = int(rng.choice(cand_t)); js = np.where(ok[t])[0]
    if len(js) < 200: continue
    if prof == "#저변동":
        thr = np.nanquantile(lv60[t, js], 1 / 3); js = js[lv60[t, js] <= thr]
    entries.append((t, int(rng.choice(js))))

rows = []; t0 = time.time()
for k, (te, j) in enumerate(entries):
    idx = KS if mk[j] == "KOSPI" else KQ
    df_all = pd.DataFrame({"Open": O[:, j], "High": H[:, j], "Low": L[:, j], "Close": C[:, j], "Volume": V[:, j]}, index=dates)
    avg = C[te, j]; first = dates[te].to_pydatetime()
    hold = {"code": tick[j], "name": "", "qty": 10, "avg_price": avg, "first_buy": first, "strategy": prof}
    prev_sig, prev = "", None
    for t in range(te, min(te + HOLD + 1, T)):
        d = dates[t]
        df = df_all.iloc[max(0, t - 110): t + 1]
        df = df[df.index >= d - pd.Timedelta(days=se.LOOKBACK_DAYS + 30)].dropna(subset=["Close"])
        if len(df) < 25 or df.index[-1] != d: break
        h = dict(hold)
        if prev:
            if prev.get("high_water_price") is not None: h["prev_high_water"] = prev["high_water_price"]
            if prev.get("grad_date_iso"): h["grad_date_iso"] = prev["grad_date_iso"]
            if isinstance(prev.get("days_since_grad"), (int, float)): h["days_since_grad"] = int(prev["days_since_grad"]) + 1
            ms = {x: prev.get(x) for x in ("mfe_pct", "mae_pct", "mfe_date", "mae_date")}
            if any(v is not None for v in ms.values()): h["mfe_state"] = ms
        try:
            r = compute_signal(h, df, idx[idx.index <= d], None, prev_signal=prev_sig, asof=d.to_pydatetime().replace(hour=20),
                               was_graduated=bool(prev.get("graduated")) if prev else False, prev_grad_avg=(prev or {}).get("grad_avg"))
        except Exception:
            break
        if not r: break
        rec = {"entry": k, "t": t, "day": t - te, "code": tick[j], "mkt": mk[j], "signal": r["signal"], "level": r.get("level"), "pnl": r.get("pnl")}
        for hh in (5, 10, 20):
            if t + hh < T and np.isfinite(C[t + hh, j]) and C[t, j] > 0:
                rr = C[t + hh, j] / C[t, j] - 1; ir = idx.iloc[t + hh] / idx.iloc[t] - 1
                rec[f"r{hh}"] = rr; rec[f"x{hh}"] = rr - ir
        rows.append(rec); prev_sig, prev = r["signal"], r
    if k % 100 == 0: print(prof, k, f"{time.time()-t0:.0f}s", flush=True)
pd.DataFrame(rows).to_csv(out, index=False)
print("done", prof, len(rows), f"{time.time()-t0:.0f}s")
