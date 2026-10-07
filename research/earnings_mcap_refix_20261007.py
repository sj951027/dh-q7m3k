# -*- coding: utf-8 -*-
"""earnings_mcap_refix_20261007.py — 실적 배지 자료(earnings_q)의 연구 수집본 행 중 '접수 뒤 주식수가 1.5배 넘게 바뀐' 행의 시총을
접수 시점 값으로 다시 맞춘다 (2026-10-07, 도전 카드 2).

문제: 시세 DB(daily_ohlcv)의 종가는 분할·병합·무상증자·감자 뒤 **새 기준으로 조정된 값**(수정주가)인데, 주식수는 그날 실제 값이다.
      그래서 사건 전 날짜의 '조정 종가 × 그날 주식수'는 비율만큼 틀린다(1:5 병합이면 5배 과대). 2026.10.16 재구축은 두 주식수 중
      큰 쪽을 써서 배지가 덜 붙는 쪽으로 피했다(1,726행, 147종목).
방법: 종목별 주식수 변화 지점을 찾아 ① 공시(무상증자·감자 = 비율형) 또는 ② 공시 없이 깔끔한 비율(1/N·N배)로 바뀐 것은 '비율형'(가격이 조정됨)
      → 접수 시점 주식수에 그 뒤 비율형 사건의 배수를 곱해 **조정 종가 기준의 주식수**로 바꾼다. 유상증자·CB(희석형)는 가격이 조정되지 않으므로
      접수 시점 주식수를 그대로 둔다. 시총 = 접수일 직전 거래일 조정 종가 × 그 주식수.
안전: 기본은 분석만(--apply 가 있어야 earnings.db 를 고친다 · 고치기 전 backup/ 에 복사). 점수·판정 코드 무관(배지 표시 전용 자료).
"""
import argparse, os, shutil, sqlite3, sys
from datetime import datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
import earnings_flag as EF   # noqa: E402

RATIO_KINDS = ("bonus", "reduction", "paid_bonus_mix")          # dart_events 유형 중 가격이 조정되는 것(무상증자·감자·유무상 혼합)
CLEAN = [1 / n for n in range(2, 21)] + [float(n) for n in range(2, 21)]
EVENT_LOOKBACK_DAYS = 120


def clean_ratio(r, tol=0.02):
    return any(abs(r / c - 1) < tol for c in CLEAN)


def steps_for(ocon, ticker):
    """[(날짜, 전 주식수, 후 주식수, 그날 종가, 전날 종가)] — 1.5배 넘게 바뀐 지점만."""
    rows = ocon.execute("SELECT date, close, shares FROM daily_ohlcv WHERE ticker=? AND shares>0 ORDER BY date", (ticker,)).fetchall()
    out = []
    for i in range(1, len(rows)):
        s0, s1 = rows[i - 1][2], rows[i][2]
        if s0 and s1 and (s1 / s0 > 1.5 or s0 / s1 > 1.5):
            out.append((rows[i][0], float(s0), float(s1), rows[i][1], rows[i - 1][1]))
    return out


def classify(ocon, ticker, step):
    d, s0, s1, c1, c0 = step
    lo = (datetime.strptime(d, "%Y%m%d") - timedelta(days=EVENT_LOOKBACK_DAYS)).strftime("%Y%m%d")
    kinds = {k for (k,) in ocon.execute("SELECT event_type FROM dart_events WHERE ticker=? AND rcept_dt BETWEEN ? AND ?", (ticker, lo, d))}
    px_cont = bool(c0 and c1) and 0.8 <= c1 / c0 <= 1.25
    if kinds & set(RATIO_KINDS):
        return "ratio_event"
    if kinds & {"paid_in", "cb", "bw", "eb"}:
        return "dilution_event"
    if px_cont and clean_ratio(s1 / s0):
        return "ratio_clean"        # 공시 유형에 없는 주식병합·분할(가격 연속 + 깔끔한 비율)
    return "unknown"


def shares_adjusted(ocon, ticker, d8, steps, cls):
    """접수일 직전 거래일의 주식수에, 그 뒤 '비율형' 사건의 배수를 곱해 조정 종가 기준으로. 반환 (주식수, 종가, 시세일, 적용한 사건 수)."""
    lo = (datetime.strptime(d8, "%Y%m%d") - timedelta(days=EF.PRICE_MAX_AGE)).strftime("%Y%m%d")
    r = ocon.execute("SELECT close, shares, date FROM daily_ohlcv WHERE ticker=? AND date<? AND date>=? AND close>0 AND shares>0 ORDER BY date DESC LIMIT 1", (ticker, d8, lo)).fetchone()
    if not r:
        return None, None, None, 0
    close, sh, px_dt = float(r[0]), float(r[1]), r[2]
    n = 0
    for st, k in zip(steps, cls):
        if st[0] > px_dt and k in ("ratio_event", "ratio_clean"):
            sh *= st[2] / st[1]; n += 1
    return sh, close, px_dt, n


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--asof", default=datetime.now().strftime("%Y%m%d"))
    a = ap.parse_args()
    ocon = sqlite3.connect(f"file:{EF.OHLCV_DB}?mode=ro", uri=True)
    econ = sqlite3.connect(f"file:{EF.EARN_DB}?mode=ro", uri=True)
    rows = econ.execute("SELECT ticker, year, reprt, rcept_dt, q_op, q_op_prev, mcap_prev, sue, source FROM earnings_q WHERE source LIKE '%shares_jump%'").fetchall()
    tickers = sorted({r[0] for r in rows})
    info = {}
    for t in tickers:
        st = steps_for(ocon, t); info[t] = (st, [classify(ocon, t, s) for s in st])
    from collections import Counter
    kc = Counter(k for st, cl in info.values() for k in cl)
    print(f"• 대상 {len(rows)}행 · {len(tickers)}종목 · 주식수 변화 지점 {sum(len(v[0]) for v in info.values())}개 → {dict(kc)}")
    upd, same, nopx = [], 0, 0; flips = Counter()
    for t, y, r, d8, q, qp, mc_old, sue_old, src in rows:
        st, cl = info[t]
        sh, close, px_dt, n = shares_adjusted(ocon, t, d8, st, cl)
        if sh is None:
            nopx += 1; continue
        mc_new = close * sh
        if abs(mc_new / mc_old - 1) < 0.005:
            same += 1; continue
        sue_new = (q - qp) / mc_new
        if abs(sue_new) > EF.SUE_CAP:
            flips["extreme_now"] += 1; continue
        b_old, b_new = sue_old <= EF.DROP, sue_new <= EF.DROP
        flips[("배지 유지" if b_old and b_new else "배지 생김" if b_new else "배지 사라짐" if b_old else "변화 없음")] += 1
        upd.append((mc_new, sue_new, sh, px_dt, (src.replace("|shares_jump", "") + "|mcap_refix"), t, y, r))
    print(f"• 시총이 바뀌는 행 {len(upd)} · 그대로 {same} · 시세 없음 {nopx} · 배지 변화: {dict(flips)}")
    ratios = sorted(u[0] / next(m for (tt, yy, rr, _, _, _, m, _, _) in rows if (tt, yy, rr) == (u[5], u[6], u[7])) for u in upd)
    if ratios:
        print(f"  새 시총 ÷ 옛 시총: 최소 {ratios[0]:.3f} · 중앙 {ratios[len(ratios)//2]:.3f} · 최대 {ratios[-1]:.3f}")
    # 오늘 기준 배지 집합 변화(임시 복사본에 적용해 비교)
    import tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "earn.db"); shutil.copy(EF.EARN_DB, tmp)
    w = sqlite3.connect(tmp)
    w.executemany("UPDATE earnings_q SET mcap_prev=?, sue=?, shares_at=?, px_dt=?, source=? WHERE ticker=? AND year=? AND reprt=?", upd); w.commit(); w.close()
    before, after = EF.load(a.asof, db=EF.EARN_DB), EF.load(a.asof, db=tmp)
    print(f"• {a.asof} 기준 배지: 전 {len(before)} → 후 {len(after)} (새로 생김 {len(set(after) - set(before))} · 사라짐 {len(set(before) - set(after))})")
    if a.apply and upd:
        os.makedirs(os.path.join(REPO, "backup"), exist_ok=True)
        bk = os.path.join(REPO, "backup", f"earnings_before_mcap_refix_{datetime.now():%Y%m%d_%H%M%S}.db"); shutil.copy(EF.EARN_DB, bk)
        w = sqlite3.connect(EF.EARN_DB)
        w.executemany("UPDATE earnings_q SET mcap_prev=?, sue=?, shares_at=?, px_dt=?, source=? WHERE ticker=? AND year=? AND reprt=?", upd); w.commit(); w.close()
        print(f"✅ 적용 {len(upd)}행 · 백업 {bk}")
    elif not a.apply:
        print("(분석만 — 적용하려면 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
