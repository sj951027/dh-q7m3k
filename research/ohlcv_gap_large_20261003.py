# -*- coding: utf-8 -*-
"""
ohlcv_gap_large_20261003.py — 대형 트랙(ls_t1) 판정 전, 시세(ohlcv.db) 결손 종목이 표본에서 어떻게 빠지는지 세기.
읽기 전용(history.db·ohlcv.db mode=ro). 점수·판정·DB 무영향. 산출: research/RESEARCH_ohlcv_gap_large_20261003.md

리더보드(leaderboard.py model_ic)와 같은 방식으로 본다:
  앵커 = run_id 거래일, 매수 = 앵커+1(ENTRY_LAG) 종가, h거래일 뒤 종가 → 선행수익.
  선행수익이 NaN(가격 없음)인 종목은 IC 계산에서 **조용히 제외**된다(m = s.notna() & b.notna()).
여기서는 등록일(20260806) 이후 앵커마다 ls_t1 점수가 있는 종목 중
  (a) ohlcv 에 아예 없는 종목, (b) 앵커+1 가격 없음, (c) h 뒤 가격 없음(아직 미래면 '대기')
를 시장별로 세고, 빠지는 종목의 시총 비중·점수 분포(상/하위)를 적는다.
"""
import sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent.parent
HIST = HERE / "history.db"
OHLCV = HERE / ".." / "dh-q7m3k-data" / "ohlcv.db"
OUT = HERE / "research" / "RESEARCH_ohlcv_gap_large_20261003.md"
REG = "20260806"; ENTRY_LAG = 1; HS = [20, 60, 120]


def main():
    con = sqlite3.connect(f"file:{HIST}?mode=ro", uri=True)
    lg = pd.read_sql("SELECT run_id, market, ticker, name, marcap, marcap_rank, per, pbr, rim_spread, div_yield "
                     "FROM large_final", con)
    con.close()
    lg["ticker"] = lg["ticker"].astype(str).str.zfill(6)
    fz = pd.DataFrame(index=lg.index)
    fz["ep"] = 1.0 / lg["per"].where(lg["per"] > 0)
    fz["bp"] = 1.0 / lg["pbr"].where(lg["pbr"] > 0)
    fz["rim"] = lg["rim_spread"]; fz["dv"] = lg["div_yield"]
    rk = fz.groupby(lg["run_id"]).rank(pct=True)
    lg["score"] = rk.mean(axis=1).where(rk.notna().sum(axis=1) >= 2)
    s = lg.dropna(subset=["score"]).copy()
    s = s[s["run_id"] >= REG]

    oc = sqlite3.connect(f"file:{OHLCV}?mode=ro", uri=True)
    px = pd.read_sql("SELECT ticker, date, close FROM daily_ohlcv", oc)
    oc.close()
    px["ticker"] = px["ticker"].astype(str)
    close = px.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    dates = list(close.index); didx = {d: i for i, d in enumerate(dates)}; N = len(dates)
    have = set(close.columns)

    def anchor(rid):
        if rid in didx: return didx[rid]
        prev = [d for d in dates if d < rid]
        return didx[prev[-1]] if prev else None

    lines = [f"# 대형 트랙 시세 결손 조사 — ls_t1 판정 전 (2026-10-03, 읽기 전용)", "",
             f"- 기준: `large_final` 등록일 {REG} 이후 앵커 {s['run_id'].nunique()}개, ls_t1 점수 있는 종목만. "
             f"시세 = `ohlcv.db` daily_ohlcv({dates[0]}~{dates[-1]}, 종목 {len(have):,}).",
             "- 리더보드 IC 계산과 같은 규칙(앵커+1 매수, h거래일 뒤 종가). 가격이 없는 종목은 IC에서 **조용히 빠진다**.", ""]

    # (a) 아예 없는 종목 — 전체 앵커 합집합
    allt = s.drop_duplicates("ticker")[["ticker", "name", "market", "marcap"]]
    miss = allt[~allt["ticker"].isin(have)]
    alpha = miss[miss["ticker"].str.contains(r"[A-Za-z]")]
    lines += ["## 1. ohlcv 에 아예 없는 종목 (등록일 이후 한 번이라도 점수가 있던 종목 기준)",
              f"- 전체 {len(allt)}종목 중 **{len(miss)}종목** 없음 — 시장별: " +
              ", ".join(f"{m} {n}" for m, n in miss["market"].value_counts().items()) +
              f" · 코드에 영문 포함 {len(alpha)}종목.", ""]
    if len(miss):
        lines += ["| 코드 | 종목 | 시장 | 시총(조, 마지막 앵커) |", "|---|---|---|---|"]
        for _, r in miss.sort_values("marcap", ascending=False).head(60).iterrows():
            lines.append(f"| {r.ticker} | {r['name']} | {r.market} | {r.marcap/1e12:.2f} |")
        if len(miss) > 60: lines.append(f"| … | 외 {len(miss)-60}종목 | | |")
        lines.append("")

    # (b)(c) 앵커별 — h 별로 표본에서 빠지는 수
    lines += ["## 2. 앵커별로 IC 표본에서 빠지는 종목 수 (시장별)", "",
              "h 열: `빠짐/전체` — 빠짐 = 앵커+1 또는 h뒤 가격이 없는 종목(점프컷 제외). '대기' = h뒤 날짜가 아직 안 옴.", ""]
    hdr = "| 앵커 | 시장 | 점수 종목 | 시세 없음 | " + " | ".join(f"h{h}" for h in HS) + " | 빠진 시총 비중 |"
    lines += [hdr, "|" + "---|" * (hdr.count("|") - 1)]
    summ = {h: [] for h in HS}
    gap_scores = []
    for rid, g in s.groupby("run_id"):
        t = anchor(rid)
        if t is None: continue
        for mk, gm in g.groupby("market"):
            tk = gm["ticker"]
            nomk = ~tk.isin(have)
            cells = []
            for h in HS:
                if t + ENTRY_LAG + h >= N:
                    cells.append("대기"); continue
                b = close.iloc[t + ENTRY_LAG + h] / close.iloc[t + ENTRY_LAG] - 1
                b = b.reindex(tk.values)
                drop = b.isna().values
                cells.append(f"{int(drop.sum())}/{len(gm)}")
                summ[h].append((rid, mk, int(drop.sum()), len(gm)))
                if h == 20:   # h60 은 아직 평가 가능한 앵커가 없어(등록 8/6 → 11월 초) h20 으로 같은 종목을 본다 — 빠지는 종목은 '시세 없음'이라 h 와 무관
                    gap_scores.append(gm.assign(drop=drop))
            # 시총 비중: 시세 없는 종목 기준
            w = gm.loc[nomk, "marcap"].sum() / gm["marcap"].sum() * 100 if gm["marcap"].sum() else float("nan")
            lines.append(f"| {rid} | {mk} | {len(gm)} | {int(nomk.sum())} | " + " | ".join(cells) + f" | {w:.1f}% |")
    lines.append("")

    # 요약
    lines += ["## 3. 요약", ""]
    for h in HS:
        rows = summ[h]
        if not rows:
            lines.append(f"- h{h}: 아직 평가 가능한 앵커 없음(전부 대기)."); continue
        df = pd.DataFrame(rows, columns=["rid", "mk", "drop", "n"])
        for mk, d in df.groupby("mk"):
            lines.append(f"- h{h} {mk}: 앵커 {d['rid'].nunique()}개, 평균 빠짐 {d['drop'].mean():.1f}/{d['n'].mean():.0f} "
                         f"({d['drop'].sum()/d['n'].sum()*100:.1f}%), 최대 {d['drop'].max()}.")
    if gap_scores:
        gs = pd.concat(gap_scores)
        gs["rank_pct"] = gs.groupby(["run_id", "market"])["score"].rank(pct=True)
        d = gs[gs["drop"]]
        k = gs[~gs["drop"]]
        lines += ["", "### 빠지는 종목의 점수 위치 (h20 평가 가능 앵커 기준 — 빠지는 종목은 시세가 아예 없어 h60·h120 에서도 같은 종목)",
                  f"- 빠진 종목의 ls_t1 백분위 평균 {d['rank_pct'].mean():.2f} (남은 종목 {k['rank_pct'].mean():.2f}). "
                  f"상위 20% 안에 든 비율: 빠진 {(d['rank_pct']>=0.8).mean()*100:.0f}% vs 남은 {(k['rank_pct']>=0.8).mean()*100:.0f}%.",
                  f"- 빠진 종목 시총 중앙값 {d['marcap'].median()/1e12:.2f}조 vs 남은 {k['marcap'].median()/1e12:.2f}조.",
                  "- 읽는 법: 빠진 쪽이 한쪽(상위/하위)으로 몰려 있으면 IC가 치우칠 수 있다. 고르게 섞여 있으면 표본만 줄어든다."]
    lines += ["", "## 4. 원인 (실측)",
              "- 시세 수집(`universe_ohlcv.py get_universe`)은 FDR 상장목록에서 **Market 이 정확히 KOSPI/KOSDAQ 이고 코드가 숫자 6자리**인 종목만 담는다.",
              "- 그래서 **코스닥 글로벌 세그먼트(Market='KOSDAQ GLOBAL', 약 50종목 — 알테오젠·에코프로·에코프로비엠·주성엔지니어링 …)** 와 "
              "**영문이 섞인 신규 코드(86종목 — 0126Z0 삼성에피스홀딩스 등)** 가 시세 DB에 아예 없다.",
              "- 같은 사실이 2026-09-11 수급 수집(`kis_flows.py`)에서 이미 확인돼 수급만 상장목록으로 보충했고, 시세 유니버스는 "
              "lowvol·wu 모델의 유니버스가 바뀌는 문제라 **일부러 건드리지 않았다**(그 주석 그대로).",
              "- 대형 트랙은 `large_final` 에 점수가 있어도 시세가 없으면 선행수익을 못 구해 IC 에서 빠진다 — 코스닥 쪽은 시총 상위가 통째로 빠지는 셈이라 "
              "'고르게 빠짐'이 아니다.",
              "", "## 5. 이 조사가 말하지 않는 것",
              "- 결손 종목을 채웠을 때 IC가 어떻게 바뀔지는 모른다(가격이 없으니). 판정문에는 '시세 없음 n종목 제외'를 각주로 적는 용도.",
              "- 결손 원인(상장 코드 형식·수집기 범위)은 여기서 다루지 않는다."]
    # [2026-10-03 (a)안 적용 후] 보충 표 daily_ohlcv_extra 를 본 표 우선으로 합쳤을 때 같은 수를 다시 센다.
    try:
        sys.path.insert(0, str(HERE))
        import extra_ohlcv
        ex = extra_ohlcv.load_extra_close(str(OHLCV), exclude=set(close.columns))
    except Exception as e:
        ex = None; lines += ["", f"## 6. 보충 후 — 보충 표 읽기 실패: {e}"]
    if ex is not None and len(ex):
        close2 = close.join(ex.reindex(close.index), how="left")
        have2 = set(close2.columns)
        miss2 = allt[~allt["ticker"].isin(have2)]
        rows2 = []
        for rid, g in s.groupby("run_id"):
            t = anchor(rid)
            if t is None or t + ENTRY_LAG + 20 >= N: continue
            for mk, gm in g.groupby("market"):
                b = (close2.iloc[t + ENTRY_LAG + 20] / close2.iloc[t + ENTRY_LAG] - 1).reindex(gm["ticker"].values)
                rows2.append((rid, mk, int(b.isna().sum()), len(gm)))
        df2 = pd.DataFrame(rows2, columns=["rid", "mk", "drop", "n"])
        lines += ["", "## 6. 보충 후 (daily_ohlcv_extra 를 본 표 우선으로 합침 — extra_ohlcv.py, 사용자 결정 (a)안)",
                  f"- 보충 표: {ex.shape[1]}종목 {ex.index.min()}~{ex.index.max()}. 시세가 아예 없는 종목 {len(miss)} → **{len(miss2)}**."]
        for mk, d in df2.groupby("mk"):
            lines.append(f"- h20 {mk}: 평균 빠짐 {d['drop'].mean():.1f}/{d['n'].mean():.0f} ({d['drop'].sum()/d['n'].sum()*100:.1f}%) — 남은 빠짐은 가격 결측·점프컷.")
        lines += ["- 리더보드 ls_t1 참고값(h20, 앵커 16일) 전후: IC +0.0614 → +0.0612 · 상위20 시장초과 +0.76%p → +1.75%p (실측 2026-10-03, 다른 25개 모델 0-diff)."]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")
    print("\n".join(lines[:8]))
    print("\n".join(l for l in lines if l.startswith("- h")))


if __name__ == "__main__":
    main()
