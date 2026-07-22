#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wu_score.py — 전체종목(whole-universe) 트랙 관측 적재 (wu 1단계)

설계 근거: RESEARCH_wholeuniverse_20260703.md / 골대: PREREGISTER_wu.md
- 유니버스: ohlcv 전체 상장 + 가드(rv21>=0.003, flat63<=0.5, 직전21일 |일수익|<=0.30,
  amt20>=5억, is_suspended=0, 당일 종가 존재). 과매도 게이트 없음(v3/lowvol과 모집단 자체가 다름).
- 모델(spec 동결): wu_a = lv63+nh252+mom12+big / wu_b = nh252+mom12
  순위합(cross-sectional pct rank, 전체 유니버스 단일 순위): 핵심팩터(첫번째) 실측필수(NaN=제외),
  보조 NaN=0.5 중립 — lowvol_score.score_run 규칙 상속.
- [2026-07-14 추가] le_a = dlow52+obv63(↓)+amt20f / sv_a = svr5 단독.
  근거: RESEARCH_tail_anatomy_20260714.md(저점탈출 lift 3.06)·RESEARCH_winners_20260714.md
  (svr5 국면독립 IC) + 익일시가 진입 재계산(저점탈출 +0.92%/5d 생존). 골대: PREREGISTER_le_sv.md.
  둘 다 발견은 post-hoc → REG_DATE 20260715부터 forward-only OOS만 판정에 사용.
  sv_a 주의: 배치 순서상 wu_score 는 kis_flows 이전 실행 → 당일 short_flows 미적재 가능.
  svr5 는 rolling(5, min 3) 평균이라 자동으로 '직전 적재분'을 쓴다(스펙의 일부, 동결).
- [2026-07-22 추가] qs_a = lv63+nh252+amt20l(↓) — '조용한 강자'(저변동+52주고가근접+저거래대금).
  근거: factor_scan(748거래일 전 구간, 2023-06~2026-07) — lv h20 IC −0.12, nh +0.05, 저거래대금 −0.05,
  결합 +0.107 CI[+0.040,+0.147], 3폴드 일관. 골대: PREREGISTER_qs.md.
  발견은 전부 in-sample → 첫 적재일(REG_DATE)부터 forward 데이터만 §11 판정에 사용.
  amt20l 은 amt20f 와 동일 프레임(mean(close·vol,20)/1e8)의 방향 반전(작을수록 상위) — 신규 계산 없음.
- 가중치 0 관측: 계산·저장만. 추천/표시/텔레그램 사용 안 함(§11 판정 전).
- 불변: v3/large/lowvol 테이블·표시 0-diff — 이 스크립트는 history.db에 wu_scores만 쓴다.
  build_wu_filter.py 는 MODEL="wu_a" 하드코딩이라 le_a/sv_a/qs_a 는 어떤 표시에도 안 나감.
- PIT: 날짜 t 점수는 t 이하 데이터만 사용(룩백 273거래일 미달 날짜는 스킵).
- 증분(OOS 청결 규칙):
    * 최초 실행(빈 테이블) = ohlcv '최신 1일'만 적재 → 그 날짜가 등록일(OOS 시작).
    * 이후 = 등록일 이후의 미적재 날짜 자동 보충(갭 포함; 원천이 raw 가격이라 재계산 PIT-안전).
    * 등록일 '이전' 백필은 발견기간(in-sample) 오염 → 기본 금지, --backfill-from 명시 시만(경고 출력).
    * 신규 모델(le_a/sv_a/qs_a)은 기존 run_id 에 소급 적재하지 않는다 — 다음 신규 run부터 자연 시작.
- 네트워크 0: ohlcv.db(읽기)·history.db(wu_scores 쓰기)만. Claude 오프라인 검증 가능.

사용:
    python wu_score.py                  # 증분(권장, 파이프라인 비치명 단계)
    python wu_score.py --date 20260702  # 특정일 보충(등록일 이전은 거부)
    python wu_score.py --backfill-from 20240715   # [연구용] 발견기간 백필 — 판정에 사용 금지
"""
import argparse, hashlib, json, os, sqlite3, sys
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("WU_HISTORY_DB", "history.db")
OHLCV_DB = os.environ.get("OHLCV_DB", os.path.join(HERE, "..", "dh-q7m3k-data", "ohlcv.db"))
KST = timezone(timedelta(hours=9))

# ---- 동결 파라미터 (PREREGISTER_wu.md와 1:1 — 변경 시 새 model_id) ----
VOL_FLOOR = 0.003        # rv21 하한(가짜 저변동=거래정지 컷)
MAX_FLAT = 0.5           # 63일 무변화일 비율 상한
MAX_JUMP = 0.30          # 직전 21일 |일수익| 상한(액면병합/유증 컷)
LIQ_FLOOR = 5.0          # amt20 하한(억) — whole_score.py 상속
LOOKBACK_MIN = 273       # mom12 = shift(21)/shift(252) 필요 최소 거래일
LOAD_PAD = 290           # 창 로딩 여유

# 팩터: name -> (ascending True=큰값이 높은 백분위, 정의문자열[spec_hash 고정용])
FACTORS = {
    "lv63":  (False, "std(pct_change(close),63,min_periods=30)"),
    "nh252": (True,  "close/rolling_max(close,252,min_periods=120)-1"),
    "mom12": (True,  "close.shift(21)/close.shift(252)-1"),
    "big":   (True,  "log10(close*shares)"),
    # [2026-07-14 추가 — PREREGISTER_le_sv.md 동결]
    "dlow52": (True,  "close/rolling_min(close,252,min_periods=120)-1"),
    "obv63":  (False, "sum(sign(pct_change)*volume,63,min_periods=30)/sum(volume,63,min_periods=30)"),
    "amt20f": (True,  "mean(close*volume,20,min_periods=10)/1e8"),
    "svr5":   (True,  "mean(short_flows.short_vol_ratio,5,min_periods=3)"),
    # [2026-07-22 추가 — PREREGISTER_qs.md 동결] amt20f 동일 정의의 방향 반전(저거래대금 우대)
    "amt20l": (False, "mean(close*volume,20,min_periods=10)/1e8"),
}
MODELS = {
    "wu_a": ["lv63", "nh252", "mom12", "big"],   # 균형·방어형
    "wu_b": ["nh252", "mom12"],                   # 순수선택 대조(size 무베팅)
    "le_a": ["dlow52", "obv63", "amt20f"],        # 저점탈출(핵심)+OBV미매집+유동성 [REG 20260715]
    "sv_a": ["svr5"],                             # 공매도비중 단독(국면독립 가설) [REG 20260715]
    "qs_a": ["lv63", "nh252", "amt20l"],          # 조용한 강자: 저변동(핵심)+고가근접+저거래대금 [PREREGISTER_qs.md]
}
GUARD_SPEC = {"rv21_floor": VOL_FLOOR, "flat63_max": MAX_FLAT, "jump21_max": MAX_JUMP,
              "amt20_floor_억": LIQ_FLOOR, "suspended": 0, "lookback_min": LOOKBACK_MIN}

def spec_hash(model_id):
    """모델별 spec_hash(lowvol_score 패턴). 다른 모델 추가와 무관하게 항상 동일 해시."""
    payload = json.dumps({
        "factors": [(f, FACTORS[f][0], FACTORS[f][1]) for f in MODELS[model_id]],
        "universe": GUARD_SPEC,
        "method": "wu_pct_rank_sum_v1(core_required,aux_nan=0.5,whole_universe_single_rank)",
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]

def ensure_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS wu_scores (
            run_id TEXT, market TEXT, ticker TEXT, model_id TEXT,
            spec_hash TEXT, wu_score REAL, wu_rank INTEGER,
            n_universe INTEGER, frozen_at TEXT,
            PRIMARY KEY (run_id, market, ticker, model_id)
        )
    """)
    con.commit()

def load_window(ohlcv_con, all_dates, first_target):
    """첫 타깃일 기준 LOAD_PAD 거래일 전부터 끝까지 로딩(증분 창)."""
    pos = all_dates.index(first_target)
    cutoff = all_dates[max(0, pos - LOAD_PAD)]
    df = pd.read_sql(
        "SELECT ticker,date,close,volume,shares,is_suspended,market FROM daily_ohlcv "
        "WHERE date >= ?", ohlcv_con, params=(cutoff,))
    piv = lambda v: df.pivot_table(index="date", columns="ticker", values=v, aggfunc="last").sort_index()
    close = piv("close")
    # [2026-07-14] sv_a 용 short_flows (없으면 빈 프레임 — sv_a 만 0행, 나머지 모델 무영향)
    try:
        sf = pd.read_sql(
            "SELECT ticker,date,short_vol_ratio FROM short_flows WHERE date >= ?",
            ohlcv_con, params=(cutoff,))
        sf["short_vol_ratio"] = pd.to_numeric(sf["short_vol_ratio"], errors="coerce")
        svr = (sf.pivot_table(index="date", columns="ticker", values="short_vol_ratio", aggfunc="last")
               .reindex(index=close.index, columns=close.columns))
    except Exception as e:
        print(f"[경고] short_flows 로딩 실패({e}) — sv_a 는 이번 실행에서 0행")
        svr = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    return dict(close=close,
                vol=piv("volume").reindex(close.index),
                shares=piv("shares").reindex(close.index),
                susp=piv("is_suspended").reindex(close.index).fillna(0),
                mkt=df.groupby("ticker")["market"].last(),
                svr=svr)

def compute_frames(W):
    c = W["close"]; r = c.pct_change(fill_method=None)
    amt20 = (c * W["vol"]).rolling(20, min_periods=10).mean() / 1e8
    F = {}
    F["lv63"] = r.rolling(63, min_periods=30).std()
    F["nh252"] = c / c.rolling(252, min_periods=120).max() - 1
    F["mom12"] = c.shift(21) / c.shift(252) - 1
    F["big"] = np.log10((c * W["shares"]).where(lambda x: x > 0))
    # [2026-07-14 추가]
    F["dlow52"] = c / c.rolling(252, min_periods=120).min() - 1
    vol63 = W["vol"].rolling(63, min_periods=30).sum()
    F["obv63"] = (np.sign(r) * W["vol"]).rolling(63, min_periods=30).sum() / vol63.where(vol63 > 0)
    F["amt20f"] = amt20
    F["svr5"] = W["svr"].rolling(5, min_periods=3).mean()
    # [2026-07-22 추가] qs_a — amt20f 동일 프레임, 방향만 FACTORS에서 반전
    F["amt20l"] = amt20
    G = dict(rv21=r.rolling(21, min_periods=8).std(),
             flat63=(r.abs() < 1e-9).rolling(63, min_periods=20).mean(),
             jump21=r.abs().rolling(21, min_periods=5).max(),
             amt20=amt20)
    return F, G

def guard_row(W, G, d):
    return ((G["rv21"].loc[d] >= VOL_FLOOR) & (G["flat63"].loc[d] <= MAX_FLAT)
            & (G["jump21"].loc[d] <= MAX_JUMP) & (G["amt20"].loc[d] >= LIQ_FLOOR)
            & (W["susp"].loc[d] == 0) & W["close"].loc[d].notna())

def score_model(F, d, factors, uni):
    """순위합: 핵심(첫 팩터) 실측필수, 보조 NaN=0.5. lowvol_score.score_run과 동일 규칙."""
    core = F[factors[0]].loc[d][uni]
    s = core.rank(pct=True, ascending=FACTORS[factors[0]][0])   # 핵심 NaN → rank NaN(제외)
    for f in factors[1:]:
        x = F[f].loc[d][uni].rank(pct=True, ascending=FACTORS[f][0]).fillna(0.5)
        s = s.add(x, fill_value=np.nan)
    return s.dropna()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="특정일 보충 적재(YYYYMMDD, 등록일 이전 거부)")
    ap.add_argument("--backfill-from", help="[연구용] 발견기간 백필 시작일 — 판정 사용 금지")
    a = ap.parse_args()

    if not os.path.exists(OHLCV_DB):
        print(f"[중단] ohlcv.db 없음: {OHLCV_DB}"); sys.exit(1)
    ocon = sqlite3.connect(f"file:{OHLCV_DB}?mode=ro", uri=True)
    all_dates = [d for (d,) in ocon.execute("SELECT DISTINCT date FROM daily_ohlcv ORDER BY date")]
    hcon = sqlite3.connect(DB)
    ensure_table(hcon)
    loaded = {d for (d,) in hcon.execute("SELECT DISTINCT run_id FROM wu_scores")}
    reg_date = min(loaded) if loaded else None

    # ---- 타깃 결정 ----
    eligible = set(all_dates[LOOKBACK_MIN:])   # 룩백 충분한 날짜만
    if a.backfill_from:
        targets = sorted(d for d in eligible if d >= a.backfill_from and d not in loaded)
        print(f"[경고] --backfill-from {a.backfill_from}: 발견기간(in-sample) 백필 — §11 판정에 사용 금지")
    elif a.date:
        if a.date not in all_dates: print(f"[중단] ohlcv에 없는 날짜: {a.date}"); sys.exit(1)
        if a.date not in eligible: print(f"[중단] 룩백 {LOOKBACK_MIN}거래일 미달: {a.date}"); sys.exit(1)
        if reg_date and a.date < reg_date:
            print(f"[중단] 등록일({reg_date}) 이전 적재는 --backfill-from 로만."); sys.exit(1)
        targets = [] if a.date in loaded else [a.date]
    else:
        if not loaded:
            targets = [max(eligible)]
            print(f"[최초 실행] 최신 1일만 적재 → 등록일 = {targets[0]} (OOS 시작)")
        else:
            targets = sorted(d for d in eligible if d > reg_date and d not in loaded)
    if not targets:
        print("[증분] 신규 적재 대상 없음(idempotent)."); hcon.close(); ocon.close(); return

    W = load_window(ocon, all_dates, targets[0]); ocon.close()
    F, G = compute_frames(W)
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S%z")
    total = 0
    for d in targets:
        if d not in W["close"].index: continue
        uni = W["close"].columns[guard_row(W, G, d)]
        n_uni = len(uni)
        if n_uni < 300:
            print(f"[스킵] {d}: 유니버스 {n_uni} < 300 (데이터 이상 의심)"); continue
        for mid, facs in MODELS.items():
            sh = spec_hash(mid)
            s = score_model(F, d, facs, uni)
            rk = s.rank(ascending=False, method="min").astype(int)
            recs = [(d, str(W["mkt"].get(t, "?")), t, mid, sh, float(s[t]), int(rk[t]), n_uni, now)
                    for t in s.index]
            hcon.executemany("INSERT OR IGNORE INTO wu_scores VALUES (?,?,?,?,?,?,?,?,?)", recs)
            total += len(recs)
        hcon.commit()
        print(f"[적재] {d}: 유니버스 {n_uni} | " +
              " | ".join(f"{m} {len(score_model(F, d, fs, uni))}행" for m, fs in MODELS.items()))
    summ = pd.read_sql("SELECT model_id, COUNT(*) n, COUNT(DISTINCT run_id) runs, "
                       "MIN(run_id) first, MAX(run_id) last FROM wu_scores GROUP BY model_id", hcon)
    print(f"[완료] 신규 {total}행\n" + summ.to_string(index=False))
    hcon.close()

if __name__ == "__main__":
    main()
