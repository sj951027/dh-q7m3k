# -*- coding: utf-8 -*-
"""
v30_history.py — v30 점수를 과거 날짜마다 "그때 알 수 있었던 자료"로 다시 계산 (2026-10-03, 관측·읽기 전용)

입력: 3년 가격 패널(research/fullscan_20260903/panel.npz) · DART 과거 재무(research/dart_history/dart_hist.db, 접수일로 PIT)
      · 공시 이벤트(ohlcv.db dart_events, 2023-06~) · 업종(sector_cache.json). 점수식은 v3_rescore.rescore(SPEC_V30) 그대로 호출.
재현 못 하는 것(정직하게):
  · 수급(외인·기관 5일): KIS 자료가 2026-04-28~ 라 **0 으로 둠** → supply_score_v2 = 0 (실제는 −10~+15)
  · 배당수익률 DIV: 안 모음 → 0 (value_score 의 +3 항 빠짐)
  · PBR·PER: KRX 값 대신 DART 연간 자본·순이익 ÷ (가격×현재 주식수) 근사 (주식수는 PIT 아님)
  · 위험등급(2단계): 공시 전체가 아니라 dart_events(유상증자·CB·BW·EB·감자) 만 → '주의'까지만, '위험' 없음
  · 2단계 입력 컷(composite ≥ 30): acc·수급·레짐 점수 없이 과매도+추세 만으로 근사
검증: --validate 는 2026-06-05~ 실제 적재(stage3_final·v3_scores)와 지표별 일치율·점수 차이를 적는다(수급은 실제 값을 끼워 비교).
출력: research/dart_history/v30_hist_scores.parquet(날짜·시장·종목·점수) · validate.md
"""
import json, sqlite3, sys, bisect, warnings
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "research" / "fullscan_20260903"))
import stage3_fundamental_momentum_v2_6 as S3        # noqa: E402  계정 매칭·YoY·패턴 함수 재사용(네트워크 없음)
import v3_rescore as V3                              # noqa: E402  점수식 그대로
import screener_fdr_v2_6 as S1                       # noqa: E402  금융 제외 키워드·과매도 식
from fslib import Panel                              # noqa: E402

DB = HERE / "dart_hist.db"; OUT = HERE / "v30_hist_scores.parquet"
MIN_SCORE = {"kospi": 50, "kosdaq": 45}


# ----------------------------------------------------------------- DART PIT
def load_reports():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute("SELECT stock_code, year, reprt, api, fs, status, rcept_no, items FROM reports WHERE status='000' AND kept>0").fetchall(); con.close()
    rep = {}
    for stock, year, reprt, api, fs, st, rc, items in rows:
        r = dict(year=int(year), reprt=reprt, api=api, fs=fs, rcept=(rc or "")[:8], items=json.loads(items)); r["avail"] = avail_date(r)
        rep.setdefault(stock, []).append(r)
    return rep


PIT_STRICT = False
DEADLINE = {"Q1": "0515", "H1": "0814", "Q3": "1114", "Y": "0331"}   # 법정 제출 마감(분기 45일·사업보고서 90일)


def avail_date(r):
    """보고서를 '그 날짜에 알 수 있었나'의 기준일. DART 는 정정 보고서가 있으면 정정 접수번호를 주므로(원본 접수일 소실)
    접수일이 마감일+10일보다 늦으면 마감일+10일로 본다(지연 제출·정정은 마감 직후 원본이 있었다고 가정 — 근사)."""
    y = r["year"] + (1 if r["reprt"] == "Y" else 0)
    dl = (datetime.strptime(f"{y}{DEADLINE[r['reprt']]}", "%Y%m%d") + pd.Timedelta(days=10)).strftime("%Y%m%d")
    rc = r["rcept"] or dl
    if PIT_STRICT: return rc            # [REPLY_007 §3] 엄격: 저장된(정정본) 접수일만 — 소급 없음(정정본 숫자를 과거에 쓰지 않음)
    return min(rc, dl)


def _find(reps, year, reprt, api, fs, d):
    for r in reps:
        if r["year"] == year and r["reprt"] == reprt and r["api"] == api and (fs is None or r["fs"] == fs) and r.get("avail", "99999999") <= d:
            return r
    return None


def annual_at(reps, d):
    """stage3.get_annual_metrics 와 같은 순서(올해-1, 올해-2 · CFS→OFS), 단 접수일 ≤ d 인 보고서만."""
    y = int(d[:4])
    for year in (y - 1, y - 2):
        for fs in ("CFS", "OFS"):
            r = _find(reps, year, "Y", "ALL", fs, d)
            if not r: continue
            op = S3.find_operating_profit(r["items"])
            if not op: continue
            lo, po = S3.parse_amount(op.get("thstrm_amount")), S3.parse_amount(op.get("frmtrm_amount"))
            ocf = S3.find_operating_cash_flow(r["items"])
            eq = next((it for it in r["items"] if "EquityAttributableToOwnersOfParent" in (it.get("account_id") or "")), None) or \
                 next((it for it in r["items"] if (it.get("account_id") or "") == "ifrs-full_Equity"), None)
            ni = next((it for it in r["items"] if "ProfitLossAttributableToOwnersOfParent" in (it.get("account_id") or "")), None) or \
                 next((it for it in r["items"] if (it.get("account_id") or "") == "ifrs-full_ProfitLoss" and it.get("sj_div") in ("IS", "CIS")), None)
            return dict(annual_yoy=S3.calculate_yoy(lo, po), annual_latest_억=S3.amount_to_억(lo),
                        ocf_latest_억=S3.amount_to_억(S3.parse_amount(ocf.get("thstrm_amount"))) if ocf else None,
                        equity=S3.parse_amount(eq.get("thstrm_amount")) if eq else None, net_income=S3.parse_amount(ni.get("thstrm_amount")) if ni else None)
    return None


def quarterly_at(reps, d):
    attempts = S3.build_quarterly_attempts(today=datetime.strptime(d, "%Y%m%d"))
    for year, period in attempts:
        for fs in ("CFS", "OFS"):
            r = _find(reps, year, period, "ALL", fs, d)
            if not r: continue
            op = S3.find_operating_profit(r["items"])
            if not op: continue
            if op.get("frmtrm_q_amount") is None:   # 저장 안 된 '전년 동기 3개월' = 전년 같은 분기 보고서의 당기 3개월(thstrm_amount)
                rp = _find(reps, year - 1, period, "ALL", fs, d)
                opp = S3.find_operating_profit(rp["items"]) if rp else None
                if opp and opp.get("thstrm_amount") is not None: op = dict(op, frmtrm_q_amount=opp["thstrm_amount"])
            res = S3._quarterly_from_op(op, year, period, fs, "fnlttSinglAcntAll")
            if res: return res
        r = _find(reps, year, period, "SINGLE", None, d)
        if r:
            for fs in ("CFS", "OFS"):
                items = S3.filter_items_by_fs(r["items"], fs)
                op = S3.find_operating_profit(items) if items else None
                if not op: continue
                res = S3._quarterly_from_op(op, year, period, fs, "fnlttSinglAcnt")
                if res: return res
    return None


# ----------------------------------------------------------------- 가격 지표(1단계 식 그대로, 벡터)
def indicators(P):
    c = P.close.astype(np.float64); o = P.open.astype(np.float64); h = P.high.astype(np.float64); l = P.low.astype(np.float64); v = P.vol.astype(np.float64)
    C = pd.DataFrame(c); O = pd.DataFrame(o); Hh = pd.DataFrame(h); L = pd.DataFrame(l); Vv = pd.DataFrame(v)
    d = C.diff(); gain = d.where(d > 0, 0).rolling(14).mean(); loss = (-d.where(d < 0, 0)).rolling(14).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    mid = C.rolling(20).mean(); sd = C.rolling(20).std(); bbu, bbl = mid + 2 * sd, mid - 2 * sd
    bbr = (bbu - bbl); bbp = ((C - bbl) / bbr * 100).where(bbr > 0, 50)
    sto = 100 * (C - L.rolling(14).min()) / (Hh.rolling(14).max() - L.rolling(14).min()).replace(0, np.nan)
    hi52 = Hh.rolling(252, min_periods=1).max(); dd = (C - hi52) / hi52 * 100
    r1w = (C / C.shift(5) - 1) * 100; r1m = (C / C.shift(21) - 1) * 100
    volma = Vv.rolling(20).mean(); vva = (Vv / volma).where(volma > 0)
    sma5 = C.rolling(5).mean(); sma20 = C.rolling(20).mean(); sma50 = C.rolling(50).mean()
    low5 = L.rolling(5).min(); prev5low = L.shift(5).rolling(5).min()
    bull = (C > O).astype(float); bull5 = bull.rolling(5).sum()
    vprev5 = Vv.shift(1).rolling(5).mean()
    above5 = (C >= sma5); rebound = (prev5low > 0) & (C >= prev5low * 1.03); volcandle = (C > O) & (vprev5 > 0) & (Vv > vprev5 * 1.2)
    fk = (C <= low5 * 1.01) & (sma5 < sma20) & (bull5 == 0)
    amt21 = (Vv * C).rolling(21).mean() / 1e8; vol5sum = Vv.rolling(5).sum()
    nbars = C.notna().astype(float).rolling(260, min_periods=1).sum()
    # 과매도 점수(1단계 식)
    os_ = (50 - rsi).clip(0, None).mul(1.5).clip(upper=30).fillna(0) + (50 - bbp).clip(0, None).mul(0.4).clip(upper=20).fillna(0) \
        + dd.abs().mul(0.4).clip(upper=20).fillna(0) + r1m.where(r1m < 0, 0).abs().mul(0.5).clip(upper=15).fillna(0) \
        + (vva - 1).where(vva > 1, 0).mul(5).clip(upper=10).fillna(0) + (30 - sto).clip(0, None).mul(0.25).clip(upper=5).fillna(0)
    trend = above5.astype(float) * 3 + rebound.astype(float) * 3 + volcandle.astype(float) * 4; trend = trend.where(~fk, -30)
    return dict(price=C, rsi=rsi, bbp=bbp, sto=sto, dd=dd, r1w=r1w, r1m=r1m, vva=vva, sma20=sma20, sma50=sma50, above5=above5, rebound=rebound, volcandle=volcandle,
                fk=fk, amt21=amt21, vol5sum=vol5sum, nbars=nbars, oversold=os_.round(1), trend=trend)


def value_score_df(df):
    """v3_rescore.attach_valuation 의 점수 부분 그대로(PBR·PER·DIV 열 사용)."""
    pbr = V3._num(df["PBR"]); per = V3._num(df["PER"]); div = V3._num(df["DIV"]).fillna(0)
    df["_pbr"] = pbr; df["_per"] = per
    def robust_pct(col, ascending=True, min_n=5):
        sec_rank = df.groupby("sector")[col].rank(pct=True, ascending=ascending); mkt_rank = df[col].rank(pct=True, ascending=ascending)
        grp_n = df.groupby("sector")[col].transform("count"); use = (df["sector"] != "미분류") & (grp_n >= min_n)
        return sec_rank.where(use, mkt_rank)
    s = pd.Series(0.0, index=df.index)
    s += ((pbr > 0) & (pbr < 1.0)).astype(int) * 6
    s += (robust_pct("_pbr", True) <= 0.30).fillna(False).astype(int) * 6
    s += ((per > 0) & (robust_pct("_per", True) <= 0.40)).fillna(False).astype(int) * 5
    s += (div > 2).astype(int) * 3
    s += (per <= 0).astype(int) * (-5)
    df["value_score"] = s.clip(-10, 25); df["value_source"] = "PYKRX"
    return df.drop(columns=["_pbr", "_per"])


def main(validate=False, start="20240102", step=1):
    P = Panel(); dates = list(P.dates); tick = list(P.tick); mk = pd.Series(P.mk).str.lower().values
    I = indicators(P)
    reps = load_reports()
    names = {}
    try:
        cc = pd.read_csv(REPO / "dart_cache" / "corp_code.csv", dtype=str, encoding="utf-8-sig").dropna(subset=["stock_code"])
        names = dict(zip(cc.stock_code.str.zfill(6), cc.corp_name))
    except Exception: pass
    sector = json.load(open(REPO / "sector_cache.json", encoding="utf-8")) if (REPO / "sector_cache.json").exists() else {}
    oc = sqlite3.connect(f"file:{REPO.parent/'dh-q7m3k-data'/'ohlcv.db'}?mode=ro", uri=True)
    ev = pd.read_sql("SELECT ticker, rcept_dt, event_type FROM dart_events WHERE event_type IN ('paid_in','cb','bw','eb','reduction','paid_bonus_mix')", oc); oc.close()
    ev["ticker"] = ev.ticker.astype(str).str.zfill(6); ev_by = {t: sorted(g.rcept_dt.tolist()) for t, g in ev.groupby("ticker")}
    fin_exclude = np.array([S1.is_financial_or_reit(t, names.get(t, ""), exclude_spac=(m == "kosdaq")) for t, m in zip(tick, mk)])
    shares = P.shares.astype(np.float64)
    V3.attach_valuation = lambda df, run_id, market: value_score_df(df)   # 밸류 csv 대신 열에서
    hist_runs = set()
    if validate:
        con = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
        hist_runs = {r[0] for r in con.execute("SELECT DISTINCT run_id FROM v3_scores WHERE model_id='v30' AND run_id>='20260605'")}; con.close()
        run_dates = [d for d in dates if d in hist_runs]
    else:
        run_dates = [d for i, d in enumerate(dates) if d >= start and i % step == 0]
    out = []
    t0 = datetime.now()
    for di, d in enumerate(run_dates):
        ti = dates.index(d)
        for market in ("kospi", "kosdaq"):
            cols = np.where((mk == market) & ~fin_exclude)[0]
            rows = []
            for j in cols:
                px = I["price"].iat[ti, j]
                if not np.isfinite(px) or px < 1000 or I["nbars"].iat[ti, j] < 50 or not (I["vol5sum"].iat[ti, j] > 0): continue
                osc = I["oversold"].iat[ti, j]
                if osc + I["trend"].iat[ti, j] < 30: continue   # 2단계 입력 컷 근사
                t = tick[j]; rp = reps.get(t, [])
                a = annual_at(rp, d) if rp else None; q = quarterly_at(rp, d) if rp else None
                ay = a["annual_yoy"] if a else None; qy = q["quarterly_yoy_%"] if q else None
                pat, _ = S3.classify_pattern(ay, qy)
                _, opat, ratio, _ = S3.calculate_ocf_score(a["annual_latest_억"] if a else None, a["ocf_latest_억"] if a else None, sector.get(t))
                mcap = px * shares[ti, j] if np.isfinite(shares[ti, j]) else np.nan
                pbr = mcap / a["equity"] if (a and a.get("equity") and a["equity"] > 0 and np.isfinite(mcap)) else np.nan
                per = (mcap / a["net_income"]) if (a and a.get("net_income") not in (None, 0) and np.isfinite(mcap)) else np.nan
                evs = ev_by.get(t, []); lo = bisect.bisect_left(evs, (datetime.strptime(d, "%Y%m%d") - pd.Timedelta(days=365)).strftime("%Y%m%d")); hi = bisect.bisect_right(evs, d)
                risk = "주의" if hi - lo > 0 else "안전"
                rows.append(dict(run_id=d, market=market, ticker=t, sector=sector.get(t) or "미분류", price=px, RSI=I["rsi"].iat[ti, j], oversold_score=osc,
                                 **{"return_1w_%": I["r1w"].iat[ti, j], "return_1m_%": I["r1m"].iat[ti, j], "drawdown_52w_high_%": I["dd"].iat[ti, j],
                                    "vs_SMA20_%": (px / I["sma20"].iat[ti, j] - 1) * 100, "vs_SMA50_%": (px / I["sma50"].iat[ti, j] - 1) * 100,
                                    "amt_avg_1m_억": I["amt21"].iat[ti, j], "foreign_5d_억": 0.0, "inst_5d_억": 0.0,
                                    "annual_yoy_%": ay, "quarterly_yoy_%": qy, "ocf_latest_억": a["ocf_latest_억"] if a else None, "ocf_to_op_ratio": ratio},
                                 reversal_above_sma5=bool(I["above5"].iat[ti, j]), reversal_rebound_3pct=bool(I["rebound"].iat[ti, j]), reversal_vol_up_candle=bool(I["volcandle"].iat[ti, j]),
                                 falling_knife=bool(I["fk"].iat[ti, j]), risk_level=risk, earnings_pattern=pat, ocf_pattern=opat, PBR=pbr, PER=per, DIV=0.0, vol_1w_vs_1m_ratio=np.nan))
            if len(rows) < 5: continue
            df = pd.DataFrame(rows)
            sc = V3.rescore(df, run_id=d, market=market)
            out.append(sc[["run_id", "market", "ticker", "final_score_v3", "grade", "bucket", "value_score", "quality_score", "turnaround_score", "reversal_score", "supply_score_v2", "oversold_component",
                           "oversold_score", "RSI", "return_1m_%", "annual_yoy_%", "quarterly_yoy_%", "earnings_pattern", "ocf_pattern", "ocf_to_op_ratio", "risk_level", "PBR", "PER", "main_candidate", "foreign_5d_억", "inst_5d_억", "amt_avg_1m_억"]])
        if (di + 1) % 20 == 0: print(f"  {di+1}/{len(run_dates)} {d} · {(datetime.now()-t0).total_seconds()/60:.1f}분", flush=True)
    res = pd.concat(out, ignore_index=True)
    res.to_parquet(OUT if not validate else HERE / "v30_hist_validate.parquet", index=False)
    print(f"저장 {len(res)}행 · 날짜 {res.run_id.nunique()}")
    if validate: do_validate(res)


def do_validate(res):
    con = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
    s3 = pd.read_sql("SELECT run_id, market, ticker, RSI, oversold_score, [return_1m_%] AS r1m, [annual_yoy_%] AS ay, [quarterly_yoy_%] AS qy, earnings_pattern, ocf_pattern, ocf_to_op_ratio, risk_level, [foreign_5d_억] AS f5, [inst_5d_억] AS i5, [amt_avg_1m_억] AS amt FROM stage3_final WHERE run_id>='20260605'", con)
    v3 = pd.read_sql("SELECT run_id, market, ticker, final_score_v3 FROM v3_scores WHERE model_id='v30' AND run_id>='20260605'", con); con.close()
    for df in (s3, v3): df["ticker"] = df.ticker.astype(str).str.zfill(6); df["market"] = df.market.str.lower(); df["run_id"] = df.run_id.astype(str)
    m = res.merge(s3, on=["run_id", "market", "ticker"], how="inner", suffixes=("", "_act"))
    lines = [f"# v30 재계산 검증 (2026-06-05~, 실제 적재 대조) — {datetime.now():%Y-%m-%d %H:%M}", "",
             f"- 겹친 (날짜·종목) {len(m):,} / 재계산 {len(res):,} / 실제 stage3 {len(s3):,} — 유니버스 일치율(재계산 중 실제에도 있음) {len(m)/max(len(res),1):.0%}, (실제 중 재계산에도 있음) {len(m)/max(len(s3),1):.0%}", ""]
    def agree(a, b, tol): x = (m[a] - m[b]).abs(); return f"{(x <= tol).mean():.0%} (중앙 오차 {x.median():.2f})"
    lines += ["| 지표 | 일치(허용 오차) |", "|---|---|",
              f"| RSI | {agree('RSI','RSI_act',0.6)} |", f"| 과매도 점수 | {agree('oversold_score','oversold_score_act',1.0)} |", f"| 1개월 수익 | {agree('return_1m_%','r1m',0.2)} |",
              f"| 연간 YoY | {agree('annual_yoy_%','ay',0.5)} (둘 다 있는 {int((m['annual_yoy_%'].notna()&m.ay.notna()).sum())}) |", f"| 분기 YoY | {agree('quarterly_yoy_%','qy',0.5)} (둘 다 있는 {int((m['quarterly_yoy_%'].notna()&m.qy.notna()).sum())}) |",
              f"| 실적 패턴 | {(m.earnings_pattern==m.earnings_pattern_act).mean():.0%} |", f"| OCF 패턴 | {(m.ocf_pattern==m.ocf_pattern_act).mean():.0%} |",
              f"| 위험 등급 | {(m.risk_level==m.risk_level_act).mean():.0%} (실제 '주의' {int((m.risk_level_act=='주의').sum())}·'위험' {int((m.risk_level_act=='위험').sum())}, 재계산 '주의' {int((m.risk_level=='주의').sum())}) |"]
    # 점수: 실제 수급을 끼워 다시 합산 (supply 항만 교체) → final 비교
    sup_act, _ = V3.supply_v2_score(pd.DataFrame({"foreign_5d_억": m.f5, "inst_5d_억": m.i5, "amt_avg_1m_억": m.amt}))
    m2 = m.merge(v3, on=["run_id", "market", "ticker"], how="inner", suffixes=("", "_v3"))
    sup_act2 = sup_act.loc[m2.index] if len(m2) == len(m) else V3.supply_v2_score(pd.DataFrame({"foreign_5d_억": m2.f5, "inst_5d_억": m2.i5, "amt_avg_1m_억": m2.amt}))[0]
    mine_full = (m2.final_score_v3 - m2.supply_score_v2 + sup_act2).where(m2.final_score_v3 > -900, m2.final_score_v3)
    diff = (mine_full - m2.final_score_v3_v3)
    ok = m2.final_score_v3_v3 > -900
    lines += ["", f"- 최종 점수(재계산 + 실제 수급 항) vs 실제 v30: 겹침 {len(m2):,} · |차이| ≤ 1점 {(diff[ok].abs()<=1).mean():.0%} · ≤ 5점 {(diff[ok].abs()<=5).mean():.0%} · 중앙 |차이| {diff[ok].abs().median():.1f} · 평균 차이 {diff[ok].mean():+.1f} (음수면 재계산이 낮음 — DIV 0·PBR/PER 근사 때문)",
              f"- 상위10 겹침: 날짜·시장마다 재계산 상위10 ∩ 실제 상위10 평균 {top_overlap(m2):.1f}/10",
              "", "읽는 법: 가격 지표(RSI·과매도)는 식이 같으니 거의 100% 여야 한다. 재무(YoY·패턴)는 접수일 PIT 와 캐시 시점 차이로 일부 다를 수 있다. 점수 차이는 수급(끼워 넣음)·DIV(0)·PBR/PER 근사·위험등급(부분)에서 온다."]
    (HERE / "validate.md").write_text("\n".join(lines), encoding="utf-8"); print("\n".join(lines))


def top_overlap(m2):
    v = []
    for (d, mk), g in m2.groupby(["run_id", "market"]):
        a = set(g.nlargest(10, "final_score_v3").ticker); b = set(g.nlargest(10, "final_score_v3_v3").ticker); v.append(len(a & b))
    return float(np.mean(v)) if v else float("nan")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--validate", action="store_true"); ap.add_argument("--start", default="20240102"); ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--pit-strict", action="store_true", help="보고서 가용일 = 저장된 접수일만(마감일 소급 없음)")
    a = ap.parse_args(); PIT_STRICT = a.pit_strict
    if PIT_STRICT: OUT = HERE / "v30_hist_scores_strict.parquet"
    main(validate=a.validate, start=a.start, step=a.step)
