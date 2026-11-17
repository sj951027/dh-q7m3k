# -*- coding: utf-8 -*-
"""변동성 역가중 — 같은 바구니를 '같은 금액' vs '덜 흔들리는 종목에 더 많이'(w ∝ 1/σ) 로 실었을 때의 차이 (2026-11-17, 읽기 전용 · 지도 카드 H3).
설계·닫는 조건·기대는 RESEARCH_invvol_weight_20261117.md §0 (이 스크립트를 돌리기 전에 적음).

틀 = research/lib/tenyr.py 그대로(정리 유니버스 · 과매도 대리 = 20일 수익 하위 20% · 5거래일 격자 · t+1 종가 진입 · 40거래일 · 비용 0.35% · 월 블록 2,000회 seed 7).
σ = 신호일까지 W 거래일 일간 로그수익의 표준편차(유효 ≥ 2W/3). 본검정 W=60 · 바구니 안 하위 5% 바닥 · w ∝ 1/σ.
주지표 D = 역가중 − 같은 금액(신호일 짝, %p). 감도: W 20·120 · 1/σ² · 바닥 없음. 참고: 실제 v30 목록(시장별 상위 10, 40일·20일).
출력: research/out_invvol_weight/days.csv · summary.json · v30_days.csv · stdout."""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from lib import tenyr  # noqa: E402

OUT = HERE / "out_invvol_weight"; OUT.mkdir(exist_ok=True)
WINS = (60, 20, 120); MAIN_W = 60; FLOOR_Q = 0.05; TAIL_Q = 0.10; EDGE = 0.5      # §0 에 적은 값
pd.set_option("display.width", 240)


def inv_w(sig, power=1.0, floor_q=FLOOR_Q):
    """w ∝ 1/σ^power (합 1). floor_q 가 있으면 바구니 안 그 분위보다 작은 σ 를 그 값으로 올린다."""
    s = np.asarray(sig, float).copy()
    if floor_q is not None and len(s):
        s = np.maximum(s, np.quantile(s, floor_q))
    w = 1.0 / s ** power
    return w / w.sum()


def spearman(a, b):
    if len(a) < 8:
        return np.nan
    return float(np.corrcoef(pd.Series(a).rank(), pd.Series(b).rank())[0, 1])


def ci_line(name, vals, months):
    vals = np.asarray(vals, float); lo, hi = tenyr.block_ci(vals, months)
    return dict(이름=name, n=int((~np.isnan(vals)).sum()), 평균=float(np.nanmean(vals)), 하한=lo, 상한=hi, 양수비율=float((vals[~np.isnan(vals)] > 0).mean() * 100))


def show(d, unit="%p"):
    return f"{d['이름']}: {d['평균']:+.2f}{unit} [{d['하한']:+.2f}, {d['상한']:+.2f}] · 양수인 날 {d['양수비율']:.0f}% · n={d['n']}"


# ── 1. 11년 대리 ─────────────────────────────────────────────────────────
tenyr.reset_rng()
P = tenyr.load_panel()
lr = np.log(P.cu).diff()
SIG = {W: lr.rolling(W, min_periods=int(np.ceil(W * 2 / 3))).std().values for W in WINS}


def extra(P_, i, ok):
    r = P_.R20[i]; thr = np.quantile(r[ok], 0.20); os_ = ok & (r <= thr)          # 틀과 같은 과매도 집합
    g = (P_.CF[i + 1 + tenyr.H] / P_.CU[i + 1] - 1 - tenyr.COST) * 100
    out = dict(n_all=int(os_.sum()))
    for W in WINS:
        s = SIG[W][i]; v = os_ & ~np.isnan(s) & (s > 0)
        gv, sv = g[v], s[v]
        out[f"n{W}"] = int(v.sum()); out[f"ew{W}"] = float(gv.mean()); out[f"iv{W}"] = float((inv_w(sv) * gv).sum())
        if W == MAIN_W:
            w = inv_w(sv)
            out.update(iv_sq=float((inv_w(sv, power=2.0) * gv).sum()), iv_nofloor=float((inv_w(sv, floor_q=None) * gv).sum()),
                       effn=float(1 / (w ** 2).sum()), wmax=float(w.max() * 100), rho_sig_g=spearman(sv, gv),
                       sig_med=float(np.median(sv) * 100), g_lowvol=float(gv[sv <= np.median(sv)].mean()), g_highvol=float(gv[sv > np.median(sv)].mean()))
            qb = np.minimum((pd.Series(sv).rank(method="first").values - 1) * 5 // len(sv), 4).astype(int)      # σ 5분위(0 = 가장 덜 흔들림)
            for q in range(5):
                out[f"q{q + 1}"] = float(gv[qb == q].mean()); out[f"q{q + 1}_med"] = float(np.median(gv[qb == q]))
    return out


R = tenyr.signal_days(P, extra=extra)
for W in WINS:
    R[f"D{W}"] = R[f"iv{W}"] - R[f"ew{W}"]
R["D_sq"] = R.iv_sq - R[f"ew{MAIN_W}"]; R["D_nofloor"] = R.iv_nofloor - R[f"ew{MAIN_W}"]
R.to_csv(OUT / "days.csv", index=False, encoding="utf-8-sig")
ew, iv, D = R[f"ew{MAIN_W}"], R[f"iv{MAIN_W}"], R[f"D{MAIN_W}"]
S = {}

print(f"\n=== 1. 11년 대리 — 신호일 {len(R)}개 [{R.date.min()}~{R.date.max()}] · 월 {R.month.nunique()} ===")
print(f"  바구니(과매도 대리) 종목 수 중앙 {R.n_all.median():.0f} · σ60 있는 종목 {100 * (R[f'n{MAIN_W}'] / R.n_all).mean():.1f}% · "
      f"역가중의 실효 종목 수 중앙 {R.effn.median():.0f}(같은 금액이면 {R[f'n{MAIN_W}'].median():.0f}) · 한 종목 최대 비중 중앙 {R.wmax.median():.2f}%")
print(f"  같은 금액 40일 {ew.mean():+.2f}% · 역가중 {iv.mean():+.2f}% (틀의 os40 {R.os40.mean():+.2f}% — σ 없는 종목을 뺀 차이 {ew.mean() - R.os40.mean():+.2f})")
S["main"] = ci_line("본검정 D(역가중 − 같은 금액, σ60·바닥 5%)", D, R.month); print("  " + show(S["main"]))
for h in ("앞", "뒤"):
    m = R.half == h; S[f"half_{h}"] = ci_line(f"{h}반", D[m], R.month[m]); print("    " + show(S[f"half_{h}"]))
print("  감도(본검정 아님):")
for key, name in ((f"D20", "σ 창 20일"), ("D120", "σ 창 120일"), ("D_sq", "1/σ² 가중"), ("D_nofloor", "바닥 없음")):
    S[key] = ci_line(name, R[key], R.month); line = show(S[key])
    hv = " · 앞반 {:+.2f} / 뒤반 {:+.2f}".format(R[key][R.half == "앞"].mean(), R[key][R.half == "뒤"].mean())
    print("    " + line + hv)

print(f"\n=== 2. 흔들림 ===")
sd_e, sd_i = float(ew.std()), float(iv.std())
print(f"  신호일별 바구니 40일 수익의 표준편차: 같은 금액 {sd_e:.2f}%p · 역가중 {sd_i:.2f}%p → {100 * (sd_i / sd_e - 1):+.1f}%")
for h in ("앞", "뒤"):
    m = R.half == h; print(f"    {h}반: 같은 금액 {ew[m].std():.2f} · 역가중 {iv[m].std():.2f} → {100 * (iv[m].std() / ew[m].std() - 1):+.1f}%")
cut = ew.quantile(TAIL_Q); bad = ew <= cut
S["tail"] = ci_line(f"가장 나빴던 {TAIL_Q:.0%} 신호일(같은 금액 ≤ {cut:+.1f}%)의 D", D[bad], R.month[bad]); print("  " + show(S["tail"]))
for h in ("앞", "뒤"):
    m = bad & (R.half == h)
    if m.sum() >= 3:
        S[f"tail_{h}"] = ci_line(f"{h}반 나쁜 날", D[m], R.month[m]); print("    " + show(S[f"tail_{h}"]))
good = ew >= ew.quantile(1 - TAIL_Q)
S["best"] = ci_line(f"가장 좋았던 {TAIL_Q:.0%} 신호일의 D", D[good], R.month[good]); print("  " + show(S["best"]))
print(f"  최악 신호일: 같은 금액 {ew.min():+.1f}% · 역가중 {iv.min():+.1f}% / 하위 5% 평균: 같은 금액 {ew[ew <= ew.quantile(.05)].mean():+.1f}% · 역가중 {iv[iv <= iv.quantile(.05)].mean():+.1f}%")

print(f"\n=== 3. 칸별 D (코스피 20일 등락: A ≤ −5 · B ≤ 0 · C ≤ +5 · D 그 위) ===")
for c in ("A", "B", "C", "D"):
    m = R.cell4 == c
    if m.sum() >= 5:
        S[f"cell_{c}"] = ci_line(f"칸 {c}", D[m], R.month[m])
        print("  " + show(S[f"cell_{c}"]) + f" · 앞반 {D[m & (R.half == '앞')].mean():+.2f} / 뒤반 {D[m & (R.half == '뒤')].mean():+.2f}")

print(f"\n=== 4. 왜 그런가 — 바구니 안에서 σ 와 40일 수익의 관계 ===")
S["rho"] = ci_line("σ60 과 40일 수익의 순위 상관(바구니 안, 신호일 평균)", R.rho_sig_g, R.month); print("  " + show(S["rho"], unit=""))
gap = R.g_lowvol - R.g_highvol
S["halfgap"] = ci_line("덜 흔들린 절반 − 더 흔들린 절반(40일 수익)", gap, R.month); print("  " + show(S["halfgap"]))
print(f"    앞반 {gap[R.half == '앞'].mean():+.2f} / 뒤반 {gap[R.half == '뒤'].mean():+.2f} (K26 '과매도 안 저변동' 앞 −2.6 · 뒤 +2.7 과 같은 방향인지)")
yr = R.assign(year=R.date.str[:4]).groupby("year").agg(n=("date", "size"), D=(f"D{MAIN_W}", "mean"), ew=(f"ew{MAIN_W}", "mean"))
print("  해마다 D: " + " · ".join(f"{y} {v.D:+.2f}(n{int(v.n)})" for y, v in yr.iterrows()))

# ── 5. 실제 v30 목록(참고) ───────────────────────────────────────────────
print(f"\n=== 5. 참고 — 실제 v30 목록(시장별 상위 10 · 등록 뒤 · t+1 종가 · ohlcv.db 본표) ===")
try:
    import leaderboard as lb
    import build_v32a_page as pg
    close, _ = lb.load_ohlcv(); close.index = close.index.astype(str)
    con = sqlite3.connect(f"file:{REPO / 'history.db'}?mode=ro", uri=True)
    reg = lb.REG_DATE.get("v30")
    V = pd.read_sql("SELECT run_id, market, ticker, final_score_v3 FROM v3_scores WHERE model_id='v30' AND run_id >= ?", con, params=[reg])
    partial, dbl, didx = lb.build_gates(con, close.index); con.close()
    V["run_id"] = V.run_id.astype(str); V["ticker"] = V.ticker.astype(str); V["market"] = V.market.str.lower()
    keep = lb.dedupe_by_anchor(V.rename(columns={"final_score_v3": "score"}), didx, partial | dbl, reg=reg)
    sig60 = np.log(close.where(close > 0)).diff().rolling(60, min_periods=40).std()
    cf = close.ffill(); dates = list(close.index); N = len(dates); rows = []
    for rid in sorted(keep):
        t = lb.anchor(rid, didx); rec = dict(run_id=rid, date=dates[t], month=dates[t][:6])
        for h in (40, 20):
            if t + 1 + h >= N:
                continue
            ds, es = [], []
            for mkt in ("kospi", "kosdaq"):
                tk = [k for k in pg.top(V[(V.run_id == rid) & (V.market == mkt)])["ticker"] if k in close.columns]
                p0 = close.iloc[t + 1][tk]; g = (cf.iloc[t + 1 + h][tk] / p0 - 1) * 100; s = sig60.iloc[t][tk]
                ok = p0.notna() & (p0 > 0) & g.notna() & s.notna() & (s > 0)
                if ok.sum() < 5:
                    continue
                gv, sv = g[ok].values, s[ok].values
                es.append(gv.mean()); ds.append((inv_w(sv) * gv).sum() - gv.mean())
            if len(ds) == 2:
                rec[f"ew{h}"] = float(np.mean(es)); rec[f"D{h}"] = float(np.mean(ds))
        rows.append(rec)
    VD = pd.DataFrame(rows); VD.to_csv(OUT / "v30_days.csv", index=False, encoding="utf-8-sig")
    for h in (40, 20):
        if f"D{h}" in VD and VD[f"D{h}"].notna().sum() >= 5:
            x = VD.dropna(subset=[f"D{h}"]); S[f"v30_h{h}"] = ci_line(f"v30 실제 목록 h{h} D", x[f"D{h}"], x.month)
            print("  " + show(S[f"v30_h{h}"]) + f" [{x.run_id.min()}~{x.run_id.max()}] · 같은 금액 {x[f'ew{h}'].mean():+.2f}% · 월 {x.month.nunique()}개(창이 겹쳐 가르는 힘 없음 — 방향만)")
except Exception as e:                                     # 참고 절이 실패해도 본검정 결과는 남긴다
    print(f"  (참고 절 생략: {e!r})")

# ── 6. 닫는 조건(§0 에 적은 그대로) ──────────────────────────────────────
m = S["main"]; ha, hb = S["half_앞"]["평균"], S["half_뒤"]["평균"]; signs = [S[k]["평균"] > 0 for k in ("main", "D20", "D120")]
open_ = m["하한"] > 0 and ha > 0 and hb > 0 and all(signs)
t = S["tail"]; ta, tb = S.get("tail_앞", {}).get("평균"), S.get("tail_뒤", {}).get("평균")
risk = (m["하한"] <= 0 <= m["상한"]) and abs(m["평균"]) < EDGE and t["하한"] > 0 and ta is not None and tb is not None and ta > 0 and tb > 0
verdict = "열림" if open_ else ("흔들림만 줄임" if risk else "닫음")
if verdict == "열림" and "v30_h40" in S and S["v30_h40"]["평균"] < 0:
    verdict = "보류(대리는 열림 · 실제 목록 부호 반대)"
print(f"\n=== 6. 닫는 조건 대조 → **{verdict}** ===")
print(f"  열림: 전체 하단 > 0 {'✔' if m['하한'] > 0 else '✘'}({m['하한']:+.2f}) · 앞·뒤반 모두 양수 {'✔' if ha > 0 and hb > 0 else '✘'}({ha:+.2f}/{hb:+.2f}) · σ 창 20·60·120 모두 양수 {'✔' if all(signs) else '✘'}")
print(f"  흔들림만 줄임: D 가 0 을 걸치고 |D| < {EDGE} {'✔' if (m['하한'] <= 0 <= m['상한']) and abs(m['평균']) < EDGE else '✘'} · 나쁜 날 D 하단 > 0 {'✔' if t['하한'] > 0 else '✘'}({t['하한']:+.2f}) · "
      f"앞·뒤반 나쁜 날 모두 양수 {'✔' if (ta is not None and tb is not None and ta > 0 and tb > 0) else '✘'}({ta if ta is None else round(ta, 2)}/{tb if tb is None else round(tb, 2)})")
# ── 7. 탐색(결과를 본 뒤 19:05 에 붙임 — §6 결론에 쓰지 않는다. 부트스트랩 호출을 맨 뒤에 둬 위 숫자는 그대로) ──
print(f"\n=== 7. 탐색 — σ60 5분위별 40일 수익(1 = 가장 덜 흔들림 · 5 = 가장 많이 흔들림) ===")
for lab, m in (("전체", R.half.notna()), ("앞반", R.half == "앞"), ("뒤반", R.half == "뒤")):
    print(f"  {lab}: 평균 " + " · ".join(f"Q{q} {R[f'q{q}'][m].mean():+.2f}" for q in range(1, 6)) + "   | 중앙값 " + " · ".join(f"Q{q} {R[f'q{q}_med'][m].mean():+.2f}" for q in range(1, 6)))
q15 = R.q1 - R.q5
S["q1_q5"] = ci_line("Q1 − Q5 (덜 흔들린 5분위 − 많이 흔들린 5분위)", q15, R.month); print("  " + show(S["q1_q5"]))
print(f"    앞반 {q15[R.half == '앞'].mean():+.2f} / 뒤반 {q15[R.half == '뒤'].mean():+.2f}   ← 10/23 옛 유니버스(동전주·우선주·스팩 포함)에서는 앞 −2.63 / 뒤 +2.65 였다(K26)")
S["ex_q5"] = ci_line("가장 많이 흔들린 5분위만 뺀 같은 금액 − 전체 같은 금액", (R.q1 + R.q2 + R.q3 + R.q4) / 4 - R[f"ew{MAIN_W}"], R.month); print("  " + show(S["ex_q5"]))
S["verdict"] = verdict; S["sd"] = dict(ew=sd_e, iv=sd_i); S["n_days"] = len(R)
(OUT / "summary.json").write_text(json.dumps(S, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n💾 {OUT}")
