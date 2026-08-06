# -*- coding: utf-8 -*-
"""
build_large_test.py — 대형 트랙 '테스트 모델 ls_t1' 점수 페이지 생성 (로컬 전용)
==============================================================================
★ 테스트·관측 전용 — 매수신호 아님. 산출물은 docs/_large_test.html —
  _large_obs.html 과 같은 '메인/필터 미링크 비공개 경로' 컨벤션(텔레그램에서만 링크).
  정식 판정은 h=60/120d(§9, 9월~) — leaderboard(large 트랙)가 정본.

ls_t1 스펙(동결 — PREREGISTER_ls_t1.md):
  run 내 ep(1/PER)·bp(1/PBR)·rim_spread·div_yield 의 백분위 랭크 **동일가중 평균**
  (결측 팩터 제외, 최소 2개 필요). 가중치 탐색 없음(매직넘버 금지 — 동일가중 고정).
  large_final 은 run별 동결 적재이므로 점수는 언제 재계산해도 동일(PIT 재현 가능).

표시 IC는 in-sample(등록 20260806 이전 백필 포함) — '증거'가 아니라 '가설' 수치.
등록 이후 OOS 판정은 leaderboard.py(large 트랙)가 정본.

실행:  python build_large_test.py            # 최신 run
       python build_large_test.py --run-id 20260805
"""
import argparse
import html as _h
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DB = HERE / "history.db"
OUT = HERE / "docs" / "_large_test.html"

FACTORS = {"ep": "1/PER", "bp": "1/PBR", "rim": "RIM스프레드", "dv": "배당수익률"}


def build_scores(con):
    lg = pd.read_sql(
        "SELECT run_id, run_timestamp, market, ticker, name, close, marcap, sector, "
        "per, pbr, rim_spread, div_yield, roe_value, quality_gate, is_holding, "
        "is_financial, is_cyclical, foreign_20d, inst_20d FROM large_final", con)
    lg["ticker"] = lg["ticker"].astype(str)
    f = pd.DataFrame(index=lg.index)
    f["ep"] = 1.0 / lg["per"].where(lg["per"] > 0)
    f["bp"] = 1.0 / lg["pbr"].where(lg["pbr"] > 0)
    f["rim"] = lg["rim_spread"]
    f["dv"] = lg["div_yield"]
    r = f.groupby(lg["run_id"]).rank(pct=True)
    lg[[f"r_{c}" for c in FACTORS]] = r[list(FACTORS)]
    lg["ls_t1"] = r.mean(axis=1).where(r.notna().sum(axis=1) >= 2)
    return lg


def insample_ic(lg, horizons=(10, 20)):
    """in-sample 참고 IC(전 run·백필 포함 — 증거 아님). ohlcv.db 없으면 None."""
    ohlcv = HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"
    if not ohlcv.exists():
        return None
    con = sqlite3.connect(f"file:{ohlcv}?mode=ro", uri=True)
    px = pd.read_sql("SELECT ticker,date,close FROM daily_ohlcv", con)
    con.close()
    close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    dates = list(close.index)
    didx = {d: i for i, d in enumerate(dates)}
    out = {}
    for h in horizons:
        ics = []
        for rid, g in lg.dropna(subset=["ls_t1"]).groupby("run_id"):
            t = didx.get(str(rid))
            if t is None or t + 1 + h >= len(dates):
                continue
            fwd = close.iloc[t + 1 + h] / close.iloc[t + 1] - 1
            s = g.set_index("ticker")["ls_t1"]
            b = fwd.reindex(s.index)
            m = s.notna() & b.notna()
            if m.sum() < 30:
                continue
            ics.append(float(np.corrcoef(s[m].rank(), b[m].rank())[0, 1]))
        if len(ics) >= 3:
            a = np.array(ics)
            rng = np.random.default_rng(7)
            bo = [rng.choice(a, len(a)).mean() for _ in range(2000)]
            out[h] = dict(ic=float(a.mean()), n=len(a),
                          ci=(float(np.percentile(bo, 2.5)), float(np.percentile(bo, 97.5))))
    return out


def render(g, rid, ts, ic):
    rows = []
    g = g.sort_values("ls_t1", ascending=False).reset_index(drop=True)
    for i, x in g.iterrows():
        if pd.isna(x["ls_t1"]):
            continue
        flags = "".join([
            "<span class=flag>지주</span>" if x["is_holding"] else "",
            "<span class=flag>금융</span>" if x["is_financial"] else "",
            "<span class=flag>시클</span>" if x["is_cyclical"] else "",
        ])
        gate = "<span class=ok>통과</span>" if x["quality_gate"] else "<span class=ng>미통과</span>"
        def pct(v):
            return f"{v*100:.0f}" if pd.notna(v) else "·"
        def flow(v):
            if pd.isna(v):
                return "<td>·</td>"
            cls = "pos" if v > 0 else ("neg" if v < 0 else "")
            return f"<td class='{cls}'>{v:+,.0f}</td>"
        rows.append(
            f"<tr><td>{i+1}</td><td class=nm>{_h.escape(str(x['name']))} "
            f"<span class=tk>{x['ticker']}</span></td><td>{x['market']}</td>"
            f"<td>{x['marcap']/1e12:.1f}조</td>"
            f"<td class=sc><b>{x['ls_t1']*100:.1f}</b></td>"
            f"<td>{pct(x['r_ep'])}</td><td>{pct(x['r_bp'])}</td>"
            f"<td>{pct(x['r_rim'])}</td><td>{pct(x['r_dv'])}</td>"
            f"<td>{gate}</td><td>{flags or '·'}</td>"
            + flow(x["foreign_20d"]) + flow(x["inst_20d"])
            + f"<td class=sec>{_h.escape(str(x['sector'] or '·'))}</td></tr>")
    ic_txt = "산출 불가(ohlcv.db 없음)"
    if ic:
        ic_txt = " · ".join(
            f"h{h}: IC {v['ic']:+.3f} [{v['ci'][0]:+.3f},{v['ci'][1]:+.3f}] n={v['n']}"
            for h, v in sorted(ic.items()))
    return f"""<!doctype html><html lang=ko><meta charset=utf-8>
<title>ls_t1 테스트 점수 — {rid} (관측·검증 전)</title>
<style>
 body{{background:#12151c;color:#cfd6e4;font:14px/1.5 'IBM Plex Sans KR',sans-serif;margin:24px}}
 .warn{{background:#3a2b12;border:1px solid #8a6d2f;color:#e8c77a;padding:12px 16px;border-radius:8px;margin-bottom:16px}}
 .meta{{color:#8b93a7;font-size:12px;margin-bottom:16px}}
 table{{border-collapse:collapse;width:100%;font-size:13px}}
 th,td{{padding:5px 8px;border-bottom:1px solid #232837;text-align:right;white-space:nowrap}}
 th{{color:#8b93a7;position:sticky;top:0;background:#12151c}}
 td.nm{{text-align:left}} .tk{{color:#5c6478;font-size:11px}} td.sec{{text-align:left;color:#8b93a7}}
 td.sc{{color:#7db3ff}} .ok{{color:#69c98a}} .ng{{color:#8b93a7}}
 .pos{{color:#69c98a}} .neg{{color:#e06c75}}
 .flag{{background:#232837;border-radius:4px;padding:1px 5px;margin-left:3px;font-size:11px;color:#a8b0c2}}
</style>
<div class=warn>⚠️ <b>ls_t1 — 테스트 모델(관측·검증 전)</b> · 매수신호 아님 · 정식 판정 h=60/120d(9월~) ·
동일가중 랭크 스펙 동결(PREREGISTER_ls_t1.md) · 이 파일은 로컬 전용(docs/ 공개 금지)</div>
<div class=meta>run {rid} ({ts}) · in-sample 참고 IC(백필 포함 — <b>증거 아님</b>): {ic_txt}
· OOS 판정 정본: leaderboard(large 트랙, 등록 20260806)</div>
<table><tr><th>#</th><th>종목</th><th>시장</th><th>시총</th><th>ls_t1</th>
<th>1/PER%</th><th>1/PBR%</th><th>RIM%</th><th>배당%</th>
<th>품질게이트</th><th>플래그</th><th>외인20d(억)</th><th>기관20d(억)</th><th>업종</th></tr>
{''.join(rows)}</table></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=None)
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    lg = build_scores(con)
    con.close()
    rid = a.run_id or lg["run_id"].max()
    g = lg[lg["run_id"] == rid]
    if g.empty:
        print(f"run {rid} 없음"); return
    ic = insample_ic(lg)
    OUT.write_text(render(g, rid, str(g['run_timestamp'].iloc[0])[:16], ic), encoding="utf-8")
    n = g["ls_t1"].notna().sum()
    print(f"[large_test] {OUT.name} 생성 — run {rid}, 점수 산출 {n}종목")
    top = g.sort_values('ls_t1', ascending=False).head(10)
    for _, x in top.iterrows():
        print(f"  {x['name']:12s} {x['ticker']} ls_t1={x['ls_t1']*100:.1f} gate={'O' if x['quality_gate'] else '·'}")


if __name__ == "__main__":
    main()
