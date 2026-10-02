# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/model_rotation_20261002/ 에서 실행. 읽기 전용(history.db·ohlcv.db mode=ro).
"""rotation_study.py — "최근 잘한 모델을 따라가면 다음에도 이기는가" (2026-10-02, 관측·판정 아님)

질문: 매 거래일 T 에, 그때까지 '끝난' 성적만 보고 최근 1등 모델을 골라 그 모델의 오늘 상위10 을 따라 사면
      시장 평균을 이기는가? 그리고 '전 모델 고르게 섞기'·'꼴찌 따라가기'보다 나은가?

규칙(결과를 보기 전에 고정):
  · 모델 성적 = 성적표(build_scoreboard.py)와 같은 잣대: 시장별 점수 상위 10 을 다음날 종가에 사서 h 거래일 뒤 종가에 팖,
    초과 = 바스켓 평균 − 같은 시장 전 종목 동일가중 평균, 시장별 계산 후 평균. 앵커·게이트·등록일은 leaderboard.py 규약.
  · T 시점에 알 수 있는 성적 = 진입일+h 가 T 이하인 앵커만(미래 정보 금지).
  · '최근 폼' = 가장 최근에 끝난 앵커 L 개의 초과 평균. L 의 절반 이상 있어야 후보.
  · 설정 2개만: A) h=20·L=20 (주) / B) h=5·L=10 (보조 — 사용자가 단기 전환에 관심).
  · 대형(ls_t1)은 유니버스가 달라 제외. 후보 2개 미만인 날은 건너뜀.
  · 비교: 1등 따라가기 / 꼴찌 따라가기 / 후보 전부 고르게 / 고정 모델들.
  · 구간: 겹치는 날이 많아 h 일 블록 부트스트랩(2,000회, seed 7). '독립 구간 수' = 날 수 / h 를 같이 적는다.
"""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import leaderboard as lb            # noqa: E402
import build_scoreboard as bs       # noqa: E402

TOP, MIN_BASKET = bs.TOP, bs.MIN_BASKET
CONFIGS = [("A", 20, 20), ("B", 5, 10)]


def model_excess(con, m, close, mk, didx, excl, N, h):
    """{앵커 t: h일 초과(%p)} — 끝난 앵커만."""
    S = bs.load_scores(con, m)
    keep = lb.dedupe_by_anchor(S, didx, excl, reg=m["reg_date"])
    out = {}
    for rid in keep:
        t = lb.anchor(rid, didx)
        if t is None or t + 1 + h >= N:
            continue
        r = close.iloc[t + 1 + h] / close.iloc[t + 1] - 1
        g = S[S.run_id == rid].dropna(subset=["score"])
        ex = []
        for mkt, gm in g.groupby("market"):
            a = r.reindex(gm.nlargest(TOP, "score").ticker).dropna()
            b = r.reindex(mk.index[mk == mkt]).dropna()
            if len(a) >= MIN_BASKET and len(b):
                ex.append((a.mean() - b.mean()) * 100)
        if ex:
            out[t] = float(np.mean(ex))
    return pd.Series(out).sort_index()


def block_ci(x, h, k=2000, seed=7):
    x = np.asarray(x, float); n = len(x)
    if n < 2:
        return [float("nan")] * 2
    rng = np.random.default_rng(seed); nb = int(np.ceil(n / h)); res = []
    for _ in range(k):
        st = rng.integers(0, max(n - h + 1, 1), nb)
        res.append(np.concatenate([x[s:s + h] for s in st])[:n].mean())
    return [float(np.percentile(res, 2.5)), float(np.percentile(res, 97.5))]


def run(tag, h, L, EX, dates):
    models = list(EX)
    N = len(dates); rows = []; rho = []
    for T in range(N):
        form = {}
        for m in models:
            s = EX[m]
            known = s[s.index + 1 + h <= T]          # T 에 이미 끝난 앵커
            if len(known) == 0:
                continue
            recent = known.iloc[-L:]
            # '최근'이어야 한다: 마지막 끝난 앵커가 T 에서 너무 멀면(적재 중단) 후보 아님
            if len(recent) >= L / 2 and (T - 1 - h) - recent.index[-1] <= 5:
                form[m] = recent.mean()
        nxt = {m: EX[m].get(T) for m in form if T in EX[m].index}
        if len(nxt) < 2:
            continue
        f = pd.Series({m: form[m] for m in nxt}); r = pd.Series(nxt)
        lead, lag = f.idxmax(), f.idxmin()
        rows.append({"date": dates[T], "n_models": len(nxt), "leader": lead, "laggard": lag,
                     "lead_ret": r[lead], "lag_ret": r[lag], "mix_ret": r.mean(),
                     **{f"fix_{m}": r.get(m, np.nan) for m in models}})
        if len(nxt) >= 4:
            rho.append(f.rank().corr(r.rank()))
    D = pd.DataFrame(rows)
    if D.empty:
        print(f"[{tag}] 결정일 없음"); return None
    out = {"config": tag, "h": h, "L": L, "n_days": int(len(D)), "indep_windows": round(len(D) / h, 1),
           "first": D.date.min(), "last": D.date.max()}

    def stat(x):
        x = pd.Series(x).dropna().values
        return {"n": int(len(x)), "mean": float(np.mean(x)), "ci": block_ci(x, h), "pos": float((x > 0).mean())}
    out["leader"] = stat(D.lead_ret); out["laggard"] = stat(D.lag_ret); out["mix"] = stat(D.mix_ret)
    out["leader_minus_mix"] = stat(D.lead_ret - D.mix_ret)
    out["leader_minus_laggard"] = stat(D.lead_ret - D.lag_ret)
    out["rank_corr_mean"] = float(np.nanmean(rho)) if rho else None
    out["rank_corr_n"] = len(rho)
    out["leader_counts"] = D.leader.value_counts().to_dict()
    out["fixed"] = {m: stat(D[f"fix_{m}"]) for m in models if D[f"fix_{m}"].notna().sum() >= max(h, 10)}
    D.to_csv(Path(__file__).parent / f"decisions_{tag}.csv", index=False, encoding="utf-8-sig")
    return out


def main():
    close, mktmap = lb.load_ohlcv(); dates = list(close.index); N = len(dates)
    mk = pd.Series(mktmap).str.lower()
    con = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    lbj = json.loads((REPO / "docs/leaderboard.json").read_text(encoding="utf-8"))
    ms = [m for m in lbj["models"] if m["model"] in bs.NAME and m["track"] != "large"]
    res = []
    for tag, h, L in CONFIGS:
        EX = {}
        for m in ms:
            s = model_excess(con, m, close, mk, didx, excl, N, h)
            if len(s):
                EX[m["model"]] = s
        print(f"[{tag}] h={h} L={L} · 모델 {len(EX)}개 · 앵커 수 " + ", ".join(f"{k}:{len(v)}" for k, v in EX.items()))
        r = run(tag, h, L, EX, dates)
        if r:
            res.append(r)
    con.close()
    (Path(__file__).parent / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in res:
        print(f"\n== 설정 {r['config']}: {r['h']}일 보유 · 최근 {r['L']}개 폼 · 결정일 {r['n_days']}일({r['first']}~{r['last']}) · 독립 구간 약 {r['indep_windows']}개")
        for k, nm in (("leader", "1등 따라가기"), ("mix", "고르게 섞기"), ("laggard", "꼴찌 따라가기"),
                      ("leader_minus_mix", "1등 − 섞기"), ("leader_minus_laggard", "1등 − 꼴찌")):
            s = r[k]; print(f"  {nm:<10} 평균 {s['mean']:+6.2f}%p  [{s['ci'][0]:+.2f}, {s['ci'][1]:+.2f}]  양수 {s['pos']*100:.0f}%  n={s['n']}")
        print(f"  폼 순위 ↔ 다음 성적 순위 상관(평균): {r['rank_corr_mean']}  (n={r['rank_corr_n']}일)")
        print(f"  1등으로 뽑힌 횟수: {r['leader_counts']}")
        for m, s in sorted(r["fixed"].items(), key=lambda kv: -kv[1]["mean"]):
            print(f"    고정 {m:<6} 평균 {s['mean']:+6.2f}%p  [{s['ci'][0]:+.2f}, {s['ci'][1]:+.2f}]  n={s['n']}")


if __name__ == "__main__":
    main()
