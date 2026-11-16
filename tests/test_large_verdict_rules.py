# -*- coding: utf-8 -*-
"""대형 ls_t1 판정(large_verdict) 규칙 회귀 테스트 (합성 — DB 불필요, 파일 안 씀)

왜: 닫힌 주간 앵커가 8개가 될 때까지 '대기' 다음 줄들(라벨 매기기·낮은 쪽 고르기)은 실제 자료로 한 번도 돌지 않는다.
    12월 말 판정 날 처음 도는 길을 가짜 자료로 미리 돌린다(2026-11-16 Codex 점검 A-3·A-5 제안).

고정하는 규칙 (DECISIONS_LOG.md D44 세부 규칙 · 2026-10-03 절차):
  1. label_one: 날짜상 닫힌 수·계산분 중 하나라도 8 미만이면 '대기'.
  2. '유의'는 비겹침 앵커 계산분 2개 이상이고 그 구간 하단 > 0 일 때만, 아니면 '기움'.
  3. combine: 한쪽이라도 '대기'면 '대기', 아니면 역작동 < 노이즈 < 기움 < 유의 중 낮은 쪽(순서 무관).
  4. leaderboard.verdict 가 내는 라벨은 전부 LABEL_ORDER 에 있다(새 라벨이 생기면 여기서 걸린다).
  5. 주간 앵커 = ISO 주 첫 앵커 · 비겹침 = h거래일 이상 간격 · 닫힘 = 앵커 + 진입 1일 + h 가 달력 안.
  6. 전 유니버스 값은 모든 시장(둘 이상)이 최소 조건을 채운 앵커에서만 — 한 시장이 모자란 앵커·한 시장뿐인 앵커는
     시장별 평균에는 남고 전 유니버스에서는 빠진다(공통 앵커).
  7. 끝까지 한 번(run() 과 같은 순서로 호출): 닫힌 앵커 7개 → 대기 · 8개인데 비겹침 1개 → 기움 · 비겹침 2개 → 유의 ·
     시장 안에서는 맞고 시장 사이가 거꾸로면 시장별 평균 '유의' + 전 유니버스 '역작동' → 최종 '역작동'.
  8. 감도(D44 규칙 6): 창 끝 날짜가 정한 날(20261116)과 같거나 앞이면 '정하기 전에 닫힌 것'으로 빠지고, 다음 거래일이면 남는다.
실행: python tests/test_large_verdict_rules.py
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import leaderboard as L
import large_verdict as lv

P = 0
def check(n, c, info=""):
    global P
    assert c, f"FAIL: {n} {info}"
    P += 1
    print(f"  ok  {n}" + (f"  [{info}]" if info else ""))


def st(ic, lo, hi, pos, n):
    return dict(ic=ic, n=n, ci=[lo, hi], pos=pos)

NONE = dict(ic=None, n=0, ci=[None, None], pos=None)
GOOD = st(0.20, 0.05, 0.35, 0.8, 8)          # 구간 하단 > 0 · 양수 비율 ≥ 60%
NO2 = st(0.15, 0.01, 0.30, 1.0, 2)           # 비겹침 2개·하단 > 0
OOS = 60

# ── 1·2. label_one ───────────────────────────────────────────────────────
print("label_one")
check("계산분 7 → 대기", lv.label_one(st(0.2, 0.05, 0.35, 0.8, 7), 8, NO2, OOS)[0] == "대기")
check("날짜상 닫힘 7 → 대기", lv.label_one(GOOD, 7, NO2, OOS)[0] == "대기")
check("값 없음(n=0) → 대기", lv.label_one(NONE, 0, NONE, OOS)[0] == "대기")
check("8개·비겹침 2개·하단>0 → 유의", lv.label_one(GOOD, 8, NO2, OOS)[0] == "유의")
check("비겹침 1개 → 기움", lv.label_one(GOOD, 8, st(0.15, 0.15, 0.15, 1.0, 1), OOS)[0] == "기움")
check("비겹침 0개 → 기움", lv.label_one(GOOD, 8, NONE, OOS)[0] == "기움")
check("비겹침 2개인데 하단 ≤ 0 → 기움", lv.label_one(GOOD, 8, st(0.15, -0.01, 0.30, 0.5, 2), OOS)[0] == "기움")
check("비겹침 하단이 정확히 0 → 기움(0 은 '위'가 아님)", lv.label_one(GOOD, 8, st(0.15, 0.0, 0.30, 1.0, 2), OOS)[0] == "기움")
check("구간이 0 에 걸침·IC>+0.03 → 기움", lv.label_one(st(0.10, -0.01, 0.20, 0.7, 8), 8, NO2, OOS)[0] == "기움")
check("0 근처 → 노이즈", lv.label_one(st(0.01, -0.10, 0.10, 0.5, 8), 8, NO2, OOS)[0] == "노이즈")
check("IC < −0.03 → 역작동", lv.label_one(st(-0.10, -0.20, -0.01, 0.2, 8), 8, NO2, OOS)[0] == "역작동")
check("양수 비율 60% 미만이면 유의 아님", lv.label_one(st(0.20, 0.05, 0.35, 0.5, 8), 8, NO2, OOS)[0] != "유의")

# ── 3·4. combine · 라벨 집합 ─────────────────────────────────────────────
print("combine")
ORDER = ["역작동", "노이즈", "기움", "유의"]
for a in ORDER + ["대기"]:
    for b in ORDER + ["대기"]:
        want = "대기" if "대기" in (a, b) else ORDER[min(ORDER.index(a), ORDER.index(b))]
        assert lv.combine(a, b) == want and lv.combine(b, a) == want, f"FAIL: combine({a},{b})"
check("combine 25쌍 — 대기 우선·낮은 쪽·순서 무관", True)
seen = {L.verdict(s_, 1, OOS)[0] for s_ in (GOOD, st(0.10, -0.01, 0.20, 0.7, 8), st(0.01, -0.10, 0.10, 0.5, 8),
                                            st(-0.10, -0.20, -0.01, 0.2, 8), NONE)} | {L.verdict(GOOD, 1, 10)[0]}
check("leaderboard.verdict 라벨 ⊂ LABEL_ORDER", seen <= set(lv.LABEL_ORDER), str(sorted(seen)))
check("LABEL_ORDER 순서 = 역작동<노이즈<기움<유의", [k for k, _ in sorted(lv.LABEL_ORDER.items(), key=lambda x: x[1])] == ORDER)

# ── 합성 자료 ────────────────────────────────────────────────────────────
DATES = [d.strftime("%Y%m%d") for d in pd.bdate_range("2026-08-03", periods=140)]   # 2026-08-03 = 월요일
KS = [f"K{i:02d}" for i in range(1, 13)]; QS = [f"Q{i:02d}" for i in range(1, 13)]


def make_close(n_days, inverted):
    """종목마다 하루 성장률이 일정 → 어느 앵커·어느 기간에서도 수익 순위 = 성장률 순위(점프 없음).
    aligned: 코스피(점수 높음)가 수익도 높음 → 두 정의 모두 +1. inverted: 시장 안에서는 맞지만 코스닥(점수 낮음)이 통째로 더 오름."""
    g = {}
    for i, k in enumerate(KS, 1):
        g[k] = (0.0001 * i) if inverted else (0.0030 + 0.0001 * i)
    for i, q in enumerate(QS, 1):
        g[q] = (0.0040 + 0.0001 * i) if inverted else (0.0001 * i)
    t = np.arange(n_days)
    return pd.DataFrame({k: 100 * np.exp(v * t) for k, v in g.items()}, index=DATES[:n_days])


def make_scores(n_runs=100, thin=None, one_market=None):
    """매 거래일 run. 코스피 점수 0.5~1.0, 코스닥 0~0.5(대형 가치 점수가 코스피로 쏠린 모양).
    thin: 그 run 의 코스닥을 5종목만(시장별 최소 8 미달) · one_market: 그 run 은 코스피만."""
    rows = []
    for rid in DATES[:n_runs]:
        for i, k in enumerate(KS, 1):
            rows.append((rid, "kospi", k, 0.5 + i / 24))
        if rid == one_market:
            continue
        for i, q in enumerate(QS, 1):
            if rid == thin and i > 5:
                continue
            rows.append((rid, "kosdaq", q, i / 24))
    return pd.DataFrame(rows, columns=["run_id", "market", "ticker", "score"])


def judge(s, close, h=60):
    """large_verdict.run() 의 판정 부분과 같은 순서로 부른다(DB·파일 없음)."""
    L.HORIZONS = lv.HS
    dates = list(close.index); N = len(dates); didx = {d: i for i, d in enumerate(dates)}; excl = set()
    keep_daily = L.dedupe_by_anchor(s, didx, excl)
    keep_weekly = lv.weekly_subset(keep_daily, didx, dates)
    sub = lambda rids: s[s["run_id"].astype(str).isin(rids)]
    daily = L.model_ic(s, close, N, didx, excl)
    weekly = L.model_ic(sub(keep_weekly), close, N, didx, excl)
    p_weekly = lv.pooled_ic(sub(keep_weekly), close, N, didx, excl)
    ss = lv.nonoverlap_subset(keep_weekly, didx, h)
    no_m = L.model_ic(sub(ss), close, N, didx, excl)[h]
    no_p = lv.pooled_ic(sub(ss), close, N, didx, excl)["pooled"][h]
    nclosed = lv.closed_count(keep_weekly, didx, N, h)
    lab_m, _ = lv.label_one(weekly[h], nclosed, no_m, daily["oos_days"])
    lab_p, _ = lv.label_one(p_weekly["pooled"][h], nclosed, no_p, daily["oos_days"])
    return dict(final=lv.combine(lab_p, lab_m), pooled=lab_p, market=lab_m, nclosed=nclosed, w=weekly[h], p=p_weekly["pooled"][h],
                no_m=no_m, no_p=no_p, weekly=keep_weekly, nonov=ss, didx=didx, p_all=p_weekly)

_horizons = list(L.HORIZONS)
try:
    # ── 5. 앵커 고르기 ───────────────────────────────────────────────────
    print("앵커")
    r = judge(make_scores(), make_close(140, inverted=False))
    wk_t = sorted(r["didx"][x] for x in r["weekly"])
    check("주간 앵커 = 매주 첫 거래일(월요일) 20개", wk_t == list(range(0, 100, 5)), str(wk_t[:4]))
    check("비겹침(h60) = 60거래일 간격", sorted(r["didx"][x] for x in r["nonov"]) == [0, 60])
    check("닫힘 = t+1+60 < 140 → t ≤ 78 → 16개", r["nclosed"] == 16 and r["w"]["n"] == 16)

    # ── 7. 끝까지 한 번 ──────────────────────────────────────────────────
    print("끝까지")
    check("두 정의 모두 +1 · 비겹침 2개 → 유의", (r["final"], r["pooled"], r["market"]) == ("유의", "유의", "유의")
          and r["w"]["ic"] == 1.0 and r["p"]["ic"] == 1.0 and r["no_m"]["n"] == 2 and r["no_p"]["n"] == 2)
    r96 = judge(make_scores(), make_close(96, inverted=False))
    check("닫힌 주간 앵커 7개(N=96) → 대기", r96["nclosed"] == 7 and r96["final"] == "대기", f"nclosed {r96['nclosed']}")
    r97 = judge(make_scores(), make_close(97, inverted=False))
    check("닫힌 주간 앵커 8개(N=97)·비겹침 계산분 1개 → 기움", r97["nclosed"] == 8 and r97["no_m"]["n"] == 1 and r97["final"] == "기움",
          f"nclosed {r97['nclosed']} · 비겹침 {r97['no_m']['n']}")
    ri = judge(make_scores(), make_close(140, inverted=True))
    check("시장 안 +1 · 시장 사이 거꾸로 → 시장별 평균 유의 + 전 유니버스 역작동 → 역작동",
          (ri["final"], ri["pooled"], ri["market"]) == ("역작동", "역작동", "유의") and ri["w"]["ic"] == 1.0 and ri["p"]["ic"] < -0.4,
          f"전 유니버스 IC {ri['p']['ic']:+.4f}")

    # ── 6. 공통 앵커 ─────────────────────────────────────────────────────
    print("공통 앵커")
    rt = judge(make_scores(thin=DATES[10], one_market=DATES[20]), make_close(140, inverted=False))
    check("코스닥 5종목뿐인 앵커 + 코스피만 있는 앵커 → 시장별 평균 16 · 전 유니버스 14",
          rt["w"]["n"] == 16 and rt["p"]["n"] == 14, f"시장별 {rt['w']['n']} · 전 유니버스 {rt['p']['n']}")
    check("시장별 참고값: 코스피 16 · 코스닥 14", rt["p_all"]["kospi"][60]["n"] == 16 and rt["p_all"]["kosdaq"][60]["n"] == 14)
    # ── 8. 감도 경계 [D44 규칙 6] ────────────────────────────────────────
    print("감도 경계")
    didx = {d: i for i, d in enumerate(DATES)}
    wk = sorted(r["weekly"])                                  # 주간 앵커 t = 0, 5, 10, …
    end_of = lambda rid: DATES[didx[rid] + L.ENTRY_LAG + 60]  # 그 앵커의 h60 창이 끝나는 날
    cut = end_of(wk[2])                                       # t=10 앵커의 창이 '정한 날'에 정확히 끝난다고 놓는다
    pre = lv.pre_decision_set(set(wk), didx, DATES, len(DATES), 60, decision=cut)
    check("창 끝 = 정한 날 → '정하기 전에 닫힌 것'에 들어간다(감도에서 빠짐)", wk[2] in pre and pre == set(wk[:3]), f"정한 날 {cut}")
    check("창 끝이 정한 날 다음 거래일 → 안 빠진다", wk[3] not in pre and end_of(wk[3]) > cut)
    day_before = DATES[didx[cut] - 1]
    check("정한 날을 하루 앞당기면 그 앵커도 안 빠진다", lv.pre_decision_set(set(wk), didx, DATES, len(DATES), 60, decision=day_before) == set(wk[:2]))
    check("창이 아직 안 닫힌 앵커는 날짜와 무관하게 안 빠진다", lv.pre_decision_set(set(wk), didx, DATES, len(DATES), 60, decision="99999999") == {x for x in wk if didx[x] + 61 < len(DATES)})
    check("정한 날 상수 = 20261116", lv.DECISION_DATE == "20261116")

    one = lv.pooled_ic(make_scores(one_market=DATES[0]).query("run_id == @DATES[0]"), make_close(140, False), 140,
                       {d: i for i, d in enumerate(DATES)}, set())
    check("한 시장뿐인 자료 → 전 유니버스 값 없음(n=0, 키는 있음)", one["pooled"][60]["n"] == 0 and one["pooled"][60]["ic"] is None)
finally:
    L.HORIZONS = _horizons

print(f"\n✅ test_large_verdict_rules: {P} 통과")
