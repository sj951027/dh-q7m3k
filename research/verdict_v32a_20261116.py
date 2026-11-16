# -*- coding: utf-8 -*-
"""verdict_v32a_20261116.py — v32a(v3 챌린저 · REG 20261026 · 짝 v30) 판정 계산 도구

준비 2026-11-16 — **D20 완결 앵커가 0개일 때 썼다**(첫 완결 ≈11/24). 판정은 유효 앵커 40 도달 다음 배치 뒤 1회(≈12/21~, PROMISES P04).
정본: `PREREGISTER_v32a.md` §2~§4 → 없는 항목은 `VERDICT_RULES.md` 기본값 → 대조표는 `VERDICT_CHECKLIST.md` §3·§5.

무엇을 재나 (사전등록 §2 그대로):
  바구니 = 앵커·시장·모델마다 점수 > −999 중 점수 내림차순·동점 종목코드 순 상위 10(모자라면 있는 만큼) — `build_v32a_page.top` 을 그대로 쓴다.
  D20   = (v32a 바구니 − v30 바구니) 동일가중 h20 수익 차. 진입 = 추천 다음 거래일 종가(없거나 0 이하면 그 종목 현금, 평균은 체결분만),
          청산 = 20거래일 뒤 종가(없으면 마지막 가격). **두 시장 모두 산출될 때만** 두 시장 평균, 아니면 'D 산출 불가'(표본에서 빼고 개수 병기).
          가격 = ohlcv.db 본표(보충표 미사용) · 비용 0 · 점프컷 없음 · 희석 제외 없음.
  구간  = 앵커 D 의 iid 부트스트랩 4,000회 seed 7 95% · Bonferroni (1 − 0.05/분모, 분모 8 — 실측과 다르면 둘 다) · 주블록(월~일 달력 주) 감도.
  주별  = 주별 평균 D20 > 0 인 주 비율 ≥ 60%.   보조 = D10(사후 출신 재현 조건) · D40(표기만) · 같은 셀 IC(참고, 리더보드 함수).
  라벨  = 사전등록 §3 해석표 6칸 + 나머지(위에서부터 첫 번째). 리더보드 자동 라벨은 쓰지 않는다.
  참고(§4 — 라벨에 안 씀) = 체결 한도 세 단(주문 100만/300만/1,000만원 ≤ 21일 평균 거래대금 × 1% 인 종목만 남긴 D20) · 시장별 D20 ·
          바구니 겹침·거래대금 중앙·비겹침 앵커 수 · 국면(코스피 20일 ≤ −5%).
  각주 ④ = 겹치지 않는 앵커 수 · 하루 지속성 · 자리바꿈 백분위(2,000회·seed 20261012) + 시총 5분위 안에서만 섞는 감도(`VERDICT_NOTE_20261011_power.md`).
          자리바꿈 = 창 안에 나온 종목을 같은 시장 안에서 1:1 로 뒤섞어 두 모델에 같은 이름표를 붙임(바구니 차이라 '차이의 분포'가 곧 주지표의 분포).

쓰는 법 (읽기 전용 · 화면 출력만 · 파일을 만들지 않는다):
  python research/verdict_v32a_20261116.py                 # 유효 앵커 40 미만이면 **개수만** 보여 주고 끝난다(값은 숨김)
  python research/verdict_v32a_20261116.py --interim       # 40 미만이어도 값을 본다(중간 관측 — 판정 아님)
  python research/verdict_v32a_20261116.py --asof 20261221 # 그날까지의 가격·run 으로 자른다(추기·재현용)
  python research/verdict_v32a_20261116.py --model v31c    # 리허설: 다른 모델(창이 다 닫힌 것)로 같은 길을 끝까지 돌려 본다 — v32a 값이 아니다
  --perm N (기본: 판정 가능하면 2,000, 아니면 0)

계산 핵심은 순수 함수(ret_matrix·build_baskets·d_table·week_block_ci·interpret·strata_perm) — `tests/test_v32a_verdict_rules.py`.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from lib.verdict_util import strata_perm, cap_quintiles, first_cap   # noqa: E402  (자리바꿈의 층 나누기 — lv_e 2차 창 도구와 공용)

MODEL, REF = "v32a", "v30"
BOOT, SEED = 4000, 7
DEN_PRE = 8                      # 사전등록 §2 분모
GOAL = 40                        # 판정 조건: 유효 앵커
TIERS = (100, 300, 1000)         # 주문 크기(만원) — §4-1
PERM_SEED = 20261012
MARKETS = ("kospi", "kosdaq")
A_CUT = -0.05                    # 국면 각주: 코스피 20일 등락 ≤ −5%


# ── 순수 함수 ────────────────────────────────────────────────────────────
def boot_ci(a, lo=2.5, hi=97.5, seed=SEED, boot=BOOT):
    """앵커 값의 iid 부트스트랩 구간(판정 도구 공통 방식: seed 7 · 4,000회)."""
    a = np.asarray(a, float)
    if len(a) == 0:
        return None
    rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(boot)]
    return float(np.percentile(b, lo)), float(np.percentile(b, hi))


def week_of(datestr):
    """월~일 달력 주의 이름표(그 주 월요일 날짜)."""
    d = pd.Timestamp(datestr)
    return (d - pd.Timedelta(days=d.weekday())).strftime("%Y%m%d")


def week_block_ci(vals, weeks, lo=2.5, hi=97.5, seed=SEED, boot=BOOT):
    """주 블록 부트스트랩: 주를 복원추출해 그 주의 앵커를 이어 붙인 평균. 주가 2개 미만이면 None(산출 불가)."""
    vals = np.asarray(vals, float); weeks = np.asarray(weeks)
    blocks = [vals[weeks == w] for w in sorted(set(weeks))]
    if len(blocks) < 2:
        return None
    rng = np.random.default_rng(seed)
    means = [np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))]).mean() for _ in range(boot)]
    return float(np.percentile(means, lo)), float(np.percentile(means, hi)), len(blocks)


def weekly_pos(vals, weeks):
    """주별 평균이 양(+)인 주의 비율, 주 수."""
    if len(vals) == 0:
        return None, 0
    s = pd.Series(np.asarray(vals, float)).groupby(np.asarray(weeks)).mean()
    return float((s > 0).mean()), int(len(s))


def nonoverlap(ts, h):
    """앞에서 고른 앵커보다 h 거래일 이상 뒤인 것만 차례로 고른 위치 목록."""
    out, last = [], None
    for t in sorted(ts):
        if last is None or t - last >= h:
            out.append(t); last = t
    return out


def ret_matrix(close, ts, h):
    """앵커 위치 ts → (앵커 × 종목) h 수익(%). 진입 = t+1 종가(없거나 0 이하면 NaN = 못 삼 — 현금), 청산 = t+1+h 의 마지막 가격(ffill).
    창이 안 닫힌 앵커(t+1+h 가 달력 밖)는 줄 전체 NaN. 반환 (R, done)."""
    c = close.to_numpy(float); f = close.ffill().to_numpy(float); N = len(c)
    R = np.full((len(ts), c.shape[1]), np.nan); done = np.zeros(len(ts), bool)
    for i, t in enumerate(ts):
        e, x = t + 1, t + 1 + h
        if x < N:
            done[i] = True
            ok = np.isfinite(c[e]) & (c[e] > 0) & np.isfinite(f[x])
            R[i, ok] = (f[x, ok] / c[e, ok] - 1) * 100
    return R, done


def build_baskets(S, rids, models, top_fn, n=10):
    """S(run_id, market, ticker, model_id, score) → {(rid, mkt, mid): [종목 …]} — 바구니 규칙은 top_fn(= build_v32a_page.top) 하나."""
    out = {}
    S = S[S.run_id.isin(set(rids)) & S.model_id.isin(models)].dropna(subset=["score"])
    for (rid, mkt, mid), g in S.groupby(["run_id", "market", "model_id"]):
        out[(rid, mkt, mid)] = list(top_fn(g.rename(columns={"score": "final_score_v3"}), n=n)["ticker"])
    return out


def d_table(R, done, rids, baskets, col, models=(MODEL, REF), remap=None, allow=None):
    """앵커별 D(%p). col = {종목: R 의 열 번호}. remap = {종목: 종목'}(자리바꿈) · allow = {(rid, mkt): 살 수 있는 종목 집합}(체결 한도).
    시장별: 두 바구니 모두 체결분이 1개 이상이어야 그 시장의 차이가 나온다. 두 시장 모두 나와야 D(ok). 반환 DataFrame."""
    rows = []
    for i, rid in enumerate(rids):
        rec = dict(run_id=rid, done=bool(done[i]), ok=False, D=np.nan)
        for mkt in MARKETS:
            d = np.nan
            if done[i]:
                r = {}
                for mid in models:
                    tk = baskets.get((rid, mkt, mid), [])
                    if allow is not None:
                        ok_set = allow.get((rid, mkt), set()); tk = [k for k in tk if k in ok_set]
                    if remap is not None:
                        tk = [remap.get(k, k) for k in tk]
                    idx = [col[k] for k in tk if k in col]
                    v = R[i, idx] if idx else np.array([])
                    v = v[np.isfinite(v)]
                    r[mid] = float(v.mean()) if len(v) else np.nan
                d = r[models[0]] - r[models[1]]
            rec[f"D_{mkt}"] = d
        ds = [rec[f"D_{m}"] for m in MARKETS]
        if rec["done"] and all(np.isfinite(ds)):
            rec["ok"], rec["D"] = True, float(np.mean(ds))
        rows.append(rec)
    return pd.DataFrame(rows, columns=["run_id", "done", "ok", "D"] + [f"D_{m}" for m in MARKETS])


def summarize(vals, weeks, denoms):
    """D 값 묶음 → 구간들. denoms = Bonferroni 분모 목록."""
    vals = np.asarray(vals, float)
    out = dict(n=len(vals), mean=float(vals.mean()) if len(vals) else None, iid=boot_ci(vals), bonf={}, wb=None, wb_bonf={}, wpos=None, nweeks=0)
    if len(vals):
        for dn in denoms:
            a = 100 * (0.05 / dn) / 2
            out["bonf"][dn] = boot_ci(vals, a, 100 - a)
            out["wb_bonf"][dn] = week_block_ci(vals, weeks, a, 100 - a)
        out["wb"] = week_block_ci(vals, weeks)
        out["wpos"], out["nweeks"] = weekly_pos(vals, weeks)
    return out


def fast_summary(vals, weeks, dn, seed=SEED, boot=BOOT):
    """summarize() 와 같은 모양을 한 번에 뽑는 빠른 판(자리바꿈 반복용 — 난수 순서가 달라 끝자리는 정본 구간과 다르다. 정본 숫자에는 쓰지 않는다)."""
    vals = np.asarray(vals, float); n = len(vals)
    out = dict(n=n, mean=float(vals.mean()) if n else None, iid=None, bonf={}, wb=None, wpos=None, nweeks=0)
    if not n:
        return out
    rng = np.random.default_rng(seed)
    b = vals[rng.integers(0, n, (boot, n))].mean(1); a = 100 * (0.05 / dn) / 2
    out["iid"] = (float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5)))
    out["bonf"][dn] = (float(np.percentile(b, a)), float(np.percentile(b, 100 - a)))
    wk = pd.factorize(np.asarray(weeks))[0]; nb = int(wk.max()) + 1
    s = np.bincount(wk, vals, nb); c = np.bincount(wk, minlength=nb)
    if nb >= 2:
        idx = rng.integers(0, nb, (boot, nb)); m = s[idx].sum(1) / c[idx].sum(1)
        out["wb"] = (float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)), nb)
    out["wpos"], out["nweeks"] = float(((s / c) > 0).mean()), nb
    return out


def interpret(n_valid, n_done, d20, d10, dn):
    """사전등록 §3 해석표 — 위에서부터 첫 번째. d20·d10 = summarize() 결과, dn = 쓸 Bonferroni 분모. 반환 (라벨, 사정)."""
    if n_valid < GOAL:
        return "판정 전", f"유효 앵커 {n_valid}/{GOAL} — 중간 관측(라벨 아님)"
    if n_done == 0 or d20["n"] == 0:
        return "판정불가", f"h20 완결 앵커 {n_done} · D 산출 가능 앵커 {d20['n']}"
    lo, hi = d20["iid"]; b = d20["bonf"][dn]; wb = d20["wb"]
    if lo > 0:
        miss = []
        if not (d20["wpos"] is not None and d20["wpos"] >= 0.60): miss.append("주별 양 < 60%")
        if not b[0] > 0: miss.append(f"보정(분모 {dn}) 하단 ≤ 0")
        if not (d10 and d10["n"] and d10["iid"][0] > 0): miss.append("D10 재현 하단 ≤ 0")
        if not (wb is not None and wb[0] > 0): miss.append("주블록 하단 ≤ 0" if wb is not None else "주블록 산출 불가")
        return ("유의", "다섯 조건 모두 충족") if not miss else ("기움", "미달: " + " · ".join(miss))
    if hi >= 0:
        return "노이즈", "D20 구간이 0 을 걸침"
    # 여기부터 iid 상단 < 0
    if wb is not None and b[1] < 0 and wb[1] < 0:
        return "역작동(유의)", "iid·보정·주블록 상단 모두 < 0"
    if (b[0] <= 0 <= b[1]) or (wb is not None and wb[0] <= 0 <= wb[1]):
        return "역작동(유의 아님)", "iid 상단 < 0 이나 보정 또는 주블록이 0 을 걸침"
    return "노이즈", "(나머지 칸 — 보수적으로 노이즈) iid 상단 < 0 인데 " + ("주블록 산출 불가" if wb is None else "주블록 구간이 0 을 걸치지도 전부 음수도 아님")


def fmt_ci(c, d=2):
    return "—" if c is None else f"[{c[0]:+.{d}f}, {c[1]:+.{d}f}]"


# ── 자료 읽기(읽기 전용) ─────────────────────────────────────────────────
def load(model, ref, asof):
    import leaderboard as lb
    close, mktmap = lb.load_ohlcv()                       # 본표만(보충표 미사용 — 사전등록 §2)
    close.index = close.index.astype(str)
    if asof:
        close = close.loc[:asof]
    con = sqlite3.connect(f"file:{REPO / 'history.db'}?mode=ro", uri=True)
    reg = lb.REG_DATE.get(model)
    hi = asof or "99999999"
    S = pd.read_sql("SELECT run_id, market, ticker, model_id, final_score_v3 AS score FROM v3_scores "
                    "WHERE model_id IN (?, ?) AND run_id >= ? AND run_id <= ?", con, params=[model, ref, reg, hi])
    S["run_id"] = S.run_id.astype(str); S["ticker"] = S.ticker.astype(str); S["market"] = S.market.str.lower()
    den = con.execute("SELECT COUNT(DISTINCT model_id) FROM v3_scores WHERE run_id <= ?", [hi]).fetchone()[0]
    amt = pd.read_sql('SELECT run_id, market, ticker, "amt_avg_1m_억" AS amt FROM stage3_final WHERE run_id >= ? AND run_id <= ?', con, params=[reg, hi])
    amt["run_id"] = amt.run_id.astype(str); amt["ticker"] = amt.ticker.astype(str); amt["market"] = amt.market.str.lower()
    partial, dbl, didx = lb.build_gates(con, close.index)
    con.close()
    ocon = sqlite3.connect(f"file:{Path(lb.OHLCV_DB)}?mode=ro", uri=True)
    kospi = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSPI' ORDER BY date", ocon)
    d0 = close.index[max(0, len(close) - 400)]
    sh = pd.read_sql("SELECT date, ticker, close, shares FROM daily_ohlcv WHERE date >= ? AND date <= ?", ocon, params=[d0, close.index[-1]])
    ocon.close()
    kospi["date"] = kospi.date.astype(str).str.replace("-", ""); kospi = kospi.set_index("date")["close"].astype(float)
    return dict(lb=lb, close=close, mktmap=mktmap, S=S, den=den, amt=amt, excl=partial | dbl, partial=partial, dbl=dbl, didx=didx, reg=reg, kospi=kospi, sh=sh)


# ── 실행 ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interim", action="store_true", help="유효 앵커 40 미만이어도 값을 출력(중간 관측 — 판정 아님)")
    ap.add_argument("--asof", default=None, help="YYYYMMDD — 그날까지의 가격·run 만 쓴다")
    ap.add_argument("--model", default=MODEL, help="리허설용: 다른 v3 모델로 같은 길을 돌린다(v32a 값이 아님)")
    ap.add_argument("--perm", type=int, default=None, help="자리바꿈 횟수(기본: 판정 가능하면 2,000 · 아니면 0)")
    a = ap.parse_args()
    import build_v32a_page as pg                          # 바구니 규칙의 단일 원천(top)
    model, rehearsal = a.model, a.model != MODEL
    D = load(model, REF, a.asof)
    lb, close, S, didx, excl, reg = D["lb"], D["close"], D["S"], D["didx"], D["excl"], D["reg"]
    dates = list(close.index); N = len(dates)
    col = {t: j for j, t in enumerate(close.columns.astype(str))}

    keep = lb.dedupe_by_anchor(S[S.model_id == model], didx, excl, reg=reg)
    rids = sorted(keep, key=lambda r: lb.anchor(r, didx)); ts = [lb.anchor(r, didx) for r in rids]
    adate = [dates[t] for t in ts]; weeks = np.array([week_of(d) for d in adate])
    n_valid = len(rids); ready = n_valid >= GOAL
    denoms = [DEN_PRE] if D["den"] == DEN_PRE else sorted({DEN_PRE, D["den"]})
    dn_use = max(denoms)                                  # 결론이 갈리면 큰 분모(VERDICT_RULES §1)

    print("=" * 100)
    if rehearsal:
        print(f"★★ 리허설 — 모델 {model} 로 같은 길을 돌린 것. **v32a 의 값이 아니다.** 분모·등록일도 {model} 의 것이 아니라 도구 점검용.")
    print(f"[{model} − {REF} 판정 도구] 가격 마지막 {dates[-1]}" + (f" (--asof {a.asof})" if a.asof else "") +
          f" · 등록일 {reg} · {'판정 가능(유효 앵커 ≥ 40)' if ready else f'★ 중간 관측 — 유효 앵커 {n_valid}/{GOAL}, 판정 아님'}")

    # §0 게이트
    R20, done20 = ret_matrix(close, ts, 20); R10, done10 = ret_matrix(close, ts, 10); R40, done40 = ret_matrix(close, ts, 40)
    bk = build_baskets(S, rids, (model, REF), pg.top)
    T20 = d_table(R20, done20, rids, bk, col, models=(model, REF)); T10 = d_table(R10, done10, rids, bk, col, models=(model, REF))
    T40 = d_table(R40, done40, rids, bk, col, models=(model, REF))
    t_reg = next((i for i, d in enumerate(dates) if d >= reg), None)
    allruns = sorted(set(S[S.model_id == model].run_id))
    last_done = dates[N - 1 - 21] if N > 21 else None      # 이 날짜까지의 앵커는 h20 이 닫혔다
    miss = [d for d in dates if d >= reg and d not in set(allruns)]
    gated = [r for r in allruns if r in excl]
    tag = lambda d: "안" if (last_done and d <= last_done) else "밖"
    print(f"\n=== §0 게이트 ===")
    print(f"  유효 앵커 {n_valid}개" + (f" [{rids[0]}~{rids[-1]}]" if rids else "") + f" · 가격 날짜 차 {N - 1 - t_reg if t_reg is not None else '—'}거래일 · "
          f"h20 완결 {int(done20.sum())} · D20 산출 가능 {int(T20.ok.sum())} · D 산출 불가(완결인데) {int((T20.done & ~T20.ok).sum())}")
    print(f"  h10 완결 {int(done10.sum())}(D10 산출 {int(T10.ok.sum())}) · h40 완결 {int(done40.sum())}(D40 산출 {int(T40.ok.sum())})")
    print(f"  창 안 run 없는 거래일: {[f'{d}(완결 범위 {tag(d)})' for d in miss] or '없음'} · 게이트 제외 run: {[f'{r}(완결 범위 {tag(r)})' for r in gated] or '없음'}"
          f" (부분 {sorted(D['partial'])} · 이중 {sorted(D['dbl'])})")
    print(f"  분모: 사전등록 {DEN_PRE} · v3_scores 실측 distinct {D['den']}" + ("" if len(denoms) == 1 else f" → 둘 다 적고 갈리면 큰 쪽({dn_use})"))
    small = [(k, len(v)) for k, v in bk.items() if len(v) < 10]
    print(f"  바구니 10개 미만: {small or '없음'}")

    if not ready and not a.interim and not rehearsal:
        print("\n  값은 출력하지 않았다(유효 앵커 40 미만). 중간 관측을 보려면 --interim. 도구 점검은 --model v31c(리허설).")
        return 0

    ok20 = T20[T20.ok]; w20 = weeks[T20.ok.to_numpy()]
    ok10 = T10[T10.ok]; w10 = weeks[T10.ok.to_numpy()]
    s20 = summarize(ok20.D.values, w20, denoms); s10 = summarize(ok10.D.values, w10, denoms)

    print(f"\n=== §1 주지표 D20 = ({model} 상위10 − {REF} 상위10) h20 수익 차, 두 시장 평균 (%p) ===")
    if s20["n"]:
        print(f"  n={s20['n']} [{ok20.run_id.min()}~{ok20.run_id.max()}]  D20 {s20['mean']:+.2f}  (중앙 {np.median(ok20.D):+.2f} · 양수 앵커 {100 * (ok20.D > 0).mean():.0f}%)")
        print(f"  iid 95% {fmt_ci(s20['iid'])}" + "".join(f" · 보정(분모 {dn}) {fmt_ci(s20['bonf'][dn])}" for dn in denoms))
        wb = s20["wb"]
        print(f"  주블록 95% {fmt_ci(wb[:2]) if wb else '산출 불가(주 < 2)'}" + (f" ({wb[2]}주)" if wb else "") +
              "".join(f" · 주블록 보정(분모 {dn}) {fmt_ci(s20['wb_bonf'][dn][:2]) if s20['wb_bonf'][dn] else '—'}" for dn in denoms))
        print(f"  주별 평균 D20 > 0 인 주: {100 * s20['wpos']:.0f}% ({s20['nweeks']}주) — 기준 60%")
        wk = ok20.assign(week=w20).groupby("week").D.agg(["mean", "size"])
        print("  주별: " + "  ".join(f"{k[4:]}~ {v['mean']:+.2f}(n{int(v['size'])})" for k, v in wk.iterrows()))
        print("  앵커별: " + " ".join(f"{r.run_id[4:]}:{r.D:+.1f}" for r in ok20.itertuples()))
    else:
        print("  D20 산출 가능 앵커 없음")

    print(f"\n=== §2 보조 ===")
    for name, s, T in (("D10(사후 출신 재현 조건)", s10, ok10), ("D40(운용 리듬 — 표기만)", summarize(T40[T40.ok].D.values, weeks[T40.ok.to_numpy()], denoms), T40[T40.ok])):
        print(f"  {name}: " + (f"n={s['n']}  {s['mean']:+.2f}  iid 95% {fmt_ci(s['iid'])}  주블록 {fmt_ci(s['wb'][:2]) if s['wb'] else '—'}" if s["n"] else "표본 없음"))
    hz = list(lb.HORIZONS)
    try:
        lb.HORIZONS = [10, 20]
        for mid in (model, REF):
            st = lb.model_ic(S[S.model_id == mid][["run_id", "market", "ticker", "score"]], close, N, didx, excl, reg=reg)
            print(f"  같은 셀 순위 상관(참고 — 리더보드 함수·2,000회·점프컷, 판정에 안 씀) {mid}: h20 {st[20]['ic']} n={st[20]['n']} CI {st[20]['ci']} · h10 {st[10]['ic']} n={st[10]['n']}")
    finally:
        lb.HORIZONS = hz

    print(f"\n=== §3 해석표 (사전등록 §3 — 위에서부터 첫 번째 · 라벨은 사용자 확정) ===")
    labs = {dn: interpret(n_valid, int(done20.sum()), s20, s10, dn) for dn in denoms}
    for dn in denoms:
        print(f"  분모 {dn}: **{labs[dn][0]}** — {labs[dn][1]}")
    if len({v[0] for v in labs.values()}) > 1:
        print(f"  → 분모에 따라 갈린다. 규약대로 큰 분모({dn_use})의 라벨을 쓴다: **{labs[dn_use][0]}**")
    if s20["n"]:
        lo, hi = s20["iid"]; b = s20["bonf"][dn_use]; wb = s20["wb"]
        rows = [("유효 앵커 ≥ 40", ready, f"{n_valid}"), ("D20 iid 하단 > 0", lo > 0, fmt_ci(s20["iid"])),
                ("주별 양 ≥ 60%", s20["wpos"] >= 0.6, f"{100 * s20['wpos']:.0f}%"), (f"보정(분모 {dn_use}) 하단 > 0", b[0] > 0, fmt_ci(b)),
                ("D10 iid 하단 > 0", bool(s10["n"] and s10["iid"][0] > 0), fmt_ci(s10["iid"]) if s10["n"] else "표본 없음"),
                ("주블록 하단 > 0", bool(wb and wb[0] > 0), fmt_ci(wb[:2]) if wb else "산출 불가"),
                ("(역작동 쪽) iid 상단 < 0", hi < 0, fmt_ci(s20["iid"])), ("(역작동 쪽) 보정·주블록 상단 모두 < 0", bool(b[1] < 0 and wb and wb[1] < 0), "")]
        for lab, ok, val in rows:
            print(f"  {'✔' if ok else '✘'} {lab}: {val}")

    print(f"\n=== §4 참고값 (라벨에 쓰지 않음) ===")
    am = D["amt"].dropna(subset=["amt"])
    amt_of = {(r.run_id, r.market, r.ticker): r.amt for r in am.itertuples()}
    for tier in TIERS:
        need = tier / 100.0                                 # 주문(만원) ≤ 거래대금(억) × 1%  ⇔  거래대금(억) ≥ 주문(만원)/100
        allow = {}
        for (rid, mkt, tk), v in amt_of.items():
            if v >= need:
                allow.setdefault((rid, mkt), set()).add(tk)
        Tt = d_table(R20, done20, rids, bk, col, models=(model, REF), allow=allow); o = Tt[Tt.ok]
        left = [np.mean([len([k for k in bk.get((rid, m, mid), []) if k in allow.get((rid, m), set())]) for rid in rids for m in MARKETS]) for mid in (model, REF)]
        print(f"  체결 한도 주문 {tier:,}만원(거래대금 ≥ {need:g}억): " + (f"D20 {o.D.mean():+.2f} iid {fmt_ci(boot_ci(o.D.values))} n={len(o)}" if len(o) else "산출 가능 앵커 없음") +
              f" · 산출 불가 {int((Tt.done & ~Tt.ok).sum())} · 바구니에 남는 종목 평균 {model} {left[0]:.1f} / {REF} {left[1]:.1f}")
    for m in MARKETS:
        v = T20[f"D_{m}"].dropna().values
        print(f"  시장별 D20 {m}: " + (f"{v.mean():+.2f} iid {fmt_ci(boot_ci(v))} n={len(v)}" if len(v) else "표본 없음"))
    ov = {m: [len(set(bk.get((rid, m, model), [])) & set(bk.get((rid, m, REF), []))) for rid in rids] for m in MARKETS}
    med = [np.median([amt_of[(rid, m, k)] for k in bk.get((rid, m, model), []) if (rid, m, k) in amt_of] or [np.nan]) for rid in rids for m in MARKETS]
    print(f"  바구니 겹침(앵커당 같은 종목 수 평균): 코스피 {np.mean(ov['kospi']):.1f} · 코스닥 {np.mean(ov['kosdaq']):.1f} · {model} 바구니 거래대금 중앙(억) 의 중앙 {np.nanmedian(med):.2f}")
    k20 = D["kospi"]; r20 = (k20 / k20.shift(20) - 1).reindex(adate)
    isA = (r20 <= A_CUT).to_numpy()[T20.ok.to_numpy()]
    for name, m in (("코스피 20일 ≤ −5%(A)", isA), ("그 밖", ~isA)):
        v = ok20.D.values[m] if len(ok20) else np.array([])
        print(f"  국면 {name}: " + (f"D20 {v.mean():+.2f} iid {fmt_ci(boot_ci(v))} n={len(v)}" if len(v) >= 3 else f"n={len(v)} (부족)"))

    print(f"\n=== 각주 ④ 참고값 (라벨에 쓰지 않음) ===")
    for h, T in ((20, T20), (10, T10)):
        tt = [t for t, okk in zip(ts, T.ok) if okk]
        print(f"  h{h} 산출 앵커 {len(tt)} → 겹치지 않는 앵커 {len(nonoverlap(tt, h))}개")
    carry, rho = [], []
    Sm = S[(S.model_id == model) & (S.score > -999)]
    for r0, r1 in zip(rids[:-1], rids[1:]):
        for m in MARKETS:
            b0, b1 = set(bk.get((r0, m, model), [])), set(bk.get((r1, m, model), []))
            if b0: carry.append(len(b0 & b1) / len(b0))
            g0 = Sm[(Sm.run_id == r0) & (Sm.market == m)].set_index("ticker").score; g1 = Sm[(Sm.run_id == r1) & (Sm.market == m)].set_index("ticker").score
            cm = g0.index.intersection(g1.index)
            if len(cm) >= 8: rho.append(g0[cm].rank().corr(g1[cm].rank()))
    if carry:
        print(f"  하루 지속성({model}, 연속 run {len(rids) - 1}쌍): 점수 순위 상관 {np.mean(rho):+.3f}(적격 종목끼리) · 하루 뒤 바구니에 남는 종목 {100 * np.mean(carry):.0f}%")

    nperm = a.perm if a.perm is not None else (2000 if ready else 0)
    if nperm > 0 and s20["n"]:
        real = s20["mean"]; names = {m: sorted(set(S[S.market == m].ticker)) for m in MARKETS}
        cap = first_cap(D["sh"], adate[0])                 # 창 안 첫 유효 close×shares
        w10_all, w20_all = weeks, weeks
        for label, strata in (("같은 시장 안", {m: np.zeros(len(names[m]), int) for m in MARKETS}),
                              ("같은 시장 × 시총 5분위 안(감도)", {m: cap_quintiles(names[m], cap).reindex(names[m]).to_numpy() for m in MARKETS})):
            rng = np.random.default_rng(PERM_SEED); means, sig, lo_pos, same = [], 0, 0, []
            for i in range(nperm):
                remap = {}
                for m in MARKETS:
                    remap.update(strata_perm(names[m], strata[m], rng))
                same.append(np.mean([k == v for k, v in remap.items()]))
                P20 = d_table(R20, done20, rids, bk, col, models=(model, REF), remap=remap); P10 = d_table(R10, done10, rids, bk, col, models=(model, REF), remap=remap)
                p20 = fast_summary(P20[P20.ok].D.values, w20_all[P20.ok.to_numpy()], dn_use) if P20.ok.any() else None
                if p20 is None:
                    continue
                means.append(p20["mean"])
                p10 = fast_summary(P10[P10.ok].D.values, w10_all[P10.ok.to_numpy()], dn_use) if P10.ok.any() else dict(n=0)
                sig += int(interpret(GOAL, 1, p20, p10, dn_use)[0] == "유의"); lo_pos += int(p20["iid"][0] > 0)
            means = np.array(means)
            tail = (means >= real).mean() if real >= 0 else (means <= real).mean()
            print(f"  자리바꿈 {len(means)}회 · {label} (seed {PERM_SEED} · 두 모델에 같은 이름표 · 제자리 비율 {100 * np.mean(same):.1f}%): "
                  f"뒤섞은 D20 2.5/50/97.5 = {np.percentile(means, 2.5):+.2f}/{np.percentile(means, 50):+.2f}/{np.percentile(means, 97.5):+.2f} · "
                  f"실제 {real:+.2f} 는 {100 * (means < real).mean():.1f} 백분위(실제보다 {'크거나 같은' if real >= 0 else '작거나 같은'} 뒤섞음 {100 * tail:.1f}%) · "
                  f"뒤섞은 점수에 '유의'(§3 다섯 조건 전부, 분모 {dn_use}) {100 * sig / len(means):.1f}% · iid 하단 > 0 만 {100 * lo_pos / len(means):.1f}%")
    else:
        print(f"  자리바꿈: 생략(--perm {nperm}) — 판정 때는 2,000회(기본값이 그렇게 켜진다)")

    print(f"\n=== 돈 관측표 (관측 계약 §2 — 2026-11-07 전 등록 모델이라 참고 병기 · 라벨 아님) ===")
    try:
        import paper_account as _pa; dil_of = _pa._dil_flags
    except Exception as e:
        dil_of = None; print(f"  (희석 제외 못 함 — paper_account import 실패: {e!r})")
    mk = D["mktmap"].astype(str).str.lower(); mk.index = mk.index.astype(str)
    cf = close.ffill()
    for mid in (model, REF):
        for cost in (0.005, 0.0035):
            rows = []
            for rid, t in zip(rids, ts):
                if t + 1 + 40 >= N:
                    continue
                ent = close.iloc[t + 1]; r40 = (cf.iloc[t + 1 + 40] / ent - 1).where(ent > 0)
                dil = dil_of(rid) if dil_of else set(); ex = []
                for m in MARKETS:
                    g = S[(S.run_id == rid) & (S.market == m) & (S.model_id == mid) & (S.score > -999)]
                    g = g[~g.ticker.isin(dil)].sort_values(["score", "ticker"], ascending=[False, True]).head(10)
                    top = r40.reindex(g.ticker).dropna(); allm = r40.reindex(mk.index[mk == m]).dropna()
                    if len(top) < 5 or len(allm) < 50:
                        continue
                    ex.append((top.mean() - cost - allm.mean()) * 100)
                if ex:
                    rows.append((t, float(np.mean(ex))))
            if not rows:
                print(f"  {mid} 비용 {cost * 100:.2f}%: 40일 완결 표본 없음"); continue
            t0 = rows[0][0]; blocks = {}
            for t, v in rows:
                blocks.setdefault((t - t0) // 40, []).append(v)
            bl = [np.array(b) for b in blocks.values()]; vals = np.array([v for _, v in rows]); rng = np.random.default_rng(SEED)
            mm = [np.concatenate([bl[i] for i in rng.integers(0, len(bl), len(bl))]).mean() for _ in range(BOOT)]
            print(f"  {mid} 비용 {cost * 100:.2f}%: 상위10 40일 초과(같은 시장 전종목 대비) {vals.mean():+.2f}%p 코호트블록 95% [{np.percentile(mm, 2.5):+.2f}, {np.percentile(mm, 97.5):+.2f}] "
                  f"n={len(rows)} · 코호트 {len(bl)}" + ("" if len(bl) >= 4 else " (코호트 < 4 → 구간은 참고·승격 판단 보류)"))

    print(f"\n=== 판정문에 옮길 대조표 자리(VERDICT_CHECKLIST §3 — v32a 는 4·8번을 D20 으로 읽는다) ===")
    print("  1 → §0 유효 앵커·가격 날짜 차 | 2 → §0 run 없는 날·게이트 제외(완결 범위 안/밖) | 3 → 해당 없음(v3 트랙 — 사후 적재 앵커 규정은 wu) | 4·8 → §1 D20 |"
          " 5 → §0 분모·§1 보정 | 6 → §1 주블록 | 7 → §2 D10 | 9 → 각주 ④(비겹침·지속성·자리바꿈·시총 5분위) | 10 → 재무 성분 각주(v3 점수 — VERDICT_RULES §1 마지막 행 문구) |"
          " 11 → 사전등록에 보류 조건 없음(§3 '판정불가'만) | 12 → 돈 관측표(참고 병기) | 13 → 해당 없음(1차 창) | 14 → 리더보드 자동 라벨은 쓰지 않음·독립 계산 대조 | 15 → PROMISES P04")
    return 0


if __name__ == "__main__":
    sys.exit(main())
