#!/usr/bin/env python3
"""
[V2.6] GitHub Pages 대시보드 자동 생성기
==========================================
history.db를 읽어 docs/index.html을 생성한다.
GitHub Actions에서 매일 실행 → GitHub Pages가 자동 서빙.

[실행]
    python build_dashboard.py
[출력]
    docs/index.html  (단일 파일, 외부 의존성 최소)
    docs/data.json   (인터랙티브 필터/차트용 데이터)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_PATH = Path("history.db")
DOCS_DIR = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)


def safe_query(conn, sql, params=()):
    """테이블/컬럼이 없을 때도 빈 DF 반환."""
    try:
        return pd.read_sql(sql, conn, params=params)
    except Exception as e:
        print(f"  ⚠️ Query failed: {e}")
        return pd.DataFrame()


V3_DIR = Path("v3_archive")
_BUCKET_RANK = {"BUY": 0, "WAIT": 1, "OBSERVE": 2, "WATCH": 3}


def _v3_file(market, run_id=None):
    """run_id 를 주면 그 회차의 v3 파일만(없으면 None). 없으면 가장 최근 파일.

    run_id 를 주는 게 중요하다: 대시보드를 '그날 v3 가 만들어지기 전'에 그리면
    최근 파일은 '전날' v3 라서 표가 하루 묵게 된다. 현재 run_id 파일이 아직
    없으면 None 을 돌려 v2.6 으로 폴백시킨다.
    """
    if run_id is not None:
        f = V3_DIR / f"v3_{market}_{run_id}.csv"
        return f if f.exists() else None
    files = sorted(V3_DIR.glob(f"v3_{market}_*.csv"))
    return files[-1] if files else None


def _read_v3(market, run_id=None):
    """v3 파일 DataFrame (없으면 None)."""
    f = _v3_file(market, run_id)
    if not f:
        return None
    try:
        d = pd.read_csv(f)
    except Exception:
        return None
    if "final_score_v3" not in d.columns:
        return None
    d["final_score_v3"] = pd.to_numeric(d["final_score_v3"], errors="coerce")
    if "ticker" in d.columns:
        d["ticker"] = d["ticker"].astype(str).str.zfill(6)
    return d


def load_v3_top(market, run_id=None, top_n=30, buckets=("BUY", "WAIT")):
    """현재 run_id 의 v3 파일에서 지정 버킷만, 버킷순→final_score_v3 내림차순 상위 N개.

    buckets 에 든 것만 포함(EXCLUDE 는 절대 안 들어감). 해당 버킷이 없으면 None.
    """
    d = _read_v3(market, run_id)
    if d is None or "bucket" not in d.columns:
        return None
    d = d[d["bucket"].isin(buckets)].copy()
    if d.empty:
        return None
    d["_brank"] = d["bucket"].map(_BUCKET_RANK).fillna(9)
    d = d.sort_values(["_brank", "final_score_v3"],
                      ascending=[True, False]).head(top_n)
    keep = [c for c in ["ticker", "name", "sector", "final_score_v3",
                        "grade", "bucket", "q_basis"] if c in d.columns]
    return d[keep]


def build_data_payload() -> dict:
    """대시보드용 데이터 페이로드 생성."""
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M KST"),
        "runs": {"kospi": [], "kosdaq": []},
        "latest": {"kospi": {"top": [], "meta": {}}, "kosdaq": {"top": [], "meta": {}}},
        "frequent": {"kospi": [], "kosdaq": []},
        "regime_history": {"kospi": [], "kosdaq": []},
    }

    if not DB_PATH.exists():
        print(f"  ℹ️  {DB_PATH}가 없습니다 — 빈 대시보드 생성")
        return payload

    conn = sqlite3.connect(DB_PATH)

    for market in ("kospi", "kosdaq"):
        # 최근 30회 실행 메타
        df_runs = safe_query(
            conn,
            "SELECT run_id, market_regime, regime_score, usdkrw, "
            "foreign_kospi_5d_억 AS foreign_5d, stage1_count "
            "FROM runs WHERE market=? ORDER BY run_id DESC LIMIT 30",
            (market,),
        )
        payload["runs"][market] = df_runs.to_dict(orient="records")

        if df_runs.empty:
            continue

        latest_run_id = df_runs.iloc[0]["run_id"]

        # 최신 회차 TOP — v3 등급/버킷 기준. BUY→WAIT 우선, 없으면 OBSERVE/WATCH까지(여전히 v3).
        df_top = load_v3_top(market, run_id=latest_run_id, top_n=30, buckets=("BUY", "WAIT"))
        if df_top is None or df_top.empty:
            df_top = load_v3_top(market, run_id=latest_run_id, top_n=30,
                                 buckets=("BUY", "WAIT", "OBSERVE", "WATCH"))
        used_v3 = df_top is not None and not df_top.empty
        if not used_v3:
            # v3 파일 자체가 없을 때만 v2.6 으로 폴백
            df_top = safe_query(
                conn,
                "SELECT ticker, name, final_score AS final_score_v3, "
                "q_basis, sector "
                "FROM stage3_final WHERE market=? AND run_id=? "
                "ORDER BY final_score DESC LIMIT 30",
                (market, latest_run_id),
            )
            if not df_top.empty:
                df_top["grade"] = "-"
                df_top["bucket"] = "-"
        # 컬럼이 없을 수도 있으니 안전 처리
        if df_top is not None and not df_top.empty:
            for col in ("q_basis", "sector", "grade", "bucket"):
                if col not in df_top.columns:
                    df_top[col] = None
            payload["latest"][market]["top"] = df_top.fillna("-").to_dict(orient="records")
            payload["latest"][market]["ranked_by"] = "v3" if used_v3 else "v2"

        latest_meta = df_runs.iloc[0].to_dict()
        payload["latest"][market]["meta"] = {
            k: (None if pd.isna(v) else v) for k, v in latest_meta.items()
        }

        # 최근 30일 자주 등장한 종목
        df_freq = safe_query(
            conn,
            """
            SELECT name, ticker,
                   COUNT(*) AS appearances,
                   ROUND(AVG(final_score), 1) AS avg_score,
                   MAX(final_score) AS max_score
            FROM stage3_final
            WHERE market=? AND run_id >= ?
            GROUP BY ticker, name
            HAVING appearances >= 2
            ORDER BY appearances DESC, avg_score DESC
            LIMIT 20
            """,
            (market, "20000101"),
        )
        payload["frequent"][market] = df_freq.to_dict(orient="records")

        # 단골 종목에 '현재 v3 등급/점수' 붙이기 (최신 v3 파일 기준)
        if not df_freq.empty:
            v3now = _read_v3(market, latest_run_id)
            if v3now is not None and "ticker" in v3now.columns:
                gmap = v3now.set_index("ticker")
                recs = []
                for r in payload["frequent"][market]:
                    tk = str(r.get("ticker", "")).zfill(6)
                    if tk in gmap.index:
                        row = gmap.loc[tk]
                        if hasattr(row, "iloc") and getattr(row, "ndim", 1) > 1:
                            row = row.iloc[0]
                        r["v3_score"] = (None if pd.isna(row.get("final_score_v3"))
                                         else round(float(row.get("final_score_v3")), 1))
                        r["grade"] = None if pd.isna(row.get("grade")) else row.get("grade")
                        r["bucket"] = None if pd.isna(row.get("bucket")) else row.get("bucket")
                    else:
                        r["v3_score"], r["grade"], r["bucket"] = None, None, None
                    recs.append(r)
                payload["frequent"][market] = recs

        # 레짐 점수 시계열 (차트용)
        df_regime = df_runs[["run_id", "regime_score", "market_regime"]].copy()
        df_regime = df_regime.iloc[::-1]  # 오름차순
        payload["regime_history"][market] = df_regime.to_dict(orient="records")

    conn.close()
    return payload


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V3.0 KOSPI/KOSDAQ Screener</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;500;700&family=JetBrains+Mono:wght@400;500;700&family=IBM+Plex+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #f6f3ec;
  --bg-paper: #fbf9f3;
  --ink: #1a1814;
  --ink-soft: #4a4640;
  --rule: #1a1814;
  --rule-light: #c8c2b5;
  --accent: #b8281c;
  --accent-cool: #1d4d6e;
  --positive: #2d6a3e;
  --negative: #b8281c;
  --neutral: #7a6e5b;
}

* { margin: 0; padding: 0; box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  font-family: 'IBM Plex Sans KR', -apple-system, sans-serif;
  background: var(--bg);
  color: var(--ink);
  line-height: 1.5;
  padding: 0;
  font-size: 14px;
  background-image:
    radial-gradient(circle at 2px 2px, rgba(0,0,0,0.018) 1px, transparent 0);
  background-size: 24px 24px;
}

.container { max-width: 1280px; margin: 0 auto; padding: 0 32px; }

/* ────── MASTHEAD ────── */
header.masthead {
  border-bottom: 2px solid var(--rule);
  padding: 28px 0 18px;
  margin-bottom: 0;
}
.masthead-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink-soft);
  margin-bottom: 24px;
  border-bottom: 1px solid var(--rule-light);
  padding-bottom: 12px;
}
.masthead-top span { white-space: nowrap; }
h1.title {
  font-family: 'Noto Serif KR', serif;
  font-weight: 700;
  font-size: clamp(40px, 6vw, 68px);
  line-height: 1.0;
  letter-spacing: -0.02em;
  margin-bottom: 8px;
}
h1.title .subtitle {
  display: block;
  font-family: 'IBM Plex Sans KR', sans-serif;
  font-weight: 300;
  font-size: 16px;
  color: var(--ink-soft);
  margin-top: 12px;
  letter-spacing: 0;
}

/* ────── MARKET TABS ────── */
.market-nav {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--rule);
  margin: 32px 0 28px;
}
.market-tab {
  font-family: 'Noto Serif KR', serif;
  font-weight: 500;
  font-size: 22px;
  padding: 16px 32px 14px;
  cursor: pointer;
  border: none;
  background: none;
  color: var(--ink-soft);
  position: relative;
  letter-spacing: -0.01em;
  transition: color 0.2s;
}
.market-tab:hover { color: var(--ink); }
.market-tab.active { color: var(--ink); }
.market-tab.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--accent);
}
.market-tab .count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  margin-left: 8px;
  color: var(--ink-soft);
  font-weight: 400;
  vertical-align: super;
}

/* ────── REGIME PANEL ────── */
.regime-panel {
  display: grid;
  grid-template-columns: 1.5fr 1fr 1fr 1fr 1fr;
  gap: 0;
  border-top: 2px solid var(--rule);
  border-bottom: 2px solid var(--rule);
  margin-bottom: 40px;
}
.regime-cell {
  padding: 20px 16px 18px;
  border-right: 1px solid var(--rule-light);
}
.regime-cell:last-child { border-right: none; }
.regime-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-soft);
  margin-bottom: 8px;
}
.regime-value {
  font-family: 'Noto Serif KR', serif;
  font-size: 28px;
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.1;
}
.regime-value.small {
  font-family: 'JetBrains Mono', monospace;
  font-size: 22px;
  font-weight: 500;
}
.regime-value.pos { color: var(--positive); }
.regime-value.neg { color: var(--negative); }
.regime-detail {
  font-size: 11px;
  color: var(--ink-soft);
  margin-top: 4px;
  font-family: 'JetBrains Mono', monospace;
}

/* ────── SECTION HEADERS ────── */
section { margin-bottom: 64px; }
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--rule-light);
}
.section-head h2 {
  font-family: 'Noto Serif KR', serif;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.section-head h2 .num {
  font-family: 'JetBrains Mono', monospace;
  color: var(--accent);
  font-size: 14px;
  margin-right: 8px;
  vertical-align: super;
  font-weight: 400;
}
.section-head .meta {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-soft);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ────── DATA TABLES ────── */
table.data {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
table.data thead th {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-align: left;
  padding: 10px 12px 8px;
  border-bottom: 2px solid var(--rule);
  color: var(--ink-soft);
  font-weight: 500;
  white-space: nowrap;
}
table.data thead th.num { text-align: right; }
table.data tbody td {
  padding: 11px 12px;
  border-bottom: 1px solid var(--rule-light);
  vertical-align: top;
}
table.data tbody td.num {
  text-align: right;
  font-family: 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums;
}
table.data tbody tr:hover { background: rgba(184, 40, 28, 0.04); }
table.data .ticker {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-soft);
  display: block;
  margin-top: 2px;
}
table.data .name {
  font-weight: 500;
  font-size: 14px;
}
table.data .rank {
  font-family: 'Noto Serif KR', serif;
  font-size: 18px;
  color: var(--accent);
  font-weight: 500;
  width: 30px;
}
.score-bar {
  display: inline-block;
  width: 60px;
  height: 6px;
  background: var(--rule-light);
  position: relative;
  margin-right: 8px;
  vertical-align: middle;
}
.score-bar-fill {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: var(--accent);
}
.tag {
  display: inline-block;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  padding: 2px 6px;
  background: var(--ink);
  color: var(--bg-paper);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

/* ────── REGIME CHART ────── */
.chart-frame {
  border: 1px solid var(--rule-light);
  background: var(--bg-paper);
  padding: 24px;
  position: relative;
}
.chart-svg { width: 100%; height: 280px; display: block; }
.chart-axis text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  fill: var(--ink-soft);
}
.chart-line { fill: none; stroke: var(--ink); stroke-width: 1.5; }
.chart-point { fill: var(--bg-paper); stroke: var(--ink); stroke-width: 1.5; }
.chart-point.alert { fill: var(--accent); stroke: var(--accent); }
.chart-zero { stroke: var(--rule-light); stroke-dasharray: 2,3; }

/* ────── EMPTY STATE ────── */
.empty {
  padding: 60px 20px;
  text-align: center;
  color: var(--ink-soft);
  font-style: italic;
  border: 1px dashed var(--rule-light);
}

/* ────── FOOTER ────── */
footer {
  margin-top: 80px;
  padding: 32px 0 48px;
  border-top: 2px solid var(--rule);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-soft);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}
footer .colophon { max-width: 600px; line-height: 1.7; }

/* ────── ANIMATIONS ────── */
.market-panel { display: none; opacity: 0; }
.market-panel.active {
  display: block;
  animation: fadeIn 0.4s ease-out forwards;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ────── RESPONSIVE ────── */
@media (max-width: 768px) {
  .container { padding: 0 16px; }
  h1.title { font-size: 38px; }
  .regime-panel { grid-template-columns: 1fr 1fr; }
  .regime-cell { border-bottom: 1px solid var(--rule-light); }
  .market-tab { padding: 12px 16px; font-size: 18px; }
  .section-head { flex-direction: column; gap: 4px; }
  .section-head h2 { font-size: 22px; }
  table.data { font-size: 12px; }
  table.data tbody td { padding: 8px 6px; }
  table.data thead th { padding: 8px 6px; }
  table.data .name { font-size: 13px; }
}
</style>
</head>
<body>
<div class="container">

<header class="masthead">
  <div class="masthead-top">
    <span>V3.0 · ALGORITHMIC SCREENING</span>
    <span>GENERATED <span id="generated-at"></span></span>
  </div>
  <h1 class="title">
    Oversold Screener
    <span class="subtitle">KOSPI · KOSDAQ — 시장 레짐과 펀더멘털 기반 일일 과매도 종목 발굴</span>
  </h1>
</header>

<nav class="market-nav">
  <button class="market-tab active" data-market="kospi">
    KOSPI<span class="count" id="count-kospi">—</span>
  </button>
  <button class="market-tab" data-market="kosdaq">
    KOSDAQ<span class="count" id="count-kosdaq">—</span>
  </button>
</nav>

<!-- 점수 적중도(IC) 카드 — ic_summary.json에서 로드 -->
<div id="ic-card" style="border:1px solid var(--rule,#d8d2c4);border-radius:10px;
     padding:18px 20px;margin:0 0 28px;background:rgba(0,0,0,0.015);">
  <div style="display:flex;justify-content:space-between;align-items:baseline;
       flex-wrap:wrap;gap:6px;margin-bottom:10px;">
    <strong style="font-size:0.95rem;letter-spacing:0.02em;">📊 점수 적중도 (IC)</strong>
    <span id="ic-asof" style="font-size:0.7rem;opacity:0.55;font-family:monospace;">—</span>
  </div>
  <div id="ic-body" style="font-size:0.85rem;opacity:0.7;">불러오는 중…</div>
</div>

<!-- 인터랙티브 필터 페이지로 -->
<a href="filter.html" style="display:block;text-align:center;margin:0 0 28px;padding:14px;
   border:1px solid var(--rule,#d8d2c4);border-radius:10px;text-decoration:none;
   font-weight:600;font-size:0.95rem;color:inherit;background:rgba(66,153,225,0.06);">
  🔍 필터·정렬·검색으로 자세히 보기 →
</a>

<!-- KOSPI PANEL -->
<div class="market-panel active" data-market="kospi">
  <div class="regime-panel" id="regime-kospi"></div>

  <section>
    <div class="section-head">
      <h2><span class="num">01</span>최신 회차 상위 종목</h2>
      <span class="meta">v3 등급 · BUY → WAIT</span>
    </div>
    <div id="top-kospi"></div>
  </section>

  <section>
    <div class="section-head">
      <h2><span class="num">02</span>레짐 점수 추이</h2>
      <span class="meta">RECENT 30 RUNS</span>
    </div>
    <div class="chart-frame">
      <svg class="chart-svg" id="chart-kospi" viewBox="0 0 800 280" preserveAspectRatio="none"></svg>
    </div>
  </section>

  <section>
    <div class="section-head">
      <h2><span class="num">03</span>단골 종목 — 최근 30회 자주 등장</h2>
      <span class="meta">APPEARANCES ≥ 2</span>
    </div>
    <div id="frequent-kospi"></div>
  </section>
</div>

<!-- KOSDAQ PANEL -->
<div class="market-panel" data-market="kosdaq">
  <div class="regime-panel" id="regime-kosdaq"></div>

  <section>
    <div class="section-head">
      <h2><span class="num">01</span>최신 회차 상위 종목</h2>
      <span class="meta">v3 등급 · BUY → WAIT · KOSDAQ TUNED</span>
    </div>
    <div id="top-kosdaq"></div>
  </section>

  <section>
    <div class="section-head">
      <h2><span class="num">02</span>레짐 점수 추이</h2>
      <span class="meta">RECENT 30 RUNS</span>
    </div>
    <div class="chart-frame">
      <svg class="chart-svg" id="chart-kosdaq" viewBox="0 0 800 280" preserveAspectRatio="none"></svg>
    </div>
  </section>

  <section>
    <div class="section-head">
      <h2><span class="num">03</span>단골 종목 — 최근 30회 자주 등장</h2>
      <span class="meta">APPEARANCES ≥ 2</span>
    </div>
    <div id="frequent-kosdaq"></div>
  </section>
</div>

<footer>
  <div class="colophon">
    Built with V3.0 Pipeline · Stage 1 Regime/FX/Foreign Flow ·
    Stage 2 DART Risk Filter · Stage 3 Fundamentals & Momentum.
    Data accumulated to SQLite · Snapshots in Parquet.
    Not investment advice.
  </div>
  <div>
    <div>SOURCE · FDR · NAVER · DART · BOK</div>
    <div>RUN @ <span id="footer-generated"></span></div>
  </div>
</footer>

</div>

<script>
// 데이터는 같은 디렉토리의 data.json에서 로드
const PAYLOAD = __DATA__;

document.getElementById('generated-at').textContent = PAYLOAD.generated_at || '—';
document.getElementById('footer-generated').textContent = PAYLOAD.generated_at || '—';

function fmt(v, digits=1) {
  if (v === null || v === undefined || v === '' || (typeof v === 'number' && isNaN(v))) return '—';
  if (typeof v === 'number') return v.toFixed(digits);
  return v;
}

function fmtScore(v) {
  if (v === null || v === undefined) return '—';
  return Math.round(v);
}

// ── 점수 적중도(IC) 카드 ──────────────────────────────
function icColor(ic) {
  if (ic === null || ic === undefined) return 'inherit';
  if (ic < -0.03) return '#b3261e';      // 역방향(빨강)
  if (ic < 0.03)  return '#8a8170';      // 무의미(회색)
  return '#2e7d32';                       // 유효(초록)
}
function renderICCard() {
  const body = document.getElementById('ic-body');
  const asof = document.getElementById('ic-asof');
  fetch('ic_summary.json?ts=' + Date.now())
    .then(r => r.ok ? r.json() : Promise.reject())
    .then(d => {
      asof.textContent = (d.generated_at || '') + (d.n_dates ? ` · ${d.n_dates}일치` : '');
      if (d.status !== 'ok' || !d.headline || d.headline.ic === null) {
        body.innerHTML = '<span style="opacity:0.7;">아직 데이터를 쌓는 중입니다. '
          + '거래일마다 스크리너를 돌리면 점점 정확해집니다.</span>';
        return;
      }
      const h = d.headline;
      const big = (h.ic >= 0 ? '+' : '') + h.ic.toFixed(3);
      let chips = '';
      (d.factors || []).forEach(f => {
        const ic20 = f.ic && f.ic['20'];
        const c = icColor(ic20);
        const val = (ic20 === null || ic20 === undefined) ? '—'
                    : (ic20 >= 0 ? '+' : '') + ic20.toFixed(2);
        chips += `<span style="display:inline-block;margin:2px 6px 2px 0;padding:2px 8px;
          border:1px solid var(--rule,#d8d2c4);border-radius:12px;font-size:0.72rem;">
          ${f.label} <b style="color:${c};">${val}</b></span>`;
      });
      body.innerHTML = `
        <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:8px;">
          <span style="font-size:1.6rem;font-weight:700;color:${icColor(h.ic)};">${big}</span>
          <span style="font-size:0.8rem;">${h.score === 'final_score_v3' ? 'v3 점수' : '최종점수'} 적중도 (+${h.horizon}일, N=${h.n})</span>
          <span style="font-size:0.78rem;opacity:0.8;">${h.verdict || ''}</span>
        </div>
        ${h.spread !== null && h.spread !== undefined
          ? `<div style="font-size:0.76rem;opacity:0.7;margin-bottom:8px;">
             상위↔하위 평균 수익률 격차: <b>${h.spread >= 0 ? '+' : ''}${h.spread}%p</b>
             ${h.spread > 0 ? '(상위가 더 좋음 ✓)' : '(점수 역작동 의심)'}</div>` : ''}
        <div style="margin-bottom:6px;font-size:0.72rem;opacity:0.6;">요소별 (+20일 IC):</div>
        <div>${chips}</div>
        <div style="font-size:0.7rem;opacity:0.55;margin-top:8px;">
          ※ +0.05↑ 유효 · 0 근처 노이즈 · 음수 역작동. ${d.note || ''}
          ${h.score === 'final_score_v3' ? '<br>※ 텔레그램 IC와는 측정 기간(여기 +5/20일)·종목군(최근 추천권)이 달라 값이 다를 수 있습니다.' : ''}</div>`;
    })
    .catch(() => {
      body.innerHTML = '<span style="opacity:0.6;">점수 적중도 데이터가 아직 없습니다 '
        + '(스크리너를 한 번 더 돌리면 생성됩니다).</span>';
    });
}
renderICCard();

function renderRegime(market) {
  const meta = (PAYLOAD.latest[market] || {}).meta || {};
  const el = document.getElementById('regime-' + market);
  if (!meta || !meta.market_regime) {
    el.innerHTML = '<div class="regime-cell" style="grid-column:1/-1"><div class="regime-label">No Data</div><div class="regime-value small">DB가 비어있거나 아직 실행 이력이 없습니다</div></div>';
    return;
  }
  const regimeCls = (meta.regime_score >= 0) ? 'pos' : 'neg';
  const flowVal = meta.foreign_5d;
  el.innerHTML = `
    <div class="regime-cell">
      <div class="regime-label">Market Regime</div>
      <div class="regime-value">${meta.market_regime || '—'}</div>
      <div class="regime-detail">RUN_ID ${meta.run_id || '—'}</div>
    </div>
    <div class="regime-cell">
      <div class="regime-label">Regime Score</div>
      <div class="regime-value small ${regimeCls}">${fmt(meta.regime_score, 1)}</div>
      <div class="regime-detail">시장 맥락 · 종목순위 무관</div>
    </div>
    <div class="regime-cell">
      <div class="regime-label">USD/KRW</div>
      <div class="regime-value small">${fmt(meta.usdkrw, 2)}</div>
      <div class="regime-detail">원/달러</div>
    </div>
    <div class="regime-cell">
      <div class="regime-label">외인 5일 (억)</div>
      <div class="regime-value small ${(flowVal||0) >= 0 ? 'pos' : 'neg'}">${fmt(flowVal, 0)}</div>
      <div class="regime-detail">시총상위 10종목</div>
    </div>
    <div class="regime-cell">
      <div class="regime-label">발굴 종목</div>
      <div class="regime-value small">${meta.stage1_count || 0}</div>
      <div class="regime-detail">Stage 1 통과</div>
    </div>
  `;
}

function renderTop(market) {
  const top = (PAYLOAD.latest[market] || {}).top || [];
  const el = document.getElementById('top-' + market);
  if (!top.length) { el.innerHTML = '<div class="empty">최신 결과가 없습니다.</div>'; return; }

  const maxScore = Math.max(...top.map(r => r.final_score_v3 || 0));
  const rows = top.map((r, i) => {
    const v3 = r.final_score_v3;
    const fillPct = maxScore > 0 ? (v3 / maxScore) * 100 : 0;
    const bk = r.bucket || '-';
    const bkColor = bk === 'BUY' ? '#2e7d32' : (bk === 'WAIT' ? '#b26a00' : 'var(--rule-light)');
    const bkLabel = (bk === 'BUY' || bk === 'WAIT') ? bk : '—';
    const gr = (r.grade && r.grade !== '-') ? r.grade : '—';
    return `
      <tr>
        <td class="rank">${i + 1}</td>
        <td>
          <span class="name">${r.name || '—'}</span>
          <span class="ticker">${r.ticker || ''}</span>
        </td>
        <td>${r.sector && r.sector !== '-' ? `<span style="font-size:11px;color:var(--ink-soft)">${r.sector}</span>` : '<span style="color:var(--rule-light)">—</span>'}</td>
        <td class="num">
          <span class="score-bar"><span class="score-bar-fill" style="width:${fillPct}%"></span></span>
          ${fmtScore(v3)}
        </td>
        <td class="num"><span class="ticker">${gr}</span></td>
        <td class="num"><span style="font-weight:600;color:${bkColor}">${bkLabel}</span></td>
      </tr>
    `;
  }).join('');
  el.innerHTML = `
    <table class="data">
      <thead><tr>
        <th>#</th><th>종목</th><th>산업</th>
        <th class="num">V3</th><th class="num">등급</th><th class="num">버킷</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderFrequent(market) {
  const freq = PAYLOAD.frequent[market] || [];
  const el = document.getElementById('frequent-' + market);
  if (!freq.length) { el.innerHTML = '<div class="empty">아직 단골 데이터가 모이지 않았습니다.</div>'; return; }
  const rows = freq.map((r, i) => {
    const gr = (r.grade && r.grade !== '-') ? r.grade : '—';
    const v3 = (r.v3_score === null || r.v3_score === undefined) ? '—' : fmtScore(r.v3_score);
    return `
    <tr>
      <td class="rank">${i + 1}</td>
      <td><span class="name">${r.name}</span><span class="ticker">${r.ticker}</span></td>
      <td class="num"><span class="tag">${r.appearances}회</span></td>
      <td class="num">${v3}</td>
      <td class="num"><span class="ticker">${gr}</span></td>
    </tr>
  `;
  }).join('');
  el.innerHTML = `
    <table class="data">
      <thead><tr>
        <th>#</th><th>종목</th><th class="num">등장</th>
        <th class="num">V3</th><th class="num">등급</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderChart(market) {
  const data = (PAYLOAD.regime_history[market] || []).slice(-30);
  const svg = document.getElementById('chart-' + market);
  if (!data.length) {
    svg.innerHTML = '<text x="400" y="140" text-anchor="middle" font-family="JetBrains Mono" fill="#7a6e5b">데이터 없음</text>';
    return;
  }

  const W = 800, H = 280, P = 40;
  const scores = data.map(d => d.regime_score || 0);
  const minS = Math.min(...scores, -2);
  const maxS = Math.max(...scores, 2);
  const range = maxS - minS || 1;

  const xStep = (W - 2 * P) / Math.max(data.length - 1, 1);
  const yScale = s => P + (H - 2 * P) * (1 - (s - minS) / range);
  const yZero = yScale(0);

  // Path
  const path = data.map((d, i) => {
    const x = P + i * xStep;
    const y = yScale(d.regime_score || 0);
    return (i === 0 ? 'M' : 'L') + x + ',' + y;
  }).join(' ');

  // Points
  const points = data.map((d, i) => {
    const x = P + i * xStep;
    const y = yScale(d.regime_score || 0);
    const alert = (d.regime_score || 0) <= -8;
    return `<circle class="chart-point${alert ? ' alert' : ''}" cx="${x}" cy="${y}" r="3"/>`;
  }).join('');

  // X-axis labels (5개 정도)
  const labelStep = Math.max(1, Math.floor(data.length / 5));
  const xLabels = data.filter((_, i) => i % labelStep === 0).map((d, idx) => {
    const realIdx = idx * labelStep;
    const x = P + realIdx * xStep;
    const dateStr = String(d.run_id || '').slice(4, 8).replace(/(\d{2})(\d{2})/, '$1/$2');
    return `<text x="${x}" y="${H - 12}" text-anchor="middle">${dateStr}</text>`;
  }).join('');

  // Y-axis labels
  const yLabels = [maxS, 0, minS].map(s => `
    <text x="${P - 8}" y="${yScale(s) + 4}" text-anchor="end">${s.toFixed(0)}</text>
  `).join('');

  svg.innerHTML = `
    <g class="chart-axis">
      <line class="chart-zero" x1="${P}" y1="${yZero}" x2="${W - P}" y2="${yZero}"/>
      ${yLabels}
      ${xLabels}
    </g>
    <path class="chart-line" d="${path}"/>
    ${points}
  `;
}

function renderAll() {
  ['kospi', 'kosdaq'].forEach(m => {
    document.getElementById('count-' + m).textContent =
      (PAYLOAD.latest[m] || {}).top ? `(${PAYLOAD.latest[m].top.length})` : '(0)';
    renderRegime(m);
    renderTop(m);
    renderFrequent(m);
    renderChart(m);
  });
}

// Tab switching
document.querySelectorAll('.market-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const market = btn.dataset.market;
    document.querySelectorAll('.market-tab').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.market-panel').forEach(p =>
      p.classList.toggle('active', p.dataset.market === market));
  });
});

renderAll();
</script>

</body>
</html>
"""


def main():
    print(f"\n{'='*60}")
    print(f"📊 GitHub Pages 대시보드 생성")
    print(f"{'='*60}")

    payload = build_data_payload()

    # JSON으로도 저장 (디버깅/외부 분석용)
    data_path = DOCS_DIR / "data.json"
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # HTML 생성 — 데이터를 inline으로 박아넣음 (CORS 회피)
    payload_json = json.dumps(payload, ensure_ascii=False, default=str)
    html = HTML_TEMPLATE.replace("__DATA__", payload_json)

    out_path = DOCS_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")

    # 필터 페이지(docs/filter.html)가 fetch할 수 있도록 최신 CSV를 docs/로 복사
    import shutil
    for mkt in ("kospi", "kosdaq"):
        src = Path(f"latest_{mkt}_final.csv")
        if src.exists():
            try:
                shutil.copy(src, DOCS_DIR / src.name)
                print(f"  ✓ docs/{src.name} (필터 페이지용 복사)")
            except Exception as e:
                print(f"  ⚠️ {src.name} 복사 실패: {e}")

    size_kb = out_path.stat().st_size / 1024
    kospi_runs = len(payload.get("runs", {}).get("kospi", []))
    kosdaq_runs = len(payload.get("runs", {}).get("kosdaq", []))
    print(f"  ✓ docs/index.html  ({size_kb:.1f} KB)")
    print(f"  ✓ docs/data.json")
    print(f"  📈 KOSPI 실행 이력: {kospi_runs}건")
    print(f"  📈 KOSDAQ 실행 이력: {kosdaq_runs}건")
    print(f"\n✅ 완료 → GitHub Pages에서 자동 서빙됨")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
