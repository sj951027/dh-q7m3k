# -*- coding: utf-8 -*-
"""종목별 환율 반응 × 과매도 40일 — X = β(52주 주간 회귀의 환율 계수) × FX20 의 5분위 Q5 − Q1 (2026-11-17, 읽기 전용).
조건표·닫는 조건·기대는 RESEARCH_fx_exposure_20261117.md §0 (이 스크립트를 돌리기 전에 적음). Codex 가 같은 조건표로 따로 계산한다(눈가림).

틀 = research/lib/tenyr.py(정리 유니버스 · 5거래일 격자 · 과매도 대리 20일 하위 20% · t+1 진입 40일 · 비용 0.35% · 월 블록 2,000회 seed 7).
F(d) = USDKRW 중 날짜 ≤ d−1 달력일의 마지막 값. β = 신호일에서 뒤로 5거래일씩 W 번의 주간 로그수익으로 종목 = a + b_m·코스피 + β·환율(OLS, 유효 주 ≥ 최소).
FX20 = F(i) ÷ (그 관측일의 28달력일 전 이하 마지막 값) − 1 (%). X = β × FX20.
출력: research/out_fx_exposure/days.csv · summary.json · stdout."""
import bisect, json, sqlite3, sys
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from lib import tenyr  # noqa: E402

OUT = HERE / "out_fx_exposure"; OUT.mkdir(exist_ok=True)
MACRO_DB = str(tenyr.REPO / ".." / "dh-q7m3k-data" / "macro_10y.db")
W_MAIN, MIN_MAIN = 52, 40; W_LONG, MIN_LONG = 104, 80; LAG_DAYS = 1; REF20, REF60 = 28, 84; EDGE = 1.0; MIN_Q = 25     # §0 의 값(MIN_Q = 5분위마다 5종목)


def ymd_minus(s, days):
    return (datetime.strptime(s, "%Y%m%d") - timedelta(days=days)).strftime("%Y%m%d")


def load_fx():
    con = sqlite3.connect(f"file:{MACRO_DB}?mode=ro", uri=True)
    m = pd.read_sql("SELECT date, close FROM series_daily WHERE series='USDKRW' ORDER BY date", con); con.close()
    return list(m.date.astype(str)), m.close.values.astype(float)


def fx_asof(fd, fv, d, ref_days=None):
    """d 의 환율 수준(날짜 ≤ d−1 의 마지막 값). ref_days 가 있으면 (수준, 그 관측일에서 ref_days 달력일 전 이하의 마지막 값)."""
    j = bisect.bisect_right(fd, ymd_minus(d, LAG_DAYS)) - 1
    if j < 0:
        return (np.nan, np.nan) if ref_days else np.nan
    if ref_days is None:
        return fv[j]
    k = bisect.bisect_right(fd, ymd_minus(fd[j], ref_days)) - 1
    return (fv[j], fv[k]) if k >= 0 else (fv[j], np.nan)


def betas(P, F, ks, i, W, min_weeks):
    """신호일 i 에서 뒤로 5거래일씩 W 번의 주간 로그수익 회귀. 반환: 종목별 환율 계수(없으면 NaN)."""
    if i - 5 * W < 0:
        return np.full(P.CU.shape[1], np.nan)
    idx = i - 5 * np.arange(W, -1, -1)                                   # 오름차순 W+1 개 시점
    with np.errstate(invalid="ignore", divide="ignore"):
        Y = np.diff(np.log(P.CU[idx]), axis=0)                           # W × 종목
    X = np.column_stack([np.ones(W), np.diff(np.log(ks[idx])), np.diff(np.log(F[idx]))])
    if not np.isfinite(X).all():
        return np.full(P.CU.shape[1], np.nan)
    Wm = np.isfinite(Y).astype(float); Y0 = np.where(np.isfinite(Y), Y, 0.0)
    A = np.einsum("ki,kj,ks->sij", X, X, Wm); b = np.einsum("ki,ks->si", X, Y0)
    out = np.full(Y.shape[1], np.nan); good = Wm.sum(0) >= min_weeks
    if good.any():
        try:
            out[good] = np.linalg.solve(A[good], b[good][..., None])[:, 2, 0]
        except np.linalg.LinAlgError:
            for s in np.where(good)[0]:
                try: out[s] = np.linalg.solve(A[s], b[s])[2]
                except np.linalg.LinAlgError: pass
    return out


def q_spread(x, g):
    """x 5분위(동률은 순서대로)의 g 평균 Q5 − Q1. 종목이 MIN_Q 미만이면 NaN."""
    m = np.isfinite(x) & np.isfinite(g); x, g = x[m], g[m]
    if len(x) < MIN_Q:
        return np.nan
    qb = np.minimum((pd.Series(x).rank(method="first").values - 1) * 5 // len(x), 4).astype(int)
    return float(g[qb == 4].mean() - g[qb == 0].mean())


def rank_corr(x, g):
    m = np.isfinite(x) & np.isfinite(g)
    return float(np.corrcoef(pd.Series(x[m]).rank(), pd.Series(g[m]).rank())[0, 1]) if m.sum() >= MIN_Q else np.nan


tenyr.reset_rng()
P = tenyr.load_panel()
fd, fv = load_fx()
F = np.array([fx_asof(fd, fv, d) for d in P.dates]); ks = P.ks.reindex(P.dates).ffill().values
print(f"환율 자료 {fd[0]}~{fd[-1]} ({len(fd)}일) · 가격판 {P.dates[0]}~{P.dates[-1]}")
PREV = {}                                                               # i → β(52주) — 1년 전 β 와의 안정성용


def extra(P_, i, ok):
    d = P_.dates[i]; out = dict(fx20=np.nan, fx60=np.nan)
    a, b = fx_asof(fd, fv, d, REF20); a6, b6 = fx_asof(fd, fv, d, REF60)
    out["fx20"] = (a / b - 1) * 100 if b == b else np.nan; out["fx60"] = (a6 / b6 - 1) * 100 if b6 == b6 else np.nan
    r = P_.R20[i]; os_ = ok & (r <= np.quantile(r[ok], 0.20))             # 틀과 같은 과매도 집합
    g = (P_.CF[i + 1 + tenyr.H] / P_.CU[i + 1] - 1 - tenyr.COST) * 100
    be = betas(P_, F, ks, i, W_MAIN, MIN_MAIN); bl = betas(P_, F, ks, i, W_LONG, MIN_LONG); PREV[i] = be
    out.update(n_os=int(os_.sum()), n_os_beta=int((os_ & np.isfinite(be)).sum()), beta_sd=float(np.nanstd(be[ok])) if np.isfinite(be[ok]).any() else np.nan)
    f20, f60 = out["fx20"], out["fx60"]
    if f20 == f20 and f20 != 0 and np.isfinite(be).any():
        out.update(sp_os=q_spread(np.where(os_, be * f20, np.nan), g), sp_all=q_spread(np.where(ok, be * f20, np.nan), g),
                   sp_beta_only=q_spread(np.where(os_, be, np.nan), g), rho_os=rank_corr(np.where(os_, be * f20, np.nan), g),
                   sp_w104=q_spread(np.where(os_, bl * f20, np.nan), g) if np.isfinite(bl).any() else np.nan)
        if f60 == f60 and f60 != 0:
            out["sp_fx60"] = q_spread(np.where(os_, be * f60, np.nan), g)
    p = PREV.get(i - 260)
    if p is not None:
        out["beta_stab"] = rank_corr(np.where(ok, p, np.nan), be)
    return out


R = tenyr.signal_days(P, extra=extra)
R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
S = {}


def ci_line(name, col, sub=None):
    x = R if sub is None else R[sub]; v = x[col].values.astype(float); lo, hi = tenyr.block_ci(v, x.month)
    ok_ = np.isfinite(v)
    return dict(이름=name, n=int(ok_.sum()), 평균=float(np.nanmean(v)) if ok_.any() else np.nan, 하한=lo, 상한=hi, 양수비율=float((v[ok_] > 0).mean() * 100) if ok_.any() else np.nan)


def show(d, unit="%p"):
    return f"{d['이름']}: {d['평균']:+.2f}{unit} [{d['하한']:+.2f}, {d['상한']:+.2f}] · 양수인 날 {d['양수비율']:.0f}% · n={d['n']}"


have = R.sp_os.notna()
print(f"\n=== 1. 표본 — 신호일 {len(R)}개 중 주지표가 나온 날 {int(have.sum())}개 [{R.date[have].min()}~{R.date[have].max()}] · 월 {R.month[have].nunique()} ===")
print(f"  과매도 바구니 종목 수 중앙 {R.n_os[have].median():.0f} · β 있는 종목 {100 * (R.n_os_beta[have] / R.n_os[have]).mean():.1f}% · β 의 종목 간 표준편차 중앙 {R.beta_sd[have].median():.2f} · "
      f"FX20 평균 {R.fx20[have].mean():+.2f}% (|FX20| 중앙 {R.fx20[have].abs().median():.2f}%) · 환율이 오른 날 {100 * (R.fx20[have] > 0).mean():.0f}%")
S["main"] = ci_line("주지표 — 과매도 안 X 5분위 Q5 − Q1(40일)", "sp_os"); print("  " + show(S["main"]))
for h in ("앞", "뒤"):
    S[f"half_{h}"] = ci_line(f"{h}반", "sp_os", R.half == h); print("    " + show(S[f"half_{h}"]))
print("  조건에 쓰는 보조:")
for key, col, name in (("all", "sp_all", "전 종목 판"), ("w104", "sp_w104", "β 창 104주"), ("fx60", "sp_fx60", "환율 60거래일 판")):
    S[key] = ci_line(name, col); print("    " + show(S[key]) + f" · 앞반 {R[col][R.half == '앞'].mean():+.2f} / 뒤반 {R[col][R.half == '뒤'].mean():+.2f}")
print("  같이 적는 것(조건 아님):")
S["beta_only"] = ci_line("β 만으로 나눈 Q5 − Q1(환율 방향을 곱하지 않음)", "sp_beta_only"); print("    " + show(S["beta_only"]))
up = R.fx20 > 0
S["beta_up"] = ci_line("  환율이 오른 날의 β Q5 − Q1", "sp_beta_only", up & have); S["beta_dn"] = ci_line("  환율이 내린 날의 β Q5 − Q1", "sp_beta_only", (~up) & have)
print("    " + show(S["beta_up"])); print("    " + show(S["beta_dn"]))
big = R.fx20.abs() >= R.fx20[have].abs().quantile(2 / 3)
S["big"] = ci_line("|FX20| 이 큰 3분의 1 날의 주지표", "sp_os", big & have); print("    " + show(S["big"]))
S["rho"] = ci_line("X 와 40일 수익의 순위 상관(과매도 안)", "rho_os"); print("    " + show(S["rho"], unit=""))
S["stab"] = ci_line("β 안정성 — 같은 종목의 1년 전 β 와의 순위 상관", "beta_stab"); print("    " + show(S["stab"], unit=""))
yr = R[have].assign(year=R.date.str[:4]).groupby("year").sp_os.agg(["mean", "size"])
print("  해마다 주지표: " + " · ".join(f"{y} {v['mean']:+.2f}(n{int(v['size'])})" for y, v in yr.iterrows()))

m = S["main"]; sg = np.sign(m["평균"])
c_size = abs(m["평균"]) >= EDGE; c_ci = (m["하한"] > 0) or (m["상한"] < 0)
c_half = np.sign(S["half_앞"]["평균"]) == sg and np.sign(S["half_뒤"]["평균"]) == sg
c_all = np.sign(S["all"]["평균"]) == sg; c_sens = np.sign(S["w104"]["평균"]) == sg and np.sign(S["fx60"]["평균"]) == sg
verdict = "열림" if (c_size and c_ci and c_half and c_all and c_sens) else "닫음"
print(f"\n=== 2. 닫는 조건 대조(§0) → **{verdict}** ===")
print(f"  |평균| ≥ {EDGE} {'✔' if c_size else '✘'}({m['평균']:+.2f}) · 구간이 0 을 벗어남 {'✔' if c_ci else '✘'}([{m['하한']:+.2f}, {m['상한']:+.2f}]) · 앞·뒤반 같은 부호 {'✔' if c_half else '✘'}"
      f"({S['half_앞']['평균']:+.2f}/{S['half_뒤']['평균']:+.2f}) · 전 종목 판 같은 부호 {'✔' if c_all else '✘'}({S['all']['평균']:+.2f}) · 감도 둘 같은 부호 {'✔' if c_sens else '✘'}({S['w104']['평균']:+.2f}/{S['fx60']['평균']:+.2f})")
S["verdict"] = verdict; S["n_days"] = int(have.sum())
(OUT / "summary.json").write_text(json.dumps(S, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
print(f"\n💾 {OUT}")
