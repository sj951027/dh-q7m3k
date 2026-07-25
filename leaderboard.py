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

# 등록일 원장: checkup.py REG_DATE 단일소스(중복 하드코딩 금지).
# wu 는 PREREGISTER_wu.md 명시 등록일 20260702 (원장 미기재분 보충 — 원장 갱신되면 그쪽 우선).
from checkup import REG_DATE as _REG
REG_DATE = dict(_REG)
REG_DATE.setdefault("wu_a", "20260702")
REG_DATE.setdefault("wu_b", "20260702")

ENTRY_LAG = 1                 # validate_scores 와 동일(추천 +1거래일 종가 매수)
H_PRIMARY = 20                # §11 주지표
HORIZONS = [1, 3, 5, 10, 20] # h1·h3·h10 은 관측 전용(2026-07-25 추가) — 판정은 H_PRIMARY(h20)만
MIN_OOS = 40                  # §11 판정 최소 거래일
MIN_GROUP = 8                 # 그룹 IC 최소 종목쌍
TOP_EXC = 20                  # 시장초과 관측용 상위 종목 수(시장별) — 분산추천 개수와 동일 (2026-07-25)
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
    #   ⚠️ 2026-07-18 오탐 수정: 신규 모델 '백필'(예: mom_b — 과거 run_id 행이 나중 날짜
    #      frozen_at)이 섞이면 run 전체 gap 이 며칠로 벌어져 전 run 이 이중실행으로 오탐
    #      → 전 트랙 표본 전멸. 실측 근거로 규칙 교정: 진짜 이중실행(20260703)은 '같은
    #      model_id 안에서' 시각이 벌어지고(v30 00:39~21:28 — 배치 간 유니버스 차이로
    #      INSERT OR IGNORE 를 뚫고 양쪽 행이 공존), 백필·모델추가는 모델 '간'에만
    #      벌어진다(각 모델의 배치는 원자적 = 모델 내 gap 0). → gap 을 (run_id, model_id)
    #      내부에서 계산. 시간 창 같은 추가 매직넘버 불필요.
    dbl = set()
    for tb, sc, _ in TRACKS.values():
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({tb})")]
        if "frozen_at" not in cols:
            continue
        fa = pd.read_sql(f"SELECT run_id, model_id, frozen_at FROM {tb}", con)
        fa["ts"] = pd.to_datetime(fa["frozen_at"], errors="coerce", utc=True)
        for (rid, _mid), g in fa.dropna(subset=["ts"]).groupby(["run_id", "model_id"]):
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


def dedupe_by_anchor(scores, didx, excl, reg=None):
    """앵커 거래일 중복 제거 — 주말/공휴일 run 은 직전 거래일로 앵커되어 같은 날이
    이중 계상됨(유사복제 → n 부풀림·CI 과소). v3_backtest 의 '정적/주말 제거'와 동일 사상.
    거래일 run 자체가 있으면 그것을, 없으면(예: 공휴일 등록 첫 run) 최소 run_id 를 유지.
    reg 필터를 중복제거보다 먼저 적용 — 등록일 run(예: v30 의 20260606 공휴일 run)이
    등록 전 run 에 밀려 탈락하는 순서 버그 방지."""
    cand = {}
    for rid in scores["run_id"].astype(str).unique():
        if rid in excl or (reg and rid < reg):
            continue
        t = anchor(rid, didx)
        if t is None:
            continue
        cand.setdefault(t, []).append(rid)
    keep = set()
    for t, rids in cand.items():
        trade = [r for r in rids if r in didx]
        keep.add(min(trade) if trade else min(rids))
    return keep


def model_ic(scores, close, N, didx, excl, reg=None):
    """scores: DataFrame(run_id, market, ticker, score). 게이트 제외 후 h별 그룹 IC + 부트스트랩.
    reg: 등록일(YYYYMMDD). 등록 전 run 은 post-hoc 백필이므로 IC 표본에서 제외(§11 forward-only).
    반환에 oos_days(등록 후 경과 유효 거래일 수 — §11 판정 게이트) 포함."""
    out = {}
    keep = dedupe_by_anchor(scores, didx, excl, reg=reg)
    out["oos_days"] = len(keep)
    for h in HORIZONS:
        per_run = []          # (앵커 거래일별 그룹평균 IC) 리스트 — n = 유효 거래일 수
        per_exc = []          # 상위 TOP_EXC 종목 평균수익 − 유니버스 중앙값 (관측 전용, h5/h20만 저장)
        for rid, g in scores.groupby("run_id"):
            rid = str(rid)
            if rid in excl or rid not in keep:
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
            day_excs = []
            for mk, gm in g.groupby("market"):
                s = gm.set_index("ticker")["score"].astype(float)
                s.index = s.index.astype(str)
                b = fwd_all.reindex(s.index)
                m = s.notna() & b.notna()
                if m.sum() < MIN_GROUP or s[m].nunique() < 3 or b[m].nunique() < 3:
                    continue
                day_ics.append(np.corrcoef(s[m].rank(), b[m].rank())[0, 1])
                # 시장초과 관측: 상위 TOP_EXC 평균수익 − 유니버스 중앙값 (v3_backtest 와 동일 사상)
                top = s[m].sort_values(ascending=False).head(TOP_EXC).index
                day_excs.append(float(b[m].reindex(top).mean() - b[m].median()))
            if day_ics:
                per_run.append(float(np.mean(day_ics)))
            if day_excs:
                per_exc.append(float(np.mean(day_excs)))
        if h in (5, 20):      # 시장초과 관측치 저장(별도 rng — 기존 IC 부트스트랩과 완전 분리)
            ae = np.array(per_exc)
            if len(ae) == 0:
                out[f"exc{h}"] = dict(mean=None, n=0, ci=[None, None])
            else:
                rng2 = np.random.default_rng(11)
                bo = [rng2.choice(ae, len(ae)).mean() for _ in range(BOOT)]
                out[f"exc{h}"] = dict(mean=round(float(ae.mean() * 100), 2), n=len(ae),
                                      ci=[round(float(np.percentile(bo, 2.5) * 100), 2),
                                          round(float(np.percentile(bo, 97.5) * 100), 2)])
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


def verdict(stat, denom, oos_days):
    """§11 판정. stat=model_ic()[H_PRIMARY]. denom=Bonferroni 동시검정 수.
    게이트는 §11 원문대로 '등록 후 경과 OOS 거래일'(h20 표본수 아님 — 표본수 기준이면
    판정이 등록+60거래일로 밀려 사전등록 시점표와 어긋남)."""
    n, ic, ci = stat["n"], stat["ic"], stat["ci"]
    if oos_days < MIN_OOS:
        return "노이즈", f"OOS {oos_days}/{MIN_OOS}거래일 — 표본 부족(기본값)"
    if n == 0:
        return "노이즈", f"OOS {oos_days}일이나 h20 창 닫힌 표본 0 — 산출 불가"
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
                reg = REG_DATE.get(mid)
                stat = model_ic(s, close, N, didx, excl, reg=reg)
                vd, why = verdict(stat[H_PRIMARY], denom[trk], stat["oos_days"])
                if reg is None:
                    why += " · ⚠원장(REG_DATE) 미등록 — 등록일 필터 미적용"
                results.append(dict(track=trk, model=mid, reg_date=reg,
                                    oos_days=stat["oos_days"],
                                    h5=stat[5], h20=stat[20],
                                    h1=stat[1], h3=stat[3], h10=stat[10],   # 관측 전용 — 판정·정렬 미사용
                                    exc5=stat.get("exc5"), exc20=stat.get("exc20"),  # 시장초과 %p (관측 전용)
                                    verdict=vd, why=why, denom=denom[trk]))
        con.close()

        results.sort(key=lambda r: (r["h20"]["ic"] is None, -(r["h20"]["ic"] or -9),
                                    r["h5"]["ic"] is None, -(r["h5"]["ic"] or -9)))
        payload = dict(
            status="ok",
            note="트랙 간 IC 절대값 비교 금지(유니버스 상이). h=20d 주지표, OOS<40거래일=노이즈.",
            entry_lag=ENTRY_LAG, min_oos=MIN_OOS,
            gates=dict(partial_run=sorted(partial), double_run=sorted(dbl)),
            models=results)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        # 콘솔 요약
        print(f"[leaderboard] 게이트 제외: 부분실행 {sorted(partial)} · 이중실행 {sorted(dbl)}")
        # h5 는 §11 명시 보조지표("보조로 h=5d 같이 본다") — 판정은 여전히 h20 게이트만.
        print(f"{'트랙':7s} {'모델':10s} {'h20 IC':>8s} {'n':>3s} {'OOS':>4s} {'95%CI':>20s}"
              f" {'h5 IC(보조)':>12s} {'n':>3s} {'판정':>6s}")
        for r in results:
            s = r["h20"]; ic = f"{s['ic']:+.3f}" if s["ic"] is not None else "  n/a"
            ci = f"[{s['ci'][0]:+.3f},{s['ci'][1]:+.3f}]" if s["ci"][0] is not None else "-"
            a = r["h5"]; ic5 = f"{a['ic']:+.3f}" if a["ic"] is not None else "  n/a"
            ci5 = f" CI[{a['ci'][0]:+.2f},{a['ci'][1]:+.2f}]" if a["ci"][0] is not None else ""
            print(f"{r['track']:7s} {r['model']:10s} {ic:>8s} {s['n']:3d} {r['oos_days']:4d} {ci:>20s}"
                  f" {ic5:>8s}{ci5} {a['n']:3d} {r['verdict']:>6s}")
        print("\n※ 트랙 간 IC 절대값 비교 금지 · h=20d 주지표 · OOS<40거래일=노이즈(기본값)")
    except Exception as e:
        _pending(f"예외(비치명): {e}\n{traceback.format_exc()[:500]}")


if __name__ == "__main__":
    main()
