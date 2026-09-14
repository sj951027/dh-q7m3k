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
        "is_financial, is_cyclical, foreign_20d, inst_20d, marcap_rank, rim_quadrant FROM large_final", con)
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


def flows_5d(rid, tickers):
    """[2026-09-14] 표시 전용: KIS daily_flows(ohlcv.db, 읽기 전용)에서 run_id 이하 최근 5거래일 외인·기관 순매수(수량×종가) 합(억) — 스크리너 foreign_5d_억 과 같은 정의.
    없으면 빈 표(열은 · 로 표시). 점수·판정 무관."""
    ohlcv = HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"
    if not ohlcv.exists():
        return pd.DataFrame(columns=["ticker", "foreign_5d", "inst_5d"])
    try:
        con = sqlite3.connect(f"file:{ohlcv}?mode=ro", uri=True)
        days = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily_flows WHERE date<=? ORDER BY date DESC LIMIT 5", (str(rid),))]
        if not days:
            con.close(); return pd.DataFrame(columns=["ticker", "foreign_5d", "inst_5d"])
        q = ("SELECT ticker, SUM(foreign_net_qty*close)/1e8 AS foreign_5d, SUM(inst_net_qty*close)/1e8 AS inst_5d FROM daily_flows "
             f"WHERE date IN ({','.join('?' * len(days))}) GROUP BY ticker")
        f = pd.read_sql(q, con, params=days); con.close()
        f["ticker"] = f["ticker"].astype(str).str.zfill(6)
        return f[f["ticker"].isin(set(tickers))]
    except Exception as e:
        print(f"   ⚠️ 5일 수급 로드 실패(표시만 생략): {str(e)[:80]}")
        return pd.DataFrame(columns=["ticker", "foreign_5d", "inst_5d"])


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
            f"<tr class=r data-ls='{x['ls_t1']:.4f}' data-ep='{(x['r_ep'] if pd.notna(x['r_ep']) else -1):.4f}' data-rim='{(x['r_rim'] if pd.notna(x['r_rim']) else -1):.4f}' "
            f"data-gate='{1 if x['quality_gate'] else 0}' data-mr='{int(x['marcap_rank']) if pd.notna(x['marcap_rank']) else 0}' data-rq='{1 if x['rim_quadrant']==1 else 0}' "
            f"data-fin='{1 if x['is_financial'] else 0}' data-hold='{1 if x['is_holding'] else 0}'>"
            f"<td class=no>{i+1}</td><td class=nm>{_h.escape(str(x['name']))} "
            f"<span class=tk>{x['ticker']}</span></td><td>{x['market']}</td>"
            f"<td>{x['marcap']/1e12:.1f}조</td>"
            f"<td class=sc><b>{x['ls_t1']*100:.1f}</b></td>"
            f"<td>{pct(x['r_ep'])}</td><td>{pct(x['r_bp'])}</td>"
            f"<td>{pct(x['r_rim'])}</td><td>{pct(x['r_dv'])}</td>"
            f"<td>{gate}</td><td>{flags or '·'}</td>"
            + flow(x.get("foreign_5d", float("nan"))) + flow(x.get("inst_5d", float("nan")))
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
 .memo{{background:#151a24;border:1px solid #2a3550;border-radius:8px;padding:10px 14px;margin-bottom:12px;line-height:1.6}} .memo ul{{margin:6px 0 6px 18px;padding:0}} .memo li{{margin:2px 0}}
 .fbar{{background:#171b25;border:1px solid #232837;border-radius:8px;padding:10px 14px;margin-bottom:12px;line-height:2}} .fbar label{{margin-right:10px}} .fbar select,.fbar input{{background:#0f1218;color:#cfd6e4;border:1px solid #2a3040;border-radius:4px;padding:2px 6px}} .note{{color:#8b93a7;font-size:12px}}
 .flag{{background:#232837;border-radius:4px;padding:1px 5px;margin-left:3px;font-size:11px;color:#a8b0c2}}
</style>
<div class=warn>⚠️ <b>ls_t1 — 테스트 모델(관측·검증 전)</b> · 매수신호 아님 · 정식 판정 h=60/120d(9월~) ·
동일가중 랭크 스펙 동결(PREREGISTER_ls_t1.md) · 이 파일은 로컬 전용(docs/ 공개 금지)</div>
<div class=meta>run {rid} ({ts}) · in-sample 참고 IC(백필 포함 — <b>증거 아님</b>): {ic_txt}
· OOS 판정 정본: leaderboard(large 트랙, 등록 20260806)</div>
<div class=memo><b>📝 어떤 걸 고르는 게 좋았나 — 관측 메모 (2026-09-14 실측, 판정 아님)</b><div class=note>기간 6/10~9/11(약 3개월, 대형 가치주 강세 국면 하나). 앵커가 매일 겹쳐 신뢰구간은 실제보다 좁음. 등록(8/06) 전 자료 포함. 다른 국면에서도 그런지는 3년 자료를 받아야 알 수 있음.</div><ul><li><b>집중이 낫다</b>: 상위 5 &gt; 상위 10 &gt; 상위 20·30 (20일 기준 상위5 가 상위10 보다 +0.8%p, 40일 +1.3%p).</li><li><b>품질게이트는 걸지 않는 게 나았다</b>: 통과 종목만 고르면 −1.6%p(20일)·−4.7%p(40일). 싸고 실적이 도는 종목이 질 좋은 종목보다 올랐던 시기.</li><li><b>초대형은 별로</b>: 시총 상위 100 안만 고르면 −2.0%p. 101~500위가 +0.7~1.0%p.</li><li><b>RIM 사분면 1 이 일관되게 좋았다</b>: +1.5%p(20일)·+1.9%p(40일)·등록 후 +2.3%p.</li><li><b>업종 분산은 손해</b>: 업종당 최대 2로 나누면 −0.7~−1.4%p.</li><li><b>단독 팩터가 합성보다 나았다</b>: RIM 단독 상위10 +2.5/+4.5%p, 1/PER 단독 +2.2/+3.9%p. 반대로 1/PBR·배당 단독은 합성보다 나쁨.</li><li><b>가장 나았던 조합</b>: <u>RIM(또는 1/PER) 단독 정렬 · 시총 101~500 · RIM 사분면 1 · 상위 10</u> → 합성 상위10 대비 20일 +4.6%p, 40일 +9.2%p, 등록 후 +6.3%p. 전반·후반 모두 양수. 위 필터로 재현 가능.</li><li><b>상위 50 안에서는</b> 저PBR·고배당·전년 대비 이익 증가·외인 20일 순매수 양수가 더 갔고, 현금흐름·ROE 좋은 종목은 뒤처짐.</li></ul><div class=note>스펙(4팩터 동일가중)은 동결이라 ls_t1 자체는 바꾸지 않음. 바꾸려면 새 model_id(ls_t2)로 사전등록. 근거: research/RESEARCH_ls_t1_selection_rules_20260914.md · RESEARCH_ls_t1_top_decile_20260914.md · RESEARCH_ls_t1_filter_combo_20260914.md</div></div>
<div class=fbar><b>관측용 필터</b> <span class=note>— 매수신호 아님 · 근거 research/RESEARCH_ls_t1_selection_rules_20260914.md (참고 기간, 판정 아님)</span><br>정렬 <select id=fsort><option value=ls>합성 ls_t1</option><option value=ep>1/PER 단독</option><option value=rim>RIM 단독</option></select> <label><input type=checkbox id=fgate> 품질게이트 통과만</label> <label><input type=checkbox id=fmr> 시총 101~500위만</label> <label><input type=checkbox id=frq> RIM 사분면 1만</label> <label><input type=checkbox id=ffin> 금융·지주 제외</label> 상위 <input type=number id=ftop value=50 min=1 max=500 style="width:56px"> 개 <span id=fcount class=note></span></div>
<table><tr><th>#</th><th>종목</th><th>시장</th><th>시총</th><th>ls_t1</th>
<th>1/PER%</th><th>1/PBR%</th><th>RIM%</th><th>배당%</th>
<th>품질게이트</th><th>플래그</th><th>외인5d(억)</th><th>기관5d(억)</th><th>외인20d(억)</th><th>기관20d(억)</th><th>업종</th></tr>
{''.join(rows)}</table>
<script>
(function(){{
  const $=id=>document.getElementById(id); const rows=[...document.querySelectorAll("tr.r")]; const tb=rows[0]&&rows[0].parentNode;
  function apply(){{ const key=$("fsort").value, top=+$("ftop").value||500;
    const keep=rows.filter(r=>(!$("fgate").checked||r.dataset.gate==="1")&&(!$("fmr").checked||(+r.dataset.mr>100&&+r.dataset.mr<=500))&&(!$("frq").checked||r.dataset.rq==="1")&&(!$("ffin").checked||(r.dataset.fin==="0"&&r.dataset.hold==="0")));
    keep.sort((a,b)=>(+b.dataset[key])-(+a.dataset[key]));
    rows.forEach(r=>r.style.display="none"); keep.forEach((r,i)=>{{ r.style.display=i<top?"":"none"; r.querySelector("td.no").textContent=i+1; tb.appendChild(r); }});
    $("fcount").textContent="조건 충족 "+keep.length+"개 중 "+Math.min(top,keep.length)+"개 표시"; }}
  ["fsort","fgate","fmr","frq","ffin","ftop"].forEach(id=>$(id).addEventListener("change",apply)); apply();
}})();
</script></html>"""


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
    f5 = flows_5d(rid, g["ticker"].astype(str).str.zfill(6))
    g = g.assign(_tk=g["ticker"].astype(str).str.zfill(6)).merge(f5, left_on="_tk", right_on="ticker", how="left", suffixes=("", "_f5")).drop(columns=["_tk", "ticker_f5"], errors="ignore")
    ic = insample_ic(lg)
    OUT.write_text(render(g, rid, str(g['run_timestamp'].iloc[0])[:16], ic), encoding="utf-8")
    n = g["ls_t1"].notna().sum()
    print(f"[large_test] {OUT.name} 생성 - run {rid}, 점수 산출 {n}종목")
    top = g.sort_values('ls_t1', ascending=False).head(10)
    for _, x in top.iterrows():
        print(f"  {x['name']:12s} {x['ticker']} ls_t1={x['ls_t1']*100:.1f} gate={'O' if x['quality_gate'] else '·'}")


if __name__ == "__main__":
    main()
