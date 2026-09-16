# -*- coding: utf-8 -*-
"""
build_cross_sim.py — 트랙 간 '공통 잣대' 모의계좌 → docs/cross_sim.json (표시 전용)
====================================================================================
리더보드 하단 '공통 잣대 모의계좌' 섹션의 데이터 생성기 (2026-08-14 사용자 결정).
원리(research/cross_track_compare.py와 동일): 같은 기간 · 매일 점수 상위 20 동일가중 ·
ENTRY_LAG=1 · 공통 벤치마크(전체상장 거래대금≥5억 EW, KOSPI 병기)로 모의 계좌 비교.

⚠ 관측 전용 — §11 판정과 무관(판정 도구 leaderboard.py 는 일절 안 건드림).
  거래비용 0 · 매일 전량 리밸런스 가정. 실패해도 파이프라인 비치명.

[2026-09-16 정정] 종전 daily_series 는 신호일 t 의 바구니에 t+1 일간수익을 적용해 '매수 전 하루'를
  수익으로 세고, 점수 없는 날엔 수익률을 ffill 했다(외부 검토로 발견, research/RESEARCH_cross_sim_entry_lag_20260916.md).
  지금은 **보유 상태 기준**으로 계산한다(simulate):
    · 신호일 t(배치, 그날 종가 데이터) → t+1 종가에 교체(ENTRY_LAG=1) → 새 바구니 수익은 t+2 부터.
    · t→t+1 수익은 기존 보유분에 귀속. 신호 없는 날은 보유 유지(수익 복사 없음).
    · 교체 시 종가 없는 종목 몫은 현금. 보유 중 가격 결측(거래정지)은 직전가로 평가(재개 시 재평가).
    · 마지막 날 신호는 진입만 예약, 미실현 구간은 계산하지 않는다. 수정주가(ohlcv close) 전제.
  고정 사례 테스트: tests/test_cross_sim_hold.py
등록일(REG_DATE) 이후 forward 점수만 사용. 패널:
  A = 주력 공통창(v30·lv_a·lv_b·mom_a, 20260702~ — wu_a 는 2026-09-04 은퇴로 제외)
  B = 전 모델 공통창(+sv_a·qs_a, 20260724~)
  C = 신모델 공통창(+px_a, 20260810~ — px_a 등록일 시작. 2026-08-29 추가) ⚠ 창이 짧아 참고 최소한.
      판정 시즌 후 공통창 전체 개편(창 시작 재설정·편입 모델 정리) 예정 — patch_note 20260829 참조.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OHLCV = HERE.parent / "dh-q7m3k-data" / "ohlcv.db"
TOPN = 20

MODELS = [
    ("v30",   "v3_scores",     "final_score_v3", "v30",   "20260606"),
    ("lv_b",  "lowvol_scores", "lowvol_score",   "lv_b",  "20260625"),
    ("lv_a",  "lowvol_scores", "lowvol_score",   "lv_a",  "20260625"),
    ("mom_a", "lowvol_scores", "lowvol_score",   "mom_a", "20260627"),
    ("sv_a",  "wu_scores",     "wu_score",       "sv_a",  "20260715"),
    ("qs_a",  "wu_scores",     "wu_score",       "qs_a",  "20260723"),
    ("px_a",  "wu_scores",     "wu_score",       "px_a",  "20260810"),
    # [2026-09-15] 리더보드 ① 돈 표에 빠져 있던 현역 모델 추가(관측 전용). ls_t1 은 점수 테이블이 없어 아래에서 large_final 로 합성.
    ("mom_b", "lowvol_scores", "lowvol_score",   "mom_b", "20260717"),
    ("lv_e",  "lowvol_scores", "lowvol_score",   "lv_e",  "20260901"),
    ("sv_b",  "wu_scores",     "wu_score",       "sv_b",  "20260914"),
    ("ls_t1", "large_final",   None,             "ls_t1", "20260806"),
]
MIN_DAYS = 10   # 표시 기준: 공통창 유효 거래일 10 미만 모델은 자동 대기(가독성 — 창이 차면 저절로 등장)
# [2026-08-29] 등록일이 창 시작보다 늦은 모델은 그 창에서 제외 — 공백일이 0%로 채워져
#   누적수익 비교가 왜곡되던 문제(px_a 실측: 창 24일 중 실점수 ~14일, "-8.4%p 뒤짐"의
#   대부분이 미등록 기간 0% 앉음 탓). 제외 외 타 모델 수치는 0-diff 검증 완료.
PANELS = [
    # [2026-09-04] wu_a 제거 — 은퇴(적재 중지). 적재가 멈춘 모델은 공백일이 0%로 채워져 창을 왜곡한다.
    ("주력 공통창 (7/02~)", ["v30", "lv_b", "lv_a", "mom_a"], "20260702"),
    ("전 모델 공통창 (7/24~ · 짧음)", ["v30", "lv_b", "lv_a", "mom_a", "mom_b", "sv_a", "qs_a", "px_a"], "20260724"),
    ("신모델 공통창 (8/10~ · 매우 짧음 — 참고 최소한)", ["v30", "lv_b", "lv_a", "mom_a", "mom_b", "sv_a", "qs_a", "px_a", "ls_t1"], "20260810"),
]


ENTRY_LAG = 1   # 신호일 t → t+ENTRY_LAG 종가 교체 (리더보드와 같은 뜻)


def simulate(picks_by_day, close, dts, start, end, cost=0.0):
    """보유 상태 기준 모의계좌. picks_by_day: {거래일 t: [ticker,...] 또는 None}. close: DataFrame(index=date, columns=ticker).
    start~end 사이 신호만 쓴다. 반환: 일별 수익 Series(index=수익이 실현된 날, 첫 값은 첫 진입 다음 날).
    cost: 교체 시 왕복 비용 비율(전량 교체 가정 · 기본 0)."""
    days = [d for d in dts if start <= d <= end]
    if not days:
        return pd.Series(dtype=float)
    idx = {d: i for i, d in enumerate(dts)}
    cols = {c: j for j, c in enumerate(close.columns)}
    P = close.to_numpy(float)
    holdings = {}          # ticker -> 수량
    last_px = {}           # ticker -> 마지막 유효가(거래정지 시 평가용)
    cash = 0.0
    value = 1.0
    entered = False
    pending = None         # (교체 예정일, 종목 리스트)
    out = {}
    for d in dts:
        if d < days[0]:
            continue
        i = idx[d]
        # ① 당일 종가로 평가 (기존 보유 귀속). 오늘 교체가 있으면 교체 비용을 오늘 수익에 반영.
        rebalance_today = pending is not None and pending[0] == d and pending[1] is not None
        if entered:
            v = cash
            for tk, q in holdings.items():
                px = P[i, cols[tk]] if tk in cols else np.nan
                if np.isfinite(px) and px > 0:
                    last_px[tk] = px
                v += q * last_px.get(tk, 0.0)
            if rebalance_today and cost > 0:
                v *= (1.0 - cost)
            out[d] = (v / value - 1.0) if value > 0 else 0.0
            value = v
        # ② 예약된 교체가 오늘이면 종가에 실행
        if pending is not None and pending[0] == d:
            sel = pending[1]; pending = None
            if sel is not None:
                holdings, cash = {}, 0.0
                per = value / max(len(sel), 1)
                for tk in sel:
                    px = P[i, cols[tk]] if tk in cols else np.nan
                    if np.isfinite(px) and px > 0:
                        holdings[tk] = per / px; last_px[tk] = px
                    else:
                        cash += per          # 못 사는 종목 몫은 현금
                entered = True
        # ③ 오늘 신호가 있으면 t+ENTRY_LAG 종가 교체 예약 (기간 안 신호만)
        sel_today = picks_by_day.get(d) if days[0] <= d <= days[-1] else None
        if sel_today:            # 빈 목록(살 수 있는 종목 0)은 신호 없음으로 취급 → 보유 유지
            j = i + ENTRY_LAG
            if j < len(dts):
                pending = (dts[j], picks_by_day[d])
        if d >= days[-1]:        # end 이후 구간은 계산하지 않는다(미실현·범위 밖)
            break
    return pd.Series(out).sort_index()


def picks_by_day_from_scores(df, dts, topn, universe):
    """run_id → 거래일 매핑(비거래일 run 은 직전 거래일; 같은 날 여럿이면 거래일과 같은 run 우선, 없으면 최소)."""
    import bisect
    runs = sorted(df.run_id.astype(str).unique())
    cand = {}
    for run in runs:
        k = bisect.bisect_right(dts, run) - 1
        if k >= 0:
            cand.setdefault(dts[k], []).append(run)
    out = {}
    for day, rs in cand.items():
        run = day if day in rs else min(rs)
        sub = df[df.run_id.astype(str) == run]
        if len(sub) == 0:
            continue
        out[day] = [c for c in sub.nlargest(topn, "s").ticker if c in universe]
    return out


def main():
    hc = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    oc = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    scores = {}
    reg_map = {name: reg for name, tbl, col, mid, reg in MODELS}
    for name, tbl, col, mid, reg in MODELS:
        if col is None:   # ls_t1: leaderboard.py 와 같은 정의 — run 내 ep·bp·rim·dv 백분위 랭크 동일가중 평균(결측 제외, 최소 2개)
            lg = pd.read_sql("SELECT run_id, ticker, per, pbr, rim_spread, div_yield FROM large_final WHERE run_id>=?", hc, params=(reg,))
            fz = pd.DataFrame({"ep": 1.0 / lg["per"].where(lg["per"] > 0), "bp": 1.0 / lg["pbr"].where(lg["pbr"] > 0),
                               "rim": lg["rim_spread"], "dv": lg["div_yield"]})
            rk = fz.groupby(lg["run_id"]).rank(pct=True)
            lg["s"] = rk.mean(axis=1, skipna=True).where(rk.notna().sum(axis=1) >= 2)
            lg["ticker"] = lg["ticker"].astype(str).str.zfill(6)
            scores[name] = lg.loc[lg["s"].notna(), ["run_id", "ticker", "s"]]
            continue
        scores[name] = pd.read_sql(
            f"SELECT run_id, ticker, {col} AS s FROM {tbl} WHERE model_id=? AND run_id>=?",
            hc, params=(mid, reg))
    px = pd.read_sql("SELECT ticker,date,close,volume,change_pct FROM daily_ohlcv "
                     "WHERE date>='20260601'", oc)
    dts = sorted(px.date.unique())
    R = px.pivot_table(index="date", columns="ticker", values="change_pct", aggfunc="last").reindex(dts)
    C = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").reindex(dts)
    V = px.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").reindex(dts)
    amt20 = (C * V).rolling(20, min_periods=10).mean() / 1e8
    K = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSPI'",
                    oc).set_index("date")["close"].reindex(dts).ffill()

    universe = set(C.columns)

    def daily_series(picks, start, end):
        """picks: {거래일: [ticker]} (모델) 또는 callable(t)->[ticker] (벤치마크: 매일 신호)."""
        if callable(picks):
            pmap = {t: list(picks(t)) for t in dts if start <= t <= end}
        else:
            pmap = picks
        return simulate(pmap, C, dts, start, end)

    def stats(s):
        nav = (1 + s).cumprod()
        return dict(cum=round(float(nav.iloc[-1] - 1) * 100, 1),
                    vol=round(float(s.std()) * 100, 2),
                    mdd=round(float((nav / nav.cummax() - 1).min()) * 100, 1),
                    n=int(len(s)))

    panels = []
    end = dts[-1]   # [2026-09-16] simulate 는 마지막 종가까지 실현된 수익만 계산
    for label, group, start in PANELS:
        bench = daily_series(lambda t: amt20.loc[t][amt20.loc[t] >= 5].index.intersection(R.columns),
                             start, end)
        k_days = [d for d in dts if d >= start]
        kospi_cum = round(float(K.iloc[-1] / K.loc[k_days[0]] - 1) * 100, 1)
        rows = []
        for m in group:
            top = picks_by_day_from_scores(scores[m], dts, TOPN, universe)
            if reg_map.get(m, "00000000") > start:
                print(f"  ⏳ {m}: 등록일 {reg_map[m]} > 창 시작 {start} — 창 전체 커버 전 표시 대기")
                continue
            s = daily_series(top, start, end)
            eff = max(0, int((s.index >= reg_map[m]).sum())) if m in reg_map else len(s)
            if eff < MIN_DAYS:
                print(f"  ⏳ {m}: 유효 {eff}거래일 < {MIN_DAYS} — 창이 찰 때까지 표시 대기")
                continue
            st = stats(s)
            common = s.index.intersection(bench.index)
            st["exc_bp"] = round(float((s.reindex(common) - bench.reindex(common)).mean()) * 10000, 1)
            st["model"] = m
            rows.append(st)
        rows.sort(key=lambda r: -r["cum"])
        bench_total = round(float(((1 + bench).cumprod().iloc[-1] - 1) * 100), 1)
        for r in rows:
            r["exc_cum"] = round(r["cum"] - bench_total, 1)   # 시장평균 대비 누적 %p (직관 표시용)
            r["day_avg"] = round(((1 + r["cum"] / 100) ** (1 / max(r["n"], 1)) - 1) * 100, 2)  # 기하 일평균 %
        panels.append(dict(label=label, start=start, end=end,
                           bench_cum=round(float(((1 + bench).cumprod().iloc[-1] - 1) * 100), 1),
                           kospi_cum=kospi_cum, rows=rows))
    # ---- [2026-08-30] trailing: 모델별 최근 1·5·20 수익일 실수익 (사용자 요청 — 실수치 비교) ----
    #   각 모델의 등록일 이후 전체 시리즈에서 끝 N일 누적. 창을 다 못 채우는 모델(신생)은 null.
    #   기존 panels 계산과 완전 분리(값 무접촉).
    kq = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSDAQ'",
                     oc).set_index("date")["close"].reindex(dts).ffill()
    def tail_cum(s, k):
        if s is None or len(s) < k:
            return None
        seg = s.iloc[-k:]
        return round(float(((1 + seg).cumprod().iloc[-1] - 1) * 100), 1)
    full_bench = daily_series(lambda t: amt20.loc[t][amt20.loc[t] >= 5].index.intersection(R.columns),
                              "20260601", end)
    t_rows = []
    for name, tbl, col, mid, reg in MODELS:
        s = daily_series(picks_by_day_from_scores(scores[name], dts, TOPN, universe), reg, end)
        if len(s) == 0:
            continue
        nav = (1 + s).cumprod()
        t_rows.append(dict(model=name, r1=tail_cum(s, 1), r5=tail_cum(s, 5),
                           r20=tail_cum(s, 20), n=int(len(s)),
                           rall=round(float((nav.iloc[-1] - 1) * 100), 1),
                           mdd=round(float((nav / nav.cummax() - 1).min() * 100), 1),
                           since=str(s.index.min())))
    b1, b5, b20 = tail_cum(full_bench, 1), tail_cum(full_bench, 5), tail_cum(full_bench, 20)
    kr = kq.pct_change().dropna()
    trailing = dict(asof=end, rows=t_rows,
                    bench=dict(r1=b1, r5=b5, r20=b20),
                    kosdaq=dict(r1=tail_cum(kr, 1), r5=tail_cum(kr, 5), r20=tail_cum(kr, 20)))
    out = dict(status="ok", generated=datetime.now().isoformat(timespec="seconds"),
               topn=TOPN, panels=panels, trailing=trailing)
    (HERE / "docs" / "cross_sim.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"💾 docs/cross_sim.json 생성 — 패널 {len(panels)}개, 기준일 {end}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠ cross_sim 생성 실패(비치명): {e}")
