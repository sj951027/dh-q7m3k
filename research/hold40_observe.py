# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행. 읽기 전용(mode=ro) · 관측 전용 · 판정 아님.
"""hold40_observe.py — "매일 시장별 상위 10을 사서 40거래일 보유했다면" 전 모델 관측표 (2026-09-17 샘플)

규약(운용 채택 사전등록 v5 와 같은 뼈대, 단 관측 전용):
  · 앵커 = 등록일 이후 매 거래일(leaderboard 규약: 게이트 run 제외, 비거래일 run 은 직전 거래일)
  · 시장별 점수 상위 10 동일가중 · 다음 거래일 종가 매수 · 40거래일 뒤 종가 매도 · 점프컷 없음 · 비용 0(각주에 0.35 병기)
  · 비교 = 같은 시장 전체 종목 동일가중 평균(ohlcv.db 에 그날 가격이 있는 종목) · 시장별 계산 후 평균
  · 대형(ls_t1)은 그 run 의 large_final 전체 = 비교대상
  · 사전등록과 다른 점: 희석 배지 제외 안 함 · PIT 유니버스 아님 · 40일 블록 부트스트랩 대신 iid 참고 구간만 → 그래서 '판정 아님'
출력: research/out_hold40/hold40_observe.json · research/handoff/mock_006_claude_hold40.html
"""
import json, sqlite3, sys
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO)); import leaderboard as lb

H = 40; TOP = 10; COST = 0.35
NAME = {"v30": "과매도 v3", "lv_b": "저변동 lv_b", "lv_a": "저변동+반전 lv_a", "lv_e": "저변동+저회전 lv_e", "mom_a": "모멘텀 mom_a",
        "mom_b": "모멘텀+눌림 mom_b", "sm_a": "초소형 sm_a", "sv_a": "공매도비중 sv_a", "sv_b": "공매도+신용 sv_b", "le_a": "저점탈출 le_a",
        "qs_a": "조용한강자 qs_a", "px_a": "가격4팩터 px_a", "ls_t1": "대형밸류 ls_t1"}
TBL = {"v3": ("v3_scores", "final_score_v3"), "lowvol": ("lowvol_scores", "lowvol_score"), "wu": ("wu_scores", "wu_score")}

close, mktmap = lb.load_ohlcv(); dates = list(close.index); N = len(dates)
mk = pd.Series(mktmap).str.lower()
con = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
LBJ = json.loads((REPO / "docs/leaderboard.json").read_text(encoding="utf-8"))
REG = json.loads((REPO / "docs/models_registry.json").read_text(encoding="utf-8"))
models = [m for m in LBJ["models"]]


def load_scores(m):
    if m["track"] == "large":
        lg = pd.read_sql("SELECT run_id, market, ticker, per, pbr, rim_spread, div_yield FROM large_final", con)
        fz = pd.DataFrame({"ep": 1.0 / lg["per"].where(lg["per"] > 0), "bp": 1.0 / lg["pbr"].where(lg["pbr"] > 0), "rim": lg["rim_spread"], "dv": lg["div_yield"]})
        rk = fz.groupby(lg["run_id"]).rank(pct=True)
        lg["score"] = rk.mean(axis=1, skipna=True).where(rk.notna().sum(axis=1) >= 2)
        S = lg[["run_id", "market", "ticker", "score"]]
    else:
        tbl, col = TBL[m["track"]]
        S = pd.read_sql(f"SELECT run_id, market, ticker, {col} AS score FROM {tbl} WHERE model_id=?", con, params=(m["model"],))
    S = S.copy(); S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str); S["market"] = S.market.str.lower()
    return S


def boot(a, k=2000, seed=7):
    a = np.asarray(a, float); rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(k)]; return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def observe(m):
    S = load_scores(m); reg = m["reg_date"]; is_large = m["track"] == "large"
    keep = lb.dedupe_by_anchor(S, didx, excl, reg=reg)
    rows = []
    for rid in keep:
        t = lb.anchor(rid, didx)
        if t is None or t + 1 >= N: continue
        e = close.iloc[t + 1]; done = t + 1 + H < N
        r_fix = (close.iloc[t + 1 + H] / e - 1) if done else None
        r_now = close.iloc[-1] / e - 1
        g = S[S.run_id == rid].dropna(subset=["score"])
        fx, bf, nw, bn = [], [], [], []
        for mkt, gm in g.groupby("market"):
            top = gm.nlargest(TOP, "score").ticker
            uni = gm.ticker if is_large else mk.index[mk == mkt]
            a = r_now.reindex(top).dropna(); b = r_now.reindex(uni).dropna()
            if len(a) >= 5: nw.append(a.mean() * 100); bn.append(b.mean() * 100)
            if done:
                a = r_fix.reindex(top).dropna(); b = r_fix.reindex(uni).dropna()
                if len(a) >= 5: fx.append(a.mean() * 100); bf.append(b.mean() * 100)
        rows.append({"date": dates[t], "done": bool(done and fx), "ret40": np.mean(fx) if fx else None, "bench40": np.mean(bf) if bf else None,
                     "ret_now": np.mean(nw) if nw else None, "bench_now": np.mean(bn) if bn else None, "days_held": N - 1 - (t + 1)})
    df = pd.DataFrame(rows)
    out = {"model": m["model"], "name": NAME.get(m["model"], m["model"]), "track": m["track"], "reg_date": reg, "n_anchors": int(len(df)), "retired": bool(m.get("retired"))}
    d = df[df.done] if len(df) else df
    if len(d) >= 1:
        ex = (d.ret40 - d.bench40).values
        out["fix"] = {"n": int(len(d)), "blocks": round(len(d) / H, 1), "ret_mean": float(d.ret40.mean()), "ret_median": float(d.ret40.median()), "bench_mean": float(d.bench40.mean()),
                      "exc_mean": float(ex.mean()), "exc_median": float(np.median(ex)), "win": float((ex > 0).mean()), "first": d.date.min(), "last": d.date.max(),
                      "ci_ref": boot(ex) if len(d) >= 4 else None, "worst": float(ex.min()), "best": float(ex.max())}
    else:
        out["fix"] = None
    # 첫 완결 예상: 등록 다음 거래일 + 1 + 40 거래일 → 달력 근사(거래일 1개 ≈ 1.45일)
    t_reg = next((i for i, dd in enumerate(dates) if dd >= reg), None)
    if t_reg is not None:
        need = (t_reg + 1 + H) - (N - 1)
        out["first_done_eta"] = (datetime.strptime(dates[-1], "%Y%m%d") + pd.Timedelta(days=int(round(max(need, 0) * 1.45)))).strftime("%m/%d") if need > 0 else None
    dn = df.dropna(subset=["ret_now"])
    if len(dn):
        exn = (dn.ret_now - dn.bench_now).values
        out["now"] = {"n": int(len(dn)), "ret_mean": float(dn.ret_now.mean()), "ret_median": float(dn.ret_now.median()), "bench_mean": float(dn.bench_now.mean()),
                      "exc_mean": float(exn.mean()), "exc_median": float(np.median(exn)), "win": float((exn > 0).mean())}
    # 판정(고정) · 현재 관측(움직임)
    s = REG["sealed"].get(m["model"]); lbm = m
    out["sealed"] = ({"v": s["v"], "short": s.get("short", s["t"])} if s else None)
    if t_reg is not None:
        w_end = dates[min(t_reg + H, N - 1)]
        out["verdict_window"] = f"{reg[4:6]}/{reg[6:]}~{w_end[4:6]}/{w_end[6:]}"
    h20 = lbm.get("h20") or {}
    out["live"] = {"ic20": h20.get("ic"), "n": h20.get("n"), "ci": h20.get("ci"), "ic5": (lbm.get("h5") or {}).get("ic"), "oos_days": lbm.get("oos_days")}
    out["retired"] = bool(m.get("retired")) or m["model"] in REG.get("retired", {})
    out["role"] = ("운용 중" if m["model"] == REG.get("live") else "참고 모델" if m["model"] == REG.get("reference") else "은퇴(기록)" if out["retired"] else "관측 중")
    return out


res = [observe(m) for m in models if m["model"] in NAME]
res.sort(key=lambda r: (r["track"] == "large", -(r["fix"]["exc_mean"] if r["fix"] and r["fix"]["n"] >= 4 else -99)))
payload = {"asof": dates[-1], "generated": datetime.now().isoformat(timespec="seconds"), "H": H, "TOP": TOP, "COST": COST,
           "note": "관측 전용 · 판정 아님 · 사전등록 v5 와 뼈대 동일하나 희석 제외·PIT·블록 CI 미적용", "models": res}
(HERE / "out_hold40").mkdir(exist_ok=True)
(HERE / "out_hold40" / "hold40_observe.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
for r in res:
    f = r["fix"]
    print(f"{r['model']:6s} {r['role']:6s} " + (f"n={f['n']:2d} 40일 {f['ret_mean']:+.1f}% (시장 {f['bench_mean']:+.1f}%) 초과 {f['exc_mean']:+.1f}%p 중앙 {f['exc_median']:+.1f}%p 이긴날 {f['win']:.0%}" if f else f"완결 없음 (첫 완결 ~{r.get('first_done_eta')})"))

# ---------------- HTML 샘플 ----------------
tpl = (HERE / "hold40_mock_template.html").read_text(encoding="utf-8")
html = tpl.replace("/*DATA*/", json.dumps(payload, ensure_ascii=False))
(HERE / "handoff" / "mock_006_claude_hold40.html").write_text(html, encoding="utf-8")
print("→ research/handoff/mock_006_claude_hold40.html")
