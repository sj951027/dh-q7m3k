# -*- coding: utf-8 -*-
"""업종 집중도 — 지수 급락이 몇 업종에 몰린 날 vs 골고루 빠진 날의 과매도 초과 (2026-11-08, 읽기 전용 · 지도 C7 남은 축). SECTOR_CONCENTRATION_20261108.md §0.

틀은 `signal_board_10y_20261108.py` 그대로(정리 유니버스 · 과매도 대리 = 20일 수익 하위 20% · 5거래일 격자 · t+1 진입 40일 · 비용 0.35% · 월 블록 부트스트랩 2,000회 seed 7).
집중도 = 신호일의 업종 20일 수익(구성 종목 동일가중, 유효 ≥10 종목인 업종만)의 업종 간 표준편차(%p). 높음 = 몰림, 낮음 = 골고루.
본검정: 코스피 R20 ≤ −5 신호일을 집중도 중앙값으로 상/하 절반 → 초과 차이(상−하), 월 블록 CI, 앞/뒤반 부호.
참고: (a) '코스피만큼 빠진 업종 비율' 정의 · (b) R20 ≤ 0 넓힌 표본 · (c) 순위상관.
출력: research/out_sector_concentration/days.csv · main.csv · ref.csv · stdout."""
import json, os, sqlite3, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
OUT = HERE / "out_sector_concentration"; OUT.mkdir(exist_ok=True)
STEP = 5; SPLIT = "20210101"; H = 40; COST = 0.0035; MIN_SEC = 10; rng = np.random.default_rng(7)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
pd.set_option("display.width", 240)


def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    if len(um) == 0:
        return (np.nan, np.nan)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5))


def diff_ci(a, b, k=2000):
    ua, ub = a.month.unique(), b.month.unique()
    ga = {u: a.exc[a.month == u].values for u in ua}; gb = {u: b.exc[b.month == u].values for u in ub}
    d = [np.concatenate([ga[u] for u in rng.choice(ua, len(ua))]).mean() - np.concatenate([gb[u] for u in rng.choice(ub, len(ub))]).mean() for _ in range(k)]
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def cell6(x):
    if x != x:
        return None
    for k, hi in (("A2", -10), ("A1", -5), ("B", 0), ("C", 5), ("D1", 10)):
        if x <= hi:
            return k
    return "D2"


t0 = time.time()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index()
con.close()
sec_map = json.load(open(REPO / "sector_cache.json", encoding="utf-8"))
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
dates = list(close.index); N = len(dates); tick = list(close.columns)
ks_r20 = (ks / ks.shift(20) - 1).reindex(dates) * 100
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
cu = close.loc[:, in_u.values]; vu = vol.loc[:, in_u.values]; del close, vol
tick = list(cu.columns)
dl = meta.note.reindex(tick).fillna("").str.contains("delisted").values
cf = cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()
r20 = cu / cu.shift(20) - 1
penny = cu < 1000
CF = cf.values; CU = cu.values; VU = vu.fillna(0).values; PEN = penny.fillna(True).values; R20 = r20.values
sec = np.array([sec_map.get(t, "") for t in tick], dtype=object)
sec_names = sorted({s for s in sec if s})
sec_idx = {s: np.where(sec == s)[0] for s in sec_names}
n_unc = int((sec == "").sum()); n_unc_dl = int(((sec == "") & dl).sum())
print(f"유니버스 {cu.shape[1]} 종목 · 날 {N} · 업종 {len(sec_names)} · 미분류 {n_unc}(그중 폐지 {n_unc_dl}) · {time.time()-t0:.0f}s")

rows = []
for i in range(130, N - H - 1, STEP):
    r = R20[i]
    v0 = (VU[i] == 0) | (VU[i + 1] == 0)
    e = CU[i + 1]; p40 = CF[i + 1 + H]
    ok = ~np.isnan(r) & ~v0 & ~PEN[i] & ~np.isnan(e) & (e > 0) & ~np.isnan(p40)
    if ok.sum() < 300:
        continue
    d = dates[i]
    thr = np.quantile(r[ok], 0.20); os_ = ok & (r <= thr)
    g = p40 / e - 1 - COST
    os40 = g[os_].mean() * 100; all40 = g[ok].mean() * 100
    # 업종 20일 수익(동일가중, 유효 ≥ MIN_SEC)
    valid = ~np.isnan(r) & ~PEN[i]
    sr = []
    for s in sec_names:
        ix = sec_idx[s]; m = valid[ix]
        if m.sum() >= MIN_SEC:
            sr.append(r[ix][m].mean() * 100)
    sr = np.array(sr)
    kr = ks_r20.iloc[i]
    rows.append(dict(date=d, month=d[:6], half=("앞" if d < SPLIT else "뒤"), r20=kr, cell=cell6(kr), n_sec=len(sr),
                     disp=(sr.std() if len(sr) else np.nan), frac_deep=((sr <= kr).mean() * 100 if len(sr) and kr == kr else np.nan),
                     frac_down=((sr < 0).mean() * 100 if len(sr) else np.nan), sec_mean=(sr.mean() if len(sr) else np.nan),
                     n_os=int(os_.sum()), os40=os40, all40=all40, exc=os40 - all40))
R = pd.DataFrame(rows); R = R[R.cell.notna() & R.disp.notna()].copy()
R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
print(f"신호일 {len(R)} · 업종 수 중앙 {R.n_sec.median():.0f}(최소 {R.n_sec.min()}) · {time.time()-t0:.0f}s")


def split_test(sub, col, label, higher_is_conc=True):
    """sub 를 col 중앙값으로 상/하 절반(중앙값과 같으면 하위) → 차이(상−하)·CI·앞/뒤반 부호."""
    med = sub[col].median(); hi_ = sub[sub[col] > med]; lo_ = sub[sub[col] <= med]
    out = dict(표=label, 날수=len(sub), 월수=sub.month.nunique(), 중앙값=med, 상위날수=len(hi_), 하위날수=len(lo_))
    if len(hi_) == 0 or len(lo_) == 0:
        return out
    hl, hh = block_ci(hi_.exc, hi_.month); ll, lh = block_ci(lo_.exc, lo_.month); dlo, dhi = diff_ci(hi_, lo_)
    out.update(상위초과=hi_.exc.mean(), 상위하한=hl, 상위상한=hh, 상위과매도40=hi_.os40.mean(), 상위시장40=hi_.all40.mean(),
               하위초과=lo_.exc.mean(), 하위하한=ll, 하위상한=lh, 하위과매도40=lo_.os40.mean(), 하위시장40=lo_.all40.mean(),
               차이=hi_.exc.mean() - lo_.exc.mean(), 차하한=dlo, 차상한=dhi)
    for h in ("앞", "뒤"):
        a, b = hi_[hi_.half == h], lo_[lo_.half == h]
        out[f"{h}반상위날수"] = len(a); out[f"{h}반하위날수"] = len(b)
        out[f"{h}반차이"] = (a.exc.mean() - b.exc.mean()) if len(a) and len(b) else np.nan
    out["CI_0제외"] = bool(dlo > 0 or dhi < 0)
    out["앞뒤부호일치"] = bool(np.sign(out["앞반차이"]) == np.sign(out["차이"]) == np.sign(out["뒤반차이"])) if out["앞반차이"] == out["앞반차이"] and out["뒤반차이"] == out["뒤반차이"] else False
    out["절반≥20"] = bool(len(hi_) >= 20 and len(lo_) >= 20)
    out["통과"] = bool(out["CI_0제외"] and out["앞뒤부호일치"] and out["절반≥20"])
    out["순위상관"] = sub[[col, "exc"]].corr(method="spearman").iloc[0, 1]
    return out


A = R[R.r20 <= -5]
print("\n### 본검정 — 코스피 R20 ≤ −5 신호일 · 집중도(업종 20일 수익 표준편차) 상위 절반(몰림) − 하위 절반(골고루) · 초과 %p")
main = pd.DataFrame([split_test(A, "disp", "본검정 R20≤−5 · 표준편차")])
main.to_csv(OUT / "main.csv", index=False, encoding="utf-8-sig")
print(main.T.to_string())
print("\n본검정 신호일 목록(날짜·R20·업종수·집중도·초과):")
print(A[["date", "r20", "n_sec", "disp", "frac_deep", "os40", "all40", "exc"]].round(2).to_string(index=False))

print("\n### 참고표 (판정 밖)")
ref = pd.DataFrame([
    split_test(A, "frac_deep", "(a) R20≤−5 · 코스피만큼 빠진 업종 비율(낮음=몰림)"),
    split_test(R[R.r20 <= 0], "disp", "(b) R20≤0 · 표준편차"),
    split_test(R[R.r20 <= 0], "frac_deep", "(b)(a) R20≤0 · 비율"),
    split_test(R, "disp", "(참고) 전 신호일 · 표준편차"),
])
ref.to_csv(OUT / "ref.csv", index=False, encoding="utf-8-sig")
print(ref.T.to_string())

print("\n### 집중도 분포 (칸별 중앙값) — 급락 칸에서 집중도 자체가 커지는지")
print(R.groupby("cell").agg(날수=("disp", "size"), 표준편차중앙=("disp", "median"), 비율중앙=("frac_deep", "median"), 초과평균=("exc", "mean")).round(2))
print(f"\n{time.time()-t0:.0f}s")
