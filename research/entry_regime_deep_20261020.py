# -*- coding: utf-8 -*-
"""entry_regime_deep_20261020.py — "급락 뒤 매수" 심화 (2026-10-20, 읽기 전용 · 관측 · 판정 아님)

RESEARCH_entry_regime_20261020.md 의 1차 결과(크게 떨어진 뒤 매수가 40일 뒤 가장 좋음)를 아홉 가지로 뜯어본다. 모델 무관, 3년 전 종목.
  S1 문턱×기간: 낙폭 문턱 −3/−5/−8/−10 · 되돌아보기 10/20/40 · 보유 20/40/60 · 지수 코스피/코스닥
  S2 사건별: 코스피·코스닥 '급락 뒤' 사건(겹치지 않게 40거래일 간격)마다 날짜·낙폭·20/40/60일 수익·보유 중 최악
  S3 칸에 들어온 지 며칠째(1~3 / 4~10 / 11+)  S4 깊이(−5~−10 / −10~−15 / <−15)
  S5 위험: 보유 40일 안 최악 낙폭(경로)·하위 10% 수익  S6 다른 신호(60일 고점 대비 −10% · 20일선 아래 5일째 · 지수 RSI14<30)
  S7 급락 뒤 어떤 종목: 많이 떨어진(20일 하위 20%)·조용한(60일 변동성 하위 20%)·큰 회사(시총 상위 20%)·작은 회사(하위 20%)
  S8 칸의 빈도·지속·이동  S9 단순 규칙 모의(40일 슬롯·비용 0.5%): 항상 / 급락 뒤만 / 급등 뒤 절반 / 급락 뒤 2배
수익 = 다음 거래일 종가 매수 → h 거래일 뒤 종가. 전 종목 동일가중(그날 시세 있는 종목). 구간은 겹침 때문에 생략하고 '겹치지 않는 사건 수'를 적는다.
출력: research/out_entry_regime/deep_summary.md (+ episodes.csv)
"""
import sys, sqlite3
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import leaderboard as lb  # noqa: E402

OUT = HERE / "out_entry_regime"; OUT.mkdir(exist_ok=True)
con = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
idx = pd.read_sql("SELECT series, date, close FROM market_daily WHERE series IN ('KOSPI','KOSDAQ')", con).pivot(index="date", columns="series", values="close").sort_index()
px = pd.read_sql("SELECT ticker, date, close, shares FROM daily_ohlcv", con); con.close()
px["ticker"] = px.ticker.astype(str).str.zfill(6)
close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
shares = px.pivot_table(index="date", columns="ticker", values="shares", aggfunc="last").sort_index().reindex(close.index).ffill()
dates = list(close.index); N = len(dates)
dret = close.pct_change(fill_method=None)
ew_d = dret.mean(axis=1)                                   # 전 종목 동일가중 일수익
IDX = {s: idx[s].reindex(dates).ffill() for s in ("KOSPI", "KOSDAQ")}


def fwd_ret(h):
    return (close.shift(-(1 + h)) / close.shift(-1) - 1) * 100   # t+1 → t+1+h, 종목별


FWD = {h: fwd_ret(h) for h in (20, 40, 60)}
EW = {h: FWD[h].mean(axis=1) for h in FWD}                   # 전 종목 동일가중 h일 수익(진입 t 기준)


def nonov(ix, h):
    k, last = 0, -10**9
    for i in ix:
        if i - last >= h:
            k += 1; last = i
    return k


def worst_path(i, h=40):
    """t+1 매수 뒤 h일 안 전 종목 동일가중 경로의 최저점(%)."""
    seg = ew_d.iloc[i + 2:i + 2 + h]
    if len(seg) < 5:
        return np.nan
    cum = (1 + seg).cumprod()
    return float((cum.min() - 1) * 100)


L = ["# 급락 뒤 매수 — 심화 (2026-10-20, 관측 · 판정 아님)", "", f"가격 {dates[0]}~{dates[-1]} · 전 종목 동일가중 · 매수 = 다음 거래일 종가 · n = 날 수(괄호 = 겹치지 않는 사건 수, 보유일 간격)", ""]

# ───── S1 문턱 × 되돌아보기 × 보유 × 지수 ─────
L += ["## S1 문턱·기간을 바꿔도 사는가 — '낙폭 문턱 이하인 날' 매수의 평균 수익(%) · 승률 · 날 수(사건)", ""]
for s in ("KOSPI", "KOSDAQ"):
    L += [f"### {s} 기준", "", "| 되돌아보기 | 문턱 | 보유 20일 | 보유 40일 | 보유 60일 |", "|---|---|---|---|---|"]
    for lb_ in (10, 20, 40):
        r = (IDX[s] / IDX[s].shift(lb_) - 1) * 100
        for th in (-3, -5, -8, -10):
            cells = []
            for h in (20, 40, 60):
                m = (r <= th) & EW[h].notna()
                ix = [i for i in range(N) if m.iloc[i]]
                if not ix:
                    cells.append("—"); continue
                v = EW[h].iloc[ix]
                cells.append(f"{v.mean():+.1f} · {(v > 0).mean():.0%} · {len(ix)}({nonov(ix, h)})")
            L.append(f"| {lb_}일 | ≤{th}% | " + " | ".join(cells) + " |")
    L.append("")
# 비교용: 전체 평균
L += ["비교: 아무 날이나 매수 — " + " · ".join(f"보유 {h}일 {EW[h].mean():+.1f}%(승률 {(EW[h].dropna() > 0).mean():.0%})" for h in (20, 40, 60)), ""]

# ───── S2 사건별 ─────
L += ["## S2 사건별 — '급락 뒤(20일 ≤ −5%)' 에 처음 들어온 날(40거래일 간격)", ""]
ep_rows = []
for s in ("KOSPI", "KOSDAQ"):
    r = (IDX[s] / IDX[s].shift(20) - 1) * 100
    L += [f"### {s}", "", "| 진입일 | 20일 낙폭 | 그 뒤 20일 | 40일 | 60일 | 보유 40일 중 최악(경로) | 그 뒤 20일 지수 |", "|---|---|---|---|---|---|---|"]
    last = -10**9
    for i in range(25, N - 21):
        if r.iloc[i] <= -5 and i - last >= 40:
            last = i
            vals = [EW[h].iloc[i] if i + 1 + h < N else np.nan for h in (20, 40, 60)]
            w = worst_path(i)
            ir = (IDX[s].iloc[i + 21] / IDX[s].iloc[i + 1] - 1) * 100 if i + 21 < N else np.nan
            ep_rows.append({"by": s, "date": dates[i], "drop20": r.iloc[i], "r20": vals[0], "r40": vals[1], "r60": vals[2], "worst40": w, "idx20": ir})
            f = lambda v: "—" if np.isnan(v) else f"{v:+.1f}"
            L.append(f"| {dates[i]} | {r.iloc[i]:+.1f}% | {f(vals[0])} | {f(vals[1])} | {f(vals[2])} | {f(w)} | {f(ir)} |")
    L.append("")
pd.DataFrame(ep_rows).to_csv(OUT / "episodes.csv", index=False, encoding="utf-8-sig")

# ───── S3 며칠째 · S4 깊이 · S5 위험 (코스피·코스닥 각각, 보유 40일) ─────
for s in ("KOSPI", "KOSDAQ"):
    r = (IDX[s] / IDX[s].shift(20) - 1) * 100
    inA = (r <= -5)
    days_in = inA.astype(int).groupby((~inA).cumsum()).cumsum()     # 칸에 들어온 지 며칠째(A 인 날만 의미)
    L += [f"## S3·S4·S5 ({s} 기준, 보유 40일)", "", "| 구분 | 날 수(사건) | 평균(%) | 중앙값 | 승률 | 하위 10% | 보유 중 최악(평균) |", "|---|---|---|---|---|---|---|"]
    def row(label, mask):
        ix = [i for i in range(N) if mask.iloc[i] and not np.isnan(EW[40].iloc[i])]
        if not ix:
            return
        v = EW[40].iloc[ix]; w = pd.Series([worst_path(i) for i in ix])
        L.append(f"| {label} | {len(ix)}({nonov(ix, 40)}) | {v.mean():+.2f} | {v.median():+.2f} | {(v > 0).mean():.0%} | {v.quantile(0.1):+.2f} | {w.mean():+.2f} |")
    row("A 전체(≤−5%)", inA)
    row("  들어온 지 1~3일째", inA & (days_in <= 3)); row("  4~10일째", inA & (days_in >= 4) & (days_in <= 10)); row("  11일째 이상", inA & (days_in >= 11))
    row("  깊이 −5~−10%", (r <= -5) & (r > -10)); row("  깊이 −10~−15%", (r <= -10) & (r > -15)); row("  깊이 < −15%", r <= -15)
    row("B 약세(−5~0)", (r > -5) & (r <= 0)); row("C 강세(0~+5)", (r > 0) & (r <= 5)); row("D 급등 뒤(>+5)", r > 5)
    L.append("")

# ───── S6 다른 신호 ─────
L += ["## S6 다른 신호와 비교 (보유 40일, 전 종목)", "", "| 지수 | 신호 | 날 수(사건) | 평균(%) | 승률 | 보유 중 최악(평균) |", "|---|---|---|---|---|---|"]
for s in ("KOSPI", "KOSDAQ"):
    ser = IDX[s]
    dd60 = (ser / ser.rolling(60).max() - 1) * 100
    sma20 = ser.rolling(20).mean(); below = ser < sma20
    below_days = below.astype(int).groupby((~below).cumsum()).cumsum()
    delta = ser.diff(); up = delta.clip(lower=0).rolling(14).mean(); dn = (-delta.clip(upper=0)).rolling(14).mean(); rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    r20 = (ser / ser.shift(20) - 1) * 100
    for label, mask in (("20일 ≤ −5%(기준)", r20 <= -5), ("60일 고점 대비 ≤ −10%", dd60 <= -10), ("60일 고점 대비 ≤ −15%", dd60 <= -15),
                        ("20일선 아래 5일째 이상", below & (below_days >= 5)), ("지수 RSI14 < 30", rsi < 30), ("지수 RSI14 > 70", rsi > 70)):
        ix = [i for i in range(N) if bool(mask.iloc[i]) and not np.isnan(EW[40].iloc[i])]
        if not ix:
            continue
        v = EW[40].iloc[ix]; w = np.mean([worst_path(i) for i in ix])
        L.append(f"| {s} | {label} | {len(ix)}({nonov(ix, 40)}) | {v.mean():+.2f} | {(v > 0).mean():.0%} | {w:+.2f} |")
L.append("")

# ───── S7 급락 뒤 어떤 종목 (코스피 기준 A, 보유 40일) ─────
L += ["## S7 급락 뒤(코스피 20일 ≤ −5%)엔 어떤 종목이 더 올랐나 (보유 40일, 종목군 동일가중)", "", "| 종목군 | 급락 뒤 평균(%) | 승률 | 그 밖의 날 평균(%) | 차이 |", "|---|---|---|---|---|"]
rK = (IDX["KOSPI"] / IDX["KOSPI"].shift(20) - 1) * 100
own20 = (close / close.shift(20) - 1) * 100
vol60 = dret.rolling(60).std() * np.sqrt(252) * 100
mcap = close * shares
def group_ret(i, kind):
    f = FWD[40].iloc[i]; ok = f.notna()
    if kind == "all":
        sel = ok
    elif kind == "fell":
        o = own20.iloc[i]; sel = ok & o.notna() & (o <= o[ok].quantile(0.2))
    elif kind == "rose":
        o = own20.iloc[i]; sel = ok & o.notna() & (o >= o[ok].quantile(0.8))
    elif kind == "quiet":
        v = vol60.iloc[i]; sel = ok & v.notna() & (v <= v[ok].quantile(0.2))
    elif kind == "wild":
        v = vol60.iloc[i]; sel = ok & v.notna() & (v >= v[ok].quantile(0.8))
    elif kind == "big":
        m = mcap.iloc[i]; sel = ok & m.notna() & (m >= m[ok].quantile(0.8))
    elif kind == "small":
        m = mcap.iloc[i]; sel = ok & m.notna() & (m <= m[ok].quantile(0.2))
    return f[sel].mean() if sel.sum() >= 30 else np.nan
ixA = [i for i in range(25, N - 41) if rK.iloc[i] <= -5]; ixO = [i for i in range(25, N - 41) if rK.iloc[i] > -5]
for kind, label in (("all", "전 종목"), ("fell", "많이 떨어진 종목(20일 하위 20%)"), ("rose", "오른 종목(20일 상위 20%)"), ("quiet", "조용한 종목(60일 변동성 하위 20%)"), ("wild", "거친 종목(변동성 상위 20%)"), ("big", "큰 회사(시총 상위 20%)"), ("small", "작은 회사(시총 하위 20%)")):
    a = pd.Series([group_ret(i, kind) for i in ixA]).dropna(); o = pd.Series([group_ret(i, kind) for i in ixO]).dropna()
    L.append(f"| {label} | {a.mean():+.2f} | {(a > 0).mean():.0%} | {o.mean():+.2f} | {a.mean() - o.mean():+.2f} |")
L.append("")

# ───── S8 빈도·지속·이동 ─────
L += ["## S8 칸의 빈도·지속·이동 (코스피 / 코스닥, 20일 수익 기준)", ""]
for s in ("KOSPI", "KOSDAQ"):
    r = (IDX[s] / IDX[s].shift(20) - 1) * 100
    lab = r.map(lambda x: np.nan if np.isnan(x) else ("A" if x <= -5 else "B" if x <= 0 else "C" if x <= 5 else "D")).dropna()
    runs = []; cur, start = None, None
    for d, v in lab.items():
        if v != cur:
            if cur is not None: runs.append((cur, start, d, (lab.index.get_loc(d) - lab.index.get_loc(start))))
            cur, start = v, d
    runs.append((cur, start, lab.index[-1], len(lab) - lab.index.get_loc(start)))
    R = pd.DataFrame(runs, columns=["k", "start", "end", "days"])
    freq = lab.value_counts(normalize=True).reindex(list("ABCD")).fillna(0)
    nxt = {k: (R.k.shift(-1)[R.k == k].value_counts(normalize=True).reindex(list("ABCD")).fillna(0)) for k in "ABCD"}
    L += [f"### {s}", "", "| 칸 | 날 비율 | 구간 수 | 평균 지속(거래일) | 다음에 A | B | C | D |", "|---|---|---|---|---|---|---|---|"]
    for k, name in zip("ABCD", ("A 급락 뒤", "B 약세", "C 강세", "D 급등 뒤")):
        g = R[R.k == k]
        L.append(f"| {name} | {freq[k]:.0%} | {len(g)} | {g.days.mean():.1f} | " + " | ".join(f"{nxt[k][j]:.0%}" for j in "ABCD") + " |")
    L.append("")

# ───── S9 단순 규칙 모의 (40일 슬롯, 비용 0.5% 왕복, 전 종목 동일가중) ─────
L += ["## S9 단순 규칙 3년 모의 — 매일 자본의 1/40 을 전 종목 동일가중에 넣고 40일 보유(비용 왕복 0.5%), 규칙은 '그날 새 슬롯을 얼마나 채우나'만 바꿈", "",
      "| 규칙(코스피 20일 수익 기준) | 총수익 | 연환산 | 최대 낙폭 | 현금 비중(평균) | 슬롯 채운 날 |", "|---|---|---|---|---|---|"]
def simulate(weight_fn):
    nav, cash, slots = 1.0, 1.0, []     # slots: [remaining_days, value]
    path = []
    for i in range(25, N):
        # 기존 슬롯 하루 수익
        g = ew_d.iloc[i] if not np.isnan(ew_d.iloc[i]) else 0.0
        for sl in slots:
            sl[1] *= (1 + g); sl[0] -= 1
        # 만기 슬롯 → 현금(매도 비용 0.25%)
        done = [sl for sl in slots if sl[0] <= 0]
        for sl in done:
            cash += sl[1] * (1 - 0.0025)
        slots = [sl for sl in slots if sl[0] > 0]
        total = cash + sum(sl[1] for sl in slots)
        # 새 슬롯(어제 신호로 오늘 종가 매수, 매수 비용 0.25%)
        w = weight_fn(i - 1)
        amt = min(cash, total / 40 * w)
        if amt > 0:
            cash -= amt; slots.append([40, amt * (1 - 0.0025)])
        path.append((dates[i], cash + sum(sl[1] for sl in slots), cash / (cash + sum(sl[1] for sl in slots)), w > 0))
    P = pd.DataFrame(path, columns=["d", "nav", "cash", "filled"]).set_index("d")
    tot = P.nav.iloc[-1] / P.nav.iloc[0] - 1; yrs = len(P) / 252
    mdd = (P.nav / P.nav.cummax() - 1).min()
    return tot * 100, ((1 + tot) ** (1 / yrs) - 1) * 100, mdd * 100, P.cash.mean() * 100, P.filled.mean() * 100
rules = {"항상 매수": lambda i: 1.0,
         "급락 뒤(≤−5%)만": lambda i: 1.0 if rK.iloc[i] <= -5 else 0.0,
         "급등 뒤(>+5%) 절반": lambda i: 0.5 if rK.iloc[i] > 5 else 1.0,
         "급등 뒤 0": lambda i: 0.0 if rK.iloc[i] > 5 else 1.0,
         "급락 뒤 2배(현금 허용 범위)": lambda i: 2.0 if rK.iloc[i] <= -5 else 1.0,
         "약세(−5~0)·급등 뒤 절반": lambda i: 0.5 if (-5 < rK.iloc[i] <= 0 or rK.iloc[i] > 5) else 1.0}
for name, fn in rules.items():
    tot, cagr, mdd, cashp, filled = simulate(fn)
    L.append(f"| {name} | {tot:+.1f}% | {cagr:+.1f}% | {mdd:+.1f}% | {cashp:.0f}% | {filled:.0f}% |")
L += ["", "주의: 규칙은 결과를 본 뒤 고른 것(사후)이고 같은 3년 자료다. 현금 비중이 큰 규칙은 '덜 잃음'과 '덜 번 것'이 섞인다. 생존편향·비용 단일 가정. 쓰려면 사전등록 + 앞으로의 자료.", ""]
(OUT / "deep_summary.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
