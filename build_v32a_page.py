# -*- coding: utf-8 -*-
"""build_v32a_page.py — v3 트랙 챌린저 v32a(한산한 과매도) 관측 페이지 docs/v32a.html 생성. 표시 전용(점수·판정 무관), 읽기 전용.

PREREGISTER_v32a.md: v30 점수 그대로, 같은 (run×market) 셀의 21일 평균 거래대금(amt_avg_1m_억) 중앙값 이하만 남긴 '한산한 절반'.
그날 보기: history.db stage3_final 최신 run 을 v3_rescore 로 v30·v32a 두 번 재점수 → 시장별 점수 순 상위 10(동점 종목코드 순 — paper_engine 과 같음),
  v32a 목록의 v30 순위 · v30 상위 10 중 빠진 종목 · 20일 거래대금 · 참여율 1% 주문 상한(= 거래대금 × 1%).
쌓인 기록: v3_scores 의 v32a·v30 동결 점수(REG_DATE 이후 · 게이트 제외 · 앵커 중복 제거 — leaderboard 와 같은 함수)로
  앵커마다 D20 = (v32a 상위 10 − v30 상위 10) h20 동일가중 수익 차, 두 시장 평균. ohlcv.db 본표(성적표 트랙 A 와 같은 경로), 보유 중 정지·상폐는 마지막 가격.
  라벨 없음 — 판정은 유효 앵커 40 뒤 사전등록 §2·§3 로 한 번(사람이 적용). 실행: python build_v32a_page.py
"""
import html, os, sqlite3, sys
from datetime import datetime
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v3_rescore as v3
import leaderboard as lb
from checkup import REG_DATE
MODEL = "v32a"; REF = "v30"; TOP = 10; H = 20; GOAL = 40
OUT = os.path.join(HERE, "docs", "v32a.html"); DB = os.path.join(HERE, "history.db")
MK = {"kospi": "코스피", "kosdaq": "코스닥"}

CSS = """
  :root{--bg:#0f1115;--card:#171a21;--line:#262b36;--txt:#e6e8ec;--sub:#9aa3b2;--accent:#5aa9ff;--warn:#f0b429;--warnbg:#2a230f;--good:#2dd4a7;--bad:#f0997b}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;font-size:14px;line-height:1.5}
  .wrap{max-width:1200px;margin:0 auto;padding:16px} h1{font-size:18px;margin:0 0 4px} h2{font-size:14px;margin:18px 0 8px}
  .sub{color:var(--sub);font-size:12px;margin-bottom:14px} .sub a{color:var(--accent)}
  .warn{background:var(--warnbg);border:1px solid var(--warn);border-radius:10px;padding:12px 14px;margin-bottom:16px;font-size:12.5px} .warn b{color:var(--warn)}
  .explain{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:0 14px;margin-bottom:16px;font-size:12.5px}
  .explain summary{cursor:pointer;padding:12px 0;color:var(--accent);font-weight:600}
  .explain-body{padding:0 0 12px} .explain-body p{margin:8px 0;color:#c9cfda;line-height:1.65} .explain-body b{color:var(--txt)}
  .meta{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px} .chip{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:12px;color:var(--sub)} .chip b{color:var(--txt)}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;margin-bottom:14px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px} .kpi .l{color:var(--sub);font-size:11px} .kpi .v{font-size:18px;font-weight:700} .kpi .s{color:var(--sub);font-size:11px}
  .cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:14px}
  .tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px} table{border-collapse:collapse;width:100%;font-size:12px}
  th,td{padding:6px 7px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)} th{background:var(--card);color:var(--sub);font-weight:600}
  th:nth-child(2),td:nth-child(2){text-align:left} tr:hover td{background:#1b1f28}
  .same{color:var(--sub)} .new{color:var(--good);font-weight:600} .pos{color:var(--good)} .neg{color:var(--bad)}
  .foot{color:var(--sub);font-size:11px;margin-top:14px;line-height:1.7} .empty{padding:20px;text-align:center;color:var(--sub);background:var(--card);border:1px solid var(--line);border-radius:10px}
  @media (max-width:600px){.cols{grid-template-columns:1fr}}
"""
esc = html.escape


def top(df, n=TOP):
    return df.sort_values(["final_score_v3", "ticker"], ascending=[False, True]).head(n)


def today_lists(allruns, rid):
    """최신 run 의 시장별 (v32a 상위 10 표, v30 상위 10 중 빠진 종목 표, 요약)."""
    out = {}
    for mkt in ("kospi", "kosdaq"):
        sub = allruns[(allruns["run_id"] == rid) & (allruns["market"] == mkt)]
        if sub.empty:
            continue
        a = v3.rescore(sub.copy(), run_id=rid, market=mkt, spec=v3.MODELS[REF])
        w = v3.rescore(sub.copy(), run_id=rid, market=mkt, spec=v3.MODELS[MODEL])
        a_rank = {t: i + 1 for i, t in enumerate(a.sort_values(["final_score_v3", "ticker"], ascending=[False, True])["ticker"])}
        tw, ta = top(w), top(a)
        med = pd.to_numeric(sub["amt_avg_1m_억"], errors="coerce").median()
        dropped = ta[~ta["ticker"].isin(set(tw["ticker"]))]
        out[mkt] = dict(w=tw, a_rank=a_rank, a_top=set(ta["ticker"]), dropped=dropped, med=med, n=len(sub),
                        overlap=len(set(tw["ticker"]) & set(ta["ticker"])))
    return out


def d20_history(today):
    """REG_DATE 이후 v32a·v30 동결 점수로 앵커별 D20(완결)·진행 중 앵커 수. 실패하면 (None, 메시지)."""
    reg = REG_DATE.get(MODEL)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        S = pd.read_sql("SELECT run_id, market, ticker, model_id, final_score_v3 AS score FROM v3_scores WHERE model_id IN (?, ?) AND run_id >= ?",
                        con, params=[MODEL, REF, reg])
        if S[S.model_id == MODEL].empty:
            return None, f"첫 적재 대기 — 등록일 {reg}(예정) 배치부터 쌓입니다."
        close, _ = lb.load_ohlcv()
        partial, dbl, didx = lb.build_gates(con, close.index)
    finally:
        con.close()
    excl = partial | dbl
    keep = lb.dedupe_by_anchor(S[S.model_id == MODEL], didx, excl, reg=reg)
    dates = list(close.index); cf = close.ffill()          # 보유 중 정지·상폐 = 마지막 가격
    rows = []
    for rid in sorted(keep):
        t = lb.anchor(rid, didx)
        if t is None:
            continue
        e, x = t + 1, t + 1 + H
        done = x < len(dates)
        rec = dict(run_id=rid, done=done)
        if done:
            ds = []
            for mkt in ("kospi", "kosdaq"):
                r = {}
                for mid in (MODEL, REF):
                    g = S[(S.run_id == rid) & (S.market == mkt) & (S.model_id == mid)].dropna(subset=["score"])
                    tk = [k for k in top(g.rename(columns={"score": "final_score_v3"}))["ticker"] if k in close.columns]
                    p0, p1 = close.iloc[e][tk], cf.iloc[x][tk]
                    ok = p0.notna() & p1.notna() & (p0 > 0)
                    r[mid] = float(((p1[ok] / p0[ok] - 1) * 100).mean()) if ok.any() else np.nan
                ds.append(r[MODEL] - r[REF])
            rec["D20"] = float(np.nanmean(ds)) if np.isfinite(ds).any() else np.nan
        rows.append(rec)
    return pd.DataFrame(rows), None


def fmt(x, d=1, unit=""):
    return "—" if x is None or not np.isfinite(x) else f"{x:+.{d}f}{unit}"


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    allruns = v3.load_runs(DB); allruns["run_id"] = allruns["run_id"].astype(str)
    rid = allruns["run_id"].max(); reg = REG_DATE.get(MODEL, "")
    lists = today_lists(allruns, rid)
    hist, msg = d20_history(today)
    parts = [f"""<h1>한산한 과매도 v32a — v3 트랙 챌린저 (관측)</h1>
<div class="sub">v30 점수 그대로 · 그날 시장 후보 중 1개월 평균 거래대금이 중앙값 이하인 절반만 · 점수 순 시장별 상위 10 · 가중 0 · <b>관측 전용</b> — <a href="https://github.com/sj951027/dh-q7m3k/blob/main/PREREGISTER_v32a.md">PREREGISTER_v32a.md</a> · <a href="leaderboard.html">리더보드로</a></div>
<div class="warn"><b>매수 추천이 아닙니다.</b> 사전등록한 규칙(v32a)이 앞으로 v30 보다 나은지 기록만 합니다. 판정은 유효 앵커 40개가 쌓인 뒤 한 번(사전등록 §2·§3). 근거는 전부 사후 관측(10년 자료의 v30 대리)이고, <b>거래가 적은 종목이라 큰 금액은 살 수 없습니다</b> — 아래 '참여율 1% 주문 상한' 열을 보세요.</div>
<details class="explain"><summary>이 규칙이 뭔가요 · 무엇을 재나요</summary><div class="explain-body">
<p><b>고르는 법</b>: v30 과 같은 점수로 줄 세우되, 그날 그 시장 후보 전체에서 최근 한 달 하루 평균 거래대금이 <b>중간보다 많은 종목은 뺍니다</b>(점수 −999, 기존 '제외'와 같은 처리). 남은 한산한 절반에서 상위 10.</p>
<p><b>재는 것(D20)</b>: 매 앵커마다 v32a 상위 10 과 v30 상위 10 을 다음 거래일 종가에 같은 금액으로 산 것으로 보고 20거래일 뒤 수익률 차이(v32a − v30)를 두 시장 평균. 두 목록이 같으면 그날 0.</p>
<p><b>왜</b>: 10년 자료에서 과매도 종목 중 거래대금 아래 절반이 과매도 전체보다 40일 +1.3%p(Codex 독립 +1.5) 높았습니다 — 코스닥 위주, 2025 는 음수, 주문이 커지면 약해짐. 2026-08 기각된 v31c(5억 미만 제외)와 같은 방향의 관측을 앞으로 고정된 규칙으로 재는 것입니다.</p>
<p><b>참여율 1% 주문 상한</b> = 20일 평균 거래대금 × 1%. 이보다 크게 사면 내 주문이 가격을 움직일 수 있다는 어림 기준(체결 보장 아님).</p></div></details>"""]
    chips = [f"승인 <b>2026-10-23</b>", f"등록일(첫 적재) <b>{esc(reg)}</b>", f"spec <b>{esc(__import__('freeze_scores').spec_hash(MODEL))}</b>", f"기준 run <b>{esc(rid)}</b>",
             f"분모(v3) <b>8</b>", f"생성 <b>{today}</b>"]
    parts.append('<div class="meta">' + "".join(f'<span class="chip">{c}</span>' for c in chips) + "</div>")
    # 쌓인 기록
    if hist is None:
        parts.append(f'<h2>쌓인 기록 (D20)</h2><div class="empty">{esc(msg)}</div>')
    else:
        dn = hist[hist.done]; n_all, n_done = len(hist), len(dn)
        d = dn["D20"].dropna()
        lo = hi = None
        if len(d) >= 5:
            rng = np.random.default_rng(7); bs = [rng.choice(d.values, len(d)).mean() for _ in range(4000)]; lo, hi = np.percentile(bs, [2.5, 97.5])
        parts.append('<h2>쌓인 기록 (D20 · 라벨 없음)</h2><div class="grid">'
                     f'<div class="kpi"><div class="l">유효 앵커</div><div class="v">{n_all} / {GOAL}</div><div class="s">판정은 40 도달 뒤 1회</div></div>'
                     f'<div class="kpi"><div class="l">20일 완결 앵커</div><div class="v">{n_done}</div><div class="s">진행 중 {n_all - n_done}</div></div>'
                     f'<div class="kpi"><div class="l">D20 평균 (v32a − v30)</div><div class="v {"pos" if len(d) and d.mean() > 0 else "neg" if len(d) else ""}">{fmt(d.mean() if len(d) else None, 2, "%p")}</div>'
                     f'<div class="s">{"95% [" + fmt(lo, 2) + ", " + fmt(hi, 2) + "]" if lo is not None else "구간은 완결 5개부터"}</div></div>'
                     f'<div class="kpi"><div class="l">D20 &gt; 0 인 앵커</div><div class="v">{int((d > 0).sum())} / {len(d)}</div><div class="s">같은 목록이면 0</div></div></div>')
    # 오늘 목록
    pre = rid < reg if reg else False
    parts.append(f'<h2>그날 목록 — run {esc(rid)}{" (등록 전 미리보기 · 표본 아님)" if pre else ""}</h2><div class="cols">')
    for mkt, L in lists.items():
        w = L["w"]
        trs = []
        for i, (_, r) in enumerate(w.iterrows(), 1):
            amt = pd.to_numeric(r.get("amt_avg_1m_억"), errors="coerce")
            ar = L["a_rank"].get(r["ticker"]); inv = r["ticker"] in L["a_top"]
            trs.append(f'<tr><td>{i}</td><td>{esc(str(r.get("name", "")))} <span class="same">{esc(r["ticker"])}</span></td><td>{r["final_score_v3"]:.1f}</td>'
                       f'<td class="{"same" if inv else "new"}">{ar if ar else "—"}{"" if inv else " (새로)"}</td><td>{esc(str(r.get("bucket", "")))}</td>'
                       f'<td>{"—" if not np.isfinite(amt) else f"{amt:.1f}"}</td><td>{"—" if not np.isfinite(amt) else f"{amt * 100:,.0f}만"}</td></tr>')
        dr = "".join(f'<tr><td>—</td><td>{esc(str(r.get("name", "")))} <span class="same">{esc(r["ticker"])}</span></td><td>{r["final_score_v3"]:.1f}</td><td>{L["a_rank"].get(r["ticker"], "—")}</td><td>빠짐</td>'
                     f'<td>{pd.to_numeric(r.get("amt_avg_1m_억"), errors="coerce"):.1f}</td><td>—</td></tr>' for _, r in L["dropped"].iterrows())
        parts.append(f'<div><div class="sub"><b>{MK[mkt]}</b> · 후보 {L["n"]}종목 · 거래대금 중앙값 {L["med"]:.1f}억 · v30 상위 10 과 겹침 <b>{L["overlap"]}/10</b></div>'
                     '<div class="tablewrap"><table><thead><tr><th>#</th><th>종목</th><th>점수</th><th>v30 순위</th><th>버킷</th><th>거래대금(억)</th><th>참여율1% 상한</th></tr></thead><tbody>'
                     + "".join(trs) + (f'<tr><td colspan="7" style="text-align:left;color:var(--sub)">v30 상위 10 중 거래대금이 많아 빠진 종목</td></tr>' + dr if dr else "")
                     + "</tbody></table></div></div>")
    parts.append("</div>")
    parts.append('<div class="foot">점수·버킷은 v3_rescore 로 그날 스냅샷을 다시 계산한 값(동결 점수와 같은 코드). 거래대금 = stage3 의 1개월 평균(원시 가격 × 거래량). '
                 'D20 은 동결 점수(v3_scores)·leaderboard 와 같은 게이트·앵커 규칙으로 계산한 관측값이며 판정이 아닙니다. 비용·희석 제외 없음. '
                 '판정은 PREREGISTER_v32a.md §2·§3 대로 유효 앵커 40 뒤 한 번.</div>')
    page = (f'<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">'
            f'<title>한산한 과매도 v32a · 관측 전용</title><style>{CSS}</style></head><body><div class="wrap">{"".join(parts)}</div><script src="common.js" defer></script></body></html>')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"✓ docs/v32a.html — run {rid} · 시장 {len(lists)} · 쌓인 앵커 {'0(대기)' if hist is None else len(hist)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠ build_v32a_page 실패(비치명): {e}")
        sys.exit(1)
