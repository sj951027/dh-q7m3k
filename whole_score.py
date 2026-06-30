"""
whole_score.py — lv 계열 전 모델을 '전체 종목(whole-universe)' 에 적용 (탐색 전용)
==============================================================================
lowvol_score.py 는 lv_a~d 등을 '과매도 선별(stage3) 340종목' 안에서만 점수냄.
이 스크립트는 '같은 모델·같은 점수식'을 'ohlcv 전체 2600+종목' 모집단에 적용한다.
→ "전체 종목에서 lv 계열 점수가 어떻게 나오나"를 본다.

lowvol_score 와의 관계(정확히 일치시킴):
  * 점수식: cross_sectional_pct_rank_sum_v1 (동일). 핵심팩터(factors[0]) 실측필수,
    보조(2번째~) NaN 은 0.5 중립 — lowvol_score.score_run 과 같은 규칙.
  * 팩터 방향: lowvol_score.FACTORS 와 동일(저변동 False, ROE True, drawdown True 등).
  * 모델: lv_a/lv_b/lv_c/lv_d (+ hv_a/lv_short/mom_a). 유니버스만 '전체'로 교체
    (과매도 30~70 범위 제거 — 전체 종목이 대상).

재료(가격은 ohlcv 에서 직접 계산, lowvol 은 stage3 에서 받던 것):
  realized_vol = trailing WINDOW 거래일 종가수익률 std       (observe_vol 정의)
  reversal     = return_1w = 5거래일 수익률 (작을수록=패자=가점)
  drawdown     = (price/52주최고 -1)x100  (큰 낙폭=가점, 스크리너 식)
  sma20        = (price/SMA20 -1)x100      (모멘텀)
  mom_1m       = 22거래일 수익률
  vol_exp      = std(5일)/std(21일)         (스크리너 vol_1w_vs_1m_ratio)
  highvol      = realized_vol 의 반대방향
  roe          = valuation EPS/BPS x100
  short        = ohlcv.short_flows short_vol_ratio (보조, 낮을수록 좋음)

데이터 가드(전체 모집단 전용 — stage3 엔 없던 raw 쓰레기 제거):
  거래정지(가격고정)·가격점프(액면병합/유증/신규상장)·변동성하한 컷.

안전(기존 트랙 불간섭):
  * ohlcv.db READONLY, valuation CSV 읽기. 점수테이블·docs·telegram 안 씀.
  * 출력 = research/whole_score_{date}.csv 하나(롱포맷: ticker x model). 14절 탐색=게이트 면제.
  * 네트워크 0.

사용:
    python whole_score.py --date 20260630
    python whole_score.py --date 20260630 --models lv_a,lv_b,lv_c,lv_d
    python whole_score.py --date 20260630 --topn 20 --show lv_a

[주의] 탐색 산출물. 채택은 11절(40거래일 OOS·h20 IC·부트스트랩 CI) 후에만. 경계값='기움'.
"""
import argparse
import os
import sqlite3

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OHLCV_DB = os.environ.get(
    "OHLCV_DB", os.path.join(HERE, "..", "dh-q7m3k-data", "ohlcv.db"))
RESEARCH_DIR = os.path.join(HERE, "research")

# 동결 파라미터(lowvol_score / observe_vol 표준과 정렬)
WINDOW = 21             # realized_vol·vol_exp(21일)·drawdown 룩백 거래일.
MIN_OBS = 8            # 변동성 최소 관측. 미만이면 NaN(핵심팩터 결손=제외).
REV_DAYS = 5           # 반전(return_1w) 거래일.
DD_LOOKBACK = 252      # 52주 최고가 룩백 거래일.
LIQ_FLOOR = 5.0        # 유동성 하한(억).

# 데이터 품질 가드(전체 모집단 전용)
VOL_FLOOR = 0.003       # 변동성 하한(가짜 저변동=거래정지 컷).
MAX_FLAT_RATIO = 0.5    # 무변화일 비율 상한(거래정지 컷).
MAX_ABS_RET = 0.30      # 일중 |수익률| 상한(가격점프 컷).

# 팩터 방향(lowvol_score.FACTORS 와 동일; True=큰값이 높은 백분위)
FACTOR_DIR = {
    "realized_vol": False,   # 저변동 우대
    "highvol":      True,    # 고변동 우대(realized_vol 반대)
    "roe_value":    True,    # 고ROE 우대
    "reversal":     False,   # 패자(많이 빠짐) 우대
    "drawdown":     True,    # 큰 낙폭 우대(원시 IC +0.129)
    "sma20":        True,    # 20일선 위 우대(모멘텀)
    "mom_1m":       True,    # 1개월 모멘텀 우대
    "vol_exp":      True,    # 변동성 팽창 우대
    "short":        False,   # 공매도 적을수록 우대
}

# 모델 정의(lowvol_score.MODELS 의 factors 그대로; 유니버스는 '전체')
ALL_MODELS = {
    "lv_a":     ["realized_vol", "roe_value", "reversal"],
    "lv_b":     ["realized_vol", "roe_value"],
    "lv_c":     ["drawdown", "roe_value", "reversal"],
    "lv_d":     ["drawdown", "roe_value"],
    "hv_a":     ["highvol", "roe_value", "reversal"],
    "lv_short": ["realized_vol", "roe_value", "reversal", "short"],
    "mom_a":    ["sma20", "mom_1m", "vol_exp"],
}
DEFAULT_MODELS = ["lv_a", "lv_b", "lv_c", "lv_d"]


def pct_rank(series, ascending):
    return series.rank(pct=True, ascending=ascending)


def score_frame(df, factors):
    """lowvol_score.score_run 과 동일: 핵심팩터 실측필수, 보조 NaN 은 0.5 중립."""
    total = None
    core_mask = None
    for i, fname in enumerate(factors):
        r = pct_rank(df[fname], FACTOR_DIR[fname])
        if i == 0:
            core_mask = r.notna()
            filled = r
        else:
            filled = r.fillna(0.5)
        total = filled if total is None else total + filled
    return total.where(core_mask)


def load_price_panel(con, as_of):
    """ohlcv.daily_ohlcv -> ticker x date 종가/고가 패널. as_of 까지만."""
    cols = [r[1] for r in con.execute("PRAGMA table_info(daily_ohlcv)")]
    high_col = "high" if "high" in cols else None
    sel = "ticker, date, close" + (", high" if high_col else "")
    raw = pd.read_sql(
        f"SELECT {sel} FROM daily_ohlcv WHERE date <= ?", con, params=(as_of,))
    if raw.empty:
        return pd.DataFrame(), pd.DataFrame()
    raw["close"] = pd.to_numeric(raw["close"], errors="coerce")
    close = raw.pivot_table(index="ticker", columns="date", values="close", aggfunc="last")
    close = close.reindex(sorted(close.columns), axis=1)
    if high_col:
        raw["high"] = pd.to_numeric(raw["high"], errors="coerce")
        high = raw.pivot_table(index="ticker", columns="date", values="high", aggfunc="last")
        high = high.reindex(sorted(high.columns), axis=1)
    else:
        high = close
    return close, high


def compute_price_factors(close, high, as_of):
    """기준일 시점의 전 가격팩터 + 데이터가드 신호."""
    if close.empty:
        return pd.DataFrame()
    dates = list(close.columns)
    if as_of not in dates:
        prior = [d for d in dates if d <= as_of]
        if not prior:
            return pd.DataFrame()
        as_of = prior[-1]
    idx = dates.index(as_of)
    c_now = close[dates[idx]]
    rets_all = close.pct_change(axis=1, fill_method=None)

    lo = max(0, idx - WINDOW + 1)
    win = rets_all[dates[lo: idx + 1]]
    n = win.notna().sum(axis=1)
    vol = win.std(axis=1, ddof=1).where(n >= MIN_OBS)

    lo5 = max(0, idx - 5 + 1)
    v5 = rets_all[dates[lo5: idx + 1]].std(axis=1, ddof=1)
    vol_exp = (v5 / vol).replace([np.inf, -np.inf], np.nan)

    j = max(0, idx - REV_DAYS)
    reversal = (c_now / close[dates[j]] - 1.0) * 100.0

    k = max(0, idx - 22)
    mom_1m = (c_now / close[dates[k]] - 1.0) * 100.0

    dlo = max(0, idx - DD_LOOKBACK + 1)
    high_52 = high[dates[dlo: idx + 1]].max(axis=1)
    drawdown = (c_now / high_52 - 1.0) * 100.0

    slo = max(0, idx - 20 + 1)
    sma20_val = close[dates[slo: idx + 1]].mean(axis=1)
    sma20 = (c_now / sma20_val - 1.0) * 100.0

    flat = (win == 0).sum(axis=1)
    flat_ratio = flat / n.where(n > 0)
    max_abs = win.abs().max(axis=1)

    return pd.DataFrame({
        "ticker": close.index,
        "realized_vol": vol.values,
        "highvol": vol.values,
        "reversal": reversal.values,
        "drawdown": drawdown.values,
        "sma20": sma20.values,
        "mom_1m": mom_1m.values,
        "vol_exp": vol_exp.values,
        "flat_ratio": flat_ratio.values,
        "max_abs_ret": max_abs.values,
        "return_1m": mom_1m.values,
    })


def compute_liquidity(con, as_of, lookback=20):
    cols = [r[1] for r in con.execute("PRAGMA table_info(daily_ohlcv)")]
    if "volume" not in cols:
        return pd.Series(dtype=float)
    raw = pd.read_sql(
        "SELECT ticker, date, close, volume FROM daily_ohlcv WHERE date <= ? ORDER BY date",
        con, params=(as_of,))
    if raw.empty:
        return pd.Series(dtype=float)
    raw["amt"] = (pd.to_numeric(raw["close"], errors="coerce")
                  * pd.to_numeric(raw["volume"], errors="coerce")) / 1e8
    return raw.groupby("ticker").apply(
        lambda g: g.sort_values("date")["amt"].tail(lookback).mean())


def load_valuation(as_of):
    frames, mkt_map = [], {}
    for mkt in ("kospi", "kosdaq"):
        p = os.path.join(HERE, f"valuation_{mkt}_{as_of}.csv")
        if not os.path.exists(p):
            print(f"   [경고] {os.path.basename(p)} 없음 - {mkt} ROE 결손(보조 0.5 중립).")
            continue
        v = pd.read_csv(p, dtype={"ticker": str})
        for c in ("EPS", "BPS"):
            v[c] = pd.to_numeric(v[c], errors="coerce")
        v["roe_value"] = np.where(
            (v["BPS"] > 0) & (v["EPS"] != 0), v["EPS"] / v["BPS"] * 100.0, np.nan)
        for tk in v["ticker"]:
            mkt_map.setdefault(tk, mkt)
        frames.append(v[["ticker", "roe_value"]])
    if not frames:
        return pd.DataFrame(columns=["ticker", "roe_value"]), {}
    out = pd.concat(frames, ignore_index=True)
    if out["ticker"].duplicated().any():
        out = out.drop_duplicates(subset="ticker", keep="first")
    return out[["ticker", "roe_value"]], mkt_map


def load_short(con, as_of):
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(short_flows)")]
    except Exception:
        return pd.Series(dtype=float)
    if "short_vol_ratio" not in cols:
        return pd.Series(dtype=float)
    raw = pd.read_sql(
        "SELECT ticker, date, short_vol_ratio FROM short_flows WHERE date <= ? ORDER BY date",
        con, params=(as_of,))
    if raw.empty:
        return pd.Series(dtype=float)
    raw["short_vol_ratio"] = pd.to_numeric(raw["short_vol_ratio"], errors="coerce")
    return raw.groupby("ticker")["short_vol_ratio"].last()


def main():
    ap = argparse.ArgumentParser(description="lv 계열 전 모델 - 전체 종목 점수(탐색)")
    ap.add_argument("--date", required=True, help="기준일 YYYYMMDD (point-in-time)")
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS),
                    help=f"콤마구분. 사용가능: {','.join(ALL_MODELS)} (기본 lv_a~d)")
    ap.add_argument("--liq-floor", type=float, default=LIQ_FLOOR)
    ap.add_argument("--topn", type=int, default=20)
    ap.add_argument("--show", default=None, help="콘솔 상위 N 보여줄 모델(기본 첫 모델)")
    args = ap.parse_args()
    as_of = args.date
    models = [m.strip() for m in args.models.split(",") if m.strip() in ALL_MODELS]
    if not models:
        raise SystemExit(f"유효 모델 없음. 사용가능: {','.join(ALL_MODELS)}")
    if not os.path.exists(OHLCV_DB):
        raise SystemExit(f"ohlcv.db 없음: {OHLCV_DB}")

    print("=" * 64)
    print(f"전체 종목 lv 계열 점수(탐색) - 기준일 {as_of}")
    print(f"  모델: {models}")
    print(f"  [주의] research 산출물(게이트 면제). 채택 아님 - 11절 통과 후에만 판정.")
    print("=" * 64)

    con = sqlite3.connect(f"file:{OHLCV_DB}?mode=ro", uri=True)

    close, high = load_price_panel(con, as_of)
    if close.empty:
        raise SystemExit(f"{as_of} 까지 ohlcv 가격 없음.")
    print(f"   - 가격 패널: {close.shape[0]}종목 x {close.shape[1]}거래일(<={as_of})")
    pf = compute_price_factors(close, high, as_of)
    pf = pf.dropna(subset=["realized_vol"]).copy()
    n_raw = len(pf)

    g_flat = pf["flat_ratio"] > MAX_FLAT_RATIO
    g_jump = pf["max_abs_ret"] > MAX_ABS_RET
    g_floor = pf["realized_vol"] < VOL_FLOOR
    drop = g_flat | g_jump | g_floor
    if drop.any():
        print(f"   - 데이터 가드: 거래정지 {int(g_flat.sum())} · 점프 {int(g_jump.sum())} · "
              f"변동성하한 {int(g_floor.sum())} -> {int(drop.sum())}종목 제외")
        pf = pf[~drop].copy()
    pf = pf.drop(columns=["flat_ratio", "max_abs_ret"])
    print(f"   - 가격팩터 유효(가드 후): {len(pf)}/{n_raw}종목")

    val, mkt_map = load_valuation(as_of)
    df = pf.merge(val, on="ticker", how="left")
    df["market"] = df["ticker"].map(mkt_map)
    roe_cov = df["roe_value"].notna().sum()
    print(f"   - ROE 조인: {roe_cov}/{len(df)}종목 (결손은 보조 0.5 중립)")

    liq = compute_liquidity(con, as_of)
    if not liq.empty:
        df = df.merge(liq.rename("amt_avg_1m_억"), left_on="ticker", right_index=True, how="left")
        before = len(df)
        df = df[(df["amt_avg_1m_억"].isna()) | (df["amt_avg_1m_억"] >= args.liq_floor)].copy()
        print(f"   - 유동성 컷(>={args.liq_floor}억): {before}->{len(df)}종목")
    else:
        df["amt_avg_1m_억"] = np.nan

    if any("short" in ALL_MODELS[m] for m in models):
        sh = load_short(con, as_of)
        if not sh.empty:
            df = df.merge(sh.rename("short"), left_on="ticker", right_index=True, how="left")
            print(f"   - 공매도 조인: {df['short'].notna().sum()}/{len(df)}종목")
        else:
            df["short"] = np.nan
            print("   - short_flows 없음 - lv_short 의 공매도는 0.5 중립")
    con.close()

    long_rows, summary = [], []
    for m in models:
        s = score_frame(df, ALL_MODELS[m])
        sub = df.copy()
        sub["model_id"] = m
        sub["whole_score"] = s
        sub = sub.dropna(subset=["whole_score"]).copy()
        sub = sub.sort_values("whole_score", ascending=False).reset_index(drop=True)
        sub["rank"] = sub.index + 1
        sub["n_universe"] = len(sub)
        long_rows.append(sub)
        summary.append((m, len(sub)))

    out_df = pd.concat(long_rows, ignore_index=True)
    out_df["as_of"] = as_of

    os.makedirs(RESEARCH_DIR, exist_ok=True)
    outp = os.path.join(RESEARCH_DIR, f"whole_score_{as_of}.csv")
    keep = ["model_id", "rank", "ticker", "market", "whole_score",
            "realized_vol", "roe_value", "reversal", "drawdown", "sma20",
            "mom_1m", "vol_exp", "return_1m", "amt_avg_1m_억", "n_universe", "as_of"]
    if "short" in out_df.columns:
        keep.insert(12, "short")
    out_df[keep].to_csv(outp, index=False, encoding="utf-8-sig")
    print(f"\n[저장] research/{os.path.basename(outp)} - {len(out_df)}행 "
          f"({len(models)}모델 x 종목, 롱포맷)")
    print("   모델별 종목수:", ", ".join(f"{m}={n}" for m, n in summary))

    show_m = args.show if args.show in ALL_MODELS else models[0]
    sm = out_df[out_df.model_id == show_m].sort_values("rank").head(args.topn)
    print(f"\n{'='*64}\n[{show_m}] 상위 {args.topn}\n{'='*64}")
    print(f"{'#':>3} {'종목':8} {'시장':7} {'점수':>6} {'변동성':>8} {'ROE':>6} {'반전%':>7} {'낙폭%':>7} {'1M%':>7}")
    for _, r in sm.iterrows():
        roe = "" if pd.isna(r["roe_value"]) else f"{r['roe_value']:.1f}"
        print(f"{int(r['rank']):>3} {str(r['ticker']):8} {str(r['market']):7} "
              f"{r['whole_score']:.3f}  {r['realized_vol']:.4f}  {roe:>5}  "
              f"{r['reversal']:>6.1f}  {r['drawdown']:>6.1f}  {r['return_1m']:>6.1f}")

    full = out_df[out_df.model_id == show_m].sort_values("rank")
    if len(full) >= 20:
        t10 = full.head(10)["realized_vol"].mean()
        b10 = full.tail(10)["realized_vol"].mean()
        ok = "OK" if t10 < b10 else "역전(고변동/낙폭 모델이면 정상)"
        print(f"\n[sanity {show_m}] 변동성 상위10 {t10:.4f} vs 하위10 {b10:.4f}  {ok}")
    print("\n다음: forward 쌓이면 모델별 IC 비교(lv_a vs lv_b vs lv_c vs lv_d).")
    print("      과매도 lv_a(lowvol_score) 대비 전체 모집단판이 나은지가 핵심.")


if __name__ == "__main__":
    main()
