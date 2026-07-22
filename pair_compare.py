# -*- coding: utf-8 -*-
"""
pair_compare.py — 같은 트랙 내 모델 paired 비교 (오프라인, 관측 전용)
====================================================================
왜: leaderboard 는 모델별 '단독 IC'만 보여준다. 등록일이 다르면 표본 기간이 달라
    단독 IC 나란히 놓기는 무의미하고, 같은 기간이어도 시장 국면 노이즈가 섞인다.
    → 해결: '공통 날짜 교집합'에서 날짜별 IC 차이 d_t = IC_모델(t) − IC_베이스(t)를
    paired 로 잰다. 공통 시장 노이즈가 상쇄되어 n 이 작아도 CI 가 훨씬 좁다.

원칙(프로젝트 규칙 그대로):
  - leaderboard.py 의 게이트/앵커/중복제거/REG_DATE/IC 사상을 그대로 import (프로토콜 동일).
  - history.db·ohlcv.db 읽기 전용. 점수/동작 무변경 — 순수 관측 도구.
  - 트랙 간 비교는 여전히 금지. 이 도구는 '같은 트랙 안'만 비교한다.
  - n<40 이면 판정이 아니라 '기움(lean)'까지만. CI 는 부트스트랩(날짜 paired 리샘플).
  - 유사도(score_sim)≈1.0 + ΔIC=0 은 '버킷형 챌린저'(랭킹 동일) — IC 비교 자체가
    무의미하므로 '동일랭킹'으로 표시. 그런 모델은 compare_models.py 의 BUY/WAIT
    수익으로 봐야 한다.

실행:  cd <repo> && python pair_compare.py                    # 전 트랙, 기본 베이스
       python pair_compare.py --track v3 --base v30           # 트랙·베이스 지정
산출:  콘솔 표 + (스크립트 옆) pair_compare.json
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(os.environ.get("REPO", ".")).resolve()
sys.path.insert(0, str(REPO))
import leaderboard as lb  # noqa: E402  (동일 프로토콜 재사용)

BASE_DEFAULT = {"v3": "v30", "lowvol": "lv_a", "wu": "wu_a"}
BOOT = 2000
# 산출: repo/docs 가 있으면 그쪽(leaderboard.json 과 동일 관례), 없으면 스크립트 옆
OUT = (REPO / "docs" / "pair_compare.json") if (REPO / "docs").is_dir() \
    else Path(__file__).resolve().parent / "pair_compare.json"


def build_fwd_cache(close, chg, N):
    cache = {}

    def fwd(t, h):
        key = (t, h)
        if key in cache:
            return cache[key]
        if t + lb.ENTRY_LAG + h >= N:
            cache[key] = None
            return None
        f = close.iloc[t + lb.ENTRY_LAG + h] / close.iloc[t + lb.ENTRY_LAG] - 1
        jump = chg.iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + h + 1].max()
        cache[key] = f.where(jump <= lb.JUMP_CAP)
        return cache[key]

    return fwd


def day_ic(g, fwd_series):
    """leaderboard.model_ic 내부와 동일 사상: 시장별 cross-sectional Spearman 평균."""
    ics = []
    for _mk, gm in g.groupby("market"):
        s = gm.set_index("ticker")["score"].astype(float)
        s.index = s.index.astype(str)
        b = fwd_series.reindex(s.index)
        m = s.notna() & b.notna()
        if m.sum() < lb.MIN_GROUP or s[m].nunique() < 3 or b[m].nunique() < 3:
            continue
        ics.append(np.corrcoef(s[m].rank(), b[m].rank())[0, 1])
    return float(np.mean(ics)) if ics else None


def boot_ci(arr):
    rng = np.random.default_rng(7)
    boots = [rng.choice(arr, len(arr)).mean() for _ in range(BOOT)]
    return [round(float(np.percentile(boots, 2.5)), 4),
            round(float(np.percentile(boots, 97.5)), 4)]


MIN_PAIR_N = 5  # 이보다 적으면 paired 라도 부트스트랩이 퇴화(n=1이면 CI 폭 0) — 표본부족


def pair_verdict(n, dic, ci, sim):
    if dic is None:
        return "n/a"
    if sim is not None and sim > 0.9995 and abs(dic) < 1e-6:
        return "동일랭킹"
    if n < MIN_PAIR_N:
        return "표본부족"
    lo, hi = ci
    if lo is not None and lo > 0:
        return "우세" if n >= lb.MIN_OOS else "우세기움"
    if hi is not None and hi < 0:
        return "열세" if n >= lb.MIN_OOS else "열세기움"
    return "차이없음"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default=None)
    ap.add_argument("--base", default=None)
    args = ap.parse_args()

    close, _ = lb.load_ohlcv()
    dates = list(close.index)
    N = len(dates)
    chg = close.pct_change(fill_method=None).abs()
    fwd = build_fwd_cache(close, chg, N)

    con = sqlite3.connect(f"file:{lb.DB}?mode=ro", uri=True)
    partial, dbl, didx = lb.build_gates(con, dates)
    excl = partial | dbl
    print(f"[pair] 게이트 제외: 부분실행 {sorted(partial)} · 이중실행 {sorted(dbl)}")

    tracks = [args.track] if args.track else list(lb.TRACKS)
    results = []
    for trk in tracks:
        tb, sc, _ = lb.TRACKS[trk]
        base = args.base if (args.track and args.base) else BASE_DEFAULT[trk]
        mids = [m for (m,) in con.execute(f"SELECT DISTINCT model_id FROM {tb}")]
        if base not in mids:
            print(f"[pair] {trk}: 베이스 {base} 없음 — 건너뜀")
            continue

        # 모델별 점수 로드 + keep(게이트·등록일·중복제거) + 앵커맵 + 날짜별 IC
        data = {}
        for mid in mids:
            s = pd.read_sql(
                f"SELECT run_id, market, ticker, {sc} AS score FROM {tb} WHERE model_id=?",
                con, params=(mid,))
            s["run_id"] = s["run_id"].astype(str)
            s["ticker"] = s["ticker"].astype(str)
            keep = lb.dedupe_by_anchor(s, didx, excl, reg=lb.REG_DATE.get(mid))
            amap = {}
            for rid in keep:
                t = lb.anchor(rid, didx)
                if t is not None:
                    amap[t] = rid
            icmap = {h: {} for h in lb.HORIZONS}
            for t, rid in amap.items():
                g = s[s["run_id"] == rid]
                for h in lb.HORIZONS:
                    f = fwd(t, h)
                    if f is not None:
                        ic = day_ic(g, f)
                        if ic is not None:
                            icmap[h][t] = ic
            data[mid] = dict(scores=s, amap=amap, icmap=icmap)

        sb = data[base]
        for mid in mids:
            if mid == base:
                continue
            sm = data[mid]
            common_anchor = sorted(set(sb["amap"]) & set(sm["amap"]))
            row = dict(track=trk, model=mid, base=base,
                       n_common_days=len(common_anchor))

            # 점수 유사도(랭킹): 공통 날짜·시장·종목에서 모델 간 Spearman 평균
            sims = []
            for t in common_anchor:
                gb = sb["scores"][sb["scores"]["run_id"] == sb["amap"][t]]
                gm = sm["scores"][sm["scores"]["run_id"] == sm["amap"][t]]
                for mk in set(gb["market"]) & set(gm["market"]):
                    x = gb[gb["market"] == mk].set_index("ticker")["score"].astype(float)
                    y = gm[gm["market"] == mk].set_index("ticker")["score"].astype(float)
                    x = x[~x.index.duplicated()]
                    y = y[~y.index.duplicated()]
                    ix = x.index.intersection(y.index)
                    if len(ix) >= lb.MIN_GROUP and x[ix].nunique() > 2 and y[ix].nunique() > 2:
                        sims.append(np.corrcoef(x[ix].rank(), y[ix].rank())[0, 1])
            row["score_sim"] = round(float(np.mean(sims)), 4) if sims else None

            for h in lb.HORIZONS:
                ts = sorted(set(sb["icmap"][h]) & set(sm["icmap"][h]))
                if not ts:
                    row[f"h{h}"] = dict(n=0, dic=None, ci=[None, None], win=None,
                                        ic_model=None, ic_base=None)
                    continue
                im = np.array([sm["icmap"][h][t] for t in ts])
                ib = np.array([sb["icmap"][h][t] for t in ts])
                d = im - ib
                row[f"h{h}"] = dict(
                    n=len(d), dic=round(float(d.mean()), 4), ci=boot_ci(d),
                    win=round(float((d > 0).mean()), 3),
                    ic_model=round(float(im.mean()), 4),
                    ic_base=round(float(ib.mean()), 4))
            hp = row[f"h{lb.H_PRIMARY}"]
            row["verdict"] = pair_verdict(hp["n"], hp["dic"], hp["ci"], row["score_sim"])
            results.append(row)

    con.close()

    results.sort(key=lambda r: (r["track"],
                                -(r[f"h{lb.H_PRIMARY}"]["dic"] or -9)))
    OUT.write_text(json.dumps(dict(
        status="ok",
        note=("paired ΔIC = 모델 − 베이스, 공통 날짜 교집합. 트랙 간 비교 금지. "
              f"n<{lb.MIN_OOS}일은 '기움'까지만. 동일랭킹=버킷형 → compare_models 로."),
        results=results), ensure_ascii=False, indent=2), encoding="utf-8")

    hp = f"h{lb.H_PRIMARY}"
    print(f"\n{'트랙':6s} {'모델vs베이스':14s} {'n':>3s} {'ΔIC(h20)':>9s} {'95%CI':>18s}"
          f" {'승률':>5s} {'IC모델/베이스':>15s} {'ΔIC(h5,보조)':>26s} {'유사도':>6s} {'판정':>6s}")
    for r in results:
        p = r[hp]
        dic = f"{p['dic']:+.4f}" if p["dic"] is not None else "n/a"
        ci = f"[{p['ci'][0]:+.3f},{p['ci'][1]:+.3f}]" if p["ci"][0] is not None else "-"
        win = f"{p['win']:.0%}" if p["win"] is not None else "-"
        mb = (f"{p['ic_model']:+.3f}/{p['ic_base']:+.3f}"
              if p["ic_model"] is not None else "-")
        a = r["h5"]
        if a["dic"] is not None:
            d5 = f"{a['dic']:+.4f} CI[{a['ci'][0]:+.2f},{a['ci'][1]:+.2f}] n={a['n']}"
        else:
            d5 = "n/a"
        sim = f"{r['score_sim']:.3f}" if r["score_sim"] is not None else "-"
        print(f"{r['track']:6s} {r['model']+'vs'+r['base']:14s} {p['n']:3d} {dic:>9s}"
              f" {ci:>18s} {win:>5s} {mb:>15s} {d5:>26s} {sim:>6s} {r['verdict']:>6s}")
    print(f"\n※ 같은 트랙 안에서만 유효 · ΔIC>0 = 모델이 베이스보다 우세 · "
          f"n<{lb.MIN_OOS}일은 판정 아닌 '기움' · 동일랭킹은 compare_models 의 버킷수익으로")


if __name__ == "__main__":
    main()
