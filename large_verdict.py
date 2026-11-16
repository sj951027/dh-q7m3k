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
    h 창이 닫힌 주간 앵커 **8개 미만이면 '대기'**(날짜상 닫힌 수와 IC 계산된 수 둘 다). h120 은 같은 방식으로 병기(정본은 둘 다).
  - ⚠ 이 세부 규칙(주간 앵커·8개·비겹침 보수화)은 PREREGISTER_ls_t1 에 없던 구현자 결정(2026-10-03)이다. 첫 창이 닫히기 전(11월 초)
    사용자 확정이 필요하며, leaderboard.verdict 재사용은 판정문의 검증 전체(주블록 감도·짝비교·국면 각주)를 대체하지 않는다.
  - 창이 서로 겹치는(h60 이면 12주 겹침) 앵커들의 iid 부트스트랩 CI 는 너무 좁다 → **비겹침 앵커**(앞 앵커에서 h거래일
    이상 떨어진 것만) 통계를 같이 적고, 둘이 어긋나면 '기움' 이상으로 올리지 않는다(보수).

순위 상관 정의 (2026-11-16 사용자 결정 D44 — DECISIONS_LOG.md 에 세부 규칙 7개, 전 유니버스 h60·h120 값을 보기 전에 고정):
  - 설계 §9 문구는 '전 유니버스', 리더보드 공용 함수는 '시장별 상관의 평균'이다. 둘을 **각각** 같은 절차로 판정하고
    최종 라벨은 **둘 중 낮은 쪽**(한쪽이라도 '대기'면 '대기', 아니면 역작동 < 노이즈 < 기움 < 유의). 앞에 내세우는 값은 전 유니버스.
  - 전 유니버스 값은 그 run 의 모든 시장(둘 이상)이 시장별 최소 조건을 채운 앵커에서만 계산한다(공통 앵커).
    시세·진입·점프 제외·부트스트랩은 leaderboard.model_ic 과 같고 순위만 시장 구분 없이 매긴다. 공용 model_ic 은 건드리지 않는다.
  - 정의를 정한 날(DECISION_DATE) 종가까지 창이 닫힌 주간 앵커를 뺀 감도를 같이 적는다(대신 쓰지 않는다).
  - '코스피만'·'코스닥만'·일간 앵커·h20 은 참고 줄(판정 조건 아님).

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
DECISION_DATE = "20261116"       # D44: 순위 상관 정의를 정한 날 — 이 날 종가까지 창이 닫힌 앵커는 '정하기 전에 닫힌 것'
LABEL_ORDER = {"역작동": 0, "노이즈": 1, "기움": 2, "유의": 3}   # D44 규칙 4 — 낮은 쪽이 최종


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


def _boot_stat(vals):
    """leaderboard.model_ic 의 IC 요약과 같은 식(씨앗 7 · BOOT 회 · 소수 4자리)."""
    arr = np.array(vals)
    if len(arr) == 0:
        return dict(ic=None, n=0, ci=[None, None], pos=None)
    rng = np.random.default_rng(7)
    boots = [rng.choice(arr, len(arr)).mean() for _ in range(L.BOOT)]
    return dict(ic=round(float(arr.mean()), 4), n=len(arr),
                ci=[round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)],
                pos=round(float((arr > 0).mean()), 3))


def pooled_ic(scores, close, N, didx, excl, reg=None):
    """[D44] 전 유니버스 순위 상관 + 시장별 참고값. 반환: {'pooled'|시장명: {h: stat}}.
    시세·진입·점프 제외·최소 조건은 leaderboard.model_ic 과 같다. 순위만 시장 구분 없이 매긴다.
    공통 앵커: 그 run 의 모든 시장(둘 이상)이 최소 조건(MIN_GROUP 종목·서로 다른 값 3개)을 채운 앵커만 'pooled' 에 넣는다."""
    keep = L.dedupe_by_anchor(scores, didx, excl, reg=reg)
    chg = close.pct_change(fill_method=None).abs()
    vals = {}
    for h in HS:
        for rid, g in scores.groupby("run_id"):
            rid = str(rid)
            if rid in excl or rid not in keep:
                continue
            t = L.anchor(rid, didx)
            if t is None or t + L.ENTRY_LAG + h >= N:
                continue
            fwd = close.iloc[t + L.ENTRY_LAG + h] / close.iloc[t + L.ENTRY_LAG] - 1
            jump = chg.iloc[t + L.ENTRY_LAG + 1:t + L.ENTRY_LAG + h + 1].max()
            fwd = fwd.where(jump <= L.JUMP_CAP)
            parts, n_mk = [], 0
            for mk, gm in g.groupby("market"):
                n_mk += 1
                s = gm.set_index("ticker")["score"].astype(float)
                s.index = s.index.astype(str)
                b = fwd.reindex(s.index)
                m = s.notna() & b.notna()
                if m.sum() < L.MIN_GROUP or s[m].nunique() < 3 or b[m].nunique() < 3:
                    continue
                parts.append((s[m], b[m]))
                vals.setdefault(str(mk).lower(), {}).setdefault(h, []).append(
                    float(np.corrcoef(s[m].rank(), b[m].rank())[0, 1]))
            if n_mk >= 2 and len(parts) == n_mk:
                S = pd.concat([p[0] for p in parts]); B = pd.concat([p[1] for p in parts])
                vals.setdefault("pooled", {}).setdefault(h, []).append(float(np.corrcoef(S.rank(), B.rank())[0, 1]))
    return {k: {h: _boot_stat(v.get(h, [])) for h in HS} for k, v in vals.items()} | \
           ({} if "pooled" in vals else {"pooled": {h: _boot_stat([]) for h in HS}})


def label_one(st, nclosed, no_st, oos_days):
    """한 정의의 주간 통계 → 라벨(2026-10-03 절차 그대로 — D44 규칙 3)."""
    # [2026-10-03 Codex 검토 반영] 날짜상 닫힌 수(nclosed)와 실제 IC 계산된 수(st['n'])가 다를 수 있다(시세 결손) → 둘 다 8 이상이어야 판정.
    #   비겹침 앵커가 0·1개면 '유의'를 줄 근거가 없다 → 비겹침 계산분 ≥2 이고 그 CI 하단 > 0 일 때만 '유의' 유지, 아니면 '기움'.
    if min(nclosed, st["n"]) < MIN_WEEKLY:
        return "대기", f"창 닫힌 주간 앵커 {nclosed}/{MIN_WEEKLY} · IC 계산분 {st['n']}"
    lab, why = L.verdict(st, 1, oos_days)
    if lab == "유의":
        ok = no_st["ic"] is not None and no_st["n"] >= 2 and no_st["ci"][0] is not None and no_st["ci"][0] > 0
        if not ok:
            lab, why = "기움", why + f" · 비겹침 앵커 계산분 {no_st['n']}개(CI {no_st['ci']}) — 2개 이상·하단>0 아니면 유의 안 줌"
    return lab, why


def combine(lab_pool, lab_mkt):
    """[D44 규칙 4] 한쪽이라도 '대기'면 '대기', 아니면 낮은 쪽."""
    if "대기" in (lab_pool, lab_mkt):
        return "대기"
    return min((lab_pool, lab_mkt), key=lambda x: LABEL_ORDER[x])


def _fmt(st):
    icx = "—" if st["ic"] is None else f"{st['ic']:+.4f}"
    cix = "—" if st["ci"][0] is None else f"[{st['ci'][0]:+.4f}, {st['ci'][1]:+.4f}]"
    posx = "—" if st["pos"] is None else f"{st['pos']:.0%}"
    return icx, cix, posx


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

    def sub(rids):
        return s[s["run_id"].astype(str).isin(rids)]

    daily = L.model_ic(s, close, N, didx, excl, reg=reg)
    weekly = L.model_ic(sub(keep_weekly), close, N, didx, excl, reg=reg)
    p_daily = pooled_ic(s, close, N, didx, excl, reg=reg)
    p_weekly = pooled_ic(sub(keep_weekly), close, N, didx, excl, reg=reg)
    nonov, p_nonov = {}, {}
    for h in (60, 120):
        ss = nonoverlap_subset(keep_weekly, didx, h)
        nonov[h] = (L.model_ic(sub(ss), close, N, didx, excl, reg=reg)[h], len(ss))
        p_nonov[h] = pooled_ic(sub(ss), close, N, didx, excl, reg=reg)["pooled"][h]

    today = dates[-1]
    first_t = min(L.anchor(r, didx) for r in keep_daily) if keep_daily else None
    lines = [f"# 대형 트랙 ls_t1 — §9 판정 상태 (기준일 {today}, 생성 {dt.datetime.now():%Y-%m-%d %H:%M})", "",
             f"- 등록 {reg} · 등록 후 경과 거래일(일간 앵커, 게이트·중복 제거 후) **{daily['oos_days']}** · 주간 앵커 {len(keep_weekly)}개 · "
             f"시세 종목 {close.shape[1]:,}(보충표 포함) · 게이트 제외 run {len(excl)}.",
             "- 규칙은 이 파일 머리말(2026-10-03 고정). 판정은 h60·h120 주간 앵커, 라벨은 §11 과 같은 규칙(분모 1) + 주간 앵커 8개 미만이면 '대기'.",
             f"- 순위 상관은 두 가지를 각각 판정해 **낮은 쪽 라벨**을 준다(2026-11-16 결정 D44 — 원문 DECISIONS_LOG.md). "
             f"전 유니버스 = 시장 구분 없이 한 순위(설계 §9 문구, 앞에 내세우는 값) · 시장별 평균 = 시장 안 상관의 평균(리더보드와 같은 방식).", ""]
    lines += ["| h | 기준 | 창 닫힌 앵커 n | IC | 95% CI | 주별 양(+) | 라벨 |", "|---|---|---|---|---|---|---|"]
    verdicts = {}
    for h in HS:
        for tag, st, pst, rids in (("일간(참고)", daily[h], p_daily["pooled"][h], keep_daily),
                                   ("주간(정본)", weekly[h], p_weekly["pooled"][h], keep_weekly)):
            nclosed = closed_count(rids, didx, N, h)
            if tag.startswith("주간") and h in (60, 120):
                lab_m, why_m = label_one(st, nclosed, nonov[h][0], daily["oos_days"])
                lab_p, why_p = label_one(pst, nclosed, p_nonov[h], daily["oos_days"])
                verdicts[h] = (combine(lab_p, lab_m), lab_p, why_p, lab_m, why_m, nclosed)
            else:
                lab_m = lab_p = "참고" if h == 20 else ("대기" if nclosed < MIN_WEEKLY else "참고")
            for name, x, lab in (("전 유니버스", pst, lab_p), ("시장별 평균", st, lab_m)):
                icx, cix, posx = _fmt(x)
                lines.append(f"| h{h} | {tag} · {name} | {nclosed}/{len(rids)} | {icx} | {cix} | {posx} | {lab} |")
    lines.append("")
    for h in (60, 120):
        no_st, no_n = nonov[h]
        icx = "—" if no_st["ic"] is None else f"{no_st['ic']:+.4f} CI[{no_st['ci'][0]:+.4f}, {no_st['ci'][1]:+.4f}]"
        pn = p_nonov[h]
        pcx = "—" if pn["ic"] is None else f"{pn['ic']:+.4f} CI[{pn['ci'][0]:+.4f}, {pn['ci'][1]:+.4f}]"
        lines.append(f"- 비겹침 앵커(h{h}): {no_n}개 중 창 닫힘 {no_st['n']} → 시장별 평균 IC {icx} · 전 유니버스 IC {pcx}.")
    if first_t is not None:
        for h in (60, 120):
            need = first_t + L.ENTRY_LAG + h
            lines.append(f"- h{h} 첫 창이 닫히는 거래일: {'이미 닫힘' if need < N else f'앞으로 {need - N + 1}거래일 뒤'} "
                         f"(첫 앵커 {dates[first_t]}). 주간 앵커 {MIN_WEEKLY}개가 닫히려면 그로부터 약 7주 더.")
    lines += ["", "## 판정"]
    for h in (60, 120):
        lab, lab_p, why_p, lab_m, why_m, nclosed = verdicts[h]
        lines.append(f"- **h{h}: {lab}** (두 정의 중 낮은 쪽) — 전 유니버스 **{lab_p}**: {why_p} / 시장별 평균 **{lab_m}**: {why_m}")

    # [D44 규칙 6] 정의를 정하기 전에 창이 닫힌 주간 앵커를 뺀 감도 — 같이 적기만 한다(대신 쓰지 않는다)
    lines += ["", f"## 감도 — 정의를 정한 날({DECISION_DATE}) 종가까지 창이 닫힌 주간 앵커를 뺀 값"]
    for h in (60, 120):
        pre = {r for r in keep_weekly
               if L.anchor(r, didx) + L.ENTRY_LAG + h < N and dates[L.anchor(r, didx) + L.ENTRY_LAG + h] <= DECISION_DATE}
        rest = keep_weekly - pre
        nclosed = closed_count(rest, didx, N, h)
        w_st = L.model_ic(sub(rest), close, N, didx, excl, reg=reg)[h]
        p_st = pooled_ic(sub(rest), close, N, didx, excl, reg=reg)["pooled"][h]
        ss = nonoverlap_subset(rest, didx, h)
        w_no = L.model_ic(sub(ss), close, N, didx, excl, reg=reg)[h]
        p_no = pooled_ic(sub(ss), close, N, didx, excl, reg=reg)["pooled"][h]
        lab_m, _ = label_one(w_st, nclosed, w_no, daily["oos_days"])
        lab_p, _ = label_one(p_st, nclosed, p_no, daily["oos_days"])
        pi, pc, _ = _fmt(p_st); wi, wc, _ = _fmt(w_st)
        lines.append(f"- h{h}: 뺀 앵커 {len(pre)}개 · 남은 주간 앵커 중 창 닫힘 {nclosed}/{len(rest)} → 전 유니버스 {pi} {pc} ({lab_p}) · "
                     f"시장별 평균 {wi} {wc} ({lab_m}) → **{combine(lab_p, lab_m)}**")
    lines.append("- 시장별 평균의 h60 주간 값은 정의를 정하기 전에 2개가 이 파일에 보였다(11/13 기준). 전 유니버스의 h60·h120 값은 정한 뒤에 처음 계산했다.")

    lines += ["", "## 참고 — 시장별 값(판정 조건 아님)"]
    for h in (60, 120):
        bits = []
        for mk in sorted(k for k in p_weekly if k != "pooled"):
            icx, cix, posx = _fmt(p_weekly[mk][h])
            bits.append(f"{mk} {icx} {cix} n={p_weekly[mk][h]['n']}")
        lines.append(f"- h{h} 주간: " + " · ".join(bits))

    lines += ["", "- 리더보드 ls_t1 h20 참고값과 '일간(참고) · 시장별 평균 h20' 줄이 같아야 한다(같은 함수·같은 시세). 다르면 코드를 의심.",
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
