# -*- coding: utf-8 -*-
"""모델별 '첫 주 우상향' 비율 — 리더보드 틀 그대로(게이트·앵커 중복 제거·등록일 이후·t+1 종가 진입), 읽기 전용 (2026-11-10).
리더보드는 h5 IC 와 상위 20 시장초과(exc5)를 관측용으로 저장한다. 여기선 사용자 질문("5일 내에 사서 우상향")에 맞춰
① 시장별 상위 10(실제 산 종목 수) 의 5일째 진입가 위 비율(up5) ② 같은 날 유니버스 전체의 up5(기준율) ③ 상위 10 평균 5일 수익과 유니버스 중앙값 초과
④ 경로: 5일 중 종가가 진입가 아래로 한 번도 안 간 비율(path5). 앵커 iid 부트스트랩 2,000회 seed 7(리더보드와 같은 방식).
재현: python research/first_week_by_model_20261110.py → research/out_first_week/by_model.csv · stdout.txt"""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE))
import leaderboard as LB

H = 5; TOP = 10; OUT = Path(__file__).resolve().parent / "out_first_week"; OUT.mkdir(exist_ok=True)
t0 = time.time()
close, mkt = LB.load_ohlcv(); N = len(close); con = sqlite3.connect(f"file:{LB.DB}?mode=ro", uri=True)
partial, dbl, didx = LB.build_gates(con, close.index); excl = partial | dbl
print(f"가격 {N}일 · 게이트 제외 run {sorted(excl)}")
rows = []
for track, (tb, sc, _) in LB.TRACKS.items():
    S = pd.read_sql(f"SELECT run_id, market, ticker, model_id, {sc} AS score FROM {tb}", con)
    S["run_id"] = S.run_id.astype(str); S["market"] = S.market.str.upper(); S["ticker"] = S.ticker.astype(str)
    for mid, sm in S.groupby("model_id"):
        reg = LB.REG_DATE.get(mid); keep = LB.dedupe_by_anchor(sm, didx, excl, reg=reg)
        per = []
        for rid, g in sm.groupby("run_id"):
            if rid in excl or rid not in keep: continue
            t = LB.anchor(rid, didx)
            if t is None or t + LB.ENTRY_LAG + H >= N: continue
            e = close.iloc[t + LB.ENTRY_LAG]; path = close.iloc[t + LB.ENTRY_LAG + 1:t + LB.ENTRY_LAG + H + 1]
            fwd = path.iloc[-1] / e - 1
            jump = close.pct_change(fill_method=None).abs().iloc[t + LB.ENTRY_LAG + 1:t + LB.ENTRY_LAG + H + 1].max()
            fwd = fwd.where(jump <= LB.JUMP_CAP)
            pathok = (path.min() / e >= 1.0)        # 5일 중 종가가 진입가 아래로 한 번도 안 감(진입가 = 0일째)
            d = dict(run_id=rid)
            vals = []
            for m_, gm in g.groupby("market"):
                s = gm.set_index("ticker")["score"].astype(float); b = fwd.reindex(s.index); ok = s.notna() & b.notna()
                if ok.sum() < LB.MIN_GROUP: continue
                top = s[ok].sort_values(ascending=False).head(TOP).index
                vals.append(dict(up=(b[top] > 0).mean(), base=(b[ok] > 0).mean(), ret=b[top].mean(), exc=b[top].mean() - b[ok].median(),
                                 path=pathok.reindex(top).fillna(False).mean(), pbase=pathok.reindex(s[ok].index).fillna(False).mean()))
            if not vals: continue
            for k in vals[0]: d[k] = float(np.mean([v[k] for v in vals]))
            per.append(d)
        if not per: continue
        P = pd.DataFrame(per); rng = np.random.default_rng(7)
        def ci(x):
            x = x.values; bo = [rng.choice(x, len(x)).mean() for _ in range(LB.BOOT)]; return float(np.percentile(bo, 2.5)), float(np.percentile(bo, 97.5))
        ulo, uhi = ci(P.up); dlo, dhi = ci(P.up - P.base); elo, ehi = ci(P.exc); plo, phi = ci(P.path)
        rows.append(dict(track=track, model=mid, reg=reg, retired=(mid in LB.RETIRED), n=len(P), 첫앵커=P.run_id.min(), 끝앵커=P.run_id.max(),
                         up5=P.up.mean() * 100, up5하한=ulo * 100, up5상한=uhi * 100, 기준율=P.base.mean() * 100,
                         차=(P.up - P.base).mean() * 100, 차하한=dlo * 100, 차상한=dhi * 100,
                         수익5=P.ret.mean() * 100, 초과5=P.exc.mean() * 100, 초과하한=elo * 100, 초과상한=ehi * 100,
                         경로5=P.path.mean() * 100, 경로하한=plo * 100, 경로상한=phi * 100, 경로기준=P.pbase.mean() * 100,
                         up5_60이상_날비율=(P.up >= 0.6).mean() * 100))
        print(f"  {track}/{mid} n={len(P)} up5 {P.up.mean()*100:.1f} 기준 {P.base.mean()*100:.1f} · {time.time()-t0:.0f}s", flush=True)
T = pd.DataFrame(rows).sort_values("차", ascending=False); T.to_csv(OUT / "by_model.csv", index=False, encoding="utf-8-sig")
pd.set_option("display.width", 250)
print("\n### 시장별 상위 10 · 5일째 진입가 위 비율(up5, %) vs 같은 날 유니버스(기준율) · 앵커 iid 95%")
print(T[["track", "model", "retired", "n", "첫앵커", "up5", "up5하한", "up5상한", "기준율", "차", "차하한", "차상한", "수익5", "초과5", "초과하한", "초과상한", "경로5", "경로기준", "up5_60이상_날비율"]].round(1).to_string(index=False))
print(f"\n{time.time()-t0:.0f}s")
