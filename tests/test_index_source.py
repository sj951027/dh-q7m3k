# -*- coding: utf-8 -*-
"""지수 소스 보강 회귀(2026-09-21) — 합성 입력만, 네트워크·운영 DB 미접촉.

계약:
  A. 스크리너 레짐: FDR 지수가 DB 만큼 최신이면 **종전대로 FDR**(평소 0-diff). DB 가 더 최신일 때만 DB.
  B. 레짐 계산식은 시리즈만 같으면 소스와 무관하게 같은 결과(옮기기만 했다).
  C. market_series: 증분 실행은 최근 7일을 다시 받아 임시값을 바로잡되, **소스의 마지막 행은 덮어쓰지 않는다**
     (멈춘 소스의 임시값이 KRX 정정값을 되돌리는 사고 방지 — 9/21 실제로 한 번 났다).
실행: python tests/test_index_source.py
"""
import os, sys, sqlite3, tempfile, types, io, contextlib
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO)); os.chdir(REPO)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
P = 0


def check(name, cond, info=""):
    global P
    if not cond:
        print(f"  FAIL  {name}  {info}"); sys.exit(1)
    P += 1; print(f"  ok    {name}")


import screener_fdr_v2_6 as scr

idx = pd.bdate_range("2025-01-01", periods=300)
rng = np.random.default_rng(3)
base = pd.Series(3000 + np.cumsum(rng.normal(2, 25, len(idx))), index=idx)

print("[A] 소스 선택")
f, d = base.copy(), base.copy()
s, src = scr._pick_index_series(f, d)
check("둘 다 같은 날까지 → FDR(종전 경로)", src == "fdr" and s is f)
s, src = scr._pick_index_series(f.iloc[:-3], d)
check("FDR 가 3일 뒤처짐 → DB", src == "db" and s is d)
s, src = scr._pick_index_series(f, d.iloc[:-2])
check("DB 가 뒤처짐 → FDR", src == "fdr")
check("FDR 없음 → DB", scr._pick_index_series(None, d)[1] == "db")
check("DB 없음 → FDR", scr._pick_index_series(f, None)[1] == "fdr")
check("둘 다 없음 → None", scr._pick_index_series(None, None) == (None, None))
check("빈 시리즈는 없는 것으로 취급", scr._pick_index_series(f.iloc[:0], d)[1] == "db")

print("[B] 계산식 — 종전 본문과 같은 산식")
cfg = scr.MARKET_CONFIG["kospi"]
r = scr._regime_from_close(base, cfg)
latest = float(base.iloc[-1]); sma50 = float(base.rolling(50).mean().iloc[-1]); sma200 = float(base.rolling(200).mean().iloc[-1])
check("지수·50일선·200일선·1개월·3개월·전일대비", r["kospi"] == round(latest, 2)
      and r["kospi_vs_sma50_%"] == round((latest / sma50 - 1) * 100, 1)
      and r["kospi_vs_sma200_%"] == round((latest / sma200 - 1) * 100, 1)
      and r["kospi_return_1m_%"] == round((latest / float(base.iloc[-22]) - 1) * 100, 1)
      and r["kospi_return_3m_%"] == round((latest / float(base.iloc[-63]) - 1) * 100, 1)
      and r["kospi_daily_change_%"] == round((latest / float(base.iloc[-2]) - 1) * 100, 2))
exp = ("강세" if latest > sma200 and latest > sma50 else "조정" if latest > sma200 else "반등" if latest > sma50 else "약세")
check("레짐 분류·점수", r["regime"] == exp and r["regime_kospi_score"] == cfg["regime_scores"][exp])

print("[A'] _analyze_index_regime 배선 — FDR 정지 시 DB 값으로 계산")
stale = base.iloc[:-3]
scr.fdr = types.SimpleNamespace(DataReader=lambda *a, **k: pd.DataFrame({"Close": stale}))
scr._index_close_db = lambda *a, **k: base
with contextlib.redirect_stdout(io.StringIO()) as buf:
    got = scr._analyze_index_regime(cfg)
check("DB 최신값 사용", got["kospi"] == round(float(base.iloc[-1]), 2))
check("대체 사실을 로그에 남긴다", "지수 소스: ohlcv.db market_daily" in buf.getvalue())
scr.fdr = types.SimpleNamespace(DataReader=lambda *a, **k: pd.DataFrame({"Close": base}))
with contextlib.redirect_stdout(io.StringIO()) as buf:
    got2 = scr._analyze_index_regime(cfg)
check("FDR 가 최신이면 로그 없이 종전 경로", got2 == scr._regime_from_close(base, cfg) and "지수 소스" not in buf.getvalue())
scr.fdr = types.SimpleNamespace(DataReader=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("404")))
with contextlib.redirect_stdout(io.StringIO()):
    got3 = scr._analyze_index_regime(cfg)
check("FDR 예외 → DB 로 계속", got3 is not None and got3["kospi"] == round(float(base.iloc[-1]), 2))

print("[C] market_series — 최근 7일 재확인, 소스의 마지막 행은 안 덮어씀")
tmp = Path(tempfile.mkdtemp()) / "t.db"
os.environ["OHLCV_DB"] = str(tmp)
import importlib, market_series as ms
importlib.reload(ms)
con = sqlite3.connect(tmp); con.execute(ms.DDL)
con.execute("CREATE TABLE daily_ohlcv (ticker TEXT, date TEXT)")
days = [x.strftime("%Y%m%d") for x in pd.bdate_range("2026-09-07", periods=9)]      # 9/07 … 9/17
for i, dd in enumerate(days):
    for name in ("KOSPI", "KOSDAQ", "USDKRW"):
        con.execute("INSERT INTO market_daily VALUES (?,?,?)", (name, dd, 100.0 + i))
con.execute("UPDATE market_daily SET close=555.0 WHERE series='KOSPI' AND date=?", (days[-3],))   # 과거 임시값(정정 대상)
con.execute("UPDATE market_daily SET close=777.0 WHERE series='KOSPI' AND date=?", (days[-1],))   # 마지막 날 = KRX 정정값(보존 대상)
con.execute("INSERT INTO daily_ohlcv VALUES ('000001', ?)", (days[-1],))
con.commit(); con.close()


def fake_reader(code, start):
    ix = pd.to_datetime(days[-6:], format="%Y%m%d")                                  # 소스는 days[-1] 에서 '정지'
    vals = [200.0 + i for i in range(6)]                                            # 소스 값(마지막 행 205 = 임시값)
    return pd.DataFrame({"Close": vals}, index=ix)


sys.modules["FinanceDataReader"] = types.SimpleNamespace(DataReader=fake_reader)
with contextlib.redirect_stdout(io.StringIO()):
    ms.main(); ms.main()                                                             # 두 번 돌려도 같아야 한다
con = sqlite3.connect(tmp)
g = dict(con.execute("SELECT date, close FROM market_daily WHERE series='KOSPI'").fetchall()); con.close()
check("과거 임시값(마지막 행이 아닌 날)은 소스 값으로 정정", g[days[-3]] == 203.0, str(g[days[-3]]))
check("소스의 마지막 행은 덮어쓰지 않음 — KRX 정정값 보존", g[days[-1]] == 777.0, str(g[days[-1]]))
check("재확인 창 밖의 옛 행은 그대로", g[days[0]] == 100.0)
check("행이 늘거나 줄지 않음", len(g) == len(days))
src = (REPO / "market_series.py").read_text(encoding="utf-8")
check("정정 명령은 0행·예외 시 종료코드 1", "sys.exit(1)" in src and "정정된 행 0" in src)

print("[D] validate_scores.PriceProvider — 지수만 예비 소스, 종목은 종전 경로")
import validate_scores as vs
days2 = pd.bdate_range("2026-08-03", periods=30)
full = pd.Series(np.linspace(100, 129, 30), index=days2)
stale_df = pd.DataFrame({"Close": full.iloc[:-4]})
check("순수 선택: 같은 날까지면 FDR", vs._prefer_fresher_index(full, full)[1] == "fdr")
check("순수 선택: DB 가 더 최신이면 DB", vs._prefer_fresher_index(full.iloc[:-4], full)[1] == "db")
check("순수 선택: 둘 다 없으면 None", vs._prefer_fresher_index(None, None) == (None, None))
calls = []
vs._index_close_db = lambda code, st, en: (calls.append(code) or full[(full.index >= pd.Timestamp(st)) & (full.index <= pd.Timestamp(en))])
st, en = days2[0].strftime("%Y-%m-%d"), days2[-1].strftime("%Y-%m-%d")
prov = vs.PriceProvider(cache_dir=tempfile.mkdtemp())
prov._fdr = types.SimpleNamespace(DataReader=lambda code, s0, e0: stale_df.copy())
with contextlib.redirect_stdout(io.StringIO()) as buf:
    got = prov.get_close("KS11", st, en)
check("지수: FDR 가 4일 멈춤 → DB 의 마지막 날까지 나온다", got.index[-1] == days2[-1] and float(got.iloc[-1]) == 129.0)
check("지수: 대체 사실을 로그에", "지수 소스: ohlcv.db market_daily" in buf.getvalue())
prov2 = vs.PriceProvider(cache_dir=tempfile.mkdtemp())
prov2._fdr = types.SimpleNamespace(DataReader=lambda code, s0, e0: pd.DataFrame({"Close": full}))
with contextlib.redirect_stdout(io.StringIO()) as buf:
    got2 = prov2.get_close("KQ11", st, en)
check("지수: FDR 가 최신이면 FDR 시리즈 그대로·로그 없음", got2.equals(full.astype(float)) and "지수 소스" not in buf.getvalue())
calls.clear()
prov3 = vs.PriceProvider(cache_dir=tempfile.mkdtemp())
prov3._fdr = types.SimpleNamespace(DataReader=lambda code, s0, e0: stale_df.copy())
with contextlib.redirect_stdout(io.StringIO()):
    got3 = prov3.get_close("005930", st, en)
check("종목 코드는 예비 소스를 아예 조회하지 않는다", calls == [] and got3.index[-1] == stale_df.index[-1])


def _boom(code, s0, e0):
    raise RuntimeError("404")


prov4 = vs.PriceProvider(cache_dir=tempfile.mkdtemp())
prov4._fdr = types.SimpleNamespace(DataReader=_boom)
with contextlib.redirect_stdout(io.StringIO()):
    got4 = prov4.get_close("KS11", st, en); got5 = prov4.get_close("000660", st, en)
check("FDR 예외: 지수는 DB 로 계속, 종목은 종전대로 None", got4 is not None and got4.index[-1] == days2[-1] and got5 is None)

print(f"\n전체 {P}체크 통과")
