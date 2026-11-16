# -*- coding: utf-8 -*-
"""바깥 축(환율·미국 지수·금리) × 코스피 급락 칸(A) — Claude 독립 재현 (2026-11-16, 약속 P01 · K11 재검 조건).

설계·기대·일치 기준은 `research/RESEARCH_macro_regime_repro_20261116.md` §0 (결과 전에 적음).
규칙 출처: `handoff/REQUEST_20261102_macro_regime_blind.md` + Codex 가 계산 전에 고정한 `handoff/out_20261102_macro_regime/protocol.json`.
Codex 코드(`code_20261102_macro_regime_blind.py`)는 열지 않았다. 대조는 Codex 산출물(days.csv·events.csv·results.json)과만.

실행: PYTHONIOENCODING=utf-8 python -X utf8 -B research/macro_regime_repro_20261116.py
읽기 전용: ../dh-q7m3k-data/ohlcv_10y.db · macro_10y.db. 산출물: research/out_macro_regime_repro/.
"""
import bisect, json, sqlite3, sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lib import tenyr  # noqa: E402  (공통 틀 — 가격판·집 틀 격자)

OUT = HERE / "out_macro_regime_repro"
OUT.mkdir(exist_ok=True)
MACRO_DB = str(tenyr.REPO / ".." / "dh-q7m3k-data" / "macro_10y.db")
CODEX = HERE / "handoff" / "out_20261102_macro_regime"

# ── 요청서·protocol.json 에서 온 값(새로 정한 것 없음) ──
GRID_FROM, GRID_TO = "20150201", "20260831"      # protocol signal_window
STEP, HOLD = 5, 40                               # 5거래일 격자 · t+1 → t+41
Q_OS = 0.20                                      # 과매도 = R20 하위 20%
A_CUT, D_CUT = -5.0, 5.0                         # 칸 A ≤ −5 · D > +5
EVENT_GAP = 40                                   # A 사건 간격(거래일)
TAIL = -0.20                                     # os_tail20
SPLIT = tenyr.SPLIT                              # 앞/뒤반 20210101
EV_SEED, EV_K = 20261030, 4000                   # 사건 부트스트랩
MB_SEED, MB_K = 7, 2000                          # 월 블록
MIN_GROUP = 5                                    # 사건 그룹 최소 n
OPEN_ABS = 3.0                                   # |차| ≥ 3%p
RHO_DEPTH = 0.5                                  # 축↔R20 |ρ| ≥ 0.5
# 축: (시리즈, 달력일 지연, 변화 정의, 나쁜 쪽)
AXES = {"FX20": ("USDKRW", 1, "pct", "hi"), "US20": ("SPX", 0, "pct", "lo"), "RATE20": ("US10Y", 2, "diff", "hi"),
        "IXIC20": ("IXIC", 0, "pct", "lo"), "OIL20": ("WTI", 2, "pct", "hi")}
MAIN = ("FX20", "US20", "RATE20")
REF_LAG_DAYS = 28
METRICS = ("os_mean", "all_mean", "ks_f40", "os_tail20", "os_minus_all")


def ymd_minus(s, days):
    return (datetime.strptime(s, "%Y%m%d") - timedelta(days=days)).strftime("%Y%m%d")


def load_macro():
    con = sqlite3.connect(f"file:{MACRO_DB}?mode=ro", uri=True)
    m = pd.read_sql("SELECT series, date, close FROM series_daily ORDER BY series, date", con)
    con.close()
    return {s: (list(g.date), g.close.values.astype(float)) for s, g in m.groupby("series")}


def axis_value(M, name, t):
    series, lag, kind, _ = AXES[name]
    dates, vals = M[series]
    j = bisect.bisect_right(dates, ymd_minus(t, lag)) - 1
    if j < 0:
        return np.nan
    k = bisect.bisect_right(dates, ymd_minus(dates[j], REF_LAG_DAYS)) - 1
    if k < 0:
        return np.nan
    if series == "WTI" and (vals[k:j + 1] <= 0).any():
        return np.nan
    return (vals[j] / vals[k] - 1) * 100 if kind == "pct" else vals[j] - vals[k]


def add_axes(D, M):
    for name in AXES:
        D[name] = [axis_value(M, name, t) for t in D.date]
    return D


def regime_of(x):
    return "A" if x <= A_CUT else ("D" if x > D_CUT else "BC")


def mark_events(D):
    ev, last = [], -10 ** 9
    for i, rg in zip(D.i, D.regime):
        hit = (rg == "A") and (i - last >= EVENT_GAP)
        ev.append(hit)
        if hit:
            last = i
    D["event"] = ev
    return D


def spec_days(P):
    """본 재현 — 요청서 규칙 그대로의 격자(집 틀과 다른 네 군데는 메모 §0)."""
    ks = P.ks.reindex(P.dates).values
    i0 = next(i for i, d in enumerate(P.dates) if d >= GRID_FROM)
    delisted = P.meta.note.reindex(P.tick).fillna("").str.contains("delisted").values
    rows = []
    for i in range(i0, P.N, STEP):
        if i + 1 + HOLD >= P.N or P.dates[i] > GRID_TO:
            break
        c0, c1, cm = P.CU[i], P.CU[i + 1], P.CU[i - 20]
        with np.errstate(invalid="ignore"):
            elig = (c0 > 0) & (c1 > 0) & (P.VU[i] > 0) & (P.VU[i + 1] > 0) & (c0 >= 1000) & (c1 >= 1000) & (cm > 0)
            r = c0 / cm - 1
        thr = np.quantile(r[elig], Q_OS)
        os_ = elig & (r <= thr)
        pH = P.CF[i + 1 + HOLD]
        have = ~np.isnan(pH)
        g = pH / c1 - 1
        d = P.dates[i]
        r20 = (ks[i] / ks[i - 20] - 1) * 100
        rows.append(dict(date=d, month=d[:6], i=i, ks_r20=r20, regime=regime_of(r20),
                         ks_f40=(ks[i + 1 + HOLD] / ks[i + 1] - 1) * 100,
                         os_mean=g[os_ & have].mean() * 100, all_mean=g[elig & have].mean() * 100,
                         os_tail20=(g[os_ & have] <= TAIL).mean() * 100,
                         n_eligible=int(elig.sum()), n_os=int(os_.sum()),
                         n_all_missing=int((elig & ~have).sum()), n_os_missing=int((os_ & ~have).sum()),
                         n_delist_fallback=int((elig & delisted & np.isnan(P.CU[i + 1 + HOLD]) & have).sum())))
    return pd.DataFrame(rows)


def house_days(P):
    """집 틀 감도 — tenyr.signal_days 기본값 그대로(시작 130번째 날 · 비용 0.35% · 유효 ≥300)."""
    ks = P.ks.reindex(P.dates).values

    def extra(P_, i, ok):
        r = P_.R20[i]
        os_ = ok & (r <= np.quantile(r[ok], Q_OS))
        g = P_.CF[i + 1 + tenyr.H] / P_.CU[i + 1] - 1 - tenyr.COST
        return dict(os_tail20=(g[os_] <= TAIL).mean() * 100, ks_f40=(ks[i + 1 + tenyr.H] / ks[i + 1] - 1) * 100)

    R = tenyr.signal_days(P, extra=extra)
    D = R.rename(columns={"os40": "os_mean", "all40": "all_mean", "r20": "ks_r20"})[
        ["date", "month", "i", "ks_r20", "ks_f40", "os_mean", "all_mean", "os_tail20", "n_os"]].copy()
    D["regime"] = D.ks_r20.map(regime_of)
    return D


# ── 통계 ──
def bad_of(x, thr, side):
    return (x > thr) if side == "hi" else (x <= thr)      # 동률은 아래(≤)


def diffs(S, bad):
    b = bad.values
    return {m: float(S[m].values[b].mean() - S[m].values[~b].mean()) for m in METRICS}


def event_ci(S, bad):
    x = {m: S[m].values for m in METRICS}
    b = bad.values
    rng = np.random.default_rng(EV_SEED)
    acc = {m: [] for m in METRICS}
    for _ in range(EV_K):
        idx = rng.integers(0, len(b), len(b))
        bb = b[idx]
        if bb.all() or not bb.any():
            continue
        for m in METRICS:
            v = x[m][idx]
            acc[m].append(v[bb].mean() - v[~bb].mean())
    return {m: (float(np.percentile(acc[m], 2.5)), float(np.percentile(acc[m], 97.5))) for m in METRICS}, len(acc["os_mean"])


def month_ci(S, bad, stat, cols=("os_mean",)):
    """달 묶음을 통째로 뽑는다(두 집단 함께). stat(S_sub, bad_sub, col) → 값."""
    months = S.month.values
    um = np.unique(months)
    pos = {u: np.where(months == u)[0] for u in um}
    rng = np.random.default_rng(MB_SEED)
    acc = {c: [] for c in cols}
    for _ in range(MB_K):
        idx = np.concatenate([pos[u] for u in rng.choice(um, len(um))])
        for c in cols:
            v = stat(idx, c)
            if v == v:
                acc[c].append(v)
    return {c: (float(np.percentile(acc[c], 2.5)), float(np.percentile(acc[c], 97.5))) for c in cols}


def split_stat(S, bad):
    b = bad.values
    X = {m: S[m].values for m in METRICS}

    def stat(idx, c):
        bb = b[idx]
        if bb.all() or not bb.any():
            return np.nan
        v = X[c][idx]
        return v[bb].mean() - v[~bb].mean()
    return stat


def matched(S, bad, bins):
    """깊이 5분위 안 비교: 칸별 (나쁨−좋음) 을 min(n) 으로 가중."""
    b = bad.values
    X = {m: S[m].values for m in METRICS}

    def stat(idx, c):
        bb, bn, v = b[idx], bins[idx], X[c][idx]
        num = den = 0.0
        for q in range(5):
            mb, mg = (bn == q) & bb, (bn == q) & ~bb
            w = min(mb.sum(), mg.sum())
            if w > 0:
                num += w * (v[mb].mean() - v[mg].mean())
                den += w
        return num / den if den else np.nan
    full = np.arange(len(b))
    return {m: stat(full, m) for m in METRICS}, stat


def sgn(x):
    return 0 if x == 0 else (1 if x > 0 else -1)


def analyse(D, tag):
    D = D.copy()
    D["os_minus_all"] = D.os_mean - D.all_mean
    D["half"] = np.where(D.date < SPLIT, "early", "late")
    res = {"n_days": len(D), "regimes": D.regime.value_counts().to_dict(), "events": list(D.date[D.event]), "axes": {}}
    A = D[D.regime == "A"]
    for name, (_, _, _, side) in AXES.items():
        Dn = D[D[name].notna()]
        An = Dn[Dn.regime == "A"]
        En = An[An.event]
        thrA = float(np.median(An[name]))
        thrALL = float(np.median(Dn[name]))
        out = {"thr_A": thrA, "thr_ALL": thrALL, "missing": int(D[name].isna().sum()), "refs": {}}
        # 본문 — A 사건
        badE = bad_of(En[name], thrA, side)
        nb, ng = int(badE.sum()), int((~badE).sum())
        out["event"] = {"n_bad": nb, "n_good": ng}
        if min(nb, ng) >= MIN_GROUP:
            ci, valid = event_ci(En, badE)
            out["event"].update(diff=diffs(En, badE), ci=ci, valid=valid)
        # 참고 — 겹치는 날
        samples = {"A_days": (An, thrA), "ALL_pooled": (Dn, thrALL)}
        for rg in ("BC", "D"):
            Sg = Dn[Dn.regime == rg]
            samples[f"{rg}_pooled"] = (Sg, float(np.median(Sg[name])))
        for h in ("early", "late"):
            samples[f"A_{h}"] = (An[An.half == h], thrA)
            samples[f"ALL_{h}"] = (Dn[Dn.half == h], thrALL)
        for k, (S, thr) in samples.items():
            bad = bad_of(S[name], thr, side)
            nb_, ng_ = int(bad.sum()), int((~bad).sum())
            if min(nb_, ng_) == 0:
                out["refs"][k] = {"n_bad": nb_, "n_good": ng_}
                continue
            d = diffs(S, bad)["os_mean"]
            lo, hi = month_ci(S, bad, split_stat(S, bad))["os_mean"]
            out["refs"][k] = {"n_bad": nb_, "n_good": ng_, "diff": d, "lo": lo, "hi": hi}
        # 깊이 짝
        bins = pd.qcut(An.ks_r20, 5, labels=False).values
        badA = bad_of(An[name], thrA, side)
        md, st = matched(An, badA, bins)
        out["matched"] = {"diff": md, "ci": month_ci(An, badA, st, cols=METRICS)}
        # 순위상관
        out["rho"] = {f"{sn}:{c}": float(S[name].corr(S[c], method="spearman"))
                      for sn, S in (("ALL", Dn), ("A_days", An), ("A_events", En)) for c in ("os_mean", "ks_f40", "ks_r20")}
        # 판정(요청서 §4 + protocol verdict 줄)
        if name in MAIN:
            ev = out["event"]
            if "diff" not in ev:
                out["verdict"] = {"label": "보류", "reasons": ["사건 그룹 n 부족 — 판정 불가"]}
            else:
                d0 = ev["diff"]["os_mean"]
                lo, hi = ev["ci"]["os_mean"]
                s = sgn(d0)
                flips = [k for k in ("A_days", "ALL_pooled", "BC_pooled", "D_pooled", "A_early", "A_late", "ALL_early", "ALL_late")
                         if "diff" in out["refs"][k] and sgn(out["refs"][k]["diff"]) != s]
                m_os = out["matched"]["diff"]["os_mean"]
                rho = out["rho"]["A_days:ks_r20"]
                reasons = []
                if abs(d0) < OPEN_ABS:
                    reasons.append("|A 사건 차이|<3%p")
                if flips:
                    reasons.append("부호 반전: " + ",".join(flips))
                if abs(rho) >= RHO_DEPTH and abs(m_os) < OPEN_ABS:
                    reasons.append("깊이의 반복 표현")
                if reasons:
                    label = "닫음"
                elif (lo > 0 or hi < 0) and abs(d0) >= OPEN_ABS and sgn(m_os) == s:
                    label = "열림"
                else:
                    label = "보류"
                    reasons = ["부호 일관 · 구간이 0 을 품음" if not (lo > 0 or hi < 0) else "깊이 짝 부호 다름"]
                out["verdict"] = {"label": label, "reasons": reasons}
        res["axes"][name] = out
    res["axis_rho"] = {f"{sn}:{a}:{b}": float(S[a].corr(S[b], method="spearman"))
                       for sn, S in (("ALL", D), ("A_days", A), ("A_events", A[A.event]))
                       for a, b in (("FX20", "US20"), ("FX20", "RATE20"), ("US20", "RATE20"))}
    D.to_csv(OUT / f"days_{tag}.csv", index=False, encoding="utf-8-sig")
    return res


def show(res, title):
    print(f"\n{'=' * 8} {title} — 격자 {res['n_days']}일 · 칸 {res['regimes']} · A 사건 {len(res['events'])}개")
    print("사건:", ", ".join(res["events"]))
    for name, o in res["axes"].items():
        ev = o["event"]
        if "diff" in ev:
            line = " · ".join(f"{m} {ev['diff'][m]:+.3f} [{ev['ci'][m][0]:+.3f}, {ev['ci'][m][1]:+.3f}]" for m in METRICS)
        else:
            line = "n 부족"
        print(f"\n[{name}] A 날 중앙값 {o['thr_A']:.3f} · 사건 나쁨 {ev['n_bad']} / 좋음 {ev['n_good']} · {line}")
        for k, r in o["refs"].items():
            print(f"   {k:11s} {r['n_bad']:>3}/{r['n_good']:<3} " + (f"{r['diff']:+.3f} [{r['lo']:+.3f}, {r['hi']:+.3f}]" if "diff" in r else "한쪽 0"))
        m = o["matched"]
        print(f"   깊이 짝 os_mean {m['diff']['os_mean']:+.3f} [{m['ci']['os_mean'][0]:+.3f}, {m['ci']['os_mean'][1]:+.3f}] · ρ(축,R20) A 날 {o['rho']['A_days:ks_r20']:+.3f} · 전체 {o['rho']['ALL:ks_r20']:+.3f}")
        if "verdict" in o:
            print(f"   → 판정 {o['verdict']['label']} — {'; '.join(o['verdict']['reasons'])}")


def compare_codex(D, res):
    """Codex 산출물과 대조(본 재현만)."""
    cd = pd.read_csv(CODEX / "days.csv", dtype={"date": str}, encoding="utf-8-sig")
    cr = json.loads((CODEX / "results.json").read_text(encoding="utf-8"))
    out = {"n_mine": len(D), "n_codex": len(cd), "dates_equal": list(D.date) == list(cd.date)}
    J = D.merge(cd, on="date", suffixes=("", "_c"))
    cols = ["ks_r20", "ks_f40", "os_mean", "all_mean", "os_tail20"] + list(AXES)
    out["max_abs_diff"] = {}
    for c in cols:
        d = (J[c] - J[c + "_c"]).abs()
        k = d.idxmax()
        out["max_abs_diff"][c] = {"max": float(d.max()), "date": J.date[k], "n_over_0.01": int((d >= 0.01).sum()),
                                  "nan_mismatch": int((J[c].isna() != J[c + "_c"].isna()).sum())}
    out["n_eligible_diff_days"] = int((J.n_eligible != J.n_eligible_c).sum())
    out["n_os_diff_days"] = int((J.n_os != J.n_os_selected).sum())
    out["regime_diff_days"] = int((J.regime != J.regime_c).sum())
    out["missing_mine"] = [int(D.n_all_missing.sum()), int(D.n_os_missing.sum())]
    out["missing_codex"] = [int(cd.n_all_missing_outcome.sum()), int(cd.n_os_missing_outcome.sum())]
    out["delist_mine"], out["delist_codex"] = int(D.n_delist_fallback.sum()), int(cd.n_delist_fallback.sum())
    out["events_equal"] = res["events"] == [str(x) for x in cr["data"]["event_dates"]]
    out["events_only_mine"] = sorted(set(res["events"]) - {str(x) for x in cr["data"]["event_dates"]})
    out["events_only_codex"] = sorted({str(x) for x in cr["data"]["event_dates"]} - set(res["events"]))
    out["axes"] = {}
    for name in AXES:
        o = res["axes"][name]
        ce = cr["splits"][f"{name}:median"]["A_events"]
        row = {"thr_mine": o["thr_A"], "thr_codex": cr["thresholds"][name], "n_mine": [o["event"]["n_bad"], o["event"]["n_good"]], "n_codex": [ce["n_bad"], ce["n_good"]]}
        if "diff" in o["event"] and "metrics" in ce:
            row["event"] = {m: {"mine": o["event"]["diff"][m], "codex": ce["metrics"][m]["diff"],
                                "ci_mine": o["event"]["ci"][m], "ci_codex": [ce["metrics"][m]["lo"], ce["metrics"][m]["hi"]]} for m in METRICS}
        row["refs"] = {}
        for k, r in o["refs"].items():
            c = cr["splits"][f"{name}:median"].get(k, {})
            cm = c.get("metrics", {}).get("os_mean", {})
            row["refs"][k] = {"mine": r.get("diff"), "codex": cm.get("diff"), "ci_mine": [r.get("lo"), r.get("hi")], "ci_codex": [cm.get("lo"), cm.get("hi")],
                              "n_mine": [r["n_bad"], r["n_good"]], "n_codex": [c.get("n_bad"), c.get("n_good")]}
        row["rho_Adays_r20"] = {"mine": o["rho"]["A_days:ks_r20"], "codex": cr["correlations"][f"{name}:A_days:ks_r20"]["rho"]}
        if name in MAIN:
            row["verdict"] = {"mine": o["verdict"], "codex": cr["verdicts"][name]}
        out["axes"][name] = row
    return out


def main():
    P = tenyr.load_panel()
    M = load_macro()
    S = mark_events(add_axes(spec_days(P), M))
    rs = analyse(S, "spec")
    show(rs, "본 재현(요청서 규칙)")
    cmp_ = compare_codex(S, rs)
    print("\n" + "=" * 8, "Codex 대조")
    print("격자", cmp_["n_mine"], "vs", cmp_["n_codex"], "· 날짜 같음", cmp_["dates_equal"], "· 사건 같음", cmp_["events_equal"], cmp_["events_only_mine"], cmp_["events_only_codex"])
    for c, v in cmp_["max_abs_diff"].items():
        print(f"   {c:9s} 최대 |차| {v['max']:.6f} ({v['date']}) · 0.01 이상 {v['n_over_0.01']}일 · 결측 어긋남 {v['nan_mismatch']}")
    print("   대상 수 다른 날", cmp_["n_eligible_diff_days"], "· 과매도 수 다른 날", cmp_["n_os_diff_days"], "· 칸 다른 날", cmp_["regime_diff_days"],
          "· 결과 누락(전체, 과매도) 나", cmp_["missing_mine"], "Codex", cmp_["missing_codex"], "· 상폐 대체 나", cmp_["delist_mine"], "Codex", cmp_["delist_codex"])
    for name, row in cmp_["axes"].items():
        print(f"\n[{name}] 문턱 {row['thr_mine']:.6f} vs {row['thr_codex']:.6f} · n {row['n_mine']} vs {row['n_codex']}")
        for m, e in row.get("event", {}).items():
            print(f"   사건 {m:12s} 나 {e['mine']:+.3f} [{e['ci_mine'][0]:+.3f}, {e['ci_mine'][1]:+.3f}] · Codex {e['codex']:+.3f} [{e['ci_codex'][0]:+.3f}, {e['ci_codex'][1]:+.3f}]")
        for k, r in row["refs"].items():
            if r["mine"] is not None and r["codex"] is not None:
                print(f"   {k:11s} 나 {r['mine']:+.3f} [{r['ci_mine'][0]:+.3f}, {r['ci_mine'][1]:+.3f}] · Codex {r['codex']:+.3f} [{r['ci_codex'][0]:+.3f}, {r['ci_codex'][1]:+.3f}] · n {r['n_mine']} vs {r['n_codex']}")
        if "verdict" in row:
            print(f"   판정 나 {row['verdict']['mine']} · Codex {row['verdict']['codex']}")
    H = mark_events(add_axes(house_days(P), M))
    rh = analyse(H, "house")
    show(rh, "집 틀 감도(tenyr.signal_days 기본값)")
    print("\n사건 날짜 교집합(본 재현 ∩ 집 틀):", sorted(set(rs["events"]) & set(rh["events"])))
    (OUT / "results.json").write_text(json.dumps({"spec": rs, "house": rh, "codex_compare": cmp_}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n저장:", OUT)


if __name__ == "__main__":
    main()
