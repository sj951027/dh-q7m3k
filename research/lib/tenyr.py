# -*- coding: utf-8 -*-
"""11년 대리 틀 (2026-11-08 — `signal_board_10y_20261108.py`·`hold_early_exit_10y_20261108.py`·`sector_concentration_10y_20261108.py` 가 복사해 쓰던 공통부를 한 곳으로).

쓰는 법:
    import sys; sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # research/ 를 경로에
    from lib import tenyr
    tenyr.reset_rng()                           # 부트스트랩 재현(seed 7)
    P = tenyr.load_panel()                      # ohlcv_10y.db 읽기 전용 · 정리 유니버스
    R = tenyr.signal_days(P)                    # 5거래일 격자 신호일 × 과매도 대리(20일 하위 20%) 40일 · 전 종목 40일 · 초과
    lo, hi = tenyr.block_ci(R.exc, R.month)     # 월 블록 부트스트랩 2,000회

고정값(결과 비교의 '같은 자'): STEP 5 · H 40 · COST 0.0035(왕복) · SPLIT 20210101(앞/뒤반) · 시작 i=130 · 유효 ≥300 종목인 날만 ·
정리 유니버스 = KOSPI/KOSDAQ/KOSDAQ GLOBAL · 보통주(코드 끝 0) · 금융·스팩·리츠 제외 · 거래량 0·동전주(<1,000원) 제외 · 상폐 = 마지막 가격 유지.
바꾸고 싶으면 인자로 넘기되, 바꾼 값은 메모 §0 에 적는다(매직넘버 금지).
검증: `tests/test_tenyr_lib.py` 가 `research/out_signal_board/{tenyr_days,e1_cells}.csv` 와 0-diff 인지 확인."""
import os, sqlite3, time
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(__file__).resolve().parents[2]
DB = os.environ.get("OHLCV_10Y_DB", str(REPO / ".." / "dh-q7m3k-data" / "ohlcv_10y.db"))
STEP = 5; SPLIT = "20210101"; H = 40; COST = 0.0035; START = 130; MIN_OK = 300; SEED = 7; K = 2000
FIN_KW = ['금융', '은행', '증권', '보험', '캐피탈', '캐피털', '카드', '손해보험', '생명', '화재', '저축', '여신', '신탁', '리츠', 'REIT', '부동산투자', '스팩', 'SPAC']
FIN_TICKERS = {'055550', '001450'}
MARKETS = ("KOSPI", "KOSDAQ", "KOSDAQ GLOBAL")
rng = np.random.default_rng(SEED)


def reset_rng(seed=SEED):
    """스크립트 첫 줄에서 호출 — 부트스트랩 호출 순서가 같으면 결과가 그대로 재현된다."""
    global rng
    rng = np.random.default_rng(seed)
    return rng


def block_ci(vals, months, k=K):
    """월 블록 부트스트랩 평균의 95% 구간."""
    vals = np.asarray(vals, float); months = np.asarray(months); m = ~np.isnan(vals); vals, months = vals[m], months[m]
    um = np.unique(months)
    if len(um) == 0:
        return (np.nan, np.nan)
    by = {u: vals[months == u] for u in um}
    ms = [np.concatenate([by[u] for u in rng.choice(um, len(um))]).mean() for _ in range(k)]
    return float(np.percentile(ms, 2.5)), float(np.percentile(ms, 97.5))


def diff_ci(a, b, col="exc", k=K):
    """두 집단(DataFrame: col, month)을 월 블록으로 각각 재표집한 평균 차이(a−b)의 95% 구간."""
    ua, ub = a.month.unique(), b.month.unique()
    ga = {u: a[col][a.month == u].values for u in ua}; gb = {u: b[col][b.month == u].values for u in ub}
    d = [np.concatenate([ga[u] for u in rng.choice(ua, len(ua))]).mean() - np.concatenate([gb[u] for u in rng.choice(ub, len(ub))]).mean() for _ in range(k)]
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def cell6(x):
    """코스피 20일 등락(%) → buy_context 6칸(A2 ≤−10 · A1 ≤−5 · B ≤0 · C ≤5 · D1 ≤10 · D2)."""
    if x != x:
        return None
    for k_, hi in (("A2", -10), ("A1", -5), ("B", 0), ("C", 5), ("D1", 10)):
        if x <= hi:
            return k_
    return "D2"


CELL4 = {"A2": "A", "A1": "A", "B": "B", "C": "C", "D1": "D", "D2": "D"}


def _is_universe(t, m, n):
    return (m in MARKETS) and t.endswith("0") and t not in FIN_TICKERS and not any(k in n.upper() if k in ("SPAC", "REIT") else k in n for k in FIN_KW)


class Panel:
    """정리 유니버스 가격판. CU 원 종가 · CF 상폐 ffill 종가 · VU 거래량 · PEN 동전주 · R20 20일 수익(비율) · ks 코스피 종가 · ks_r20 (%)."""

    def __init__(self, db=DB, verbose=True):
        t0 = time.time()
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        px = pd.read_sql("SELECT ticker, date, close, volume FROM prices", con)
        self.meta = pd.read_sql("SELECT ticker, name, market, note FROM meta", con).set_index("ticker")
        self.ks = pd.read_sql("SELECT date, close FROM index_daily WHERE series='KOSPI'", con).set_index("date")["close"].sort_index()
        con.close()
        close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index(); close = close.where(close > 0)
        vol = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(close.index); del px
        tick = list(close.columns)
        mk = self.meta.market.reindex(tick); nm = self.meta.name.reindex(tick).fillna("")
        in_u = pd.Series([_is_universe(t, m, n) for t, m, n in zip(tick, mk, nm)], index=tick)
        self.cu = close.loc[:, in_u.values]; self.vu = vol.loc[:, in_u.values]; del close, vol
        self.dates = list(self.cu.index); self.N = len(self.dates); self.tick = list(self.cu.columns)
        self.ks_r20 = (self.ks / self.ks.shift(20) - 1).reindex(self.dates) * 100
        dl = self.meta.note.reindex(self.tick).fillna("").str.contains("delisted").values
        cf = self.cu.copy(); cf.loc[:, dl] = cf.loc[:, dl].ffill()
        self.CU = self.cu.values; self.CF = cf.values; self.VU = self.vu.fillna(0).values
        self.PEN = (self.cu < 1000).fillna(True).values; self.R20 = (self.cu / self.cu.shift(20) - 1).values
        if verbose:
            print(f"유니버스 {len(self.tick)} 종목 · 날 {self.N} · {time.time()-t0:.0f}s")


def load_panel(db=DB, verbose=True):
    return Panel(db, verbose)


def signal_days(P, H=H, step=STEP, start=START, cost=COST, q=0.20, min_ok=MIN_OK, extra=None):
    """신호일 격자 → 한 줄씩: date · month · half · i · r20(코스피 %) · cell · cell4 · n_os · os40 · all40 · exc(%p).
    extra(P, i, ok) 가 있으면 그 dict 를 줄에 합친다(예: 변동성·업종 집중도)."""
    rows = []
    for i in range(start, P.N - H - 1, step):
        r = P.R20[i]
        v0 = (P.VU[i] == 0) | (P.VU[i + 1] == 0)
        e = P.CU[i + 1]; pH = P.CF[i + 1 + H]
        ok = ~np.isnan(r) & ~v0 & ~P.PEN[i] & ~np.isnan(e) & (e > 0) & ~np.isnan(pH)
        if ok.sum() < min_ok:
            continue
        d = P.dates[i]
        thr = np.quantile(r[ok], q); os_ = ok & (r <= thr)
        g = pH / e - 1 - cost
        osH = g[os_].mean() * 100; allH = g[ok].mean() * 100
        row = dict(date=d, month=d[:6], half=("앞" if d < SPLIT else "뒤"), i=i, r20=P.ks_r20.iloc[i], cell=cell6(P.ks_r20.iloc[i]),
                   n_os=int(os_.sum()), os40=osH, all40=allH, exc=osH - allH)
        if extra is not None:
            row.update(extra(P, i, ok))
        rows.append(row)
    R = pd.DataFrame(rows)
    R["cell4"] = R.cell.map(CELL4)
    return R


def summ(sub):
    """한 칸 요약(과매도·시장·초과 평균과 CI, 비율). 부트스트랩 호출 순서 = exc → all40 → os40 (재현용)."""
    lo, hi = block_ci(sub.exc, sub.month); mlo, mhi = block_ci(sub.all40, sub.month); olo, ohi = block_ci(sub.os40, sub.month)
    return dict(날수=len(sub), 월수=sub.month.nunique(), 과매도40=sub.os40.mean(), 과매도하한=olo, 과매도상한=ohi, 시장40=sub.all40.mean(), 시장하한=mlo, 시장상한=mhi,
                시장플러스비율=(sub.all40 > 0).mean() * 100, 초과=sub.exc.mean(), 초과하한=lo, 초과상한=hi, 초과양수비율=(sub.exc > 0).mean() * 100)
