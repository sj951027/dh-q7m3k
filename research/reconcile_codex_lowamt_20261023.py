# -*- coding: utf-8 -*-
"""Codex 블라인드 답(REPLY_20261024_lowamt_blind) ↔ Claude 재검증 차이 원인 확인 (2026-10-23 밤, 읽기 전용, 10년 DB 만).
같은 코드로 (가) 정리 단계 S3(Codex 와 비슷: 최하위 5%·동전주 안 뺌) vs S5(Claude 기본) 의 D·시장별,
(나) 체결 한도 두 방식: Claude식 = 한도 통과 종목만으로 과매도·중앙값 다시 정의 / Codex식 = 전체에서 정한 아래 절반·과매도를 그대로 두고 양쪽에서 한도 통과 종목만 남김."""
import os, sqlite3
import numpy as np, pandas as pd
from pathlib import Path
DB = os.environ.get("OHLCV_10Y_DB", str(Path(__file__).resolve().parent.parent.parent / "dh-q7m3k-data" / "ohlcv_10y.db")); H = 40; rng = np.random.default_rng(7)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', '부동산투자', '스팩']
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con); meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker"); con.close()
c = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); c = c.where(c > 0)
v = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(c.index)
t = list(c.columns); mk = meta.market.reindex(t); nm = meta.name.reindex(t).fillna("")
u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and k.endswith("0") and not any(w in n for w in FIN_KW) and "SPAC" not in n.upper() and "REIT" not in n.upper() for k, m, n in zip(t, mk, nm)], index=t)
mks = pd.Series(np.where(mk.values == "KOSPI", "KOSPI", "KOSDAQ"), index=t)
dl = meta.note.reindex(t).fillna("").str.contains("delisted")
cf = c.copy(); cf.loc[:, dl.values] = cf.loc[:, dl.values].ffill()
fwd = (cf.shift(-1 - H) / c.shift(-1) - 1) * 100; r20 = c / c.shift(20) - 1; amt = (c * v).rolling(20, min_periods=10).mean()
V = v.values; lastpos = {}
liq = pd.Series(10 ** 9, index=t)
for j, k in enumerate(t):
    if dl[k]:
        p = np.where((V[:, j] > 0) & ~np.isnan(c.values[:, j]))[0]
        if len(p): liq[k] = p[-7] if len(p) >= 7 else p[0]
dates = list(c.index); rows = []
for i in range(130, len(dates) - H - 1, 5):
    d = dates[i]; a, r, f, cl = amt.iloc[i], r20.iloc[i], fwd.iloc[i], c.iloc[i]
    m3 = u & a.notna() & r.notna() & f.notna() & (v.iloc[i] > 0) & (v.iloc[i + 1] > 0) & pd.Series(i < liq.values, index=t)
    m5 = m3 & (a > a[m3].quantile(0.05)) & (cl >= 1000)
    rec = dict(date=d, month=d[:6], half="앞" if d < "20210101" else "뒤")
    for st, m in (("S3", m3), ("S5", m5)):
        os_ = m & (r <= r[m].quantile(0.2)); lo = os_ & (a <= a[os_].median())
        rec[f"{st}_D"] = f[lo].mean() - f[os_].mean()
        for mm in ("KOSPI", "KOSDAQ"):
            mm_ = m & (mks == mm); o2 = mm_ & (r <= r[mm_].quantile(0.2)); l2 = o2 & (a <= a[o2].median())
            rec[f"{st}_{mm}"] = f[l2].mean() - f[o2].mean()
        for cap in (1e8, 3e8, 1e9):   # 주문 100만·300만·1000만 → 거래대금 ≥ 1억·3억·10억
            ok = a >= cap
            # Codex식: 집단 고정, 양쪽에서 통과 종목만
            lc, oc = lo & ok, os_ & ok
            rec[f"{st}_cx{int(cap/1e6)}"] = (f[lc].mean() - f[oc].mean()) if lc.sum() and oc.sum() else np.nan
            # Claude식: 통과 종목만으로 표본 다시 → 과매도·중앙값 다시
            m2 = m & ok
            if m2.sum() >= 300:
                o3 = m2 & (r <= r[m2].quantile(0.2)); l3 = o3 & (a <= a[o3].median())
                rec[f"{st}_cl{int(cap/1e6)}"] = f[l3].mean() - f[o3].mean()
    rows.append(rec)
R = pd.DataFrame(rows)
def ci(x, mo, k=2000):
    x = np.asarray(x, float); mo = np.asarray(mo); ok = ~np.isnan(x); x, mo = x[ok], mo[ok]; um = np.unique(mo); by = {q: x[mo == q] for q in um}
    s = [np.concatenate([by[q] for q in rng.choice(um, len(um))]).mean() for _ in range(k)]; return np.percentile(s, [2.5, 97.5])
out = []
for col in [x for x in R.columns if x[:2] in ("S3", "S5")]:
    for sc, sub in (("전체", R), ("앞반", R[R.half == "앞"]), ("뒤반", R[R.half == "뒤"])):
        x = sub[col]; lo_, hi_ = ci(x, sub.month); out.append(dict(항목=col, 범위=sc, n=int(x.notna().sum()), D=f"{x.mean():+.2f} [{lo_:+.2f}, {hi_:+.2f}]"))
T = pd.DataFrame(out).pivot(index="항목", columns="범위", values="D"); N = pd.DataFrame(out).pivot(index="항목", columns="범위", values="n")
pd.set_option("display.width", 250); print(T[["전체", "앞반", "뒤반"]].to_string()); print(N[["전체", "뒤반"]].to_string())
