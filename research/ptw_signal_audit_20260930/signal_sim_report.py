# signal_sim_report.py — 가상 포지션 시뮬 결과 집계: 신호 '첫날'(연속 발생은 첫날만) 뒤 20일 수익을
#   같은 프로필의 '⚪ 보유' 첫날들과 비교. 포지션(entry) 단위 클러스터 부트스트랩.
import os, sys, numpy as np, pandas as pd
S = os.path.dirname(os.path.abspath(__file__))
SELL = {"🔴 손절", "🔴 트레일링 손절", "📉 시장 대비 약세", "🔻 추세 둔화 익절", "🔻 모멘텀 둔화", "🔻 고점 이탈 익절",
        "🟡 부분익절", "🟠 익절 준비", "⚠️ RSI 급락", "⏰ 시간 손절", "⚠️ 정체 관찰", "🟢 목표 도달"}
def boot(v, grp, reps=2000, seed=1):
    v = np.asarray(v, float); grp = np.asarray(grp); ok = np.isfinite(v); v, grp = v[ok], grp[ok]
    if len(v) < 5: return (np.nan, np.nan, np.nan)
    u = np.unique(grp); idx = {g: np.where(grp == g)[0] for g in u}; r = np.random.default_rng(seed); ms = []
    for _ in range(reps):
        pick = r.choice(u, len(u)); sel = np.concatenate([idx[g] for g in pick]); ms.append(v[sel].mean())
    return (v.mean(), np.quantile(ms, .025), np.quantile(ms, .975))
L = []
for prof, files in (("#스윙", ["sim_sw1.csv", "sim_sw2.csv"]), ("#저변동", ["sim_lv1.csv", "sim_lv2.csv"])):
    D = pd.concat([pd.read_csv(os.path.join(S, f)).assign(entry=lambda d, f=f: f + ":" + d.entry.astype(str)) for f in files])
    D = D.sort_values(["entry", "day"])
    D["start"] = D.signal != D.groupby("entry").signal.shift(1)
    E = D[D.start]
    hold = E[E.signal == "⚪ 보유"]
    b20 = hold.x20.mean(); b10 = hold.x10.mean()
    L.append(f"=== {prof} — 가상 포지션 {D.entry.nunique():,}개 · 보유일 {len(D):,} · 신호 첫날 기준 · 비교 = '⚪ 보유' 첫날 (20일 지수 대비 {b20*100:+.2f}%p, 10일 {b10*100:+.2f}%p)")
    L.append(f"  {'신호':<14} {'첫날 수':>7} {'평균 보유일':>6} {'그때 손익':>7} | 10일 뒤 지수 대비(보유 대비) | 20일 뒤 지수 대비 [95%] (보유 대비) | 20일 오른 비율 | 판독")
    for sig, g in sorted(E.groupby("signal"), key=lambda kv: -len(kv[1])):
        if len(g) < 15: continue
        c20 = boot(g.x20.values, g.entry.values); d20 = c20[0] - b20; d10 = g.x10.mean() - b10
        up = (g.r20 > 0).mean()
        if sig == "⚪ 보유": verdict = "기준"
        elif sig in SELL:
            verdict = "팔면 이득(이후 더 약함)" if c20[2] < b20 else ("팔면 손해(이후 더 강함)" if c20[1] > b20 else "보유와 구분 안 됨")
        else:
            verdict = "들고 있으면 이득(이후 더 강함)" if c20[1] > b20 else ("이후 더 약함" if c20[2] < b20 else "보유와 구분 안 됨")
        L.append(f"  {sig:<14} {len(g):>7,} {g.day.mean():>6.0f}일 {g.pnl.mean():>+6.1f}% | {g.x10.mean()*100:+.2f} ({d10*100:+.2f}) | {c20[0]*100:+.2f} [{c20[1]*100:+.2f}, {c20[2]*100:+.2f}] ({d20*100:+.2f}) | {up*100:.0f}% | {verdict}")
    L.append("  (신호 분포 전체 일수) " + ", ".join(f"{k} {v}" for k, v in D.signal.value_counts().items()))
txt = "\n".join(L); print(txt); open(os.path.join(S, "signal_sim_summary.txt"), "w", encoding="utf-8").write(txt)
