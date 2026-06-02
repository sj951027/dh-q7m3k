# -*- coding: utf-8 -*-
"""
v3_rescore.py
=============
과매도 스크리너를 "과매도=입장권, 순위=가치/품질/턴어라운드/반전/수급" 구조로
재점수화한다. history.db(stage3_final)의 기존 산출물을 입력으로 받아
새 점수 final_score_v3 와 등급(grade)을 만든다.

지금 오프라인에서 적용되는 것:
  - oversold_score cap (과매도 비중 축소)
  - regime 분리 (종목 랭킹에서 시장레짐 제외)
  - risk_level=주의 패널티 + 메인후보 제외
  - 수급 정규화 (순매수 / 평균거래대금)
  - 반전 점수 (5일선 회복 / 3% 반등 / 거래량 양봉 / 단기개선)
  - 품질 점수 (간이 Piotroski: OCF / OCF전환 / YoY / ocf_pattern)
  - 턴어라운드 점수 (earnings_pattern + 분기 YoY, 이중적자 시 감액)
  - falling_knife 제외
  - sector 백필 (sector_cache.json)
  - A+/A/B/C/WATCH/EXCLUDE 등급

네트워크 필요 (지금은 hook만):
  - 진짜 밸류에이션(PBR/PER/배당/ROE) → attach_valuation()
    valuation_{market}_{run_id}.csv (ticker,PBR,PER,DIV,...) 가 있으면 자동 사용.
    없으면 value_score=0, value_source='UNAVAILABLE_OFFLINE'.
"""
import os
import json
import sqlite3
import argparse
import numpy as np
import pandas as pd

DB_PATH = "history.db"
SECTOR_CACHE = "sector_cache.json"


# ---------------------------------------------------------------- 로딩
def load_runs(db_path=DB_PATH, run_id=None):
    """stage3_final 전체(또는 특정 run_id)를 읽는다."""
    con = sqlite3.connect(db_path)
    if run_id:
        df = pd.read_sql("SELECT * FROM stage3_final WHERE run_id=?", con, params=[run_id])
    else:
        df = pd.read_sql("SELECT * FROM stage3_final", con)
    con.close()
    return df


def attach_sector(df, cache_path=SECTOR_CACHE):
    """sector가 비어 있으면 sector_cache.json으로 백필."""
    if not os.path.exists(cache_path):
        return df
    cache = json.load(open(cache_path, encoding="utf-8"))
    cur = df["sector"].astype(str).str.strip()
    need = cur.isin(["", "nan", "None"]) | df["sector"].isna()
    df.loc[need, "sector"] = df.loc[need, "ticker"].map(cache)
    df["sector"] = df["sector"].fillna("미분류")
    return df


# ------------------------------------------------------------ 헬퍼
def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _flag(s):
    """0/1, True/False, 'true'/'yes' 등을 bool로."""
    return (
        s.fillna(0).astype(str).str.lower().isin(["1", "true", "yes", "y", "t"])
    )


# ------------------------------------------------------------ 개별 점수
def reversal_score(df):
    """반전(타이밍) 점수 0~15. falling_knife는 별도 패널티에서 처리."""
    a = _flag(df["reversal_above_sma5"]).astype(int) * 4
    b = _flag(df["reversal_rebound_3pct"]).astype(int) * 4
    c = _flag(df["reversal_vol_up_candle"]).astype(int) * 4
    r1w = _num(df["return_1w_%"]).fillna(0)
    r1m = _num(df["return_1m_%"]).fillna(0)
    # 1주 수익률이 '월간 평균 페이스'보다 나으면 단기 개선으로 +3
    improving = (r1w > (r1m / 4.0)).astype(int) * 3
    return (a + b + c + improving).clip(0, 15)


def supply_v2_score(df):
    """수급 정규화: (외인+기관 5일 순매수) / 20일 평균거래대금."""
    f = _num(df["foreign_5d_억"]).fillna(0)
    i = _num(df["inst_5d_억"]).fillna(0)
    amt = _num(df["amt_avg_1m_억"]).fillna(0).clip(lower=0.1)
    net = f + i
    intensity = net / amt
    s = pd.Series(0, index=df.index, dtype=float)
    s = s.mask(intensity >= 0.05, 5)
    s = s.mask(intensity >= 0.15, 10)
    s = s.mask(intensity >= 0.30, 15)
    s = s.mask(intensity <= -0.15, -10)
    both_pos = (f > 0) & (i > 0)
    s = (s + both_pos.astype(int) * 3).clip(-10, 15)
    return s, intensity.round(3)


OCF_QUALITY = {
    "현금창출양호": 5, "현금창출보통": 2, "현금창출약함": -3,
    "밸류트랩의심": -15, "이중적자": -20, "회계손실현금유입": 0,
    "데이터없음": -2, "데이터부족": -2,
}


def quality_score(df):
    """간이 품질 점수(-25~25). OCF 흑자/전환/YoY/ocf_pattern 기반."""
    q = pd.Series(0.0, index=df.index)
    ocf = _num(df["ocf_latest_억"]).fillna(np.nan)
    ratio = _num(df["ocf_to_op_ratio"])
    qy = _num(df["quarterly_yoy_%"])
    ay = _num(df["annual_yoy_%"])

    q += (ocf > 0).astype(int) * 5
    # OCF 전환율 건전(0.7~5배). 분모 작아 폭주하는 값은 제외.
    q += ((ratio >= 0.7) & (ratio <= 5)).astype(int) * 5
    q += (qy > 10).astype(int) * 5
    q += ((qy > 0) & (qy <= 10)).astype(int) * 2
    q += (ay > 0).astype(int) * 3
    q += df["ocf_pattern"].map(OCF_QUALITY).fillna(0)
    return q.clip(-25, 25)


EARN_TURN = {
    "턴어라운드": 12, "흑자전환": 12, "성장지속": 6,
    "관망": 0, "하락지속": -10, "데이터부족": 0, "피크아웃": -15,
}


def turnaround_score(df):
    """턴어라운드 0~20(이중적자/밸류트랩이면 절반)."""
    t = df["earnings_pattern"].map(EARN_TURN).fillna(0).astype(float)
    qy = _num(df["quarterly_yoy_%"]).fillna(0)
    t += (qy > 20).astype(int) * 5
    bad = df["ocf_pattern"].isin(["이중적자", "밸류트랩의심"])
    t = t.where(~bad, t * 0.5)  # 가짜 턴어라운드 방지
    return t.clip(-15, 20)


def oversold_component(df, cap=20, scale=0.25):
    """과매도는 후보 자격일 뿐. 최종 점수에는 최대 cap 점만."""
    o = _num(df["oversold_score"]).fillna(0)
    return (o * scale).clip(0, cap)


# ------------------------------------------------------------ 밸류에이션(hook)
def attach_valuation(df, run_id, market):
    """
    valuation_{market}_{run_id}.csv (ticker, PBR, PER, DIV[, ROE]) 가 있으면
    업종 내 percentile 기반 value_score(0~25)를 만든다. 없으면 0 + 플래그.
    """
    path = f"valuation_{market}_{run_id}.csv"
    if not os.path.exists(path):
        df["value_score"] = 0.0
        df["value_source"] = "UNAVAILABLE_OFFLINE"
        return df
    v = pd.read_csv(path, dtype={"ticker": str})
    df = df.merge(v, on="ticker", how="left", suffixes=("", "_val"))
    pbr = _num(df.get("PBR"))
    per = _num(df.get("PER"))
    div = _num(df.get("DIV")).fillna(0)
    df["_pbr"] = pbr
    df["_per"] = per

    # 업종 percentile. 단 '미분류' 또는 표본<5인 업종은 시장 전체 percentile로 대체
    # (미분류 안에서 서로 다른 업종을 한 통에 비교하는 왜곡을 막음)
    def robust_pct(col, ascending=True, min_n=5):
        sec_rank = df.groupby("sector")[col].rank(pct=True, ascending=ascending)
        mkt_rank = df[col].rank(pct=True, ascending=ascending)
        grp_n = df.groupby("sector")[col].transform("count")
        use_sector = (df["sector"] != "미분류") & (grp_n >= min_n)
        return sec_rank.where(use_sector, mkt_rank)

    score = pd.Series(0.0, index=df.index)
    score += ((pbr > 0) & (pbr < 1.0)).astype(int) * 6
    score += (robust_pct("_pbr", ascending=True) <= 0.30).fillna(False).astype(int) * 6
    score += ((per > 0) & (robust_pct("_per", ascending=True) <= 0.40)).fillna(False).astype(int) * 5
    score += (div > 2).astype(int) * 3
    score += (per <= 0).astype(int) * (-5)          # 적자 패널티
    df["value_score"] = score.clip(-10, 25)
    df["value_source"] = "PYKRX"
    return df.drop(columns=["_pbr", "_per"], errors="ignore")


# ------------------------------------------------------------ 조립
def rescore(df, run_id=None, market=None, oversold_cap=20):
    """한 (run_id, market) 묶음을 v3로 재점수화."""
    df = df.copy().reset_index(drop=True)
    df = attach_sector(df)

    df["reversal_score"] = reversal_score(df)
    df["supply_score_v2"], df["supply_intensity"] = supply_v2_score(df)
    df["quality_score"] = quality_score(df)
    df["turnaround_score"] = turnaround_score(df)
    df["oversold_component"] = oversold_component(df, cap=oversold_cap)

    if run_id is None:
        run_id = str(df["run_id"].iloc[0])
    if market is None:
        market = str(df["market"].iloc[0])
    df = attach_valuation(df, run_id, market)

    fk = _flag(df["falling_knife"])
    risk = df["risk_level"].astype(str)
    hard_trap = df["ocf_pattern"].isin(["이중적자"])      # 하드 제외
    soft_trap = df["ocf_pattern"].isin(["밸류트랩의심"])   # 메인후보 제외(+패널티)

    penalty = pd.Series(0.0, index=df.index)
    penalty += (risk == "주의").astype(int) * (-10)
    penalty += soft_trap.astype(int) * (-10)
    # 메인후보: 주의/위험/이중적자/밸류트랩의심/falling_knife 모두 제외
    df["main_candidate"] = ~(
        (risk == "주의") | (risk == "위험") | fk | hard_trap | soft_trap)

    df["final_score_v3"] = (
        df["value_score"]
        + df["quality_score"]
        + df["turnaround_score"]
        + df["reversal_score"]
        + df["supply_score_v2"]
        + df["oversold_component"]
        + penalty
    ).round(1)

    # 진입 타이밍 점수: 메인후보 '내부'에서 누가 먼저 들어갈지 (반전·수급 가중)
    df["entry_score"] = (
        df["reversal_score"] * 2.0
        + df["supply_score_v2"] * 1.2
        + df["quality_score"] * 0.8
        + df["turnaround_score"] * 0.7
        + df["oversold_component"] * 0.3
    ).round(1)

    # 하드 제외는 점수를 완전히 바닥으로 (위험/falling_knife/이중적자 모두)
    hard_exclude = (risk == "위험") | fk | hard_trap
    df.loc[hard_exclude, ["final_score_v3", "entry_score"]] = -999

    df["grade"] = grade(df)
    df["bucket"] = bucket(df)
    return df.sort_values("final_score_v3", ascending=False).reset_index(drop=True)


def bucket(df):
    """실사용 의사결정용 버킷. Top 점수 단순 정렬 오해를 막는다."""
    g = df["grade"]; rev = df["reversal_score"]
    b = pd.Series("OBSERVE", index=df.index)
    b = b.mask((g == "B") & (rev < 4), "OBSERVE")
    b = b.mask((g == "B") & (rev >= 4), "WAIT")
    b = b.mask(g.isin(["A+", "A"]), "BUY")
    b = b.mask(g == "WATCH", "WATCH")
    b = b.mask(g == "EXCLUDE", "EXCLUDE")
    return b


def grade(df):
    risk = df["risk_level"].astype(str)
    fk = _flag(df["falling_knife"])
    trap = df["ocf_pattern"].isin(["이중적자"])
    val = df["value_score"]
    has_val = bool((df.get("value_source", "UNAVAILABLE_OFFLINE") == "PYKRX").any())
    mc = df["main_candidate"]
    q = df["quality_score"]; rev = df["reversal_score"]; sup = df["supply_score_v2"]
    turn = df["turnaround_score"]; fs = df["final_score_v3"]

    g = pd.Series("C", index=df.index)
    # B: 메인후보 + 품질은 괜찮으나 반전 미확인 (대기)
    b = mc & (q >= 12)
    # A: 더 엄격 — 반전 확인 + 수급 비음수 + 턴어라운드 비음수 + 점수 하한
    a = mc & (q >= 15) & (rev >= 8) & (sup >= 0) & (turn >= 0) & (fs >= 35)
    # A+: 가장 엄격
    a_plus = (mc & (q >= 18) & (rev >= 8) & (sup >= 8)
              & (turn >= 5) & (fs >= 50) & (risk == "안전"))
    if has_val:                       # 밸류 켜지면 저평가 조건 필수
        a = a & (val >= 12)
        a_plus = a_plus & (val >= 15)
    g = g.mask(b, "B")
    g = g.mask(a, "A")
    g = g.mask(a_plus, "A+")
    g = g.mask(df["ocf_pattern"].isin(["밸류트랩의심"]), "WATCH")
    g = g.mask(risk == "주의", "WATCH")
    g = g.mask((risk == "위험") | fk | trap, "EXCLUDE")
    return g


# ------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--run_id", default=None, help="기본: 가장 최근 run")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--oversold_cap", type=int, default=20)
    ap.add_argument("--quiet", action="store_true",
                    help="자동 실행용: BUY/WAIT 표를 출력하지 않고 보관 폴더에만 저장")
    ap.add_argument("--archive", default="v3_archive",
                    help="run_id별 결과를 쌓아둘 폴더(검증 히스토리 누적용)")
    ap.add_argument("--docs", action="store_true",
                    help="docs/latest_*_v3.csv 로도 저장(대시보드 노출). 기본 꺼짐")
    args = ap.parse_args()

    allruns = load_runs(args.db)
    run_id = args.run_id or sorted(allruns["run_id"].unique())[-1]
    os.makedirs(args.archive, exist_ok=True)

    for mkt in ["kospi", "kosdaq"]:
        sub = allruns[(allruns["run_id"] == run_id) & (allruns["market"] == mkt)]
        if sub.empty:
            continue
        rs = rescore(sub, run_id=run_id, market=mkt, oversold_cap=args.oversold_cap)

        # (1) 검증 히스토리 누적: 보관 폴더에 run_id별로 영구 저장
        rs.to_csv(f"{args.archive}/v3_{mkt}_{run_id}.csv",
                  index=False, encoding="utf-8-sig")
        # (2) 작업용 최신본
        rs.to_csv(f"v3_{mkt}_final_{run_id}.csv",
                  index=False, encoding="utf-8-sig")
        # (3) 대시보드 노출은 명시적으로 --docs 줄 때만 (자동 실행에선 안 함)
        if args.docs and os.path.isdir("docs"):
            rs.to_csv(f"docs/latest_{mkt}_v3.csv",
                      index=False, encoding="utf-8-sig")

        if args.quiet:
            # 조용한 모드: 매수신호처럼 보이는 표는 출력하지 않음
            vc = rs["bucket"].value_counts().to_dict()
            print(f"[v3] {mkt} {run_id} 저장 (보관:{args.archive}) "
                  f"value={rs['value_source'].iloc[0]} 버킷={vc}")
            continue

        show = ["name", "grade", "final_score_v3", "entry_score",
                "value_score", "quality_score", "turnaround_score",
                "reversal_score", "supply_score_v2", "oversold_component",
                "risk_level", "sector"]
        show = [c for c in show if c in rs.columns]
        print(f"\n========== {mkt.upper()} {run_id} ==========")
        print("버킷 분포:", rs["bucket"].value_counts().to_dict())
        for bk in ["BUY", "WAIT"]:
            part = rs[rs["bucket"] == bk]
            if part.empty:
                print(f"\n[{bk}] 해당 없음")
                continue
            part = part.sort_values("final_score_v3", ascending=False)
            print(f"\n[{bk}] {len(part)}개")
            print(part[show].head(args.top).to_string(index=False))
        print(f"\n저장: v3_{mkt}_final_{run_id}.csv  (+보관 {args.archive}/)")


if __name__ == "__main__":
    main()
