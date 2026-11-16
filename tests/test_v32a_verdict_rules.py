# -*- coding: utf-8 -*-
"""v32a 판정 도구(research/verdict_v32a_20261116.py) 규칙 회귀 테스트 (합성 — DB 불필요, 파일 안 씀)

고정하는 규칙 (PREREGISTER_v32a.md §2·§3·§4-1, VERDICT_NOTE_20261011_power 각주 ④):
  1. 도구의 D 표(numpy 길)는 공개 페이지 코드 build_v32a_page.d20_rows(pandas 길)와 같은 값을 낸다 — 바구니·체결·두 시장 규칙이 한 벌.
  2. 진입가 없음 → 그 종목 현금(평균은 체결분만) · 청산가 없음 → 마지막 가격 · 창이 안 닫힌 앵커는 값 없음.
  3. 한 시장이라도 못 내면 'D 산출 불가'(ok=False) — 표본에서 빠진다.
  4. 체결 한도: 바구니는 그대로 두고 양쪽에서 살 수 있는 종목만 남긴다. 한쪽 바구니가 비면 그 앵커는 산출 불가.
  5. 해석표 6칸 + 나머지(위에서부터 첫 번째): 유의 / 기움(미달 항목) / 노이즈 / 역작동(유의 아님) / 역작동(유의) / 판정불가 / (나머지 → 노이즈).
     유효 앵커 40 미만이면 라벨이 아니라 '판정 전'.
  6. 주 = 월~일 달력 주 · 주가 1개뿐이면 주블록 산출 불가 · 주별 양(+) 비율.
  7. 자리바꿈: 같은 층 안에서만 1:1 · 시총 결측은 6번째 층 · 제자리 이름표면 값이 그대로.
실행: python tests/test_v32a_verdict_rules.py
"""
import importlib.util, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build_v32a_page as pg
spec = importlib.util.spec_from_file_location("verdict_v32a", ROOT / "research" / "verdict_v32a_20261116.py")
vt = importlib.util.module_from_spec(spec); spec.loader.exec_module(vt)

P = 0
def check(n, c, info=""):
    global P
    assert c, f"FAIL: {n} {info}"
    P += 1
    print(f"  ok  {n}" + (f"  [{info}]" if info else ""))

REG = "20261026"
DATES = [d.strftime("%Y%m%d") for d in pd.bdate_range("2026-10-26", periods=40)]     # 10/26 = 월요일
DIDX = {d: i for i, d in enumerate(DATES)}
KS = [f"K{i:02d}" for i in range(1, 15)]; QS = [f"Q{i:02d}" for i in range(1, 15)]


def make_close():
    """종목마다 하루 성장률이 다르다(뒤 번호일수록 더 오름)."""
    t = np.arange(len(DATES))
    c = pd.DataFrame({k: 100 * np.exp(0.0005 * (i + 1) * t) for i, k in enumerate(KS + QS)}, index=DATES)
    return c


def make_scores(n_runs=25, drop=None):
    """v30 = 앞 번호가 점수 높음(K01…). v32a = v30 과 같되 K01~K03·Q01~Q03 은 −999(유동성 탈락) → 바구니가 뒤 번호로 밀린다.
    drop = (run, market, model) 이면 그 칸을 전부 −999 로(바구니 0개)."""
    rows = []
    for rid in DATES[:n_runs]:
        for mkt, names in (("kospi", KS), ("kosdaq", QS)):
            for i, k in enumerate(names):
                for mid in ("v30", "v32a"):
                    s = 100.0 - i
                    if mid == "v32a" and i < 3:
                        s = -999.0
                    if drop == (rid, mkt, mid):
                        s = -999.0
                    rows.append((rid, mkt, k, mid, s))
    return pd.DataFrame(rows, columns=["run_id", "market", "ticker", "model_id", "score"])


def tool_table(S, close, h=20, **kw):
    import leaderboard as lb
    keep = lb.dedupe_by_anchor(S[S.model_id == "v32a"], DIDX, set(), reg=REG)
    rids = sorted(keep); ts = [DIDX[r] for r in rids]
    R, done = vt.ret_matrix(close, ts, h)
    bk = vt.build_baskets(S, rids, ("v32a", "v30"), pg.top)
    col = {t: j for j, t in enumerate(close.columns)}
    return vt.d_table(R, done, rids, bk, col, **kw), bk, rids

# ── 1~3. D 표 ────────────────────────────────────────────────────────────
print("D 표")
C = make_close(); S = make_scores()
T, bk, rids = tool_table(S, C)
Pg = pg.d20_rows(S, C, DIDX, set(), REG)
check("앵커 수·완결·산출 여부가 페이지 코드와 같다", list(T.run_id) == list(Pg.run_id) and (T.done.values == Pg.done.values).all() and (T.ok.values == Pg.ok.values).all())
check("D20 값이 페이지 코드와 같다", np.allclose(T.D.dropna().values, Pg.D20.dropna().values, atol=1e-12), f"완결 {int(T.ok.sum())}개")
check("v32a 바구니 = −999 를 뺀 상위 10(K04~K13)", bk[(rids[0], "kospi", "v32a")] == KS[3:13] and bk[(rids[0], "kospi", "v30")] == KS[:10])
check("뒤 번호가 더 오르게 만들었으니 D20 > 0", (T.D.dropna() > 0).all())
check("창이 안 닫힌 앵커(t+21 이 달력 밖 — 40일 달력이면 t ≥ 19)는 done=False·값 없음",
      int(T.done.sum()) == 19 and len(rids) == 25 and T[~T.done].D.isna().all() and T[T.done].ok.all(), f"완결 {int(T.done.sum())}/{len(rids)}")

C2 = make_close(); C2.loc[DATES[1], "K04"] = np.nan            # 앵커 0 의 진입일 가격 없음 → K04 는 현금
T2, _, _ = tool_table(S, C2); Pg2 = pg.d20_rows(S, C2, DIDX, set(), REG)
check("진입가 없는 종목은 빼고 평균(페이지 코드와 같음)", np.allclose(T2.D.dropna().values, Pg2.D20.dropna().values, atol=1e-12) and T2.D[0] != T.D[0])
C3 = make_close(); C3.loc[DATES[21]:, "K13"] = np.nan          # 앵커 0 의 청산일부터 가격 없음 → 마지막 가격으로 청산
T3, _, _ = tool_table(S, C3); Pg3 = pg.d20_rows(S, C3, DIDX, set(), REG)
check("청산가 없으면 마지막 가격(페이지 코드와 같음)", np.allclose(T3.D.dropna().values, Pg3.D20.dropna().values, atol=1e-12) and np.isfinite(T3.D[0]))
Sd = make_scores(drop=(DATES[0], "kosdaq", "v32a"))
Td, _, _ = tool_table(Sd, C); Pgd = pg.d20_rows(Sd, C, DIDX, set(), REG)
check("한 시장의 바구니가 비면 그 앵커는 D 산출 불가", (not Td.ok[0]) and Td.done[0] and np.isnan(Td.D[0]) and np.isfinite(Td.D_kospi[0]) and (Td.ok.values == Pgd.ok.values).all())

# ── 4. 체결 한도 ─────────────────────────────────────────────────────────
print("체결 한도")
allow_all = {(r, m): set(KS + QS) for r in rids for m in ("kospi", "kosdaq")}
Ta, _, _ = tool_table(S, C, allow=allow_all)
check("전부 살 수 있으면 값이 그대로", np.allclose(Ta.D.dropna().values, T.D.dropna().values))
allow_some = {(r, m): set(KS[:8] + QS[:8]) for r in rids for m in ("kospi", "kosdaq")}     # v30 은 01~08, v32a 는 04~08 만 남는다
Ts, _, _ = tool_table(S, C, allow=allow_some)
g = lambda names: float(np.mean([(np.exp(0.0005 * ((KS + QS).index(k) + 1) * 20) - 1) * 100 for k in names]))
want = np.mean([g(KS[3:8]) - g(KS[:8]), g(QS[3:8]) - g(QS[:8])])
check("통과 종목만 남긴 값 = 손계산", abs(Ts.D[0] - want) < 1e-9, f"{Ts.D[0]:+.4f}")
allow_none = {(r, m): set(KS[:3] + QS[:3]) for r in rids for m in ("kospi", "kosdaq")}     # v32a 바구니에서 살 수 있는 것이 없다
Tn, _, _ = tool_table(S, C, allow=allow_none)
check("한쪽 바구니가 비면 산출 불가", not Tn.ok.any() and Tn.done.any())

# ── 5. 해석표 ────────────────────────────────────────────────────────────
print("해석표")
def s(lo, hi, wpos=0.8, b=None, wb="same", n=30):
    return dict(n=n, mean=(lo + hi) / 2, iid=(lo, hi), bonf={8: b or (lo, hi)}, wb=((lo, hi, 6) if wb == "same" else wb), wpos=wpos, nweeks=6)
D10P, D10N = s(0.2, 1.0), s(-0.2, 1.0)
lab = lambda *a: vt.interpret(*a)[0]
check("유효 앵커 39 → 판정 전(라벨 아님)", lab(39, 19, s(0.5, 2.0), D10P, 8) == "판정 전")
check("40 인데 완결 0 → 판정불가", lab(40, 0, dict(n=0), dict(n=0), 8) == "판정불가")
check("완결은 있는데 D 산출 0 → 판정불가", lab(40, 20, dict(n=0), dict(n=0), 8) == "판정불가")
check("다섯 조건 전부 → 유의", lab(40, 20, s(0.5, 2.0), D10P, 8) == "유의")
check("주별 59% → 기움", vt.interpret(40, 20, s(0.5, 2.0, wpos=0.59), D10P, 8) == ("기움", "미달: 주별 양 < 60%"))
check("주별 정확히 60% → 유의", lab(40, 20, s(0.5, 2.0, wpos=0.60), D10P, 8) == "유의")
check("보정 하단 ≤ 0 → 기움", lab(40, 20, s(0.5, 2.0, b=(-0.1, 2.4)), D10P, 8) == "기움")
check("D10 하단 ≤ 0 → 기움", lab(40, 20, s(0.5, 2.0), D10N, 8) == "기움")
check("D10 표본 없음 → 기움", lab(40, 20, s(0.5, 2.0), dict(n=0), 8) == "기움")
check("주블록 하단 ≤ 0 → 기움", lab(40, 20, s(0.5, 2.0, wb=(-0.1, 2.2, 6)), D10P, 8) == "기움")
check("주블록 산출 불가 → 기움", lab(40, 20, s(0.5, 2.0, wb=None), D10P, 8) == "기움")
check("구간이 0 을 걸침(평균 +) → 노이즈", lab(40, 20, s(-0.1, 2.0), D10P, 8) == "노이즈")
check("구간이 0 을 걸침(평균 −) → 노이즈", lab(40, 20, s(-2.0, 0.1), D10P, 8) == "노이즈")
check("하단이 정확히 0 → 노이즈(0 은 '위'가 아님)", lab(40, 20, s(0.0, 2.0), D10P, 8) == "노이즈")
check("iid·보정·주블록 상단 모두 < 0 → 역작동(유의)", lab(40, 20, s(-2.0, -0.5), D10P, 8) == "역작동(유의)")
check("iid 상단 < 0 · 보정이 0 걸침 → 역작동(유의 아님)", lab(40, 20, s(-2.0, -0.5, b=(-2.4, 0.1)), D10P, 8) == "역작동(유의 아님)")
check("iid 상단 < 0 · 주블록이 0 걸침 → 역작동(유의 아님)", lab(40, 20, s(-2.0, -0.5, wb=(-2.4, 0.1, 6)), D10P, 8) == "역작동(유의 아님)")
check("iid 상단 < 0 · 주블록 산출 불가 → (나머지) 노이즈", lab(40, 20, s(-2.0, -0.5, wb=None), D10P, 8) == "노이즈")
check("iid 상단 < 0 · 주블록 전부 양수 → (나머지) 노이즈", lab(40, 20, s(-2.0, -0.5, wb=(0.1, 0.5, 6)), D10P, 8) == "노이즈")
labs = {vt.interpret(40, 20, x, D10P, 8)[0] for x in (s(0.5, 2), s(0.5, 2, wpos=0.1), s(-1, 1), s(-2, -0.5), s(-2, -0.5, b=(-3, 0.1)))} | {lab(40, 0, dict(n=0), dict(n=0), 8)}
check("사전등록 §3 의 6칸이 전부 나온다", labs == {"유의", "기움", "노이즈", "역작동(유의 아님)", "역작동(유의)", "판정불가"})

# ── 6. 주 ────────────────────────────────────────────────────────────────
print("주")
check("월~일이 한 주(월요일 이름표)", vt.week_of("20261026") == vt.week_of("20261101") == "20261026" and vt.week_of("20261102") == "20261102")
check("주 1개 → 주블록 산출 불가", vt.week_block_ci([1.0, 2.0, 3.0], ["a", "a", "a"]) is None)
wb = vt.week_block_ci([1.0, 1.0, 3.0, 3.0], ["a", "a", "b", "b"])
check("주 2개 → 구간이 두 주 평균 사이", wb is not None and wb[2] == 2 and 1.0 <= wb[0] <= wb[1] <= 3.0)
check("주별 양(+) 비율", vt.weekly_pos([1.0, -3.0, 2.0, 2.0], ["a", "a", "b", "b"]) == (0.5, 2))
fs = vt.fast_summary([1.0, -3.0, 2.0, 2.0], ["a", "a", "b", "b"], 8)
check("빠른 판(자리바꿈용)도 같은 평균·주별 비율", fs["mean"] == 0.5 and fs["wpos"] == 0.5 and fs["nweeks"] == 2 and fs["wb"][2] == 2)
check("겹치지 않는 앵커: 20거래일 간격", vt.nonoverlap(list(range(0, 45)), 20) == [0, 20, 40])

# ── 7. 자리바꿈 ──────────────────────────────────────────────────────────
print("자리바꿈")
rng = np.random.default_rng(1)
names = KS + QS; strata = [0] * len(KS) + [1] * len(QS)
mp = vt.strata_perm(names, strata, rng)
check("1:1(빠지거나 겹치는 이름표 없음)", sorted(mp) == sorted(names) and sorted(mp.values()) == sorted(names))
check("같은 층 안에서만 섞인다", all((k in KS) == (v in KS) for k, v in mp.items()))
q = vt.cap_quintiles(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "Z"], {x: i + 1.0 for i, x in enumerate("ABCDEFGHIJ")})
check("시총 5분위(각 2개) · 결측은 6번째 층", q["Z"] == 6 and sorted(q.drop("Z").value_counts().tolist()) == [2] * 5 and q["A"] == 1 and q["J"] == 5)
Ti, _, _ = tool_table(S, C, remap={k: k for k in names})
check("제자리 이름표 → 값 그대로", np.allclose(Ti.D.dropna().values, T.D.dropna().values))
rev = dict(zip(KS, KS[::-1])) | dict(zip(QS, QS[::-1]))
Tr, _, _ = tool_table(S, C, remap=rev)
check("이름표를 뒤집으면 부호가 뒤집힌다(뒤 번호가 오르는 자료)", (Tr.D.dropna() < 0).all())

print(f"\n✅ test_v32a_verdict_rules: {P} 통과")
