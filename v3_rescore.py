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
import copy
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


def supply_v2_score(df, both_pos_bonus=3):
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
    s = (s + both_pos.astype(int) * both_pos_bonus).clip(-10, 15)
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


# ------------------------------------------------------- 모델 스펙(챔피언/챌린저)
# v30 = 현재 챔피언. 값은 기존 코드 상수와 100% 동일 → 출력 불변(회귀 테스트로 증명).
# 챌린저는 v30 에서 '딱 한 가지'만 바꾼다(무엇이 효과인지 분리하기 위해).
LIQ_FLOOR = 5.0    # E4: 최소 20일 평균거래대금(억). 거래 불가 초소형주 컷(튜닝 가능).
# F1(v31f) macd 이격도 가산 가중치. 셀내 z(±3 clip) std≈0.92, 성분 std 중앙값≈5.93 →
# 기여 std가 '성분 1개' 크기가 되도록 6.0 으로 보정·동결(불변규칙 2: 시작하면 변경 금지).
MACD_TILT_W = 6.0
# F2(v31g) 거래량팽창(vol_1w_vs_1m_ratio) 가산 가중치. 셀내 z(±3)std≈0.863 →
# 기여 std가 '성분 1개'(≈5.93)가 되도록 7.0 으로 보정·동결(불변규칙 2).
VOLEXP_TILT_W = 7.0

SPEC_V30 = {
    "label": "v30 · 챔피언(현재)",
    "oversold_cap": 20,
    "oversold_scale": 0.25,
    # final_score_v3 합산 가중치 (v30 = 전부 1.0)
    "w": {"value": 1.0, "quality": 1.0, "turnaround": 1.0,
          "reversal": 1.0, "supply": 1.0, "oversold": 1.0},
    "supply_both_pos_bonus": 3,
    "penalty_caution": -10.0,
    "penalty_soft_trap": -10.0,
    "entry_w": {"reversal": 2.0, "supply": 1.2, "quality": 0.8,
                "turnaround": 0.7, "oversold": 0.3},
    "grade_B":  {"q": 12},
    "grade_A":  {"q": 15, "rev": 8, "sup": 0, "turn": 0, "fs": 35, "val": 12},
    "grade_Ap": {"q": 18, "rev": 8, "sup": 8, "turn": 5, "fs": 50, "val": 15},
    "bucket_wait_rev": 4,
    # ── 챌린저 훅(v30 = 전부 OFF) ──
    "liquidity_floor": 0.0,          # E4
    "buy_requires_reversal": False,  # E2
    "sector_neutralize": False,      # E5
    "macd_tilt_w": 0.0,              # F1 (v31f) — 0 이면 점수 불변(v30/v31a~d 동일)
    "volexp_tilt_w": 0.0,            # F2 (v31g) — 0 이면 점수 불변(v30/v31a~d/v31f 동일)
}


def _spec(label, **over):
    """v30 을 깊은 복사한 뒤 지정한 키만 덮어쓴 새 스펙(=한 가지만 다른 챌린저)."""
    s = copy.deepcopy(SPEC_V30)
    s["label"] = label
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k] = {**s[k], **v}
        else:
            s[k] = v
    return s


# 등록된 모델. v30 외에는 전부 '한 변수'만 변경.
MODELS = {
    "v30":  SPEC_V30,
    "v31a": _spec("v31a · E2 반전확인 진입게이트", buy_requires_reversal=True),
    "v31b": _spec("v31b · E3 수급 가중↑",          w={"supply": 1.6}),
    "v31c": _spec("v31c · E4 유동성 하한",          liquidity_floor=LIQ_FLOOR),
    "v31d": _spec("v31d · E5 섹터 중립화",          sector_neutralize=True),
    "v31f": _spec("v31f · F1 macd 이격도 가산(섀도우)", macd_tilt_w=MACD_TILT_W),
    "v31g": _spec("v31g · F2 거래량팽창 가산(섀도우)",   volexp_tilt_w=VOLEXP_TILT_W),
}

# [2026-08-09] §11 첫 판정(VERDICT_20260809.md): 챌린저 6개 전원 기각 → 챔피언 v30 유지.
#   기각 모델은 일일 섀도우·동결 '중지'만 한다(스펙·엔진·기존 v3_scores 행은 §불변 규칙대로 보존).
#   재도전은 새 model_id + 사전등록으로만. v31f 는 h10 재현 있었으나 h20 채택기준 미달(기움) — 기록.
RETIRED = {"v31a", "v31b", "v31c", "v31d", "v31f", "v31g"}


# ------------------------------------------------------------ 조립
def rescore(df, run_id=None, market=None, oversold_cap=None, spec=None):
    """한 (run_id, market) 묶음을 재점수화. spec 미지정 시 v30(챔피언)과 100% 동일."""
    spec = spec or SPEC_V30
    cap = oversold_cap if oversold_cap is not None else spec["oversold_cap"]
    w = spec["w"]

    df = df.copy().reset_index(drop=True)
    df = attach_sector(df)

    df["reversal_score"] = reversal_score(df)
    df["supply_score_v2"], df["supply_intensity"] = supply_v2_score(
        df, both_pos_bonus=spec["supply_both_pos_bonus"])
    df["quality_score"] = quality_score(df)
    df["turnaround_score"] = turnaround_score(df)
    df["oversold_component"] = oversold_component(df, cap=cap, scale=spec["oversold_scale"])

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
    penalty += (risk == "주의").astype(int) * spec["penalty_caution"]
    penalty += soft_trap.astype(int) * spec["penalty_soft_trap"]

    # 메인후보: 주의/위험/이중적자/밸류트랩의심/falling_knife 모두 제외
    main = ~((risk == "주의") | (risk == "위험") | fk | hard_trap | soft_trap)
    # E4: 유동성 하한 (켜졌을 때만 — v30 은 floor=0 이라 건너뜀 → 동일)
    if spec["liquidity_floor"] > 0:
        amt = _num(df["amt_avg_1m_억"]).fillna(0)
        main = main & (amt >= spec["liquidity_floor"])
    df["main_candidate"] = main

    fs = (
        df["value_score"] * w["value"]
        + df["quality_score"] * w["quality"]
        + df["turnaround_score"] * w["turnaround"]
        + df["reversal_score"] * w["reversal"]
        + df["supply_score_v2"] * w["supply"]
        + df["oversold_component"] * w["oversold"]
        + penalty
    )

    # F1 (v31f): 단기-중기 이격도(vs_SMA20 − vs_SMA50) 가산. 켜졌을 때만 —
    # v30/v31a~d 는 macd_tilt_w=0 이라 건너뜀 → 출력 100% 동일(0-diff).
    # 셀(run×market) 내 z-score(±3 clip; 동시점 데이터라 룩어헤드 없음) → 스케일 안정.
    if spec.get("macd_tilt_w", 0.0):
        _macd = _num(df["vs_SMA20_%"]) - _num(df["vs_SMA50_%"])
        _sd = _macd.std(ddof=0)
        _z = ((_macd - _macd.mean()) / (_sd if _sd > 1e-9 else 1.0)).clip(-3, 3)
        fs = fs + spec["macd_tilt_w"] * _z.fillna(0.0)

    # F2 (v31g): 거래량 팽창(vol_1w_vs_1m_ratio) 가산. 켜졌을 때만 —
    # v30/v31a~d/v31f 는 volexp_tilt_w=0 이라 건너뜀 → 출력 동일(0-diff).
    # 셀 내 z-score(±3 clip). 우편향이라 +3 클램프가 극단 거래량스파이크를 정규화(클램프 규율).
    if spec.get("volexp_tilt_w", 0.0):
        _ve = _num(df["vol_1w_vs_1m_ratio"])
        _ves = _ve.std(ddof=0)
        _vez = ((_ve - _ve.mean()) / (_ves if _ves > 1e-9 else 1.0)).clip(-3, 3)
        fs = fs + spec["volexp_tilt_w"] * _vez.fillna(0.0)

    hard_exclude = (risk == "위험") | fk | hard_trap

    # E5: 섹터 중립화 (켜졌을 때만). 제외 종목은 평균에서 빼고, 비제외만 섹터평균 차감.
    if spec["sector_neutralize"]:
        valid = ~hard_exclude
        sec_mean = fs.where(valid).groupby(df["sector"]).transform("mean")
        glob_mean = fs[valid].mean()
        fs = fs - sec_mean.fillna(glob_mean) + glob_mean

    df["final_score_v3"] = fs.round(1)

    ew = spec["entry_w"]
    df["entry_score"] = (
        df["reversal_score"] * ew["reversal"]
        + df["supply_score_v2"] * ew["supply"]
        + df["quality_score"] * ew["quality"]
        + df["turnaround_score"] * ew["turnaround"]
        + df["oversold_component"] * ew["oversold"]
    ).round(1)

    # 하드 제외는 점수를 완전히 바닥으로 (위험/falling_knife/이중적자 모두)
    df.loc[hard_exclude, ["final_score_v3", "entry_score"]] = -999

    df["grade"] = grade(df, spec)
    df["bucket"] = bucket(df, spec)
    return df.sort_values("final_score_v3", ascending=False).reset_index(drop=True)


def bucket(df, spec=SPEC_V30):
    """실사용 의사결정용 버킷. Top 점수 단순 정렬 오해를 막는다."""
    g = df["grade"]; rev = df["reversal_score"]
    wr = spec["bucket_wait_rev"]
    b = pd.Series("OBSERVE", index=df.index)
    b = b.mask((g == "B") & (rev < wr), "OBSERVE")
    b = b.mask((g == "B") & (rev >= wr), "WAIT")
    b = b.mask(g.isin(["A+", "A"]), "BUY")
    # E2: '실제' 반전 확인(5일선 회복 AND 거래량 양봉)이 없으면 BUY→WAIT 강등.
    #     A등급이 이미 reversal_score>=8 을 요구하므로, 합성점수가 아니라 개별 플래그로 봐야 의미가 있다.
    if spec["buy_requires_reversal"]:
        confirmed = _flag(df["reversal_above_sma5"]) & _flag(df["reversal_vol_up_candle"])
        b = b.mask((b == "BUY") & ~confirmed, "WAIT")
    b = b.mask(g == "WATCH", "WATCH")
    b = b.mask(g == "EXCLUDE", "EXCLUDE")
    return b


def grade(df, spec=SPEC_V30):
    risk = df["risk_level"].astype(str)
    fk = _flag(df["falling_knife"])
    trap = df["ocf_pattern"].isin(["이중적자"])
    val = df["value_score"]
    has_val = bool((df.get("value_source", "UNAVAILABLE_OFFLINE") == "PYKRX").any())
    mc = df["main_candidate"]
    q = df["quality_score"]; rev = df["reversal_score"]; sup = df["supply_score_v2"]
    turn = df["turnaround_score"]; fs = df["final_score_v3"]
    gB, gA, gAp = spec["grade_B"], spec["grade_A"], spec["grade_Ap"]

    g = pd.Series("C", index=df.index)
    # B: 메인후보 + 품질은 괜찮으나 반전 미확인 (대기)
    b = mc & (q >= gB["q"])
    # A: 더 엄격 — 반전 확인 + 수급 비음수 + 턴어라운드 비음수 + 점수 하한
    a = (mc & (q >= gA["q"]) & (rev >= gA["rev"]) & (sup >= gA["sup"])
         & (turn >= gA["turn"]) & (fs >= gA["fs"]))
    # A+: 가장 엄격
    a_plus = (mc & (q >= gAp["q"]) & (rev >= gAp["rev"]) & (sup >= gAp["sup"])
              & (turn >= gAp["turn"]) & (fs >= gAp["fs"]) & (risk == "안전"))
    if has_val:                       # 밸류 켜지면 저평가 조건 필수
        a = a & (val >= gA["val"])
        a_plus = a_plus & (val >= gAp["val"])
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
    ap.add_argument("--model", default="v30", choices=list(MODELS.keys()),
                    help="채점 모델(스펙). 기본 v30=챔피언. 챌린저는 보통 shadow_run.py 가 돌림")
    args = ap.parse_args()

    spec = MODELS[args.model]
    allruns = load_runs(args.db)
    run_id = args.run_id or sorted(allruns["run_id"].unique())[-1]
    os.makedirs(args.archive, exist_ok=True)

    for mkt in ["kospi", "kosdaq"]:
        sub = allruns[(allruns["run_id"] == run_id) & (allruns["market"] == mkt)]
        if sub.empty:
            continue
        rs = rescore(sub, run_id=run_id, market=mkt,
                     oversold_cap=args.oversold_cap, spec=spec)

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
