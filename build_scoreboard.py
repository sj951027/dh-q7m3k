# -*- coding: utf-8 -*-
"""build_scoreboard.py — 모델 성적표(docs/scoreboard.json) 생성 · 표시 전용 · 판정 아님 (2026-09-18)

"모델 등록일부터 매 거래일, 시장별 상위 10을 다음날 종가에 사서 40거래일 뒤 종가에 팔았다면" 을 전 모델에 같은 규칙으로 잰다.
  · 앵커/게이트/거래일 매핑은 leaderboard.py 규약(anchor · dedupe_by_anchor · build_gates) 그대로
  · 비교 = 같은 시장 전체 종목 동일가중 평균(ohlcv.db 에 그날 가격이 있는 종목) · 시장별 계산 후 평균
  · 대형(ls_t1)은 그 run 의 large_final 전체가 비교대상 (트랙 A 와 숫자 비교 금지)
  · 점프컷 없음 · 비용 0(화면에 왕복 0.35 병기) · 희석 배지 제외·PIT 유니버스·40일 블록 CI 는 미적용 → 그래서 '참고 성적'
  · 검증 결론(고정)은 docs/models_registry.json sealed, 지금 흐름(참고)은 docs/leaderboard.json h20/h5 를 그대로 옮긴다
읽기 전용(mode=ro) · 점수·판정·게이트 코드 미접촉 · 실패해도 비치명. 실행: python build_scoreboard.py
연구용 원본: research/hold40_observe.py (2026-09-17 샘플). 이 파일이 운영본.
"""
import json, sqlite3, sys
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); import leaderboard as lb

H = 40; TOP = 10; COST = 0.35; MIN_BASKET = 5
NAME = {"v30": "과매도 v3", "lv_b": "저변동 lv_b", "lv_a": "저변동+반전 lv_a", "lv_e": "저변동+저회전 lv_e", "mom_a": "모멘텀 mom_a",
        "mom_b": "모멘텀+눌림 mom_b", "sm_a": "초소형 sm_a", "sv_a": "공매도비중 sv_a", "sv_b": "공매도+신용 sv_b", "le_a": "저점탈출 le_a",
        "qs_a": "조용한강자 qs_a", "px_a": "가격4팩터 px_a", "ls_t1": "대형밸류 ls_t1"}
TBL = {"v3": ("v3_scores", "final_score_v3"), "lowvol": ("lowvol_scores", "lowvol_score"), "wu": ("wu_scores", "wu_score")}


def boot(a, k=2000, seed=7):
    a = np.asarray(a, float); rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(k)]; return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def load_scores(con, m):
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


def observe(con, m, close, mk, dates, didx, excl, reg_json):
    N = len(dates); S = load_scores(con, m); reg = m["reg_date"]; is_large = m["track"] == "large"
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
            if len(a) >= MIN_BASKET: nw.append(a.mean() * 100); bn.append(b.mean() * 100)
            if done:
                a = r_fix.reindex(top).dropna(); b = r_fix.reindex(uni).dropna()
                if len(a) >= MIN_BASKET: fx.append(a.mean() * 100); bf.append(b.mean() * 100)
        rows.append({"date": dates[t], "done": bool(done and fx), "ret40": np.mean(fx) if fx else None, "bench40": np.mean(bf) if bf else None,
                     "ret_now": np.mean(nw) if nw else None, "bench_now": np.mean(bn) if bn else None})
    df = pd.DataFrame(rows, columns=["date", "done", "ret40", "bench40", "ret_now", "bench_now"])   # 앵커 0개(등록 직후)여도 컬럼 보장
    out = {"model": m["model"], "name": NAME.get(m["model"], m["model"]), "track": m["track"], "reg_date": reg, "n_anchors": int(len(df))}
    d = df[df.done.astype(bool)]
    if len(d):
        ex = (d.ret40 - d.bench40).values
        out["fix"] = {"n": int(len(d)), "blocks": round(len(d) / H, 1), "ret_mean": float(d.ret40.mean()), "ret_median": float(d.ret40.median()), "bench_mean": float(d.bench40.mean()),
                      "exc_mean": float(ex.mean()), "exc_median": float(np.median(ex)), "win": float((ex > 0).mean()), "first": d.date.min(), "last": d.date.max(),
                      "ci_ref": boot(ex) if len(d) >= 4 else None, "worst": float(ex.min()), "best": float(ex.max())}
    else:
        out["fix"] = None
    t_reg = next((i for i, dd in enumerate(dates) if dd >= reg), None)
    if t_reg is not None:
        need = (t_reg + 1 + H) - (N - 1)
        out["first_done_eta"] = (datetime.strptime(dates[-1], "%Y%m%d") + pd.Timedelta(days=int(round(max(need, 0) * 1.45)))).strftime("%m/%d") if need > 0 else None
        w_end = dates[min(t_reg + H, N - 1)]
        out["verdict_window"] = f"{reg[4:6]}/{reg[6:]}~{w_end[4:6]}/{w_end[6:]}"
    dn = df.dropna(subset=["ret_now"])
    if len(dn):
        exn = (dn.ret_now - dn.bench_now).values
        out["now"] = {"n": int(len(dn)), "ret_mean": float(dn.ret_now.mean()), "ret_median": float(dn.ret_now.median()), "bench_mean": float(dn.bench_now.mean()),
                      "exc_mean": float(exn.mean()), "exc_median": float(np.median(exn)), "win": float((exn > 0).mean())}
    s = reg_json["sealed"].get(m["model"])
    out["sealed"] = ({"v": s["v"], "short": s.get("short", s["t"])} if s else None)
    h20 = m.get("h20") or {}; h5 = m.get("h5") or {}
    out["live"] = {"ic20": h20.get("ic"), "n": h20.get("n"), "ci": h20.get("ci"), "ic5": h5.get("ic"), "oos_days": m.get("oos_days")}
    out["retired"] = bool(m.get("retired")) or m["model"] in reg_json.get("retired", {})
    return out


def main():
    close, mktmap = lb.load_ohlcv(); dates = list(close.index)
    mk = pd.Series(mktmap).str.lower()
    con = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    lbj = json.loads((HERE / "docs/leaderboard.json").read_text(encoding="utf-8"))
    reg_json = json.loads((HERE / "docs/models_registry.json").read_text(encoding="utf-8"))
    res = [observe(con, m, close, mk, dates, didx, excl, reg_json) for m in lbj["models"] if m["model"] in NAME]
    con.close()
    res.sort(key=lambda r: (r["track"] == "large", r["retired"], -(r["fix"]["exc_mean"] if r["fix"] and r["fix"]["n"] >= 4 else -99)))   # 은퇴는 트랙 맨 아래
    payload = {"asof": dates[-1], "generated": datetime.now().isoformat(timespec="seconds"), "H": H, "TOP": TOP, "COST": COST,
               "note": "참고 성적 · 검증 결론 아님 · 사전등록 v5 와 뼈대 동일하나 희석 제외·PIT·블록 CI 미적용", "models": res}
    (HERE / "docs" / "scoreboard.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    done = sum(1 for r in res if r["fix"] and r["fix"]["n"] >= 4)
    print(f"  ✓ docs/scoreboard.json — {len(res)}모델 (40일 완결 4일↑ {done}개) · {dates[-1]} 기준")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠ scoreboard 생성 실패(비치명): {e}")
