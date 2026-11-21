# -*- coding: utf-8 -*-
"""sv_b 판정문(11/13) 추기 ③용 — 자리바꿈의 '시총 5분위 안에서만 섞는 감도' (PROMISES P18 · VERDICT_RULES §1 각주 ④). 2026-11-21.

성격: 참고값이다. 라벨('노이즈')·처분에 쓰지 않는다 — 어떤 값이 나와도 라벨은 그대로(결과 전에 적음).
기대(결과 전, 2026-11-21): sv_b 평균은 뒤섞은 분포 한가운데(30~70 백분위)에 그대로 있고, 짝 sv_b−sv_a 는 여전히 아래 꼬리(2.5 백분위 아래)일 것.
  이유 — 시장 전체로 섞었을 때 54.9 · 0.0 이었고, 시총 층을 지켜도 sv_a 의 우위(같은 창 +0.09)가 크기 때문.

어떻게(11/15 추기와 같은 틀):
  1) 판정 스크립트 `verdict_sv_b_20261113.py` 를 고치지 않고, 가격·run 을 판정 당시(20261112 까지)로 잘라 그대로 실행 → 주지표 n=19 · +0.0025 재현 확인.
  2) 시장 안 1:1 자리바꿈을 같은 씨앗으로 다시 돌려 11/15 추기 ②의 값(54.9 · 0.0 백분위)이 나오는지 확인 — 이 틀이 그때 계산과 같다는 확인.
  3) 감도: 같은 시장 × 시총 5분위 안에서만 섞기. 정의·함수는 `research/lib/verdict_util.py`(창 안 첫 유효 close×shares · 결측은 6번째 층 · 제자리 허용)
     — lv_e 2차 창·v32a 도구와 같은 함수(복사 없음). 씨앗 20261012 를 새로 시작.
읽기 전용(history.db·ohlcv.db mode=ro). 화면 출력만 — 산출은 `research/out_verdict_sv_b/addendum3_20261121.txt` 로 받아 둔다.

실행: python -X utf8 research/verdict_sv_b_addendum3_20261121.py [--n 2000]
"""
import runpy
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leaderboard as lb  # noqa: E402
from lib.verdict_util import strata_perm, cap_quintiles, first_cap  # noqa: E402

N = 2000
if "--n" in sys.argv:
    N = int(sys.argv[sys.argv.index("--n") + 1])
CUT = "20261112"
EXPECT_N, EXPECT_IC = 19, 0.0025
EXPECT_PCT = (54.9, 0.0)   # 11/15 추기 ②: sv_b · 짝 백분위(시장 안 1:1, 2,000회)

_load, _read, _argv = lb.load_ohlcv, pd.read_sql, sys.argv


def load_cut():
    close, mktmap = _load()
    return close.loc[[d for d in close.index if str(d) <= CUT]], mktmap


def read_cut(sql, con, *a, **k):
    df = _read(sql, con, *a, **k)
    if "run_id" in df.columns:
        df = df[df["run_id"].astype(str) <= CUT]
    return df


lb.load_ohlcv = load_cut; pd.read_sql = read_cut; sys.argv = [_argv[0]]   # 판정 스크립트는 --perm 0 으로(자리바꿈은 아래에서 직접)
try:
    g = runpy.run_path(str(REPO / "research" / "verdict_sv_b_20261113.py"), run_name="__main__")
finally:
    lb.load_ohlcv = _load; pd.read_sql = _read; sys.argv = _argv

base, per_anchor_ic = g["base"], g["per_anchor_ic"]
MID, PAIR, R0 = g["MID"], g["PAIR"], g["R0"]
b = base["sv_b"]; a = base["sv_a(9/14~)"]
ok = len(b) == EXPECT_N and abs(round(float(b.mean()), 4) - EXPECT_IC) < 1e-9
print("\n=== 추기 ③ 1) 재현 확인(자료를 %s 까지로 자름) ===" % CUT)
print(f"  sv_b h20: n={len(b)} 평균 {b.mean():+.4f} — 판정문 n={EXPECT_N} {EXPECT_IC:+.4f} → {'일치' if ok else '불일치'} · 분모 {g['DEN_LV']}(사전등록 {g['DEN_PRE']})")
if not ok or g["DEN_LV"] != g["DEN_PRE"]:
    sys.exit("재현 불일치 또는 분모 변화 — 감도 값을 내지 않는다")

s_e, s_b, keep_e, keep_b = g["s_e"], g["s_b"], g["keep_e"], g["keep_b"]
win_e = s_e[s_e.run_id.isin(keep_e)]; win_b = s_b[s_b.run_id.isin(keep_b)]
G = per_anchor_ic.__globals__   # 판정 스크립트의 전역 — LV 를 뒤섞은 표로 잠깐 바꿔 끼운다(그 스크립트의 ic_from 과 같은 방식)


def ic_from(sdf, mid):
    saved = G["LV"]; G["LV"] = sdf
    try:
        return per_anchor_ic(mid, R0)
    finally:
        G["LV"] = saved


real_e = float(b.mean()); real_d = float((b - a).dropna().mean())
nm = {mk: sorted(set(win_e[win_e.market == mk].ticker) | set(win_b[win_b.market == mk].ticker)) for mk in ("kospi", "kosdaq")}


def run(make_maps, n):
    pe, pdf, same = [], [], []
    for _ in range(n):
        maps = make_maps()
        same.append(np.mean([k == v for k, v in maps.items()]))
        df = pd.concat([win_e.assign(ticker=win_e.ticker.map(maps)), win_b.assign(ticker=win_b.ticker.map(maps))])
        se = ic_from(df, MID); sb = ic_from(df, PAIR)
        pe.append(se.mean()); pdf.append((se - sb).dropna().mean())
    return np.array(pe), np.array(pdf), float(np.mean(same))


def show(tag, pe, pdf, same):
    pc_e = 100 * (pe < real_e).mean(); pc_d = 100 * (pdf < real_d).mean()
    print(f"  {tag}: sv_b 뒤섞은 2.5/50/97.5 = {np.percentile(pe, 2.5):+.4f}/{np.percentile(pe, 50):+.4f}/{np.percentile(pe, 97.5):+.4f} · 실제 {real_e:+.4f} 는 {pc_e:.1f} 백분위(실제보다 큰 뒤섞음 {int((pe > real_e).sum())}번)")
    print(f"  {' ' * len(tag)}  짝 뒤섞은 2.5/50/97.5 = {np.percentile(pdf, 2.5):+.4f}/{np.percentile(pdf, 50):+.4f}/{np.percentile(pdf, 97.5):+.4f} · 실제 {real_d:+.4f} 는 {pc_d:.1f} 백분위(실제보다 작은 뒤섞음 {int((pdf < real_d).sum())}번) · 제자리 {100 * same:.1f}%")
    return pc_e, pc_d


# 2) 시장 안 1:1 — 11/15 추기 ②와 같은 씨앗·같은 순서(이름 정렬 → rng.permutation)
t0 = time.time()
rng = np.random.default_rng(20261012)


def plain():
    maps = {}
    for mk in ("kospi", "kosdaq"):
        maps.update(dict(zip(nm[mk], rng.permutation(nm[mk]))))
    return maps


print(f"\n=== 추기 ③ 2) 시장 안 1:1 자리바꿈 {N}회 다시(11/15 추기 ② 재현 확인) ===")
pc = show("시장 안", *run(plain, N))
if N == 2000:
    same_as_1115 = (round(pc[0], 1), round(pc[1], 1)) == EXPECT_PCT
    print(f"  11/15 추기 ②(54.9 · 0.0 백분위)와 {'일치' if same_as_1115 else '불일치 — 아래 감도 값은 틀이 다를 수 있으니 쓰지 않는다'}")
print(f"  ({time.time() - t0:.0f}초)")

# 3) 감도 — 시장 × 시총 5분위(창 안 첫 유효 close×shares · 결측 6번째 층)
dates, didx, ocon = g["dates"], g["didx"], g["ocon"]
d_first = str(dates[lb.anchor(min(keep_e), didx)])
sh = _read("SELECT date, ticker, close, shares FROM daily_ohlcv WHERE date >= ? AND date <= ?", ocon, params=(d_first, str(dates[-1])))
sh["ticker"] = sh.ticker.astype(str).str.zfill(6); cap = first_cap(sh, d_first)
st5 = {mk: cap_quintiles(nm[mk], cap).reindex(nm[mk]).to_numpy() for mk in nm}
rng = np.random.default_rng(20261012)


def strat():
    maps = {}
    for mk in nm:
        maps.update(strata_perm(nm[mk], st5[mk], rng))
    return maps


t0 = time.time()
print(f"\n=== 추기 ③ 3) 감도: 시총 5분위 안에서만 섞기 {N}회 ===")
print(f"  창 첫 앵커 날짜 {d_first} ~ {dates[-1]} · 층별 종목 수(1~5분위, 6=시총 결측) 코스피 {np.bincount(st5['kospi'], minlength=7)[1:].tolist()} · 코스닥 {np.bincount(st5['kosdaq'], minlength=7)[1:].tolist()}")
show("5분위 안", *run(strat, N))
print(f"  ({time.time() - t0:.0f}초)")
print("  읽는 법: 참고값 — 라벨('노이즈')·처분에 쓰지 않는다. 가격·run 만 판정 당시로 자른 것이라 당시 DB 전체의 복원은 아니다(주식 수는 지금 DB 의 값).")
