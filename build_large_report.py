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
    finally:
        con.close()
    return str(rid), df, n_runs, runs, flows


def fmt(v, pat="{:.2f}", dash="·"):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return dash
    return pat.format(v)


def build_html(rid, df, n_runs, runs, flows):
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
        if pd.isna(ocf):
            gate = "·"
        elif r["quality_gate"] == 1:
            gate = "통과"
        else:
            gate = "탈락↓" if ocf < QUALITY_OCF_LO else "탈락↑"
        in_u = r["marcap_rank"] <= UNIVERSE_N
        ext = "" if in_u else ' class="ext"'
        p = pct_top(r["rim_spread"]) if in_u else None
        quad = " ◆" if r["rim_quadrant"] == 1 else ""
        sp_cell = (f"{fmt(r['rim_spread'], '{:+.2f}')}{quad}"
                   + (f" <span class='pct'>상위{p}%</span>" if p is not None else ""))
        rows.append(
            f"<tr{ext}><td class='num'>{int(r['marcap_rank'])}</td>"
            f"<td>{html.escape(str(r['name']))} <span class='tk'>{r['ticker']}</span></td>"
            f"<td>{html.escape(str(r['sector']))}</td>"
            f"<td class='num'>{fmt(r['marcap']/1e12, '{:.1f}')}</td>"
            f"<td class='num'>{fmt(r['pbr'])}</td>"
            f"<td class='num'>{fmt(r['roe_value'], '{:.1f}')}</td>"
            f"<td class='num'>{fmt(r['rim_fair_pbr'])}</td>"
            f"<td class='num sp'>{sp_cell}</td>"
            f"<td class='num'>{fmt(r['div_yield'], '{:.1f}')}</td>"
            f"<td class='num'>{bb}</td>"
            f"<td class='num'>{fmt(r['ocf_to_op_ratio'])}</td>"
            f"<td class='num'>{gate}</td>"
            f"<td>{flags}</td></tr>")
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
<tr><td>◆ 사분면</td><td>ROE&gt;10% &amp; PBR&lt;1 — 설계(§4①)가 지목한 최우선 관찰 구역.</td></tr>
<tr><td>배당% · 소각</td><td>주주환원 두 축. 소각 = 최근 90일 내 자사주 소각 공시(DART).</td></tr>
<tr><td>OCF/OP</td><td>영업이익 1원당 영업현금 배율. <b>높을수록 좋은 값이 아니라 구간 게이트</b>:
 {QUALITY_OCF_LO}~{QUALITY_OCF_HI}배가 건전(통과). <b>탈락↓({QUALITY_OCF_LO} 미만)이 특히 경계</b> — 장부이익이 현금으로 안 들어오는
 밸류트랩·분식 패턴. 탈락↑({QUALITY_OCF_HI} 초과)는 일회성·회계 왜곡 가능.</td></tr>
<tr><td>플래그</td><td>구조적 특성 표시(감점 아님): 우선주 / 금융 / 지주 / 리츠 / 시클리컬.</td></tr>
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
  </span>
  <label><input type="checkbox" id="ext" onchange="document.getElementById('tb').classList.toggle('show-ext',this.checked); filt()"> 상위 500 모두</label>
  <span>칩=조건 슬라이스(조합 가능) · 머리글 클릭=정렬 · 기본=시총순</span>
</div>
<table class="ledger" id="tb"><thead>
<tr class="grp"><th colspan="4">식별</th><th colspan="4">밸류 · RIM (관측)</th>
<th colspan="2">주주환원 (관측)</th><th colspan="2">품질 (관측)</th><th></th></tr>
<tr>
<th>#</th><th>종목</th><th>업종</th><th>시총(조)</th><th>PBR</th><th>ROE%</th>
<th>정당PBR</th><th>RIM스프레드</th><th>배당%</th><th>소각</th><th>OCF/OP</th><th>게이트</th><th>플래그</th>
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
 const num=![1,2,9,11,12].includes(i); asc[i]=!asc[i];
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
    args = ap.parse_args()

    rid, df, n_runs, runs, flows = load(Path(args.db), args.run_id)
    htm = build_html(rid, df, n_runs, runs, flows)
    Path(args.out).write_text(htm, encoding="utf-8")
    print(f"💾 {args.out} 생성 — run {rid}, {len(df)}종목, 누적 {n_runs}run. 더블클릭으로 열람.")
    print("   (관측 전용 라벨 포함 · docs/ 공개 탭은 §9 검증 후 별도 결정)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
