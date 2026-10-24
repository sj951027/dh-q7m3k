# -*- coding: utf-8 -*-
"""v32a 관측 페이지(build_v32a_page) 규칙 회귀 테스트 (합성 — DB 불필요)

고정하는 규칙 (PREREGISTER_v32a.md §2, 2026-10-24 Codex 커밋 점검 F1~F3 반영):
  1. 바구니 = 점수 > −999 인 행 중 상위 10 — −999 는 고르지 않고, 모자라면 있는 만큼(F2).
  2. D20 표는 행이 0 이어도 run_id·done·ok·D20 열을 가진다 — 첫 적재 직후(20일 미완결)·전부 게이트에서도 안 깨짐(F1).
  3. 두 시장 모두 산출될 때만 D20, 한 시장만 있으면 'D 산출 불가'(F3).
  4. 진입가 없는 종목은 빼고 체결분만 평균, 진입가는 ffill 하지 않음(F3).
  5. 같은 바구니면 D20 = 0.
  6. 페이지 main() 은 stage3 가 비어도·D 산출 불가만 있어도 끝까지 그린다(F1).
실행: python tests/test_v32a_page_rules.py
"""
import sys, tempfile
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_v32a_page as pg

P = 0
def check(n, c, info=""):
    global P
    assert c, f"FAIL: {n} {info}"
    P += 1
    print(f"  ok  {n}" + (f"  [{info}]" if info else ""))

REG = "20261026"
DATES = [d.strftime("%Y%m%d") for d in pd.bdate_range("2026-10-26", periods=30)]
DIDX = {d: i for i, d in enumerate(DATES)}
TK = ["K1", "K2", "K3", "Q1", "Q2", "Q3"]          # K* 코스피 · Q* 코스닥


def make_close(n_days=len(DATES), exit_px=None):
    c = pd.DataFrame(100.0, index=DATES[:n_days], columns=TK)
    if exit_px and n_days > 21:
        for k, v in exit_px.items():
            c.loc[DATES[21]:, k] = v                     # t=0 앵커 → 진입 t+1, 청산 t+21
    return c


def scores(rows):
    return pd.DataFrame(rows, columns=["run_id", "market", "ticker", "model_id", "score"])


print("[1] 바구니 선택")
df = pd.DataFrame({"ticker": ["a", "b", "c", "d", "e"], "final_score_v3": [5, -999, 4, -999, 3]})
t = pg.top(df)
check("−999 는 고르지 않음", (t["final_score_v3"] > -999).all() and len(t) == 3, str(list(t["ticker"])))
check("점수 순·동점 종목코드 순", list(pg.top(pd.DataFrame({"ticker": ["z", "y", "x"], "final_score_v3": [1, 1, 2]}))["ticker"]) == ["x", "y", "z"])

print("[2] 빈 표·미완결")
S1 = scores([(REG, m, k, mid, 1.0) for mid in ("v32a", "v30") for m, ks in (("kospi", TK[:3]), ("kosdaq", TK[3:])) for k in ks])
h = pg.d20_rows(S1, make_close(n_days=5), {d: i for i, d in enumerate(DATES[:5])}, set(), REG)
check("미완결 1행 · 열 유지", list(h.columns) == pg.COLS and len(h) == 1 and not h["done"].iloc[0] and np.isnan(h["D20"].iloc[0]))
h = pg.d20_rows(S1, make_close(), DIDX, {REG}, REG)
check("전부 게이트 → 0행 · 열 유지", list(h.columns) == pg.COLS and len(h) == 0)
h = pg.d20_rows(scores([]), make_close(), DIDX, set(), REG)
check("점수 0행 → 0행 · 열 유지", list(h.columns) == pg.COLS and len(h) == 0)

print("[3] 같은 바구니 = 0 · 두 시장 평균")
h = pg.d20_rows(S1, make_close(exit_px={"K1": 110, "Q1": 90}), DIDX, set(), REG)
check("같은 바구니면 D20 = 0", h["ok"].iloc[0] and abs(h["D20"].iloc[0]) < 1e-12, str(h.to_dict("records")))
S2 = scores([(REG, "kospi", "K1", "v32a", 3.0), (REG, "kospi", "K2", "v30", 3.0), (REG, "kosdaq", "Q1", "v32a", 3.0), (REG, "kosdaq", "Q2", "v30", 3.0)])
h = pg.d20_rows(S2, make_close(exit_px={"K1": 120, "Q2": 110}), DIDX, set(), REG)
check("D20 = ((+20−0) + (0−10))/2 = +5", h["ok"].iloc[0] and abs(h["D20"].iloc[0] - 5.0) < 1e-9, str(h["D20"].iloc[0]))

print("[4] 한 시장만 · 진입가 결측 · −999")
S3 = S2[S2.market == "kospi"]
h = pg.d20_rows(S3, make_close(exit_px={"K1": 120}), DIDX, set(), REG)
check("한 시장만 → D 산출 불가", h["done"].iloc[0] and not h["ok"].iloc[0] and np.isnan(h["D20"].iloc[0]))
S4 = scores([(REG, "kospi", "K1", "v32a", 3.0), (REG, "kospi", "K3", "v32a", 2.0), (REG, "kospi", "K2", "v30", 3.0),
             (REG, "kosdaq", "Q1", "v32a", 3.0), (REG, "kosdaq", "Q1", "v30", 3.0)])
c = make_close(exit_px={"K1": 150, "K3": 110}); c.loc[DATES[1], "K1"] = np.nan          # K1 진입가 없음 → 빠지고 K3 만
h = pg.d20_rows(S4, c, DIDX, set(), REG)
check("진입가 결측 종목 제외(ffill 안 함) → 코스피 +10, 코스닥 0 → D20 +5", h["ok"].iloc[0] and abs(h["D20"].iloc[0] - 5.0) < 1e-9, str(h["D20"].iloc[0]))
S5 = scores([(REG, "kospi", "K1", "v32a", -999.0), (REG, "kospi", "K3", "v32a", 1.0), (REG, "kospi", "K3", "v30", 1.0),
             (REG, "kosdaq", "Q1", "v32a", 1.0), (REG, "kosdaq", "Q1", "v30", 1.0)])
h = pg.d20_rows(S5, make_close(exit_px={"K1": 300}), DIDX, set(), REG)
check("−999 종목(K1 +200%)은 바구니에 안 들어감 → D20 0", h["ok"].iloc[0] and abs(h["D20"].iloc[0]) < 1e-12, str(h["D20"].iloc[0]))
c = make_close(); c.loc[DATES[1], ["K1", "K2"]] = np.nan
h = pg.d20_rows(S2, c, DIDX, set(), REG)
check("한 바구니 체결 0 → 그 앵커 D 산출 불가", not h["ok"].iloc[0])

print("[5] 페이지 main 이 빈 경우에도 끝까지 그림")
orig = (pg.v3.load_runs, pg.d20_history, pg.OUT)
with tempfile.TemporaryDirectory() as td:
    try:
        pg.v3.load_runs = lambda *a, **k: pd.DataFrame(columns=["run_id", "market", "ticker"])
        pg.OUT = str(Path(td) / "a.html")
        pg.d20_history = lambda today: (pd.DataFrame(columns=pg.COLS), None)
        pg.main(); check("stage3 없음 + 앵커 0행", Path(pg.OUT).exists() and "stage3 후보 자료가 없습니다" in Path(pg.OUT).read_text(encoding="utf-8"))
        pg.OUT = str(Path(td) / "b.html")
        pg.d20_history = lambda today: (pd.DataFrame([dict(run_id=REG, done=True, ok=False, D20=np.nan)], columns=pg.COLS), None)
        pg.main(); check("D 산출 불가만 있음", "D 산출 불가 1" in Path(pg.OUT).read_text(encoding="utf-8"))
        pg.OUT = str(Path(td) / "c.html")
        pg.d20_history = lambda today: (pd.DataFrame([dict(run_id=REG, done=False, ok=False, D20=np.nan)], columns=pg.COLS), None)
        pg.main(); check("20일 미완결만 있음(첫 적재 직후)", "진행 중 1" in Path(pg.OUT).read_text(encoding="utf-8"))
    finally:
        pg.v3.load_runs, pg.d20_history, pg.OUT = orig

print(f"\n✅ v32a 페이지 규칙 {P}개 체크 통과")
