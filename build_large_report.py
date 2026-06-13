# -*- coding: utf-8 -*-
"""
build_large_report.py — 대형 가치주 트랙 '관측 리포트' HTML 생성 (로컬 전용)
==============================================================================
history.db의 large_final 최신 run을 읽어 self-contained HTML(large_report.html)을
만든다. 더블클릭으로 열람. 네트워크 0, v3 무접촉(읽기 전용).

★ 이것은 '추천 화면'이 아니다 — 설계 §6의 공개 탭(docs/large.html)은 §9 검증
  (h=60/120d, 9월~) 이후에만 노출한다. 이 리포트는 그 전까지의 '관측 데이터 점검'
  용도라서 의도적으로 다음을 지킨다:
    - 종합 점수 없음(존재하지도 않음), 값에 등락색 없음, 기본 정렬 = 시총순.
    - 모든 화면 요소에 '관측·검증 전' 라벨.
    - 산출 파일은 repo 루트(.gitignore 등록) — docs/(공개 Pages)에 두지 않는다.

실행:  python build_large_report.py            # 최신 run
       python build_large_report.py --run-id 20260611
"""
import argparse
import html
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from large_score import QUALITY_OCF_LO, QUALITY_OCF_HI   # 게이트 구간(단일 출처)

DB_PATH = Path("history.db")
OUT = Path("large_report.html")
UNIVERSE_N = 300
JUDGE_DAYS = (60, 120)          # §9 검증 호라이즌(거래일)


def load(db_path, run_id=None):
    con = sqlite3.connect(db_path)
    try:
        rid = run_id or con.execute("SELECT MAX(run_id) FROM large_final").fetchone()[0]
        if not rid:
            raise RuntimeError("large_final 비어 있음 — large_score.py 먼저 실행")
        df = pd.read_sql("SELECT * FROM large_final WHERE run_id=? ORDER BY marcap_rank",
                         con, params=(str(rid),))
        n_runs = con.execute("SELECT COUNT(DISTINCT run_id) FROM large_final").fetchone()[0]
        runs = [r[0] for r in con.execute(
            "SELECT DISTINCT run_id FROM large_final ORDER BY run_id")]
        flows = None
        if con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_flows'").fetchone():
            flows = con.execute(
                "SELECT COUNT(DISTINCT date), COUNT(DISTINCT ticker), MIN(date), MAX(date) "
                "FROM daily_flows").fetchone()
        # 시총·순위 변화(②) — large_universe의 '직전 run' 대비. 점수 아님, 사실 표시.
        # 직전 run = 현재 run 미만의 가장 큰 run_id (자정경계·결손 run 안전).
        prev = con.execute(
            "SELECT MAX(run_id) FROM large_universe WHERE run_id < ?", (str(rid),)).fetchone()[0]
        prev_df = None
        if prev:
            prev_df = pd.read_sql(
                "SELECT ticker, marcap AS marcap_prev, marcap_rank AS rank_prev "
                "FROM large_universe WHERE run_id=?", con, params=(str(prev),))
    finally:
        con.close()
    if prev_df is not None and len(prev_df):
        df = df.merge(prev_df, on="ticker", how="left")
        df["mc_chg_pct"] = (df["marcap"] / df["marcap_prev"] - 1) * 100
        df["rank_chg"] = df["rank_prev"] - df["marcap_rank"]   # +면 순위 상승(숫자 작아짐)
    else:
        df["mc_chg_pct"] = pd.NA
        df["rank_chg"] = pd.NA
    return str(rid), df, n_runs, runs, flows, (prev if prev_df is not None else None)


def fmt(v, pat="{:.2f}", dash="·"):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return dash
    return pat.format(v)


def build_html(rid, df, n_runs, runs, flows, prev_run=None):
    u = df[df["marcap_rank"] <= UNIVERSE_N]
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── 수집 현황 ──────────────────────────────────────────────
    cov = {
        "PBR": int(u["pbr"].notna().sum()),
        "ROE": int(u["roe_value"].notna().sum()),
        "RIM 스프레드": int(u["rim_spread"].notna().sum()),
        "배당>0": int((u["div_yield"] > 0).sum()),
        "자사주 플래그": int(u["buyback_cancel_flag"].notna().sum()),
        "OCF(품질)": int(u["ocf_to_op_ratio"].notna().sum()),
    }
    quad = int(u["rim_quadrant"].sum()) if u["rim_quadrant"].notna().any() else 0
    g1, g0 = int((u["quality_gate"] == 1).sum()), int((u["quality_gate"] == 0).sum())
    flows_txt = (f"{flows[0]}거래일 · {flows[1]}종목 ({flows[2]}~{flows[3]})"
                 if flows and flows[0] else "수집 시작 전 (kis_flows 가동 후 누적)")
    q = u["rim_spread"].quantile([0.25, 0.5, 0.75])

    # ── 타임라인 레일 (시그니처: '아직 판정 전'을 시각화) ──────────
    prog = n_runs
    rail_w = 760
    def x(d): return int(rail_w * min(d, JUDGE_DAYS[1]) / JUDGE_DAYS[1])
    rail = f"""
    <div class="rail-wrap">
      <div class="rail"><div class="rail-fill" style="width:{x(prog)}px"></div>
        <div class="tick" style="left:{x(JUDGE_DAYS[0])}px"><span>60일<br>1차 IC</span></div>
        <div class="tick" style="left:{x(JUDGE_DAYS[1])}px"><span>120일<br>판정</span></div>
        <div class="now" style="left:{x(prog)}px"><span>관측 {prog}일째</span></div>
      </div>
      <p class="rail-note">§9 사전등록: h=60/120 거래일 전의 모든 수치는 노이즈로 간주한다. 첫 판정 가능 시점 ≈ 9월.</p>
    </div>"""

    # ── 업종 구성 미니바 ──────────────────────────────────────
    sec = u["sector"].value_counts().head(10)
    mx = int(sec.max()) if len(sec) else 1
    sec_rows = "".join(
        f'<tr><td>{html.escape(str(s))}</td><td class="num">{n}</td>'
        f'<td class="bar"><i style="width:{int(100*n/mx)}%"></i></td></tr>'
        for s, n in sec.items())

    # ── 종목 원장 ─────────────────────────────────────────────
    # RIM 스프레드 백분위: 분석 유니버스(rank≤N) 내 단일 팩터 위치 설명 — 합성 점수 아님
    sp = u["rim_spread"].dropna()
    def pct_top(v):
        if pd.isna(v) or len(sp) == 0:
            return None
        return max(1, int(round(100 * (sp > v).mean() + 0.0)))  # 상위 X%
    rows = []
    for _, r in df.iterrows():
        labels = [lab for flag, lab in (
            (r["is_pref"], "우선주"), (r["is_financial"], "금융"),
            (r["is_holding"], "지주"), (r["is_reit"], "리츠"),
            (r["is_cyclical"], "시클리컬")) if flag]
        flags = "".join(f"<span class='fb'>{l}</span>" for l in labels)
        bb = {1.0: "소각", 0.0: "—"}.get(r["buyback_cancel_flag"], "·")
        ocf = r["ocf_to_op_ratio"]
        # 품질 게이트 — §4③ 객관 구간이라 색 부여(통과 초록 / 탈락↓ 빨강 / 탈락↑ 주황)
        if pd.isna(ocf):
            gate, gcls = "·", ""
        elif r["quality_gate"] == 1:
            gate, gcls = "통과", " g-ok"
        elif ocf < QUALITY_OCF_LO:
            gate, gcls = "탈락↓", " g-bad"      # 현금 미유입 — 밸류트랩 경계
        else:
            gate, gcls = "탈락↑", " g-warn"     # 일회성·왜곡 의심
        in_u = r["marcap_rank"] <= UNIVERSE_N
        # 구조적 경고(사실, 주장 아님): 진짜 자본잠식(BPS<=0)만. 단순 EPS 무자료는
        # 경고가 아니라 '·'로 — 멀쩡한 회사를 부실로 오인시키지 않도록(색 원칙 준수).
        cls = []
        if not in_u:
            cls.append("ext")
        bps = r.get("bps")
        if pd.notna(bps) and bps <= 0:
            cls.append("warn-row")
        ext = f' class="{" ".join(cls)}"' if cls else ""
        p = pct_top(r["rim_spread"]) if in_u else None
        # 사분면 ◆ — ROE>10%&PBR<1 (§4① 객관 조건) → 초록 배지
        quad = " <span class='quad-on'>◆</span>" if r["rim_quadrant"] == 1 else ""
        sp_cell = (f"{fmt(r['rim_spread'], '{:+.2f}')}{quad}"
                   + (f" <span class='pct'>상위{p}%</span>" if p is not None else ""))
        # 수급 관측(20일 부호·임시, 리버설 아님) — 결측 크고 검증 전이라 색 없이 중립 표기
        spp = r.get("supply20_pos")
        if pd.isna(spp):
            sup = "·"
        else:
            net = r.get("supply20_net")
            sup = (f"▲ {fmt(net, '{:.0f}')}" if spp == 1 else f"▽ {fmt(net, '{:.0f}')}")
        # ② 시총·순위 변화 (직전 run 대비) — 사실 표시. 모멘텀 신호 아님, 색 없음.
        mc = r.get("mc_chg_pct")
        mc_cell = "·" if pd.isna(mc) else (f"▲{mc:.1f}" if mc > 0 else (f"▽{mc:.1f}" if mc < 0 else "0.0"))
        rk = r.get("rank_chg")
        rk_cell = "·" if pd.isna(rk) else (f"▲{int(rk)}" if rk > 0 else (f"▽{int(abs(rk))}" if rk < 0 else "—"))
        rows.append(
            f"<tr{ext}><td class='num'>{int(r['marcap_rank'])}</td>"
            f"<td>{html.escape(str(r['name']))} <span class='tk'>{r['ticker']}</span>{flags}</td>"
            f"<td>{html.escape(str(r['sector']))}</td>"
            f"<td class='num'>{fmt(r['marcap']/1e12, '{:.1f}')}</td>"
            f"<td class='num'>{fmt(r['pbr'])}</td>"
            f"<td class='num'>{fmt(r['roe_value'], '{:.1f}')}</td>"
            f"<td class='num'>{fmt(r['rim_fair_pbr'])}</td>"
            f"<td class='num sp'>{sp_cell}</td>"
            f"<td class='num'>{fmt(r['div_yield'], '{:.1f}')}</td>"
            f"<td class='num'>{bb}</td>"
            f"<td class='num'>{fmt(r['ocf_to_op_ratio'])}</td>"
            f"<td class='num{gcls}'>{gate}</td>"
            f"<td class='num'>{sup}</td>"
            f"<td class='num'>{mc_cell}</td>"
            f"<td class='num'>{rk_cell}</td></tr>")
    table_rows = "\n".join(rows)

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>대형 가치 트랙 — 관측 리포트 {rid}</title>
<style>
:root {{ --ink:#16202B; --paper:#FCFCF9; --line:#D9DCD6; --indigo:#2D4F8F;
        --amber:#8A5F14; --amber-bg:#FBF3E2; --mut:#6B7280; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink);
  font:15px/1.55 Pretendard,'Noto Sans KR','Malgun Gothic',system-ui,sans-serif; }}
.wrap {{ max-width:1180px; margin:0 auto; padding:34px 26px 80px; }}
header h1 {{ font-size:27px; letter-spacing:-.4px; margin:0; font-weight:800; }}
header .sub {{ color:var(--mut); margin-top:4px; font-size:13.5px; }}
.badge {{ display:inline-block; background:var(--amber-bg); color:var(--amber);
  border:1px solid #E3CFA0; border-radius:3px; padding:2px 9px; font-size:12.5px;
  font-weight:700; letter-spacing:.4px; vertical-align:3px; margin-left:10px; }}
.notice {{ border-left:3px solid var(--amber); background:var(--amber-bg);
  padding:10px 14px; margin:20px 0 0; font-size:13.5px; color:#5A431A; }}
.rail-wrap {{ margin:30px 0 6px; }}
.rail {{ position:relative; height:6px; width:{rail_w}px; max-width:100%;
  background:#ECEEE9; border-radius:3px; }}
.rail-fill {{ position:absolute; left:0; top:0; height:6px; background:var(--indigo);
  border-radius:3px; }}
.tick {{ position:absolute; top:-5px; width:1px; height:16px; background:var(--ink); }}
.tick span {{ position:absolute; top:18px; left:-18px; width:60px; font-size:11px;
  color:var(--mut); text-align:center; line-height:1.25; }}
.now {{ position:absolute; top:-7px; width:9px; height:9px; margin-left:-4px;
  background:var(--indigo); border:2px solid var(--paper); border-radius:50%; }}
.now span {{ position:absolute; top:-22px; left:-28px; width:90px; font-size:11.5px;
  color:var(--indigo); font-weight:700; text-align:center; }}
.rail-note {{ font-size:12.5px; color:var(--mut); margin-top:34px; }}
h2 {{ font-size:15px; letter-spacing:.6px; color:var(--indigo); margin:36px 0 10px;
  text-transform:uppercase; }}
h2::before {{ content:""; display:inline-block; width:18px; height:1px;
  background:var(--indigo); vertical-align:4px; margin-right:8px; }}
.stats {{ display:flex; flex-wrap:wrap; gap:0; border-top:1px solid var(--line);
  border-bottom:1px solid var(--line); }}
.stat {{ flex:1 1 150px; padding:12px 14px 11px; border-right:1px solid var(--line); }}
.stat:last-child {{ border-right:0; }}
.stat b {{ display:block; font-size:20px; font-variant-numeric:tabular-nums; }}
.stat span {{ font-size:12px; color:var(--mut); }}
table {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
.ledger {{ table-layout:fixed; }}
.ledger td {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.ledger td:nth-child(2) {{ white-space:normal; overflow:visible; }}
.mini td {{ padding:4px 10px 4px 0; }}
.mini .bar {{ width:240px; }} .mini .bar i {{ display:block; height:7px;
  background:#C7D2E8; }}
.ledger th {{ text-align:right; font-size:12px; color:var(--mut); font-weight:600;
  border-bottom:1.5px solid var(--ink); padding:7px 8px; cursor:pointer;
  white-space:nowrap; user-select:none; }}
.ledger th:nth-child(2), .ledger th:nth-child(3) {{ text-align:left; }}
.ledger td {{ border-bottom:1px solid var(--line); padding:6px 8px;
  font-variant-numeric:tabular-nums; }}
.ledger td.num {{ text-align:right;
  font-family:ui-monospace,'Cascadia Mono',Consolas,monospace; font-size:13px; }}
.ledger .tk {{ color:var(--mut); font-size:11.5px; }}
.ledger tr:hover td {{ background:#F3F5F0; }}
.ctrl {{ display:flex; gap:14px; align-items:center; margin:10px 0 12px;
  font-size:13px; color:var(--mut); flex-wrap:wrap; }}
.ctrl input[type=text], .ctrl select {{ font:inherit; padding:5px 9px;
  border:1px solid var(--line); border-radius:3px; background:#fff; }}
.ext {{ display:none; }} .show-ext .ext {{ display:table-row; }}
.ledger thead th {{ position:sticky; background:var(--paper); z-index:2; }}
.ledger tr.grp th {{ top:0; height:22px; text-align:left; font-size:11px;
  letter-spacing:.8px; color:var(--indigo); border-bottom:1px solid var(--line);
  cursor:default; }}
.ledger thead tr:nth-child(2) th {{ top:23px; }}
.ledger tbody tr:nth-child(even) td {{ background:#F7F8F4; }}
.ledger tbody tr:hover td {{ background:#EFF2EA; }}
.pct {{ color:var(--mut); font-size:10.5px; font-family:inherit; }}
.chips {{ display:inline-flex; gap:6px; }}
.chip {{ font:12.5px/1 inherit; padding:6px 10px; border:1px solid var(--line);
  background:#fff; border-radius:14px; cursor:pointer; color:var(--ink); }}
.chip.on {{ background:var(--indigo); border-color:var(--indigo); color:#fff; }}
.g-ok {{ color:#1B7A43; font-weight:700; }}
.g-bad {{ color:#B4231F; font-weight:700; }}
.g-warn {{ color:#A6650E; font-weight:700; }}
.quad-on {{ color:#1B7A43; font-weight:800; }}
.warn-row td:nth-child(2) {{ box-shadow:inset 3px 0 0 #D9A0A0; }}
.warn-row td:nth-child(6) {{ color:#B4231F; }}   /* ROE 칸 — 산출 불가 강조 */
.fb {{ display:inline-block; font-size:10.5px; border:1px solid var(--line);
  border-radius:3px; padding:1px 5px; margin:0 3px 1px 0; color:var(--mut);
  background:#fff; white-space:nowrap; }}
.legend td:first-child {{ white-space:nowrap; color:var(--indigo); font-weight:700;
  vertical-align:top; padding-right:16px; }}
.legend td {{ font-size:13px; padding:5px 10px 5px 0; }}
footer {{ margin-top:46px; font-size:12.5px; color:var(--mut);
  border-top:1px solid var(--line); padding-top:12px; }}
@media (max-width:760px) {{ .stat {{ flex-basis:46%; border-right:0; }} }}
</style></head><body><div class="wrap">

<header>
  <h1>대형 가치 트랙 · 관측 리포트<span class="badge">관측 전용 — 추천 아님</span></h1>
  <div class="sub">run {rid} · 생성 {gen} · 분석 유니버스 시총 상위 {UNIVERSE_N} (적재 {len(df)})</div>
  <div class="notice">모든 값은 <b>가중치 0의 관측 데이터</b>다. 종합 점수는 존재하지 않으며,
  값에 등락 색을 입히지 않고 기본 정렬을 시총순으로 둔 것은 의도다 — 검증(§9) 전의
  순위 강조는 추천 오인을 만든다.</div>
  {rail}
</header>

<h2>수집 현황 — rank≤{UNIVERSE_N} 기준</h2>
<div class="stats">
  <div class="stat"><b>{n_runs}</b><span>관측 run 누적 ({runs[0]}~{runs[-1]})</span></div>
  {"".join(f'<div class="stat"><b>{v}<small style="font-size:12px;color:var(--mut)">/{UNIVERSE_N}</small></b><span>{k}</span></div>' for k, v in cov.items())}
</div>
<p style="font-size:13px;color:var(--mut);margin-top:8px">수급 이력(daily_flows): {flows_txt}
 · RIM 스프레드 분위 25/50/75% = {fmt(q[0.25],'{:+.2f}')} / {fmt(q[0.5],'{:+.2f}')} / {fmt(q[0.75],'{:+.2f}')}
 · 사분면(ROE&gt;10%·PBR&lt;1) {quad}개 · 품질게이트 통과 {g1} / 탈락 {g0}</p>

<h2>업종 구성 (보정 후 라벨)</h2>
<table class="mini">{sec_rows}</table>

<h2>읽는 법</h2>
<table class="mini legend">
<tr><td>RIM 스프레드</td><td>log(정당PBR ÷ 실제PBR). <b>+면 정당가 대비 싸게 거래 중이라는 '관측'</b>.
 균일 COE 9% 가정이라 금융·보험은 구조적으로 크게 나오는 경향 — §9에서 업종 내 비교로 판정.</td></tr>
<tr><td><span class="quad-on">◆</span> 사분면</td><td>ROE&gt;10% &amp; PBR&lt;1 — 설계(§4①)가 지목한 최우선 관찰 구역(초록 ◆).</td></tr>
<tr><td>배당% · 소각</td><td>주주환원 두 축. 소각 = 최근 90일 내 자사주 소각 공시(DART).</td></tr>
<tr><td>OCF/OP</td><td>영업이익 1원당 영업현금 배율. <b>높을수록 좋은 값이 아니라 구간 게이트</b>:
 {QUALITY_OCF_LO}~{QUALITY_OCF_HI}배가 건전(통과). <b>탈락↓({QUALITY_OCF_LO} 미만)이 특히 경계</b> — 장부이익이 현금으로 안 들어오는
 밸류트랩·분식 패턴. 탈락↑({QUALITY_OCF_HI} 초과)는 일회성·회계 왜곡 가능.
 <span class="g-ok">통과</span>·<span class="g-bad">탈락↓</span>·<span class="g-warn">탈락↑</span>로 색 구분.</td></tr>
<tr><td>수급20</td><td>최근 20일 외국인+기관 합산 순매수(억). <b>▲ 순매수 · ▽ 순매도</b>. <b>⚠️ 설계 §4의 '수급 리버설'이 아니다</b> — 리버설은 "장기(60일) 소외 → 단기(20일) 전환"인데 60일 데이터가 아직 없어, 지금은 20일 부호만 보는 거친 신호다(daily_flows 60거래일 적재 후 8월 말 진짜 리버설로 교체). 대형주는 자료없음('·')이 ~1/3. 색을 안 칠한 이유다.</td></tr>
<tr><td>시총 추세</td><td>직전 run 대비 <b>시총 변화율(시총Δ%)</b>·<b>순위 변화(순위Δ, ▲=상승)</b>. <b>⚠️ 사실 표시일 뿐 "오를 종목" 신호가 아니다</b> — "오르는 중"인지 "이미 다 올라 과열"인지는 지난 데이터로 구분 못 한다(모멘텀의 본질적 함정). 현재 누적 4거래일이라 추세라 부를 수도 없는 노이즈 구간. 색을 안 칠한 이유다. 수급 결합 정식 관측은 daily_flows 60일 적재 후(8월 말).</td></tr>
<tr><td>플래그</td><td>종목명 옆 배지(감점 아님): 우선주 / 금융 / 지주 / 리츠 / 시클리컬 — 구조적 특성 표시.</td></tr>
<tr><td><span style="color:#B4231F">경고행</span></td><td><b>자본잠식</b>(BPS≤0)만 표시 — 지표 신뢰 불가라는 <b>사실</b>(나쁜 종목이라는 주장 아님). 종목명 왼쪽 붉은 띠 + ROE 칸 적색. 단순 EPS 무자료(우선주·일부 지주 등)는 경고가 아니라 '·'.</td></tr>
<tr><td>색 원칙</td><td><b>객관적 게이트·조건에만</b> 색(게이트 통과/탈락, 사분면, 경고행). RIM·배당·ROE 같은 <b>연속 수치엔 무색</b> — 거기 색을 칠하면 검증 안 된 가중치를 주장하는 셈이라 일부러 비웠다.</td></tr>
<tr><td>'·'</td><td>자료 없음(미수집·미산출) — 0이나 탈락이 아님.</td></tr>
</table>

<h2>종목 원장</h2>
<div class="ctrl">
  <input type="text" id="q" placeholder="종목명/티커 필터" oninput="filt()">
  <select id="sec" onchange="filt()"><option value="">업종 전체</option>
  {"".join(f'<option>{html.escape(str(s))}</option>' for s in sorted(df["sector"].dropna().unique()))}</select>
  <span class="chips">
    <button class="chip" data-k="quad" onclick="chip(this)">◆ 사분면</button>
    <button class="chip" data-k="gate" onclick="chip(this)">게이트 통과</button>
    <button class="chip" data-k="bb" onclick="chip(this)">소각 있음</button>
    <button class="chip" data-k="div" onclick="chip(this)">배당&gt;0</button>
    <button class="chip" data-k="sup" onclick="chip(this)">▲ 20일 순매수</button>
    <button class="chip" data-k="mcup" onclick="chip(this)">▲ 시총 상승</button>
  </span>
  <label><input type="checkbox" id="ext" onchange="document.getElementById('tb').classList.toggle('show-ext',this.checked); filt()"> 상위 500 모두</label>
  <span>칩=조건 슬라이스(조합 가능) · 머리글 클릭=정렬 · 기본=시총순</span>
</div>
<table class="ledger" id="tb">
<colgroup><col style="width:32px"><col><col style="width:108px"><col style="width:54px">
<col style="width:46px"><col style="width:46px"><col style="width:52px"><col style="width:112px">
<col style="width:44px"><col style="width:40px"><col style="width:50px"><col style="width:46px"><col style="width:66px">
<col style="width:58px"><col style="width:48px"></colgroup>
<thead>
<tr class="grp"><th colspan="4">식별 · 플래그</th><th colspan="4">밸류 · RIM (관측)</th>
<th colspan="2">주주환원 (관측)</th><th colspan="3">품질 · 수급 (관측)</th><th colspan="2">시총 추세 (직전 run 대비)</th></tr>
<tr>
<th>#</th><th>종목</th><th>업종</th><th>시총(조)</th><th>PBR</th><th>ROE%</th>
<th>정당PBR</th><th>RIM스프레드</th><th>배당%</th><th>소각</th><th>OCF/OP</th><th>게이트</th><th title="최근 20일 외인+기관 순매수(억). ▲순매수 ▽순매도. 리버설 아님">수급20</th><th title="직전 run 대비 시총 변화율(%)">시총Δ%</th><th title="직전 run 대비 순위 변화(▲=상승)">순위Δ</th>
</tr></thead><tbody>
{table_rows}
</tbody></table>

<footer>원천: history.db · large_final(관측 적재) — fetch: KRX(valuation)/DART(소각)/stage3 운반.
 상위%=분석 유니버스 내 RIM 스프레드 단일 팩터 백분위(합성 아님) · 각 칼럼 해석은 상단 '읽는 법' 참조.
 <b>§9 검증(h=60/120d) 전 — 이 페이지의 어떤 값도 매수·매도 신호가 아니다.</b> 공개 대시보드 탭은 검증 후 별도 결정.</footer>
</div>
<script>
const tb=document.getElementById('tb');
const chipsOn={{}};
function chip(b){{b.classList.toggle('on');chipsOn[b.dataset.k]=b.classList.contains('on');filt();}}
function pass(tr){{
 if(chipsOn.quad && !tr.cells[7].innerText.includes('◆'))return false;
 if(chipsOn.gate && tr.cells[11].innerText!=='통과')return false;
 if(chipsOn.bb   && tr.cells[9].innerText!=='소각')return false;
 if(chipsOn.div){{const d=parseFloat(tr.cells[8].innerText);if(!(d>0))return false;}}
 if(chipsOn.sup && !tr.cells[12].innerText.includes('▲'))return false;
 if(chipsOn.mcup && !tr.cells[13].innerText.includes('▲'))return false;
 return true;}}
function filt(){{const q=document.getElementById('q').value.trim().toLowerCase();
 const s=document.getElementById('sec').value;const ext=document.getElementById('ext').checked;
 for(const tr of tb.tBodies[0].rows){{
   const isExt=tr.classList.contains('ext');
   const name=tr.cells[1].innerText.toLowerCase(), sec=tr.cells[2].innerText;
   const ok=(!q||name.includes(q))&&(!s||sec===s)&&(ext||!isExt)&&pass(tr);
   tr.style.display=ok?'':'none';}}}}
let asc={{}};
tb.tHead.rows[1].querySelectorAll('th').forEach((th,i)=>th.onclick=()=>{{
 const num=![1,2,9,11].includes(i); asc[i]=!asc[i];
 const rows=[...tb.tBodies[0].rows];
 rows.sort((a,b)=>{{let x=a.cells[i].innerText.split(' 상위')[0].replace('◆','').replace('·','').trim(),
   y=b.cells[i].innerText.split(' 상위')[0].replace('◆','').replace('·','').trim();
   if(num){{x=parseFloat(x);y=parseFloat(y);
     if(isNaN(x))return 1; if(isNaN(y))return -1; return asc[i]?x-y:y-x;}}
   return asc[i]?x.localeCompare(y,'ko'):y.localeCompare(x,'ko');}});
 rows.forEach(r=>tb.tBodies[0].appendChild(r));}});
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="대형 트랙 관측 리포트 HTML 생성(로컬)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--no-publish-obs", dest="publish_obs", action="store_false",
                    help="docs/_large_obs.html 비공개 경로 복사 생략")
    ap.set_defaults(publish_obs=True)
    args = ap.parse_args()

    rid, df, n_runs, runs, flows, prev_run = load(Path(args.db), args.run_id)
    htm = build_html(rid, df, n_runs, runs, flows, prev_run)
    Path(args.out).write_text(htm, encoding="utf-8")
    print(f"💾 {args.out} 생성 — run {rid}, {len(df)}종목, 누적 {n_runs}run. 더블클릭으로 열람.")
    # 텔레그램 '대형 가치 트랙(준비중)' 링크 대상 — docs 내 '링크 안 걸린' 비공개 경로.
    # 메인(index)·필터에서 참조하지 않으므로 공개 탭이 아니며, 주소를 아는 본인만 폰에서 열람.
    if args.publish_obs:
        dst = Path("docs") / "_large_obs.html"
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(htm, encoding="utf-8")
            print(f"   • {dst} 로도 복사 (텔레그램 준비중 링크 대상 · 비공개 경로)")
        except Exception as e:
            print(f"   ⚠️  {dst} 복사 실패(무시 가능): {e}")
    print("   (관측 전용 라벨 포함 · docs/ 공개 *탭*은 §9 검증 후 별도 결정)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
