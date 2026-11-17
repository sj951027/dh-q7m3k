# -*- coding: utf-8 -*-
"""K26 '과매도 안 저변동 탈락'(10/23: Q1−Q5 앞반 −2.63 · 뒤반 +2.65)과 11/17 탐색(+1.36 · +3.64)이 왜 다른가 — 틀 차이를 하나씩 되돌려 본다.
(2026-11-17, 읽기 전용 · 탐색 — 결과를 본 뒤의 확인이라 결론 조건에 쓰지 않는다. RESEARCH_invvol_weight_20261117.md §3)

10/23 `pick_10y_20261023.py` 와 지금 틀(`lib/tenyr.py`)의 차이 넷:
  ① 유니버스: 그때는 전 종목(우선주·스팩·금융 포함) / 지금은 정리 유니버스   ② 동전주(<1,000원)·거래량 0: 그때 포함 / 지금 제외
  ③ 40일 안에 가격이 끊긴 종목(폐지 등): 그때 표본에서 빠짐 / 지금 마지막 가격으로 청산   ④ 비용: 그때 0 / 지금 0.35%(분위 차이에는 영향 없음)
출력: 화면만."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from lib import tenyr  # noqa: E402


def q1_q5(P, pen=True, vol0=True, ffill=True):
    """신호일마다 과매도(20일 하위 20%) 안 σ60 5분위의 40일 수익 Q1(덜 흔들림) − Q5. 반환 DataFrame(date, month, half, d, n)."""
    sig = np.log(P.cu).diff().rolling(60, min_periods=40).std().values
    rows = []
    for i in range(tenyr.START, P.N - tenyr.H - 1, tenyr.STEP):
        r = P.R20[i]; e = P.CU[i + 1]; pH = (P.CF if ffill else P.CU)[i + 1 + tenyr.H]
        ok = ~np.isnan(r) & ~np.isnan(e) & (e > 0) & ~np.isnan(pH)
        if vol0:
            ok &= ~((P.VU[i] == 0) | (P.VU[i + 1] == 0))
        if pen:
            ok &= ~P.PEN[i]
        if ok.sum() < tenyr.MIN_OK:
            continue
        os_ = ok & (r <= np.quantile(r[ok], 0.20)) & ~np.isnan(sig[i]) & (sig[i] > 0)
        g = (pH[os_] / e[os_] - 1) * 100; s = sig[i][os_]
        qb = np.minimum((pd.Series(s).rank(method="first").values - 1) * 5 // len(s), 4).astype(int)
        d = P.dates[i]
        rows.append(dict(date=d, month=d[:6], half=("앞" if d < tenyr.SPLIT else "뒤"), d=float(g[qb == 0].mean() - g[qb == 4].mean()), n=int(os_.sum())))
    return pd.DataFrame(rows)


def line(name, R):
    lo, hi = tenyr.block_ci(R.d, R.month)
    a, b = R.d[R.half == "앞"].mean(), R.d[R.half == "뒤"].mean()
    print(f"  {name}: Q1−Q5 {R.d.mean():+.2f} [{lo:+.2f}, {hi:+.2f}] · 앞반 {a:+.2f} / 뒤반 {b:+.2f} · 신호일 {len(R)} · 바구니 중앙 {R.n.median():.0f}종목")


tenyr.reset_rng()
P = tenyr.load_panel()
print("\n[정리 유니버스]")
line("가. 지금 틀 그대로", q1_q5(P))
line("나. 동전주·거래량 0 을 다시 넣음", q1_q5(P, pen=False, vol0=False))
line("다. 가격이 끊긴 종목을 표본에서 뺌(마지막 가격 청산 안 함)", q1_q5(P, ffill=False))
line("라. 나 + 다", q1_q5(P, pen=False, vol0=False, ffill=False))
orig = tenyr._is_universe
tenyr._is_universe = lambda t, m, n: True                  # 전 종목(이 프로세스 안에서만)
try:
    PA = tenyr.load_panel()
finally:
    tenyr._is_universe = orig
print("\n[전 종목 — 우선주·스팩·금융 포함]")
line("마. 전 종목 + 지금 틀의 거르기", q1_q5(PA))
line("바. 전 종목 + 동전주·거래량 0 포함 + 끊긴 종목 뺌 (= 10/23 과 가장 가까움)", q1_q5(PA, pen=False, vol0=False, ffill=False))
print("\n  10/23 원래 값(K26): Q1−Q5 +0.04 [−1.12, +1.18] · 앞반 −2.63 / 뒤반 +2.65")
