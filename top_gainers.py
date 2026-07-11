"""
top_gainers.py — "무엇이 올랐고, 오른 종목은 어떤 특성이었나" (research 탐색 전용)
================================================================================
§14 research 모드: ohlcv.db READONLY, 산출물 research/ 한정, 게이트 면제.
점수테이블·docs·텔레그램 안 씀. 네트워크 0. 채택 판정 아님(§11 별도).

두 모드:
  1) 기본(최근 구간): 앵커=최근 --days 거래일 전. 앵커→최신 상승률 상위 종목 +
     '앵커 시점' 팩터 프로파일(포인트-인-타임: 팩터는 앵커 이전 데이터만 사용).
  2) --full(전 기간): 20일 간격 앵커 반복 → h=--h 전방수익 상위 10% '승자'들의
     팩터 백분위 평균 + 팩터별 Spearman IC(앵커별)·5분위 수익. 표본수 함께 출력.

사용:
    python top_gainers.py                  # 최근 60거래일 상승률 상위 + 특성
    python top_gainers.py --days 20
    python top_gainers.py --full --h 20    # 전 기간 승자 특성(가설)
"""
import argparse
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
OHLCV_DB = os.environ.get(
    "OHLCV_DB", os.path.join(HERE, "..", "dh-q7m3k-data", "ohlcv.db"))
RESEARCH_DIR = os.path.join(HERE, "research")

# 가드(whole_score.py 상속)
VOL_FLOOR = 0.003
MAX_FLAT_RATIO = 0.5
MAX_ABS_RET = 0.30
LIQ_FLOOR = 5.0          # 억
FWD_ABS_CUT = 0.32       # 전방 |일수익| 데이터오류 컷(RESEARCH_wholeuniverse 동일)

# 팩터 방향(True=큰값이 '가설상 좋음') — wu/whole_score 정의와 정렬
FACTORS = {
    "lv63":   (False, "63일 변동성(저변동 우대)"),
    "rv21":   (False, "21일 변동성"),
    "nh252":  (True,  "52주고가 근접(close/max252-1)"),
    "mom12":  (True,  "12-1개월 모멘텀"),
    "mom_1m": (True,  "1개월 수익률"),
    "sma20":  (True,  "20일선 이격(%)"),
    "vol_exp": (True, "변동성 팽창(std5/std21)"),
    "drawdown": (True, "52주 낙폭(큰 낙폭=가점, v3 가설방향)"),
    "big":    (True,  "log10(시총)"),
    "amt20":  (True,  "20일 평균 거래대금(억)"),
}


def load_panels(con):
    cols = [r[1] for r in con.execute("PRAGMA table_info(daily_ohlcv)")]
    want = [c for c in ("ticker", "date", "close", "high", "volume",
                        "shares", "is_suspended", "market") if c in cols]
    raw = pd.read_sql(f"SELECT {','.join(want)} FROM daily_ohlcv", con)
    for c in ("close", "high", "volume", "shares"):
        if c in raw.columns:
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
    piv = lambda v: raw.pivot_table(index="ticker", columns="date",
                                    values=v, aggfunc="last").sort_index(axis=1)
    close = piv("close")
    high = piv("high") if "high" in raw.columns else close
    volume = piv("volume") if "volume" in raw.columns else None
    shares = piv("shares") if "shares" in raw.columns else None
    mkt = raw.groupby("ticker")["market"].last() if "market" in raw.columns else None
    return close, high.reindex(close.index), volume, shares, mkt


def factors_at(close, high, volume, shares, dates, idx):
    """앵커 idx 시점 팩터 — idx 이전(포함) 데이터만 사용(포인트-인-타임)."""
    c = close[dates[: idx + 1]]
    r = c.pct_change(axis=1, fill_method=None)
    c_now = c[dates[idx]]
    F = pd.DataFrame(index=close.index)
    w21 = r[dates[max(0, idx - 20): idx + 1]]
    n21 = w21.notna().sum(axis=1)
    F["rv21"] = w21.std(axis=1, ddof=1).where(n21 >= 8)
    F["lv63"] = r[dates[max(0, idx - 62): idx + 1]].std(axis=1, ddof=1).where(
        r[dates[max(0, idx - 62): idx + 1]].notna().sum(axis=1) >= 30)
    v5 = r[dates[max(0, idx - 4): idx + 1]].std(axis=1, ddof=1)
    F["vol_exp"] = (v5 / F["rv21"]).replace([np.inf, -np.inf], np.nan)
    F["mom_1m"] = (c_now / c[dates[max(0, idx - 22)]] - 1) * 100
    if idx >= 252:
        F["mom12"] = c[dates[idx - 21]] / c[dates[idx - 252]] - 1
    else:
        F["mom12"] = np.nan
    h252 = high[dates[max(0, idx - 251): idx + 1]].max(axis=1)
    F["nh252"] = c_now / h252 - 1
    F["drawdown"] = F["nh252"] * 100
    F["sma20"] = (c_now / c[dates[max(0, idx - 19): idx + 1]].mean(axis=1) - 1) * 100
    if volume is not None:
        amt = (close[dates[max(0, idx - 19): idx + 1]]
               * volume[dates[max(0, idx - 19): idx + 1]]).mean(axis=1) / 1e8
        F["amt20"] = amt
    if shares is not None:
        F["big"] = np.log10((c_now * shares[dates[idx]]).where(lambda x: x > 0))
    # 가드 재료
    F["_flat"] = (w21 == 0).sum(axis=1) / n21.where(n21 > 0)
    F["_jump"] = w21.abs().max(axis=1)
    return F


def apply_guards(F):
    ok = F["rv21"].notna()
    ok &= F["rv21"] >= VOL_FLOOR
    ok &= F["_flat"].fillna(1) <= MAX_FLAT_RATIO
    ok &= F["_jump"].fillna(1) <= MAX_ABS_RET
    if "amt20" in F.columns:
        ok &= F["amt20"].fillna(0) >= LIQ_FLOOR
    return ok


def fwd_return(close, dates, i0, i1):
    c = close[dates[i0: i1 + 1]]
    r = c.pct_change(axis=1, fill_method=None)
    bad = r.abs().max(axis=1) > FWD_ABS_CUT
    ret = (c[dates[i1]] / c[dates[i0]] - 1) * 100
    return ret.where(~bad)


def profile(F, winners, universe):
    """승자들의 팩터 백분위(유니버스 내) 중앙값."""
    rows = []
    for f, (_, desc) in FACTORS.items():
        if f not in F.columns:
            continue
        pct = F.loc[universe, f].rank(pct=True)
        rows.append((f, desc, F.loc[winners, f].median(),
                     F.loc[universe, f].median(), pct.reindex(winners).median()))
    return pd.DataFrame(rows, columns=["factor", "설명", "승자중앙값", "전체중앙값", "승자백분위"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60, help="기본모드: 최근 N거래일 수익")
    ap.add_argument("--topn", type=int, default=30)
    ap.add_argument("--full", action="store_true", help="전 기간 앵커 반복(승자 특성)")
    ap.add_argument("--h", type=int, default=20, help="--full 전방 거래일")
    ap.add_argument("--step", type=int, default=20)
    args = ap.parse_args()

    if not os.path.exists(OHLCV_DB):
        raise SystemExit(f"ohlcv.db 없음: {OHLCV_DB} (OHLCV_DB env로 지정 가능)")
    con = sqlite3.connect(f"file:{OHLCV_DB}?mode=ro", uri=True)
    close, high, volume, shares, mkt = load_panels(con)
    con.close()
    dates = list(close.columns)
    print(f"[데이터] {close.shape[0]}종목 × {len(dates)}거래일 ({dates[0]}~{dates[-1]})")
    print("[주의] research 탐색 산출물 — 전부 가설. 채택은 §11(40거래일 OOS)로만.\n")
    os.makedirs(RESEARCH_DIR, exist_ok=True)

    if not args.full:
        i1 = len(dates) - 1
        i0 = max(252, i1 - args.days)
        F = factors_at(close, high, volume, shares, dates, i0)
        ok = apply_guards(F)
        ret = fwd_return(close, dates, i0, i1)
        uni = F.index[ok & ret.notna()]
        print(f"[기간] {dates[i0]} → {dates[i1]} ({i1-i0}거래일) · 가드 후 {len(uni)}종목")
        top = ret.reindex(uni).sort_values(ascending=False).head(args.topn)
        out = pd.DataFrame({"ticker": top.index, "return_pct": top.values})
        if mkt is not None:
            out["market"] = out["ticker"].map(mkt)
        for f in FACTORS:
            if f in F.columns:
                out[f"{f}@앵커"] = F.loc[top.index, f].values
        med = ret.reindex(uni).median()
        print(f"[유니버스] 수익 중앙값 {med:+.1f}% · 상위{args.topn} 평균 "
              f"{top.mean():+.1f}% (n={len(uni)})")
        print(f"\n상승률 상위 {args.topn} (팩터는 앵커={dates[i0]} 시점, 포인트-인-타임)")
        print(f"{'#':>3} {'종목':8} {'수익%':>8} {'nh252':>7} {'mom12':>7} {'lv63':>7} {'낙폭%':>7} {'big':>5}")
        for i, (tk, v) in enumerate(top.items(), 1):
            g = lambda f: ("" if f not in F.columns or pd.isna(F.at[tk, f])
                           else f"{F.at[tk, f]:.3f}" if f != "drawdown" else f"{F.at[tk, f]:.1f}")
            print(f"{i:>3} {tk:8} {v:>+7.1f}  {g('nh252'):>7} {g('mom12'):>7} "
                  f"{g('lv63'):>7} {g('drawdown'):>7} {g('big'):>5}")
        prof = profile(F, top.index, uni)
        print("\n[특성] 상승 상위 종목의 앵커 시점 팩터 백분위(0.5=평범):")
        for _, r in prof.iterrows():
            print(f"  {r['factor']:9} {r['승자백분위']:.2f}  ({r['설명']})")
        p = os.path.join(RESEARCH_DIR, f"top_gainers_{dates[i0]}_{dates[i1]}.csv")
        out.to_csv(p, index=False, encoding="utf-8-sig")
        prof.to_csv(p.replace(".csv", "_profile.csv"), index=False, encoding="utf-8-sig")
        print(f"\n[저장] research/{os.path.basename(p)} (+_profile.csv)")
        print("※ 단일 앵커 = 표본 1시점. 일반화는 --full 로 확인.")
        return

    # --full: 전 기간 앵커 반복
    anchors = list(range(252, len(dates) - args.h, args.step))
    print(f"[--full] 앵커 {len(anchors)}개 (step={args.step}, h={args.h})")
    ic_rows, prof_acc = [], []
    for i0 in anchors:
        F = factors_at(close, high, volume, shares, dates, i0)
        ok = apply_guards(F)
        ret = fwd_return(close, dates, i0, i0 + args.h)
        uni = F.index[ok & ret.notna()]
        if len(uni) < 200:
            continue
        r_u = ret.reindex(uni)
        winners = r_u[r_u >= r_u.quantile(0.9)].index
        pr = profile(F, winners, uni).set_index("factor")["승자백분위"]
        prof_acc.append(pr)
        for f, (good_high, _) in FACTORS.items():
            if f not in F.columns:
                continue
            x = F.loc[uni, f]
            m = x.notna()
            if m.sum() < 100:
                continue
            ic = x[m].rank().corr(r_u[m].rank())
            ic_rows.append((dates[i0], f, ic if good_high else -ic, int(m.sum())))
    icdf = pd.DataFrame(ic_rows, columns=["date", "factor", "signed_ic", "n"])
    g = icdf.groupby("factor")["signed_ic"]
    boot = {}
    rng = np.random.default_rng(42)
    for f, s in g:
        v = s.values
        bs = [rng.choice(v, len(v), replace=True).mean() for _ in range(2000)]
        boot[f] = (np.percentile(bs, 2.5), np.percentile(bs, 97.5))
    summ = pd.DataFrame({
        "mean_signed_ic": g.mean(), "n_anchors": g.size(),
        "ci_lo": {f: b[0] for f, b in boot.items()},
        "ci_hi": {f: b[1] for f, b in boot.items()},
        "승자백분위평균": pd.concat(prof_acc, axis=1).mean(axis=1),
    }).sort_values("mean_signed_ic", ascending=False)
    print(f"\n[전 기간 h={args.h}d] 팩터별 signed IC(가설방향 × Spearman) · 승자(상위10%) 백분위")
    print(f"{'factor':10} {'IC':>7} {'95%CI':>18} {'n':>4} {'승자pct':>7}")
    for f, r in summ.iterrows():
        print(f"{f:10} {r['mean_signed_ic']:+.3f} [{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}]"
              f" {int(r['n_anchors']):>4} {r['승자백분위평균']:>7.2f}")
    p = os.path.join(RESEARCH_DIR, f"top_gainers_full_h{args.h}.csv")
    summ.to_csv(p, encoding="utf-8-sig")
    print(f"\n[저장] research/{os.path.basename(p)}")
    print("※ 앵커 중첩(step<h면 유효 n<표기). in-sample 가설 — 채택 근거 아님.")


if __name__ == "__main__":
    main()
