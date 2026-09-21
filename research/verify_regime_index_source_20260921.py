# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션 작성 — research/ 에서 실행. 읽기 전용(ohlcv.db mode=ro · FDR 지수 조회). 파일·DB 쓰기 없음.
"""verify_regime_index_source_20260921.py — 레짐 지수 소스 보강의 0-diff 검증

사용: python research/verify_regime_index_source_20260921.py <패치본 screener 경로>
  ① 정상 모드(FDR 가 DB 만큼 최신): 원본 vs 패치본의 레짐 dict 가 과거 as-of 날짜 전부에서 동일한가
  ② 예비 모드(FDR 가 3거래일 뒤처짐 → DB 사용): '원본이 FDR 로 제대로 받았다면 냈을 값'과 동일한가
  ③ 실제로 바뀌는 날: 9/18~9/21 (FDR 가 9/17 장중 값에서 정지) — 종전 값 vs 정정 값
as-of 는 시리즈를 그 날짜까지 잘라 DataReader·DB 조회를 흉내 낸다(네트워크는 처음 1회만).
"""
import importlib.util, sys, io, contextlib
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import os; os.chdir(REPO)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


orig = load(REPO / "screener_fdr_v2_6.py", "scr_orig")
new = load(sys.argv[1], "scr_new")
import FinanceDataReader as fdr

out = []
_REAL_DB = new._index_close_db            # 아래에서 모듈 함수를 갈아끼우므로 원본을 잡아 둔다
for mkt, cfg in orig.MARKET_CONFIG.items():
    code = cfg["index_code"]
    F = fdr.DataReader(code, "2025-01-01")                       # FDR 원본(지금은 9/17 에서 정지)
    D = _REAL_DB(code, "2025-01-01")                             # 우리 DB(9/17 정정 · 9/18~ KRX 예비)
    assert D is not None and len(D) > 300, "DB 지수 없음"
    days = [d for d in F.index if pd.Timestamp("2026-06-01") <= d <= pd.Timestamp("2026-09-16")]
    # 과거 구간에서 두 소스 값이 같은가(예비 모드 동일성의 전제)
    common = F["Close"].reindex(D.index).dropna()
    mism = int((common.loc[:"2026-09-16"].round(2) != D.reindex(common.index).loc[:"2026-09-16"].round(2)).sum())
    _bad = common.loc[:"2026-09-16"].round(2) != D.reindex(common.index).loc[:"2026-09-16"].round(2)
    for dd in _bad[_bad].index:
        out.append(f"    값이 다른 날 {dd.date()}: FDR {float(F['Close'].loc[dd]):.2f} / DB {float(D.loc[dd]):.2f}")
    out.append(f"[{mkt}] FDR 마지막 {F.index[-1].date()} · DB 마지막 {D.index[-1].date()} · ~9/16 값 불일치 {mism}일 / {len(common.loc[:'2026-09-16'])}일")

    def run(mod, f_asof, d_asof=None):
        f_cut = F.loc[:f_asof]
        mod.fdr = type("X", (), {"DataReader": staticmethod(lambda *a, **k: f_cut)})
        if hasattr(mod, "_index_close_db"):
            mod._index_close_db = (lambda *a, **k: D.loc[:d_asof]) if d_asof is not None else (lambda *a, **k: None)
        with contextlib.redirect_stdout(io.StringIO()):
            return mod._analyze_index_regime(cfg)

    n1 = d1 = n2 = d2 = 0
    for i, d in enumerate(days):
        a = run(orig, d)
        b = run(new, d, d)                      # ① 정상: FDR·DB 둘 다 그날까지
        n1 += 1; d1 += (a != b)
        if i >= 3:
            c = run(new, days[i - 3], d)        # ② 예비: FDR 는 3거래일 전에서 멈춤, DB 는 그날까지
            n2 += 1; d2 += (a != c)
    out.append(f"  ① 정상 모드: {n1}일 비교 · 다른 날 {d1}")
    out.append(f"  ② 예비 모드(FDR 3거래일 정지 가정): {n2}일 비교 · 원본(FDR 정상 시)과 다른 날 {d2}")
    # ③ 실제 정지 구간
    for d in [x for x in D.index if x >= pd.Timestamp("2026-09-17")]:
        a = run(orig, d)                        # 원본: FDR 가 9/17 에서 멈춰 그 값 고정
        b = run(new, d, d)
        keys = ("regime", "regime_kospi_score", "kospi", "kospi_vs_sma50_%", "kospi_vs_sma200_%", "kospi_return_1m_%")
        out.append(f"  ③ {d.date()}  종전 {tuple(a[k] for k in keys)}")
        out.append(f"               정정 {tuple(b[k] for k in keys)}")
sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(out))
