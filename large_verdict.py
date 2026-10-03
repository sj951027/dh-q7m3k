# -*- coding: utf-8 -*-
"""
large_verdict.py — 대형 트랙 ls_t1 의 §9 판정(h=60·120거래일) 준비/산출. 읽기 전용, 점수 무관.

왜: 리더보드(leaderboard.py)는 h20 만 계산하고 ls_t1 라벨은 '참고'다. 정본 판정은 LARGE_SCORE_DESIGN §9 +
   PREREGISTER_ls_t1.md(h=60·120, 주간 리밸런스 기준, 표본 작아 보수적). 첫 앵커(등록 20260806)의 h60 창이
   2026-11 초에 닫히므로, 그 전에 같은 계산을 매일 돌려 "앵커 n · 대기 중"을 보이게 한다.

어떻게 (2026-10-03 고정 — 결과를 보고 바꾸지 않는다):
  - 점수·게이트·앵커·IC·부트스트랩은 leaderboard.py 의 함수를 그대로 가져다 쓴다(model_ic 를 HORIZONS=[20,60,120] 로).
    → h20 일간 앵커 값은 리더보드 ls_t1 의 h20 과 일치해야 한다(자체 검증, --check).
  - 시세 = daily_ohlcv + 대형 전용 보충표 daily_ohlcv_extra(본 표 우선) — 리더보드 ls_t1 블록과 동일.
  - 주간 리밸런스: 등록일 이후 게이트 통과·중복 제거된 일간 앵커 중 **ISO 주마다 첫 앵커 1개**만 쓴다(정본).
    일간 앵커 값은 참고로 같이 적는다.
  - 판정 라벨: leaderboard.verdict (§11 과 같은 규칙, Bonferroni 분모 1) 를 h60 주간 통계에 적용. 단 추가 게이트:
    h 창이 닫힌 주간 앵커 **8개 미만이면 '대기'**(아직 판정 안 함). h120 은 같은 방식으로 병기(정본은 둘 다).
  - 창이 서로 겹치는(h60 이면 12주 겹침) 앵커들의 iid 부트스트랩 CI 는 너무 좁다 → **비겹침 앵커**(앞 앵커에서 h거래일
    이상 떨어진 것만) 통계를 같이 적고, 둘이 어긋나면 '기움' 이상으로 올리지 않는다(보수).

사용:
  python large_verdict.py            # 상태 출력 + research/large_verdict_status.md
  python large_verdict.py --check    # h20 일간 값이 리더보드(임시 생성)와 같은지 자체 검증
"""
import argparse
import json
import sqlite3
import sys
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import leaderboard as L          # noqa: E402  (읽기 전용 함수만 사용 — main 은 부르지 않는다)

OUT = HERE / "research" / "large_verdict_status.md"
HS = [20, 60, 120]
MIN_WEEKLY = 8                   # h 창이 닫힌 주간 앵커 최소 수(미만이면 '대기')
MODEL = "ls_t1"


def ls_t1_scores(con):
    """leaderboard.py ls_t1 블록과 같은 식(PREREGISTER_ls_t1): 4팩터 백분위 동일가중, 최소 2개."""
    lg = pd.read_sql("SELECT run_id, market, ticker, per, pbr, rim_spread, div_yield FROM large_final", con)
    lg["ticker"] = lg["ticker"].astype(str)
    fz = pd.DataFrame(index=lg.index)
    fz["ep"] = 1.0 / lg["per"].where(lg["per"] > 0)
    fz["bp"] = 1.0 / lg["pbr"].where(lg["pbr"] > 0)
    fz["rim"] = lg["rim_spread"]; fz["dv"] = lg["div_yield"]
    rk = fz.groupby(lg["run_id"]).rank(pct=True)
    lg["score"] = rk.mean(axis=1).where(rk.notna().sum(axis=1) >= 2)
    return lg.dropna(subset=["score"])[["run_id", "market", "ticker", "score"]]


def load_close_with_extra():
    close, _ = L.load_ohlcv()
    try:
        import extra_ohlcv
        ex = extra_ohlcv.load_extra_close(L.OHLCV_DB, exclude=set(close.columns))
        if len(ex):
            close = close.join(ex.reindex(close.index), how="left")
    except Exception as e:
        print(f"   ⚠️ 시세 보충 생략(비치명): {e}")
    return close


def weekly_subset(keep_rids, didx, dates):
    """일간 앵커(run_id 집합) → ISO 주마다 첫 앵커 1개."""
    by_week = {}
    for rid in sorted(keep_rids):
        t = L.anchor(rid, didx)
        d = dt.datetime.strptime(dates[t], "%Y%m%d")
        wk = d.isocalendar()[:2]
        by_week.setdefault(wk, rid)
    return set(by_week.values())


def nonoverlap_subset(rids, didx, h):
    """앞 앵커와 h거래일 이상 떨어진 앵커만(비겹침)."""
    out, last = [], None
    for rid in sorted(rids, key=lambda r: L.anchor(r, didx)):
        t = L.anchor(rid, didx)
        if last is None or t - last >= h:
            out.append(rid); last = t
    return set(out)


def closed_count(rids, didx, N, h):
    return sum(1 for r in rids if L.anchor(r, didx) + L.ENTRY_LAG + h < N)


def run(check=False):
    if not L.DB.exists() or not Path(L.OHLCV_DB).exists():
        print("history.db 또는 ohlcv.db 없음"); return 1
    L.HORIZONS = HS                      # model_ic 가 읽는 모듈 전역 — 이 프로세스 안에서만
    close = load_close_with_extra()
    dates = list(close.index); N = len(dates)
    con = sqlite3.connect(f"file:{L.DB}?mode=ro", uri=True)
    partial, dbl, didx = L.build_gates(con, dates)
    excl = partial | dbl
    s = ls_t1_scores(con)
    con.close()
    reg = L.REG_DATE.get(MODEL)
    keep_daily = L.dedupe_by_anchor(s, didx, excl, reg=reg)
    keep_weekly = weekly_subset(keep_daily, didx, dates)
    daily = L.model_ic(s, close, N, didx, excl, reg=reg)
    weekly = L.model_ic(s[s["run_id"].astype(str).isin(keep_weekly)], close, N, didx, excl, reg=reg)
    nonov = {}
    for h in (60, 120):
        sub = nonoverlap_subset(keep_weekly, didx, h)
        nonov[h] = (L.model_ic(s[s["run_id"].astype(str).isin(sub)], close, N, didx, excl, reg=reg)[h], len(sub))

    today = dates[-1]
    first_t = min(L.anchor(r, didx) for r in keep_daily) if keep_daily else None
    lines = [f"# 대형 트랙 ls_t1 — §9 판정 상태 (기준일 {today}, 생성 {dt.datetime.now():%Y-%m-%d %H:%M})", "",
             f"- 등록 {reg} · 등록 후 경과 거래일(일간 앵커, 게이트·중복 제거 후) **{daily['oos_days']}** · 주간 앵커 {len(keep_weekly)}개 · "
             f"시세 종목 {close.shape[1]:,}(보충표 포함) · 게이트 제외 run {len(excl)}.",
             "- 규칙은 이 파일 머리말(2026-10-03 고정). 판정은 h60·h120 주간 앵커, 라벨은 §11 과 같은 규칙(분모 1) + 주간 앵커 8개 미만이면 '대기'.", ""]
    lines += ["| h | 기준 | 창 닫힌 앵커 n | IC | 95% CI | 주별 양(+) | 라벨 |", "|---|---|---|---|---|---|---|"]
    verdicts = {}
    for h in HS:
        for tag, st, rids in (("일간(참고)", daily[h], keep_daily), ("주간(정본)", weekly[h], keep_weekly)):
            nclosed = closed_count(rids, didx, N, h)
            ic = st["ic"]; ci = st["ci"]; pos = st["pos"]
            if tag.startswith("주간") and h in (60, 120):
                if nclosed < MIN_WEEKLY:
                    lab, why = "대기", f"창 닫힌 주간 앵커 {nclosed}/{MIN_WEEKLY}"
                else:
                    lab, why = L.verdict(st, 1, daily["oos_days"])
                    no_st, no_n = nonov[h]
                    if no_st["ic"] is not None and lab == "유의" and not (no_st["ci"][0] is not None and no_st["ci"][0] > 0):
                        lab, why = "기움", why + f" · 비겹침 {no_n}앵커 CI 0 걸침 → 기움으로 보수화"
                verdicts[h] = (lab, why, nclosed)
            else:
                lab = "참고" if h == 20 else ("대기" if nclosed < MIN_WEEKLY else "참고")
            icx = "—" if ic is None else f"{ic:+.4f}"
            cix = "—" if ci[0] is None else f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"
            posx = "—" if pos is None else f"{pos:.0%}"
            lines.append(f"| h{h} | {tag} | {nclosed}/{len(rids)} | {icx} | {cix} | {posx} | {lab} |")
    lines.append("")
    for h in (60, 120):
        no_st, no_n = nonov[h]
        icx = "—" if no_st["ic"] is None else f"{no_st['ic']:+.4f} CI[{no_st['ci'][0]:+.4f}, {no_st['ci'][1]:+.4f}]"
        lines.append(f"- 비겹침 앵커(h{h}): {no_n}개 중 창 닫힘 {no_st['n']} → IC {icx}.")
    if first_t is not None:
        for h in (60, 120):
            need = first_t + L.ENTRY_LAG + h
            lines.append(f"- h{h} 첫 창이 닫히는 거래일: {'이미 닫힘' if need < N else f'앞으로 {need - N + 1}거래일 뒤'} "
                         f"(첫 앵커 {dates[first_t]}). 주간 앵커 {MIN_WEEKLY}개가 닫히려면 그로부터 약 7주 더.")
    lines += ["", "## 판정"]
    for h in (60, 120):
        lab, why, nclosed = verdicts[h]
        lines.append(f"- **h{h}: {lab}** — {why}")
    lines += ["", "- 리더보드 ls_t1 h20 참고값과 '일간(참고) h20' 줄이 같아야 한다(같은 함수·같은 시세). 다르면 코드를 의심.",
              "- 시세: daily_ohlcv + daily_ohlcv_extra(2026-10-03 보충, 코스닥 글로벌·영문코드 136종목). 그 전 리더보드 값과는 비교하지 않는다."]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n💾 {OUT}")

    if check:
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        L.HORIZONS = [1, 3, 5, 10, 20]
        L.OUT = tmp / "leaderboard.json"
        L.main()
        lb = json.loads(L.OUT.read_text(encoding="utf-8"))
        ref = next(m for m in lb["models"] if m["model"] == MODEL)["h20"]
        mine = {k: daily[20][k] for k in ("ic", "n", "ci", "pos")}
        ok = (ref == mine)
        print(f"\n[check] 리더보드 ls_t1 h20 {ref}\n[check] 이 스크립트 일간 h20 {mine}\n[check] {'일치 ✅' if ok else '불일치 ❌'}")
        return 0 if ok else 2
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="h20 일간 값이 리더보드와 같은지 자체 검증(리더보드는 임시 폴더에 생성)")
    a = ap.parse_args()
    return run(check=a.check)


if __name__ == "__main__":
    sys.exit(main())
