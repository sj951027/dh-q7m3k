# -*- coding: utf-8 -*-
"""🧭 통계 바구니 감도 (2026-10-23 밤, 읽기 전용): build_scoreboard.build_buy_context 의 10년 DB 바구니(전 종목, 40일 안 상폐 = 빠짐)를
정리 바구니(스크리너 유니버스: 코넥스·우선주·금융/리츠/스팩 제외 + 40일 안 상폐 = 마지막 가격, 감도로 −90%)로 바꾸면 칸별 숫자가 어떻게 바뀌나.
10년 DB 만 사용(운영 DB 이음새 없음 → 최근 41일 신호는 둘 다 미완결). buy_context.stats 그대로 호출."""
import os, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
REPO = Path(os.environ.get("DH_REPO", Path(__file__).resolve().parent.parent)); sys.path.insert(0, str(REPO))
import buy_context as bc
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db")); H = 40
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', '부동산투자', '스팩']
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
idx = pd.read_sql("SELECT series, date, close FROM index_daily", con).pivot(index="date", columns="series", values="close").sort_index(); con.close()
c = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); c = c.where(c > 0)
dates = list(c.index)
b_now = ((c.shift(-1 - H) / c.shift(-1) - 1).mean(axis=1, skipna=True) * 100)          # 현행과 같은 식
t = list(c.columns); mk = meta.market.reindex(t); nm = meta.name.reindex(t).fillna("")
u = [(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and k.endswith("0") and not any(w in n for w in FIN_KW) and "SPAC" not in n.upper() and "REIT" not in n.upper() for k, m, n in zip(t, mk, nm)]
cu = c.loc[:, u]; dl = meta.note.reindex(cu.columns).fillna("").str.contains("delisted").values
cf = cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()
r_dl = (cf.shift(-1 - H) / cu.shift(-1) - 1) * 100
b_clean = r_dl.mean(axis=1, skipna=True)
# −90%: 40일 안 상폐(마지막 행 위치가 t+1..t+41) 이면 −90
lp = np.array([np.where(cu.iloc[:, j].notna())[0].max() if cu.iloc[:, j].notna().any() else -1 for j in range(cu.shape[1])])
P = np.arange(len(dates))[:, None]; hit = dl[None, :] & (lp[None, :] >= P + 1) & (lp[None, :] < P + 1 + H)
b_m90 = r_dl.where(~hit, -90.0).mean(axis=1, skipna=True)
pd.set_option("display.width", 250)
for k, s in (("코스피", "KOSPI"), ("코스닥", "KOSDAQ")):
    ix = idx[s].dropna(); r20 = (ix / ix.shift(20) - 1) * 100
    rows = []
    for lab, b in (("현행(전 종목·상폐 빠짐)", b_now), ("정리(유니버스·상폐 마지막 가격)", b_clean), ("정리 + 상폐 −90%", b_m90)):
        b = b.copy(); b.iloc[-(H + 1):] = np.nan
        st = bc.stats(dates, r20, b, ix)
        for cell, v in st.items():
            rows.append(dict(바구니=lab, 칸=cell, 날수=v["n_days"], 사건=v["n_events"], 사건평균=round(v["mean"], 2), 플러스=f'{v["events_pos"]}/{v["events_n"]}',
                             날평균=round(v["mean_days"], 2), 더떨어진뒤회복=f'{v["further_then_up"]}/{v["further_n"]}', 최악=round(v["worst_event"], 1)))
    T = pd.DataFrame(rows).pivot_table(index="칸", columns="바구니", values=["사건평균", "날평균"], aggfunc="first")
    print(f"\n=== {k} ==="); print(pd.DataFrame(rows).to_string(index=False))
