# -*- coding: utf-8 -*-
"""short_horizon_20261018.py — "배치 다음날 샀을 때 그 당일·다음날 상승률" 탐색 (2026-10-18, 읽기 전용·판정 아님)

질문(사용자): 각 모델 목록을 다음 거래일에 샀을 때, 그 당일과 다음날 수익이 높은 종목을 뽑을 수 있나?
정의(Codex 요청문 REQUEST_20261018_short_horizon.md 와 글자 그대로 같음):
  앵커 run t(저녁 발표) → 다음 거래일 t+1 매수.
  A 당일   = t+1 시가 → t+1 종가          (시가에 사서 그날 종가까지)
  B 다음날 = t+1 종가 → t+2 종가          (t+1 종가에 사서 다음날 종가까지)
  C 이틀   = t+1 시가 → t+2 종가          (시가에 사서 이틀 보유)
  G 갭     = t 종가 → t+1 시가            (참고: 목록 발표 뒤 시가가 얼마나 뛰나 — 시가 매수가 잃는 몫)
  모델·창: v30(v3_scores, 등록 20260606) · le_a(wu_scores, 20260715) · lv_b(lowvol_scores, 20260625) · lv_e(lowvol_scores, 20260901). 등록일 이후 run 만.
  게이트: §11 과 동일(부분실행 20260608·이중실행 20260703 제외, 앵커 중복 제거). 점프컷: t+1~t+2 일간 등락 절댓값 > 32% 제외. 점수 -999(결측 표시)는 결측으로.
  측정(앵커마다 시장별 → 시장 평균 → 앵커 동일가중):
    ① 순위 상관(Spearman) 점수 vs 수익(A·B·C)  ② 상위 10(시장별) 평균 수익 − 같은 시장 전 종목 동일가중 평균(같은 날) = 초과
    ③ 상위 10 양(+) 비율  ④ 점수 10분위(상위 10% − 하위 10%)
  구간: 날짜 iid 부트스트랩 4,000회 seed 7 · 주 블록(월~일) 병기 · 탐색이라 Bonferroni 는 (모델 4 × 지평 3 = 12) 감도 표기만.
  주의: 사후 탐색(사전등록 없음). 여기서 나온 규칙은 '가설'이며 쓰려면 새 사전등록(PREREGISTER)이 필요하다. 점수식 변경 없음.
실행: python research/short_horizon_20261018.py  → research/out_short_horizon/summary.md · anchors_{model}.csv
"""
import sys, sqlite3
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import leaderboard as lb  # noqa: E402

OUT = HERE / "out_short_horizon"; OUT.mkdir(exist_ok=True)
BOOT, SEED, TOP_N, JUMP = 4000, 7, 10, lb.JUMP_CAP
MODELS = {  # model_id: (table, score col, reg)
    "v30": ("v3_scores", "final_score_v3", lb.REG_DATE["v30"]),
    "le_a": ("wu_scores", "wu_score", lb.REG_DATE["le_a"]),
    "lv_b": ("lowvol_scores", "lowvol_score", lb.REG_DATE["lv_b"]),
    "lv_e": ("lowvol_scores", "lowvol_score", lb.REG_DATE["lv_e"]),
}
HORIZONS = ("A", "B", "C")

con_o = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
px = pd.read_sql("SELECT ticker, date, open, close, market FROM daily_ohlcv", con_o); con_o.close()
px["ticker"] = px.ticker.astype(str).str.zfill(6)
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
opn = px.pivot_table(index="date", columns="ticker", values="open", aggfunc="last").sort_index()
mkt = px.groupby("ticker")["market"].last().str.lower()
dates = list(close.index); N = len(dates)
con = sqlite3.connect(f"file:{REPO / 'history.db'}?mode=ro", uri=True)
partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
print(f"가격 마지막 {dates[-1]} · 게이트 제외 run: 부분 {sorted(partial)} 이중 {sorted(dbl)}")


def rets_for(t):
    """앵커 인덱스 t → (A, B, C, G) 종목별 수익(%) Series. 점프컷은 t+1~t+2 일간 등락으로."""
    if t + 2 >= N:
        return None
    c0, o1, c1, c2 = close.iloc[t], opn.iloc[t + 1], close.iloc[t + 1], close.iloc[t + 2]
    jump = pd.concat([(c1 / c0 - 1).abs(), (c2 / c1 - 1).abs()], axis=1).max(axis=1)
    ok = (jump <= JUMP) & o1.gt(0) & c1.gt(0) & c2.gt(0)
    A = (c1 / o1 - 1) * 100; B = (c2 / c1 - 1) * 100; C = (c2 / o1 - 1) * 100; G = (o1 / c0 - 1) * 100
    return {"A": A.where(ok), "B": B.where(ok), "C": C.where(ok), "G": G.where(ok)}


def boot(a, lo=2.5, hi=97.5):
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    if len(a) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(SEED)
    b = [rng.choice(a, len(a)).mean() for _ in range(BOOT)]
    return float(np.percentile(b, lo)), float(np.percentile(b, hi))


def week_boot(vals, days):
    """주 블록(월~일) 부트스트랩 — 주 단위 복원추출 후 그 주의 앵커 전부 연결."""
    df = pd.DataFrame({"v": vals, "d": pd.to_datetime(days, format="%Y%m%d")}).dropna()
    if df.empty:
        return (np.nan, np.nan, 0)
    df["wk"] = df.d.dt.to_period("W-SUN").astype(str)
    groups = [g.v.values for _, g in df.groupby("wk")]
    if len(groups) < 2:
        return (np.nan, np.nan, len(groups))
    rng = np.random.default_rng(SEED); b = []
    for _ in range(BOOT):
        pick = rng.integers(0, len(groups), len(groups))
        b.append(np.concatenate([groups[i] for i in pick]).mean())
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5)), len(groups)


lines = ["# 단기(당일·다음날) 수익 탐색 — 2026-10-18 (판정 아님 · 사후 탐색)", "",
         f"가격 마지막 {dates[-1]} · 정의는 스크립트 머리말 · 구간 = 날짜 iid 95% [주 블록 95%] · n = 앵커 수", ""]
rows_all = []
for mid, (tb, sc, reg) in MODELS.items():
    S = pd.read_sql(f"SELECT run_id, market, ticker, {sc} AS score FROM {tb} WHERE model_id=?", con, params=(mid,))
    S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str); S["market"] = S.market.str.lower()
    keep = lb.dedupe_by_anchor(S, didx, excl, reg=reg)
    recs = []
    for rid, g in S.groupby("run_id"):
        if rid not in keep:
            continue
        t = lb.anchor(rid, didx)
        if t is None:
            continue
        R = rets_for(t)
        if R is None:
            continue
        rec = {"run_id": rid, "anchor": dates[t], "n_rows": len(g)}
        for h in HORIZONS + ("G",):
            ics, exc, hit, dec = [], [], [], []
            for m, gm in g.groupby("market"):
                s = gm.set_index("ticker")["score"].astype(float)
                s = s.where(s > -999)   # v3 의 -999 = 결측 표시(실측: v30 kosdaq 한 run 에 수십 개 동점) → 결측으로
                r = R[h].reindex(s.index)
                ok = s.notna() & r.notna()
                if ok.sum() < 8 or s[ok].nunique() < 3 or r[ok].nunique() < 3:
                    continue
                ics.append(s[ok].rank().corr(r[ok].rank()))
                top = s[ok].sort_values(ascending=False).index[:TOP_N]
                # 시장 전 종목 동일가중(그날 시세 있는 종목 전체) — 같은 시장
                uni = R[h][mkt.reindex(R[h].index) == m].dropna()
                exc.append(r[top].mean() - uni.mean())
                hit.append((r[top] > 0).mean())
                q = s[ok].rank(pct=True)
                dec.append(r[ok][q > 0.9].mean() - r[ok][q <= 0.1].mean())
            if ics:
                rec[f"ic_{h}"] = float(np.mean(ics)); rec[f"exc_{h}"] = float(np.mean(exc))
                rec[f"hit_{h}"] = float(np.mean(hit)); rec[f"dec_{h}"] = float(np.mean(dec))
        recs.append(rec)
    df = pd.DataFrame(recs).sort_values("anchor")
    df.to_csv(OUT / f"anchors_{mid}.csv", index=False, encoding="utf-8-sig")
    lines += [f"## {mid} (등록 {reg}~ · 앵커 n={len(df)} · {df.anchor.min() if len(df) else '-'}~{df.anchor.max() if len(df) else '-'})", "",
              "| 지평 | 순위상관 IC | 95% [주블록] | 상위10 초과(%p) | 95% [주블록] | 상위10 양(+) | 10분위 차(%p) | 95% | 갭 G 평균 |",
              "|---|---|---|---|---|---|---|---|---|"]
    for h in HORIZONS:
        ic = df[f"ic_{h}"]; ex = df[f"exc_{h}"]; hi = df[f"hit_{h}"]; de = df[f"dec_{h}"]
        ci = boot(ic); cw = week_boot(ic.values, df.anchor.values); ce = boot(ex); cew = week_boot(ex.values, df.anchor.values); cd = boot(de)
        g = df["exc_G"].mean() if "exc_G" in df else np.nan
        lines.append(f"| {h} | {ic.mean():+.4f} | [{ci[0]:+.4f},{ci[1]:+.4f}] [{cw[0]:+.4f},{cw[1]:+.4f}] | {ex.mean():+.3f} | [{ce[0]:+.3f},{ce[1]:+.3f}] [{cew[0]:+.3f},{cew[1]:+.3f}] | {hi.mean():.0%} | {de.mean():+.3f} | [{cd[0]:+.3f},{cd[1]:+.3f}] | {g:+.3f} |")
        rows_all.append({"model": mid, "h": h, "n": len(df), "ic": ic.mean(), "ic_lo": ci[0], "ic_hi": ci[1], "ic_wlo": cw[0], "ic_whi": cw[1], "weeks": cw[2],
                         "exc": ex.mean(), "exc_lo": ce[0], "exc_hi": ce[1], "exc_wlo": cew[0], "exc_whi": cew[1], "hit": hi.mean(), "dec": de.mean(), "dec_lo": cd[0], "dec_hi": cd[1]})
    # 상위10 갭(G)의 평균 — '시가 매수가 잃는 몫'
    lines.append(f"| G(갭) | — | — | 상위10 갭 {df['exc_G'].mean():+.3f}%p(시장 대비) | | 상위10 갭>0 {df['hit_G'].mean():.0%} | | | |")
    lines.append("")
pd.DataFrame(rows_all).to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
lines += ["주의: 사후 탐색(사전등록 없음) · 모델 4 × 지평 3 = 12검정(Bonferroni /12 면 날짜 구간 폭 ×1.6 추정) · 비용 왕복 0.35~0.5% 를 빼지 않은 값 — "
          "A·B 는 하루 보유라 비용이 수익과 같은 자릿수다. 여기서 규칙을 만들려면 새 사전등록이 필요하다.", ""]
(OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
