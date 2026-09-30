# pullback_redesign.py — RESEARCH_pullback_redesign_20260930 §0 설계 그대로. 읽기 전용(패널 캐시).
# 실행: python research/pullback_redesign_20260930/pullback_redesign.py [panel.npz]
import os, sys, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "research", "fullscan_20260903"))
PANEL = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "research", "bigwinners_20260924", "panel.npz")
os.environ["FS_PANEL"] = PANEL
import fslib as fs
P = fs.Panel(PANEL); T, N = P.T, P.N; ok = fs.guards(P)
C = pd.DataFrame(P.close.astype(float)); V = pd.DataFrame(P.vol.astype(float))
dates = np.array(P.dates); mk = np.where(P.mk == "KOSPI", 0, 1)
KP = pd.Series(P.kospi.astype(float)).ffill(); KQ = pd.Series(P.kosdaq.astype(float)).ffill()
IDX = pd.DataFrame(np.where(mk[None, :] == 0, KP.values[:, None], KQ.values[:, None]))

# ---- PTW 엔진과 같은 정의 ----
d = C.diff()
gain = d.where(d > 0, 0).rolling(14).mean(); loss = (-d.where(d < 0, 0)).rolling(14).mean()
rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
rsi = rsi.mask(gain.notna() & loss.notna() & (loss == 0) & (gain > 0), 100.0).mask(gain.notna() & loss.notna() & (loss == 0) & (gain == 0), 50.0)
ma5 = C.rolling(5).mean(); ma20 = C.rolling(20).mean()
Tm = (C > ma20) & (ma20 >= ma20.shift(5))                                       # ① 상승추세 = 기준선
near = ((C / ma5 - 1).abs() <= 0.03) | ((C / ma20 - 1).abs() <= 0.03)
dip = (rsi >= 38) & (rsi <= 55)
turn = (rsi.diff() > 0) | (C > C.shift(1))
rs20 = (C / C.shift(20) - 1) * 100 - (IDX / IDX.shift(20) - 1) * 100
P0 = Tm & near & dip & turn & (rs20 >= 0)
# ---- 후보 ----
nh252 = C / C.rolling(252, min_periods=120).max() - 1
dd20 = C / C.rolling(20).max() - 1
P1 = Tm & (nh252 >= -0.10) & (dd20 <= -0.05) & (dd20 >= -0.12) & turn
P2 = P0 & (V.rolling(5).mean() / V.rolling(20).mean() < 0.7)
lv60 = pd.DataFrame(P.ret).rolling(60, min_periods=40).std()
lvr = lv60.where(pd.DataFrame(ok)).rank(axis=1, pct=True)
P3 = P0 & (lvr <= 1 / 3)
r5 = C / C.shift(5) - 1; i5 = IDX / IDX.shift(5) - 1
P4 = P0 & (r5 < 0) & (i5 < 0)
OK = pd.DataFrame(ok) & C.notna()
SIG = {"P0": P0, "P1": P1, "P2": P2, "P3": P3, "P4": P4}

def fwd(h):   # 다음날 종가 진입 → +h 거래일 종가
    return C.shift(-(1 + h)) / C.shift(-1) - 1
def fwdi(h):
    return IDX.shift(-(1 + h)) / IDX.shift(-1) - 1

def bci(x, block=20, reps=3000, q=(0.025, 0.975), seed=930):
    x = np.asarray(x, float); x = x[np.isfinite(x)]; L = len(x)
    if L < 10: return (np.nan, np.nan, np.nan, L)
    r = np.random.default_rng(seed); b = min(block, L // 3)
    st = r.integers(0, L, (reps, int(np.ceil(L / b)))); ix = (st[:, :, None] + np.arange(b)) % L
    mm = x[ix.reshape(reps, -1)[:, :L]].mean(axis=1)
    return (float(x.mean()), float(np.quantile(mm, q[0])), float(np.quantile(mm, q[1])), L)
def f(t): return f"{t[0]*100:+.2f} [{t[1]*100:+.2f}, {t[2]*100:+.2f}] 날짜 {t[3]}"

def evaluate(name, lo, hi, h, q=(0.025, 0.975)):
    rows = (dates >= lo) & (dates <= hi)
    F = fwd(h)[rows]; FX = (fwd(h) - fwdi(h))[rows]
    base = F.where((Tm & OK)[rows]); sig = F.where((SIG[name] & OK)[rows])
    diff = (sig.mean(axis=1) - base.mean(axis=1))
    have = sig.notna().sum(axis=1)
    diff = diff[have >= 3]           # 신호 종목 3개 이상인 날만
    xs = FX.where((SIG[name] & OK)[rows]).stack()
    up = F.where((SIG[name] & OK)[rows]).stack()
    return diff.values, dict(n_obs=int(sig.notna().values.sum()), per_day=float(have[have > 0].mean()) if (have > 0).any() else 0,
                             vs_index=float(xs.mean()), up=float((up > 0).mean()), days=int(len(diff)), dates=dates[rows][have.values >= 3])

L = []
TR = ("20240101", "20250630"); HO = ("20250701", "20260930")
L.append(f"=== 탐색 구간 {TR[0]}~{TR[1]} — 주지표: 신호 − 같은 날 상승추세(T) 종목, 20거래일 (98.75% = Bonferroni 4)")
pick = []
for nm in ["P0", "P1", "P2", "P3", "P4"]:
    x, info = evaluate(nm, *TR, 20)
    ci = bci(x, q=(0.00625, 0.99375)); ci95 = bci(x)
    dd = info["dates"]; h1 = x[dd < "20240701"].mean() if (dd < "20240701").any() else np.nan; h2 = x[dd >= "20240701"].mean()
    L.append(f"  {nm}: 관측 {info['n_obs']:,} (하루 평균 {info['per_day']:.1f}종목) · 20일 T 대비 {f(ci)} · 95% [{ci95[1]*100:+.2f}, {ci95[2]*100:+.2f}] · 반기 2024H1 {h1*100:+.2f} / 이후 {h2*100:+.2f} · 지수 대비 {info['vs_index']*100:+.2f}%p · 오른 비율 {info['up']*100:.1f}%")
    for h in (10, 40):
        xh, _ = evaluate(nm, *TR, h); L.append(f"      h{h}: {f(bci(xh))}")
    if nm != "P0" and np.isfinite(ci[1]) and ci[1] > 0 and h1 > 0 and h2 > 0:
        pick.append((ci[0], nm))
L.append(f"  → 선택 규칙 통과: {[p[1] for p in sorted(pick, reverse=True)] or '없음'}")
if pick:
    best = sorted(pick, reverse=True)[0][1]
    x, info = evaluate(best, *HO, 20); ci = bci(x)
    L.append(f"\n=== 확인 구간 {HO[0]}~ (1회) — {best}: 20일 T 대비 {f(ci)} · 지수 대비 {info['vs_index']*100:+.2f}%p · 오른 비율 {info['up']*100:.1f}% → {'통과' if ci[1] > 0 else '불통과'}")
    for h in (10, 40):
        xh, _ = evaluate(best, *HO, h); L.append(f"      h{h}: {f(bci(xh))}")
    xp, _ = evaluate("P0", *HO, 20); L.append(f"  (참고) P0 확인 구간 20일 T 대비 {f(bci(xp))}")
else:
    L.append("\n=== 확인 구간: 선택된 후보 없음 → 설계대로 중단(확인 구간 열지 않음)")
txt = "\n".join(L); print(txt)
open(os.path.join(HERE, "summary.txt"), "w", encoding="utf-8").write(txt)
