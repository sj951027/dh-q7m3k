# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/form_signals_20261003/ 에서 실행. 읽기 전용(history.db·ohlcv.db mode=ro).
"""form_signals.py — "지금 앞서는 중인 모델"을 보여 줄 신호 후보 10개가 다음 20거래일 성적을 조금이라도 말해 주는가 (2026-10-03, 관측)

질문: 결정일 d 에 그때까지 알 수 있는 것만으로 만든 신호 F(d, 모델) 가, 그 모델이 d 에 고른 상위10 의
      이후 20거래일 초과수익 Y(d, 모델) 와 관계가 있는가? (Y = 바스켓 평균 − 같은 시장 전종목 동일가중 평균, 시장별 계산 후 평균)

신호 후보(결과를 보기 전에 고정):
  F1 끝난 20일 초과 — 최근 20앵커 평균            (지난 갈아타기 연구의 '폼' 그대로, 기준선)
  F2 끝난 5일 초과 — 최근 10앵커 평균
  F3 열린 포지션 시가평가 — 최근 20앵커 바스켓의 d 까지 초과수익 평균(아직 안 끝난 것)
  F4 꾸준함 — 최근 20개 끝난 20일 초과 중 양(+)인 비율
  F5 IC(20일) — 최근 20앵커 평균
  F6 IC 꾸준함 — 최근 20앵커 IC 중 양(+) 비율
  F7 국면 맞춤 — 지금 국면(KOSDAQ>20일선 여부)과 같은 국면이었던 과거 앵커들의 IC 평균(≥5개)
  F8 모델 간 합의 — 오늘 이 모델 상위10 이 다른 모델들 상위10 과 겹치는 비율 평균
  F9 낙폭 — 최근 40앵커 누적 초과수익의 고점 대비 낙폭(0 이면 고점, 음수가 클수록 나쁨)
  F10 개선 — F3 − F1 (최근이 더 좋아지는 중인가)
평가(각 신호마다):
  (a) 모델 안: F 와 Y 의 순위상관(전 (d,모델) 쌍 합침, Y 는 그날 모델 평균을 뺀 상대값) — 20일 블록 부트스트랩 CI
  (b) 1등 따라가기: 매 결정일 F 가 가장 큰 모델의 Y − 그날 전 모델 평균 Y — 20일 블록 CI, 양수 비율
  (c) 날마다 모델 순위 상관(F 순위 vs Y 순위) 평균
표본: 등록일 필터 없이 동결 점수 전부(백필 포함 — 지속성 질문엔 PIT 가격만 맞으면 됨). 대형(ls_t1)은 유니버스가 달라 제외.
      결정일은 앵커(run)이면서 모델 3개 이상에 F·Y 가 있는 날. 끝난 Y 가 필요해 마지막 결정일 = 자료 끝 − 21거래일.
"""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
import leaderboard as lb            # noqa: E402
import build_scoreboard as bs       # noqa: E402

TOP, MIN_BASKET, H = bs.TOP, bs.MIN_BASKET, 20
MODELS = ["v30", "lv_b", "lv_a", "lv_e", "sm_a", "mom_a", "sv_a", "le_a", "qs_a", "px_a"]
MIN_MODELS = 3


def block_ci(x, h=20, k=2000, seed=7):
    x = np.asarray(x, float); n = len(x)
    if n < 2:
        return [float("nan")] * 2
    rng = np.random.default_rng(seed); nb = int(np.ceil(n / h)); res = []
    for _ in range(k):
        st = rng.integers(0, max(n - h + 1, 1), nb)
        res.append(np.concatenate([x[s:s + h] for s in st])[:n].mean())
    return [float(np.percentile(res, 2.5)), float(np.percentile(res, 97.5))]


def spearman(a, b):
    a = pd.Series(a).rank(); b = pd.Series(b).rank()
    return float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 and a.nunique() > 1 and b.nunique() > 1 else float("nan")


def main():
    close, mktmap = lb.load_ohlcv(); dates = list(close.index); N = len(dates)
    mk = pd.Series(mktmap).str.lower()
    mk_tickers = {m: close.columns.intersection(mk.index[mk == m]) for m in ("kospi", "kosdaq")}
    con = sqlite3.connect(f"file:{REPO/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    lbj = json.loads((REPO / "docs/leaderboard.json").read_text(encoding="utf-8"))
    ms = {m["model"]: m for m in lbj["models"] if m["model"] in MODELS}

    # 국면: KOSDAQ > 20일선
    oc = sqlite3.connect(f"file:{REPO.parent/'dh-q7m3k-data'/'ohlcv.db'}?mode=ro", uri=True)
    kq = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSDAQ' ORDER BY date", oc); oc.close()
    kq["date"] = kq.date.astype(str).str.replace("-", ""); kq = kq.set_index("date")["close"].astype(float)
    regime = (kq > kq.rolling(20).mean()).reindex(dates)

    # 모델별: 앵커 t → {market: 상위10 티커}, 앵커별 점수(IC 용)
    basket, scores = {}, {}
    for name, m in ms.items():
        S = bs.load_scores(con, m); S["ticker"] = S.ticker.astype(str); S["run_id"] = S.run_id.astype(str)
        keep = lb.dedupe_by_anchor(S, didx, excl, reg=None)
        b, sc = {}, {}
        for rid in keep:
            t = lb.anchor(rid, didx)
            if t is None or t + 1 >= N: continue
            g = S[S.run_id == rid].dropna(subset=["score"])
            b[t] = {mkt: list(gm.nlargest(TOP, "score").ticker) for mkt, gm in g.groupby("market")}
            sc[t] = g
        basket[name], scores[name] = b, sc
    con.close()

    def ret(t_from, t_to):
        return close.iloc[t_to] / close.iloc[t_from] - 1

    def excess(name, t, t_to):
        """앵커 t 바스켓(진입 t+1)의 t_to 까지 초과(%p), 시장별 평균."""
        r = ret(t + 1, t_to); ex = []
        for mkt, tk in basket[name][t].items():
            a = r.reindex(tk).dropna(); bm = r.reindex(mk_tickers[mkt]).dropna()
            if len(a) >= MIN_BASKET and len(bm): ex.append((a.mean() - bm.mean()) * 100)
        return float(np.mean(ex)) if ex else np.nan

    def ic(name, t, h=H):
        if t + 1 + h >= N: return np.nan
        r = ret(t + 1, t + 1 + h); out = []
        for mkt, gm in scores[name][t].groupby("market"):
            s = gm.set_index("ticker")["score"].astype(float); b = r.reindex(s.index); mm = s.notna() & b.notna()
            if mm.sum() >= lb.MIN_GROUP: out.append(spearman(s[mm], b[mm]))
        return float(np.nanmean(out)) if out else np.nan

    # 끝난 값 캐시
    EX20 = {n: {t: excess(n, t, t + 1 + H) for t in b if t + 1 + H < N} for n, b in basket.items()}
    EX5 = {n: {t: excess(n, t, t + 1 + 5) for t in b if t + 1 + 5 < N} for n, b in basket.items()}
    IC20 = {n: {t: ic(n, t) for t in b if t + 1 + H < N} for n, b in basket.items()}

    def last_k(d, table, k, h):
        """결정일 d 에 '끝난' 값(앵커 t 는 t+1+h <= d)만, 최근 k 개."""
        xs = [(t, v) for t, v in table.items() if t + 1 + h <= d and not np.isnan(v)]
        xs.sort(); return [v for _, v in xs[-k:]]

    # 신호 계산
    rows = []
    decision_days = sorted({t for n in basket for t in basket[n] if t + 1 + H < N})
    for d in decision_days:
        reg_now = regime.iloc[d]
        todays = {n: basket[n][d] for n in basket if d in basket[n]}
        for n in todays:
            Y = EX20[n].get(d, np.nan)
            if np.isnan(Y): continue
            f = {}
            x = last_k(d, EX20[n], 20, H); f["F1"] = np.mean(x) if len(x) >= 10 else np.nan
            x = last_k(d, EX5[n], 10, 5); f["F2"] = np.mean(x) if len(x) >= 5 else np.nan
            op = [excess(n, t, d) for t in basket[n] if d - H <= t <= d - 1]
            op = [v for v in op if not np.isnan(v)]; f["F3"] = np.mean(op) if len(op) >= 5 else np.nan
            x = last_k(d, EX20[n], 20, H); f["F4"] = np.mean(np.array(x) > 0) if len(x) >= 10 else np.nan
            x = last_k(d, IC20[n], 20, H); f["F5"] = np.mean(x) if len(x) >= 10 else np.nan
            f["F6"] = np.mean(np.array(x) > 0) if len(x) >= 10 else np.nan
            same = [v for t, v in IC20[n].items() if t + 1 + H <= d and not np.isnan(v) and regime.iloc[t] == reg_now]
            f["F7"] = np.mean(same) if len(same) >= 5 and reg_now == reg_now else np.nan
            ov = []
            for o in todays:
                if o == n: continue
                for mkt in todays[n]:
                    if mkt in todays[o]:
                        ov.append(len(set(todays[n][mkt]) & set(todays[o][mkt])) / TOP)
            f["F8"] = np.mean(ov) if ov else np.nan
            x = last_k(d, EX20[n], 40, H)
            if len(x) >= 10:
                c = np.cumsum(x); f["F9"] = float(c[-1] - np.max(c))
            else: f["F9"] = np.nan
            f["F10"] = f["F3"] - f["F1"] if not (np.isnan(f["F3"]) or np.isnan(f["F1"])) else np.nan
            rows.append(dict(d=d, date=dates[d], model=n, Y=Y, **f))
    df = pd.DataFrame(rows)
    df["Yrel"] = df["Y"] - df.groupby("d")["Y"].transform("mean")
    print(f"결정일 {df.d.nunique()}일({df.date.min()}~{df.date.max()}) · (일,모델) 쌍 {len(df)} · 독립 20일 구간 약 {df.d.nunique()//20}개")

    names = {"F1": "끝난20일초과 최근20", "F2": "끝난5일초과 최근10", "F3": "열린포지션 시가평가", "F4": "20일초과 양수비율",
             "F5": "IC20 최근20", "F6": "IC20 양수비율", "F7": "같은국면 IC", "F8": "모델간 합의(겹침)", "F9": "누적초과 낙폭", "F10": "개선(F3−F1)"}
    out = []
    for F, nm in names.items():
        sub = df.dropna(subset=[F])
        days = sub.groupby("d").filter(lambda g: len(g) >= MIN_MODELS)
        if days.d.nunique() < 10:
            out.append(dict(F=F, name=nm, n_days=int(days.d.nunique()), note="결정일 부족")); continue
        # (a) 합친 순위상관 — 블록 부트스트랩: 날짜 블록 단위로 재표집
        dd = sorted(days.d.unique()); byd = {d: g for d, g in days.groupby("d")}
        rng = np.random.default_rng(7); nb = int(np.ceil(len(dd) / 20)); rc = []
        for _ in range(1000):
            st = rng.integers(0, max(len(dd) - 20 + 1, 1), nb)
            pick = [byd[x] for s in st for x in dd[s:s + 20]][:len(dd)]
            g = pd.concat(pick); rc.append(spearman(g[F], g["Yrel"]))
        rho = spearman(days[F], days["Yrel"])
        # (b) 1등 따라가기
        lead = days.loc[days.groupby("d")[F].idxmax()].set_index("d")
        mixY = days.groupby("d")["Y"].mean()
        diff = (lead["Y"] - mixY.reindex(lead.index)).values
        # (c) 날마다 순위 상관
        rk = [spearman(g[F], g["Y"]) for _, g in days.groupby("d") if len(g) >= MIN_MODELS]
        rk = [v for v in rk if not np.isnan(v)]
        out.append(dict(F=F, name=nm, n_days=int(days.d.nunique()), n_pairs=int(len(days)),
                        rho=round(rho, 3), rho_ci=[round(v, 3) for v in np.percentile(rc, [2.5, 97.5])],
                        leader_minus_mix=round(float(diff.mean()), 2), leader_ci=[round(v, 2) for v in block_ci(diff)],
                        leader_pos=round(float((diff > 0).mean()), 2),
                        daily_rank_corr=round(float(np.mean(rk)), 3), daily_rank_n=len(rk)))
    (HERE / "result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    df.to_csv(HERE / "signals.csv", index=False, encoding="utf-8-sig")
    print(f"{'신호':<4} {'이름':<16} {'결정일':>5} {'쌍':>5} {'순위상관':>8} {'CI':>18} {'1등−섞기':>9} {'CI':>16} {'양수':>5} {'일별순위상관':>8}")
    for r in out:
        if "note" in r: print(f"{r['F']:<4} {r['name']:<16} {r['n_days']:>5} {r['note']}"); continue
        print(f"{r['F']:<4} {r['name']:<16} {r['n_days']:>5} {r['n_pairs']:>5} {r['rho']:>+8.3f} [{r['rho_ci'][0]:+.3f},{r['rho_ci'][1]:+.3f}] "
              f"{r['leader_minus_mix']:>+8.2f}%p [{r['leader_ci'][0]:+.2f},{r['leader_ci'][1]:+.2f}] {r['leader_pos']:>5.0%} {r['daily_rank_corr']:>+8.3f}({r['daily_rank_n']})")


if __name__ == "__main__":
    main()
