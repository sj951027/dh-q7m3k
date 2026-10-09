# -*- coding: utf-8 -*-
"""earnings_mcap_refix_20261007.py — 실적 배지 자료(earnings_q)의 연구 수집본 행 중 '접수 뒤 주식수가 1.5배 넘게 바뀐' 행의 시총을
접수 시점 값으로 다시 맞춘다 (2026-10-07 작성 · 10/09 1차 적용 · 10/09 오후 2차 — Codex 검토 반영).

문제: 시세 DB(daily_ohlcv)의 종가는 분할·병합·무상증자·감자 뒤 새 기준으로 조정된 값(수정주가)인 경우가 많은데, 주식수는 그날 실제 값이다.
      그래서 사건 전 날짜의 '조정 종가 × 그날 주식수'는 비율만큼 틀린다(1:5 병합이면 5배 과대). 2026.10.16 재구축은 두 주식수 중
      큰 쪽을 써서 배지가 덜 붙는 쪽으로 피했다(1,726행, 147종목).
방법(2차): 주식수 변화 지점마다 **실제로 거래된 날의 종가**(거래량 > 0)로 앞뒤를 견준다.
      · 거래 종가가 주식수와 반대로 움직였으면(가격배수 × 주식수배수 ≈ 1) = DB 의 과거 종가가 **조정되지 않은 원래 값** → 보정하지 않는다(배수 1).
        [10/09 Codex 지적: 012170 은 거래정지 중 주식수만 1/5 로 줄고 정지 전 종가 748원이 그대로 복사돼 있었다. 1차는 '인접일 종가가 같다'를
         가격이 조정된 증거로 잘못 읽어 시총을 1/5 로 줄였다.]
      · 거래 종가가 이어지면(가격배수 ≈ 1) = 과거 종가가 조정된 값 → 주식수가 줄었거나(병합·감자) · 공시가 비율형(무상증자·감자)이거나 ·
        정확히 N배(분할)면 접수 시점 주식수에 그 배수를 곱해 조정 종가와 같은 기준으로. 2배 미만 증자·전환(희석형)은 그대로.
      · 어느 쪽인지 가릴 수 없으면 '불명' → 그 사건이 걸린 행은 손대지 않는다(보정 전 값 = 큰 쪽 주식수, 배지가 덜 붙는 쪽).
      시총 = 접수일 직전 거래일 종가 × 위 주식수.
안전: 기본은 분석만(--apply 가 있어야 earnings.db 를 고친다 · 고치기 전 backup/ 에 사본). --base 로 '보정 전 상태'의 DB(백업)를 주면
      그 값에서 다시 계산한다(1차 적용분을 덮어쓴다). 점수·판정 코드 무관(배지 표시 전용 자료).
"""
import argparse, math, os, shutil, sqlite3, sys, tempfile
from collections import Counter
from datetime import datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
import earnings_flag as EF   # noqa: E402

RATIO_KINDS = ("bonus", "reduction", "paid_bonus_mix")          # dart_events 유형 중 가격이 조정되는 것(무상증자·감자·유무상 혼합)
EVENT_LOOKBACK_DAYS = 120
NEAR = math.log(1.6)           # 두 가설(가격이 조정됨: 거래 종가 배수 ≈ 1 / 미조정: 가격배수 × 주식수배수 ≈ 1) 중 가까운 쪽이 이 안이어야 하고
MARGIN = math.log(1.5)         # 다른 가설보다 이만큼은 더 가까워야 판정한다(정지 뒤 재개 첫날 ±30% 를 허용하되, 애매하면 '불명')
RATIO_TYPES = ("ratio_event", "ratio_clean", "ratio_decrease")


def steps_for(ocon, ticker):
    """[(날짜, 전 주식수, 후 주식수, 뒤 첫 거래 종가, 앞 마지막 거래 종가)] — 주식수가 1.5배 넘게 바뀐 지점만. 거래 종가 = 거래량 > 0 인 날의 종가."""
    rows = ocon.execute("SELECT date, close, shares, volume FROM daily_ohlcv WHERE ticker=? AND shares>0 ORDER BY date", (ticker,)).fetchall()
    out = []
    for i in range(1, len(rows)):
        s0, s1 = rows[i - 1][2], rows[i][2]
        if s0 and s1 and (s1 / s0 > 1.5 or s0 / s1 > 1.5):
            before = next((rows[j][1] for j in range(i - 1, -1, -1) if (rows[j][3] or 0) > 0 and rows[j][1]), None)
            after = next((rows[j][1] for j in range(i, len(rows)) if (rows[j][3] or 0) > 0 and rows[j][1]), None)
            out.append((rows[i][0], float(s0), float(s1), after, before))
    return out


def classify(ocon, ticker, step):
    d, s0, s1, c_after, c_before = step
    if not c_after or not c_before:
        return "unknown"                       # 앞뒤로 실제 거래가 없음(정지가 이어짐)
    r, pr = s1 / s0, c_after / c_before
    d_adj, d_raw = abs(math.log(pr)), abs(math.log(pr * r))
    if d_raw < NEAR and d_adj - d_raw > MARGIN:
        return "price_unadjusted"              # 가격이 주식수와 반대로 뜀 = 과거 종가가 원래 값 → 보정 불필요
    if not (d_adj < NEAR and d_raw - d_adj > MARGIN):
        return "unknown"                       # 어느 쪽인지 가릴 수 없음
    lo = (datetime.strptime(d, "%Y%m%d") - timedelta(days=EVENT_LOOKBACK_DAYS)).strftime("%Y%m%d")
    kinds = {k for (k,) in ocon.execute("SELECT event_type FROM dart_events WHERE ticker=? AND rcept_dt BETWEEN ? AND ?", (ticker, lo, d))}
    if s1 < s0:
        return "ratio_decrease"                # 주식수가 줄었고 거래 종가가 이어짐 = 병합·감자가 가격에 조정돼 있음
    if kinds & set(RATIO_KINDS):
        return "ratio_event"
    if abs(r - round(r)) < 0.01 * r and round(r) >= 2:
        return "ratio_clean"                   # 정확히 N배(가격 이어짐) = 공시 유형에 없는 액면분할
    if kinds & {"paid_in", "cb", "bw", "eb"} and r < 2:
        return "dilution_event"                # 2배 미만 증자·전환 — 가격 조정이 작다고 보고 접수 시점 주식수 그대로
    return "unknown"                           # 2배 넘는 비정수 증가 등 — 손대지 않는다


def shares_adjusted(ocon, ticker, d8, steps, cls):
    """접수일 직전 거래일의 주식수에, 그 뒤 사건의 배수를 유형에 맞게 곱한다. 반환 (주식수, 종가, 시세일, 적용한 사건 수)."""
    lo = (datetime.strptime(d8, "%Y%m%d") - timedelta(days=EF.PRICE_MAX_AGE)).strftime("%Y%m%d")
    r = ocon.execute("SELECT close, shares, date FROM daily_ohlcv WHERE ticker=? AND date<? AND date>=? AND close>0 AND shares>0 ORDER BY date DESC LIMIT 1", (ticker, d8, lo)).fetchone()
    if not r:
        return None, None, None, 0
    close, sh, px_dt = float(r[0]), float(r[1]), r[2]
    n = 0
    for st, k in zip(steps, cls):
        if st[0] <= px_dt:
            continue
        if k in RATIO_TYPES:
            sh *= st[2] / st[1]; n += 1
        elif k == "unknown":
            return None, close, px_dt, -1      # 뒤에 불명 사건이 하나라도 있으면 이 행은 손대지 않는다(종전 값 유지)
        # price_unadjusted · dilution_event → 배수 1
    return sh, close, px_dt, n


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--asof", default=datetime.now().strftime("%Y%m%d"))
    ap.add_argument("--base", default=None, help="보정 전 상태의 earnings.db(백업). 주면 그 값에서 다시 계산해 현재 DB 에 쓴다")
    a = ap.parse_args()
    ocon = sqlite3.connect(f"file:{EF.OHLCV_DB}?mode=ro", uri=True)
    base = a.base or EF.EARN_DB
    bcon = sqlite3.connect(f"file:{base}?mode=ro", uri=True)
    rows = bcon.execute("SELECT ticker, year, reprt, rcept_dt, q_op, q_op_prev, mcap_prev, sue, source FROM earnings_q WHERE source LIKE '%shares_jump%'").fetchall()
    ccon = sqlite3.connect(f"file:{EF.EARN_DB}?mode=ro", uri=True)
    cur = {(t, y, r): (m, s) for t, y, r, m, s in ccon.execute("SELECT ticker, year, reprt, mcap_prev, sue FROM earnings_q")}
    tickers = sorted({r[0] for r in rows}); info = {}
    for t in tickers:
        st = steps_for(ocon, t); info[t] = (st, [classify(ocon, t, s) for s in st])
    kc = Counter(k for st, cl in info.values() for k in cl)
    print(f"• 기준 {os.path.basename(base)} · 대상 {len(rows)}행 · {len(tickers)}종목 · 주식수 변화 지점 {sum(len(v[0]) for v in info.values())}개 → {dict(kc)}")
    upd, flips, nopx, vs_cur = [], Counter(), 0, Counter()
    for t, y, r, d8, q, qp, mc_old, sue_old, src in rows:
        st, cl = info[t]
        sh, close, px_dt, n = shares_adjusted(ocon, t, d8, st, cl)
        if sh is None and n != -1:
            nopx += 1; continue
        if n == -1:                            # 불명 사건이 걸린 행 — 보정 전 값 그대로
            flips["불명 사건이라 종전 값 유지"] += 1; mc_new, sue_new, changed = mc_old, sue_old, False
        else:
            mc_new = close * sh; sue_new = (q - qp) / mc_new
            changed = abs(mc_new / mc_old - 1) >= 0.005
        if changed and abs(sue_new) > EF.SUE_CAP:
            flips["극단값이 돼 종전 값 유지"] += 1; mc_new, sue_new, changed = mc_old, sue_old, False
        b_old, b_new = sue_old <= EF.DROP, sue_new <= EF.DROP
        if b_old != b_new:
            flips["배지 생김" if b_new else "배지 사라짐"] += 1
        source = (src.replace("|shares_jump", "") + "|mcap_refix") if changed else src
        c = cur.get((t, y, r))
        if c and abs(c[0] / mc_new - 1) >= 0.005:
            vs_cur["지금 DB 값과 다름(이번에 바뀜)"] += 1
        upd.append((mc_new, sue_new, (sh if changed else None), (px_dt if changed else None), source, t, y, r, changed))
    n_changed = sum(1 for u in upd if u[8])
    print(f"• 기준 대비 시총이 바뀌는 행 {n_changed} · 그대로 {len(upd) - n_changed} · 시세 없음 {nopx} · 배지(기준 대비): {dict(flips)}")
    print(f"• 현재 DB 대비: {dict(vs_cur) or '차이 없음'}")
    tmp = os.path.join(tempfile.mkdtemp(), "earn.db"); shutil.copy(EF.EARN_DB, tmp)
    SQL = "UPDATE earnings_q SET mcap_prev=?, sue=?, shares_at=?, px_dt=?, source=? WHERE ticker=? AND year=? AND reprt=?"
    w = sqlite3.connect(tmp); w.executemany(SQL, [u[:8] for u in upd]); w.commit(); w.close()
    before, after = EF.load(a.asof, db=EF.EARN_DB), EF.load(a.asof, db=tmp)
    b0 = EF.load(a.asof, db=base) if a.base else before
    print(f"• {a.asof} 기준 배지: 보정 전 {len(b0)} → 지금 DB {len(before)} → 이번 계산 {len(after)} (지금 대비 새로 {len(set(after) - set(before))} · 사라짐 {len(set(before) - set(after))})")
    if a.apply:
        os.makedirs(os.path.join(REPO, "backup"), exist_ok=True)
        bk = os.path.join(REPO, "backup", f"earnings_before_mcap_refix_{datetime.now():%Y%m%d_%H%M%S}.db"); shutil.copy(EF.EARN_DB, bk)
        w = sqlite3.connect(EF.EARN_DB); w.executemany(SQL, [u[:8] for u in upd]); w.commit(); w.close()
        print(f"✅ 적용 {len(upd)}행(그중 기준 대비 변경 {n_changed}) · 직전 상태 백업 {bk}")
    else:
        print("(분석만 — 적용하려면 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
