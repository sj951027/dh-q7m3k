# -*- coding: utf-8 -*-
"""C5 국면 전환 시 조기 청산 — 11년 대리 (2026-11-10). 메모 `research/REGIME_EXIT_20261110.md` §0 의 규칙·잣대 그대로.
규칙: 보유 중 코스피 20일 등락(종가)이 문턱 이상이면 다음 거래일 종가에 판다, 아니면 40일. 기준 A40. 읽기 전용.
재현: python research/regime_exit_10y_20261110.py → research/out_regime_exit/"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import tenyr

OUT = Path(__file__).resolve().parent / "out_regime_exit"; OUT.mkdir(exist_ok=True)
H, COST, STEP, SPLIT = tenyr.H, tenyr.COST, tenyr.STEP, tenyr.SPLIT
RULES = {"A40": (None, 0), "C5_5": (5.0, 0), "C5_10": (10.0, 0), "C5_5m10": (5.0, 10)}   # (문턱 %, 최소 보유일 전엔 안 봄)

t0 = time.time(); tenyr.reset_rng(); P = tenyr.load_panel()
KS = P.ks_r20.values          # 날짜 정렬 = P.dates


def exit_day(i, thr, m):
    """신호일 i → 매도 인덱스 k(경로 index, 0=진입일 i+1). 보유 k일째 종가(날 i+1+k)에서 ks_r20 ≥ thr 이면 k+1 에 판다."""
    if thr is None:
        return H
    for k in range(max(m, 1), H):      # k = 1..H-1 에서 관측, 집행은 k+1 ≤ H
        v = KS[i + 1 + k]
        if v == v and v >= thr:
            return k + 1
    return H


rows = []
for i in range(tenyr.START, P.N - H - 1, STEP):
    r = P.R20[i]; v0 = (P.VU[i] == 0) | (P.VU[i + 1] == 0)
    e = P.CU[i + 1]; path = P.CF[i + 1:i + 2 + H].T
    ok = ~np.isnan(r) & ~v0 & ~P.PEN[i] & ~np.isnan(e) & (e > 0) & ~np.isnan(path).any(1)
    if ok.sum() < tenyr.MIN_OK:
        continue
    d = P.dates[i]; ks0 = KS[i]
    thr = np.quantile(r[ok], 0.20); os_ = ok & (r <= thr)
    PP = path / e[:, None]; Pos, Pall = PP[os_], PP[ok]
    all40_daily = (Pall[:, H].mean() - 1 - COST) / H
    row = dict(date=d, month=d[:6], i=i, half=("앞" if d < SPLIT else "뒤"), r20=ks0, cell=tenyr.cell6(ks0), A=bool(ks0 == ks0 and ks0 <= -5), n_os=int(os_.sum()))
    for rl, (th, m) in RULES.items():
        K = exit_day(i, th, m); row[f"k_{rl}"] = K; row[f"fire_{rl}"] = int(K < H)
        mrem = ((Pall[:, H] / Pall[:, K]).mean() - 1 - COST) if K < H else 0.0     # ③′ 사후 보정: 판 날 K 부터 40일까지 전 종목 바구니 '실제' 수익(§0 의 ③ 은 창 전체 평균 일수익 — 시장 상승에 조건부인 규칙엔 유리하게 치우침)
        row[f"mrem_{rl}"] = mrem * 100
        for tag, X in (("os", Pos), ("all", Pall)):
            g = X[:, K] - 1 - COST
            rv = (1 + g) * (1 + (all40_daily * (H - K) - COST if K < H else 0.0)) - 1
            rv2 = (1 + g) * (1 + mrem) - 1
            row[f"{tag}_win_{rl}"] = g.mean() * 100; row[f"{tag}_reinv_{rl}"] = rv.mean() * 100; row[f"{tag}_reinv2_{rl}"] = rv2.mean() * 100
        for m_ in ("win", "reinv", "reinv2"):
            row[f"exc_{m_}_{rl}"] = row[f"os_{m_}_{rl}"] - row[f"all_{m_}_{rl}"]
    rows.append(row)
R = pd.DataFrame(rows); R["cell4"] = R.cell.map(tenyr.CELL4); R.to_csv(OUT / "tenyr_days.csv", index=False, encoding="utf-8-sig")
print(f"신호일 {len(R)} · 월 {R.month.nunique()} · 급락 날 {int(R.A.sum())} · {time.time()-t0:.0f}s")

SCOPES = (("전체", R), ("코스피 급락 날", R[R.A]), ("그 밖", R[~R.A]), ("앞반 2015~20", R[R.half == "앞"]), ("뒤반 2021~", R[R.half == "뒤"]))
METRICS = (("os_win", "① 과매도 창 수익(%)"), ("exc_win", "① 창 초과(%p)"), ("os_reinv", "③ 과매도 창 수익+재투자(%)"), ("exc_reinv", "③ 창 초과+재투자(%p)"), ("os_reinv2", "③′ 과매도 창 수익+실제 남은 날 시장(%)"), ("exc_reinv2", "③′ 창 초과+실제 남은 날 시장(%p)"))
out = []
for scope, sub in SCOPES:
    for metric, lab in METRICS:
        base = sub[f"{metric}_A40"]
        for rl in RULES:
            v = sub[f"{metric}_{rl}"]; d_ = v - base
            lo, hi = tenyr.block_ci(v, sub.month)
            dlo, dhi = tenyr.block_ci(d_, sub.month) if rl != "A40" else (np.nan, np.nan)
            out.append(dict(범위=scope, 잣대=lab, rule=rl, 날수=len(sub), 평균=v.mean(), 하한=lo, 상한=hi, A40대비=d_.mean(), 차하한=dlo, 차상한=dhi,
                            양수비율=(v > 0).mean() * 100, 발동비율=sub[f"fire_{rl}"].mean() * 100, 평균보유=sub[f"k_{rl}"].mean()))
T = pd.DataFrame(out); T.to_csv(OUT / "summary.csv", index=False, encoding="utf-8-sig")
for (scope, lab), g in T.groupby(["범위", "잣대"], sort=False):
    print(f"\n### {scope} · {lab} (신호일 {g.날수.iloc[0]})")
    print(g[["rule", "평균", "하한", "상한", "A40대비", "차하한", "차상한", "양수비율", "발동비율", "평균보유"]].round(2).to_string(index=False))

# 설명용(사후): 발동한 앵커만 · 신호일 칸별 발동 비율
print("\n### 설명용 — 발동한 날만(사후 선택, 판정 아님) · ① 창 수익 규칙 − A40")
for rl in ("C5_5", "C5_10", "C5_5m10"):
    f = R[R[f"fire_{rl}"] == 1]
    if len(f) == 0:
        print(f"{rl}: 발동 0"); continue
    d_ = f[f"os_win_{rl}"] - f.os_win_A40; lo, hi = tenyr.block_ci(d_, f.month)
    da = f[f"all_win_{rl}"] - f.all_win_A40; alo, ahi = tenyr.block_ci(da, f.month)
    print(f"{rl}: 발동 {len(f)}일({f.month.nunique()}개월) · 평균 보유 {f[f'k_{rl}'].mean():.1f}일 · 과매도 차 {d_.mean():+.2f} [{lo:+.2f}, {hi:+.2f}] · 시장 차 {da.mean():+.2f} [{alo:+.2f}, {ahi:+.2f}] · 그날 시장 40일 전체 {f.all_win_A40.mean():+.2f} · 판 뒤 남은 날 시장 실제 {f[f'mrem_{rl}'].mean():+.2f}")
print("\n### 설명용 — 신호일 칸별 C5_5 발동 비율·① 차이")
for c in ("A", "B", "C", "D"):
    s = R[R.cell4 == c]
    if len(s) == 0: continue
    d_ = s.os_win_C5_5 - s.os_win_A40; lo, hi = tenyr.block_ci(d_, s.month)
    print(f"{c} 칸 {len(s)}일: 발동 {s.fire_C5_5.mean()*100:.0f}% · 과매도 A40 {s.os_win_A40.mean():+.2f} · C5_5 {s.os_win_C5_5.mean():+.2f} · 차 {d_.mean():+.2f} [{lo:+.2f}, {hi:+.2f}]")
print(f"\n{time.time()-t0:.0f}s")
