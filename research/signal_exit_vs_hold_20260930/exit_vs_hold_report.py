# exit_vs_hold_report.py — §0 주지표: 앵커별 [B−A] 평균 → 앵커 블록 부트스트랩 95%.
import os, numpy as np, pandas as pd
S = os.path.dirname(os.path.abspath(__file__))
def bci(x, block, reps=3000, seed=930):
    x = np.asarray(x, float); x = x[np.isfinite(x)]; L = len(x)
    if L < 4: return (np.nanmean(x) if L else np.nan, np.nan, np.nan, L)
    b = max(1, min(block, L // 3)); r = np.random.default_rng(seed)
    st = r.integers(0, L, (reps, int(np.ceil(L / b)))); ix = (st[:, :, None] + np.arange(b)) % L
    mm = x[ix.reshape(reps, -1)[:, :L]].mean(axis=1)
    return (x.mean(), np.quantile(mm, .025), np.quantile(mm, .975), L)
def f(t): return f"{t[0]*100:+.2f} [{t[1]*100:+.2f}, {t[2]*100:+.2f}]" if np.isfinite(t[1]) else f"{t[0]*100:+.2f} (n<4)"
def verdict(t):
    if not np.isfinite(t[1]): return "판단 불가"
    return "갈아타기가 낫다" if t[1] > 0 else ("40일 유지가 낫다" if t[2] < 0 else "차이 없음")
L = []
for smp, files, block in (("LVB", ["evh_lvb.csv"], 40), ("V30", ["evh_v30.csv"], 40), ("Q3Y", ["evh_q3y0.csv", "evh_q3y1.csv"], 8)):
    D = pd.concat([pd.read_csv(os.path.join(S, x), dtype={"anchor": str}) for x in files]).sort_values("anchor")
    G = D.groupby("anchor").mean(numeric_only=True)
    L.append(f"=== {smp}: 매수일 {len(G)} · 종목-매수일 {len(D):,} · A(40일 유지) 평균 {D.A.mean()*100:+.2f}% · 지수 {D.ix.mean()*100:+.2f}%")
    for nm, lab in (("1", "S1 익절류"), ("2", "S2 매도 쪽 전부")):
        hit = D[f"day{nm}"].notna()
        tB = bci((G[f"B{nm}"] - G.A).values, block); tC = bci((G[f"C{nm}"] - G.A).values, block)
        L.append(f"  {lab}: 신호 뜬 비율 {hit.mean()*100:.0f}% (평균 {D.loc[hit, f'day{nm}'].mean():.0f}거래일째)")
        L.append(f"    B 갈아타기 − A 유지: {f(tB)}%p → {verdict(tB)}")
        L.append(f"    C 현금     − A 유지: {f(tC)}%p → {verdict(tC)}")
        H = D[hit]
        if len(H):
            L.append(f"    신호 뜬 종목만(조건부): B−A {(H[f'B{nm}']-H.A).mean()*100:+.2f}%p · C−A {(H[f'C{nm}']-H.A).mean()*100:+.2f}%p · 판 뒤 남은 기간 그 종목 수익 {((1+H.A)/(1+H[f'C{nm}'])-1).mean()*100:+.2f}% (n={len(H)})")
    if smp == "Q3Y":
        for y in ("2024", "2025", "2026"):
            g = G[G.index.str.startswith(y)]
            L.append(f"    연도 {y}: S1 B−A {(g.B1-g.A).mean()*100:+.2f} · C−A {(g.C1-g.A).mean()*100:+.2f} (매수일 {len(g)})")
    L.append(f"  S1 신호 종류: {D.sig1[D.sig1.fillna('') != ''].value_counts().to_dict()}")
txt = "\n".join(L); print(txt); open(os.path.join(S, "exit_vs_hold_summary.txt"), "w", encoding="utf-8").write(txt)
