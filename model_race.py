# -*- coding: utf-8 -*-
"""
model_race.py — 전 모델 '같은 자·같은 규칙' 가상 포트폴리오 레이스 (research 관측 전용)
==============================================================================
질문: "실제 수익률로 따지면 어느 모델이 낫나?"
IC는 유니버스가 다르면 절대값 비교 금지지만, **같은 기간·같은 규칙·같은 벤치마크**로
굴린 페이퍼 포트폴리오의 원화 수익률은 트랙이 달라도 공정 비교 가능하다.

규칙(전 모델 동일 — 유리한 조작 여지 제거):
  * 매 run일 점수 상위 TOP_N 종목 동일가중.
  * 진입 = run 다음 거래일 종가(ENTRY_LAG=1, 리더보드와 동일).
  * 다음 run의 top이 나오면 그 다음날 교체(일일 리밸런스). run 없는 날은 보유 유지.
  * 벤치마크 = 동일 기간 EW(전 종목 동일가중)·CW(시총가중) — 모든 모델에 같은 잣대.
  * 게이트 run(부분실행 20260608·이중실행 20260703) 제외.
  * 시작일: (a) 각 모델 등록일 이후  (b) 공통 구간(전 모델 등록 완료 후) 두 가지 표.

한계(정직):
  * OOS가 짧다(모델별 6~23거래일). 이 레이스는 '지금 어떤 기움인지' 직관용 관측이지
    §11 판정(40거래일·CI·Bonferroni)을 대체하지 않는다. 거래비용 미반영.
  * 절대수익은 시장 베타가 지배(§17) — 하락장에선 다 마이너스일 수 있음. 그래서
    'EW초과'를 같이 본다(같은 벤치마크라 모델 간 비교 공정).

사용:
    python model_race.py            # 기본(TOP_N=10)
    python model_race.py --topn 20
산출: research/model_race_{마지막날}.csv + 콘솔 표. history.db·ohlcv.db READONLY.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "history.db"
OHLCV_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))
RESEARCH_DIR = HERE / "research"

GATES = {"20260608", "20260703"}
REG_DATE = {
    "v30": "20260606", "v31a": "20260606", "v31b": "20260606",
    "v31c": "20260606", "v31d": "20260606",
    "v31f": "20260622", "v31g": "20260622",
    "lv_a": "20260625", "lv_b": "20260625", "lv_c": "20260625",
    "lv_d": "20260625", "lv_a3": "20260625",
    "mom_a": "20260627", "lv_short": "20260627", "hv_a": "20260627", "sm_a": "20260627",
    "wu_a": "20260702", "wu_b": "20260702",
}
TRACK = {m: ("v3" if m.startswith("v3") else "wu" if m.startswith("wu") else "lowvol")
         for m in REG_DATE}
SCORE_TBL = {"v3": ("v3_scores", "final_score_v3"),
             "lowvol": ("lowvol_scores", "lowvol_score"),
             "wu": ("wu_scores", "wu_score")}


def load_prices(con):
    raw = pd.read_sql(
        "SELECT ticker,date,close,shares FROM daily_ohlcv WHERE date>='20260520'", con)
    raw["close"] = pd.to_numeric(raw["close"], errors="coerce")
    close = raw.pivot_table(index="ticker", columns="date", values="close",
                            aggfunc="last").sort_index(axis=1)
    sh = raw[raw.date == raw.date.max()].set_index("ticker")["shares"]
    return close, pd.to_numeric(sh, errors="coerce")


def run_portfolio(picks_by_run, close, dates, start_date, topn):
    """run일→top리스트 dict 로 일일 리밸런스 페이퍼 포트폴리오 일별수익 시리즈."""
    rets = close.pct_change(axis=1, fill_method=None)
    daily = {}
    cur = None            # 현재 보유 종목 리스트
    pending = None        # 다음날 진입 예정(전일 run 의 top)
    for d in dates:
        if d <= start_date:
            if d in picks_by_run:
                pending = picks_by_run[d]
            continue
        if pending is not None:
            cur = pending; pending = None   # 전일 run 의 top 으로 오늘 종가 진입
        if cur:
            r = rets[d].reindex(cur).dropna()
            if len(r):
                daily[d] = r.mean()
        if d in picks_by_run:
            pending = picks_by_run[d]
    return pd.Series(daily)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topn", type=int, default=10)
    args = ap.parse_args()

    if not DB_PATH.exists():
        raise SystemExit("history.db 없음")
    if not os.path.exists(OHLCV_DB):
        raise SystemExit(f"ohlcv.db 없음: {OHLCV_DB}")
    h = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    o = sqlite3.connect(f"file:{OHLCV_DB}?mode=ro", uri=True)
    close, shares = load_prices(o)
    o.close()
    dates = [d for d in close.columns if d >= "20260601"]

    # 모델별 run→top 리스트
    picks = {}
    for m, reg in REG_DATE.items():
        tbl, scol = SCORE_TBL[TRACK[m]]
        df = pd.read_sql(
            f"SELECT run_id, ticker, {scol} AS s FROM {tbl} WHERE model_id=?",
            h, params=(m,))
        if df.empty:
            continue
        d = {}
        for run, g in df.groupby("run_id"):
            if run in GATES:
                continue
            d[str(run)] = g.dropna(subset=["s"]).nlargest(args.topn, "s")["ticker"].tolist()
        if d:
            picks[m] = (reg, d)
    h.close()

    # 벤치마크: EW(전 종목)·CW(시총가중) 일별수익
    rets = close.pct_change(axis=1, fill_method=None)
    ew = rets.median()          # 강건한 EW proxy(중앙값 — 이상치 상장폐지 왜곡 방지)
    mc = (close.iloc[:, -1] * shares).dropna()
    cw_w = mc / mc.sum()
    cw = (rets.mul(cw_w, axis=0)).sum() / cw_w[rets.notna().any(axis=1)].sum()

    common_start = max(reg for reg, _ in picks.values())   # 전 모델 등록 완료일

    def table(start_of):
        rows = []
        for m, (reg, d) in picks.items():
            s0 = start_of(reg)
            ser = run_portfolio(d, close, dates, s0, args.topn)
            ser = ser[ser.index > s0]
            if ser.empty:
                continue
            cum = float((1 + ser).prod() - 1) * 100
            ewb = ew.reindex(ser.index)
            cwb = cw.reindex(ser.index)
            rows.append((TRACK[m], m, len(ser), cum,
                         float((1 + ewb).prod() - 1) * 100,
                         float((1 + cwb).prod() - 1) * 100,
                         cum - float((1 + ewb).prod() - 1) * 100,
                         float((ser > ewb).mean()) * 100))
        out = pd.DataFrame(rows, columns=[
            "track", "model", "일수", "누적%", "EW시장%", "CW시장%", "EW초과%p", "EW승률%"])
        return out.sort_values("누적%", ascending=False)

    print("=" * 78)
    print(f"모델 레이스 — top{args.topn} 동일가중 · 익일 종가 진입 · 일일 리밸 · 비용 미반영")
    print("⚠️ 관측용 직관 지표. §11 판정(40거래일) 대체 아님. OOS 짧음 — 전부 '기움'.")
    print("=" * 78)

    t1 = table(lambda reg: max(reg, common_start))
    print(f"\n[A] 공통 구간(전 모델 등록 완료 {common_start} 이후) — 같은 날짜·같은 잣대")
    print(t1.to_string(index=False, float_format=lambda x: f"{x:+.2f}"))

    t2 = table(lambda reg: reg)
    print(f"\n[B] 각자 등록일 이후(기간 다름 — 참고용, 서로 직접 비교 금지)")
    print(t2.to_string(index=False, float_format=lambda x: f"{x:+.2f}"))

    RESEARCH_DIR.mkdir(exist_ok=True)
    last = dates[-1]
    t1.assign(구간="common").pipe(lambda a: pd.concat(
        [a, t2.assign(구간="since_reg")])).to_csv(
        RESEARCH_DIR / f"model_race_{last}.csv", index=False, encoding="utf-8-sig")
    print(f"\n[저장] research/model_race_{last}.csv")
    print("읽는 법: '누적%'=절대수익(베타 포함), 'EW초과%p'=같은 기간 시장(동일가중) 대비.")
    print("        모델 간 공정 비교는 [A]표의 EW초과%p 와 EW승률. 판정은 여전히 리더보드.")


if __name__ == "__main__":
    main()
