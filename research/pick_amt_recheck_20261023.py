# -*- coding: utf-8 -*-
"""거래대금 하위 효과 재검증 (2026-10-23, 사후 관측 · 채택 아님). 10년 DB(ohlcv_10y.db)만 읽는다(운영 DB·history.db 안 읽음).

10/23 `pick_10y_20261023.py` B) '20일 거래대금 적을수록 +6.17%p' 를 아래 순서로 한 겹씩 걸러 다시 잰다(누적):
  S0 원래 정의 재현(전 종목, 40일 안 상폐 종목은 수익 NaN 이라 빠짐)
  S1 + 스크리너 유니버스(코넥스·우선주(코드 끝 '0' 아님)·금융/리츠/스팩 이름 제외)
  S2 + 상폐 손실 반영(40일 안 상폐 = 마지막 거래 가격으로 청산) + 신호일·매수일 거래량 0(정지) 제외
  S3 + 정리매매 창 제외(상폐 종목의 마지막 7거래일 — 그날 알 수 있는 사실)
  S4 + 거래대금 최하위 5%(유니버스 전체 기준) 제외
  S5 + 동전주(수정 종가 < 1,000원) 제외 — 관리종목 대리(관리종목 이력 자료 없음)  ← '정리 기본'
감도(S5 위에): 상폐 −90% · 앞으로 250거래일 안 상폐 종목 제외(미래를 앎 — 가장 센 제거) · 가격 조정 의심 종목 제외 ·
  참여율 1% 한도(20일 평균 거래대금 ≥ 주문액×100: 주문 100만/1,000만/1억 → 1억/10억/100억).
주의: 이 DB 는 가격만 수정주가이고 거래량은 원래 값 → 20일 거래대금 = 수정가×원거래량 은 그 날 뒤 분할·병합·무상증자가 있으면 틀어진다.
  '가격 조정 의심' = 거래량 0 이 2일 이상 이어진 뒤(분할·병합 변경상장 정지) 앞뒤 20일 거래량 중앙값이 4배 넘게 바뀐 지점. 무상증자(정지 없음)는 못 잡는다.
지표: 과매도(20일 수익 하위 20%) 안에서 거래대금 아래 절반 − 위 절반, Q1 − Q5, 아래 절반 − 과매도 전체(챌린저가 v30 대리 위에 얹는 몫). 120일 수익 아래 절반도 같은 틀.
신호일 5거래일 간격, t+1 종가 매수 → t+41 종가 매도, 동일가중. 월 블록 부트스트랩 2,000회 seed 7, 95%."""
import json, os, sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("DH_REPO", HERE.parent))
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
OUT = Path(os.environ.get("OUT_DIR", HERE / "out_pick_amt")); OUT.mkdir(exist_ok=True, parents=True)
H = 40; STEP = 5; Q = 5; SPLIT = "20210101"; rng = np.random.default_rng(7)
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁',
          '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']                     # screener_fdr_v2_6.py 와 같은 낱말
FIN_TICKERS = {'055550', '001450'}
CAPS = ((1e8, "참여율1%·주문100만"), (1e9, "참여율1%·주문1000만"), (1e10, "참여율1%·주문1억"))


def block_ci(vals, months, k=2000):
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    if len(um) < 2 or len(vals) < 2: return (np.nan, np.nan)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return (float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5)))


def nonov(pos, gap=H):
    c = 0; last = -10 ** 9
    for p in sorted(pos):
        if p - last >= gap: c += 1; last = p
    return c


t0 = time.time()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
meta = pd.read_sql("SELECT ticker, name, market, delisted, note FROM meta", con).set_index("ticker")
ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index()
con.close()
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index)
dates = list(close.index); N = len(dates); tick = list(close.columns)
ks_r20 = (ks / ks.shift(20) - 1).reindex(dates)

# 유니버스(S1)
mk = meta.market.reindex(tick); nm = meta.name.reindex(tick).fillna("")
in_u = pd.Series([(m in ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)
                  for t, m, n in zip(tick, mk, nm)], index=tick)
mk_s = pd.Series(mk.values, index=tick)
delisted = meta.note.reindex(tick).fillna("").str.contains("delisted")

# 위치 정보: 종목별 마지막 거래 행, 정리매매 창(상폐 종목 마지막 거래량>0 7행)
V = vol.values; C = close.values
last_pos = pd.Series({t: (np.where(~np.isnan(C[:, j]))[0].max() if (~np.isnan(C[:, j])).any() else -1) for j, t in enumerate(tick)})
liq_start = pd.Series(10 ** 9, index=tick)          # 정리매매 창 시작 위치(상폐 종목만)
for j, t in enumerate(tick):
    if not delisted[t]: continue
    pos = np.where((V[:, j] > 0) & ~np.isnan(C[:, j]))[0]
    if len(pos): liq_start[t] = pos[-7] if len(pos) >= 7 else pos[0]

# 가격 조정 의심 지점(분할·병합 변경상장 정지)
events = {}
for j, t in enumerate(tick):
    v = V[:, j]; z = (v == 0) & ~np.isnan(C[:, j]); k = 0; ev = []
    for p in range(N):
        if z[p]: k += 1; continue
        if k >= 2 and not np.isnan(v[p]):
            pre = v[max(0, p - k - 20):p - k]; post = v[p:p + 20]
            pre = pre[(pre > 0) & ~np.isnan(pre)]; post = post[(post > 0) & ~np.isnan(post)]
            if len(pre) >= 10 and len(post) >= 10:
                r = np.median(post) / np.median(pre)
                if r >= 4 or r <= 0.25: ev.append(p)
        k = 0
    if ev: events[t] = ev
print(f"종목 {len(tick)} · 유니버스 {int(in_u.sum())} · 상폐 {int(delisted.sum())} · 가격 조정 의심 종목 {len(events)}(지점 {sum(map(len, events.values()))}) · {time.time()-t0:.0f}s")
last_event = pd.Series({t: max(e) for t, e in events.items()}).reindex(tick).fillna(-1)

r20 = close / close.shift(20) - 1; r120 = close / close.shift(120) - 1
amt20 = (close * vol).rolling(20, min_periods=10).mean()
# 수익: 원래(NaN 이면 빠짐) / 상폐 반영(마지막 가격 ffill, 상폐 종목만)
cf = close.copy(); dl_cols = [t for t in tick if delisted[t]]
cf[dl_cols] = cf[dl_cols].ffill()
fwd_raw = (close.shift(-1 - H) / close.shift(-1) - 1) * 100
fwd_dl = (cf.shift(-1 - H) / close.shift(-1) - 1) * 100
dl_in_win = pd.DataFrame(False, index=close.index, columns=tick)          # 40일 안 상폐(마지막 거래 위치가 t+1 ~ t+41 사이)
lp = last_pos.values
pos_idx = np.arange(N)[:, None]
dl_in_win.loc[:, :] = delisted.values[None, :] & (lp[None, :] < pos_idx + 1 + H) & (lp[None, :] >= pos_idx + 1)
fwd_m90 = fwd_dl.where(~dl_in_win, -90.0)
fwd_clip = fwd_dl.clip(-95, 200)                                            # 종목 수익 절단(불연속 한 건이 평균을 끄는지)
# 가격 불연속(Codex 10/23 품질 답 §1·§5): 직전 유효 종가 대비 |변화| > 35% 인 행 — 가격제한폭 밖이라 정상 거래로 설명 안 됨(병합 미반영·재상장 등)
jump = ((close / close.ffill().shift(1) - 1).abs() > 0.35).astype(float)
jump_win = jump[::-1].rolling(H + 2, min_periods=1).max()[::-1].shift(0)      # t ~ t+41 안에 불연속
jump_back = jump.rolling(21, min_periods=1).max()                            # t-20 ~ t 안에 불연속
no_jump = (jump_win.fillna(0) + jump_back.fillna(0)) == 0
print(f"지표 준비 {time.time()-t0:.0f}s")

rows = []
for i in range(130, N - H - 1, STEP):
    d = dates[i]; A = bool(ks_r20.iloc[i] == ks_r20.iloc[i] and ks_r20.iloc[i] <= -0.05); half = "앞" if d < SPLIT else "뒤"
    r = r20.iloc[i]; a = amt20.iloc[i]; c120 = r120.iloc[i]; cl = close.iloc[i]
    v0 = vol.iloc[i]; v1 = vol.iloc[i + 1]
    fr, fd, f9 = fwd_raw.iloc[i], fwd_dl.iloc[i], fwd_m90.iloc[i]
    traded = (v0 > 0) & (v1 > 0)
    not_liq = pd.Series(i < liq_start.values, index=tick)
    no_fut_dl = pd.Series(~(delisted.values & (lp - i <= 250)), index=tick)
    no_adj = pd.Series(last_event.values <= i - 20, index=tick)
    base_ok = r.notna() & a.notna()
    # 단계별 (표본 마스크, 수익 벡터)
    S = {}
    S["S0 원래 재현"] = (base_ok & fr.notna(), fr)
    m1 = base_ok & in_u
    S["S1 +유니버스"] = (m1 & fr.notna(), fr)
    m2 = m1 & fd.notna() & traded
    S["S2 +상폐손실·정지제외"] = (m2, fd)
    m3 = m2 & not_liq
    S["S3 +정리매매 제외"] = (m3, fd)
    q05 = a[m3].quantile(0.05) if m3.sum() else np.nan
    m4 = m3 & (a > q05)
    S["S4 +최하위5% 제외"] = (m4, fd)
    m5 = m4 & (cl >= 1000)
    S["S5 +동전주 제외(정리 기본)"] = (m5, fd)
    S["감도 상폐−90%"] = (m5 & f9.notna(), f9)
    S["감도 250일 안 상폐 제외(미래)"] = (m5 & no_fut_dl, fd)
    S["감도 가격조정 의심 제외"] = (m5 & no_adj, fd)
    S["감도 불연속 창 제외"] = (m5 & no_jump.iloc[i], fd)
    S["감도 수익 절단 −95~+200"] = (m5, fwd_clip.iloc[i])
    for cap, nmc in CAPS: S["감도 " + nmc] = (m5 & (a >= cap), fd)
    for sname, (m, f) in S.items():
        if m.sum() < 300: continue
        osd = m & (r <= r[m].quantile(0.20))          # 과매도 = 그 표본 안 20일 수익 하위 20%
        allm = float(f[m].mean()); om = float(f[osd].mean())
        rec = dict(stage=sname, date=d, month=d[:6], i=i, A=A, half=half, n_all=int(m.sum()), n_os=int(osd.sum()), all=allm, os=om)
        for feat, X in (("amt", a), ("r120", c120)):
            x = X[osd].replace([np.inf, -np.inf], np.nan).dropna()
            if len(x) < 40 or x.nunique() < Q: continue
            ff = f[x.index]; med = x.median()
            lo_half = float(ff[x <= med].mean()); hi_half = float(ff[x > med].mean())
            qq = pd.qcut(x.rank(method="first"), Q, labels=False); g = ff.groupby(qq.values).mean()
            rec[f"{feat}_lowhalf"] = lo_half; rec[f"{feat}_half_spread"] = lo_half - hi_half; rec[f"{feat}_q_spread"] = float(g[0] - g[Q - 1])
            rec[f"{feat}_low_vs_os"] = lo_half - om
            rec[f"{feat}_half_med"] = float(ff[x <= med].median() - ff[x > med].median())      # 종목 수익 중앙값 차이(큰 승자 몇 개 영향 확인)
            if feat == "amt": rec["amt_lowhalf_med_eok"] = float(x[x <= med].median() / 1e8)
        if sname.startswith("S5"):                                           # v30 처럼 시장별로: 시장 안 과매도 → 시장 안 거래대금 절반
            for mname, mset in (("코스피", ("KOSPI",)), ("코스닥", ("KOSDAQ", "KOSDAQ GLOBAL"))):
                mm = m & mk_s.isin(mset)
                if mm.sum() < 150: continue
                o2 = mm & (r <= r[mm].quantile(0.20)); x = a[o2].dropna(); ff = f[x.index]; med = x.median()
                rec[f"mkt_{mname}_low_vs_os"] = float(ff[x <= med].mean() - f[o2].mean())
                rec[f"mkt_{mname}_half_spread"] = float(ff[x <= med].mean() - ff[x > med].mean())
                rec[f"mkt_{mname}_n_os"] = int(o2.sum()); rec[f"mkt_{mname}_low_med_eok"] = float(x[x <= med].median() / 1e8)
        xa = a[m]; fa = f[m]; ma = xa.median()                          # 맥락: 과매도 아닌 전 표본에서도 한산한 쪽이 나은가
        rec["amt_all_half_spread"] = float(fa[xa <= ma].mean() - fa[xa > ma].mean())
        rows.append(rec)
R = pd.DataFrame(rows); R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
print(f"신호일 {R.date.nunique()} · 비겹침 {nonov(R.i.unique())} · {time.time()-t0:.0f}s")

out = []
order = list(dict.fromkeys(R.stage))
for st in order:
    g0 = R[R.stage == st]
    for scope, sub in (("전체", g0), ("코스피 급락 날", g0[g0.A]), ("그 밖", g0[~g0.A]), ("앞반", g0[g0.half == "앞"]), ("뒤반", g0[g0.half == "뒤"])):
        if len(sub) < 8: continue
        rec = dict(단계=st, 범위=scope, 날수=len(sub), 비겹침=nonov(sub.i), 표본중앙=int(sub.n_all.median()), 과매도중앙=int(sub.n_os.median()),
                   과매도초과=(sub.os - sub["all"]).mean())
        for col, lab in (("amt_half_spread", "대금 아래−위 절반"), ("amt_q_spread", "대금 Q1−Q5"), ("amt_low_vs_os", "대금 아래절반−과매도"),
                         ("amt_half_med", "대금 절반 중앙값차"), ("amt_all_half_spread", "전표본 대금 아래−위"),
                         ("r120_half_spread", "120일 아래−위 절반"), ("r120_q_spread", "120일 Q1−Q5"), ("r120_half_med", "120일 절반 중앙값차"), ("r120_low_vs_os", "120일 아래절반−과매도")):
            if col not in sub or sub[col].notna().sum() < 8: continue
            lo, hi = block_ci(sub[col], sub.month)
            rec[lab] = f"{sub[col].mean():+.2f} [{lo:+.2f}, {hi:+.2f}] {100*(sub[col] > 0).mean():.0f}%"
        for mname in ("코스피", "코스닥"):
            for col, lab in ((f"mkt_{mname}_half_spread", f"{mname} 대금 아래−위"), (f"mkt_{mname}_low_vs_os", f"{mname} 아래절반−과매도")):
                if col in sub and sub[col].notna().sum() >= 8:
                    lo, hi = block_ci(sub[col], sub.month); rec[lab] = f"{sub[col].mean():+.2f} [{lo:+.2f}, {hi:+.2f}] {100*(sub[col] > 0).mean():.0f}%"
            if f"mkt_{mname}_n_os" in sub and sub[f"mkt_{mname}_n_os"].notna().any():
                rec[f"{mname} 과매도 중앙"] = int(sub[f"mkt_{mname}_n_os"].median()); rec[f"{mname} 아래절반 대금중앙(억)"] = round(float(sub[f"mkt_{mname}_low_med_eok"].median()), 2)
        if "amt_lowhalf_med_eok" in sub: rec["아래절반 대금중앙(억)"] = round(float(sub.amt_lowhalf_med_eok.median()), 2)
        out.append(rec)
T = pd.DataFrame(out); T.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 40)
for scope in ("전체", "코스피 급락 날", "그 밖", "앞반", "뒤반"):
    print(f"\n=== {scope} ===")
    print(T[T.범위 == scope].drop(columns=["범위"]).to_string(index=False))
print("\n=== 해마다: S5 정리 기본 / 참여율1%·주문1000만 — 대금 아래절반−과매도, 120일 아래−위 절반, 과매도 초과 (%p) ===")
R["year"] = R.date.str[:4]; R["os_ex"] = R.os - R["all"]
Y = R[R.stage.isin(["S5 +동전주 제외(정리 기본)", "감도 참여율1%·주문1000만"])].groupby(["year", "stage"])[["amt_low_vs_os", "r120_half_spread", "os_ex"]].mean().unstack().round(2)
print(Y.to_string()); Y.to_csv(OUT / "by_year.csv", encoding="utf-8-sig")
print(f"\n끝 {time.time()-t0:.0f}s")
