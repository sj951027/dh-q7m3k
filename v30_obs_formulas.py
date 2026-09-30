# -*- coding: utf-8 -*-
"""v30_obs_formulas.py — v30 후보 관측 공식 F1~F4 순위 (표시 전용 · 점수·순위·판정 무반영) [2026-09-30]

출처: research 2026-09-30 v30 전수 탐색(약 7.5만 공식) 중 '6월·7월·8월(20일 확정)·8월 말·9월(중간) 5개 기간 모두 v30 보다
나았던' 공식 4개. 같은 기간 데이터로 고른 것이라 앞으로의 성적은 모른다 → 오늘 날짜로 고정해 두고 관측만 한다.
  F1 = 거래대금(1개월)↓ + 3개월 수익↓ + 1개월 수익↓
  F2 = PBR↓ + 52주 고점 대비 낙폭 큼 + 3개월 수익↓
  F3 = 거래대금(1개월)↓ + 3개월 수익↓ + 200일선 대비↓
  F4 = V3가치점수↓ + PBR↓ + 3개월 수익↓   (⚠ 가치점수와 PBR 방향이 서로 모순 — 우연일 가능성 큼)
계산: 그날·그 시장 v30 후보 중 버킷 WATCH·EXCLUDE 와 희석 공시 60거래일 종목을 뺀 풀에서, 각 항목을 백분위(0~1)로 바꿔
'낮을수록 좋음'이면 1−백분위, 결측은 0.5 → 세 항목 합(0~3, 클수록 우선) → 시장별 순위(1=최우선). 풀 밖 종목은 빈칸.
입력: v3_archive/v3_{market}_{run}.csv · dilution_flag(ohlcv.db 읽기 전용).
출력: docs/latest_v30_obs.csv (최신 run) · docs/hist/v30_obs.json (최근 12 run, run_id 별 {ticker: [r1..r4, s1..s4]}).
실패해도 비치명(build_daily_lists.py 끝에서 호출, 예외는 경고만).
"""
import glob, json, os, sys
from datetime import datetime
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
ARCH = Path(os.environ.get("V30OBS_ARCH", HERE / "v3_archive"))
OUT = Path(os.environ.get("V30OBS_OUT", HERE / "docs"))
DB = os.environ.get("V30OBS_DB")          # 없으면 dilution_flag 기본 경로
N_HIST = 12
SPEC_DATE = "20260930"
FORMULAS = {   # id: [(컬럼, 낮을수록 좋음?)]  — 동결(2026-09-30). 바꾸려면 새 id.
    "F1": [("amt_avg_1m_억", True), ("return_3m_%", True), ("return_1m_%", True)],
    "F2": [("PBR", True), ("drawdown_52w_high_%", True), ("return_3m_%", True)],
    "F3": [("amt_avg_1m_억", True), ("return_3m_%", True), ("vs_SMA200_%", True)],
    "F4": [("value_score", True), ("PBR", True), ("return_3m_%", True)],
}
LABELS = {"F1": "거래대금↓+3개월↓+1개월↓", "F2": "PBR↓+고점낙폭↑+3개월↓",
          "F3": "거래대금↓+3개월↓+200일선↓", "F4": "가치점수↓+PBR↓+3개월↓(모순주의)"}


def _dil(run_id):
    try:
        sys.path.insert(0, str(HERE))
        import dilution_flag as dil
        return set(dil.load(asof=run_id, db=DB).keys()) if DB else set(dil.load(asof=run_id).keys())
    except Exception as e:
        print(f"   ⚠ v30_obs: 희석 플래그 로드 실패(풀에서 희석 제외 생략): {e}")
        return set()


def score_run(run_id):
    """→ DataFrame(market, ticker, F1_rank.., F1_score..) — 풀 종목만."""
    dil = _dil(run_id); out = []
    for mkt in ("kospi", "kosdaq"):
        p = ARCH / f"v3_{mkt}_{run_id}.csv"
        if not p.exists():
            continue
        g = pd.read_csv(p, dtype={"ticker": str}, encoding="utf-8-sig", low_memory=False)
        g["ticker"] = g["ticker"].astype(str).str.zfill(6)
        g = g[~g["bucket"].isin(["WATCH", "EXCLUDE"]) & ~g["ticker"].isin(dil)].copy()
        if g.empty:
            continue
        res = pd.DataFrame({"market": mkt, "ticker": g["ticker"].values})
        for fid, parts in FORMULAS.items():
            s = 0.0
            for col, low_good in parts:
                x = pd.to_numeric(g[col], errors="coerce") if col in g else pd.Series(float("nan"), index=g.index)
                pr = x.rank(pct=True)
                s = s + ((1 - pr) if low_good else pr).fillna(0.5)
            res[f"{fid}_score"] = s.round(3).values
            res[f"{fid}_rank"] = s.rank(ascending=False, method="min").astype(int).values
        out.append(res)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _v30_top(run_id, n):
    """그날 v3_archive 의 final_score_v3 시장별 상위 n (날짜 탭 행과 같은 점수) → {(market, ticker)}."""
    out = set()
    for mkt in ("kospi", "kosdaq"):
        p = ARCH / f"v3_{mkt}_{run_id}.csv"
        if not p.exists():
            continue
        g = pd.read_csv(p, dtype={"ticker": str}, encoding="utf-8-sig", usecols=["ticker", "final_score_v3"])
        g["ticker"] = g["ticker"].astype(str).str.zfill(6)
        g["final_score_v3"] = pd.to_numeric(g["final_score_v3"], errors="coerce")
        out |= {(mkt, t) for t in g.nlargest(n, "final_score_v3")["ticker"]}
    return out


def main():
    runs = sorted({Path(f).stem.split("_")[-1] for f in glob.glob(str(ARCH / "v3_kospi_*.csv"))})
    if not runs:
        print("   ⚠ v30_obs: v3_archive 없음"); return
    latest = runs[-1]
    cur = score_run(latest)
    OUT.mkdir(parents=True, exist_ok=True)
    cur.insert(0, "run_id", latest)
    cur.to_csv(OUT / "latest_v30_obs.csv", index=False, encoding="utf-8-sig")
    days = []
    for rid in reversed(runs[-N_HIST:]):
        d = cur if rid == latest else score_run(rid)
        if d.empty:
            continue
        # [용량] 날짜 탭에 보이는 종목(그날 v30 상위 60)과 어느 공식이든 상위 30 만 남긴다 — 전체 저장 시 하루 약 280KB
        keep = _v30_top(rid, 60)
        rows = {f"{r.market}:{r.ticker}": [int(getattr(r, f"{f}_rank")) for f in FORMULAS] + [round(float(getattr(r, f"{f}_score")), 2) for f in FORMULAS]
                for r in d.itertuples(index=False)
                if (r.market, r.ticker) in keep or min(int(getattr(r, f"{f}_rank")) for f in FORMULAS) <= 30}
        days.append({"run_id": rid, "rows": rows})
    payload = {"spec_date": SPEC_DATE, "generated": datetime.now().isoformat(timespec="seconds"),
               "formulas": {k: LABELS[k] for k in FORMULAS}, "fields": [f"{f}_rank" for f in FORMULAS] + [f"{f}_score" for f in FORMULAS],
               "note": "v30 후보(WATCH·EXCLUDE·희석 제외) 안 관측 공식 순위 · 표시 전용 · 점수·추천·판정 무반영", "days": days}
    (OUT / "hist").mkdir(parents=True, exist_ok=True)
    (OUT / "hist" / "v30_obs.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ docs/latest_v30_obs.csv ({latest}, {len(cur)}행) · docs/hist/v30_obs.json ({len(days)}일)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠ v30_obs 생성 실패(비치명): {e}")
        sys.exit(1)
