# -*- coding: utf-8 -*-
"""급락 깊이별 '하한' 연구 (2026-10-30, 읽기 전용 · 관측 · 판정 아님) — 외부 조사 카드 B1 "너무 깊은 낙폭은 실패인가".

질문: 코스피 20일 수익(R20)이 더 깊게 빠진 날에 살수록 40일 바구니 수익이 계속 좋아지나, 아니면 어느 깊이부터 나빠지나(하한)?
자료: 10년 DB(`ohlcv_10y.db`, 2014-11~2026-10-22) 만 사용 — 정리판 규칙(handoff/CLAUDE_20261023_10y_quality_crosscheck.md §3):
  유니버스 = 스크리너와 같게(코스피·코스닥, 보통주, 금융/리츠/스팩 제외) · 40일 안 상폐 = 마지막 가격 + −90% 감도 ·
  가격 불연속(하루 ±35% 초과) 창 제외 감도 · 운영 DB 와 값 이어 붙이지 않음(현재 사건은 지수만 따로 표시).
바구니 수익 = 신호일 t 다음날(t+1) 종가 매수 → t+41 종가 매도, 동일가중(compass_basket_check_20261023.py 와 같은 식).
사건 = buy_context.stats 와 같은 규칙(같은 문턱의 날을 시간순으로 보며 직전 사건과 40거래일 이상 떨어진 날).
재현: python research/crash_depth_floor_20261030.py  → research/out_crash_depth/*.csv (약 1~2분)
"""
import os, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(os.environ.get("DH_REPO", Path(__file__).resolve().parent.parent)); sys.path.insert(0, str(REPO))
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
OPS = os.environ.get("OHLCV_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv.db"))
OUT = REPO / "research" / "out_crash_depth"; OUT.mkdir(exist_ok=True)
H = 40; DISC = 0.35; SEED = 20261030; NBOOT = 4000
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', '부동산투자', '스팩']
THRESH = [-5, -10, -15, -20]                       # 누적 문턱(≤)
BINS = [(-10, -5), (-15, -10), (-20, -15), (-np.inf, -20)]   # 배타 구간 (lo, hi]
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)

# ---------- 자료 ----------
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
idx = pd.read_sql("SELECT series, date, close FROM index_daily", con).pivot(index="date", columns="series", values="close").sort_index(); con.close()
c = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); c = c.where(c > 0); del px
dates = list(c.index); N = len(dates)
t = list(c.columns); mk = meta.market.reindex(t); nm = meta.name.reindex(t).fillna("")
u = [(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and k.endswith("0") and not any(w in n for w in FIN_KW) and "SPAC" not in n.upper() and "REIT" not in n.upper() for k, m, n in zip(t, mk, nm)]
cu = c.loc[:, u]; del c
dl = meta.note.reindex(cu.columns).fillna("").str.contains("delisted").values
cf = cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()              # 상폐 = 마지막 가격 유지
r_dl = (cf.shift(-1 - H) / cu.shift(-1) - 1) * 100                   # t+1 매수 → t+41 매도
b_clean = r_dl.mean(axis=1, skipna=True)
lp = np.array([np.where(cu.iloc[:, j].notna())[0].max() if cu.iloc[:, j].notna().any() else -1 for j in range(cu.shape[1])])
P = np.arange(N)[:, None]; hit = dl[None, :] & (lp[None, :] >= P + 1) & (lp[None, :] < P + 1 + H)
b_m90 = r_dl.where(~hit, -90.0).mean(axis=1, skipna=True)             # 40일 안 상폐 = −90%
jump = (cu.pct_change().abs() > DISC)                                  # 하루 ±35% 초과
inwin = jump.iloc[::-1].rolling(H + 1, min_periods=1).max().iloc[::-1].shift(-1).fillna(0).astype(bool)   # t+1..t+41 안에 불연속
b_disc = r_dl.where(~inwin).mean(axis=1, skipna=True)                   # 불연속 창 제외 감도
n_stk = r_dl.notna().sum(axis=1)
for s in (b_clean, b_m90, b_disc):
    s.iloc[-(H + 1):] = np.nan                                           # 미완결
del r_dl, cf, jump, inwin


def idx_block(series):
    ix = idx[series].reindex(dates).astype(float)
    r20 = (ix / ix.shift(20) - 1) * 100
    i40 = (ix.shift(-1 - H) / ix.shift(-1) - 1) * 100; i40.iloc[-(H + 1):] = np.nan
    arr = ix.to_numpy()
    fur20 = pd.Series([np.nanmin(arr[i + 1:i + 21]) / arr[i] * 100 - 100 if i + 1 < N and arr[i] == arr[i] else np.nan for i in range(N)], index=dates)   # 20일 안 최저(신호일 대비 %)
    low40 = pd.Series([np.nanmin(arr[i + 1:i + 1 + H + 1]) / arr[i] * 100 - 100 if i + 1 < N and arr[i] == arr[i] else np.nan for i in range(N)], index=dates)
    return ix, r20, i40, fur20, low40


def events_of(days):
    ev, last = [], -10 ** 9
    for i in days:
        if i - last >= H:
            ev.append(i); last = i
    return ev


def boot_ci(x, n=NBOOT):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    if len(x) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(SEED); m = rng.choice(x, (n, len(x)), replace=True).mean(axis=1)
    return (float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)))


def analyse(series, label):
    ix, r20, i40, fur20, low40 = idx_block(series)
    ok = b_clean.notna().to_numpy(); r = r20.to_numpy()
    print(f"\n==================== {label} ====================")
    # 1) 배타 구간 — 날 단위(겹침 포함)
    rows = []
    for lo, hi in BINS + [(-5, 0), (0, 5), (5, 10), (10, np.inf)]:
        m = ok & (r > lo) & (r <= hi)
        if m.sum() == 0:
            continue
        bc_, bm, bd, ii = b_clean[m], b_m90[m], b_disc[m], i40[m]
        name = f"({lo:+.0f}, {hi:+.0f}]" if np.isfinite(lo) and np.isfinite(hi) else (f"<= {hi:+.0f}" if not np.isfinite(lo) else f"> {lo:+.0f}")
        rows.append(dict(구간=name, 날수=int(m.sum()), 바구니평균=round(bc_.mean(), 2), 중앙=round(bc_.median(), 2), 플러스비율=round((bc_ > 0).mean() * 100), 최악=round(bc_.min(), 1),
                         상폐m90=round(bm.mean(), 2), 불연속제외=round(bd.mean(), 2), 지수평균=round(ii.mean(), 2), 종목수중앙=int(n_stk[m].median())))
    bins = pd.DataFrame(rows); print("\n[1] 깊이 구간별 — 날 단위(겹침 포함, 40일 끝난 날만)"); print(bins.to_string(index=False))
    # 2) 누적 문턱 — 사건 단위
    ev_rows, summ = [], []
    for th in THRESH:
        days = [i for i in range(N) if ok[i] and r[i] <= th]
        ev = events_of(days)
        x = b_clean.iloc[ev].to_numpy(); lo_, hi_ = boot_ci(x)
        summ.append(dict(문턱=f"<= {th:+d}%", 날수=len(days), 사건=len(ev), 사건평균=round(np.nanmean(x), 2) if len(x) else None, 구간=f"[{lo_:+.1f}, {hi_:+.1f}]" if len(x) > 1 else "-",
                         플러스=f"{int((x > 0).sum())}/{len(x)}", 중앙=round(float(np.nanmedian(x)), 2) if len(x) else None, 최악=round(float(np.nanmin(x)), 1) if len(x) else None,
                         상폐m90=round(float(np.nanmean(b_m90.iloc[ev])), 2) if len(ev) else None, 불연속제외=round(float(np.nanmean(b_disc.iloc[ev])), 2) if len(ev) else None,
                         지수평균=round(float(np.nanmean(i40.iloc[ev])), 2) if len(ev) else None,
                         더빠진뒤회복=f"{int(sum(1 for i in ev if fur20.iloc[i] <= -5 and b_clean.iloc[i] > 0))}/{int(sum(1 for i in ev if fur20.iloc[i] <= -5))}"))
        for i in ev:
            ev_rows.append(dict(문턱=th, 날짜=dates[i], R20=round(r[i], 1), 바구니40=round(b_clean.iloc[i], 1), 상폐m90=round(b_m90.iloc[i], 1), 불연속제외=round(b_disc.iloc[i], 1),
                                지수40=round(i40.iloc[i], 1), 지수20일최저=round(fur20.iloc[i], 1), 지수40일최저=round(low40.iloc[i], 1)))
    print("\n[2] 누적 문턱별 — 사건 단위(직전 사건과 40거래일 이상 떨어진 첫 날)"); print(pd.DataFrame(summ).to_string(index=False))
    evdf = pd.DataFrame(ev_rows)
    for th in THRESH[1:]:
        print(f"\n   사건 목록 <= {th:+d}%"); print(evdf[evdf.문턱 == th].drop(columns="문턱").to_string(index=False))
    # 3) 깊이와 결과의 관계(설명용)
    m5 = ok & (r <= -5)
    rho_days = pd.Series(r[m5]).corr(pd.Series(b_clean[m5].to_numpy()), method="spearman")
    e5 = events_of([i for i in range(N) if m5[i]])
    rho_ev = pd.Series(r[e5]).corr(pd.Series(b_clean.iloc[e5].to_numpy()), method="spearman")
    print(f"\n[3] 깊이(R20)와 40일 바구니의 순위상관(음수 = 더 깊을수록 더 좋음): 날 단위 {rho_days:+.3f} (n={int(m5.sum())}, 겹침) · 사건 단위 {rho_ev:+.3f} (n={len(e5)})")
    # 4) 에피소드 — 같은 급락 안에서 '첫 ≤−5 날' vs '첫 ≤−10/−15/−20 날'에 산 결과
    epi, cur = [], None
    for i in range(N):
        if r[i] == r[i] and r[i] <= -5:
            if cur is None or i - cur["last"] > 10:      # 10거래일 넘게 떨어지면 새 에피소드
                if cur:
                    epi.append(cur)
                cur = dict(start=i, last=i, first={}, minr=r[i], minday=i)
            cur["last"] = i
            if r[i] < cur["minr"]:
                cur["minr"], cur["minday"] = r[i], i
            for th in THRESH:
                if r[i] <= th and th not in cur["first"]:
                    cur["first"][th] = i
    if cur:
        epi.append(cur)
    erows = []
    for e in epi:
        row = dict(시작=dates[e["start"]], 끝=dates[e["last"]], 최저R20=round(e["minr"], 1), 최저날=dates[e["minday"]])
        for th in THRESH:
            i = e["first"].get(th); row[f"첫<={th}"] = (round(b_clean.iloc[i], 1) if i is not None and b_clean.iloc[i] == b_clean.iloc[i] else None)
        i = e["minday"]; row["최저날매수"] = round(b_clean.iloc[i], 1) if b_clean.iloc[i] == b_clean.iloc[i] else None
        erows.append(row)
    ep = pd.DataFrame(erows); print("\n[4] 에피소드(<=-5 날이 10거래일 넘게 끊기면 새 에피소드) — 같은 급락 안에서 문턱별 첫 날에 샀을 때 40일 바구니(%)"); print(ep.to_string(index=False))
    print("\n   규칙 비교(에피소드 단위): '첫 <=-5 에 산다' vs '<=-X 에 닿은 에피소드만, 그 첫 날에 산다'")
    comp = []
    for th in THRESH:
        col = f"첫<={th}"; v = ep[col].dropna()
        base = ep.loc[ep[col].notna(), "첫<=-5"].dropna()
        comp.append(dict(규칙=f"<={th} 첫 날", 참여에피소드=f"{len(v)}/{len(ep)}", 평균=round(v.mean(), 2) if len(v) else None, 플러스=f"{int((v > 0).sum())}/{len(v)}", 최악=round(v.min(), 1) if len(v) else None,
                         같은에피소드_첫m5=round(base.mean(), 2) if len(base) else None))
    print(pd.DataFrame(comp).to_string(index=False))
    bins.to_csv(OUT / f"bins_{series}.csv", index=False, encoding="utf-8-sig"); pd.DataFrame(summ).to_csv(OUT / f"thresholds_{series}.csv", index=False, encoding="utf-8-sig")
    evdf.to_csv(OUT / f"events_{series}.csv", index=False, encoding="utf-8-sig"); ep.to_csv(OUT / f"episodes_{series}.csv", index=False, encoding="utf-8-sig")
    return ix, r20


ix_k, r20_k = analyse("KOSPI", "코스피")
analyse("KOSDAQ", "코스닥 (참고)")

# ---------- 현재 사건: 운영 DB 지수만(바구니와 이어 붙이지 않음) ----------
try:
    oc = sqlite3.connect(f"file:{OPS}?mode=ro", uri=True)
    ks = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSPI' ORDER BY date", oc).set_index("date")["close"]; oc.close()
    r20o = (ks / ks.shift(20) - 1) * 100
    print("\n==================== 현재 사건(2026-10, 운영 DB 지수만 · 진행 중 · 바구니 아님) ====================")
    firsts = {}
    for d in r20o.index:
        if d < "20261001":
            continue
        for th in THRESH:
            if r20o[d] <= th and th not in firsts:
                firsts[th] = d
    last = ks.index[-1]; kl = list(ks.index)
    for th in THRESH:
        d = firsts.get(th)
        if d:
            i = kl.index(d); nxt = kl[i + 1] if i + 1 < len(kl) else None
            if nxt:
                print(f"  첫 <={th:+d}% = {d} (R20 {r20o[d]:+.1f}%) → 다음날 {nxt} 종가 매수 가정, {last} 현재 지수 {ks.iloc[-1] / ks[nxt] * 100 - 100:+.1f}% · 경과 {len(kl) - 1 - (i + 1)}거래일/40")
    print(f"  10년 DB 마지막 날 {dates[-1]} · 운영 DB 마지막 날 {last} · 이번 최저 R20 {r20o.loc['20261001':].min():+.1f}% ({r20o.loc['20261001':].idxmin()})")
except Exception as e:
    print("현재 사건 표시 실패:", e)
