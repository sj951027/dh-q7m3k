# -*- coding: utf-8 -*-
"""
build_cross_sim.py — 트랙 간 '공통 잣대' 모의계좌 → docs/cross_sim.json (표시 전용)
====================================================================================
리더보드 하단 '공통 잣대 모의계좌' 섹션의 데이터 생성기 (2026-08-14 사용자 결정).
원리(research/cross_track_compare.py와 동일): 같은 기간 · 매일 점수 상위 20 동일가중 ·
ENTRY_LAG=1 · 공통 벤치마크(전체상장 거래대금≥5억 EW, KOSPI 병기)로 모의 계좌 비교.

⚠ 관측 전용 — §11 판정과 무관(판정 도구 leaderboard.py 는 일절 안 건드림).
  거래비용 0 · 매일 전량 리밸런스 가정. 실패해도 파이프라인 비치명.
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
]
MIN_DAYS = 10   # 표시 기준: 공통창 유효 거래일 10 미만 모델은 자동 대기(가독성 — 창이 차면 저절로 등장)
# [2026-08-29] 등록일이 창 시작보다 늦은 모델은 그 창에서 제외 — 공백일이 0%로 채워져
#   누적수익 비교가 왜곡되던 문제(px_a 실측: 창 24일 중 실점수 ~14일, "-8.4%p 뒤짐"의
#   대부분이 미등록 기간 0% 앉음 탓). 제외 외 타 모델 수치는 0-diff 검증 완료.
PANELS = [
    # [2026-09-04] wu_a 제거 — 은퇴(적재 중지). 적재가 멈춘 모델은 공백일이 0%로 채워져 창을 왜곡한다.
    ("주력 공통창 (7/02~)", ["v30", "lv_b", "lv_a", "mom_a"], "20260702"),
    ("전 모델 공통창 (7/24~ · 짧음)", ["v30", "lv_b", "lv_a", "mom_a", "sv_a", "qs_a", "px_a"], "20260724"),
    ("신모델 공통창 (8/10~ · 매우 짧음 — 참고 최소한)", ["v30", "lv_b", "lv_a", "mom_a", "sv_a", "qs_a", "px_a"], "20260810"),
]


def main():
    hc = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    oc = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    scores = {}
    reg_map = {name: reg for name, tbl, col, mid, reg in MODELS}
    for name, tbl, col, mid, reg in MODELS:
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

    def daily_series(fn_top, start, end):
        out = []
        for t in [d for d in dts if start <= d <= end]:
            i = dts.index(t)
            if i + 1 >= len(dts):
                continue
            nxt = dts[i + 1]
            sel = fn_top(t)
            if sel is None:
                out.append((nxt, np.nan))
            else:
                out.append((nxt, float(R.loc[nxt, sel].astype(float).mean(skipna=True))))
        s = pd.Series(dict(out)).sort_index()
        return s.ffill(limit=2).fillna(0)

    def stats(s):
        nav = (1 + s).cumprod()
        return dict(cum=round(float(nav.iloc[-1] - 1) * 100, 1),
                    vol=round(float(s.std()) * 100, 2),
                    mdd=round(float((nav / nav.cummax() - 1).min()) * 100, 1),
                    n=int(len(s)))

    panels = []
    end = dts[-2]
    for label, group, start in PANELS:
        bench = daily_series(lambda t: amt20.loc[t][amt20.loc[t] >= 5].index.intersection(R.columns),
                             start, end)
        k_days = [d for d in dts if d >= start]
        kospi_cum = round(float(K.iloc[-1] / K.loc[k_days[0]] - 1) * 100, 1)
        rows = []
        for m in group:
            df = scores[m]

            def top(t, df=df):
                sub = df[df.run_id == t]
                if len(sub) == 0:
                    return None
                return [c for c in sub.nlargest(TOPN, "s").ticker if c in R.columns]
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
        def top_t(t, df=scores[name]):
            sub = df[df.run_id == t]
            if len(sub) == 0:
                return None
            return [c for c in sub.nlargest(TOPN, "s").ticker if c in R.columns]
        s = daily_series(top_t, reg, end)
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
