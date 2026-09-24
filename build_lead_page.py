# -*- coding: utf-8 -*-
"""build_lead_page.py — lead 트랙(ld_a) 관측 페이지 docs/lead.html 생성. 표시 전용(점수·판정 무관), 읽기 전용.

입력: history.db lead_picks(ld_a·ld_ctl_amt) + lead_universe, ohlcv.db(가격·지수). 출력: docs/lead.html.
앵커별: 진입(t+1 종가) → 오늘(진행 중) 또는 t+1+120(창 마감)까지 바스켓 수익, ① 픽 시장비중 지수 ② 앵커 유니버스 동일가중 ③ 대조군.
누적: 창 마감 앵커만, 6개월 원형 블록 CI(n≥3 일 때만), 비겹침 창 부호. 라벨 없음(PREREGISTER_ld_a §3 는 사람이 적용).
picks 가 없으면 '첫 앵커 대기' 페이지를 쓴다. 실행: python build_lead_page.py
"""
import html, os, sqlite3, sys
from datetime import datetime
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import lead_observe as lo
H = 120; COST = 0.005; OUT = os.path.join(HERE, "docs", "lead.html")

def block_ci(x, block=6, reps=3000, seed=924):
    x = np.asarray(x, float); x = x[np.isfinite(x)]; L = len(x)
    if L < 3: return None
    rng = np.random.default_rng(seed); block = min(block, L)
    st = rng.integers(0, L, (reps, int(np.ceil(L / block)))); ix = (st[:, :, None] + np.arange(block)) % L
    mm = x[ix.reshape(reps, -1)[:, :L]].mean(axis=1)
    return (float(np.quantile(mm, .025)), float(np.quantile(mm, .975)))

def pct(x): return "—" if x is None or not np.isfinite(x) else f"{x*100:+.1f}%"
def pp(x): return "—" if x is None or not np.isfinite(x) else f"{x*100:+.1f}%p"
def cls(x): return "" if x is None or not np.isfinite(x) else ("pos" if x > 0 else "neg")

CSS = """
  :root{--bg:#0f1115;--card:#171a21;--line:#262b36;--txt:#e6e8ec;--sub:#9aa3b2;--accent:#5aa9ff;--warn:#f0b429;--warnbg:#2a230f;--good:#2dd4a7;--bad:#f0997b}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;font-size:14px;line-height:1.5}
  .wrap{max-width:1600px;margin:0 auto;padding:16px} h1{font-size:18px;margin:0 0 4px} h2{font-size:14px;margin:18px 0 8px}
  .sub{color:var(--sub);font-size:12px;margin-bottom:14px} .sub a{color:var(--accent)}
  .warn{background:var(--warnbg);border:1px solid var(--warn);border-radius:10px;padding:12px 14px;margin-bottom:16px;font-size:12.5px} .warn b{color:var(--warn)}
  .explain{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:0 14px;margin-bottom:16px;font-size:12.5px}
  .explain summary{cursor:pointer;padding:12px 0;color:var(--accent);font-weight:600;list-style:none} .explain summary::-webkit-details-marker{display:none}
  .explain-body{padding:0 0 12px} .explain-body p{margin:8px 0;color:#c9cfda;line-height:1.65} .explain-body b{color:var(--txt)}
  .warnp{background:#1f1a0c;border-left:3px solid var(--warn);padding:9px 12px;color:#e8dcc0} .warnp b{color:var(--warn)}
  .meta{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px} .chip{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:12px;color:var(--sub)} .chip b{color:var(--txt)}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;margin-bottom:14px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px} .kpi .l{color:var(--sub);font-size:11px} .kpi .v{font-size:18px;font-weight:700} .kpi .s{color:var(--sub);font-size:11px}
  .badge{display:inline-block;border-radius:6px;padding:2px 7px;font-size:11px;border:1px solid var(--line);color:var(--sub);margin-left:6px} .badge.open{border-color:var(--warn);color:var(--warn)} .badge.done{border-color:var(--good);color:var(--good)}
  .tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px} table{border-collapse:collapse;width:100%;font-size:11.5px}
  th,td{padding:6px 7px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)} th{background:var(--card);color:var(--sub);font-weight:600;position:sticky;top:0}
  th:first-child,td:first-child,th:nth-child(3),td:nth-child(3){text-align:left} tr:hover td{background:#1b1f28}
  .tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px} .tab{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 12px;cursor:pointer;font-size:12px;color:var(--sub)} .tab.active{border-color:var(--accent);color:var(--accent)}
  .pos{color:var(--good)} .neg{color:var(--bad)} .foot{color:var(--sub);font-size:11px;margin-top:14px;line-height:1.7} .empty{padding:30px;text-align:center;color:var(--sub);background:var(--card);border:1px solid var(--line);border-radius:10px}
"""
HEAD = """<h1>주도주 관측 — ld_a (lead 트랙)</h1>
<div class="sub">고베타 × 최근 52주 신고가 · 매월 첫 거래일 상위 20 · 120거래일 보유 · 동행그룹당 4종목 · 가중 0 · <b>관측 전용</b> — <a href="https://github.com/sj951027/dh-q7m3k/blob/main/PREREGISTER_ld_a.md">PREREGISTER_ld_a.md</a> · <a href="leaderboard.html">리더보드로</a></div>
<div class="warn"><b>추천 목록이 아닙니다.</b> 사전등록한 규칙이 새 데이터에서 어떻게 되는지 기록만 합니다. 판정은 겹치지 않는 120일 창 3개가 쌓인 뒤(≈2028-03) 한 번 — 그 전엔 '관측 중'. 리더보드(매일 상위 10·40일 보유 잣대)와 규칙이 달라 그 표에는 넣지 않습니다. 손절·익절 없음(연구에서 손절이 성과를 깎았음).</div>
<details class="explain"><summary>이 규칙이 뭔가요 · 무엇과 비교하나요</summary><div class="explain-body">
<p><b>고르는 법</b>: 가드(거래정지·급등락·저유동 제외)를 통과한 전 종목을 두 가지로 줄 세워 더합니다 — 지수와 같이 크게 움직이는 종목(베타60 높을수록), 최근에 52주 신고가를 찍은 종목(경과일 짧을수록). 상위 20을 사되 수익률이 같이 움직이는 동행그룹에서 4개까지만.</p>
<p><b>비교 셋</b>: ① 뽑힌 종목의 코스피/코스닥 비중대로 섞은 지수 ② 같은 날 가드 유니버스 전체를 동일가중으로 산 것 ③ 그냥 거래대금 상위 20을 산 것(대조군). ③을 못 이기면 "주도주 규칙"이 아니라 "큰 종목 사기"일 뿐입니다.</p>
<div class="warnp"><b>읽을 때 주의</b>: 한 앵커 수익은 그 반년 시장의 결과가 대부분입니다. 앵커가 여러 개 쌓여 구간(CI)이 나올 때까지 좋고 나쁨을 말하지 않습니다.</div></div></details>"""

DAILY_JSON = os.path.join(HERE, "docs", "hist", "lead_daily.json"); DAILY_KEEP = 10

def update_daily(today, oc):
    """오늘 기준 ld_a 상위 20(참고 · 동결 아님)을 docs/hist/lead_daily.json 에 누적(최근 DAILY_KEEP 거래일). 실패는 비치명."""
    try:
        data = {"days": []}
        if os.path.exists(DAILY_JSON):
            import json; data = json.loads(open(DAILY_JSON, encoding="utf-8").read())
        if any(d["date"] == today for d in data["days"]): return data
        nrow = oc.execute("SELECT COUNT(*) FROM daily_ohlcv WHERE date=?", (today,)).fetchone()[0]
        if nrow < 2000: return data
        P, _ = lo.load_panel(today); F = lo.compute(P); ai = int(np.where(P["dates"] == today)[0][0])
        rows_m, _, meta = lo.select(P, F, ai); nm = lo.names_map()
        day = {"date": today, "n_universe": meta["n_universe"], "cap_applied": meta["cap_applied"],
               "rows": [{"rank": r["rank"], "ticker": r["ticker"], "name": nm.get(r["ticker"], ""), "market": r["market"], "beta60": round(r["beta60"], 3),
                         "dsh": r["days_since_high"], "cluster": r["cluster"], "amt20": r["amt20"], "close": r["close"]} for r in rows_m]}
        data["days"] = sorted([d for d in data["days"] if d["date"] != today] + [day], key=lambda d: d["date"], reverse=True)[:DAILY_KEEP]
        import json; os.makedirs(os.path.dirname(DAILY_JSON), exist_ok=True)
        open(DAILY_JSON, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False))
        return data
    except Exception as e:
        print(f"  [경고] 일별 참고 목록 갱신 실패(비치명): {e}"); return {"days": []}

def daily_html(data, oc, today):
    days = data.get("days", [])
    if not days: return ""
    tk = sorted({r["ticker"] for d in days for r in d["rows"]})
    q = ",".join("?" * len(tk))
    latest = dict(oc.execute(f"SELECT ticker, close FROM daily_ohlcv WHERE date=? AND ticker IN ({q})", (today, *tk)).fetchall())
    tabs = "".join(f'<button class="tab{" active" if i == 0 else ""}" data-i="{i}">{d["date"][4:6]}/{d["date"][6:]}</button>' for i, d in enumerate(days))
    panes = []
    for i, d in enumerate(days):
        tr = "".join(f"<tr><td>{r['rank']}</td><td>{r['ticker']}</td><td>{html.escape(r.get('name') or '')}</td><td>{r['market']}</td><td>{r['beta60']:.2f}</td><td>{'' if r['dsh'] is None else r['dsh']}</td><td>{r['cluster']}</td><td>{r['amt20']/1e8:,.0f}억</td><td>{r['close']:,.0f}</td><td class='{cls((latest.get(r['ticker'], np.nan) / r['close'] - 1) if r['close'] else np.nan)}'>{pct((latest.get(r['ticker'], np.nan) / r['close'] - 1) if r['close'] else np.nan)}</td></tr>" for r in d["rows"])
        panes.append(f'<div class="pane" data-i="{i}"{"" if i == 0 else " hidden"}><div class="sub">유니버스 {d["n_universe"]:,} · 그룹 상한 {"적용" if d["cap_applied"] else "미적용"} · 그날 종가 → {today} 종가 등락</div><div class="tablewrap"><table><thead><tr><th>#</th><th>코드</th><th>종목</th><th>시장</th><th>베타60</th><th>신고가 후 일수</th><th>동행그룹</th><th>거래대금20</th><th>그날 종가</th><th>이후 등락</th></tr></thead><tbody>{tr}</tbody></table></div></div>')
    return f"""<h2>오늘 기준 순위 — 최근 {len(days)}거래일 <span class="badge">참고 · 동결 아님 · 판정에 안 씀</span></h2>
<div class="sub">같은 규칙을 매일 돌려 본 것입니다. 실제 기록(위 앵커)은 <b>매월 첫 거래일</b> 것만 동결되고, 판정도 그것만 씁니다. 이 탭은 "규칙이 지금 무엇을 가리키나"를 보는 용도입니다.</div>
<div class="tabs">{tabs}</div>{"".join(panes)}
<script>document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.pane').forEach(p=>p.hidden=p.dataset.i!==b.dataset.i);}});</script>"""

def main():
    hc = sqlite3.connect(f"file:{lo.HIST}?mode=ro", uri=True)
    try:
        picks = pd.read_sql(f"SELECT * FROM {lo.TABLE}", hc)
        uni = pd.read_sql(f"SELECT * FROM {lo.UNI_TABLE}", hc)
    except Exception:
        picks = pd.DataFrame(); uni = pd.DataFrame()
    hc.close()
    oc = sqlite3.connect(f"file:{lo.OHLCV}?mode=ro", uri=True)
    dates = [r[0] for r in oc.execute("SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
    md = pd.read_sql("SELECT series,date,close FROM market_daily", oc).pivot(index="date", columns="series", values="close").reindex(dates).ffill()
    today = dates[-1]; blocks = []
    for run_id, g in sorted(picks.groupby("run_id"), key=lambda kv: kv[0], reverse=True) if len(picks) else []:
        t = dates.index(run_id); e = t + 1
        if e >= len(dates): continue
        closed = t + 1 + H < len(dates); end = t + 1 + H if closed else len(dates) - 1
        de, dend = dates[e], dates[end]; elapsed = end - e
        px = pd.read_sql("SELECT ticker,date,close,volume FROM daily_ohlcv WHERE date IN (?,?)", oc, params=(de, dend))
        pe = px[px.date == de].set_index("ticker"); pend = px[px.date == dend].set_index("ticker").close
        last = pd.read_sql("SELECT ticker, close FROM daily_ohlcv WHERE date<=? GROUP BY ticker HAVING date=max(date)", oc, params=(dend,)).set_index("ticker").close
        def r_(tk):
            if tk not in pe.index or not (pe.loc[tk, "close"] > 0 and pe.loc[tk, "volume"] > 0): return 0.0   # 진입 불가 = 현금
            out = pend.get(tk, last.get(tk, np.nan)); return out / pe.loc[tk, "close"] - 1 if np.isfinite(out) else -1.0
        gm = g[g.model_id == lo.MODEL].sort_values("rank"); gc = g[g.model_id == lo.CONTROL]
        rows = []
        for _, r in gm.iterrows():
            ret = r_(r.ticker); idx = (md.loc[dend, "KOSPI"] / md.loc[de, "KOSPI"] - 1) if r.market == "KOSPI" else (md.loc[dend, "KOSDAQ"] / md.loc[de, "KOSDAQ"] - 1)
            rows.append(dict(r, ret=ret, ex=ret - idx))
        ik = md.loc[dend, "KOSPI"] / md.loc[de, "KOSPI"] - 1; iq = md.loc[dend, "KOSDAQ"] / md.loc[de, "KOSDAQ"] - 1
        pk = float((gm.market == "KOSPI").mean()); bench = pk * ik + (1 - pk) * iq
        ret_m = float(np.mean([r["ret"] for r in rows])) - COST; ret_c = float(np.mean([r_(tk) for tk in gc.ticker])) - COST if len(gc) else np.nan
        u = uni[uni.run_id == run_id].ticker.tolist(); ew = float(np.mean([r_(tk) for tk in u])) - COST if u else np.nan
        blocks.append(dict(anchor=run_id, entry=de, asof=dend, closed=closed, elapsed=elapsed, rows=rows, ret=ret_m, bench=bench, ew=ew, ctl=ret_c,
                           kospi_share=pk, ik=ik, iq=iq, n_universe=int(gm.n_universe.iloc[0]) if len(gm) else len(u), cap=int(gm.cap_applied.min()) if len(gm) else 0))
    daily = update_daily(today, oc); daily_section = daily_html(daily, oc, today)
    oc.close()
    parts = [HEAD]
    n_closed = sum(b["closed"] for b in blocks); n_open = len(blocks) - n_closed
    # 다음 앵커: 오늘 이후 첫 달 첫 거래일 (표시용 추정)
    nxt = (pd.Timestamp(today) + pd.offsets.MonthBegin(1)).strftime("%Y-%m") if today else "—"
    non, lastt = [], -10**9
    for b in sorted(blocks, key=lambda b: b["anchor"]):
        if b["closed"] and dates.index(b["anchor"]) - lastt >= H: non.append(b); lastt = dates.index(b["anchor"])
    parts.append(f"""<div class="meta"><span class="chip">등록 <b>2026-09-24</b></span><span class="chip">첫 앵커 <b>2026-10-01</b></span><span class="chip">앵커 <b>{len(blocks)}</b>개 (마감 {n_closed} · 진행 {n_open})</span><span class="chip">비겹침 창 <b>{len(non)}/3</b></span><span class="chip">spec <b>{lo.spec_hash(lo.MODEL)}</b></span><span class="chip">다음 앵커 <b>{nxt} 첫 거래일</b></span><span class="chip">기준일 <b>{today}</b></span></div>""")
    if not blocks:
        parts.append('<div class="empty">아직 적재된 앵커가 없습니다. 첫 앵커는 2026-10-01(목) 배치에서 저장되고, 이 페이지는 그때부터 채워집니다.</div>')
    else:
        closed_b = [b for b in blocks if b["closed"]]
        trs = []
        for key, lab in [("bench", "① 픽 시장비중 지수 대비"), ("ew", "② 유니버스 동일가중 대비"), ("ctl", "③ 대조군(거래대금 상위20) 대비")]:
            xs = [b["ret"] - b[key] for b in closed_b if np.isfinite(b[key])]
            mean = float(np.mean(xs)) if xs else np.nan; ci = block_ci(xs) if xs else None
            signs = "".join("+" if (b["ret"] - b[key]) > 0 else "−" for b in non if np.isfinite(b[key]))
            trs.append(f'<tr><td>{lab}</td><td class="{cls(mean)}">{pp(mean)}</td><td>{("[" + pp(ci[0]) + ", " + pp(ci[1]) + "]") if ci else "n&lt;3 · 계산 안 함"}</td><td>{len(xs)}</td><td>{signs or "—"}</td></tr>')
        parts.append(f'<h2>누적 (창 마감 앵커만 · 비용 {COST*100:.1f}% 후)</h2><div class="tablewrap"><table><thead><tr><th>비교</th><th>평균 초과</th><th>95% 구간(6개월 블록)</th><th>앵커 n</th><th>비겹침 창 부호</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div>')
        for b in blocks:
            a = b["anchor"]; badge = '<span class="badge done">창 마감 · 120일</span>' if b["closed"] else f'<span class="badge open">진행 중 · {b["elapsed"]}/120일</span>'
            head_ret = "120일 수익" if b["closed"] else f"현재까지({b['elapsed']}일)"
            tr = "".join(f"<tr><td>{int(r['rank'])}</td><td>{r['ticker']}</td><td>{html.escape(str(r.get('name') or ''))}</td><td>{r['market']}</td><td>{r['beta60']:.2f}</td><td>{'' if pd.isna(r['days_since_high']) else int(r['days_since_high'])}</td><td>{int(r['cluster'])}</td><td>{r['amt20']/1e8:,.0f}억</td><td class='{cls(r['ret'])}'>{pct(r['ret'])}</td><td class='{cls(r['ex'])}'>{pp(r['ex'])}</td></tr>" for r in b["rows"])
            ewx = b["ret"] - b["ew"] if np.isfinite(b["ew"]) else np.nan
            parts.append(f"""<h2>앵커 {a[:4]}-{a[4:6]}-{a[6:]} {badge}</h2>
<div class="meta"><span class="chip">진입 <b>{b['entry']}</b> 종가 · 기준일 <b>{b['asof']}</b></span><span class="chip">유니버스 <b>{b['n_universe']:,}</b> 종목</span><span class="chip">코스피 비중 <b>{b['kospi_share']*100:.0f}%</b></span><span class="chip">그룹 상한 <b>{'적용' if b['cap'] else '미적용'}</b></span></div>
<div class="grid">
 <div class="kpi"><div class="l">바스켓 수익(비용 {COST*100:.1f}% 후)</div><div class="v {cls(b['ret'])}">{pct(b['ret'])}</div><div class="s">동일가중 20종목</div></div>
 <div class="kpi"><div class="l">① 픽 시장비중 지수</div><div class="v">{pct(b['bench'])}</div><div class="s">초과 <b class="{cls(b['ret']-b['bench'])}">{pp(b['ret']-b['bench'])}</b> · KOSPI {pct(b['ik'])} / KOSDAQ {pct(b['iq'])}</div></div>
 <div class="kpi"><div class="l">② 유니버스 동일가중</div><div class="v">{pct(b['ew'])}</div><div class="s">초과 <b class="{cls(ewx)}">{pp(ewx)}</b></div></div>
 <div class="kpi"><div class="l">③ 대조군(거래대금 상위20)</div><div class="v">{pct(b['ctl'])}</div><div class="s">초과 <b class="{cls(b['ret']-b['ctl'])}">{pp(b['ret']-b['ctl'])}</b></div></div>
</div>
<div class="tablewrap"><table><thead><tr><th>#</th><th>코드</th><th>종목</th><th>시장</th><th>베타60</th><th>신고가 후 일수</th><th>동행그룹</th><th>거래대금20</th><th>{head_ret}</th><th>같은 시장 지수 대비</th></tr></thead><tbody>{tr}</tbody></table></div>""")
    parts.append(daily_section)
    parts.append(f'<div class="foot">잣대·라벨 규칙: PREREGISTER_ld_a.md §3 · 적재: lead_observe.py(월 첫 거래일) · 평가: lead_eval.py · 이 페이지는 표시 전용(점수·판정 무관). 비용 왕복 {COST*100:.1f}%, 종가 체결 가정, 진입 불가는 현금, 거래정지는 마지막 관측가. 한 앵커의 수익은 독립 표본이 아니라 그 반년 장세 하나. 생성 {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>')
    page = f'<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>주도주 관측 (ld_a) · 관측 전용</title><style>{CSS}</style></head><body><div class="wrap">{"".join(parts)}</div></body></html>'
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh: fh.write(page)
    print(f"  ✓ docs/lead.html — 앵커 {len(blocks)}개(마감 {n_closed}) · 기준일 {today}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
