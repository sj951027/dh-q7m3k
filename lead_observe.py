# -*- coding: utf-8 -*-
"""lead_observe.py — lead 트랙(주도주) 월 1회 관측 픽 적재 (PREREGISTER_ld_a.md, 2026-09-24 등록)

무엇: 매월 '첫 거래일'(daily_ohlcv 기준) 종가로 전체 가드 유니버스를 줄 세워 top20 을 history.db
      `lead_picks` 에 동결 저장한다. 표시 없음·가중 0·기존 점수/판정/게이트 무접촉(0-diff).
모델:  ld_a      = rank(beta60, 높을수록↑) + (1 − rank(days_since_high))   [핵심 beta60 필수 · 보조 NaN=0.5]
                   + 동행 그룹(120일 수익률 상관 k-means 25) 그룹당 4종목 상한
       ld_ctl_amt = 거래대금20 상위 20 (대조군 — 모델 아님, 판정 짝비교용)
판정:  PREREGISTER_ld_a.md §3 — 120거래일 보유·비용 0.5%·픽 시장비중 지수/동일가중/대조군 3중 · 비겹침 3창.
       §11(h20 IC·40거래일)은 이 트랙에 적용하지 않는다. 평가는 lead_eval.py.
게이트: 자동 앵커 = daily_ohlcv '최신 달의 첫 거래일'(month_anchor). 그날 배치가 못 돌아도 같은 달 안의 다음 배치가 따라잡는다
        (팩터는 앵커일까지 정보만 쓰므로 스펙 동일 — 2026-09-24 전수점검 결함 1 수정). 등록일(REG_DATE 20261001) 이전 달은 건너뜀.
        같은 달 행이 이미 있으면 재적재 금지(동결). 앵커일 종목 수 <2000 이면 적재 안 하고 exit 1(다음 배치 재시도). --dry-run 은 DB 무접촉.
실행:  python lead_observe.py                (배치, 월초 자동)
       python lead_observe.py --anchor 20260901 --dry-run     (재현/검증 — 첫 거래일 아니어도 --force 로 계산만)
"""
import argparse, hashlib, json, os, sqlite3, sys
from datetime import datetime
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, "history.db")
OHLCV = os.path.join(HERE, "..", "dh-q7m3k-data", "ohlcv.db")
TABLE = "lead_picks"

# ---------- 스펙 (동결) ----------
MODEL = "ld_a"
CONTROL = "ld_ctl_amt"
TOP_N = 20
CLUSTER_K = 25; CLUSTER_CAP = 4; CLUSTER_WIN = 120; CLUSTER_EIG = 10; CLUSTER_SEED = 0
GUARD = {"flat63_max": 0.5, "jump21_cap": 0.32, "rv21_floor": 0.003, "amt20_floor": 5e8, "suspended": 0}
FACTORS = {"beta60": "cov(ret, idx_ret; 60, min40) / var(idx_ret; 60, min40), 같은 시장 지수(KOSPI/KOSDAQ)",
           "days_since_high": "close >= 0.999*rollmax(close,252,min120) 이후 경과 거래일(신고가일=0; 룩백 330일 내 신고가 없음=330)"}
LOOKBACK = 330   # 앵커 이전 필요 거래일(252+60 여유)

def spec_hash(model_id):
    payload = json.dumps({
        "model": model_id,
        "factors": (["beta60+", "days_since_high-"] if model_id == MODEL else ["amt20+"]),
        "defs": FACTORS if model_id == MODEL else {"amt20": "mean(close*volume,20,min10)"},
        "method": "pooled_pct_rank_sum(core_required=first,aux_nan=0.5)",
        "top_n": TOP_N, "cluster": ({"k": CLUSTER_K, "cap": CLUSTER_CAP, "win": CLUSTER_WIN, "eig": CLUSTER_EIG, "seed": CLUSTER_SEED} if model_id == MODEL else None),
        "universe": GUARD, "anchor": "first_trading_day_of_month(daily_ohlcv)", "entry": "t+1 close", "hold": 120, "cost_rt": 0.005,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]

# ---------- 순수 함수 (테스트 대상) ----------
def roll_mean(a, w, minp): return pd.DataFrame(a).rolling(w, min_periods=minp).mean().values
def roll_std(a, w, minp): return pd.DataFrame(a).rolling(w, min_periods=minp).std().values
def roll_max(a, w, minp): return pd.DataFrame(a).rolling(w, min_periods=minp).max().values

def rank01(x):
    return pd.DataFrame(x).rank(axis=1, pct=True).values

def rank_sum(core_rank, aux_ranks):
    """핵심 순위(NaN=제외) + 보조(NaN=0.5). 모두 '높을수록 좋음'으로 정렬된 0~1 순위."""
    sc = core_rank.copy()
    for r in aux_ranks:
        sc = sc + np.where(np.isfinite(r), r, 0.5)
    return sc

def is_first_trading_day(dates_sorted, anchor):
    """같은 YYYYMM 안에 anchor 보다 이른 거래일이 없으면 True."""
    ym = anchor[:6]
    return not any(d < anchor and d[:6] == ym for d in dates_sorted)

REG_DATE = "20261001"   # PREREGISTER_ld_a — 이 날 이전 달은 앵커로 잡지 않는다(소급 적재 없음)

def month_anchor(dates_sorted, reg_date=REG_DATE):
    """자동 앵커 = daily_ohlcv 최신 달의 '첫 거래일'. 그날 배치가 못 돌아도(PC 꺼짐·부분 수집) 같은 달 안에서 따라잡는다 —
    팩터는 앵커일까지 정보만 쓰므로 며칠 뒤 계산해도 같은 스펙. 최신 달의 첫 거래일이 reg_date 이전이면 None."""
    if not dates_sorted: return None
    ym = dates_sorted[-1][:6]
    first = next(d for d in dates_sorted if d[:6] == ym)
    return first if first >= reg_date else None

def kmeans(X, k, seed=0, it=30):
    rng = np.random.default_rng(seed)
    C_ = X[rng.choice(len(X), k, replace=False)].copy()
    lab = np.zeros(len(X), int)
    for _ in range(it):
        d = ((X[:, None, :] - C_[None, :, :]) ** 2).sum(-1); lab = d.argmin(1)
        for i in range(k):
            if (lab == i).any(): C_[i] = X[lab == i].mean(0)
    return lab

def cluster_labels(ret_win, seed=CLUSTER_SEED, k=CLUSTER_K, eig=CLUSTER_EIG):
    """ret_win: (win, n) 일수익 — 표준화 → 상관 → 상위 고유벡터 → k-means. 결정적(seed 고정)."""
    r = np.where(np.isfinite(ret_win), ret_win, 0.0)
    r = (r - r.mean(0)) / (r.std(0) + 1e-9)
    Cm = (r.T @ r) / len(r)
    w, v = np.linalg.eigh(Cm)
    X = v[:, -eig:] * np.sqrt(np.maximum(w[-eig:], 0))
    return kmeans(X, min(k, len(X)), seed=seed)

def pick_with_cap(order, labels, cap, n):
    """order: 점수 내림차순 인덱스(유효분만). labels: idx->cluster(없으면 -1). 그룹당 cap."""
    pick, cnt = [], {}
    for j in order:
        k = labels.get(int(j), -1)
        if cap and cnt.get(k, 0) >= cap: continue
        pick.append(int(j)); cnt[k] = cnt.get(k, 0) + 1
        if len(pick) == n: break
    return pick

# ---------- 데이터 ----------
def load_panel(anchor):
    con = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    all_dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
    if anchor not in all_dates: con.close(); raise SystemExit(f"[중단] 앵커 {anchor} 가 daily_ohlcv 에 없음")
    ai = all_dates.index(anchor)
    if ai < LOOKBACK: con.close(); raise SystemExit(f"[중단] 룩백 {LOOKBACK}거래일 미달")
    start = all_dates[ai - LOOKBACK]
    df = pd.read_sql("SELECT ticker,date,close,volume,shares,is_suspended,market FROM daily_ohlcv WHERE date BETWEEN ? AND ?", con, params=(start, anchor))
    md = pd.read_sql("SELECT series,date,close FROM market_daily WHERE date BETWEEN ? AND ?", con, params=(start, anchor))
    con.close()
    df = df[df.ticker.str.fullmatch(r"\d{6}")]
    dates = np.array(sorted(df.date.unique())); tick = np.array(sorted(df.ticker.unique()))
    di = {d: i for i, d in enumerate(dates)}; ti = {t: i for i, t in enumerate(tick)}
    r = df.date.map(di).values; c_ = df.ticker.map(ti).values
    def mat(col, fill=np.nan):
        m = np.full((len(dates), len(tick)), fill, dtype=np.float64); m[r, c_] = df[col].values.astype(np.float64); return m
    P = dict(dates=dates, tick=tick, close=mat("close"), vol=mat("volume"), shares=mat("shares"), susp=mat("is_suspended", 0.0))
    P["mk"] = df.groupby("ticker").market.last().reindex(tick).values.astype(str)
    mdp = md.pivot(index="date", columns="series", values="close").reindex(dates)
    P["kospi"] = mdp["KOSPI"].ffill().values.astype(float); P["kosdaq"] = mdp["KOSDAQ"].ffill().values.astype(float)
    return P, all_dates

def compute(P):
    c = P["close"]; T, N = c.shape
    with np.errstate(all="ignore"):
        ret = np.vstack([np.full((1, N), np.nan), c[1:] / c[:-1] - 1]); ret[~np.isfinite(ret)] = np.nan
        amt = c * P["vol"]
        flat = roll_mean((np.abs(ret) < 1e-9).astype(float), 63, 20) > GUARD["flat63_max"]
        jump = roll_max((np.abs(ret) > GUARD["jump21_cap"]).astype(float), 21, 5) > 0
        rv21 = roll_std(ret, 21, 15); amt20 = roll_mean(amt, 20, 10)
        ok = (~flat) & (~jump) & (rv21 >= GUARD["rv21_floor"]) & (amt20 >= GUARD["amt20_floor"]) & (P["susp"] == 0) & np.isfinite(c)
        idx = np.where(P["mk"] == "KOSPI", 0, 1)
        kp, kq = P["kospi"], P["kosdaq"]
        mi = np.where(idx[None, :] == 0, np.r_[np.nan, kp[1:] / kp[:-1] - 1][:, None], np.r_[np.nan, kq[1:] / kq[:-1] - 1][:, None])
        cov = roll_mean(ret * mi, 60, 40) - roll_mean(ret, 60, 40) * roll_mean(mi, 60, 40)
        var = roll_std(mi, 60, 40) ** 2
        beta60 = cov / var
        beta60[~np.isfinite(beta60)] = np.nan          # 지수 분산 0 등 비유한값 → 결측(핵심 팩터라 제외)
        rm = roll_max(c, 252, 120); ishigh = c >= rm * 0.999
        dsh = np.full((T, N), np.nan); cnt = np.full(N, np.nan)
        for t in range(T):
            cnt = np.where(ishigh[t], 0, cnt + 1); dsh[t] = cnt
        # 룩백 창 안에서 신고가가 한 번도 없었던 종목(연구 패널에선 '오래 전') = 최하위: 창 길이로 고정
        obs = np.cumsum(np.isfinite(c), axis=0)
        dsh = np.where(~np.isfinite(dsh) & np.isfinite(c) & (obs >= 120), float(LOOKBACK), dsh)
        mcap = c * P["shares"]
    return dict(ret=ret, ok=ok, beta60=beta60, dsh=dsh, amt20=amt20, mcap=mcap, idx=idx)

def select(P, F, a):
    """앵커 행 a 에서 ld_a top20(그룹 상한) + 대조군 top20. 반환 (rows_model, rows_control, meta)."""
    ok = F["ok"][a]
    rb = rank01(np.where(ok, F["beta60"][a], np.nan)[None, :])[0]
    rd = rank01(np.where(ok, F["dsh"][a], np.nan)[None, :])[0]
    score = rank_sum(rb, [1 - rd])                         # 핵심 beta60 · 보조 (1−rank dsh)
    valid = np.isfinite(score)
    order = np.argsort(-np.where(valid, score, -np.inf), kind="stable")[: int(valid.sum())]
    # 동행 그룹
    labels, cap_applied = {}, 0
    try:
        js = np.where(ok & np.isfinite(P["close"][a]))[0]
        lab = cluster_labels(F["ret"][a - CLUSTER_WIN + 1: a + 1][:, js])
        labels = {int(j): int(l) for j, l in zip(js, lab)}; cap_applied = 1
    except Exception as e:  # 실패 시 상한 없이(적재 행에 cap_applied=0 기록)
        print(f"  [경고] 클러스터 실패 → 상한 없이 선정: {e}")
    pick = pick_with_cap(order, labels, CLUSTER_CAP if cap_applied else 0, TOP_N)
    ra = rank01(np.where(ok, F["amt20"][a], np.nan)[None, :])[0]
    ctl = [int(j) for j in np.argsort(-np.where(np.isfinite(ra), ra, -np.inf), kind="stable")[:TOP_N]]
    def rows(model, idxs, sc):
        out = []
        for rnk, j in enumerate(idxs, 1):
            out.append(dict(model_id=model, rank=rnk, ticker=P["tick"][j], market=P["mk"][j], score=float(sc[j]),
                            beta60=float(F["beta60"][a][j]), days_since_high=(None if not np.isfinite(F["dsh"][a][j]) else int(F["dsh"][a][j])),
                            cluster=labels.get(int(j), -1), cap_applied=cap_applied if model == MODEL else 0,
                            marcap=float(F["mcap"][a][j]) if np.isfinite(F["mcap"][a][j]) else None,
                            amt20=float(F["amt20"][a][j]), close=float(P["close"][a][j])))
        return out
    return rows(MODEL, pick, score), rows(CONTROL, ctl, ra), dict(n_universe=int(ok.sum()), cap_applied=cap_applied)

# ---------- DB ----------
UNI_TABLE = "lead_universe"   # 앵커일 가드 유니버스(동일가중 비교 ② 재현용, 모델 무관)

def ensure_table(con):
    con.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE} (
        model_id TEXT, run_id TEXT, rank INTEGER, ticker TEXT, market TEXT, name TEXT,
        score REAL, beta60 REAL, days_since_high INTEGER, cluster INTEGER, cap_applied INTEGER,
        marcap REAL, amt20 REAL, close REAL, n_universe INTEGER, spec_hash TEXT, frozen_at TEXT,
        PRIMARY KEY (model_id, run_id, ticker))""")
    con.execute(f"""CREATE TABLE IF NOT EXISTS {UNI_TABLE} (
        run_id TEXT, ticker TEXT, market TEXT, PRIMARY KEY (run_id, ticker))""")

def names_map():
    try:
        con = sqlite3.connect(f"file:{HIST}?mode=ro", uri=True)
        d = {t: (n or "") for t, n in con.execute("SELECT ticker, name FROM stage1_oversold GROUP BY ticker").fetchall()}; con.close(); return d
    except Exception:
        return {}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", help="YYYYMMDD (기본: daily_ohlcv 최신일)")
    ap.add_argument("--dry-run", action="store_true", help="DB 무접촉(계산·출력만)")
    ap.add_argument("--force", action="store_true", help="첫 거래일 게이트 무시(dry-run 전용)")
    a = ap.parse_args()
    if a.force and not a.dry_run:
        print("[중단] --force 는 --dry-run 과 함께만(동결 원칙)"); return 2
    con0 = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    all_dates = [r[0] for r in con0.execute("SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
    if a.anchor:
        anchor = a.anchor
        if not is_first_trading_day(all_dates, anchor) and not a.force:
            print(f"[lead_observe] {anchor} 은 첫 거래일 아님({anchor[:6]}월) → 건너뜀"); con0.close(); return 0
    else:
        anchor = month_anchor(all_dates, REG_DATE)
        if anchor is None:
            print(f"[lead_observe] 최신 달({all_dates[-1][:6]}) 첫 거래일이 등록일({REG_DATE}) 이전 → 건너뜀"); con0.close(); return 0
    nrow = con0.execute("SELECT COUNT(*) FROM daily_ohlcv WHERE date=?", (anchor,)).fetchone()[0]; con0.close()
    print(f"[lead_observe] 앵커 {anchor} · 행 {nrow} · 최신일 {all_dates[-1]}")
    if nrow < 2000:
        print(f"  [중단] 앵커일 종목 수 {nrow} < 2000 (부분 수집 의심) → 적재 안 함(다음 배치에서 재시도)"); return 1
    if not a.dry_run:
        con = sqlite3.connect(HIST); ensure_table(con)
        dup = con.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE model_id=? AND substr(run_id,1,6)=?", (MODEL, anchor[:6])).fetchone()[0]
        if dup:
            print(f"  이미 {anchor[:6]}월 적재 있음({dup}행) → 동결, 건너뜀"); con.close(); return 0
        con.close()
    P, _ = load_panel(anchor); F = compute(P); ai = int(np.where(P["dates"] == anchor)[0][0])
    rows_m, rows_c, meta = select(P, F, ai)
    nm = names_map(); now = datetime.now().isoformat(timespec="seconds")
    print(f"  유니버스 {meta['n_universe']} · 그룹상한 {'적용' if meta['cap_applied'] else '미적용'} · spec {spec_hash(MODEL)} / ctl {spec_hash(CONTROL)}")
    for r in rows_m:
        print(f"   {r['rank']:2d} {r['ticker']} {(nm.get(r['ticker']) or ''):10s} {r['market']:6s} beta {r['beta60']:.2f} dsh {r['days_since_high']} grp {r['cluster']:2d} amt {r['amt20']/1e8:6.0f}억")
    print("  대조군(거래대금 상위20):", " ".join(r["ticker"] for r in rows_c))
    if a.dry_run:
        print("  (dry-run — DB 무접촉)"); return 0
    con = sqlite3.connect(HIST); ensure_table(con)
    for rows in (rows_m, rows_c):
        for r in rows:
            con.execute(f"INSERT OR IGNORE INTO {TABLE} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (r["model_id"], anchor, r["rank"], r["ticker"], r["market"], nm.get(r["ticker"], ""), r["score"], r["beta60"],
                         r["days_since_high"], r["cluster"], r["cap_applied"], r["marcap"], r["amt20"], r["close"], meta["n_universe"],
                         spec_hash(r["model_id"]), now))
    uni = np.where(F["ok"][ai])[0]
    con.executemany(f"INSERT OR IGNORE INTO {UNI_TABLE} VALUES (?,?,?)", [(anchor, P["tick"][j], P["mk"][j]) for j in uni])
    con.commit(); con.close()
    print(f"  ✓ {TABLE} 적재: {MODEL} {len(rows_m)}행 · {CONTROL} {len(rows_c)}행 · {UNI_TABLE} {len(uni)}행 (run_id {anchor})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
