# -*- coding: utf-8 -*-
"""과매도 바구니의 '실행 세부' 11년 검증 — 외부 조사 카드 B2(종가 매수 vs 시가 매수)·B4(보유 40일 vs 더 길게) (2026-10-30, 사후 관측 · 채택 아님)

10년 DB(ohlcv_10y.db, 2015~, 폐지 포함·수정주가, open·close 있음)만 읽는다. 틀은 `pick_exclude_10y_20261030.py` 와 같다
(정리 유니버스 · 과매도 = 20일 수익 하위 20% · 신호일 5거래일 간격 · 거래량 0·동전주 제외 · 40일 안 상폐 = 마지막 가격 · 동일가중 · 월 블록 부트스트랩 2,000회 seed 7).
B4 보유 기간: 매수 t+1 종가 고정, 매도 t+1+h 종가, h = 20·40·60·80. 과매도 초과 = 과매도 바구니 − 전 종목 바구니(같은 h). 한계 초과 = 초과(h) − 초과(h−20) (40일 뒤 20일을 더 들면 초과가 더 붙나).
B2 진입 가격(h=40 고정, 매도 t+41 종가): ① t+1 종가(기준) · ② t+1 시가 · ③ t+2 종가 · ④ t+2 시가. 그리고 신호 다음날의 야간(t 종가→t+1 시가)·장중(t+1 시가→t+1 종가) 바구니 수익.
재현: python research/pick_exec_hold_10y_20261030.py → research/out_pick_exec/*.csv (약 1분)."""
import os, sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("DH_REPO", HERE.parent))
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
OUT = Path(os.environ.get("OUT_DIR", HERE / "out_pick_exec")); OUT.mkdir(exist_ok=True, parents=True)
STEP = 5; SPLIT = "20210101"; HS = (20, 40, 60, 80); HMAX = max(HS); rng = np.random.default_rng(7)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)


def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    if len(um) < 2 or len(vals) < 2:
        return (np.nan, np.nan)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


def nonov(pos, gap=40):
    c = 0; last = -10 ** 9
    for p in sorted(pos):
        if p - last >= gap:
            c += 1; last = p
    return c


t0 = time.time()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, open, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index()
con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
opn = px.pivot_table(index="date", columns="ticker", values="open", aggfunc="last").reindex(close.index); opn = opn.where(opn > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
dates = list(close.index); N = len(dates); tick = list(close.columns)
ks_r20 = (ks / ks.shift(20) - 1).reindex(dates)
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; ou = opn.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, opn, vol
tick = list(cu.columns)
dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
cf = cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()                       # 상폐 = 마지막 가격
r20 = cu / cu.shift(20) - 1
penny = cu < 1000
# B4: 매수 t+1 종가 → 매도 t+1+h 종가
F = {h: (cf.shift(-1 - h) / cu.shift(-1) - 1) * 100 for h in HS}
# B2: 진입 변형(h=40)
sell41 = cf.shift(-41)
E = {"① t+1 종가": (sell41 / cu.shift(-1) - 1) * 100, "② t+1 시가": (sell41 / ou.shift(-1) - 1) * 100,
     "③ t+2 종가": (sell41 / cu.shift(-2) - 1) * 100, "④ t+2 시가": (sell41 / ou.shift(-2) - 1) * 100}
night1 = (ou.shift(-1) / cu - 1) * 100            # t 종가 → t+1 시가
intra1 = (cu.shift(-1) / ou.shift(-1) - 1) * 100  # t+1 시가 → t+1 종가
del cf, sell41
print(f"유니버스 {cu.shape[1]} 종목 · 날 {N} · {time.time()-t0:.0f}s")

rows = []
for i in range(130, N - HMAX - 1, STEP):
    r = r20.iloc[i]
    v0 = (vu.iloc[i].fillna(0) == 0) | (vu.iloc[i + 1].fillna(0) == 0)
    ok = r.notna() & ~v0 & ~penny.iloc[i].fillna(True) & F[HMAX].iloc[i].notna() & E["④ t+2 시가"].iloc[i].notna()
    if ok.sum() < 300:
        continue
    d = dates[i]; A = bool(ks_r20.iloc[i] == ks_r20.iloc[i] and ks_r20.iloc[i] <= -0.05)
    os_ = ok & (r <= r[ok].quantile(0.20))
    row = dict(date=d, month=d[:6], i=i, A=A, half=("앞" if d < SPLIT else "뒤"), n_os=int(os_.sum()))
    for h in HS:
        f = F[h].iloc[i]; row[f"os{h}"] = float(f[os_].mean()); row[f"all{h}"] = float(f[ok].mean()); row[f"exc{h}"] = row[f"os{h}"] - row[f"all{h}"]
    for k, e in E.items():
        f = e.iloc[i]; row[f"os_{k}"] = float(f[os_].mean()); row[f"exc_{k}"] = float(f[os_].mean() - f[ok].mean())
    row["night_os"] = float(night1.iloc[i][os_].mean()); row["night_all"] = float(night1.iloc[i][ok].mean())
    row["intra_os"] = float(intra1.iloc[i][os_].mean()); row["intra_all"] = float(intra1.iloc[i][ok].mean())
    rows.append(row)
R = pd.DataFrame(rows); R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
print(f"신호일 {len(R)} · 비겹침(40일) {nonov(R.i)} · {time.time()-t0:.0f}s")
SCOPES = (("전체", R), ("코스피 급락 날", R[R.A]), ("그 밖", R[~R.A]), ("앞반 2015~20", R[R.half == "앞"]), ("뒤반 2021~", R[R.half == "뒤"]))

print("\n[B4] 보유 기간 — 과매도 바구니 절대 수익 · 전 종목 · 초과(%p) · 한계 초과(직전 h 대비)")
out = []
for scope, sub in SCOPES:
    if len(sub) < 8:
        continue
    for j, h in enumerate(HS):
        lo, hi = block_ci(sub[f"exc{h}"], sub.month)
        marg = sub[f"exc{h}"] - sub[f"exc{HS[j-1]}"] if j else sub[f"exc{h}"]
        mlo, mhi = block_ci(marg, sub.month)
        out.append(dict(범위=scope, h=h, 날수=len(sub), 과매도=sub[f"os{h}"].mean(), 전종목=sub[f"all{h}"].mean(), 초과=sub[f"exc{h}"].mean(), 하한=lo, 상한=hi,
                        양수비율=(sub[f"exc{h}"] > 0).mean() * 100, 한계초과=marg.mean(), 한계하한=mlo, 한계상한=mhi, 일당초과=sub[f"exc{h}"].mean() / h * 20))
T4 = pd.DataFrame(out); print(T4.round(2).to_string(index=False)); T4.to_csv(OUT / "B4_hold.csv", index=False, encoding="utf-8-sig")

print("\n[B2] 진입 가격(h=40, 매도 t+41 종가) — 과매도 바구니 절대 수익 · 초과(%p) · 기준(① t+1 종가) 대비 차이")
out = []
for scope, sub in SCOPES:
    if len(sub) < 8:
        continue
    for k in E:
        diff = sub[f"os_{k}"] - sub["os_① t+1 종가"]; lo, hi = block_ci(diff, sub.month)
        out.append(dict(범위=scope, 진입=k, 날수=len(sub), 과매도=sub[f"os_{k}"].mean(), 초과=sub[f"exc_{k}"].mean(), 기준대비=diff.mean(), 하한=lo, 상한=hi, 양수비율=(diff > 0).mean() * 100))
T2 = pd.DataFrame(out); print(T2.round(2).to_string(index=False)); T2.to_csv(OUT / "B2_entry.csv", index=False, encoding="utf-8-sig")

print("\n[B2 보조] 신호 다음날 야간(t 종가→t+1 시가)·장중(t+1 시가→t+1 종가) 바구니 수익(%)")
out = []
for scope, sub in SCOPES:
    if len(sub) < 8:
        continue
    out.append(dict(범위=scope, 날수=len(sub), 야간_과매도=sub.night_os.mean(), 야간_전종목=sub.night_all.mean(), 야간_CI=block_ci(sub.night_os, sub.month),
                    장중_과매도=sub.intra_os.mean(), 장중_전종목=sub.intra_all.mean(), 장중_CI=block_ci(sub.intra_os, sub.month)))
T2b = pd.DataFrame(out); print(T2b.round(2).to_string(index=False)); T2b.to_csv(OUT / "B2_night_intra.csv", index=False, encoding="utf-8-sig")
print(f"\n끝 {time.time()-t0:.0f}s")
