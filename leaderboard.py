# -*- coding: utf-8 -*-
"""
leaderboard.py — 전 트랙 통합 판정 리더보드 (오프라인, 비치명 관측 단계)
========================================================================
목적: 판정 시즌(첫 판정 08-13~)에 §11 판정을 손계산이 아니라 자동으로.
      전 모델 동결점수를 '동일 프로토콜'로 forward IC + 부트스트랩 CI + §11 판정 라벨.

설계 원칙(이 프로젝트 규칙 그대로):
  - IC 계산은 validate_scores.grouped_spearman_ic 와 '같은 방식'(날짜×시장 cross-sectional
    Spearman 평균, ENTRY_LAG=1). 시세만 네트워크 provider 대신 ohlcv.db(오프라인).
  - 게이트 3종을 코드로 고정: ① 부분실행일(스크리너 유니버스<중앙값 30%) 제외
    ② 이중실행일(동결 frozen_at 2종↑ per run) 제외 ③ 비거래일 run_id는 직전 거래일 앵커.
  - §11 판정: h=20d 주지표, OOS 40거래일 미만=노이즈(기본값), 부트스트랩 CI 포함,
    Bonferroni는 '트랙 동시검정 수'로 임계 보정. 경계=기움(lean), 유의는 CI>0 & 40일↑ & 방향일치.
  - **트랙 간 IC 절대값 비교 금지**(유니버스 다르면 수준이 다름) — 출력에 경고 박음.
  - history.db·ohlcv.db 읽기 전용. 산출물 docs/leaderboard.json + 요약 텍스트.
  - 비치명: 실패해도 예외를 삼키고 pending 기록(§12-4 패턴). 라이브 신호 안 막음.

주의: h=20d 표본(40거래일)이 아직 없는 모델이 대부분 → 대부분 '노이즈'가 정상 출력.
      이 스크립트는 '무엇이 좋은지'가 아니라 '무엇을 언제 판정 가능한지'를 정직히 보여준다.
"""
import json, os, sqlite3, sys, traceback
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DB = HERE / "history.db"
OHLCV_DB = os.environ.get("OHLCV_DB", str(HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"))
OUT = HERE / "docs" / "leaderboard.json"

ENTRY_LAG = 1                 # validate_scores 와 동일(추천 +1거래일 종가 매수)
H_PRIMARY = 20                # §11 주지표
HORIZONS = [5, 20]
MIN_OOS = 40                  # §11 판정 최소 거래일
MIN_GROUP = 8                 # 그룹 IC 최소 종목쌍
JUMP_CAP = 0.32               # 이상치(우선주 점프 등) 컷
BOOT = 2000
GATE_FRAC = 0.30              # 부분실행일: 유니버스 < 중앙값*이 비율

# 트랙 정의: (테이블, 점수컬럼, 스크리너 유니버스 테이블[부분실행 게이트용])
TRACKS = {
    "v3":     ("v3_scores", "final_score_v3", "stage3_final"),
    "lowvol": ("lowvol_scores", "lowvol_score", "stage3_final"),
    "wu":     ("wu_scores", "wu_score", None),          # 전체상장, 유니버스 게이트 없음
}
# Bonferroni 분모 = 트랙별 '동시 검정 모델 수'(원장이 생기면 그걸로 대체)
#   현재값은 history.db 실측으로 산출(하드코딩 아님 — 아래 count_models).


def _pending(reason):
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"status": "pending", "reason": reason},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    print(f"[leaderboard] pending: {reason}")


def load_ohlcv():
    con = sqlite3.connect(f"file:{OHLCV_DB}?mode=ro", uri=True)
    px = pd.read_sql("SELECT ticker,date,close,market FROM daily_ohlcv", con)
    con.close()
    close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    mkt = px.groupby("ticker")["market"].last()
    return close, mkt


def build_gates(con, close_index):
    """게이트 대상 run_id 집합 산출(부분실행·이중실행)."""
    didx = {d: i for i, d in enumerate(close_index)}
    # ① 부분실행일: stage3_final 유니버스가 중앙값의 GATE_FRAC 미만
    partial = set()
    try:
        cnt = pd.read_sql("SELECT run_id, COUNT(*) n FROM stage3_final GROUP BY run_id", con)
        med = cnt["n"].median()
        partial = set(cnt.loc[cnt["n"] < med * GATE_FRAC, "run_id"].astype(str))
    except Exception:
        pass
    # ② 이중실행일: 동결점수 frozen_at 의 '최대 시간 간격'이 크면(별개 배치) 제외.
    #   ⚠️ distinct 개수로 판별하면 안 됨 — 정상 1회 적재도 종목마다 초 단위로 다른 frozen_at 을
    #      가져(예: 14:31:29~14:31:33) distinct 다종이 됨. 진짜 이중실행은 새벽/저녁처럼 시간이
    #      크게 벌어짐(20260703: 00:39 vs 21:28 = 21시간). 실측상 정상일 gap 0분 vs 이중 1249분
    #      → 임계 60분이면 안전. (2026-07-05 오탐 교정)
    DOUBLE_GAP_MIN = 60
    dbl = set()
    for tb, sc, _ in TRACKS.values():
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({tb})")]
        if "frozen_at" not in cols:
            continue
        fa = pd.read_sql(f"SELECT run_id, frozen_at FROM {tb}", con)
        fa["ts"] = pd.to_datetime(fa["frozen_at"], errors="coerce", utc=True)
        for rid, g in fa.dropna(subset=["ts"]).groupby("run_id"):
            gap = (g["ts"].max() - g["ts"].min()).total_seconds() / 60.0
            if gap >= DOUBLE_GAP_MIN:
                dbl.add(str(rid))
    return partial, dbl, didx


def anchor(rid, didx):
    """run_id → 거래일 인덱스. 비거래일(주말 등)이면 직전 거래일."""
    if rid in didx:
        return didx[rid]
    import datetime as dt
    try:
        d = dt.datetime.strptime(rid, "%Y%m%d")
    except Exception:
        return None
    for k in range(1, 6):
        c = (d - dt.timedelta(days=k)).strftime("%Y%m%d")
        if c in didx:
            return didx[c]
    return None


def model_ic(scores, close, N, didx, excl):
    """scores: DataFrame(run_id, market, ticker, score). 게이트 제외 후 h별 그룹 IC + 부트스트랩."""
    out = {}
    for h in HORIZONS:
        per_run = []          # (run별 그룹평균 IC) 리스트 — n = 유효 거래일 수
        for rid, g in scores.groupby("run_id"):
            rid = str(rid)
            if rid in excl:
                continue
            t = anchor(rid, didx)
            if t is None or t + h >= N:
                continue
            fwd_all = close.iloc[t + ENTRY_LAG + h] / close.iloc[t + ENTRY_LAG] - 1 \
                if t + ENTRY_LAG + h < N else None
            if fwd_all is None:
                continue
            jump = close.pct_change(fill_method=None).abs()\
                .iloc[t + ENTRY_LAG + 1:t + ENTRY_LAG + h + 1].max()
            fwd_all = fwd_all.where(jump <= JUMP_CAP)
            # 시장별 cross-sectional IC → 평균 (grouped_spearman_ic 와 동일 사상)
            day_ics = []
            for mk, gm in g.groupby("market"):
                s = gm.set_index("ticker")["score"].astype(float)
                s.index = s.index.astype(str)
                b = fwd_all.reindex(s.index)
                m = s.notna() & b.notna()
                if m.sum() < MIN_GROUP or s[m].nunique() < 3 or b[m].nunique() < 3:
                    continue
                day_ics.append(np.corrcoef(s[m].rank(), b[m].rank())[0, 1])
            if day_ics:
                per_run.append(float(np.mean(day_ics)))
        arr = np.array(per_run)
        if len(arr) == 0:
            out[h] = dict(ic=None, n=0, ci=[None, None], pos=None)
            continue
        rng = np.random.default_rng(7)
        boots = [rng.choice(arr, len(arr)).mean() for _ in range(BOOT)]
        out[h] = dict(ic=round(float(arr.mean()), 4), n=len(arr),
                      ci=[round(float(np.percentile(boots, 2.5)), 4),
                          round(float(np.percentile(boots, 97.5)), 4)],
                      pos=round(float((arr > 0).mean()), 3))
    return out


def verdict(stat, denom):
    """§11 판정. stat=model_ic()[H_PRIMARY]. denom=Bonferroni 동시검정 수."""
    n, ic, ci = stat["n"], stat["ic"], stat["ci"]
    if n < MIN_OOS:
        return "노이즈", f"OOS {n}/{MIN_OOS}거래일 — 표본 부족(기본값)"
    if ic is None:
        return "노이즈", "IC 산출 불가"
    lo, hi = ci
    # Bonferroni: 동시검정 보정 — CI를 (1 - 0.05/denom) 수준으로 봐야 엄밀하나,
    #   부트스트랩 2.5/97.5(95%)만 보유 → 보수적으로 '분모>1이면 경계는 기움 강등' 규칙.
    if lo is not None and lo > 0 and stat["pos"] >= 0.60:
        if denom > 1 and lo < 0.02:      # 다중검정 여유 얇으면 유의 보류
            return "기움", f"IC {ic:+.3f} CI[{lo:+.3f},{hi:+.3f}] 방향{stat['pos']:.0%} · Bonferroni(분모{denom}) 여유 얇아 보류"
        return "유의", f"IC {ic:+.3f} CI>0[{lo:+.3f},{hi:+.3f}] 방향{stat['pos']:.0%} (분모{denom})"
    if ic > 0.03 and (lo is None or lo > -0.02):
        return "기움", f"IC {ic:+.3f} CI[{lo:+.3f},{hi:+.3f}] — 양(+)이나 CI가 0에 걸침"
    if ic < -0.03:
        return "역작동", f"IC {ic:+.3f} — 점수가 거꾸로"
    return "노이즈", f"IC {ic:+.3f} CI[{lo:+.3f},{hi:+.3f}] — 0 근처"


def main():
    if not DB.exists():
        _pending("history.db 없음"); return
    if not os.path.exists(OHLCV_DB):
        _pending(f"ohlcv.db 없음({OHLCV_DB})"); return
    try:
        close, _ = load_ohlcv()
        dates = list(close.index); N = len(dates)
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        partial, dbl, didx = build_gates(con, dates)
        excl = partial | dbl

        # Bonferroni 분모 = 트랙별 실측 모델 수(원장 생기면 대체)
        denom = {}
        for trk, (tb, sc, _) in TRACKS.items():
            denom[trk] = con.execute(f"SELECT COUNT(DISTINCT model_id) FROM {tb}").fetchone()[0]

        results = []
        for trk, (tb, sc, _) in TRACKS.items():
            for (mid,) in con.execute(f"SELECT DISTINCT model_id FROM {tb}"):
                s = pd.read_sql(
                    f"SELECT run_id, market, ticker, {sc} AS score FROM {tb} WHERE model_id=?",
                    con, params=(mid,))
                s["ticker"] = s["ticker"].astype(str)
                stat = model_ic(s, close, N, didx, excl)
                vd, why = verdict(stat[H_PRIMARY], denom[trk])
                results.append(dict(track=trk, model=mid,
                                    h5=stat[5], h20=stat[20],
                                    verdict=vd, why=why, denom=denom[trk]))
        con.close()

        results.sort(key=lambda r: (r["h20"]["ic"] is None, -(r["h20"]["ic"] or -9)))
        payload = dict(
            status="ok",
            note="트랙 간 IC 절대값 비교 금지(유니버스 상이). h=20d 주지표, OOS<40거래일=노이즈.",
            entry_lag=ENTRY_LAG, min_oos=MIN_OOS,
            gates=dict(partial_run=sorted(partial), double_run=sorted(dbl)),
            models=results)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        # 콘솔 요약 — JSON 저장 '후'의 표시 단계. 여기서 예외(파이프 끊김 등)가 나도
        # 이미 저장된 산출물을 pending 으로 덮어쓰면 안 되므로 별도 try 로 격리한다.
        try:
            print(f"[leaderboard] 게이트 제외: 부분실행 {sorted(partial)} · 이중실행 {sorted(dbl)}")
            print(f"{'트랙':7s} {'모델':10s} {'h20 IC':>8s} {'n':>3s} {'95%CI':>20s} {'판정':>6s}")
            for r in results:
                s = r["h20"]; ic = f"{s['ic']:+.3f}" if s["ic"] is not None else "  n/a"
                ci = f"[{s['ci'][0]:+.3f},{s['ci'][1]:+.3f}]" if s["ci"][0] is not None else "-"
                print(f"{r['track']:7s} {r['model']:10s} {ic:>8s} {s['n']:3d} {ci:>20s} {r['verdict']:>6s}")
            print("\n※ 트랙 간 IC 절대값 비교 금지 · h=20d 주지표 · OOS<40거래일=노이즈(기본값)")
        except Exception:
            pass   # 표시 실패는 무해 — 산출물(leaderboard.json)은 이미 저장됨
    except Exception as e:
        _pending(f"예외(비치명): {e}\n{traceback.format_exc()[:500]}")


if __name__ == "__main__":
    main()
