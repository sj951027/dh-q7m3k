# -*- coding: utf-8 -*-
"""build_scoreboard.py — 모델 성적표(docs/scoreboard.json) 생성 · 표시 전용 · 판정 아님 (2026-09-18)

"모델 등록일부터 매 거래일, 시장별 상위 10을 다음날 종가에 사서 40거래일 뒤 종가에 팔았다면" 을 전 모델에 같은 규칙으로 잰다.
  · 앵커/게이트/거래일 매핑은 leaderboard.py 규약(anchor · dedupe_by_anchor · build_gates) 그대로
  · 비교 = 같은 시장 전체 종목 동일가중 평균(ohlcv.db 에 그날 가격이 있는 종목) · 시장별 계산 후 평균
  · 대형(ls_t1)은 그 run 의 large_final 전체가 비교대상 (트랙 A 와 숫자 비교 금지)
  · 점프컷 없음 · 비용 0(화면에 왕복 0.35 병기) · 희석 배지 제외·PIT 유니버스·40일 블록 CI 는 미적용 → 그래서 '참고 성적'
  · 검증 결론(고정)은 docs/models_registry.json sealed, 지금 흐름(참고)은 docs/leaderboard.json h20/h5 를 그대로 옮긴다
읽기 전용(mode=ro) · 점수·판정·게이트 코드 미접촉 · 실패해도 비치명. 실행: python build_scoreboard.py
연구용 원본: research/hold40_observe.py (2026-09-17 샘플). 이 파일이 운영본.
"""
import json, re, sqlite3, sys
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); import leaderboard as lb

H = 40; TOP = 10; COST = 0.35; MIN_BASKET = 5
NAME = {"v30": "과매도 v3", "lv_b": "저변동 lv_b", "lv_a": "저변동+반전 lv_a", "lv_e": "저변동+저회전 lv_e", "mom_a": "모멘텀 mom_a",
        "mom_b": "모멘텀+눌림 mom_b", "sm_a": "초소형 sm_a", "sv_a": "공매도비중 sv_a", "sv_b": "공매도+신용 sv_b", "le_a": "저점탈출 le_a",
        "qs_a": "조용한강자 qs_a", "px_a": "가격4팩터 px_a", "ls_t1": "대형밸류 ls_t1"}
TBL = {"v3": ("v3_scores", "final_score_v3"), "lowvol": ("lowvol_scores", "lowvol_score"), "wu": ("wu_scores", "wu_score")}


def boot(a, k=2000, seed=7):
    a = np.asarray(a, float); rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(k)]; return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def load_scores(con, m):
    if m["track"] == "large":
        lg = pd.read_sql("SELECT run_id, market, ticker, per, pbr, rim_spread, div_yield FROM large_final", con)
        fz = pd.DataFrame({"ep": 1.0 / lg["per"].where(lg["per"] > 0), "bp": 1.0 / lg["pbr"].where(lg["pbr"] > 0), "rim": lg["rim_spread"], "dv": lg["div_yield"]})
        rk = fz.groupby(lg["run_id"]).rank(pct=True)
        lg["score"] = rk.mean(axis=1, skipna=True).where(rk.notna().sum(axis=1) >= 2)
        S = lg[["run_id", "market", "ticker", "score"]]
    else:
        tbl, col = TBL[m["track"]]
        S = pd.read_sql(f"SELECT run_id, market, ticker, {col} AS score FROM {tbl} WHERE model_id=?", con, params=(m["model"],))
    S = S.copy(); S["ticker"] = S.ticker.astype(str).str.zfill(6); S["run_id"] = S.run_id.astype(str); S["market"] = S.market.str.lower()
    return S


def _eta(last_ymd, n_days):
    """last_ymd 에서 n_days 거래일 뒤 날짜(M/D). 주말과 skip_dates.txt(휴장일)만 뺀다 — 공휴일 달력이 없으니 근사."""
    skips = set()
    try:
        skips = {l.strip() for l in (HERE / "skip_dates.txt").read_text(encoding="utf-8").splitlines() if l.strip()}
    except Exception:
        pass
    d = datetime.strptime(last_ymd, "%Y%m%d"); k = 0
    while k < n_days:
        d += pd.Timedelta(days=1)
        if d.weekday() < 5 and d.strftime("%Y%m%d") not in skips: k += 1
    return d.strftime("%m/%d")


def observe(con, m, close, mk, dates, didx, excl, reg_json):
    N = len(dates); S = load_scores(con, m); reg = m["reg_date"]; is_large = m["track"] == "large"
    keep = lb.dedupe_by_anchor(S, didx, excl, reg=reg)
    rows = []
    # [2026-10-02] keep 은 집합이라 도는 순서가 실행마다 달랐다 → 평균은 같아도 참고 구간(부트스트랩)이 매번 조금씩 달라졌다.
    #   날짜순으로 고정해 같은 자료면 같은 값이 나오게 한다(평균·이긴 날 등 다른 값은 순서와 무관 — 불변).
    for rid in sorted(keep):
        t = lb.anchor(rid, didx)
        if t is None or t + 1 >= N: continue
        e = close.iloc[t + 1]; done = t + 1 + H < N
        r_fix = (close.iloc[t + 1 + H] / e - 1) if done else None
        r_now = close.iloc[-1] / e - 1
        g = S[S.run_id == rid].dropna(subset=["score"])
        fx, bf, nw, bn = [], [], [], []
        pm = {}   # [2026-10-02] 시장별 초과(%p) — 상세 줄 표시용(첫 줄 숫자·검증 결론은 종전대로 두 시장 평균)
        for mkt, gm in g.groupby("market"):
            top = gm.nlargest(TOP, "score").ticker
            uni = gm.ticker if is_large else mk.index[mk == mkt]
            a = r_now.reindex(top).dropna(); b = r_now.reindex(uni).dropna()
            if len(a) >= MIN_BASKET: nw.append(a.mean() * 100); bn.append(b.mean() * 100)
            if done:
                a = r_fix.reindex(top).dropna(); b = r_fix.reindex(uni).dropna()
                if len(a) >= MIN_BASKET:
                    fx.append(a.mean() * 100); bf.append(b.mean() * 100)
                    pm[str(mkt)] = float(a.mean() * 100 - b.mean() * 100)
                    pm["_" + str(mkt)] = (float(a.mean() * 100), float(b.mean() * 100))   # [2026-10-03] 시장별 바스켓·시장 수익(표시용)
        rows.append({"date": dates[t], "done": bool(done and fx), "ret40": np.mean(fx) if fx else None, "bench40": np.mean(bf) if bf else None,
                     "ret_now": np.mean(nw) if nw else None, "bench_now": np.mean(bn) if bn else None, "pm": pm,
                     "t": t, "tops": {str(mkt): list(gm.nlargest(TOP, "score").ticker) for mkt, gm in g.groupby("market")}})   # [2026-10-03] 꾸준함 계산용
    df = pd.DataFrame(rows, columns=["date", "done", "ret40", "bench40", "ret_now", "bench_now", "pm", "t", "tops"])   # 앵커 0개(등록 직후)여도 컬럼 보장
    out = {"model": m["model"], "name": NAME.get(m["model"], m["model"]), "track": m["track"], "reg_date": reg, "n_anchors": int(len(df))}
    d = df[df.done.astype(bool)]
    if len(d):
        ex = (d.ret40 - d.bench40).values
        out["fix"] = {"n": int(len(d)), "blocks": round(len(d) / H, 1), "ret_mean": float(d.ret40.mean()), "ret_median": float(d.ret40.median()), "bench_mean": float(d.bench40.mean()),
                      "exc_mean": float(ex.mean()), "exc_median": float(np.median(ex)), "win": float((ex > 0).mean()), "first": d.date.min(), "last": d.date.max(),
                      "ci_ref": boot(ex) if len(d) >= 4 else None, "worst": float(ex.min()), "best": float(ex.max())}
        # [2026-10-02] 시장별 분해(참고) — 그 시장 바스켓이 성립한 매수일만. 4일 미만이면 싣지 않는다. 판정은 나누지 않는다.
        bm = {}
        for mkt in ("kospi", "kosdaq"):
            v = np.array([p[mkt] for p in d.pm if isinstance(p, dict) and mkt in p], float)
            if len(v) >= 4:
                bm[mkt] = {"n": int(len(v)), "exc_mean": float(v.mean()), "win": float((v > 0).mean())}
                rb = np.array([p["_" + mkt] for p in d.pm if isinstance(p, dict) and ("_" + mkt) in p], float)
                if len(rb): bm[mkt]["ret_mean"] = float(rb[:, 0].mean()); bm[mkt]["bench_mean"] = float(rb[:, 1].mean())
        out["fix"]["by_market"] = bm
    else:
        out["fix"] = None
    t_reg = next((i for i, dd in enumerate(dates) if dd >= reg), None)
    if t_reg is not None:
        need = (t_reg + 1 + H) - (N - 1)
        out["first_done_eta"] = _eta(dates[-1], need) if need > 0 else None   # [2026-10-03] 거래일 달력(주말·skip_dates 제외)으로
        w_end = dates[min(t_reg + H, N - 1)]
        out["verdict_window"] = f"{reg[4:6]}/{reg[6:]}~{w_end[4:6]}/{w_end[6:]}"
    dn = df.dropna(subset=["ret_now"])
    if len(dn):
        exn = (dn.ret_now - dn.bench_now).values
        out["now"] = {"n": int(len(dn)), "ret_mean": float(dn.ret_now.mean()), "ret_median": float(dn.ret_now.median()), "bench_mean": float(dn.bench_now.mean()),
                      "exc_mean": float(exn.mean()), "exc_median": float(np.median(exn)), "win": float((exn > 0).mean())}
    s = reg_json["sealed"].get(m["model"])
    out["sealed"] = ({"v": s["v"], "short": s.get("short", s["t"])} if s else None)
    # [2026-10-03] '시험 기록' 표시용 — 시험 날짜(registry 의 short/t 에 적힌 M/D)와 그 뒤에 산 매수분의 성적.
    #   그 뒤 매수분은 40일이 안 찬 것이 대부분이라 '오늘 가격 기준'(now)으로 잰다 — 참고값, 결론을 바꾸지 않는다.
    if s:
        _md = re.search(r"(\d{1,2})/(\d{1,2})", str(s.get("short") or s.get("t") or ""))
        if s.get("date"):            # [2026-10-03] registry 에 적힌 판정일(YYYYMMDD)이 정본 — 문구에서 M/D 를 뽑아 올해를 붙이는 건 폴백
            _vd = str(s["date"])
        elif _md:
            _vd = f"{dates[-1][:4]}{int(_md.group(1)):02d}{int(_md.group(2)):02d}"
        else:
            _vd = None
        if _vd:
            out["sealed"]["date"] = _vd
            _da = dn[dn.date > _vd]
            if len(_da) >= 4:
                _ex = (_da.ret_now - _da.bench_now).values
                out["after"] = {"n": int(len(_da)), "exc_mean": float(_ex.mean()), "win": float((_ex > 0).mean()),
                                "first": _da.date.min(), "last": _da.date.max()}
    out["_df"] = df   # [2026-10-03] 묶음·지금 형세 계산용(JSON 직전에 뺀다)
    h20 = m.get("h20") or {}; h5 = m.get("h5") or {}
    out["live"] = {"ic20": h20.get("ic"), "n": h20.get("n"), "ci": h20.get("ci"), "ic5": h5.get("ic"), "oos_days": m.get("oos_days")}
    _oos = m.get("oos_days")   # [2026-10-03] 순위 판정(40거래일) 예정일 — 거래일 달력 근사. 판정 끝난 모델은 없음
    out["verdict_eta"] = _eta(dates[-1], 40 - _oos) if (_oos is not None and _oos < 40 and not s and m["track"] != "large") else None
    out["retired"] = bool(m.get("retired")) or m["model"] in reg_json.get("retired", {})
    return out


# ---------------------------------------------------------------------------------------------
# [2026-10-03] 사용자 결정 1·2·3 (research/RESEARCH_form_signals_20261003.md §4):
#   ① 묶음 = 시험 기록이 '유의'·'기움'인 현역 트랙A 모델을 같은 날짜에 동일가중으로 섞은 줄(예측 불필요)
#   ② 지금 형세 = 최근 40거래일 안에 끝난 매수분의 성적(서술 전용 — "다음 달을 맞힌 기록: 자료 부족" 각주 고정)
#   ③ 국면별 기록 = 등록 후 앵커의 20일 IC 를 KOSDAQ 20일선 위/아래로 나눠 적고 지금 국면을 표시
#   전부 표시 전용 · 점수·판정 무관 · 기존 JSON 키는 그대로.
RECENT_DAYS = 40; REGIME_MIN = 5; ENSEMBLE_LABELS = ("유의", "기움")
PERSISTENCE_NOTE = ("이 칸의 숫자가 다음 달 성적을 맞힌 기록: 자료 부족(독립 20일 구간 3개) — 2027-04 재점검. "
                    "신호 후보 10개 전부 다음 20일과 관계 없음(2026-10-03 실측).")


def recent_form(df, dates, didx):
    """최근 RECENT_DAYS 거래일 안에 40일 창이 끝난 매수분. n<4 면 None."""
    N = len(dates)
    d = df[df.done.astype(bool)].copy()
    if not len(d): return None
    d["t_end"] = d.date.map(lambda x: didx.get(x, -10**6)) + 1 + H
    d = d[d.t_end >= N - RECENT_DAYS]
    if len(d) < 4: return None
    ex = (d.ret40 - d.bench40).values
    wk = pd.to_datetime(d.date, format="%Y%m%d").dt.isocalendar().week.astype(str) + "-" + pd.to_datetime(d.date, format="%Y%m%d").dt.isocalendar().year.astype(str)
    w = pd.Series(ex, index=d.index).groupby(wk.values).mean()
    bm = {}   # 시장별(참고) — 그 시장 바스켓이 성립한 매수일만, 4일 미만이면 비움
    for mkt in ("kospi", "kosdaq"):
        v = np.array([pm[mkt] for pm in d.pm if isinstance(pm, dict) and mkt in pm], float)
        if len(v) >= 4:
            bm[mkt] = {"n": int(len(v)), "exc_mean": float(v.mean()), "win": float((v > 0).mean())}
            rb = np.array([pm["_" + mkt] for pm in d.pm if isinstance(pm, dict) and ("_" + mkt) in pm], float)
            if len(rb): bm[mkt]["ret_mean"] = float(rb[:, 0].mean()); bm[mkt]["bench_mean"] = float(rb[:, 1].mean())
    return {"n": int(len(d)), "exc_mean": float(ex.mean()), "win": float((ex > 0).mean()), "ci_ref": boot(ex),
            "weeks_pos": int((w > 0).sum()), "weeks": int(len(w)), "first": d.date.min(), "last": d.date.max(), "by_market": bm}


def steadiness(df, close, mk, dates, is_large=False):
    """[2026-10-03] 꾸준함 두 숫자: ① 매수일 양수 비율(= fix.win) ② "매일 같은 금액으로 사서 계속 들고 간 계좌"가 시장보다 앞선 날의 비율.
    계좌(d) = d 까지 들어온 매수분 각각의 d 시점 수익 평균 · 시장 = 같은 날 같은 금액 전종목 동일가중(대형은 그날 후보군). 표시 전용."""
    N = len(dates); d0 = df.dropna(subset=["t"])
    if not len(d0): return None
    uni = {m: mk.index[mk == m] for m in ("kospi", "kosdaq")}
    ent = [(int(r.t) + 1, r.tops) for r in d0.itertuples() if int(r.t) + 1 < N]
    if not ent: return None
    first = min(e for e, _ in ent); exc = []
    for d in range(first, N):
        pa, pb = [], []
        for e, tops in ent:
            if e > d: continue
            r = close.iloc[d] / close.iloc[e] - 1; a = []; b = []
            for mkt, tk in tops.items():
                x = r.reindex(tk).dropna(); y = r.reindex(tk if is_large else uni[mkt]).dropna() if not is_large else x
                if len(x) >= MIN_BASKET and len(y): a.append(x.mean() * 100); b.append(y.mean() * 100)
            if a: pa.append(np.mean(a)); pb.append(np.mean(b))
        if pa: exc.append(np.mean(pa) - np.mean(pb))
    if len(exc) < 5: return None
    ex = np.array(exc)
    return {"days": int(len(ex)), "days_above": float((ex > 0).mean()), "last": float(ex[-1]), "min": float(ex.min()), "max": float(ex.max())}


def regime_money(df, regime):
    """[2026-10-03] 국면별 40일 초과(돈 단위, %p): 목록 기준일의 국면(코스닥 20일선 위=상승/아래=약세)으로 나눠 평균·양수 비율. 4일 미만 국면은 비움."""
    if regime is None: return None
    d = df[df.done.astype(bool)].copy()
    if not len(d): return None
    d["rg"] = d.date.map(lambda x: regime.loc[x] if x in regime.index else None); d["exc"] = d.ret40 - d.bench40
    out = {}
    for rg, g in d.groupby("rg"):
        if len(g) >= 4: out[rg] = {"n": int(len(g)), "exc_mean": float(g.exc.mean()), "win": float((g.exc > 0).mean()), "first": g.date.min(), "last": g.date.max()}
    return out


def load_regime(dates):
    """KOSDAQ 종가 > 20일선 → '상승', 아니면 '약세'. market_daily 없으면 None."""
    try:
        oc = sqlite3.connect(f"file:{lb.OHLCV_DB}?mode=ro", uri=True)
        kq = pd.read_sql("SELECT date, close FROM market_daily WHERE series='KOSDAQ' ORDER BY date", oc); oc.close()
        kq["date"] = kq.date.astype(str).str.replace("-", ""); kq = kq.set_index("date")["close"].astype(float)
        above = (kq > kq.rolling(20).mean()).reindex(dates)
        return above.map(lambda v: None if pd.isna(v) else ("상승" if v else "약세"))
    except Exception:
        return None


def regime_split(S, reg, close, dates, didx, excl, regime):
    """등록 후 앵커별 20일 IC(시장별 스피어만 평균, leaderboard 규약)를 국면별로. 각 n<REGIME_MIN 이면 그 국면은 없음."""
    if regime is None: return None
    N = len(dates); h = 20
    keep = lb.dedupe_by_anchor(S, didx, excl, reg=reg)
    rows = []
    for rid in sorted(keep):
        t = lb.anchor(rid, didx)
        if t is None or t + 1 + h >= N: continue
        r = close.iloc[t + 1 + h] / close.iloc[t + 1] - 1
        jump = close.pct_change(fill_method=None).abs().iloc[t + 2:t + 2 + h].max()
        r = r.where(jump <= lb.JUMP_CAP)
        ics = []
        for mkt, gm in S[S.run_id == rid].groupby("market"):
            s = gm.set_index("ticker")["score"].astype(float); bb = r.reindex(s.index); mm = s.notna() & bb.notna()
            if mm.sum() < lb.MIN_GROUP or s[mm].nunique() < 3 or bb[mm].nunique() < 3: continue
            ics.append(float(np.corrcoef(s[mm].rank(), bb[mm].rank())[0, 1]))
        if ics and regime.iloc[t]: rows.append((regime.iloc[t], float(np.mean(ics)), dates[t]))
    if not rows: return {}
    out = {}
    for rg in ("상승", "약세"):
        v = np.array([x for g, x, _ in rows if g == rg], float); ds = [d for g, _, d in rows if g == rg]
        if len(v) >= REGIME_MIN:   # first/last: 국면이 특정 시기와 겹치는지 화면에서 보이게(지금 자료는 약세=6~7월·상승=8~9월)
            out[rg] = {"n": int(len(v)), "ic": float(v.mean()), "ci": boot(v), "pos": float((v > 0).mean()), "first": min(ds), "last": max(ds)}
    return out


def ensemble(res):
    """묶음: 같은 매수일에 끝난 멤버 모델 초과(%p)의 평균(모델 동일가중). 멤버 2개 이상인 날만. 짝비교(묶음−멤버)도 적는다."""
    mem = [r for r in res if r["track"] != "large" and not r["retired"] and r.get("sealed") and r["sealed"]["v"] in ENSEMBLE_LABELS]
    if len(mem) < 2: return None
    per = {}
    for r in mem:
        d = r["_df"]; d = d[d.done.astype(bool)]
        per[r["model"]] = pd.Series((d.ret40 - d.bench40).values, index=d.date.values)
    tab = pd.DataFrame(per)
    tab = tab[tab.notna().sum(axis=1) >= 2].sort_index()
    if len(tab) < 4: return None
    mix = tab.mean(axis=1)
    pairs = {}
    for mname in tab.columns:
        c = tab[mname].dropna(); dd = (mix.reindex(c.index) - c).values
        if len(dd) >= 4: pairs[mname] = {"n": int(len(dd)), "diff_mean": float(dd.mean()), "ci_ref": boot(dd)}
    ex = mix.values
    return {"members": [m["model"] for m in mem], "names": [m["name"] for m in mem],
            "fix": {"n": int(len(ex)), "blocks": round(len(ex) / H, 1), "exc_mean": float(ex.mean()), "exc_median": float(np.median(ex)),
                    "win": float((ex > 0).mean()), "ci_ref": boot(ex), "first": str(tab.index.min()), "last": str(tab.index.max()),
                    "worst": float(ex.min()), "best": float(ex.max())},
            "pairs": pairs,
            "rule": "시험 기록이 '효과 확인됨'·'확정 못 함'인 현역 트랙A 모델을 같은 매수일에 같은 금액씩 — 어느 모델이 앞설지 고르지 않는다"}


def main():
    close, mktmap = lb.load_ohlcv(); dates = list(close.index)
    mk = pd.Series(mktmap).str.lower()
    con = sqlite3.connect(f"file:{HERE/'history.db'}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    lbj = json.loads((HERE / "docs/leaderboard.json").read_text(encoding="utf-8"))
    reg_json = json.loads((HERE / "docs/models_registry.json").read_text(encoding="utf-8"))
    # [2026-10-03 Codex 검토 반영] 대형(ls_t1)만 보충 시세(daily_ohlcv_extra)를 합친 close 로 — 리더보드 ls_t1 블록과 같은 경로. 트랙 A 는 본 표 그대로(0-diff).
    close_lg = close
    try:
        import extra_ohlcv
        ex = extra_ohlcv.load_extra_close(lb.OHLCV_DB, exclude=set(close.columns))
        if len(ex): close_lg = close.join(ex.reindex(close.index), how="left")
    except Exception as e:
        print(f"   ⚠ 대형 보충 시세 생략(비치명): {e}")
    res = [observe(con, m, (close_lg if m["track"] == "large" else close), mk, dates, didx, excl, reg_json) for m in lbj["models"] if m["model"] in NAME]
    regime = load_regime(dates)
    for r, m in zip(res, [m for m in lbj["models"] if m["model"] in NAME]):
        try:
            r["recent"] = recent_form(r["_df"], dates, didx)
            r["steady"] = steadiness(r["_df"], close, mk, dates) if m["track"] != "large" else None   # 대형은 후보군(large_final) 비교라 여기선 생략
            if r.get("fix") and r["steady"]: r["steady"]["pos_share"] = r["fix"]["win"]
            r["regime_money"] = regime_money(r["_df"], regime)
            r["regime"] = regime_split(load_scores(con, m), m["reg_date"], close, dates, didx, excl, regime) if m["track"] != "large" else None
        except Exception as e:
            r["recent"] = None; r["regime"] = None; r["steady"] = None; r["regime_money"] = None; print(f"   ⚠ {m['model']} 지금 형세/국면 생략(비치명): {e}")
    con.close()
    try:
        ens = ensemble(res)
    except Exception as e:
        ens = None; print(f"   ⚠ 묶음 생략(비치명): {e}")
    for r in res: r.pop("_df", None)
    res.sort(key=lambda r: (r["track"] == "large", r["retired"], -(r["fix"]["exc_mean"] if r["fix"] and r["fix"]["n"] >= 4 else -99)))   # 은퇴는 트랙 맨 아래
    payload = {"asof": dates[-1], "generated": datetime.now().isoformat(timespec="seconds"), "H": H, "TOP": TOP, "COST": COST,
               "note": "참고 성적 · 검증 결론 아님 · 사전등록 v5 와 뼈대 동일하나 희석 제외·PIT·블록 CI 미적용", "models": res,
               "ensemble": ens, "regime_now": (regime.iloc[-1] if regime is not None else None), "recent_days": RECENT_DAYS,
               "persistence_note": PERSISTENCE_NOTE}
    (HERE / "docs" / "scoreboard.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    done = sum(1 for r in res if r["fix"] and r["fix"]["n"] >= 4)
    print(f"  ✓ docs/scoreboard.json — {len(res)}모델 (40일 완결 4일↑ {done}개) · {dates[-1]} 기준")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠ scoreboard 생성 실패(비치명): {e}")
        sys.exit(1)   # [2026-09-21] 조용히 낡는 것 방지 — .bat 의 FAILED 에 잡혀 텔레그램 🔔(표시 전용 단계라 첫 줄은 안 바뀜)
